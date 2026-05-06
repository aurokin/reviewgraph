from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from reviewgraph.hashing import canonical_json_hash
from reviewgraph.memory_provenance import memory_body_overlaps_text
from reviewgraph.models import (
    ClarificationRequest,
    ClassifiedFinding,
    Confidence,
    LocalNote,
    MemoryReference,
    RawReviewerFinding,
    ReviewerResult,
    Severity,
    SuggestedReply,
    SuppressedOutput,
)


FINDING_QUALITY_SUPPRESSION_REASON = "Finding candidate did not meet postable quality policy."
FINDING_OMITTED_CONTEXT_SUPPRESSION_REASON = "Finding candidate referenced context omitted by context budget."
FINDING_LOCATION_SUPPRESSION_REASON = "Finding candidate location did not overlap changed code."
FINDING_UNSAFE_PROVENANCE_SUPPRESSION_REASON = "Finding candidate used passive or untrusted memory as evidence."
CLARIFICATION_OMITTED_CONTEXT_SUPPRESSION_REASON = (
    "Clarification request referenced context omitted by context budget."
)
CLARIFICATION_UNSAFE_PROVENANCE_SUPPRESSION_REASON = (
    "Clarification request used passive or untrusted memory as evidence."
)


class ChangedLineContext(Protocol):
    path: str
    patch_status: str

    def contains_line(self, line: int) -> bool: ...


@dataclass(frozen=True)
class QualityClassificationResult:
    findings: tuple[ClassifiedFinding, ...] = ()
    local_notes: tuple[LocalNote, ...] = ()
    clarification_requests: tuple[ClarificationRequest, ...] = ()
    suggested_replies: tuple[SuggestedReply, ...] = ()
    suppressed_outputs: tuple[SuppressedOutput, ...] = ()


def classify_review_quality(
    *,
    changed_files: tuple[ChangedLineContext, ...],
    reviewer_result: ReviewerResult,
    memory_references: tuple[MemoryReference, ...],
    omitted_file_paths: tuple[str, ...] = (),
    omitted_memory_ids: tuple[str, ...] = (),
) -> QualityClassificationResult:
    findings: list[ClassifiedFinding] = []
    suppressed_outputs: list[SuppressedOutput] = []

    reviewer = reviewer_result.run_key.reviewer
    stage = reviewer_result.run_key.stage.value
    for raw_finding in reviewer_result.findings:
        if _finding_depends_on_omitted_context(
            changed_files,
            raw_finding,
            omitted_file_paths=omitted_file_paths,
            omitted_memory_ids=omitted_memory_ids,
        ):
            suppressed_outputs.append(
                SuppressedOutput(
                    id=raw_finding.id,
                    reason=FINDING_OMITTED_CONTEXT_SUPPRESSION_REASON,
                )
            )
            continue
        if not _finding_location_overlaps_changed_line(changed_files, raw_finding):
            suppressed_outputs.append(
                SuppressedOutput(
                    id=raw_finding.id,
                    reason=FINDING_LOCATION_SUPPRESSION_REASON,
                )
            )
            continue
        finding = _classified_finding(
            reviewer=reviewer,
            stage=stage,
            raw_finding=raw_finding,
        )
        if _is_postable_finding(finding):
            if _finding_has_unsafe_evidence_provenance(
                raw_finding,
                memory_references=memory_references,
            ):
                suppressed_outputs.append(
                    SuppressedOutput(
                        id=raw_finding.id,
                        reason=FINDING_UNSAFE_PROVENANCE_SUPPRESSION_REASON,
                    )
                )
            else:
                findings.append(finding)
        else:
            suppressed_outputs.append(
                SuppressedOutput(
                    id=finding.id,
                    reason=FINDING_QUALITY_SUPPRESSION_REASON,
                )
            )

    clarification_requests: list[ClarificationRequest] = []
    for request in reviewer_result.clarification_requests:
        if _uses_omitted_memory(
            request.evidence_memory_ids,
            omitted_memory_ids=omitted_memory_ids,
        ):
            suppressed_outputs.append(
                SuppressedOutput(
                    id=request.id,
                    reason=CLARIFICATION_OMITTED_CONTEXT_SUPPRESSION_REASON,
                )
            )
        elif _clarification_has_unsafe_evidence_provenance(
            request,
            memory_references=memory_references,
        ):
            suppressed_outputs.append(
                SuppressedOutput(
                    id=request.id,
                    reason=CLARIFICATION_UNSAFE_PROVENANCE_SUPPRESSION_REASON,
                )
            )
        else:
            clarification_requests.append(request)

    suppressed_outputs.extend(reviewer_result.suppressed_outputs)
    return QualityClassificationResult(
        findings=tuple(findings),
        local_notes=reviewer_result.local_notes,
        clarification_requests=tuple(clarification_requests),
        suggested_replies=reviewer_result.suggested_replies,
        suppressed_outputs=tuple(suppressed_outputs),
    )


