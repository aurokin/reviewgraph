from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from reviewgraph.approval import build_approval_decision, build_approval_proof
from reviewgraph.final_payload import build_approved_final_issue_comment
from reviewgraph.finalization import (
    ApprovedItemDescriptor,
    FinalizeGithubPayloadResult,
    TargetFreshnessProbeResult,
    evaluate_writer_release_preflight,
    finalize_github_payload,
)
from reviewgraph.markers import (
    MarkerCommentPage,
    PaginatedMarkerComment,
    build_final_issue_comment_payload,
    reconcile_paginated_trusted_markers,
)
from reviewgraph.models import (
    ApprovalDecision,
    ArtifactKind,
    ClassifiedFinding,
    Confidence,
    FinalizationState,
    GateStatus,
    GitHubWriterResult,
    MarkerReconciliationStatus,
    OutputClassification,
    PostingDestination,
    PostingPlan,
    PostingPlanItem,
    RedactionStatus,
    ReviewTarget,
    RunMode,
    Severity,
    WriterStatus,
)
from reviewgraph.permissions import ActorPermissionProbeResult, evaluate_actor_permission_gate, issue_comment_endpoint
from reviewgraph.post_interaction import (
    NON_INTERACTIVE_POST_MODE_ERROR_CODE,
    PostModeInteractionContext,
    evaluate_post_mode_interaction_gate,
)
from reviewgraph.posting import build_candidate_issue_comment_payload, build_posting_plan
from reviewgraph.writer_fake import FakeIssueCommentWriter, build_finalized_issue_comment_writer_input


EVALUATED_AT = "2026-05-07T00:05:00Z"
CHECKED_AT = "2026-05-07T00:04:00Z"
APPROVED_AT = "2026-05-07T00:04:30Z"
RUN_ID = "run-123"


@dataclass(frozen=True)
class FakePostHarnessResult:
    json_data: dict[str, Any]
    writer: FakeIssueCommentWriter
    finalization: FinalizeGithubPayloadResult | None = None
    writer_result: GitHubWriterResult | None = None

    @property
    def writer_call_count(self) -> int:
        return self.writer.call_count


class _StaticMarkerTransport:
    def __init__(self, body: str, *, author: str = "reviewgraph-bot") -> None:
        self.body = body
        self.author = author

    def get_issue_comments_page(
        self,
        owner_repo: str,
        pr_number: int,
        cursor: object | None,
        timeout_seconds: int,
    ) -> MarkerCommentPage:
        if cursor is not None:
            return MarkerCommentPage(comments=(), completed=True, request_id="REQ-static")
        return MarkerCommentPage(
            comments=(
                PaginatedMarkerComment(
                    comment_id="existing-conflict",
                    body=self.body,
                    author_login=self.author,
                    author_type="Bot",
                    source_provider="github",
                ),
            ),
            completed=True,
            request_id="REQ-static",
        )


