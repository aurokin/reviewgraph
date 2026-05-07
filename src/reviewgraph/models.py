from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, TypeAlias


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


class RunMode(StrEnum):
    DRY_RUN = "dry_run"
    POST = "post"


class ReviewStage(StrEnum):
    INITIAL_TRIAGE = "initial_triage"
    SPECIALIZED_REVIEW = "specialized_review"
    LOGIC_REVIEW = "logic_review"
    CLARIFICATION_REVIEW = "clarification_review"


class ReviewerRunStatusValue(StrEnum):
    SELECTED = "selected"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GateStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class FinalizationState(StrEnum):
    NOT_READY = "not_ready"
    FINALIZED = "finalized"
    FAILED_CLOSED = "failed_closed"


class WriterStatus(StrEnum):
    NOT_CALLED = "not_called"
    POSTED = "posted"
    RECONCILED = "reconciled"
    FAILED = "failed"


class ClarificationState(StrEnum):
    PENDING = "pending"
    ANSWERED = "answered"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


class PostingDestination(StrEnum):
    LOCAL_ONLY = "local_only"
    TOP_LEVEL_SUMMARY_ITEM = "top_level_summary_item"
    REVIEW_BODY_ITEM = "review_body_item"
    INLINE_CANDIDATE = "inline_candidate"
    SUGGESTED_REPLY = "suggested_reply"


ALLOWED_REVIEWER_CAPABILITIES = frozenset({"none", "diff_context"})
ALLOWED_REVIEWER_VERDICT_POWERS = frozenset({"comment", "request_changes"})
ALLOWED_RAW_FINDING_EVIDENCE_SOURCES = frozenset({"diff", "trusted_memory"})
INERT_REVIEWER_TOOL_PREFIX = "future-"


def validate_priority(priority: int) -> int:
    if type(priority) is not int or priority < 0 or priority > 3:
        raise ValueError("priority must be an integer from 0 through 3")
    return priority


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json_hash(data: object) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_text(encoded)


def _domain_json_hash(domain: str, data: object) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return _sha256_text(f"{domain}\n{encoded}")


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} is required")


