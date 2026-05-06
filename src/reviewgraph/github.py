from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import urlparse

from reviewgraph.models import (
    ActorPermissionGateResult,
    GateStatus,
    PullRequestChangedFile,
    PullRequestContext,
    ReadGap,
    RedactionStatus,
    ReviewTarget,
)
from reviewgraph.redaction import redact_data, redact_text


class GitHubReadScope(StrEnum):
    METADATA_FILES_ONLY = "metadata_files_only"


class ResourceReadStatus(StrEnum):
    COMPLETE = "complete"
    NOT_FETCHED_IN_SCOPE = "not_fetched_in_scope"


class GitHubReadError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class GitHubFakeReadTransport(Protocol):
    def get_pull_request(self, owner_repo: str, pr_number: int) -> dict[str, object]: ...

    def get_changed_files(self, owner_repo: str, pr_number: int) -> list[dict[str, object]]: ...


@dataclass(frozen=True)
class GitHubPRRef:
    owner: str
    repo: str
    pr_number: int

    @property
    def owner_repo(self) -> str:
        return f"{self.owner}/{self.repo}"


@dataclass(frozen=True)
class GitHubPRMetadata:
    author: str
    base_ref: str
    head_ref: str


@dataclass(frozen=True)
class GitHubChangedRange:
    start: int
    end: int

    def contains(self, line: int) -> bool:
        return self.start <= line <= self.end


@dataclass(frozen=True)
class GitHubChangedFileLines:
    path: str
    changed_ranges: tuple[GitHubChangedRange, ...]
    status: str
    previous_path: str | None
    patch_status: str

    def contains_line(self, line: int) -> bool:
        return any(changed_range.contains(line) for changed_range in self.changed_ranges)


@dataclass(frozen=True)
class GitHubResourceCoverage:
    metadata: ResourceReadStatus
    files: ResourceReadStatus
    comments: ResourceReadStatus
    reviews: ResourceReadStatus
    review_comments: ResourceReadStatus
    thread_state: ResourceReadStatus

    @classmethod
    def metadata_files_only(cls) -> "GitHubResourceCoverage":
        return cls(
            metadata=ResourceReadStatus.COMPLETE,
            files=ResourceReadStatus.COMPLETE,
            comments=ResourceReadStatus.NOT_FETCHED_IN_SCOPE,
            reviews=ResourceReadStatus.NOT_FETCHED_IN_SCOPE,
            review_comments=ResourceReadStatus.NOT_FETCHED_IN_SCOPE,
            thread_state=ResourceReadStatus.NOT_FETCHED_IN_SCOPE,
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "metadata": self.metadata.value,
            "files": self.files.value,
            "comments": self.comments.value,
            "reviews": self.reviews.value,
            "review_comments": self.review_comments.value,
            "thread_state": self.thread_state.value,
        }


@dataclass(frozen=True)
class GitHubThreadStateAvailability:
    available: bool
    reason: str


@dataclass(frozen=True)
class GitHubReadResult:
    pr_ref: GitHubPRRef
    metadata: GitHubPRMetadata
    pr: PullRequestContext
    review_target: ReviewTarget
    changed_file_lines: tuple[GitHubChangedFileLines, ...]
    anchor_unavailable: tuple[dict[str, str], ...]
    resource_coverage: GitHubResourceCoverage
    read_gaps: tuple[ReadGap, ...]
    thread_state: GitHubThreadStateAvailability
    actor_permission: ActorPermissionGateResult | None
    redaction_status: RedactionStatus
    scope: GitHubReadScope = GitHubReadScope.METADATA_FILES_ONLY

    def to_redacted_dict(self) -> dict[str, object]:
        return self.to_dict()

    def to_dict(self) -> dict[str, object]:
        redacted = redact_data(self._to_raw_dict()).data
        if not isinstance(redacted, dict):
            raise GitHubReadError("redaction_error", "GitHub read result redaction did not return an object")
        return redacted

    def with_actor_permission(self, actor_permission: ActorPermissionGateResult | None) -> "GitHubReadResult":
        return _with_current_redaction_status(replace(self, actor_permission=actor_permission))

    def _to_raw_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope.value,
            "pr_ref": {
                "owner": self.pr_ref.owner,
                "repo": self.pr_ref.repo,
                "owner_repo": self.pr_ref.owner_repo,
                "pr_number": self.pr_ref.pr_number,
            },
            "metadata": {
                "author": self.metadata.author,
                "base_ref": self.metadata.base_ref,
                "head_ref": self.metadata.head_ref,
            },
            "review_target": self.review_target.to_ordered_dict(),
            "pr": {
                "title": self.pr.title,
                "body": self.pr.body,
                "labels": list(self.pr.labels),
                "changed_files": [
                    {
                        "path": item.path,
                        "patch": item.patch,
                        "additions": item.additions,
                        "deletions": item.deletions,
                        "status": item.status,
                        "previous_path": item.previous_path,
                        "patch_status": item.patch_status,
                    }
                    for item in self.pr.changed_files
                ],
            },
            "changed_file_lines": [
                {
                    "path": item.path,
                    "changed_ranges": [
                        {
                            "start": changed_range.start,
                            "end": changed_range.end,
                        }
                        for changed_range in item.changed_ranges
                    ],
                    "status": item.status,
                    "previous_path": item.previous_path,
                    "patch_status": item.patch_status,
                }
                for item in self.changed_file_lines
            ],
            "anchor_unavailable": list(self.anchor_unavailable),
            "resource_coverage": self.resource_coverage.to_dict(),
            "read_gaps": [
                {
                    "resource": gap.resource,
                    "required": gap.required,
                    "reason": gap.reason,
                    "retryable": gap.retryable,
                }
                for gap in self.read_gaps
            ],
            "thread_state": {
                "available": self.thread_state.available,
                "reason": self.thread_state.reason,
            },
            "actor_permission": _actor_permission_dict(self.actor_permission),
            "redaction_status": {
                "redacted": self.redaction_status.redacted,
                "replacement_count": self.redaction_status.replacement_count,
                "categories": list(self.redaction_status.categories),
                "status": self.redaction_status.status.value,
            },
        }


