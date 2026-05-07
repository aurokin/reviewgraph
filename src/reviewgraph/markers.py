from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Protocol

from reviewgraph.hashing import (
    canonical_text_body,
    final_payload_hash,
    findings_hash,
    is_exact_reviewgraph_v1_marker_line,
    marker_payload_hash,
    parse_reviewgraph_v1_marker_line,
    visible_body_hash,
)
from reviewgraph.models import ArtifactKind, FinalIssueCommentPayload, RedactionStatus, ReviewTarget


class MarkerScanStatus(StrEnum):
    MATCHED = "matched"
    NO_MATCH = "no_match"
    DEFERRED_CONFLICT = "deferred_conflict"
    DEFERRED_MALFORMED = "deferred_malformed"


class MarkerReconciliationStatus(StrEnum):
    SAFE_TO_POST = "safe_to_post"
    RECONCILED_EXISTING = "reconciled_existing"
    FAILED_CLOSED = "failed_closed"


class MarkerReconciliationReasonCode(StrEnum):
    SAFE_TO_POST = "safe_to_post"
    MATCHED_EXISTING = "matched_existing"
    PAGINATION_INCOMPLETE = "pagination_incomplete"
    REPEATED_CURSOR = "repeated_cursor"
    PAGE_CAP_EXCEEDED = "page_cap_exceeded"
    COMMENT_CAP_EXCEEDED = "comment_cap_exceeded"
    MALFORMED_PAGE = "malformed_page"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    TRANSPORT_UNKNOWN = "transport_unknown"
    TRUSTED_MARKER_CONFLICT = "trusted_marker_conflict"
    TRUSTED_MARKER_MALFORMED = "trusted_marker_malformed"


RETRYABLE_MARKER_RECONCILIATION_REASON_CODES = frozenset(
    {
        MarkerReconciliationReasonCode.TIMEOUT,
        MarkerReconciliationReasonCode.RATE_LIMITED,
        MarkerReconciliationReasonCode.UNAVAILABLE,
        MarkerReconciliationReasonCode.TRANSPORT_UNKNOWN,
    }
)

MARKER_SCAN_ENDPOINT_KIND = "issue_comments"
_ALLOWED_MARKER_REQUEST_ID_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:/"
)
_SECRET_MARKER_REQUEST_ID_FRAGMENTS = ("token", "ghp_", "github_pat_", "gho_", "ghs_", "ghu_")


@dataclass(frozen=True)
class MarkerScanLimits:
    max_pages: int = 20
    max_comments: int = 1000
    timeout_seconds: int = 10

    def __post_init__(self) -> None:
        for name in ("max_pages", "max_comments", "timeout_seconds"):
            value = getattr(self, name)
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"marker scan {name} must be a positive integer")


@dataclass(frozen=True)
class MarkerScanTransportSummary:
    endpoint_kind: str
    page_count: int
    comment_count: int
    marker_count: int
    retryable: bool
    reason_code: MarkerReconciliationReasonCode | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        if self.endpoint_kind != MARKER_SCAN_ENDPOINT_KIND:
            raise ValueError("marker scan transport summary endpoint_kind must be issue_comments")
        for name in ("page_count", "comment_count", "marker_count"):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"marker scan transport summary {name} must be non-negative")
        if not isinstance(self.retryable, bool):
            raise ValueError("marker scan transport summary retryable must be bool")
        if self.reason_code is not None and not isinstance(
            self.reason_code,
            MarkerReconciliationReasonCode,
        ):
            raise ValueError("marker scan transport summary reason_code must be valid")
        if self.reason_code is None and self.retryable:
            raise ValueError("marker scan transport summary without failure cannot be retryable")
        if self.reason_code is not None:
            expected_retryable = self.reason_code in RETRYABLE_MARKER_RECONCILIATION_REASON_CODES
            if self.retryable != expected_retryable:
                raise ValueError("marker scan transport summary retryable mismatch")
        if self.request_id is not None and not _is_safe_marker_request_id(self.request_id):
            raise ValueError("marker scan transport summary request_id must be allowlisted")


