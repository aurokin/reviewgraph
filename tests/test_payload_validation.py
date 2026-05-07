from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

from reviewgraph.hashing import final_payload_hash, findings_hash, marker_payload_hash, visible_body_hash
from reviewgraph.models import (
    ArtifactKind,
    CandidateIssueCommentPayload,
    ClassifiedFinding,
    Confidence,
    FinalIssueCommentPayload,
    GateStatus,
    GitHubIssueCommentRequest,
    PayloadValidationReasonCode,
    RedactionStatus,
    ReviewTarget,
    Severity,
)
from reviewgraph.payload_validation import (
    reject_formal_review_payload,
    validate_candidate_issue_comment_payload,
    validate_final_issue_comment_payload,
    validate_issue_comment_request,
)
from reviewgraph.posting import build_candidate_issue_comment_payload, build_posting_plan


def test_candidate_payload_validation_passes_with_independent_expected_inputs() -> None:
    expected_findings = (finding(),)
    expected_plan = build_posting_plan(findings=expected_findings)
    candidate = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=expected_plan,
        findings=expected_findings,
    )

    result = validate_candidate_issue_comment_payload(
        candidate,
        expected_review_target=target(),
        expected_posting_plan=expected_plan,
        expected_findings=expected_findings,
    )

    assert result.status == GateStatus.PASS
    assert result.payload_hash == candidate.visible_body_hash
    assert result.target_hash == target().target_hash()
    assert result.reason_code is None


def test_candidate_payload_validation_rejects_tampering_and_marker_lines() -> None:
    expected_findings = (finding(),)
    expected_plan = build_posting_plan(findings=expected_findings)
    candidate = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=expected_plan,
        findings=expected_findings,
    )
    tampered = replace(
        candidate,
        body=f"{candidate.body}\nUnexpected public text",
        visible_body_hash=visible_body_hash(f"{candidate.body}\nUnexpected public text"),
    )
    marker = _marker_line(target(), "ReviewGraph dry-run candidate\n", candidate.item_fingerprints)
    with_marker = replace(
        candidate,
        body=f"{candidate.body}{marker}\n",
        visible_body_hash=visible_body_hash(f"{candidate.body}{marker}\n"),
    )

    assert (
        validate_candidate_issue_comment_payload(
            tampered,
            expected_review_target=target(),
            expected_posting_plan=expected_plan,
            expected_findings=expected_findings,
        ).reason_code
        == PayloadValidationReasonCode.CANDIDATE_BINDING_MISMATCH
    )
    assert (
        validate_candidate_issue_comment_payload(
            with_marker,
            expected_review_target=target(),
            expected_posting_plan=expected_plan,
            expected_findings=expected_findings,
        ).reason_code
        == PayloadValidationReasonCode.CANDIDATE_CONTAINS_MARKER
    )


def test_candidate_payload_validation_rejects_hash_fingerprint_and_redaction_failures() -> None:
    expected_findings = (finding(),)
    expected_plan = build_posting_plan(findings=expected_findings)
    candidate = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=expected_plan,
        findings=expected_findings,
    )

    cases = [
        (
            replace(candidate, visible_body_hash="sha256:" + "0" * 64),
            PayloadValidationReasonCode.BODY_HASH_MISMATCH,
        ),
        (
            replace(candidate, findings_hash="sha256:" + "0" * 64),
            PayloadValidationReasonCode.FINDINGS_HASH_MISMATCH,
        ),
        (
            replace(candidate, redaction_status=RedactionStatus(False, 0, status=GateStatus.FAIL)),
            PayloadValidationReasonCode.REDACTION_NOT_PASSED,
        ),
    ]

    for payload, reason_code in cases:
        result = validate_candidate_issue_comment_payload(
            payload,
            expected_review_target=target(),
            expected_posting_plan=expected_plan,
            expected_findings=expected_findings,
        )
        assert result.status == GateStatus.FAIL
        assert result.reason_code == reason_code


def test_candidate_payload_validation_rebuilds_expected_payload_from_inputs() -> None:
    candidate = _candidate_payload()
    tampered_clone = replace(
        candidate,
        body=f"{candidate.body}\nUnexpected public text",
        visible_body_hash=visible_body_hash(f"{candidate.body}\nUnexpected public text"),
    )

    result = validate_candidate_issue_comment_payload(
        tampered_clone,
        expected_review_target=target(),
        expected_posting_plan=build_posting_plan(findings=[finding()]),
        expected_findings=(finding(),),
    )

    assert result.reason_code == PayloadValidationReasonCode.CANDIDATE_BINDING_MISMATCH


