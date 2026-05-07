from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from reviewgraph.github import (
    GitHubPRRef,
    GitHubReadResult,
    parse_github_pr_ref,
    read_github_pr_with_paginated_fake_transport,
)
from reviewgraph.read_gaps import FailClosedReadOutcome
from reviewgraph.read_gaps import build_fail_closed_read_outcome, classify_github_read_gap
from reviewgraph.redaction import redact_data, redact_text


LIVE_READ_OPT_IN_ENV = "REVIEWGRAPH_LIVE_READ"
LIVE_READ_PR_ENV = "REVIEWGRAPH_LIVE_READ_PR"
LIVE_READ_OUT_ENV = "REVIEWGRAPH_LIVE_READ_OUT"
_TOKEN_ENVS = ("GITHUB_TOKEN", "GH_TOKEN")
_DEFAULT_TIMEOUT_SECONDS = 20
_DEFAULT_PER_PAGE = 100
_DEFAULT_MAX_PAGES = 5
_READ_ONLY_REST_RESOURCE_RE = re.compile(
    r"^repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/"
    r"(?:pulls/[1-9][0-9]*|pulls/[1-9][0-9]*/files|issues/[1-9][0-9]*/comments|"
    r"pulls/[1-9][0-9]*/comments|pulls/[1-9][0-9]*/reviews)"
    r"(?:\?per_page=[1-9][0-9]*&page=[1-9][0-9]*)?$"
)


@dataclass(frozen=True)
class GhCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class GhCommandRunner(Protocol):
    def run(self, args: tuple[str, ...], *, timeout_seconds: int, env: Mapping[str, str]) -> GhCommandResult: ...


@dataclass(frozen=True)
class SubprocessGhCommandRunner:
    def run(self, args: tuple[str, ...], *, timeout_seconds: int, env: Mapping[str, str]) -> GhCommandResult:
        try:
            completed = subprocess.run(
                list(args),
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env={**dict(env), "GH_PROMPT_DISABLED": "1"},
            )
        except subprocess.TimeoutExpired as exc:
            return GhCommandResult(
                returncode=124,
                stdout=exc.stdout if isinstance(exc.stdout, str) else "",
                stderr=exc.stderr if isinstance(exc.stderr, str) else "gh command timed out",
                timed_out=True,
            )
        return GhCommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


class GhApiCommandError(RuntimeError):
    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


@dataclass(frozen=True)
class LiveReadSmokeArtifact:
    status: str
    reason: str
    pr_ref: dict[str, object] | None = None
    github_read: dict[str, object] | None = None
    fail_closed: dict[str, object] | None = None
    read_gaps: tuple[dict[str, object], ...] = ()
    page_gap_descriptors: tuple[dict[str, object], ...] = ()
    truncation_notes: tuple[dict[str, object], ...] = ()
    command_summary: dict[str, object] | None = None
    redaction_status: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        data = {
            "status": self.status,
            "reason": self.reason,
            "pr_ref": self.pr_ref,
            "github_read": self.github_read,
            "fail_closed": self.fail_closed,
            "read_gaps": list(self.read_gaps),
            "page_gap_descriptors": list(self.page_gap_descriptors),
            "truncation_notes": list(self.truncation_notes),
            "command_summary": self.command_summary or {},
            "redaction_status": self.redaction_status or _empty_redaction_status(),
        }
        redacted = redact_data(data)
        if not isinstance(redacted.data, dict):
            raise ValueError("live read smoke artifact must serialize to an object")
        redacted.data["redaction_status"] = {
            "redacted": redacted.redaction_status.redacted
            or bool((self.redaction_status or {}).get("redacted")),
            "replacement_count": redacted.redaction_status.replacement_count
            + _replacement_count(self.redaction_status),
            "categories": sorted(
                set(redacted.redaction_status.categories)
                | {
                    item
                    for item in (self.redaction_status or {}).get("categories", ())
                    if isinstance(item, str)
                }
            ),
        }
        return redacted.data


def blocked_live_read_artifact(
    *,
    env: Mapping[str, str] | None = None,
    gh_path: str | None = None,
    runner: GhCommandRunner | None = None,
) -> LiveReadSmokeArtifact | None:
    env = dict(os.environ if env is None else env)
    if env.get(LIVE_READ_OPT_IN_ENV) != "1":
        return _blocked("missing_opt_in", env=env)
    pr_ref = env.get(LIVE_READ_PR_ENV)
    if not pr_ref:
        return _blocked("missing_pr_ref", env=env)
    if gh_path is None:
        gh_path = shutil.which("gh")
    if not gh_path:
        return _blocked("missing_gh", env=env, pr_ref=_parsed_ref_or_none(pr_ref))
    if any(env.get(name) for name in _TOKEN_ENVS):
        return None
    runner = runner or SubprocessGhCommandRunner()
    token_result = runner.run((gh_path, "auth", "token"), timeout_seconds=_DEFAULT_TIMEOUT_SECONDS, env=_gh_env(env))
    if token_result.returncode != 0 or token_result.timed_out or not token_result.stdout.strip():
        return _blocked("missing_token", env=env, pr_ref=_parsed_ref_or_none(pr_ref), message=token_result.stderr)
    return None


