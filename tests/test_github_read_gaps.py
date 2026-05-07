import json

import pytest

from reviewgraph.github import GitHubPRRef
from reviewgraph.models import (
    ClassifiedFinding,
    Confidence,
    GraphError,
    ReadGap,
    ReviewTarget,
    SelectedReviewer,
    Severity,
    TruncationNotice,
)
from reviewgraph.posting import build_candidate_issue_comment_payload, build_posting_plan
from reviewgraph.read_gaps import (
    GITHUB_READ_GAP_TRACE,
    GitHubPageGapDescriptor,
    build_fail_closed_read_outcome,
    classify_github_read_gap,
    graph_errors_from_read_gaps,
    read_gap_json,
    render_targetless_read_failure,
)
from reviewgraph.render import RenderError, render_review


def test_required_github_read_gaps_fail_closed_without_review_or_candidate_payload() -> None:
    outcome = build_fail_closed_read_outcome(
        pr_ref=GitHubPRRef("acme", "widgets", 42),
        read_gaps=(
            ReadGap(resource="comments", required=True, reason="not_fetched_in_scope", retryable=True),
        ),
    )

    assert outcome.post_enabled is False
    assert outcome.selected_reviewers == ()
    assert outcome.findings == ()
    assert outcome.posting_plan is None
    assert outcome.candidate_payload is None
    assert outcome.graph_trace == (GITHUB_READ_GAP_TRACE,)
    assert outcome.errors == (
        GraphError(
            code="github_read_gap",
            message="Required GitHub read gap for comments: not_fetched_in_scope",
            retryable=True,
        ),
    )


def test_required_github_read_gap_errors_cannot_be_overridden() -> None:
    outcome = build_fail_closed_read_outcome(
        pr_ref=GitHubPRRef("acme", "widgets", 42),
        read_gaps=(
            ReadGap(resource="comments", required=True, reason="timeout", retryable=True),
        ),
        errors=(),
    )

    assert outcome.errors == (
        GraphError(
            code="github_read_gap",
            message="Required GitHub read gap for comments: timeout",
            retryable=True,
        ),
    )


def test_optional_github_read_gaps_render_without_graph_errors() -> None:
    optional = ReadGap(resource="checks", required=False, reason="unavailable", retryable=False)

    assert graph_errors_from_read_gaps((optional,)) == ()
    assert read_gap_json(optional)["usage"] == "visible_only_not_routing_evidence_or_public_payload"
    with pytest.raises(ValueError, match="required GitHub read gap"):
        build_fail_closed_read_outcome(
            pr_ref=GitHubPRRef("acme", "widgets", 42),
            read_gaps=(optional,),
        )


def test_targeted_dry_run_render_includes_read_gaps_and_graph_errors_separate_from_truncation() -> None:
    read_gap = ReadGap(resource="review_comments", required=True, reason="timeout", retryable=True)
    error = graph_errors_from_read_gaps((read_gap,))[0]
    rendered = render_review(
        review_target=_target(),
        selected_reviewers=[],
        findings=[],
        read_gaps=(read_gap,),
        errors=(error,),
        truncation_notices=(),
    )

    assert rendered.json_data["read_gaps"] == [
        {
            "resource": "review_comments",
            "required": True,
            "reason": "timeout",
            "retryable": True,
            "usage": "required_fail_closed",
        }
    ]
    assert rendered.json_data["errors"] == [
        {
            "code": "github_read_gap",
            "message": "Required GitHub read gap for review_comments: timeout",
            "retryable": True,
        }
    ]
    assert rendered.json_data["truncation"] == []
    assert "## Read Gaps" in rendered.markdown
    assert "review_comments: required=true, retryable=true - timeout" in rendered.markdown
    assert "## Graph Errors" in rendered.markdown
    assert "github_read_gap: Required GitHub read gap for review_comments: timeout" in rendered.markdown
    assert "## Truncation\n- None" in rendered.markdown


def test_required_read_gap_rejects_candidate_payload_preview() -> None:
    gap = ReadGap(resource="comments", required=True, reason="timeout", retryable=True)
    plan = build_posting_plan(findings=[finding()], include_summary=True)
    payload = build_candidate_issue_comment_payload(
        review_target=_target(),
        posting_plan=plan,
        findings=[finding()],
    )

    with pytest.raises(RenderError, match="required read gaps suppress candidate payload"):
        render_review(
            review_target=_target(),
            selected_reviewers=[],
            findings=[],
            read_gaps=(gap,),
            errors=graph_errors_from_read_gaps((gap,)),
            candidate_payload=payload,
        )


@pytest.mark.parametrize(
    ("case", "message"),
    [
        (
            "selected_reviewers",
            "required read gaps suppress reviewer execution",
        ),
        ("findings", "required read gaps suppress findings"),
        (
            "posting_plan",
            "required read gaps suppress posting plan",
        ),
        ("errors", "required read gaps require github_read_gap errors"),
    ],
)
def test_required_read_gap_rejects_contradictory_render_state(
    case: str,
    message: str,
) -> None:
    gap = ReadGap(resource="comments", required=True, reason="timeout", retryable=True)
    errors = graph_errors_from_read_gaps((gap,))
    base_kwargs: dict[str, object] = {
        "review_target": _target(),
        "selected_reviewers": [],
        "findings": [],
        "read_gaps": (gap,),
        "errors": errors,
    }
    if case == "selected_reviewers":
        base_kwargs["selected_reviewers"] = [SelectedReviewer("correctness", "initial_triage", ("always-on",))]
    elif case == "findings":
        base_kwargs["findings"] = [finding()]
    elif case == "posting_plan":
        base_kwargs["posting_plan"] = build_posting_plan(findings=[finding()], include_summary=True)
    elif case == "errors":
        base_kwargs["errors"] = ()

    with pytest.raises(RenderError, match=message):
        render_review(**base_kwargs)