def run_fixture_fake_post_attempt(
    *,
    case: str = "approved",
    writer: FakeIssueCommentWriter | None = None,
) -> FakePostHarnessResult:
    fake_writer = writer or FakeIssueCommentWriter(author_login="reviewgraph-bot")
    writer_call_count_before = fake_writer.call_count
    graph_trace = ["render_review"]
    if case == "dry_run":
        graph_trace.append("post_or_emit")
        return _result(fake_writer, graph_trace, writer_call_count_before=writer_call_count_before, post_or_emit_reason="dry_run")

    graph_trace.append("post_mode_interaction_gate")
    interaction = evaluate_post_mode_interaction_gate(
        PostModeInteractionContext(
            run_mode=RunMode.POST,
            interactive=case != "non_interactive",
            reason="harness",
        )
    )
    if interaction.status != GateStatus.PASS:
        return _result(
            fake_writer,
            graph_trace,
            writer_call_count_before=writer_call_count_before,
            post_interaction_gate=_gate_json(interaction.status, interaction.reason),
            errors=[{"code": NON_INTERACTIVE_POST_MODE_ERROR_CODE, "message": interaction.reason, "retryable": False}],
            post_or_emit_reason="non_interactive_post_mode",
        )

    graph_trace.append("approval_gate")
    target = _target()
    finding = _finding()
    plan = build_posting_plan(findings=(finding,))
    candidate = build_candidate_issue_comment_payload(review_target=target, posting_plan=plan, findings=(finding,))
    approval_result: object | None = _approval(plan=plan, finding=finding, target=target, candidate=candidate)
    if case == "missing_approval":
        approval_result = None
    elif case == "rejected_approval":
        approval_result = replace(approval_result, approved=False, approved_item_ids=())
    elif case == "empty_approval":
        proof = build_approval_proof(
            approved_item_ids=(),
            review_target=target,
            posting_plan=plan,
            findings=(finding,),
            candidate_payload=candidate,
            run_id=RUN_ID,
            approved_by="local-user",
            timestamp=APPROVED_AT,
        )
        approval_result = build_approval_decision(proof=proof, actor_permission_gate=_actor_gate(target=target))
    elif case == "non_public_approval":
        plan = PostingPlan(items=(PostingPlanItem("note-1", "local_note", PostingDestination.LOCAL_ONLY, False),))
        approval_result = replace(approval_result, approved_item_ids=("note-1",))

    graph_trace.append("writer_release_preflight")
    writer_release = evaluate_writer_release_preflight(
        post_enabled=True,
        approval_result=approval_result,
        posting_plan=plan,
        current_items_by_id=_descriptors(plan),
    )
    if writer_release.status != GateStatus.PASS:
        graph_trace.append("post_or_emit")
        return _result(
            fake_writer,
            graph_trace,
            writer_call_count_before=writer_call_count_before,
            post_interaction_gate=_gate_json(GateStatus.PASS, None),
            writer_release_preflight=_writer_release_json(writer_release),
            post_or_emit_reason=writer_release.reason_code.value if writer_release.reason_code is not None else "writer_release_failed",
        )
    if not isinstance(approval_result, ApprovalDecision):
        raise AssertionError("passing writer release preflight requires approval")

    graph_trace.append("finalize_github_payload")
    selected_items = tuple(item for item in plan.items if item.id in approval_result.approved_item_ids)

    def final_payload_builder():
        payload = build_approved_final_issue_comment(
            run_id=RUN_ID,
            review_target=target,
            findings_by_id={finding.id: finding},
            selected_items=selected_items,
            local_verdict=None,
            include_public_verdict=False,
        ).payload
        if case == "payload_validation_failure":
            return replace(payload, marker_run_id="other-run")
        return payload

    transport = fake_writer
    if case == "marker_conflict":
        conflict = build_final_issue_comment_payload(
            run_id="run-conflict",
            review_target=target,
            visible_body="ReviewGraph approved findings\nTarget: acme/widgets#42\nHead: head456\n\nApproved findings:\n- P1 Different: Different body. (src/app.py:10)\n",
            item_fingerprints=("fp-1",),
            redaction_status=RedactionStatus(redacted=False, replacement_count=0),
        )
        transport = _StaticMarkerTransport(conflict.body)

    def marker_reconciler(payload):
        return reconcile_paginated_trusted_markers(
            transport=transport,
            owner_repo=target.owner_repo,
            pr_number=target.pr_number,
            approved_actor=approval_result.approved_github_actor,
            trusted_bot_authors=("reviewgraph-bot",),
            expected_target_hash=payload.marker_target_hash,
            expected_payload_hash=payload.marker_payload_hash,
            expected_findings_hash=payload.marker_findings_hash,
        )

    actor_probe = _actor_probe(target=target)
    if case == "actor_mismatch":
        actor_probe = _actor_probe(target=target, actor="other-bot", credential_principal="gh-user:other-bot")
    elif case == "permission_failure":
        actor_probe = _actor_probe(target=target, issue_comment_write=False, repo_permission="read")

    target_probe = _target_probe(target)
    if case == "stale_target":
        target_probe = _target_probe(replace(target, head_sha="head999"))
    elif case == "unknown_target_freshness":
        target_probe = TargetFreshnessProbeResult(current_target=None, request_id="REQ-target", unknown_retryable=True)

    finalization = finalize_github_payload(
        approval=approval_result,
        posting_plan=plan,
        approved_findings_by_id={finding.id: finding},
        current_actor_permission_probe=actor_probe,
        current_target_probe=target_probe,
        evaluated_at=EVALUATED_AT,
        final_payload_builder=final_payload_builder,
        marker_reconciler=marker_reconciler,
    )
    graph_trace.append("post_or_emit")
    writer_result = _post_or_emit(
        finalization=finalization,
        approval=approval_result,
        writer=fake_writer,
    )
    return _result(
        fake_writer,
        graph_trace,
        writer_call_count_before=writer_call_count_before,
        finalization=finalization,
        writer_result=writer_result,
        post_interaction_gate=_gate_json(GateStatus.PASS, None),
        writer_release_preflight=_writer_release_json(writer_release),
        post_or_emit_reason=_post_or_emit_reason(finalization, writer_result),
    )


