from __future__ import annotations

from inspect import Parameter, signature
from typing import Iterable

from reviewgraph.hashing import (
    canonical_json_hash,
    canonical_text_body,
    canonical_visible_body as canonical_hash_visible_body,
    final_payload_hash,
    findings_hash as canonical_findings_hash,
    is_exact_reviewgraph_v1_marker_line,
    marker_payload_hash,
    sha256_text,
    visible_body_hash as canonical_visible_body_hash,
)
from reviewgraph.models import (
    ArtifactKind,
    CandidateIssueCommentPayload,
    ClarificationRequest,
    ClassifiedFinding,
    LocalNote,
    OutputClassification,
    PostingDestination,
    PostingPlan,
    PostingPlanItem,
    RedactionStatus,
    ReviewTarget,
    ReviewVerdict,
    SuggestedReply,
    SuppressedOutput,
)
from reviewgraph.redaction import redact_text


class PostingPlanError(ValueError):
    pass


MARKER_PREFIX = "<!-- reviewgraph:"
MARKER_SUFFIX = " -->"


def canonical_visible_body(text: str) -> str:
    return canonical_hash_visible_body(text)


def _is_marker_line(line: str) -> bool:
    return is_exact_reviewgraph_v1_marker_line(line)


def canonical_full_body(text: str) -> str:
    return canonical_text_body(text)


def visible_body_hash(text: str) -> str:
    return canonical_visible_body_hash(text)


def full_body_hash(full_body: str) -> str:
    return final_payload_hash(full_body)


def findings_hash(fingerprints: Iterable[str]) -> str:
    try:
        return canonical_findings_hash(fingerprints)
    except ValueError as exc:
        raise PostingPlanError(str(exc)) from exc


def validate_mvp_artifact_kind(kind: str | ArtifactKind) -> ArtifactKind:
    if kind == ArtifactKind.ISSUE_COMMENT or kind == ArtifactKind.ISSUE_COMMENT.value:
        return ArtifactKind.ISSUE_COMMENT
    raise PostingPlanError("MVP supports only top-level issue_comment payloads")


def build_posting_plan(
    *,
    findings: Iterable[ClassifiedFinding],
    review_target: ReviewTarget | None = None,
    local_notes: Iterable[LocalNote] = (),
    suggested_replies: Iterable[SuggestedReply] = (),
    clarification_requests: Iterable[ClarificationRequest] = (),
    suppressed_outputs: Iterable[SuppressedOutput] = (),
    inline_candidate_ids: set[str] | None = None,
    include_summary: bool = False,
) -> PostingPlan:
    inline_candidate_ids = inline_candidate_ids or set()
    matched_inline_ids: set[str] = set()
    items: list[PostingPlanItem] = []

    if include_summary:
        items.append(
            PostingPlanItem(
                id="summary",
                source_classification="summary",
                destination=PostingDestination.TOP_LEVEL_SUMMARY_ITEM,
                public_payload_eligible=True,
            )
        )

    for finding in findings:
        if finding.id in inline_candidate_ids:
            matched_inline_ids.add(finding.id)
            if finding.diff_anchor is None:
                raise PostingPlanError("inline candidates require a diff anchor overlapping changed target code")
            if review_target is None:
                raise PostingPlanError("inline candidates require a review target")
            if not finding.diff_anchor.validates_finding_location(
                path=finding.path,
                line=finding.line,
                line_end=finding.line_end,
                target_commit_sha=review_target.head_sha,
            ):
                raise PostingPlanError("inline candidates require a diff anchor overlapping changed target code")
            destination = PostingDestination.INLINE_CANDIDATE
            public_payload_eligible = False
        else:
            destination = PostingDestination.REVIEW_BODY_ITEM
            public_payload_eligible = True
        items.append(
            PostingPlanItem(
                id=finding.id,
                source_classification=finding.classification.value,
                destination=destination,
                public_payload_eligible=public_payload_eligible,
                fingerprint=finding.fingerprint,
                body=finding.body,
            )
        )

    for note in local_notes:
        items.append(_local_item(note.id, note.classification.value, note.body))
    for reply in suggested_replies:
        items.append(
            PostingPlanItem(
                id=reply.id,
                source_classification=reply.classification.value,
                destination=PostingDestination.SUGGESTED_REPLY,
                public_payload_eligible=False,
                body=reply.proposed_body,
            )
        )
    for request in clarification_requests:
        items.append(_local_item(request.id, request.classification.value, request.question))
    for output in suppressed_outputs:
        items.append(_local_item(output.id, output.classification.value, output.reason))

    unknown_inline_ids = inline_candidate_ids - matched_inline_ids
    if unknown_inline_ids:
        raise PostingPlanError(f"unknown inline candidate ids: {', '.join(sorted(unknown_inline_ids))}")

    return PostingPlan(items=tuple(items))


