from reviewgraph.findings import GRAPH_OWNED_SUPPRESSION_REASON, normalize_reviewer_output
from reviewgraph.models import (
    ClarificationState,
    Confidence,
    ReviewStage,
    ReviewerRunKey,
    Severity,
)


def test_normalize_reviewer_output_preserves_all_valid_artifact_types() -> None:
    run_key = _run_key()

    result = normalize_reviewer_output(
        {
            "reviewer": "spoofed",
            "stage": "wrong_stage",
            "items": [
                {
                    "type": "finding",
                    "id": "finding-cache",
                    "severity": "warning",
                    "confidence": "high",
                    "path": "src/cache.py",
                    "line": 12,
                    "line_end": 14,
                    "title": "Cache miss returns stale value",
                    "rationale": "The new branch returns stale data.",
                    "evidence": "Changed line 12 returns stale_value.",
                    "suggested_fix": "Fetch before returning.",
                    "evidence_sources": ["diff"],
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
                    "question": "Should stale cache values be allowed?",
                    "why_it_matters": "The verdict depends on intended fallback behavior.",
                    "evidence_sources": ["diff"],
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
        },
        run_key,
    )

    assert result.errors == ()
    assert result.findings[0].id == "finding-cache"
    assert result.findings[0].severity == Severity.WARNING
    assert result.findings[0].confidence == Confidence.HIGH
    assert result.findings[0].line_end == 14
    assert result.findings[0].evidence_sources == ("diff",)
    assert result.local_notes[0].id == "note-context"
    request = result.clarification_requests[0]
    assert request.id == "clarify-cache"
    assert request.reviewer == "quality"
    assert request.source_stage == "initial_triage"
    assert request.source_run_key == run_key
    assert request.status == ClarificationState.PENDING
    assert request.resume_target_stage == ReviewStage.CLARIFICATION_REVIEW
    assert request.resume_target_reviewers == ("quality",)
    assert request.evidence_sources == ("diff",)
    assert result.suggested_replies[0].id == "reply-cache"
    assert result.suppressed_outputs[0].id == "nonfinding-style"


def test_clarification_control_metadata_is_graph_owned() -> None:
    run_key = _run_key(reviewer="logic", stage=ReviewStage.LOGIC_REVIEW)

    result = normalize_reviewer_output(
        {
            "reviewer": "logic",
            "stage": "logic_review",
            "items": [
                {
                    "type": "clarification_request",
                    "id": "clarify-intent",
                    "question": "Is this migration intentional?",
                    "why_it_matters": "Mergeability depends on product intent.",
                    "source_stage": "initial_triage",
                    "source_run_key": {"reviewer": "spoofed"},
                    "status": "resolved",
                    "resume_target": {"stage": "initial_triage", "reviewers": ["security"]},
                }
            ],
        },
        run_key,
    )

    assert result.clarification_requests == ()
    assert result.suppressed_outputs[0].reason == GRAPH_OWNED_SUPPRESSION_REASON
    assert result.errors[0].code == "graph_owned_reviewer_fields"
    assert result.errors[0].fatal is False
    assert result.errors[0].repairable is False
    assert result.errors[0].rejected_fields == (
        "resume_target",
        "source_run_key",
        "source_stage",
        "status",
    )


def test_graph_owned_fields_on_non_finding_artifacts_are_rejected() -> None:
    run_key = _run_key()

    result = normalize_reviewer_output(
        {
            "reviewer": "quality",
            "stage": "initial_triage",
            "items": [
                {
                    "type": "local_note",
                    "id": "note-context",
                    "title": "Context note",
                    "body": "Keep this local.",
                    "evidence": "Fixture metadata.",
                    "verdict": "approved",
                },
                {
                    "type": "suggested_reply",
                    "id": "reply-cache",
                    "source_comment_id": "comment-cache-intent",
                    "proposed_body": "I checked the cache fallback path.",
                    "posting_destination": "github",
                },
                {
                    "type": "non_finding",
                    "id": "nonfinding-style",
                    "reason": "Style-only observation.",
                    "classification": "non_finding",
                },
            ],
        },
        run_key,
    )

    assert result.local_notes == ()
    assert result.suggested_replies == ()
    assert len(result.suppressed_outputs) == 3
    assert [error.code for error in result.errors] == [
        "graph_owned_reviewer_fields",
        "graph_owned_reviewer_fields",
        "graph_owned_reviewer_fields",
    ]
    assert [error.rejected_fields for error in result.errors] == [
        ("verdict",),
        ("posting_destination",),
        ("classification",),
    ]


def test_graph_owned_finding_fields_are_rejected_without_being_stripped() -> None:
    run_key = _run_key()

    result = normalize_reviewer_output(
        {
            "reviewer": "quality",
            "stage": "initial_triage",
            "items": [
                {
                    "type": "finding",
                    "id": "finding-cache",
                    "severity": "warning",
                    "confidence": "high",
                    "path": "src/cache.py",
                    "line": 12,
                    "title": "Cache miss returns stale value",
                    "rationale": "The new branch returns stale data.",
                    "evidence": "Changed line 12 returns stale_value.",
                    "fingerprint": "reviewer-owned",
                    "priority": 0,
                }
            ],
        },
        run_key,
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].reason == GRAPH_OWNED_SUPPRESSION_REASON
    assert result.errors[0].code == "graph_owned_reviewer_fields"
    assert result.errors[0].fatal is False
    assert result.errors[0].repairable is False
    assert result.errors[0].rejected_fields == ("fingerprint", "priority")


def test_malformed_output_is_atomic_and_structured_for_repair_policy() -> None:
    run_key = _run_key()

    result = normalize_reviewer_output(
        {
            "reviewer": "quality",
            "stage": "initial_triage",
            "items": [
                {
                    "type": "finding",
                    "id": "finding-cache",
                    "severity": "warning",
                    "confidence": "high",
                    "path": "src/cache.py",
                    "line": 12,
                    "title": "Cache miss returns stale value",
                    "rationale": "The new branch returns stale data.",
                    "evidence": "Changed line 12 returns stale_value.",
                },
                {
                    "type": "local_note",
                    "id": "note-bad",
                    "title": "Bad note",
                    "body": ["not", "a", "string"],
                    "evidence": "Fixture metadata.",
                },
            ],
        },
        run_key,
    )

    assert result.findings == ()
    assert result.local_notes == ()
    assert result.fatal_errors[0].code == "invalid_local_note"
    assert result.fatal_errors[0].message == "local_note.body is required"
    assert result.fatal_errors[0].run_key == run_key
    assert result.fatal_errors[0].repairable is True
    assert result.fatal_errors[0].item_id == "note-bad"
    assert result.fatal_errors[0].item_index == 1


def test_invalid_items_list_returns_structured_normalization_error() -> None:
    run_key = _run_key()

    result = normalize_reviewer_output(
        {"reviewer": "quality", "stage": "initial_triage", "items": "not-a-list"},
        run_key,
    )

    assert result.fatal_errors[0].code == "invalid_items"
    assert result.fatal_errors[0].message == "fake reviewer output requires an items list"
    assert result.fatal_errors[0].repairable is True
    assert result.fatal_errors[0].run_key == run_key


def _run_key(
    *,
    reviewer: str = "quality",
    stage: ReviewStage = ReviewStage.INITIAL_TRIAGE,
) -> ReviewerRunKey:
    return ReviewerRunKey(
        target_hash="sha256:target",
        config_hash="sha256:config",
        stage=stage,
        reviewer=reviewer,
    )