def _post_or_emit(
    *,
    finalization: FinalizeGithubPayloadResult,
    approval: ApprovalDecision,
    writer: FakeIssueCommentWriter,
) -> GitHubWriterResult | None:
    marker = finalization.marker_reconciliation
    if marker is not None and marker.status == MarkerReconciliationStatus.RECONCILED_EXISTING:
        return GitHubWriterResult(
            status=WriterStatus.RECONCILED,
            artifact_kind=ArtifactKind.ISSUE_COMMENT,
            target_hash=approval.approved_review_target_hash,
            payload_hash=approval.approved_final_payload_hash,
            comment_id=marker.existing_comment_id,
        )
    if (
        finalization.finalization_status.state != FinalizationState.FINALIZED
        or marker is None
        or marker.status != MarkerReconciliationStatus.SAFE_TO_POST
        or not finalization.writer_input_released
        or finalization.final_payload is None
    ):
        return None
    writer_input = build_finalized_issue_comment_writer_input(
        finalization=finalization,
        approved_actor=approval.approved_github_actor,
        run_id=RUN_ID,
    )
    return writer.post_issue_comment(writer_input)


def _post_or_emit_reason(
    finalization: FinalizeGithubPayloadResult | None,
    writer_result: GitHubWriterResult | None,
) -> str:
    if writer_result is not None:
        return writer_result.status.value
    if finalization is None:
        return "not_finalized"
    if finalization.marker_reconciliation is not None:
        return finalization.marker_reconciliation.reason_code.value
    if finalization.finalization_status.reason_code is not None:
        return finalization.finalization_status.reason_code.value
    return "not_called"


