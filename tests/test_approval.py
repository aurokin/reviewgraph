import ast
from dataclasses import replace
from pathlib import Path

import pytest

from reviewgraph.approval import build_approval_proof
from reviewgraph.hashing import final_payload_hash, findings_hash, marker_payload_hash, visible_body_hash
from reviewgraph.models import (
    ApprovalProofReasonCode,
    CandidateIssueCommentPayload,
    ClassifiedFinding,
    Confidence,
    GateStatus,
    LocalNote,
    OutputClassification,
    PostingDestination,
    PostingPlan,
    PostingPlanItem,
    RedactionStatus,
    ReviewTarget,
    ReviewVerdict,
    Severity,
    SuggestedReply,
)
from reviewgraph.payload_validation import validate_final_issue_comment_payload
from reviewgraph.posting import build_candidate_issue_comment_payload, build_posting_plan


def target() -> ReviewTarget:
    return ReviewTarget(
        owner_repo="acme/widgets",
        pr_number=42,
        base_sha="base123",
        head_sha="head456",
        merge_base_sha="merge789",
        diff_basis="merge_base",
    )


def finding(
    finding_id: str = "finding-1",
    body: str = "The new branch returns stale data when the cache misses.",
    fingerprint: str = "fp-1",
) -> ClassifiedFinding:
    return ClassifiedFinding(
        id=finding_id,
        source_reviewer="correctness",
        source_stage="initial_triage",
        title="Cache miss returns stale data",
        body=body,
        evidence="changed line 12",
        path="src/cache.py",
        line=12,
        priority=1,
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        fingerprint=fingerprint,
    )


def test_approval_proof_stores_approved_ids_target_and_final_hash() -> None:
    findings = (finding(), finding("finding-2", body="Second approved issue.", fingerprint="fp-2"))
    plan = build_posting_plan(findings=findings)
    candidate = build_candidate_issue_comment_payload(review_target=target(), posting_plan=plan, findings=findings)

    proof = build_approval_proof(
        approved_item_ids=("finding-1", "finding-2"),
        review_target=target(),
        posting_plan=plan,
        findings=findings,
        candidate_payload=candidate,
        run_id="run-123",
        approved_by="local-user",
        timestamp="2026-05-07T04:20:00Z",
    )

    visible_body = (
        "ReviewGraph approved findings\n"
        "Target: acme/widgets#42\n"
        "Head: head456\n\n"
        "Approved findings:\n"
        "- P1 Cache miss returns stale data: The new branch returns stale data when the cache misses. (src/cache.py:12)\n"
        "- P1 Cache miss returns stale data: Second approved issue. (src/cache.py:12)\n"
    )
    marker_line = (
        "<!-- reviewgraph:v1 run_id=run-123 "
        f"target={target().target_hash()} "
        f"payload={marker_payload_hash(visible_body)} "
        f"findings={findings_hash(('fp-1', 'fp-2'))} -->"
    )

    assert proof.status == GateStatus.PASS
    assert proof.approved_item_ids == ("finding-1", "finding-2")
    assert proof.approved_review_target == target()
    assert proof.approved_review_target_hash == target().target_hash()
    assert proof.final_visible_body_hash == visible_body_hash(visible_body)
    assert proof.marker_payload_hash == marker_payload_hash(visible_body)
    assert proof.findings_hash == findings_hash(("fp-1", "fp-2"))
    assert proof.marker_line == marker_line
    assert proof.approved_final_payload_hash == final_payload_hash(f"{visible_body}{marker_line}\n")
    assert proof.approved_by == "local-user"
    assert proof.timestamp == "2026-05-07T04:20:00Z"
    assert proof.final_redaction_status == RedactionStatus(redacted=False, replacement_count=0)


def test_approving_subset_changes_final_hash_and_findings_hash() -> None:
    findings = (finding(), finding("finding-2", body="Second approved issue.", fingerprint="fp-2"))
    plan = build_posting_plan(findings=findings)
    candidate = build_candidate_issue_comment_payload(review_target=target(), posting_plan=plan, findings=findings)

    all_proof = _proof(("finding-1", "finding-2"), plan=plan, findings=findings, candidate=candidate)
    subset_proof = _proof(("finding-1",), plan=plan, findings=findings, candidate=candidate)

    assert all_proof.status == GateStatus.PASS
    assert subset_proof.status == GateStatus.PASS
    assert subset_proof.approved_final_payload_hash != all_proof.approved_final_payload_hash
    assert subset_proof.findings_hash == findings_hash(("fp-1",))
    assert all_proof.findings_hash == findings_hash(("fp-1", "fp-2"))


