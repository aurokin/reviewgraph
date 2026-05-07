from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from reviewgraph.hashing import (
    canonical_text_body,
    final_payload_hash,
    findings_hash,
    is_exact_reviewgraph_v1_marker_line,
    marker_payload_hash,
    parse_reviewgraph_v1_marker_line,
    visible_body_hash,
)
from reviewgraph.models import ArtifactKind, FinalIssueCommentPayload, RedactionStatus, ReviewTarget


class MarkerScanStatus(StrEnum):
    MATCHED = "matched"
    NO_MATCH = "no_match"
    DEFERRED_CONFLICT = "deferred_conflict"
    DEFERRED_MALFORMED = "deferred_malformed"


@dataclass(frozen=True)
class ReviewGraphMarker:
    run_id: str
    target_hash: str
    payload_hash: str
    findings_hash: str
    line: str

    def __post_init__(self) -> None:
        parsed = parse_reviewgraph_v1_marker_line(self.line)
        if parsed is None:
            raise ValueError("review graph marker line must match v1 grammar")
        if parsed != {
            "run_id": self.run_id,
            "target": self.target_hash,
            "payload": self.payload_hash,
            "findings": self.findings_hash,
        }:
            raise ValueError("review graph marker fields must match marker line")


@dataclass(frozen=True)
class ExistingComment:
    comment_id: str
    body: str

    def __post_init__(self) -> None:
        if not isinstance(self.comment_id, str) or not self.comment_id:
            raise ValueError("existing comment id is required")
        if not isinstance(self.body, str) or not self.body:
            raise ValueError("existing comment body is required")


@dataclass(frozen=True)
class MarkerScanResult:
    status: MarkerScanStatus
    existing_comment_id: str | None = None
    marker: ReviewGraphMarker | None = None
    reason: str | None = None
    writer_input_released: bool = False
    finalization_passed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.status, MarkerScanStatus):
            raise ValueError("marker scan status must be valid")
        if self.existing_comment_id is not None and not self.existing_comment_id:
            raise ValueError("marker scan existing_comment_id must be non-empty")
        if self.marker is not None and not isinstance(self.marker, ReviewGraphMarker):
            raise ValueError("marker scan marker must be a ReviewGraphMarker")
        if self.reason is not None and not self.reason:
            raise ValueError("marker scan reason must be non-empty")
        if not isinstance(self.writer_input_released, bool):
            raise ValueError("marker scan writer_input_released must be bool")
        if not isinstance(self.finalization_passed, bool):
            raise ValueError("marker scan finalization_passed must be bool")
        if self.writer_input_released or self.finalization_passed:
            raise ValueError("marker scan results are trust-neutral and cannot release writer input")
        if self.status == MarkerScanStatus.MATCHED:
            if self.existing_comment_id is None or self.marker is None:
                raise ValueError("matched marker scan requires existing comment and marker")
        if self.status == MarkerScanStatus.NO_MATCH:
            if self.existing_comment_id is not None or self.marker is not None:
                raise ValueError("no-match marker scan must not include a marker")
        if self.status == MarkerScanStatus.DEFERRED_CONFLICT:
            if self.existing_comment_id is None or self.marker is None:
                raise ValueError("deferred marker conflict requires existing comment and marker")
        if self.status == MarkerScanStatus.DEFERRED_MALFORMED:
            if self.existing_comment_id is None or self.marker is not None:
                raise ValueError("deferred malformed marker requires existing comment and no parsed marker")


def build_reviewgraph_marker_line(
    *,
    run_id: str,
    review_target: ReviewTarget,
    visible_body: str,
    finding_fingerprints: Iterable[str],
) -> str:
    if not isinstance(review_target, ReviewTarget):
        raise ValueError("review_target must be a ReviewTarget")
    body = canonical_text_body(visible_body)
    marker_line = (
        "<!-- reviewgraph:v1 "
        f"run_id={run_id} "
        f"target={review_target.target_hash()} "
        f"payload={marker_payload_hash(body)} "
        f"findings={findings_hash(finding_fingerprints)} -->"
    )
    if not is_exact_reviewgraph_v1_marker_line(marker_line):
        raise ValueError("generated marker line is invalid")
    return marker_line