def _finding_depends_on_omitted_context(
    changed_files: tuple[ChangedLineContext, ...],
    raw_finding: RawReviewerFinding,
    *,
    omitted_file_paths: tuple[str, ...],
    omitted_memory_ids: tuple[str, ...],
) -> bool:
    if raw_finding.path in omitted_file_paths:
        return True
    if _uses_omitted_memory(
        raw_finding.evidence_memory_ids,
        omitted_memory_ids=omitted_memory_ids,
    ):
        return True
    for changed_file in changed_files:
        if changed_file.path == raw_finding.path and changed_file.contains_line(raw_finding.line):
            return changed_file.patch_status != "available"
    return False


def _finding_location_overlaps_changed_line(
    changed_files: tuple[ChangedLineContext, ...],
    raw_finding: RawReviewerFinding,
) -> bool:
    return any(
        changed_file.path == raw_finding.path and changed_file.contains_line(raw_finding.line)
        for changed_file in changed_files
    )


def _uses_omitted_memory(
    evidence_memory_ids: tuple[str, ...],
    *,
    omitted_memory_ids: tuple[str, ...],
) -> bool:
    omitted = set(omitted_memory_ids)
    return any(memory_id in omitted for memory_id in evidence_memory_ids)


def _finding_has_unsafe_evidence_provenance(
    raw_finding: RawReviewerFinding,
    *,
    memory_references: tuple[MemoryReference, ...],
) -> bool:
    return _unsafe_evidence_provenance(
        evidence_sources=raw_finding.evidence_sources,
        evidence_memory_ids=raw_finding.evidence_memory_ids,
        memory_references=memory_references,
        text_values=(raw_finding.title, raw_finding.rationale, raw_finding.evidence),
        require_provenance_with_passive_memory=False,
        strict_passive_text_overlap=True,
    )


def _clarification_has_unsafe_evidence_provenance(
    request: ClarificationRequest,
    *,
    memory_references: tuple[MemoryReference, ...],
) -> bool:
    return _unsafe_evidence_provenance(
        evidence_sources=request.evidence_sources,
        evidence_memory_ids=request.evidence_memory_ids,
        memory_references=memory_references,
        text_values=(request.question, request.why_it_matters),
        require_provenance_with_passive_memory=True,
        strict_passive_text_overlap=False,
    )


def _unsafe_evidence_provenance(
    *,
    evidence_sources: tuple[str, ...],
    evidence_memory_ids: tuple[str, ...],
    memory_references: tuple[MemoryReference, ...],
    text_values: tuple[str, ...],
    require_provenance_with_passive_memory: bool,
    strict_passive_text_overlap: bool,
) -> bool:
    if require_provenance_with_passive_memory:
        has_passive_memory = any(not memory.actionable for memory in memory_references)
        if has_passive_memory and not evidence_sources and not evidence_memory_ids:
            return True
    if "trusted_memory" in evidence_sources and not evidence_memory_ids:
        return True
    if evidence_memory_ids and "trusted_memory" not in evidence_sources:
        return True
    memory_by_id = {memory.id: memory for memory in memory_references}
    if any(
        (memory := memory_by_id.get(memory_id)) is None or not memory.actionable
        for memory_id in evidence_memory_ids
    ):
        return True
    if _text_copies_passive_memory(
        text_values,
        memory_references=memory_references,
        strict=strict_passive_text_overlap,
    ):
        return True
    if evidence_sources:
        return False
    return False


def _text_copies_passive_memory(
    text_values: tuple[str, ...],
    *,
    memory_references: tuple[MemoryReference, ...],
    strict: bool,
) -> bool:
    if strict:
        text = "\n".join(text_values)
        for memory in memory_references:
            if memory.actionable:
                continue
            if memory_body_overlaps_text(memory.body, text):
                return True
        return False
    values = [
        normalized
        for value in text_values
        if len(normalized := _normalized_provenance_text(value)) >= 30
    ]
    if not values:
        return False
    for memory in memory_references:
        if memory.actionable:
            continue
        body = _normalized_provenance_text(memory.body or "")
        if len(body) < 30:
            continue
        for value in values:
            if value in body or body in value:
                return True
    return False