def test_approval_proof_is_order_independent_for_approved_id_set() -> None:
    findings = (finding(), finding("finding-2", body="Second approved issue.", fingerprint="fp-2"))
    plan = build_posting_plan(findings=findings)
    candidate = build_candidate_issue_comment_payload(review_target=target(), posting_plan=plan, findings=findings)

    normal = _proof(("finding-1", "finding-2"), plan=plan, findings=findings, candidate=candidate)
    reversed_ids = _proof(("finding-2", "finding-1"), plan=plan, findings=findings, candidate=candidate)

    assert normal.approved_item_ids == ("finding-1", "finding-2")
    assert reversed_ids.approved_item_ids == ("finding-1", "finding-2")
    assert reversed_ids.marker_line == normal.marker_line
    assert reversed_ids.final_visible_body_hash == normal.final_visible_body_hash
    assert reversed_ids.approved_final_payload_hash == normal.approved_final_payload_hash


def test_stale_candidate_payload_with_recomputed_hashes_is_rejected() -> None:
    findings = (finding(),)
    plan = build_posting_plan(findings=findings)
    candidate = build_candidate_issue_comment_payload(review_target=target(), posting_plan=plan, findings=findings)
    tampered_body = f"{candidate.body}\nUnexpected public text"
    tampered = replace(
        candidate,
        body=tampered_body,
        visible_body_hash=visible_body_hash(tampered_body),
    )

    proof = _proof(("finding-1",), plan=plan, findings=findings, candidate=tampered)

    assert proof.status == GateStatus.FAIL
    assert proof.reason_code == ApprovalProofReasonCode.CANDIDATE_BINDING_MISMATCH


def test_candidate_payload_is_not_final_or_writer_input() -> None:
    candidate = _candidate_payload()

    result = validate_final_issue_comment_payload(candidate)

    assert isinstance(candidate, CandidateIssueCommentPayload)
    assert result.status == GateStatus.FAIL
    assert result.reason_code.value == "not_final_payload"


def test_empty_approval_duplicate_fingerprints_and_invalid_run_id_fail_closed() -> None:
    findings = (finding(),)
    plan = build_posting_plan(findings=findings)
    candidate = build_candidate_issue_comment_payload(review_target=target(), posting_plan=plan, findings=findings)
    duplicate_plan = PostingPlan(
        items=(
            PostingPlanItem(
                id="finding-1",
                source_classification=OutputClassification.POSTABLE_FINDING.value,
                destination=PostingDestination.REVIEW_BODY_ITEM,
                public_payload_eligible=True,
                fingerprint="fp-1",
                body="First duplicate",
            ),
            PostingPlanItem(
                id="finding-2",
                source_classification=OutputClassification.POSTABLE_FINDING.value,
                destination=PostingDestination.REVIEW_BODY_ITEM,
                public_payload_eligible=True,
                fingerprint="fp-1",
                body="Second duplicate",
            ),
        )
    )
    duplicate_findings = (
        finding(),
        finding("finding-2", body="Duplicate fingerprint issue.", fingerprint="fp-1"),
    )

    assert _proof((), plan=plan, findings=findings, candidate=candidate).reason_code == ApprovalProofReasonCode.EMPTY_APPROVAL
    assert (
        _proof(("finding-1", "finding-1"), plan=plan, findings=findings, candidate=candidate).reason_code
        == ApprovalProofReasonCode.DUPLICATE_APPROVED_FINGERPRINT
    )
    assert (
        _proof(("finding-1", "finding-2"), plan=duplicate_plan, findings=duplicate_findings, candidate=candidate).reason_code
        == ApprovalProofReasonCode.DUPLICATE_APPROVED_FINGERPRINT
    )
    assert (
        build_approval_proof(
            approved_item_ids=("finding-1",),
            review_target=target(),
            posting_plan=plan,
            findings=findings,
            candidate_payload=candidate,
            run_id="bad=value",
            approved_by="local-user",
            timestamp="2026-05-07T04:20:00Z",
        ).reason_code
        == ApprovalProofReasonCode.INVALID_RUN_ID
    )


