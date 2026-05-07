import json
import re
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

import pytest

from reviewgraph.models import (
    ActorPermissionGateResult,
    ApprovalDecision,
    ArtifactKind,
    CandidateIssueCommentPayload,
    ClarificationAnswer,
    ClarificationRequest,
    ClarificationState,
    ClarificationStatus,
    ClassifiedFinding,
    Confidence,
    ContextBudget,
    FinalIssueCommentPayload,
    FinalizationState,
    FinalizationStatus,
    GateStatus,
    GitHubWriterResult,
    GraphError,
    MarkerReconciliationResult,
    MemoryReference,
    NormalizationError,
    OutputClassification,
    PayloadValidationReasonCode,
    PayloadValidationResult,
    PostInteractionGateResult,
    PostingDestination,
    PostingPlan,
    PostingPlanItem,
    PostingTarget,
    RawReviewerFinding,
    RedactionStatus,
    ReviewConfig,
    ReviewerResult,
    ReviewerAgentConfig,
    ReviewerRepairRecord,
    ReviewerRunKey,
    ReviewerRunStatus,
    ReviewerRunStatusValue,
    ReviewerTriggers,
    ReviewStage,
    ReviewState,
    ReviewTarget,
    RiskLevel,
    RiskAssessment,
    RiskThresholds,
    RunMode,
    Severity,
    LocalNote,
    PullRequestComment,
    PullRequestReview,
    PullRequestReviewThread,
    SuggestedReply,
    SuppressedReviewerOutput,
    WriterStatus,
    validate_priority,
)
from reviewgraph.hashing import final_payload_hash, findings_hash, marker_payload_hash, visible_body_hash


EXPECTED_STATE_FIELDS = (
    "run_id",
    "run_mode",
    "post_enabled",
    "pr_ref",
    "review_target",
    "posting_target",
    "pr",
    "conversation_memory",
    "read_gaps",
    "config",
    "config_hash",
    "stage_queue",
    "active_stage",
    "suspended_stage",
    "completed_stages",
    "risk",
    "selected_reviewers",
    "reviewer_run_keys",
    "reviewer_run_status",
    "reviewer_results",
    "context_budget",
    "redaction_status",
    "findings",
    "local_notes",
    "suggested_replies",
    "suppressed_outputs",
    "clarification_requests",
    "pending_clarification_ids",
    "ready_clarification_ids",
    "active_clarification_id",
    "clarifications",
    "clarification_status",
    "ranked_findings",
    "local_verdict",
    "rendered_markdown",
    "posting_plan",
    "post_interaction_gate",
    "actor_permission_gate",
    "payload_validation",
    "marker_reconciliation",
    "finalization_status",
    "candidate_github_payload",
    "final_github_payload",
    "final_payload_hash",
    "approval",
    "writer_result",
    "errors",
)


def test_review_state_matches_state_graph_fields_without_defer_list() -> None:
    docs_fields = _state_graph_fields()

    assert tuple(docs_fields) == EXPECTED_STATE_FIELDS
    assert ReviewState.field_names() == EXPECTED_STATE_FIELDS


def test_review_state_core_fields_are_typed_contracts_not_placeholders() -> None:
    hints = get_type_hints(ReviewState)

    for name in EXPECTED_STATE_FIELDS:
        assert name in hints
        assert not _contains_any(hints[name]), f"{name} must not use Any"
        assert get_origin(hints[name]) not in {dict, list} or get_args(hints[name]), name


def test_review_target_hash_is_canonical_and_target_bound() -> None:
    target = ReviewTarget(
        owner_repo="acme/widgets",
        pr_number=42,
        base_sha="base123",
        head_sha="head456",
        merge_base_sha=None,
        diff_basis="merge_base",
    )
    canonical_json = (
        '{"base_sha":"base123","diff_basis":"merge_base","head_sha":"head456",'
        '"merge_base_sha":null,"owner_repo":"acme/widgets","pr_number":42}'
    )

    assert json.dumps(target.to_ordered_dict(), sort_keys=True, separators=(",", ":")) == canonical_json
    assert target.target_hash() == "sha256:b0b1700548a7afe8fda856a5128dd4dc3059e7b67bf19aa730bee6a5a9cf4376"
    assert target.target_hash() == target.target_hash()

    mutations = (
        {"owner_repo": "acme/other"},
        {"pr_number": 43},
        {"base_sha": "base999"},
        {"head_sha": "head999"},
        {"merge_base_sha": "merge789"},
        {"diff_basis": "head"},
    )
    for mutation in mutations:
        values = target.to_ordered_dict()
        values.update(mutation)
        assert ReviewTarget(**values).target_hash() != target.target_hash()


def test_invalid_priority_and_enum_values_fail() -> None:
    with pytest.raises(ValueError, match="priority"):
        validate_priority(4)
    with pytest.raises(ValueError, match="priority"):
        validate_priority(True)
    with pytest.raises(ValueError):
        Severity("blocker")
    with pytest.raises(ValueError):
        Confidence("certain")
    with pytest.raises(ValueError):
        RunMode("live")


