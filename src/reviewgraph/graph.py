from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from reviewgraph.context_budget import apply_input_context_budget, default_context_budget
from reviewgraph.fixtures import FixturePR, load_fixture_pr
from reviewgraph.memory import build_conversation_memory
from reviewgraph.models import (
    ReviewConfig,
    ReviewStage,
    ReviewState,
    ReviewTarget,
    RunMode,
)
from reviewgraph.posting import canonical_json_hash
from reviewgraph.redaction import redact_data
from reviewgraph.risk import classify_change_risk, risk_assessment_to_json
from reviewgraph.state import initial_stage_queue


class _EmptyDryRunRuntimeState(TypedDict):
    fixture_ref: str
    review_state: ReviewState | None
    graph_trace: list[str]
    json_data: dict[str, Any]


@dataclass(frozen=True)
class EmptyDryRunGraphResult:
    review_state: ReviewState
    graph_trace: tuple[str, ...]
    json_data: dict[str, Any]


def run_empty_fixture_dry_run_graph(
    *,
    fixture_ref: str,
    writer_sentinel: object | None = None,
) -> EmptyDryRunGraphResult:
    writer_call_count_before = _writer_call_count(writer_sentinel)
    graph = build_empty_dry_run_graph()
    output = graph.invoke(
        {
            "fixture_ref": fixture_ref,
            "review_state": None,
            "graph_trace": [],
            "json_data": {},
        }
    )
    writer_call_count = _writer_call_count(writer_sentinel) - writer_call_count_before
    review_state = output["review_state"]
    if review_state is None:
        raise RuntimeError("empty dry-run graph did not initialize ReviewState")
    json_data = {
        **output["json_data"],
        "side_effects": {
            "writer_called": writer_call_count > 0,
            "writer_call_count": writer_call_count,
        },
    }
    return EmptyDryRunGraphResult(
        review_state=review_state,
        graph_trace=tuple(output["graph_trace"]),
        json_data=_redact_json_value(json_data),
    )


def build_empty_dry_run_graph() -> Any:
    graph = StateGraph(_EmptyDryRunRuntimeState)
    graph.add_node("initialize_review_state", _initialize_review_state)
    graph.add_node("emit_dry_run", _emit_dry_run)
    graph.add_edge(START, "initialize_review_state")
    graph.add_edge("initialize_review_state", "emit_dry_run")
    graph.add_edge("emit_dry_run", END)
    return graph.compile()


def _initialize_review_state(state: _EmptyDryRunRuntimeState) -> dict[str, Any]:
    fixture = load_fixture_pr(state["fixture_ref"])
    conversation_memory = build_conversation_memory(
        fixture.pr,
        trusted_operator_authors=(),
        trusted_bot_authors=(),
    )
    budgeted_context = apply_input_context_budget(
        pr=fixture.pr,
        memory=conversation_memory,
        limits=default_context_budget(),
        existing_truncation=(),
    )
    risk_assessment = classify_change_risk(fixture.pr)
    review_state = ReviewState(
        run_id=f"fixture-empty:{fixture.id}",
        run_mode=RunMode.DRY_RUN,
        post_enabled=False,
        pr_ref=fixture.pr_ref,
        review_target=_review_target(fixture),
        posting_target=None,
        pr=budgeted_context.pr,
        conversation_memory=budgeted_context.memory,
        read_gaps=[],
        config=ReviewConfig(agents={}),
        config_hash=canonical_json_hash({"agents": {}}),
        stage_queue=initial_stage_queue(),
        active_stage=None,
        suspended_stage=None,
        completed_stages=[],
        risk=risk_assessment,
        selected_reviewers=[],
        reviewer_run_keys=[],
        reviewer_run_status={},
        reviewer_results=[],
        context_budget=budgeted_context.context_budget,
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
    return {
        "review_state": review_state,
        "graph_trace": state["graph_trace"] + ["initialize_review_state"],
    }


def _emit_dry_run(state: _EmptyDryRunRuntimeState) -> dict[str, Any]:
    review_state = state["review_state"]
    if review_state is None:
        raise RuntimeError("emit_dry_run requires initialized ReviewState")
    return {
        "graph_trace": state["graph_trace"] + ["emit_dry_run"],
        "json_data": _review_state_json(review_state, graph_trace=state["graph_trace"] + ["emit_dry_run"]),
    }


def _review_state_json(review_state: ReviewState, *, graph_trace: list[str]) -> dict[str, Any]:
    memory = review_state.conversation_memory
    return {
        "run_id": review_state.run_id,
        "run_mode": review_state.run_mode.value,
        "post_enabled": review_state.post_enabled,
        "fixture_ref": review_state.pr_ref,
        "graph_trace": list(graph_trace),
        "review_target": review_state.review_target.to_ordered_dict(),
        "stage_cursor": {
            "active_stage": review_state.active_stage,
            "suspended_stage": review_state.suspended_stage,
            "stage_queue": [stage.value for stage in review_state.stage_queue],
            "completed_stages": [stage.value for stage in review_state.completed_stages],
            "ready_clarification_ids": list(review_state.ready_clarification_ids),
            "active_clarification_id": review_state.active_clarification_id,
        },
        "selected_reviewers": [],
        "risk": risk_assessment_to_json(review_state.risk),
        "local_verdict": review_state.local_verdict,
        "classified_output": {
            "findings": [],
            "local_notes": [],
            "suggested_replies": [],
            "suppressed_outputs": [],
            "clarification_requests": [],
        },
        "memory": {
            "entry_count": len(memory.entries) if memory is not None else 0,
            "entry_ids": [entry.id for entry in memory.entries] if memory is not None else [],
        },
        "context_budget": {
            "changed_file_count": review_state.context_budget.retained_changed_file_count,
            "omitted_file_paths": list(review_state.context_budget.omitted_file_paths),
            "generated_local_note_ids": list(review_state.context_budget.generated_local_note_ids),
        },
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


def _writer_call_count(writer_sentinel: object | None) -> int:
    if writer_sentinel is None:
        return 0
    value = getattr(writer_sentinel, "call_count", 0)
    if type(value) is not int:
        return 0
    return value


def _redact_json_value(value: Any) -> Any:
    return redact_data(value).data