def _normalized_provenance_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _classified_finding(
    *,
    reviewer: str,
    stage: str,
    raw_finding: RawReviewerFinding,
) -> ClassifiedFinding:
    return ClassifiedFinding(
        id=raw_finding.id,
        source_reviewer=reviewer,
        source_stage=stage,
        title=raw_finding.title,
        body=raw_finding.rationale,
        evidence=raw_finding.evidence,
        path=raw_finding.path,
        line=raw_finding.line,
        line_end=raw_finding.line_end,
        priority=_graph_priority(raw_finding),
        severity=raw_finding.severity,
        confidence=raw_finding.confidence,
        fingerprint=_graph_fingerprint(raw_finding),
    )


def _graph_priority(raw_finding: RawReviewerFinding) -> int:
    if raw_finding.severity in {Severity.CRITICAL, Severity.WARNING}:
        return 1
    if raw_finding.severity == Severity.SUGGESTION:
        return 2
    return 3


def _graph_fingerprint(raw_finding: RawReviewerFinding) -> str:
    return canonical_json_hash(
        {
            "domain": "reviewgraph.fixture_finding.v1",
            "path": raw_finding.path,
            "line": raw_finding.line,
            "title": raw_finding.title,
            "evidence": raw_finding.evidence,
        }
    )


def _is_postable_finding(finding: ClassifiedFinding) -> bool:
    if finding.confidence == Confidence.LOW:
        return False
    if finding.confidence != Confidence.HIGH and finding.severity == Severity.CRITICAL:
        return False
    if finding.blocking and finding.confidence != Confidence.HIGH:
        return False
    if not _has_concrete_finding_evidence(finding.evidence):
        return False
    public_text = f"{finding.title}\n{finding.body}"
    text = f"{public_text}\n{finding.evidence}".casefold()
    if not _has_public_comment_shape(public_text):
        return False
    if _is_testing_advice(finding, text):
        return _has_testing_finding_shape(public_text=public_text.casefold(), text=text)
    if _is_generic_speculative_advice(text):
        return False
    if not _has_non_testing_finding_shape(text):
        return False
    generic_refactor_advice = (
        "clean this up",
        "cleaner structure",
        "could be refactored",
        "easier maintenance",
        "easier to maintain",
        "easier to read",
        "cleaner code",
        "better organization",
        "better structure",
        "better modularity",
        "decoupling",
        "modularity",
        "testability",
        "improve maintainability",
        "abstractions",
        "future maintainer",
        "future maintainers",
        "improve readability",
        "refactor this",
        "simplify this code",
        "when this grows",
    )
    return not any(phrase in text for phrase in generic_refactor_advice)


def _has_public_comment_shape(body: str) -> bool:
    normalized = body.casefold()
    if len(body.split()) > 120:
        return False
    public_verdict_pressure = (
        "request changes",
        "requested changes",
        "block merge",
        "blocking merge",
        "do not merge",
        "don't merge",
        "must not merge",
        "reject this pr",
    )
    pressure_text = re.sub(r"[_-]+", " ", normalized)
    if any(phrase in pressure_text for phrase in public_verdict_pressure):
        return False
    multi_issue_markers = (
        "also,",
        "also ",
        "another issue",
        "second issue",
        "separate issue",
        "unrelated issue",
    )
    return not any(marker in normalized for marker in multi_issue_markers)


def _has_concrete_finding_evidence(evidence: str) -> bool:
    normalized = evidence.casefold().strip()
    if not normalized:
        return False
    if re.fullmatch(
        r"(?:n/?a|none|unknown|tbd|see (?:diff|above)|"
        r"(?:changed\s+)?lines?\s+\d+(?:\s*[-,]\s*\d+)*\.?)",
        normalized,
    ):
        return False
    if not re.search(r"\b(changed lines?|new branch|introduced|now)\b", normalized):
        return False
    detail = re.sub(r"^changed\s+lines?\s+\d+(?:\s*[-,]\s*\d+)*\s*[:.-]?\s*", "", normalized)
    if len(detail.split()) < 3:
        return False
    return bool(re.search(r"[a-z]{3,}", detail))


def _is_testing_advice(finding: ClassifiedFinding, text: str) -> bool:
    if finding.source_reviewer == "testing":
        return True
    testing_terms = (
        "add tests",
        "improve coverage",
        "missing coverage",
        "missing test",
        "missing tests",
        "no regression coverage",
        "no test coverage",
        "please add tests",
        "regression test",
        "test coverage",
        "without tests",
    )
    return any(term in text for term in testing_terms)


def _has_testing_finding_shape(*, public_text: str, text: str) -> bool:
    return (
        _has_identifiable_missing_coverage_target(public_text)
        and _has_concrete_testing_shape(text)
        and not _has_only_vague_testing_scenario(text)
    )