_SHORT_REF_RE = re.compile(r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)#(?P<number>[1-9][0-9]*)$")
_OWNER_REPO_PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_HUNK_RE = re.compile(
    r"^@@ -(?P<source_start>\d+)(?:,(?P<source_count>\d+))?"
    r" \+(?P<target_start>\d+)(?:,(?P<target_count>\d+))? @@(?: .*)?$"
)
_INLINEABLE_FILE_STATUSES = frozenset({"added", "modified", "renamed"})


def parse_github_pr_ref(value: str) -> GitHubPRRef:
    if match := _SHORT_REF_RE.match(value):
        return GitHubPRRef(
            owner=match.group("owner"),
            repo=match.group("repo"),
            pr_number=int(match.group("number")),
        )
    parsed = urlparse(value)
    if (
        parsed.scheme == "https"
        and parsed.netloc == "github.com"
        and not parsed.query
        and not parsed.fragment
    ):
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) == 4 and parts[2] == "pull" and parts[3].isdigit() and int(parts[3]) > 0:
            if parsed.path.endswith("/"):
                _raise_invalid_ref(value)
            if not _valid_owner_repo_part(parts[0]) or not _valid_owner_repo_part(parts[1]):
                _raise_invalid_ref(value)
            return GitHubPRRef(owner=parts[0], repo=parts[1], pr_number=int(parts[3]))
    _raise_invalid_ref(value)


def read_github_pr_with_fake_transport(
    transport: GitHubFakeReadTransport,
    ref: str | GitHubPRRef,
) -> GitHubReadResult:
    pr_ref = parse_github_pr_ref(ref) if isinstance(ref, str) else ref
    try:
        pr_payload = transport.get_pull_request(pr_ref.owner_repo, pr_ref.pr_number)
        file_payloads = transport.get_changed_files(pr_ref.owner_repo, pr_ref.pr_number)
    except Exception as exc:
        message = redact_text(str(exc)).text
        raise GitHubReadError("fake_transport_error", f"GitHub fake read failed: {message}") from exc
    if not isinstance(pr_payload, dict):
        raise GitHubReadError("invalid_pr_payload", "GitHub fake PR payload must be an object")
    if not isinstance(file_payloads, list):
        raise GitHubReadError("invalid_files_payload", "GitHub fake files payload must be a list")
    if not file_payloads:
        raise GitHubReadError("invalid_files_payload", "GitHub fake changed files must not be empty")

    review_target = _review_target_from_payload(pr_ref, pr_payload)
    metadata = GitHubPRMetadata(
        author=_required_str(pr_payload, "author", "pull request"),
        base_ref=_required_nested_str(pr_payload, "base", "ref"),
        head_ref=_required_nested_str(pr_payload, "head", "ref"),
    )
    changed_files, changed_file_lines, anchor_unavailable = _changed_files_from_payload(file_payloads)
    pr = PullRequestContext(
        review_target=review_target,
        title=_required_str(pr_payload, "title", "pull request"),
        body=_optional_text(pr_payload, "body", "pull request"),
        labels=tuple(_str_list(pr_payload.get("labels", []), "pull request labels")),
        changed_files=changed_files,
    )
    return _with_current_redaction_status(GitHubReadResult(
        pr_ref=pr_ref,
        metadata=metadata,
        pr=pr,
        review_target=review_target,
        changed_file_lines=changed_file_lines,
        anchor_unavailable=anchor_unavailable,
        resource_coverage=GitHubResourceCoverage.metadata_files_only(),
        read_gaps=_metadata_files_only_read_gaps(),
        thread_state=GitHubThreadStateAvailability(
            available=False,
            reason="not_fetched_in_scope",
        ),
        actor_permission=None,
        redaction_status=RedactionStatus(
            status=GateStatus.PASS,
            redacted=False,
            replacement_count=0,
            categories=(),
        ),
    ))


