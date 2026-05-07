from dataclasses import replace
from types import SimpleNamespace

import pytest

from reviewgraph.approval import build_approval_decision, build_approval_proof
from reviewgraph.hashing import visible_body_hash
from reviewgraph.finalization import (
    ApprovedItemDescriptor,
    TargetFreshnessProbeResult,
    evaluate_writer_release_preflight,
    finalize_github_payload,
)
from reviewgraph.models import (
    ApprovalDecisionBuildReasonCode,
    ApprovalProofReasonCode,
    ClassifiedFinding,
    Confidence,
    GateStatus,
    LocalNote,
    OutputClassification,
    PostingDestination,
    PostingPlan,
    PostingPlanItem,
    ReviewTarget,
    Severity,
    SuggestedReply,
    WriterReleaseItemReasonCode,
    WriterReleasePreflightReasonCode,
)
from reviewgraph.permissions import ActorPermissionProbeResult, issue_comment_endpoint
from reviewgraph.posting import build_candidate_issue_comment_payload, build_posting_plan
from reviewgraph.runner import run_fixture_dry_run


EVALUATED_AT = "2026-05-07T00:05:00Z"
CHECKED_AT = "2026-05-07T00:04:00Z"


def test_empty_approval_proof_propagates_nested_reason_without_writer_release() -> None:
    proof = build_approval_proof(
        approved_item_ids=(),
        review_target=_target(),
        posting_plan=_plan(),
        findings=(_finding(),),
        candidate_payload=_candidate(),
        run_id="run-123",
        approved_by="local-user",
        timestamp="2026-05-07T00:03:30Z",
    )
    build_result = build_approval_decision(proof=proof, actor_permission_gate=_actor_gate())

    result = evaluate_writer_release_preflight(
        post_enabled=True,
        approval_result=build_result,
        posting_plan=_plan(),
        current_items_by_id=_descriptors(_plan()),
    )

    assert build_result.reason_code == ApprovalDecisionBuildReasonCode.APPROVAL_PROOF_FAILED
    assert build_result.approval_proof_reason_code == ApprovalProofReasonCode.EMPTY_APPROVAL
    assert result.status == GateStatus.FAIL
    assert result.reason_code == WriterReleasePreflightReasonCode.APPROVAL_BUILD_FAILED
    assert result.nested_reason_code == ApprovalDecisionBuildReasonCode.APPROVAL_PROOF_FAILED
    assert result.nested_approval_proof_reason_code == ApprovalProofReasonCode.EMPTY_APPROVAL
    assert result.writer_input_released is False
    assert result.final_payload_hash is None
    assert result.writer_result is None


