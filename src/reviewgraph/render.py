from __future__ import annotations

import re
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
from reviewgraph.posting import (
    CandidateIssueCommentPayload,
    PostingPlan,
    PostingPlanItem,
    build_candidate_issue_comment_payload,
    findings_hash,
    full_body_hash,
    visible_body_hash,
)
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
    review_target: ReviewTarget,
    posting_plan: PostingPlan | None,
    findings: tuple[ClassifiedFinding, ...],
    memory_references: tuple[MemoryReference, ...],
    context: "_RenderContext",
) -> dict[str, Any] | None:
    if candidate_payload is None:
        return None
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
        if _is_unsafe_memory(memory) and _memory_body_overlaps_candidate(
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
        "full_body_hash": candidate_payload.full_body_hash,
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
    if candidate_payload.full_body_hash != full_body_hash(candidate_payload.body):
        raise RenderError("candidate payload full body hash does not match body")
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
    return memory.trust_label != "trusted"


def _memory_body_overlaps_candidate(memory_body: str | None, candidate_body: str) -> bool:
    if not memory_body:
        return False
    normalized_memory = _normalize_memory_text(memory_body)
    normalized_candidate = _normalize_memory_text(candidate_body)
    if _exact_memory_body_is_meaningful(normalized_memory) and _normalized_phrase_in_text(
        normalized_memory,
        normalized_candidate,
    ):
        return True
    candidate_words = set(normalized_candidate.split())
    compact_candidate = normalized_candidate.replace(" ", "")
    meaningful_fragments = _meaningful_memory_fragments(memory_body)
    for fragment in meaningful_fragments:
        if (
            " " in fragment
            and (_has_enough_fragment_signal(fragment) or fragment == normalized_memory)
            and _normalized_phrase_in_text(fragment, normalized_candidate)
        ):
            return True
        if " " not in fragment and fragment in candidate_words:
            return True
        compact_fragment = fragment.replace(" ", "")
        if " " not in fragment and _looks_mixed_identifier_like(fragment) and compact_fragment in compact_candidate:
            return True
        if (
            " " in fragment
            and (_has_enough_fragment_signal(fragment) or _looks_identifier_like(compact_fragment))
            and _has_enough_compact_fragment_signal(compact_fragment)
            and compact_fragment in compact_candidate
        ):
            return True
    return False


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


def _meaningful_memory_fragments(memory_body: str) -> tuple[str, ...]:
    normalized = _normalize_memory_text(memory_body)
    raw_tokens = [token for token in re.split(r"\s+", memory_body.strip()) if token]
    fragments = {normalized} if _full_memory_fragment_is_meaningful(normalized) else set()
    for sentence in normalized.replace("!", ".").replace("?", ".").split("."):
        sentence = sentence.strip()
        if len(sentence) >= 16:
            fragments.add(sentence)
    words = normalized.split()
    for index, word in enumerate(words):
        if _has_enough_word_signal(word, words, index):
            fragments.add(word)
    for index, raw_token in enumerate(raw_tokens):
        compact_token = _compact_raw_token(raw_token)
        if compact_token and (
            _raw_token_has_high_signal_context(raw_tokens, index)
            or _raw_token_has_delimiter_digit_signal(raw_token)
            or _raw_token_has_delimiter_signal(raw_token)
        ) and _has_meaningful_compact_raw_token_signal(compact_token, words, index):
            fragments.add(compact_token)
    for size in range(2, min(5, len(words)) + 1):
        for index in range(0, len(words) - size + 1):
            fragment = " ".join(words[index : index + size])
            raw_fragment = " ".join(raw_tokens[index : index + size])
            if _has_enough_fragment_signal(fragment) or _has_enough_compact_fragment_signal(
                fragment,
                raw_fragment,
            ):
                fragments.add(fragment)
    for index in range(0, max(len(words) - 5, 0)):
        fragment = " ".join(words[index : index + 6])
        if len(fragment) >= 24:
            fragments.add(fragment)
    return tuple(sorted(fragments))


def _has_enough_fragment_signal(fragment: str) -> bool:
    words = fragment.split()
    if len(words) >= 3:
        return len(fragment) >= 10 and len(set(fragment.replace(" ", ""))) >= 5
    if len(words) == 2:
        sensitive_words = {"account", "codename", "identifier", "key", "password", "secret", "ticket", "token"}
        return (
            len(fragment) >= 10
            and len(set(fragment.replace(" ", ""))) >= 5
            and any(word in sensitive_words for word in words)
        )
    compact = fragment.replace(" ", "")
    return len(fragment) >= 7 and len(set(compact)) >= 5


def _exact_memory_body_is_meaningful(normalized: str) -> bool:
    words = normalized.split()
    if not words:
        return False
    if all(word in _COMMON_MEMORY_WORDS for word in words):
        return False
    if len(words) == 1:
        word = words[0]
        return word not in _COMMON_MEMORY_WORDS and len(word) >= 4 and len(set(word)) >= 4
    return len(normalized) >= 4 and len(set(normalized.replace(" ", ""))) >= 4


def _normalized_phrase_in_text(phrase: str, text: str) -> bool:
    words = phrase.split()
    if len(words) == 1:
        return words[0] in set(text.split())
    return f" {phrase} " in f" {text} "


def _full_memory_fragment_is_meaningful(normalized: str) -> bool:
    return " " in normalized and _exact_memory_body_is_meaningful(normalized)


def _has_enough_word_signal(word: str, words: list[str], index: int) -> bool:
    if word in _COMMON_MEMORY_WORDS:
        return False
    if len(words) == 1:
        return len(word) >= 5 and len(set(word)) >= 4
    context_window = words[max(0, index - 2) : index] + words[index + 1 : index + 3]
    if _looks_identifier_like(word):
        if _looks_mixed_identifier_like(word):
            return True
        return any(token in _HIGH_SIGNAL_CONTEXT_WORDS for token in context_window)
    if len(word) >= 10 and len(set(word)) >= 6:
        return True
    return len(word) >= 5 and len(set(word)) >= 4 and any(token in _HIGH_SIGNAL_CONTEXT_WORDS for token in context_window)


def _looks_identifier_like(word: str) -> bool:
    return any(char.isdigit() for char in word) and len(word) >= 6 and len(set(word)) >= 4


def _looks_mixed_identifier_like(word: str) -> bool:
    if word in _COMMON_TECH_TOKENS:
        return False
    return (
        any(char.isalpha() for char in word)
        and any(char.isdigit() for char in word)
        and len(word) >= 6
        and len(set(word)) >= 4
    )


def _has_enough_compact_fragment_signal(fragment: str, raw_fragment: str = "") -> bool:
    compact = fragment.replace(" ", "")
    return _looks_identifier_like(compact) and _has_high_signal_context(fragment.split(), raw_fragment)


def _has_high_signal_context(words: list[str], raw_fragment: str) -> bool:
    return any(word in _HIGH_SIGNAL_CONTEXT_WORDS for word in words) or bool(
        re.search(
            r"[A-Za-z]+(?:[^\w\s]|_)[A-Za-z0-9]*\d|\d(?:[^\w\s]|_)[A-Za-z0-9]+|[A-Za-z]+(?:[^\w\s]|_)[A-Za-z]+",
            raw_fragment,
        )
    )


def _compact_raw_token(raw_token: str) -> str | None:
    if not re.search(r"(?:[^\w\s]|_)", raw_token):
        return None
    compact = _normalize_memory_text(raw_token).replace(" ", "")
    if len(compact) < 5 or len(set(compact)) < 4:
        return None
    return compact


def _raw_token_has_high_signal_context(raw_tokens: list[str], index: int) -> bool:
    token = _normalize_memory_text(raw_tokens[index])
    if any(word in _HIGH_SIGNAL_CONTEXT_WORDS for word in token.split()):
        return True
    context_tokens = raw_tokens[max(0, index - 2) : index] + raw_tokens[index + 1 : index + 3]
    context = _normalize_memory_text(" ".join(context_tokens)).split()
    return any(word in _HIGH_SIGNAL_CONTEXT_WORDS for word in context)


def _raw_token_has_delimiter_signal(raw_token: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9]+(?:[^\w\s]|_)[A-Za-z0-9]+", raw_token))


def _raw_token_has_delimiter_digit_signal(raw_token: str) -> bool:
    return bool(re.search(r"[A-Za-z0-9]+(?:[^\w\s]|_)[A-Za-z0-9]*\d|\d(?:[^\w\s]|_)[A-Za-z0-9]+", raw_token))


def _has_meaningful_compact_raw_token_signal(compact_token: str, words: list[str], index: int) -> bool:
    if compact_token in _COMMON_TECH_TOKENS:
        return False
    context_window = words[max(0, index - 2) : index] + words[index + 1 : index + 3]
    prefix = _common_word_numeric_prefix(compact_token)
    if prefix is not None:
        return prefix in _IDENTIFIER_NUMERIC_PREFIX_WORDS or any(
            token in _HIGH_SIGNAL_CONTEXT_WORDS for token in context_window
        )
    if compact_token.isdigit():
        return any(token in _HIGH_SIGNAL_CONTEXT_WORDS for token in context_window)
    return _looks_mixed_identifier_like(compact_token) or len(compact_token) >= 5


def _common_word_numeric_prefix(compact_token: str) -> str | None:
    return next(
        (
            word
            for word in _COMMON_MEMORY_WORDS
            if compact_token.startswith(word) and compact_token[len(word) :].isdigit()
        ),
        None,
    )


_IDENTIFIER_NUMERIC_PREFIX_WORDS = {
    "customer",
    "user",
}


def _normalize_memory_text(value: str) -> str:
    return " ".join(re.sub(r"[_\W]+", " ", value.casefold()).split())


_COMMON_MEMORY_WORDS = {
    "authentication",
    "authorization",
    "become",
    "branch",
    "cache",
    "candidate",
    "change",
    "comment",
    "commenter",
    "customer",
    "during",
    "evidence",
    "here",
    "if",
    "issue",
    "line",
    "mentioned",
    "never",
    "patch",
    "payload",
    "please",
    "public",
    "referenced",
    "review",
    "reviewer",
    "should",
    "target",
    "the",
    "thread",
    "untrusted",
}

_HIGH_SIGNAL_CONTEXT_WORDS = {
    "account",
    "codename",
    "identifier",
    "key",
    "secret",
    "ticket",
    "token",
}

_COMMON_TECH_TOKENS = {
    "go122",
    "http2",
    "node18",
    "python3",
    "react19",
    "sha256",
}


def _finding_json(finding: ClassifiedFinding, context: "_RenderContext") -> dict[str, Any]:
    return {
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


def _local_note_json(note: LocalNote, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": context.redact(note.id),
        "classification": note.classification.value,
        "title": context.redact(note.title),
        "body": context.redact(note.body),
        "evidence": context.redact(note.evidence),
    }


def _clarification_json(request: ClarificationRequest, context: "_RenderContext") -> dict[str, Any]:
    return {
        "id": context.redact(request.id),
        "classification": request.classification.value,
        "reviewer": context.redact(request.reviewer),
        "question": context.redact(request.question),
        "why_it_matters": context.redact(request.why_it_matters),
        "blocks_verdict": request.blocks_verdict,
    }


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
    return {
        "id": context.redact(memory.id),
        "trust_label": context.redact(memory.trust_label),
        "resolved_status": context.redact(memory.resolved_status),
        "source_type": context.redact(memory.source_type),
        "body": context.redact(memory.body) if memory.body and not _is_unsafe_memory(memory) else None,
    }


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
