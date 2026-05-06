from dataclasses import replace

import pytest

from reviewgraph.clarification import evaluate_clarification_gate, ingest_clarification_answer
from reviewgraph.config import parse_reviewer_config
from reviewgraph.graph import run_empty_fixture_dry_run_graph
from reviewgraph.models import (
    ClarificationAnswer,
    ClarificationRequest,
    ClarificationState,
    ClarificationStatus,
    ReviewerRunStatusValue,
    ReviewStage,
    SelectedReviewer,
)
from reviewgraph.posting import canonical_json_hash
from reviewgraph.reviewer_runs import (
    retry_after_failure,
    record_reviewer_run_status,
    register_selected_reviewer,
    reviewer_run_key_for_selection,
)
from reviewgraph.routing import select_reviewers_for_active_stage
from reviewgraph.runner import run_fixture_dry_run
from reviewgraph.state import advance_or_finish_stage


def test_ingest_clarification_answer_marks_answered_without_cursor_mutation() -> None:
    state = _state_with_pending_clarification()
    cursor_before = _stage_cursor_snapshot(state)
    answer = _answer()

    ingest_clarification_answer(state, answer)

    assert _stage_cursor_snapshot(state) == cursor_before
    assert state.clarifications == [answer]
    assert state.pending_clarification_ids == []
    assert state.ready_clarification_ids == ["clarify-cache"]
    assert state.clarification_requests[0].status == ClarificationState.ANSWERED
    assert state.clarification_status["clarify-cache"] == ClarificationStatus(
        request_id="clarify-cache",
        status=ClarificationState.ANSWERED,
    )


def test_advance_enters_clarification_review_and_restores_suspended_stage_once() -> None:
    state = _state_with_pending_clarification()
    ingest_clarification_answer(state, _answer())

    enter = advance_or_finish_stage(state)

    assert enter.to_json() == {
        "active_stage_before": "initial_triage",
        "active_stage_after": "clarification_review",
        "suspended_stage_before": None,
        "suspended_stage_after": "initial_triage",
        "stage_queue_before": ["specialized_review", "logic_review"],
        "stage_queue_after": ["specialized_review", "logic_review"],
        "completed_stages_before": [],
        "completed_stages_after": [],
        "transition_reason": "enter_clarification_review",
    }
    assert state.ready_clarification_ids == []
    assert state.active_clarification_id == "clarify-cache"

    restore = advance_or_finish_stage(state)

    assert restore.to_json()["active_stage_after"] == "initial_triage"
    assert restore.to_json()["suspended_stage_after"] is None
    assert state.active_clarification_id is None
    assert state.ready_clarification_ids == []

    next_transition = advance_or_finish_stage(state)

    assert next_transition.to_json()["transition_reason"] == "complete_initial_triage_start_specialized_review"
    assert state.active_stage == ReviewStage.SPECIALIZED_REVIEW


def test_resume_selection_runs_only_affected_reviewer_with_clarification_id() -> None:
    state = _state_with_pending_clarification()
    state.config = parse_reviewer_config(
        {
            "agents": {
                "logic": {
                    "stages": ["logic_review"],
                    "triggers": {"always": True},
                },
                "security": {
                    "stages": ["specialized_review"],
                    "triggers": {"always": True},
                },
            }
        }
    )
    state.config_hash = canonical_json_hash({"agents": ["logic", "security"]})
    completed_security = SelectedReviewer(
        name="security",
        stage="specialized_review",
        reasons=("specialized_review triggers.always=true",),
    )
    completed_key = register_selected_reviewer(state, completed_security)
    assert completed_key is not None
    record_reviewer_run_status(
        state,
        completed_key,
        status=ReviewerRunStatusValue.COMPLETED,
        reason="completed before clarification resume",
    )
    ingest_clarification_answer(state, _answer())
    advance_or_finish_stage(state)

    selected = select_reviewers_for_active_stage(state)

    assert selected == (
        SelectedReviewer(
            name="logic",
            stage="clarification_review",
            reasons=("clarification_review resume.clarification_id=clarify-cache",),
        ),
    )
    resumed_key = state.reviewer_run_keys[-1]
    assert resumed_key.reviewer == "logic"
    assert resumed_key.stage == ReviewStage.CLARIFICATION_REVIEW
    assert resumed_key.clarification_id == "clarify-cache"
    assert reviewer_run_key_for_selection(state, selected[0]) == resumed_key
    assert all(key.reviewer != "security" or key == completed_key for key in state.reviewer_run_keys)


