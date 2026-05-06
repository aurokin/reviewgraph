import json
from importlib import resources
from pathlib import Path

from reviewgraph.fixtures import load_fixture_pr
from reviewgraph.models import (
    Confidence,
    LocalNote,
    RawReviewerFinding,
    ReviewStage,
    ReviewerResult,
    ReviewerRunKey,
    Severity,
)
from reviewgraph.quality import classify_review_quality
from reviewgraph.runner import run_fixture_dry_run


def test_testing_finding_is_postable_with_changed_behavior_scenario_and_missing_coverage() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(
            findings=(
                _finding(
                    id="finding-cache-miss-coverage",
                    title="Missing cache miss regression coverage",
                    rationale=(
                        "The new branch returns stale data when the cache misses, "
                        "but there is no regression test covering cache invalidation misses."
                    ),
                    evidence="Changed line 12 returns stale value when the cache misses.",
                ),
            )
        ),
        memory_references=(),
    )

    assert [finding.id for finding in result.findings] == ["finding-cache-miss-coverage"]
    assert result.findings[0].source_reviewer == "testing"
    assert result.suppressed_outputs == ()


def test_testing_finding_accepts_common_concrete_missing_coverage_phrasings() -> None:
    cases = (
        (
            "finding-missing-tests",
            "Missing cache miss tests",
            (
                "The new branch returns stale data when the cache misses, "
                "but there are no tests for cache misses."
            ),
        ),
        (
            "finding-no-tests-cover",
            "Missing cache miss tests",
            (
                "The new branch returns stale data when the cache misses, "
                "but no tests cover cache misses."
            ),
        ),
        (
            "finding-no-coverage",
            "Missing cache coverage",
            (
                "The new branch returns stale data when the cache misses, "
                "but there is no coverage for cache misses."
            ),
        ),
        (
            "finding-lacks-coverage",
            "Cache miss path lacks coverage",
            (
                "The new branch returns stale data when the cache misses, "
                "but the cache miss path lacks coverage for invalidation."
            ),
        ),
        (
            "finding-lacks-tests",
            "Cache miss path lacks tests",
            (
                "The new branch returns stale data when the cache misses, "
                "but it lacks tests for cache misses."
            ),
        ),
        (
            "finding-without-coverage",
            "Missing cache coverage",
            (
                "The new branch returns stale data when the cache misses "
                "without coverage for cache invalidation."
            ),
        ),
    )

    for finding_id, title, rationale in cases:
        result = classify_review_quality(
            changed_files=_changed_files(),
            reviewer_result=_result(
                findings=(
                    _finding(
                        id=finding_id,
                        title=title,
                        rationale=rationale,
                        evidence="Changed line 12 returns stale value when the cache misses.",
                    ),
                )
            ),
            memory_references=(),
        )

        assert [finding.id for finding in result.findings] == [finding_id]
        assert result.suppressed_outputs == ()


def test_testing_finding_suppresses_generic_add_tests_output() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(
            findings=(
                _finding(
                    id="finding-generic-tests",
                    title="Add tests",
                    rationale="This change should improve coverage.",
                    evidence="Changed line 12 returns a value.",
                ),
            )
        ),
        memory_references=(),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].id == "finding-generic-tests"
    assert result.suppressed_outputs[0].reason == "Finding candidate did not meet postable quality policy."


def test_testing_finding_suppresses_changed_behavior_without_missing_coverage_target() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(
            findings=(
                _finding(
                    id="finding-behavior-only",
                    title="Cache miss behavior changed",
                    rationale="The new branch returns stale data when the cache misses.",
                    evidence="Changed line 12 returns stale value when the cache misses.",
                ),
            )
        ),
        memory_references=(),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].id == "finding-behavior-only"


def test_testing_finding_suppresses_missing_coverage_with_vague_scenario() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(
            findings=(
                _finding(
                    id="finding-vague-coverage",
                    title="Missing tests",
                    rationale="No tests cover this changed behavior.",
                    evidence="Changed line 12 returns stale value.",
                ),
            )
        ),
        memory_references=(),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].id == "finding-vague-coverage"


