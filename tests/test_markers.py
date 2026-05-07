import ast
from pathlib import Path

import pytest

from reviewgraph.hashing import (
    final_payload_hash,
    findings_hash,
    is_exact_reviewgraph_v1_marker_line,
    marker_payload_hash,
    visible_body_hash,
)
from reviewgraph.markers import (
    ExistingComment,
    MarkerScanStatus,
    build_final_issue_comment_payload,
    build_reviewgraph_marker_line,
    parse_reviewgraph_marker_line,
    reconcile_existing_markers,
    scan_final_line_marker,
)
from reviewgraph.models import GateStatus, RedactionStatus, ReviewTarget
from reviewgraph.payload_validation import validate_final_issue_comment_payload


def test_generated_marker_line_matches_exact_v1_grammar_and_hash_domains() -> None:
    marker = build_reviewgraph_marker_line(
        run_id="run-123",
        review_target=target(),
        visible_body=visible_body(),
        finding_fingerprints=("fp-2", "fp-1"),
    )

    assert is_exact_reviewgraph_v1_marker_line(marker)
    assert marker == (
        "<!-- reviewgraph:v1 run_id=run-123 "
        f"target={target().target_hash()} "
        f"payload={marker_payload_hash(visible_body())} "
        f"findings={findings_hash(('fp-1', 'fp-2'))} -->"
    )


def test_final_issue_comment_payload_helper_attaches_marker_as_final_line() -> None:
    payload = build_final_issue_comment_payload(
        run_id="run-123",
        review_target=target(),
        visible_body=visible_body().replace("\n", "\r\n"),
        item_fingerprints=("fp-2", "fp-1"),
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )

    assert payload.body == f"{visible_body()}{payload.marker_line}\n"
    assert payload.body.endswith(f"{payload.marker_line}\n")
    assert payload.body.count(payload.marker_line) == 1
    assert payload.marker_target_hash == target().target_hash()
    assert payload.marker_payload_hash == marker_payload_hash(visible_body())
    assert payload.visible_body_hash == visible_body_hash(payload.body)
    assert payload.final_payload_hash == final_payload_hash(payload.body)
    assert payload.findings_hash == findings_hash(("fp-1", "fp-2"))
    assert payload.item_fingerprints == ("fp-1", "fp-2")
    assert validate_final_issue_comment_payload(payload).status == GateStatus.PASS


def test_parser_returns_marker_fields_for_exact_marker_lines() -> None:
    marker_line = build_reviewgraph_marker_line(
        run_id="github:acme/widgets#42",
        review_target=target(),
        visible_body=visible_body(),
        finding_fingerprints=("fp-1",),
    )

    marker = parse_reviewgraph_marker_line(marker_line)

    assert marker is not None
    assert marker.run_id == "github:acme/widgets#42"
    assert marker.target_hash == target().target_hash()
    assert marker.payload_hash == marker_payload_hash(visible_body())
    assert marker.findings_hash == findings_hash(("fp-1",))
    assert marker.line == marker_line


@pytest.mark.parametrize(
    "case",
    [
        "wrong_prefix",
        "wrong_version",
        "missing_findings",
        "empty_run_id",
        "run_id_with_equals",
        "quoted_run_id",
        "bad_run_id_char",
        "reordered_fields",
        "extra_whitespace",
        "extra_field",
        "uppercase_hash",
    ],
)
def test_parser_rejects_malformed_markers(case: str) -> None:
    target_hash = target().target_hash()
    payload_hash = marker_payload_hash(visible_body())
    selected_findings_hash = findings_hash(("fp-1",))
    cases = {
        "wrong_prefix": "<!-- reviewgraph:payload -->",
        "wrong_version": (
            "<!-- reviewgraph:v2 run_id=run-123 "
            f"target={target_hash} payload={payload_hash} findings={selected_findings_hash} -->"
        ),
        "missing_findings": f"<!-- reviewgraph:v1 run_id=run-123 target={target_hash} payload={payload_hash} -->",
        "empty_run_id": (
            "<!-- reviewgraph:v1 run_id= "
            f"target={target_hash} payload={payload_hash} findings={selected_findings_hash} -->"
        ),
        "run_id_with_equals": (
            "<!-- reviewgraph:v1 run_id=bad=value "
            f"target={target_hash} payload={payload_hash} findings={selected_findings_hash} -->"
        ),
        "quoted_run_id": (
            "<!-- reviewgraph:v1 run_id='quoted' "
            f"target={target_hash} payload={payload_hash} findings={selected_findings_hash} -->"
        ),
        "bad_run_id_char": (
            "<!-- reviewgraph:v1 run_id=bad!value "
            f"target={target_hash} payload={payload_hash} findings={selected_findings_hash} -->"
        ),
        "reordered_fields": (
            "<!-- reviewgraph:v1 run_id=run-123 "
            f"target={target_hash} findings={selected_findings_hash} payload={payload_hash} -->"
        ),
        "extra_whitespace": (
            "<!-- reviewgraph:v1  run_id=run-123 "
            f"target={target_hash} payload={payload_hash} findings={selected_findings_hash} -->"
        ),
        "extra_field": (
            "<!-- reviewgraph:v1 run_id=run-123 "
            f"target={target_hash} payload={payload_hash} findings={selected_findings_hash} extra=1 -->"
        ),
        "uppercase_hash": (
            "<!-- reviewgraph:v1 run_id=run-123 "
            f"target={target_hash.upper()} payload={payload_hash} findings={selected_findings_hash} -->"
        ),
    }
    bad_marker = cases[case]

    assert parse_reviewgraph_marker_line(bad_marker) is None