def test_completed_clarification_run_does_not_suppress_different_clarification_id() -> None:
    state = _state_with_pending_clarification()
    state.active_stage = ReviewStage.CLARIFICATION_REVIEW
    state.suspended_stage = ReviewStage.INITIAL_TRIAGE
    state.active_clarification_id = "clarify-cache-2"
    state.clarification_requests.append(
        replace(_request(), id="clarify-cache-2", resume_target_reviewers=("logic",))
    )
    reviewer = SelectedReviewer(
        name="logic",
        stage="clarification_review",
        reasons=("clarification_review resume.clarification_id=clarify-cache",),
    )
    first_key = register_selected_reviewer(state, reviewer, clarification_id="clarify-cache")
    assert first_key is not None
    record_reviewer_run_status(
        state,
        first_key,
        status=ReviewerRunStatusValue.COMPLETED,
        reason="completed first clarification",
    )
    second = select_reviewers_for_active_stage(state)

    assert second
    assert state.reviewer_run_keys[-1].clarification_id == "clarify-cache-2"
    assert reviewer_run_key_for_selection(state, second[0]).clarification_id == "clarify-cache-2"


def test_clarification_run_key_lookup_uses_latest_active_retry_attempt() -> None:
    state = _state_with_pending_clarification()
    state.active_stage = ReviewStage.CLARIFICATION_REVIEW
    state.suspended_stage = ReviewStage.INITIAL_TRIAGE
    state.active_clarification_id = "clarify-cache"
    reviewer = SelectedReviewer(
        name="logic",
        stage="clarification_review",
        reasons=("clarification_review resume.clarification_id=clarify-cache",),
    )
    first_key = register_selected_reviewer(state, reviewer, clarification_id="clarify-cache")
    assert first_key is not None
    decision = retry_after_failure(state, first_key, reason="transient fake failure")
    assert decision.run_key is not None

    selected_key = reviewer_run_key_for_selection(state, reviewer)

    assert selected_key == decision.run_key
    assert selected_key.attempt == 2
    assert selected_key.clarification_id == "clarify-cache"


def test_completed_clarification_resume_selection_is_idempotent() -> None:
    state = _state_with_pending_clarification()
    state.active_stage = ReviewStage.CLARIFICATION_REVIEW
    state.suspended_stage = ReviewStage.INITIAL_TRIAGE
    state.active_clarification_id = "clarify-cache"
    reviewer = SelectedReviewer(
        name="logic",
        stage="clarification_review",
        reasons=("clarification_review resume.clarification_id=clarify-cache",),
    )
    run_key = register_selected_reviewer(state, reviewer, clarification_id="clarify-cache")
    assert run_key is not None
    record_reviewer_run_status(
        state,
        run_key,
        status=ReviewerRunStatusValue.COMPLETED,
        reason="completed clarification resume",
    )

    assert select_reviewers_for_active_stage(state) == ()


def test_fixture_run_resumes_answered_clarification_through_affected_reviewer(tmp_path) -> None:
    fixture_path = tmp_path / "answered-clarification.json"
    fixture = _basic_fixture()
    fixture["id"] = "answered-clarification"
    fixture["raw_reviewer_outputs"][0]["items"] = [
        {
            "type": "clarification_request",
            "id": "clarify-cache",
            "question": "Is stale cache fallback intentional?",
            "why_it_matters": "The mergeability decision depends on product intent.",
            "evidence_sources": ["diff"],
        }
    ]
    fixture["raw_reviewer_outputs"].append(
        {
            "reviewer": "correctness",
            "stage": "clarification_review",
            "items": [
                {
                    "type": "finding",
                    "id": "finding-cache-after-answer",
                    "title": "Cache miss returns stale data",
                    "body": "The new branch returns stale data when the cache misses after the maintainer clarified this is unintended.",
                    "evidence": "Changed line 12 returns stale value when the cache misses.",
                    "path": "src/cache.py",
                    "line": 12,
                    "severity": "warning",
                    "confidence": "high",
                }
            ],
        }
    )
    fixture_path.write_text(__import__("json").dumps(fixture))

    result = run_fixture_dry_run(
        fixture_ref=str(fixture_path),
        clarification_answers=(_answer(),),
    )

    assert result.json_data["post_enabled"] is True
    assert result.json_data["local_verdict"] == "comment"
    assert result.json_data["pending_clarification_ids"] == []
    assert result.json_data["blocking_clarification_ids"] == []
    assert result.json_data["clarification_status"]["clarify-cache"]["status"] == "answered"
    assert [finding["id"] for finding in result.json_data["review"]["classified_output"]["postable_findings"]] == [
        "finding-cache-after-answer"
    ]
    assert any(
        run["stage"] == "clarification_review" and '"clarification_id":"clarify-cache"' in run["key"]
        for run in result.json_data["reviewer_results"]
    )
    assert "enter_clarification_review" in {
        transition["transition_reason"] for transition in result.json_data["graph_trace"]
    }
    assert any(
        transition["transition_reason"] == "finish_clarification_review_restore_initial_triage"
        for transition in result.json_data["graph_trace"]
    )


