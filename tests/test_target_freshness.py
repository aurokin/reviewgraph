import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from reviewgraph.approval import build_approval_decision, build_approval_proof
from reviewgraph.finalization import (
    TargetFreshnessProbeResult,
    finalize_github_payload,
    validate_target_freshness_for_finalization,
)
from reviewgraph.models import (
    FinalizationReasonCode,
    FinalizationState,
    GateStatus,
    ReviewTarget,
    TargetFreshnessReasonCode,
    TargetFreshnessTransportSummary,
)
from reviewgraph.permissions import ActorPermissionProbeResult, issue_comment_endpoint
from reviewgraph.posting import build_candidate_issue_comment_payload, build_posting_plan
from reviewgraph.models import ClassifiedFinding, Confidence, Severity


EVALUATED_AT = "2026-05-07T00:05:00Z"
CHECKED_AT = "2026-05-07T00:04:00Z"


def test_fresh_matching_target_passes_with_redacted_transport_summary() -> None:
    result = validate_target_freshness_for_finalization(
        approval=_approval(),
        current_probe=_target_probe(request_id="REQ-1"),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.PASS
    assert result.current_target == _target()
    assert result.current_target_hash == _target().target_hash()
    assert result.transport_summary is not None
    assert result.transport_summary.endpoint_kind == "pull_request_target"
    assert result.transport_summary.request_id == "REQ-1"


@pytest.mark.parametrize(
    ("target_updates", "field"),
    [
        ({"head_sha": "head999"}, "head_sha"),
        ({"base_sha": "base999"}, "base_sha"),
        ({"merge_base_sha": "merge999"}, "merge_base_sha"),
        ({"diff_basis": "head"}, "diff_basis"),
        ({"owner_repo": "acme/other"}, "owner_repo"),
        ({"pr_number": 43}, "pr_number"),
    ],
)
def test_target_drift_fails_closed(target_updates: dict[str, object], field: str) -> None:
    result = validate_target_freshness_for_finalization(
        approval=_approval(),
        current_probe=_target_probe(current_target=replace(_target(), **target_updates)),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == TargetFreshnessReasonCode.TARGET_MISMATCH
    assert field in result.mismatched_fields


def test_missing_merge_base_fails_closed() -> None:
    result = validate_target_freshness_for_finalization(
        approval=_approval(),
        current_probe=_target_probe(current_target=replace(_target(), merge_base_sha=None)),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == TargetFreshnessReasonCode.MISSING_MERGE_BASE


def test_missing_approved_merge_base_fails_closed() -> None:
    target = replace(_target(), merge_base_sha=None)
    approval = replace(
        _approval(),
        approved_review_target=target,
        approved_review_target_hash=target.target_hash(),
        approved_permission_checked_target=target.to_ordered_dict(),
        approved_permission_checked_target_hash=target.target_hash(),
        approved_permission_endpoint=issue_comment_endpoint(target),
    )

    result = validate_target_freshness_for_finalization(
        approval=approval,
        current_probe=_target_probe(),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == TargetFreshnessReasonCode.MISSING_MERGE_BASE


@pytest.mark.parametrize(
    ("updates", "reason_code"),
    [
        ({"checked_at": None}, TargetFreshnessReasonCode.MISSING_CHECKED_AT),
        ({"checked_at": "not-a-time"}, TargetFreshnessReasonCode.MALFORMED_RESPONSE),
        ({"checked_at": "2026-05-06T23:00:00Z"}, TargetFreshnessReasonCode.STALE_CACHED_TARGET),
        ({"checked_at": "2026-05-07T00:07:00Z"}, TargetFreshnessReasonCode.FUTURE_CHECKED_AT),
    ],
)
def test_target_checked_at_failures(updates: dict[str, object], reason_code: TargetFreshnessReasonCode) -> None:
    result = validate_target_freshness_for_finalization(
        approval=_approval(),
        current_probe=_target_probe(**updates),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == reason_code


def test_checked_at_before_approval_fails_even_when_fresh() -> None:
    approval = replace(_approval(), timestamp="2026-05-07T00:04:30Z")

    result = validate_target_freshness_for_finalization(
        approval=approval,
        current_probe=_target_probe(checked_at=CHECKED_AT),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == TargetFreshnessReasonCode.CHECKED_AT_BEFORE_APPROVAL
    assert result.mismatched_fields == ("checked_at",)


@pytest.mark.parametrize(
    ("reason_code", "retryable"),
    [
        (TargetFreshnessReasonCode.TIMEOUT, True),
        (TargetFreshnessReasonCode.RATE_LIMITED, True),
        (TargetFreshnessReasonCode.FORBIDDEN, False),
        (TargetFreshnessReasonCode.NOT_FOUND, False),
        (TargetFreshnessReasonCode.UNAVAILABLE, True),
        (TargetFreshnessReasonCode.MALFORMED_RESPONSE, False),
    ],
)
def test_transport_failures_emit_stable_redacted_summaries(
    reason_code: TargetFreshnessReasonCode,
    retryable: bool,
) -> None:
    result = validate_target_freshness_for_finalization(
        approval=_approval(),
        current_probe=_target_probe(transport_reason_code=reason_code, request_id="REQ-2"),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == reason_code
    assert result.transport_summary is not None
    assert result.transport_summary.reason_code == reason_code
    assert result.transport_summary.retryable is retryable
    assert result.transport_summary.request_id == "REQ-2"


def test_unknown_freshness_returns_structured_fail_closed_result() -> None:
    result = validate_target_freshness_for_finalization(
        approval=_approval(),
        current_probe=TargetFreshnessProbeResult(current_target=None, request_id="REQ-3", unknown_retryable=True),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == TargetFreshnessReasonCode.UNKNOWN_FRESHNESS
    assert result.transport_summary is not None
    assert result.transport_summary.retryable is True


def test_target_freshness_result_rejects_unknown_status_and_unsafe_transport() -> None:
    with pytest.raises(ValueError):
        from reviewgraph.models import TargetFreshnessCheckResult

        TargetFreshnessCheckResult(GateStatus.UNKNOWN)
    with pytest.raises(ValueError):
        TargetFreshnessTransportSummary("pull_request_target", False, request_id="ghp_secret")


@pytest.mark.parametrize(
    ("probe_kind", "expected_reason", "expected_retryable", "expected_mismatches"),
    [
        (
            "target_mismatch",
            "target_mismatch",
            False,
            ["head_sha"],
        ),
        (
            "unknown_freshness",
            "unknown_freshness",
            True,
            [],
        ),
        (
            "stale_cached_target",
            "stale_cached_target",
            False,
            [],
        ),
    ],
)
def test_failed_target_freshness_blocks_payload_builder_and_emits_dry_run_evidence(
    probe_kind: str,
    expected_reason: str,
    expected_retryable: bool,
    expected_mismatches: list[str],
) -> None:
    calls = {"count": 0}

    def builder():
        calls["count"] += 1
        return SimpleNamespace(final_payload_hash=_approval().approved_final_payload_hash)

    if probe_kind == "target_mismatch":
        probe = _target_probe(current_target=replace(_target(), head_sha="head999"), request_id="REQ-4")
    elif probe_kind == "unknown_freshness":
        probe = TargetFreshnessProbeResult(current_target=None, request_id="REQ-4", unknown_retryable=True)
    else:
        probe = _target_probe(checked_at="2026-05-06T23:00:00Z", request_id="REQ-4")

    result = finalize_github_payload(
        approval=_approval(),
        posting_plan=build_posting_plan(findings=(_finding(),)),
        approved_findings_by_id={"finding-1": _finding()},
        current_actor_permission_probe=_actor_probe(),
        current_target_probe=probe,
        evaluated_at=EVALUATED_AT,
        final_payload_builder=builder,
    )

    assert result.finalization_status.state == FinalizationState.FAILED_CLOSED
    assert result.finalization_status.reason_code == FinalizationReasonCode.TARGET_FRESHNESS_FAILED
    assert result.final_payload_builder_calls == 0
    assert calls["count"] == 0
    assert result.writer_input_released is False
    assert result.dry_run_error == {
        "reason_code": expected_reason,
        "retryable": expected_retryable,
        "endpoint_kind": "pull_request_target",
        "request_id": "REQ-4",
        "mismatched_fields": expected_mismatches,
    }


@pytest.mark.parametrize(
    "case",
    [
        "not_approved",
        "duplicate_items",
        "unknown_item",
        "missing_fingerprint",
        "duplicate_fingerprints",
    ],
)
def test_approval_preflight_blocks_current_reads(case: str) -> None:
    approval_updates: dict[str, object] = {}
    findings_by_id: dict[str, object] = {"finding-1": _finding()}
    posting_plan = build_posting_plan(findings=(_finding(),))
    if case == "not_approved":
        approval_updates = {"approved": False}
    elif case == "duplicate_items":
        approval_updates = {"approved_item_ids": ("finding-1", "finding-1")}
    elif case == "unknown_item":
        approval_updates = {"approved_item_ids": ("missing",)}
    elif case == "missing_fingerprint":
        findings_by_id = {"finding-1": SimpleNamespace(fingerprint="")}
    else:
        approval_updates = {"approved_item_ids": ("finding-1", "finding-2")}
        second = replace(_finding(), id="finding-2")
        posting_plan = build_posting_plan(findings=(_finding(), second))
        findings_by_id = {
            "finding-1": _finding(),
            "finding-2": second,
        }

    result = finalize_github_payload(
        approval=replace(_approval(), **approval_updates),
        posting_plan=posting_plan,
        approved_findings_by_id=findings_by_id,
        current_actor_permission_probe=_actor_probe(actor=None),
        current_target_probe=_target_probe(current_target=replace(_target(), head_sha="head999")),
        evaluated_at=EVALUATED_AT,
    )

    assert result.finalization_status.reason_code == FinalizationReasonCode.APPROVAL_PREFLIGHT_FAILED
    assert result.actor_permission_finalization_check is None
    assert result.target_freshness_check is None


def test_fresh_target_does_not_finalize_or_release_writer_input_before_markers() -> None:
    calls = {"count": 0}

    def builder():
        calls["count"] += 1
        return SimpleNamespace(final_payload_hash=_approval().approved_final_payload_hash)

    result = finalize_github_payload(
        approval=_approval(),
        posting_plan=build_posting_plan(findings=(_finding(),)),
        approved_findings_by_id={"finding-1": _finding()},
        current_actor_permission_probe=_actor_probe(),
        current_target_probe=_target_probe(),
        evaluated_at=EVALUATED_AT,
        final_payload_builder=builder,
    )

    assert result.target_freshness_check is not None
    assert result.target_freshness_check.status == GateStatus.PASS
    assert result.finalization_status.state == FinalizationState.NOT_READY
    assert result.finalization_status.reason_code == FinalizationReasonCode.MARKER_RECONCILIATION_DEFERRED
    assert result.final_payload_builder_calls == 1
    assert calls["count"] == 1
    assert result.final_payload is None
    assert result.writer_input_released is False


def test_finalization_module_target_freshness_import_boundary() -> None:
    tree = ast.parse(Path("src/reviewgraph/finalization.py").read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for forbidden in ("subprocess", "os", "reviewgraph.github", "reviewgraph.graph", "reviewgraph.writer", "reviewgraph.marker"):
        assert forbidden not in imported


def _target() -> ReviewTarget:
    return ReviewTarget("acme/widgets", 42, "base123", "head456", "merge789", "merge_base")


def _finding() -> ClassifiedFinding:
    return ClassifiedFinding(
        id="finding-1",
        source_reviewer="correctness",
        source_stage="initial_triage",
        title="Cache miss returns stale data",
        body="The new branch returns stale data when the cache misses.",
        evidence="changed line 12",
        path="src/cache.py",
        line=12,
        priority=1,
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        fingerprint="fp-1",
    )


def _approval():
    plan = build_posting_plan(findings=(_finding(),))
    candidate = build_candidate_issue_comment_payload(review_target=_target(), posting_plan=plan, findings=(_finding(),))
    proof = build_approval_proof(
        approved_item_ids=("finding-1",),
        review_target=_target(),
        posting_plan=plan,
        findings=(_finding(),),
        candidate_payload=candidate,
        run_id="run-123",
        approved_by="local-user",
        timestamp="2026-05-07T00:03:30Z",
    )
    decision = build_approval_decision(proof=proof, actor_permission_gate=_actor_gate())
    assert decision.approval is not None
    return decision.approval


def _actor_gate():
    from reviewgraph.permissions import evaluate_actor_permission_gate

    return evaluate_actor_permission_gate(_actor_probe(), expected_target=_target(), evaluated_at=EVALUATED_AT)


def _actor_probe(**updates: object) -> ActorPermissionProbeResult:
    values = {
        "actor": "reviewgraph-bot",
        "credential_principal": "gh-user:reviewgraph-bot",
        "credential_source": "pat",
        "repo_permission": "write",
        "issue_comment_write": True,
        "check_method": "fake_issue_comment_permission_probe",
        "endpoint_method": "POST",
        "checked_target": _target(),
        "checked_at": CHECKED_AT,
        "endpoint": issue_comment_endpoint(_target()),
        "endpoint_kind": "issue_comment",
        "request_id": "REQ-actor",
    }
    values.update(updates)
    return ActorPermissionProbeResult(**values)


def _target_probe(**updates: object) -> TargetFreshnessProbeResult:
    values = {
        "current_target": _target(),
        "checked_at": CHECKED_AT,
        "check_method": "fake_pull_request_target_probe",
        "request_id": "REQ-target",
    }
    values.update(updates)
    return TargetFreshnessProbeResult(**values)
