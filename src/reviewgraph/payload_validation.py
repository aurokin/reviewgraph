from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from reviewgraph.hashing import (
    canonical_text_body,
    final_payload_hash,
    findings_hash,
    is_exact_reviewgraph_v1_marker_line,
    marker_payload_hash,
    visible_body_hash,
)
from reviewgraph.models import (
    ArtifactKind,
    CandidateIssueCommentPayload,
    ClassifiedFinding,
    FinalIssueCommentPayload,
    GateStatus,
    GitHubIssueCommentRequest,
    PayloadValidationReasonCode,
    PayloadValidationResult,
    PostingPlan,
    ReviewTarget,
    ReviewVerdict,
)
from reviewgraph.posting import PostingPlanError, build_candidate_issue_comment_payload


_MARKER_RE = re.compile(
    r"^<!-- reviewgraph:v1 "
    r"run_id=(?P<run_id>[A-Za-z0-9][A-Za-z0-9._:/#-]{0,127}) "
    r"target=(?P<target>sha256:[0-9a-f]{64}) "
    r"payload=(?P<payload>sha256:[0-9a-f]{64}) "
    r"findings=(?P<findings>sha256:[0-9a-f]{64}) -->$"
)


def validate_candidate_issue_comment_payload(
    payload: object,
    *,
    expected_review_target: ReviewTarget,
    expected_posting_plan: PostingPlan,
    expected_findings: Iterable[ClassifiedFinding],
    expected_local_verdict: ReviewVerdict | None = None,
    expected_include_public_verdict: bool = False,
) -> PayloadValidationResult:
    if not isinstance(payload, CandidateIssueCommentPayload):
        return _fail(PayloadValidationReasonCode.CANDIDATE_BINDING_MISMATCH, "payload is not a candidate issue comment")
    try:
        expected_payload = build_candidate_issue_comment_payload(
            review_target=expected_review_target,
            posting_plan=expected_posting_plan,
            findings=tuple(expected_findings),
            local_verdict=expected_local_verdict,
            include_public_verdict=expected_include_public_verdict,
        )
    except PostingPlanError as exc:
        return _fail(PayloadValidationReasonCode.CANDIDATE_BINDING_MISMATCH, str(exc))
    if payload.artifact_kind != ArtifactKind.ISSUE_COMMENT:
        return _fail(PayloadValidationReasonCode.WRONG_ARTIFACT_KIND, "candidate payload must be issue_comment")
    if payload.redaction_status.status != GateStatus.PASS:
        return _fail(PayloadValidationReasonCode.REDACTION_NOT_PASSED, "candidate payload redaction did not pass")
    if _contains_marker_line(payload.body):
        return _fail(PayloadValidationReasonCode.CANDIDATE_CONTAINS_MARKER, "candidate payload must not contain marker")
    if payload.review_target != expected_review_target:
        return _fail(PayloadValidationReasonCode.CANDIDATE_BINDING_MISMATCH, "candidate target does not match expected target")
    if payload.visible_body_hash != visible_body_hash(payload.body):
        return _fail(PayloadValidationReasonCode.BODY_HASH_MISMATCH, "candidate visible body hash does not match body")
    expected_fingerprints = expected_payload.item_fingerprints
    if tuple(sorted(payload.item_fingerprints)) != expected_fingerprints:
        return _fail(PayloadValidationReasonCode.CANDIDATE_BINDING_MISMATCH, "candidate fingerprints do not match expected fingerprints")
    if payload.item_fingerprints != expected_fingerprints:
        return _fail(PayloadValidationReasonCode.CANDIDATE_BINDING_MISMATCH, "candidate fingerprints must be sorted")
    expected_findings_hash = findings_hash(expected_fingerprints)
    if payload.findings_hash != expected_findings_hash:
        return _fail(PayloadValidationReasonCode.FINDINGS_HASH_MISMATCH, "candidate findings hash does not match fingerprints")
    if payload != expected_payload:
        return _fail(PayloadValidationReasonCode.CANDIDATE_BINDING_MISMATCH, "candidate payload does not match expected payload")
    return _pass(payload_hash=payload.visible_body_hash, target_hash=payload.review_target.target_hash())


