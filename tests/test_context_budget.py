import json
from dataclasses import replace
from pathlib import Path

import pytest

from reviewgraph.config import ConfigError, parse_reviewer_config
from reviewgraph.context_budget import (
    apply_input_context_budget,
    apply_reviewer_budget,
    default_context_budget,
    merge_context_budgets,
)
from reviewgraph.fixtures import load_fixture_pr
from reviewgraph.memory import build_conversation_memory
from reviewgraph.models import (
    ContextBudget,
    PullRequestChangedFile,
    SelectedReviewer,
)
from reviewgraph.reviewer_context import build_reviewer_context_package
from reviewgraph.runner import run_fixture_dry_run


def test_budget_caps_changed_files_patch_and_memory() -> None:
    fixture = load_fixture_pr("basic-pr")
    first_file = fixture.pr.changed_files[0]
    second_file = PullRequestChangedFile(
        path="src/extra.py",
        patch="+added\n",
        additions=1,
        deletions=0,
    )
    pr = replace(fixture.pr, changed_files=(first_file, second_file))
    memory = build_conversation_memory(pr)
    limits = ContextBudget(
        max_changed_files=1,
        max_patch_bytes=8,
        max_memory_bytes=64,
        max_reviewers=4,
        max_live_calls=4,
    )

    result = apply_input_context_budget(pr=pr, memory=memory, limits=limits)

    assert result.context_budget.original_changed_file_count == 2
    assert result.context_budget.retained_changed_file_count == 1
    assert result.context_budget.omitted_file_paths == ("src/cache.py", "src/extra.py")
    assert result.pr.changed_files[0].patch is None
    assert result.pr.changed_files[0].patch_status == "budget_truncated"
    assert result.context_budget.original_memory_count == len(memory.entries)
    assert result.context_budget.omitted_memory_ids
    assert "patch_byte_budget_exceeded" in result.context_budget.reasons
    assert "changed_file_count_exceeded" in result.context_budget.reasons
    assert "memory_byte_budget_exceeded" in result.context_budget.reasons


def test_oversized_fixture_missing_patch_becomes_budget_marker() -> None:
    fixture = load_fixture_pr("oversized-change")
    memory = build_conversation_memory(fixture.pr)

    result = apply_input_context_budget(
        pr=fixture.pr,
        memory=memory,
        limits=default_context_budget(),
    )

    assert result.pr.changed_files[0].patch is None
    assert result.context_budget.omitted_file_paths == ("src/settings/migration.py",)
    assert result.context_budget.omitted_context[0].reason_code == "fixture_patch_truncated"
    assert "fixture_patch_truncated" in result.context_budget.reasons


def test_reviewer_count_and_live_call_budgets_defer_reviewers() -> None:
    reviewers = (
        SelectedReviewer(name="alpha", stage="initial_triage", reasons=("always",)),
        SelectedReviewer(name="beta", stage="initial_triage", reasons=("always",)),
        SelectedReviewer(name="gamma", stage="initial_triage", reasons=("always",)),
    )
    reviewer_cap = ContextBudget(
        max_changed_files=10,
        max_patch_bytes=10_000,
        max_memory_bytes=10_000,
        max_reviewers=1,
        max_live_calls=10,
    )
    live_cap = ContextBudget(
        max_changed_files=10,
        max_patch_bytes=10_000,
        max_memory_bytes=10_000,
        max_reviewers=10,
        max_live_calls=1,
    )

    reviewer_result = apply_reviewer_budget(reviewers=reviewers, limits=reviewer_cap)
    live_result = apply_reviewer_budget(
        reviewers=reviewers[:2],
        limits=live_cap,
        live_call_costs={"initial_triage:alpha": 1, "initial_triage:beta": 1},
    )

    assert [reviewer.name for reviewer in reviewer_result.retained_reviewers] == ["alpha"]
    assert [reviewer.name for reviewer in reviewer_result.deferred_reviewers] == ["beta", "gamma"]
    assert reviewer_result.context_budget.deferred_reviewer_ids == (
        "initial_triage:beta",
        "initial_triage:gamma",
    )
    assert [note.title for note in reviewer_result.local_notes] == [
        "Reviewer deferred by context budget",
        "Reviewer deferred by context budget",
    ]
    assert [reviewer.name for reviewer in live_result.retained_reviewers] == ["alpha"]
    assert [reviewer.name for reviewer in live_result.deferred_reviewers] == ["beta"]
    assert live_result.context_budget.planned_live_calls == 1
    assert live_result.context_budget.deferred_live_call_reviewer_ids == ("initial_triage:beta",)


