from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from reviewgraph.models import (
    ClarificationRequest,
    ClassifiedFinding,
    LocalNote,
    MemoryReference,
    RedactionStatus,
    ReviewTarget,
    ReviewVerdict,
    SelectedReviewer,
    SuggestedReply,
    SuppressedOutput,
    TruncationNotice,
)
from reviewgraph.posting import CandidateIssueCommentPayload, PostingPlan, PostingPlanItem
from reviewgraph.redaction import redact_text


class RenderError(ValueError):
    pass


@dataclass(frozen=True)
class RenderedReview:
    markdown: str
    json_data: dict[str, Any]
    redaction_status: RedactionStatus


def render_review(
    *,
    review_target: ReviewTarget,
    selected_reviewers: Iterable[SelectedReviewer],
    findings: Iterable[ClassifiedFinding],
    local_notes: Iterable[LocalNote] = (),
    clarification_requests: Iterable[ClarificationRequest] = (),
    suggested_replies: Iterable[SuggestedReply] = (),
    suppressed_outputs: Iterable[SuppressedOutput] = (),
    local_verdict: ReviewVerdict | None = None,
    posting_plan: PostingPlan | None = None,
    candidate_payload: CandidateIssueCommentPayload | None = None,
    memory_references: Iterable[MemoryReference] = (),
    truncation_notices: Iterable[TruncationNotice] = (),
) -> RenderedReview:
    context = _RenderContext()
    inputs = _RenderInputs(
        review_target=review_target,
        selected_reviewers=tuple(selected_reviewers),
        findings=tuple(findings),
        local_notes=tuple(local_notes),
        clarification_requests=tuple(clarification_requests),
        suggested_replies=tuple(suggested_replies),
        suppressed_outputs=tuple(suppressed_outputs),
        local_verdict=local_verdict,
        posting_plan=posting_plan,
        candidate_payload=candidate_payload,
        memory_references=tuple(memory_references),
        truncation_notices=tuple(truncation_notices),
    )
    json_data = render_json(inputs=inputs, context=context)
    markdown = render_markdown(inputs=inputs, context=context)
    json_data["redaction_status"] = context.status_dict()
    return RenderedReview(
        markdown=markdown,
        json_data=json_data,
        redaction_status=context.status(),
    )


def render_json(*, inputs: "_RenderInputs", context: "_RenderContext | None" = None) -> dict[str, Any]:
    context = context or _RenderContext()
    candidate_preview = _candidate_payload_preview(
        inputs.candidate_payload,
        inputs.memory_references,
        context,
    )
    return {
        "review_target": inputs.review_target.to_ordered_dict(),
        "selected_reviewers": [
            {
                "name": reviewer.name,
                "stage": reviewer.stage,
                "reasons": [context.redact(reason) for reason in reviewer.reasons],
            }
            for reviewer in inputs.selected_reviewers
        ],
        "classified_output": {
            "postable_findings": [_finding_json(finding, context) for finding in inputs.findings],
            "local_notes": [_local_note_json(note, context) for note in inputs.local_notes],
            "clarification_requests": [
                _clarification_json(request, context) for request in inputs.clarification_requests
            ],
            "suggested_replies": [_suggested_reply_json(reply, context) for reply in inputs.suggested_replies],
            "suppressed": [_suppressed_json(output, context) for output in inputs.suppressed_outputs],
            "suppressed_count": len(inputs.suppressed_outputs),
        },
        "local_verdict": inputs.local_verdict.value if inputs.local_verdict is not None else None,
        "posting_plan": _posting_plan_json(inputs.posting_plan, context),
        "memory": [_memory_json(memory, context) for memory in inputs.memory_references],
        "truncation": [_truncation_json(notice, context) for notice in inputs.truncation_notices],
        "candidate_payload_preview": candidate_preview,
        "redaction_status": context.status_dict(),
    }


