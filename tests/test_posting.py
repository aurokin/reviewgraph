import ast
from pathlib import Path

import pytest

from reviewgraph.models import (
    ClarificationRequest,
    ClassifiedFinding,
    Confidence,
    DiffAnchor,
    LocalNote,
    ReviewTarget,
    ReviewVerdict,
    Severity,
    SuggestedReply,
    SuppressedOutput,
)
from reviewgraph.posting import (
    ArtifactKind,
    PostingPlan,
    PostingDestination,
    PostingPlanError,
    PostingPlanItem,
    assert_builder_signatures_are_pure,
    build_candidate_issue_comment_payload,
    build_posting_plan,
    canonical_visible_body,
    full_body_hash,
    validate_mvp_artifact_kind,
    visible_body_hash,
)


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
    finding_id: str = "finding-1",
    body: str = "The new branch returns stale data when the cache misses.",
    fingerprint: str = "fp-1",
    diff_anchor: DiffAnchor | None = None,
    severity: Severity = Severity.WARNING,
    confidence: Confidence = Confidence.HIGH,
) -> ClassifiedFinding:
    return ClassifiedFinding(
        id=finding_id,
        source_reviewer="correctness",
        source_stage="initial_triage",
        title="Cache miss returns stale data",
        body=body,
        evidence="changed line 12",
        path="src/cache.py",
        line=12,
        priority=1,
        severity=severity,
        confidence=confidence,
        fingerprint=fingerprint,
        diff_anchor=diff_anchor,
    )


def test_posting_plan_supports_all_destinations() -> None:
    anchor = DiffAnchor(
        path="src/cache.py",
        line=12,
        hunk_start=10,
        hunk_end=14,
        hunk_id="src/cache.py:10-14",
        start_line=12,
        target_commit_sha="head456",
    )
    plan = build_posting_plan(
        findings=[finding(), finding("finding-2", fingerprint="fp-2", diff_anchor=anchor)],
        review_target=target(),
        local_notes=[LocalNote("note-1", "Review size", "This is local.", "file count")],
        suggested_replies=[SuggestedReply("reply-1", "comment-1", "Local draft reply")],
        include_summary=True,
        inline_candidate_ids={"finding-2"},
    )

    assert {item.destination for item in plan.items} == {
        PostingDestination.TOP_LEVEL_SUMMARY_ITEM,
        PostingDestination.REVIEW_BODY_ITEM,
        PostingDestination.INLINE_CANDIDATE,
        PostingDestination.LOCAL_ONLY,
        PostingDestination.SUGGESTED_REPLY,
    }


def test_inline_candidates_require_changed_target_diff_anchor() -> None:
    with pytest.raises(PostingPlanError, match="diff anchor"):
        build_posting_plan(findings=[finding()], inline_candidate_ids={"finding-1"})

    bad_anchor = DiffAnchor(
        path="src/cache.py",
        line=20,
        hunk_start=10,
        hunk_end=14,
        hunk_id="src/cache.py:10-14",
        start_line=20,
        target_commit_sha="head456",
    )
    with pytest.raises(PostingPlanError, match="diff anchor"):
        build_posting_plan(
            findings=[finding(diff_anchor=bad_anchor)],
            review_target=target(),
            inline_candidate_ids={"finding-1"},
        )

    wrong_path_anchor = DiffAnchor(
        path="src/other.py",
        line=12,
        hunk_start=10,
        hunk_end=14,
        hunk_id="src/other.py:10-14",
        start_line=12,
        target_commit_sha="head456",
    )
    with pytest.raises(PostingPlanError, match="diff anchor"):
        build_posting_plan(
            findings=[finding(diff_anchor=wrong_path_anchor)],
            review_target=target(),
            inline_candidate_ids={"finding-1"},
        )

    stale_anchor = DiffAnchor(
        path="src/cache.py",
        line=12,
        hunk_start=10,
        hunk_end=14,
        hunk_id="src/cache.py:10-14",
        start_line=12,
        target_commit_sha="oldhead",
    )
    with pytest.raises(PostingPlanError, match="diff anchor"):
        build_posting_plan(
            findings=[finding(diff_anchor=stale_anchor)],
            review_target=target(),
            inline_candidate_ids={"finding-1"},
        )

    bad_start_line_anchor = DiffAnchor(
        path="src/cache.py",
        line=12,
        hunk_start=10,
        hunk_end=14,
        hunk_id="src/cache.py:10-14",
        start_line=13,
        target_commit_sha="head456",
    )
    with pytest.raises(PostingPlanError, match="diff anchor"):
        build_posting_plan(
            findings=[finding(diff_anchor=bad_start_line_anchor)],
            review_target=target(),
            inline_candidate_ids={"finding-1"},
        )

    valid_anchor = DiffAnchor(
        path="src/cache.py",
        line=12,
        hunk_start=10,
        hunk_end=14,
        hunk_id="src/cache.py:10-14",
        start_line=12,
        target_commit_sha="head456",
    )
    with pytest.raises(PostingPlanError, match="unknown inline"):
        build_posting_plan(
            findings=[finding(diff_anchor=valid_anchor)],
            review_target=target(),
            inline_candidate_ids={"finding-1", "missing-finding"},
        )