@dataclass(frozen=True)
class PaginatedMarkerComment:
    comment_id: str
    body: str
    author_login: str
    author_type: str
    source_provider: str
    author_association: str | None = None

    def __post_init__(self) -> None:
        for name in ("comment_id", "body", "source_provider"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"paginated marker comment {name} is required")
        for name in ("author_login", "author_type"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise ValueError(f"paginated marker comment {name} must be a string")
        if self.author_association is not None and (
            not isinstance(self.author_association, str) or not self.author_association
        ):
            raise ValueError("paginated marker comment author_association must be non-empty")


@dataclass(frozen=True)
class MarkerCommentPage:
    comments: tuple[PaginatedMarkerComment, ...]
    next_cursor: object | None = None
    completed: bool = True
    request_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.comments, tuple) or not all(
            isinstance(comment, PaginatedMarkerComment) for comment in self.comments
        ):
            raise ValueError("marker comment page comments must be PaginatedMarkerComment tuple")
        if not isinstance(self.completed, bool):
            raise ValueError("marker comment page completed must be bool")
        if self.request_id is not None and not isinstance(self.request_id, str):
            raise ValueError("marker comment page request_id must be a string")


class MarkerScanTransportFailure(Exception):
    def __init__(
        self,
        reason_code: MarkerReconciliationReasonCode,
        *,
        request_id: str | None = None,
        raw_stderr: str | None = None,
    ) -> None:
        if not isinstance(reason_code, MarkerReconciliationReasonCode):
            raise ValueError("marker scan transport failure reason_code must be valid")
        self.reason_code = reason_code
        self.request_id = request_id
        self.raw_stderr = raw_stderr
        super().__init__(reason_code.value)


class PaginatedMarkerCommentTransport(Protocol):
    def get_issue_comments_page(
        self,
        owner_repo: str,
        pr_number: int,
        cursor: object | None,
    ) -> MarkerCommentPage: ...


