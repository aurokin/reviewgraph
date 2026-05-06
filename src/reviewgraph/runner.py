from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from reviewgraph.fixtures import (
    ChangedFile,
    FixtureError,
    FixturePR,
    ReviewerConfig,
    assert_changed_line,
    load_fixture_pr,
    load_reviewer_config,
    redact_for_error,
)
from reviewgraph.context_budget import (
    BudgetedInputContext,
    apply_input_context_budget,
    apply_reviewer_budget,
    default_context_budget,
    merge_context_budgets,
    reviewer_key,
)
from reviewgraph.memory import build_conversation_memory
from reviewgraph.posting import canonical_json_hash
from reviewgraph.models import (
    ALLOWED_RAW_FINDING_EVIDENCE_SOURCES,
    ClarificationRequest,
    ClassifiedFinding,
    Confidence,
    ContextBudget,
    LocalNote,
    MemoryReference,
    PRConversationMemory,
    RawReviewerFinding,
    ReviewConfig,
    RiskAssessment,
    ReviewerRunKey,
    ReviewerRunStatus,
    ReviewerRunStatusValue,
    ReviewTarget,
    ReviewVerdict,
    ReviewState,
    RunMode,
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
from reviewgraph.risk import classify_change_risk, risk_assessment_to_json
from reviewgraph.routing import select_reviewers_for_active_stage
from reviewgraph.reviewer_runs import record_reviewer_run_status, reviewer_run_key_for_selection
from reviewgraph.state import StageCursor, StageCursorTransition, advance_or_finish_stage, initial_stage_cursor


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
    reviewer_run_keys: tuple[ReviewerRunKey, ...]
    reviewer_run_status: dict[str, ReviewerRunStatus]
    graph_trace: list[dict[str, Any]]
    classified: dict[str, tuple[Any, ...]]
    context_budget: ContextBudget


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
    context_budget_limits = config.context_budget or default_context_budget()
    budgeted_context = apply_input_context_budget(
        pr=fixture.pr,
        memory=conversation_memory,
        limits=context_budget_limits,
        existing_truncation=_truncation_notices(fixture),
    )
    memory_references = budgeted_context.memory.entries
    budgeted_fixture = _budgeted_fixture_view(fixture, budgeted_context)
    risk_assessment = classify_change_risk(fixture.pr)
    stage_run = _run_review_stages(
        config,
        budgeted_fixture,
        memory_references=memory_references,
        budget_limits=context_budget_limits,
        risk=risk_assessment,
        omitted_file_paths=budgeted_context.context_budget.omitted_file_paths,
    )
    selected_reviewers = stage_run.selected_reviewers
    graph_trace = stage_run.graph_trace
    review_target = _review_target(fixture)
    context_budget = merge_context_budgets(budgeted_context.context_budget, stage_run.context_budget)
    truncation_notices = context_budget.truncation
    classified = {
        **stage_run.classified,
        "local_notes": budgeted_context.local_notes + stage_run.classified["local_notes"],
    }
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
        context_budget=context_budget,
    )
    writer_call_count = _writer_call_count(writer_sentinel) - writer_call_count_before
    envelope = _json_envelope(
        fixture=fixture,
        post_enabled=post_enabled,
        local_verdict=local_verdict,
        risk=risk_assessment,
        selected_reviewers=selected_reviewers,
        reviewer_run_status=stage_run.reviewer_run_status,
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
    budget_limits: ContextBudget,
    risk: RiskAssessment,
    omitted_file_paths: tuple[str, ...] = (),
) -> _StageRunResult:
    raw_outputs_by_key = _raw_outputs_by_key(fixture)
    selected_reviewers: list[SelectedReviewer] = []
    graph_trace: list[dict[str, Any]] = []
    classified = _empty_classified_lists()
    seen_raw_keys: set[tuple[str, str]] = set()
    deferred_raw_keys: set[tuple[str, str]] = set()
    stage_budgets: list[ContextBudget] = []
    retained_reviewer_count = 0
    planned_live_calls = 0
    cursor = initial_stage_cursor()
    routing_state = _routing_review_state(
        config,
        fixture,
        memory_references=memory_references,
        context_budget=budget_limits,
        risk=risk,
    )
    clarification_needed = False

    while cursor.stage_queue:
        transition = advance_or_finish_stage(cursor)
        graph_trace.append(transition.to_json())
        if cursor.active_stage is None:
            raise RunnerError("stage cursor did not activate a review stage")
        routing_state.active_stage = cursor.active_stage
        routing_state.stage_queue = list(cursor.stage_queue)
        routing_state.completed_stages = list(cursor.completed_stages)
        stage = cursor.active_stage.value

        selected_stage_reviewers = select_reviewers_for_active_stage(routing_state)
        budgeted_reviewers = apply_reviewer_budget(
            reviewers=selected_stage_reviewers,
            limits=budget_limits,
            retained_reviewer_count=retained_reviewer_count,
            planned_live_calls=planned_live_calls,
        )
        stage_budgets.append(budgeted_reviewers.context_budget)
        deferred_raw_keys.update(budgeted_reviewers.deferred_keys)
        for reviewer in budgeted_reviewers.deferred_reviewers:
            _update_reviewer_status(
                routing_state,
                reviewer,
                status=ReviewerRunStatusValue.SKIPPED,
                reason="skipped by context budget before execution",
            )
        classified["local_notes"].extend(budgeted_reviewers.local_notes)
        stage_reviewers = budgeted_reviewers.retained_reviewers
        retained_reviewer_count += len(stage_reviewers)
        planned_live_calls += budgeted_reviewers.context_budget.planned_live_calls
        if stage == "initial_triage" and not stage_reviewers:
            raise RunnerError("reviewer config has no eligible initial_triage always-on reviewer")
        selected_reviewers.extend(selected_stage_reviewers)
        for reviewer in stage_reviewers:
            key = (reviewer.name, reviewer.stage)
            reviewer_output = raw_outputs_by_key.get(key)
            if reviewer_output is None:
                _update_reviewer_status(
                    routing_state,
                    reviewer,
                    status=ReviewerRunStatusValue.FAILED,
                    reason="missing raw reviewer output for selected reviewer",
                )
                if not _reviewer_is_required(config, reviewer):
                    classified["local_notes"].append(_optional_reviewer_failure_note(reviewer))
                    continue
                raise RunnerError(
                    "raw reviewer output was not selected; missing raw reviewer output for selected reviewer: "
                    f"{reviewer.name}/{reviewer.stage}"
                )
            seen_raw_keys.add(key)
            _update_reviewer_status(
                routing_state,
                reviewer,
                status=ReviewerRunStatusValue.RUNNING,
                reason="deterministic fixture output execution started",
            )
            try:
                _classify_reviewer_output(
                    fixture,
                    reviewer_output=reviewer_output,
                    classified=classified,
                    memory_references=memory_references,
                    omitted_file_paths=omitted_file_paths,
                )
            except RunnerError:
                _update_reviewer_status(
                    routing_state,
                    reviewer,
                    status=ReviewerRunStatusValue.FAILED,
                    reason="deterministic fixture output execution failed",
                )
                if not _reviewer_is_required(config, reviewer):
                    classified["local_notes"].append(_optional_reviewer_failure_note(reviewer))
                    continue
                raise
            _update_reviewer_status(
                routing_state,
                reviewer,
                status=ReviewerRunStatusValue.COMPLETED,
                reason="deterministic fixture output execution completed",
            )
        if classified["clarification_requests"]:
            clarification_needed = True
            break

    if clarification_needed:
        graph_trace.append(
            _stage_cursor_terminal_trace(
                cursor,
                transition_reason="clarification_needed_end",
            )
        )
    else:
        graph_trace.append(advance_or_finish_stage(cursor).to_json())

    extra_raw_keys = sorted(set(raw_outputs_by_key) - seen_raw_keys - deferred_raw_keys)
    if extra_raw_keys:
        extra = ", ".join(f"{reviewer}/{stage}" for reviewer, stage in extra_raw_keys)
        raise RunnerError(f"raw reviewer output was not selected: {extra}")
    return _StageRunResult(
        selected_reviewers=tuple(selected_reviewers),
        reviewer_run_keys=tuple(routing_state.reviewer_run_keys),
        reviewer_run_status=dict(routing_state.reviewer_run_status),
        graph_trace=graph_trace,
        classified={key: tuple(value) for key, value in classified.items()},
        context_budget=merge_context_budgets(budget_limits, *stage_budgets),
    )