def _has_identifiable_missing_coverage_target(text: str) -> bool:
    patterns = (
        r"\bmissing\s+(?!tests?\b|coverage\b|regression\s+(?:tests?|coverage)\b)(?:[\w-]+\s+){1,8}(?:tests?|coverage)\b",
        r"\bmissing\s+(?:regression\s+)?(?:tests?|coverage)\s+(?:for|covering|on|in|with|when|around)\s+\w+",
        r"\bno\s+(?:regression\s+)?tests?\s+(?:for|covering|on|in|with|when|around)\s+\w+",
        r"\bno\s+(?:regression\s+)?tests?\s+(?:currently\s+|that\s+)?covers?\s+\w+",
        r"\bno\s+(?:regression\s+)?coverage\s+(?:for|covering|on|in|with|when|around)\s+(?!this\s+change\b)\w+",
        r"\bno\s+(?!coverage\s+(?:for|on)\s+this\s+change\b)(?:[\w-]+\s+){1,8}coverage\b",
        r"\bwithout\s+(?:a\s+)?(?:regression\s+)?tests?\s+(?:for|covering|on|in|with|when|around)\s+\w+",
        r"\bwithout\s+(?:regression\s+)?coverage\s+(?:for|covering|on|in|with|when|around)\s+\w+",
        r"\blacks\s+(?!tests?\b|coverage\b)(?:[\w-]+\s+){1,8}(?:tests?|coverage)\b",
        r"\blacks\s+(?:regression\s+)?tests?\s+(?:for|covering|on|in|with|when|around)\s+\w+",
        r"\blacks\s+(?:regression\s+)?coverage\s+(?:for|covering|on|in|with|when|around)\s+\w+",
        r"\b(?:tests?|coverage)\s+(?:does\s+not|doesn't|do\s+not|don't)\s+cover\s+\w+",
        r"\bnot\s+covered\s+(?:by|for|on|in|with|when|around)\s+\w+",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def _has_only_vague_testing_scenario(text: str) -> bool:
    has_vague = any(phrase in text for phrase in ("for this change", "when this changes", "this changes", "changed behavior"))
    concrete_text = text
    for phrase in ("for this change", "when this changes", "this changes", "changed behavior"):
        concrete_text = concrete_text.replace(phrase, " ")
    has_specific = bool(re.search(r"\b(whenever|when|if|after|before|with|without|on|in|to|via|from|while|where)\b", concrete_text))
    return has_vague and not has_specific


def _is_generic_speculative_advice(text: str) -> bool:
    speculative_pattern = (
        r"\b(could|may|might)\s+(?:cause|fail|break|regress|leak|expose)"
        r"|potential issue|requires investigation|should investigate"
        r"|still (?:fail|fails|failing|broken)"
        r"|already (?:fail|fails|failing|broken|present|known)"
        r"|was already (?:fail|failing|broken|present|known)"
        r"|was previously (?:present|known|failing|broken)"
        r"|pre[\s-]?existing"
    )
    return bool(re.search(speculative_pattern, text))


def _has_non_testing_finding_shape(text: str) -> bool:
    return _has_concrete_finding_shape(text)


def _has_concrete_testing_shape(text: str) -> bool:
    scenario = bool(re.search(r"\b(whenever|when|if|after|before|with|without|on|in|to|via|from|while|where)\b", text))
    introduced = bool(re.search(r"\b(changed line|new branch|introduced|now)\b", text))
    coverage_target = bool(re.search(r"\b(regression tests?|regression coverage|coverage|tests?)\b", text))
    return scenario and introduced and coverage_target


def _has_concrete_finding_shape(text: str) -> bool:
    scenario = bool(re.search(r"\b(whenever|when|if|after|before|with|without|for|on|in|to|via|from|while|where)\b", text))
    introduced = bool(re.search(r"\b(changed line|new branch|introduced|now)\b", text))
    harmful_behavior = bool(
        re.search(
            r"\b(regress|overcharg\w*|double[- ]charg\w*|duplicate emails?|loops? forever|shifts?|breaks?|corrupts?|deletes?|drops?|exposes?|fails?|hangs?|ignores?|includes?|leaks?|logs?|misroutes?|omits?|persists?|raises?|rejects?|returns?|rounds?|sends?|skips?|bypasses?|cannot|stale|unauthorized|writes?|open redirect|path traversal|unauthenticated access)\b",
            text,
        )
    )
    harmful_broad_access = bool(
        re.search(
            r"\b(allows?|accepts?|permits?)\b.*\b(unauthenticated access|unauthorized|open redirect|path traversal|user-controlled|private|leak|expos|bypass|admin|token|session|email|charge|overcharg|double charg)\b",
            text,
        )
    )
    return scenario and introduced and (harmful_behavior or harmful_broad_access)
