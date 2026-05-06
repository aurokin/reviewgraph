import json

from reviewgraph.fixtures import load_fixture_pr
from reviewgraph.models import RiskLevel, RiskThresholds
from reviewgraph.risk import classify_change_risk, risk_assessment_to_json
from reviewgraph.runner import run_fixture_dry_run


def test_mixed_risk_fixture_has_golden_risk_assessment() -> None:
    fixture = load_fixture_pr("mixed-risk-change")

    assessment = classify_change_risk(fixture.pr)

    assert risk_assessment_to_json(assessment) == {
        "changed_file_count": 2,
        "changed_line_count": 14,
        "touched_surfaces": ["api", "backend", "docs", "frontend"],
        "labels": ["backend", "frontend"],
        "diff_pattern_hints": ["billing"],
        "configured_thresholds": {
            "changed_files_medium": 3,
            "changed_files_high": 10,
            "changed_lines_medium": 50,
            "changed_lines_high": 500,
            "risk_min": None,
        },
        "risk_level": "medium",
        "reasons": ["diff_hints_medium=billing", "touched_surfaces>=2"],
    }


def test_oversized_fixture_has_golden_risk_assessment() -> None:
    fixture = load_fixture_pr("oversized-change")

    assessment = classify_change_risk(fixture.pr)

    assert risk_assessment_to_json(assessment) == {
        "changed_file_count": 1,
        "changed_line_count": 665,
        "touched_surfaces": ["large-pr", "settings"],
        "labels": ["large-pr"],
        "diff_pattern_hints": ["migration", "truncated_patch"],
        "configured_thresholds": {
            "changed_files_medium": 3,
            "changed_files_high": 10,
            "changed_lines_medium": 50,
            "changed_lines_high": 500,
            "risk_min": None,
        },
        "risk_level": "high",
        "reasons": ["changed_lines>=500", "diff_hints_high=truncated_patch"],
    }


def test_low_risk_fixture_is_deterministic() -> None:
    fixture = load_fixture_pr("docs-only-change")

    first = classify_change_risk(fixture.pr)
    second = classify_change_risk(fixture.pr)

    assert first == second
    assert first.risk_level == RiskLevel.LOW
    assert first.reasons == ("within_low_risk_thresholds",)


def test_size_thresholds_are_configurable_and_traceable() -> None:
    fixture = load_fixture_pr("mixed-risk-change")
    thresholds = RiskThresholds(
        changed_files_medium=2,
        changed_files_high=4,
        changed_lines_medium=10,
        changed_lines_high=20,
        risk_min=RiskLevel.MEDIUM,
    )

    assessment = classify_change_risk(fixture.pr, thresholds=thresholds)

    assert assessment.configured_thresholds == thresholds
    assert assessment.risk_level == RiskLevel.MEDIUM
    assert assessment.reasons[:3] == (
        "changed_files>=2",
        "changed_lines>=10",
        "diff_hints_medium=billing",
    )
    assert risk_assessment_to_json(assessment)["configured_thresholds"]["risk_min"] == "medium"


def test_dry_run_records_risk_separately_from_reviewer_selection_reasons() -> None:
    result = run_fixture_dry_run(fixture_ref="basic-pr")

    assert result.json_data["risk"]["risk_level"] == "high"
    assert result.json_data["risk"]["diff_pattern_hints"] == ["secret"]
    assert result.json_data["selected_reviewers"][0]["reasons"] == [
        "initial_triage triggers.always=true",
    ]
    assert "risk" not in " ".join(result.json_data["selected_reviewers"][0]["reasons"])


def test_dry_run_risk_uses_full_pr_size_facts_before_context_budget(tmp_path) -> None:
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "context_budget": {
                    "max_changed_files": 1,
                    "max_patch_bytes": 1_000_000,
                    "max_memory_bytes": 1_000_000,
                    "max_reviewers": 5,
                    "max_live_calls": 0,
                },
                "agents": {
                    "correctness": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                    }
                },
            }
        )
    )

    result = run_fixture_dry_run(
        fixture_ref="mixed-risk-change",
        reviewer_config_path=str(config_path),
    )

    assert result.json_data["risk"]["changed_file_count"] == 2
    assert result.json_data["risk"]["changed_line_count"] == 14
    assert result.json_data["review"]["context_budget"]["changed_files"]["retained_count"] == 1