def build_final_issue_comment_payload(
    *,
    run_id: str,
    review_target: ReviewTarget,
    visible_body: str,
    item_fingerprints: Iterable[str],
    redaction_status: RedactionStatus,
) -> FinalIssueCommentPayload:
    body_without_marker = canonical_text_body(visible_body)
    fingerprints = tuple(sorted(item_fingerprints))
    marker_line = build_reviewgraph_marker_line(
        run_id=run_id,
        review_target=review_target,
        visible_body=body_without_marker,
        finding_fingerprints=fingerprints,
    )
    body = f"{body_without_marker}{marker_line}\n"
    selected_findings_hash = findings_hash(fingerprints)
    selected_marker_payload_hash = marker_payload_hash(body_without_marker)
    return FinalIssueCommentPayload(
        artifact_kind=ArtifactKind.ISSUE_COMMENT,
        review_target=review_target,
        body=body,
        marker_line=marker_line,
        marker_run_id=run_id,
        marker_target_hash=review_target.target_hash(),
        marker_payload_hash=selected_marker_payload_hash,
        marker_findings_hash=selected_findings_hash,
        visible_body_hash=visible_body_hash(body),
        final_payload_hash=final_payload_hash(body),
        findings_hash=selected_findings_hash,
        item_fingerprints=fingerprints,
        redaction_status=redaction_status,
    )


def parse_reviewgraph_marker_line(line: str) -> ReviewGraphMarker | None:
    parsed = parse_reviewgraph_v1_marker_line(line)
    if parsed is None:
        return None
    return ReviewGraphMarker(
        run_id=parsed["run_id"],
        target_hash=parsed["target"],
        payload_hash=parsed["payload"],
        findings_hash=parsed["findings"],
        line=line,
    )


def scan_final_line_marker(body: str) -> ReviewGraphMarker | None:
    final_line = _body_final_line(body)
    if final_line is None:
        return None
    return parse_reviewgraph_marker_line(final_line)


def reconcile_existing_markers(
    *,
    existing_comments: Iterable[ExistingComment],
    expected_target_hash: str,
    expected_payload_hash: str,
    expected_findings_hash: str,
) -> MarkerScanResult:
    matched: MarkerScanResult | None = None
    deferred_conflict: MarkerScanResult | None = None
    deferred_malformed: MarkerScanResult | None = None
    for comment in existing_comments:
        if not isinstance(comment, ExistingComment):
            raise ValueError("existing comments must be ExistingComment values")
        final_line = _body_final_line(comment.body)
        marker = parse_reviewgraph_marker_line(final_line) if final_line is not None else None
        if marker is None:
            if _looks_like_reviewgraph_marker(final_line):
                deferred_malformed = MarkerScanResult(
                    status=MarkerScanStatus.DEFERRED_MALFORMED,
                    existing_comment_id=comment.comment_id,
                    reason="malformed reviewgraph marker final line",
                )
            continue
        if marker.target_hash != expected_target_hash or marker.findings_hash != expected_findings_hash:
            continue
        if marker.payload_hash == expected_payload_hash:
            matched = MarkerScanResult(
                status=MarkerScanStatus.MATCHED,
                existing_comment_id=comment.comment_id,
                marker=marker,
                reason="matching marker",
            )
            continue
        deferred_conflict = MarkerScanResult(
            status=MarkerScanStatus.DEFERRED_CONFLICT,
            existing_comment_id=comment.comment_id,
            marker=marker,
            reason="same target and findings with different payload",
        )
    if deferred_malformed is not None:
        return deferred_malformed
    if deferred_conflict is not None:
        return deferred_conflict
    if matched is not None:
        return matched
    return MarkerScanResult(status=MarkerScanStatus.NO_MATCH, reason="no matching marker")


def _body_final_line(body: str) -> str | None:
    if not isinstance(body, str) or not body:
        return None
    normalized = body.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.endswith("\n"):
        normalized = normalized[:-1]
    if not normalized:
        return ""
    return normalized.split("\n")[-1]


def _looks_like_reviewgraph_marker(line: str | None) -> bool:
    return isinstance(line, str) and line.startswith("<!-- reviewgraph:")