def test_classified_finding_keeps_graph_owned_fields_explicit() -> None:
    finding = ClassifiedFinding(
        id="finding-1",
        source_reviewer="security",
        source_stage="specialized_review",
        title="Auth bypass",
        body="The new branch skips auth.",
        evidence="Changed line 12 skips auth.",
        path="src/auth.py",
        line=12,
        priority=1,
        severity=Severity.CRITICAL,
        confidence=Confidence.HIGH,
        fingerprint="fp-1",
        blocking=True,
    )

    assert finding.classification == OutputClassification.POSTABLE_FINDING
    assert finding.priority == 1
    assert finding.blocking is True
    assert finding.fingerprint == "fp-1"
    assert "blocking" in {field.name for field in fields(ClassifiedFinding)}


@pytest.mark.parametrize(
    "graph_owned_field",
    [
        "approved",
        "blocking",
        "classification",
        "destination",
        "diff_anchor",
        "final_priority",
        "fingerprint",
        "github_destination",
        "posting_destination",
        "posting_plan",
        "priority",
        "public_payload_eligible",
        "review_event",
        "target_commit_sha",
        "verdict",
    ],
)
def test_raw_reviewer_findings_reject_graph_owned_fields(graph_owned_field: str) -> None:
    raw = _raw_finding()
    raw[graph_owned_field] = "graph-owned"

    with pytest.raises(ValueError, match="graph-owned"):
        RawReviewerFinding.from_mapping(raw)


def test_raw_reviewer_finding_serialization_excludes_graph_owned_fields() -> None:
    finding = RawReviewerFinding.from_mapping(_raw_finding())
    serialized = asdict(finding)

    for field in ("classification", "blocking", "priority", "fingerprint", "github_destination", "verdict"):
        assert field not in serialized


def test_raw_reviewer_finding_records_evidence_memory_ids() -> None:
    raw = _raw_finding()
    raw["evidence_sources"] = ["trusted_memory"]
    raw["evidence_memory_ids"] = ["comment-1", "thread-1"]

    finding = RawReviewerFinding.from_mapping(raw)

    assert finding.evidence_sources == ("trusted_memory",)
    assert finding.evidence_memory_ids == ("comment-1", "thread-1")


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("id", None),
        ("path", []),
        ("line", True),
        ("line", 0),
        ("title", ""),
        ("evidence", ["x"]),
        ("evidence_sources", ["diff", "unsupported"]),
        ("evidence_sources", "diff"),
        ("evidence_memory_ids", ["comment-1", ""]),
        ("evidence_memory_ids", "comment-1"),
        ("line_end", 1),
        ("suggested_fix", ""),
    ],
)
def test_raw_reviewer_findings_reject_malformed_field_types(field_name: str, bad_value: object) -> None:
    raw = _raw_finding()
    raw[field_name] = bad_value

    with pytest.raises(ValueError):
        RawReviewerFinding.from_mapping(raw)


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("id", ""),
        ("severity", "warning"),
        ("confidence", "high"),
        ("line", True),
        ("line", 0),
        ("line_end", 10),
        ("suggested_fix", ""),
    ],
)
def test_raw_reviewer_finding_constructor_rejects_invalid_contract_values(
    field_name: str, bad_value: object
) -> None:
    kwargs: dict[str, object] = {
        "id": "raw-1",
        "severity": Severity.WARNING,
        "confidence": Confidence.HIGH,
        "path": "src/cache.py",
        "line": 12,
        "title": "Cache miss returns stale data",
        "rationale": "The branch returns stale data.",
        "evidence": "Changed line 12 returns stale data.",
    }
    kwargs[field_name] = bad_value

    with pytest.raises(ValueError):
        RawReviewerFinding(**kwargs)  # type: ignore[arg-type]


def test_reviewer_run_key_is_stable_and_status_is_explicit() -> None:
    key = ReviewerRunKey(
        target_hash="sha256:target",
        config_hash="sha256:config",
        stage=ReviewStage.LOGIC_REVIEW,
        reviewer="logic",
        attempt=2,
        retry_of="run-1",
        clarification_id="clarify-1",
    )
    status = ReviewerRunStatus(status=ReviewerRunStatusValue.SELECTED, run_key=key)

    assert key.stable_key() == (
        '{"attempt":2,"clarification_id":"clarify-1","config_hash":"sha256:config",'
        '"retry_of":"run-1","reviewer":"logic","stage":"logic_review","target_hash":"sha256:target"}'
    )
    assert status.status == ReviewerRunStatusValue.SELECTED