def _require_optional_non_empty(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_non_empty(value, field_name)


def _require_hash_like(value: str, field_name: str) -> None:
    _require_non_empty(value, field_name)
    if not value.startswith("sha256:"):
        raise ValueError(f"{field_name} must be a sha256 hash")


def _require_optional_hash_like(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_hash_like(value, field_name)


def _require_non_negative_int(value: int, field_name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_positive_int(value: int, field_name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_string_tuple(value: tuple[str, ...], field_name: str, *, allow_empty: bool = True) -> None:
    if not isinstance(value, tuple) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{field_name} must be a tuple of non-empty strings")
    if not allow_empty and not value:
        raise ValueError(f"{field_name} must include at least one reason")


def _require_allowed_str_tuple(value: tuple[str, ...], field_name: str, allowed: frozenset[str]) -> None:
    _require_string_tuple(value, field_name)
    invalid = [item for item in value if item not in allowed]
    if invalid:
        raise ValueError(f"{field_name} contains unsupported values: {', '.join(sorted(invalid))}")


def _require_inert_tool_identifiers(value: tuple[str, ...], field_name: str) -> None:
    allowed_chars = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
    invalid = [
        item
        for item in value
        if not item.startswith(INERT_REVIEWER_TOOL_PREFIX)
        or not item.removeprefix(INERT_REVIEWER_TOOL_PREFIX)
        or any(char not in allowed_chars for char in item)
    ]
    if invalid:
        raise ValueError(f"{field_name} must contain inert future-* identifiers")


def _require_optional_positive_int(value: int | None, field_name: str) -> None:
    if value is not None:
        _require_positive_int(value, field_name)


def _require_instance_tuple(value: object, field_name: str, item_type: type[object]) -> None:
    if not isinstance(value, tuple) or any(not isinstance(item, item_type) for item in value):
        raise ValueError(f"{field_name} must be a tuple of {item_type.__name__} values")


def _require_optional_reviewer_output(value: object, field_name: str) -> None:
    if value is not None and not isinstance(value, (Mapping, str)):
        raise ValueError(f"{field_name} must be a mapping, string, or None")


def _require_json_value(value: object, field_name: str) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{field_name} mapping keys must be strings")
            _require_json_value(item, field_name)
        return
    if isinstance(value, list):
        for item in value:
            _require_json_value(item, field_name)
        return
    raise ValueError(f"{field_name} must be JSON-compatible")


def _require_issue_comment_artifact(value: ArtifactKind, field_name: str) -> None:
    if not isinstance(value, ArtifactKind) or value != ArtifactKind.ISSUE_COMMENT:
        raise ValueError(f"{field_name} must be ArtifactKind.ISSUE_COMMENT")


def _required_mapping_str(data: Mapping[str, object], field_name: str, label: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} {field_name} must be a non-empty string")
    return value


def _optional_mapping_str(data: Mapping[str, object], field_name: str, label: str) -> str | None:
    if field_name not in data:
        return None
    return _required_mapping_str(data, field_name, label)


def _optional_mapping_str_tuple(data: Mapping[str, object], field_name: str, label: str) -> tuple[str, ...]:
    if field_name not in data:
        return ()
    value = data[field_name]
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{label} {field_name} must be an array of non-empty strings")
    return tuple(value)


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
        if type(self.pr_number) is not int or self.pr_number <= 0:
            raise ValueError("pr_number must be positive")
        for name in ("base_sha", "head_sha", "diff_basis"):
            if not getattr(self, name):
                raise ValueError(f"{name} is required")
        if self.merge_base_sha is not None and not isinstance(self.merge_base_sha, str):
            raise ValueError("merge_base_sha must be a string or None")

    def to_ordered_dict(self) -> dict[str, Any]:
        return {
            "owner_repo": self.owner_repo,
            "pr_number": self.pr_number,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "merge_base_sha": self.merge_base_sha,
            "diff_basis": self.diff_basis,
        }

    def target_hash(self) -> str:
        return _domain_json_hash("reviewgraph.review_target.v1", self.to_ordered_dict())


@dataclass(frozen=True)
class PostingTarget:
    review_target: ReviewTarget
    artifact_kind: ArtifactKind = ArtifactKind.ISSUE_COMMENT

    def __post_init__(self) -> None:
        if not isinstance(self.review_target, ReviewTarget):
            raise ValueError("posting target review_target must be a ReviewTarget")
        _require_issue_comment_artifact(self.artifact_kind, "posting target artifact_kind")


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

    def validates_finding_location(
        self,
        *,
        path: str,
        line: int,
        target_commit_sha: str,
        line_end: int | None = None,
    ) -> bool:
        finding_line_end = line if line_end is None else line_end
        return (
            self.path == path
            and self.line == line
            and self.target_commit_sha == target_commit_sha
            and self.start_line is not None
            and self.hunk_start <= self.start_line <= self.line <= finding_line_end <= self.hunk_end
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
    blocking: bool = False
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
        if type(self.blocking) is not bool:
            raise ValueError("blocking must be a boolean")
        for name in ("id", "source_reviewer", "source_stage", "title", "body", "evidence", "path", "fingerprint"):
            if not getattr(self, name):
                raise ValueError(f"{name} is required")
        if self.line <= 0:
            raise ValueError("line must be positive")


Finding: TypeAlias = ClassifiedFinding


@dataclass(frozen=True)
class LocalNote:
    id: str
    title: str
    body: str
    evidence: str
    classification: OutputClassification = OutputClassification.LOCAL_NOTE

    def __post_init__(self) -> None:
        for name in ("id", "title", "body", "evidence"):
            _require_non_empty(getattr(self, name), f"local note {name}")
        if self.classification != OutputClassification.LOCAL_NOTE:
            raise ValueError("LocalNote must use local_note classification")


@dataclass(frozen=True)
class SuggestedReply:
    id: str
    source_comment_id: str
    proposed_body: str
    classification: OutputClassification = OutputClassification.SUGGESTED_REPLY

    def __post_init__(self) -> None:
        for name in ("id", "source_comment_id", "proposed_body"):
            _require_non_empty(getattr(self, name), f"suggested reply {name}")
        if self.classification != OutputClassification.SUGGESTED_REPLY:
            raise ValueError("SuggestedReply must use suggested_reply classification")


@dataclass(frozen=True)
class SuppressedReviewerOutput:
    id: str
    reason: str
    classification: OutputClassification = OutputClassification.NON_FINDING

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "suppressed reviewer output id")
        _require_non_empty(self.reason, "suppressed reviewer output reason")
        if self.classification != OutputClassification.NON_FINDING:
            raise ValueError("SuppressedReviewerOutput must use non_finding classification")


SuppressedOutput: TypeAlias = SuppressedReviewerOutput


@dataclass(frozen=True)
class ReviewerRunKey:
    target_hash: str
    config_hash: str
    stage: ReviewStage
    reviewer: str
    attempt: int = 1
    retry_of: str | None = None
    clarification_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.target_hash, "target_hash")
        _require_non_empty(self.config_hash, "config_hash")
        _require_non_empty(self.reviewer, "reviewer")
        if not isinstance(self.stage, ReviewStage):
            raise ValueError("stage must be a ReviewStage")
        if type(self.attempt) is not int or self.attempt <= 0:
            raise ValueError("attempt must be a positive integer")
        _require_optional_non_empty(self.retry_of, "retry_of")
        _require_optional_non_empty(self.clarification_id, "clarification_id")

    def stable_key(self) -> str:
        return json.dumps(
            {
                "attempt": self.attempt,
                "clarification_id": self.clarification_id,
                "config_hash": self.config_hash,
                "retry_of": self.retry_of,
                "reviewer": self.reviewer,
                "stage": self.stage.value,
                "target_hash": self.target_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class ReviewerRunStatus:
    status: ReviewerRunStatusValue
    run_key: ReviewerRunKey
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ReviewerRunStatusValue):
            raise ValueError("reviewer run status must be a ReviewerRunStatusValue")
        if not isinstance(self.run_key, ReviewerRunKey):
            raise ValueError("reviewer run status run_key must be a ReviewerRunKey")
        _require_optional_non_empty(self.reason, "reviewer run status reason")


GRAPH_OWNED_REVIEWER_FIELDS = frozenset(
    {
        "approved",
        "blocking",
        "classification",
        "destination",
        "diff_anchor",
        "final_priority",
        "fingerprint",
        "github_destination",
        "github_payload",
        "posting_destination",
        "posting_plan",
        "priority",
        "public_payload_eligible",
        "review_event",
        "target_commit_sha",
        "verdict",
    }
)


@dataclass(frozen=True)
class RawReviewerFinding:
    id: str
    severity: Severity
    confidence: Confidence
    path: str
    line: int
    title: str
    rationale: str
    evidence: str
    line_end: int | None = None
    suggested_fix: str | None = None
    evidence_sources: tuple[str, ...] = ()
    evidence_memory_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("id", "path", "title", "rationale", "evidence"):
            _require_non_empty(getattr(self, name), f"raw reviewer finding {name}")
        if not isinstance(self.severity, Severity):
            raise ValueError("raw reviewer finding severity must be a Severity value")
        if not isinstance(self.confidence, Confidence):
            raise ValueError("raw reviewer finding confidence must be a Confidence value")
        if type(self.line) is not int or self.line <= 0:
            raise ValueError("raw reviewer finding line must be a positive integer")
        if self.line_end is not None and (type(self.line_end) is not int or self.line_end < self.line):
            raise ValueError("raw reviewer finding line_end must be an integer greater than or equal to line")
        _require_optional_non_empty(self.suggested_fix, "raw reviewer finding suggested_fix")
        _require_allowed_str_tuple(
            self.evidence_sources,
            "raw reviewer finding evidence_sources",
            ALLOWED_RAW_FINDING_EVIDENCE_SOURCES,
        )
        _require_string_tuple(self.evidence_memory_ids, "raw reviewer finding evidence_memory_ids")

    @classmethod
    def from_mapping(cls, data: dict[str, object]) -> "RawReviewerFinding":
        graph_owned = GRAPH_OWNED_REVIEWER_FIELDS.intersection(data)
        if graph_owned:
            raise ValueError(f"raw reviewer finding contains graph-owned fields: {', '.join(sorted(graph_owned))}")
        required = ("id", "severity", "confidence", "path", "line", "title", "rationale", "evidence")
        if "rationale" not in data and "body" in data:
            data = {**data, "rationale": data["body"]}
        if "type" in data and data["type"] not in {"finding", "raw_finding"}:
            raise ValueError("raw reviewer finding type must be finding")
        for name in required:
            if name not in data:
                raise ValueError(f"raw reviewer finding {name} is required")
        line = data["line"]
        if type(line) is not int or line <= 0:
            raise ValueError("raw reviewer finding line must be a positive integer")
        line_end = data.get("line_end")
        if line_end is not None and (type(line_end) is not int or line_end < line):
            raise ValueError("raw reviewer finding line_end must be an integer greater than or equal to line")
        return cls(
            id=_required_mapping_str(data, "id", "raw reviewer finding"),
            severity=Severity(_required_mapping_str(data, "severity", "raw reviewer finding")),
            confidence=Confidence(_required_mapping_str(data, "confidence", "raw reviewer finding")),
            path=_required_mapping_str(data, "path", "raw reviewer finding"),
            line=line,
            title=_required_mapping_str(data, "title", "raw reviewer finding"),
            rationale=_required_mapping_str(data, "rationale", "raw reviewer finding"),
            evidence=_required_mapping_str(data, "evidence", "raw reviewer finding"),
            line_end=line_end,
            suggested_fix=_optional_mapping_str(data, "suggested_fix", "raw reviewer finding"),
            evidence_sources=_optional_mapping_str_tuple(data, "evidence_sources", "raw reviewer finding"),
            evidence_memory_ids=_optional_mapping_str_tuple(
                data,
                "evidence_memory_ids",
                "raw reviewer finding",
            ),
        )


@dataclass(frozen=True)
class ClarificationRequest:
    id: str
    reviewer: str
    question: str
    why_it_matters: str
    blocks_verdict: bool = True
    classification: OutputClassification = OutputClassification.CLARIFICATION_REQUEST
    source_stage: str | None = None
    source_run_key: ReviewerRunKey | None = None
    status: ClarificationState | None = None
    resume_target_stage: ReviewStage | None = None
    resume_target_reviewers: tuple[str, ...] = field(default_factory=tuple)
    evidence_sources: tuple[str, ...] = field(default_factory=tuple)
    evidence_memory_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in ("id", "reviewer", "question", "why_it_matters"):
            _require_non_empty(getattr(self, name), f"clarification request {name}")
        if type(self.blocks_verdict) is not bool:
            raise ValueError("clarification request blocks_verdict must be a boolean")
        if self.classification != OutputClassification.CLARIFICATION_REQUEST:
            raise ValueError("ClarificationRequest must use clarification_request classification")
        _require_optional_non_empty(self.source_stage, "clarification request source_stage")
        if self.source_run_key is not None and not isinstance(self.source_run_key, ReviewerRunKey):
            raise ValueError("clarification request source_run_key must be a ReviewerRunKey")
        if self.status is not None and not isinstance(self.status, ClarificationState):
            raise ValueError("clarification request status must be a ClarificationState")
        if self.resume_target_stage is not None and not isinstance(self.resume_target_stage, ReviewStage):
            raise ValueError("clarification request resume_target_stage must be a ReviewStage")
        _require_string_tuple(self.resume_target_reviewers, "clarification request resume_target_reviewers")
        _require_allowed_str_tuple(
            self.evidence_sources,
            "clarification request evidence_sources",
            ALLOWED_RAW_FINDING_EVIDENCE_SOURCES,
        )
        _require_string_tuple(self.evidence_memory_ids, "clarification request evidence_memory_ids")


@dataclass(frozen=True)
class NormalizationError:
    code: str
    message: str
    run_key: ReviewerRunKey
    repairable: bool
    fatal: bool = True
    item_id: str | None = None
    item_index: int | None = None
    rejected_fields: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_non_empty(self.code, "normalization error code")
        _require_non_empty(self.message, "normalization error message")
        if not isinstance(self.run_key, ReviewerRunKey):
            raise ValueError("normalization error run_key must be a ReviewerRunKey")
        if type(self.repairable) is not bool:
            raise ValueError("normalization error repairable must be a boolean")
        if type(self.fatal) is not bool:
            raise ValueError("normalization error fatal must be a boolean")
        _require_optional_non_empty(self.item_id, "normalization error item_id")
        if self.item_index is not None and (type(self.item_index) is not int or self.item_index < 0):
            raise ValueError("normalization error item_index must be a non-negative integer")
        _require_string_tuple(self.rejected_fields, "normalization error rejected_fields")

    def to_ordered_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "run_key": self.run_key.stable_key(),
            "repairable": self.repairable,
            "fatal": self.fatal,
            "item_id": self.item_id,
            "item_index": self.item_index,
            "rejected_fields": list(self.rejected_fields),
        }


@dataclass(frozen=True)
class ReviewerRepairRecord:
    attempt_count: int
    status: str
    original_output: Any = None
    repaired_output: Any = None
    errors: tuple[NormalizationError, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if type(self.attempt_count) is not int or self.attempt_count < 0:
            raise ValueError("reviewer repair record attempt_count must be a non-negative integer")
        if self.status not in {"not_attempted", "succeeded", "failed"}:
            raise ValueError("reviewer repair record status must be not_attempted, succeeded, or failed")
        _require_json_value(self.original_output, "reviewer repair record original_output")
        _require_json_value(self.repaired_output, "reviewer repair record repaired_output")
        _require_instance_tuple(self.errors, "reviewer repair record errors", NormalizationError)

    def to_ordered_dict(self) -> dict[str, Any]:
        return {
            "attempt_count": self.attempt_count,
            "status": self.status,
            "original_output": self.original_output,
            "repaired_output": self.repaired_output,
            "errors": [error.to_ordered_dict() for error in self.errors],
        }


@dataclass(frozen=True)
class ClarificationAnswer:
    id: str
    request_id: str
    answer: str
    answered_by: str
    answered_at: str

    def __post_init__(self) -> None:
        for name in ("id", "request_id", "answer", "answered_by", "answered_at"):
            _require_non_empty(getattr(self, name), f"clarification answer {name}")


@dataclass(frozen=True)
class ClarificationStatus:
    request_id: str
    status: ClarificationState
    reason: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.request_id, "clarification status request_id")
        if not isinstance(self.status, ClarificationState):
            raise ValueError("clarification status must be a ClarificationState value")
        _require_optional_non_empty(self.reason, "clarification status reason")


@dataclass(frozen=True)
class ReviewerResult:
    run_key: ReviewerRunKey
    status: ReviewerRunStatusValue = ReviewerRunStatusValue.COMPLETED
    raw_output: Mapping[str, object] | str | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)
    findings: tuple[RawReviewerFinding, ...] = field(default_factory=tuple)
    clarification_requests: tuple[ClarificationRequest, ...] = field(default_factory=tuple)
    local_notes: tuple[LocalNote, ...] = field(default_factory=tuple)
    suggested_replies: tuple[SuggestedReply, ...] = field(default_factory=tuple)
    suppressed_outputs: tuple[SuppressedReviewerOutput, ...] = field(default_factory=tuple)
    normalization_errors: tuple[NormalizationError, ...] = field(default_factory=tuple)
    repair_record: ReviewerRepairRecord | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.run_key, ReviewerRunKey):
            raise ValueError("reviewer result run_key must be a ReviewerRunKey")
        if not isinstance(self.status, ReviewerRunStatusValue):
            raise ValueError("reviewer result status must be a ReviewerRunStatusValue")
        _require_optional_reviewer_output(self.raw_output, "reviewer result raw_output")
        _require_string_tuple(self.errors, "reviewer result errors")
        _require_instance_tuple(self.findings, "reviewer result findings", RawReviewerFinding)
        _require_instance_tuple(
            self.clarification_requests,
            "reviewer result clarification_requests",
            ClarificationRequest,
        )
        _require_instance_tuple(self.local_notes, "reviewer result local_notes", LocalNote)
        _require_instance_tuple(self.suggested_replies, "reviewer result suggested_replies", SuggestedReply)
        _require_instance_tuple(
            self.suppressed_outputs,
            "reviewer result suppressed_outputs",
            SuppressedReviewerOutput,
        )
        _require_instance_tuple(
            self.normalization_errors,
            "reviewer result normalization_errors",
            NormalizationError,
        )
        if self.repair_record is not None and not isinstance(self.repair_record, ReviewerRepairRecord):
            raise ValueError("reviewer result repair_record must be a ReviewerRepairRecord")


@dataclass(frozen=True)
class RedactionStatus:
    redacted: bool
    replacement_count: int
    categories: tuple[str, ...] = field(default_factory=tuple)
    status: GateStatus = GateStatus.PASS

    def __post_init__(self) -> None:
        if type(self.redacted) is not bool:
            raise ValueError("redaction redacted must be a boolean")
        _require_non_negative_int(self.replacement_count, "redaction replacement_count")
        _require_string_tuple(self.categories, "redaction categories")
        if not isinstance(self.status, GateStatus):
            raise ValueError("redaction status must be a GateStatus")
        if self.redacted and self.replacement_count <= 0:
            raise ValueError("redacted payloads require replacement_count")


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
    author: str | None = None
    author_association: str | None = None
    author_type: str | None = None
    created_at: str | None = None
    url: str | None = None
    path: str | None = None
    line: int | None = None
    actionable: bool = False
    passive_reason: str | None = None
    source_provider: str | None = None
    source_id: str | None = None
    thread_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("id", "trust_label", "resolved_status", "source_type"):
            if not getattr(self, name):
                raise ValueError(f"{name} is required")
        for name in (
            "author",
            "author_association",
            "author_type",
            "created_at",
            "url",
            "path",
            "passive_reason",
            "source_provider",
            "source_id",
            "thread_id",
        ):
            _require_optional_non_empty(getattr(self, name), f"memory {name}")
        _require_optional_positive_int(self.line, "memory line")
        if type(self.actionable) is not bool:
            raise ValueError("memory actionable must be a boolean")
        if self.actionable:
            if self.trust_label != "trusted":
                raise ValueError("actionable memory requires trusted trust_label")
            if self.resolved_status != "unresolved":
                raise ValueError("actionable memory requires unresolved resolved_status")
            if self.source_type not in {"issue_comment", "review_thread"}:
                raise ValueError("actionable memory requires issue_comment or review_thread source_type")
            if self.author_type is None or self.author_type.casefold() not in {"user", "bot"}:
                raise ValueError("actionable memory requires supported author_type")


@dataclass(frozen=True)
class PullRequestComment:
    id: str
    author: str
    author_association: str
    author_type: str
    body: str
    created_at: str
    trust_label: str
    source_type: str
    url: str | None = None
    path: str | None = None
    line: int | None = None
    side: str | None = None
    commit_sha: str | None = None
    position: int | None = None
    source_provider: str = "fixture"

    def __post_init__(self) -> None:
        for name in (
            "id",
            "author",
            "author_association",
            "body",
            "created_at",
            "trust_label",
            "source_type",
            "author_type",
            "source_provider",
        ):
            _require_non_empty(getattr(self, name), f"pull request comment {name}")
        for name in ("url", "path", "side", "commit_sha"):
            _require_optional_non_empty(getattr(self, name), f"pull request comment {name}")
        _require_optional_positive_int(self.line, "pull request comment line")
        _require_optional_positive_int(self.position, "pull request comment position")


@dataclass(frozen=True)
class PullRequestReview:
    id: str
    author: str
    author_association: str
    author_type: str
    state: str
    created_at: str
    trust_label: str
    source_type: str
    body: str | None = None
    url: str | None = None
    source_provider: str = "fixture"

    def __post_init__(self) -> None:
        for name in (
            "id",
            "author",
            "author_association",
            "state",
            "created_at",
            "trust_label",
            "source_type",
            "author_type",
            "source_provider",
        ):
            _require_non_empty(getattr(self, name), f"pull request review {name}")
        _require_optional_non_empty(self.body, "pull request review body")
        _require_optional_non_empty(self.url, "pull request review url")


@dataclass(frozen=True)
class PullRequestReviewThread:
    id: str
    path: str
    resolved_status: str
    comments: tuple[PullRequestComment, ...]

    def __post_init__(self) -> None:
        for name in ("id", "path", "resolved_status"):
            _require_non_empty(getattr(self, name), f"pull request review thread {name}")
        if self.resolved_status not in {"resolved", "unresolved", "unknown"}:
            raise ValueError("pull request review thread resolved_status must be resolved, unresolved, or unknown")
        _require_instance_tuple(self.comments, "pull request review thread comments", PullRequestComment)
        if not self.comments:
            raise ValueError("pull request review thread comments must not be empty")


@dataclass(frozen=True)
class PullRequestChangedFile:
    path: str
    patch: str | None
    additions: int = 0
    deletions: int = 0
    status: str = "modified"
    previous_path: str | None = None
    patch_status: str = "available"

    def __post_init__(self) -> None:
        _require_non_empty(self.path, "pull request changed file path")
        if self.patch is not None and not isinstance(self.patch, str):
            raise ValueError("pull request changed file patch must be a string or None")
        _require_non_negative_int(self.additions, "pull request changed file additions")
        _require_non_negative_int(self.deletions, "pull request changed file deletions")
        _require_non_empty(self.status, "pull request changed file status")
        _require_optional_non_empty(self.previous_path, "pull request changed file previous_path")
        _require_non_empty(self.patch_status, "pull request changed file patch_status")
        if self.patch is None and self.patch_status == "available":
            raise ValueError("pull request changed file patch_status must explain missing patch")


@dataclass(frozen=True)
class PullRequestContext:
    review_target: ReviewTarget
    title: str
    body: str | None
    labels: tuple[str, ...]
    changed_files: tuple[PullRequestChangedFile, ...]
    comments: tuple[PullRequestComment, ...] = field(default_factory=tuple)
    reviews: tuple[PullRequestReview, ...] = field(default_factory=tuple)
    review_threads: tuple[PullRequestReviewThread, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.review_target, ReviewTarget):
            raise ValueError("pull request context review_target must be a ReviewTarget")
        _require_non_empty(self.title, "pull request context title")
        if self.body is not None and not isinstance(self.body, str):
            raise ValueError("pull request context body must be a string or None")
        _require_string_tuple(self.labels, "pull request context labels")
        _require_instance_tuple(self.changed_files, "pull request context changed_files", PullRequestChangedFile)
        if not self.changed_files:
            raise ValueError("pull request context changed_files must not be empty")
        _require_instance_tuple(self.comments, "pull request context comments", PullRequestComment)
        _require_instance_tuple(self.reviews, "pull request context reviews", PullRequestReview)
        _require_instance_tuple(
            self.review_threads,
            "pull request context review_threads",
            PullRequestReviewThread,
        )


@dataclass(frozen=True)
class PRConversationMemory:
    entries: tuple[MemoryReference, ...]


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


@dataclass(frozen=True)
class OmittedContextMarker:
    id: str
    source: str
    reason_code: str
    dimension: str
    affected_id: str
    original_count: int | None = None
    retained_count: int | None = None
    original_bytes: int | None = None
    retained_bytes: int | None = None

    def __post_init__(self) -> None:
        for name in ("id", "source", "reason_code", "dimension", "affected_id"):
            _require_non_empty(getattr(self, name), f"omitted context {name}")
        for name in ("original_count", "retained_count", "original_bytes", "retained_bytes"):
            value = getattr(self, name)
            if value is not None:
                _require_non_negative_int(value, f"omitted context {name}")


@dataclass(frozen=True)
class ContextBudget:
    max_changed_files: int
    max_patch_bytes: int
    max_memory_bytes: int
    max_reviewers: int
    max_live_calls: int
    truncation: tuple[TruncationNotice, ...] = field(default_factory=tuple)
    omitted_context: tuple[OmittedContextMarker, ...] = field(default_factory=tuple)
    original_changed_file_count: int = 0
    retained_changed_file_count: int = 0
    original_patch_bytes: int = 0
    retained_patch_bytes: int = 0
    original_memory_count: int = 0
    retained_memory_count: int = 0
    original_memory_bytes: int = 0
    retained_memory_bytes: int = 0
    original_reviewer_count: int = 0
    retained_reviewer_count: int = 0
    planned_live_calls: int = 0
    retained_file_paths: tuple[str, ...] = field(default_factory=tuple)
    omitted_file_paths: tuple[str, ...] = field(default_factory=tuple)
    retained_memory_ids: tuple[str, ...] = field(default_factory=tuple)
    omitted_memory_ids: tuple[str, ...] = field(default_factory=tuple)
    retained_reviewer_ids: tuple[str, ...] = field(default_factory=tuple)
    deferred_reviewer_ids: tuple[str, ...] = field(default_factory=tuple)
    retained_live_call_reviewer_ids: tuple[str, ...] = field(default_factory=tuple)
    deferred_live_call_reviewer_ids: tuple[str, ...] = field(default_factory=tuple)
    generated_local_note_ids: tuple[str, ...] = field(default_factory=tuple)
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in (
            "max_changed_files",
            "max_patch_bytes",
            "max_memory_bytes",
            "max_reviewers",
        ):
            _require_positive_int(getattr(self, name), f"context budget {name}")
        _require_non_negative_int(self.max_live_calls, "context budget max_live_calls")
        _require_instance_tuple(self.truncation, "context budget truncation", TruncationNotice)
        _require_instance_tuple(self.omitted_context, "context budget omitted_context", OmittedContextMarker)
        for name in (
            "original_changed_file_count",
            "retained_changed_file_count",
            "original_patch_bytes",
            "retained_patch_bytes",
            "original_memory_count",
            "retained_memory_count",
            "original_memory_bytes",
            "retained_memory_bytes",
            "original_reviewer_count",
            "retained_reviewer_count",
            "planned_live_calls",
        ):
            _require_non_negative_int(getattr(self, name), f"context budget {name}")
        for name in (
            "retained_file_paths",
            "omitted_file_paths",
            "retained_memory_ids",
            "omitted_memory_ids",
            "retained_reviewer_ids",
            "deferred_reviewer_ids",
            "retained_live_call_reviewer_ids",
            "deferred_live_call_reviewer_ids",
            "generated_local_note_ids",
            "reasons",
        ):
            _require_string_tuple(getattr(self, name), f"context budget {name}")


@dataclass(frozen=True)
class RiskThresholds:
    changed_files_medium: int
    changed_files_high: int
    changed_lines_medium: int
    changed_lines_high: int
    risk_min: RiskLevel | None = None

    def __post_init__(self) -> None:
        _require_positive_int(self.changed_files_medium, "changed_files_medium")
        _require_positive_int(self.changed_files_high, "changed_files_high")
        _require_positive_int(self.changed_lines_medium, "changed_lines_medium")
        _require_positive_int(self.changed_lines_high, "changed_lines_high")
        if self.changed_files_high <= self.changed_files_medium:
            raise ValueError("changed_files_high must be greater than changed_files_medium")
        if self.changed_lines_high <= self.changed_lines_medium:
            raise ValueError("changed_lines_high must be greater than changed_lines_medium")
        if self.risk_min is not None and not isinstance(self.risk_min, RiskLevel):
            raise ValueError("risk_min must be a RiskLevel or None")


@dataclass(frozen=True)
class RiskAssessment:
    changed_file_count: int
    changed_line_count: int
    touched_surfaces: tuple[str, ...]
    labels: tuple[str, ...]
    diff_pattern_hints: tuple[str, ...]
    configured_thresholds: RiskThresholds
    risk_level: RiskLevel
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_negative_int(self.changed_file_count, "changed_file_count")
        _require_non_negative_int(self.changed_line_count, "changed_line_count")
        _require_string_tuple(self.touched_surfaces, "touched_surfaces")
        _require_string_tuple(self.labels, "labels")
        _require_string_tuple(self.diff_pattern_hints, "diff_pattern_hints")
        _require_string_tuple(self.reasons, "reasons", allow_empty=False)
        if not isinstance(self.configured_thresholds, RiskThresholds):
            raise ValueError("configured_thresholds must be a RiskThresholds value")
        if not isinstance(self.risk_level, RiskLevel):
            raise ValueError("risk_level must be a RiskLevel value")


@dataclass(frozen=True)
class ReviewerTriggers:
    always: bool = False
    paths: tuple[str, ...] = field(default_factory=tuple)
    labels: tuple[str, ...] = field(default_factory=tuple)
    diff_patterns: tuple[str, ...] = field(default_factory=tuple)
    conversation_patterns: tuple[str, ...] = field(default_factory=tuple)
    risk_min: RiskLevel | None = None
    max_files: int | None = None
    changed_lines_min: int | None = None
    changed_files_min: int | None = None

    def __post_init__(self) -> None:
        if type(self.always) is not bool:
            raise ValueError("reviewer trigger always must be a boolean")
        _require_string_tuple(self.paths, "reviewer trigger paths")
        _require_string_tuple(self.labels, "reviewer trigger labels")
        _require_string_tuple(self.diff_patterns, "reviewer trigger diff_patterns")
        _require_string_tuple(self.conversation_patterns, "reviewer trigger conversation_patterns")
        if self.risk_min is not None and not isinstance(self.risk_min, RiskLevel):
            raise ValueError("reviewer trigger risk_min must be a RiskLevel or None")
        _require_optional_positive_int(self.max_files, "reviewer trigger max_files")
        _require_optional_positive_int(self.changed_lines_min, "reviewer trigger changed_lines_min")
        _require_optional_positive_int(self.changed_files_min, "reviewer trigger changed_files_min")
        if not any(
            (
                self.always,
                self.paths,
                self.labels,
                self.diff_patterns,
                self.conversation_patterns,
                self.risk_min is not None,
                self.max_files is not None,
                self.changed_lines_min is not None,
                self.changed_files_min is not None,
            )
        ):
            raise ValueError("reviewer trigger must include at least one selector or gate")


@dataclass(frozen=True)
class ReviewerAgentConfig:
    name: str
    description: str | None
    stages: tuple[ReviewStage, ...]
    triggers: ReviewerTriggers
    required: bool = False
    verdict_power: str = "comment"
    capabilities: tuple[str, ...] = ("diff_context",)
    model: str | None = None
    context: str | None = None
    tools: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_non_empty(self.name, "reviewer agent name")
        _require_optional_non_empty(self.description, "reviewer agent description")
        _require_optional_non_empty(self.model, "reviewer agent model")
        _require_optional_non_empty(self.context, "reviewer agent context")
        _require_string_tuple(self.tools, "reviewer agent tools")
        if len(set(self.tools)) != len(self.tools):
            raise ValueError("reviewer agent tools must not contain duplicates")
        _require_inert_tool_identifiers(self.tools, "reviewer agent tools")
        if not isinstance(self.stages, tuple) or not self.stages:
            raise ValueError("reviewer agent stages must be a non-empty tuple")
        if any(not isinstance(stage, ReviewStage) for stage in self.stages):
            raise ValueError("reviewer agent stages must contain ReviewStage values")
        if len(set(self.stages)) != len(self.stages):
            raise ValueError("reviewer agent stages must not contain duplicates")
        if not isinstance(self.triggers, ReviewerTriggers):
            raise ValueError("reviewer agent triggers must be a ReviewerTriggers value")
        if type(self.required) is not bool:
            raise ValueError("reviewer agent required must be a boolean")
        if not isinstance(self.verdict_power, str) or self.verdict_power not in ALLOWED_REVIEWER_VERDICT_POWERS:
            raise ValueError("reviewer agent has unsupported verdict_power")
        _require_string_tuple(self.capabilities, "reviewer agent capabilities", allow_empty=False)
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("reviewer agent capabilities must not contain duplicates")
        if unsupported := sorted(set(self.capabilities) - ALLOWED_REVIEWER_CAPABILITIES):
            raise ValueError(f"reviewer agent has unsupported capabilities: {', '.join(unsupported)}")


@dataclass(frozen=True)
class ReviewConfig:
    agents: Mapping[str, ReviewerAgentConfig]
    trusted_operator_authors: tuple[str, ...] = field(default_factory=tuple)
    trusted_bot_authors: tuple[str, ...] = field(default_factory=tuple)
    context_budget: ContextBudget | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.agents, Mapping):
            raise ValueError("review config agents must be a mapping")
        for name, agent in self.agents.items():
            if not isinstance(name, str) or not name:
                raise ValueError("review config agent names must be non-empty strings")
            if not isinstance(agent, ReviewerAgentConfig):
                raise ValueError("review config agents must contain ReviewerAgentConfig values")
            if agent.name != name:
                raise ValueError("review config agent mapping key must match reviewer agent name")
        _require_string_tuple(self.trusted_operator_authors, "review config trusted_operator_authors")
        _require_string_tuple(self.trusted_bot_authors, "review config trusted_bot_authors")
        if self.context_budget is not None and not isinstance(self.context_budget, ContextBudget):
            raise ValueError("review config context_budget must be a ContextBudget value")
        if len(set(self.trusted_operator_authors)) != len(self.trusted_operator_authors):
            raise ValueError("review config trusted_operator_authors must not contain duplicates")
        if len(set(self.trusted_bot_authors)) != len(self.trusted_bot_authors):
            raise ValueError("review config trusted_bot_authors must not contain duplicates")
        object.__setattr__(self, "agents", MappingProxyType(dict(self.agents)))


