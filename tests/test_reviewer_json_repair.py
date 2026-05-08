import json
from importlib import resources

import pytest

from reviewgraph.context_budget import ContextBudget, apply_input_context_budget
from reviewgraph.config import parse_reviewer_config
from reviewgraph.memory import build_conversation_memory
from reviewgraph.models import ReviewerRunStatusValue, SelectedReviewer
from reviewgraph.reviewer_context import build_reviewer_context_package
from reviewgraph.reviewer_runs import make_reviewer_run_key
from reviewgraph.reviewers import FakeReviewerAdapter, execute_fake_reviewer, fake_registry_from_fixture_outputs
from reviewgraph.runner import run_fixture_dry_run


def test_invalid_raw_string_repairs_once_and_normalizes_repaired_output() -> None:
    package, run_key = _package_and_key(reviewer_name="quality")
    finding = _basic_fixture()["raw_reviewer_outputs"][0]["items"][0]
    registry = fake_registry_from_fixture_outputs(
        fixture_id="basic-pr",
        outputs=[
            {
                "reviewer": "quality",
                "stage": "initial_triage",
                "raw_output": '{"items": [',
                "repair_output": {
                    "items": [
                        {**finding, "id": "finding-repaired-cache"}
                    ]
                },
            }
        ],
    )

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.COMPLETED
    assert result.raw_output == '{"items": ['
    assert result.repair_record is not None
    assert result.repair_record.attempt_count == 1
    assert result.repair_record.status == "succeeded"
    assert result.repair_record.original_output == '{"items": ['
    assert result.repair_record.repaired_output["items"][0]["id"] == "finding-repaired-cache"
    assert [error.code for error in result.repair_record.errors] == ["invalid_json"]
    assert result.findings[0].id == "finding-repaired-cache"


def test_valid_raw_json_string_normalizes_without_repairing() -> None:
    package, run_key = _package_and_key(reviewer_name="quality")
    finding = _basic_fixture()["raw_reviewer_outputs"][0]["items"][0]
    raw_output = json.dumps({"items": [{**finding, "id": "finding-raw-json-string"}]})
    registry = fake_registry_from_fixture_outputs(
        fixture_id="basic-pr",
        outputs=[
            {
                "reviewer": "quality",
                "stage": "initial_triage",
                "raw_output": raw_output,
                "repair_output": {
                    "items": [
                        {**finding, "id": "finding-should-not-be-used"}
                    ]
                },
            }
        ],
    )

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.COMPLETED
    assert result.raw_output == raw_output
    assert result.repair_record is None
    assert [finding.id for finding in result.findings] == ["finding-raw-json-string"]


def test_valid_non_object_raw_json_string_does_not_repair() -> None:
    package, run_key = _package_and_key(reviewer_name="quality")
    finding = _basic_fixture()["raw_reviewer_outputs"][0]["items"][0]
    registry = fake_registry_from_fixture_outputs(
        fixture_id="basic-pr",
        outputs=[
            {
                "reviewer": "quality",
                "stage": "initial_triage",
                "raw_output": "[]",
                "repair_output": {
                    "items": [
                        {**finding, "id": "finding-should-not-be-used"}
                    ]
                },
            }
        ],
    )

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.FAILED
    assert result.raw_output == "[]"
    assert result.repair_record is None
    assert result.normalization_errors[0].code == "invalid_output_type"
    assert result.normalization_errors[0].repairable is False


def test_non_mapping_repair_envelope_payloads_are_preserved_in_repair_record() -> None:
    package, run_key = _package_and_key(reviewer_name="quality")
    registry = fake_registry_from_fixture_outputs(
        fixture_id="basic-pr",
        outputs=[
            {
                "reviewer": "quality",
                "stage": "initial_triage",
                "raw_output": ["not", "a", "mapping"],
                "repair_output": ["still", "not", "a", "mapping"],
            }
        ],
    )

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.FAILED
    assert result.repair_record is not None
    assert result.repair_record.original_output == ["not", "a", "mapping"]
    assert result.repair_record.repaired_output == ["still", "not", "a", "mapping"]
    assert [error.code for error in result.repair_record.errors] == [
        "invalid_output_type",
        "repair_invalid_output_type",
    ]


