import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from reviewgraph.fixtures import resolve_fixture_ref
from reviewgraph.models import (
    ArtifactKind,
    ClassifiedFinding,
    Confidence,
    GateStatus,
    GitHubReviewPayload,
    RedactionStatus,
    ReviewTarget,
    SelectedReviewer,
    Severity,
)
from reviewgraph.posting import build_candidate_issue_comment_payload, build_posting_plan, full_body_hash, visible_body_hash
from reviewgraph.redaction import (
    REDACTION_TOKEN,
    RedactionPolicyError,
    redact_data,
    redact_provider_bound_text,
    redact_text,
    redact_trace_data,
    require_passing_redaction_status,
    require_state_redaction_before_payload_validation,
)
from reviewgraph.render import render_review
from reviewgraph.runner import run_fixture_dry_run


def target() -> ReviewTarget:
    return ReviewTarget(
        owner_repo="acme/widgets",
        pr_number=42,
        base_sha="base123",
        head_sha="head456",
        merge_base_sha="merge789",
        diff_basis="merge_base",
    )


def finding(body: str) -> ClassifiedFinding:
    return ClassifiedFinding(
        id="finding-1",
        source_reviewer="correctness",
        source_stage="initial_triage",
        title="Secret handling regression",
        body=body,
        evidence="changed line 12",
        path="src/cache.py",
        line=12,
        priority=1,
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        fingerprint="fp-1",
    )


def selected_reviewers() -> list[SelectedReviewer]:
    return [SelectedReviewer("correctness", "initial_triage", ("always-on reviewer",))]


SECRET_TEXT = """
api_key = sk_live_1234567890abcdef
{"api_key": "sk-proj-1234567890abcdef"}
Authorization: Bearer abcdefghijklmnopqrstuvwxyz
Use Bearer zyxwvutsrqponmlkjihgfedcba here
token=ghp_abcdefghijklmnopqrstuvwxyz123456
fine_grained=github_pat_abcdefghijklmnopqrstuvwxyz123456
standalone sk-proj-zyxwvutsrqponmlkjihgfedcba
GITHUB_TOKEN=ghs_abcdefghijklmnopqrstuvwxyz123456
-----BEGIN PRIVATE KEY-----
private-material
-----END PRIVATE KEY-----
"""


SECRET_FRAGMENTS = (
    "sk_live",
    "sk-proj",
    "ghp_",
    "github_pat_",
    "ghs_",
    "abcdefghijklmnopqrstuvwxyz",
    "PRIVATE KEY",
)


def test_redacts_required_secret_classes_deterministically() -> None:
    first = redact_text(SECRET_TEXT)
    second = redact_text(SECRET_TEXT)

    assert first == second
    assert first.redacted is True
    for fragment in SECRET_FRAGMENTS:
        assert fragment not in first.text
    assert set(first.categories) >= {
        "private_key",
        "authorization_header",
        "bearer_token",
        "github_token",
        "standalone_api_key",
        "api_key",
        "env_assignment",
    }


def test_redacts_nested_json_like_trace_and_error_data() -> None:
    payload = {
        "error": "failed for Bearer abcdefghijklmnopqrstuvwxyz",
        "headers": {"Authorization": "Bearer zyxwvutsrqponmlkjihgfedcba"},
        "items": ["token=ghp_abcdefghijklmnopqrstuvwxyz123456"],
        "ghp_abcdefghijklmnopqrstuvwxyz123456": "secret key should redact object keys too",
        "ghs_abcdefghijklmnopqrstuvwxyz123456": "second secret key should not overwrite the first",
    }

    result = redact_data(payload)

    serialized = json.dumps(result.data, sort_keys=True)
    for fragment in ("Bearer abc", "Bearer zyx", "ghp_", "abcdefghijklmnopqrstuvwxyz"):
        assert fragment not in serialized
    assert REDACTION_TOKEN in serialized
    assert result.redaction_status.redacted is True
    assert len(result.data) == len(payload)


def test_redacts_fixture_external_pr_text_fields() -> None:
    fixture = json.loads(resolve_fixture_ref("basic-pr").read_text())

    result = redact_data(fixture)

    serialized = json.dumps(result.data, sort_keys=True)
    assert "ghp_" not in serialized
    assert "sk_live" not in serialized
    assert REDACTION_TOKEN in serialized


def test_rendered_markdown_json_and_candidate_payload_are_redacted() -> None:
    secret_finding = finding(body=SECRET_TEXT)
    plan = build_posting_plan(findings=[secret_finding])
    candidate = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=[secret_finding],
    )

    rendered = render_review(
        review_target=target(),
        selected_reviewers=selected_reviewers(),
        findings=[secret_finding],
        posting_plan=plan,
        candidate_payload=candidate,
    )

    serialized = rendered.markdown + json.dumps(rendered.json_data, sort_keys=True) + candidate.body
    for fragment in SECRET_FRAGMENTS:
        assert fragment not in serialized
    assert rendered.redaction_status.redacted is True
    assert candidate.redaction_status.redacted is True


