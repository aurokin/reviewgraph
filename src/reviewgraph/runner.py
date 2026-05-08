from __future__ import annotations

import importlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from reviewgraph.fixtures import (
    ChangedFile,
    FixtureError,
    FixturePR,
    ReviewerConfig,
    load_fixture_pr,
    load_reviewer_config,
    redact_for_error,
)
from reviewgraph.clarification import (
    ClarificationGateResult,
    evaluate_clarification_gate,
    ingest_clarification_answer,
)
from reviewgraph.context_budget import (
    BudgetedInputContext,
    apply_input_context_budget,
    apply_reviewer_budget,
    default_context_budget,
    merge_context_budgets,
    reviewer_key,
)
from reviewgraph.diff_anchor import attach_diff_anchors
from reviewgraph.hashing import canonical_json_hash
from reviewgraph.memory import build_conversation_memory
from reviewgraph.models import (
    ClarificationRequest,
    ClarificationAnswer,
    ClassifiedFinding,
    ContextBudget,
    GateStatus,
    GraphError,
    LiveLLMConfig,
    LocalNote,
    MemoryReference,
    PRConversationMemory,
    ReviewConfig,
    ReviewerResult,
    RiskAssessment,
    ReviewerRunKey,
    ReviewerRunStatus,
    ReviewerRunStatusValue,
    ReviewTarget,
    ReviewVerdict,
    ReviewState,
    RunMode,
    SelectedReviewer,
    TruncationNotice,
    RedactionStatus,
    PostInteractionGateResult,
)
from reviewgraph.posting import (
    CandidateIssueCommentPayload,
    PostingDestination,
    PostingPlan,
    PostingPlanItem,
    build_candidate_issue_comment_payload,
    build_posting_plan,
)
from reviewgraph.post_interaction import (
    NON_INTERACTIVE_POST_MODE_ERROR_CODE,
    PostModeInteractionContext,
    evaluate_post_mode_interaction_gate,
)
from reviewgraph.quality import classify_review_quality
from reviewgraph.redaction import redact_data
from reviewgraph.read_gaps import FailClosedReadOutcome
from reviewgraph.render import RenderedReview, render_review
from reviewgraph.risk import classify_change_risk, risk_assessment_to_json
from reviewgraph.routing import select_reviewers_for_active_stage
from reviewgraph.reviewer_context import build_reviewer_context_package
from reviewgraph.reviewer_runs import record_reviewer_run_status, reviewer_run_key_for_selection
from reviewgraph.reviewers import FakeReviewerAdapter, execute_fake_reviewer, fake_registry_from_fixture_outputs
from reviewgraph.state import StageCursor, StageCursorTransition, advance_or_finish_stage, initial_stage_cursor
from reviewgraph.verdict import compute_local_verdict, compute_post_enabled


class RunnerError(ValueError):
    pass


@dataclass(frozen=True)
class DryRunResult:
    markdown: str
    json_data: dict[str, Any]
    rendered: RenderedReview
    writer_call_count: int


@dataclass(frozen=True)
class _DryRunInput:
    source_type: str
    source_id: str
    source_ref: str
    pr: Any
    review_target: ReviewTarget
    changed_files: tuple[Any, ...]
    raw_reviewer_outputs: tuple[dict[str, Any], ...]
    truncation: tuple[TruncationNotice, ...] = ()
    github_read: dict[str, Any] | None = None


@dataclass(frozen=True)
class _StageRunResult:
    selected_reviewers: tuple[SelectedReviewer, ...]
    reviewer_run_keys: tuple[ReviewerRunKey, ...]
    reviewer_run_status: dict[str, ReviewerRunStatus]
    reviewer_results: tuple[ReviewerResult, ...]
    errors: tuple[GraphError, ...]
    graph_trace: list[dict[str, Any]]
    classified: dict[str, tuple[Any, ...]]
    context_budget: ContextBudget
    clarification_gate: ClarificationGateResult
    live_llm_ledger: dict[str, object] | None = None
    live_llm_policy_audits: tuple[dict[str, object], ...] = ()


def run_fixture_dry_run(
    *,
    fixture_ref: str,
    reviewer_config_path: str | None = None,
    writer_sentinel: object | None = None,
    clarification_answers: tuple[ClarificationAnswer, ...] = (),
    live_llm_settings: Mapping[str, object] | None = None,
    live_llm_transport: object | None = None,
    live_llm_opt_in_source: str | None = None,
) -> DryRunResult:
    writer_call_count_before = _writer_call_count(writer_sentinel)
    fixture = load_fixture_pr(fixture_ref)
    config = load_reviewer_config(reviewer_config_path)
    config = _config_with_live_settings(config, live_llm_settings)
    return _run_dry_run_core(
        dry_run_input=_input_from_fixture(fixture),
        config=config,
        writer_call_count_before=writer_call_count_before,
        writer_sentinel=writer_sentinel,
        clarification_answers=clarification_answers,
        live_llm_transport=live_llm_transport,
        live_llm_opt_in_source=live_llm_opt_in_source,
    )


