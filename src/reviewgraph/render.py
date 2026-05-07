from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from reviewgraph.memory_provenance import memory_body_overlaps_text
from reviewgraph.models import (
    ClarificationRequest,
    ClassifiedFinding,
    ContextBudget,
    LocalNote,
    MemoryReference,
    OmittedContextMarker,
    GraphError,
    ReadGap,
    RedactionStatus,
    ReviewTarget,
    ReviewVerdict,
    SelectedReviewer,
    SuggestedReply,
    SuppressedOutput,
    TruncationNotice,
)
from reviewgraph.posting import (
    CandidateIssueCommentPayload,
    PostingPlan,
    PostingPlanItem,
    build_candidate_issue_comment_payload,
    findings_hash,
    visible_body_hash,
)
from reviewgraph.redaction import redact_text, require_passing_redaction_status


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
    read_gaps: Iterable[ReadGap] = (),
    errors: Iterable[GraphError] = (),
    context_budget: ContextBudget | None = None,
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
        read_gaps=tuple(read_gaps),
        errors=tuple(errors),
        context_budget=context_budget,
    )
    _validate_read_gap_inputs(inputs)
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
        inputs.review_target,
        inputs.posting_plan,
        inputs.findings,
        inputs.memory_references,
        context,
    )
    return {
        "review_target": _review_target_json(inputs.review_target, context),
        "selected_reviewers": [
            {
                "name": context.redact(reviewer.name),
                "stage": context.redact(reviewer.stage),
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
        "read_gaps": [_read_gap_json(gap, context) for gap in inputs.read_gaps],
        "errors": [_graph_error_json(error, context) for error in inputs.errors],
        "truncation": [_truncation_json(notice, context) for notice in inputs.truncation_notices],
        "context_budget": _context_budget_json(inputs.context_budget, context),
        "candidate_payload_preview": candidate_preview,
        "redaction_status": context.status_dict(),
    }


def render_markdown(*, inputs: "_RenderInputs", context: "_RenderContext | None" = None) -> str:
    context = context or _RenderContext()
    lines: list[str] = [
        "# ReviewGraph Dry Run",
        "",
        "## Target",
        f"- PR: {context.redact(inputs.review_target.owner_repo)}#{inputs.review_target.pr_number}",
        f"- Head: {context.redact(inputs.review_target.head_sha)}",
        "",
        "## Local Verdict",
        f"- Value: {_private_verdict_label(inputs.local_verdict)}",
        "",
        "## Selected Reviewers",
    ]
    lines.extend(
        f"- {context.redact(reviewer.name)} ({context.redact(reviewer.stage)}): "
        f"{', '.join(context.redact(reason) for reason in reviewer.reasons)}"
        for reviewer in inputs.selected_reviewers
    )
    lines.extend(["", "## Postable Findings"])
    if inputs.findings:
        lines.extend(
            f"- P{finding.priority} {context.redact(finding.title)} ({context.redact(finding.path)}:{finding.line})"
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
        f"- {context.redact(reply.id)}: {context.redact(reply.proposed_body)}" for reply in inputs.suggested_replies
    )
    if not inputs.suggested_replies:
        lines.append("- None")

    lines.extend(["", "## Suppressed Outputs", f"- Count: {len(inputs.suppressed_outputs)}"])
    for output in inputs.suppressed_outputs:
        lines.append(f"- {context.redact(output.id)}: {context.redact(output.reason)}")

    lines.extend(["", "## Memory"])
    for memory in inputs.memory_references:
        lines.append(
            f"- {context.redact(memory.id)}: trust={context.redact(memory.trust_label)}, "
            f"resolved={context.redact(memory.resolved_status)}, source={context.redact(memory.source_type)}"
        )
    if not inputs.memory_references:
        lines.append("- None")

    lines.extend(["", "## Read Gaps"])
    if inputs.read_gaps:
        for gap in inputs.read_gaps:
            lines.append(
                f"- {context.redact(gap.resource)}: required={str(gap.required).lower()}, "
                f"retryable={str(gap.retryable).lower()} - {context.redact(gap.reason)}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Graph Errors"])
    if inputs.errors:
        for error in inputs.errors:
            lines.append(
                f"- {context.redact(error.code)}: {context.redact(error.message)} "
                f"(retryable={str(error.retryable).lower()})"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Truncation"])
    if inputs.truncation_notices:
        for notice in inputs.truncation_notices:
            lines.append(
                f"- {context.redact(notice.resource)}: truncated={str(notice.truncated).lower()}"
                f" - {context.redact(notice.note)}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Posting Plan"])
    if inputs.posting_plan is not None:
        for item in inputs.posting_plan.items:
            lines.append(
                f"- {context.redact(item.id)}: {context.redact(item.destination.value)}, "
                f"public={str(item.public_payload_eligible).lower()}"
            )
    else:
        lines.append("- None")

    preview = _candidate_payload_preview(
        inputs.candidate_payload,
        inputs.review_target,
        inputs.posting_plan,
        inputs.findings,
        inputs.memory_references,
        context,
    )
    lines.extend(["", "## Candidate Payload Preview"])
    if preview is None:
        lines.append("- None")
    else:
        lines.append(f"- Kind: {preview['artifact_kind']}")
        lines.append(f"- Visible body hash: {preview['visible_body_hash']}")
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


def _validate_read_gap_inputs(inputs: "_RenderInputs") -> None:
    required_gaps = tuple(gap for gap in inputs.read_gaps if gap.required)
    if not required_gaps:
        return
    if inputs.selected_reviewers:
        raise RenderError("required read gaps suppress reviewer execution")
    if inputs.findings:
        raise RenderError("required read gaps suppress findings")
    if inputs.posting_plan is not None:
        raise RenderError("required read gaps suppress posting plan")
    if not _has_required_read_gap_errors(required_gaps, inputs.errors):
        raise RenderError("required read gaps require github_read_gap errors")
    if inputs.candidate_payload is not None:
        raise RenderError("required read gaps suppress candidate payload")


def _has_required_read_gap_errors(
    required_gaps: tuple[ReadGap, ...],
    errors: tuple[GraphError, ...],
) -> bool:
    expected = {
        (
            f"Required GitHub read gap for {gap.resource}: {gap.reason}",
            gap.retryable,
        )
        for gap in required_gaps
    }
    actual = {
        (error.message, error.retryable)
        for error in errors
        if error.code == "github_read_gap"
    }
    return expected <= actual


def _markdown_items(items: Iterable[tuple[str, str]], context: "_RenderContext") -> list[str]:
    return [f"- {context.redact(title)}: {context.redact(body)}" for title, body in items]


def _candidate_payload_preview(
    candidate_payload: CandidateIssueCommentPayload | None,
    review_target: ReviewTarget,
    posting_plan: PostingPlan | None,
    findings: tuple[ClassifiedFinding, ...],
    memory_references: tuple[MemoryReference, ...],
    context: "_RenderContext",
) -> dict[str, Any] | None:
    if candidate_payload is None:
        return None
    require_passing_redaction_status(candidate_payload.redaction_status, surface="candidate_payload")
    _validate_candidate_payload_binding(
        candidate_payload=candidate_payload,
        review_target=review_target,
        posting_plan=posting_plan,
        findings=findings,
    )
    body = context.redact(candidate_payload.body)
    if body != candidate_payload.body:
        raise RenderError("candidate payload requires redaction after hash binding")
    for memory in memory_references:
        if _is_unsafe_memory(memory) and memory_body_overlaps_text(
            memory.body,
            _public_finding_text(posting_plan, findings),
        ):
            raise RenderError(f"candidate payload contains untrusted memory body: {memory.id}")
    item_fingerprints = [context.redact(fingerprint) for fingerprint in candidate_payload.item_fingerprints]
    if item_fingerprints != list(candidate_payload.item_fingerprints):
        raise RenderError("candidate payload item fingerprints require redaction after hash binding")
    context.absorb_candidate_payload_status(candidate_payload.redaction_status)
    return {
        "artifact_kind": candidate_payload.artifact_kind.value,
        "review_target": _review_target_json(candidate_payload.review_target, context),
        "body": body,
        "visible_body_hash": candidate_payload.visible_body_hash,
        "findings_hash": candidate_payload.findings_hash,
        "item_fingerprints": item_fingerprints,
        "redaction_status": {
            "redacted": candidate_payload.redaction_status.redacted,
            "replacement_count": candidate_payload.redaction_status.replacement_count,
            "categories": list(candidate_payload.redaction_status.categories),
        },
    }


def _review_target_json(review_target: ReviewTarget, context: "_RenderContext") -> dict[str, Any]:
    return {
        "owner_repo": context.redact(review_target.owner_repo),
        "pr_number": review_target.pr_number,
        "base_sha": context.redact(review_target.base_sha),
        "head_sha": context.redact(review_target.head_sha),
        "merge_base_sha": context.redact(review_target.merge_base_sha) if review_target.merge_base_sha else None,
        "diff_basis": context.redact(review_target.diff_basis),
    }


def _validate_candidate_payload_binding(
    *,
    candidate_payload: CandidateIssueCommentPayload,
    review_target: ReviewTarget,
    posting_plan: PostingPlan | None,
    findings: tuple[ClassifiedFinding, ...],
) -> None:
    if candidate_payload.review_target != review_target:
        raise RenderError("candidate payload target does not match rendered review target")
    if candidate_payload.visible_body_hash != visible_body_hash(candidate_payload.body):
        raise RenderError("candidate payload visible body hash does not match body")
    if candidate_payload.findings_hash != findings_hash(candidate_payload.item_fingerprints):
        raise RenderError("candidate payload findings hash does not match item fingerprints")
    if posting_plan is None:
        raise RenderError("candidate payload requires a posting plan")
    for item in posting_plan.public_payload_items:
        if item.id != "summary" and not item.fingerprint:
            raise RenderError("public payload item is missing a fingerprint")
    plan_fingerprints = tuple(
        sorted(item.fingerprint for item in posting_plan.public_payload_items if item.fingerprint)
    )
    if plan_fingerprints != candidate_payload.item_fingerprints:
        raise RenderError("candidate payload item fingerprints do not match posting plan")
    expected_payload = build_candidate_issue_comment_payload(
        review_target=review_target,
        posting_plan=posting_plan,
        findings=findings,
    )
    if candidate_payload != expected_payload:
        raise RenderError("candidate payload does not match current rendered findings")


def _is_unsafe_memory(memory: MemoryReference) -> bool:
    return not memory.actionable


def _can_render_memory_body(memory: MemoryReference) -> bool:
    return memory.actionable


def _public_finding_text(posting_plan: PostingPlan | None, findings: tuple[ClassifiedFinding, ...]) -> str:
    if posting_plan is None:
        return ""
    findings_by_id = {finding.id: finding for finding in findings}
    public_text: list[str] = []
    for item in posting_plan.public_payload_items:
        if item.id == "summary":
            continue
        finding = findings_by_id.get(item.id)
        if finding is not None:
            public_text.extend([finding.title, finding.body])
    return "\n".join(public_text)


def _finding_json(finding: ClassifiedFinding, context: "_RenderContext") -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": context.redact(finding.id),
        "source_reviewer": context.redact(finding.source_reviewer),
        "source_stage": context.redact(finding.source_stage),
        "classification": finding.classification.value,
        "priority": finding.priority,
        "severity": finding.severity.value,
        "confidence": finding.confidence.value,
        "title": context.redact(finding.title),
        "body": context.redact(finding.body),
        "evidence": context.redact(finding.evidence),
        "path": context.redact(finding.path),
        "line": finding.line,
        "fingerprint": context.redact(finding.fingerprint),
    }
    if finding.line_end is not None:
        data["line_end"] = finding.line_end
    if finding.diff_anchor is not None:
        data["diff_anchor"] = _diff_anchor_json(finding.diff_anchor, context)
    return data