@dataclass(frozen=True)
class TrustedMarkerReconciliationResult:
    status: MarkerReconciliationStatus
    reason_code: MarkerReconciliationReasonCode
    transport_summary: MarkerScanTransportSummary
    trusted_actor: str | None = None
    existing_comment_id: str | None = None
    marker: ReviewGraphMarker | None = None
    duplicate_comment_ids: tuple[str, ...] = ()
    writer_input_released: bool = False
    finalization_passed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.status, MarkerReconciliationStatus):
            raise ValueError("trusted marker reconciliation status must be valid")
        if not isinstance(self.reason_code, MarkerReconciliationReasonCode):
            raise ValueError("trusted marker reconciliation reason_code must be valid")
        if not isinstance(self.transport_summary, MarkerScanTransportSummary):
            raise ValueError("trusted marker reconciliation transport_summary must be valid")
        for name in ("trusted_actor", "existing_comment_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"trusted marker reconciliation {name} must be non-empty")
        if self.marker is not None and not isinstance(self.marker, ReviewGraphMarker):
            raise ValueError("trusted marker reconciliation marker must be a ReviewGraphMarker")
        if not isinstance(self.duplicate_comment_ids, tuple) or not all(
            isinstance(comment_id, str) and comment_id for comment_id in self.duplicate_comment_ids
        ):
            raise ValueError("trusted marker reconciliation duplicate_comment_ids must be non-empty strings")
        if self.writer_input_released or self.finalization_passed:
            raise ValueError("marker reconciliation cannot release writer input by itself")
        if self.status == MarkerReconciliationStatus.SAFE_TO_POST:
            if self.reason_code != MarkerReconciliationReasonCode.SAFE_TO_POST:
                raise ValueError("safe marker reconciliation requires safe_to_post reason")
            if self.trusted_actor is not None or self.existing_comment_id is not None or self.marker is not None:
                raise ValueError("safe marker reconciliation must not include existing marker data")
        if self.status == MarkerReconciliationStatus.RECONCILED_EXISTING:
            if self.reason_code != MarkerReconciliationReasonCode.MATCHED_EXISTING:
                raise ValueError("reconciled marker requires matched_existing reason")
            if self.trusted_actor is None or self.existing_comment_id is None or self.marker is None:
                raise ValueError("reconciled marker requires trusted actor, comment id, and marker")
        if self.status == MarkerReconciliationStatus.FAILED_CLOSED:
            if self.reason_code in {
                MarkerReconciliationReasonCode.SAFE_TO_POST,
                MarkerReconciliationReasonCode.MATCHED_EXISTING,
            }:
                raise ValueError("failed marker reconciliation requires failure reason")


@dataclass(frozen=True)
class ReviewGraphMarker:
    run_id: str
    target_hash: str
    payload_hash: str
    findings_hash: str
    line: str

    def __post_init__(self) -> None:
        parsed = parse_reviewgraph_v1_marker_line(self.line)
        if parsed is None:
            raise ValueError("review graph marker line must match v1 grammar")
        if parsed != {
            "run_id": self.run_id,
            "target": self.target_hash,
            "payload": self.payload_hash,
            "findings": self.findings_hash,
        }:
            raise ValueError("review graph marker fields must match marker line")


@dataclass(frozen=True)
class ExistingComment:
    comment_id: str
    body: str

    def __post_init__(self) -> None:
        if not isinstance(self.comment_id, str) or not self.comment_id:
            raise ValueError("existing comment id is required")
        if not isinstance(self.body, str) or not self.body:
            raise ValueError("existing comment body is required")


@dataclass(frozen=True)
class MarkerScanResult:
    status: MarkerScanStatus
    existing_comment_id: str | None = None
    marker: ReviewGraphMarker | None = None
    reason: str | None = None
    writer_input_released: bool = False
    finalization_passed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.status, MarkerScanStatus):
            raise ValueError("marker scan status must be valid")
        if self.existing_comment_id is not None and not self.existing_comment_id:
            raise ValueError("marker scan existing_comment_id must be non-empty")
        if self.marker is not None and not isinstance(self.marker, ReviewGraphMarker):
            raise ValueError("marker scan marker must be a ReviewGraphMarker")
        if self.reason is not None and not self.reason:
            raise ValueError("marker scan reason must be non-empty")
        if not isinstance(self.writer_input_released, bool):
            raise ValueError("marker scan writer_input_released must be bool")
        if not isinstance(self.finalization_passed, bool):
            raise ValueError("marker scan finalization_passed must be bool")
        if self.writer_input_released or self.finalization_passed:
            raise ValueError("marker scan results are trust-neutral and cannot release writer input")
        if self.status == MarkerScanStatus.MATCHED:
            if self.existing_comment_id is None or self.marker is None:
                raise ValueError("matched marker scan requires existing comment and marker")
        if self.status == MarkerScanStatus.NO_MATCH:
            if self.existing_comment_id is not None or self.marker is not None:
                raise ValueError("no-match marker scan must not include a marker")
        if self.status == MarkerScanStatus.DEFERRED_CONFLICT:
            if self.existing_comment_id is None or self.marker is None:
                raise ValueError("deferred marker conflict requires existing comment and marker")
        if self.status == MarkerScanStatus.DEFERRED_MALFORMED:
            if self.existing_comment_id is None or self.marker is not None:
                raise ValueError("deferred malformed marker requires existing comment and no parsed marker")


def build_reviewgraph_marker_line(
    *,
    run_id: str,
    review_target: ReviewTarget,
    visible_body: str,
    finding_fingerprints: Iterable[str],
) -> str:
    if not isinstance(review_target, ReviewTarget):
        raise ValueError("review_target must be a ReviewTarget")
    body = canonical_text_body(visible_body)
    marker_line = (
        "<!-- reviewgraph:v1 "
        f"run_id={run_id} "
        f"target={review_target.target_hash()} "
        f"payload={marker_payload_hash(body)} "
        f"findings={findings_hash(finding_fingerprints)} -->"
    )
    if not is_exact_reviewgraph_v1_marker_line(marker_line):
        raise ValueError("generated marker line is invalid")
    return marker_line