def test_successful_repair_classifies_through_existing_runner_policy(tmp_path) -> None:
    fixture = _basic_fixture()
    finding = fixture["raw_reviewer_outputs"][0]["items"][0]
    fixture["raw_reviewer_outputs"][0] = {
        "reviewer": "correctness",
        "stage": "initial_triage",
        "raw_output": '{"items": [',
        "repair_output": {
            "items": [
                {**finding, "id": "finding-repaired-cache"}
            ]
        },
    }
    fixture_path = tmp_path / "repair-success.json"
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))

    assert result.json_data["post_enabled"] is True
    assert result.json_data["errors"] == []
    assert result.json_data["reviewer_results"][0]["raw_output"] == '{"items": ['
    assert result.json_data["reviewer_results"][0]["repair_record"]["attempt_count"] == 1
    assert result.json_data["reviewer_results"][0]["repair_record"]["status"] == "succeeded"
    assert [finding["id"] for finding in result.json_data["review"]["classified_output"]["postable_findings"]] == [
        "finding-repaired-cache"
    ]


def test_failed_repair_records_structured_original_and_repair_errors() -> None:
    package, run_key = _package_and_key(reviewer_name="quality")
    registry = fake_registry_from_fixture_outputs(
        fixture_id="basic-pr",
        outputs=[
            {
                "reviewer": "quality",
                "stage": "initial_triage",
                "raw_output": '{"items": [',
                "repair_output": '{"items": [',
            }
        ],
    )

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.FAILED
    assert result.raw_output == '{"items": ['
    assert result.errors == ("fake reviewer output repair failed",)
    assert result.repair_record is not None
    assert result.repair_record.attempt_count == 1
    assert result.repair_record.status == "failed"
    assert result.repair_record.original_output == '{"items": ['
    assert result.repair_record.repaired_output == '{"items": ['
    assert [error.code for error in result.repair_record.errors] == ["invalid_json", "repair_invalid_json"]
    assert [error.code for error in result.normalization_errors] == ["invalid_json", "repair_invalid_json"]


def test_required_unrepaired_failure_blocks_posting_but_keeps_other_outputs(tmp_path) -> None:
    fixture = _basic_fixture()
    finding = fixture["raw_reviewer_outputs"][0]["items"][0]
    fixture["raw_reviewer_outputs"] = [
        {
            "reviewer": "correctness",
            "stage": "initial_triage",
            "raw_output": '{"items": [',
            "repair_output": '{"items": [',
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
    fixture_path = tmp_path / "required-repair-failure.json"
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path), reviewer_config_path=str(config_path))

    assert [finding["id"] for finding in result.json_data["review"]["classified_output"]["postable_findings"]] == [
        "finding-optional-cache"
    ]
    assert result.json_data["post_enabled"] is False
    assert result.json_data["review"]["candidate_payload_preview"] is None
    assert result.json_data["errors"][0]["code"] == "required_reviewer_failed"
    assert result.json_data["reviewer_results"][0]["status"] == "failed"
    assert result.json_data["reviewer_results"][0]["repair_record"]["status"] == "failed"


def test_required_explicit_failure_json_string_is_fail_closed(tmp_path) -> None:
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0] = {
        "reviewer": "correctness",
        "stage": "initial_triage",
        "raw_output": json.dumps(
            {
                "failure": True,
                "error": "required reviewer failed before output",
            }
        ),
        "repair_output": {"items": []},
    }
    fixture_path = tmp_path / "required-json-string-failure.json"
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))

    assert result.json_data["post_enabled"] is False
    assert result.json_data["errors"][0]["code"] == "required_reviewer_failed"
    assert "required reviewer failed before output" in result.json_data["errors"][0]["message"]
    assert result.json_data["reviewer_results"][0]["status"] == "failed"
    assert result.json_data["reviewer_results"][0]["repair_record"] is None


