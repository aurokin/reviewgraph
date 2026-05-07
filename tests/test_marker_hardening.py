import ast
from pathlib import Path

import pytest

from reviewgraph.markers import (
    MarkerCommentPage,
    MarkerReconciliationReasonCode,
    MarkerReconciliationStatus,
    MarkerScanLimits,
    MarkerScanTransportFailure,
    PaginatedMarkerComment,
    build_final_issue_comment_payload,
    reconcile_paginated_trusted_markers,
)
from reviewgraph.models import RedactionStatus, ReviewTarget


def test_paginated_scan_reads_all_pages_before_safe_to_post() -> None:
    transport = _Transport(
        {
            None: MarkerCommentPage(
                comments=(_comment("human-1", "Plain comment.\n"),),
                next_cursor="page-2",
                completed=False,
                request_id="REQ-1",
            ),
            "page-2": MarkerCommentPage(
                comments=(_comment("human-2", "Another plain comment.\n"),),
                completed=True,
                request_id="REQ-2",
            ),
        }
    )

    result = _scan(transport)

    assert result.status == MarkerReconciliationStatus.SAFE_TO_POST
    assert result.reason_code == MarkerReconciliationReasonCode.SAFE_TO_POST
    assert result.transport_summary.page_count == 2
    assert result.transport_summary.comment_count == 2
    assert result.transport_summary.marker_count == 0
    assert result.transport_summary.request_id == "REQ-2"
    assert result.writer_input_released is False
    assert transport.calls == [("acme/widgets", 42, None), ("acme/widgets", 42, "page-2")]


def test_matching_trusted_marker_on_later_page_reconciles_without_writer_release() -> None:
    payload = _payload()
    transport = _Transport(
        {
            None: MarkerCommentPage(comments=(), next_cursor="page-2", completed=False, request_id="REQ-1"),
            "page-2": MarkerCommentPage(
                comments=(_comment("existing", payload.body, author="reviewgraph-bot"),),
                completed=True,
                request_id="REQ-2",
            ),
        }
    )

    result = _scan(transport, payload=payload)

    assert result.status == MarkerReconciliationStatus.RECONCILED_EXISTING
    assert result.reason_code == MarkerReconciliationReasonCode.MATCHED_EXISTING
    assert result.existing_comment_id == "existing"
    assert result.trusted_actor == "reviewgraph-bot"
    assert result.duplicate_comment_ids == ()
    assert result.writer_input_released is False


@pytest.mark.parametrize("case", ["later_conflict", "later_malformed", "later_transport_failure"])
def test_full_scan_failures_override_earlier_matching_marker(case: str) -> None:
    payload = _payload()
    pages = {
        None: MarkerCommentPage(
            comments=(_comment("existing", payload.body, author="reviewgraph-bot"),),
            next_cursor="page-2",
            completed=False,
            request_id="REQ-1",
        )
    }
    failures = {}
    if case == "later_conflict":
        pages["page-2"] = MarkerCommentPage(
            comments=(_comment("conflict", _conflicting_payload().body, author="reviewgraph-bot"),),
            completed=True,
            request_id="REQ-2",
        )
        expected = MarkerReconciliationReasonCode.TRUSTED_MARKER_CONFLICT
    elif case == "later_malformed":
        pages["page-2"] = MarkerCommentPage(
            comments=(_comment("malformed", _malformed_marker_body(), author="reviewgraph-bot"),),
            completed=True,
            request_id="REQ-2",
        )
        expected = MarkerReconciliationReasonCode.TRUSTED_MARKER_MALFORMED
    else:
        failures["page-2"] = MarkerScanTransportFailure(
            MarkerReconciliationReasonCode.TIMEOUT,
            request_id="REQ-2",
            raw_stderr="token ghp_abcdefghijklmnopqrstuvwxyz123456",
        )
        expected = MarkerReconciliationReasonCode.TIMEOUT

    result = _scan(_Transport(pages, failures=failures), payload=payload)

    assert result.status == MarkerReconciliationStatus.FAILED_CLOSED
    assert result.reason_code == expected
    assert result.existing_comment_id is None
    assert result.writer_input_released is False