@dataclass(frozen=True)
class ReadGap:
    resource: str
    required: bool
    reason: str
    retryable: bool = False


@dataclass(frozen=True)
class PostingPlanItem:
    id: str
    source_classification: str
    destination: PostingDestination
    public_payload_eligible: bool
    fingerprint: str | None = None
    body: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "posting plan item id")
        _require_non_empty(self.source_classification, "posting plan item source_classification")
        if not isinstance(self.destination, PostingDestination):
            raise ValueError("posting plan item destination must be a PostingDestination")
        if type(self.public_payload_eligible) is not bool:
            raise ValueError("posting plan item public_payload_eligible must be a boolean")
        _require_optional_non_empty(self.fingerprint, "posting plan item fingerprint")
        _require_optional_non_empty(self.body, "posting plan item body")
        if self.public_payload_eligible and self.destination not in {
            PostingDestination.TOP_LEVEL_SUMMARY_ITEM,
            PostingDestination.REVIEW_BODY_ITEM,
        }:
            raise ValueError("public payload posting plan items must use a public payload destination")


@dataclass(frozen=True)
class PostingPlan:
    items: tuple[PostingPlanItem, ...]

    def __post_init__(self) -> None:
        _require_instance_tuple(self.items, "posting plan items", PostingPlanItem)
        item_ids = [item.id for item in self.items]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("posting plan item ids must be unique")

    @property
    def public_payload_items(self) -> tuple[PostingPlanItem, ...]:
        return tuple(item for item in self.items if item.public_payload_eligible)