def test_required_unrepaired_failure_continues_into_later_stages(tmp_path) -> None:
    fixture = _basic_fixture()
    finding = fixture["raw_reviewer_outputs"][0]["items"][0]
    fixture["raw_reviewer_outputs"] = [
        {
            "reviewer": "correctness",
            "stage": "initial_triage",
            "raw_output": '{"items": [',
            "repair_output": '{"items": [',
        },
        {
            "reviewer": "specialist",
            "stage": "specialized_review",
            "items": [{**finding, "id": "finding-later-stage-cache"}],
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
                    "specialist": {
                        "stages": ["specialized_review"],
                        "triggers": {"always": True},
                        "required": False,
                    },
                }
            }
        )
    )
    fixture_path = tmp_path / "required-repair-failure-later-stage.json"
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path), reviewer_config_path=str(config_path))

    assert result.json_data["post_enabled"] is False
    assert result.json_data["errors"][0]["code"] == "required_reviewer_failed"
    assert [finding["id"] for finding in result.json_data["review"]["classified_output"]["postable_findings"]] == [
        "finding-later-stage-cache"
    ]
    assert [
        (reviewer_result["reviewer"], reviewer_result["stage"], reviewer_result["status"])
        for reviewer_result in result.json_data["reviewer_results"]
    ] == [
        ("correctness", "initial_triage", "failed"),
        ("specialist", "specialized_review", "completed"),
    ]


def test_optional_unrepaired_failure_continues_as_partial_review(tmp_path) -> None:
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
    fixture_path = tmp_path / "optional-repair-failure.json"
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path), reviewer_config_path=str(config_path))

    assert result.json_data["post_enabled"] is True
    assert result.json_data["errors"] == []
    optional_result = [
        reviewer_result
        for reviewer_result in result.json_data["reviewer_results"]
        if reviewer_result["reviewer"] == "optional-check"
    ][0]
    assert optional_result["status"] == "failed"
    assert optional_result["repair_record"]["attempt_count"] == 1
    assert optional_result["repair_record"]["status"] == "failed"
    assert any(
        note["title"] == "Optional reviewer failed"
        for note in result.json_data["review"]["classified_output"]["local_notes"]
    )


def test_explicit_reviewer_failure_is_not_repaired() -> None:
    package, run_key = _package_and_key(reviewer_name="quality")
    registry = fake_registry_from_fixture_outputs(
        fixture_id="basic-pr",
        outputs=[
            {
                "reviewer": "quality",
                "stage": "initial_triage",
                "failure": True,
                "error": "reviewer failed before output",
            }
        ],
    )

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.FAILED
    assert result.errors == ("reviewer failed before output",)
    assert result.repair_record is None


def test_missing_repair_output_is_fixture_input_error() -> None:
    with pytest.raises(ValueError, match="repair envelope requires repair_output"):
        fake_registry_from_fixture_outputs(
            fixture_id="basic-pr",
            outputs=[
                {
                    "reviewer": "quality",
                    "stage": "initial_triage",
                    "raw_output": '{"items": [',
                }
            ],
        )


def test_missing_raw_output_is_fixture_input_error() -> None:
    with pytest.raises(ValueError, match="repair envelope requires raw_output"):
        fake_registry_from_fixture_outputs(
            fixture_id="basic-pr",
            outputs=[
                {
                    "reviewer": "quality",
                    "stage": "initial_triage",
                    "repair_output": {"items": []},
                }
            ],
        )


@pytest.mark.parametrize(
    ("field", "expected_message"),
    (
        ("reviewer", "reviewer must be a non-empty string"),
        ("stage", "stage must be a non-empty string"),
    ),
)
def test_direct_repair_envelope_requires_reviewer_and_stage(field: str, expected_message: str) -> None:
    package, run_key = _package_and_key(reviewer_name="quality")
    envelope = {
        "reviewer": "quality",
        "stage": "initial_triage",
        "raw_output": '{"items": [',
        "repair_output": {"items": []},
    }
    del envelope[field]

    with pytest.raises(ValueError, match=expected_message):
        execute_fake_reviewer(
            adapter=FakeReviewerAdapter(
                fixture_id="basic-pr",
                registry={("basic-pr", "quality", "initial_triage"): envelope},
            ),
            package=package,
            run_key=run_key,
        )


