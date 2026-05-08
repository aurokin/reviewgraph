from dataclasses import replace
from pathlib import Path
import ast

import pytest

from reviewgraph.finalization import finalize_github_payload
from reviewgraph.models import (
    FinalizationReasonCode,
    FinalizationState,
    FinalizationStatus,
    MarkerReconciliationReasonCode,
    MarkerReconciliationResult,
    MarkerReconciliationStatus,
    MarkerScanTransportSummary,
    WriterStatus,
)
from reviewgraph.post_mode_harness import _post_or_emit, run_fixture_fake_post_attempt


def test_approved_post_mode_route_calls_fake_writer_once() -> None:
    result = run_fixture_fake_post_attempt(case="approved")

    assert result.json_data["graph_trace"] == [
        "render_review",
        "post_mode_interaction_gate",
        "approval_gate",
        "writer_release_preflight",
        "finalize_github_payload",
        "post_or_emit",
    ]
    assert result.json_data["writer_release_preflight"]["status"] == "pass"
    assert result.json_data["approval"]["approved"] is True
    assert result.json_data["approval"]["approved_item_ids"] == ["finding-1"]
    assert result.json_data["actor_permission_finalization_check"]["status"] == "pass"
    assert result.json_data["target_freshness_check"]["status"] == "pass"
    assert result.json_data["finalization_status"]["state"] == "finalized"
    assert result.json_data["payload_validation"]["status"] == "pass"
    assert result.json_data["payload_validation"]["reason_code"] is None
    assert result.json_data["marker_reconciliation"]["status"] == "safe_to_post"
    assert result.json_data["marker_reconciliation"]["transport_summary"]["endpoint_kind"] == "issue_comments"
    assert result.json_data["writer_result"]["status"] == "posted"
    assert result.json_data["writer_result"]["comment_id"] == "fake-comment-1"
    assert result.json_data["side_effects"] == {"writer_called": True, "writer_call_count": 1}


def test_retry_after_stored_fake_comment_reconciles_without_second_post() -> None:
    first = run_fixture_fake_post_attempt(case="approved")
    second = run_fixture_fake_post_attempt(case="approved", writer=first.writer)

    assert first.writer_call_count == 1
    assert second.writer_call_count == 1
    assert len(second.writer.comments) == 1
    assert second.json_data["marker_reconciliation"]["status"] == "reconciled_existing"
    assert second.json_data["writer_result"]["status"] == "reconciled"
    assert second.json_data["writer_result"]["comment_id"] == "fake-comment-1"
    assert second.json_data["side_effects"] == {"writer_called": False, "writer_call_count": 0}


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    [
        ("dry_run", "dry_run"),
        ("non_interactive", "non_interactive_post_mode"),
        ("missing_approval", "missing_approval"),
        ("rejected_approval", "rejected_approval"),
        ("empty_approval", "approval_build_failed"),
        ("non_public_approval", "non_public_approved_item"),
        ("stale_target", "target_mismatch"),
        ("unknown_target_freshness", "unknown_freshness"),
        ("actor_mismatch", "actor_permission_failed"),
        ("permission_failure", "actor_permission_failed"),
        ("payload_validation_failure", "payload_validation_failed"),
        ("marker_conflict", "trusted_marker_conflict"),
        ("marker_malformed", "trusted_marker_malformed"),
        ("marker_incomplete", "pagination_incomplete"),
        ("marker_timeout", "timeout"),
        ("marker_rate_limited", "rate_limited"),
        ("marker_forbidden", "forbidden"),
        ("marker_not_found", "not_found"),
        ("marker_unavailable", "unavailable"),
        ("marker_malformed_page", "malformed_page"),
        ("marker_repeated_cursor", "repeated_cursor"),
        ("marker_page_cap", "page_cap_exceeded"),
        ("marker_comment_cap", "comment_cap_exceeded"),
        ("marker_transport_unknown", "transport_unknown"),
        ("marker_binding_mismatch", "marker_reconciliation_binding_mismatch"),
    ],
)
def test_blocked_post_mode_paths_call_fake_writer_zero_times(case: str, expected_reason: str) -> None:
    result = run_fixture_fake_post_attempt(case=case)

    assert result.writer_call_count == 0
    assert result.writer.comments == ()
    assert result.json_data["side_effects"] == {"writer_called": False, "writer_call_count": 0}
    assert result.json_data["post_or_emit"]["reason_code"] == expected_reason
    assert "approval" in result.json_data
    assert "actor_permission_finalization_check" in result.json_data
    assert "target_freshness_check" in result.json_data
    assert "dry_run_error" in result.json_data
    assert "writer_result" in result.json_data
    if case != "marker_duplicate_matching":
        assert result.json_data["writer_result"] is None


def test_payload_validation_failure_records_reason_evidence() -> None:
    result = run_fixture_fake_post_attempt(case="payload_validation_failure")

    assert result.json_data["payload_validation"]["status"] == "fail"
    assert result.json_data["payload_validation"]["reason_code"] == "marker_field_mismatch"
    assert result.json_data["dry_run_error"]["reason_code"] == "payload_validation_failed"
    assert result.json_data["dry_run_error"]["endpoint_kind"] == "final_payload"


def test_marker_transport_failure_records_redacted_transport_summary() -> None:
    result = run_fixture_fake_post_attempt(case="marker_timeout")

    assert result.json_data["marker_reconciliation"]["status"] == "failed_closed"
    assert result.json_data["marker_reconciliation"]["reason_code"] == "timeout"
    assert result.json_data["marker_reconciliation"]["transport_summary"] == {
        "endpoint_kind": "issue_comments",
        "page_count": 0,
        "comment_count": 0,
        "marker_count": 0,
        "retryable": True,
        "reason_code": "timeout",
        "request_id": "REQ-marker-failure",
    }
    assert result.json_data["dry_run_error"]["retryable"] is True
    assert result.json_data["dry_run_error"]["request_id"] == "REQ-marker-failure"


