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
    ApprovalDecisionBuildReasonCode,
    ApprovalDecisionBuildResult,
    ClassifiedFinding,
    FinalIssueCommentPayload,
    FinalizationReasonCode,
    FinalizationState,
    FinalizationStatus,
    GateStatus,
    OutputClassification,
    PayloadValidationResult,
    PostingDestination,
    PostingPlan,
    ReviewTarget,
    TargetFreshnessCheckResult,
    TargetFreshnessReasonCode,
    TargetFreshnessTransportSummary,
    WriterReleaseItemDiagnostic,
    WriterReleaseItemReasonCode,
    WriterReleasePreflightReasonCode,
    WriterReleasePreflightResult,
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


@dataclass(frozen=True)
class ApprovedItemDescriptor:
    item_id: str
    source_classification: str
    destination: PostingDestination
    public_payload_eligible: bool
    has_fingerprint: bool

    def __post_init__(self) -> None:
        if not isinstance(self.item_id, str) or not self.item_id:
            raise ValueError("approved item descriptor item_id is required")
        if not isinstance(self.source_classification, str) or not self.source_classification:
            raise ValueError("approved item descriptor source_classification is required")
        if not isinstance(self.destination, PostingDestination):
            raise ValueError("approved item descriptor destination must be valid")
        if type(self.public_payload_eligible) is not bool:
            raise ValueError("approved item descriptor public_payload_eligible must be bool")
        if type(self.has_fingerprint) is not bool:
            raise ValueError("approved item descriptor has_fingerprint must be bool")


def evaluate_writer_release_preflight(
    *,
    post_enabled: bool,
    approval_result: ApprovalDecisionBuildResult | ApprovalDecision | None,
    posting_plan: PostingPlan,
    current_items_by_id: dict[str, ApprovedItemDescriptor],
) -> WriterReleasePreflightResult:
    if type(post_enabled) is not bool:
        raise ValueError("writer release preflight post_enabled must be bool")
    if not isinstance(posting_plan, PostingPlan):
        raise ValueError("writer release preflight posting_plan must be a PostingPlan")
    if not isinstance(current_items_by_id, dict) or any(
        not isinstance(key, str) or not isinstance(value, ApprovedItemDescriptor)
        for key, value in current_items_by_id.items()
    ):
        raise ValueError("writer release preflight current_items_by_id must map ids to descriptors")
    if not post_enabled:
        return _writer_preflight_fail(WriterReleasePreflightReasonCode.POST_DISABLED)
    if isinstance(approval_result, ApprovalDecisionBuildResult):
        if approval_result.status != GateStatus.PASS:
            return _writer_preflight_fail(
                WriterReleasePreflightReasonCode.APPROVAL_BUILD_FAILED,
                nested_reason_code=approval_result.reason_code,
                nested_approval_proof_reason_code=approval_result.approval_proof_reason_code,
                nested_actor_permission_reason_code=approval_result.actor_permission_reason_code,
            )
        approval = approval_result.approval
    else:
        approval = approval_result
    if approval is None:
        return _writer_preflight_fail(WriterReleasePreflightReasonCode.MISSING_APPROVAL)
    if not approval.approved:
        return _writer_preflight_fail(WriterReleasePreflightReasonCode.REJECTED_APPROVAL)
    return _writer_preflight_for_approval(
        approval=approval,
        posting_plan=posting_plan,
        current_items_by_id=current_items_by_id,
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
    posting_plan: PostingPlan,
    approved_findings_by_id: dict[str, object],
    current_actor_permission_probe: ActorPermissionProbeResult,
    current_target_probe: TargetFreshnessProbeResult,
    evaluated_at: str,
    final_payload_builder=None,
) -> FinalizeGithubPayloadResult:
    approved_preflight = _approval_preflight(approval, posting_plan, approved_findings_by_id)
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


def _writer_preflight_for_approval(
    *,
    approval: ApprovalDecision,
    posting_plan: PostingPlan,
    current_items_by_id: dict[str, ApprovedItemDescriptor],
) -> WriterReleasePreflightResult:
    duplicate = _duplicate_value(approval.approved_item_ids)
    if duplicate is not None:
        return _writer_preflight_fail(
            WriterReleasePreflightReasonCode.DUPLICATE_APPROVED_ITEM,
        )
    items_by_id = {item.id: item for item in posting_plan.items}
    diagnostics: list[WriterReleaseItemDiagnostic] = []
    fingerprints: list[str] = []
    for item_id in approval.approved_item_ids:
        plan_item = items_by_id.get(item_id)
        descriptor = current_items_by_id.get(item_id)
        if plan_item is None or descriptor is None:
            diagnostics.append(
                WriterReleaseItemDiagnostic(
                    item_id=item_id,
                    reason_code=WriterReleaseItemReasonCode.MISSING_CURRENT_ITEM,
                )
            )
            continue
        if not _descriptor_matches_plan_item(descriptor, plan_item):
            diagnostics.append(_plan_item_diagnostic(plan_item))
            continue
        diagnostic = _public_item_diagnostic(descriptor)
        if diagnostic is not None:
            diagnostics.append(diagnostic)
            continue
        fingerprints.append(plan_item.fingerprint or "")
    duplicate_fingerprint = _duplicate_value(tuple(fingerprints))
    if duplicate_fingerprint is not None:
        return _writer_preflight_fail(WriterReleasePreflightReasonCode.DUPLICATE_APPROVED_FINGERPRINT)
    if diagnostics:
        reason = (
            WriterReleasePreflightReasonCode.UNKNOWN_APPROVED_ID
            if any(item.reason_code == WriterReleaseItemReasonCode.MISSING_CURRENT_ITEM for item in diagnostics)
            else WriterReleasePreflightReasonCode.NON_PUBLIC_APPROVED_ITEM
        )
        return _writer_preflight_fail(reason, item_diagnostics=tuple(diagnostics))
    return WriterReleasePreflightResult(
        status=GateStatus.PASS,
        writer_input_released=False,
        eligible_for_finalization=True,
        approved_item_ids=approval.approved_item_ids,
    )