def _stage_cursor_terminal_trace(cursor: StageCursor, *, transition_reason: str) -> dict[str, Any]:
    return StageCursorTransition(
        active_stage_before=cursor.active_stage,
        active_stage_after=cursor.active_stage,
        suspended_stage_before=cursor.suspended_stage,
        suspended_stage_after=cursor.suspended_stage,
        stage_queue_before=tuple(cursor.stage_queue),
        stage_queue_after=tuple(cursor.stage_queue),
        completed_stages_before=tuple(cursor.completed_stages),
        completed_stages_after=tuple(cursor.completed_stages),
        transition_reason=transition_reason,
    ).to_json()


def _routing_review_state(
    config: ReviewerConfig,
    fixture: FixturePR,
    *,
    memory_references: tuple[MemoryReference, ...],
    context_budget: ContextBudget,
    risk: RiskAssessment,
) -> ReviewState:
    return ReviewState(
        run_id=f"fixture-routing:{fixture.id}",
        run_mode=RunMode.DRY_RUN,
        post_enabled=False,
        pr_ref=fixture.pr_ref,
        review_target=_review_target(fixture),
        posting_target=None,
        pr=fixture.pr,
        conversation_memory=PRConversationMemory(entries=memory_references),
        read_gaps=[],
        config=config,
        config_hash=_review_config_hash(config),
        stage_queue=initial_stage_cursor().stage_queue,
        active_stage=None,
        suspended_stage=None,
        completed_stages=[],
        risk=risk,
        selected_reviewers=[],
        reviewer_run_keys=[],
        reviewer_run_status={},
        reviewer_results=[],
        context_budget=context_budget,
        redaction_status=None,
        findings=[],
        local_notes=[],
        suggested_replies=[],
        suppressed_outputs=[],
        clarification_requests=[],
        pending_clarification_ids=[],
        clarifications=[],
        clarification_status={},
        ranked_findings=[],
        local_verdict=None,
        rendered_markdown=None,
        posting_plan=None,
        actor_permission_gate=None,
        payload_validation=None,
        marker_reconciliation=None,
        finalization_status=None,
        candidate_github_payload=None,
        final_github_payload=None,
        candidate_payload_hash=None,
        final_payload_hash=None,
        approval=None,
        writer_result=None,
        errors=[],
    )


