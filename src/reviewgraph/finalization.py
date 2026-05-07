from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass

from reviewgraph.models import (
    ACTOR_PERMISSION_FINALIZATION_MISMATCH_FIELDS,
    TARGET_FRESHNESS_CHECK_METHOD,
    TARGET_FRESHNESS_RETRYABLE_REASON_CODES,
    TARGET_FRESHNESS_TRANSPORT_ENDPOINT_KIND,
    ActorPermissionFinalizationCheckResult,
    ActorPermissionFinalizationReasonCode,
    ApprovalDecision,
    FinalIssueCommentPayload,
    FinalizationReasonCode,
    FinalizationState,
    FinalizationStatus,
    GateStatus,
    PayloadValidationResult,
    ReviewTarget,
    TargetFreshnessCheckResult,
    TargetFreshnessReasonCode,
    TargetFreshnessTransportSummary,
)
from reviewgraph.permissions import (
    DEFAULT_MAX_PROOF_AGE_SECONDS,
    ActorPermissionProbeResult,
    evaluate_actor_permission_gate,
)

TARGET_DEFAULT_MAX_PROOF_AGE_SECONDS = 300
TARGET_MAX_FUTURE_SKEW_SECONDS = 60
TARGET_TRANSPORT_REASON_CODES = frozenset(
    {
        TargetFreshnessReasonCode.TIMEOUT,
        TargetFreshnessReasonCode.RATE_LIMITED,
        TargetFreshnessReasonCode.FORBIDDEN,
        TargetFreshnessReasonCode.NOT_FOUND,
        TargetFreshnessReasonCode.UNAVAILABLE,
        TargetFreshnessReasonCode.MALFORMED_RESPONSE,
    }
)


@dataclass(frozen=True)
class TargetFreshnessProbeResult:
    current_target: ReviewTarget | None = None
    checked_at: str | None = None
    check_method: str | None = None
    transport_reason_code: TargetFreshnessReasonCode | None = None
    request_id: str | None = None
    unknown_retryable: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class FinalizeGithubPayloadResult:
    actor_permission_finalization_check: ActorPermissionFinalizationCheckResult | None
    target_freshness_check: TargetFreshnessCheckResult | None
    finalization_status: FinalizationStatus
    payload_validation: PayloadValidationResult | None = None
    final_payload: FinalIssueCommentPayload | None = None
    dry_run_error: dict[str, object] | None = None
    final_payload_builder_calls: int = 0
    writer_input_released: bool = False


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