@pytest.mark.parametrize(
    "build",
    [
        lambda: ReviewerRunKey(
            target_hash="sha256:target",
            config_hash="sha256:config",
            stage=ReviewStage.LOGIC_REVIEW,
            reviewer="logic",
            retry_of="",
        ),
        lambda: ReviewerRunStatus(status="selected", run_key=_run_key()),
        lambda: ReviewerRunStatus(status=ReviewerRunStatusValue.SELECTED, run_key=object()),
        lambda: ReviewerRunStatus(status=ReviewerRunStatusValue.SELECTED, run_key=_run_key(), reason=""),
    ],
)
def test_reviewer_run_status_contracts_reject_invalid_values(build: object) -> None:
    with pytest.raises(ValueError):
        build()


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("findings", ({"id": "raw-1"},)),
        (
            "findings",
            (
                ClassifiedFinding(
                    id="finding-1",
                    source_reviewer="logic",
                    source_stage="logic_review",
                    title="Graph-owned classified finding",
                    body="This should not pass as raw reviewer output.",
                    evidence="The graph owns classification fields.",
                    path="src/cache.py",
                    line=12,
                    priority=1,
                    severity=Severity.WARNING,
                    confidence=Confidence.HIGH,
                    fingerprint="sha256:finding",
                ),
            ),
        ),
        ("clarification_requests", (object(),)),
        ("local_notes", (object(),)),
        ("suggested_replies", (object(),)),
        ("suppressed_outputs", (object(),)),
    ],
)
def test_reviewer_result_rejects_non_raw_output_contract_values(field_name: str, bad_value: object) -> None:
    key = ReviewerRunKey(
        target_hash="sha256:target",
        config_hash="sha256:config",
        stage=ReviewStage.LOGIC_REVIEW,
        reviewer="logic",
    )
    kwargs: dict[str, object] = {"run_key": key, field_name: bad_value}

    with pytest.raises(ValueError):
        ReviewerResult(**kwargs)  # type: ignore[arg-type]


def test_reviewer_repair_record_serializes_machine_readable_audit_shape() -> None:
    key = ReviewerRunKey(
        target_hash="sha256:target",
        config_hash="sha256:config",
        stage=ReviewStage.LOGIC_REVIEW,
        reviewer="logic",
    )
    error = NormalizationError(
        code="invalid_json",
        message="fake reviewer output is not valid JSON",
        run_key=key,
        repairable=True,
    )

    record = ReviewerRepairRecord(
        attempt_count=1,
        status="succeeded",
        original_output='{"items": [',
        repaired_output={"items": []},
        errors=(error,),
    )

    assert record.to_ordered_dict() == {
        "attempt_count": 1,
        "status": "succeeded",
        "original_output": '{"items": [',
        "repaired_output": {"items": []},
        "errors": [error.to_ordered_dict()],
    }
    result = ReviewerResult(run_key=key, repair_record=record)
    assert result.repair_record == record


@pytest.mark.parametrize(
    "build",
    [
        lambda key: ReviewerRepairRecord(attempt_count=-1, status="failed"),
        lambda key: ReviewerRepairRecord(attempt_count=1, status="unknown"),
        lambda key: ReviewerRepairRecord(attempt_count=1, status="failed", original_output=object()),
        lambda key: ReviewerRepairRecord(attempt_count=1, status="failed", repaired_output=object()),
        lambda key: ReviewerRepairRecord(attempt_count=1, status="failed", original_output={1: "bad-key"}),
        lambda key: ReviewerRepairRecord(
            attempt_count=1,
            status="failed",
            errors=("invalid_json",),
        ),
        lambda key: ReviewerResult(run_key=key, repair_record=object()),
    ],
)
def test_reviewer_repair_record_rejects_invalid_contract_values(build) -> None:
    key = ReviewerRunKey(
        target_hash="sha256:target",
        config_hash="sha256:config",
        stage=ReviewStage.LOGIC_REVIEW,
        reviewer="logic",
    )

    with pytest.raises(ValueError):
        build(key)


@pytest.mark.parametrize(
    "build",
    [
        lambda: LocalNote("", "Title", "Body", "Evidence"),
        lambda: LocalNote("note-1", "", "Body", "Evidence"),
        lambda: LocalNote(
            "note-1",
            "Title",
            "Body",
            "Evidence",
            classification=OutputClassification.POSTABLE_FINDING,
        ),
        lambda: SuggestedReply("", "comment-1", "Reply"),
        lambda: SuggestedReply("reply-1", "", "Reply"),
        lambda: SuggestedReply("reply-1", "comment-1", ""),
        lambda: SuggestedReply("reply-1", "comment-1", "Reply", classification=OutputClassification.NON_FINDING),
        lambda: SuppressedReviewerOutput("", "Reason"),
        lambda: SuppressedReviewerOutput("suppressed-1", ""),
        lambda: SuppressedReviewerOutput("suppressed-1", "Reason", classification=OutputClassification.LOCAL_NOTE),
        lambda: ClarificationRequest("", "logic", "Question?", "Ambiguity blocks review."),
        lambda: ClarificationRequest("clarify-1", "", "Question?", "Ambiguity blocks review."),
        lambda: ClarificationRequest("clarify-1", "logic", "", "Ambiguity blocks review."),
        lambda: ClarificationRequest("clarify-1", "logic", "Question?", ""),
        lambda: ClarificationRequest("clarify-1", "logic", "Question?", "Why", blocks_verdict=1),
        lambda: ClarificationRequest(
            "clarify-1",
            "logic",
            "Question?",
            "Why",
            classification=OutputClassification.SUGGESTED_REPLY,
        ),
        lambda: ClarificationAnswer("", "clarify-1", "Answer", "human", "2026-05-06T01:00:00Z"),
        lambda: ClarificationAnswer("answer-1", "", "Answer", "human", "2026-05-06T01:00:00Z"),
        lambda: ClarificationStatus("", ClarificationState.PENDING),
        lambda: ClarificationStatus("clarify-1", "pending"),
        lambda: ClarificationStatus("clarify-1", ClarificationState.PENDING, reason=""),
    ],
)
def test_non_finding_output_contracts_reject_invalid_values(build: object) -> None:
    with pytest.raises(ValueError):
        build()


