import ast
import json
from pathlib import Path

import pytest

from reviewgraph.models import (
    ClarificationRequest,
    ClassifiedFinding,
    Confidence,
    LocalNote,
    MemoryReference,
    ReviewTarget,
    ReviewVerdict,
    SelectedReviewer,
    Severity,
    SuggestedReply,
    SuppressedOutput,
    TruncationNotice,
)
from reviewgraph.posting import build_candidate_issue_comment_payload, build_posting_plan
from reviewgraph.render import RenderError, render_review


def target() -> ReviewTarget:
    return ReviewTarget(
        owner_repo="acme/widgets",
        pr_number=42,
        base_sha="base123",
        head_sha="head456",
        merge_base_sha="merge789",
        diff_basis="merge_base",
    )


def finding(body: str = "Cache miss returns stale data.") -> ClassifiedFinding:
    return ClassifiedFinding(
        id="finding-1",
        source_reviewer="correctness",
        source_stage="initial_triage",
        title="Cache miss returns stale data",
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
    return [
        SelectedReviewer(
            name="correctness",
            stage="initial_triage",
            reasons=("always-on reviewer",),
        )
    ]


def test_rendered_markdown_and_json_include_required_sections() -> None:
    findings = [finding()]
    local_notes = [LocalNote("note-1", "Review size", "Keep this local.", "file count")]
    clarifications = [ClarificationRequest("clarify-1", "logic", "Is this intentional?", "It matters.")]
    replies = [SuggestedReply("reply-1", "comment-1", "Draft reply only")]
    suppressed = [SuppressedOutput("suppressed-1", "Generic advice")]
    plan = build_posting_plan(
        findings=findings,
        local_notes=local_notes,
        suggested_replies=replies,
        clarification_requests=clarifications,
        suppressed_outputs=suppressed,
        include_summary=True,
    )
    payload = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=findings,
    )
    rendered = render_review(
        review_target=target(),
        selected_reviewers=selected_reviewers(),
        findings=findings,
        local_notes=local_notes,
        clarification_requests=clarifications,
        suggested_replies=replies,
        suppressed_outputs=suppressed,
        local_verdict=ReviewVerdict.REQUEST_CHANGES,
        posting_plan=plan,
        candidate_payload=payload,
        memory_references=[
            MemoryReference("mem-1", "trusted", "resolved", "review_thread", "Trusted note"),
            MemoryReference("mem-2", "untrusted", "unresolved", "issue_comment", "UNTRUSTED_BODY"),
        ],
        truncation_notices=[
            TruncationNotice(
                resource="patch",
                truncated=True,
                original_count=10,
                retained_count=5,
                note="Patch was bounded.",
            )
        ],
    )

    for heading in (
        "## Postable Findings",
        "## Local Notes",
        "## Clarification Requests",
        "## Suggested Replies",
        "## Suppressed Outputs",
        "## Selected Reviewers",
        "## Memory",
        "## Truncation",
        "## Local Verdict",
        "## Posting Plan",
        "## Candidate Payload Preview",
    ):
        assert heading in rendered.markdown
    assert "Count: 1" in rendered.markdown
    assert "private local blocking recommendation" in rendered.markdown
    assert "request_changes" not in rendered.markdown

    data = rendered.json_data
    assert data["review_target"]["owner_repo"] == "acme/widgets"
    assert data["selected_reviewers"][0]["name"] == "correctness"
    assert data["classified_output"]["postable_findings"][0]["id"] == "finding-1"
    assert data["classified_output"]["local_notes"][0]["id"] == "note-1"
    assert data["classified_output"]["clarification_requests"][0]["id"] == "clarify-1"
    assert data["classified_output"]["suggested_replies"][0]["id"] == "reply-1"
    assert data["classified_output"]["suppressed_count"] == 1
    assert data["local_verdict"] == "request_changes"
    assert data["posting_plan"]["items"][0]["destination"] == "top_level_summary_item"
    assert data["memory"][1] == {
        "id": "mem-2",
        "trust_label": "untrusted",
        "resolved_status": "unresolved",
        "source_type": "issue_comment",
        "body": None,
    }
    assert data["truncation"][0]["truncated"] is True