def _update_reviewer_status(
    review_state: ReviewState,
    reviewer: SelectedReviewer,
    *,
    status: ReviewerRunStatusValue,
    reason: str,
) -> None:
    run_key = reviewer_run_key_for_selection(review_state, reviewer)
    record_reviewer_run_status(
        review_state,
        run_key,
        status=status,
        reason=reason,
    )


def _reviewer_is_required(config: ReviewerConfig, reviewer: SelectedReviewer) -> bool:
    agent = config.agents.get(reviewer.name)
    return bool(agent.required) if agent is not None else False


def _optional_reviewer_failure_note(reviewer: SelectedReviewer) -> LocalNote:
    return LocalNote(
        id=f"note-reviewer-failure-{reviewer.stage}-{reviewer.name}",
        title="Optional reviewer failed",
        body=f"{reviewer.name} was selected for {reviewer.stage} but failed before producing usable output.",
        evidence=f"Trigger reasons: {', '.join(reviewer.reasons)}",
    )


def _review_config_hash(config: ReviewConfig) -> str:
    return canonical_json_hash(
        {
            "agents": {
                name: {
                    "capabilities": list(agent.capabilities),
                    "context": agent.context,
                    "model": agent.model,
                    "required": agent.required,
                    "stages": [stage.value for stage in agent.stages],
                    "tools": list(agent.tools),
                    "triggers": {
                        "always": agent.triggers.always,
                        "changed_files_min": agent.triggers.changed_files_min,
                        "changed_lines_min": agent.triggers.changed_lines_min,
                        "conversation_patterns": list(agent.triggers.conversation_patterns),
                        "diff_patterns": list(agent.triggers.diff_patterns),
                        "labels": list(agent.triggers.labels),
                        "max_files": agent.triggers.max_files,
                        "paths": list(agent.triggers.paths),
                        "risk_min": agent.triggers.risk_min.value if agent.triggers.risk_min else None,
                    },
                    "verdict_power": agent.verdict_power,
                }
                for name, agent in sorted(config.agents.items())
            },
            "trusted_bot_authors": list(config.trusted_bot_authors),
            "trusted_operator_authors": list(config.trusted_operator_authors),
            "context_budget": _context_budget_hash_payload(config.context_budget),
        }
    )


