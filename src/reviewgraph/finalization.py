from __future__ import annotations

from datetime import datetime, timezone

from reviewgraph.models import (
    ACTOR_PERMISSION_FINALIZATION_MISMATCH_FIELDS,
    ActorPermissionFinalizationCheckResult,
    ActorPermissionFinalizationReasonCode,
    ApprovalDecision,
    GateStatus,
    ReviewTarget,
)
from reviewgraph.permissions import (
    DEFAULT_MAX_PROOF_AGE_SECONDS,
    ActorPermissionProbeResult,
    evaluate_actor_permission_gate,
)


def validate_actor_permission_snapshot_for_finalization(
    *,
    approval: ApprovalDecision,
    current_probe: ActorPermissionProbeResult,
    expected_target: ReviewTarget,
    evaluated_at: str,
    max_proof_age_seconds: int = DEFAULT_MAX_PROOF_AGE_SECONDS,
) -> ActorPermissionFinalizationCheckResult:
    current_gate = evaluate_actor_permission_gate(
        current_probe,
        expected_target=expected_target,
        evaluated_at=evaluated_at,
        max_proof_age_seconds=max_proof_age_seconds,
    )
    if current_gate.status != GateStatus.PASS:
        return ActorPermissionFinalizationCheckResult(
            status=GateStatus.FAIL,
            reason_code=ActorPermissionFinalizationReasonCode.ACTOR_PERMISSION_GATE_FAILED,
            actor_permission_reason_code=current_gate.reason_code,
            actor_permission_transport_summary=current_gate.transport_summary,
            current_actor_permission_checked_at=current_gate.checked_at,
            reason="current actor permission gate failed",
        )

    if expected_target != approval.approved_review_target:
        return _snapshot_mismatch(
            ("checked_target", "checked_target_hash"),
            transport_summary=current_gate.transport_summary,
            checked_at=current_gate.checked_at,
        )

    mismatched_fields = _mismatched_fields(approval, current_gate)
    if mismatched_fields:
        return _snapshot_mismatch(
            mismatched_fields,
            transport_summary=current_gate.transport_summary,
            checked_at=current_gate.checked_at,
        )

    if _parse_utc_z(current_gate.checked_at) < _parse_utc_z(approval.approved_permission_checked_at):
        return ActorPermissionFinalizationCheckResult(
            status=GateStatus.FAIL,
            reason_code=ActorPermissionFinalizationReasonCode.ACTOR_PERMISSION_CHECKED_AT_REGRESSED,
            actor_permission_transport_summary=current_gate.transport_summary,
            current_actor_permission_checked_at=current_gate.checked_at,
            mismatched_fields=("checked_at",),
            reason="current actor permission proof predates approval proof",
        )

    return ActorPermissionFinalizationCheckResult(
        status=GateStatus.PASS,
        actor_permission_transport_summary=current_gate.transport_summary,
        current_actor_permission_checked_at=current_gate.checked_at,
    )


def _mismatched_fields(approval: ApprovalDecision, current_gate) -> tuple[str, ...]:
    comparisons = (
        ("actor", approval.approved_github_actor, current_gate.actor),
        ("credential_principal", approval.approved_credential_principal, current_gate.credential_principal),
        ("credential_source", approval.approved_credential_source, current_gate.credential_source),
        ("permission", approval.approved_permission, current_gate.permission),
        ("repo_permission", approval.approved_repo_permission, current_gate.repo_permission),
        ("installation_permission", approval.approved_installation_permission, current_gate.installation_permission),
        ("endpoint_permission", approval.approved_endpoint_permission, current_gate.endpoint_permission),
        ("issue_comment_write", approval.approved_issue_comment_write, current_gate.issue_comment_write),
        ("check_method", approval.approved_permission_check_method, current_gate.check_method),
        ("endpoint_method", approval.approved_permission_endpoint_method, current_gate.endpoint_method),
        ("checked_target", dict(approval.approved_permission_checked_target), dict(current_gate.checked_target)),
        ("checked_target_hash", approval.approved_permission_checked_target_hash, current_gate.checked_target_hash),
        ("endpoint", approval.approved_permission_endpoint, current_gate.endpoint),
        ("endpoint_kind", approval.approved_permission_endpoint_kind, current_gate.endpoint_kind),
    )
    mismatches = tuple(name for name, approved, current in comparisons if approved != current)
    return tuple(name for name in mismatches if name in ACTOR_PERMISSION_FINALIZATION_MISMATCH_FIELDS)


def _snapshot_mismatch(
    fields: tuple[str, ...],
    *,
    transport_summary=None,
    checked_at: str | None = None,
) -> ActorPermissionFinalizationCheckResult:
    return ActorPermissionFinalizationCheckResult(
        status=GateStatus.FAIL,
        reason_code=ActorPermissionFinalizationReasonCode.ACTOR_PERMISSION_SNAPSHOT_MISMATCH,
        actor_permission_transport_summary=transport_summary,
        current_actor_permission_checked_at=checked_at,
        mismatched_fields=fields,
        reason="current actor permission snapshot differs from approved snapshot",
    )


def _parse_utc_z(value: str) -> datetime:
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00").astimezone(timezone.utc)