def test_risk_assessment_records_configured_thresholds() -> None:
    assessment = RiskAssessment(
        changed_file_count=4,
        changed_line_count=120,
        touched_surfaces=("billing",),
        labels=("backend",),
        diff_pattern_hints=("migration",),
        configured_thresholds=RiskThresholds(
            changed_files_medium=3,
            changed_files_high=10,
            changed_lines_medium=50,
            changed_lines_high=500,
            risk_min=RiskLevel.MEDIUM,
        ),
        risk_level=RiskLevel.MEDIUM,
        reasons=("changed_lines >= medium threshold",),
    )

    assert assessment.configured_thresholds.changed_lines_medium == 50
    assert assessment.configured_thresholds.risk_min == RiskLevel.MEDIUM


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("changed_files_medium", 0),
        ("changed_files_medium", True),
        ("changed_files_high", 3),
        ("changed_lines_medium", -1),
        ("changed_lines_high", 50),
        ("risk_min", "medium"),
    ],
)
def test_risk_thresholds_reject_invalid_contract_values(field_name: str, bad_value: object) -> None:
    kwargs: dict[str, object] = {
        "changed_files_medium": 3,
        "changed_files_high": 10,
        "changed_lines_medium": 50,
        "changed_lines_high": 500,
        "risk_min": RiskLevel.MEDIUM,
    }
    kwargs[field_name] = bad_value

    with pytest.raises(ValueError):
        RiskThresholds(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("changed_file_count", -1),
        ("changed_file_count", False),
        ("changed_line_count", -1),
        ("changed_line_count", True),
        ("touched_surfaces", ["billing"]),
        ("touched_surfaces", ("",)),
        ("labels", ["backend"]),
        ("diff_pattern_hints", [".*migration.*"]),
        ("configured_thresholds", "not-thresholds"),
        ("risk_level", "medium"),
        ("reasons", ()),
        ("reasons", ("",)),
        ("reasons", ["changed_lines >= medium threshold"]),
    ],
)
def test_risk_assessment_rejects_invalid_contract_values(field_name: str, bad_value: object) -> None:
    kwargs: dict[str, object] = {
        "changed_file_count": 4,
        "changed_line_count": 120,
        "touched_surfaces": ("billing",),
        "labels": ("backend",),
        "diff_pattern_hints": ("migration",),
        "configured_thresholds": RiskThresholds(
            changed_files_medium=3,
            changed_files_high=10,
            changed_lines_medium=50,
            changed_lines_high=500,
            risk_min=RiskLevel.MEDIUM,
        ),
        "risk_level": RiskLevel.MEDIUM,
        "reasons": ("changed_lines >= medium threshold",),
    }
    kwargs[field_name] = bad_value

    with pytest.raises(ValueError):
        RiskAssessment(**kwargs)  # type: ignore[arg-type]


def test_side_effect_contracts_bind_approval_finalization_and_writer_metadata() -> None:
    target = _target()
    redaction = RedactionStatus(redacted=False, replacement_count=0)
    posting_target = PostingTarget(review_target=target)
    plan = PostingPlan(
        items=(
            PostingPlanItem(
                id="finding-1",
                source_classification=OutputClassification.POSTABLE_FINDING.value,
                destination=PostingDestination.REVIEW_BODY_ITEM,
                public_payload_eligible=True,
                fingerprint="sha256:finding",
                body="Review body",
            ),
        )
    )
    payload = _final_payload(target=target, fingerprints=("fp-1",), redaction=redaction)
    approval = ApprovalDecision(
        approved=True,
        approved_item_ids=("finding-1",),
        approved_final_payload_hash=payload.final_payload_hash,
        approved_review_target_hash=target.target_hash(),
        approved_review_target=target,
        approved_github_actor="reviewgraph-bot",
        approved_permission="write",
        approved_permission_checked_at="2026-05-06T01:00:00Z",
        include_public_verdict=False,
        approved_by="local-user",
        timestamp="2026-05-06T01:01:00Z",
    )
    actor_gate = ActorPermissionGateResult(
        status=GateStatus.PASS,
        actor="reviewgraph-bot",
        permission="write",
        checked_at="2026-05-06T01:00:00Z",
    )
    interaction_gate = PostInteractionGateResult(status=GateStatus.PASS, interactive=True)
    validation = PayloadValidationResult(
        status=GateStatus.PASS,
        payload_hash=payload.final_payload_hash,
        target_hash=target.target_hash(),
    )
    reconciliation = MarkerReconciliationResult(
        status=GateStatus.PASS,
        trusted_actor="reviewgraph-bot",
        existing_comment_id=None,
    )
    finalization = FinalizationStatus(
        state=FinalizationState.FINALIZED,
        final_payload_hash=payload.final_payload_hash,
        target_hash=target.target_hash(),
    )
    writer = GitHubWriterResult(
        status=WriterStatus.NOT_CALLED,
        artifact_kind=ArtifactKind.ISSUE_COMMENT,
        target_hash=target.target_hash(),
        payload_hash=payload.final_payload_hash,
    )

    assert approval.approved_item_ids == ("finding-1",)
    assert approval.approved_review_target_hash == target.target_hash()
    assert posting_target.review_target == target
    assert plan.public_payload_items[0].id == "finding-1"
    assert interaction_gate.interactive is True
    assert actor_gate.permission == "write"
    assert validation.payload_hash == payload.final_payload_hash
    assert reconciliation.trusted_actor == "reviewgraph-bot"
    assert finalization.state == FinalizationState.FINALIZED
    assert writer.status == WriterStatus.NOT_CALLED