@dataclass(frozen=True)
class GitHubReviewPayload:
    artifact_kind: ArtifactKind
    review_target: ReviewTarget
    body: str
    visible_body_hash: str
    full_body_hash: str
    findings_hash: str
    item_fingerprints: tuple[str, ...]
    redaction_status: RedactionStatus

    def __post_init__(self) -> None:
        _require_issue_comment_artifact(self.artifact_kind, "github review payload artifact_kind")
        if not isinstance(self.review_target, ReviewTarget):
            raise ValueError("github review payload review_target must be a ReviewTarget")
        _require_non_empty(self.body, "github review payload body")
        _require_hash_like(self.visible_body_hash, "github review payload visible_body_hash")
        _require_hash_like(self.full_body_hash, "github review payload full_body_hash")
        _require_hash_like(self.findings_hash, "github review payload findings_hash")
        _require_string_tuple(self.item_fingerprints, "github review payload item_fingerprints")
        if not isinstance(self.redaction_status, RedactionStatus):
            raise ValueError("github review payload redaction_status must be a RedactionStatus")


CandidateIssueCommentPayload: TypeAlias = GitHubReviewPayload


@dataclass(frozen=True)
class ActorPermissionGateResult:
    status: GateStatus
    actor: str | None
    permission: str | None
    checked_at: str | None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GateStatus):
            raise ValueError("actor permission gate status must be a GateStatus")
        _require_optional_non_empty(self.actor, "actor permission gate actor")
        _require_optional_non_empty(self.permission, "actor permission gate permission")
        _require_optional_non_empty(self.checked_at, "actor permission gate checked_at")
        _require_optional_non_empty(self.reason, "actor permission gate reason")
        if self.status == GateStatus.PASS:
            for name in ("actor", "permission", "checked_at"):
                if getattr(self, name) is None:
                    raise ValueError(f"actor permission gate pass requires {name}")