def test_resume_selection_fails_when_target_reviewer_is_unavailable() -> None:
    state = _state_with_pending_clarification()
    state.active_stage = ReviewStage.CLARIFICATION_REVIEW
    state.suspended_stage = ReviewStage.INITIAL_TRIAGE
    state.active_clarification_id = "clarify-cache"
    state.config = parse_reviewer_config(
        {
            "agents": {
                "security": {
                    "stages": ["specialized_review"],
                    "triggers": {"always": True},
                }
            }
        }
    )

    with pytest.raises(ValueError, match="resume reviewers unavailable: logic"):
        select_reviewers_for_active_stage(state)


def test_answered_request_does_not_keep_clarification_gate_blocking() -> None:
    state = _state_with_pending_clarification()
    state.pending_clarification_ids.append("stale-duplicate")
    state.post_enabled = False
    ingest_clarification_answer(state, _answer())

    gate = evaluate_clarification_gate(state.clarification_requests)
    post_enabled = not gate.blocks_posting and bool([object()])

    assert gate.pending_ids == ()
    assert gate.blocking_pending_ids == ()
    assert gate.blocks_posting is False
    assert post_enabled is True


def test_resume_from_later_stage_preserves_completed_prefix() -> None:
    state = _state_with_pending_clarification()
    state.completed_stages = [ReviewStage.INITIAL_TRIAGE]
    state.active_stage = ReviewStage.SPECIALIZED_REVIEW
    state.stage_queue = [ReviewStage.LOGIC_REVIEW]
    ingest_clarification_answer(state, _answer())

    enter = advance_or_finish_stage(state)
    restore = advance_or_finish_stage(state)

    assert enter.to_json()["active_stage_after"] == "clarification_review"
    assert enter.to_json()["completed_stages_after"] == ["initial_triage"]
    assert restore.to_json()["active_stage_after"] == "specialized_review"
    assert state.completed_stages == [ReviewStage.INITIAL_TRIAGE]
    assert state.stage_queue == [ReviewStage.LOGIC_REVIEW]


def _state_with_pending_clarification():
    state = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
    state.config = parse_reviewer_config(
        {
            "agents": {
                "logic": {
                    "stages": ["logic_review"],
                    "triggers": {"always": True},
                }
            }
        }
    )
    state.config_hash = canonical_json_hash({"agents": ["logic"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE
    state.stage_queue = [ReviewStage.SPECIALIZED_REVIEW, ReviewStage.LOGIC_REVIEW]
    state.clarification_requests = [_request()]
    state.pending_clarification_ids = ["clarify-cache"]
    state.clarification_status = {
        "clarify-cache": ClarificationStatus(
            request_id="clarify-cache",
            status=ClarificationState.PENDING,
        )
    }
    return state


def _basic_fixture() -> dict[str, object]:
    import json
    from importlib import resources

    fixture_text = resources.files("reviewgraph").joinpath("fixtures_data/prs/basic-pr.json").read_text()
    return json.loads(fixture_text)


def _request() -> ClarificationRequest:
    return ClarificationRequest(
        id="clarify-cache",
        reviewer="logic",
        question="Is stale cache fallback intentional?",
        why_it_matters="The mergeability decision depends on product intent.",
        source_stage="initial_triage",
        status=ClarificationState.PENDING,
        resume_target_stage=ReviewStage.CLARIFICATION_REVIEW,
        resume_target_reviewers=("logic",),
    )


def _answer() -> ClarificationAnswer:
    return ClarificationAnswer(
        id="answer-cache",
        request_id="clarify-cache",
        answer="No, stale fallback is not intended.",
        answered_by="maintainer",
        answered_at="2026-05-06T21:45:00Z",
    )


def _stage_cursor_snapshot(state) -> tuple[object, ...]:
    return (
        state.active_stage,
        state.suspended_stage,
        tuple(state.stage_queue),
        tuple(state.completed_stages),
    )
