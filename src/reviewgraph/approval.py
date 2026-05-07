from __future__ import annotations

from collections.abc import Iterable

from reviewgraph.hashing import (
    final_payload_hash,
    findings_hash,
    is_exact_reviewgraph_v1_marker_line,
    marker_payload_hash,
    visible_body_hash,
)
from reviewgraph.markers import build_reviewgraph_marker_line
from reviewgraph.models import (
    ApprovalDecision,
    ApprovalDecisionBuildReasonCode,
    ApprovalDecisionBuildResult,
    ApprovalProofReasonCode,
    ApprovalProofResult,
    ActorPermissionGateResult,
    ActorPermissionReasonCode,
    CandidateIssueCommentPayload,
    ClassifiedFinding,
    GateStatus,
    OutputClassification,
    PostingDestination,
    PostingPlan,
    PostingPlanItem,
    RedactionStatus,
    ReviewTarget,
    ReviewVerdict,
)
from reviewgraph.payload_validation import validate_candidate_issue_comment_payload
from reviewgraph.posting import build_candidate_issue_comment_payload
from reviewgraph.redaction import redact_text


class ApprovalProofError(ValueError):
    pass


def build_approval_proof(
    *,
    approved_item_ids: Iterable[str],
    review_target: ReviewTarget,
    posting_plan: PostingPlan,
    findings: Iterable[ClassifiedFinding],
    candidate_payload: CandidateIssueCommentPayload,
    run_id: str,
    approved_by: str,
    timestamp: str,
    local_verdict: ReviewVerdict | None = None,
    include_public_verdict: bool = False,
) -> ApprovalProofResult:
    approved_ids = tuple(approved_item_ids)
    findings_tuple = tuple(findings)
    if not _is_valid_run_id(run_id):
        return _fail(ApprovalProofReasonCode.INVALID_RUN_ID, "approval proof run_id does not match marker grammar")
    if include_public_verdict and local_verdict == ReviewVerdict.REQUEST_CHANGES:
        return _fail(
            ApprovalProofReasonCode.REQUEST_CHANGES_PUBLIC_TEXT_DEFERRED,
            "public request_changes text is deferred",
        )
    summary = _summary_item(posting_plan)
    if summary is not None:
        return _fail(ApprovalProofReasonCode.SUMMARY_ITEM_DEFERRED, "summary item approval is deferred")
    if not approved_ids:
        return _fail(ApprovalProofReasonCode.EMPTY_APPROVAL, "approved approval proof requires approved item ids")
    if len(set(approved_ids)) != len(approved_ids):
        return _fail(ApprovalProofReasonCode.DUPLICATE_APPROVED_FINGERPRINT, "duplicate approved item ids")

    public_items_by_id = {item.id: item for item in posting_plan.public_payload_items}
    approved_id_set = set(approved_ids)
    findings_by_id = {finding.id: finding for finding in findings_tuple}
    for item_id in approved_ids:
        if item_id not in {item.id for item in posting_plan.items}:
            return _fail(ApprovalProofReasonCode.UNKNOWN_APPROVED_ID, f"unknown approved item id: {item_id}")
    selected_items: list[PostingPlanItem] = []
    selected_fingerprints: list[str] = []
    for item in posting_plan.items:
        if item.id not in approved_id_set:
            continue
        if item.id not in public_items_by_id:
            return _fail(ApprovalProofReasonCode.NON_PUBLIC_DESTINATION, f"approved item is not public: {item.id}")
        if item.destination != PostingDestination.REVIEW_BODY_ITEM:
            return _fail(ApprovalProofReasonCode.NON_PUBLIC_DESTINATION, f"approved item is not review_body_item: {item.id}")
        if item.source_classification != OutputClassification.POSTABLE_FINDING.value:
            return _fail(ApprovalProofReasonCode.NON_PUBLIC_DESTINATION, f"approved item is not a postable finding: {item.id}")
        finding = findings_by_id.get(item.id)
        if finding is None or item.fingerprint != finding.fingerprint:
            return _fail(ApprovalProofReasonCode.UNKNOWN_APPROVED_ID, f"approved item has no current finding: {item.id}")
        selected_items.append(item)
        selected_fingerprints.append(finding.fingerprint)

    sorted_fingerprints = tuple(sorted(selected_fingerprints))
    if len(set(sorted_fingerprints)) != len(sorted_fingerprints):
        return _fail(ApprovalProofReasonCode.DUPLICATE_APPROVED_FINGERPRINT, "duplicate approved fingerprints")

    candidate_validation = validate_candidate_issue_comment_payload(
        candidate_payload,
        expected_review_target=review_target,
        expected_posting_plan=posting_plan,
        expected_findings=findings_tuple,
        expected_local_verdict=local_verdict,
        expected_include_public_verdict=include_public_verdict,
    )
    if candidate_validation.status != GateStatus.PASS:
        return _fail(ApprovalProofReasonCode.CANDIDATE_BINDING_MISMATCH, candidate_validation.reason or "candidate binding failed")

    raw_visible_body = _approved_visible_body(
        review_target=review_target,
        findings_by_id=findings_by_id,
        selected_items=tuple(selected_items),
        local_verdict=local_verdict,
        include_public_verdict=include_public_verdict,
    )
    redaction = redact_text(raw_visible_body)
    final_redaction_status = RedactionStatus(
        redacted=redaction.redacted,
        replacement_count=redaction.replacement_count,
        categories=redaction.categories,
    )
    if final_redaction_status.status != GateStatus.PASS:
        return _fail(ApprovalProofReasonCode.FINAL_REDACTION_FAILED, "final redaction did not pass")

    visible_body = redaction.text.rstrip("\n") + "\n"
    visible_hash = visible_body_hash(visible_body)
    selected_findings_hash = findings_hash(sorted_fingerprints)
    marker_line = build_reviewgraph_marker_line(
        run_id=run_id,
        review_target=review_target,
        visible_body=visible_body,
        finding_fingerprints=sorted_fingerprints,
    )
    if not is_exact_reviewgraph_v1_marker_line(marker_line):
        return _fail(ApprovalProofReasonCode.INVALID_RUN_ID, "generated marker line is invalid")
    full_body = f"{visible_body}{marker_line}\n"

    return ApprovalProofResult(
        status=GateStatus.PASS,
        approved_item_ids=tuple(item.id for item in selected_items),
        approved_review_target=review_target,
        approved_review_target_hash=review_target.target_hash(),
        approved_final_payload_hash=final_payload_hash(full_body),
        final_visible_body_hash=visible_hash,
        marker_payload_hash=marker_payload_hash(visible_body),
        findings_hash=selected_findings_hash,
        marker_line=marker_line,
        final_redaction_status=final_redaction_status,
        include_public_verdict=include_public_verdict,
        approved_by=approved_by,
        timestamp=timestamp,
    )


