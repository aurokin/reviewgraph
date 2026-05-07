from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from reviewgraph.models import (
    ActorPermissionGateResult,
    GateStatus,
    PullRequestChangedFile,
    PullRequestComment,
    PullRequestContext,
    PullRequestReview,
    PullRequestReviewThread,
    ReadGap,
    RedactionStatus,
    ReviewTarget,
)
from reviewgraph.read_gaps import (
    FailClosedReadOutcome,
    GitHubPageGapDescriptor,
    build_fail_closed_read_outcome,
    classify_github_read_gap,
)
from reviewgraph.redaction import redact_data, redact_text


MAX_GITHUB_FAKE_DATA_BYTES = 1_048_576
_PAGINATED_FAKE_RESOURCE_KEYS = (
    "files",
    "issue_comments",
    "review_comments",
    "reviews",
    "review_threads",
)


class GitHubReadScope(StrEnum):
    METADATA_FILES_ONLY = "metadata_files_only"
    FULL_CONTEXT = "full_context"


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


class GitHubPaginatedFakeReadTransport(Protocol):
    def get_pull_request(self, owner_repo: str, pr_number: int) -> dict[str, object]: ...

    def get_changed_files_page(
        self,
        owner_repo: str,
        pr_number: int,
        cursor: object | None,
    ) -> dict[str, object]: ...

    def get_issue_comments_page(
        self,
        owner_repo: str,
        pr_number: int,
        cursor: object | None,
    ) -> dict[str, object]: ...

    def get_review_comments_page(
        self,
        owner_repo: str,
        pr_number: int,
        cursor: object | None,
    ) -> dict[str, object]: ...

    def get_reviews_page(
        self,
        owner_repo: str,
        pr_number: int,
        cursor: object | None,
    ) -> dict[str, object]: ...

    def get_review_threads_page(
        self,
        owner_repo: str,
        pr_number: int,
        cursor: object | None,
    ) -> dict[str, object]: ...