def test_trusted_conflict_before_or_after_exact_marker_fails_closed() -> None:
    payload = _payload()
    conflict = _conflicting_payload()
    before = _scan(
        _Transport(
            {
                None: MarkerCommentPage(
                    comments=(
                        _comment("conflict", conflict.body, author="reviewgraph-bot"),
                        _comment("existing", payload.body, author="reviewgraph-bot"),
                    ),
                    completed=True,
                )
            }
        ),
        payload=payload,
    )
    after = _scan(
        _Transport(
            {
                None: MarkerCommentPage(
                    comments=(
                        _comment("existing", payload.body, author="reviewgraph-bot"),
                        _comment("conflict", conflict.body, author="reviewgraph-bot"),
                    ),
                    completed=True,
                )
            }
        ),
        payload=payload,
    )

    assert before.status == MarkerReconciliationStatus.FAILED_CLOSED
    assert after.status == MarkerReconciliationStatus.FAILED_CLOSED
    assert before.reason_code == MarkerReconciliationReasonCode.TRUSTED_MARKER_CONFLICT
    assert after.reason_code == MarkerReconciliationReasonCode.TRUSTED_MARKER_CONFLICT


def test_page_and_comment_cap_boundaries() -> None:
    payload = _payload()
    at_page_cap = _scan(
        _Transport(
            {
                None: MarkerCommentPage(comments=(), next_cursor="page-2", completed=False),
                "page-2": MarkerCommentPage(comments=(), completed=True),
            }
        ),
        limits=MarkerScanLimits(max_pages=2, max_comments=10, timeout_seconds=10),
    )
    over_page_cap = _scan(
        _Transport(
            {
                None: MarkerCommentPage(comments=(), next_cursor="page-2", completed=False),
                "page-2": MarkerCommentPage(comments=(), next_cursor="page-3", completed=False),
                "page-3": MarkerCommentPage(comments=(), completed=True),
            }
        ),
        limits=MarkerScanLimits(max_pages=2, max_comments=10, timeout_seconds=10),
    )
    at_comment_cap = _scan(
        _Transport(
            {None: MarkerCommentPage(comments=(_comment("c1", payload.body, author="reviewgraph-bot"),), completed=True)}
        ),
        payload=payload,
        limits=MarkerScanLimits(max_pages=2, max_comments=1, timeout_seconds=10),
    )
    over_comment_cap = _scan(
        _Transport(
            {
                None: MarkerCommentPage(
                    comments=(_comment("c1", "One.\n"), _comment("c2", "Two.\n")),
                    completed=True,
                )
            }
        ),
        limits=MarkerScanLimits(max_pages=2, max_comments=1, timeout_seconds=10),
    )

    assert at_page_cap.status == MarkerReconciliationStatus.SAFE_TO_POST
    assert over_page_cap.reason_code == MarkerReconciliationReasonCode.PAGE_CAP_EXCEEDED
    assert at_comment_cap.status == MarkerReconciliationStatus.RECONCILED_EXISTING
    assert over_comment_cap.reason_code == MarkerReconciliationReasonCode.COMMENT_CAP_EXCEEDED


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        (MarkerCommentPage(comments=(), completed=True), MarkerReconciliationReasonCode.SAFE_TO_POST),
        (MarkerCommentPage(comments=(), completed=False, next_cursor=None), MarkerReconciliationReasonCode.PAGINATION_INCOMPLETE),
        (MarkerCommentPage(comments=(), completed=False, next_cursor="same"), MarkerReconciliationReasonCode.REPEATED_CURSOR),
    ],
)
def test_empty_pages_completion_and_cursor_progression(page: MarkerCommentPage, expected: MarkerReconciliationReasonCode) -> None:
    pages = {None: page}
    if page.next_cursor == "same":
        pages["same"] = page

    result = _scan(_Transport(pages), limits=MarkerScanLimits(max_pages=3, max_comments=10, timeout_seconds=10))

    assert result.reason_code == expected


@pytest.mark.parametrize(
    ("reason_code", "retryable"),
    [
        (MarkerReconciliationReasonCode.TIMEOUT, True),
        (MarkerReconciliationReasonCode.RATE_LIMITED, True),
        (MarkerReconciliationReasonCode.FORBIDDEN, False),
        (MarkerReconciliationReasonCode.NOT_FOUND, False),
        (MarkerReconciliationReasonCode.UNAVAILABLE, True),
        (MarkerReconciliationReasonCode.MALFORMED_PAGE, False),
        (MarkerReconciliationReasonCode.TRANSPORT_UNKNOWN, True),
    ],
)
def test_transport_failures_have_stable_redacted_summaries(
    reason_code: MarkerReconciliationReasonCode,
    retryable: bool,
) -> None:
    result = _scan(
        _Transport(
            {},
            failures={
                None: MarkerScanTransportFailure(
                    reason_code,
                    request_id="REQ-safe",
                    raw_stderr="raw stderr includes ghp_abcdefghijklmnopqrstuvwxyz123456",
                )
            },
        )
    )

    assert result.status == MarkerReconciliationStatus.FAILED_CLOSED
    assert result.reason_code == reason_code
    assert result.transport_summary.endpoint_kind == "issue_comments"
    assert result.transport_summary.retryable is retryable
    assert result.transport_summary.request_id == "REQ-safe"
    assert "ghp_" not in repr(result)
    assert "raw stderr" not in repr(result)


