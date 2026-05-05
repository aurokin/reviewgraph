import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from reviewgraph.models import (
    ClarificationRequest,
    ClassifiedFinding,
    Confidence,
    LocalNote,
    MemoryReference,
    OutputClassification,
    RedactionStatus,
    ReviewTarget,
    ReviewVerdict,
    SelectedReviewer,
    Severity,
    SuggestedReply,
    SuppressedOutput,
    TruncationNotice,
)
from reviewgraph.posting import (
    build_candidate_issue_comment_payload,
    build_posting_plan,
    full_body_hash,
    PostingDestination,
    PostingPlan,
    PostingPlanItem,
    visible_body_hash,
)
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


def finding(
    body: str = "Cache miss returns stale data.",
    fingerprint: str = "fp-1",
    title: str = "Cache miss returns stale data",
) -> ClassifiedFinding:
    return ClassifiedFinding(
        id="finding-1",
        source_reviewer="correctness",
        source_stage="initial_triage",
        title=title,
        body=body,
        evidence="changed line 12",
        path="src/cache.py",
        line=12,
        priority=1,
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        fingerprint=fingerprint,
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


def test_candidate_payload_preview_rejects_unbound_target_plan_and_hashes() -> None:
    findings = [finding()]
    plan = build_posting_plan(findings=findings)
    payload = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=findings,
    )

    other_target = ReviewTarget(
        owner_repo="acme/widgets",
        pr_number=43,
        base_sha="base123",
        head_sha="head456",
        merge_base_sha="merge789",
        diff_basis="merge_base",
    )
    with pytest.raises(RenderError, match="target"):
        render_review(
            review_target=other_target,
            selected_reviewers=selected_reviewers(),
            findings=findings,
            posting_plan=plan,
            candidate_payload=payload,
        )

    with pytest.raises(RenderError, match="posting plan"):
        render_review(
            review_target=target(),
            selected_reviewers=selected_reviewers(),
            findings=findings,
            candidate_payload=payload,
        )

    other_finding = finding(fingerprint="fp-2")
    other_plan = build_posting_plan(findings=[other_finding])
    with pytest.raises(RenderError, match="posting plan"):
        render_review(
            review_target=target(),
            selected_reviewers=selected_reviewers(),
            findings=[other_finding],
            posting_plan=other_plan,
            candidate_payload=payload,
        )

    tampered = replace(payload, visible_body_hash="sha256:bad")
    with pytest.raises(RenderError, match="visible body hash"):
        render_review(
            review_target=target(),
            selected_reviewers=selected_reviewers(),
            findings=findings,
            posting_plan=plan,
            candidate_payload=tampered,
        )

    tampered_body = (
        "ReviewGraph dry-run candidate\n"
        "Target: acme/widgets#42\n"
        "Head: head456\n\n"
        "Postable findings:\n"
        "- P1 Cache miss returns stale data: Different public text. (src/cache.py:12)\n"
    )
    tampered_with_recomputed_hashes = replace(
        payload,
        body=tampered_body,
        visible_body_hash=visible_body_hash(tampered_body),
        full_body_hash=full_body_hash(tampered_body),
    )
    with pytest.raises(RenderError, match="current rendered findings"):
        render_review(
            review_target=target(),
            selected_reviewers=selected_reviewers(),
            findings=findings,
            posting_plan=plan,
            candidate_payload=tampered_with_recomputed_hashes,
        )


def test_candidate_payload_preview_rejects_malformed_plan_and_redaction_status() -> None:
    secret_finding = finding(body="api_key = sk_live_1234567890abcdef")
    plan = build_posting_plan(findings=[secret_finding])
    payload = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=[secret_finding],
    )

    malformed_plan = PostingPlan(
        items=(
            PostingPlanItem(
                id="finding-1",
                source_classification=OutputClassification.POSTABLE_FINDING.value,
                destination=PostingDestination.REVIEW_BODY_ITEM,
                public_payload_eligible=True,
            ),
        )
    )
    with pytest.raises(RenderError, match="fingerprint"):
        render_review(
            review_target=target(),
            selected_reviewers=selected_reviewers(),
            findings=[secret_finding],
            posting_plan=malformed_plan,
            candidate_payload=payload,
        )

    tampered_status = replace(
        payload,
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )
    with pytest.raises(RenderError, match="current rendered findings"):
        render_review(
            review_target=target(),
            selected_reviewers=selected_reviewers(),
            findings=[secret_finding],
            posting_plan=plan,
            candidate_payload=tampered_status,
        )