def _local_item(item_id: str, source_classification: str, body: str) -> PostingPlanItem:
    return PostingPlanItem(
        id=item_id,
        source_classification=source_classification,
        destination=PostingDestination.LOCAL_ONLY,
        public_payload_eligible=False,
        body=body,
    )


def build_candidate_issue_comment_payload(
    *,
    review_target: ReviewTarget,
    posting_plan: PostingPlan,
    findings: Iterable[ClassifiedFinding],
    local_verdict: ReviewVerdict | None = None,
    include_public_verdict: bool = False,
    artifact_kind: str | ArtifactKind = ArtifactKind.ISSUE_COMMENT,
) -> CandidateIssueCommentPayload:
    kind = validate_mvp_artifact_kind(artifact_kind)
    findings_by_id: dict[str, ClassifiedFinding] = {}
    for finding in findings:
        if finding.id in findings_by_id:
            raise PostingPlanError(f"duplicate finding id: {finding.id}")
        findings_by_id[finding.id] = finding
    public_items = posting_plan.public_payload_items
    _validate_public_payload_items(public_items)
    missing = [item.id for item in public_items if item.id != "summary" and item.id not in findings_by_id]
    if missing:
        raise PostingPlanError(f"public payload item has no matching finding: {', '.join(missing)}")

    body_parts = [
        "ReviewGraph dry-run candidate",
        f"Target: {review_target.owner_repo}#{review_target.pr_number}",
        f"Head: {review_target.head_sha}",
        "",
    ]
    if include_public_verdict and local_verdict == ReviewVerdict.REQUEST_CHANGES:
        raise PostingPlanError("request_changes verdict text is not public in MVP candidate payloads")
    if include_public_verdict and local_verdict is not None:
        body_parts.extend([f"Local verdict: {local_verdict.value}", ""])

    finding_fingerprints: list[str] = []
    if public_items:
        body_parts.append("Postable findings:")
    for item in public_items:
        if item.id == "summary":
            body_parts.append("- Summary item reserved for renderer output.")
            continue
        finding = findings_by_id[item.id]
        if item.fingerprint != finding.fingerprint:
            raise PostingPlanError(f"posting plan fingerprint mismatch for {item.id}")
        finding_fingerprints.append(finding.fingerprint)
        body_parts.append(
            f"- P{finding.priority} {finding.title}: {finding.body} ({finding.path}:{finding.line})"
        )

    if not public_items:
        body_parts.append("Postable findings: none.")

    raw_body = "\n".join(body_parts)
    redaction = redact_text(raw_body)
    visible_body = canonical_visible_body(redaction.text)
    item_fingerprints = tuple(sorted(finding_fingerprints))
    return CandidateIssueCommentPayload(
        artifact_kind=kind,
        review_target=review_target,
        body=visible_body,
        visible_body_hash=visible_body_hash(visible_body),
        findings_hash=findings_hash(item_fingerprints),
        item_fingerprints=item_fingerprints,
        redaction_status=RedactionStatus(
            redacted=redaction.redacted,
            replacement_count=redaction.replacement_count,
            categories=redaction.categories,
        ),
    )


def _validate_public_payload_items(public_items: tuple[PostingPlanItem, ...]) -> None:
    for item in public_items:
        if item.id == "summary":
            if item.destination != PostingDestination.TOP_LEVEL_SUMMARY_ITEM:
                raise PostingPlanError("summary public item must use top_level_summary_item destination")
            continue
        if item.destination != PostingDestination.REVIEW_BODY_ITEM:
            raise PostingPlanError("only review_body_item findings can enter public payload items")
        if item.source_classification != OutputClassification.POSTABLE_FINDING.value:
            raise PostingPlanError("only postable findings can enter public payload items")
        if not item.fingerprint:
            raise PostingPlanError("public payload findings require fingerprints")


def assert_builder_signatures_are_pure() -> None:
    forbidden_names = {"writer", "client", "transport", "github", "approval", "finalization"}
    for func in (build_posting_plan, build_candidate_issue_comment_payload):
        for parameter in signature(func).parameters.values():
            if parameter.kind in {Parameter.VAR_KEYWORD, Parameter.VAR_POSITIONAL}:
                raise AssertionError(f"{func.__name__} must not accept variadic parameters")
            if parameter.name.lower() in forbidden_names:
                raise AssertionError(f"{func.__name__} accepts forbidden parameter {parameter.name!r}")