def test_transport_summary_exists_on_every_outcome_and_does_not_expose_bodies_or_secret_request_ids() -> None:
    secret_body = "Comment body with ghp_abcdefghijklmnopqrstuvwxyz123456\n"
    result = _scan(
        _Transport(
            {
                None: MarkerCommentPage(
                    comments=(_comment("secret", secret_body),),
                    completed=True,
                    request_id="ghp_abcdefghijklmnopqrstuvwxyz123456",
                )
            }
        )
    )

    assert result.status == MarkerReconciliationStatus.SAFE_TO_POST
    assert result.transport_summary.reason_code is None
    assert result.transport_summary.request_id is None
    assert set(result.transport_summary.__dataclass_fields__) == {
        "endpoint_kind",
        "page_count",
        "comment_count",
        "marker_count",
        "retryable",
        "reason_code",
        "request_id",
    }
    assert "ghp_" not in repr(result)
    assert secret_body.strip() not in repr(result)


@pytest.mark.parametrize(
    ("comment_id", "author", "author_type", "association"),
    [
        ("unapproved-user", "repo-owner", "user", "OWNER"),
        ("unconfigured-bot", "other-bot", "bot", "NONE"),
        ("missing-author", "", "user", "NONE"),
        ("unknown-type", "reviewgraph-bot", "organization", "NONE"),
        ("case-mismatch", "ReviewGraph-Bot", "bot", "NONE"),
        ("bot-name-user-type", "reviewgraph-bot", "user", "NONE"),
    ],
)
def test_untrusted_and_spoofed_marker_authors_are_ignored(
    comment_id: str,
    author: str,
    author_type: str,
    association: str,
) -> None:
    comment = _comment(
        comment_id,
        _payload().body,
        author=author,
        author_type=author_type,
        author_association=association,
    )
    result = _scan(
        _Transport({None: MarkerCommentPage(comments=(comment,), completed=True)}),
        approved_actor="reviewgraph-bot-approved",
        trusted_bot_authors=("reviewgraph-bot",),
    )

    assert result.status == MarkerReconciliationStatus.SAFE_TO_POST
    assert result.existing_comment_id is None
    assert result.transport_summary.marker_count == 1


@pytest.mark.parametrize(
    ("comment_id", "author", "author_type"),
    [
        ("approved-user", "local-user", "user"),
        ("approved-bot", "reviewgraph-bot", "bot"),
        ("configured-bot", "trusted-reviewgraph-bot", "bot"),
    ],
)
def test_approved_actor_and_configured_reviewgraph_bot_markers_are_trusted(
    comment_id: str,
    author: str,
    author_type: str,
) -> None:
    comment = _comment(comment_id, _payload().body, author=author, author_type=author_type)
    approved_actor = "local-user" if comment.comment_id == "approved-user" else "reviewgraph-bot"
    result = _scan(
        _Transport({None: MarkerCommentPage(comments=(comment,), completed=True)}),
        approved_actor=approved_actor,
        trusted_bot_authors=("trusted-reviewgraph-bot",),
    )

    assert result.status == MarkerReconciliationStatus.RECONCILED_EXISTING
    assert result.existing_comment_id == comment.comment_id


def test_trusted_malformed_final_line_fails_closed_but_untrusted_malformed_is_ignored() -> None:
    trusted = _scan(
        _Transport(
            {
                None: MarkerCommentPage(
                    comments=(_comment("malformed", _malformed_marker_body(), author="reviewgraph-bot"),),
                    completed=True,
                )
            }
        )
    )
    untrusted = _scan(
        _Transport(
            {
                None: MarkerCommentPage(
                    comments=(_comment("malformed", _malformed_marker_body(), author="repo-owner"),),
                    completed=True,
                )
            }
        ),
        approved_actor="reviewgraph-bot-approved",
    )

    assert trusted.status == MarkerReconciliationStatus.FAILED_CLOSED
    assert trusted.reason_code == MarkerReconciliationReasonCode.TRUSTED_MARKER_MALFORMED
    assert untrusted.status == MarkerReconciliationStatus.SAFE_TO_POST