@pytest.mark.parametrize(
    "override",
    (
        {"reviewer": "other"},
        {"stage": "logic_review"},
    ),
)
def test_direct_repair_envelope_must_match_selected_reviewer_and_stage(override: dict[str, str]) -> None:
    package, run_key = _package_and_key(reviewer_name="quality")
    envelope = {
        "reviewer": "quality",
        "stage": "initial_triage",
        "raw_output": '{"items": [',
        "repair_output": {"items": []},
    }
    envelope.update(override)

    with pytest.raises(ValueError, match="repair envelope reviewer/stage must match"):
        execute_fake_reviewer(
            adapter=FakeReviewerAdapter(
                fixture_id="basic-pr",
                registry={("basic-pr", "quality", "initial_triage"): envelope},
            ),
            package=package,
            run_key=run_key,
        )


@pytest.mark.parametrize("field", ("failure", "items", "error"))
def test_repair_envelope_rejects_extra_top_level_fields(field: str) -> None:
    package, run_key = _package_and_key(reviewer_name="quality")
    envelope = {
        "reviewer": "quality",
        "stage": "initial_triage",
        "raw_output": '{"items": [',
        "repair_output": {"items": []},
        field: True,
    }

    with pytest.raises(ValueError, match="repair envelope contains unsupported fields"):
        execute_fake_reviewer(
            adapter=FakeReviewerAdapter(
                fixture_id="basic-pr",
                registry={("basic-pr", "quality", "initial_triage"): envelope},
            ),
            package=package,
            run_key=run_key,
        )


def test_missing_repair_output_for_optional_reviewer_is_not_downgraded_to_postable(tmp_path) -> None:
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"].append(
        {
            "reviewer": "optional-check",
            "stage": "initial_triage",
            "raw_output": '{"items": [',
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
    fixture_path = tmp_path / "missing-repair-output.json"
    fixture_path.write_text(json.dumps(fixture))

    with pytest.raises(ValueError, match="repair envelope requires repair_output"):
        run_fixture_dry_run(fixture_ref=str(fixture_path), reviewer_config_path=str(config_path))


def _package_and_key(*, reviewer_name: str, required: bool = False):
    from reviewgraph.fixtures import load_fixture_pr

    loaded_fixture = load_fixture_pr("basic-pr")
    memory = build_conversation_memory(loaded_fixture.pr)
    budgeted_context = apply_input_context_budget(
        pr=loaded_fixture.pr,
        memory=memory,
        limits=ContextBudget(
            max_changed_files=10,
            max_patch_bytes=1_000_000,
            max_memory_bytes=1_000_000,
            max_reviewers=10,
            max_live_calls=0,
        ),
    )
    config = parse_reviewer_config(
        {
            "agents": {
                reviewer_name: {
                    "stages": ["initial_triage"],
                    "triggers": {"always": True},
                    "required": required,
                }
            }
        }
    )
    reviewer = SelectedReviewer(
        name=reviewer_name,
        stage="initial_triage",
        reasons=("initial_triage triggers.always=true",),
    )
    package = build_reviewer_context_package(
        active_stage="initial_triage",
        reviewer=reviewer,
        reviewer_config=config.agents[reviewer_name],
        budgeted_context=budgeted_context,
    )
    state = type(
        "ReviewStateLike",
        (),
        {
            "review_target": loaded_fixture.review_target,
            "config_hash": "sha256:config",
        },
    )()
    return package, make_reviewer_run_key(state, reviewer)


def _basic_fixture() -> dict[str, object]:
    return json.loads(resources.files("reviewgraph").joinpath("fixtures_data/prs/basic-pr.json").read_text())