def test_candidate_payload_preview_rejects_redaction_drift_and_unexpected_public_text() -> None:
    findings = [finding()]
    plan = build_posting_plan(findings=findings)
    payload = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=findings,
    )

    secret_body = f"{payload.body}\napi_key = sk_live_1234567890abcdef"
    secret_payload = replace(
        payload,
        body=secret_body,
        visible_body_hash=visible_body_hash(secret_body),
        full_body_hash=full_body_hash(secret_body),
    )
    with pytest.raises(RenderError, match="current rendered findings"):
        render_review(
            review_target=target(),
            selected_reviewers=selected_reviewers(),
            findings=findings,
            posting_plan=plan,
            candidate_payload=secret_payload,
        )

    unexpected_body = f"{payload.body}\nLocal verdict: request_changes"
    unexpected_payload = replace(
        payload,
        body=unexpected_body,
        visible_body_hash=visible_body_hash(unexpected_body),
        full_body_hash=full_body_hash(unexpected_body),
    )
    with pytest.raises(RenderError, match="current rendered findings"):
        render_review(
            review_target=target(),
            selected_reviewers=selected_reviewers(),
            findings=findings,
            posting_plan=plan,
            candidate_payload=unexpected_payload,
        )


def test_postable_finding_can_discuss_request_changes_string() -> None:
    findings = [finding(body="The docs mention request_changes behavior correctly.")]
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

    assert "request_changes behavior" in rendered.markdown


def test_literal_redacted_marker_is_not_counted_as_generated_redaction() -> None:
    findings = [finding(body="The UI literally displays [REDACTED] in this state.")]
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

    assert payload.redaction_status.redacted is False
    assert payload.redaction_status.replacement_count == 0
    assert "literally displays [REDACTED]" in rendered.markdown


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
    assert rendered.redaction_status.replacement_count >= payload.redaction_status.replacement_count


def test_untrusted_memory_body_cannot_enter_candidate_payload_preview() -> None:
    untrusted_body = (
        "The reviewer speculated from stale context. "
        "This exact sentence must not become public evidence."
    )
    copied_sentence = "This exact sentence must not become public evidence."
    findings = [finding(body=f"Copied: {copied_sentence}")]
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
                MemoryReference(
                    "mem-untrusted",
                    "untrusted",
                    "unresolved",
                    "issue_comment",
                    untrusted_body,
                )
            ],
        )


def test_non_trusted_memory_labels_are_unsafe_for_candidate_payload_preview() -> None:
    passive_body = "Unlisted bot context should stay private."
    findings = [finding(body=f"Copied: {passive_body}")]
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
                MemoryReference(
                    "mem-passive",
                    "unlisted_bot",
                    "unresolved",
                    "issue_comment",
                    passive_body,
                )
            ],
        )


def test_non_trusted_memory_body_is_suppressed_from_json_memory() -> None:
    passive_body = "Non trusted memory is local-only."
    rendered = render_review(
        review_target=target(),
        selected_reviewers=selected_reviewers(),
        findings=[finding()],
        memory_references=[
            MemoryReference(
                "mem-passive",
                "unlisted_bot",
                "unresolved",
                "issue_comment",
                passive_body,
            )
        ],
    )

    assert rendered.json_data["memory"][0]["body"] is None


def test_short_untrusted_memory_body_cannot_enter_candidate_payload_preview() -> None:
    untrusted_body = "Ship it now"
    findings = [finding(body=untrusted_body)]
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
                MemoryReference(
                    "mem-short",
                    "untrusted",
                    "unresolved",
                    "issue_comment",
                    untrusted_body,
                )
            ],
        )


def test_exact_short_two_word_untrusted_memory_body_cannot_enter_candidate_payload_preview() -> None:
    untrusted_body = "Ship now"
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
                MemoryReference(
                    "mem-short-two-word",
                    "untrusted",
                    "unresolved",
                    "issue_comment",
                    untrusted_body,
                )
            ],
        )


def test_short_partial_untrusted_memory_fragment_cannot_enter_candidate_payload_preview() -> None:
    untrusted_body = "The customer mentioned codename orion during the thread."
    findings = [finding(body="Copied: codename orion")]
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
                MemoryReference(
                    "mem-fragment",
                    "untrusted",
                    "unresolved",
                    "issue_comment",
                    untrusted_body,
                )
            ],
        )


def test_high_signal_single_token_untrusted_memory_fragment_cannot_enter_candidate_payload_preview() -> None:
    untrusted_body = "The customer mentioned codename orion during the thread."
    findings = [finding(body="Copied: orion")]
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
                MemoryReference(
                    "mem-token",
                    "untrusted",
                    "unresolved",
                    "issue_comment",
                    untrusted_body,
                )
            ],
        )