@dataclass(frozen=True)
class PayloadValidationResult:
    status: GateStatus
    payload_hash: str | None
    target_hash: str | None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GateStatus):
            raise ValueError("payload validation status must be a GateStatus")
        _require_optional_hash_like(self.payload_hash, "payload validation payload_hash")
        _require_optional_hash_like(self.target_hash, "payload validation target_hash")
        _require_optional_non_empty(self.reason, "payload validation reason")
        if self.status == GateStatus.PASS:
            for name in ("payload_hash", "target_hash"):
                if getattr(self, name) is None:
                    raise ValueError(f"payload validation pass requires {name}")


@dataclass(frozen=True)
class MarkerReconciliationResult:
    status: GateStatus
    trusted_actor: str | None
    existing_comment_id: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GateStatus):
            raise ValueError("marker reconciliation status must be a GateStatus")
        _require_optional_non_empty(self.trusted_actor, "marker reconciliation trusted_actor")
        _require_optional_non_empty(self.existing_comment_id, "marker reconciliation existing_comment_id")
        _require_optional_non_empty(self.reason, "marker reconciliation reason")
        if self.status == GateStatus.PASS and self.trusted_actor is None:
            raise ValueError("marker reconciliation pass requires trusted_actor")


@dataclass(frozen=True)
class FinalizationStatus:
    state: FinalizationState
    final_payload_hash: str | None
    target_hash: str | None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, FinalizationState):
            raise ValueError("finalization state must be a FinalizationState")
        _require_optional_hash_like(self.final_payload_hash, "finalization final_payload_hash")
        _require_optional_hash_like(self.target_hash, "finalization target_hash")
        _require_optional_non_empty(self.reason, "finalization reason")
        if self.state == FinalizationState.FINALIZED:
            for name in ("final_payload_hash", "target_hash"):
                if getattr(self, name) is None:
                    raise ValueError(f"finalized status requires {name}")