def run_fixture_non_interactive_post_attempt(
    *,
    fixture_ref: str,
    reviewer_config_path: str | None = None,
    writer_sentinel: object | None = None,
    non_interactive_reason: str = "non_tty_cli",
    approval_prompt: Callable[[], object] | None = None,
    final_payload_builder: Callable[[], object] | None = None,
) -> DryRunResult:
    del approval_prompt
    del final_payload_builder
    dry_run = run_fixture_dry_run(
        fixture_ref=fixture_ref,
        reviewer_config_path=reviewer_config_path,
        writer_sentinel=writer_sentinel,
    )
    gate = evaluate_post_mode_interaction_gate(
        PostModeInteractionContext(
            run_mode=RunMode.POST,
            interactive=False,
            reason=non_interactive_reason,
        )
    )
    error = GraphError(
        code=NON_INTERACTIVE_POST_MODE_ERROR_CODE,
        message=(
            "Non-interactive post mode requires a future explicit approval policy; "
            "CI, webhook, config-only, and non-TTY CLI contexts cannot approve or post by configuration alone."
        ),
        retryable=False,
    )
    return _non_interactive_post_result(dry_run=dry_run, gate=gate, error=error)


def _fail_closed_dry_run_result(*, outcome: FailClosedReadOutcome, writer_call_count: int) -> DryRunResult:
    outcome_data = outcome.to_dict()
    review_target = outcome_data.get("review_target")
    pr_ref = outcome_data.get("pr_ref")
    source_ref = _github_source_ref(pr_ref)
    review_data = {
        "review_target": review_target,
        "selected_reviewers": [],
        "classified_output": {
            "postable_findings": [],
            "local_notes": [],
            "clarification_requests": [],
            "suggested_replies": [],
            "suppressed": [],
            "suppressed_count": 0,
        },
        "local_verdict": None,
        "posting_plan": None,
        "memory": [],
        "read_gaps": outcome_data["read_gaps"],
        "errors": outcome_data["errors"],
        "truncation": [],
        "context_budget": None,
        "candidate_payload_preview": None,
        "public_payload_preparation": {
            "status": "not_prepared",
            "reason_code": "blocked_by_graph_error",
            "public_payload_item_count": 0,
            "candidate_payload_present": False,
        },
        "redaction_status": outcome_data["redaction_status"],
    }
    data = _redact_json_value({
        "run_mode": "dry_run",
        "post_enabled": False,
        "source_type": "github",
        "source_id": source_ref,
        "source_ref": source_ref,
        "github_read": outcome_data,
        "partial_review": {
            "has_partial_review": False,
            "failed_optional_reviewers": [],
        },
        "graph_trace": outcome_data["graph_trace"],
        "local_verdict": None,
        "pending_clarification_ids": [],
        "blocking_clarification_ids": [],
        "clarification_status": {},
        "errors": outcome_data["errors"],
        "read_gaps": outcome_data["read_gaps"],
        "page_gap_descriptors": outcome_data["page_gap_descriptors"],
        "selected_reviewers": [],
        "reviewer_run_status": [],
        "reviewer_results": [],
        "findings": [],
        "posting_plan": None,
        "candidate_payload_preview": None,
        "public_payload_preparation": review_data["public_payload_preparation"],
        "side_effects": {
            "writer_called": writer_call_count > 0,
            "writer_call_count": writer_call_count,
        },
        "review": review_data,
        "redaction_status": outcome_data["redaction_status"],
    })
    redaction_status = _redaction_status_from_json(data.get("redaction_status"))
    rendered = RenderedReview(
        markdown=_fail_closed_markdown(data),
        json_data=review_data,
        redaction_status=redaction_status,
    )
    return DryRunResult(
        markdown=rendered.markdown,
        json_data=data,
        rendered=rendered,
        writer_call_count=writer_call_count,
    )


