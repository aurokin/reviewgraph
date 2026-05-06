import pytest

from reviewgraph.graph import run_empty_fixture_dry_run_graph
from reviewgraph.models import ReviewStage, ReviewState
from reviewgraph.state import StageCursorError, advance_or_finish_stage, initial_stage_queue


def test_initial_cursor_state_uses_future_normal_stage_queue() -> None:
    state = _empty_state()

    assert state.active_stage is None
    assert state.suspended_stage is None
    assert state.stage_queue == initial_stage_queue()
    assert state.completed_stages == []


def test_advance_or_finish_stage_starts_first_stage_and_records_trace() -> None:
    state = _empty_state()

    transition = advance_or_finish_stage(state)

    assert state.active_stage == ReviewStage.INITIAL_TRIAGE
    assert state.stage_queue == [ReviewStage.SPECIALIZED_REVIEW, ReviewStage.LOGIC_REVIEW]
    assert state.completed_stages == []
    assert transition.to_json() == {
        "active_stage_before": None,
        "active_stage_after": "initial_triage",
        "suspended_stage_before": None,
        "suspended_stage_after": None,
        "stage_queue_before": ["initial_triage", "specialized_review", "logic_review"],
        "stage_queue_after": ["specialized_review", "logic_review"],
        "completed_stages_before": [],
        "completed_stages_after": [],
        "transition_reason": "start_initial_triage",
    }


def test_advance_or_finish_stage_never_reruns_completed_normal_stages() -> None:
    state = _empty_state()

    transitions = [advance_or_finish_stage(state).to_json() for _ in range(4)]

    assert state.active_stage is None
    assert state.stage_queue == []
    assert state.completed_stages == [
        ReviewStage.INITIAL_TRIAGE,
        ReviewStage.SPECIALIZED_REVIEW,
        ReviewStage.LOGIC_REVIEW,
    ]
    assert [transition["active_stage_after"] for transition in transitions] == [
        "initial_triage",
        "specialized_review",
        "logic_review",
        None,
    ]
    assert transitions[-1]["transition_reason"] == "finish_review_stages"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: state.stage_queue.append(ReviewStage.CLARIFICATION_REVIEW),
        lambda state: state.stage_queue.append(ReviewStage.INITIAL_TRIAGE),
        lambda state: state.completed_stages.append(ReviewStage.SPECIALIZED_REVIEW),
    ],
)
def test_stage_queue_contains_only_future_normal_stages(mutate: object) -> None:
    state = _empty_state()
    advance_or_finish_stage(state)
    mutate(state)

    with pytest.raises(StageCursorError):
        advance_or_finish_stage(state)


def test_completed_stage_in_queue_fails_before_rerun() -> None:
    state = _empty_state()
    state.completed_stages.append(ReviewStage.INITIAL_TRIAGE)

    with pytest.raises(StageCursorError):
        advance_or_finish_stage(state)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda state: setattr(state, "active_stage", ReviewStage.SPECIALIZED_REVIEW),
        lambda state: state.completed_stages.append(ReviewStage.LOGIC_REVIEW),
        lambda state: state.stage_queue.reverse(),
    ],
)
def test_stage_cursor_rejects_out_of_order_normal_stages(mutate: object) -> None:
    state = _empty_state()
    mutate(state)

    with pytest.raises(StageCursorError):
        advance_or_finish_stage(state)


def _empty_state() -> ReviewState:
    return run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