def render_markdown(*, inputs: "_RenderInputs", context: "_RenderContext | None" = None) -> str:
    context = context or _RenderContext()
    lines: list[str] = [
        "# ReviewGraph Dry Run",
        "",
        "## Target",
        f"- PR: {inputs.review_target.owner_repo}#{inputs.review_target.pr_number}",
        f"- Head: {inputs.review_target.head_sha}",
        "",
        "## Local Verdict",
        f"- Value: {_private_verdict_label(inputs.local_verdict)}",
        "",
        "## Selected Reviewers",
    ]
    lines.extend(
        f"- {reviewer.name} ({reviewer.stage}): {', '.join(context.redact(reason) for reason in reviewer.reasons)}"
        for reviewer in inputs.selected_reviewers
    )
    lines.extend(["", "## Postable Findings"])
    if inputs.findings:
        lines.extend(
            f"- P{finding.priority} {context.redact(finding.title)} ({finding.path}:{finding.line})"
            f" - {context.redact(finding.body)}"
            for finding in inputs.findings
        )
    else:
        lines.append("- None")

    lines.extend(["", "## Local Notes"])
    lines.extend(_markdown_items(((note.title, note.body) for note in inputs.local_notes), context) or ["- None"])

    lines.extend(["", "## Clarification Requests"])
    lines.extend(
        _markdown_items(
            ((request.question, request.why_it_matters) for request in inputs.clarification_requests),
            context,
        )
        or ["- None"]
    )

    lines.extend(["", "## Suggested Replies"])
    lines.extend(
        f"- {reply.id}: {context.redact(reply.proposed_body)}" for reply in inputs.suggested_replies
    )
    if not inputs.suggested_replies:
        lines.append("- None")

    lines.extend(["", "## Suppressed Outputs", f"- Count: {len(inputs.suppressed_outputs)}"])
    for output in inputs.suppressed_outputs:
        lines.append(f"- {output.id}: {context.redact(output.reason)}")

    lines.extend(["", "## Memory"])
    for memory in inputs.memory_references:
        lines.append(
            f"- {memory.id}: trust={memory.trust_label}, resolved={memory.resolved_status}, source={memory.source_type}"
        )
    if not inputs.memory_references:
        lines.append("- None")

    lines.extend(["", "## Truncation"])
    if inputs.truncation_notices:
        for notice in inputs.truncation_notices:
            lines.append(
                f"- {notice.resource}: truncated={str(notice.truncated).lower()} - {context.redact(notice.note)}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Posting Plan"])
    if inputs.posting_plan is not None:
        for item in inputs.posting_plan.items:
            lines.append(f"- {item.id}: {item.destination.value}, public={str(item.public_payload_eligible).lower()}")
    else:
        lines.append("- None")

    preview = _candidate_payload_preview(inputs.candidate_payload, inputs.memory_references, context)
    lines.extend(["", "## Candidate Payload Preview"])
    if preview is None:
        lines.append("- None")
    else:
        lines.append(f"- Kind: {preview['artifact_kind']}")
        lines.append(f"- Visible body hash: {preview['visible_body_hash']}")
        lines.append(f"- Full body hash: {preview['full_body_hash']}")
        lines.append(f"- Findings hash: {preview['findings_hash']}")
        lines.append("- Body:")
        lines.append("```text")
        lines.append(str(preview["body"]).rstrip("\n"))
        lines.append("```")

    return "\n".join(lines) + "\n"


def _private_verdict_label(verdict: ReviewVerdict | None) -> str:
    if verdict is None:
        return "none"
    if verdict == ReviewVerdict.REQUEST_CHANGES:
        return "private local blocking recommendation"
    return verdict.value


def _markdown_items(items: Iterable[tuple[str, str]], context: "_RenderContext") -> list[str]:
    return [f"- {context.redact(title)}: {context.redact(body)}" for title, body in items]


def _candidate_payload_preview(
    candidate_payload: CandidateIssueCommentPayload | None,
    memory_references: tuple[MemoryReference, ...],
    context: "_RenderContext",
) -> dict[str, Any] | None:
    if candidate_payload is None:
        return None
    body = context.redact(candidate_payload.body)
    for memory in memory_references:
        if memory.trust_label == "untrusted" and memory.body and memory.body in body:
            raise RenderError(f"candidate payload contains untrusted memory body: {memory.id}")
    return {
        "artifact_kind": candidate_payload.artifact_kind.value,
        "review_target": candidate_payload.review_target.to_ordered_dict(),
        "body": body,
        "visible_body_hash": candidate_payload.visible_body_hash,
        "full_body_hash": candidate_payload.full_body_hash,
        "findings_hash": candidate_payload.findings_hash,
        "item_fingerprints": list(candidate_payload.item_fingerprints),
        "redaction_status": {
            "redacted": candidate_payload.redaction_status.redacted,
            "replacement_count": candidate_payload.redaction_status.replacement_count,
            "categories": list(candidate_payload.redaction_status.categories),
        },
    }