def test_scanner_recognizes_only_final_line_markers() -> None:
    marker_line = build_reviewgraph_marker_line(
        run_id="run-123",
        review_target=target(),
        visible_body=visible_body(),
        finding_fingerprints=("fp-1",),
    )
    copied_body = f"{visible_body()}{marker_line}\nHuman copied marker above.\n"

    assert scan_final_line_marker(f"{visible_body()}{marker_line}\n") is not None
    assert scan_final_line_marker(copied_body) is None
    assert scan_final_line_marker(f"{visible_body()}{marker_line}\n\n") is None


def test_existing_matching_marker_returns_trust_neutral_reconciled_scan_result() -> None:
    payload = build_final_issue_comment_payload(
        run_id="run-123",
        review_target=target(),
        visible_body=visible_body(),
        item_fingerprints=("fp-1",),
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )

    result = reconcile_existing_markers(
        existing_comments=(ExistingComment(comment_id="comment-1", body=payload.body),),
        expected_target_hash=payload.marker_target_hash,
        expected_payload_hash=payload.marker_payload_hash,
        expected_findings_hash=payload.marker_findings_hash,
    )

    assert result.status == MarkerScanStatus.MATCHED
    assert result.existing_comment_id == "comment-1"
    assert result.marker == parse_reviewgraph_marker_line(payload.marker_line)
    assert result.writer_input_released is False
    assert result.finalization_passed is False


def test_same_target_and_findings_with_different_payload_is_not_reconciled() -> None:
    payload = build_final_issue_comment_payload(
        run_id="run-123",
        review_target=target(),
        visible_body=visible_body(),
        item_fingerprints=("fp-1",),
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )

    result = reconcile_existing_markers(
        existing_comments=(ExistingComment(comment_id="comment-1", body=payload.body),),
        expected_target_hash=payload.marker_target_hash,
        expected_payload_hash=marker_payload_hash("A different approved body.\n"),
        expected_findings_hash=payload.marker_findings_hash,
    )

    assert result.status == MarkerScanStatus.DEFERRED_CONFLICT
    assert result.existing_comment_id == "comment-1"
    assert result.writer_input_released is False
    assert result.finalization_passed is False


def test_payload_conflict_prevents_no_post_success_even_when_exact_marker_exists_later() -> None:
    payload = build_final_issue_comment_payload(
        run_id="run-123",
        review_target=target(),
        visible_body=visible_body(),
        item_fingerprints=("fp-1",),
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )
    conflicting = build_final_issue_comment_payload(
        run_id="run-124",
        review_target=target(),
        visible_body="Different approved body.\n",
        item_fingerprints=("fp-1",),
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )

    result = reconcile_existing_markers(
        existing_comments=(
            ExistingComment(comment_id="conflict", body=conflicting.body),
            ExistingComment(comment_id="exact", body=payload.body),
        ),
        expected_target_hash=payload.marker_target_hash,
        expected_payload_hash=payload.marker_payload_hash,
        expected_findings_hash=payload.marker_findings_hash,
    )

    assert result.status == MarkerScanStatus.DEFERRED_CONFLICT
    assert result.existing_comment_id == "conflict"