def run_live_read_smoke(
    *,
    env: Mapping[str, str] | None = None,
    gh_path: str | None = None,
    runner: GhCommandRunner | None = None,
    output_path: str | Path | None = None,
) -> LiveReadSmokeArtifact:
    env = dict(os.environ if env is None else env)
    runner = runner or SubprocessGhCommandRunner()
    resolved_gh_path = gh_path if gh_path is not None else shutil.which("gh")
    blocked = blocked_live_read_artifact(env=env, gh_path=resolved_gh_path, runner=runner)
    if blocked is not None:
        _write_artifact_if_requested(blocked, env=env, output_path=output_path)
        return blocked
    pr_ref_text = env[LIVE_READ_PR_ENV]
    try:
        result = read_live_github_pr(
            pr_ref_text,
            runner=runner,
            env=env,
            gh_executable=resolved_gh_path or "gh",
        )
    except Exception as exc:
        artifact = _blocked("live_read_failed", env=env, pr_ref=_parsed_ref_or_none(pr_ref_text), message=str(exc))
        _write_artifact_if_requested(artifact, env=env, output_path=output_path)
        return artifact
    artifact = live_read_artifact(result, command_summary={"transport": "gh_api_rest"})
    _write_artifact_if_requested(artifact, env=env, output_path=output_path)
    return artifact


def read_live_github_pr(
    ref: str | GitHubPRRef,
    *,
    runner: GhCommandRunner,
    env: Mapping[str, str] | None = None,
    max_pages: int = _DEFAULT_MAX_PAGES,
    per_page: int = _DEFAULT_PER_PAGE,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    gh_executable: str = "gh",
) -> GitHubReadResult | FailClosedReadOutcome:
    transport = GhApiReadTransport(
        runner=runner,
        env=dict(os.environ if env is None else env),
        max_pages=max_pages,
        per_page=per_page,
        timeout_seconds=timeout_seconds,
        gh_executable=gh_executable,
    )
    pr_ref = parse_github_pr_ref(ref) if isinstance(ref, str) else ref
    try:
        return read_github_pr_with_paginated_fake_transport(transport, pr_ref)
    except Exception:
        if transport.last_error is None:
            raise
        gap = classify_github_read_gap(
            resource="metadata",
            required=True,
            reason=transport.last_error.reason,
            message=str(transport.last_error),
        )
        return build_fail_closed_read_outcome(
            pr_ref=pr_ref,
            read_gaps=(gap,),
        )


def live_read_artifact(
    result: GitHubReadResult | FailClosedReadOutcome,
    *,
    command_summary: dict[str, object] | None = None,
) -> LiveReadSmokeArtifact:
    if isinstance(result, FailClosedReadOutcome):
        data = result.to_dict()
        return LiveReadSmokeArtifact(
            status="fail_closed",
            reason="read_gap",
            pr_ref=data.get("pr_ref") if isinstance(data.get("pr_ref"), dict) else None,
            fail_closed=data,
            read_gaps=tuple(data.get("read_gaps", ())),
            page_gap_descriptors=tuple(data.get("page_gap_descriptors", ())),
            command_summary=command_summary,
            redaction_status=data.get("redaction_status") if isinstance(data.get("redaction_status"), dict) else None,
        )
    data = result.to_dict()
    return LiveReadSmokeArtifact(
        status="succeeded",
        reason="complete",
        pr_ref=data.get("pr_ref") if isinstance(data.get("pr_ref"), dict) else None,
        github_read=data,
        read_gaps=tuple(data.get("read_gaps", ())),
        page_gap_descriptors=(),
        command_summary=command_summary,
        redaction_status=data.get("redaction_status") if isinstance(data.get("redaction_status"), dict) else None,
    )


