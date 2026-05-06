import json
from importlib import resources

import pytest

from reviewgraph.clarification import evaluate_clarification_gate
from reviewgraph.models import (
    ClarificationRequest,
    ClassifiedFinding,
    Confidence,
    GraphError,
    ReviewVerdict,
    Severity,
)
from reviewgraph.posting import (
    PostingPlanError,
    build_candidate_issue_comment_payload,
    build_posting_plan,
)
from reviewgraph.runner import run_fixture_dry_run
from reviewgraph.verdict import compute_local_verdict, compute_post_enabled


def test_blocking_clarification_computes_needs_clarification_not_request_changes() -> None:
    gate = evaluate_clarification_gate(
        [
            ClarificationRequest(
                id="clarify-intent",
                reviewer="logic",
                question="Is stale fallback intentional?",
                why_it_matters="It affects mergeability.",
            )
        ]
    )

    verdict = compute_local_verdict(findings=(_finding(),), clarification_gate=gate)

    assert verdict == ReviewVerdict.NEEDS_CLARIFICATION
    assert verdict != ReviewVerdict.REQUEST_CHANGES
    assert compute_post_enabled(
        errors=(),
        clarification_gate=gate,
        local_verdict=verdict,
        findings=(_finding(),),
    ) is False


def test_low_confidence_or_no_postable_findings_cannot_request_changes() -> None:
    gate = evaluate_clarification_gate(())
    low_confidence = _finding(confidence=Confidence.LOW, severity=Severity.CRITICAL)

    assert compute_local_verdict(
        findings=(low_confidence,),
        clarification_gate=gate,
        reviewer_verdict_powers={"correctness": "request_changes"},
    ) == ReviewVerdict.COMMENT
    assert compute_local_verdict(findings=(), clarification_gate=gate) == ReviewVerdict.NO_FINDINGS
    assert compute_local_verdict(
        findings=(low_confidence,),
        clarification_gate=gate,
        reviewer_verdict_powers={"correctness": "request_changes"},
    ) != ReviewVerdict.REQUEST_CHANGES
    assert compute_local_verdict(findings=(), clarification_gate=gate) != ReviewVerdict.REQUEST_CHANGES
    assert compute_post_enabled(
        errors=(),
        clarification_gate=gate,
        local_verdict=ReviewVerdict.NO_FINDINGS,
        findings=(),
    ) is False


def test_high_confidence_critical_finding_can_drive_private_request_changes_verdict() -> None:
    gate = evaluate_clarification_gate(())
    finding = _finding(severity=Severity.CRITICAL, confidence=Confidence.HIGH)

    verdict = compute_local_verdict(
        findings=(finding,),
        clarification_gate=gate,
        reviewer_verdict_powers={"correctness": "request_changes"},
    )

    assert verdict == ReviewVerdict.REQUEST_CHANGES
    assert compute_post_enabled(
        errors=(),
        clarification_gate=gate,
        local_verdict=verdict,
        findings=(finding,),
    ) is True


def test_comment_power_reviewer_cannot_drive_request_changes_verdict() -> None:
    gate = evaluate_clarification_gate(())
    finding = _finding(severity=Severity.CRITICAL, confidence=Confidence.HIGH)

    assert compute_local_verdict(
        findings=(finding,),
        clarification_gate=gate,
        reviewer_verdict_powers={"correctness": "comment"},
    ) == ReviewVerdict.COMMENT


def test_graph_errors_disable_posting_even_when_findings_exist() -> None:
    gate = evaluate_clarification_gate(())
    verdict = compute_local_verdict(findings=(_finding(),), clarification_gate=gate)

    assert verdict == ReviewVerdict.COMMENT
    assert compute_post_enabled(
        errors=(GraphError("required_reviewer_failed", "required reviewer failed", retryable=False),),
        clarification_gate=gate,
        local_verdict=verdict,
        findings=(_finding(),),
    ) is False


def test_dry_run_renders_local_verdict_separate_from_issue_comment_artifact() -> None:
    result = run_fixture_dry_run(fixture_ref="basic-pr")

    assert result.json_data["local_verdict"] == "comment"
    assert result.json_data["review"]["local_verdict"] == "comment"
    assert result.json_data["review"]["candidate_payload_preview"]["artifact_kind"] == "issue_comment"
    assert "## Local Verdict" in result.markdown
    assert "GitHub artifact" not in result.markdown


def test_required_failure_blocks_post_eligibility_but_keeps_local_verdict_renderable(tmp_path) -> None:
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

    assert result.json_data["local_verdict"] == "comment"
    assert result.json_data["post_enabled"] is False
    assert result.json_data["review"]["candidate_payload_preview"] is None
    assert result.json_data["errors"][0]["code"] == "required_reviewer_failed"


def test_public_payload_excludes_request_changes_wording_by_default() -> None:
    finding = _finding()
    plan = build_posting_plan(findings=(finding,))
    payload = build_candidate_issue_comment_payload(
        review_target=_target(),
        posting_plan=plan,
        findings=(finding,),
        local_verdict=ReviewVerdict.REQUEST_CHANGES,
    )

    assert "request_changes" not in payload.body
    assert "request changes" not in payload.body.lower()
    assert payload.artifact_kind.value == "issue_comment"

    with pytest.raises(PostingPlanError, match="request_changes"):
        build_candidate_issue_comment_payload(
            review_target=_target(),
            posting_plan=plan,
            findings=(finding,),
            local_verdict=ReviewVerdict.REQUEST_CHANGES,
            include_public_verdict=True,
        )


def _finding(
    *,
    confidence: Confidence = Confidence.HIGH,
    severity: Severity = Severity.WARNING,
) -> ClassifiedFinding:
    return ClassifiedFinding(
        id="finding-cache-stale",
        source_reviewer="correctness",
        source_stage="initial_triage",
        title="Cache miss returns stale data",
        body="The new branch returns stale data when the cache misses.",
        evidence="Changed line 12 returns stale value.",
        path="src/cache.py",
        line=12,
        priority=1,
        severity=severity,
        confidence=confidence,
        fingerprint="fp-cache-stale",
    )


def _target():
    from reviewgraph.models import ReviewTarget

    return ReviewTarget(
        owner_repo="acme/widgets",
        pr_number=42,
        base_sha="base123",
        head_sha="head456",
        merge_base_sha="merge789",
        diff_basis="merge_base",
    )


def _basic_fixture() -> dict[str, object]:
    return json.loads(resources.files("reviewgraph").joinpath("fixtures_data/prs/basic-pr.json").read_text())