@pytest.mark.parametrize(
    ("post_enabled", "approval_result", "reason_code"),
    [
        (False, None, WriterReleasePreflightReasonCode.POST_DISABLED),
        (True, None, WriterReleasePreflightReasonCode.MISSING_APPROVAL),
        (True, "rejected", WriterReleasePreflightReasonCode.REJECTED_APPROVAL),
    ],
)
def test_writer_release_preflight_blocks_post_disabled_missing_and_rejected_approval(
    post_enabled: bool,
    approval_result: object,
    reason_code: WriterReleasePreflightReasonCode,
) -> None:
    approval = _approval()
    if approval_result == "rejected":
        approval_result = replace(approval, approved=False, approved_item_ids=())

    result = evaluate_writer_release_preflight(
        post_enabled=post_enabled,
        approval_result=approval_result,
        posting_plan=_plan(),
        current_items_by_id=_descriptors(_plan()),
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == reason_code
    assert result.approved_item_ids == ()
    assert result.eligible_for_finalization is False
    assert result.writer_input_released is False


def test_writer_release_preflight_passes_public_findings_without_releasing_writer_input() -> None:
    plan = build_posting_plan(
        findings=(_finding(),),
        suggested_replies=[SuggestedReply("reply-1", "comment-1", "Draft reply must stay local.")],
    )
    candidate = build_candidate_issue_comment_payload(
        review_target=_target(),
        posting_plan=plan,
        findings=(_finding(),),
    )
    proof = build_approval_proof(
        approved_item_ids=("finding-1",),
        review_target=_target(),
        posting_plan=plan,
        findings=(_finding(),),
        candidate_payload=candidate,
        run_id="run-123",
        approved_by="local-user",
        timestamp="2026-05-07T00:03:30Z",
    )
    decision = build_approval_decision(proof=proof, actor_permission_gate=_actor_gate())
    assert decision.approval is not None

    result = evaluate_writer_release_preflight(
        post_enabled=True,
        approval_result=decision.approval,
        posting_plan=plan,
        current_items_by_id=_descriptors(plan),
    )

    assert result.status == GateStatus.PASS
    assert result.eligible_for_finalization is True
    assert result.writer_input_released is False
    assert result.approved_item_ids == ("finding-1",)
    assert result.reason_code is None

    approved_visible_body = (
        "ReviewGraph approved findings\n"
        "Target: acme/widgets#42\n"
        "Head: head456\n\n"
        "Approved findings:\n"
        "- P1 Cache miss returns stale data: The new branch returns stale data when the cache misses. (src/cache.py:12)\n"
    )
    assert proof.status == GateStatus.PASS
    assert proof.approved_item_ids == ("finding-1",)
    assert proof.final_visible_body_hash == visible_body_hash(approved_visible_body)
    assert "Draft reply must stay local." not in candidate.body


def test_writer_release_preflight_rejects_unknown_approved_id_before_finalization() -> None:
    result = evaluate_writer_release_preflight(
        post_enabled=True,
        approval_result=replace(_approval(), approved_item_ids=("missing-finding",)),
        posting_plan=_plan(),
        current_items_by_id=_descriptors(_plan()),
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == WriterReleasePreflightReasonCode.UNKNOWN_APPROVED_ID
    assert result.writer_input_released is False
    assert result.item_diagnostics
    assert result.item_diagnostics[0].item_id == "missing-finding"
    assert result.item_diagnostics[0].reason_code == WriterReleaseItemReasonCode.MISSING_CURRENT_ITEM


def test_writer_release_preflight_prioritizes_unknown_id_over_non_public_items() -> None:
    plan = PostingPlan(
        items=(
            PostingPlanItem("note-1", "local_note", PostingDestination.LOCAL_ONLY, False),
        )
    )

    result = evaluate_writer_release_preflight(
        post_enabled=True,
        approval_result=replace(_approval(), approved_item_ids=("missing-finding", "note-1")),
        posting_plan=plan,
        current_items_by_id=_descriptors(plan),
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == WriterReleasePreflightReasonCode.UNKNOWN_APPROVED_ID
    assert [item.item_id for item in result.item_diagnostics] == ["missing-finding", "note-1"]


def test_writer_release_preflight_rejects_duplicate_approved_item_ids() -> None:
    result = evaluate_writer_release_preflight(
        post_enabled=True,
        approval_result=replace(_approval(), approved_item_ids=("finding-1", "finding-1")),
        posting_plan=_plan(),
        current_items_by_id=_descriptors(_plan()),
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == WriterReleasePreflightReasonCode.DUPLICATE_APPROVED_ITEM
    assert result.writer_input_released is False
    assert result.item_diagnostics == ()


def test_writer_release_preflight_rejects_duplicate_approved_fingerprints() -> None:
    plan = PostingPlan(
        items=(
            PostingPlanItem(
                "finding-1",
                OutputClassification.POSTABLE_FINDING.value,
                PostingDestination.REVIEW_BODY_ITEM,
                True,
                "fp-duplicate",
            ),
            PostingPlanItem(
                "finding-2",
                OutputClassification.POSTABLE_FINDING.value,
                PostingDestination.REVIEW_BODY_ITEM,
                True,
                "fp-duplicate",
            ),
        )
    )

    result = evaluate_writer_release_preflight(
        post_enabled=True,
        approval_result=replace(_approval(), approved_item_ids=("finding-1", "finding-2")),
        posting_plan=plan,
        current_items_by_id=_descriptors(plan),
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == WriterReleasePreflightReasonCode.DUPLICATE_APPROVED_FINGERPRINT
    assert result.item_diagnostics == ()
    assert result.writer_input_released is False


def test_writer_release_preflight_prioritizes_duplicate_fingerprints_over_item_diagnostics() -> None:
    plan = PostingPlan(
        items=(
            PostingPlanItem(
                "finding-1",
                OutputClassification.POSTABLE_FINDING.value,
                PostingDestination.REVIEW_BODY_ITEM,
                True,
                "fp-duplicate",
            ),
            PostingPlanItem(
                "finding-2",
                OutputClassification.POSTABLE_FINDING.value,
                PostingDestination.REVIEW_BODY_ITEM,
                True,
                "fp-duplicate",
            ),
            PostingPlanItem("note-1", "local_note", PostingDestination.LOCAL_ONLY, False),
        )
    )

    result = evaluate_writer_release_preflight(
        post_enabled=True,
        approval_result=replace(_approval(), approved_item_ids=("finding-1", "finding-2", "missing-finding", "note-1")),
        posting_plan=plan,
        current_items_by_id=_descriptors(plan),
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == WriterReleasePreflightReasonCode.DUPLICATE_APPROVED_FINGERPRINT
    assert result.item_diagnostics == ()
    assert result.writer_input_released is False


@pytest.mark.parametrize(
    "plan",
    [
        PostingPlan(items=(PostingPlanItem("note-1", "local_note", PostingDestination.LOCAL_ONLY, False),)),
        PostingPlan(items=(PostingPlanItem("reply-1", "suggested_reply", PostingDestination.SUGGESTED_REPLY, False),)),
        PostingPlan(items=(PostingPlanItem("suppressed-1", "non_finding", PostingDestination.LOCAL_ONLY, False),)),
        PostingPlan(items=(PostingPlanItem("clarify-1", "clarification_request", PostingDestination.LOCAL_ONLY, False),)),
        PostingPlan(items=(PostingPlanItem("finding-1", "postable_finding", PostingDestination.INLINE_CANDIDATE, False, "fp-1"),)),
        PostingPlan(items=(PostingPlanItem("summary", "summary", PostingDestination.TOP_LEVEL_SUMMARY_ITEM, True),)),
        PostingPlan(items=(PostingPlanItem("finding-1", "postable_finding", PostingDestination.REVIEW_BODY_ITEM, True, None),)),
    ],
)
def test_non_public_approved_ids_fail_before_finalization_or_writer_release(plan: PostingPlan) -> None:
    approved_id = plan.items[0].id
    approval = replace(_approval(), approved_item_ids=(approved_id,))

    result = evaluate_writer_release_preflight(
        post_enabled=True,
        approval_result=approval,
        posting_plan=plan,
        current_items_by_id=_descriptors(plan),
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == WriterReleasePreflightReasonCode.NON_PUBLIC_APPROVED_ITEM
    assert result.writer_input_released is False
    assert result.item_diagnostics
    assert result.item_diagnostics[0].item_id == approved_id


def test_writer_release_preflight_rejects_descriptor_drift_from_posting_plan() -> None:
    plan = PostingPlan(
        items=(PostingPlanItem("reply-1", "suggested_reply", PostingDestination.SUGGESTED_REPLY, False, "fp-1"),)
    )
    approval = replace(_approval(), approved_item_ids=("reply-1",))

    result = evaluate_writer_release_preflight(
        post_enabled=True,
        approval_result=approval,
        posting_plan=plan,
        current_items_by_id={
            "reply-1": ApprovedItemDescriptor(
                item_id="reply-1",
                source_classification=OutputClassification.POSTABLE_FINDING.value,
                destination=PostingDestination.REVIEW_BODY_ITEM,
                public_payload_eligible=True,
                has_fingerprint=True,
            )
        },
    )

    assert result.status == GateStatus.FAIL
    assert result.reason_code == WriterReleasePreflightReasonCode.NON_PUBLIC_APPROVED_ITEM
    assert result.item_diagnostics[0].destination == PostingDestination.SUGGESTED_REPLY


def test_finalization_rechecks_current_posting_plan_before_current_reads_or_payload_builder() -> None:
    calls = {"count": 0}

    def builder():
        calls["count"] += 1
        raise AssertionError("final payload builder must not be called")

    plan = PostingPlan(
        items=(PostingPlanItem("finding-1", "suggested_reply", PostingDestination.SUGGESTED_REPLY, False),)
    )
    result = finalize_github_payload(
        approval=_approval(),
        posting_plan=plan,
        approved_findings_by_id={"finding-1": SimpleNamespace(fingerprint="fp-1", classification=OutputClassification.LOCAL_NOTE)},
        current_actor_permission_probe=_actor_probe(actor=None),
        current_target_probe=TargetFreshnessProbeResult(current_target=None),
        evaluated_at=EVALUATED_AT,
        final_payload_builder=builder,
    )

    assert result.finalization_status.reason_code.value == "approval_preflight_failed"
    assert result.actor_permission_finalization_check is None
    assert result.target_freshness_check is None
    assert result.final_payload_builder_calls == 0
    assert calls["count"] == 0
    assert result.final_payload is None
    assert result.writer_input_released is False


@pytest.mark.parametrize(
    "case",
    [
        "malformed_object",
        "fingerprint_drift",
    ],
)
def test_finalization_rejects_malformed_or_drifted_current_finding_before_current_reads(
    case: str,
) -> None:
    calls = {"count": 0}

    def builder():
        calls["count"] += 1
        raise AssertionError("final payload builder must not be called")

    approved_findings_by_id = (
        {"finding-1": SimpleNamespace(fingerprint="fp-1", classification=OutputClassification.POSTABLE_FINDING)}
        if case == "malformed_object"
        else {"finding-1": replace(_finding(), fingerprint="fp-drift")}
    )

    result = finalize_github_payload(
        approval=_approval(),
        posting_plan=_plan(),
        approved_findings_by_id=approved_findings_by_id,
        current_actor_permission_probe=_actor_probe(actor=None),
        current_target_probe=TargetFreshnessProbeResult(current_target=None),
        evaluated_at=EVALUATED_AT,
        final_payload_builder=builder,
    )

    assert result.finalization_status.reason_code.value == "approval_preflight_failed"
    assert result.actor_permission_finalization_check is None
    assert result.target_freshness_check is None
    assert result.final_payload_builder_calls == 0
    assert calls["count"] == 0
    assert result.writer_input_released is False


@pytest.mark.parametrize(
    ("items", "expected_reason"),
    [
        (({"type": "local_note", "id": "note-only", "title": "Local", "body": "Keep local.", "evidence": "fixture"},), "no_public_postable_items"),
        (({"type": "suggested_reply", "id": "reply-only", "source_comment_id": "comment-1", "proposed_body": "Draft reply."},), "no_public_postable_items"),
        (({"type": "finding", "id": "finding-generic-tests", "title": "Add tests", "body": "Add tests.", "evidence": "Changed line 12.", "path": "src/cache.py", "line": 12, "severity": "suggestion", "confidence": "low"},), "no_public_postable_items"),
        (({"type": "clarification_request", "id": "clarify-intent", "question": "Is this intended?", "why_it_matters": "Mergeability depends on product intent.", "evidence_sources": ["diff"]},), "blocked_by_clarification"),
    ],
)
def test_local_only_dry_runs_expose_public_payload_preparation_reason(
    tmp_path,
    items: tuple[dict[str, object], ...],
    expected_reason: str,
) -> None:
    fixture_path = tmp_path / "local-only.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["items"] = list(items)
    fixture_path.write_text(__import__("json").dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))

    assert result.json_data["post_enabled"] is False
    assert result.json_data["side_effects"] == {"writer_called": False, "writer_call_count": 0}
    assert result.json_data["review"]["candidate_payload_preview"] is None
    assert result.json_data["public_payload_preparation"]["reason_code"] == expected_reason
    assert result.json_data["review"]["public_payload_preparation"]["reason_code"] == expected_reason
    if expected_reason == "no_public_postable_items":
        assert "No public GitHub payload was prepared because no public postable finding items are eligible." in result.markdown
    else:
        assert "no public postable finding items are eligible" not in result.markdown


def test_public_candidate_dry_run_does_not_evaluate_writer_release_preflight() -> None:
    result = run_fixture_dry_run(fixture_ref="basic-pr")

    assert "writer_release_preflight" not in result.json_data
    assert result.json_data["public_payload_preparation"]["reason_code"] == "dry_run_candidate_prepared"


def _target() -> ReviewTarget:
    return ReviewTarget("acme/widgets", 42, "base123", "head456", "merge789", "merge_base")


def _finding() -> ClassifiedFinding:
    return ClassifiedFinding(
        id="finding-1",
        source_reviewer="correctness",
        source_stage="initial_triage",
        title="Cache miss returns stale data",
        body="The new branch returns stale data when the cache misses.",
        evidence="changed line 12",
        path="src/cache.py",
        line=12,
        priority=1,
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        fingerprint="fp-1",
    )


def _plan() -> PostingPlan:
    return build_posting_plan(findings=(_finding(),))


def _candidate():
    return build_candidate_issue_comment_payload(review_target=_target(), posting_plan=_plan(), findings=(_finding(),))


def _approval():
    proof = build_approval_proof(
        approved_item_ids=("finding-1",),
        review_target=_target(),
        posting_plan=_plan(),
        findings=(_finding(),),
        candidate_payload=_candidate(),
        run_id="run-123",
        approved_by="local-user",
        timestamp="2026-05-07T00:03:30Z",
    )
    decision = build_approval_decision(proof=proof, actor_permission_gate=_actor_gate())
    assert decision.approval is not None
    return decision.approval


def _actor_gate():
    from reviewgraph.permissions import evaluate_actor_permission_gate

    return evaluate_actor_permission_gate(_actor_probe(), expected_target=_target(), evaluated_at=EVALUATED_AT)


def _actor_probe(**updates: object) -> ActorPermissionProbeResult:
    values = {
        "actor": "reviewgraph-bot",
        "credential_principal": "gh-user:reviewgraph-bot",
        "credential_source": "pat",
        "repo_permission": "write",
        "issue_comment_write": True,
        "check_method": "fake_issue_comment_permission_probe",
        "endpoint_method": "POST",
        "checked_target": _target(),
        "checked_at": CHECKED_AT,
        "endpoint": issue_comment_endpoint(_target()),
        "endpoint_kind": "issue_comment",
        "request_id": "REQ-actor",
    }
    values.update(updates)
    return ActorPermissionProbeResult(**values)


def _descriptors(plan: PostingPlan) -> dict[str, ApprovedItemDescriptor]:
    return {
        item.id: ApprovedItemDescriptor(
            item_id=item.id,
            source_classification=item.source_classification,
            destination=item.destination,
            public_payload_eligible=item.public_payload_eligible,
            has_fingerprint=bool(item.fingerprint),
        )
        for item in plan.items
    }


def _basic_fixture() -> dict[str, object]:
    fixture = __import__("json").loads(
        __import__("pathlib").Path("src/reviewgraph/fixtures_data/prs/basic-pr.json").read_text()
    )
    fixture["raw_reviewer_outputs"] = [dict(fixture["raw_reviewer_outputs"][0])]
    return fixture