def _run_dry_run_core(
    *,
    dry_run_input: _DryRunInput,
    config: ReviewerConfig,
    writer_call_count_before: int,
    writer_sentinel: object | None,
    clarification_answers: tuple[ClarificationAnswer, ...] = (),
    live_llm_transport: object | None = None,
    live_llm_opt_in_source: str | None = None,
) -> DryRunResult:
    if live_llm_transport is not None and live_llm_opt_in_source is None:
        raise RunnerError("live LLM execution requires an explicit opt-in source")
    if live_llm_opt_in_source is not None and live_llm_transport is None:
        raise RunnerError("live LLM execution requires an injected live transport")
    conversation_memory = build_conversation_memory(
        dry_run_input.pr,
        trusted_operator_authors=set(config.trusted_operator_authors),
        trusted_bot_authors=set(config.trusted_bot_authors),
    )
    context_budget_limits = config.context_budget or default_context_budget()
    budgeted_context = apply_input_context_budget(
        pr=dry_run_input.pr,
        memory=conversation_memory,
        limits=context_budget_limits,
        existing_truncation=dry_run_input.truncation,
    )
    memory_references = budgeted_context.memory.entries
    budgeted_input = _budgeted_dry_run_input_view(dry_run_input, budgeted_context)
    risk_assessment = classify_change_risk(dry_run_input.pr)
    stage_run = _run_review_stages(
        config,
        budgeted_input,
        memory_references=memory_references,
        budget_limits=context_budget_limits,
        budgeted_context=budgeted_context,
        risk=risk_assessment,
        omitted_file_paths=budgeted_context.context_budget.omitted_file_paths,
        omitted_memory_ids=budgeted_context.context_budget.omitted_memory_ids,
        clarification_answers=clarification_answers,
        live_llm_transport=live_llm_transport,
        live_llm_opt_in_source=live_llm_opt_in_source,
    )
    selected_reviewers = stage_run.selected_reviewers
    graph_trace = stage_run.graph_trace
    review_target = dry_run_input.review_target
    context_budget = merge_context_budgets(budgeted_context.context_budget, stage_run.context_budget)
    truncation_notices = context_budget.truncation
    classified = {
        **stage_run.classified,
        "local_notes": budgeted_context.local_notes + stage_run.classified["local_notes"],
    }
    classified["findings"] = attach_diff_anchors(
        changed_files=budgeted_input.changed_files,
        review_target=review_target,
        findings=classified["findings"],
    )
    _validate_output_item_ids(classified)
    _validate_finding_fingerprints(classified["findings"])
    clarification_gate = evaluate_clarification_gate(classified["clarification_requests"])
    partial_review = _partial_review_metadata(
        config=config,
        reviewer_results=stage_run.reviewer_results,
    )
    local_verdict = compute_local_verdict(
        findings=classified["findings"],
        clarification_gate=clarification_gate,
        reviewer_verdict_powers={
            name: agent.verdict_power
            for name, agent in config.agents.items()
        },
    )
    post_enabled = compute_post_enabled(
        errors=stage_run.errors,
        clarification_gate=clarification_gate,
        local_verdict=local_verdict,
        findings=classified["findings"],
    )
    posting_plan = build_posting_plan(
        findings=classified["findings"],
        review_target=review_target,
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
        dry_run_input=budgeted_input,
        post_enabled=post_enabled,
        local_verdict=local_verdict,
        risk=risk_assessment,
        selected_reviewers=selected_reviewers,
        reviewer_run_status=stage_run.reviewer_run_status,
        reviewer_results=stage_run.reviewer_results,
        errors=stage_run.errors,
        graph_trace=graph_trace,
        writer_call_count=writer_call_count,
        rendered=rendered,
        clarification_gate=clarification_gate,
        partial_review=partial_review,
        live_llm_ledger=stage_run.live_llm_ledger,
        live_llm_policy_audits=stage_run.live_llm_policy_audits,
    )
    return DryRunResult(
        markdown=rendered.markdown,
        json_data=envelope,
        rendered=rendered,
        writer_call_count=writer_call_count,
    )