@dataclass
class GhApiReadTransport:
    runner: GhCommandRunner
    env: Mapping[str, str]
    max_pages: int = _DEFAULT_MAX_PAGES
    per_page: int = _DEFAULT_PER_PAGE
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS
    gh_executable: str = "gh"
    last_error: GhApiCommandError | None = None

    def get_pull_request(self, owner_repo: str, pr_number: int) -> dict[str, object]:
        payload = self._get_json(f"repos/{owner_repo}/pulls/{pr_number}")
        if not isinstance(payload, dict):
            raise ValueError("GitHub live PR payload must be an object")
        return _map_pull_request_payload(payload)

    def get_changed_files_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        return self._paged(
            resource=f"repos/{owner_repo}/pulls/{pr_number}/files",
            cursor=cursor,
            map_item=_map_changed_file_payload,
        )

    def get_issue_comments_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        return self._paged(
            resource=f"repos/{owner_repo}/issues/{pr_number}/comments",
            cursor=cursor,
            map_item=lambda item: _map_comment_payload(item, source_type="issue_comment"),
        )

    def get_review_comments_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        return self._paged(
            resource=f"repos/{owner_repo}/pulls/{pr_number}/comments",
            cursor=cursor,
            map_item=_map_review_comment_payload,
        )

    def get_reviews_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        return self._paged(
            resource=f"repos/{owner_repo}/pulls/{pr_number}/reviews",
            cursor=cursor,
            map_item=_map_review_payload,
        )

    def get_review_threads_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        page = _page_number(cursor)
        if page != 1:
            return {"items": [], "has_next_page": False}
        return {"items": [], "has_next_page": False}

    def _paged(self, *, resource: str, cursor: object | None, map_item: Any) -> dict[str, object]:
        page = _page_number(cursor)
        if page > self.max_pages:
            return {
                "error": {
                    "reason": "pagination_incomplete",
                    "message": f"{resource} exceeded live smoke page limit",
                }
            }
        try:
            payload = self._get_json(f"{resource}?per_page={self.per_page}&page={page}")
        except GhApiCommandError as exc:
            return {"error": {"reason": exc.reason, "message": str(exc)}}
        if not isinstance(payload, list):
            return {
                "error": {
                    "reason": "pagination_incomplete",
                    "message": f"{resource} live page must be a list",
                }
            }
        items = [map_item(item) for item in payload if isinstance(item, dict)]
        has_next_page = len(payload) == self.per_page
        result: dict[str, object] = {
            "items": items,
            "has_next_page": has_next_page,
        }
        if has_next_page:
            if page >= self.max_pages:
                return {
                    "error": {
                        "reason": "pagination_incomplete",
                        "message": f"{resource} reached live smoke page limit",
                    }
                }
            result["next_cursor"] = str(page + 1)
        return result

    def _get_json(self, resource: str) -> object:
        args = (self.gh_executable, "api", resource)
        _assert_read_only_gh_args(args, gh_executable=self.gh_executable)
        completed = self.runner.run(args, timeout_seconds=self.timeout_seconds, env=_gh_env(self.env))
        if completed.timed_out:
            error = GhApiCommandError("timeout", _redacted_text(completed.stderr or "gh api timed out"))
            self.last_error = error
            raise error
        if completed.returncode != 0:
            message = _redacted_text(completed.stderr or "gh api failed")
            error = GhApiCommandError(_reason_from_gh_failure(completed.stderr, completed.returncode), message)
            self.last_error = error
            raise error
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            error = GhApiCommandError("pagination_incomplete", f"gh api returned invalid JSON: {exc.msg}")
            self.last_error = error
            raise error from exc


def _assert_read_only_gh_args(args: tuple[str, ...], *, gh_executable: str) -> None:
    if len(args) != 3 or args[0] != gh_executable or args[1] != "api":
        raise ValueError("live read smoke may only run gh api")
    resource = args[2]
    if not _READ_ONLY_REST_RESOURCE_RE.match(resource):
        raise ValueError("live read smoke may only run REST read endpoints")


def _reason_from_gh_failure(stderr: str, returncode: int) -> str:
    text = stderr.casefold()
    if "403" in text or "forbidden" in text:
        return "forbidden"
    if "404" in text or "not found" in text:
        return "not_found"
    if "429" in text or "rate limit" in text or "rate_limited" in text:
        return "rate_limited"
    if returncode == 124 or "timed out" in text or "timeout" in text:
        return "timeout"
    return "unavailable"


def _map_pull_request_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "title": _text(payload.get("title")),
        "body": _nullable_text(payload.get("body")),
        "author": _user_login(payload.get("user")),
        "labels": [_text(item.get("name")) for item in _dict_list(payload.get("labels")) if item.get("name")],
        "base": _ref_payload(payload.get("base")),
        "head": _ref_payload(payload.get("head")),
        "merge_base_sha": None,
        "diff_basis": "merge_base",
    }


def _map_changed_file_payload(payload: dict[str, object]) -> dict[str, object]:
    return {
        "path": _text(payload.get("filename")),
        "patch": _nullable_text(payload.get("patch")),
        "additions": _non_negative_int(payload.get("additions")),
        "deletions": _non_negative_int(payload.get("deletions")),
        "status": _text(payload.get("status"), default="modified"),
        "previous_path": _nullable_text(payload.get("previous_filename")),
    }