@dataclass(frozen=True)
class ApprovalDecision:
    approved: bool
    approved_item_ids: tuple[str, ...]
    approved_final_payload_hash: str
    approved_review_target_hash: str
    approved_review_target: ReviewTarget
    approved_github_actor: str
    approved_permission: str
    approved_permission_checked_at: str
    include_public_verdict: bool
    approved_by: str
    timestamp: str

    def __post_init__(self) -> None:
        if type(self.approved) is not bool:
            raise ValueError("approval approved must be a boolean")
        _require_string_tuple(self.approved_item_ids, "approval approved_item_ids")
        _require_hash_like(self.approved_final_payload_hash, "approval approved_final_payload_hash")
        _require_hash_like(self.approved_review_target_hash, "approval approved_review_target_hash")
        if not isinstance(self.approved_review_target, ReviewTarget):
            raise ValueError("approval approved_review_target must be a ReviewTarget")
        if self.approved_review_target_hash != self.approved_review_target.target_hash():
            raise ValueError("approval approved_review_target_hash must match approved_review_target")
        for name in (
            "approved_github_actor",
            "approved_permission",
            "approved_permission_checked_at",
            "approved_by",
            "timestamp",
        ):
            _require_non_empty(getattr(self, name), f"approval {name}")
        if type(self.include_public_verdict) is not bool:
            raise ValueError("approval include_public_verdict must be a boolean")
        if self.approved and not self.approved_item_ids:
            raise ValueError("approved decision requires approved_item_ids")