def test_targetless_fetch_failure_renders_redacted_fail_closed_envelope() -> None:
    read_gap = classify_github_read_gap(
        resource="metadata",
        status=403,
        required=True,
        message="token=sk_live_1234567890abcdef",
    )
    rendered = render_targetless_read_failure(
        pr_ref=GitHubPRRef("acme", "widgets", 42),
        read_gaps=(read_gap,),
        error_message="metadata fetch failed for token=sk_live_1234567890abcdef",
    )
    serialized = json.dumps(rendered.json_data, sort_keys=True)

    assert rendered.json_data["post_enabled"] is False
    assert rendered.json_data["review_target"] is None
    assert rendered.json_data["pr_ref"] == {"owner_repo": "acme/widgets", "pr_number": 42}
    assert rendered.json_data["graph_trace"] == [GITHUB_READ_GAP_TRACE]
    assert rendered.json_data["selected_reviewers"] == []
    assert rendered.json_data["review"]["candidate_payload_preview"] is None
    assert rendered.json_data["redaction_status"]["redacted"] is True
    assert rendered.redaction_status.redacted is True
    assert rendered.redaction_status.replacement_count > 0
    assert "sk_live" not in serialized
    assert "[REDACTED]" in serialized
    assert "sk_live" not in rendered.markdown
    assert "## Read Failure" in rendered.markdown


def test_targetless_read_gap_fields_contribute_to_redaction_status() -> None:
    rendered = render_targetless_read_failure(
        pr_ref=GitHubPRRef("acme", "widgets", 42),
        read_gaps=(
            ReadGap(
                resource="comments ghp_abcdefghijklmnopqrstuvwxyz123456",
                required=True,
                reason="timeout",
                retryable=True,
            ),
        ),
        error_message="metadata fetch failed",
    )

    assert rendered.redaction_status.redacted is True
    assert rendered.json_data["redaction_status"]["redacted"] is True
    assert rendered.json_data["read_gaps"][0]["resource"] == "comments [REDACTED]"


def test_classifies_required_github_read_gap_failure_reasons() -> None:
    cases = [
        (403, None, "forbidden", False),
        (403, "rate_limited", "rate_limited", True),
        (404, None, "not_found", False),
        (429, None, "rate_limited", True),
        (None, "timeout", "timeout", True),
        (None, "unavailable", "unavailable", False),
        (None, "thread_state_unknown", "thread_state_unknown", False),
    ]

    for status, reason, expected_reason, expected_retryable in cases:
        gap = classify_github_read_gap(
            resource="comments",
            status=status,
            reason=reason,
            required=True,
        )
        assert gap == ReadGap(
            resource="comments",
            required=True,
            reason=expected_reason,
            retryable=expected_retryable,
        )


def test_page_gap_descriptors_preserve_underlying_failure_and_later_page_risk() -> None:
    gap = classify_github_read_gap(
        resource="comments",
        reason="timeout",
        required=True,
        page=2,
    )
    descriptor = GitHubPageGapDescriptor(
        resource="comments",
        missing_page=2,
        underlying_reason=gap.reason,
        would_affect=("routing", "trust", "redaction"),
        examples=("comment mentions sk_live_1234567890abcdef and requests logic review",),
    )
    file_descriptor = GitHubPageGapDescriptor(
        resource="files",
        missing_page=2,
        underlying_reason="rate_limited",
        would_affect=("routing",),
        examples=("src/security.py would trigger security reviewer",),
    )

    assert gap.reason == "timeout"
    assert read_gap_json(gap, page_gap=descriptor) == {
        "resource": "comments",
        "required": True,
        "reason": "timeout",
        "retryable": True,
        "usage": "required_fail_closed",
        "page_gap": {
            "resource": "comments",
            "missing_page": 2,
            "underlying_reason": "timeout",
            "would_affect": ["routing", "trust", "redaction"],
            "examples": ["comment mentions [REDACTED] and requests logic review"],
        },
    }
    assert read_gap_json(
        ReadGap(resource="files", required=True, reason="rate_limited", retryable=True),
        page_gap=file_descriptor,
    )["page_gap"] == {
        "resource": "files",
        "missing_page": 2,
        "underlying_reason": "rate_limited",
        "would_affect": ["routing"],
        "examples": ["src/security.py would trigger security reviewer"],
    }


def test_configured_truncation_is_distinct_from_read_gap_failure() -> None:
    read_gap = ReadGap(resource="files", required=True, reason="timeout", retryable=True)
    rendered = render_review(
        review_target=_target(),
        selected_reviewers=[],
        findings=[],
        read_gaps=(read_gap,),
        errors=graph_errors_from_read_gaps((read_gap,)),
        truncation_notices=(
            TruncationNotice(resource="patch", truncated=True, note="Patch budget applied."),
        ),
    )

    assert rendered.json_data["read_gaps"][0]["reason"] == "timeout"
    assert rendered.json_data["truncation"][0]["resource"] == "patch"
    assert rendered.json_data["truncation"][0]["note"] == "Patch budget applied."


def _target() -> ReviewTarget:
    return ReviewTarget(
        owner_repo="acme/widgets",
        pr_number=42,
        base_sha="base123",
        head_sha="head456",
        merge_base_sha="merge789",
        diff_basis="merge_base",
    )


def finding() -> ClassifiedFinding:
    return ClassifiedFinding(
        id="finding-1",
        source_reviewer="correctness",
        source_stage="initial_triage",
        title="Cache miss returns stale data",
        body="Cache miss returns stale data.",
        evidence="changed line 12",
        path="src/cache.py",
        line=12,
        priority=1,
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        fingerprint="fp-1",
    )