@pytest.mark.parametrize(
    "build",
    [
        lambda: PullRequestComment(
            id="comment-1",
            author="reviewer",
            author_association="MEMBER",
            author_type="user",
            body="body",
            created_at="2026-05-06T00:00:00Z",
            trust_label="",
            source_type="issue_comment",
        ),
        lambda: PullRequestComment(
            id="comment-1",
            author="reviewer",
            author_association="MEMBER",
            author_type="user",
            body="body",
            created_at="2026-05-06T00:00:00Z",
            trust_label="trusted",
            source_type="",
        ),
        lambda: PullRequestReview(
            id="review-1",
            author="reviewer",
            author_association="MEMBER",
            author_type="user",
            state="COMMENTED",
            created_at="",
            trust_label="trusted",
            source_type="review",
        ),
        lambda: PullRequestReview(
            id="review-1",
            author="reviewer",
            author_association="MEMBER",
            author_type="user",
            state="COMMENTED",
            created_at="2026-05-06T00:00:00Z",
            trust_label="trusted",
            source_type="",
        ),
        lambda: PullRequestReviewThread(
            id="thread-1",
            path="src/app.py",
            resolved_status="unresolved",
            comments=(),
        ),
    ],
)
def test_pull_request_context_contracts_require_trust_source_and_thread_comments(build: object) -> None:
    with pytest.raises(ValueError):
        build()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"trust_label": "untrusted"},
        {"resolved_status": "resolved"},
        {"source_type": "review"},
        {"author_type": None},
        {"author_type": "organization"},
    ],
)
def test_actionable_memory_requires_trusted_unresolved_supported_actor(kwargs: dict[str, object]) -> None:
    values = {
        "id": "mem-1",
        "trust_label": "trusted",
        "resolved_status": "unresolved",
        "source_type": "issue_comment",
        "body": "Please review ambiguous behavior.",
        "author": "maintainer",
        "author_association": "MEMBER",
        "author_type": "user",
        "actionable": True,
    }
    values.update(kwargs)

    with pytest.raises(ValueError):
        MemoryReference(**values)