def build_final_issue_comment_payload(
    *,
    run_id: str,
    review_target: ReviewTarget,
    visible_body: str,
    item_fingerprints: Iterable[str],
    redaction_status: RedactionStatus,
) -> FinalIssueCommentPayload:
    body_without_marker = canonical_text_body(visible_body)
    fingerprints = tuple(sorted(item_fingerprints))
    marker_line = build_reviewgraph_marker_line(
        run_id=run_id,
        review_target=review_target,
        visible_body=body_without_marker,
        finding_fingerprints=fingerprints,
    )
    body = f"{body_without_marker}{marker_line}\n"
    selected_findings_hash = findings_hash(fingerprints)
    selected_marker_payload_hash = marker_payload_hash(body_without_marker)
    return FinalIssueCommentPayload(
        artifact_kind=ArtifactKind.ISSUE_COMMENT,
        review_target=review_target,
        body=body,
        marker_line=marker_line,
        marker_run_id=run_id,
        marker_target_hash=review_target.target_hash(),
        marker_payload_hash=selected_marker_payload_hash,
        marker_findings_hash=selected_findings_hash,
        visible_body_hash=visible_body_hash(body),
        final_payload_hash=final_payload_hash(body),
        findings_hash=selected_findings_hash,
        item_fingerprints=fingerprints,
        redaction_status=redaction_status,
    )


def parse_reviewgraph_marker_line(line: str) -> ReviewGraphMarker | None:
    parsed = parse_reviewgraph_v1_marker_line(line)
    if parsed is None:
        return None
    return ReviewGraphMarker(
        run_id=parsed["run_id"],
        target_hash=parsed["target"],
        payload_hash=parsed["payload"],
        findings_hash=parsed["findings"],
        line=line,
    )


def scan_final_line_marker(body: str) -> ReviewGraphMarker | None:
    final_line = _body_final_line(body)
    if final_line is None:
        return None
    return parse_reviewgraph_marker_line(final_line)


def reconcile_existing_markers(
    *,
    existing_comments: Iterable[ExistingComment],
    expected_target_hash: str,
    expected_payload_hash: str,
    expected_findings_hash: str,
) -> MarkerScanResult:
    matched: MarkerScanResult | None = None
    deferred_conflict: MarkerScanResult | None = None
    deferred_malformed: MarkerScanResult | None = None
    for comment in existing_comments:
        if not isinstance(comment, ExistingComment):
            raise ValueError("existing comments must be ExistingComment values")
        final_line = _body_final_line(comment.body)
        marker = parse_reviewgraph_marker_line(final_line) if final_line is not None else None
        if marker is None:
            if _looks_like_reviewgraph_marker(final_line):
                deferred_malformed = MarkerScanResult(
                    status=MarkerScanStatus.DEFERRED_MALFORMED,
                    existing_comment_id=comment.comment_id,
                    reason="malformed reviewgraph marker final line",
                )
            continue
        if marker.target_hash != expected_target_hash or marker.findings_hash != expected_findings_hash:
            continue
        if marker.payload_hash == expected_payload_hash:
            matched = MarkerScanResult(
                status=MarkerScanStatus.MATCHED,
                existing_comment_id=comment.comment_id,
                marker=marker,
                reason="matching marker",
            )
            continue
        deferred_conflict = MarkerScanResult(
            status=MarkerScanStatus.DEFERRED_CONFLICT,
            existing_comment_id=comment.comment_id,
            marker=marker,
            reason="same target and findings with different payload",
        )
    if deferred_malformed is not None:
        return deferred_malformed
    if deferred_conflict is not None:
        return deferred_conflict
    if matched is not None:
        return matched
    return MarkerScanResult(status=MarkerScanStatus.NO_MATCH, reason="no matching marker")


