import json
from importlib import resources

from reviewgraph.runner import run_fixture_dry_run


def test_optional_reviewer_failure_records_partial_review_without_blocking_post(tmp_path) -> None:
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"].append(
        {
            "reviewer": "optional-check",
            "stage": "initial_triage",
            "failure": True,
            "error": "optional reviewer failed with token ghp_abcdefghijklmnopqrstuvwxyz123456",
            "items": [],
        }
    )
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(json.dumps(_optional_initial_triage_config()))
    fixture_path = tmp_path / "optional-failure.json"
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path), reviewer_config_path=str(config_path))

    assert result.json_data["post_enabled"] is True
    assert result.json_data["errors"] == []
    assert result.json_data["partial_review"] == {
        "has_partial_review": True,
        "failed_optional_reviewers": [
            {
                "reviewer": "optional-check",
                "stage": "initial_triage",
                "status": "failed",
                "required": False,
                "reason": "optional reviewer failed with token [REDACTED]",
                "errors": ["optional reviewer failed with token [REDACTED]"],
            }
        ],
    }
    assert [finding["id"] for finding in result.json_data["review"]["classified_output"]["postable_findings"]] == [
        "finding-cache-stale"
    ]
    assert result.json_data["review"]["candidate_payload_preview"] is not None
    assert any(
        note["title"] == "Optional reviewer failed"
        for note in result.json_data["review"]["classified_output"]["local_notes"]
    )
    assert all(
        "Optional reviewer failed" not in item["body"]
        for item in result.json_data["review"]["posting_plan"]["items"]
        if item["public_payload_eligible"]
    )


def test_optional_unrepaired_json_failure_records_partial_review_metadata(tmp_path) -> None:
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"].append(
        {
            "reviewer": "optional-check",
            "stage": "initial_triage",
            "raw_output": '{"items": [',
            "repair_output": '{"items": [',
        }
    )
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(json.dumps(_optional_initial_triage_config()))
    fixture_path = tmp_path / "optional-repair-failure.json"
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path), reviewer_config_path=str(config_path))

    assert result.json_data["post_enabled"] is True
    assert result.json_data["errors"] == []
    assert result.json_data["partial_review"]["has_partial_review"] is True
    assert result.json_data["partial_review"]["failed_optional_reviewers"] == [
        {
            "reviewer": "optional-check",
            "stage": "initial_triage",
            "status": "failed",
            "required": False,
            "reason": "fake reviewer output repair failed",
            "errors": ["fake reviewer output repair failed"],
        }
    ]
    optional_result = [
        reviewer_result
        for reviewer_result in result.json_data["reviewer_results"]
        if reviewer_result["reviewer"] == "optional-check"
    ][0]
    assert optional_result["repair_record"]["status"] == "failed"


def test_optional_failure_in_initial_stage_continues_to_later_stage_output(tmp_path) -> None:
    fixture = _basic_fixture()
    finding = fixture["raw_reviewer_outputs"][0]["items"][0]
    fixture["raw_reviewer_outputs"].append(
        {
            "reviewer": "optional-check",
            "stage": "initial_triage",
            "failure": True,
            "error": "optional reviewer failed deterministically",
            "items": [],
        }
    )
    fixture["raw_reviewer_outputs"].append(
        {
            "reviewer": "specialist",
            "stage": "specialized_review",
            "items": [
                {
                    **finding,
                    "id": "finding-specialized-cache",
                    "title": "Cache miss exposes stale fallback to callers",
                    "evidence": "Changed line 12 returns stale fallback data on a cache miss.",
                }
            ],
        }
    )
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(json.dumps(_later_stage_config()))
    fixture_path = tmp_path / "optional-failure-later-stage.json"
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path), reviewer_config_path=str(config_path))

    assert result.json_data["post_enabled"] is True
    assert result.json_data["partial_review"]["failed_optional_reviewers"][0]["reviewer"] == "optional-check"
    assert [
        (reviewer_result["reviewer"], reviewer_result["stage"], reviewer_result["status"])
        for reviewer_result in result.json_data["reviewer_results"]
    ] == [
        ("correctness", "initial_triage", "completed"),
        ("optional-check", "initial_triage", "failed"),
        ("specialist", "specialized_review", "completed"),
    ]
    assert [finding["id"] for finding in result.json_data["review"]["classified_output"]["postable_findings"]] == [
        "finding-cache-stale",
        "finding-specialized-cache",
    ]
    assert "complete_initial_triage_start_specialized_review" in {
        transition["transition_reason"] for transition in result.json_data["graph_trace"]
    }


def _basic_fixture() -> dict[str, object]:
    return json.loads(resources.files("reviewgraph").joinpath("fixtures_data/prs/basic-pr.json").read_text())


def _optional_initial_triage_config() -> dict[str, object]:
    return {
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


def _later_stage_config() -> dict[str, object]:
    config = _optional_initial_triage_config()
    config["agents"]["specialist"] = {
        "stages": ["specialized_review"],
        "triggers": {"always": True},
        "required": False,
    }
    return config
