from dataclasses import replace
from pathlib import Path
import ast

import pytest

from reviewgraph.finalization import FinalizeGithubPayloadResult
from reviewgraph.markers import (
    MarkerCommentPage,
    MarkerScanTransportFailure,
    PaginatedMarkerComment,
    build_final_issue_comment_payload,
)
from reviewgraph.models import (
    ActorPermissionFinalizationCheckResult,
    ActorPermissionTransportSummary,
    ApprovalDecision,
    ArtifactKind,
    FinalizationState,
    FinalizationStatus,
    GateStatus,
    MarkerReconciliationReasonCode,
    MarkerReconciliationResult,
    MarkerReconciliationStatus,
    MarkerScanTransportSummary,
    PayloadValidationResult,
    RedactionStatus,
    ReviewTarget,
    TargetFreshnessCheckResult,
    TargetFreshnessTransportSummary,
    WriterStatus,
)
from reviewgraph.permissions import issue_comment_endpoint
from reviewgraph.writer_github import (
    GitHubIssueCommentPostResponse,
    GitHubIssueCommentPostTransportFailure,
    GitHubIssueCommentWriter,
    GitHubIssueCommentWriterOutcomeDetail,
    GitHubIssueCommentWriterReasonCode,
)
from reviewgraph.writer_input import build_finalized_issue_comment_writer_input


def test_github_writer_posts_exact_top_level_issue_comment_request() -> None:
    writer_input = _writer_input()
    transport = _PostTransport(GitHubIssueCommentPostResponse("comment-1", "reviewgraph-bot", "REQ-post"))
    writer = GitHubIssueCommentWriter(transport=transport)

    result = writer.post_issue_comment(writer_input)

    assert transport.calls == [
        {
            "owner_repo": "acme/widgets",
            "pr_number": 42,
            "body": {"body": writer_input.final_payload.body},
            "timeout_seconds": 10,
        }
    ]
    assert result.writer_result.status == WriterStatus.POSTED
    assert result.writer_result.artifact_kind == ArtifactKind.ISSUE_COMMENT
    assert result.writer_result.comment_id == "comment-1"
    assert result.outcome_detail == GitHubIssueCommentWriterOutcomeDetail.POSTED
    assert result.transport_summary.endpoint == "/repos/acme/widgets/issues/42/comments"
    assert result.transport_summary.method == "POST"
    assert result.transport_summary.post_attempt_count == 1
    assert result.transport_summary.recovery_scan_count == 0
    assert result.transport_summary.request_id == "REQ-post"
    assert writer_input.final_payload.body not in repr(result.transport_summary)


@pytest.mark.parametrize("case", ["raw_final_payload", "formal_review_like_payload"])
def test_github_writer_rejects_raw_or_formal_review_like_payloads(case: str) -> None:
    writer = GitHubIssueCommentWriter(transport=_PostTransport())
    raw_input = _payload() if case == "raw_final_payload" else {"event": "COMMENT", "body": "not supported"}

    with pytest.raises(ValueError, match="finalized issue-comment writer input"):
        writer.post_issue_comment(raw_input)  # type: ignore[arg-type]

    assert writer.transport.calls == []


def test_github_writer_validates_final_payload_before_transport() -> None:
    payload = replace(_payload(), marker_run_id="other-run")
    writer_input = _writer_input(payload=payload)
    transport = _PostTransport()
    writer = GitHubIssueCommentWriter(transport=transport)

    result = writer.post_issue_comment(writer_input)

    assert transport.calls == []
    assert result.writer_result.status == WriterStatus.FAILED
    assert result.writer_result.error == "marker_field_mismatch"
    assert result.outcome_detail == GitHubIssueCommentWriterOutcomeDetail.VALIDATION_FAILED
    assert result.transport_summary.post_attempt_count == 0


def test_github_writer_fails_posted_response_actor_mismatch_and_forbids_retry_post() -> None:
    writer_input = _writer_input()
    transport = _PostTransport(GitHubIssueCommentPostResponse("comment-1", "other-bot", "REQ-post"))
    recovery = _PagesMarkerTransport(
        {None: MarkerCommentPage(comments=(), completed=True, request_id="REQ-recovery")}
    )
    writer = GitHubIssueCommentWriter(transport=transport, recovery_marker_transport=recovery)

    first = writer.post_issue_comment(writer_input)
    second = writer.post_issue_comment(writer_input)

    assert first.writer_result.status == WriterStatus.FAILED
    assert first.outcome_detail == GitHubIssueCommentWriterOutcomeDetail.RESPONSE_ACTOR_MISMATCH
    assert first.transport_summary.post_attempt_count == 1
    assert second.writer_result.status == WriterStatus.FAILED
    assert second.outcome_detail == GitHubIssueCommentWriterOutcomeDetail.FORBIDDEN_SECOND_POST
    assert second.transport_summary.post_attempt_count == 0
    assert second.transport_summary.recovery_scan_count == 1
    assert len(transport.calls) == 1