@pytest.mark.parametrize(
    "build",
    [
        lambda: RedactionStatus(redacted="no", replacement_count=0),
        lambda: RedactionStatus(redacted=False, replacement_count=-1),
        lambda: RedactionStatus(redacted=True, replacement_count=0),
        lambda: RedactionStatus(redacted=False, replacement_count=0, categories=["secret"]),
        lambda: RedactionStatus(redacted=False, replacement_count=0, status="pass"),
        lambda: PostingTarget(review_target=object()),
        lambda: PostingTarget(review_target=_target(), artifact_kind="pull_request_review"),
        lambda: PostingPlanItem(
            id="",
            source_classification=OutputClassification.POSTABLE_FINDING.value,
            destination=PostingDestination.REVIEW_BODY_ITEM,
            public_payload_eligible=True,
        ),
        lambda: PostingPlanItem(
            id="finding-1",
            source_classification="",
            destination=PostingDestination.REVIEW_BODY_ITEM,
            public_payload_eligible=True,
        ),
        lambda: PostingPlanItem(
            id="finding-1",
            source_classification=OutputClassification.POSTABLE_FINDING.value,
            destination="review_body_item",
            public_payload_eligible=True,
        ),
        lambda: PostingPlanItem(
            id="finding-1",
            source_classification=OutputClassification.POSTABLE_FINDING.value,
            destination=PostingDestination.REVIEW_BODY_ITEM,
            public_payload_eligible=1,
        ),
        lambda: PostingPlanItem(
            id="finding-1",
            source_classification=OutputClassification.POSTABLE_FINDING.value,
            destination=PostingDestination.LOCAL_ONLY,
            public_payload_eligible=True,
        ),
        lambda: PostingPlanItem(
            id="finding-1",
            source_classification=OutputClassification.POSTABLE_FINDING.value,
            destination=PostingDestination.REVIEW_BODY_ITEM,
            public_payload_eligible=True,
            fingerprint="",
        ),
        lambda: PostingPlan(items=[]),
        lambda: PostingPlan(items=(object(),)),
        lambda: PostingPlan(
            items=(
                PostingPlanItem(
                    id="finding-1",
                    source_classification=OutputClassification.POSTABLE_FINDING.value,
                    destination=PostingDestination.REVIEW_BODY_ITEM,
                    public_payload_eligible=True,
                ),
                PostingPlanItem(
                    id="finding-1",
                    source_classification=OutputClassification.POSTABLE_FINDING.value,
                    destination=PostingDestination.REVIEW_BODY_ITEM,
                    public_payload_eligible=True,
                ),
            )
        ),
        lambda: CandidateIssueCommentPayload(
            artifact_kind="issue_comment",
            review_target=_target(),
            body="ReviewGraph dry-run candidate\n",
            visible_body_hash="sha256:visible",
            findings_hash="sha256:findings",
            item_fingerprints=("fp-1",),
            redaction_status=RedactionStatus(redacted=False, replacement_count=0),
        ),
        lambda: CandidateIssueCommentPayload(
            artifact_kind=ArtifactKind.ISSUE_COMMENT,
            review_target=object(),
            body="ReviewGraph dry-run candidate\n",
            visible_body_hash="sha256:visible",
            findings_hash="sha256:findings",
            item_fingerprints=("fp-1",),
            redaction_status=RedactionStatus(redacted=False, replacement_count=0),
        ),
        lambda: CandidateIssueCommentPayload(
            artifact_kind=ArtifactKind.ISSUE_COMMENT,
            review_target=_target(),
            body="",
            visible_body_hash="sha256:visible",
            findings_hash="sha256:findings",
            item_fingerprints=("fp-1",),
            redaction_status=RedactionStatus(redacted=False, replacement_count=0),
        ),
        lambda: CandidateIssueCommentPayload(
            artifact_kind=ArtifactKind.ISSUE_COMMENT,
            review_target=_target(),
            body="ReviewGraph dry-run candidate\n",
            visible_body_hash="visible",
            findings_hash="sha256:findings",
            item_fingerprints=("fp-1",),
            redaction_status=RedactionStatus(redacted=False, replacement_count=0),
        ),
        lambda: CandidateIssueCommentPayload(
            artifact_kind=ArtifactKind.ISSUE_COMMENT,
            review_target=_target(),
            body="ReviewGraph dry-run candidate\n",
            visible_body_hash="sha256:visible",
            findings_hash="sha256:findings",
            item_fingerprints=["fp-1"],
            redaction_status=RedactionStatus(redacted=False, replacement_count=0),
        ),
        lambda: ActorPermissionGateResult(GateStatus.PASS, None, "write", "2026-05-06T01:00:00Z"),
        lambda: ActorPermissionGateResult("pass", "reviewgraph-bot", "write", "2026-05-06T01:00:00Z"),
        lambda: ActorPermissionGateResult(GateStatus.FAIL, "", None, None),
        lambda: PostInteractionGateResult(GateStatus.PASS, False),
        lambda: PostInteractionGateResult("pass", True),
        lambda: PayloadValidationResult(GateStatus.PASS, None, "sha256:target"),
        lambda: PayloadValidationResult("pass", "sha256:payload", "sha256:target"),
        lambda: PayloadValidationResult(GateStatus.FAIL, "payload", None),
        lambda: PayloadValidationResult(GateStatus.FAIL, None, None),
        lambda: PayloadValidationResult(GateStatus.FAIL, None, None, "unknown_code"),
        lambda: PayloadValidationResult(
            GateStatus.PASS,
            "sha256:payload",
            "sha256:target",
            PayloadValidationReasonCode.WRONG_ENDPOINT,
        ),
        lambda: MarkerReconciliationResult(GateStatus.PASS, None),
        lambda: MarkerReconciliationResult("pass", "reviewgraph-bot"),
        lambda: MarkerReconciliationResult(GateStatus.FAIL, "", reason="failed"),
        lambda: FinalizationStatus(FinalizationState.FINALIZED, None, "sha256:target"),
        lambda: FinalizationStatus("finalized", "sha256:payload", "sha256:target"),
        lambda: FinalizationStatus(FinalizationState.FAILED_CLOSED, "payload", None),
        lambda: ApprovalDecision(
            approved=True,
            approved_item_ids=["finding-1"],
            approved_final_payload_hash="sha256:full",
            approved_review_target_hash=_target().target_hash(),
            approved_review_target=_target(),
            approved_github_actor="reviewgraph-bot",
            approved_permission="write",
            approved_permission_checked_at="2026-05-06T01:00:00Z",
            include_public_verdict=False,
            approved_by="local-user",
            timestamp="2026-05-06T01:01:00Z",
        ),
        lambda: ApprovalDecision(
            approved=True,
            approved_item_ids=("finding-1",),
            approved_final_payload_hash="sha256:full",
            approved_review_target_hash="sha256:not-target",
            approved_review_target=_target(),
            approved_github_actor="reviewgraph-bot",
            approved_permission="write",
            approved_permission_checked_at="2026-05-06T01:00:00Z",
            include_public_verdict=False,
            approved_by="local-user",
            timestamp="2026-05-06T01:01:00Z",
        ),
        lambda: ApprovalDecision(
            approved=True,
            approved_item_ids=(),
            approved_final_payload_hash="sha256:full",
            approved_review_target_hash=_target().target_hash(),
            approved_review_target=_target(),
            approved_github_actor="reviewgraph-bot",
            approved_permission="write",
            approved_permission_checked_at="2026-05-06T01:00:00Z",
            include_public_verdict=False,
            approved_by="local-user",
            timestamp="2026-05-06T01:01:00Z",
        ),
        lambda: GitHubWriterResult(
            status="not_called",
            artifact_kind=ArtifactKind.ISSUE_COMMENT,
            target_hash=_target().target_hash(),
            payload_hash="sha256:full",
        ),
        lambda: GitHubWriterResult(
            status=WriterStatus.NOT_CALLED,
            artifact_kind="issue_comment",
            target_hash=_target().target_hash(),
            payload_hash="sha256:full",
        ),
        lambda: GitHubWriterResult(
            status=WriterStatus.NOT_CALLED,
            artifact_kind=ArtifactKind.ISSUE_COMMENT,
            target_hash="target",
            payload_hash="sha256:full",
        ),
        lambda: GitHubWriterResult(
            status=WriterStatus.POSTED,
            artifact_kind=ArtifactKind.ISSUE_COMMENT,
            target_hash=_target().target_hash(),
            payload_hash="sha256:full",
        ),
        lambda: GitHubWriterResult(
            status=WriterStatus.FAILED,
            artifact_kind=ArtifactKind.ISSUE_COMMENT,
            target_hash=_target().target_hash(),
            payload_hash="sha256:full",
        ),
    ],
)
def test_side_effect_contracts_reject_invalid_values(build: object) -> None:
    with pytest.raises(ValueError):
        build()


