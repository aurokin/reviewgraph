from __future__ import annotations

from dataclasses import dataclass

from reviewgraph.hashing import visible_body_hash
from reviewgraph.markers import build_final_issue_comment_payload
from reviewgraph.models import (
    ClassifiedFinding,
    FinalIssueCommentPayload,
    PostingPlanItem,
    RedactionStatus,
    ReviewTarget,
    ReviewVerdict,
)
from reviewgraph.redaction import redact_text


@dataclass(frozen=True)
class ApprovedFinalIssueCommentBuild:
    visible_body: str
    visible_body_hash: str
    payload: FinalIssueCommentPayload
    redaction_status: RedactionStatus


def build_approved_final_issue_comment(
    *,
    run_id: str,
    review_target: ReviewTarget,
    findings_by_id: dict[str, ClassifiedFinding],
    selected_items: tuple[PostingPlanItem, ...],
    local_verdict: ReviewVerdict | None,
    include_public_verdict: bool,
) -> ApprovedFinalIssueCommentBuild:
    if not isinstance(review_target, ReviewTarget):
        raise ValueError("approved final payload review_target must be a ReviewTarget")
    if not isinstance(findings_by_id, dict) or not all(
        isinstance(key, str) and isinstance(value, ClassifiedFinding)
        for key, value in findings_by_id.items()
    ):
        raise ValueError("approved final payload findings_by_id must map ids to findings")
    if not isinstance(selected_items, tuple) or not all(
        isinstance(item, PostingPlanItem) for item in selected_items
    ):
        raise ValueError("approved final payload selected_items must be posting plan items")
    raw_visible_body = _approved_visible_body(
        review_target=review_target,
        findings_by_id=findings_by_id,
        selected_items=selected_items,
        local_verdict=local_verdict,
        include_public_verdict=include_public_verdict,
    )
    redaction = redact_text(raw_visible_body)
    redaction_status = RedactionStatus(
        redacted=redaction.redacted,
        replacement_count=redaction.replacement_count,
        categories=redaction.categories,
    )
    visible_body = redaction.text.rstrip("\n") + "\n"
    payload = build_final_issue_comment_payload(
        run_id=run_id,
        review_target=review_target,
        visible_body=visible_body,
        item_fingerprints=tuple(findings_by_id[item.id].fingerprint for item in selected_items),
        redaction_status=redaction_status,
    )
    return ApprovedFinalIssueCommentBuild(
        visible_body=visible_body,
        visible_body_hash=visible_body_hash(visible_body),
        payload=payload,
        redaction_status=redaction_status,
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
