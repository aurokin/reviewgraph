from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

from reviewgraph.fixtures import (
    FixtureError,
    FixturePR,
    ReviewerConfig,
    assert_changed_line,
    load_fixture_pr,
    load_reviewer_config,
    redact_for_error,
)
from reviewgraph.memory import build_conversation_memory
from reviewgraph.posting import canonical_json_hash
from reviewgraph.models import (
    ClarificationRequest,
    ClassifiedFinding,
    Confidence,
    LocalNote,
    MemoryReference,
    RawReviewerFinding,
    ReviewTarget,
    ReviewVerdict,
    ReviewerTriggers,
    SelectedReviewer,
    Severity,
    SuggestedReply,
    SuppressedOutput,
    TruncationNotice,
)
from reviewgraph.posting import (
    CandidateIssueCommentPayload,
    PostingDestination,
    PostingPlan,
    PostingPlanItem,
    build_candidate_issue_comment_payload,
    build_posting_plan,
)
from reviewgraph.redaction import redact_data
from reviewgraph.render import RenderedReview, render_review


class RunnerError(ValueError):
    pass


@dataclass(frozen=True)
class DryRunResult:
    markdown: str
    json_data: dict[str, Any]
    rendered: RenderedReview
    writer_call_count: int


@dataclass(frozen=True)
class _StageRunResult:
    selected_reviewers: tuple[SelectedReviewer, ...]
    graph_trace: list[dict[str, Any]]
    classified: dict[str, tuple[Any, ...]]


NORMAL_STAGES = ("initial_triage", "specialized_review", "logic_review")


def run_fixture_dry_run(
    *,
    fixture_ref: str,
    reviewer_config_path: str | None = None,
    writer_sentinel: object | None = None,
) -> DryRunResult:
    writer_call_count_before = _writer_call_count(writer_sentinel)
    fixture = load_fixture_pr(fixture_ref)
    config = load_reviewer_config(reviewer_config_path)
    conversation_memory = build_conversation_memory(
        fixture.pr,
        trusted_operator_authors=set(config.trusted_operator_authors),
        trusted_bot_authors=set(config.trusted_bot_authors),
    )
    memory_references = conversation_memory.entries
    stage_run = _run_review_stages(config, fixture, memory_references=memory_references)
    selected_reviewers = stage_run.selected_reviewers
    graph_trace = stage_run.graph_trace
    review_target = _review_target(fixture)
    truncation_notices = _truncation_notices(fixture)
    classified = stage_run.classified
    _validate_output_item_ids(classified)
    _validate_finding_fingerprints(classified["findings"])
    local_verdict = _local_verdict(
        findings=classified["findings"],
        clarification_requests=classified["clarification_requests"],
    )
    post_enabled = local_verdict == ReviewVerdict.COMMENT and bool(classified["findings"])
    posting_plan = build_posting_plan(
        findings=classified["findings"],
        local_notes=classified["local_notes"],
        suggested_replies=classified["suggested_replies"],
        clarification_requests=classified["clarification_requests"],
        suppressed_outputs=classified["suppressed_outputs"],
    )
    if not post_enabled:
        posting_plan = _local_only_posting_plan(posting_plan)
    candidate_payload = _candidate_payload(
        enabled=post_enabled,
        review_target=review_target,
        posting_plan=posting_plan,
        findings=classified["findings"],
    )
    rendered = render_review(
        review_target=review_target,
        selected_reviewers=selected_reviewers,
        findings=classified["findings"],
        local_notes=classified["local_notes"],
        clarification_requests=classified["clarification_requests"],
        suggested_replies=classified["suggested_replies"],
        suppressed_outputs=classified["suppressed_outputs"],
        local_verdict=local_verdict,
        posting_plan=posting_plan,
        candidate_payload=candidate_payload,
        memory_references=memory_references,
        truncation_notices=truncation_notices,
    )
    writer_call_count = _writer_call_count(writer_sentinel) - writer_call_count_before
    envelope = _json_envelope(
        fixture=fixture,
        post_enabled=post_enabled,
        local_verdict=local_verdict,
        selected_reviewers=selected_reviewers,
        graph_trace=graph_trace,
        writer_call_count=writer_call_count,
        rendered=rendered,
    )
    return DryRunResult(
        markdown=rendered.markdown,
        json_data=envelope,
        rendered=rendered,
        writer_call_count=writer_call_count,
    )