def validate_final_issue_comment_payload(payload: object) -> PayloadValidationResult:
    if not isinstance(payload, FinalIssueCommentPayload):
        return _fail(PayloadValidationReasonCode.NOT_FINAL_PAYLOAD, "payload is not a final issue comment")
    if payload.artifact_kind != ArtifactKind.ISSUE_COMMENT:
        return _fail(PayloadValidationReasonCode.WRONG_ARTIFACT_KIND, "final payload must be issue_comment")
    if payload.redaction_status.status != GateStatus.PASS:
        return _fail(PayloadValidationReasonCode.REDACTION_NOT_PASSED, "final payload redaction did not pass")
    marker_validation = _validate_marker(payload)
    if marker_validation is not None:
        return marker_validation
    if payload.visible_body_hash != visible_body_hash(payload.body):
        return _fail(PayloadValidationReasonCode.BODY_HASH_MISMATCH, "final visible body hash does not match body")
    try:
        computed_findings_hash = findings_hash(payload.item_fingerprints)
    except ValueError:
        return _fail(PayloadValidationReasonCode.DUPLICATE_FINGERPRINTS, "final payload fingerprints contain duplicates")
    if payload.findings_hash != computed_findings_hash or payload.marker_findings_hash != computed_findings_hash:
        return _fail(PayloadValidationReasonCode.FINDINGS_HASH_MISMATCH, "final findings hash does not match fingerprints")
    if payload.final_payload_hash != final_payload_hash(payload.body):
        return _fail(PayloadValidationReasonCode.FINAL_PAYLOAD_HASH_MISMATCH, "final payload hash does not match body")
    target_hash = payload.review_target.target_hash()
    if payload.marker_target_hash != target_hash:
        return _fail(PayloadValidationReasonCode.TARGET_HASH_MISMATCH, "marker target hash does not match review target")
    return _pass(payload_hash=payload.final_payload_hash, target_hash=target_hash)


def validate_issue_comment_request(
    request: object,
    *,
    expected_review_target: ReviewTarget,
    expected_item_fingerprints: Iterable[str],
    expected_final_payload_hash: str,
    expected_body: str,
) -> PayloadValidationResult:
    if not isinstance(request, GitHubIssueCommentRequest):
        return _fail(PayloadValidationReasonCode.NOT_FINAL_PAYLOAD, "request must carry a final issue comment payload")
    final_validation = validate_final_issue_comment_payload(request.payload)
    if final_validation.status != GateStatus.PASS:
        return final_validation
    expected_fingerprints = tuple(sorted(expected_item_fingerprints))
    if len(set(expected_fingerprints)) != len(expected_fingerprints):
        return _fail(PayloadValidationReasonCode.DUPLICATE_FINGERPRINTS, "expected fingerprints contain duplicates")
    if request.payload.review_target != expected_review_target:
        return _fail(PayloadValidationReasonCode.REQUEST_TARGET_MISMATCH, "request payload target does not match expected target")
    if request.payload.item_fingerprints != expected_fingerprints:
        return _fail(PayloadValidationReasonCode.REQUEST_TARGET_MISMATCH, "request fingerprints do not match expected fingerprints")
    if request.payload.final_payload_hash != expected_final_payload_hash or request.payload.body != expected_body:
        return _fail(PayloadValidationReasonCode.NOT_FINAL_PAYLOAD, "request payload does not match approved final payload proof")
    if request.method != "POST":
        return _fail(PayloadValidationReasonCode.WRONG_METHOD, "issue comment requests must use POST")
    expected_endpoint = _issue_comment_endpoint(expected_review_target)
    if _is_formal_review_endpoint(request.endpoint):
        return _fail(PayloadValidationReasonCode.FORMAL_REVIEW_PAYLOAD_REJECTED, "formal PR review endpoint is deferred")
    if request.endpoint != expected_endpoint:
        return _fail(PayloadValidationReasonCode.WRONG_ENDPOINT, "request endpoint is not the issue comment endpoint")
    if _is_formal_review_body(request.body):
        return _fail(PayloadValidationReasonCode.FORMAL_REVIEW_PAYLOAD_REJECTED, "formal PR review payload is deferred")
    if dict(request.body) != {"body": expected_body}:
        return _fail(PayloadValidationReasonCode.WRONG_REQUEST_BODY, "issue comment request body must contain only final body")
    return _pass(payload_hash=request.payload.final_payload_hash, target_hash=expected_review_target.target_hash())


