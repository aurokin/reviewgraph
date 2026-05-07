import inspect
from dataclasses import replace
from pathlib import Path

import pytest

from reviewgraph.approval import build_approval_decision, build_approval_proof
from reviewgraph.finalization import validate_actor_permission_snapshot_for_finalization
from reviewgraph.hashing import final_payload_hash, findings_hash, marker_payload_hash
from reviewgraph.models import (
    ActorPermissionFinalizationReasonCode,
    ActorPermissionReasonCode,
    ApprovalDecisionBuildReasonCode,
    CandidateIssueCommentPayload,
    ClassifiedFinding,
    Confidence,
    FinalIssueCommentPayload,
    GateStatus,
    OutputClassification,
    PayloadValidationResult,
    PostingDestination,
    PostingPlan,
    PostingPlanItem,
    RedactionStatus,
    ReviewTarget,
    Severity,
)
from reviewgraph.permissions import ActorPermissionProbeResult, issue_comment_endpoint
from reviewgraph.posting import build_candidate_issue_comment_payload, build_posting_plan


EVALUATED_AT = "2026-05-07T00:05:00Z"
CHECKED_AT = "2026-05-07T00:03:00Z"


def test_approval_decision_stores_actor_permission_snapshot() -> None:
    proof = _proof()
    gate = _gate()

    result = build_approval_decision(proof=proof, actor_permission_gate=gate)

    assert result.status == GateStatus.PASS
    approval = result.approval
    assert approval is not None
    assert approval.approved_github_actor == "reviewgraph-bot"
    assert approval.approved_credential_principal == "gh-user:reviewgraph-bot"
    assert approval.approved_credential_source == "pat"
    assert approval.approved_permission == "write"
    assert approval.approved_repo_permission == "write"
    assert approval.approved_installation_permission is None
    assert approval.approved_endpoint_permission is None
    assert approval.approved_issue_comment_write is True
    assert approval.approved_permission_checked_at == CHECKED_AT
    assert approval.approved_permission_checked_target == _target().to_ordered_dict()
    assert approval.approved_permission_checked_target_hash == _target().target_hash()
    assert approval.approved_permission_endpoint == "/repos/acme/widgets/issues/42/comments"
    assert approval.approved_permission_endpoint_kind == "issue_comment"
    assert approval.approved_permission_transport_summary.request_id == "REQ-1"


def test_approval_decision_build_blocks_failed_proof_and_failed_gate() -> None:
    failed_proof = build_approval_proof(
        approved_item_ids=(),
        review_target=_target(),
        posting_plan=build_posting_plan(findings=(_finding(),)),
        findings=(_finding(),),
        candidate_payload=_candidate(),
        run_id="run-123",
        approved_by="local-user",
        timestamp="2026-05-07T00:04:00Z",
    )
    proof_result = build_approval_decision(proof=failed_proof, actor_permission_gate=_gate())

    assert proof_result.status == GateStatus.FAIL
    assert proof_result.reason_code == ApprovalDecisionBuildReasonCode.APPROVAL_PROOF_FAILED

    failed_gate_result = build_approval_decision(
        proof=_proof(),
        actor_permission_gate=_gate(actor=None),
    )

    assert failed_gate_result.status == GateStatus.FAIL
    assert failed_gate_result.reason_code == ApprovalDecisionBuildReasonCode.ACTOR_PERMISSION_GATE_FAILED
    assert failed_gate_result.actor_permission_reason_code == ActorPermissionReasonCode.UNKNOWN_ACTOR
    assert failed_gate_result.actor_permission_transport_summary is not None


def test_approval_decision_rejects_actor_permission_target_mismatch() -> None:
    other_target = ReviewTarget(
        owner_repo="acme/widgets",
        pr_number=43,
        base_sha="base123",
        head_sha="head456",
        merge_base_sha="merge789",
        diff_basis="merge_base",
    )

    result = build_approval_decision(proof=_proof(), actor_permission_gate=_gate(target=other_target))

    assert result.status == GateStatus.FAIL
    assert result.reason_code == ApprovalDecisionBuildReasonCode.ACTOR_PERMISSION_TARGET_MISMATCH