def _diff_anchor_json(anchor: "DiffAnchor", context: "_RenderContext") -> dict[str, Any]:
    return {
        "path": context.redact(anchor.path),
        "old_path": context.redact(anchor.old_path) if anchor.old_path is not None else None,
        "file_status": context.redact(anchor.file_status),
        "hunk_id": context.redact(anchor.hunk_id),
        "hunk_start": anchor.hunk_start,
        "hunk_end": anchor.hunk_end,
        "side": anchor.side,
        "start_side": anchor.start_side,
        "line": anchor.line,
        "start_line": anchor.start_line,
        "target_commit_sha": context.redact(anchor.target_commit_sha),
    }


def _local_note_json(note: LocalNote, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": context.redact(note.id),
        "classification": note.classification.value,
        "title": context.redact(note.title),
        "body": context.redact(note.body),
        "evidence": context.redact(note.evidence),
    }


def _clarification_json(request: ClarificationRequest, context: "_RenderContext") -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": context.redact(request.id),
        "classification": request.classification.value,
        "reviewer": context.redact(request.reviewer),
        "question": context.redact(request.question),
        "why_it_matters": context.redact(request.why_it_matters),
        "blocks_verdict": request.blocks_verdict,
    }
    if request.source_stage is not None:
        data["source_stage"] = context.redact(request.source_stage)
    if request.source_run_key is not None:
        data["source_run_key"] = context.redact(request.source_run_key.stable_key())
    if request.status is not None:
        data["status"] = request.status.value
    if request.resume_target_stage is not None or request.resume_target_reviewers:
        data["resume_target"] = {
            "stage": request.resume_target_stage.value if request.resume_target_stage is not None else None,
            "reviewers": [context.redact(reviewer) for reviewer in request.resume_target_reviewers],
        }
    return data