def _raise_invalid_ref(value: str) -> None:
    raise GitHubReadError("invalid_pr_ref", "invalid GitHub PR reference")


def _metadata_files_only_read_gaps() -> tuple[ReadGap, ...]:
    return (
        ReadGap(
            resource="comments",
            required=True,
            reason="not_fetched_in_scope",
            retryable=True,
        ),
        ReadGap(
            resource="reviews",
            required=True,
            reason="not_fetched_in_scope",
            retryable=True,
        ),
        ReadGap(
            resource="review_comments",
            required=True,
            reason="not_fetched_in_scope",
            retryable=True,
        ),
        ReadGap(
            resource="thread_state",
            required=True,
            reason="not_fetched_in_scope",
            retryable=True,
        ),
    )


def _review_target_from_payload(pr_ref: GitHubPRRef, payload: dict[str, object]) -> ReviewTarget:
    return ReviewTarget(
        owner_repo=pr_ref.owner_repo,
        pr_number=pr_ref.pr_number,
        base_sha=_required_nested_str(payload, "base", "sha"),
        head_sha=_required_nested_str(payload, "head", "sha"),
        merge_base_sha=_optional_str(payload, "merge_base_sha", "pull request"),
        diff_basis=_optional_str(payload, "diff_basis", "pull request") or "merge_base",
    )


def _changed_files_from_payload(
    payloads: list[dict[str, object]],
) -> tuple[tuple[PullRequestChangedFile, ...], tuple[GitHubChangedFileLines, ...], tuple[dict[str, str], ...]]:
    changed_files: list[PullRequestChangedFile] = []
    changed_lines: list[GitHubChangedFileLines] = []
    anchor_unavailable: list[dict[str, str]] = []
    for index, payload in enumerate(payloads):
        if not isinstance(payload, dict):
            raise GitHubReadError("invalid_file_payload", f"changed file {index} must be an object")
        path = _required_str(payload, "path", "changed file")
        patch = _optional_str(payload, "patch", "changed file")
        status = _optional_str(payload, "status", "changed file") or "modified"
        patch_status = _optional_str(payload, "patch_status", "changed file")
        if patch_status is None:
            patch_status = "available" if patch is not None else "unavailable"
        previous_path = _optional_str(payload, "previous_path", "changed file")
        changed_file = PullRequestChangedFile(
            path=path,
            patch=patch,
            additions=_optional_non_negative_int(payload, "additions"),
            deletions=_optional_non_negative_int(payload, "deletions"),
            status=status,
            previous_path=previous_path,
            patch_status=patch_status,
        )
        ranges, unavailable_reason = _changed_ranges_from_patch(
            path=path,
            patch=patch,
            status=status,
            patch_status=patch_status,
        )
        changed_line = GitHubChangedFileLines(
            path=path,
            changed_ranges=ranges,
            status=status,
            previous_path=previous_path,
            patch_status=patch_status,
        )
        if unavailable_reason is not None:
            anchor_unavailable.append(
                {
                    "path": path,
                    "reason": unavailable_reason,
                }
            )
        changed_files.append(changed_file)
        changed_lines.append(changed_line)
    return tuple(changed_files), tuple(changed_lines), tuple(anchor_unavailable)


