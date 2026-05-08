from __future__ import annotations

from dataclasses import dataclass

from reviewgraph.finalization import FinalizeGithubPayloadResult
from reviewgraph.models import (
    ApprovalDecision,
    FinalIssueCommentPayload,
    FinalizationState,
    GateStatus,
    MarkerReconciliationStatus,
)


_WRITER_INPUT_BUILD_TOKEN = object()


@dataclass(frozen=True, init=False)
class FinalizedIssueCommentWriterInput:
    final_payload: FinalIssueCommentPayload
    final_payload_hash: str
    target_hash: str
    marker_reconciliation_status: MarkerReconciliationStatus
    approved_actor: str
    run_id: str

    def __init__(
        self,
        *,
        final_payload: FinalIssueCommentPayload,
        final_payload_hash: str,
        target_hash: str,
        marker_reconciliation_status: MarkerReconciliationStatus,
        approved_actor: str,
        run_id: str,
        _build_token: object | None = None,
    ) -> None:
        if _build_token is not _WRITER_INPUT_BUILD_TOKEN:
            raise ValueError("finalized writer input must be built from verified finalization")
        object.__setattr__(self, "final_payload", final_payload)
        object.__setattr__(self, "final_payload_hash", final_payload_hash)
        object.__setattr__(self, "target_hash", target_hash)
        object.__setattr__(self, "marker_reconciliation_status", marker_reconciliation_status)
        object.__setattr__(self, "approved_actor", approved_actor)
        object.__setattr__(self, "run_id", run_id)
        self._validate()

    def _validate(self) -> None:
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


def build_finalized_issue_comment_writer_input(
    *,
    finalization: FinalizeGithubPayloadResult,
    approval: ApprovalDecision,
    run_id: str,
) -> FinalizedIssueCommentWriterInput:
    if not isinstance(finalization, FinalizeGithubPayloadResult):
        raise ValueError("finalized writer input requires finalization result")
    if not isinstance(approval, ApprovalDecision):
        raise ValueError("finalized writer input requires approval decision")
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
    if finalization.approved_github_actor != approval.approved_github_actor:
        raise ValueError("finalized writer input approved actor mismatch")
    if approval.approved_final_payload_hash != finalization.final_payload.final_payload_hash:
        raise ValueError("finalized writer input approval payload hash mismatch")
    if approval.approved_review_target_hash != finalization.final_payload.review_target.target_hash():
        raise ValueError("finalized writer input approval target hash mismatch")
    return FinalizedIssueCommentWriterInput(
        final_payload=finalization.final_payload,
        final_payload_hash=finalization.final_payload.final_payload_hash,
        target_hash=finalization.final_payload.review_target.target_hash(),
        marker_reconciliation_status=finalization.marker_reconciliation.status,
        approved_actor=approval.approved_github_actor,
        run_id=run_id,
        _build_token=_WRITER_INPUT_BUILD_TOKEN,
    )
