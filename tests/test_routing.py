from reviewgraph.config import parse_reviewer_config
from reviewgraph.graph import run_empty_fixture_dry_run_graph
from reviewgraph.models import ReviewStage, ReviewerRunStatus, ReviewerRunStatusValue
from reviewgraph.posting import canonical_json_hash
from reviewgraph.routing import select_reviewers_for_active_stage, select_reviewers_for_stage
from reviewgraph.runner import _review_config_hash


def test_always_on_reviewer_selected_for_active_stage_with_reason() -> None:
    config = parse_reviewer_config(
        {
            "agents": {
                "correctness": {
                    "stages": ["initial_triage"],
                    "triggers": {"always": True},
                }
            }
        }
    )
    state = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
    state.config = config
    state.config_hash = canonical_json_hash({"agents": ["correctness"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE

    selected = select_reviewers_for_active_stage(state)

    assert selected == tuple(state.selected_reviewers)
    assert len(state.selected_reviewers) == 1
    assert state.selected_reviewers[0].name == "correctness"
    assert state.selected_reviewers[0].stage == "initial_triage"
    assert state.selected_reviewers[0].reasons == ("initial_triage triggers.always=true",)
    assert len(state.reviewer_run_keys) == 1
    run_key = state.reviewer_run_keys[0]
    assert run_key.target_hash == state.review_target.target_hash()
    assert run_key.config_hash == state.config_hash
    assert run_key.stage == ReviewStage.INITIAL_TRIAGE
    assert run_key.reviewer == "correctness"
    assert state.reviewer_run_status[run_key.stable_key()].status == ReviewerRunStatusValue.SELECTED


def test_active_stage_selection_is_idempotent_for_state_persistence() -> None:
    config = parse_reviewer_config(
        {
            "agents": {
                "correctness": {
                    "stages": ["initial_triage"],
                    "triggers": {"always": True},
                }
            }
        }
    )
    state = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
    state.config = config
    state.config_hash = canonical_json_hash({"agents": ["correctness"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE

    first = select_reviewers_for_active_stage(state)
    second = select_reviewers_for_active_stage(state)

    assert [reviewer.name for reviewer in first] == ["correctness"]
    assert second == first
    assert len(state.selected_reviewers) == 1
    assert len(state.reviewer_run_keys) == 1
    assert len(state.reviewer_run_status) == 1


def test_completed_reviewer_status_suppresses_active_stage_selection() -> None:
    config = parse_reviewer_config(
        {
            "agents": {
                "correctness": {
                    "stages": ["initial_triage"],
                    "triggers": {"always": True},
                }
            }
        }
    )
    state = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
    state.config = config
    state.config_hash = canonical_json_hash({"agents": ["correctness"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE
    first = select_reviewers_for_active_stage(state)
    run_key = state.reviewer_run_keys[0]
    state.reviewer_run_status[run_key.stable_key()] = ReviewerRunStatus(
        status=ReviewerRunStatusValue.COMPLETED,
        run_key=run_key,
    )

    assert [reviewer.name for reviewer in first] == ["correctness"]
    assert select_reviewers_for_active_stage(state) == ()
    assert len(state.selected_reviewers) == 1


def test_failed_reviewer_status_remains_runnable_until_retry_policy_exists() -> None:
    config = parse_reviewer_config(
        {
            "agents": {
                "correctness": {
                    "stages": ["initial_triage"],
                    "triggers": {"always": True},
                }
            }
        }
    )
    state = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
    state.config = config
    state.config_hash = canonical_json_hash({"agents": ["correctness"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE
    first = select_reviewers_for_active_stage(state)
    run_key = state.reviewer_run_keys[0]
    state.reviewer_run_status[run_key.stable_key()] = ReviewerRunStatus(
        status=ReviewerRunStatusValue.FAILED,
        run_key=run_key,
    )

    assert [reviewer.name for reviewer in first] == ["correctness"]
    assert select_reviewers_for_active_stage(state) == first
    assert len(state.selected_reviewers) == 1


def test_always_on_reviewer_not_selected_for_non_eligible_stage() -> None:
    config = parse_reviewer_config(
        {
            "agents": {
                "specialized": {
                    "stages": ["specialized_review"],
                    "triggers": {"always": True},
                }
            }
        }
    )
    state = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
    state.config = config
    state.config_hash = canonical_json_hash({"agents": ["specialized"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE

    assert select_reviewers_for_active_stage(state) == ()
    assert state.selected_reviewers == []
    assert state.reviewer_run_keys == []
    assert state.reviewer_run_status == {}


def test_stage_selection_accepts_review_stage_values() -> None:
    config = parse_reviewer_config(
        {
            "agents": {
                "correctness": {
                    "stages": ["initial_triage"],
                    "triggers": {"always": True},
                }
            }
        }
    )
    pr = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state.pr

    selected = select_reviewers_for_stage(config, pr, ReviewStage.INITIAL_TRIAGE)

    assert [reviewer.name for reviewer in selected] == ["correctness"]


def test_path_diff_and_label_selectors_record_every_matching_reason() -> None:
    config = parse_reviewer_config(
        {
            "agents": {
                "composite": {
                    "stages": ["initial_triage"],
                    "triggers": {
                        "paths": ["src/cache.py"],
                        "diff_patterns": ["RETURN\\s+STALE_VALUE"],
                        "labels": ["BACKEND"],
                    },
                },
                "nonmatching": {
                    "stages": ["initial_triage"],
                    "triggers": {
                        "paths": ["src/auth/**"],
                        "diff_patterns": ["requires\\s+product\\s+intent"],
                        "labels": ["frontend"],
                    },
                }
            }
        }
    )
    state = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
    state.config = config
    state.config_hash = canonical_json_hash({"agents": ["composite", "nonmatching"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE

    selected = select_reviewers_for_active_stage(state)

    assert [reviewer.name for reviewer in selected] == ["composite"]
    assert selected[0].reasons == (
        "initial_triage triggers.paths=src/cache.py",
        "initial_triage triggers.diff_patterns=RETURN\\s+STALE_VALUE",
        "initial_triage triggers.labels=BACKEND",
    )
    assert state.selected_reviewers == list(selected)
    assert len(state.reviewer_run_keys) == 1
    assert state.reviewer_run_status[state.reviewer_run_keys[0].stable_key()].status == (
        ReviewerRunStatusValue.SELECTED
    )


def test_non_matching_path_diff_and_label_selectors_do_not_persist_selection() -> None:
    config = parse_reviewer_config(
        {
            "agents": {
                "diff": {
                    "stages": ["initial_triage"],
                    "triggers": {"diff_patterns": ["requires\\s+product\\s+intent"]},
                },
                "label": {
                    "stages": ["initial_triage"],
                    "triggers": {"labels": ["frontend"]},
                },
                "path": {
                    "stages": ["initial_triage"],
                    "triggers": {"paths": ["docs/**"]},
                },
            }
        }
    )
    state = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
    state.config = config
    state.config_hash = canonical_json_hash({"agents": ["diff", "label", "path"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE

    assert select_reviewers_for_active_stage(state) == ()
    assert state.selected_reviewers == []
    assert state.reviewer_run_keys == []
    assert state.reviewer_run_status == {}


def test_active_stage_without_review_target_selects_nothing() -> None:
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
    state.active_stage = None

    assert select_reviewers_for_active_stage(state) == ()
    assert state.selected_reviewers == []


def test_active_stage_selection_defaults_to_review_state_conversation_memory() -> None:
    state = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
    state.config = parse_reviewer_config(
        {
            "agents": {
                "memory": {
                    "stages": ["initial_triage"],
                    "triggers": {"conversation_patterns": ["cache miss fallback"]},
                }
            }
        }
    )
    state.config_hash = canonical_json_hash({"agents": ["memory"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE

    selected = select_reviewers_for_active_stage(state)

    assert [reviewer.name for reviewer in selected] == ["memory"]
    assert state.selected_reviewers[0].reasons == (
        "initial_triage triggers.conversation_patterns=cache miss fallback",
    )


def test_review_config_hash_includes_context_budget_limits() -> None:
    base = {
        "agents": {
            "correctness": {
                "stages": ["initial_triage"],
                "triggers": {"always": True},
            }
        }
    }
    low_budget = parse_reviewer_config({**base, "context_budget": {"max_reviewers": 1}})
    high_budget = parse_reviewer_config({**base, "context_budget": {"max_reviewers": 2}})

    assert _review_config_hash(low_budget) != _review_config_hash(high_budget)