def test_final_payload_validation_passes_and_rejects_candidate_as_final() -> None:
    final_payload = _final_payload()

    result = validate_final_issue_comment_payload(final_payload)
    candidate_result = validate_final_issue_comment_payload(_candidate_payload())

    assert result.status == GateStatus.PASS
    assert result.payload_hash == final_payload.final_payload_hash
    assert result.target_hash == target().target_hash()
    assert candidate_result.reason_code == PayloadValidationReasonCode.NOT_FINAL_PAYLOAD


def test_final_payload_validation_rejects_marker_and_hash_mismatches() -> None:
    final_payload = _final_payload()
    not_final_line = replace(final_payload, body=f"{final_payload.marker_line}\nFinal body\n")
    extra_trailing_blank = replace(final_payload, body=f"{final_payload.body}\n")
    marker_mismatch = replace(final_payload, marker_run_id="other-run")
    body_hash_mismatch = replace(final_payload, visible_body_hash="sha256:" + "0" * 64)
    final_hash_mismatch = replace(final_payload, final_payload_hash="sha256:" + "1" * 64)
    target_hash_mismatch = replace(final_payload, marker_target_hash="sha256:" + "2" * 64)
    findings_mismatch = replace(final_payload, findings_hash="sha256:" + "3" * 64)
    duplicate_fingerprints = replace(final_payload, item_fingerprints=("fp-1", "fp-1"))

    assert validate_final_issue_comment_payload(not_final_line).reason_code == PayloadValidationReasonCode.MARKER_NOT_FINAL_LINE
    assert validate_final_issue_comment_payload(extra_trailing_blank).reason_code == PayloadValidationReasonCode.MARKER_NOT_FINAL_LINE
    assert validate_final_issue_comment_payload(marker_mismatch).reason_code == PayloadValidationReasonCode.MARKER_FIELD_MISMATCH
    assert validate_final_issue_comment_payload(body_hash_mismatch).reason_code == PayloadValidationReasonCode.BODY_HASH_MISMATCH
    assert validate_final_issue_comment_payload(final_hash_mismatch).reason_code == PayloadValidationReasonCode.FINAL_PAYLOAD_HASH_MISMATCH
    assert validate_final_issue_comment_payload(target_hash_mismatch).reason_code == PayloadValidationReasonCode.MARKER_FIELD_MISMATCH
    assert validate_final_issue_comment_payload(findings_mismatch).reason_code == PayloadValidationReasonCode.FINDINGS_HASH_MISMATCH
    assert validate_final_issue_comment_payload(duplicate_fingerprints).reason_code == PayloadValidationReasonCode.DUPLICATE_FINGERPRINTS


def test_issue_comment_request_validation_requires_exact_post_endpoint_and_body() -> None:
    final_payload = _final_payload()
    request = GitHubIssueCommentRequest(
        method="POST",
        endpoint="/repos/acme/widgets/issues/42/comments",
        body={"body": final_payload.body},
        payload=final_payload,
    )

    assert validate_issue_comment_request(
        request,
        expected_review_target=target(),
        expected_item_fingerprints=final_payload.item_fingerprints,
        expected_final_payload_hash=final_payload.final_payload_hash,
        expected_body=final_payload.body,
    ).status == GateStatus.PASS
    assert validate_issue_comment_request(
        replace(request, method="GET"),
        expected_review_target=target(),
        expected_item_fingerprints=final_payload.item_fingerprints,
        expected_final_payload_hash=final_payload.final_payload_hash,
        expected_body=final_payload.body,
    ).reason_code == PayloadValidationReasonCode.WRONG_METHOD
    assert validate_issue_comment_request(
        replace(request, endpoint="/repos/acme/widgets/issues/43/comments"),
        expected_review_target=target(),
        expected_item_fingerprints=final_payload.item_fingerprints,
        expected_final_payload_hash=final_payload.final_payload_hash,
        expected_body=final_payload.body,
    ).reason_code == PayloadValidationReasonCode.WRONG_ENDPOINT
    assert validate_issue_comment_request(
        replace(request, endpoint="/repos/acme/widgets/pulls/42/reviews"),
        expected_review_target=target(),
        expected_item_fingerprints=final_payload.item_fingerprints,
        expected_final_payload_hash=final_payload.final_payload_hash,
        expected_body=final_payload.body,
    ).reason_code == PayloadValidationReasonCode.FORMAL_REVIEW_PAYLOAD_REJECTED
    assert validate_issue_comment_request(
        replace(request, body={"body": final_payload.body, "event": "COMMENT"}),
        expected_review_target=target(),
        expected_item_fingerprints=final_payload.item_fingerprints,
        expected_final_payload_hash=final_payload.final_payload_hash,
        expected_body=final_payload.body,
    ).reason_code == PayloadValidationReasonCode.FORMAL_REVIEW_PAYLOAD_REJECTED
    assert validate_issue_comment_request(
        replace(request, body={"body": final_payload.body, "extra": "nope"}),
        expected_review_target=target(),
        expected_item_fingerprints=final_payload.item_fingerprints,
        expected_final_payload_hash=final_payload.final_payload_hash,
        expected_body=final_payload.body,
    ).reason_code == PayloadValidationReasonCode.WRONG_REQUEST_BODY
    drifted_payload = _final_payload(visible_body="Final ReviewGraph payload changed\n")
    assert validate_issue_comment_request(
        replace(request, payload=drifted_payload, body={"body": drifted_payload.body}),
        expected_review_target=target(),
        expected_item_fingerprints=final_payload.item_fingerprints,
        expected_final_payload_hash=final_payload.final_payload_hash,
        expected_body=final_payload.body,
    ).reason_code == PayloadValidationReasonCode.NOT_FINAL_PAYLOAD
    assert validate_issue_comment_request(
        request,
        expected_review_target=target(),
        expected_item_fingerprints=final_payload.item_fingerprints,
        expected_final_payload_hash="sha256:" + "0" * 64,
        expected_body=final_payload.body,
    ).reason_code == PayloadValidationReasonCode.NOT_FINAL_PAYLOAD