def build_approval_decision(
    *,
    proof: ApprovalProofResult,
    actor_permission_gate: ActorPermissionGateResult,
    max_actor_permission_proof_age_seconds: int = 300,
    max_actor_permission_future_skew_seconds: int = 60,
) -> ApprovalDecisionBuildResult:
    if proof.status != GateStatus.PASS:
        return ApprovalDecisionBuildResult(
            status=GateStatus.FAIL,
            reason_code=ApprovalDecisionBuildReasonCode.APPROVAL_PROOF_FAILED,
            reason="approval proof did not pass",
        )
    if actor_permission_gate.status != GateStatus.PASS:
        return ApprovalDecisionBuildResult(
            status=GateStatus.FAIL,
            reason_code=ApprovalDecisionBuildReasonCode.ACTOR_PERMISSION_GATE_FAILED,
            actor_permission_reason_code=actor_permission_gate.reason_code,
            actor_permission_transport_summary=actor_permission_gate.transport_summary,
            reason="actor permission gate did not pass",
        )
    gate_age_seconds = _utc_z_age_seconds(proof.timestamp, actor_permission_gate.checked_at)
    if (
        gate_age_seconds is None
        or gate_age_seconds > max_actor_permission_proof_age_seconds
        or gate_age_seconds < -max_actor_permission_future_skew_seconds
    ):
        return ApprovalDecisionBuildResult(
            status=GateStatus.FAIL,
            reason_code=ApprovalDecisionBuildReasonCode.ACTOR_PERMISSION_GATE_FAILED,
            actor_permission_reason_code=ActorPermissionReasonCode.STALE_CACHED_PROOF,
            actor_permission_transport_summary=actor_permission_gate.transport_summary,
            reason="actor permission proof is stale at approval time",
        )
    target = proof.approved_review_target
    if (
        actor_permission_gate.checked_target != target.to_ordered_dict()
        or actor_permission_gate.checked_target_hash != target.target_hash()
        or actor_permission_gate.endpoint != _issue_comment_endpoint(target)
        or actor_permission_gate.endpoint_kind != "issue_comment"
    ):
        return ApprovalDecisionBuildResult(
            status=GateStatus.FAIL,
            reason_code=ApprovalDecisionBuildReasonCode.ACTOR_PERMISSION_TARGET_MISMATCH,
            reason="actor permission gate target did not match approval target",
        )

    return ApprovalDecisionBuildResult(
        status=GateStatus.PASS,
        approval=ApprovalDecision(
            approved=True,
            approved_item_ids=proof.approved_item_ids,
            approved_final_payload_hash=proof.approved_final_payload_hash,
            approved_review_target_hash=proof.approved_review_target_hash,
            approved_review_target=target,
            approved_github_actor=actor_permission_gate.actor,
            approved_permission=actor_permission_gate.permission,
            approved_permission_checked_at=actor_permission_gate.checked_at,
            approved_credential_principal=actor_permission_gate.credential_principal,
            approved_credential_source=actor_permission_gate.credential_source,
            approved_repo_permission=actor_permission_gate.repo_permission,
            approved_installation_permission=actor_permission_gate.installation_permission,
            approved_endpoint_permission=actor_permission_gate.endpoint_permission,
            approved_issue_comment_write=actor_permission_gate.issue_comment_write,
            approved_permission_check_method=actor_permission_gate.check_method,
            approved_permission_endpoint_method=actor_permission_gate.endpoint_method,
            approved_permission_checked_target=actor_permission_gate.checked_target,
            approved_permission_checked_target_hash=actor_permission_gate.checked_target_hash,
            approved_permission_endpoint=actor_permission_gate.endpoint,
            approved_permission_endpoint_kind=actor_permission_gate.endpoint_kind,
            approved_permission_transport_summary=actor_permission_gate.transport_summary,
            include_public_verdict=proof.include_public_verdict,
            approved_by=proof.approved_by,
            timestamp=proof.timestamp,
        ),
    )