def _run_review_stages(
    config: ReviewerConfig,
    fixture: FixturePR,
    *,
    memory_references: tuple[MemoryReference, ...],
) -> _StageRunResult:
    raw_outputs_by_key = _raw_outputs_by_key(fixture)
    selected_reviewers: list[SelectedReviewer] = []
    graph_trace: list[dict[str, Any]] = []
    classified = _empty_classified_lists()
    seen_raw_keys: set[tuple[str, str]] = set()
    active_stage: str | None = None
    stage_queue = list(NORMAL_STAGES)
    clarification_needed = False

    for stage in NORMAL_STAGES:
        before_active = active_stage
        before_queue = list(stage_queue)
        if not stage_queue or stage_queue[0] != stage:
            raise RunnerError(f"stage cursor expected {stage}")
        stage_queue.pop(0)
        active_stage = stage
        graph_trace.append(
            _stage_transition_trace(
                active_stage_before=before_active,
                active_stage_after=active_stage,
                stage_queue_before=before_queue,
                stage_queue_after=stage_queue,
            )
        )

        stage_reviewers = _select_reviewers_for_stage(
            config,
            fixture,
            stage,
            memory_references=memory_references,
        )
        if stage == "initial_triage" and not stage_reviewers:
            raise RunnerError("reviewer config has no eligible initial_triage always-on reviewer")
        selected_reviewers.extend(stage_reviewers)
        for reviewer in stage_reviewers:
            key = (reviewer.name, reviewer.stage)
            reviewer_output = raw_outputs_by_key.get(key)
            if reviewer_output is None:
                raise RunnerError(
                    "raw reviewer output was not selected; missing raw reviewer output for selected reviewer: "
                    f"{reviewer.name}/{reviewer.stage}"
                )
            seen_raw_keys.add(key)
            _classify_reviewer_output(fixture, reviewer_output=reviewer_output, classified=classified)
        if classified["clarification_requests"]:
            clarification_needed = True
            break

    if clarification_needed:
        graph_trace.append(
            {
                "active_stage_before": active_stage,
                "active_stage_after": None,
                "suspended_stage_before": None,
                "suspended_stage_after": None,
                "stage_queue_before": list(stage_queue),
                "stage_queue_after": list(stage_queue),
                "transition_reason": "clarification_needed_end",
            }
        )
    else:
        graph_trace.append(
            {
                "active_stage_before": active_stage,
                "active_stage_after": None,
                "suspended_stage_before": None,
                "suspended_stage_after": None,
                "stage_queue_before": list(stage_queue),
                "stage_queue_after": list(stage_queue),
                "transition_reason": "finish_review_stages",
            }
        )

    extra_raw_keys = sorted(set(raw_outputs_by_key) - seen_raw_keys)
    if extra_raw_keys:
        extra = ", ".join(f"{reviewer}/{stage}" for reviewer, stage in extra_raw_keys)
        raise RunnerError(f"raw reviewer output was not selected: {extra}")
    return _StageRunResult(
        selected_reviewers=tuple(selected_reviewers),
        graph_trace=graph_trace,
        classified={key: tuple(value) for key, value in classified.items()},
    )


def _select_reviewers_for_stage(
    config: ReviewerConfig,
    fixture: FixturePR,
    stage: str,
    *,
    memory_references: tuple[MemoryReference, ...],
) -> tuple[SelectedReviewer, ...]:
    selected: list[SelectedReviewer] = []
    for name in sorted(config.agents):
        agent = config.agents[name]
        stages = tuple(agent_stage.value for agent_stage in agent.stages)
        if stage in stages:
            reasons = _trigger_reasons(
                stage=stage,
                triggers=agent.triggers,
                fixture=fixture,
                memory_references=memory_references,
            )
            if not reasons:
                continue
            selected.append(
                SelectedReviewer(
                    name=name,
                    stage=stage,
                    reasons=tuple(reasons),
                )
            )
    return tuple(selected)