def _suggested_reply_json(reply: SuggestedReply, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": context.redact(reply.id),
        "classification": reply.classification.value,
        "source_comment_id": context.redact(reply.source_comment_id),
        "proposed_body": context.redact(reply.proposed_body),
    }


def _suppressed_json(output: SuppressedOutput, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": context.redact(output.id),
        "classification": output.classification.value,
        "reason": context.redact(output.reason),
    }


def _posting_plan_json(posting_plan: PostingPlan | None, context: "_RenderContext") -> dict[str, Any] | None:
    if posting_plan is None:
        return None
    return {"items": [_posting_plan_item_json(item, context) for item in posting_plan.items]}


def _posting_plan_item_json(item: PostingPlanItem, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": context.redact(item.id),
        "source_classification": item.source_classification,
        "destination": item.destination.value,
        "public_payload_eligible": item.public_payload_eligible,
        "fingerprint": context.redact(item.fingerprint) if item.fingerprint is not None else None,
        "body": context.redact(item.body) if item.body is not None else None,
    }


def _memory_json(memory: MemoryReference, context: "_RenderContext") -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": context.redact(memory.id),
        "trust_label": context.redact(memory.trust_label),
        "resolved_status": context.redact(memory.resolved_status),
        "source_type": context.redact(memory.source_type),
        "role": "trusted_actionable_data" if memory.actionable else "passive_data",
        "body": context.redact(memory.body) if memory.body and _can_render_memory_body(memory) else None,
        "author": context.redact(memory.author) if memory.author is not None else None,
        "author_association": context.redact(memory.author_association)
        if memory.author_association is not None
        else None,
        "author_type": context.redact(memory.author_type) if memory.author_type is not None else None,
        "created_at": context.redact(memory.created_at) if memory.created_at is not None else None,
        "url": context.redact(memory.url) if memory.url is not None else None,
        "path": context.redact(memory.path) if memory.path is not None else None,
        "line": memory.line,
        "actionable": memory.actionable,
        "passive_reason": context.redact(memory.passive_reason) if memory.passive_reason is not None else None,
    }
    if memory.source_provider is not None:
        data["source_provider"] = context.redact(memory.source_provider)
    if memory.source_id is not None:
        data["source_id"] = context.redact(memory.source_id)
    if memory.thread_id is not None:
        data["thread_id"] = context.redact(memory.thread_id)
    return data