def _finding_json(finding: ClassifiedFinding, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": finding.id,
        "source_reviewer": finding.source_reviewer,
        "source_stage": finding.source_stage,
        "classification": finding.classification.value,
        "priority": finding.priority,
        "severity": finding.severity.value,
        "confidence": finding.confidence.value,
        "title": context.redact(finding.title),
        "body": context.redact(finding.body),
        "evidence": context.redact(finding.evidence),
        "path": finding.path,
        "line": finding.line,
        "fingerprint": finding.fingerprint,
    }


def _local_note_json(note: LocalNote, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": note.id,
        "classification": note.classification.value,
        "title": context.redact(note.title),
        "body": context.redact(note.body),
        "evidence": context.redact(note.evidence),
    }


def _clarification_json(request: ClarificationRequest, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": request.id,
        "classification": request.classification.value,
        "reviewer": request.reviewer,
        "question": context.redact(request.question),
        "why_it_matters": context.redact(request.why_it_matters),
        "blocks_verdict": request.blocks_verdict,
    }


def _suggested_reply_json(reply: SuggestedReply, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": reply.id,
        "classification": reply.classification.value,
        "source_comment_id": reply.source_comment_id,
        "proposed_body": context.redact(reply.proposed_body),
    }


def _suppressed_json(output: SuppressedOutput, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": output.id,
        "classification": output.classification.value,
        "reason": context.redact(output.reason),
    }


def _posting_plan_json(posting_plan: PostingPlan | None, context: "_RenderContext") -> dict[str, Any] | None:
    if posting_plan is None:
        return None
    return {"items": [_posting_plan_item_json(item, context) for item in posting_plan.items]}


def _posting_plan_item_json(item: PostingPlanItem, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": item.id,
        "source_classification": item.source_classification,
        "destination": item.destination.value,
        "public_payload_eligible": item.public_payload_eligible,
        "fingerprint": item.fingerprint,
        "body": context.redact(item.body) if item.body is not None else None,
    }


def _memory_json(memory: MemoryReference, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": memory.id,
        "trust_label": memory.trust_label,
        "resolved_status": memory.resolved_status,
        "source_type": memory.source_type,
        "body": context.redact(memory.body) if memory.body and memory.trust_label != "untrusted" else None,
    }


def _truncation_json(notice: TruncationNotice, context: "_RenderContext") -> dict[str, Any]:
    return {
        "resource": notice.resource,
        "truncated": notice.truncated,
        "note": context.redact(notice.note),
        "original_count": notice.original_count,
        "retained_count": notice.retained_count,
        "original_bytes": notice.original_bytes,
        "retained_bytes": notice.retained_bytes,
    }


@dataclass(frozen=True)
class _RenderInputs:
    review_target: ReviewTarget
    selected_reviewers: tuple[SelectedReviewer, ...]
    findings: tuple[ClassifiedFinding, ...]
    local_notes: tuple[LocalNote, ...]
    clarification_requests: tuple[ClarificationRequest, ...]
    suggested_replies: tuple[SuggestedReply, ...]
    suppressed_outputs: tuple[SuppressedOutput, ...]
    local_verdict: ReviewVerdict | None
    posting_plan: PostingPlan | None
    candidate_payload: CandidateIssueCommentPayload | None
    memory_references: tuple[MemoryReference, ...]
    truncation_notices: tuple[TruncationNotice, ...]


class _RenderContext:
    def __init__(self) -> None:
        self._replacement_count = 0
        self._categories: list[str] = []

    def redact(self, value: str) -> str:
        result = redact_text(value)
        self._replacement_count += result.replacement_count
        self._categories.extend(result.categories)
        return result.text

    def status(self) -> RedactionStatus:
        return RedactionStatus(
            redacted=self._replacement_count > 0,
            replacement_count=self._replacement_count,
            categories=tuple(dict.fromkeys(self._categories)),
        )

    def status_dict(self) -> dict[str, Any]:
        status = self.status()
        return {
            "redacted": status.redacted,
            "replacement_count": status.replacement_count,
            "categories": list(status.categories),
        }