def _trigger_reasons(
    *,
    stage: str,
    triggers: ReviewerTriggers,
    fixture: FixturePR,
    memory_references: tuple[MemoryReference, ...],
) -> list[str]:
    reasons: list[str] = []
    gate_failures: list[str] = []
    changed_file_count = len(fixture.changed_files)
    changed_line_count = _changed_line_count(fixture)
    risk_level = _fixture_risk_level(fixture)

    if triggers.max_files is not None:
        if changed_file_count > triggers.max_files:
            gate_failures.append(f"{stage} triggers.max_files>{triggers.max_files}")
        else:
            reasons.append(f"{stage} triggers.max_files<={triggers.max_files}")
    if triggers.changed_files_min is not None:
        if changed_file_count < triggers.changed_files_min:
            gate_failures.append(f"{stage} triggers.changed_files_min<{triggers.changed_files_min}")
        else:
            reasons.append(f"{stage} triggers.changed_files_min={triggers.changed_files_min}")
    if triggers.changed_lines_min is not None:
        if changed_line_count < triggers.changed_lines_min:
            gate_failures.append(f"{stage} triggers.changed_lines_min<{triggers.changed_lines_min}")
        else:
            reasons.append(f"{stage} triggers.changed_lines_min={triggers.changed_lines_min}")
    if triggers.risk_min is not None:
        if _risk_rank(risk_level) < _risk_rank(triggers.risk_min.value):
            gate_failures.append(f"{stage} triggers.risk_min<{triggers.risk_min.value}")
        else:
            reasons.append(f"{stage} triggers.risk_min={triggers.risk_min.value}")
    if gate_failures:
        return []

    selector_reasons: list[str] = []
    if triggers.always is True:
        selector_reasons.append(f"{stage} triggers.always=true")
    for pattern in triggers.paths:
        if any(_path_matches(changed_file.path, pattern) for changed_file in fixture.changed_files):
            selector_reasons.append(f"{stage} triggers.paths={pattern}")
    patches = "\n".join(changed_file.patch or "" for changed_file in fixture.changed_files).casefold()
    for pattern in triggers.diff_patterns:
        if _diff_pattern_matches(patches, pattern):
            selector_reasons.append(f"{stage} triggers.diff_patterns={pattern}")
    labels = {label.casefold() for label in fixture.labels}
    for label in triggers.labels:
        if label.casefold() in labels:
            selector_reasons.append(f"{stage} triggers.labels={label}")
    trusted_memory = "\n".join(
        memory.body or ""
        for memory in memory_references
        if memory.actionable
    ).casefold()
    for pattern in triggers.conversation_patterns:
        if pattern.casefold() in trusted_memory:
            selector_reasons.append(f"{stage} triggers.conversation_patterns={pattern}")

    has_explicit_selector = any(
        (
            triggers.always,
            triggers.paths,
            triggers.labels,
            triggers.diff_patterns,
            triggers.conversation_patterns,
        )
    )
    if not has_explicit_selector and reasons:
        return reasons
    return selector_reasons + reasons if selector_reasons else []


def _path_matches(path: str, pattern: str) -> bool:
    return path == pattern or fnmatch(path, pattern) or path.startswith(pattern.rstrip("/") + "/")


def _diff_pattern_matches(casefolded_patch: str, pattern: str) -> bool:
    try:
        return re.search(pattern, casefolded_patch, flags=re.IGNORECASE) is not None
    except re.error:
        return pattern.casefold() in casefolded_patch


def _changed_line_count(fixture: FixturePR) -> int:
    return sum(
        changed_range.end - changed_range.start + 1
        for changed_file in fixture.changed_files
        for changed_range in changed_file.changed_ranges
    )


def _fixture_risk_level(fixture: FixturePR) -> str:
    changed_files = len(fixture.changed_files)
    changed_lines = _changed_line_count(fixture)
    patches = "\n".join(changed_file.patch or "" for changed_file in fixture.changed_files).casefold()
    if changed_files >= 10 or changed_lines >= 500 or any(term in patches for term in ("auth", "token", "password")):
        return "high"
    if changed_files >= 3 or changed_lines >= 50 or any(term in patches for term in ("billing", "product intent")):
        return "medium"
    return "low"