def test_approval_decision_rejects_stale_reconstructed_pass_gate() -> None:
    stale_gate = replace(_gate(), checked_at="2026-05-06T23:50:00Z")

    result = build_approval_decision(proof=_proof(), actor_permission_gate=stale_gate)

    assert result.status == GateStatus.FAIL
    assert result.reason_code == ApprovalDecisionBuildReasonCode.ACTOR_PERMISSION_GATE_FAILED
    assert result.actor_permission_reason_code == ActorPermissionReasonCode.STALE_CACHED_PROOF
    assert result.actor_permission_transport_summary is not None


def test_actor_permission_finalization_check_passes_with_current_snapshot_and_new_request_id() -> None:
    approval = _approval()

    result = validate_actor_permission_snapshot_for_finalization(
        approval=approval,
        current_probe=_probe(request_id="REQ-2"),
        expected_target=_target(),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.PASS
    assert result.current_actor_permission_checked_at == CHECKED_AT
    assert result.actor_permission_transport_summary is not None
    assert result.actor_permission_transport_summary.request_id == "REQ-2"
    assert result.mismatched_fields == ()


def test_actor_permission_finalization_api_requires_raw_current_probe() -> None:
    parameters = inspect.signature(validate_actor_permission_snapshot_for_finalization).parameters

    assert "current_probe" in parameters
    assert "current_gate" not in parameters


@pytest.mark.parametrize(
    ("updates", "reason_code"),
    [
        ({"actor": None}, ActorPermissionReasonCode.UNKNOWN_ACTOR),
        ({"credential_source": "mystery"}, ActorPermissionReasonCode.UNKNOWN_CREDENTIAL_SOURCE),
        ({"repo_permission": None}, ActorPermissionReasonCode.UNKNOWN_PERMISSION),
        ({"repo_permission": "read"}, ActorPermissionReasonCode.INSUFFICIENT_ENDPOINT_PERMISSION),
        ({"checked_at": None}, ActorPermissionReasonCode.MISSING_CHECKED_AT),
        ({"checked_at": "not-a-time"}, ActorPermissionReasonCode.MALFORMED_RESPONSE),
        ({"checked_at": "2026-05-06T23:00:00Z"}, ActorPermissionReasonCode.STALE_CACHED_PROOF),
        ({"transport_reason_code": ActorPermissionReasonCode.TIMEOUT}, ActorPermissionReasonCode.TIMEOUT),
        ({"transport_reason_code": ActorPermissionReasonCode.RATE_LIMITED}, ActorPermissionReasonCode.RATE_LIMITED),
        ({"transport_reason_code": ActorPermissionReasonCode.FORBIDDEN}, ActorPermissionReasonCode.FORBIDDEN),
        ({"transport_reason_code": ActorPermissionReasonCode.NOT_FOUND}, ActorPermissionReasonCode.NOT_FOUND),
        ({"transport_reason_code": ActorPermissionReasonCode.UNAVAILABLE}, ActorPermissionReasonCode.UNAVAILABLE),
    ],
)
def test_current_actor_permission_gate_failures_block_finalization(
    updates: dict[str, object],
    reason_code: ActorPermissionReasonCode,
) -> None:
    result = validate_actor_permission_snapshot_for_finalization(
        approval=_approval(),
        current_probe=_probe(**updates),
        expected_target=_target(),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == ActorPermissionFinalizationReasonCode.ACTOR_PERMISSION_GATE_FAILED
    assert result.actor_permission_reason_code == reason_code
    assert result.actor_permission_transport_summary is not None
    assert "token" not in (result.reason or "")


@pytest.mark.parametrize(
    ("updates", "field"),
    [
        ({"actor": "another-bot"}, "actor"),
        ({"credential_principal": "gh-user:other"}, "credential_principal"),
        ({"credential_source": "fine_grained_pat", "repo_permission": None, "endpoint_permission": "issues:write"}, "credential_source"),
        ({"repo_permission": "maintain"}, "permission"),
        ({"issue_comment_write": False}, "issue_comment_write"),
        ({"check_method": "other_method"}, "check_method"),
        ({"endpoint_method": "PUT"}, "endpoint_method"),
        ({"endpoint_kind": "pull_request_review"}, "endpoint_kind"),
    ],
)
def test_current_actor_permission_snapshot_mismatches_fail_closed(
    updates: dict[str, object],
    field: str,
) -> None:
    result = validate_actor_permission_snapshot_for_finalization(
        approval=_approval(),
        current_probe=_probe(**updates),
        expected_target=_target(),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code in {
        ActorPermissionFinalizationReasonCode.ACTOR_PERMISSION_GATE_FAILED,
        ActorPermissionFinalizationReasonCode.ACTOR_PERMISSION_SNAPSHOT_MISMATCH,
    }
    assert field in result.mismatched_fields or result.actor_permission_reason_code is not None


def test_current_checked_at_regression_fails_even_when_fresh_by_age() -> None:
    approval = replace(_approval(), approved_permission_checked_at="2026-05-07T00:04:00Z")

    result = validate_actor_permission_snapshot_for_finalization(
        approval=approval,
        current_probe=_probe(checked_at=CHECKED_AT),
        expected_target=_target(),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == ActorPermissionFinalizationReasonCode.ACTOR_PERMISSION_CHECKED_AT_REGRESSED
    assert result.mismatched_fields == ("checked_at",)


def test_actor_permission_finalization_check_never_builds_payload_or_writer_state() -> None:
    result = validate_actor_permission_snapshot_for_finalization(
        approval=_approval(),
        current_probe=_probe(),
        expected_target=_target(),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.PASS
    assert not isinstance(result, (CandidateIssueCommentPayload, FinalIssueCommentPayload, PayloadValidationResult))
    assert not hasattr(result, "final_payload_hash")
    assert not hasattr(result, "writer_result")


def test_failed_finalization_check_serializes_redacted_diagnostics() -> None:
    result = validate_actor_permission_snapshot_for_finalization(
        approval=_approval(),
        current_probe=_probe(
            transport_reason_code=ActorPermissionReasonCode.TIMEOUT,
            request_id="REQ-2",
            reason="raw stderr token ghp_secret should not survive",
        ),
        expected_target=_target(),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == GateStatus.FAIL
    assert result.actor_permission_transport_summary is not None
    assert result.actor_permission_transport_summary.request_id == "REQ-2"
    serialized = repr(result)
    assert "REQ-2" in serialized
    assert "ghp_secret" not in serialized
    assert "raw stderr" not in serialized


def test_finalization_module_import_boundary() -> None:
    source = Path("src/reviewgraph/finalization.py").read_text()

    for forbidden in ("subprocess", "os", "reviewgraph.github", "reviewgraph.graph", "reviewgraph.writer", "reviewgraph.marker"):
        assert forbidden not in source


def _target() -> ReviewTarget:
    return ReviewTarget(
        owner_repo="acme/widgets",
        pr_number=42,
        base_sha="base123",
        head_sha="head456",
        merge_base_sha="merge789",
        diff_basis="merge_base",
    )


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


def _candidate() -> CandidateIssueCommentPayload:
    return build_candidate_issue_comment_payload(
        review_target=_target(),
        posting_plan=_plan(),
        findings=(_finding(),),
    )


def _plan() -> PostingPlan:
    return build_posting_plan(findings=(_finding(),))


def _proof():
    return build_approval_proof(
        approved_item_ids=("finding-1",),
        review_target=_target(),
        posting_plan=_plan(),
        findings=(_finding(),),
        candidate_payload=_candidate(),
        run_id="run-123",
        approved_by="local-user",
        timestamp="2026-05-07T00:04:00Z",
    )


def _approval():
    result = build_approval_decision(proof=_proof(), actor_permission_gate=_gate())
    assert result.approval is not None
    return result.approval


def _gate(target: ReviewTarget | None = None, **updates: object):
    from reviewgraph.permissions import evaluate_actor_permission_gate

    review_target = target or _target()
    return evaluate_actor_permission_gate(
        _probe(target=review_target, **updates),
        expected_target=review_target,
        evaluated_at=EVALUATED_AT,
    )


def _probe(target: ReviewTarget | None = None, **updates: object) -> ActorPermissionProbeResult:
    review_target = target or _target()
    values = {
        "actor": "reviewgraph-bot",
        "credential_principal": "gh-user:reviewgraph-bot",
        "credential_source": "pat",
        "repo_permission": "write",
        "installation_permission": None,
        "endpoint_permission": None,
        "issue_comment_write": True,
        "check_method": "fake_issue_comment_permission_probe",
        "endpoint_method": "POST",
        "checked_target": review_target,
        "checked_at": CHECKED_AT,
        "endpoint": issue_comment_endpoint(review_target),
        "endpoint_kind": "issue_comment",
        "request_id": "REQ-1",
    }
    values.update(updates)
    return ActorPermissionProbeResult(**values)