def validate_target_freshness_for_finalization(
    *,
    approval: ApprovalDecision,
    current_probe: TargetFreshnessProbeResult,
    evaluated_at: str,
    max_proof_age_seconds: int = TARGET_DEFAULT_MAX_PROOF_AGE_SECONDS,
) -> TargetFreshnessCheckResult:
    evaluated_time = _parse_required_utc_z(evaluated_at)
    approved_time = _parse_optional_utc_z(approval.timestamp)
    if approved_time is None:
        return _target_fail(
            reason_code=TargetFreshnessReasonCode.MALFORMED_RESPONSE,
            transport_summary=_target_transport_summary(None, None, False),
            reason="approval timestamp is malformed",
        )
    if not isinstance(current_probe, TargetFreshnessProbeResult):
        return _target_fail(
            reason_code=TargetFreshnessReasonCode.MALFORMED_RESPONSE,
            transport_summary=_target_transport_summary(None, None, False),
            reason="target freshness probe is malformed",
        )
    if not isinstance(current_probe.unknown_retryable, bool):
        return _target_fail(
            reason_code=TargetFreshnessReasonCode.MALFORMED_RESPONSE,
            transport_summary=_target_transport_summary(current_probe.request_id, None, False),
            reason="target freshness retryability is malformed",
        )
    if current_probe.transport_reason_code is not None:
        if not isinstance(current_probe.transport_reason_code, TargetFreshnessReasonCode):
            return _target_fail(
                reason_code=TargetFreshnessReasonCode.MALFORMED_RESPONSE,
                transport_summary=_target_transport_summary(current_probe.request_id, TargetFreshnessReasonCode.MALFORMED_RESPONSE, False),
                reason="target freshness transport reason is malformed",
            )
        if current_probe.transport_reason_code not in TARGET_TRANSPORT_REASON_CODES:
            return _target_fail(
                reason_code=TargetFreshnessReasonCode.MALFORMED_RESPONSE,
                transport_summary=_target_transport_summary(current_probe.request_id, TargetFreshnessReasonCode.MALFORMED_RESPONSE, False),
                reason="target freshness transport reason is unsupported",
            )
        return _target_fail(
            reason_code=current_probe.transport_reason_code,
            transport_summary=_target_transport_summary(
                current_probe.request_id,
                current_probe.transport_reason_code,
                current_probe.transport_reason_code in TARGET_FRESHNESS_RETRYABLE_REASON_CODES,
            ),
            reason=f"target freshness transport failed: {current_probe.transport_reason_code.value}",
        )
    if current_probe.current_target is None:
        return _target_fail(
            reason_code=TargetFreshnessReasonCode.UNKNOWN_FRESHNESS,
            transport_summary=_target_transport_summary(
                current_probe.request_id,
                TargetFreshnessReasonCode.UNKNOWN_FRESHNESS,
                current_probe.unknown_retryable,
            ),
            reason="target freshness is unknown",
        )
    if not isinstance(current_probe.current_target, ReviewTarget):
        return _target_fail(
            reason_code=TargetFreshnessReasonCode.MALFORMED_RESPONSE,
            transport_summary=_target_transport_summary(current_probe.request_id, None, False),
            reason="target freshness current target is malformed",
        )
    if current_probe.check_method != TARGET_FRESHNESS_CHECK_METHOD:
        return _target_fail(
            reason_code=TargetFreshnessReasonCode.MALFORMED_RESPONSE,
            transport_summary=_target_transport_summary(current_probe.request_id, None, False),
            current_target=current_probe.current_target,
            reason="target freshness check method is malformed",
        )
    if current_probe.current_target.merge_base_sha is None or approval.approved_review_target.merge_base_sha is None:
        return _target_fail(
            reason_code=TargetFreshnessReasonCode.MISSING_MERGE_BASE,
            transport_summary=_target_transport_summary(current_probe.request_id, None, False),
            current_target=current_probe.current_target,
            checked_at=current_probe.checked_at if _parse_optional_utc_z(current_probe.checked_at) else None,
            reason="target freshness requires merge base",
        )
    if current_probe.checked_at is None:
        return _target_fail(
            reason_code=TargetFreshnessReasonCode.MISSING_CHECKED_AT,
            transport_summary=_target_transport_summary(current_probe.request_id, None, False),
            current_target=current_probe.current_target,
            reason="target freshness checked_at is missing",
        )
    checked_time = _parse_optional_utc_z(current_probe.checked_at)
    if checked_time is None:
        return _target_fail(
            reason_code=TargetFreshnessReasonCode.MALFORMED_RESPONSE,
            transport_summary=_target_transport_summary(current_probe.request_id, None, False),
            current_target=current_probe.current_target,
            reason="target freshness checked_at is malformed",
        )
    age_seconds = (evaluated_time - checked_time).total_seconds()
    if age_seconds > max_proof_age_seconds:
        return _target_fail(
            reason_code=TargetFreshnessReasonCode.STALE_CACHED_TARGET,
            transport_summary=_target_transport_summary(current_probe.request_id, None, False),
            current_target=current_probe.current_target,
            checked_at=current_probe.checked_at,
            reason="target freshness proof is stale",
        )
    if age_seconds < -TARGET_MAX_FUTURE_SKEW_SECONDS:
        return _target_fail(
            reason_code=TargetFreshnessReasonCode.FUTURE_CHECKED_AT,
            transport_summary=_target_transport_summary(current_probe.request_id, None, False),
            current_target=current_probe.current_target,
            checked_at=current_probe.checked_at,
            reason="target freshness proof is from the future",
        )
    if checked_time < approved_time:
        return _target_fail(
            reason_code=TargetFreshnessReasonCode.CHECKED_AT_BEFORE_APPROVAL,
            transport_summary=_target_transport_summary(current_probe.request_id, None, False),
            current_target=current_probe.current_target,
            checked_at=current_probe.checked_at,
            mismatched_fields=("checked_at",),
            reason="target freshness proof predates approval",
        )
    mismatched_fields = _target_mismatched_fields(approval.approved_review_target, current_probe.current_target)
    if mismatched_fields:
        return _target_fail(
            reason_code=TargetFreshnessReasonCode.TARGET_MISMATCH,
            transport_summary=_target_transport_summary(current_probe.request_id, None, False),
            current_target=current_probe.current_target,
            checked_at=current_probe.checked_at,
            mismatched_fields=mismatched_fields,
            reason="current target differs from approved target",
        )
    return TargetFreshnessCheckResult(
        status=GateStatus.PASS,
        transport_summary=_target_transport_summary(current_probe.request_id, None, False),
        current_target=current_probe.current_target,
        current_target_hash=current_probe.current_target.target_hash(),
        current_checked_at=current_probe.checked_at,
        check_method=TARGET_FRESHNESS_CHECK_METHOD,
    )