def test_body_middle_copied_marker_is_inert() -> None:
    payload = _payload()
    copied = payload.body + "\nHuman copied this marker above.\n"

    result = _scan(
        _Transport({None: MarkerCommentPage(comments=(_comment("copy", copied, author="reviewgraph-bot"),), completed=True)}),
        payload=payload,
    )

    assert result.status == MarkerReconciliationStatus.SAFE_TO_POST
    assert result.transport_summary.marker_count == 0


def test_duplicate_trusted_matching_markers_reconcile_with_duplicate_metadata() -> None:
    payload = _payload()

    result = _scan(
        _Transport(
            {
                None: MarkerCommentPage(
                    comments=(
                        _comment("existing-1", payload.body, author="reviewgraph-bot"),
                        _comment("existing-2", payload.body, author="trusted-reviewgraph-bot", author_type="bot"),
                    ),
                    completed=True,
                )
            }
        ),
        payload=payload,
        trusted_bot_authors=("trusted-reviewgraph-bot",),
    )

    assert result.status == MarkerReconciliationStatus.RECONCILED_EXISTING
    assert result.existing_comment_id == "existing-1"
    assert result.duplicate_comment_ids == ("existing-2",)
    assert result.writer_input_released is False


def test_duplicate_finding_fingerprints_fail_before_marker_scan_inputs_are_needed() -> None:
    with pytest.raises(ValueError, match="duplicate finding fingerprints"):
        build_final_issue_comment_payload(
            run_id="run-123",
            review_target=_target(),
            visible_body=_visible_body(),
            item_fingerprints=("fp-1", "fp-1"),
            redaction_status=RedactionStatus(redacted=False, replacement_count=0),
        )


def test_marker_hardening_module_keeps_side_effect_import_boundary() -> None:
    tree = ast.parse(Path("src/reviewgraph/markers.py").read_text())
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    forbidden = {
        "os",
        "subprocess",
        "time",
        "datetime",
        "reviewgraph.github",
        "reviewgraph.graph",
        "reviewgraph.writer",
        "reviewgraph.finalization",
    }
    assert forbidden.isdisjoint(imported_modules)


class _Transport:
    def __init__(
        self,
        pages: dict[object | None, MarkerCommentPage],
        *,
        failures: dict[object | None, MarkerScanTransportFailure] | None = None,
    ) -> None:
        self.pages = pages
        self.failures = failures or {}
        self.calls: list[tuple[str, int, object | None]] = []

    def get_issue_comments_page(
        self,
        owner_repo: str,
        pr_number: int,
        cursor: object | None,
    ) -> MarkerCommentPage:
        self.calls.append((owner_repo, pr_number, cursor))
        if cursor in self.failures:
            raise self.failures[cursor]
        return self.pages[cursor]


def _scan(
    transport: _Transport,
    *,
    payload=None,
    approved_actor: str = "reviewgraph-bot",
    trusted_bot_authors: tuple[str, ...] = ("trusted-reviewgraph-bot",),
    limits: MarkerScanLimits | None = None,
):
    payload = payload or _payload()
    return reconcile_paginated_trusted_markers(
        transport=transport,
        owner_repo="acme/widgets",
        pr_number=42,
        approved_actor=approved_actor,
        trusted_bot_authors=trusted_bot_authors,
        expected_target_hash=payload.marker_target_hash,
        expected_payload_hash=payload.marker_payload_hash,
        expected_findings_hash=payload.marker_findings_hash,
        limits=limits or MarkerScanLimits(max_pages=20, max_comments=1000, timeout_seconds=10),
    )


def _comment(
    comment_id: str,
    body: str,
    *,
    author: str = "human",
    author_type: str = "user",
    author_association: str = "NONE",
) -> PaginatedMarkerComment:
    return PaginatedMarkerComment(
        comment_id=comment_id,
        body=body,
        author_login=author,
        author_type=author_type,
        source_provider="github",
        author_association=author_association,
    )


def _payload():
    return build_final_issue_comment_payload(
        run_id="run-123",
        review_target=_target(),
        visible_body=_visible_body(),
        item_fingerprints=("fp-1",),
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )


def _conflicting_payload():
    return build_final_issue_comment_payload(
        run_id="run-124",
        review_target=_target(),
        visible_body="Different approved body.\n",
        item_fingerprints=("fp-1",),
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )


def _malformed_marker_body() -> str:
    return f"{_visible_body()}<!-- reviewgraph:v1 run_id=run-123 target={_target().target_hash()} -->\n"


def _target() -> ReviewTarget:
    return ReviewTarget("acme/widgets", 42, "base123", "head456", "merge789", "merge_base")


def _visible_body() -> str:
    return "ReviewGraph final comment\n\n- P1 Cache miss returns stale data.\n"