def _risk_rank(risk_level: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}[risk_level]


def _stage_transition_trace(
    *,
    active_stage_before: str | None,
    active_stage_after: str,
    stage_queue_before: list[str],
    stage_queue_after: list[str],
) -> dict[str, Any]:
    if active_stage_before is None:
        transition_reason = f"start_{active_stage_after}"
    else:
        transition_reason = f"complete_{active_stage_before}_start_{active_stage_after}"
    return {
        "active_stage_before": active_stage_before,
        "active_stage_after": active_stage_after,
        "suspended_stage_before": None,
        "suspended_stage_after": None,
        "stage_queue_before": list(stage_queue_before),
        "stage_queue_after": list(stage_queue_after),
        "transition_reason": transition_reason,
    }


def _review_target(fixture: FixturePR) -> ReviewTarget:
    target = fixture.target
    return ReviewTarget(
        owner_repo=target["owner_repo"],
        pr_number=target["pr_number"],
        base_sha=target["base_sha"],
        head_sha=target["head_sha"],
        merge_base_sha=target.get("merge_base_sha"),
        diff_basis=target["diff_basis"],
    )


def _truncation_notices(fixture: FixturePR) -> tuple[TruncationNotice, ...]:
    notices: list[TruncationNotice] = []
    for item in fixture.truncation:
        _require_fields(item, ("resource", "truncated", "note"), "truncation")
        notices.append(
            TruncationNotice(
                resource=_required_str(item, "resource", "truncation"),
                truncated=_required_bool(item, "truncated", "truncation"),
                note=_required_str(item, "note", "truncation"),
                original_count=_optional_int(item, "original_count", "truncation"),
                retained_count=_optional_int(item, "retained_count", "truncation"),
                original_bytes=_optional_int(item, "original_bytes", "truncation"),
                retained_bytes=_optional_int(item, "retained_bytes", "truncation"),
            )
        )
    return tuple(notices)


def _raw_outputs_by_key(fixture: FixturePR) -> dict[tuple[str, str], dict[str, Any]]:
    raw_outputs: dict[tuple[str, str], dict[str, Any]] = {}
    for reviewer_output in fixture.raw_reviewer_outputs:
        if not isinstance(reviewer_output, dict):
            raise RunnerError("raw_reviewer_outputs entries must be objects")
        reviewer = _required_str(reviewer_output, "reviewer", "raw_reviewer_outputs[]")
        stage = _required_str(reviewer_output, "stage", "raw_reviewer_outputs[]")
        if (reviewer, stage) in raw_outputs:
            raise RunnerError(f"raw reviewer output {reviewer}/{stage} is duplicated")
        if not isinstance(reviewer_output.get("items"), list):
            raise RunnerError("raw reviewer output requires reviewer, stage, and items")
        raw_outputs[(reviewer, stage)] = reviewer_output
    return raw_outputs


def _empty_classified_lists() -> dict[str, list[Any]]:
    return {
        "findings": [],
        "local_notes": [],
        "clarification_requests": [],
        "suggested_replies": [],
        "suppressed_outputs": [],
    }