def test_common_domain_words_in_untrusted_memory_do_not_block_candidate_payload_preview() -> None:
    findings = [finding(title="Cache issue", body="The cache returns stale data on miss.")]
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
        memory_references=[
            MemoryReference(
                "mem-cache",
                "untrusted",
                "unresolved",
                "issue_comment",
                "I saw a cache issue in this PR.",
            )
        ],
    )

    assert rendered.json_data["candidate_payload_preview"]["body"] == payload.body


def test_common_long_domain_word_in_untrusted_memory_does_not_block_candidate_payload_preview() -> None:
    findings = [finding(title="Authentication regression", body="Authentication now fails for valid sessions.")]
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
        memory_references=[
            MemoryReference(
                "mem-auth",
                "untrusted",
                "unresolved",
                "issue_comment",
                "I saw authentication fail locally too.",
            )
        ],
    )

    assert rendered.json_data["candidate_payload_preview"]["body"] == payload.body


@pytest.mark.parametrize(
    "token",
    ("python3", "python-3", "node18", "node-18", "sha256", "react19", "http2"),
)
def test_common_tech_tokens_in_untrusted_memory_do_not_block_candidate_payload_preview(token: str) -> None:
    finding_token = token.replace("-", "")
    findings = [finding(title="Runtime regression", body=f"The {finding_token} runtime path now fails.")]
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
        memory_references=[
            MemoryReference(
                "mem-tech-token",
                "untrusted",
                "unresolved",
                "issue_comment",
                f"I saw {token} mentioned in this PR.",
            )
        ],
    )

    assert rendered.json_data["candidate_payload_preview"]["body"] == payload.body


@pytest.mark.parametrize(
    ("untrusted_body", "finding_body"),
    (
        ("I think line 123456 is wrong.", "Changed line 123456 returns stale data."),
        ("I think line-123456 is wrong.", "Changed line 123456 returns stale data."),
        ("I saw cache 123456 in this PR.", "Cache 123456 is handled by the new branch."),
        ("I saw cache-123456 in this PR.", "Cache 123456 is handled by the new branch."),
        ("Authentication 123456 failed locally.", "Authentication 123456 fails for valid sessions."),
    ),
)
def test_common_word_number_untrusted_memory_does_not_block_candidate_payload_preview(
    untrusted_body: str,
    finding_body: str,
) -> None:
    findings = [finding(body=finding_body)]
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
        memory_references=[
            MemoryReference(
                "mem-common-number",
                "untrusted",
                "unresolved",
                "issue_comment",
                untrusted_body,
            )
        ],
    )

    assert rendered.json_data["candidate_payload_preview"]["body"] == payload.body


def test_unique_low_context_untrusted_token_cannot_enter_candidate_payload_preview() -> None:
    untrusted_body = "Please use mergebypass here."
    findings = [finding(body="Copied: mergebypass")]
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
                MemoryReference(
                    "mem-unique-token",
                    "untrusted",
                    "unresolved",
                    "issue_comment",
                    untrusted_body,
                )
            ],
        )


def test_identifier_like_single_token_untrusted_memory_cannot_enter_candidate_payload_preview() -> None:
    untrusted_body = "The customer mentioned account abc12345 during the thread."
    findings = [finding(body="Copied: abc12345")]
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
                MemoryReference(
                    "mem-identifier",
                    "untrusted",
                    "unresolved",
                    "issue_comment",
                    untrusted_body,
                )
            ],
        )


@pytest.mark.parametrize(
    ("untrusted_body", "finding_body"),
    (
        ("Please use abc12345 here.", "Copied: abc12345"),
        ("Please use abc12345 here.", "Copied: abc-12345"),
        ("Please use abc12345 here.", "Copied: abc_12345"),
        ("The unresolved thread referenced user12345.", "Copied: user12345"),
    ),
)
def test_mixed_identifier_untrusted_memory_cannot_enter_candidate_payload_preview(
    untrusted_body: str,
    finding_body: str,
) -> None:
    findings = [finding(body=finding_body)]
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
                MemoryReference(
                    "mem-mixed-identifier",
                    "untrusted",
                    "unresolved",
                    "issue_comment",
                    untrusted_body,
                )
            ],
        )


@pytest.mark.parametrize(
    ("untrusted_body", "finding_body"),
    (
        ("ACME-42", "Copied: ACME42"),
        ("customer-123456", "Copied: customer123456"),
        ("customer/123456", "Copied: customer123456"),
        ("customer:123456", "Copied: customer123456"),
        ("account/123456", "Copied: account123456"),
        ("ACME.42", "Copied: ACME42"),
        ("The unresolved thread referenced ticket PROJ.1234.", "Copied: PROJ1234"),
        ("The unresolved thread referenced identifier user.12345.", "Copied: user12345"),
        ("The unresolved thread referenced account cache-123456.", "Copied: cache123456"),
        ("The unresolved thread referenced ticket PROJ-1234.", "Copied: PROJ1234"),
        ("The unresolved thread referenced account ACME-42.", "Copied: ACME42"),
        ("The unresolved thread referenced identifier user_12345.", "Copied: user12345"),
    ),
)
def test_delimited_identifier_untrusted_memory_cannot_enter_candidate_payload_preview(
    untrusted_body: str,
    finding_body: str,
) -> None:
    findings = [finding(body=finding_body)]
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
                MemoryReference(
                    "mem-delimited-identifier",
                    "untrusted",
                    "unresolved",
                    "issue_comment",
                    untrusted_body,
                )
            ],
        )