def test_review_state_can_represent_safe_default_contract_state() -> None:
    state = _review_state()

    assert state.run_mode == RunMode.DRY_RUN
    assert state.post_enabled is False
    assert state.approval is None
    assert state.writer_result is None
    assert state.stage_queue == [
        ReviewStage.INITIAL_TRIAGE,
        ReviewStage.SPECIALIZED_REVIEW,
        ReviewStage.LOGIC_REVIEW,
    ]


def test_review_config_agents_mapping_is_immutable() -> None:
    config = ReviewConfig(
        agents={
            "correctness": ReviewerAgentConfig(
                name="correctness",
                description="Checks correctness.",
                stages=(ReviewStage.INITIAL_TRIAGE,),
                triggers=ReviewerTriggers(always=True),
            )
        }
    )

    with pytest.raises(TypeError):
        config.agents["security"] = ReviewerAgentConfig(
            name="security",
            description="Checks security.",
            stages=(ReviewStage.SPECIALIZED_REVIEW,),
            triggers=ReviewerTriggers(paths=("src/auth/*",)),
        )


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("always", "yes"),
        ("paths", ["src/*"]),
        ("paths", ("",)),
        ("labels", ["backend"]),
        ("diff_patterns", [".*migration.*"]),
        ("conversation_patterns", ["ambiguous"]),
        ("risk_min", "medium"),
        ("max_files", False),
        ("max_files", 0),
        ("changed_lines_min", -1),
        ("changed_files_min", True),
    ],
)
def test_reviewer_triggers_reject_invalid_contract_values(field_name: str, bad_value: object) -> None:
    kwargs: dict[str, object] = {"always": True}
    kwargs[field_name] = bad_value

    with pytest.raises(ValueError):
        ReviewerTriggers(**kwargs)  # type: ignore[arg-type]


def test_reviewer_triggers_reject_empty_noop_contract() -> None:
    with pytest.raises(ValueError, match="selector or gate"):
        ReviewerTriggers()


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("name", ""),
        ("description", ""),
        ("stages", []),
        ("stages", (ReviewStage.INITIAL_TRIAGE, ReviewStage.INITIAL_TRIAGE)),
        ("stages", ("initial_triage",)),
        ("triggers", {"always": True}),
        ("required", 1),
        ("verdict_power", "approve"),
        ("capabilities", ["diff_context"]),
        ("capabilities", ()),
        ("capabilities", ("diff_context", "diff_context")),
        ("capabilities", ("read_repo",)),
        ("model", ""),
        ("context", {"prompt": "review carefully"}),
    ],
)
def test_reviewer_agent_config_rejects_invalid_contract_values(field_name: str, bad_value: object) -> None:
    kwargs: dict[str, object] = {
        "name": "correctness",
        "description": "Checks correctness.",
        "stages": (ReviewStage.INITIAL_TRIAGE,),
        "triggers": ReviewerTriggers(always=True),
    }
    kwargs[field_name] = bad_value

    with pytest.raises(ValueError):
        ReviewerAgentConfig(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "agents",
    [
        {"": ReviewerAgentConfig("correctness", None, (ReviewStage.INITIAL_TRIAGE,), ReviewerTriggers(always=True))},
        {"correctness": object()},
        {"logic": ReviewerAgentConfig("correctness", None, (ReviewStage.INITIAL_TRIAGE,), ReviewerTriggers(always=True))},
    ],
)
def test_review_config_rejects_invalid_agent_mapping(
    agents: dict[str, ReviewerAgentConfig | object]
) -> None:
    with pytest.raises(ValueError):
        ReviewConfig(agents=agents)  # type: ignore[arg-type]