def test_non_public_unknown_and_summary_items_are_rejected() -> None:
    findings = (finding(),)
    plan_with_local = build_posting_plan(
        findings=findings,
        local_notes=[LocalNote("note-1", "Local note", "Keep this local.", "not public")],
        suggested_replies=[SuggestedReply("reply-1", "comment-1", "Draft reply")],
    )
    candidate = build_candidate_issue_comment_payload(review_target=target(), posting_plan=plan_with_local, findings=findings)
    summary_plan = build_posting_plan(findings=findings, include_summary=True)
    summary_candidate = build_candidate_issue_comment_payload(review_target=target(), posting_plan=summary_plan, findings=findings)
    inline_plan = PostingPlan(
        items=(
            PostingPlanItem(
                id="finding-1",
                source_classification=OutputClassification.POSTABLE_FINDING.value,
                destination=PostingDestination.INLINE_CANDIDATE,
                public_payload_eligible=False,
                fingerprint="fp-1",
                body="Inline only",
            ),
        )
    )

    assert _proof(("missing",), plan=plan_with_local, findings=findings, candidate=candidate).reason_code == ApprovalProofReasonCode.UNKNOWN_APPROVED_ID
    assert _proof(("note-1",), plan=plan_with_local, findings=findings, candidate=candidate).reason_code == ApprovalProofReasonCode.NON_PUBLIC_DESTINATION
    assert _proof(("reply-1",), plan=plan_with_local, findings=findings, candidate=candidate).reason_code == ApprovalProofReasonCode.NON_PUBLIC_DESTINATION
    assert _proof(("finding-1",), plan=inline_plan, findings=findings, candidate=candidate).reason_code == ApprovalProofReasonCode.NON_PUBLIC_DESTINATION
    assert _proof(("finding-1",), plan=summary_plan, findings=findings, candidate=summary_candidate).reason_code == ApprovalProofReasonCode.SUMMARY_ITEM_DEFERRED


def test_final_body_proof_redacts_before_hashing() -> None:
    secret = "api_key = sk_live_1234567890abcdef"
    findings = (finding(body=f"Secret leaked: {secret}"),)
    plan = build_posting_plan(findings=findings)
    candidate = build_candidate_issue_comment_payload(review_target=target(), posting_plan=plan, findings=findings)

    proof = _proof(("finding-1",), plan=plan, findings=findings, candidate=candidate)

    assert proof.status == GateStatus.PASS
    assert proof.final_redaction_status is not None
    assert proof.final_redaction_status.redacted is True
    assert proof.final_redaction_status.categories == ("api_key",)
    assert proof.marker_payload_hash == proof.final_visible_body_hash
    assert "sk_live" not in proof.marker_line


def test_approval_proof_result_rejects_invalid_pass_marker_and_redaction_status() -> None:
    proof = _proof(
        ("finding-1",),
        plan=build_posting_plan(findings=[finding()]),
        findings=(finding(),),
        candidate=_candidate_payload(),
    )

    with pytest.raises(ValueError, match="marker_line"):
        replace(proof, marker_line="not a marker")
    with pytest.raises(ValueError, match="final_redaction_status"):
        replace(proof, final_redaction_status=RedactionStatus(False, 0, status=GateStatus.FAIL))
    with pytest.raises(ValueError, match="marker_payload_hash"):
        replace(proof, marker_payload_hash="sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="final_visible_body_hash"):
        replace(proof, final_visible_body_hash="sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="strict sha256"):
        replace(proof, approved_final_payload_hash="sha256:not-strict")


def test_request_changes_public_text_is_deferred() -> None:
    findings = (finding(),)
    plan = build_posting_plan(findings=findings)
    candidate = build_candidate_issue_comment_payload(review_target=target(), posting_plan=plan, findings=findings)

    proof = build_approval_proof(
        approved_item_ids=("finding-1",),
        review_target=target(),
        posting_plan=plan,
        findings=findings,
        candidate_payload=candidate,
        run_id="run-123",
        approved_by="local-user",
        timestamp="2026-05-07T04:20:00Z",
        local_verdict=ReviewVerdict.REQUEST_CHANGES,
        include_public_verdict=True,
    )

    assert proof.reason_code == ApprovalProofReasonCode.REQUEST_CHANGES_PUBLIC_TEXT_DEFERRED


def test_approval_module_import_boundary_and_no_clock_environment_lookup() -> None:
    source = Path("src/reviewgraph/approval.py").read_text()
    tree = ast.parse(source)
    forbidden = {"github", "writer", "transport", "finalization", "live", "os", "time", "datetime"}
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert not any(any(part == forbidden_name for part in imported.split(".")) for imported in imports for forbidden_name in forbidden)


def _candidate_payload() -> CandidateIssueCommentPayload:
    findings = (finding(),)
    plan = build_posting_plan(findings=findings)
    return build_candidate_issue_comment_payload(review_target=target(), posting_plan=plan, findings=findings)


def _proof(
    approved_ids: tuple[str, ...],
    *,
    plan: PostingPlan,
    findings: tuple[ClassifiedFinding, ...],
    candidate: CandidateIssueCommentPayload,
):
    return build_approval_proof(
        approved_item_ids=approved_ids,
        review_target=target(),
        posting_plan=plan,
        findings=findings,
        candidate_payload=candidate,
        run_id="run-123",
        approved_by="local-user",
        timestamp="2026-05-07T04:20:00Z",
    )
