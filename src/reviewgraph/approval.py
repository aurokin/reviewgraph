from __future__ import annotations

from collections.abc import Iterable

from reviewgraph.hashing import (
    final_payload_hash,
    findings_hash,
    is_exact_reviewgraph_v1_marker_line,
    marker_payload_hash,
    visible_body_hash,
)
from reviewgraph.models import (
    ApprovalProofReasonCode,
    ApprovalProofResult,
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
    marker_line = (
        "<!-- reviewgraph:v1 "
        f"run_id={run_id} "
        f"target={review_target.target_hash()} "
        f"payload={marker_payload_hash(visible_body)} "
        f"findings={selected_findings_hash} -->"
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


def _fail(code: ApprovalProofReasonCode, reason: str) -> ApprovalProofResult:
    return ApprovalProofResult(status=GateStatus.FAIL, reason_code=code, reason=reason)


def assert_builder_signatures_are_pure() -> None:
    expected = build_candidate_issue_comment_payload
    if expected.__name__ != "build_candidate_issue_comment_payload":
        raise AssertionError("approval proof must use the candidate payload builder contract")