def _approved_visible_body(
    *,
    review_target: ReviewTarget,
    findings_by_id: dict[str, ClassifiedFinding],
    selected_items: tuple[PostingPlanItem, ...],
    local_verdict: ReviewVerdict | None,
    include_public_verdict: bool,
) -> str:
    body_parts = [
        "ReviewGraph approved findings",
        f"Target: {review_target.owner_repo}#{review_target.pr_number}",
        f"Head: {review_target.head_sha}",
        "",
    ]
    if include_public_verdict and local_verdict is not None:
        body_parts.extend([f"Local verdict: {local_verdict.value}", ""])
    body_parts.append("Approved findings:")
    for item in selected_items:
        finding = findings_by_id[item.id]
        body_parts.append(
            f"- P{finding.priority} {finding.title}: {finding.body} ({finding.path}:{finding.line})"
        )
    return "\n".join(body_parts).rstrip("\n") + "\n"


def _summary_item(posting_plan: PostingPlan) -> PostingPlanItem | None:
    for item in posting_plan.items:
        if item.destination == PostingDestination.TOP_LEVEL_SUMMARY_ITEM:
            return item
    return None


def _is_valid_run_id(run_id: str) -> bool:
    marker = (
        "<!-- reviewgraph:v1 "
        f"run_id={run_id} "
        "target=sha256:0000000000000000000000000000000000000000000000000000000000000000 "
        "payload=sha256:0000000000000000000000000000000000000000000000000000000000000000 "
        "findings=sha256:0000000000000000000000000000000000000000000000000000000000000000 -->"
    )
    return is_exact_reviewgraph_v1_marker_line(marker)


def _issue_comment_endpoint(target: ReviewTarget) -> str:
    owner, repo = target.owner_repo.split("/", 1)
    return f"/repos/{owner}/{repo}/issues/{target.pr_number}/comments"


def _utc_z_age_seconds(later: str, earlier: str) -> float | None:
    later_seconds = _utc_z_seconds(later)
    earlier_seconds = _utc_z_seconds(earlier)
    if later_seconds is None or earlier_seconds is None:
        return None
    return later_seconds - earlier_seconds


def _utc_z_seconds(value: str) -> float | None:
    if not isinstance(value, str) or not value.endswith("Z") or "T" not in value:
        return None
    date, time = value[:-1].split("T", 1)
    if len(date) != 10 or date[4] != "-" or date[7] != "-":
        return None
    if len(time) < 8 or time[2] != ":" or time[5] != ":":
        return None
    try:
        year = int(date[0:4])
        month = int(date[5:7])
        day = int(date[8:10])
        hour = int(time[0:2])
        minute = int(time[3:5])
        second = int(time[6:8])
    except ValueError:
        return None
    if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 23 and minute <= 59 and second <= 59):
        return None
    days_by_month = (31, 29 if _is_leap_year(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if day > days_by_month[month - 1]:
        return None
    fractional = time[8:]
    fraction_seconds = 0.0
    if fractional:
        if len(fractional) == 1 or fractional[0] != "." or not fractional[1:].isdecimal():
            return None
        fraction_seconds = float(f"0.{fractional[1:]}")
    days = 0
    for current_year in range(1970, year):
        days += 366 if _is_leap_year(current_year) else 365
    days += sum(days_by_month[: month - 1])
    days += day - 1
    return days * 86400 + hour * 3600 + minute * 60 + second + fraction_seconds


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _fail(code: ApprovalProofReasonCode, reason: str) -> ApprovalProofResult:
    return ApprovalProofResult(status=GateStatus.FAIL, reason_code=code, reason=reason)


def assert_builder_signatures_are_pure() -> None:
    expected = build_candidate_issue_comment_payload
    if expected.__name__ != "build_candidate_issue_comment_payload":
        raise AssertionError("approval proof must use the candidate payload builder contract")