def test_duplicate_matching_markers_reconcile_without_new_fake_post() -> None:
    result = run_fixture_fake_post_attempt(case="marker_duplicate_matching")

    assert result.writer_call_count == 0
    assert result.writer.comments == ()
    assert result.json_data["marker_reconciliation"]["status"] == "reconciled_existing"
    assert result.json_data["marker_reconciliation"]["existing_comment_id"] == "existing-one"
    assert result.writer_result is not None
    assert result.writer_result.status == WriterStatus.RECONCILED


def test_post_or_emit_defensively_rejects_inconsistent_final_payload_state() -> None:
    approved = run_fixture_fake_post_attempt(case="approved")
    finalization = approved.finalization
    assert finalization is not None
    inconsistent = replace(
        finalization,
        finalization_status=FinalizationStatus(
            FinalizationState.NOT_READY,
            None,
            finalization.finalization_status.target_hash,
            FinalizationReasonCode.MARKER_RECONCILIATION_DEFERRED,
        ),
    )

    writer_result = _post_or_emit(
        finalization=inconsistent,
        approval=_approval_from_success(approved),
        writer=approved.writer,
    )

    assert writer_result is None
    assert approved.writer_call_count == 1
    assert len(approved.writer.comments) == 1


def test_post_or_emit_defensively_rejects_non_safe_marker_state() -> None:
    approved = run_fixture_fake_post_attempt(case="approved")
    finalization = approved.finalization
    assert finalization is not None
    unsafe = replace(
        finalization,
        marker_reconciliation=MarkerReconciliationResult(
            status=MarkerReconciliationStatus.FAILED_CLOSED,
            reason_code=MarkerReconciliationReasonCode.TRUSTED_MARKER_CONFLICT,
            transport_summary=MarkerScanTransportSummary(
                endpoint_kind="issue_comments",
                page_count=1,
                comment_count=1,
                marker_count=1,
                retryable=False,
                reason_code=MarkerReconciliationReasonCode.TRUSTED_MARKER_CONFLICT,
            ),
        ),
    )

    writer_result = _post_or_emit(
        finalization=unsafe,
        approval=_approval_from_success(approved),
        writer=approved.writer,
    )

    assert writer_result is None
    assert approved.writer_call_count == 1
    assert len(approved.writer.comments) == 1


@pytest.mark.parametrize("state", [FinalizationState.FAILED_CLOSED, FinalizationState.FINALIZED])
def test_post_or_emit_does_not_report_reconciled_for_inconsistent_reconciled_state(
    state: FinalizationState,
) -> None:
    first = run_fixture_fake_post_attempt(case="approved")
    reconciled = run_fixture_fake_post_attempt(case="approved", writer=first.writer)
    finalization = reconciled.finalization
    assert finalization is not None
    inconsistent = replace(
        finalization,
        finalization_status=FinalizationStatus(
            state,
            first.finalization.finalization_status.final_payload_hash if state == FinalizationState.FINALIZED else None,
            finalization.finalization_status.target_hash,
            None if state == FinalizationState.FINALIZED else FinalizationReasonCode.MARKER_RECONCILIATION_FAILED,
        ),
    )

    writer_result = _post_or_emit(
        finalization=inconsistent,
        approval=_approval_from_success(first),
        writer=first.writer,
    )

    assert writer_result is None
    assert first.writer_call_count == 1


def test_finalization_rejects_unbound_precomputed_marker_reconciliation() -> None:
    approved = run_fixture_fake_post_attempt(case="approved")
    finalization = approved.finalization
    assert finalization is not None
    from reviewgraph.post_mode_harness import _actor_probe, _finding, _target, _target_probe
    from reviewgraph.posting import build_posting_plan

    finding = _finding()
    target = _target()

    with pytest.raises(ValueError, match="marker_reconciler must be callable"):
        finalize_github_payload(
            approval=_approval_from_success(approved),
            posting_plan=build_posting_plan(findings=(finding,)),
            approved_findings_by_id={finding.id: finding},
            current_actor_permission_probe=_actor_probe(target=target),
            current_target_probe=_target_probe(target),
            evaluated_at="2026-05-07T00:05:00Z",
            final_payload_builder=lambda: finalization.final_payload,
            marker_reconciler=finalization.marker_reconciliation,  # type: ignore[arg-type]
        )


def test_public_cli_still_does_not_expose_post_flag() -> None:
    from reviewgraph.cli import _parser

    parser = _parser()

    assert "--post" not in parser.format_help()


@pytest.mark.parametrize(
    "path",
    [
        "src/reviewgraph/finalization.py",
        "src/reviewgraph/cli.py",
        "src/reviewgraph/runner.py",
    ],
)
def test_default_boundaries_do_not_import_fake_writer(path: str) -> None:
    tree = ast.parse(Path(path).read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert "reviewgraph.writer_fake" not in imports


def _approval_from_success(result):
    finalization = result.finalization
    assert finalization is not None
    final_payload = finalization.final_payload
    assert final_payload is not None
    from reviewgraph.post_mode_harness import _approval, _finding, _target
    from reviewgraph.posting import build_candidate_issue_comment_payload, build_posting_plan

    target = _target()
    finding = _finding()
    plan = build_posting_plan(findings=(finding,))
    candidate = build_candidate_issue_comment_payload(review_target=target, posting_plan=plan, findings=(finding,))
    return _approval(plan=plan, finding=finding, target=target, candidate=candidate)