def test_reviewer_context_package_contains_budget_truncation_and_markers() -> None:
    fixture = load_fixture_pr("basic-pr")
    memory = build_conversation_memory(fixture.pr)
    limits = ContextBudget(
        max_changed_files=10,
        max_patch_bytes=4,
        max_memory_bytes=10_000,
        max_reviewers=4,
        max_live_calls=4,
    )
    budgeted = apply_input_context_budget(pr=fixture.pr, memory=memory, limits=limits)
    reviewer = SelectedReviewer(
        name="correctness",
        stage="initial_triage",
        reasons=("initial_triage triggers.always=true",),
    )

    package = build_reviewer_context_package(
        active_stage="initial_triage",
        reviewer=reviewer,
        budgeted_context=budgeted,
    )

    assert package.context_budget == budgeted.context_budget
    assert package.truncation_notices
    assert package.omitted_context
    assert package.changed_files[0].patch is None
    assert package.memory_references == budgeted.memory.entries


def test_runner_defers_reviewers_before_executing_raw_outputs(tmp_path: Path) -> None:
    fixture = json.loads(Path("src/reviewgraph/fixtures_data/prs/basic-pr.json").read_text())
    fixture["id"] = "budget-defer"
    fixture["pr_ref"] = "fixture:budget-defer"
    fixture["raw_reviewer_outputs"] = [
        {
            "reviewer": "alpha",
            "stage": "initial_triage",
            "items": [
                {
                    "type": "local_note",
                    "id": "note-alpha-ran",
                    "title": "Alpha ran",
                    "body": "Retained reviewer executed.",
                    "evidence": "Budget retained alpha.",
                }
            ],
        },
        {"reviewer": "beta", "stage": "initial_triage"},
    ]
    fixture_path = tmp_path / "budget-defer.json"
    fixture_path.write_text(json.dumps(fixture))
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "context_budget": {"max_reviewers": 1},
                "agents": {
                    "alpha": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                    },
                    "beta": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                    },
                },
            }
        )
    )

    result = run_fixture_dry_run(
        fixture_ref=str(fixture_path),
        reviewer_config_path=str(config_path),
    )
    notes = result.json_data["review"]["classified_output"]["local_notes"]

    assert result.json_data["selected_reviewers"] == [
        {
            "name": "alpha",
            "stage": "initial_triage",
            "reasons": ["initial_triage triggers.always=true"],
        },
        {
            "name": "beta",
            "stage": "initial_triage",
            "reasons": ["initial_triage triggers.always=true"],
        },
    ]
    assert notes[0]["id"].startswith("note-budget-reviewer-initial-triage-beta-")
    assert notes[1]["id"] == "note-alpha-ran"
    assert result.json_data["review"]["context_budget"]["reviewers"]["deferred_ids"] == [
        "initial_triage:beta"
    ]