def test_review_config_model_allows_empty_agents_for_empty_graph_initialization() -> None:
    assert ReviewConfig(agents={}).agents == {}


def _raw_finding() -> dict[str, object]:
    return {
        "id": "raw-1",
        "severity": "warning",
        "confidence": "high",
        "path": "src/cache.py",
        "line": 12,
        "title": "Cache miss returns stale data",
        "rationale": "The branch returns stale data.",
        "evidence": "Changed line 12 returns stale data.",
    }


def _run_key() -> ReviewerRunKey:
    return ReviewerRunKey(
        target_hash="sha256:target",
        config_hash="sha256:config",
        stage=ReviewStage.LOGIC_REVIEW,
        reviewer="logic",
    )


def _target() -> ReviewTarget:
    return ReviewTarget(
        owner_repo="acme/widgets",
        pr_number=42,
        base_sha="base123",
        head_sha="head456",
        merge_base_sha="merge789",
        diff_basis="merge_base",
    )


def _final_payload(
    *,
    target: ReviewTarget | None = None,
    fingerprints: tuple[str, ...] = ("fp-1",),
    redaction: RedactionStatus | None = None,
) -> FinalIssueCommentPayload:
    review_target = target or _target()
    visible_body = "Final ReviewGraph payload\n"
    marker_findings_hash = findings_hash(fingerprints)
    marker_line = (
        "<!-- reviewgraph:v1 run_id=run-1 "
        f"target={review_target.target_hash()} "
        f"payload={marker_payload_hash(visible_body)} "
        f"findings={marker_findings_hash} -->"
    )
    body = f"{visible_body}{marker_line}\n"
    return FinalIssueCommentPayload(
        artifact_kind=ArtifactKind.ISSUE_COMMENT,
        review_target=review_target,
        body=body,
        marker_line=marker_line,
        marker_run_id="run-1",
        marker_target_hash=review_target.target_hash(),
        marker_payload_hash=marker_payload_hash(visible_body),
        marker_findings_hash=marker_findings_hash,
        visible_body_hash=visible_body_hash(body),
        final_payload_hash=final_payload_hash(body),
        findings_hash=marker_findings_hash,
        item_fingerprints=fingerprints,
        redaction_status=redaction or RedactionStatus(redacted=False, replacement_count=0),
    )


def _review_state() -> ReviewState:
    target = _target()
    config = ReviewConfig(
        agents={
            "correctness": ReviewerAgentConfig(
                name="correctness",
                description="Checks correctness.",
                stages=(ReviewStage.INITIAL_TRIAGE,),
                triggers=ReviewerTriggers(always=True),
            )
        }
    )
    return ReviewState(
        run_id="run-1",
        run_mode=RunMode.DRY_RUN,
        post_enabled=False,
        pr_ref="fixture:basic-pr",
        review_target=target,
        posting_target=None,
        pr=None,
        conversation_memory=None,
        read_gaps=[],
        config=config,
        config_hash="sha256:config",
        stage_queue=[ReviewStage.INITIAL_TRIAGE, ReviewStage.SPECIALIZED_REVIEW, ReviewStage.LOGIC_REVIEW],
        active_stage=None,
        suspended_stage=None,
        completed_stages=[],
        risk=None,
        selected_reviewers=[],
        reviewer_run_keys=[],
        reviewer_run_status={},
        reviewer_results=[],
        context_budget=ContextBudget(
            max_changed_files=10,
            max_patch_bytes=1000,
            max_memory_bytes=1000,
            max_reviewers=3,
            max_live_calls=0,
        ),
        redaction_status=None,
        findings=[],
        local_notes=[],
        suggested_replies=[],
        suppressed_outputs=[],
        clarification_requests=[],
        pending_clarification_ids=[],
        ready_clarification_ids=[],
        active_clarification_id=None,
        clarifications=[],
        clarification_status={},
        ranked_findings=[],
        local_verdict=None,
        rendered_markdown=None,
        posting_plan=PostingPlan(items=()),
        post_interaction_gate=None,
        actor_permission_gate=None,
        payload_validation=None,
        marker_reconciliation=None,
        finalization_status=None,
        candidate_github_payload=None,
        final_github_payload=None,
        final_payload_hash=None,
        approval=None,
        writer_result=None,
        errors=[GraphError(code="dry_run", message="No side effects")],
    )


def _state_graph_fields() -> tuple[str, ...]:
    text = Path("docs/architecture/state-graph.md").read_text()
    block = re.search(r"class ReviewState\(TypedDict\):\n(?P<body>.*?)\n```", text, re.S)
    assert block
    names: list[str] = []
    for line in block.group("body").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        names.append(stripped.split(":", 1)[0])
    return tuple(names)


def _contains_any(annotation: object) -> bool:
    if annotation is Any:
        return True
    return any(_contains_any(arg) for arg in get_args(annotation))