def _map_comment_payload(payload: dict[str, object], *, source_type: str) -> dict[str, object]:
    return {
        "id": str(payload.get("id") or ""),
        "author": _user_login(payload.get("user")),
        "author_association": _text(payload.get("author_association"), default="NONE"),
        "author_type": _user_type(payload.get("user")),
        "body": _text(payload.get("body"), default=""),
        "created_at": _text(payload.get("created_at"), default=""),
        "url": _nullable_text(payload.get("html_url") or payload.get("url")),
        "source_type": source_type,
    }


def _map_review_payload(payload: dict[str, object]) -> dict[str, object]:
    body = _nullable_text(payload.get("body"))
    return {
        **_map_comment_payload(payload, source_type="review"),
        "state": _text(payload.get("state"), default="COMMENTED"),
        "created_at": _text(payload.get("submitted_at") or payload.get("created_at"), default=""),
        "body": body if body else None,
    }


def _map_review_comment_payload(payload: dict[str, object]) -> dict[str, object]:
    thread_id = payload.get("thread_id") or payload.get("pull_request_review_id") or payload.get("id")
    line = payload.get("line") or payload.get("original_line")
    mapped = {
        **_map_comment_payload(payload, source_type="review_thread"),
        "thread_id": str(thread_id or ""),
        "path": _text(payload.get("path"), default=""),
        "side": _nullable_text(payload.get("side")),
        "commit_sha": _nullable_text(payload.get("commit_id") or payload.get("original_commit_id")),
        "position": _positive_int_or_none(payload.get("position") or payload.get("original_position")),
    }
    mapped["line"] = _positive_int_or_none(line)
    return mapped


def _ref_payload(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {"ref": "", "sha": ""}
    return {
        "ref": _text(value.get("ref"), default=""),
        "sha": _text(value.get("sha"), default=""),
    }


def _page_number(cursor: object | None) -> int:
    if cursor is None:
        return 1
    if isinstance(cursor, str) and cursor.isdigit() and int(cursor) > 0:
        return int(cursor)
    raise ValueError("live read pagination cursor must be a positive page number string")


def _gh_env(env: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in env.items()
        if key in {"PATH", "HOME", "GITHUB_TOKEN", "GH_TOKEN"}
    } | {"GH_PROMPT_DISABLED": "1"}


def _blocked(
    reason: str,
    *,
    env: Mapping[str, str],
    pr_ref: dict[str, object] | None = None,
    message: str | None = None,
) -> LiveReadSmokeArtifact:
    redaction_status = _empty_redaction_status()
    redacted_message: str | None = None
    if message:
        redaction = redact_text(message)
        redacted_message = redaction.text
        redaction_status = {
            "redacted": redaction.redacted,
            "replacement_count": redaction.replacement_count,
            "categories": list(redaction.categories),
        }
    return LiveReadSmokeArtifact(
        status="blocked",
        reason=reason,
        pr_ref=pr_ref,
        command_summary={
            "transport": "gh_api_rest",
            "live_read_opt_in": env.get(LIVE_READ_OPT_IN_ENV) == "1",
            "message": redacted_message,
        },
        redaction_status=redaction_status,
    )


def _write_artifact_if_requested(
    artifact: LiveReadSmokeArtifact,
    *,
    env: Mapping[str, str],
    output_path: str | Path | None,
) -> None:
    destination = output_path or env.get(LIVE_READ_OUT_ENV)
    if destination is None:
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _parsed_ref_or_none(value: str) -> dict[str, object] | None:
    try:
        ref = parse_github_pr_ref(value)
    except Exception:
        return None
    return {
        "owner_repo": ref.owner_repo,
        "pr_number": ref.pr_number,
    }


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _user_login(value: object) -> str:
    if not isinstance(value, dict):
        return "unknown"
    return _text(value.get("login"), default="unknown")


def _user_type(value: object) -> str:
    if not isinstance(value, dict):
        return "unknown"
    return _text(value.get("type"), default="unknown").lower()


def _text(value: object, *, default: str | None = None) -> str:
    if isinstance(value, str) and value:
        return value
    if default is not None:
        return default
    raise ValueError("GitHub live payload required a non-empty string")


def _nullable_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return None


def _non_negative_int(value: object) -> int:
    return value if type(value) is int and value >= 0 else 0


def _positive_int_or_none(value: object) -> int | None:
    return value if type(value) is int and value > 0 else None


def _redacted_text(value: str) -> str:
    return redact_text(value).text


def _empty_redaction_status() -> dict[str, object]:
    return {
        "redacted": False,
        "replacement_count": 0,
        "categories": [],
    }


def _replacement_count(value: object) -> int:
    if not isinstance(value, Mapping):
        return 0
    replacement_count = value.get("replacement_count")
    return replacement_count if type(replacement_count) is int else 0