def _changed_ranges_from_patch(
    *,
    path: str,
    patch: str | None,
    status: str,
    patch_status: str,
) -> tuple[tuple[GitHubChangedRange, ...], str | None]:
    if status not in _INLINEABLE_FILE_STATUSES:
        return (), f"file status {status} is not anchorable"
    if patch is None:
        return (), f"patch is {patch_status}"
    if patch_status != "available":
        return (), f"patch is {patch_status}"
    changed_ranges: list[GitHubChangedRange] = []
    saw_hunk = False
    source_remaining: int | None = None
    target_line: int | None = None
    target_remaining: int | None = None
    hunk_start: int | None = None
    hunk_end: int | None = None
    hunk_has_addition = False
    for line in patch.splitlines():
        match = _HUNK_RE.match(line) if line.startswith("@@") else None
        if match is not None:
            if saw_hunk and (source_remaining != 0 or target_remaining != 0):
                return (), f"hunk target line count mismatch in {path}"
            if saw_hunk and hunk_has_addition and hunk_start is not None and hunk_end is not None:
                changed_ranges.append(GitHubChangedRange(start=hunk_start, end=hunk_end))
            saw_hunk = True
            source_start = int(match.group("source_start"))
            source_remaining = int(match.group("source_count") or "1")
            target_line = int(match.group("target_start"))
            target_remaining = int(match.group("target_count") or "1")
            if source_start <= 0 and source_remaining > 0:
                return (), f"hunk source start must be positive in {path}"
            if target_line <= 0:
                return (), f"hunk target start must be positive in {path}"
            if target_remaining <= 0:
                return (), f"hunk has no target lines in {path}"
            hunk_start = target_line
            hunk_end = target_line + target_remaining - 1
            hunk_has_addition = False
            continue
        if line.startswith("@@"):
            return (), f"unsupported hunk header in {path}"
        if not saw_hunk or source_remaining is None or target_line is None or target_remaining is None:
            continue
        if line.startswith("\\"):
            continue
        if line.startswith("+"):
            if target_remaining <= 0:
                return (), f"hunk target line count overflow in {path}"
            hunk_has_addition = True
            target_line += 1
            target_remaining -= 1
            continue
        if line.startswith("-"):
            if source_remaining <= 0:
                return (), f"hunk source line count overflow in {path}"
            source_remaining -= 1
            continue
        if line.startswith(" "):
            if source_remaining <= 0:
                return (), f"hunk source line count overflow in {path}"
            if target_remaining <= 0:
                return (), f"hunk target line count overflow in {path}"
            source_remaining -= 1
            target_line += 1
            target_remaining -= 1
            continue
        return (), f"unsupported hunk body line in {path}"
    if not saw_hunk:
        return (), f"patch has no supported hunks in {path}"
    if source_remaining != 0 or target_remaining != 0:
        return (), f"hunk target line count mismatch in {path}"
    if hunk_has_addition and hunk_start is not None and hunk_end is not None:
        changed_ranges.append(GitHubChangedRange(start=hunk_start, end=hunk_end))
    if not changed_ranges:
        return (), f"patch has no target changed lines in {path}"
    return tuple(_coalesce_changed_ranges(changed_ranges)), None


def _with_current_redaction_status(result: GitHubReadResult) -> GitHubReadResult:
    redaction = redact_data(result._to_raw_dict())
    return replace(
        result,
        redaction_status=RedactionStatus(
            redacted=redaction.redaction_status.redacted,
            replacement_count=redaction.redaction_status.replacement_count,
            categories=redaction.redaction_status.categories,
            status=GateStatus.PASS,
        ),
    )


def _actor_permission_dict(value: ActorPermissionGateResult | None) -> dict[str, str | None] | None:
    if value is None:
        return None
    return {
        "status": value.status.value,
        "actor": value.actor,
        "permission": value.permission,
        "checked_at": value.checked_at,
        "reason": value.reason,
    }


def _valid_owner_repo_part(value: str) -> bool:
    return _OWNER_REPO_PART_RE.match(value) is not None


def _coalesce_changed_ranges(ranges: list[GitHubChangedRange]) -> list[GitHubChangedRange]:
    coalesced: list[GitHubChangedRange] = []
    current = ranges[0]
    for changed_range in ranges[1:]:
        if changed_range.start <= current.end + 1:
            current = GitHubChangedRange(start=current.start, end=max(current.end, changed_range.end))
            continue
        coalesced.append(current)
        current = changed_range
    coalesced.append(current)
    return coalesced



def _required_nested_str(data: dict[str, object], object_key: str, field_key: str) -> str:
    nested = data.get(object_key)
    if not isinstance(nested, dict):
        raise GitHubReadError("invalid_pr_payload", f"pull request {object_key} must be an object")
    return _required_str(nested, field_key, f"pull request {object_key}")


def _required_str(data: dict[str, object], key: str, label: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise GitHubReadError("invalid_payload", f"{label} {key} must be a non-empty string")
    return value


def _optional_str(data: dict[str, object], key: str, label: str) -> str | None:
    if key not in data or data[key] is None:
        return None
    value = data[key]
    if not isinstance(value, str) or not value:
        raise GitHubReadError("invalid_payload", f"{label} {key} must be a non-empty string or null")
    return value


def _optional_text(data: dict[str, object], key: str, label: str) -> str | None:
    if key not in data or data[key] is None:
        return None
    value = data[key]
    if not isinstance(value, str):
        raise GitHubReadError("invalid_payload", f"{label} {key} must be a string or null")
    return value


def _str_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise GitHubReadError("invalid_payload", f"{label} must be a list of non-empty strings")
    return value


def _optional_non_negative_int(data: dict[str, object], key: str) -> int:
    value = data.get(key, 0)
    if type(value) is not int or value < 0:
        raise GitHubReadError("invalid_payload", f"changed file {key} must be a non-negative integer")
    return value
