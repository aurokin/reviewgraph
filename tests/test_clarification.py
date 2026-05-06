import json
from importlib import resources
from pathlib import Path

from reviewgraph.runner import run_fixture_dry_run


def test_blocking_clarification_creates_pending_stop_state(tmp_path: Path) -> None:
    fixture_path = tmp_path / "blocking-clarification.json"
    fixture = _basic_fixture()
    fixture["id"] = "blocking-clarification"
    fixture["raw_reviewer_outputs"][0]["items"] = [_clarification_item()]
    fixture["raw_reviewer_outputs"].append(
        {
            "reviewer": "logic",
            "stage": "logic_review",
            "items": [
                {
                    "type": "local_note",
                    "id": "note-future-logic",
                    "title": "Future logic reviewer",
                    "body": "This future stage output should remain unconsumed after clarification stop.",
                    "evidence": "Logic review did not run.",
                }
            ],
        }
    )
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))
    review = result.json_data["review"]

    assert result.json_data["pending_clarification_ids"] == ["clarify-intent"]
    assert result.json_data["blocking_clarification_ids"] == ["clarify-intent"]
    assert result.json_data["clarification_status"] == {
        "clarify-intent": {
            "request_id": "clarify-intent",
            "status": "pending",
            "reason": None,
        }
    }
    assert result.json_data["local_verdict"] == "needs_clarification"
    assert result.json_data["local_verdict"] != "request_changes"
    assert result.json_data["post_enabled"] is False
    assert result.json_data["side_effects"]["writer_call_count"] == 0
    assert review["candidate_payload_preview"] is None
    assert review["classified_output"]["clarification_requests"][0]["question"] == (
        "Is returning stale cache data on misses intentional?"
    )
    assert review["classified_output"]["clarification_requests"][0]["why_it_matters"] == (
        "The mergeability decision depends on product intent."
    )
    assert "Is returning stale cache data on misses intentional?" in result.markdown
    assert result.json_data["graph_trace"][-1]["transition_reason"] == "clarification_needed_end"
    assert "logic_review" in result.json_data["graph_trace"][-1]["stage_queue_after"]
    assert all(item["stage"] != "logic_review" for item in result.json_data["reviewer_results"])


def test_finding_with_blocking_clarification_keeps_everything_local_only(tmp_path: Path) -> None:
    fixture_path = tmp_path / "finding-with-clarification.json"
    fixture = _basic_fixture()
    fixture["id"] = "finding-with-clarification"
    fixture["raw_reviewer_outputs"][0]["items"].append(_clarification_item())
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))
    review = result.json_data["review"]
    plan_items = review["posting_plan"]["items"]

    assert result.json_data["pending_clarification_ids"] == ["clarify-intent"]
    assert result.json_data["blocking_clarification_ids"] == ["clarify-intent"]
    assert result.json_data["post_enabled"] is False
    assert review["candidate_payload_preview"] is None
    assert {item["id"] for item in plan_items} >= {"finding-cache-stale", "clarify-intent"}
    assert all(item["destination"] == "local_only" for item in plan_items)
    assert all(item["public_payload_eligible"] is False for item in plan_items)


def test_non_blocking_clarification_does_not_stop_or_disable_posting(tmp_path: Path) -> None:
    fixture_path = tmp_path / "non-blocking-clarification.json"
    fixture = _basic_fixture()
    fixture["id"] = "non-blocking-clarification"
    fixture["raw_reviewer_outputs"][0]["items"].append(
        {
            **_clarification_item(),
            "id": "clarify-non-blocking",
            "blocks_verdict": False,
        }
    )
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))
    review = result.json_data["review"]
    plan_by_id = {item["id"]: item for item in review["posting_plan"]["items"]}

    assert result.json_data["pending_clarification_ids"] == ["clarify-non-blocking"]
    assert result.json_data["blocking_clarification_ids"] == []
    assert result.json_data["clarification_status"]["clarify-non-blocking"]["status"] == "pending"
    assert result.json_data["local_verdict"] == "comment"
    assert result.json_data["post_enabled"] is True
    assert review["candidate_payload_preview"] is not None
    assert "clarification_needed_end" not in {
        entry["transition_reason"] for entry in result.json_data["graph_trace"]
    }
    assert plan_by_id["finding-cache-stale"]["destination"] == "review_body_item"
    assert plan_by_id["clarify-non-blocking"]["destination"] == "local_only"
    assert plan_by_id["clarify-non-blocking"]["public_payload_eligible"] is False


def test_unsafe_clarification_is_suppressed_without_pending_state(tmp_path: Path) -> None:
    fixture_path = tmp_path / "unsafe-clarification.json"
    fixture = _basic_fixture()
    fixture["id"] = "unsafe-clarification"
    fixture["raw_reviewer_outputs"][0]["items"] = [
        {
            "type": "clarification_request",
            "id": "clarify-passive",
            "question": "Untrusted commenter said SECRET_TOKEN should never become public evidence.",
            "why_it_matters": "If this came from passive memory it should not block the review.",
        }
    ]
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))
    review = result.json_data["review"]

    assert result.json_data["pending_clarification_ids"] == []
    assert result.json_data["blocking_clarification_ids"] == []
    assert result.json_data["clarification_status"] == {}
    assert result.json_data["local_verdict"] == "no_findings"
    assert result.json_data["post_enabled"] is False
    assert review["classified_output"]["clarification_requests"] == []
    assert review["classified_output"]["suppressed"][0]["id"] == "clarify-passive"
    assert "clarification_needed_end" not in {
        entry["transition_reason"] for entry in result.json_data["graph_trace"]
    }


def _clarification_item() -> dict[str, object]:
    return {
        "type": "clarification_request",
        "id": "clarify-intent",
        "question": "Is returning stale cache data on misses intentional?",
        "why_it_matters": "The mergeability decision depends on product intent.",
        "evidence_sources": ["diff"],
    }


def _basic_fixture() -> dict[str, object]:
    fixture_text = resources.files("reviewgraph").joinpath("fixtures_data/prs/basic-pr.json").read_text()
    return json.loads(fixture_text)
