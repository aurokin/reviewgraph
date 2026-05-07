from dataclasses import replace

import pytest

from reviewgraph.finalization import FinalizeGithubPayloadResult
from reviewgraph.markers import build_final_issue_comment_payload
from reviewgraph.models import (
    ActorPermissionFinalizationCheckResult,
    ActorPermissionTransportSummary,
    ArtifactKind,
    FinalizationReasonCode,
    FinalizationState,
    FinalizationStatus,
    GateStatus,
    MarkerReconciliationReasonCode,
    MarkerReconciliationResult,
    MarkerReconciliationStatus,
    MarkerScanTransportSummary,
    PayloadValidationResult,
    RedactionStatus,
    ReviewTarget,
    TargetFreshnessCheckResult,
    TargetFreshnessTransportSummary,
    WriterStatus,
)
from reviewgraph.writer_fake import (
    FakeIssueCommentWriter,
    FinalizedIssueCommentWriterInput,
    build_finalized_issue_comment_writer_input,
)


def test_fake_writer_accepts_finalized_safe_to_post_input_only() -> None:
    payload = _payload()
    finalization = _finalization(payload=payload)
    writer_input = build_finalized_issue_comment_writer_input(
        finalization=finalization,
        approved_actor="reviewgraph-bot",
        run_id="run-123",
    )
    writer = FakeIssueCommentWriter(author_login="reviewgraph-bot")

    result = writer.post_issue_comment(writer_input)

    assert result.status == WriterStatus.POSTED
    assert result.artifact_kind == ArtifactKind.ISSUE_COMMENT
    assert result.target_hash == _target().target_hash()
    assert result.payload_hash == payload.final_payload_hash
    assert result.comment_id == "fake-comment-1"
    assert writer.call_count == 1
    assert len(writer.comments) == 1


def test_fake_writer_rejects_raw_final_payload_without_finalized_writer_input() -> None:
    writer = FakeIssueCommentWriter()

    with pytest.raises(ValueError, match="finalized issue-comment writer input"):
        writer.post_issue_comment(_payload())  # type: ignore[arg-type]

    assert writer.call_count == 0
    assert writer.comments == ()


def test_fake_writer_input_cannot_be_directly_constructed_to_bypass_finalization() -> None:
    payload = _payload()

    with pytest.raises(ValueError, match="verified finalization"):
        FinalizedIssueCommentWriterInput(
            final_payload=payload,
            final_payload_hash=payload.final_payload_hash,
            target_hash=payload.review_target.target_hash(),
            marker_reconciliation_status=MarkerReconciliationStatus.SAFE_TO_POST,
            approved_actor="reviewgraph-bot",
            run_id="run-123",
        )


@pytest.mark.parametrize(
    "case",
    [
        "not_ready",
        "failed_closed",
        "reconciled_existing",
        "missing_marker_reconciliation",
        "writer_input_not_released",
        "missing_actor_check",
        "missing_target_check",
        "missing_payload_validation",
        "target_hash_mismatch",
    ],
)
def test_finalized_writer_input_rejects_non_released_or_non_safe_states(case: str) -> None:
    payload = _payload()
    finalization = _finalization(payload=payload)
    if case == "not_ready":
        finalization = replace(
            finalization,
            finalization_status=FinalizationStatus(
                FinalizationState.NOT_READY,
                None,
                _target().target_hash(),
                FinalizationReasonCode.MARKER_RECONCILIATION_DEFERRED,
            ),
        )
    elif case == "failed_closed":
        finalization = replace(
            finalization,
            finalization_status=FinalizationStatus(
                FinalizationState.FAILED_CLOSED,
                None,
                _target().target_hash(),
                FinalizationReasonCode.MARKER_RECONCILIATION_FAILED,
            ),
        )
    elif case == "reconciled_existing":
        finalization = replace(finalization, marker_reconciliation=_marker_reconciliation("reconciled"))
    elif case == "missing_marker_reconciliation":
        finalization = replace(finalization, marker_reconciliation=None)
    elif case == "writer_input_not_released":
        finalization = replace(finalization, writer_input_released=False)
    elif case == "missing_actor_check":
        finalization = replace(finalization, actor_permission_finalization_check=None)
    elif case == "missing_target_check":
        finalization = replace(finalization, target_freshness_check=None)
    elif case == "missing_payload_validation":
        finalization = replace(finalization, payload_validation=None)
    else:
        finalization = replace(
            finalization,
            finalization_status=FinalizationStatus(
                FinalizationState.FINALIZED,
                payload.final_payload_hash,
                "sha256:" + "0" * 64,
            ),
        )

    with pytest.raises(ValueError):
        build_finalized_issue_comment_writer_input(
            finalization=finalization,
            approved_actor="reviewgraph-bot",
            run_id="run-123",
        )


