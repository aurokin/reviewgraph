from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Protocol

from reviewgraph.markers import (
    MarkerScanLimits,
    PaginatedMarkerCommentTransport,
    reconcile_paginated_trusted_markers,
)
from reviewgraph.models import (
    ArtifactKind,
    GitHubWriterResult,
    MarkerReconciliationReasonCode,
    MarkerReconciliationResult,
    MarkerReconciliationStatus,
    WriterStatus,
)
from reviewgraph.payload_validation import validate_final_issue_comment_payload
from reviewgraph.redaction import redact_text
from reviewgraph.writer_input import FinalizedIssueCommentWriterInput


class GitHubIssueCommentWriterOutcomeDetail(StrEnum):
    POSTED = "posted"
    RECONCILED_EXISTING = "reconciled_existing"
    VALIDATION_FAILED = "validation_failed"
    TRANSPORT_FAILED = "transport_failed"
    RETRYABLE_UNKNOWN = "retryable_unknown"
    AMBIGUOUS_UNRESOLVED = "ambiguous_unresolved"
    FORBIDDEN_SECOND_POST = "forbidden_second_post"
    TRUSTED_MARKER_CONFLICT = "trusted_marker_conflict"
    RESPONSE_ACTOR_MISMATCH = "response_actor_mismatch"
    MALFORMED_RESPONSE = "malformed_response"


class GitHubIssueCommentWriterReasonCode(StrEnum):
    VALIDATION_FAILED = "validation_failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    TRANSPORT_UNKNOWN = "transport_unknown"
    AMBIGUOUS_ACCEPTED = "ambiguous_accepted"
    AMBIGUOUS_UNRESOLVED = "ambiguous_unresolved"
    FORBIDDEN_SECOND_POST = "forbidden_second_post"
    TRUSTED_MARKER_CONFLICT = "trusted_marker_conflict"
    RESPONSE_ACTOR_MISMATCH = "response_actor_mismatch"


_RETRYABLE_WRITER_REASONS = frozenset(
    {
        GitHubIssueCommentWriterReasonCode.TIMEOUT,
        GitHubIssueCommentWriterReasonCode.RATE_LIMITED,
        GitHubIssueCommentWriterReasonCode.UNAVAILABLE,
        GitHubIssueCommentWriterReasonCode.TRANSPORT_UNKNOWN,
        GitHubIssueCommentWriterReasonCode.AMBIGUOUS_ACCEPTED,
        GitHubIssueCommentWriterReasonCode.AMBIGUOUS_UNRESOLVED,
    }
)


@dataclass(frozen=True)
class GitHubIssueCommentPostResponse:
    comment_id: str | None
    author_login: str | None
    request_id: str | None = None


class GitHubIssueCommentPostTransportFailure(Exception):
    def __init__(
        self,
        reason_code: GitHubIssueCommentWriterReasonCode,
        *,
        request_id: str | None = None,
        ambiguous_accepted: bool = False,
    ) -> None:
        if not isinstance(reason_code, GitHubIssueCommentWriterReasonCode):
            raise ValueError("github issue-comment writer failure reason_code must be valid")
        self.reason_code = reason_code
        self.request_id = request_id
        self.ambiguous_accepted = ambiguous_accepted or reason_code == GitHubIssueCommentWriterReasonCode.AMBIGUOUS_ACCEPTED
        super().__init__(reason_code.value)


class GitHubIssueCommentPostTransport(Protocol):
    def post_issue_comment(
        self,
        owner_repo: str,
        pr_number: int,
        body: dict[str, str],
        timeout_seconds: int,
    ) -> GitHubIssueCommentPostResponse: ...


@dataclass(frozen=True)
class GitHubIssueCommentWriterTransportSummary:
    endpoint_kind: str
    method: str
    endpoint: str
    post_attempt_count: int
    recovery_scan_count: int
    retryable: bool
    reason_code: str | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        if self.endpoint_kind != "issue_comment":
            raise ValueError("writer transport summary endpoint_kind must be issue_comment")
        if self.method != "POST":
            raise ValueError("writer transport summary method must be POST")
        if not isinstance(self.endpoint, str) or not self.endpoint.startswith("/repos/"):
            raise ValueError("writer transport summary endpoint must be redacted REST path")
        for name in ("post_attempt_count", "recovery_scan_count"):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"writer transport summary {name} must be non-negative")
        if not isinstance(self.retryable, bool):
            raise ValueError("writer transport summary retryable must be bool")
        _require_optional_safe_text(self.reason_code, "writer transport summary reason_code")
        _require_optional_safe_text(self.request_id, "writer transport summary request_id")


