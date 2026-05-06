import json
from importlib import resources

import pytest

from reviewgraph.runner import RunnerError, run_fixture_dry_run


def test_required_reviewer_failure_fails_closed_without_aborting_dry_run(tmp_path) -> None:
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0] = {
        "reviewer": "correctness",
        "stage": "initial_triage",
        "failure": True,
        "error": "required reviewer failed before classification",
        "items": [],
    }
    fixture_path = tmp_path / "required-failure.json"
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))

    assert result.json_data["post_enabled"] is False
    assert result.json_data["side_effects"] == {"writer_called": False, "writer_call_count": 0}
    assert result.json_data["errors"] == [
        {
            "code": "required_reviewer_failed",
            "message": (
                "Required reviewer correctness failed during initial_triage: "
                "required reviewer failed before classification"
            ),
            "retryable": False,
        }
    ]
    assert result.json_data["reviewer_results"][0]["status"] == "failed"
    assert result.json_data["reviewer_results"][0]["errors"] == [
        "required reviewer failed before classification"
    ]
    assert result.json_data["reviewer_run_status"][0]["status"] == "failed"
    assert result.json_data["review"]["candidate_payload_preview"] is None
    assert all(
        not item["public_payload_eligible"]
        for item in result.json_data["review"]["posting_plan"]["items"]
    )
    assert result.json_data["review"]["classified_output"]["local_notes"][0]["title"] == (
        "Required reviewer failed"
    )


def test_required_failure_forces_local_only_plan_even_with_other_findings(tmp_path) -> None:
    fixture = _basic_fixture()
    finding = fixture["raw_reviewer_outputs"][0]["items"][0]
    fixture["raw_reviewer_outputs"] = [
        {
            "reviewer": "correctness",
            "stage": "initial_triage",
            "failure": True,
            "error": "correctness timed out",
            "items": [],
        },
        {
            "reviewer": "optional-check",
            "stage": "initial_triage",
            "items": [{**finding, "id": "finding-optional-cache"}],
        },
    ]
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "correctness": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                        "required": True,
                    },
                    "optional-check": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                        "required": False,
                    },
                }
            }
        )
    )
    fixture_path = tmp_path / "required-failure-with-finding.json"
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path), reviewer_config_path=str(config_path))

    assert [item["id"] for item in result.json_data["review"]["classified_output"]["postable_findings"]] == [
        "finding-optional-cache"
    ]
    assert result.json_data["post_enabled"] is False
    assert result.json_data["review"]["candidate_payload_preview"] is None
    assert all(
        item["destination"] == "local_only"
        for item in result.json_data["review"]["posting_plan"]["items"]
    )


def test_optional_reviewer_failure_does_not_block_post_eligibility(tmp_path) -> None:
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"].append(
        {
            "reviewer": "optional-check",
            "stage": "initial_triage",
            "failure": True,
            "error": "optional reviewer failed deterministically",
            "items": [],
        }
    )
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "correctness": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                        "required": True,
                    },
                    "optional-check": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                        "required": False,
                    },
                }
            }
        )
    )
    fixture_path = tmp_path / "optional-failure.json"
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path), reviewer_config_path=str(config_path))

    assert result.json_data["post_enabled"] is True
    assert result.json_data["errors"] == []
    assert result.json_data["reviewer_results"][1]["status"] == "failed"
    assert result.json_data["reviewer_results"][1]["errors"] == [
        "optional reviewer failed deterministically"
    ]
    assert result.json_data["review"]["candidate_payload_preview"] is not None
    assert any(
        item["title"] == "Optional reviewer failed"
        for item in result.json_data["review"]["classified_output"]["local_notes"]
    )


def test_required_failure_does_not_hide_unselected_raw_outputs(tmp_path) -> None:
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"] = [
        {
            "reviewer": "correctness",
            "stage": "initial_triage",
            "failure": True,
            "error": "correctness timed out",
            "items": [],
        },
        {
            "reviewer": "never-selected",
            "stage": "initial_triage",
            "items": [],
        },
    ]
    fixture_path = tmp_path / "required-failure-extra-raw.json"
    fixture_path.write_text(json.dumps(fixture))

    with pytest.raises(RunnerError, match="raw reviewer output was not selected: never-selected/initial_triage"):
        run_fixture_dry_run(fixture_ref=str(fixture_path))


def _basic_fixture() -> dict[str, object]:
    return json.loads(resources.files("reviewgraph").joinpath("fixtures_data/prs/basic-pr.json").read_text())