def _classify_reviewer_output(
    fixture: FixturePR,
    *,
    reviewer_output: dict[str, Any],
    classified: dict[str, list[Any]],
) -> None:
    reviewer = _required_str(reviewer_output, "reviewer", "raw_reviewer_outputs[]")
    stage = _required_str(reviewer_output, "stage", "raw_reviewer_outputs[]")
    items = reviewer_output.get("items")
    if not isinstance(items, list):
        raise RunnerError("raw reviewer output requires reviewer, stage, and items")
    for item in items:
        if not isinstance(item, dict):
            raise RunnerError("raw reviewer output items must be objects")
        item_type = _required_str(item, "type", "raw reviewer output item")
        if item_type == "finding":
            raw_finding = _raw_reviewer_finding_or_suppression(item, classified)
            if raw_finding is None:
                continue
            finding = _classified_finding(
                fixture,
                reviewer=reviewer,
                stage=stage,
                raw_finding=raw_finding,
            )
            if _is_postable_finding(finding):
                classified["findings"].append(finding)
            else:
                classified["suppressed_outputs"].append(
                    SuppressedOutput(
                        id=finding.id,
                        reason="Finding candidate did not meet postable quality policy.",
                    )
                )
        elif item_type == "local_note":
            _require_fields(item, ("id", "title", "body", "evidence"), "local_note")
            classified["local_notes"].append(
                LocalNote(
                    id=_required_str(item, "id", "local_note"),
                    title=_required_str(item, "title", "local_note"),
                    body=_required_str(item, "body", "local_note"),
                    evidence=_required_str(item, "evidence", "local_note"),
                )
            )
        elif item_type == "clarification_request":
            _require_fields(item, ("id", "question", "why_it_matters"), "clarification_request")
            classified["clarification_requests"].append(
                ClarificationRequest(
                    id=_required_str(item, "id", "clarification_request"),
                    reviewer=reviewer,
                    question=_required_str(item, "question", "clarification_request"),
                    why_it_matters=_required_str(item, "why_it_matters", "clarification_request"),
                )
            )
        elif item_type == "suggested_reply":
            _require_fields(item, ("id", "source_comment_id", "proposed_body"), "suggested_reply")
            classified["suggested_replies"].append(
                SuggestedReply(
                    id=_required_str(item, "id", "suggested_reply"),
                    source_comment_id=_required_str(item, "source_comment_id", "suggested_reply"),
                    proposed_body=_required_str(item, "proposed_body", "suggested_reply"),
                )
            )
        elif item_type == "suppressed":
            _require_fields(item, ("id", "reason"), "suppressed")
            classified["suppressed_outputs"].append(
                SuppressedOutput(
                    id=_required_str(item, "id", "suppressed"),
                    reason=_required_str(item, "reason", "suppressed"),
                )
            )
        else:
            raise RunnerError(f"unsupported raw reviewer output type: {item_type}")


def _raw_reviewer_finding_or_suppression(
    item: dict[str, Any],
    classified: dict[str, list[Any]],
) -> RawReviewerFinding | None:
    try:
        return RawReviewerFinding.from_mapping(item)
    except ValueError as exc:
        message = str(exc)
        if "graph-owned fields" not in message:
            raise
        classified["suppressed_outputs"].append(
            SuppressedOutput(
                id=_safe_suppressed_raw_id(item),
                reason="Raw reviewer finding attempted to set graph-owned fields and was suppressed.",
            )
        )
        return None


def _safe_suppressed_raw_id(item: dict[str, Any]) -> str:
    item_id = item.get("id")
    if isinstance(item_id, str) and item_id:
        return f"suppressed-{item_id}"
    return "suppressed-invalid-raw-finding"


def _validate_finding_fingerprints(findings: tuple[ClassifiedFinding, ...]) -> None:
    seen: set[str] = set()
    for finding in findings:
        if redact_for_error(finding.fingerprint) != finding.fingerprint:
            raise RunnerError("postable_finding.fingerprint requires a non-secret stable identity")
        if finding.fingerprint in seen:
            raise RunnerError("postable_finding.fingerprint must be unique")
        seen.add(finding.fingerprint)


def _validate_output_item_ids(classified: dict[str, tuple[Any, ...]]) -> None:
    seen: set[str] = set()
    for collection in classified.values():
        for item in collection:
            item_id = item.id
            if redact_for_error(item_id) != item_id:
                raise RunnerError("classified output item ids require non-secret stable identities")
            if item_id in seen:
                raise RunnerError("classified output item ids must be unique")
            seen.add(item_id)