def reconcile_paginated_trusted_markers(
    *,
    transport: PaginatedMarkerCommentTransport,
    owner_repo: str,
    pr_number: int,
    approved_actor: str,
    trusted_bot_authors: Iterable[str],
    expected_target_hash: str,
    expected_payload_hash: str,
    expected_findings_hash: str,
    limits: MarkerScanLimits | None = None,
) -> TrustedMarkerReconciliationResult:
    _require_non_empty_string(owner_repo, "marker scan owner_repo")
    if not isinstance(pr_number, int) or pr_number <= 0:
        raise ValueError("marker scan pr_number must be a positive integer")
    _require_non_empty_string(approved_actor, "marker scan approved_actor")
    for name, value in (
        ("expected_target_hash", expected_target_hash),
        ("expected_payload_hash", expected_payload_hash),
        ("expected_findings_hash", expected_findings_hash),
    ):
        _require_non_empty_string(value, f"marker scan {name}")
    scan_limits = limits or MarkerScanLimits()
    if not isinstance(scan_limits, MarkerScanLimits):
        raise ValueError("marker scan limits must be MarkerScanLimits")
    trusted_bots = tuple(trusted_bot_authors)
    if not all(isinstance(author, str) and author for author in trusted_bots):
        raise ValueError("trusted marker bot authors must be non-empty strings")

    cursor: object | None = None
    seen_cursors: set[object | None] = {None}
    page_count = 0
    comment_count = 0
    marker_count = 0
    request_id: str | None = None
    trusted_match: tuple[PaginatedMarkerComment, ReviewGraphMarker] | None = None
    duplicate_comment_ids: list[str] = []
    deferred_failure: TrustedMarkerReconciliationResult | None = None

    while True:
        if page_count >= scan_limits.max_pages:
            return _trusted_marker_failure(
                MarkerReconciliationReasonCode.PAGE_CAP_EXCEEDED,
                page_count=page_count,
                comment_count=comment_count,
                marker_count=marker_count,
                request_id=request_id,
            )
        try:
            page = transport.get_issue_comments_page(owner_repo, pr_number, cursor)
        except MarkerScanTransportFailure as exc:
            return _trusted_marker_failure(
                exc.reason_code,
                page_count=page_count,
                comment_count=comment_count,
                marker_count=marker_count,
                request_id=exc.request_id,
            )
        except Exception:
            return _trusted_marker_failure(
                MarkerReconciliationReasonCode.TRANSPORT_UNKNOWN,
                page_count=page_count,
                comment_count=comment_count,
                marker_count=marker_count,
                request_id=request_id,
            )

        if not isinstance(page, MarkerCommentPage):
            return _trusted_marker_failure(
                MarkerReconciliationReasonCode.MALFORMED_PAGE,
                page_count=page_count,
                comment_count=comment_count,
                marker_count=marker_count,
                request_id=request_id,
            )
        page_count += 1
        request_id = _safe_marker_request_id(page.request_id)
        if page.completed and page.next_cursor is not None:
            return _trusted_marker_failure(
                MarkerReconciliationReasonCode.MALFORMED_PAGE,
                page_count=page_count,
                comment_count=comment_count,
                marker_count=marker_count,
                request_id=request_id,
            )
        if not page.completed and page.next_cursor is None:
            return _trusted_marker_failure(
                MarkerReconciliationReasonCode.PAGINATION_INCOMPLETE,
                page_count=page_count,
                comment_count=comment_count,
                marker_count=marker_count,
                request_id=request_id,
            )
        comment_count += len(page.comments)
        if comment_count > scan_limits.max_comments:
            return _trusted_marker_failure(
                MarkerReconciliationReasonCode.COMMENT_CAP_EXCEEDED,
                page_count=page_count,
                comment_count=comment_count,
                marker_count=marker_count,
                request_id=request_id,
            )
        for comment in page.comments:
            final_line = _body_final_line(comment.body)
            marker = parse_reviewgraph_marker_line(final_line) if final_line is not None else None
            looks_like_marker = _looks_like_reviewgraph_marker(final_line)
            if marker is not None or looks_like_marker:
                marker_count += 1
            trusted = _is_trusted_marker_author(
                comment,
                approved_actor=approved_actor,
                trusted_bot_authors=trusted_bots,
            )
            if not trusted:
                continue
            if marker is None:
                if looks_like_marker and deferred_failure is None:
                    deferred_failure = _trusted_marker_failure(
                        MarkerReconciliationReasonCode.TRUSTED_MARKER_MALFORMED,
                        page_count=page_count,
                        comment_count=comment_count,
                        marker_count=marker_count,
                        request_id=request_id,
                    )
                continue
            if marker.target_hash != expected_target_hash or marker.findings_hash != expected_findings_hash:
                continue
            if marker.payload_hash != expected_payload_hash:
                if deferred_failure is None:
                    deferred_failure = _trusted_marker_failure(
                        MarkerReconciliationReasonCode.TRUSTED_MARKER_CONFLICT,
                        page_count=page_count,
                        comment_count=comment_count,
                        marker_count=marker_count,
                        request_id=request_id,
                    )
                continue
            if trusted_match is None:
                trusted_match = (comment, marker)
            else:
                duplicate_comment_ids.append(comment.comment_id)

        if page.completed:
            break
        if page.next_cursor in seen_cursors:
            return _trusted_marker_failure(
                MarkerReconciliationReasonCode.REPEATED_CURSOR,
                page_count=page_count,
                comment_count=comment_count,
                marker_count=marker_count,
                request_id=request_id,
            )
        seen_cursors.add(page.next_cursor)
        cursor = page.next_cursor

    if deferred_failure is not None:
        return _trusted_marker_failure(
            deferred_failure.reason_code,
            page_count=page_count,
            comment_count=comment_count,
            marker_count=marker_count,
            request_id=request_id,
        )
    if trusted_match is not None:
        comment, marker = trusted_match
        return TrustedMarkerReconciliationResult(
            status=MarkerReconciliationStatus.RECONCILED_EXISTING,
            reason_code=MarkerReconciliationReasonCode.MATCHED_EXISTING,
            trusted_actor=comment.author_login,
            existing_comment_id=comment.comment_id,
            marker=marker,
            duplicate_comment_ids=tuple(duplicate_comment_ids),
            transport_summary=_marker_scan_summary(
                page_count=page_count,
                comment_count=comment_count,
                marker_count=marker_count,
                request_id=request_id,
            ),
        )
    return TrustedMarkerReconciliationResult(
        status=MarkerReconciliationStatus.SAFE_TO_POST,
        reason_code=MarkerReconciliationReasonCode.SAFE_TO_POST,
        transport_summary=_marker_scan_summary(
            page_count=page_count,
            comment_count=comment_count,
            marker_count=marker_count,
            request_id=request_id,
        ),
    )