def test_diff_anchor_requires_durable_inline_metadata() -> None:
    with pytest.raises(ValueError, match="hunk_id"):
        DiffAnchor(
            path="src/cache.py",
            line=12,
            hunk_start=10,
            hunk_end=14,
            start_line=12,
            target_commit_sha="head456",
        )

    with pytest.raises(ValueError, match="start_line"):
        DiffAnchor(
            path="src/cache.py",
            line=12,
            hunk_start=10,
            hunk_end=14,
            hunk_id="src/cache.py:10-14",
            target_commit_sha="head456",
        )

    with pytest.raises(ValueError, match="start_side"):
        DiffAnchor(
            path="src/cache.py",
            line=12,
            hunk_start=10,
            hunk_end=14,
            hunk_id="src/cache.py:10-14",
            start_line=12,
            start_side="LEFT",
            target_commit_sha="head456",
        )


def test_candidate_payload_is_top_level_issue_comment_only() -> None:
    plan = build_posting_plan(findings=[finding()])
    payload = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=[finding()],
    )

    assert payload.artifact_kind == ArtifactKind.ISSUE_COMMENT
    assert payload.review_target.to_ordered_dict() == {
        "owner_repo": "acme/widgets",
        "pr_number": 42,
        "base_sha": "base123",
        "head_sha": "head456",
        "merge_base_sha": "merge789",
        "diff_basis": "merge_base",
    }


@pytest.mark.parametrize(
    "artifact_kind",
    ["pull_request_review", "inline_comment", "approve", "request_changes", "COMMENT"],
)
def test_formal_review_payload_kinds_are_rejected(artifact_kind: str) -> None:
    with pytest.raises(PostingPlanError, match="issue_comment"):
        validate_mvp_artifact_kind(artifact_kind)


def test_non_postable_outputs_are_excluded_from_public_payload() -> None:
    plan = build_posting_plan(
        findings=[finding()],
        local_notes=[LocalNote("note-1", "Review size", "Do not post me.", "file count")],
        suggested_replies=[SuggestedReply("reply-1", "comment-1", "Do not reply automatically.")],
        clarification_requests=[
            ClarificationRequest("clarify-1", "logic", "Is this intentional?", "It affects mergeability.")
        ],
        suppressed_outputs=[SuppressedOutput("suppressed-1", "Generic advice.")],
    )
    payload = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=[finding()],
    )

    assert "Do not post me" not in payload.body
    assert "Do not reply automatically" not in payload.body
    assert "Is this intentional" not in payload.body
    assert "Generic advice" not in payload.body
    assert "Cache miss returns stale data" in payload.body


def test_request_changes_verdict_is_not_public_by_default() -> None:
    plan = build_posting_plan(findings=[finding()])
    payload = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=[finding()],
        local_verdict=ReviewVerdict.REQUEST_CHANGES,
    )

    assert "request_changes" not in payload.body
    assert "request changes" not in payload.body.lower()

    with pytest.raises(PostingPlanError, match="request_changes"):
        build_candidate_issue_comment_payload(
            review_target=target(),
            posting_plan=plan,
            findings=[finding()],
            local_verdict=ReviewVerdict.REQUEST_CHANGES,
            include_public_verdict=True,
        )