def test_candidate_payload_preview_serializes_supplied_payload_without_recomputing() -> None:
    findings = [finding()]
    plan = build_posting_plan(findings=findings)
    payload = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=findings,
    )
    rendered = render_review(
        review_target=target(),
        selected_reviewers=selected_reviewers(),
        findings=findings,
        posting_plan=plan,
        candidate_payload=payload,
    )

    preview = rendered.json_data["candidate_payload_preview"]
    assert preview["artifact_kind"] == payload.artifact_kind.value
    assert preview["review_target"] == payload.review_target.to_ordered_dict()
    assert preview["body"] == payload.body
    assert preview["visible_body_hash"] == payload.visible_body_hash
    assert preview["full_body_hash"] == payload.full_body_hash
    assert preview["findings_hash"] == payload.findings_hash
    assert preview["item_fingerprints"] == list(payload.item_fingerprints)
    assert preview["redaction_status"] == {
        "redacted": payload.redaction_status.redacted,
        "replacement_count": payload.redaction_status.replacement_count,
        "categories": list(payload.redaction_status.categories),
    }


def test_redacts_supported_secret_classes_from_markdown_and_json() -> None:
    secret_text = """
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
    findings = [finding(body=secret_text)]
    note = LocalNote("note-1", "Secret note", secret_text, secret_text)
    request = ClarificationRequest("clarify-1", "logic", secret_text, secret_text)
    reply = SuggestedReply("reply-1", "comment-1", secret_text)
    suppressed = SuppressedOutput("suppressed-1", secret_text)
    plan = build_posting_plan(
        findings=findings,
        local_notes=[note],
        suggested_replies=[reply],
        clarification_requests=[request],
        suppressed_outputs=[suppressed],
    )
    payload = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=findings,
    )
    rendered = render_review(
        review_target=target(),
        selected_reviewers=[
            SelectedReviewer("correctness", "initial_triage", (secret_text,)),
        ],
        findings=findings,
        local_notes=[note],
        clarification_requests=[request],
        suggested_replies=[reply],
        suppressed_outputs=[suppressed],
        posting_plan=plan,
        candidate_payload=payload,
        memory_references=[MemoryReference("mem-1", "trusted", "resolved", "issue_comment", secret_text)],
        truncation_notices=[TruncationNotice("patch", True, secret_text)],
    )

    serialized = rendered.markdown + json.dumps(rendered.json_data, sort_keys=True)
    for leaked in ("sk_live", "sk-proj", "abcdefghijklmnopqrstuvwxyz", "PRIVATE KEY"):
        assert leaked not in serialized
    assert rendered.redaction_status.redacted is True
    assert rendered.json_data["redaction_status"]["replacement_count"] == rendered.redaction_status.replacement_count
    assert set(rendered.redaction_status.categories) >= {
        "private_key",
        "authorization_header",
        "bearer_token",
        "github_token",
        "standalone_api_key",
        "api_key",
        "env_assignment",
    }


def test_untrusted_memory_body_cannot_enter_candidate_payload_preview() -> None:
    untrusted_body = "UNTRUSTED_UNIQUE_COMMENT_BODY"
    findings = [finding(body=f"Copied: {untrusted_body}")]
    plan = build_posting_plan(findings=findings)
    payload = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=findings,
    )

    with pytest.raises(RenderError, match="untrusted memory"):
        render_review(
            review_target=target(),
            selected_reviewers=selected_reviewers(),
            findings=findings,
            posting_plan=plan,
            candidate_payload=payload,
            memory_references=[
                MemoryReference("mem-untrusted", "untrusted", "unresolved", "issue_comment", untrusted_body)
            ],
        )


def test_render_json_is_deterministic_and_primitive_serializable() -> None:
    findings = [finding()]
    plan = build_posting_plan(findings=findings)
    payload = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=findings,
    )
    first = render_review(
        review_target=target(),
        selected_reviewers=selected_reviewers(),
        findings=findings,
        posting_plan=plan,
        candidate_payload=payload,
    ).json_data
    second = render_review(
        review_target=target(),
        selected_reviewers=selected_reviewers(),
        findings=findings,
        posting_plan=plan,
        candidate_payload=payload,
    ).json_data

    assert first == second
    encoded = json.dumps(first, sort_keys=True)
    assert "ClassifiedFinding" not in encoded
    assert "ReviewTarget" not in encoded
    assert "PostingPlan" not in encoded


def test_render_module_has_no_writer_or_transport_imports() -> None:
    source = Path("src/reviewgraph/render.py").read_text()
    tree = ast.parse(source)
    forbidden = {"side_effects", "github", "transport", "approval", "finalization", "marker"}
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert not any(
        any(part == forbidden_name for part in imported.split("."))
        for imported in imports
        for forbidden_name in forbidden
    )
