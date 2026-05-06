from reviewgraph.config import parse_reviewer_config
from reviewgraph.fixtures import load_fixture_pr
from reviewgraph.graph import run_empty_fixture_dry_run_graph
from reviewgraph.models import ReviewStage
from reviewgraph.posting import canonical_json_hash
from reviewgraph.risk import classify_change_risk
from reviewgraph.routing import select_reviewers_for_active_stage, select_reviewers_for_stage


def test_risk_min_gate_selects_from_review_state_risk() -> None:
    state = run_empty_fixture_dry_run_graph(fixture_ref="mixed-risk-change").review_state
    state.config = parse_reviewer_config(
        {
            "agents": {
                "logic": {
                    "stages": ["initial_triage"],
                    "triggers": {"risk_min": "medium"},
                }
            }
        }
    )
    state.config_hash = canonical_json_hash({"agents": ["logic"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE

    selected = select_reviewers_for_active_stage(state)

    assert [reviewer.name for reviewer in selected] == ["logic"]
    assert selected[0].reasons == ("initial_triage triggers.risk_min>=medium",)


def test_risk_min_gate_does_not_select_when_state_risk_is_too_low() -> None:
    state = run_empty_fixture_dry_run_graph(fixture_ref="docs-only-change").review_state
    state.config = parse_reviewer_config(
        {
            "agents": {
                "security": {
                    "stages": ["initial_triage"],
                    "triggers": {"risk_min": "medium"},
                }
            }
        }
    )
    state.config_hash = canonical_json_hash({"agents": ["security"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE

    assert select_reviewers_for_active_stage(state) == ()
    assert state.selected_reviewers == []


def test_size_gates_are_applied_from_risk_assessment_counts() -> None:
    fixture = load_fixture_pr("mixed-risk-change")
    config = parse_reviewer_config(
        {
            "agents": {
                "size": {
                    "stages": ["initial_triage"],
                    "triggers": {
                        "changed_files_min": 2,
                        "changed_lines_min": 14,
                        "max_files": 2,
                    },
                }
            }
        }
    )

    selected = select_reviewers_for_stage(
        config,
        fixture.pr,
        ReviewStage.INITIAL_TRIAGE,
        risk=classify_change_risk(fixture.pr),
    )

    assert [reviewer.name for reviewer in selected] == ["size"]
    assert selected[0].reasons == (
        "initial_triage triggers.max_files<=2",
        "initial_triage triggers.changed_files_min>=2",
        "initial_triage triggers.changed_lines_min>=14",
    )


def test_size_gate_failure_suppresses_gate_only_reviewer() -> None:
    state = run_empty_fixture_dry_run_graph(fixture_ref="mixed-risk-change").review_state
    state.config = parse_reviewer_config(
        {
            "agents": {
                "too-large": {
                    "stages": ["initial_triage"],
                    "triggers": {"max_files": 1},
                }
            }
        }
    )
    state.config_hash = canonical_json_hash({"agents": ["too-large"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE

    assert select_reviewers_for_active_stage(state) == ()
    assert state.selected_reviewers == []
    assert state.reviewer_run_keys == []


def test_gate_only_reviewer_can_be_selected_when_all_gates_pass() -> None:
    state = run_empty_fixture_dry_run_graph(fixture_ref="oversized-change").review_state
    state.config = parse_reviewer_config(
        {
            "agents": {
                "large-change": {
                    "stages": ["initial_triage"],
                    "triggers": {
                        "risk_min": "high",
                        "changed_lines_min": 500,
                        "changed_files_min": 1,
                        "max_files": 2,
                    },
                }
            }
        }
    )
    state.config_hash = canonical_json_hash({"agents": ["large-change"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE

    selected = select_reviewers_for_active_stage(state)

    assert [reviewer.name for reviewer in selected] == ["large-change"]
    assert selected[0].reasons == (
        "initial_triage triggers.max_files<=2",
        "initial_triage triggers.changed_files_min>=1",
        "initial_triage triggers.changed_lines_min>=500",
        "initial_triage triggers.risk_min>=high",
    )