def _body_final_line(body: str) -> str | None:
    if not isinstance(body, str) or not body:
        return None
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.endswith("\n"):
        normalized = normalized[:-1]
    if not normalized:
        return ""
    return normalized.split("\n")[-1]


def _looks_like_reviewgraph_marker(line: str | None) -> bool:
    return isinstance(line, str) and line.startswith("<!-- reviewgraph:")


def _trusted_marker_failure(
    reason_code: MarkerReconciliationReasonCode,
    *,
    page_count: int,
    comment_count: int,
    marker_count: int,
    request_id: str | None,
) -> TrustedMarkerReconciliationResult:
    return TrustedMarkerReconciliationResult(
        status=MarkerReconciliationStatus.FAILED_CLOSED,
        reason_code=reason_code,
        transport_summary=_marker_scan_summary(
            page_count=page_count,
            comment_count=comment_count,
            marker_count=marker_count,
            request_id=request_id,
            reason_code=reason_code,
        ),
    )


def _marker_scan_summary(
    *,
    page_count: int,
    comment_count: int,
    marker_count: int,
    request_id: str | None,
    reason_code: MarkerReconciliationReasonCode | None = None,
) -> MarkerScanTransportSummary:
    return MarkerScanTransportSummary(
        endpoint_kind=MARKER_SCAN_ENDPOINT_KIND,
        page_count=page_count,
        comment_count=comment_count,
        marker_count=marker_count,
        retryable=reason_code in RETRYABLE_MARKER_RECONCILIATION_REASON_CODES,
        reason_code=reason_code,
        request_id=_safe_marker_request_id(request_id),
    )


def _is_trusted_marker_author(
    comment: PaginatedMarkerComment,
    *,
    approved_actor: str,
    trusted_bot_authors: tuple[str, ...],
) -> bool:
    if comment.source_provider != "github":
        return False
    if not comment.author_login or not comment.author_type:
        return False
    actor_type = comment.author_type.casefold()
    if actor_type not in {"user", "bot"}:
        return False
    if comment.author_login == approved_actor:
        return True
    if actor_type == "bot" and comment.author_login in trusted_bot_authors:
        return True
    return False


def _safe_marker_request_id(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        return None
    if len(value) > 128:
        return None
    if any(char not in _ALLOWED_MARKER_REQUEST_ID_CHARS for char in value):
        return None
    if any(secret in value.casefold() for secret in _SECRET_MARKER_REQUEST_ID_FRAGMENTS):
        return None
    return value


def _is_safe_marker_request_id(value: str) -> bool:
    return _safe_marker_request_id(value) == value


def _require_non_empty_string(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")
