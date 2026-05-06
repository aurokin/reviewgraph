import pytest

from reviewgraph.config import parse_reviewer_config
from reviewgraph.graph import run_empty_fixture_dry_run_graph
from reviewgraph.models import ReviewerRunStatusValue, ReviewStage, SelectedReviewer
from reviewgraph.posting import canonical_json_hash
from reviewgraph.reviewer_runs import (
    RetryPolicy,
    is_retry_exhausted_failure,
    make_reviewer_run_key,
    record_reviewer_run_status,
    register_selected_reviewer,
    retry_after_failure,
    suppresses_rerun,
)
from reviewgraph.routing import select_reviewers_for_active_stage


def test_reviewer_run_key_contains_attempt_retry_and_clarification_metadata() -> None:
    state = _state_with_config()
    reviewer = SelectedReviewer(
        name="logic",
        stage="logic_review",
        reasons=("logic_review triggers.risk_min>=medium",),
    )

    key = make_reviewer_run_key(
        state,
        reviewer,
        attempt=2,
        retry_of="prior-stable-key",
        clarification_id="clarify-1",
    )

    assert key.target_hash == state.review_target.target_hash()
    assert key.config_hash == state.config_hash
    assert key.stage == ReviewStage.LOGIC_REVIEW
    assert key.reviewer == "logic"
    assert key.attempt == 2
    assert key.retry_of == "prior-stable-key"
    assert key.clarification_id == "clarify-1"
    assert '"attempt":2' in key.stable_key()
    assert '"retry_of":"prior-stable-key"' in key.stable_key()
    assert '"clarification_id":"clarify-1"' in key.stable_key()


@pytest.mark.parametrize(
    "status",
    [
        ReviewerRunStatusValue.SELECTED,
        ReviewerRunStatusValue.RUNNING,
        ReviewerRunStatusValue.COMPLETED,
        ReviewerRunStatusValue.FAILED,
        ReviewerRunStatusValue.SKIPPED,
    ],
)
def test_reviewer_run_status_records_all_status_values(status: ReviewerRunStatusValue) -> None:
    state = _state_with_config()
    reviewer = SelectedReviewer(name="correctness", stage="initial_triage", reasons=("initial_triage triggers.always=true",))
    run_key = register_selected_reviewer(state, reviewer)
    assert run_key is not None

    run_status = record_reviewer_run_status(
        state,
        run_key,
        status=status,
        reason=f"recorded {status.value}",
    )

    assert run_status.status == status
    assert state.reviewer_run_status[run_key.stable_key()].status == status


def test_selected_running_and_failed_are_not_treated_as_completed() -> None:
    for status in (
        ReviewerRunStatusValue.SELECTED,
        ReviewerRunStatusValue.RUNNING,
        ReviewerRunStatusValue.FAILED,
    ):
        state = _state_with_config()
        reviewer = SelectedReviewer(name="correctness", stage="initial_triage", reasons=("initial_triage triggers.always=true",))
        run_key = register_selected_reviewer(state, reviewer)
        assert run_key is not None
        run_status = record_reviewer_run_status(
            state,
            run_key,
            status=status,
            reason=f"recorded {status.value}",
        )

        assert not suppresses_rerun(run_status)
        assert register_selected_reviewer(state, reviewer) == run_key


def test_completed_and_skipped_reviewers_are_not_rerun_for_same_target_and_config() -> None:
    for status in (ReviewerRunStatusValue.COMPLETED, ReviewerRunStatusValue.SKIPPED):
        state = _state_with_config()
        reviewer = SelectedReviewer(name="correctness", stage="initial_triage", reasons=("initial_triage triggers.always=true",))
        run_key = register_selected_reviewer(state, reviewer)
        assert run_key is not None
        run_status = record_reviewer_run_status(
            state,
            run_key,
            status=status,
            reason=f"recorded {status.value}",
        )

        assert suppresses_rerun(run_status)
        assert register_selected_reviewer(state, reviewer) is None


def test_completed_retry_attempt_suppresses_default_selection_for_same_reviewer_identity() -> None:
    state = _state_with_config()
    reviewer = SelectedReviewer(name="correctness", stage="initial_triage", reasons=("initial_triage triggers.always=true",))
    initial_key = register_selected_reviewer(state, reviewer)
    assert initial_key is not None
    retry = retry_after_failure(
        state,
        initial_key,
        policy=RetryPolicy(max_attempts=2),
        reason="malformed reviewer output",
    )
    assert retry.run_key is not None
    record_reviewer_run_status(
        state,
        retry.run_key,
        status=ReviewerRunStatusValue.COMPLETED,
        reason="retry completed",
    )

    assert register_selected_reviewer(state, reviewer) is None


def test_selection_uses_run_status_for_idempotent_completed_suppression() -> None:
    state = _state_with_config()
    selected = select_reviewers_for_active_stage(state)
    run_key = state.reviewer_run_keys[0]
    record_reviewer_run_status(
        state,
        run_key,
        status=ReviewerRunStatusValue.COMPLETED,
        reason="completed once",
    )

    assert [reviewer.name for reviewer in selected] == ["correctness"]
    assert select_reviewers_for_active_stage(state) == ()


def test_retry_exhaustion_records_permanent_failure_without_new_key() -> None:
    state = _state_with_config()
    reviewer = SelectedReviewer(name="correctness", stage="initial_triage", reasons=("initial_triage triggers.always=true",))
    run_key = register_selected_reviewer(state, reviewer)
    assert run_key is not None

    retry = retry_after_failure(
        state,
        run_key,
        policy=RetryPolicy(max_attempts=1),
        reason="malformed reviewer output",
    )

    assert retry.exhausted is True
    assert retry.run_key is None
    assert state.reviewer_run_status[run_key.stable_key()].status == ReviewerRunStatusValue.FAILED
    assert state.reviewer_run_status[run_key.stable_key()].reason == (
        "retry exhausted: malformed reviewer output"
    )
    assert is_retry_exhausted_failure(state.reviewer_run_status[run_key.stable_key()])
    assert register_selected_reviewer(state, reviewer) is None


def test_retry_before_exhaustion_creates_retry_key_with_retry_metadata() -> None:
    state = _state_with_config()
    reviewer = SelectedReviewer(name="correctness", stage="initial_triage", reasons=("initial_triage triggers.always=true",))
    run_key = register_selected_reviewer(state, reviewer)
    assert run_key is not None

    retry = retry_after_failure(
        state,
        run_key,
        policy=RetryPolicy(max_attempts=2),
        reason="malformed reviewer output",
    )

    assert retry.exhausted is False
    assert retry.run_key is not None
    assert retry.run_key.attempt == 2
    assert retry.run_key.retry_of == run_key.stable_key()
    assert state.reviewer_run_status[retry.run_key.stable_key()].status == ReviewerRunStatusValue.SELECTED


def test_retry_policy_rejects_invalid_attempt_limit() -> None:
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)


def _state_with_config():
    state = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
    state.config = parse_reviewer_config(
        {
            "agents": {
                "correctness": {
                    "stages": ["initial_triage"],
                    "triggers": {"always": True},
                }
            }
        }
    )
    state.config_hash = canonical_json_hash({"agents": ["correctness"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE
    return state
