import json
import inspect
from importlib import resources

from reviewgraph.config import parse_reviewer_config
from reviewgraph.context_budget import ContextBudget, apply_input_context_budget
from reviewgraph.fixtures import load_fixture_pr
from reviewgraph.memory import build_conversation_memory
from reviewgraph.models import ReviewerRunStatusValue, ReviewStage, SelectedReviewer
from reviewgraph.posting import canonical_json_hash
from reviewgraph.reviewer_context import build_reviewer_context_package
from reviewgraph.reviewer_runs import make_reviewer_run_key
from reviewgraph.reviewers import FakeReviewerAdapter, execute_fake_reviewer, fake_registry_from_fixture_outputs
from reviewgraph.runner import run_fixture_dry_run


def test_fake_reviewer_returns_all_structured_output_types() -> None:
    package, run_key = _package_and_key(reviewer_name="quality")
    registry = fake_registry_from_fixture_outputs(
        fixture_id="basic-pr",
        outputs=[
            {
                "reviewer": "quality",
                "stage": "initial_triage",
                "items": [
                    {
                        "type": "finding",
                        "id": "finding-cache-stale",
                        "severity": "warning",
                        "confidence": "high",
                        "path": "src/cache.py",
                        "line": 12,
                        "title": "Cache fallback returns stale value",
                        "rationale": "The fallback now returns stale data when the cache misses.",
                        "evidence": "Changed line 12 returns stale_value.",
                        "suggested_fix": "Fetch a fresh value before returning.",
                    },
                    {
                        "type": "local_note",
                        "id": "note-context",
                        "title": "Context note",
                        "body": "Keep this local.",
                        "evidence": "Fixture metadata.",
                    },
                    {
                        "type": "clarification_request",
                        "id": "clarify-cache",
                        "reviewer": "spoofed-reviewer",
                        "question": "Should stale cache values be allowed?",
                        "why_it_matters": "The verdict depends on intended fallback behavior.",
                    },
                    {
                        "type": "suggested_reply",
                        "id": "reply-cache",
                        "source_comment_id": "comment-cache-intent",
                        "proposed_body": "I checked the cache fallback path.",
                    },
                    {
                        "type": "non_finding",
                        "id": "nonfinding-style",
                        "reason": "Style-only observation.",
                    },
                ],
            }
        ]
    )

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.run_key == run_key
    assert result.status == ReviewerRunStatusValue.COMPLETED
    assert result.raw_output is not None
    assert result.errors == ()
    assert result.findings[0].id == "finding-cache-stale"
    assert result.local_notes[0].id == "note-context"
    assert result.clarification_requests[0].id == "clarify-cache"
    assert result.clarification_requests[0].reviewer == "quality"
    assert result.suggested_replies[0].id == "reply-cache"
    assert result.suppressed_outputs[0].id == "nonfinding-style"


def test_fake_outputs_are_keyed_by_fixture_reviewer_and_stage() -> None:
    package, run_key = _package_and_key(reviewer_name="security")
    registry = fake_registry_from_fixture_outputs(
        fixture_id="other-fixture",
        outputs=[
            {
                "reviewer": "security",
                "stage": "initial_triage",
                "items": [],
            }
        ]
    )

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.FAILED
    assert result.errors == ("missing raw reviewer output for selected reviewer: security/initial_triage",)


def test_fake_reviewer_receives_scoped_context_package_and_required_metadata() -> None:
    package, run_key = _package_and_key(reviewer_name="required-check", required=True)
    registry = fake_registry_from_fixture_outputs(
        fixture_id="basic-pr",
        outputs=[
            {
                "reviewer": "required-check",
                "stage": "initial_triage",
                "items": [],
            }
        ]
    )

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.COMPLETED
    assert package.reviewer_config.required is True
    assert package.capability_policy.github_writes_available is False
    assert package.capability_policy.repository_access_available is False
    assert package.capability_policy.live_provider_calls_available is False
    assert [changed_file.path for changed_file in package.changed_files] == ["src/cache.py"]


def test_fake_reviewer_optional_failure_is_result_error_without_live_call() -> None:
    package, run_key = _package_and_key(reviewer_name="optional-check", required=False)
    registry = fake_registry_from_fixture_outputs(
        fixture_id="basic-pr",
        outputs=[
            {
                "reviewer": "optional-check",
                "stage": "initial_triage",
                "failure": True,
                "error": "optional reviewer failed deterministically",
            }
        ]
    )

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.FAILED
    assert result.errors == ("optional reviewer failed deterministically",)
    assert package.reviewer_config.required is False