def _truncation_json(notice: TruncationNotice, context: "_RenderContext") -> dict[str, Any]:
    return {
        "resource": context.redact(notice.resource),
        "truncated": notice.truncated,
        "note": context.redact(notice.note),
        "original_count": notice.original_count,
        "retained_count": notice.retained_count,
        "original_bytes": notice.original_bytes,
        "retained_bytes": notice.retained_bytes,
    }


def _read_gap_json(gap: ReadGap, context: "_RenderContext") -> dict[str, Any]:
    return {
        "resource": context.redact(gap.resource),
        "required": gap.required,
        "reason": context.redact(gap.reason),
        "retryable": gap.retryable,
        "usage": "required_fail_closed" if gap.required else "visible_only_not_routing_evidence_or_public_payload",
    }


def _graph_error_json(error: GraphError, context: "_RenderContext") -> dict[str, Any]:
    return {
        "code": context.redact(error.code),
        "message": context.redact(error.message),
        "retryable": error.retryable,
    }


def _context_budget_json(budget: ContextBudget | None, context: "_RenderContext") -> dict[str, Any] | None:
    if budget is None:
        return None
    return {
        "limits": {
            "max_changed_files": budget.max_changed_files,
            "max_patch_bytes": budget.max_patch_bytes,
            "max_memory_bytes": budget.max_memory_bytes,
            "max_reviewers": budget.max_reviewers,
            "max_live_calls": budget.max_live_calls,
        },
        "changed_files": {
            "original_count": budget.original_changed_file_count,
            "retained_count": budget.retained_changed_file_count,
            "retained_paths": [context.redact(path) for path in budget.retained_file_paths],
            "omitted_paths": [context.redact(path) for path in budget.omitted_file_paths],
        },
        "patch_bytes": {
            "original": budget.original_patch_bytes,
            "retained": budget.retained_patch_bytes,
        },
        "memory": {
            "original_count": budget.original_memory_count,
            "retained_count": budget.retained_memory_count,
            "original_bytes": budget.original_memory_bytes,
            "retained_bytes": budget.retained_memory_bytes,
            "retained_ids": [context.redact(memory_id) for memory_id in budget.retained_memory_ids],
            "omitted_ids": [context.redact(memory_id) for memory_id in budget.omitted_memory_ids],
        },
        "reviewers": {
            "original_count": budget.original_reviewer_count,
            "retained_count": budget.retained_reviewer_count,
            "retained_ids": [context.redact(reviewer_id) for reviewer_id in budget.retained_reviewer_ids],
            "deferred_ids": [context.redact(reviewer_id) for reviewer_id in budget.deferred_reviewer_ids],
        },
        "live_calls": {
            "planned": budget.planned_live_calls,
            "retained_reviewer_ids": [
                context.redact(reviewer_id) for reviewer_id in budget.retained_live_call_reviewer_ids
            ],
            "deferred_reviewer_ids": [
                context.redact(reviewer_id) for reviewer_id in budget.deferred_live_call_reviewer_ids
            ],
        },
        "truncation": [_truncation_json(notice, context) for notice in budget.truncation],
        "omitted_context": [_omitted_context_json(marker, context) for marker in budget.omitted_context],
        "generated_local_note_ids": [context.redact(note_id) for note_id in budget.generated_local_note_ids],
        "reasons": [context.redact(reason) for reason in budget.reasons],
    }