def test_testing_finding_suppresses_generic_public_coverage_even_with_concrete_evidence() -> None:
    cases = (
        (
            "finding-generic-public-coverage",
            "Missing coverage",
            "No coverage for this change.",
        ),
        (
            "finding-generic-regression-coverage",
            "Missing regression coverage",
            "The new branch returns stale data when the cache misses without regression coverage.",
        ),
    )

    for finding_id, title, rationale in cases:
        result = classify_review_quality(
            changed_files=_changed_files(),
            reviewer_result=_result(
                findings=(
                    _finding(
                        id=finding_id,
                        title=title,
                        rationale=rationale,
                        evidence="Changed line 12 returns stale value when the cache misses.",
                    ),
                )
            ),
            memory_references=(),
        )

        assert result.findings == ()
        assert result.suppressed_outputs[0].id == finding_id


def test_testing_finding_suppresses_test_output_mentions_that_are_not_missing_coverage() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(
            findings=(
                _finding(
                    id="finding-test-output",
                    title="Cache miss behavior appears in test output",
                    rationale=(
                        "The new branch returns stale data when the cache misses because no retry runs "
                        "after invalidation, and this appears in the test output."
                    ),
                    evidence="Changed line 12 returns stale value when the cache misses.",
                ),
            )
        ),
        memory_references=(),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].id == "finding-test-output"


def test_testing_local_note_stays_local_only() -> None:
    note = LocalNote(
        id="note-testing-gap",
        title="Testing follow-up",
        body="Consider a broader fixture later.",
        evidence="Testing reviewer emitted this as a local note.",
    )

    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=ReviewerResult(run_key=_run_key(), local_notes=(note,)),
        memory_references=(),
    )

    assert result.findings == ()
    assert result.local_notes == (note,)
    assert result.suppressed_outputs == ()


def test_suppressed_testing_finding_stays_out_of_candidate_payload(tmp_path: Path) -> None:
    fixture_path = tmp_path / "generic-testing-finding.json"
    config_path = tmp_path / "testing-reviewers.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["reviewer"] = "testing"
    fixture["raw_reviewer_outputs"][0]["items"] = [
        {
            "type": "finding",
            "id": "finding-generic-tests",
            "title": "Add tests",
            "body": "This change should improve coverage.",
            "evidence": "Changed line 12 returns stale data.",
            "path": "src/cache.py",
            "line": 12,
            "severity": "suggestion",
            "confidence": "high",
        }
    ]
    fixture_path.write_text(json.dumps(fixture))
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "testing": {
                        "description": "Checks missing regression coverage.",
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                        "required": True,
                        "verdict_power": "comment",
                        "capabilities": ["diff_context"],
                    }
                }
            }
        )
    )

    result = run_fixture_dry_run(fixture_ref=str(fixture_path), reviewer_config_path=str(config_path))
    review = result.json_data["review"]

    assert result.json_data["post_enabled"] is False
    assert result.json_data["local_verdict"] == "no_findings"
    assert review["candidate_payload_preview"] is None
    assert review["classified_output"]["postable_findings"] == []
    assert review["posting_plan"]["items"] == [
        {
            "id": "finding-generic-tests",
            "source_classification": "non_finding",
            "destination": "local_only",
            "public_payload_eligible": False,
            "fingerprint": None,
            "body": "Finding candidate did not meet postable quality policy.",
        }
    ]


def _changed_files():
    return load_fixture_pr("basic-pr").changed_files


def _run_key() -> ReviewerRunKey:
    return ReviewerRunKey(
        target_hash="sha256:target",
        config_hash="sha256:config",
        stage=ReviewStage.INITIAL_TRIAGE,
        reviewer="testing",
    )


def _result(*, findings: tuple[RawReviewerFinding, ...] = ()) -> ReviewerResult:
    return ReviewerResult(run_key=_run_key(), findings=findings)


def _finding(
    *,
    id: str,
    title: str,
    rationale: str,
    evidence: str,
) -> RawReviewerFinding:
    return RawReviewerFinding(
        id=id,
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        path="src/cache.py",
        line=12,
        title=title,
        rationale=rationale,
        evidence=evidence,
        evidence_sources=("diff",),
    )


def _basic_fixture() -> dict[str, object]:
    fixture_text = resources.files("reviewgraph").joinpath("fixtures_data/prs/basic-pr.json").read_text()
    return json.loads(fixture_text)