def test_candidate_payload_rejects_tampered_public_plan_items() -> None:
    with pytest.raises(ValueError, match="public payload"):
        PostingPlan(
            items=(
                PostingPlanItem(
                    id="finding-1",
                    source_classification="suggested_reply",
                    destination=PostingDestination.SUGGESTED_REPLY,
                    public_payload_eligible=True,
                    fingerprint="fp-1",
                ),
            )
        )

    with pytest.raises(ValueError, match="public payload"):
        PostingPlan(
            items=(
                PostingPlanItem(
                    id="finding-1",
                    source_classification="postable_finding",
                    destination=PostingDestination.LOCAL_ONLY,
                    public_payload_eligible=True,
                    fingerprint="fp-1",
                ),
            )
        )

    stale_fingerprint = PostingPlan(
        items=(
            PostingPlanItem(
                id="finding-1",
                source_classification="postable_finding",
                destination=PostingDestination.REVIEW_BODY_ITEM,
                public_payload_eligible=True,
                fingerprint="fp-old",
            ),
        )
    )
    with pytest.raises(PostingPlanError, match="fingerprint mismatch"):
        build_candidate_issue_comment_payload(
            review_target=target(),
            posting_plan=stale_fingerprint,
            findings=[finding()],
        )

    with pytest.raises(PostingPlanError, match="duplicate finding id"):
        build_candidate_issue_comment_payload(
            review_target=target(),
            posting_plan=build_posting_plan(findings=[finding()]),
            findings=[finding(), finding()],
        )


def test_candidate_payload_has_fingerprints_and_canonical_hashes() -> None:
    second = finding("finding-2", body="Another concrete issue.", fingerprint="fp-0")
    plan = build_posting_plan(findings=[finding(), second])
    payload = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=[finding(), second],
    )

    assert payload.item_fingerprints == ("fp-0", "fp-1")
    assert payload.visible_body_hash == visible_body_hash(payload.body)
    assert canonical_visible_body("a\r\nb\n\n") == "a\nb\n"
    assert full_body_hash("a\r\nb\n\n") == full_body_hash("a\nb\n")
    valid_marker = (
        "<!-- reviewgraph:v1 run_id=run-123 "
        "target=sha256:b0b1700548a7afe8fda856a5128dd4dc3059e7b67bf19aa730bee6a5a9cf4376 "
        "payload=sha256:106a40d32d329b5b429aec2b78e53b278cf66bda3815f53a1cc6d3a0ceb3239a "
        "findings=sha256:49113a9c08f5fd7850b7e050966113aee6e623b9ae1677511710f926bc30d4d0 -->"
    )
    assert visible_body_hash(f"a\n{valid_marker}\n") == visible_body_hash("a\n")
    assert visible_body_hash("a\n<!-- reviewgraph:payload -->\n") != visible_body_hash("a\n")
    assert visible_body_hash("a\n<!-- reviewgraph:payload -->\nb\n") != visible_body_hash("a\nb\n")
    assert visible_body_hash("a\n<!-- reviewgraph:payload") != visible_body_hash("a\n")

    duplicate = finding("finding-3", fingerprint="fp-1")
    duplicate_plan = build_posting_plan(findings=[finding(), duplicate])
    with pytest.raises(PostingPlanError, match="duplicate"):
        build_candidate_issue_comment_payload(
            review_target=target(),
            posting_plan=duplicate_plan,
            findings=[finding(), duplicate],
        )


def test_redacts_supported_secret_classes_before_hashing() -> None:
    secret_body = """
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
    plan = build_posting_plan(findings=[finding(body=secret_body)])
    payload = build_candidate_issue_comment_payload(
        review_target=target(),
        posting_plan=plan,
        findings=[finding(body=secret_body)],
    )

    assert "sk_live" not in payload.body
    assert "sk-proj" not in payload.body
    assert "abcdefghijklmnopqrstuvwxyz" not in payload.body
    assert "PRIVATE KEY" not in payload.body
    assert payload.redaction_status.redacted is True
    assert set(payload.redaction_status.categories) >= {
        "private_key",
        "authorization_header",
        "bearer_token",
        "github_token",
        "standalone_api_key",
        "api_key",
        "env_assignment",
    }


def test_classified_finding_rejects_invalid_enum_values() -> None:
    with pytest.raises(ValueError, match="severity"):
        finding(severity="blocker")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="confidence"):
        finding(confidence="certain")  # type: ignore[arg-type]


def test_posting_module_has_no_writer_or_transport_imports() -> None:
    source = Path("src/reviewgraph/posting.py").read_text()
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
    assert_builder_signatures_are_pure()