def test_runner_routes_against_budgeted_changed_files(tmp_path: Path) -> None:
    fixture = json.loads(Path("src/reviewgraph/fixtures_data/prs/basic-pr.json").read_text())
    fixture["id"] = "budget-routes"
    fixture["pr_ref"] = "fixture:budget-routes"
    fixture["changed_files"].append(
        {
            "path": "src/omitted.py",
            "status": "modified",
            "additions": 1,
            "deletions": 0,
            "patch": "+ omitted_trigger = True\n",
            "patch_status": "available",
            "changed_ranges": [{"start": 1, "end": 1}],
        }
    )
    fixture["raw_reviewer_outputs"] = [
        {
            "reviewer": "alpha",
            "stage": "initial_triage",
            "items": [
                {
                    "type": "local_note",
                    "id": "note-alpha-ran",
                    "title": "Alpha ran",
                    "body": "Retained reviewer executed.",
                    "evidence": "Budget retained alpha.",
                }
            ],
        },
    ]
    fixture_path = tmp_path / "budget-routes.json"
    fixture_path.write_text(json.dumps(fixture))
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "context_budget": {"max_changed_files": 1},
                "agents": {
                    "alpha": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                    },
                    "omitted_path": {
                        "stages": ["initial_triage"],
                        "triggers": {"paths": ["src/omitted.py"]},
                    },
                },
            }
        )
    )

    result = run_fixture_dry_run(
        fixture_ref=str(fixture_path),
        reviewer_config_path=str(config_path),
    )

    assert result.json_data["selected_reviewers"] == [
        {
            "name": "alpha",
            "stage": "initial_triage",
            "reasons": ["initial_triage triggers.always=true"],
        }
    ]
    assert result.json_data["review"]["context_budget"]["changed_files"]["omitted_paths"] == [
        "src/omitted.py"
    ]
    note_ids = [note["id"] for note in result.json_data["review"]["classified_output"]["local_notes"]]
    assert "note-omitted-ran" not in note_ids


def test_context_budget_decisions_and_rendered_json_are_deterministic(tmp_path: Path) -> None:
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "context_budget": {
                    "max_changed_files": 10,
                    "max_patch_bytes": 4,
                    "max_memory_bytes": 10_000,
                    "max_reviewers": 10,
                    "max_live_calls": 10,
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

    first = run_fixture_dry_run(fixture_ref="basic-pr", reviewer_config_path=str(config_path))
    second = run_fixture_dry_run(fixture_ref="basic-pr", reviewer_config_path=str(config_path))

    assert first.json_data == second.json_data
    assert first.json_data["review"]["context_budget"]["changed_files"]["omitted_paths"] == ["src/cache.py"]


def test_runner_suppresses_findings_from_omitted_patch_context(tmp_path: Path) -> None:
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "context_budget": {
                    "max_changed_files": 10,
                    "max_patch_bytes": 4,
                    "max_memory_bytes": 10_000,
                    "max_reviewers": 10,
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

    result = run_fixture_dry_run(fixture_ref="basic-pr", reviewer_config_path=str(config_path))
    classified = result.json_data["review"]["classified_output"]

    assert result.json_data["post_enabled"] is False
    assert classified["postable_findings"] == []
    assert classified["suppressed"] == [
        {
            "id": "finding-cache-stale",
            "classification": "non_finding",
            "reason": "Finding candidate referenced context omitted by context budget.",
        },
        {
            "id": "suppressed-generic-tests",
            "classification": "non_finding",
            "reason": "Generic missing-test advice without a concrete changed behavior was suppressed.",
        },
    ]
    assert result.json_data["review"]["context_budget"]["changed_files"]["omitted_paths"] == ["src/cache.py"]


def test_runner_suppresses_findings_from_fully_omitted_files(tmp_path: Path) -> None:
    fixture = json.loads(Path("src/reviewgraph/fixtures_data/prs/basic-pr.json").read_text())
    fixture["id"] = "budget-omitted-finding"
    fixture["pr_ref"] = "fixture:budget-omitted-finding"
    fixture["changed_files"].append(
        {
            "path": "src/omitted.py",
            "status": "modified",
            "additions": 1,
            "deletions": 0,
            "patch": "+ omitted_trigger = True\n",
            "patch_status": "available",
            "changed_ranges": [{"start": 1, "end": 1}],
        }
    )
    fixture["raw_reviewer_outputs"] = [
        {
            "reviewer": "alpha",
            "stage": "initial_triage",
            "items": [
                {
                    "type": "finding",
                    "id": "finding-omitted-file",
                    "title": "Omitted file finding",
                    "rationale": "The new branch fails when omitted context is used.",
                    "evidence": "Changed line 1 now references omitted context.",
                    "path": "src/omitted.py",
                    "line": 1,
                    "severity": "warning",
                    "confidence": "high",
                }
            ],
        }
    ]
    fixture_path = tmp_path / "budget-omitted-finding.json"
    fixture_path.write_text(json.dumps(fixture))
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "context_budget": {"max_changed_files": 1},
                "agents": {
                    "alpha": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                    }
                },
            }
        )
    )

    result = run_fixture_dry_run(
        fixture_ref=str(fixture_path),
        reviewer_config_path=str(config_path),
    )

    classified = result.json_data["review"]["classified_output"]
    assert result.json_data["post_enabled"] is False
    assert classified["postable_findings"] == []
    assert classified["suppressed"] == [
        {
            "id": "finding-omitted-file",
            "classification": "non_finding",
            "reason": "Finding candidate referenced context omitted by context budget.",
        }
    ]
    assert result.json_data["review"]["context_budget"]["changed_files"]["omitted_paths"] == [
        "src/omitted.py"
    ]