@dataclass(frozen=True)
class GitHubIssueCommentWriterAttemptResult:
    writer_result: GitHubWriterResult
    outcome_detail: GitHubIssueCommentWriterOutcomeDetail
    transport_summary: GitHubIssueCommentWriterTransportSummary
    marker_reconciliation: MarkerReconciliationResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.writer_result, GitHubWriterResult):
            raise ValueError("writer attempt result writer_result must be GitHubWriterResult")
        if not isinstance(self.outcome_detail, GitHubIssueCommentWriterOutcomeDetail):
            raise ValueError("writer attempt result outcome_detail must be valid")
        if not isinstance(self.transport_summary, GitHubIssueCommentWriterTransportSummary):
            raise ValueError("writer attempt result transport_summary must be valid")
        if self.marker_reconciliation is not None and not isinstance(
            self.marker_reconciliation,
            MarkerReconciliationResult,
        ):
            raise ValueError("writer attempt result marker_reconciliation must be valid")


class GitHubIssueCommentWriter:
    def __init__(
        self,
        *,
        transport: GitHubIssueCommentPostTransport,
        recovery_marker_transport: PaginatedMarkerCommentTransport | None = None,
        trusted_bot_authors: Iterable[str] = (),
        timeout_seconds: int = 10,
        marker_limits: MarkerScanLimits | None = None,
    ) -> None:
        self.transport = transport
        self.recovery_marker_transport = recovery_marker_transport
        self.trusted_bot_authors = tuple(trusted_bot_authors)
        if not all(isinstance(author, str) and author for author in self.trusted_bot_authors):
            raise ValueError("trusted bot authors must be non-empty strings")
        if not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise ValueError("github issue-comment writer timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds
        self.marker_limits = marker_limits
        self._post_attempted_keys: set[tuple[str, str, str, str]] = set()

    def post_issue_comment(
        self,
        writer_input: FinalizedIssueCommentWriterInput,
    ) -> GitHubIssueCommentWriterAttemptResult:
        if not isinstance(writer_input, FinalizedIssueCommentWriterInput):
            raise ValueError("github writer accepts only finalized issue-comment writer input")
        validation = validate_final_issue_comment_payload(writer_input.final_payload)
        if validation.status.value != "pass":
            reason = (
                validation.reason_code.value if validation.reason_code is not None else "payload_validation_failed"
            )
            return self._failed_result(
                writer_input,
                outcome_detail=GitHubIssueCommentWriterOutcomeDetail.VALIDATION_FAILED,
                reason_code=reason,
                retryable=False,
                post_attempt_count=0,
            )

        key = _retry_sequence_key(writer_input)
        if key in self._post_attempted_keys:
            return self._recover_after_potential_acceptance(
                writer_input,
                post_attempt_count=0,
                safe_to_post_detail=GitHubIssueCommentWriterOutcomeDetail.FORBIDDEN_SECOND_POST,
                safe_to_post_reason=GitHubIssueCommentWriterReasonCode.FORBIDDEN_SECOND_POST.value,
                safe_to_post_retryable=False,
            )

        self._post_attempted_keys.add(key)
        endpoint = _issue_comment_endpoint(writer_input)
        try:
            response = self.transport.post_issue_comment(
                writer_input.final_payload.review_target.owner_repo,
                writer_input.final_payload.review_target.pr_number,
                {"body": writer_input.final_payload.body},
                self.timeout_seconds,
            )
        except GitHubIssueCommentPostTransportFailure as exc:
            if exc.ambiguous_accepted:
                return self._recover_after_potential_acceptance(
                    writer_input,
                    post_attempt_count=1,
                    request_id=exc.request_id,
                    safe_to_post_detail=GitHubIssueCommentWriterOutcomeDetail.AMBIGUOUS_UNRESOLVED,
                    safe_to_post_reason=GitHubIssueCommentWriterReasonCode.AMBIGUOUS_UNRESOLVED.value,
                    safe_to_post_retryable=True,
                )
            return self._failed_result(
                writer_input,
                outcome_detail=GitHubIssueCommentWriterOutcomeDetail.TRANSPORT_FAILED,
                reason_code=exc.reason_code.value,
                retryable=exc.reason_code in _RETRYABLE_WRITER_REASONS,
                request_id=exc.request_id,
                post_attempt_count=1,
            )
        except Exception:
            return self._failed_result(
                writer_input,
                outcome_detail=GitHubIssueCommentWriterOutcomeDetail.TRANSPORT_FAILED,
                reason_code=GitHubIssueCommentWriterReasonCode.TRANSPORT_UNKNOWN.value,
                retryable=True,
                post_attempt_count=1,
            )

        if not isinstance(response, GitHubIssueCommentPostResponse):
            return self._failed_result(
                writer_input,
                outcome_detail=GitHubIssueCommentWriterOutcomeDetail.MALFORMED_RESPONSE,
                reason_code=GitHubIssueCommentWriterReasonCode.MALFORMED_RESPONSE.value,
                retryable=False,
                post_attempt_count=1,
                endpoint=endpoint,
            )
        if not isinstance(response.comment_id, str) or not response.comment_id:
            return self._failed_result(
                writer_input,
                outcome_detail=GitHubIssueCommentWriterOutcomeDetail.MALFORMED_RESPONSE,
                reason_code=GitHubIssueCommentWriterReasonCode.MALFORMED_RESPONSE.value,
                retryable=False,
                request_id=response.request_id,
                post_attempt_count=1,
                endpoint=endpoint,
            )
        if response.author_login != writer_input.approved_actor:
            return self._failed_result(
                writer_input,
                outcome_detail=GitHubIssueCommentWriterOutcomeDetail.RESPONSE_ACTOR_MISMATCH,
                reason_code=GitHubIssueCommentWriterReasonCode.RESPONSE_ACTOR_MISMATCH.value,
                retryable=False,
                request_id=response.request_id,
                post_attempt_count=1,
                endpoint=endpoint,
            )
        return GitHubIssueCommentWriterAttemptResult(
            writer_result=GitHubWriterResult(
                status=WriterStatus.POSTED,
                artifact_kind=ArtifactKind.ISSUE_COMMENT,
                target_hash=writer_input.target_hash,
                payload_hash=writer_input.final_payload_hash,
                comment_id=response.comment_id,
            ),
            outcome_detail=GitHubIssueCommentWriterOutcomeDetail.POSTED,
            transport_summary=self._summary(
                writer_input,
                post_attempt_count=1,
                recovery_scan_count=0,
                retryable=False,
                request_id=response.request_id,
            ),
        )

    def _recover_after_potential_acceptance(
        self,
        writer_input: FinalizedIssueCommentWriterInput,
        *,
        post_attempt_count: int,
        safe_to_post_detail: GitHubIssueCommentWriterOutcomeDetail,
        safe_to_post_reason: str,
        safe_to_post_retryable: bool,
        request_id: str | None = None,
    ) -> GitHubIssueCommentWriterAttemptResult:
        if self.recovery_marker_transport is None:
            return self._failed_result(
                writer_input,
                outcome_detail=safe_to_post_detail,
                reason_code=safe_to_post_reason,
                retryable=safe_to_post_retryable,
                request_id=request_id,
                post_attempt_count=post_attempt_count,
            )
        marker = reconcile_paginated_trusted_markers(
            transport=self.recovery_marker_transport,
            owner_repo=writer_input.final_payload.review_target.owner_repo,
            pr_number=writer_input.final_payload.review_target.pr_number,
            approved_actor=writer_input.approved_actor,
            trusted_bot_authors=self.trusted_bot_authors,
            expected_target_hash=writer_input.final_payload.marker_target_hash,
            expected_payload_hash=writer_input.final_payload.marker_payload_hash,
            expected_findings_hash=writer_input.final_payload.marker_findings_hash,
            limits=self.marker_limits,
        )
        if marker.status == MarkerReconciliationStatus.RECONCILED_EXISTING:
            return GitHubIssueCommentWriterAttemptResult(
                writer_result=GitHubWriterResult(
                    status=WriterStatus.RECONCILED,
                    artifact_kind=ArtifactKind.ISSUE_COMMENT,
                    target_hash=writer_input.target_hash,
                    payload_hash=writer_input.final_payload_hash,
                    comment_id=marker.existing_comment_id,
                ),
                outcome_detail=GitHubIssueCommentWriterOutcomeDetail.RECONCILED_EXISTING,
                transport_summary=self._summary(
                    writer_input,
                    post_attempt_count=post_attempt_count,
                    recovery_scan_count=1,
                    retryable=False,
                    reason_code=marker.reason_code.value,
                    request_id=marker.transport_summary.request_id,
                ),
                marker_reconciliation=marker,
            )
        if marker.status == MarkerReconciliationStatus.SAFE_TO_POST:
            return self._failed_result(
                writer_input,
                outcome_detail=safe_to_post_detail,
                reason_code=safe_to_post_reason,
                retryable=safe_to_post_retryable,
                request_id=marker.transport_summary.request_id,
                post_attempt_count=post_attempt_count,
                recovery_scan_count=1,
                marker_reconciliation=marker,
            )
        outcome_detail = (
            GitHubIssueCommentWriterOutcomeDetail.TRUSTED_MARKER_CONFLICT
            if marker.reason_code == MarkerReconciliationReasonCode.TRUSTED_MARKER_CONFLICT
            else (
                GitHubIssueCommentWriterOutcomeDetail.RETRYABLE_UNKNOWN
                if marker.transport_summary.retryable
                else GitHubIssueCommentWriterOutcomeDetail.TRANSPORT_FAILED
            )
        )
        return self._failed_result(
            writer_input,
            outcome_detail=outcome_detail,
            reason_code=marker.reason_code.value,
            retryable=marker.transport_summary.retryable,
            request_id=marker.transport_summary.request_id,
            post_attempt_count=post_attempt_count,
            recovery_scan_count=1,
            marker_reconciliation=marker,
        )

    def _failed_result(
        self,
        writer_input: FinalizedIssueCommentWriterInput,
        *,
        outcome_detail: GitHubIssueCommentWriterOutcomeDetail,
        reason_code: str,
        retryable: bool,
        request_id: str | None = None,
        post_attempt_count: int,
        recovery_scan_count: int = 0,
        marker_reconciliation: MarkerReconciliationResult | None = None,
        endpoint: str | None = None,
    ) -> GitHubIssueCommentWriterAttemptResult:
        return GitHubIssueCommentWriterAttemptResult(
            writer_result=GitHubWriterResult(
                status=WriterStatus.FAILED,
                artifact_kind=ArtifactKind.ISSUE_COMMENT,
                target_hash=writer_input.target_hash,
                payload_hash=writer_input.final_payload_hash,
                error=reason_code,
            ),
            outcome_detail=outcome_detail,
            transport_summary=self._summary(
                writer_input,
                post_attempt_count=post_attempt_count,
                recovery_scan_count=recovery_scan_count,
                retryable=retryable,
                reason_code=reason_code,
                request_id=request_id,
                endpoint=endpoint,
            ),
            marker_reconciliation=marker_reconciliation,
        )

    def _summary(
        self,
        writer_input: FinalizedIssueCommentWriterInput,
        *,
        post_attempt_count: int,
        recovery_scan_count: int,
        retryable: bool,
        reason_code: str | None = None,
        request_id: str | None = None,
        endpoint: str | None = None,
    ) -> GitHubIssueCommentWriterTransportSummary:
        return GitHubIssueCommentWriterTransportSummary(
            endpoint_kind="issue_comment",
            method="POST",
            endpoint=endpoint or _issue_comment_endpoint(writer_input),
            post_attempt_count=post_attempt_count,
            recovery_scan_count=recovery_scan_count,
            retryable=retryable,
            reason_code=reason_code,
            request_id=_safe_request_id(request_id),
        )


def _retry_sequence_key(writer_input: FinalizedIssueCommentWriterInput) -> tuple[str, str, str, str]:
    return (
        writer_input.run_id,
        writer_input.final_payload.marker_target_hash,
        writer_input.final_payload.marker_payload_hash,
        writer_input.final_payload.marker_findings_hash,
    )


def _issue_comment_endpoint(writer_input: FinalizedIssueCommentWriterInput) -> str:
    target = writer_input.final_payload.review_target
    return f"/repos/{target.owner_repo}/issues/{target.pr_number}/comments"


def _require_optional_safe_text(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be non-empty")
    lowered = value.casefold()
    if any(secret in lowered for secret in ("token", "ghp_", "github_pat_", "gho_", "ghs_", "ghu_")):
        raise ValueError(f"{field_name} must be redacted")


def _safe_request_id(request_id: str | None) -> str | None:
    if request_id is None:
        return None
    if not isinstance(request_id, str) or not request_id:
        return None
    redacted = redact_text(request_id)
    if redacted.redacted:
        return None
    if len(request_id) > 128:
        return None
    allowed = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:/")
    if any(char not in allowed for char in request_id):
        return None
    return request_id