def test_github_writer_fails_malformed_success_response_and_forbids_retry_post() -> None:
    writer_input = _writer_input()
    transport = _PostTransport(GitHubIssueCommentPostResponse(None, "reviewgraph-bot", "REQ-post"))
    recovery = _PagesMarkerTransport(
        {None: MarkerCommentPage(comments=(), completed=True, request_id="REQ-recovery")}
    )
    writer = GitHubIssueCommentWriter(transport=transport, recovery_marker_transport=recovery)

    first = writer.post_issue_comment(writer_input)
    second = writer.post_issue_comment(writer_input)

    assert first.writer_result.status == WriterStatus.FAILED
    assert first.outcome_detail == GitHubIssueCommentWriterOutcomeDetail.MALFORMED_RESPONSE
    assert second.outcome_detail == GitHubIssueCommentWriterOutcomeDetail.FORBIDDEN_SECOND_POST
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    ("reason", "retryable"),
    [
        (GitHubIssueCommentWriterReasonCode.TIMEOUT, True),
        (GitHubIssueCommentWriterReasonCode.RATE_LIMITED, True),
        (GitHubIssueCommentWriterReasonCode.FORBIDDEN, False),
        (GitHubIssueCommentWriterReasonCode.NOT_FOUND, False),
        (GitHubIssueCommentWriterReasonCode.UNAVAILABLE, True),
        (GitHubIssueCommentWriterReasonCode.MALFORMED_RESPONSE, False),
        (GitHubIssueCommentWriterReasonCode.TRANSPORT_UNKNOWN, True),
    ],
)
def test_github_writer_records_redacted_post_transport_failures(
    reason: GitHubIssueCommentWriterReasonCode,
    retryable: bool,
) -> None:
    writer_input = _writer_input()
    transport = _PostTransport(
        failure=GitHubIssueCommentPostTransportFailure(reason, request_id="REQ-failure")
    )
    writer = GitHubIssueCommentWriter(transport=transport)

    result = writer.post_issue_comment(writer_input)

    assert result.writer_result.status == WriterStatus.FAILED
    assert result.writer_result.error == reason.value
    assert result.outcome_detail == GitHubIssueCommentWriterOutcomeDetail.TRANSPORT_FAILED
    assert result.transport_summary.retryable is retryable
    assert result.transport_summary.reason_code == reason.value
    assert result.transport_summary.request_id == "REQ-failure"
    assert result.transport_summary.post_attempt_count == 1
    assert writer_input.final_payload.body not in repr(result)


def test_github_writer_drops_unsafe_request_ids_from_evidence() -> None:
    writer_input = _writer_input()
    transport = _PostTransport(GitHubIssueCommentPostResponse("comment-1", "reviewgraph-bot", "Bearer sk-prod-secret"))
    writer = GitHubIssueCommentWriter(transport=transport)

    result = writer.post_issue_comment(writer_input)

    assert result.writer_result.status == WriterStatus.POSTED
    assert result.transport_summary.request_id is None


def test_ambiguous_reason_code_enters_recovery_without_extra_flag() -> None:
    writer_input = _writer_input()
    transport = _PostTransport(
        failure=GitHubIssueCommentPostTransportFailure(
            GitHubIssueCommentWriterReasonCode.AMBIGUOUS_ACCEPTED,
            request_id="REQ-ambiguous",
        )
    )
    recovery = _PagesMarkerTransport(
        {None: MarkerCommentPage(comments=(_trusted_comment("comment-accepted", writer_input.final_payload.body),))}
    )
    writer = GitHubIssueCommentWriter(transport=transport, recovery_marker_transport=recovery)

    result = writer.post_issue_comment(writer_input)

    assert result.writer_result.status == WriterStatus.RECONCILED
    assert result.outcome_detail == GitHubIssueCommentWriterOutcomeDetail.RECONCILED_EXISTING
    assert len(transport.calls) == 1