def test_invalid_context_budget_config_fails_clearly() -> None:
    data = _valid_config()
    data["context_budget"] = {"max_reviewers": 0}

    with pytest.raises(ConfigError, match="context_budget.max_reviewers"):
        parse_reviewer_config(data)

    data = _valid_config()
    data["context_budget"] = {"unknown": 1}

    with pytest.raises(ConfigError, match="unsupported fields"):
        parse_reviewer_config(data)


def test_context_budget_merge_preserves_input_and_reviewer_decisions() -> None:
    fixture = load_fixture_pr("basic-pr")
    input_budget = apply_input_context_budget(
        pr=fixture.pr,
        memory=build_conversation_memory(fixture.pr),
        limits=ContextBudget(
            max_changed_files=10,
            max_patch_bytes=4,
            max_memory_bytes=10_000,
            max_reviewers=1,
            max_live_calls=1,
        ),
    )
    reviewer_budget = apply_reviewer_budget(
        reviewers=(
            SelectedReviewer(name="alpha", stage="initial_triage", reasons=("always",)),
            SelectedReviewer(name="beta", stage="initial_triage", reasons=("always",)),
        ),
        limits=input_budget.context_budget,
    )

    merged = merge_context_budgets(input_budget.context_budget, reviewer_budget.context_budget)

    assert merged.omitted_file_paths == ("src/cache.py",)
    assert merged.deferred_reviewer_ids == ("initial_triage:beta",)
    assert merged.generated_local_note_ids[0].startswith("note-budget-patch-src-cache-py-")
    assert merged.generated_local_note_ids[1].startswith("note-budget-reviewer-initial-triage-beta-")


def test_budget_marker_ids_are_collision_safe_for_slug_equivalent_paths() -> None:
    fixture = load_fixture_pr("basic-pr")
    keep_file = PullRequestChangedFile(
        path="src/keep.py",
        patch="+ keep\n",
        additions=1,
        deletions=0,
    )
    first_file = PullRequestChangedFile(
        path="src/a-b.py",
        patch="+ one\n",
        additions=1,
        deletions=0,
    )
    second_file = PullRequestChangedFile(
        path="src/a/b.py",
        patch="+ two\n",
        additions=1,
        deletions=0,
    )
    pr = replace(fixture.pr, changed_files=(keep_file, first_file, second_file))

    result = apply_input_context_budget(
        pr=pr,
        memory=build_conversation_memory(pr),
        limits=ContextBudget(
            max_changed_files=1,
            max_patch_bytes=10_000,
            max_memory_bytes=10_000,
            max_reviewers=4,
            max_live_calls=0,
        ),
    )

    marker_ids = [marker.id for marker in result.context_budget.omitted_context]
    note_ids = [note.id for note in result.local_notes]
    assert len(marker_ids) == 2
    assert len(set(marker_ids)) == 2
    assert all(marker_id.startswith("budget-changed-files-src-a-b-py-") for marker_id in marker_ids)
    assert note_ids == [f"note-{marker_id}" for marker_id in marker_ids]


def _valid_config() -> dict[str, object]:
    return {
        "agents": {
            "correctness": {
                "description": "Checks correctness.",
                "stages": ["initial_triage"],
                "triggers": {"always": True},
                "required": True,
                "verdict_power": "comment",
                "capabilities": ["diff_context"],
            }
        }
    }