@dataclass
class PaginatedFakeGitHubTransport:
    pull_request: dict[str, object]
    files: dict[object | None, dict[str, object]]
    issue_comments: dict[object | None, dict[str, object]]
    review_comments: dict[object | None, dict[str, object]]
    reviews: dict[object | None, dict[str, object]]
    review_threads: dict[object | None, dict[str, object]]

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, str, int, object | None]] = []

    def get_pull_request(self, owner_repo: str, pr_number: int) -> dict[str, object]:
        self.calls.append(("get_pull_request", owner_repo, pr_number, None))
        return self.pull_request

    def get_changed_files_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        self.calls.append(("get_changed_files_page", owner_repo, pr_number, cursor))
        return self.files[cursor]

    def get_issue_comments_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        self.calls.append(("get_issue_comments_page", owner_repo, pr_number, cursor))
        return self.issue_comments[cursor]

    def get_review_comments_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        self.calls.append(("get_review_comments_page", owner_repo, pr_number, cursor))
        return self.review_comments[cursor]

    def get_reviews_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        self.calls.append(("get_reviews_page", owner_repo, pr_number, cursor))
        return self.reviews[cursor]

    def get_review_threads_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        self.calls.append(("get_review_threads_page", owner_repo, pr_number, cursor))
        return self.review_threads[cursor]


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

    @classmethod
    def complete(cls) -> "GitHubResourceCoverage":
        return cls(
            metadata=ResourceReadStatus.COMPLETE,
            files=ResourceReadStatus.COMPLETE,
            comments=ResourceReadStatus.COMPLETE,
            reviews=ResourceReadStatus.COMPLETE,
            review_comments=ResourceReadStatus.COMPLETE,
            thread_state=ResourceReadStatus.COMPLETE,
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
                "comments": [
                    _pull_request_comment_dict(comment)
                    for comment in self.pr.comments
                ],
                "reviews": [
                    {
                        "id": review.id,
                        "author": review.author,
                        "author_association": review.author_association,
                        "author_type": review.author_type,
                        "state": review.state,
                        "created_at": review.created_at,
                        "trust_label": review.trust_label,
                        "source_type": review.source_type,
                        "body": review.body,
                        "url": review.url,
                        "source_provider": review.source_provider,
                    }
                    for review in self.pr.reviews
                ],
                "review_threads": [
                    {
                        "id": thread.id,
                        "path": thread.path,
                        "resolved_status": thread.resolved_status,
                        "comments": [
                            _pull_request_comment_dict(comment)
                            for comment in thread.comments
                        ],
                    }
                    for thread in self.pr.review_threads
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


def read_github_pr_with_paginated_fake_transport(
    transport: GitHubPaginatedFakeReadTransport,
    ref: str | GitHubPRRef,
) -> GitHubReadResult | FailClosedReadOutcome:
    pr_ref = parse_github_pr_ref(ref) if isinstance(ref, str) else ref
    try:
        pr_payload = transport.get_pull_request(pr_ref.owner_repo, pr_ref.pr_number)
    except Exception as exc:
        message = redact_text(str(exc)).text
        raise GitHubReadError("fake_transport_error", f"GitHub fake read failed: {message}") from exc
    if not isinstance(pr_payload, dict):
        raise GitHubReadError("invalid_pr_payload", "GitHub fake PR payload must be an object")

    review_target = _review_target_from_payload(pr_ref, pr_payload)
    metadata = GitHubPRMetadata(
        author=_required_str(pr_payload, "author", "pull request"),
        base_ref=_required_nested_str(pr_payload, "base", "ref"),
        head_ref=_required_nested_str(pr_payload, "head", "ref"),
    )
    paged_files = _collect_pages(
        resource="files",
        fetch_page=transport.get_changed_files_page,
        pr_ref=pr_ref,
        review_target=review_target,
    )
    if isinstance(paged_files, FailClosedReadOutcome):
        return paged_files
    paged_issue_comments = _collect_pages(
        resource="comments",
        fetch_page=transport.get_issue_comments_page,
        pr_ref=pr_ref,
        review_target=review_target,
    )
    if isinstance(paged_issue_comments, FailClosedReadOutcome):
        return paged_issue_comments
    paged_review_comments = _collect_pages(
        resource="review_comments",
        fetch_page=transport.get_review_comments_page,
        pr_ref=pr_ref,
        review_target=review_target,
    )
    if isinstance(paged_review_comments, FailClosedReadOutcome):
        return paged_review_comments
    paged_reviews = _collect_pages(
        resource="reviews",
        fetch_page=transport.get_reviews_page,
        pr_ref=pr_ref,
        review_target=review_target,
    )
    if isinstance(paged_reviews, FailClosedReadOutcome):
        return paged_reviews
    paged_threads = _collect_pages(
        resource="thread_state",
        fetch_page=transport.get_review_threads_page,
        pr_ref=pr_ref,
        review_target=review_target,
    )
    if isinstance(paged_threads, FailClosedReadOutcome):
        return paged_threads

    if not paged_files.items:
        raise GitHubReadError("invalid_files_payload", "GitHub fake changed files must not be empty")
    changed_files, changed_file_lines, anchor_unavailable = _changed_files_from_payload(paged_files.items)
    comments = tuple(_comment_from_payload(payload, source_type="issue_comment") for payload in paged_issue_comments.items)
    reviews = tuple(_review_from_payload(payload) for payload in paged_reviews.items)
    review_threads_or_gap = _review_threads_from_payloads(
        pr_ref=pr_ref,
        review_target=review_target,
        review_comment_payloads=paged_review_comments.items,
        thread_payloads=paged_threads.items,
    )
    if isinstance(review_threads_or_gap, FailClosedReadOutcome):
        return review_threads_or_gap
    pr = PullRequestContext(
        review_target=review_target,
        title=_required_str(pr_payload, "title", "pull request"),
        body=_optional_text(pr_payload, "body", "pull request"),
        labels=tuple(_str_list(pr_payload.get("labels", []), "pull request labels")),
        changed_files=changed_files,
        comments=comments,
        reviews=reviews,
        review_threads=review_threads_or_gap,
    )
    return _with_current_redaction_status(GitHubReadResult(
        pr_ref=pr_ref,
        metadata=metadata,
        pr=pr,
        review_target=review_target,
        changed_file_lines=changed_file_lines,
        anchor_unavailable=anchor_unavailable,
        resource_coverage=GitHubResourceCoverage.complete(),
        read_gaps=(),
        thread_state=GitHubThreadStateAvailability(
            available=True,
            reason="complete",
        ),
        actor_permission=None,
        redaction_status=RedactionStatus(
            status=GateStatus.PASS,
            redacted=False,
            replacement_count=0,
            categories=(),
        ),
        scope=GitHubReadScope.FULL_CONTEXT,
    ))


def load_paginated_fake_github_transport(
    path: str | Path,
) -> tuple[PaginatedFakeGitHubTransport, tuple[dict[str, Any], ...]]:
    data = _read_fake_data_json(Path(path))
    _require_exact_keys(data, ("transport", "raw_reviewer_outputs"), "github fake data")
    transport_data = data["transport"]
    if not isinstance(transport_data, dict):
        raise GitHubReadError("invalid_fake_data", "github fake data transport must be an object")
    _require_exact_keys(transport_data, ("pull_request", *_PAGINATED_FAKE_RESOURCE_KEYS), "github fake data transport")
    pull_request = transport_data["pull_request"]
    if not isinstance(pull_request, dict):
        raise GitHubReadError("invalid_fake_data", "github fake data transport.pull_request must be an object")
    raw_reviewer_outputs = data["raw_reviewer_outputs"]
    if (
        not isinstance(raw_reviewer_outputs, list)
        or not raw_reviewer_outputs
        or any(not isinstance(output, dict) for output in raw_reviewer_outputs)
    ):
        raise GitHubReadError(
            "invalid_fake_data",
            "github fake data raw_reviewer_outputs must be a non-empty list of objects",
        )
    return (
        PaginatedFakeGitHubTransport(
            pull_request=dict(pull_request),
            files=_load_page_map(transport_data["files"], "files"),
            issue_comments=_load_page_map(transport_data["issue_comments"], "issue_comments"),
            review_comments=_load_page_map(transport_data["review_comments"], "review_comments"),
            reviews=_load_page_map(transport_data["reviews"], "reviews"),
            review_threads=_load_page_map(transport_data["review_threads"], "review_threads"),
        ),
        tuple(dict(output) for output in raw_reviewer_outputs),
    )


def _raise_invalid_ref(value: str) -> None:
    raise GitHubReadError("invalid_pr_ref", "invalid GitHub PR reference")


def _read_fake_data_json(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file():
            raise GitHubReadError("invalid_fake_data", f"github fake data path must be a regular file: {_redact(path)}")
        with path.open("rb") as handle:
            raw = handle.read(MAX_GITHUB_FAKE_DATA_BYTES + 1)
    except OSError as exc:
        raise GitHubReadError("invalid_fake_data", f"github fake data file is not readable: {_redact(path)}") from exc
    if len(raw) > MAX_GITHUB_FAKE_DATA_BYTES:
        raise GitHubReadError(
            "invalid_fake_data",
            f"github fake data file exceeds {MAX_GITHUB_FAKE_DATA_BYTES} bytes: {_redact(path)}",
        )
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise GitHubReadError("invalid_fake_data", f"github fake data JSON is invalid at line {exc.lineno}: {exc.msg}") from exc
    except UnicodeDecodeError as exc:
        raise GitHubReadError("invalid_fake_data", "github fake data JSON must be UTF-8") from exc
    if not isinstance(data, dict):
        raise GitHubReadError("invalid_fake_data", "github fake data JSON must be an object")
    return data


def _load_page_map(value: object, resource: str) -> dict[object | None, dict[str, object]]:
    if not isinstance(value, dict):
        raise GitHubReadError("invalid_fake_data", f"github fake data transport.{resource} must be an object")
    _require_exact_keys(value, ("pages",), f"github fake data transport.{resource}")
    pages = value["pages"]
    if not isinstance(pages, list) or not pages:
        raise GitHubReadError(
            "invalid_fake_data",
            f"github fake data transport.{resource}.pages must be a non-empty list",
        )
    page_map: dict[object | None, dict[str, object]] = {}
    cursor: object | None = None
    for index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            raise GitHubReadError(
                "invalid_fake_data",
                f"github fake data transport.{resource}.pages[{index}] must be an object",
            )
        if cursor in page_map:
            raise GitHubReadError(
                "invalid_fake_data",
                f"github fake data transport.{resource}.pages[{index}] repeats pagination cursor",
            )
        page_map[cursor] = dict(page)
        if "error" in page:
            _validate_fake_error_page(page, resource, index)
            if index != len(pages):
                raise GitHubReadError(
                    "invalid_fake_data",
                    f"github fake data transport.{resource}.pages[{index}] error page must be final",
                )
            return page_map
        _validate_fake_items_page(page, resource, index)
        if page["has_next_page"] is False:
            if index != len(pages):
                raise GitHubReadError(
                    "invalid_fake_data",
                    f"github fake data transport.{resource}.pages[{index}] leaves unreachable pages",
                )
            return page_map
        cursor = page["next_cursor"]
    raise GitHubReadError(
        "invalid_fake_data",
        f"github fake data transport.{resource}.pages ended before has_next_page=false",
    )


def _validate_fake_items_page(page: dict[str, object], resource: str, index: int) -> None:
    allowed = {"items", "has_next_page", "next_cursor"}
    _reject_unknown_keys(page, allowed, f"github fake data transport.{resource}.pages[{index}]")
    items = page.get("items")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise GitHubReadError(
            "invalid_fake_data",
            f"github fake data transport.{resource}.pages[{index}].items must be a list of objects",
        )
    if type(page.get("has_next_page")) is not bool:
        raise GitHubReadError(
            "invalid_fake_data",
            f"github fake data transport.{resource}.pages[{index}].has_next_page must be a boolean",
        )
    if page["has_next_page"] is True:
        next_cursor = page.get("next_cursor")
        if not isinstance(next_cursor, str) or not next_cursor:
            raise GitHubReadError(
                "invalid_fake_data",
                f"github fake data transport.{resource}.pages[{index}].next_cursor must be a non-empty string",
            )
    elif "next_cursor" in page:
        raise GitHubReadError(
            "invalid_fake_data",
            f"github fake data transport.{resource}.pages[{index}].next_cursor requires has_next_page=true",
        )


def _validate_fake_error_page(page: dict[str, object], resource: str, index: int) -> None:
    _require_exact_keys(page, ("error",), f"github fake data transport.{resource}.pages[{index}]")
    error = page["error"]
    if not isinstance(error, dict):
        raise GitHubReadError(
            "invalid_fake_data",
            f"github fake data transport.{resource}.pages[{index}].error must be an object",
        )
    _reject_unknown_keys(error, {"reason", "message"}, f"github fake data transport.{resource}.pages[{index}].error")
    reason = error.get("reason")
    if reason is not None and (not isinstance(reason, str) or not reason):
        raise GitHubReadError(
            "invalid_fake_data",
            f"github fake data transport.{resource}.pages[{index}].error.reason must be a non-empty string or null",
        )
    message = error.get("message")
    if message is not None and not isinstance(message, str):
        raise GitHubReadError(
            "invalid_fake_data",
            f"github fake data transport.{resource}.pages[{index}].error.message must be a string or null",
        )


def _require_exact_keys(data: dict[str, object], keys: tuple[str, ...], label: str) -> None:
    missing = sorted(set(keys) - set(data))
    if missing:
        raise GitHubReadError("invalid_fake_data", f"{label}.{missing[0]} is required")
    _reject_unknown_keys(data, set(keys), label)


def _reject_unknown_keys(data: dict[str, object], allowed: set[str], label: str) -> None:
    extra = sorted(set(data) - allowed)
    if extra:
        raise GitHubReadError("invalid_fake_data", f"{label}.{extra[0]} is not supported")


def _redact(path: Path) -> str:
    return redact_text(str(path)).text


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


@dataclass(frozen=True)
class _PagedItems:
    items: list[dict[str, object]]


def _collect_pages(
    *,
    resource: str,
    fetch_page: Any,
    pr_ref: GitHubPRRef,
    review_target: ReviewTarget,
) -> _PagedItems | FailClosedReadOutcome:
    cursor: object | None = None
    page_number = 1
    items: list[dict[str, object]] = []
    seen_cursors: set[object] = set()
    while True:
        try:
            payload = fetch_page(pr_ref.owner_repo, pr_ref.pr_number, cursor)
        except Exception as exc:
            return _pagination_failure(
                pr_ref=pr_ref,
                review_target=review_target,
                resource=resource,
                page=page_number,
                reason="timeout",
                message=str(exc),
            )
        if not isinstance(payload, dict):
            return _pagination_failure(
                pr_ref=pr_ref,
                review_target=review_target,
                resource=resource,
                page=page_number,
                reason="pagination_incomplete",
                message=f"{resource} page {page_number} must be an object",
            )
        error = payload.get("error")
        if error is not None:
            if not isinstance(error, dict):
                return _pagination_failure(
                    pr_ref=pr_ref,
                    review_target=review_target,
                    resource=resource,
                    page=page_number,
                    reason="pagination_incomplete",
                    message=f"{resource} page {page_number} error must be an object",
                )
            error_reason = error.get("reason")
            if error_reason is not None and (not isinstance(error_reason, str) or not error_reason):
                return _pagination_failure(
                    pr_ref=pr_ref,
                    review_target=review_target,
                    resource=resource,
                    page=page_number,
                    reason="pagination_incomplete",
                    message=f"{resource} page {page_number} error reason must be a non-empty string or null",
                )
            error_message = error.get("message")
            if error_message is not None and not isinstance(error_message, str):
                return _pagination_failure(
                    pr_ref=pr_ref,
                    review_target=review_target,
                    resource=resource,
                    page=page_number,
                    reason="pagination_incomplete",
                    message=f"{resource} page {page_number} error message must be a string or null",
                )
            return _pagination_failure(
                pr_ref=pr_ref,
                review_target=review_target,
                resource=resource,
                page=page_number,
                reason=error_reason or "unavailable",
                message=error_message or f"{resource} page {page_number} failed",
            )
        page_items = payload.get("items")
        if not isinstance(page_items, list) or any(not isinstance(item, dict) for item in page_items):
            return _pagination_failure(
                pr_ref=pr_ref,
                review_target=review_target,
                resource=resource,
                page=page_number,
                reason="pagination_incomplete",
                message=f"{resource} page {page_number} items must be a list of objects",
            )
        items.extend(page_items)
        has_next_page = payload.get("has_next_page")
        if type(has_next_page) is not bool:
            return _pagination_failure(
                pr_ref=pr_ref,
                review_target=review_target,
                resource=resource,
                page=page_number,
                reason="pagination_incomplete",
                message=f"{resource} page {page_number} has_next_page must be a boolean",
            )
        if not has_next_page:
            return _PagedItems(items=items)
        next_cursor = payload.get("next_cursor")
        if next_cursor is None:
            return _pagination_failure(
                pr_ref=pr_ref,
                review_target=review_target,
                resource=resource,
                page=page_number,
                reason="pagination_incomplete",
                message=f"{resource} page {page_number} next_cursor is required",
            )
        if not isinstance(next_cursor, str):
            return _pagination_failure(
                pr_ref=pr_ref,
                review_target=review_target,
                resource=resource,
                page=page_number,
                reason="pagination_incomplete",
                message=f"{resource} page {page_number} next_cursor must be a string",
            )
        if next_cursor in seen_cursors:
            return _pagination_failure(
                pr_ref=pr_ref,
                review_target=review_target,
                resource=resource,
                page=page_number,
                reason="pagination_incomplete",
                message=f"{resource} page {page_number} pagination cursor repeated",
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor
        page_number += 1


def _pagination_failure(
    *,
    pr_ref: GitHubPRRef,
    review_target: ReviewTarget,
    resource: str,
    page: int,
    reason: str,
    message: str,
) -> FailClosedReadOutcome:
    gap = classify_github_read_gap(
        resource=resource,
        required=True,
        reason=reason,
        page=page,
        message=message,
    )
    return build_fail_closed_read_outcome(
        pr_ref=pr_ref,
        review_target=review_target,
        read_gaps=(gap,),
        page_gap_descriptors=(
            GitHubPageGapDescriptor(
                resource=resource,
                missing_page=page,
                underlying_reason=gap.reason,
                would_affect=("routing", "trust", "redaction"),
                examples=(message,),
            ),
        ),
    )


def _comment_from_payload(payload: dict[str, object], *, source_type: str) -> PullRequestComment:
    return PullRequestComment(
        id=_required_str(payload, "id", "pull request comment"),
        author=_required_str(payload, "author", "pull request comment"),
        author_association=_required_str(payload, "author_association", "pull request comment"),
        author_type=_required_str(payload, "author_type", "pull request comment"),
        body=_required_str(payload, "body", "pull request comment"),
        created_at=_required_str(payload, "created_at", "pull request comment"),
        trust_label="untrusted",
        source_type=source_type,
        url=_optional_str(payload, "url", "pull request comment"),
        path=_optional_str(payload, "path", "pull request comment"),
        line=_optional_positive_int(payload, "line", "pull request comment"),
        side=_optional_str(payload, "side", "pull request comment"),
        commit_sha=_optional_str(payload, "commit_sha", "pull request comment"),
        position=_optional_positive_int(payload, "position", "pull request comment"),
        source_provider="github",
    )


def _review_from_payload(payload: dict[str, object]) -> PullRequestReview:
    return PullRequestReview(
        id=_required_str(payload, "id", "pull request review"),
        author=_required_str(payload, "author", "pull request review"),
        author_association=_required_str(payload, "author_association", "pull request review"),
        author_type=_required_str(payload, "author_type", "pull request review"),
        state=_required_str(payload, "state", "pull request review"),
        created_at=_required_str(payload, "created_at", "pull request review"),
        trust_label="untrusted",
        source_type="review",
        body=_optional_text(payload, "body", "pull request review"),
        url=_optional_str(payload, "url", "pull request review"),
        source_provider="github",
    )


def _review_threads_from_payloads(
    *,
    pr_ref: GitHubPRRef,
    review_target: ReviewTarget,
    review_comment_payloads: list[dict[str, object]],
    thread_payloads: list[dict[str, object]],
) -> tuple[PullRequestReviewThread, ...] | FailClosedReadOutcome:
    comments_by_thread: dict[str, list[PullRequestComment]] = {}
    for payload in review_comment_payloads:
        thread_id = _required_str(payload, "thread_id", "review comment")
        comments_by_thread.setdefault(thread_id, []).append(
            _comment_from_payload(
                {
                    **payload,
                    "source_type": "review_thread",
                },
                source_type="review_thread",
            )
        )
    known_thread_ids = {
        _required_str(payload, "id", "review thread")
        for payload in thread_payloads
    }
    orphan_ids = sorted(set(comments_by_thread) - known_thread_ids)
    if orphan_ids:
        orphan_comment_ids = sorted(
            comment.id
            for thread_id in orphan_ids
            for comment in comments_by_thread[thread_id]
        )
        message = (
            f"review comments without thread state: {', '.join(orphan_comment_ids)} "
            f"(threads: {', '.join(orphan_ids)})"
        )
        return _pagination_failure(
            pr_ref=pr_ref,
            review_target=review_target,
            resource="thread_state",
            page=1,
            reason="thread_state_unknown",
            message=message,
        )
    threads: list[PullRequestReviewThread] = []
    for payload in thread_payloads:
        thread_id = _required_str(payload, "id", "review thread")
        comments = tuple(comments_by_thread.get(thread_id, ()))
        if not comments:
            continue
        threads.append(
            PullRequestReviewThread(
                id=thread_id,
                path=_required_str(payload, "path", "review thread"),
                resolved_status=_required_str(payload, "resolved_status", "review thread"),
                comments=comments,
            )
        )
    return tuple(threads)


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


def _actor_permission_dict(value: ActorPermissionGateResult | None) -> dict[str, object] | None:
    if value is None:
        return None
    transport_summary = None
    if value.transport_summary is not None:
        transport_summary = {
            "endpoint_kind": value.transport_summary.endpoint_kind,
            "retryable": value.transport_summary.retryable,
            "reason_code": None
            if value.transport_summary.reason_code is None
            else value.transport_summary.reason_code.value,
            "request_id": value.transport_summary.request_id,
        }
    return {
        "status": value.status.value,
        "actor": value.actor,
        "permission": value.permission,
        "checked_at": value.checked_at,
        "reason": value.reason,
        "reason_code": None if value.reason_code is None else value.reason_code.value,
        "credential_principal": value.credential_principal,
        "credential_source": value.credential_source,
        "repo_permission": value.repo_permission,
        "installation_permission": value.installation_permission,
        "endpoint_permission": value.endpoint_permission,
        "issue_comment_write": value.issue_comment_write,
        "check_method": value.check_method,
        "endpoint_method": value.endpoint_method,
        "checked_target": None if value.checked_target is None else dict(value.checked_target),
        "checked_target_hash": value.checked_target_hash,
        "endpoint": value.endpoint,
        "endpoint_kind": value.endpoint_kind,
        "transport_summary": transport_summary,
    }


def _pull_request_comment_dict(comment: PullRequestComment) -> dict[str, object]:
    return {
        "id": comment.id,
        "author": comment.author,
        "author_association": comment.author_association,
        "author_type": comment.author_type,
        "body": comment.body,
        "created_at": comment.created_at,
        "trust_label": comment.trust_label,
        "source_type": comment.source_type,
        "url": comment.url,
        "path": comment.path,
        "line": comment.line,
        "side": comment.side,
        "commit_sha": comment.commit_sha,
        "position": comment.position,
        "source_provider": comment.source_provider,
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


def _optional_positive_int(data: dict[str, object], key: str, label: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise GitHubReadError("invalid_payload", f"{label} {key} must be a positive integer or null")
    return value
