from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"
    SUGGESTION = "suggestion"
    NIT = "nit"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class OutputClassification(StrEnum):
    POSTABLE_FINDING = "postable_finding"
    LOCAL_NOTE = "local_note"
    CLARIFICATION_REQUEST = "clarification_request"
    SUGGESTED_REPLY = "suggested_reply"
    NON_FINDING = "non_finding"


class ReviewVerdict(StrEnum):
    COMMENT = "comment"
    REQUEST_CHANGES = "request_changes"
    NEEDS_CLARIFICATION = "needs_clarification"
    NO_FINDINGS = "no_findings"


class ArtifactKind(StrEnum):
    ISSUE_COMMENT = "issue_comment"


def validate_priority(priority: int) -> int:
    if type(priority) is not int or priority < 0 or priority > 3:
        raise ValueError("priority must be an integer from 0 through 3")
    return priority


@dataclass(frozen=True)
class ReviewTarget:
    owner_repo: str
    pr_number: int
    base_sha: str
    head_sha: str
    merge_base_sha: str | None
    diff_basis: str

    def __post_init__(self) -> None:
        if "/" not in self.owner_repo:
            raise ValueError("owner_repo must be in owner/repo form")
        if self.pr_number <= 0:
            raise ValueError("pr_number must be positive")
        for name in ("base_sha", "head_sha", "diff_basis"):
            if not getattr(self, name):
                raise ValueError(f"{name} is required")

    def to_ordered_dict(self) -> dict[str, Any]:
        return {
            "owner_repo": self.owner_repo,
            "pr_number": self.pr_number,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "merge_base_sha": self.merge_base_sha,
            "diff_basis": self.diff_basis,
        }


@dataclass(frozen=True)
class DiffAnchor:
    path: str
    line: int
    target_commit_sha: str
    hunk_start: int
    hunk_end: int
    side: str = "RIGHT"
    file_status: str = "modified"
    hunk_id: str = ""
    start_line: int | None = None
    start_side: str = "RIGHT"
    old_path: str | None = None

    def __post_init__(self) -> None:
        if not self.path:
            raise ValueError("diff anchor path is required")
        if self.line <= 0:
            raise ValueError("diff anchor line must be positive")
        if self.side != "RIGHT":
            raise ValueError("diff anchor side must be RIGHT for MVP inline candidates")
        if self.hunk_start <= 0 or self.hunk_end < self.hunk_start:
            raise ValueError("diff anchor hunk bounds are invalid")
        if not self.target_commit_sha:
            raise ValueError("diff anchor target_commit_sha is required")
        if not self.hunk_id:
            raise ValueError("diff anchor hunk_id is required")
        if self.start_line is None or self.start_line <= 0:
            raise ValueError("diff anchor start_line is required")
        if self.start_side != "RIGHT":
            raise ValueError("diff anchor start_side must be RIGHT for MVP inline candidates")

    @property
    def overlaps_changed_target(self) -> bool:
        return self.side == "RIGHT" and self.hunk_start <= self.line <= self.hunk_end

    def validates_finding_location(self, *, path: str, line: int, target_commit_sha: str) -> bool:
        return (
            self.path == path
            and self.line == line
            and self.target_commit_sha == target_commit_sha
            and self.start_line is not None
            and self.hunk_start <= self.start_line <= self.line <= self.hunk_end
            and self.start_side == "RIGHT"
            and self.overlaps_changed_target
        )


@dataclass(frozen=True)
class ClassifiedFinding:
    id: str
    source_reviewer: str
    source_stage: str
    title: str
    body: str
    evidence: str
    path: str
    line: int
    priority: int
    severity: Severity
    confidence: Confidence
    fingerprint: str
    classification: OutputClassification = OutputClassification.POSTABLE_FINDING
    line_end: int | None = None
    diff_anchor: DiffAnchor | None = None

    def __post_init__(self) -> None:
        validate_priority(self.priority)
        if not isinstance(self.severity, Severity):
            raise ValueError("severity must be a Severity value")
        if not isinstance(self.confidence, Confidence):
            raise ValueError("confidence must be a Confidence value")
        if self.classification != OutputClassification.POSTABLE_FINDING:
            raise ValueError("ClassifiedFinding must use postable_finding classification")
        for name in ("id", "source_reviewer", "source_stage", "title", "body", "evidence", "path", "fingerprint"):
            if not getattr(self, name):
                raise ValueError(f"{name} is required")
        if self.line <= 0:
            raise ValueError("line must be positive")


@dataclass(frozen=True)
class LocalNote:
    id: str
    title: str
    body: str
    evidence: str
    classification: OutputClassification = OutputClassification.LOCAL_NOTE


@dataclass(frozen=True)
class SuggestedReply:
    id: str
    source_comment_id: str
    proposed_body: str
    classification: OutputClassification = OutputClassification.SUGGESTED_REPLY


@dataclass(frozen=True)
class SuppressedOutput:
    id: str
    reason: str
    classification: OutputClassification = OutputClassification.NON_FINDING


@dataclass(frozen=True)
class ClarificationRequest:
    id: str
    reviewer: str
    question: str
    why_it_matters: str
    blocks_verdict: bool = True
    classification: OutputClassification = OutputClassification.CLARIFICATION_REQUEST


@dataclass(frozen=True)
class RedactionStatus:
    redacted: bool
    replacement_count: int
    categories: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SelectedReviewer:
    name: str
    stage: str
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("selected reviewer name is required")
        if not self.stage:
            raise ValueError("selected reviewer stage is required")
        if not self.reasons:
            raise ValueError("selected reviewer reasons are required")


@dataclass(frozen=True)
class MemoryReference:
    id: str
    trust_label: str
    resolved_status: str
    source_type: str
    body: str | None = None

    def __post_init__(self) -> None:
        for name in ("id", "trust_label", "resolved_status", "source_type"):
            if not getattr(self, name):
                raise ValueError(f"{name} is required")


@dataclass(frozen=True)
class TruncationNotice:
    resource: str
    truncated: bool
    note: str
    original_count: int | None = None
    retained_count: int | None = None
    original_bytes: int | None = None
    retained_bytes: int | None = None

    def __post_init__(self) -> None:
        if not self.resource:
            raise ValueError("truncation resource is required")
        if not self.note:
            raise ValueError("truncation note is required")