def _classified_finding(
    fixture: FixturePR,
    *,
    reviewer: str,
    stage: str,
    raw_finding: RawReviewerFinding,
) -> ClassifiedFinding:
    assert_changed_line(fixture, path=raw_finding.path, line=raw_finding.line)
    return ClassifiedFinding(
        id=raw_finding.id,
        source_reviewer=reviewer,
        source_stage=stage,
        title=raw_finding.title,
        body=raw_finding.rationale,
        evidence=raw_finding.evidence,
        path=raw_finding.path,
        line=raw_finding.line,
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
    if finding.confidence != Confidence.HIGH:
        return False
    if not _has_concrete_finding_evidence(finding.evidence):
        return False
    text = f"{finding.title}\n{finding.body}\n{finding.evidence}".casefold()
    if _is_testing_advice(finding, text):
        return _has_testing_finding_shape(text)
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


def _has_testing_finding_shape(text: str) -> bool:
    missing_coverage = (
        ("coverage" in text or "test" in text)
        and any(term in text for term in ("missing", "no ", "without", "lacks", "not covered", "does not cover"))
    )
    return (
        missing_coverage
        and _has_concrete_testing_shape(text)
        and not _has_only_vague_testing_scenario(text)
    )


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
    coverage_target = bool(re.search(r"\b(regression test|regression coverage|coverage|test)\b", text))
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


def _require_fields(data: dict[str, Any], fields: tuple[str, ...], label: str) -> None:
    for field in fields:
        if field not in data:
            raise RunnerError(f"{label}.{field} is required")


def _required_str(data: dict[str, Any], field: str, label: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise RunnerError(f"{label}.{field} is required")
    return value


def _required_int(data: dict[str, Any], field: str, label: str) -> int:
    value = data.get(field)
    if type(value) is not int:
        raise RunnerError(f"{label}.{field} must be an integer")
    return value


def _required_bool(data: dict[str, Any], field: str, label: str) -> bool:
    value = data.get(field)
    if type(value) is not bool:
        raise RunnerError(f"{label}.{field} must be a boolean")
    return value


def _local_verdict(
    *,
    findings: tuple[ClassifiedFinding, ...],
    clarification_requests: tuple[ClarificationRequest, ...],
) -> ReviewVerdict:
    if clarification_requests:
        return ReviewVerdict.NEEDS_CLARIFICATION
    if findings:
        return ReviewVerdict.COMMENT
    return ReviewVerdict.NO_FINDINGS


def _candidate_payload(
    *,
    enabled: bool,
    review_target: ReviewTarget,
    posting_plan: PostingPlan,
    findings: tuple[ClassifiedFinding, ...],
) -> CandidateIssueCommentPayload | None:
    if not enabled:
        return None
    return build_candidate_issue_comment_payload(
        review_target=review_target,
        posting_plan=posting_plan,
        findings=findings,
    )


def _local_only_posting_plan(posting_plan: PostingPlan) -> PostingPlan:
    return PostingPlan(
        items=tuple(
            item
            if not item.public_payload_eligible
            else PostingPlanItem(
                id=item.id,
                source_classification=item.source_classification,
                destination=PostingDestination.LOCAL_ONLY,
                public_payload_eligible=False,
                fingerprint=item.fingerprint,
                body=item.body,
            )
            for item in posting_plan.items
        )
    )


def _writer_call_count(writer_sentinel: object | None) -> int:
    if writer_sentinel is None:
        return 0
    value = getattr(writer_sentinel, "call_count", 0)
    if type(value) is not int:
        return 0
    return value


def _json_envelope(
    *,
    fixture: FixturePR,
    post_enabled: bool,
    local_verdict: ReviewVerdict,
    selected_reviewers: tuple[SelectedReviewer, ...],
    graph_trace: list[dict[str, Any]],
    writer_call_count: int,
    rendered: RenderedReview,
) -> dict[str, Any]:
    return _redact_json_value({
        "run_mode": "dry_run",
        "post_enabled": post_enabled,
        "fixture_id": fixture.id,
        "fixture_ref": fixture.pr_ref,
        "graph_trace": graph_trace,
        "local_verdict": local_verdict.value,
        "selected_reviewers": [
            {"name": reviewer.name, "stage": reviewer.stage, "reasons": list(reviewer.reasons)}
            for reviewer in selected_reviewers
        ],
        "side_effects": {
            "writer_called": writer_call_count > 0,
            "writer_call_count": writer_call_count,
        },
        "review": rendered.json_data,
    })


def _optional_int(data: dict[str, Any], field: str, label: str) -> int | None:
    value = data.get(field)
    if value is None:
        return None
    if type(value) is not int:
        raise RunnerError(f"{label}.{field} must be an integer or null")
    return value


def _redact_json_value(value: Any) -> Any:
    return redact_data(value).data