def test_final_payload_shaped_contract_carries_redacted_body_and_status() -> None:
    raw_final_body = f"Final ReviewGraph payload\n{SECRET_TEXT}\n<!-- marker -->"
    redaction = redact_text(raw_final_body)
    payload = GitHubReviewPayload(
        artifact_kind=ArtifactKind.ISSUE_COMMENT,
        review_target=ReviewTarget("acme/widgets", 42, "base123", "head456", "merge789", "merge_base"),
        body=redaction.text,
        visible_body_hash=visible_body_hash(redaction.text),
        full_body_hash=full_body_hash(redaction.text),
        findings_hash="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        item_fingerprints=(),
        redaction_status=RedactionStatus(
            redacted=redaction.redacted,
            replacement_count=redaction.replacement_count,
            categories=redaction.categories,
        ),
    )

    for fragment in SECRET_FRAGMENTS:
        assert fragment not in payload.body
    assert payload.redaction_status.redacted is True


def test_default_dry_run_json_errors_and_envelope_are_redacted(tmp_path) -> None:
    fixture_path = tmp_path / "secret-ref.json"
    fixture = json.loads(resolve_fixture_ref("basic-pr").read_text())
    fixture["id"] = "ghp_abcdefghijklmnopqrstuvwxyz123456"
    fixture["pr_ref"] = "fixture:ghp_abcdefghijklmnopqrstuvwxyz123456"
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))
    error_result = redact_data({"error": "bad token ghp_abcdefghijklmnopqrstuvwxyz123456"})

    serialized = json.dumps(result.json_data, sort_keys=True) + json.dumps(error_result.data, sort_keys=True)
    assert "ghp_" not in serialized
    assert "abcdefghijklmnopqrstuvwxyz" not in serialized
    assert REDACTION_TOKEN in serialized


def test_provider_bound_text_is_redacted_by_default_and_raw_provider_opt_in_is_separate() -> None:
    default = redact_provider_bound_text(SECRET_TEXT)
    raw_provider = redact_provider_bound_text(SECRET_TEXT, raw_provider_submission_enabled=True)
    raw_trace_only = redact_provider_bound_text(SECRET_TEXT, raw_trace_persistence_enabled=True)

    assert "sk_live" not in default.text
    assert default.raw_provider_submission_enabled is False
    assert default.raw_trace_persistence_enabled is False
    assert "sk_live" in raw_provider.text
    assert raw_provider.raw_provider_submission_enabled is True
    assert raw_provider.raw_trace_persistence_enabled is False
    assert raw_provider.redaction_status.redacted is True
    assert "api_key" in raw_provider.redaction_status.categories
    assert "sk_live" not in raw_trace_only.text
    assert raw_trace_only.raw_provider_submission_enabled is False
    assert raw_trace_only.raw_trace_persistence_enabled is True


def test_trace_data_is_redacted_by_default_and_raw_trace_opt_in_is_separate() -> None:
    data = {"trace": SECRET_TEXT}

    default = redact_trace_data(data)
    raw_trace = redact_trace_data(data, raw_trace_persistence_enabled=True)
    raw_provider_only = redact_trace_data(data, raw_provider_submission_enabled=True)

    assert "sk_live" not in json.dumps(default.data)
    assert default.raw_trace_persistence_enabled is False
    assert default.raw_provider_submission_enabled is False
    assert "sk_live" in json.dumps(raw_trace.data)
    assert raw_trace.raw_trace_persistence_enabled is True
    assert raw_trace.raw_provider_submission_enabled is False
    assert raw_trace.redaction_status.redacted is True
    assert "api_key" in raw_trace.redaction_status.categories
    assert "sk_live" not in json.dumps(raw_provider_only.data)
    assert raw_provider_only.raw_provider_submission_enabled is True
    assert raw_provider_only.raw_trace_persistence_enabled is False


def test_redaction_status_is_required_before_payload_validation() -> None:
    passing = RedactionStatus(redacted=False, replacement_count=0)

    require_passing_redaction_status(passing, surface="candidate_payload")
    require_state_redaction_before_payload_validation(SimpleNamespace(redaction_status=passing))

    with pytest.raises(RedactionPolicyError, match="requires redaction status"):
        require_passing_redaction_status(None, surface="candidate_payload")
    with pytest.raises(RedactionPolicyError, match="requires redaction status"):
        require_state_redaction_before_payload_validation(SimpleNamespace(redaction_status=None))
    with pytest.raises(RedactionPolicyError, match="must pass"):
        require_passing_redaction_status(
            RedactionStatus(redacted=False, replacement_count=0, status=GateStatus.FAIL),
            surface="candidate_payload",
        )


def test_render_checks_candidate_payload_redaction_status_before_binding() -> None:
    secret_finding = finding(body=SECRET_TEXT)
    plan = build_posting_plan(findings=[secret_finding])
    candidate = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=[secret_finding],
    )
    invalid_target_candidate = replace(
        candidate,
        review_target=ReviewTarget("acme/other", 42, "base123", "head456", "merge789", "merge_base"),
        redaction_status=RedactionStatus(redacted=False, replacement_count=0, status=GateStatus.FAIL),
    )

    with pytest.raises(RedactionPolicyError, match="must pass"):
        render_review(
            review_target=target(),
            selected_reviewers=selected_reviewers(),
            findings=[secret_finding],
            posting_plan=plan,
            candidate_payload=invalid_target_candidate,
        )
