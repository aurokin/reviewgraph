from __future__ import annotations

from dataclasses import dataclass

from reviewgraph.finalization import FinalizeGithubPayloadResult
from reviewgraph.markers import MarkerCommentPage, PaginatedMarkerComment
from reviewgraph.models import (
    ArtifactKind,
    FinalIssueCommentPayload,
    FinalizationState,
    GateStatus,
    GitHubWriterResult,
    MarkerReconciliationStatus,
    WriterStatus,
)
from reviewgraph.payload_validation import validate_final_issue_comment_payload


@dataclass(frozen=True)
class FinalizedIssueCommentWriterInput:
    final_payload: FinalIssueCommentPayload
    final_payload_hash: str
    target_hash: str
    marker_reconciliation_status: MarkerReconciliationStatus
    approved_actor: str
    run_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.final_payload, FinalIssueCommentPayload):
            raise ValueError("finalized writer input requires final payload")
        if self.final_payload_hash != self.final_payload.final_payload_hash:
            raise ValueError("finalized writer input payload hash mismatch")
        if self.target_hash != self.final_payload.review_target.target_hash():
            raise ValueError("finalized writer input target hash mismatch")
        if self.marker_reconciliation_status != MarkerReconciliationStatus.SAFE_TO_POST:
            raise ValueError("finalized writer input requires safe marker reconciliation")
        if not isinstance(self.approved_actor, str) or not self.approved_actor:
            raise ValueError("finalized writer input approved_actor is required")
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("finalized writer input run_id is required")


@dataclass(frozen=True)
class FakeIssueComment:
    comment_id: str
    body: str
    author_login: str
    author_type: str = "Bot"


def build_finalized_issue_comment_writer_input(
    *,
    finalization: FinalizeGithubPayloadResult,
    approved_actor: str,
    run_id: str,
) -> FinalizedIssueCommentWriterInput:
    if not isinstance(finalization, FinalizeGithubPayloadResult):
        raise ValueError("finalized writer input requires finalization result")
    if finalization.finalization_status.state != FinalizationState.FINALIZED:
        raise ValueError("finalized writer input requires finalized state")
    if not finalization.writer_input_released:
        raise ValueError("finalized writer input requires released writer input")
    if finalization.final_payload is None:
        raise ValueError("finalized writer input requires final payload")
    if (
        finalization.actor_permission_finalization_check is None
        or finalization.actor_permission_finalization_check.status != GateStatus.PASS
    ):
        raise ValueError("finalized writer input requires passed actor permission finalization check")
    if finalization.target_freshness_check is None or finalization.target_freshness_check.status != GateStatus.PASS:
        raise ValueError("finalized writer input requires passed target freshness check")
    if finalization.payload_validation is None or finalization.payload_validation.status != GateStatus.PASS:
        raise ValueError("finalized writer input requires passed payload validation")
    if finalization.marker_reconciliation is None:
        raise ValueError("finalized writer input requires marker reconciliation")
    if finalization.marker_reconciliation.status != MarkerReconciliationStatus.SAFE_TO_POST:
        raise ValueError("finalized writer input requires safe marker reconciliation")
    if finalization.finalization_status.final_payload_hash != finalization.final_payload.final_payload_hash:
        raise ValueError("finalized writer input finalization hash mismatch")
    if finalization.finalization_status.target_hash != finalization.final_payload.review_target.target_hash():
        raise ValueError("finalized writer input target hash mismatch")
    return FinalizedIssueCommentWriterInput(
        final_payload=finalization.final_payload,
        final_payload_hash=finalization.final_payload.final_payload_hash,
        target_hash=finalization.final_payload.review_target.target_hash(),
        marker_reconciliation_status=finalization.marker_reconciliation.status,
        approved_actor=approved_actor,
        run_id=run_id,
    )


class FakeIssueCommentWriter:
    def __init__(self, *, author_login: str = "reviewgraph-bot", request_id: str = "REQ-fake-writer") -> None:
        if not isinstance(author_login, str) or not author_login:
            raise ValueError("fake writer author_login is required")
        self.author_login = author_login
        self.request_id = request_id
        self.call_count = 0
        self._comments: list[FakeIssueComment] = []

    @property
    def comments(self) -> tuple[FakeIssueComment, ...]:
        return tuple(self._comments)

    def post_issue_comment(self, writer_input: FinalizedIssueCommentWriterInput) -> GitHubWriterResult:
        if not isinstance(writer_input, FinalizedIssueCommentWriterInput):
            raise ValueError("fake writer accepts only finalized issue-comment writer input")
        if self.author_login != writer_input.approved_actor:
            return GitHubWriterResult(
                status=WriterStatus.FAILED,
                artifact_kind=ArtifactKind.ISSUE_COMMENT,
                target_hash=writer_input.target_hash,
                payload_hash=writer_input.final_payload_hash,
                error="approved_actor_mismatch",
            )
        validation = validate_final_issue_comment_payload(writer_input.final_payload)
        if validation.status.value != "pass":
            return GitHubWriterResult(
                status=WriterStatus.FAILED,
                artifact_kind=ArtifactKind.ISSUE_COMMENT,
                target_hash=writer_input.target_hash,
                payload_hash=writer_input.final_payload_hash,
                error=validation.reason_code.value if validation.reason_code is not None else "payload_validation_failed",
            )
        self.call_count += 1
        comment_id = f"fake-comment-{len(self._comments) + 1}"
        self._comments.append(
            FakeIssueComment(
                comment_id=comment_id,
                body=writer_input.final_payload.body,
                author_login=self.author_login,
            )
        )
        return GitHubWriterResult(
            status=WriterStatus.POSTED,
            artifact_kind=ArtifactKind.ISSUE_COMMENT,
            target_hash=writer_input.target_hash,
            payload_hash=writer_input.final_payload_hash,
            comment_id=comment_id,
        )

    def get_issue_comments_page(
        self,
        owner_repo: str,
        pr_number: int,
        cursor: object | None,
        timeout_seconds: int,
    ) -> MarkerCommentPage:
        if cursor is not None:
            return MarkerCommentPage(comments=(), completed=True, request_id=self.request_id)
        return MarkerCommentPage(
            comments=tuple(
                PaginatedMarkerComment(
                    comment_id=comment.comment_id,
                    body=comment.body,
                    author_login=comment.author_login,
                    author_type=comment.author_type,
                    source_provider="github",
                )
                for comment in self._comments
            ),
            completed=True,
            request_id=self.request_id,
        )