def _run_review_stages(
    config: ReviewerConfig,
    dry_run_input: _DryRunInput,
    *,
    memory_references: tuple[MemoryReference, ...],
    budget_limits: ContextBudget,
    budgeted_context: BudgetedInputContext,
    risk: RiskAssessment,
    omitted_file_paths: tuple[str, ...] = (),
    omitted_memory_ids: tuple[str, ...] = (),
    clarification_answers: tuple[ClarificationAnswer, ...] = (),
    live_llm_transport: object | None = None,
    live_llm_opt_in_source: str | None = None,
) -> _StageRunResult:
    answers_by_request_id = {
        answer.request_id: answer
        for answer in clarification_answers
    }
    raw_outputs_by_key = _raw_outputs_by_key(dry_run_input)
    fake_adapter = FakeReviewerAdapter(
        fixture_id=dry_run_input.source_id,
        registry=fake_registry_from_fixture_outputs(
            fixture_id=dry_run_input.source_id,
            outputs=dry_run_input.raw_reviewer_outputs,
        ),
    )
    selected_reviewers: list[SelectedReviewer] = []
    graph_trace: list[dict[str, Any]] = []
    classified = _empty_classified_lists()
    errors: list[GraphError] = []
    seen_raw_keys: set[tuple[str, str]] = set()
    deferred_raw_keys: set[tuple[str, str]] = set()
    stage_budgets: list[ContextBudget] = []
    retained_reviewer_count = 0
    planned_live_calls = 0
    live_enabled = config.live_llm is not None and live_llm_transport is not None
    live_attempt_cost = _effective_live_attempts(config.live_llm) if live_enabled and config.live_llm is not None else 0
    if live_enabled and live_llm_opt_in_source is None:
        raise RunnerError("live LLM execution requires an explicit opt-in source")
    live_opt_in_source = live_llm_opt_in_source
    live_ledger = None
    live_policy_audits: list[dict[str, object]] = []
    cursor = initial_stage_cursor()
    routing_state = _routing_review_state(
        config,
        dry_run_input,
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
        routing_state.suspended_stage = cursor.suspended_stage
        routing_state.stage_queue = list(cursor.stage_queue)
        routing_state.completed_stages = list(cursor.completed_stages)
        routing_state.ready_clarification_ids = list(cursor.ready_clarification_ids)
        routing_state.active_clarification_id = cursor.active_clarification_id
        if transition.transition_reason.startswith("finish_clarification_review_restore_"):
            continue
        stage = cursor.active_stage.value

        selected_stage_reviewers = select_reviewers_for_active_stage(routing_state)
        live_call_costs = (
            {
                reviewer_key(reviewer): live_attempt_cost
                for reviewer in selected_stage_reviewers
            }
            if live_enabled and config.live_llm is not None
            else None
        )
        budgeted_reviewers = apply_reviewer_budget(
            reviewers=selected_stage_reviewers,
            limits=budget_limits,
            live_call_costs=live_call_costs,
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
        if stage == "initial_triage" and not stage_reviewers and not selected_stage_reviewers:
            raise RunnerError("reviewer config has no eligible initial_triage always-on reviewer")
        selected_reviewers.extend(selected_stage_reviewers)
        for reviewer in stage_reviewers:
            key = (reviewer.name, reviewer.stage)
            _update_reviewer_status(
                routing_state,
                reviewer,
                status=ReviewerRunStatusValue.RUNNING,
                reason=(
                    "live LLM reviewer execution started"
                    if live_enabled
                    else "deterministic fixture output execution started"
                ),
            )
            package = build_reviewer_context_package(
                active_stage=stage,
                reviewer=reviewer,
                reviewer_config=config.agents.get(reviewer.name),
                budgeted_context=budgeted_context,
            )
            run_key = reviewer_run_key_for_selection(routing_state, reviewer)
            if live_enabled:
                if config.live_llm is None:
                    raise RunnerError("live LLM config is required for live execution")
                llm_module = importlib.import_module("reviewgraph.llm")
                llm_policy_module = importlib.import_module("reviewgraph.llm_policy")
                if live_ledger is None:
                    live_ledger = llm_policy_module.LiveLLMBudgetLedger()
                provider = config.live_llm.provider
                model = config.live_llm.model or package.reviewer_config.model
                live_result = llm_module.run_live_llm_reviewer_with_retries(
                    package=package,
                    initial_run_key=run_key,
                    policy_input=llm_policy_module.LiveLLMPolicyInput(
                        reviewer_run_key=run_key,
                        live_llm_enabled=True,
                        live_llm_opt_in_source=live_opt_in_source,
                        provider=provider,
                        model=model,
                    ),
                    ledger=live_ledger,
                    transport=live_llm_transport,
                    max_attempts=config.live_llm.max_attempts,
                    timeout_seconds=config.live_llm.timeout_seconds,
                    total_timeout_seconds=config.live_llm.total_timeout_seconds,
                )
                live_ledger = live_result.ledger
                routing_state.live_llm_ledger = live_ledger.to_ordered_dict()
                graph_trace.extend(live_result.trace_events)
                for attempt in live_result.attempts:
                    live_policy_audits.append(attempt.policy_result.to_audit_dict())
                    routing_state.reviewer_results.append(attempt.reviewer_result)
                    record_reviewer_run_status(
                        routing_state,
                        attempt.reviewer_result.run_key,
                        status=attempt.reviewer_result.status,
                        reason=_reviewer_result_error(
                            attempt.reviewer_result,
                            default="live LLM reviewer execution completed",
                        ),
                    )
                reviewer_result = live_result.final_result
            else:
                reviewer_result = execute_fake_reviewer(
                    adapter=fake_adapter,
                    package=package,
                    run_key=run_key,
                )
                routing_state.reviewer_results.append(reviewer_result)
            if key in raw_outputs_by_key:
                seen_raw_keys.add(key)
            if reviewer_result.status != ReviewerRunStatusValue.COMPLETED:
                if key not in raw_outputs_by_key:
                    extra_raw_keys = sorted(set(raw_outputs_by_key) - seen_raw_keys - deferred_raw_keys)
                    if extra_raw_keys:
                        extra = ", ".join(f"{reviewer}/{stage}" for reviewer, stage in extra_raw_keys)
                        raise RunnerError(f"raw reviewer output was not selected: {extra}")
                reason = _reviewer_result_error(reviewer_result, default="fake reviewer execution failed")
                _update_reviewer_status(
                    routing_state,
                    reviewer,
                    status=ReviewerRunStatusValue.FAILED,
                    reason=reason,
                )
                if not _reviewer_is_required(config, reviewer):
                    classified["local_notes"].append(_optional_reviewer_failure_note(reviewer))
                    continue
                if (
                    _reviewer_result_is_explicit_failure(reviewer_result)
                    or _reviewer_result_is_repair_exhausted(reviewer_result)
                    or reviewer_result.live_llm_evidence is not None
                    or live_enabled
                ):
                    errors.append(_required_reviewer_failure_error(reviewer, reason=reason))
                    classified["local_notes"].append(_required_reviewer_failure_note(reviewer, reason=reason))
                    continue
                raise RunnerError(reason)
            try:
                _classify_normalized_reviewer_output(
                    dry_run_input,
                    reviewer_result=reviewer_result,
                    classified=classified,
                    memory_references=memory_references,
                    omitted_file_paths=omitted_file_paths,
                    omitted_memory_ids=omitted_memory_ids,
                )
            except RunnerError as exc:
                reason = str(exc)
                routing_state.reviewer_results[-1] = replace(
                    reviewer_result,
                    status=ReviewerRunStatusValue.FAILED,
                    errors=(reason,),
                )
                _update_reviewer_status(
                    routing_state,
                    reviewer,
                    status=ReviewerRunStatusValue.FAILED,
                    reason=reason,
                )
                if not _reviewer_is_required(config, reviewer):
                    classified["local_notes"].append(_optional_reviewer_failure_note(reviewer))
                    continue
                raise
            _update_reviewer_status(
                routing_state,
                reviewer,
                status=ReviewerRunStatusValue.COMPLETED,
                reason=(
                    "live LLM reviewer execution completed"
                    if live_enabled
                    else "deterministic fixture output execution completed"
                ),
            )
        clarification_gate = evaluate_clarification_gate(classified["clarification_requests"])
        if clarification_gate.blocks_posting:
            answered = _ingest_available_clarification_answers(
                routing_state,
                classified=classified,
                clarification_gate=clarification_gate,
                answers_by_request_id=answers_by_request_id,
            )
            if answered:
                cursor.ready_clarification_ids = list(routing_state.ready_clarification_ids)
                continue
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

    ignored_raw_stages = {stage.value for stage in cursor.stage_queue} if clarification_needed else set()
    extra_raw_keys = sorted(
        key
        for key in set(raw_outputs_by_key) - seen_raw_keys - deferred_raw_keys
        if key[1] not in ignored_raw_stages
    )
    if extra_raw_keys:
        extra = ", ".join(f"{reviewer}/{stage}" for reviewer, stage in extra_raw_keys)
        raise RunnerError(f"raw reviewer output was not selected: {extra}")
    return _StageRunResult(
        selected_reviewers=tuple(selected_reviewers),
        reviewer_run_keys=tuple(routing_state.reviewer_run_keys),
        reviewer_run_status=dict(routing_state.reviewer_run_status),
        reviewer_results=tuple(routing_state.reviewer_results),
        errors=tuple(errors),
        graph_trace=graph_trace,
        classified={key: tuple(value) for key, value in classified.items()},
        context_budget=merge_context_budgets(budget_limits, *stage_budgets),
        clarification_gate=evaluate_clarification_gate(classified["clarification_requests"]),
        live_llm_ledger=routing_state.live_llm_ledger,
        live_llm_policy_audits=tuple(live_policy_audits),
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


def _ingest_available_clarification_answers(
    review_state: ReviewState,
    *,
    classified: dict[str, list[Any]],
    clarification_gate: ClarificationGateResult,
    answers_by_request_id: dict[str, ClarificationAnswer],
) -> bool:
    answered = False
    review_state.clarification_requests = list(classified["clarification_requests"])
    review_state.pending_clarification_ids = list(clarification_gate.pending_ids)
    review_state.clarification_status = dict(clarification_gate.status)
    for request_id in clarification_gate.blocking_pending_ids:
        answer = answers_by_request_id.get(request_id)
        if answer is None:
            continue
        ingest_clarification_answer(review_state, answer)
        answered = True
    if answered:
        classified["clarification_requests"] = list(review_state.clarification_requests)
    return answered


def _routing_review_state(
    config: ReviewerConfig,
    dry_run_input: _DryRunInput,
    *,
    memory_references: tuple[MemoryReference, ...],
    context_budget: ContextBudget,
    risk: RiskAssessment,
) -> ReviewState:
    return ReviewState(
        run_id=f"{dry_run_input.source_type}-routing:{dry_run_input.source_id}",
        run_mode=RunMode.DRY_RUN,
        post_enabled=False,
        pr_ref=dry_run_input.source_ref,
        review_target=dry_run_input.review_target,
        posting_target=None,
        pr=dry_run_input.pr,
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
        live_llm_ledger=None,
        live_llm_policy_audits=[],
        context_budget=context_budget,
        redaction_status=None,
        findings=[],
        local_notes=[],
        suggested_replies=[],
        suppressed_outputs=[],
        clarification_requests=[],
        pending_clarification_ids=[],
        ready_clarification_ids=[],
        active_clarification_id=None,
        clarifications=[],
        clarification_status={},
        ranked_findings=[],
        local_verdict=None,
        rendered_markdown=None,
        posting_plan=None,
        post_interaction_gate=None,
        writer_release_preflight=None,
        actor_permission_gate=None,
        actor_permission_finalization_check=None,
        target_freshness_check=None,
        payload_validation=None,
        marker_reconciliation=None,
        finalization_status=None,
        candidate_github_payload=None,
        final_github_payload=None,
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


def _required_reviewer_failure_note(reviewer: SelectedReviewer, *, reason: str) -> LocalNote:
    return LocalNote(
        id=f"note-required-reviewer-failure-{reviewer.stage}-{reviewer.name}",
        title="Required reviewer failed",
        body=f"{reviewer.name} was selected for {reviewer.stage} but failed: {reason}",
        evidence=f"Trigger reasons: {', '.join(reviewer.reasons)}",
    )


def _required_reviewer_failure_error(reviewer: SelectedReviewer, *, reason: str) -> GraphError:
    return GraphError(
        code="required_reviewer_failed",
        message=f"Required reviewer {reviewer.name} failed during {reviewer.stage}: {reason}",
        retryable=False,
    )


def _reviewer_result_error(reviewer_result: ReviewerResult, *, default: str) -> str:
    return reviewer_result.errors[0] if reviewer_result.errors else default


def _reviewer_result_has_classifiable_raw_output(reviewer_result: ReviewerResult) -> bool:
    return (
        isinstance(reviewer_result.raw_output, Mapping)
        and "items" in reviewer_result.raw_output
        and reviewer_result.raw_output.get("failure") is not True
    )


def _reviewer_result_is_explicit_failure(reviewer_result: ReviewerResult) -> bool:
    raw_output = _reviewer_result_raw_output_mapping(reviewer_result)
    return raw_output is not None and raw_output.get("failure") is True


def _reviewer_result_raw_output_mapping(reviewer_result: ReviewerResult) -> Mapping[str, object] | None:
    if isinstance(reviewer_result.raw_output, Mapping):
        return reviewer_result.raw_output
    if not isinstance(reviewer_result.raw_output, str):
        return None
    try:
        parsed = json.loads(reviewer_result.raw_output)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, Mapping) else None


def _reviewer_result_is_repair_exhausted(reviewer_result: ReviewerResult) -> bool:
    return (
        reviewer_result.repair_record is not None
        and reviewer_result.repair_record.status == "failed"
    )


def _config_with_live_settings(
    config: ReviewerConfig,
    settings: Mapping[str, object] | None,
) -> ReviewerConfig:
    if settings is None:
        return config
    provider = _optional_setting_str(settings, "provider") or (config.live_llm.provider if config.live_llm else None)
    model = _optional_setting_str(settings, "model") or (config.live_llm.model if config.live_llm else None)
    max_attempts = _positive_setting_int(
        settings,
        "max_attempts",
        config.live_llm.max_attempts if config.live_llm else 2,
    )
    timeout_seconds = _positive_setting_int(
        settings,
        "timeout_seconds",
        config.live_llm.timeout_seconds if config.live_llm else 30,
    )
    total_timeout_seconds = _positive_setting_int(
        settings,
        "total_timeout_seconds",
        config.live_llm.total_timeout_seconds if config.live_llm else 120,
    )
    max_live_calls = _non_negative_setting_int(
        settings,
        "max_live_calls",
        config.live_llm.max_live_calls if config.live_llm else None,
    )
    live_config = LiveLLMConfig(
        provider=provider,
        model=model,
        max_attempts=max_attempts,
        timeout_seconds=timeout_seconds,
        total_timeout_seconds=total_timeout_seconds,
        max_live_calls=max_live_calls,
    )
    context_budget = config.context_budget or default_context_budget()
    if max_live_calls is not None:
        context_budget = replace(context_budget, max_live_calls=max_live_calls)
    return replace(config, context_budget=context_budget, live_llm=live_config)


def _effective_live_attempts(config: LiveLLMConfig) -> int:
    if config.total_timeout_seconds < config.timeout_seconds:
        raise RunnerError("live LLM total_timeout_seconds must be greater than or equal to timeout_seconds")
    return max(1, min(config.max_attempts, config.total_timeout_seconds // config.timeout_seconds))


def _optional_setting_str(settings: Mapping[str, object], name: str) -> str | None:
    value = settings.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise RunnerError(f"live LLM setting {name} must be a non-empty string")
    return value


def _positive_setting_int(settings: Mapping[str, object], name: str, default: int) -> int:
    value = settings.get(name, default)
    if type(value) is not int or value <= 0:
        raise RunnerError(f"live LLM setting {name} must be a positive integer")
    return value


def _non_negative_setting_int(
    settings: Mapping[str, object],
    name: str,
    default: int | None,
) -> int | None:
    value = settings.get(name, default)
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise RunnerError(f"live LLM setting {name} must be a non-negative integer")
    return value


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
            "live_llm": config.live_llm.to_ordered_dict() if config.live_llm is not None else None,
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


def _input_from_fixture(fixture: FixturePR) -> _DryRunInput:
    return _DryRunInput(
        source_type="fixture",
        source_id=fixture.id,
        source_ref=fixture.pr_ref,
        pr=fixture.pr,
        review_target=fixture.review_target,
        changed_files=fixture.changed_files,
        raw_reviewer_outputs=fixture.raw_reviewer_outputs,
        truncation=_truncation_notices(fixture),
    )


def _budgeted_dry_run_input_view(
    dry_run_input: _DryRunInput,
    budgeted_context: BudgetedInputContext,
) -> _DryRunInput:
    budgeted_files = {changed_file.path: changed_file for changed_file in budgeted_context.pr.changed_files}
    changed_files: list[Any] = []
    for original in dry_run_input.changed_files:
        budgeted_file = budgeted_files.get(original.path)
        if budgeted_file is None:
            continue
        if isinstance(original, ChangedFile):
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
        else:
            changed_files.append(original)
    return replace(
        dry_run_input,
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


def _raw_outputs_by_key(dry_run_input: _DryRunInput) -> dict[tuple[str, str], dict[str, Any]]:
    raw_outputs: dict[tuple[str, str], dict[str, Any]] = {}
    for reviewer_output in dry_run_input.raw_reviewer_outputs:
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


def _classify_normalized_reviewer_output(
    dry_run_input: _DryRunInput,
    *,
    reviewer_result: ReviewerResult,
    classified: dict[str, list[Any]],
    memory_references: tuple[MemoryReference, ...],
    omitted_file_paths: tuple[str, ...] = (),
    omitted_memory_ids: tuple[str, ...] = (),
) -> None:
    result = classify_review_quality(
        changed_files=dry_run_input.changed_files,
        reviewer_result=reviewer_result,
        memory_references=memory_references,
        omitted_file_paths=omitted_file_paths,
        omitted_memory_ids=omitted_memory_ids,
    )
    classified["findings"].extend(result.findings)
    classified["local_notes"].extend(result.local_notes)
    classified["clarification_requests"].extend(result.clarification_requests)
    classified["suggested_replies"].extend(result.suggested_replies)
    classified["suppressed_outputs"].extend(result.suppressed_outputs)


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


def _partial_review_metadata(
    *,
    config: ReviewerConfig,
    reviewer_results: tuple[ReviewerResult, ...],
) -> dict[str, Any]:
    failed_optional_reviewers: list[dict[str, Any]] = []
    terminal_results: dict[tuple[str, str, str | None], ReviewerResult] = {}
    for result in reviewer_results:
        key = (
            result.run_key.reviewer,
            result.run_key.stage.value,
            result.run_key.clarification_id,
        )
        previous = terminal_results.get(key)
        if previous is None or result.run_key.attempt >= previous.run_key.attempt:
            terminal_results[key] = result
    for result in terminal_results.values():
        agent = config.agents.get(result.run_key.reviewer)
        required = bool(agent.required) if agent is not None else False
        if required or result.status != ReviewerRunStatusValue.FAILED:
            continue
        errors = tuple(redact_for_error(error) for error in result.errors)
        failed_optional_reviewers.append(
            {
                "reviewer": result.run_key.reviewer,
                "stage": result.run_key.stage.value,
                "status": result.status.value,
                "required": False,
                "reason": errors[0] if errors else None,
                "errors": list(errors),
            }
        )
    return {
        "has_partial_review": bool(failed_optional_reviewers),
        "failed_optional_reviewers": failed_optional_reviewers,
    }


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


def _github_source_ref(pr_ref: object) -> str:
    if isinstance(pr_ref, Mapping):
        owner_repo = pr_ref.get("owner_repo")
        pr_number = pr_ref.get("pr_number")
        if isinstance(owner_repo, str) and type(pr_number) is int:
            return f"github:{owner_repo}#{pr_number}"
    return "github:unknown"


def _redaction_status_from_json(value: object) -> RedactionStatus:
    if not isinstance(value, Mapping):
        return RedactionStatus(status=GateStatus.PASS, redacted=False, replacement_count=0, categories=())
    return RedactionStatus(
        status=GateStatus.PASS,
        redacted=value.get("redacted") is True,
        replacement_count=value.get("replacement_count") if type(value.get("replacement_count")) is int else 0,
        categories=tuple(item for item in value.get("categories", ()) if isinstance(item, str)),
    )


def _fail_closed_markdown(data: dict[str, Any]) -> str:
    source_ref = data.get("source_ref", "github:unknown")
    lines = [
        "# ReviewGraph Dry Run",
        "",
        "## GitHub Read Failure",
        f"- Source: {source_ref}",
        "- Post enabled: false",
        "",
        "## Read Gaps",
    ]
    for gap in data.get("read_gaps", []):
        if isinstance(gap, Mapping):
            lines.append(
                f"- {gap.get('resource')}: required={str(gap.get('required')).lower()}, "
                f"retryable={str(gap.get('retryable')).lower()} - {gap.get('reason')}"
            )
    if len(lines) == 7:
        lines.append("- None")
    lines.extend(["", "## Graph Errors"])
    for error in data.get("errors", []):
        if isinstance(error, Mapping):
            lines.append(f"- {error.get('code')}: {error.get('message')}")
    if lines[-1] == "## Graph Errors":
        lines.append("- None")
    return "\n".join(lines) + "\n"


def _non_interactive_post_result(
    *,
    dry_run: DryRunResult,
    gate: PostInteractionGateResult,
    error: GraphError,
) -> DryRunResult:
    graph_trace = list(dry_run.json_data.get("graph_trace", []))
    graph_trace.append({"event": "render_review", "status": "completed"})
    graph_trace.append(
        {
            "event": "post_mode_interaction_gate",
            "status": gate.status.value,
            "interactive": gate.interactive,
            "reason": gate.reason,
        }
    )
    errors = [
        item
        for item in dry_run.json_data.get("errors", [])
        if isinstance(item, Mapping)
    ]
    errors.append(
        {
            "code": error.code,
            "message": error.message,
            "retryable": error.retryable,
        }
    )
    side_effects = {
        "writer_called": dry_run.writer_call_count > 0,
        "writer_call_count": dry_run.writer_call_count,
    }
    post_interaction_gate = {
        "status": gate.status.value,
        "interactive": gate.interactive,
        "reason": gate.reason,
    }
    data = {
        **dry_run.json_data,
        "run_mode": RunMode.POST.value,
        "post_enabled": False,
        "post_interaction_gate": post_interaction_gate,
        "graph_trace": graph_trace,
        "errors": errors,
        "approval": None,
        "final_github_payload": None,
        "final_payload_hash": None,
        "marker_reconciliation": None,
        "writer_result": None,
        "side_effects": side_effects,
    }
    markdown = _append_non_interactive_post_markdown(
        markdown=dry_run.markdown,
        gate=gate,
        error=error,
    )
    redacted_data = _redact_json_value(data)
    return DryRunResult(
        markdown=markdown,
        json_data=redacted_data,
        rendered=replace(dry_run.rendered, markdown=markdown),
        writer_call_count=dry_run.writer_call_count,
    )


def _append_non_interactive_post_markdown(
    *,
    markdown: str,
    gate: PostInteractionGateResult,
    error: GraphError,
) -> str:
    return (
        markdown.rstrip()
        + "\n\n"
        + "## Post Mode Interaction Gate\n"
        + f"- Status: {gate.status.value}\n"
        + f"- Interactive approval surface: {str(gate.interactive).lower()}\n"
        + f"- Reason: {gate.reason}\n"
        + f"- Error: {error.message}\n"
    )


def _json_envelope(
    *,
    dry_run_input: _DryRunInput,
    post_enabled: bool,
    local_verdict: ReviewVerdict,
    risk: RiskAssessment,
    selected_reviewers: tuple[SelectedReviewer, ...],
    reviewer_run_status: dict[str, ReviewerRunStatus],
    reviewer_results: tuple[ReviewerResult, ...],
    errors: tuple[GraphError, ...],
    graph_trace: list[dict[str, Any]],
    writer_call_count: int,
    rendered: RenderedReview,
    clarification_gate: ClarificationGateResult,
    partial_review: dict[str, Any],
    live_llm_ledger: dict[str, object] | None = None,
    live_llm_policy_audits: tuple[dict[str, object], ...] = (),
) -> dict[str, Any]:
    return _redact_json_value({
        "run_mode": "dry_run",
        "post_enabled": post_enabled,
        "source_type": dry_run_input.source_type,
        "source_id": dry_run_input.source_id,
        "source_ref": dry_run_input.source_ref,
        **_legacy_fixture_fields(dry_run_input),
        **({"github_read": dry_run_input.github_read} if dry_run_input.github_read is not None else {}),
        "partial_review": partial_review,
        "graph_trace": graph_trace,
        "local_verdict": local_verdict.value,
        "pending_clarification_ids": list(clarification_gate.pending_ids),
        "blocking_clarification_ids": list(clarification_gate.blocking_pending_ids),
        "clarification_status": {
            request_id: {
                "request_id": status.request_id,
                "status": status.status.value,
                "reason": status.reason,
            }
            for request_id, status in sorted(clarification_gate.status.items())
        },
        "errors": [
            {"code": error.code, "message": error.message, "retryable": error.retryable}
            for error in errors
        ],
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
                "reason": status.reason,
            }
            for key, status in sorted(reviewer_run_status.items())
        ],
        "reviewer_results": [
            {
                "key": result.run_key.stable_key(),
                "reviewer": result.run_key.reviewer,
                "stage": result.run_key.stage.value,
                "status": result.status.value,
                "errors": list(result.errors),
                "normalization_errors": [
                    error.to_ordered_dict() for error in result.normalization_errors
                ],
                "repair_record": (
                    result.repair_record.to_ordered_dict()
                    if result.repair_record is not None
                    else None
                ),
                "live_llm_evidence": (
                    result.live_llm_evidence.to_ordered_dict()
                    if result.live_llm_evidence is not None
                    else None
                ),
                "raw_output": result.raw_output,
            }
            for result in reviewer_results
        ],
        "live_llm": {
            "ledger": live_llm_ledger,
            "policy_audits": list(live_llm_policy_audits),
        },
        "side_effects": {
            "writer_called": writer_call_count > 0,
            "writer_call_count": writer_call_count,
        },
        "public_payload_preparation": rendered.json_data.get("public_payload_preparation"),
        "review": rendered.json_data,
    })


def _legacy_fixture_fields(dry_run_input: _DryRunInput) -> dict[str, str]:
    if dry_run_input.source_type != "fixture":
        return {}
    return {
        "fixture_id": dry_run_input.source_id,
        "fixture_ref": dry_run_input.source_ref,
    }


def _optional_int(data: dict[str, Any], field: str, label: str) -> int | None:
    value = data.get(field)
    if value is None:
        return None
    if type(value) is not int:
        raise RunnerError(f"{label}.{field} must be an integer or null")
    return value


def _redact_json_value(value: Any) -> Any:
    return redact_data(value).data