def _result(
    writer: FakeIssueCommentWriter,
    graph_trace: list[str],
    *,
    writer_call_count_before: int,
    finalization: FinalizeGithubPayloadResult | None = None,
    writer_result: GitHubWriterResult | None = None,
    post_interaction_gate: dict[str, object] | None = None,
    writer_release_preflight: dict[str, object] | None = None,
    post_or_emit_reason: str,
    errors: list[dict[str, object]] | None = None,
) -> FakePostHarnessResult:
    writer_call_delta = writer.call_count - writer_call_count_before
    json_data: dict[str, Any] = {
        "run_mode": "post" if "post_mode_interaction_gate" in graph_trace else "dry_run",
        "graph_trace": list(graph_trace),
        "side_effects": {"writer_called": writer_call_delta > 0, "writer_call_count": writer_call_delta},
        "post_or_emit": {"reason_code": post_or_emit_reason},
        "errors": errors or [],
    }
    if post_interaction_gate is not None:
        json_data["post_interaction_gate"] = post_interaction_gate
    if writer_release_preflight is not None:
        json_data["writer_release_preflight"] = writer_release_preflight
    if finalization is not None:
        json_data["finalization_status"] = {
            "state": finalization.finalization_status.state.value,
            "reason_code": (
                finalization.finalization_status.reason_code.value
                if finalization.finalization_status.reason_code is not None
                else None
            ),
        }
        json_data["final_payload_hash"] = finalization.finalization_status.final_payload_hash
        json_data["payload_validation"] = (
            {"status": finalization.payload_validation.status.value}
            if finalization.payload_validation is not None
            else None
        )
        json_data["marker_reconciliation"] = (
            {
                "status": finalization.marker_reconciliation.status.value,
                "reason_code": finalization.marker_reconciliation.reason_code.value,
                "existing_comment_id": finalization.marker_reconciliation.existing_comment_id,
            }
            if finalization.marker_reconciliation is not None
            else None
        )
    if writer_result is not None:
        json_data["writer_result"] = {
            "status": writer_result.status.value,
            "artifact_kind": writer_result.artifact_kind.value,
            "target_hash": writer_result.target_hash,
            "payload_hash": writer_result.payload_hash,
            "comment_id": writer_result.comment_id,
            "error": writer_result.error,
        }
    return FakePostHarnessResult(json_data=json_data, writer=writer, finalization=finalization, writer_result=writer_result)


def _gate_json(status: GateStatus, reason: str | None) -> dict[str, object]:
    return {"status": status.value, "reason": reason}


def _writer_release_json(result) -> dict[str, object]:
    return {
        "status": result.status.value,
        "reason_code": result.reason_code.value if result.reason_code is not None else None,
        "writer_input_released": result.writer_input_released,
        "eligible_for_finalization": result.eligible_for_finalization,
        "approved_item_ids": list(result.approved_item_ids),
    }


def _approval(*, plan, finding, target, candidate) -> ApprovalDecision:
    proof = build_approval_proof(
        approved_item_ids=("finding-1",),
        review_target=target,
        posting_plan=plan,
        findings=(finding,),
        candidate_payload=candidate,
        run_id=RUN_ID,
        approved_by="local-user",
        timestamp=APPROVED_AT,
    )
    decision = build_approval_decision(proof=proof, actor_permission_gate=_actor_gate(target=target))
    if decision.approval is None:
        raise AssertionError("expected approval fixture to pass")
    return decision.approval


def _actor_gate(*, target: ReviewTarget):
    return evaluate_actor_permission_gate(_actor_probe(target=target), expected_target=target, evaluated_at=EVALUATED_AT)


def _actor_probe(target: ReviewTarget, **updates: object) -> ActorPermissionProbeResult:
    values = {
        "actor": "reviewgraph-bot",
        "credential_principal": "gh-user:reviewgraph-bot",
        "credential_source": "pat",
        "repo_permission": "write",
        "issue_comment_write": True,
        "check_method": "fake_issue_comment_permission_probe",
        "endpoint_method": "POST",
        "checked_target": target,
        "checked_at": CHECKED_AT,
        "endpoint": issue_comment_endpoint(target),
        "endpoint_kind": "issue_comment",
        "request_id": "REQ-actor",
    }
    values.update(updates)
    return ActorPermissionProbeResult(**values)


def _target_probe(target: ReviewTarget) -> TargetFreshnessProbeResult:
    return TargetFreshnessProbeResult(
        current_target=target,
        checked_at=EVALUATED_AT,
        check_method="fake_pull_request_target_probe",
        request_id="REQ-target",
    )


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


def _target() -> ReviewTarget:
    return ReviewTarget("acme/widgets", 42, "base123", "head456", "merge789", "merge_base")


def _finding() -> ClassifiedFinding:
    return ClassifiedFinding(
        id="finding-1",
        source_reviewer="correctness",
        source_stage="initial_triage",
        title="Finding",
        body="Body.",
        evidence="changed line 10",
        path="src/app.py",
        line=10,
        priority=1,
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        fingerprint="fp-1",
        classification=OutputClassification.POSTABLE_FINDING,
    )
