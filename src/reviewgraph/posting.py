from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from inspect import Parameter, signature
from typing import Iterable

from reviewgraph.models import (
    ArtifactKind,
    ClarificationRequest,
    ClassifiedFinding,
    LocalNote,
    RedactionStatus,
    ReviewTarget,
    ReviewVerdict,
    SuggestedReply,
    SuppressedOutput,
)
from reviewgraph.redaction import redact_text


class PostingDestination(StrEnum):
    LOCAL_ONLY = "local_only"
    TOP_LEVEL_SUMMARY_ITEM = "top_level_summary_item"
    REVIEW_BODY_ITEM = "review_body_item"
    INLINE_CANDIDATE = "inline_candidate"
    SUGGESTED_REPLY = "suggested_reply"


class PostingPlanError(ValueError):
    pass


@dataclass(frozen=True)
class PostingPlanItem:
    id: str
    source_classification: str
    destination: PostingDestination
    public_payload_eligible: bool
    fingerprint: str | None = None
    body: str | None = None


@dataclass(frozen=True)
class PostingPlan:
    items: tuple[PostingPlanItem, ...]

    @property
    def public_payload_items(self) -> tuple[PostingPlanItem, ...]:
        return tuple(item for item in self.items if item.public_payload_eligible)


@dataclass(frozen=True)
class CandidateIssueCommentPayload:
    artifact_kind: ArtifactKind
    review_target: ReviewTarget
    body: str
    visible_body_hash: str
    full_body_hash: str
    findings_hash: str
    item_fingerprints: tuple[str, ...]
    redaction_status: RedactionStatus


def canonical_visible_body(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.rstrip("\n") + "\n"


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def visible_body_hash(text: str) -> str:
    return sha256_text(canonical_visible_body(text))


def full_body_hash(full_body: str) -> str:
    return sha256_text(full_body)


def canonical_json_hash(data: object) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_text(encoded)


def findings_hash(fingerprints: Iterable[str]) -> str:
    ordered = sorted(fingerprints)
    if len(set(ordered)) != len(ordered):
        raise PostingPlanError("duplicate finding fingerprints are not allowed")
    return canonical_json_hash(ordered)


def validate_mvp_artifact_kind(kind: str | ArtifactKind) -> ArtifactKind:
    if kind == ArtifactKind.ISSUE_COMMENT or kind == ArtifactKind.ISSUE_COMMENT.value:
        return ArtifactKind.ISSUE_COMMENT
    raise PostingPlanError("MVP supports only top-level issue_comment payloads")


def build_posting_plan(
    *,
    findings: Iterable[ClassifiedFinding],
    local_notes: Iterable[LocalNote] = (),
    suggested_replies: Iterable[SuggestedReply] = (),
    clarification_requests: Iterable[ClarificationRequest] = (),
    suppressed_outputs: Iterable[SuppressedOutput] = (),
    inline_candidate_ids: set[str] | None = None,
    include_summary: bool = False,
) -> PostingPlan:
    inline_candidate_ids = inline_candidate_ids or set()
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
            if finding.diff_anchor is None or not finding.diff_anchor.overlaps_changed_target:
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
    findings_by_id = {finding.id: finding for finding in findings}
    public_items = posting_plan.public_payload_items
    missing = [item.id for item in public_items if item.id != "summary" and item.id not in findings_by_id]
    if missing:
        raise PostingPlanError(f"public payload item has no matching finding: {', '.join(missing)}")

    body_parts = [
        "ReviewGraph dry-run candidate",
        f"Target: {review_target.owner_repo}#{review_target.pr_number}",
        f"Head: {review_target.head_sha}",
        "",
    ]
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
        full_body_hash=full_body_hash(visible_body),
        findings_hash=findings_hash(item_fingerprints),
        item_fingerprints=item_fingerprints,
        redaction_status=RedactionStatus(
            redacted=redaction.redacted,
            replacement_count=redaction.replacement_count,
            categories=redaction.categories,
        ),
    )


def assert_builder_signatures_are_pure() -> None:
    forbidden_names = {"writer", "client", "transport", "github", "approval", "finalization"}
    for func in (build_posting_plan, build_candidate_issue_comment_payload):
        for parameter in signature(func).parameters.values():
            if parameter.kind in {Parameter.VAR_KEYWORD, Parameter.VAR_POSITIONAL}:
                raise AssertionError(f"{func.__name__} must not accept variadic parameters")
            if parameter.name.lower() in forbidden_names:
                raise AssertionError(f"{func.__name__} accepts forbidden parameter {parameter.name!r}")