def reject_formal_review_payload(endpoint: str, body: Mapping[str, object]) -> PayloadValidationResult:
    if _is_formal_review_endpoint(endpoint):
        return _fail(PayloadValidationReasonCode.FORMAL_REVIEW_PAYLOAD_REJECTED, "formal PR review endpoint is deferred")
    if _is_formal_review_body(body):
        return _fail(PayloadValidationReasonCode.FORMAL_REVIEW_PAYLOAD_REJECTED, "formal PR review payload is deferred")
    return _fail(PayloadValidationReasonCode.WRONG_ENDPOINT, "only top-level issue comment requests can pass payload validation")


def _validate_marker(payload: FinalIssueCommentPayload) -> PayloadValidationResult | None:
    canonical = canonical_text_body(payload.body)
    lines = canonical.split("\n")
    final_line = lines[-2] if len(lines) >= 2 else ""
    marker_lines = [line for line in lines if is_exact_reviewgraph_v1_marker_line(line)]
    if final_line != payload.marker_line or not is_exact_reviewgraph_v1_marker_line(payload.marker_line):
        return _fail(PayloadValidationReasonCode.MARKER_NOT_FINAL_LINE, "marker must be the final body line")
    if marker_lines != [payload.marker_line]:
        return _fail(PayloadValidationReasonCode.MARKER_NOT_FINAL_LINE, "marker must appear exactly once as final line")
    marker = _MARKER_RE.fullmatch(payload.marker_line)
    if marker is None:
        return _fail(PayloadValidationReasonCode.MARKER_FIELD_MISMATCH, "marker line does not match v1 grammar")
    if marker.group("run_id") != payload.marker_run_id:
        return _fail(PayloadValidationReasonCode.MARKER_FIELD_MISMATCH, "marker run_id does not match payload")
    if marker.group("target") != payload.marker_target_hash:
        return _fail(PayloadValidationReasonCode.MARKER_FIELD_MISMATCH, "marker target hash does not match payload")
    if marker.group("payload") != payload.marker_payload_hash:
        return _fail(PayloadValidationReasonCode.MARKER_FIELD_MISMATCH, "marker payload hash does not match payload")
    if marker.group("findings") != payload.marker_findings_hash:
        return _fail(PayloadValidationReasonCode.MARKER_FIELD_MISMATCH, "marker findings hash does not match payload")
    marker_payload = marker_payload_hash(payload.body)
    if payload.marker_payload_hash != marker_payload:
        return _fail(PayloadValidationReasonCode.BODY_HASH_MISMATCH, "marker payload hash does not match visible body")
    if payload.visible_body_hash != payload.marker_payload_hash:
        return _fail(PayloadValidationReasonCode.BODY_HASH_MISMATCH, "visible body hash must match marker payload hash")
    return None


def _contains_marker_line(body: str) -> bool:
    return any(is_exact_reviewgraph_v1_marker_line(line) for line in canonical_text_body(body).split("\n"))


def _issue_comment_endpoint(target: ReviewTarget) -> str:
    owner, repo = target.owner_repo.split("/", 1)
    return f"/repos/{owner}/{repo}/issues/{target.pr_number}/comments"


def _is_formal_review_endpoint(endpoint: str) -> bool:
    return re.fullmatch(r"/repos/[^/]+/[^/]+/pulls/\d+/reviews", endpoint) is not None


def _is_formal_review_body(body: Mapping[str, object]) -> bool:
    return "event" in body or "comments" in body or "commit_id" in body


def _pass(*, payload_hash: str, target_hash: str) -> PayloadValidationResult:
    return PayloadValidationResult(status=GateStatus.PASS, payload_hash=payload_hash, target_hash=target_hash)


def _fail(code: PayloadValidationReasonCode, reason: str) -> PayloadValidationResult:
    return PayloadValidationResult(
        status=GateStatus.FAIL,
        payload_hash=None,
        target_hash=None,
        reason_code=code,
        reason=reason,
    )