def test_untrusted_memory_fragment_in_title_cannot_enter_candidate_payload_preview() -> None:
    untrusted_body = "Customer mentioned codename orion in the review thread."
    findings = [finding(title="Customer codename orion", body="Generic public body.")]
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
                MemoryReference(
                    "mem-title",
                    "untrusted",
                    "unresolved",
                    "issue_comment",
                    untrusted_body,
                )
            ],
        )


def test_untrusted_memory_header_words_do_not_block_candidate_payload_preview() -> None:
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
        memory_references=[
            MemoryReference(
                "mem-header",
                "untrusted",
                "unresolved",
                "issue_comment",
                "Target branch candidate payload was discussed.",
            )
        ],
    )

    assert rendered.json_data["candidate_payload_preview"]["body"] == payload.body


def test_common_word_near_untrusted_secret_context_does_not_block_candidate_payload_preview() -> None:
    findings = [finding(body="This should return a fresh value when the cache misses.")]
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
        memory_references=[
            MemoryReference(
                "mem-secret-context",
                "untrusted",
                "unresolved",
                "issue_comment",
                "Untrusted commenter said SECRET_TOKEN should never become public evidence.",
            )
        ],
    )

    assert rendered.json_data["candidate_payload_preview"]["body"] == payload.body


@pytest.mark.parametrize("untrusted_body", ("if", "the"))
def test_stopword_only_untrusted_memory_does_not_block_candidate_payload_preview(untrusted_body: str) -> None:
    findings = [finding(body=f"This returns a fresh value {untrusted_body} the cache misses.")]
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
        memory_references=[
            MemoryReference(
                "mem-stopword",
                "untrusted",
                "unresolved",
                "issue_comment",
                untrusted_body,
            )
        ],
    )

    assert rendered.json_data["candidate_payload_preview"]["body"] == payload.body


def test_punctuation_normalized_untrusted_memory_cannot_enter_candidate_payload_preview() -> None:
    untrusted_body = "The reviewer wrote Ship-it now in an unresolved comment."
    findings = [finding(body="Copied: Ship it now")]
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
                MemoryReference(
                    "mem-punctuation",
                    "untrusted",
                    "unresolved",
                    "issue_comment",
                    untrusted_body,
                )
            ],
        )


def test_underscore_normalized_untrusted_memory_cannot_enter_candidate_payload_preview() -> None:
    untrusted_body = "The unresolved thread referenced SECRET_TOKEN."
    findings = [finding(body="Copied: SECRET TOKEN")]
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
                MemoryReference(
                    "mem-underscore",
                    "untrusted",
                    "unresolved",
                    "issue_comment",
                    untrusted_body,
                )
            ],
        )


@pytest.mark.parametrize(
    ("untrusted_body", "finding_body"),
    (
        ("The unresolved thread referenced SECRET_TOKEN.", "Copied: SECRETTOKEN"),
        ("The unresolved thread referenced codename-orion.", "Copied: codenameorion"),
    ),
)
def test_compacted_delimiter_untrusted_memory_cannot_enter_candidate_payload_preview(
    untrusted_body: str,
    finding_body: str,
) -> None:
    findings = [finding(body=finding_body)]
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
                MemoryReference(
                    "mem-compact",
                    "untrusted",
                    "unresolved",
                    "issue_comment",
                    untrusted_body,
                )
            ],
        )


@pytest.mark.parametrize(
    ("untrusted_body", "finding_body"),
    (
        ("The unresolved thread said Ship-it now.", "Copied: Shipit"),
        ("The unresolved thread said O-R-I-O-N.", "Copied: orion"),
    ),
)
def test_low_signal_compacted_untrusted_memory_fragments_do_not_block_candidate_payload_preview(
    untrusted_body: str,
    finding_body: str,
) -> None:
    findings = [finding(body=finding_body)]
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
        memory_references=[
            MemoryReference(
                "mem-compact-low-signal",
                "untrusted",
                "unresolved",
                "issue_comment",
                untrusted_body,
            )
        ],
    )

    assert rendered.json_data["candidate_payload_preview"]["body"] == payload.body


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