def test_malformed_final_reviewgraph_marker_is_deferred_not_no_match() -> None:
    result = reconcile_existing_markers(
        existing_comments=(
            ExistingComment(
                comment_id="malformed",
                body=f"{visible_body()}<!-- reviewgraph:v1 run_id=run-123 target={target().target_hash()} -->\n",
            ),
        ),
        expected_target_hash=target().target_hash(),
        expected_payload_hash=marker_payload_hash(visible_body()),
        expected_findings_hash=findings_hash(("fp-1",)),
    )

    assert result.status == MarkerScanStatus.DEFERRED_MALFORMED
    assert result.existing_comment_id == "malformed"
    assert result.marker is None


def test_no_existing_marker_returns_no_match_without_fail_closed_policy() -> None:
    result = reconcile_existing_markers(
        existing_comments=(ExistingComment(comment_id="comment-1", body="Plain human comment.\n"),),
        expected_target_hash=target().target_hash(),
        expected_payload_hash=marker_payload_hash(visible_body()),
        expected_findings_hash=findings_hash(("fp-1",)),
    )

    assert result.status == MarkerScanStatus.NO_MATCH
    assert result.reason == "no matching marker"
    assert result.existing_comment_id is None


def test_retry_after_timeout_can_reconcile_by_marker_without_writer_invocation() -> None:
    payload = build_final_issue_comment_payload(
        run_id="run-123",
        review_target=target(),
        visible_body=visible_body(),
        item_fingerprints=("fp-1",),
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )
    transport = _AcceptedThenTimeoutTransport()

    with pytest.raises(TimeoutError):
        transport.create_issue_comment(payload.body)

    result = _retry_post_if_no_marker(transport, payload)

    assert result.status == MarkerScanStatus.MATCHED
    assert result.existing_comment_id == "accepted-before-timeout"
    assert transport.post_attempts == 1


def test_retry_helper_does_not_post_on_deferred_marker_states() -> None:
    payload = build_final_issue_comment_payload(
        run_id="run-123",
        review_target=target(),
        visible_body=visible_body(),
        item_fingerprints=("fp-1",),
        redaction_status=RedactionStatus(redacted=False, replacement_count=0),
    )
    malformed_transport = _AcceptedThenTimeoutTransport(
        comments=(
            ExistingComment(
                comment_id="malformed",
                body=f"{visible_body()}<!-- reviewgraph:v1 run_id=run-123 target={target().target_hash()} -->\n",
            ),
        )
    )
    conflict_transport = _AcceptedThenTimeoutTransport(
        comments=(
            ExistingComment(
                comment_id="conflict",
                body=build_final_issue_comment_payload(
                    run_id="run-124",
                    review_target=target(),
                    visible_body="Different approved body.\n",
                    item_fingerprints=("fp-1",),
                    redaction_status=RedactionStatus(redacted=False, replacement_count=0),
                ).body,
            ),
        )
    )

    malformed = _retry_post_if_no_marker(malformed_transport, payload)
    conflict = _retry_post_if_no_marker(conflict_transport, payload)

    assert malformed.status == MarkerScanStatus.DEFERRED_MALFORMED
    assert malformed_transport.post_attempts == 0
    assert conflict.status == MarkerScanStatus.DEFERRED_CONFLICT
    assert conflict_transport.post_attempts == 0


def test_marker_module_keeps_side_effect_import_boundary() -> None:
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


def target() -> ReviewTarget:
    return ReviewTarget("acme/widgets", 42, "base123", "head456", "merge789", "merge_base")


def visible_body() -> str:
    return "ReviewGraph final comment\n\n- P1 Cache miss returns stale data.\n"


class _AcceptedThenTimeoutTransport:
    def __init__(self, comments: tuple[ExistingComment, ...] = ()) -> None:
        self.post_attempts = 0
        self._comments: list[ExistingComment] = list(comments)

    def create_issue_comment(self, body: str) -> None:
        self.post_attempts += 1
        self._comments.append(ExistingComment(comment_id="accepted-before-timeout", body=body))
        raise TimeoutError("client timed out after server accepted comment")

    def list_issue_comments(self) -> tuple[ExistingComment, ...]:
        return tuple(self._comments)


def _retry_post_if_no_marker(transport: _AcceptedThenTimeoutTransport, payload) -> object:
    result = reconcile_existing_markers(
        existing_comments=transport.list_issue_comments(),
        expected_target_hash=payload.marker_target_hash,
        expected_payload_hash=payload.marker_payload_hash,
        expected_findings_hash=payload.marker_findings_hash,
    )
    if result.status == MarkerScanStatus.MATCHED:
        return result
    if result.status == MarkerScanStatus.NO_MATCH:
        transport.create_issue_comment(payload.body)
    return result