def _context_budget_hash_payload(context_budget: ContextBudget | None) -> dict[str, int] | None:
    if context_budget is None:
        return None
    return {
        "max_changed_files": context_budget.max_changed_files,
        "max_live_calls": context_budget.max_live_calls,
        "max_memory_bytes": context_budget.max_memory_bytes,
        "max_patch_bytes": context_budget.max_patch_bytes,
        "max_reviewers": context_budget.max_reviewers,
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


def _budgeted_fixture_view(fixture: FixturePR, budgeted_context: BudgetedInputContext) -> FixturePR:
    budgeted_files = {changed_file.path: changed_file for changed_file in budgeted_context.pr.changed_files}
    changed_files: list[ChangedFile] = []
    for original in fixture.changed_files:
        budgeted_file = budgeted_files.get(original.path)
        if budgeted_file is None:
            continue
        changed_files.append(
            replace(
                original,
                patch=budgeted_file.patch,
                additions=budgeted_file.additions,
                deletions=budgeted_file.deletions,
                status=budgeted_file.status,
                previous_path=budgeted_file.previous_path,
                patch_status=budgeted_file.patch_status,
            )
        )
    return replace(
        fixture,
        pr=budgeted_context.pr,
        changed_files=tuple(changed_files),
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
    memory_references: tuple[MemoryReference, ...],
    omitted_file_paths: tuple[str, ...] = (),
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
            if _finding_depends_on_omitted_context(
                fixture,
                raw_finding,
                omitted_file_paths=omitted_file_paths,
            ):
                classified["suppressed_outputs"].append(
                    SuppressedOutput(
                        id=raw_finding.id,
                        reason="Finding candidate referenced context omitted by context budget.",
                    )
                )
                continue
            finding = _classified_finding(
                fixture,
                reviewer=reviewer,
                stage=stage,
                raw_finding=raw_finding,
            )
            if _is_postable_finding(finding):
                if _finding_has_unsafe_evidence_provenance(
                    raw_finding,
                    memory_references=memory_references,
                ):
                    classified["suppressed_outputs"].append(
                        SuppressedOutput(
                            id=raw_finding.id,
                            reason="Finding candidate used passive or untrusted memory as evidence.",
                        )
                    )
                else:
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
            clarification_id = _required_str(item, "id", "clarification_request")
            question = _required_str(item, "question", "clarification_request")
            why_it_matters = _required_str(item, "why_it_matters", "clarification_request")
            if _raw_output_has_unsafe_evidence_provenance(
                item,
                memory_references=memory_references,
                text_values=(question, why_it_matters),
                require_provenance_with_passive_memory=True,
            ):
                classified["suppressed_outputs"].append(
                    SuppressedOutput(
                        id=clarification_id,
                        reason="Clarification request used passive or untrusted memory as evidence.",
                    )
                )
            else:
                classified["clarification_requests"].append(
                    ClarificationRequest(
                        id=clarification_id,
                        reviewer=reviewer,
                        question=question,
                        why_it_matters=why_it_matters,
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


def _finding_depends_on_omitted_context(
    fixture: FixturePR,
    raw_finding: RawReviewerFinding,
    *,
    omitted_file_paths: tuple[str, ...],
) -> bool:
    if raw_finding.path in omitted_file_paths:
        return True
    for changed_file in fixture.changed_files:
        if changed_file.path == raw_finding.path and changed_file.contains_line(raw_finding.line):
            return changed_file.patch_status != "available"
    return False


def _finding_has_unsafe_evidence_provenance(
    raw_finding: RawReviewerFinding,
    *,
    memory_references: tuple[MemoryReference, ...],
) -> bool:
    return _unsafe_evidence_provenance(
        evidence_sources=raw_finding.evidence_sources,
        evidence_memory_ids=raw_finding.evidence_memory_ids,
        memory_references=memory_references,
        text_values=(raw_finding.evidence,),
        require_provenance_with_passive_memory=False,
    )


def _raw_output_has_unsafe_evidence_provenance(
    item: dict[str, Any],
    *,
    memory_references: tuple[MemoryReference, ...],
    text_values: tuple[str, ...],
    require_provenance_with_passive_memory: bool,
) -> bool:
    evidence_sources = _optional_str_tuple(item, "evidence_sources", "raw reviewer output")
    _require_supported_evidence_sources(evidence_sources, "raw reviewer output evidence_sources")
    evidence_memory_ids = _optional_str_tuple(item, "evidence_memory_ids", "raw reviewer output")
    return _unsafe_evidence_provenance(
        evidence_sources=evidence_sources,
        evidence_memory_ids=evidence_memory_ids,
        memory_references=memory_references,
        text_values=text_values,
        require_provenance_with_passive_memory=require_provenance_with_passive_memory,
    )


def _unsafe_evidence_provenance(
    *,
    evidence_sources: tuple[str, ...],
    evidence_memory_ids: tuple[str, ...],
    memory_references: tuple[MemoryReference, ...],
    text_values: tuple[str, ...],
    require_provenance_with_passive_memory: bool,
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
    if _text_copies_passive_memory(text_values, memory_references=memory_references):
        return True
    if evidence_sources:
        return False
    return False


def _text_copies_passive_memory(
    text_values: tuple[str, ...],
    *,
    memory_references: tuple[MemoryReference, ...],
) -> bool:
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
        body = _normalized_provenance_text(memory.body)
        if len(body) < 30:
            continue
        for value in values:
            if value in body or body in value:
                return True
    return False


def _normalized_provenance_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _optional_str_tuple(data: dict[str, Any], field: str, label: str) -> tuple[str, ...]:
    if field not in data:
        return ()
    value = data[field]
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise RunnerError(f"{label}.{field} must be an array of non-empty strings")
    return tuple(value)


def _require_supported_evidence_sources(value: tuple[str, ...], field_name: str) -> None:
    invalid = [item for item in value if item not in ALLOWED_RAW_FINDING_EVIDENCE_SOURCES]
    if invalid:
        raise RunnerError(f"{field_name} contains unsupported values: {', '.join(sorted(invalid))}")


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
    risk: RiskAssessment,
    selected_reviewers: tuple[SelectedReviewer, ...],
    reviewer_run_status: dict[str, ReviewerRunStatus],
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
        "risk": risk_assessment_to_json(risk),
        "selected_reviewers": [
            {"name": reviewer.name, "stage": reviewer.stage, "reasons": list(reviewer.reasons)}
            for reviewer in selected_reviewers
        ],
        "reviewer_run_status": [
            {
                "key": key,
                "reviewer": status.run_key.reviewer,
                "stage": status.run_key.stage.value,
                "status": status.status.value,
            }
            for key, status in sorted(reviewer_run_status.items())
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