def _omitted_context_json(marker: OmittedContextMarker, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": context.redact(marker.id),
        "source": context.redact(marker.source),
        "reason_code": context.redact(marker.reason_code),
        "dimension": context.redact(marker.dimension),
        "affected_id": context.redact(marker.affected_id),
        "original_count": marker.original_count,
        "retained_count": marker.retained_count,
        "original_bytes": marker.original_bytes,
        "retained_bytes": marker.retained_bytes,
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
    read_gaps: tuple[ReadGap, ...]
    errors: tuple[GraphError, ...]
    context_budget: ContextBudget | None


class _RenderContext:
    def __init__(self) -> None:
        self._redacted = False
        self._replacement_count = 0
        self._categories: list[str] = []
        self._candidate_payload_status_absorbed = False

    def redact(self, value: str) -> str:
        result = redact_text(value)
        self._redacted = self._redacted or result.redacted
        self._replacement_count += result.replacement_count
        self._categories.extend(result.categories)
        return result.text

    def absorb_candidate_payload_status(self, status: RedactionStatus) -> None:
        if self._candidate_payload_status_absorbed:
            return
        self._candidate_payload_status_absorbed = True
        self._redacted = self._redacted or status.redacted
        self._replacement_count += status.replacement_count
        self._categories.extend(status.categories)

    def status(self) -> RedactionStatus:
        return RedactionStatus(
            redacted=self._redacted or self._replacement_count > 0,
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