def test_request_validation_rejects_formal_review_payloads() -> None:
    for event in ("COMMENT", "APPROVE", "REQUEST_CHANGES"):
        result = reject_formal_review_payload(
            "/repos/acme/widgets/issues/42/comments",
            {"event": event, "body": "review"},
        )
        assert result.reason_code == PayloadValidationReasonCode.FORMAL_REVIEW_PAYLOAD_REJECTED
    assert (
        reject_formal_review_payload("/repos/acme/widgets/issues/42/labels", {"labels": ["bug"]}).reason_code
        == PayloadValidationReasonCode.WRONG_ENDPOINT
    )


def test_payload_validation_module_keeps_side_effect_import_boundary() -> None:
    tree = ast.parse(Path("src/reviewgraph/payload_validation.py").read_text())
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    forbidden = {
        "reviewgraph.approval",
        "reviewgraph.github",
        "reviewgraph.github_adapter",
        "reviewgraph.github_client",
        "reviewgraph.writer",
        "reviewgraph.finalization",
    }
    assert forbidden.isdisjoint(imported_modules)


def target() -> ReviewTarget:
    return ReviewTarget(
        owner_repo="acme/widgets",
        pr_number=42,
        base_sha="base123",
        head_sha="head456",
        merge_base_sha="merge789",
        diff_basis="merge_base",
    )


def finding() -> ClassifiedFinding:
    return ClassifiedFinding(
        id="finding-1",
        source_reviewer="correctness",
        source_stage="initial_triage",
        title="Cache miss returns stale data",
        body="The new branch returns stale data when the cache misses.",
        evidence="Changed line 12 returns stale data on misses.",
        path="src/cache.py",
        line=12,
        priority=1,
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        fingerprint="fp-1",
    )


def _candidate_payload() -> CandidateIssueCommentPayload:
    plan = build_posting_plan(findings=[finding()])
    return build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=[finding()],
    )


def _final_payload(
    fingerprints: tuple[str, ...] = ("fp-1",),
    visible_body: str = "Final ReviewGraph payload\n",
) -> FinalIssueCommentPayload:
    marker_line = _marker_line(target(), visible_body, fingerprints)
    body = f"{visible_body}{marker_line}\n"
    return FinalIssueCommentPayload(
        artifact_kind=ArtifactKind.ISSUE_COMMENT,
        review_target=target(),
        body=body,
        marker_line=marker_line,
        marker_run_id="run-1",
        marker_target_hash=target().target_hash(),
        marker_payload_hash=marker_payload_hash(visible_body),
        marker_findings_hash=findings_hash(fingerprints),
        visible_body_hash=visible_body_hash(body),
        final_payload_hash=final_payload_hash(body),
        findings_hash=findings_hash(fingerprints),
        item_fingerprints=fingerprints,
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )


def _marker_line(review_target: ReviewTarget, visible_body: str, fingerprints: tuple[str, ...]) -> str:
    return (
        "<!-- reviewgraph:v1 run_id=run-1 "
        f"target={review_target.target_hash()} "
        f"payload={marker_payload_hash(visible_body)} "
        f"findings={findings_hash(fingerprints)} -->"
    )