def test_fake_writer_returns_failed_without_transport_call_for_invalid_wrapped_payload() -> None:
    payload = replace(_payload(), marker_run_id="other-run")
    finalization = _finalization(payload=payload)
    writer_input = build_finalized_issue_comment_writer_input(
        finalization=finalization,
        approved_actor="reviewgraph-bot",
        run_id="run-123",
    )
    writer = FakeIssueCommentWriter()

    result = writer.post_issue_comment(writer_input)

    assert result.status == WriterStatus.FAILED
    assert result.error == "marker_field_mismatch"
    assert writer.call_count == 0
    assert writer.comments == ()


def test_fake_writer_rejects_approved_actor_mismatch_before_transport_call() -> None:
    payload = _payload()
    writer_input = build_finalized_issue_comment_writer_input(
        finalization=_finalization(payload=payload),
        approved_actor="reviewgraph-bot",
        run_id="run-123",
    )
    writer = FakeIssueCommentWriter(author_login="other-bot")

    result = writer.post_issue_comment(writer_input)

    assert result.status == WriterStatus.FAILED
    assert result.error == "approved_actor_mismatch"
    assert writer.call_count == 0
    assert writer.comments == ()


def _finalization(payload) -> FinalizeGithubPayloadResult:
    return FinalizeGithubPayloadResult(
        actor_permission_finalization_check=ActorPermissionFinalizationCheckResult(
            status=GateStatus.PASS,
            actor_permission_transport_summary=ActorPermissionTransportSummary(
                endpoint_kind="issue_comment_permission",
                retryable=False,
            ),
            current_actor_permission_checked_at="2026-05-07T00:05:00Z",
        ),
        target_freshness_check=TargetFreshnessCheckResult(
            status=GateStatus.PASS,
            transport_summary=TargetFreshnessTransportSummary(
                endpoint_kind="pull_request_target",
                retryable=False,
            ),
            current_target=payload.review_target,
            current_target_hash=payload.review_target.target_hash(),
            current_checked_at="2026-05-07T00:05:00Z",
            check_method="fake_pull_request_target_probe",
        ),
        finalization_status=FinalizationStatus(
            FinalizationState.FINALIZED,
            payload.final_payload_hash,
            payload.review_target.target_hash(),
        ),
        payload_validation=PayloadValidationResult(
            status=GateStatus.PASS,
            payload_hash=payload.final_payload_hash,
            target_hash=payload.review_target.target_hash(),
        ),
        marker_reconciliation=_marker_reconciliation("safe"),
        final_payload=payload,
        writer_input_released=True,
    )


def _marker_reconciliation(case: str) -> MarkerReconciliationResult:
    if case == "safe":
        return MarkerReconciliationResult(
            status=MarkerReconciliationStatus.SAFE_TO_POST,
            reason_code=MarkerReconciliationReasonCode.SAFE_TO_POST,
            transport_summary=MarkerScanTransportSummary(
                endpoint_kind="issue_comments",
                page_count=1,
                comment_count=0,
                marker_count=0,
                retryable=False,
            ),
        )
    return MarkerReconciliationResult(
        status=MarkerReconciliationStatus.RECONCILED_EXISTING,
        reason_code=MarkerReconciliationReasonCode.MATCHED_EXISTING,
        trusted_actor="reviewgraph-bot",
        existing_comment_id="existing-comment",
        transport_summary=MarkerScanTransportSummary(
            endpoint_kind="issue_comments",
            page_count=1,
            comment_count=1,
            marker_count=1,
            retryable=False,
        ),
    )


def _payload():
    return build_final_issue_comment_payload(
        run_id="run-123",
        review_target=_target(),
        visible_body="ReviewGraph approved findings\nTarget: acme/widgets#42\nHead: head456\n\nApproved findings:\n- P1 Finding: Body. (src/app.py:10)\n",
        item_fingerprints=("fp-1",),
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )


def _target() -> ReviewTarget:
    return ReviewTarget("acme/widgets", 42, "base123", "head456", "merge789", "merge_base")
