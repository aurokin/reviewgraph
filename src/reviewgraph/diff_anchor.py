from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from reviewgraph.models import ClassifiedFinding, DiffAnchor, ReviewTarget


class ChangedRangeContext(Protocol):
    start: int
    end: int


class AnchorChangedFileContext(Protocol):
    path: str
    changed_ranges: tuple[ChangedRangeContext, ...]
    status: str
    previous_path: str | None
    patch_status: str

    def contains_line(self, line: int) -> bool: ...


INLINEABLE_FILE_STATUSES = frozenset({"added", "modified", "renamed"})


def derive_diff_anchor(
    *,
    changed_files: tuple[AnchorChangedFileContext, ...],
    review_target: ReviewTarget,
    finding: ClassifiedFinding,
) -> DiffAnchor | None:
    changed_file = _changed_file_for_finding(changed_files, finding)
    if changed_file is None:
        return None
    if changed_file.patch_status != "available":
        return None
    if changed_file.status not in INLINEABLE_FILE_STATUSES:
        return None
    changed_range = _changed_range_for_finding(changed_file, finding)
    if changed_range is None:
        return None
    return DiffAnchor(
        path=changed_file.path,
        old_path=changed_file.previous_path,
        file_status=changed_file.status,
        line=finding.line,
        start_line=finding.line,
        hunk_start=changed_range.start,
        hunk_end=changed_range.end,
        hunk_id=f"{changed_file.path}:{changed_range.start}-{changed_range.end}",
        target_commit_sha=review_target.head_sha,
    )


def attach_diff_anchors(
    *,
    changed_files: tuple[AnchorChangedFileContext, ...],
    review_target: ReviewTarget,
    findings: tuple[ClassifiedFinding, ...],
) -> tuple[ClassifiedFinding, ...]:
    anchored: list[ClassifiedFinding] = []
    for finding in findings:
        if finding.diff_anchor is not None:
            anchored.append(finding)
            continue
        anchor = derive_diff_anchor(
            changed_files=changed_files,
            review_target=review_target,
            finding=finding,
        )
        anchored.append(finding if anchor is None else replace(finding, diff_anchor=anchor))
    return tuple(anchored)


def _changed_file_for_finding(
    changed_files: tuple[AnchorChangedFileContext, ...],
    finding: ClassifiedFinding,
) -> AnchorChangedFileContext | None:
    return next(
        (
            changed_file
            for changed_file in changed_files
            if changed_file.path == finding.path and changed_file.contains_line(finding.line)
        ),
        None,
    )


def _changed_range_for_finding(
    changed_file: AnchorChangedFileContext,
    finding: ClassifiedFinding,
) -> ChangedRangeContext | None:
    line_end = finding.line_end if finding.line_end is not None else finding.line
    return next(
        (
            changed_range
            for changed_range in changed_file.changed_ranges
            if changed_range.start <= finding.line <= line_end <= changed_range.end
        ),
        None,
    )