def test_ambiguous_accepted_timeout_recovers_matching_marker_without_second_post() -> None:
    writer_input = _writer_input()
    transport = _PostTransport(
        failure=GitHubIssueCommentPostTransportFailure(
            GitHubIssueCommentWriterReasonCode.AMBIGUOUS_ACCEPTED,
            request_id="REQ-ambiguous",
            ambiguous_accepted=True,
        )
    )
    recovery = _PagesMarkerTransport(
        {None: MarkerCommentPage(comments=(_trusted_comment("comment-accepted", writer_input.final_payload.body),))}
    )
    writer = GitHubIssueCommentWriter(transport=transport, recovery_marker_transport=recovery)

    result = writer.post_issue_comment(writer_input)

    assert result.writer_result.status == WriterStatus.RECONCILED
    assert result.writer_result.comment_id == "comment-accepted"
    assert result.outcome_detail == GitHubIssueCommentWriterOutcomeDetail.RECONCILED_EXISTING
    assert result.transport_summary.post_attempt_count == 1
    assert result.transport_summary.recovery_scan_count == 1
    assert len(transport.calls) == 1


def test_ambiguous_accepted_timeout_records_duplicate_trusted_matching_markers() -> None:
    writer_input = _writer_input()
    transport = _PostTransport(
        failure=GitHubIssueCommentPostTransportFailure(
            GitHubIssueCommentWriterReasonCode.AMBIGUOUS_ACCEPTED,
            ambiguous_accepted=True,
        )
    )
    recovery = _PagesMarkerTransport(
        {
            None: MarkerCommentPage(
                comments=(
                    _trusted_comment("comment-one", writer_input.final_payload.body),
                    _trusted_comment("comment-two", writer_input.final_payload.body),
                ),
                request_id="REQ-duplicates",
            )
        }
    )
    writer = GitHubIssueCommentWriter(transport=transport, recovery_marker_transport=recovery)

    result = writer.post_issue_comment(writer_input)

    assert result.writer_result.status == WriterStatus.RECONCILED
    assert result.marker_reconciliation is not None
    assert result.marker_reconciliation.duplicate_comment_ids == ("comment-two",)
    assert len(transport.calls) == 1


def test_ambiguous_accepted_timeout_marker_empty_is_unresolved_and_retry_is_recovery_only() -> None:
    writer_input = _writer_input()
    transport = _PostTransport(
        failure=GitHubIssueCommentPostTransportFailure(
            GitHubIssueCommentWriterReasonCode.AMBIGUOUS_ACCEPTED,
            ambiguous_accepted=True,
        )
    )
    recovery = _PagesMarkerTransport(
        {None: MarkerCommentPage(comments=(), completed=True, request_id="REQ-empty")}
    )
    writer = GitHubIssueCommentWriter(transport=transport, recovery_marker_transport=recovery)

    first = writer.post_issue_comment(writer_input)
    second = writer.post_issue_comment(writer_input)

    assert first.writer_result.status == WriterStatus.FAILED
    assert first.outcome_detail == GitHubIssueCommentWriterOutcomeDetail.AMBIGUOUS_UNRESOLVED
    assert first.transport_summary.retryable is True
    assert first.transport_summary.post_attempt_count == 1
    assert first.transport_summary.recovery_scan_count == 1
    assert second.outcome_detail == GitHubIssueCommentWriterOutcomeDetail.FORBIDDEN_SECOND_POST
    assert second.transport_summary.post_attempt_count == 0
    assert second.transport_summary.recovery_scan_count == 1
    assert len(transport.calls) == 1


def test_ambiguous_recovery_trusted_conflict_fails_closed_without_second_post() -> None:
    writer_input = _writer_input()
    conflict = build_final_issue_comment_payload(
        run_id="run-conflict",
        review_target=_target(),
        visible_body="ReviewGraph approved findings\nTarget: acme/widgets#42\nHead: head456\n\nApproved findings:\n- P1 Different: Different body. (src/app.py:10)\n",
        item_fingerprints=("fp-1",),
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )
    transport = _PostTransport(
        failure=GitHubIssueCommentPostTransportFailure(
            GitHubIssueCommentWriterReasonCode.AMBIGUOUS_ACCEPTED,
            ambiguous_accepted=True,
        )
    )
    recovery = _PagesMarkerTransport(
        {None: MarkerCommentPage(comments=(_trusted_comment("comment-conflict", conflict.body),))}
    )
    writer = GitHubIssueCommentWriter(transport=transport, recovery_marker_transport=recovery)

    result = writer.post_issue_comment(writer_input)

    assert result.writer_result.status == WriterStatus.FAILED
    assert result.outcome_detail == GitHubIssueCommentWriterOutcomeDetail.TRUSTED_MARKER_CONFLICT
    assert result.writer_result.error == "trusted_marker_conflict"
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "case",
    [
        "timeout",
        "rate_limited",
        "forbidden",
        "not_found",
        "unavailable",
        "malformed_page",
        "transport_unknown",
        "incomplete",
        "repeated_cursor",
        "page_cap",
        "comment_cap",
    ],
)
def test_ambiguous_recovery_failures_return_failed_with_no_additional_post(case: str) -> None:
    writer_input = _writer_input()
    transport = _PostTransport(
        failure=GitHubIssueCommentPostTransportFailure(
            GitHubIssueCommentWriterReasonCode.AMBIGUOUS_ACCEPTED,
            ambiguous_accepted=True,
        )
    )
    recovery = _recovery_failure_transport(case)
    writer = GitHubIssueCommentWriter(transport=transport, recovery_marker_transport=recovery)

    result = writer.post_issue_comment(writer_input)

    assert result.writer_result.status == WriterStatus.FAILED
    assert result.transport_summary.post_attempt_count == 1
    assert result.transport_summary.recovery_scan_count == 1
    assert result.marker_reconciliation is not None
    assert len(transport.calls) == 1