def test_fake_reviewer_required_failure_is_result_error_without_posting_policy() -> None:
    package, run_key = _package_and_key(reviewer_name="required-check", required=True)
    registry = fake_registry_from_fixture_outputs(
        fixture_id="basic-pr",
        outputs=[
            {
                "reviewer": "required-check",
                "stage": "initial_triage",
                "failure": True,
                "error": "required reviewer failed deterministically",
            }
        ]
    )

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.FAILED
    assert result.errors == ("required reviewer failed deterministically",)
    assert package.reviewer_config.required is True


def test_dry_run_honors_failed_fake_reviewer_result_before_classification(tmp_path) -> None:
    data = json.loads(resources.files("reviewgraph").joinpath("fixtures_data/prs/basic-pr.json").read_text())
    data["raw_reviewer_outputs"][0] = {
        "reviewer": "correctness",
        "stage": "initial_triage",
        "failure": True,
        "error": "required reviewer failed before classification",
        "items": [],
    }
    fixture_path = tmp_path / "failed-reviewer.json"
    fixture_path.write_text(json.dumps(data))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))

    assert result.json_data["post_enabled"] is False
    assert result.json_data["errors"][0]["code"] == "required_reviewer_failed"
    assert "required reviewer failed before classification" in result.json_data["errors"][0]["message"]
    assert result.json_data["reviewer_results"][0]["status"] == "failed"


def test_dry_run_lets_legacy_classifier_handle_graph_owned_raw_fields(tmp_path) -> None:
    data = json.loads(resources.files("reviewgraph").joinpath("fixtures_data/prs/basic-pr.json").read_text())
    data["raw_reviewer_outputs"][0]["items"][0]["fingerprint"] = "reviewer-owned"
    fixture_path = tmp_path / "graph-owned-field.json"
    fixture_path.write_text(json.dumps(data))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))

    assert result.json_data["reviewer_results"][0]["status"] == "completed"
    assert result.json_data["reviewer_run_status"][0]["status"] == "completed"
    suppressed = result.json_data["review"]["classified_output"]["suppressed"]
    assert suppressed[0]["reason"] == "Raw reviewer finding attempted to set graph-owned fields and was suppressed."


def test_fake_reviewer_malformed_json_shape_returns_failed_result_with_raw_output() -> None:
    package, run_key = _package_and_key(reviewer_name="quality")
    registry = fake_registry_from_fixture_outputs(
        fixture_id="basic-pr",
        outputs=[
            {
                "reviewer": "quality",
                "stage": "initial_triage",
                "items": "not-a-list",
            }
        ]
    )

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.FAILED
    assert result.raw_output == {
        "reviewer": "quality",
        "stage": "initial_triage",
        "items": "not-a-list",
    }
    assert result.errors == ("fake reviewer output requires an items list",)


def test_fake_reviewer_has_no_live_llm_or_provider_behavior() -> None:
    package, run_key = _package_and_key(reviewer_name="quality")
    registry = fake_registry_from_fixture_outputs(
        fixture_id="basic-pr",
        outputs=[
            {
                "reviewer": "quality",
                "stage": "initial_triage",
                "items": [],
            }
        ]
    )

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.COMPLETED
    assert "provider" not in json.dumps(result.raw_output, sort_keys=True)
    assert package.capability_policy.live_provider_calls_available is False


def test_dry_run_records_fake_reviewer_result_from_runner_execution_path() -> None:
    result = run_fixture_dry_run(fixture_ref="basic-pr")

    reviewer_results = result.json_data["reviewer_results"]
    assert len(reviewer_results) == 1
    assert reviewer_results[0]["reviewer"] == "correctness"
    assert reviewer_results[0]["stage"] == "initial_triage"
    assert reviewer_results[0]["status"] == "completed"
    assert reviewer_results[0]["errors"] == []
    assert reviewer_results[0]["raw_output"]["reviewer"] == "correctness"


def test_fake_reviewer_call_signature_accepts_only_context_package() -> None:
    assert tuple(inspect.signature(FakeReviewerAdapter.run).parameters) == ("self", "package")


def test_fake_reviewer_preserves_malformed_raw_json_string() -> None:
    package, run_key = _package_and_key(reviewer_name="quality")
    registry = {("basic-pr", "quality", "initial_triage"): '{"items": ['}

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=registry),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.FAILED
    assert result.raw_output == '{"items": ['
    assert result.errors == ("fake reviewer output is not valid JSON",)


def _package_and_key(*, reviewer_name: str, required: bool = False):
    fixture = load_fixture_pr("basic-pr")
    memory = build_conversation_memory(fixture.pr)
    budgeted_context = apply_input_context_budget(
        pr=fixture.pr,
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
            "review_target": fixture.review_target,
            "config_hash": canonical_json_hash({"agents": [reviewer_name]}),
        },
    )()
    run_key = make_reviewer_run_key(state, reviewer)
    assert run_key.stage == ReviewStage.INITIAL_TRIAGE
    return package, run_key