def finalize_github_payload(
    *,
    approval: ApprovalDecision,
    approved_findings_by_id: dict[str, object],
    current_actor_permission_probe: ActorPermissionProbeResult,
    current_target_probe: TargetFreshnessProbeResult,
    evaluated_at: str,
    final_payload_builder=None,
) -> FinalizeGithubPayloadResult:
    approved_preflight = _approval_preflight(approval, approved_findings_by_id)
    if approved_preflight is not None:
        return FinalizeGithubPayloadResult(
            actor_permission_finalization_check=None,
            target_freshness_check=None,
            finalization_status=FinalizationStatus(
                state=FinalizationState.FAILED_CLOSED,
                final_payload_hash=None,
                target_hash=approval.approved_review_target_hash,
                reason_code=FinalizationReasonCode.APPROVAL_PREFLIGHT_FAILED,
                reason=approved_preflight,
            ),
            dry_run_error=_dry_run_error("approval_preflight_failed", False, "approval", None, ()),
        )
    actor_check = validate_actor_permission_snapshot_for_finalization(
        approval=approval,
        current_probe=current_actor_permission_probe,
        expected_target=approval.approved_review_target,
        evaluated_at=evaluated_at,
    )
    if actor_check.status != GateStatus.PASS:
        return FinalizeGithubPayloadResult(
            actor_permission_finalization_check=actor_check,
            target_freshness_check=None,
            finalization_status=FinalizationStatus(
                state=FinalizationState.FAILED_CLOSED,
                final_payload_hash=None,
                target_hash=approval.approved_review_target_hash,
                reason_code=FinalizationReasonCode.ACTOR_PERMISSION_FAILED,
                reason="actor permission finalization preflight failed",
            ),
            dry_run_error=_dry_run_error("actor_permission_failed", False, "issue_comment_permission", None, ()),
        )
    target_check = validate_target_freshness_for_finalization(
        approval=approval,
        current_probe=current_target_probe,
        evaluated_at=evaluated_at,
    )
    if target_check.status != GateStatus.PASS:
        summary = target_check.transport_summary
        return FinalizeGithubPayloadResult(
            actor_permission_finalization_check=actor_check,
            target_freshness_check=target_check,
            finalization_status=FinalizationStatus(
                state=FinalizationState.FAILED_CLOSED,
                final_payload_hash=None,
                target_hash=approval.approved_review_target_hash,
                reason_code=FinalizationReasonCode.TARGET_FRESHNESS_FAILED,
                reason="target freshness preflight failed",
            ),
            dry_run_error=_dry_run_error(
                target_check.reason_code.value,
                summary.retryable,
                summary.endpoint_kind,
                summary.request_id,
                target_check.mismatched_fields,
            ),
        )
    builder_calls = 0
    if final_payload_builder is not None:
        builder_calls = 1
        payload = final_payload_builder()
        if payload.final_payload_hash != approval.approved_final_payload_hash:
            return FinalizeGithubPayloadResult(
                actor_permission_finalization_check=actor_check,
                target_freshness_check=target_check,
                finalization_status=FinalizationStatus(
                    state=FinalizationState.FAILED_CLOSED,
                    final_payload_hash=None,
                    target_hash=approval.approved_review_target_hash,
                    reason_code=FinalizationReasonCode.PAYLOAD_VALIDATION_FAILED,
                    reason="final payload hash did not match approval",
                ),
                payload_validation=None,
                final_payload_builder_calls=builder_calls,
                dry_run_error=_dry_run_error("payload_validation_failed", False, "final_payload", None, ()),
            )
    return FinalizeGithubPayloadResult(
        actor_permission_finalization_check=actor_check,
        target_freshness_check=target_check,
        finalization_status=FinalizationStatus(
            state=FinalizationState.NOT_READY,
            final_payload_hash=None,
            target_hash=approval.approved_review_target_hash,
            reason_code=FinalizationReasonCode.MARKER_RECONCILIATION_DEFERRED,
            reason="marker reconciliation is deferred",
        ),
        final_payload_builder_calls=builder_calls,
        writer_input_released=False,
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


def _target_mismatched_fields(approved: ReviewTarget, current: ReviewTarget) -> tuple[str, ...]:
    comparisons = (
        ("owner_repo", approved.owner_repo, current.owner_repo),
        ("pr_number", approved.pr_number, current.pr_number),
        ("base_sha", approved.base_sha, current.base_sha),
        ("head_sha", approved.head_sha, current.head_sha),
        ("merge_base_sha", approved.merge_base_sha, current.merge_base_sha),
        ("diff_basis", approved.diff_basis, current.diff_basis),
    )
    return tuple(name for name, approved_value, current_value in comparisons if approved_value != current_value)


def _target_fail(
    *,
    reason_code: TargetFreshnessReasonCode,
    transport_summary: TargetFreshnessTransportSummary,
    current_target: ReviewTarget | None = None,
    checked_at: str | None = None,
    mismatched_fields: tuple[str, ...] = (),
    reason: str,
) -> TargetFreshnessCheckResult:
    return TargetFreshnessCheckResult(
        status=GateStatus.FAIL,
        reason_code=reason_code,
        transport_summary=transport_summary,
        current_target=current_target,
        current_target_hash=current_target.target_hash() if current_target is not None else None,
        current_checked_at=checked_at,
        check_method=TARGET_FRESHNESS_CHECK_METHOD,
        mismatched_fields=mismatched_fields,
        reason=reason,
    )


def _target_transport_summary(
    request_id: str | None,
    reason_code: TargetFreshnessReasonCode | None,
    retryable: bool,
) -> TargetFreshnessTransportSummary:
    return TargetFreshnessTransportSummary(
        endpoint_kind=TARGET_FRESHNESS_TRANSPORT_ENDPOINT_KIND,
        retryable=retryable,
        reason_code=reason_code,
        request_id=_safe_request_id(request_id),
    )


def _approval_preflight(approval: ApprovalDecision, approved_findings_by_id: dict[str, object]) -> str | None:
    if not approval.approved:
        return "approval is not approved"
    if not approval.approved_item_ids:
        return "approval has no approved item ids"
    if len(set(approval.approved_item_ids)) != len(approval.approved_item_ids):
        return "approval has duplicate approved item ids"
    for item_id in approval.approved_item_ids:
        if item_id not in approved_findings_by_id:
            return "approval references an unknown approved item id"
    fingerprints: list[str] = []
    for item_id in approval.approved_item_ids:
        finding = approved_findings_by_id[item_id]
        fingerprint = getattr(finding, "fingerprint", None)
        if not isinstance(fingerprint, str) or not fingerprint:
            return "approved finding is missing fingerprint"
        fingerprints.append(fingerprint)
    if len(set(fingerprints)) != len(fingerprints):
        return "approval has duplicate approved fingerprints"
    return None


def _dry_run_error(
    reason_code: str,
    retryable: bool,
    endpoint_kind: str,
    request_id: str | None,
    mismatched_fields: tuple[str, ...],
) -> dict[str, object]:
    return {
        "reason_code": reason_code,
        "retryable": retryable,
        "endpoint_kind": endpoint_kind,
        "request_id": request_id,
        "mismatched_fields": list(mismatched_fields),
    }


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


def _parse_required_utc_z(value: str) -> datetime:
    parsed = _parse_optional_utc_z(value)
    if parsed is None:
        raise ValueError("timestamp must be UTC RFC3339 with trailing Z")
    return parsed


def _parse_optional_utc_z(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z") or "T" not in value:
        return None
    try:
        return datetime.fromisoformat(value.removesuffix("Z") + "+00:00").astimezone(timezone.utc)
    except ValueError:
        return None


def _safe_request_id(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        return None
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:/#-")
    if len(value) > 128 or any(char not in allowed for char in value):
        return None
    if any(secret in value.casefold() for secret in ("token", "ghp_", "github_pat_", "gho_", "ghs_", "ghu_")):
        return None
    return value
