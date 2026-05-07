from dataclasses import replace
from pathlib import Path
import ast

import pytest

from reviewgraph.finalization import FinalizeGithubPayloadResult
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
    assert result.json_data["finalization_status"]["state"] == "finalized"
    assert result.json_data["marker_reconciliation"]["status"] == "safe_to_post"
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
        ("stale_target", "target_freshness_failed"),
        ("unknown_target_freshness", "target_freshness_failed"),
        ("actor_mismatch", "actor_permission_failed"),
        ("permission_failure", "actor_permission_failed"),
        ("payload_validation_failure", "payload_validation_failed"),
        ("marker_conflict", "trusted_marker_conflict"),
    ],
)
def test_blocked_post_mode_paths_call_fake_writer_zero_times(case: str, expected_reason: str) -> None:
    result = run_fixture_fake_post_attempt(case=case)

    assert result.writer_call_count == 0
    assert result.writer.comments == ()
    assert result.json_data["side_effects"] == {"writer_called": False, "writer_call_count": 0}
    assert result.json_data["post_or_emit"]["reason_code"] == expected_reason


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