def _writer_preflight_fail(
    reason_code: WriterReleasePreflightReasonCode,
    *,
    nested_reason_code: ApprovalDecisionBuildReasonCode | None = None,
    nested_approval_proof_reason_code=None,
    nested_actor_permission_reason_code=None,
    item_diagnostics: tuple[WriterReleaseItemDiagnostic, ...] = (),
) -> WriterReleasePreflightResult:
    return WriterReleasePreflightResult(
        status=GateStatus.FAIL,
        writer_input_released=False,
        reason_code=reason_code,
        nested_reason_code=nested_reason_code,
        nested_approval_proof_reason_code=nested_approval_proof_reason_code,
        nested_actor_permission_reason_code=nested_actor_permission_reason_code,
        item_diagnostics=item_diagnostics,
    )


def _public_item_diagnostic(descriptor: ApprovedItemDescriptor) -> WriterReleaseItemDiagnostic | None:
    if not descriptor.public_payload_eligible:
        return _diagnostic(descriptor, WriterReleaseItemReasonCode.NOT_PUBLIC_PAYLOAD_ELIGIBLE)
    if descriptor.destination != PostingDestination.REVIEW_BODY_ITEM:
        return _diagnostic(descriptor, WriterReleaseItemReasonCode.WRONG_DESTINATION)
    if descriptor.source_classification != OutputClassification.POSTABLE_FINDING.value:
        return _diagnostic(descriptor, WriterReleaseItemReasonCode.WRONG_SOURCE_CLASSIFICATION)
    if not descriptor.has_fingerprint:
        return _diagnostic(descriptor, WriterReleaseItemReasonCode.MISSING_FINGERPRINT)
    return None


def _descriptor_matches_plan_item(descriptor: ApprovedItemDescriptor, item: object) -> bool:
    return (
        getattr(item, "id", None) == descriptor.item_id
        and getattr(item, "source_classification", None) == descriptor.source_classification
        and getattr(item, "destination", None) == descriptor.destination
        and getattr(item, "public_payload_eligible", None) == descriptor.public_payload_eligible
        and bool(getattr(item, "fingerprint", None)) == descriptor.has_fingerprint
    )


def _plan_item_diagnostic(item) -> WriterReleaseItemDiagnostic:
    return WriterReleaseItemDiagnostic(
        item_id=item.id,
        reason_code=WriterReleaseItemReasonCode.NOT_PUBLIC_PAYLOAD_ELIGIBLE
        if not item.public_payload_eligible
        else WriterReleaseItemReasonCode.WRONG_DESTINATION,
        destination=item.destination,
        source_classification=item.source_classification,
        public_payload_eligible=item.public_payload_eligible,
    )


def _diagnostic(
    descriptor: ApprovedItemDescriptor,
    reason_code: WriterReleaseItemReasonCode,
) -> WriterReleaseItemDiagnostic:
    return WriterReleaseItemDiagnostic(
        item_id=descriptor.item_id,
        reason_code=reason_code,
        destination=descriptor.destination,
        source_classification=descriptor.source_classification,
        public_payload_eligible=descriptor.public_payload_eligible,
    )


def _approval_preflight(
    approval: ApprovalDecision,
    posting_plan: PostingPlan,
    approved_findings_by_id: dict[str, object],
) -> str | None:
    if not approval.approved:
        return "approval is not approved"
    if not approval.approved_item_ids:
        return "approval has no approved item ids"
    if len(set(approval.approved_item_ids)) != len(approval.approved_item_ids):
        return "approval has duplicate approved item ids"
    items_by_id = {item.id: item for item in posting_plan.items}
    for item_id in approval.approved_item_ids:
        item = items_by_id.get(item_id)
        if item is None:
            return "approval references an unknown approved item id"
        if (
            item.destination != PostingDestination.REVIEW_BODY_ITEM
            or item.source_classification != OutputClassification.POSTABLE_FINDING.value
            or not item.public_payload_eligible
        ):
            return "approval references a non-public approved item"
        if not item.fingerprint:
            return "approved posting plan item is missing fingerprint"
        if item_id not in approved_findings_by_id:
            return "approval references an unknown approved item id"
    fingerprints: list[str] = []
    for item_id in approval.approved_item_ids:
        finding = approved_findings_by_id[item_id]
        if not isinstance(finding, ClassifiedFinding):
            return "approval references a non-public approved item"
        if getattr(finding, "classification") != OutputClassification.POSTABLE_FINDING:
            return "approval references a non-public approved item"
        fingerprint = getattr(finding, "fingerprint", None)
        if not isinstance(fingerprint, str) or not fingerprint:
            return "approved finding is missing fingerprint"
        if items_by_id[item_id].fingerprint != fingerprint:
            return "approved finding fingerprint does not match posting plan"
        fingerprints.append(fingerprint)
    if len(set(fingerprints)) != len(fingerprints):
        return "approval has duplicate approved fingerprints"
    return None


def _duplicate_value(values: tuple[str, ...]) -> str | None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            return value
        seen.add(value)
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