@dataclass(frozen=True)
class GitHubWriterResult:
    status: WriterStatus
    artifact_kind: ArtifactKind
    target_hash: str
    payload_hash: str
    comment_id: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, WriterStatus):
            raise ValueError("github writer status must be a WriterStatus")
        _require_issue_comment_artifact(self.artifact_kind, "github writer artifact_kind")
        _require_hash_like(self.target_hash, "github writer target_hash")
        _require_hash_like(self.payload_hash, "github writer payload_hash")
        _require_optional_non_empty(self.comment_id, "github writer comment_id")
        _require_optional_non_empty(self.error, "github writer error")
        if self.status in {WriterStatus.POSTED, WriterStatus.RECONCILED} and self.comment_id is None:
            raise ValueError("posted or reconciled writer result requires comment_id")
        if self.status == WriterStatus.FAILED and self.error is None:
            raise ValueError("failed writer result requires error")


@dataclass(frozen=True)
class GraphError:
    code: str
    message: str
    retryable: bool = False


@dataclass
class ReviewState:
    run_id: str
    run_mode: RunMode
    post_enabled: bool
    pr_ref: str
    review_target: ReviewTarget
    posting_target: PostingTarget | None
    pr: PullRequestContext | None
    conversation_memory: PRConversationMemory | None
    read_gaps: list[ReadGap]
    config: ReviewConfig
    config_hash: str
    stage_queue: list[ReviewStage]
    active_stage: ReviewStage | None
    suspended_stage: ReviewStage | None
    completed_stages: list[ReviewStage]
    risk: RiskAssessment | None
    selected_reviewers: list[SelectedReviewer]
    reviewer_run_keys: list[ReviewerRunKey]
    reviewer_run_status: dict[str, ReviewerRunStatus]
    reviewer_results: list[ReviewerResult]
    context_budget: ContextBudget
    redaction_status: RedactionStatus | None
    findings: list[Finding]
    local_notes: list[LocalNote]
    suggested_replies: list[SuggestedReply]
    suppressed_outputs: list[SuppressedReviewerOutput]
    clarification_requests: list[ClarificationRequest]
    pending_clarification_ids: list[str]
    ready_clarification_ids: list[str]
    active_clarification_id: str | None
    clarifications: list[ClarificationAnswer]
    clarification_status: dict[str, ClarificationStatus]
    ranked_findings: list[Finding]
    local_verdict: ReviewVerdict | None
    rendered_markdown: str | None
    posting_plan: PostingPlan | None
    actor_permission_gate: ActorPermissionGateResult | None
    payload_validation: PayloadValidationResult | None
    marker_reconciliation: MarkerReconciliationResult | None
    finalization_status: FinalizationStatus | None
    candidate_github_payload: GitHubReviewPayload | None
    final_github_payload: GitHubReviewPayload | None
    candidate_payload_hash: str | None
    final_payload_hash: str | None
    approval: ApprovalDecision | None
    writer_result: GitHubWriterResult | None
    errors: list[GraphError]

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(field.name for field in fields(cls))