def test_writer_github_has_no_ambient_network_or_shell_imports() -> None:
    tree = ast.parse(Path("src/reviewgraph/writer_github.py").read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])

    assert not (imports & {"requests", "httpx", "urllib", "subprocess", "os", "github", "gh"})


@pytest.mark.parametrize(
    "path",
    [
        "src/reviewgraph/cli.py",
        "src/reviewgraph/runner.py",
        "src/reviewgraph/github.py",
        "src/reviewgraph/writer_fake.py",
    ],
)
def test_default_boundaries_do_not_import_real_writer(path: str) -> None:
    tree = ast.parse(Path(path).read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)

    assert "reviewgraph.writer_github" not in imports


class _PostTransport:
    def __init__(self, response: object | None = None, *, failure: Exception | None = None) -> None:
        self.response = response or GitHubIssueCommentPostResponse("comment-1", "reviewgraph-bot")
        self.failure = failure
        self.calls: list[dict[str, object]] = []

    def post_issue_comment(
        self,
        owner_repo: str,
        pr_number: int,
        body: dict[str, str],
        timeout_seconds: int,
    ):
        self.calls.append(
            {
                "owner_repo": owner_repo,
                "pr_number": pr_number,
                "body": body,
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.failure is not None:
            raise self.failure
        return self.response


class _PagesMarkerTransport:
    def __init__(
        self,
        pages: dict[object | None, object],
        failures: dict[object | None, MarkerReconciliationReasonCode] | None = None,
    ) -> None:
        self.pages = pages
        self.failures = failures or {}

    def get_issue_comments_page(
        self,
        owner_repo: str,
        pr_number: int,
        cursor: object | None,
        timeout_seconds: int,
    ):
        if cursor in self.failures:
            raise MarkerScanTransportFailure(self.failures[cursor], request_id="REQ-recovery-failure")
        return self.pages.get(cursor, MarkerCommentPage(comments=(), completed=True, request_id="REQ-recovery"))


def _recovery_failure_transport(case: str) -> _PagesMarkerTransport:
    reason_by_case = {
        "timeout": MarkerReconciliationReasonCode.TIMEOUT,
        "rate_limited": MarkerReconciliationReasonCode.RATE_LIMITED,
        "forbidden": MarkerReconciliationReasonCode.FORBIDDEN,
        "not_found": MarkerReconciliationReasonCode.NOT_FOUND,
        "unavailable": MarkerReconciliationReasonCode.UNAVAILABLE,
    }
    if case in reason_by_case:
        return _PagesMarkerTransport({}, failures={None: reason_by_case[case]})
    if case == "malformed_page":
        return _PagesMarkerTransport({None: object()})
    if case == "transport_unknown":
        return _PagesMarkerTransport({}, failures={None: MarkerReconciliationReasonCode.TRANSPORT_UNKNOWN})
    if case == "incomplete":
        return _PagesMarkerTransport({None: MarkerCommentPage(comments=(), completed=False, next_cursor=None)})
    if case == "repeated_cursor":
        repeated = MarkerCommentPage(comments=(), completed=False, next_cursor="same")
        return _PagesMarkerTransport({None: repeated, "same": repeated})
    if case == "page_cap":
        pages: dict[object | None, object] = {
            None: MarkerCommentPage(comments=(), completed=False, next_cursor="page-1")
        }
        for index in range(1, 21):
            pages[f"page-{index}"] = MarkerCommentPage(
                comments=(),
                completed=False,
                next_cursor=f"page-{index + 1}",
            )
        return _PagesMarkerTransport(pages)
    if case == "comment_cap":
        return _PagesMarkerTransport(
            {
                None: MarkerCommentPage(
                    comments=tuple(
                        PaginatedMarkerComment(
                            comment_id=f"comment-{index}",
                            body="Plain comment.\n",
                            author_login="human",
                            author_type="User",
                            source_provider="github",
                        )
                        for index in range(1001)
                    ),
                    completed=True,
                )
            }
        )
    raise AssertionError(f"unknown recovery failure case: {case}")


def _writer_input(payload=None):
    payload = payload or _payload()
    return build_finalized_issue_comment_writer_input(
        finalization=_finalization(payload),
        approval=_approval(payload),
        run_id="run-123",
    )


def _finalization(payload) -> FinalizeGithubPayloadResult:
    return FinalizeGithubPayloadResult(
        actor_permission_finalization_check=ActorPermissionFinalizationCheckResult(
            status=GateStatus.PASS,
            actor_permission_transport_summary=ActorPermissionTransportSummary(
                endpoint_kind="issue_comment_permission",
                retryable=False,
            ),
            current_actor_permission_checked_at="2026-05-07T00:05:00Z",
        ),
        target_freshness_check=TargetFreshnessCheckResult(
            status=GateStatus.PASS,
            transport_summary=TargetFreshnessTransportSummary(
                endpoint_kind="pull_request_target",
                retryable=False,
            ),
            current_target=payload.review_target,
            current_target_hash=payload.review_target.target_hash(),
            current_checked_at="2026-05-07T00:05:00Z",
            check_method="fake_pull_request_target_probe",
        ),
        finalization_status=FinalizationStatus(
            FinalizationState.FINALIZED,
            payload.final_payload_hash,
            payload.review_target.target_hash(),
        ),
        approved_github_actor="reviewgraph-bot",
        payload_validation=PayloadValidationResult(
            status=GateStatus.PASS,
            payload_hash=payload.final_payload_hash,
            target_hash=payload.review_target.target_hash(),
        ),
        marker_reconciliation=MarkerReconciliationResult(
            status=MarkerReconciliationStatus.SAFE_TO_POST,
            reason_code=MarkerReconciliationReasonCode.SAFE_TO_POST,
            transport_summary=MarkerScanTransportSummary(
                endpoint_kind="issue_comments",
                page_count=1,
                comment_count=0,
                marker_count=0,
                retryable=False,
            ),
        ),
        final_payload=payload,
        writer_input_released=True,
    )


def _approval(payload) -> ApprovalDecision:
    target = payload.review_target
    return ApprovalDecision(
        approved=True,
        approved_item_ids=("finding-1",),
        approved_final_payload_hash=payload.final_payload_hash,
        approved_review_target_hash=target.target_hash(),
        approved_review_target=target,
        approved_github_actor="reviewgraph-bot",
        approved_permission="write",
        approved_permission_checked_at="2026-05-07T00:04:00Z",
        approved_credential_principal="gh-user:reviewgraph-bot",
        approved_credential_source="pat",
        approved_repo_permission="write",
        approved_installation_permission=None,
        approved_endpoint_permission=None,
        approved_issue_comment_write=True,
        approved_permission_check_method="fake_issue_comment_permission_probe",
        approved_permission_endpoint_method="POST",
        approved_permission_checked_target=target.to_ordered_dict(),
        approved_permission_checked_target_hash=target.target_hash(),
        approved_permission_endpoint=issue_comment_endpoint(target),
        approved_permission_endpoint_kind="issue_comment",
        approved_permission_transport_summary=ActorPermissionTransportSummary(
            endpoint_kind="issue_comment_permission",
            retryable=False,
        ),
        include_public_verdict=False,
        approved_by="local-user",
        timestamp="2026-05-07T00:04:30Z",
    )


def _trusted_comment(comment_id: str, body: str) -> PaginatedMarkerComment:
    return PaginatedMarkerComment(
        comment_id=comment_id,
        body=body,
        author_login="reviewgraph-bot",
        author_type="Bot",
        source_provider="github",
    )


def _payload():
    return build_final_issue_comment_payload(
        run_id="run-123",
        review_target=_target(),
        visible_body="ReviewGraph approved findings\nTarget: acme/widgets#42\nHead: head456\n\nApproved findings:\n- P1 Finding: Body. (src/app.py:10)\n",
        item_fingerprints=("fp-1",),
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )


def _target() -> ReviewTarget:
    return ReviewTarget("acme/widgets", 42, "base123", "head456", "merge789", "merge_base")
