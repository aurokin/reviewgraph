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


class PayloadValidationReasonCode(StrEnum):
    WRONG_ARTIFACT_KIND = "wrong_artifact_kind"
    REDACTION_NOT_PASSED = "redaction_not_passed"
    CANDIDATE_CONTAINS_MARKER = "candidate_contains_marker"
    CANDIDATE_BINDING_MISMATCH = "candidate_binding_mismatch"
    NOT_FINAL_PAYLOAD = "not_final_payload"
    BODY_HASH_MISMATCH = "body_hash_mismatch"
    FINDINGS_HASH_MISMATCH = "findings_hash_mismatch"
    DUPLICATE_FINGERPRINTS = "duplicate_fingerprints"
    TARGET_HASH_MISMATCH = "target_hash_mismatch"
    MARKER_NOT_FINAL_LINE = "marker_not_final_line"
    MARKER_FIELD_MISMATCH = "marker_field_mismatch"
    FINAL_PAYLOAD_HASH_MISMATCH = "final_payload_hash_mismatch"
    WRONG_METHOD = "wrong_method"
    WRONG_ENDPOINT = "wrong_endpoint"
    REQUEST_TARGET_MISMATCH = "request_target_mismatch"
    WRONG_REQUEST_BODY = "wrong_request_body"
    FORMAL_REVIEW_PAYLOAD_REJECTED = "formal_review_payload_rejected"


class ApprovalProofReasonCode(StrEnum):
    EMPTY_APPROVAL = "empty_approval"
    UNKNOWN_APPROVED_ID = "unknown_approved_id"
    NON_PUBLIC_DESTINATION = "non_public_destination"
    SUMMARY_ITEM_DEFERRED = "summary_item_deferred"
    CANDIDATE_BINDING_MISMATCH = "candidate_binding_mismatch"
    DUPLICATE_APPROVED_FINGERPRINT = "duplicate_approved_fingerprint"
    FINAL_REDACTION_FAILED = "final_redaction_failed"
    INVALID_RUN_ID = "invalid_run_id"
    REQUEST_CHANGES_PUBLIC_TEXT_DEFERRED = "request_changes_public_text_deferred"


class ApprovalDecisionBuildReasonCode(StrEnum):
    APPROVAL_PROOF_FAILED = "approval_proof_failed"
    ACTOR_PERMISSION_GATE_FAILED = "actor_permission_gate_failed"
    ACTOR_PERMISSION_TARGET_MISMATCH = "actor_permission_target_mismatch"


class ActorPermissionReasonCode(StrEnum):
    UNKNOWN_ACTOR = "unknown_actor"
    UNKNOWN_CREDENTIAL_SOURCE = "unknown_credential_source"
    UNKNOWN_PERMISSION = "unknown_permission"
    INSUFFICIENT_ENDPOINT_PERMISSION = "insufficient_endpoint_permission"
    MISSING_CREDENTIAL_PRINCIPAL = "missing_credential_principal"
    MISSING_CHECK_METHOD = "missing_check_method"
    MISSING_CHECKED_TARGET = "missing_checked_target"
    MISSING_CHECKED_AT = "missing_checked_at"
    TARGET_MISMATCH = "target_mismatch"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    STALE_CACHED_PROOF = "stale_cached_proof"


class ActorPermissionFinalizationReasonCode(StrEnum):
    ACTOR_PERMISSION_GATE_FAILED = "actor_permission_gate_failed"
    ACTOR_PERMISSION_SNAPSHOT_MISMATCH = "actor_permission_snapshot_mismatch"
    ACTOR_PERMISSION_CHECKED_AT_REGRESSED = "actor_permission_checked_at_regressed"


class TargetFreshnessReasonCode(StrEnum):
    TARGET_MISMATCH = "target_mismatch"
    MISSING_MERGE_BASE = "missing_merge_base"
    MISSING_CHECKED_AT = "missing_checked_at"
    STALE_CACHED_TARGET = "stale_cached_target"
    FUTURE_CHECKED_AT = "future_checked_at"
    CHECKED_AT_BEFORE_APPROVAL = "checked_at_before_approval"
    UNKNOWN_FRESHNESS = "unknown_freshness"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    MALFORMED_RESPONSE = "malformed_response"


class FinalizationReasonCode(StrEnum):
    APPROVAL_PREFLIGHT_FAILED = "approval_preflight_failed"
    ACTOR_PERMISSION_FAILED = "actor_permission_failed"
    TARGET_FRESHNESS_FAILED = "target_freshness_failed"
    PAYLOAD_VALIDATION_FAILED = "payload_validation_failed"
    MARKER_RECONCILIATION_DEFERRED = "marker_reconciliation_deferred"


class WriterReleasePreflightReasonCode(StrEnum):
    POST_DISABLED = "post_disabled"
    APPROVAL_BUILD_FAILED = "approval_build_failed"
    MISSING_APPROVAL = "missing_approval"
    REJECTED_APPROVAL = "rejected_approval"
    DUPLICATE_APPROVED_ITEM = "duplicate_approved_item"
    DUPLICATE_APPROVED_FINGERPRINT = "duplicate_approved_fingerprint"
    UNKNOWN_APPROVED_ID = "unknown_approved_id"
    NON_PUBLIC_APPROVED_ITEM = "non_public_approved_item"


class WriterReleaseItemReasonCode(StrEnum):
    MISSING_CURRENT_ITEM = "missing_current_item"
    MISSING_FINGERPRINT = "missing_fingerprint"
    NOT_PUBLIC_PAYLOAD_ELIGIBLE = "not_public_payload_eligible"
    WRONG_DESTINATION = "wrong_destination"
    WRONG_SOURCE_CLASSIFICATION = "wrong_source_classification"


class MarkerReconciliationStatus(StrEnum):
    SAFE_TO_POST = "safe_to_post"
    RECONCILED_EXISTING = "reconciled_existing"
    FAILED_CLOSED = "failed_closed"


class MarkerReconciliationReasonCode(StrEnum):
    SAFE_TO_POST = "safe_to_post"
    MATCHED_EXISTING = "matched_existing"
    PAGINATION_INCOMPLETE = "pagination_incomplete"
    REPEATED_CURSOR = "repeated_cursor"
    PAGE_CAP_EXCEEDED = "page_cap_exceeded"
    COMMENT_CAP_EXCEEDED = "comment_cap_exceeded"
    MALFORMED_PAGE = "malformed_page"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    UNAVAILABLE = "unavailable"
    TRANSPORT_UNKNOWN = "transport_unknown"
    TRUSTED_MARKER_CONFLICT = "trusted_marker_conflict"
    TRUSTED_MARKER_MALFORMED = "trusted_marker_malformed"


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
ALLOWED_ACTOR_PERMISSION_CREDENTIAL_SOURCES = frozenset(
    {"pat", "fine_grained_pat", "github_app_installation", "github_app_user"}
)
ALLOWED_ACTOR_PERMISSION_REPO_PERMISSIONS = frozenset({"read", "triage", "write", "maintain", "admin"})
WRITE_ACTOR_PERMISSION_REPO_PERMISSIONS = frozenset({"write", "maintain", "admin"})
ALLOWED_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS = frozenset(
    {"issues:read", "issues:write", "pull_requests:read", "pull_requests:write"}
)
WRITE_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS = frozenset({"issues:write", "pull_requests:write"})
ALLOWED_ACTOR_PERMISSION_REQUEST_ID_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:/#-"
)
SECRET_ACTOR_PERMISSION_REQUEST_ID_FRAGMENTS = ("token", "ghp_", "github_pat_", "gho_", "ghs_", "ghu_")
TRANSPORT_ACTOR_PERMISSION_REASON_CODES = frozenset(
    {
        ActorPermissionReasonCode.TIMEOUT,
        ActorPermissionReasonCode.RATE_LIMITED,
        ActorPermissionReasonCode.FORBIDDEN,
        ActorPermissionReasonCode.NOT_FOUND,
        ActorPermissionReasonCode.UNAVAILABLE,
        ActorPermissionReasonCode.MALFORMED_RESPONSE,
    }
)
RETRYABLE_ACTOR_PERMISSION_REASON_CODES = frozenset(
    {
        ActorPermissionReasonCode.TIMEOUT,
        ActorPermissionReasonCode.RATE_LIMITED,
        ActorPermissionReasonCode.UNAVAILABLE,
    }
)
ACTOR_PERMISSION_CHECK_METHOD = "fake_issue_comment_permission_probe"
ACTOR_PERMISSION_ENDPOINT_KIND = "issue_comment"
ACTOR_PERMISSION_ENDPOINT_METHOD = "POST"
ACTOR_PERMISSION_TRANSPORT_ENDPOINT_KIND = "issue_comment_permission"
TARGET_FRESHNESS_TRANSPORT_ENDPOINT_KIND = "pull_request_target"
MARKER_SCAN_ENDPOINT_KIND = "issue_comments"
TARGET_FRESHNESS_CHECK_METHOD = "fake_pull_request_target_probe"
TARGET_FRESHNESS_MISMATCH_FIELDS = frozenset(
    {"owner_repo", "pr_number", "base_sha", "head_sha", "merge_base_sha", "diff_basis", "checked_at"}
)
TARGET_FRESHNESS_TRANSPORT_REASON_CODES = frozenset(
    {
        TargetFreshnessReasonCode.TIMEOUT,
        TargetFreshnessReasonCode.RATE_LIMITED,
        TargetFreshnessReasonCode.FORBIDDEN,
        TargetFreshnessReasonCode.NOT_FOUND,
        TargetFreshnessReasonCode.UNAVAILABLE,
        TargetFreshnessReasonCode.MALFORMED_RESPONSE,
    }
)
TARGET_FRESHNESS_RETRYABLE_REASON_CODES = frozenset(
    {
        TargetFreshnessReasonCode.TIMEOUT,
        TargetFreshnessReasonCode.RATE_LIMITED,
        TargetFreshnessReasonCode.UNAVAILABLE,
    }
)
RETRYABLE_MARKER_RECONCILIATION_REASON_CODES = frozenset(
    {
        MarkerReconciliationReasonCode.TIMEOUT,
        MarkerReconciliationReasonCode.RATE_LIMITED,
        MarkerReconciliationReasonCode.UNAVAILABLE,
        MarkerReconciliationReasonCode.TRANSPORT_UNKNOWN,
    }
)
ACTOR_PERMISSION_FINALIZATION_MISMATCH_FIELDS = frozenset(
    {
        "actor",
        "credential_principal",
        "credential_source",
        "permission",
        "repo_permission",
        "installation_permission",
        "endpoint_permission",
        "issue_comment_write",
        "check_method",
        "endpoint_method",
        "checked_target",
        "checked_target_hash",
        "endpoint",
        "endpoint_kind",
        "checked_at",
    }
)


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


def _require_strict_sha256(value: str, field_name: str) -> None:
    _require_hash_like(value, field_name)
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"{field_name} must be a strict sha256 hash")


def _parse_reviewgraph_marker(marker_line: str) -> dict[str, str] | None:
    prefix = "<!-- reviewgraph:v1 "
    suffix = " -->"
    if not isinstance(marker_line, str) or not marker_line.startswith(prefix) or not marker_line.endswith(suffix):
        return None
    body = marker_line[len(prefix) : -len(suffix)]
    parts = body.split(" ")
    if len(parts) != 4:
        return None
    fields: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            return None
        key, value = part.split("=", 1)
        if key in fields or key not in {"run_id", "target", "payload", "findings"}:
            return None
        fields[key] = value
    if tuple(fields) != ("run_id", "target", "payload", "findings"):
        return None
    run_id = fields["run_id"]
    allowed_run_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:/#-")
    if not run_id or len(run_id) > 128 or not run_id[0].isalnum() or any(char not in allowed_run_chars for char in run_id):
        return None
    for key in ("target", "payload", "findings"):
        try:
            _require_strict_sha256(fields[key], f"marker {key}")
        except ValueError:
            return None
    return fields


def _is_rfc3339_utc_z(value: str) -> bool:
    if not isinstance(value, str) or len(value) < 20 or not value.endswith("Z"):
        return False
    date_time = value[:-1]
    if "T" not in date_time:
        return False
    date, time = date_time.split("T", 1)
    if len(date) != 10 or date[4] != "-" or date[7] != "-":
        return False
    if len(time) < 8 or time[2] != ":" or time[5] != ":":
        return False
    year = date[0:4]
    month = date[5:7]
    day = date[8:10]
    hour = time[0:2]
    minute = time[3:5]
    second = time[6:8]
    if not all(part.isdecimal() for part in (year, month, day, hour, minute, second)):
        return False
    remainder = time[8:]
    if not remainder:
        return True
    return (
        len(remainder) > 1
        and remainder[0] == "."
        and all(char.isdecimal() for char in remainder[1:])
    )


def _is_realistic_rfc3339_utc_z(value: str) -> bool:
    if not _is_rfc3339_utc_z(value):
        return False
    date_time = value[:-1]
    date, time = date_time.split("T", 1)
    year = int(date[0:4])
    month = int(date[5:7])
    day = int(date[8:10])
    hour = int(time[0:2])
    minute = int(time[3:5])
    second = int(time[6:8])
    if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 23 and minute <= 59 and second <= 59):
        return False
    days_by_month = (31, 29 if _is_leap_year(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return day <= days_by_month[month - 1]


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _is_safe_actor_permission_identity(value: str) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if len(value) > 128:
        return False
    allowed = ALLOWED_ACTOR_PERMISSION_REQUEST_ID_CHARS | frozenset("[]@")
    if any(char not in allowed for char in value):
        return False
    return not any(
        secret in value.casefold() for secret in SECRET_ACTOR_PERMISSION_REQUEST_ID_FRAGMENTS
    )


def _is_safe_actor_permission_reason(value: str) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if len(value) > 256:
        return False
    if any(secret in value.casefold() for secret in SECRET_ACTOR_PERMISSION_REQUEST_ID_FRAGMENTS):
        return False
    return all(char in "\n\r\t" or 32 <= ord(char) <= 126 for char in value)


def _actor_permission_expected_endpoint(checked_target: Mapping[str, object]) -> str | None:
    if tuple(checked_target) != ("owner_repo", "pr_number", "base_sha", "head_sha", "merge_base_sha", "diff_basis"):
        return None
    owner_repo = checked_target.get("owner_repo")
    pr_number = checked_target.get("pr_number")
    base_sha = checked_target.get("base_sha")
    head_sha = checked_target.get("head_sha")
    merge_base_sha = checked_target.get("merge_base_sha")
    diff_basis = checked_target.get("diff_basis")
    if not isinstance(owner_repo, str) or "/" not in owner_repo:
        return None
    if type(pr_number) is not int or pr_number <= 0:
        return None
    if not isinstance(base_sha, str) or not base_sha:
        return None
    if not isinstance(head_sha, str) or not head_sha:
        return None
    if merge_base_sha is not None and not isinstance(merge_base_sha, str):
        return None
    if not isinstance(diff_basis, str) or not diff_basis:
        return None
    owner, repo = owner_repo.split("/", 1)
    return f"/repos/{owner}/{repo}/issues/{pr_number}/comments"


def _actor_permission_derived_permission(
    *,
    credential_source: str | None,
    repo_permission: str | None,
    installation_permission: str | None,
    endpoint_permission: str | None,
) -> str | None:
    if credential_source not in ALLOWED_ACTOR_PERMISSION_CREDENTIAL_SOURCES:
        return None
    if repo_permission is not None and repo_permission not in ALLOWED_ACTOR_PERMISSION_REPO_PERMISSIONS:
        return None
    if (
        installation_permission is not None
        and installation_permission not in ALLOWED_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS
    ):
        return None
    if endpoint_permission is not None and endpoint_permission not in ALLOWED_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS:
        return None
    if credential_source == "pat":
        if installation_permission is not None or endpoint_permission is not None:
            return None
        permission = repo_permission
    elif credential_source == "fine_grained_pat":
        if repo_permission is not None or installation_permission is not None:
            return None
        permission = endpoint_permission
    elif credential_source == "github_app_installation":
        if repo_permission is not None or installation_permission is None:
            return None
        if endpoint_permission is not None and endpoint_permission != installation_permission:
            return None
        permission = installation_permission
    elif credential_source == "github_app_user":
        if repo_permission is not None or installation_permission is not None:
            return None
        permission = endpoint_permission
    else:
        return None
    if permission in WRITE_ACTOR_PERMISSION_REPO_PERMISSIONS:
        return permission
    if permission in WRITE_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS:
        return permission
    return None


def _actor_permission_failure_permission(
    repo_permission: str | None,
    installation_permission: str | None,
    endpoint_permission: str | None,
) -> str | None:
    if repo_permission is not None and repo_permission in ALLOWED_ACTOR_PERMISSION_REPO_PERMISSIONS:
        return repo_permission
    if (
        installation_permission is not None
        and installation_permission in ALLOWED_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS
    ):
        return installation_permission
    if endpoint_permission is not None and endpoint_permission in ALLOWED_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS:
        return endpoint_permission
    return None


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
class CandidateIssueCommentPayload:
    artifact_kind: ArtifactKind
    review_target: ReviewTarget
    body: str
    visible_body_hash: str
    findings_hash: str
    item_fingerprints: tuple[str, ...]
    redaction_status: RedactionStatus

    def __post_init__(self) -> None:
        _require_issue_comment_artifact(self.artifact_kind, "candidate issue comment payload artifact_kind")
        if not isinstance(self.review_target, ReviewTarget):
            raise ValueError("candidate issue comment payload review_target must be a ReviewTarget")
        _require_non_empty(self.body, "candidate issue comment payload body")
        _require_hash_like(self.visible_body_hash, "candidate issue comment payload visible_body_hash")
        _require_hash_like(self.findings_hash, "candidate issue comment payload findings_hash")
        _require_string_tuple(self.item_fingerprints, "candidate issue comment payload item_fingerprints")
        if not isinstance(self.redaction_status, RedactionStatus):
            raise ValueError("candidate issue comment payload redaction_status must be a RedactionStatus")


@dataclass(frozen=True)
class FinalIssueCommentPayload:
    artifact_kind: ArtifactKind
    review_target: ReviewTarget
    body: str
    marker_line: str
    marker_run_id: str
    marker_target_hash: str
    marker_payload_hash: str
    marker_findings_hash: str
    visible_body_hash: str
    final_payload_hash: str
    findings_hash: str
    item_fingerprints: tuple[str, ...]
    redaction_status: RedactionStatus

    def __post_init__(self) -> None:
        _require_issue_comment_artifact(self.artifact_kind, "final issue comment payload artifact_kind")
        if not isinstance(self.review_target, ReviewTarget):
            raise ValueError("final issue comment payload review_target must be a ReviewTarget")
        _require_non_empty(self.body, "final issue comment payload body")
        _require_non_empty(self.marker_line, "final issue comment payload marker_line")
        _require_non_empty(self.marker_run_id, "final issue comment payload marker_run_id")
        _require_hash_like(self.marker_target_hash, "final issue comment payload marker_target_hash")
        _require_hash_like(self.marker_payload_hash, "final issue comment payload marker_payload_hash")
        _require_hash_like(self.marker_findings_hash, "final issue comment payload marker_findings_hash")
        _require_hash_like(self.visible_body_hash, "final issue comment payload visible_body_hash")
        _require_hash_like(self.final_payload_hash, "final issue comment payload final_payload_hash")
        _require_hash_like(self.findings_hash, "final issue comment payload findings_hash")
        _require_string_tuple(self.item_fingerprints, "final issue comment payload item_fingerprints")
        if not isinstance(self.redaction_status, RedactionStatus):
            raise ValueError("final issue comment payload redaction_status must be a RedactionStatus")


GitHubReviewPayload: TypeAlias = FinalIssueCommentPayload


@dataclass(frozen=True)
class GitHubIssueCommentRequest:
    method: str
    endpoint: str
    body: Mapping[str, object]
    payload: FinalIssueCommentPayload

    def __post_init__(self) -> None:
        _require_non_empty(self.method, "github issue comment request method")
        _require_non_empty(self.endpoint, "github issue comment request endpoint")
        if not isinstance(self.body, Mapping):
            raise ValueError("github issue comment request body must be a mapping")
        if not all(isinstance(key, str) for key in self.body):
            raise ValueError("github issue comment request body keys must be strings")
        if not isinstance(self.payload, FinalIssueCommentPayload):
            raise ValueError("github issue comment request payload must be a FinalIssueCommentPayload")


@dataclass(frozen=True)
class PostInteractionGateResult:
    status: GateStatus
    interactive: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GateStatus):
            raise ValueError("post interaction gate status must be a GateStatus")
        if not isinstance(self.interactive, bool):
            raise ValueError("post interaction gate interactive must be a bool")
        _require_optional_non_empty(self.reason, "post interaction gate reason")
        if self.status == GateStatus.PASS and not self.interactive:
            raise ValueError("post interaction gate pass requires interactive human approval surface")


@dataclass(frozen=True)
class ActorPermissionTransportSummary:
    endpoint_kind: str
    retryable: bool
    reason_code: ActorPermissionReasonCode | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.endpoint_kind, "actor permission transport summary endpoint_kind")
        if self.endpoint_kind != ACTOR_PERMISSION_TRANSPORT_ENDPOINT_KIND:
            raise ValueError("actor permission transport summary endpoint_kind must be issue_comment_permission")
        if not isinstance(self.retryable, bool):
            raise ValueError("actor permission transport summary retryable must be a bool")
        if self.reason_code is not None and not isinstance(self.reason_code, ActorPermissionReasonCode):
            raise ValueError("actor permission transport summary reason_code must be an ActorPermissionReasonCode")
        _require_optional_non_empty(self.request_id, "actor permission transport summary request_id")
        if self.request_id is not None:
            if len(self.request_id) > 128 or any(
                char not in ALLOWED_ACTOR_PERMISSION_REQUEST_ID_CHARS for char in self.request_id
            ):
                raise ValueError("actor permission transport summary request_id must be allowlisted")
            if any(
                secret in self.request_id.casefold()
                for secret in SECRET_ACTOR_PERMISSION_REQUEST_ID_FRAGMENTS
            ):
                raise ValueError("actor permission transport summary request_id must not contain secrets")


@dataclass(frozen=True)
class ActorPermissionGateResult:
    status: GateStatus
    actor: str | None
    permission: str | None
    checked_at: str | None
    reason: str | None = None
    reason_code: ActorPermissionReasonCode | None = None
    credential_principal: str | None = None
    credential_source: str | None = None
    repo_permission: str | None = None
    installation_permission: str | None = None
    endpoint_permission: str | None = None
    issue_comment_write: bool | None = None
    check_method: str | None = None
    endpoint_method: str | None = None
    checked_target: Mapping[str, object] | None = None
    checked_target_hash: str | None = None
    endpoint: str | None = None
    endpoint_kind: str | None = None
    transport_summary: ActorPermissionTransportSummary | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GateStatus):
            raise ValueError("actor permission gate status must be a GateStatus")
        if self.status == GateStatus.UNKNOWN:
            raise ValueError("actor permission gate status must be pass or fail")
        _require_optional_non_empty(self.actor, "actor permission gate actor")
        _require_optional_non_empty(self.permission, "actor permission gate permission")
        _require_optional_non_empty(self.checked_at, "actor permission gate checked_at")
        _require_optional_non_empty(self.reason, "actor permission gate reason")
        if self.actor is not None and not _is_safe_actor_permission_identity(self.actor):
            raise ValueError("actor permission gate actor must be allowlisted")
        if self.credential_principal is not None and not _is_safe_actor_permission_identity(
            self.credential_principal
        ):
            raise ValueError("actor permission gate credential_principal must be allowlisted")
        if self.reason is not None and not _is_safe_actor_permission_reason(self.reason):
            raise ValueError("actor permission gate reason must be allowlisted")
        if self.reason_code is not None and not isinstance(self.reason_code, ActorPermissionReasonCode):
            raise ValueError("actor permission gate reason_code must be an ActorPermissionReasonCode")
        _require_optional_non_empty(self.credential_principal, "actor permission gate credential_principal")
        _require_optional_non_empty(self.credential_source, "actor permission gate credential_source")
        _require_optional_non_empty(self.repo_permission, "actor permission gate repo_permission")
        _require_optional_non_empty(self.installation_permission, "actor permission gate installation_permission")
        _require_optional_non_empty(self.endpoint_permission, "actor permission gate endpoint_permission")
        if self.issue_comment_write is not None and not isinstance(self.issue_comment_write, bool):
            raise ValueError("actor permission gate issue_comment_write must be a bool")
        _require_optional_non_empty(self.check_method, "actor permission gate check_method")
        _require_optional_non_empty(self.endpoint_method, "actor permission gate endpoint_method")
        if self.checked_target is not None:
            if not isinstance(self.checked_target, Mapping):
                raise ValueError("actor permission gate checked_target must be a mapping")
            if not all(isinstance(key, str) for key in self.checked_target):
                raise ValueError("actor permission gate checked_target keys must be strings")
            object.__setattr__(self, "checked_target", MappingProxyType(dict(self.checked_target)))
        _require_optional_hash_like(self.checked_target_hash, "actor permission gate checked_target_hash")
        _require_optional_non_empty(self.endpoint, "actor permission gate endpoint")
        _require_optional_non_empty(self.endpoint_kind, "actor permission gate endpoint_kind")
        if self.transport_summary is not None and not isinstance(
            self.transport_summary, ActorPermissionTransportSummary
        ):
            raise ValueError("actor permission gate transport_summary must be an ActorPermissionTransportSummary")
        if self.status == GateStatus.PASS:
            for name in (
                "actor",
                "permission",
                "checked_at",
                "credential_principal",
                "credential_source",
                "check_method",
                "endpoint_method",
                "checked_target",
                "checked_target_hash",
                "endpoint",
                "endpoint_kind",
                "transport_summary",
            ):
                if getattr(self, name) is None:
                    raise ValueError(f"actor permission gate pass requires {name}")
            if self.issue_comment_write is not True:
                raise ValueError("actor permission gate pass requires issue_comment_write")
            if self.reason_code is not None:
                raise ValueError("actor permission gate pass must not include reason_code")
            if self.reason is not None:
                raise ValueError("actor permission gate pass must not include reason")
            if self.permission in {"read", "triage", "issues:read", "pull_requests:read"}:
                raise ValueError("actor permission gate pass requires write permission")
            derived_permission = _actor_permission_derived_permission(
                credential_source=self.credential_source,
                repo_permission=self.repo_permission,
                installation_permission=self.installation_permission,
                endpoint_permission=self.endpoint_permission,
            )
            if derived_permission is None or self.permission != derived_permission:
                raise ValueError("actor permission gate pass permission proof is inconsistent")
            if self.check_method != ACTOR_PERMISSION_CHECK_METHOD:
                raise ValueError("actor permission gate pass requires permission check_method")
            if self.endpoint_method != ACTOR_PERMISSION_ENDPOINT_METHOD:
                raise ValueError("actor permission gate pass requires POST endpoint_method")
            if self.endpoint_kind != ACTOR_PERMISSION_ENDPOINT_KIND:
                raise ValueError("actor permission gate pass requires issue_comment endpoint_kind")
            if self.checked_at is not None and not _is_realistic_rfc3339_utc_z(self.checked_at):
                raise ValueError("actor permission gate pass requires UTC RFC3339 checked_at")
            if self.checked_target is not None:
                expected_endpoint = _actor_permission_expected_endpoint(self.checked_target)
                if expected_endpoint is None or self.endpoint != expected_endpoint:
                    raise ValueError("actor permission gate pass endpoint does not match checked_target")
                if self.checked_target_hash != _domain_json_hash(
                    "reviewgraph.review_target.v1", dict(self.checked_target)
                ):
                    raise ValueError("actor permission gate pass checked_target_hash mismatch")
            if self.transport_summary is not None:
                if self.transport_summary.endpoint_kind != ACTOR_PERMISSION_TRANSPORT_ENDPOINT_KIND:
                    raise ValueError("actor permission gate pass transport summary endpoint_kind mismatch")
                if self.transport_summary.reason_code is not None:
                    raise ValueError("actor permission gate pass transport summary must not include reason_code")
                if self.transport_summary.retryable:
                    raise ValueError("actor permission gate pass transport summary must not be retryable")
        if self.status == GateStatus.FAIL and self.reason_code is None:
            raise ValueError("actor permission gate failure requires reason_code")
        if self.status == GateStatus.FAIL and self.transport_summary is None:
            raise ValueError("actor permission gate failure requires transport_summary")
        if self.status == GateStatus.FAIL and self.transport_summary is not None and self.reason_code is not None:
            if self.permission is not None and self.permission != _actor_permission_failure_permission(
                self.repo_permission,
                self.installation_permission,
                self.endpoint_permission,
            ):
                raise ValueError("actor permission gate failure permission proof is unsafe")
            if self.checked_at is not None and not _is_realistic_rfc3339_utc_z(self.checked_at):
                raise ValueError("actor permission gate failure checked_at must be validated")
            if self.credential_source is not None and self.credential_source not in ALLOWED_ACTOR_PERMISSION_CREDENTIAL_SOURCES:
                raise ValueError("actor permission gate failure credential_source is unsafe")
            if self.repo_permission is not None and self.repo_permission not in ALLOWED_ACTOR_PERMISSION_REPO_PERMISSIONS:
                raise ValueError("actor permission gate failure repo_permission is unsafe")
            if (
                self.installation_permission is not None
                and self.installation_permission not in ALLOWED_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS
            ):
                raise ValueError("actor permission gate failure installation_permission is unsafe")
            if (
                self.endpoint_permission is not None
                and self.endpoint_permission not in ALLOWED_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS
            ):
                raise ValueError("actor permission gate failure endpoint_permission is unsafe")
            if self.check_method is not None and self.check_method != ACTOR_PERMISSION_CHECK_METHOD:
                raise ValueError("actor permission gate failure check_method is unsafe")
            if self.endpoint_method is not None and self.endpoint_method != ACTOR_PERMISSION_ENDPOINT_METHOD:
                raise ValueError("actor permission gate failure endpoint_method is unsafe")
            if self.endpoint_kind is not None and self.endpoint_kind != ACTOR_PERMISSION_ENDPOINT_KIND:
                raise ValueError("actor permission gate failure endpoint_kind is unsafe")
            if self.endpoint is not None:
                if self.checked_target is None:
                    raise ValueError("actor permission gate failure endpoint requires checked_target")
                expected_endpoint = _actor_permission_expected_endpoint(self.checked_target)
                if expected_endpoint is None or self.endpoint != expected_endpoint:
                    raise ValueError("actor permission gate failure endpoint is unsafe")
            transport_reason_code = self.transport_summary.reason_code
            if transport_reason_code is not None:
                if transport_reason_code not in TRANSPORT_ACTOR_PERMISSION_REASON_CODES:
                    raise ValueError("actor permission gate transport summary reason_code must be transport failure")
                if transport_reason_code != self.reason_code:
                    raise ValueError("actor permission gate transport summary reason_code mismatch")
            elif self.reason_code in TRANSPORT_ACTOR_PERMISSION_REASON_CODES - {ActorPermissionReasonCode.MALFORMED_RESPONSE}:
                if transport_reason_code != self.reason_code:
                    raise ValueError("actor permission gate transport summary reason_code mismatch")
            if self.transport_summary.retryable != (transport_reason_code in RETRYABLE_ACTOR_PERMISSION_REASON_CODES):
                raise ValueError("actor permission gate transport summary retryable mismatch")


@dataclass(frozen=True)
class PayloadValidationResult:
    status: GateStatus
    payload_hash: str | None
    target_hash: str | None
    reason_code: PayloadValidationReasonCode | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GateStatus):
            raise ValueError("payload validation status must be a GateStatus")
        _require_optional_hash_like(self.payload_hash, "payload validation payload_hash")
        _require_optional_hash_like(self.target_hash, "payload validation target_hash")
        if self.reason_code is not None and not isinstance(self.reason_code, PayloadValidationReasonCode):
            raise ValueError("payload validation reason_code must be a PayloadValidationReasonCode")
        _require_optional_non_empty(self.reason, "payload validation reason")
        if self.status == GateStatus.PASS:
            for name in ("payload_hash", "target_hash"):
                if getattr(self, name) is None:
                    raise ValueError(f"payload validation pass requires {name}")
            if self.reason_code is not None:
                raise ValueError("payload validation pass must not include reason_code")
        if self.status != GateStatus.PASS and self.reason_code is None:
            raise ValueError("payload validation failure requires reason_code")


@dataclass(frozen=True)
class ApprovalProofResult:
    status: GateStatus
    approved_item_ids: tuple[str, ...] = field(default_factory=tuple)
    approved_review_target: ReviewTarget | None = None
    approved_review_target_hash: str | None = None
    approved_final_payload_hash: str | None = None
    final_visible_body_hash: str | None = None
    marker_payload_hash: str | None = None
    findings_hash: str | None = None
    marker_line: str | None = None
    final_redaction_status: RedactionStatus | None = None
    include_public_verdict: bool = False
    approved_by: str | None = None
    timestamp: str | None = None
    reason_code: ApprovalProofReasonCode | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GateStatus):
            raise ValueError("approval proof status must be a GateStatus")
        _require_string_tuple(self.approved_item_ids, "approval proof approved_item_ids")
        if self.approved_review_target is not None and not isinstance(self.approved_review_target, ReviewTarget):
            raise ValueError("approval proof approved_review_target must be a ReviewTarget")
        _require_optional_hash_like(self.approved_review_target_hash, "approval proof approved_review_target_hash")
        _require_optional_hash_like(self.approved_final_payload_hash, "approval proof approved_final_payload_hash")
        _require_optional_hash_like(self.final_visible_body_hash, "approval proof final_visible_body_hash")
        _require_optional_hash_like(self.marker_payload_hash, "approval proof marker_payload_hash")
        _require_optional_hash_like(self.findings_hash, "approval proof findings_hash")
        _require_optional_non_empty(self.marker_line, "approval proof marker_line")
        if self.final_redaction_status is not None and not isinstance(self.final_redaction_status, RedactionStatus):
            raise ValueError("approval proof final_redaction_status must be a RedactionStatus")
        if type(self.include_public_verdict) is not bool:
            raise ValueError("approval proof include_public_verdict must be a boolean")
        _require_optional_non_empty(self.approved_by, "approval proof approved_by")
        _require_optional_non_empty(self.timestamp, "approval proof timestamp")
        if self.reason_code is not None and not isinstance(self.reason_code, ApprovalProofReasonCode):
            raise ValueError("approval proof reason_code must be an ApprovalProofReasonCode")
        _require_optional_non_empty(self.reason, "approval proof reason")
        proof_fields = (
            "approved_item_ids",
            "approved_review_target",
            "approved_review_target_hash",
            "approved_final_payload_hash",
            "final_visible_body_hash",
            "marker_payload_hash",
            "findings_hash",
            "marker_line",
            "final_redaction_status",
            "approved_by",
            "timestamp",
        )
        if self.status == GateStatus.PASS:
            for name in proof_fields:
                value = getattr(self, name)
                if value is None or value == ():
                    raise ValueError(f"approval proof pass requires {name}")
            if self.reason_code is not None:
                raise ValueError("approval proof pass must not include reason_code")
            if self.approved_review_target_hash != self.approved_review_target.target_hash():
                raise ValueError("approval proof approved_review_target_hash must match approved_review_target")
            if self.final_redaction_status.status != GateStatus.PASS:
                raise ValueError("approval proof pass requires passing final_redaction_status")
            marker = _parse_reviewgraph_marker(self.marker_line)
            if marker is None:
                raise ValueError("approval proof marker_line must match ReviewGraph v1 marker grammar")
            for name in (
                "approved_review_target_hash",
                "approved_final_payload_hash",
                "final_visible_body_hash",
                "marker_payload_hash",
                "findings_hash",
            ):
                _require_strict_sha256(getattr(self, name), f"approval proof {name}")
            if self.final_visible_body_hash != self.marker_payload_hash:
                raise ValueError("approval proof final_visible_body_hash must match marker_payload_hash")
            if marker["target"] != self.approved_review_target_hash:
                raise ValueError("approval proof marker target must match approved_review_target_hash")
            if marker["payload"] != self.marker_payload_hash:
                raise ValueError("approval proof marker payload must match marker_payload_hash")
            if marker["findings"] != self.findings_hash:
                raise ValueError("approval proof marker findings must match findings_hash")
        else:
            if self.reason_code is None:
                raise ValueError("approval proof failure requires reason_code")
            for name in proof_fields:
                value = getattr(self, name)
                if value is not None and value != ():
                    raise ValueError(f"approval proof failure must not include {name}")


@dataclass(frozen=True)
class MarkerScanTransportSummary:
    endpoint_kind: str
    page_count: int
    comment_count: int
    marker_count: int
    retryable: bool
    reason_code: MarkerReconciliationReasonCode | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.endpoint_kind, "marker scan transport summary endpoint_kind")
        if self.endpoint_kind != MARKER_SCAN_ENDPOINT_KIND:
            raise ValueError("marker scan transport summary endpoint_kind must be issue_comments")
        for name in ("page_count", "comment_count", "marker_count"):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 0:
                raise ValueError(f"marker scan transport summary {name} must be non-negative")
        if not isinstance(self.retryable, bool):
            raise ValueError("marker scan transport summary retryable must be bool")
        if self.reason_code is not None and not isinstance(
            self.reason_code,
            MarkerReconciliationReasonCode,
        ):
            raise ValueError("marker scan transport summary reason_code must be valid")
        if self.reason_code is None and self.retryable:
            raise ValueError("marker scan transport summary without failure cannot be retryable")
        if self.reason_code is not None:
            expected_retryable = self.reason_code in RETRYABLE_MARKER_RECONCILIATION_REASON_CODES
            if self.retryable != expected_retryable:
                raise ValueError("marker scan transport summary retryable mismatch")
        _require_optional_non_empty(self.request_id, "marker scan transport summary request_id")
        if self.request_id is not None:
            if len(self.request_id) > 128 or any(
                char not in ALLOWED_ACTOR_PERMISSION_REQUEST_ID_CHARS for char in self.request_id
            ):
                raise ValueError("marker scan transport summary request_id must be allowlisted")
            if any(
                secret in self.request_id.casefold()
                for secret in SECRET_ACTOR_PERMISSION_REQUEST_ID_FRAGMENTS
            ):
                raise ValueError("marker scan transport summary request_id must not contain secrets")


@dataclass(frozen=True)
class MarkerReconciliationResult:
    status: MarkerReconciliationStatus
    reason_code: MarkerReconciliationReasonCode
    transport_summary: MarkerScanTransportSummary
    trusted_actor: str | None = None
    existing_comment_id: str | None = None
    duplicate_comment_ids: tuple[str, ...] = field(default_factory=tuple)
    writer_input_released: bool = False
    finalization_passed: bool = False
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, MarkerReconciliationStatus):
            raise ValueError("marker reconciliation status must be a MarkerReconciliationStatus")
        if not isinstance(self.reason_code, MarkerReconciliationReasonCode):
            raise ValueError("marker reconciliation reason_code must be valid")
        if not isinstance(self.transport_summary, MarkerScanTransportSummary):
            raise ValueError("marker reconciliation transport_summary must be valid")
        _require_optional_non_empty(self.trusted_actor, "marker reconciliation trusted_actor")
        _require_optional_non_empty(self.existing_comment_id, "marker reconciliation existing_comment_id")
        _require_string_tuple(self.duplicate_comment_ids, "marker reconciliation duplicate_comment_ids")
        if not isinstance(self.writer_input_released, bool):
            raise ValueError("marker reconciliation writer_input_released must be bool")
        if not isinstance(self.finalization_passed, bool):
            raise ValueError("marker reconciliation finalization_passed must be bool")
        if self.writer_input_released or self.finalization_passed:
            raise ValueError("marker reconciliation cannot release writer input by itself")
        _require_optional_non_empty(self.reason, "marker reconciliation reason")
        if self.status == MarkerReconciliationStatus.SAFE_TO_POST:
            if self.reason_code != MarkerReconciliationReasonCode.SAFE_TO_POST:
                raise ValueError("safe marker reconciliation requires safe_to_post reason")
            if self.trusted_actor is not None or self.existing_comment_id is not None or self.duplicate_comment_ids:
                raise ValueError("safe marker reconciliation must not include existing marker data")
            if self.transport_summary.reason_code is not None or self.transport_summary.retryable:
                raise ValueError("safe marker reconciliation transport summary must not include failure")
        if self.status == MarkerReconciliationStatus.RECONCILED_EXISTING:
            if self.reason_code != MarkerReconciliationReasonCode.MATCHED_EXISTING:
                raise ValueError("reconciled marker requires matched_existing reason")
            if self.trusted_actor is None or self.existing_comment_id is None:
                raise ValueError("reconciled marker requires trusted actor and existing comment")
            if self.transport_summary.reason_code is not None or self.transport_summary.retryable:
                raise ValueError("reconciled marker transport summary must not include failure")
        if self.status == MarkerReconciliationStatus.FAILED_CLOSED:
            if self.reason_code in {
                MarkerReconciliationReasonCode.SAFE_TO_POST,
                MarkerReconciliationReasonCode.MATCHED_EXISTING,
            }:
                raise ValueError("failed marker reconciliation requires failure reason")
            if self.trusted_actor is not None or self.existing_comment_id is not None or self.duplicate_comment_ids:
                raise ValueError("failed marker reconciliation must not include existing marker data")
            if self.transport_summary.reason_code != self.reason_code:
                raise ValueError("failed marker reconciliation transport summary reason mismatch")


@dataclass(frozen=True)
class ActorPermissionFinalizationCheckResult:
    status: GateStatus
    reason_code: ActorPermissionFinalizationReasonCode | None = None
    actor_permission_reason_code: ActorPermissionReasonCode | None = None
    actor_permission_transport_summary: ActorPermissionTransportSummary | None = None
    current_actor_permission_checked_at: str | None = None
    mismatched_fields: tuple[str, ...] = field(default_factory=tuple)
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GateStatus):
            raise ValueError("actor permission finalization check status must be a GateStatus")
        if self.status == GateStatus.UNKNOWN:
            raise ValueError("actor permission finalization check status must be pass or fail")
        if self.reason_code is not None and not isinstance(
            self.reason_code, ActorPermissionFinalizationReasonCode
        ):
            raise ValueError("actor permission finalization check reason_code must be valid")
        if self.actor_permission_reason_code is not None and not isinstance(
            self.actor_permission_reason_code, ActorPermissionReasonCode
        ):
            raise ValueError("actor permission finalization check actor_permission_reason_code must be valid")
        if self.actor_permission_transport_summary is not None and not isinstance(
            self.actor_permission_transport_summary, ActorPermissionTransportSummary
        ):
            raise ValueError("actor permission finalization check transport summary must be valid")
        _require_optional_non_empty(
            self.current_actor_permission_checked_at,
            "actor permission finalization check current_checked_at",
        )
        if self.current_actor_permission_checked_at is not None and not _is_realistic_rfc3339_utc_z(
            self.current_actor_permission_checked_at
        ):
            raise ValueError("actor permission finalization check current_checked_at must be UTC RFC3339")
        _require_allowed_str_tuple(
            self.mismatched_fields,
            "actor permission finalization check mismatched_fields",
            ACTOR_PERMISSION_FINALIZATION_MISMATCH_FIELDS,
        )
        _require_optional_non_empty(self.reason, "actor permission finalization check reason")
        if self.reason is not None and not _is_safe_actor_permission_reason(self.reason):
            raise ValueError("actor permission finalization check reason must be allowlisted")
        if self.status == GateStatus.PASS:
            if self.actor_permission_transport_summary is None:
                raise ValueError("actor permission finalization check pass requires transport summary")
            if self.reason_code is not None:
                raise ValueError("actor permission finalization check pass must not include reason_code")
            if self.actor_permission_reason_code is not None:
                raise ValueError("actor permission finalization check pass must not include actor reason")
            if self.current_actor_permission_checked_at is None:
                raise ValueError("actor permission finalization check pass requires current_checked_at")
            if self.mismatched_fields:
                raise ValueError("actor permission finalization check pass must not include mismatches")
            if self.reason is not None:
                raise ValueError("actor permission finalization check pass must not include reason")
        else:
            if self.actor_permission_transport_summary is None:
                raise ValueError("actor permission finalization check failure requires transport summary")
            if self.reason_code is None:
                raise ValueError("actor permission finalization check failure requires reason_code")
            if (
                self.reason_code == ActorPermissionFinalizationReasonCode.ACTOR_PERMISSION_GATE_FAILED
                and self.actor_permission_reason_code is None
            ):
                raise ValueError("actor permission gate failure requires actor_permission_reason_code")
            if (
                self.reason_code == ActorPermissionFinalizationReasonCode.ACTOR_PERMISSION_SNAPSHOT_MISMATCH
                and not self.mismatched_fields
            ):
                raise ValueError("actor permission snapshot mismatch requires mismatched_fields")
            if (
                self.reason_code == ActorPermissionFinalizationReasonCode.ACTOR_PERMISSION_CHECKED_AT_REGRESSED
                and self.mismatched_fields != ("checked_at",)
            ):
                raise ValueError("actor permission checked_at regression requires checked_at mismatch")


@dataclass(frozen=True)
class TargetFreshnessTransportSummary:
    endpoint_kind: str
    retryable: bool
    reason_code: TargetFreshnessReasonCode | None = None
    request_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.endpoint_kind, "target freshness transport summary endpoint_kind")
        if self.endpoint_kind != TARGET_FRESHNESS_TRANSPORT_ENDPOINT_KIND:
            raise ValueError("target freshness transport summary endpoint_kind must be pull_request_target")
        if not isinstance(self.retryable, bool):
            raise ValueError("target freshness transport summary retryable must be a bool")
        if self.reason_code is not None and not isinstance(self.reason_code, TargetFreshnessReasonCode):
            raise ValueError("target freshness transport summary reason_code must be valid")
        if (
            self.reason_code is not None
            and self.reason_code not in TARGET_FRESHNESS_TRANSPORT_REASON_CODES
            and self.reason_code != TargetFreshnessReasonCode.UNKNOWN_FRESHNESS
        ):
            raise ValueError("target freshness transport summary reason_code must be transport failure")
        if self.reason_code == TargetFreshnessReasonCode.UNKNOWN_FRESHNESS:
            pass
        elif self.retryable != (self.reason_code in TARGET_FRESHNESS_RETRYABLE_REASON_CODES):
            raise ValueError("target freshness transport summary retryable mismatch")
        _require_optional_non_empty(self.request_id, "target freshness transport summary request_id")
        if self.request_id is not None:
            if len(self.request_id) > 128 or any(
                char not in ALLOWED_ACTOR_PERMISSION_REQUEST_ID_CHARS for char in self.request_id
            ):
                raise ValueError("target freshness transport summary request_id must be allowlisted")
            if any(
                secret in self.request_id.casefold()
                for secret in SECRET_ACTOR_PERMISSION_REQUEST_ID_FRAGMENTS
            ):
                raise ValueError("target freshness transport summary request_id must not contain secrets")


@dataclass(frozen=True)
class TargetFreshnessCheckResult:
    status: GateStatus
    reason_code: TargetFreshnessReasonCode | None = None
    transport_summary: TargetFreshnessTransportSummary | None = None
    current_target: ReviewTarget | None = None
    current_target_hash: str | None = None
    current_checked_at: str | None = None
    check_method: str | None = None
    mismatched_fields: tuple[str, ...] = field(default_factory=tuple)
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GateStatus):
            raise ValueError("target freshness status must be a GateStatus")
        if self.status == GateStatus.UNKNOWN:
            raise ValueError("target freshness status must be pass or fail")
        if self.reason_code is not None and not isinstance(self.reason_code, TargetFreshnessReasonCode):
            raise ValueError("target freshness reason_code must be valid")
        if self.transport_summary is not None and not isinstance(
            self.transport_summary, TargetFreshnessTransportSummary
        ):
            raise ValueError("target freshness transport_summary must be valid")
        if self.current_target is not None and not isinstance(self.current_target, ReviewTarget):
            raise ValueError("target freshness current_target must be a ReviewTarget")
        _require_optional_hash_like(self.current_target_hash, "target freshness current_target_hash")
        _require_optional_non_empty(self.current_checked_at, "target freshness current_checked_at")
        if self.current_checked_at is not None and not _is_realistic_rfc3339_utc_z(self.current_checked_at):
            raise ValueError("target freshness current_checked_at must be UTC RFC3339")
        _require_optional_non_empty(self.check_method, "target freshness check_method")
        if self.check_method is not None and self.check_method != TARGET_FRESHNESS_CHECK_METHOD:
            raise ValueError("target freshness check_method is unsupported")
        _require_allowed_str_tuple(
            self.mismatched_fields,
            "target freshness mismatched_fields",
            TARGET_FRESHNESS_MISMATCH_FIELDS,
        )
        _require_optional_non_empty(self.reason, "target freshness reason")
        if self.reason is not None and not _is_safe_actor_permission_reason(self.reason):
            raise ValueError("target freshness reason must be allowlisted")
        if self.status == GateStatus.PASS:
            for name in ("transport_summary", "current_target", "current_target_hash", "current_checked_at", "check_method"):
                if getattr(self, name) is None:
                    raise ValueError(f"target freshness pass requires {name}")
            if self.reason_code is not None:
                raise ValueError("target freshness pass must not include reason_code")
            if self.mismatched_fields:
                raise ValueError("target freshness pass must not include mismatched_fields")
            if self.reason is not None:
                raise ValueError("target freshness pass must not include reason")
            if self.transport_summary.reason_code is not None or self.transport_summary.retryable:
                raise ValueError("target freshness pass transport summary must not include failure")
            if self.current_target_hash != self.current_target.target_hash():
                raise ValueError("target freshness current_target_hash mismatch")
        else:
            if self.reason_code is None:
                raise ValueError("target freshness failure requires reason_code")
            if self.transport_summary is None:
                raise ValueError("target freshness failure requires transport_summary")
            if self.reason_code == TargetFreshnessReasonCode.TARGET_MISMATCH and not self.mismatched_fields:
                raise ValueError("target freshness mismatch requires mismatched_fields")
            if self.reason_code == TargetFreshnessReasonCode.CHECKED_AT_BEFORE_APPROVAL and self.mismatched_fields != ("checked_at",):
                raise ValueError("target freshness checked-at regression requires checked_at mismatch")
            if self.current_target is not None and self.current_target_hash != self.current_target.target_hash():
                raise ValueError("target freshness failure current_target_hash mismatch")


@dataclass(frozen=True)
class FinalizationStatus:
    state: FinalizationState
    final_payload_hash: str | None
    target_hash: str | None
    reason_code: FinalizationReasonCode | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, FinalizationState):
            raise ValueError("finalization state must be a FinalizationState")
        _require_optional_hash_like(self.final_payload_hash, "finalization final_payload_hash")
        _require_optional_hash_like(self.target_hash, "finalization target_hash")
        if self.reason_code is not None and not isinstance(self.reason_code, FinalizationReasonCode):
            raise ValueError("finalization reason_code must be valid")
        _require_optional_non_empty(self.reason, "finalization reason")
        if self.state == FinalizationState.FINALIZED:
            for name in ("final_payload_hash", "target_hash"):
                if getattr(self, name) is None:
                    raise ValueError(f"finalized status requires {name}")
            if self.reason_code is not None:
                raise ValueError("finalized status must not include reason_code")
        if self.state != FinalizationState.FINALIZED and self.reason_code is None:
            raise ValueError("non-finalized status requires reason_code")
        if self.state != FinalizationState.FINALIZED and self.final_payload_hash is not None:
            raise ValueError("non-finalized status must not include final_payload_hash")


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
    approved_credential_principal: str
    approved_credential_source: str
    approved_repo_permission: str | None
    approved_installation_permission: str | None
    approved_endpoint_permission: str | None
    approved_issue_comment_write: bool
    approved_permission_check_method: str
    approved_permission_endpoint_method: str
    approved_permission_checked_target: Mapping[str, object]
    approved_permission_checked_target_hash: str
    approved_permission_endpoint: str
    approved_permission_endpoint_kind: str
    approved_permission_transport_summary: ActorPermissionTransportSummary
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
            "approved_credential_principal",
            "approved_credential_source",
            "approved_permission_check_method",
            "approved_permission_endpoint_method",
            "approved_permission_endpoint",
            "approved_permission_endpoint_kind",
            "approved_by",
            "timestamp",
        ):
            _require_non_empty(getattr(self, name), f"approval {name}")
        if not _is_safe_actor_permission_identity(self.approved_github_actor):
            raise ValueError("approval approved_github_actor must be allowlisted")
        if not _is_safe_actor_permission_identity(self.approved_credential_principal):
            raise ValueError("approval approved_credential_principal must be allowlisted")
        if self.approved_credential_source not in ALLOWED_ACTOR_PERMISSION_CREDENTIAL_SOURCES:
            raise ValueError("approval approved_credential_source is unsupported")
        if self.approved_repo_permission is not None:
            _require_non_empty(self.approved_repo_permission, "approval approved_repo_permission")
            if self.approved_repo_permission not in ALLOWED_ACTOR_PERMISSION_REPO_PERMISSIONS:
                raise ValueError("approval approved_repo_permission is unsupported")
        if self.approved_installation_permission is not None:
            _require_non_empty(self.approved_installation_permission, "approval approved_installation_permission")
            if self.approved_installation_permission not in ALLOWED_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS:
                raise ValueError("approval approved_installation_permission is unsupported")
        if self.approved_endpoint_permission is not None:
            _require_non_empty(self.approved_endpoint_permission, "approval approved_endpoint_permission")
            if self.approved_endpoint_permission not in ALLOWED_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS:
                raise ValueError("approval approved_endpoint_permission is unsupported")
        if type(self.approved_issue_comment_write) is not bool:
            raise ValueError("approval approved_issue_comment_write must be a boolean")
        if self.approved_issue_comment_write is not True:
            raise ValueError("approval requires issue-comment write proof")
        if self.approved_permission_check_method != ACTOR_PERMISSION_CHECK_METHOD:
            raise ValueError("approval approved_permission_check_method is unsupported")
        if self.approved_permission_endpoint_method != ACTOR_PERMISSION_ENDPOINT_METHOD:
            raise ValueError("approval approved_permission_endpoint_method is unsupported")
        if self.approved_permission_endpoint_kind != ACTOR_PERMISSION_ENDPOINT_KIND:
            raise ValueError("approval approved_permission_endpoint_kind is unsupported")
        if not isinstance(self.approved_permission_checked_target, Mapping):
            raise ValueError("approval approved_permission_checked_target must be a mapping")
        if not all(isinstance(key, str) for key in self.approved_permission_checked_target):
            raise ValueError("approval approved_permission_checked_target keys must be strings")
        object.__setattr__(
            self,
            "approved_permission_checked_target",
            MappingProxyType(dict(self.approved_permission_checked_target)),
        )
        _require_hash_like(
            self.approved_permission_checked_target_hash,
            "approval approved_permission_checked_target_hash",
        )
        if self.approved_permission_checked_target != self.approved_review_target.to_ordered_dict():
            raise ValueError("approval permission checked_target must match approved_review_target")
        if self.approved_permission_checked_target_hash != self.approved_review_target_hash:
            raise ValueError("approval permission checked_target_hash must match approved_review_target_hash")
        expected_endpoint = _actor_permission_expected_endpoint(self.approved_permission_checked_target)
        if expected_endpoint is None or self.approved_permission_endpoint != expected_endpoint:
            raise ValueError("approval permission endpoint must match approved_review_target")
        if not _is_realistic_rfc3339_utc_z(self.approved_permission_checked_at):
            raise ValueError("approval approved_permission_checked_at must be UTC RFC3339")
        derived_permission = _actor_permission_derived_permission(
            credential_source=self.approved_credential_source,
            repo_permission=self.approved_repo_permission,
            installation_permission=self.approved_installation_permission,
            endpoint_permission=self.approved_endpoint_permission,
        )
        if derived_permission is None or self.approved_permission != derived_permission:
            raise ValueError("approval permission proof is inconsistent")
        if not isinstance(self.approved_permission_transport_summary, ActorPermissionTransportSummary):
            raise ValueError("approval approved_permission_transport_summary must be valid")
        if self.approved_permission_transport_summary.reason_code is not None:
            raise ValueError("approval passing permission transport summary must not include reason_code")
        if self.approved_permission_transport_summary.retryable:
            raise ValueError("approval passing permission transport summary must not be retryable")
        if type(self.include_public_verdict) is not bool:
            raise ValueError("approval include_public_verdict must be a boolean")
        if self.approved and not self.approved_item_ids:
            raise ValueError("approved decision requires approved_item_ids")


@dataclass(frozen=True)
class ApprovalDecisionBuildResult:
    status: GateStatus
    approval: ApprovalDecision | None = None
    reason_code: ApprovalDecisionBuildReasonCode | None = None
    approval_proof_reason_code: ApprovalProofReasonCode | None = None
    actor_permission_reason_code: ActorPermissionReasonCode | None = None
    actor_permission_transport_summary: ActorPermissionTransportSummary | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GateStatus):
            raise ValueError("approval decision build status must be a GateStatus")
        if self.status == GateStatus.UNKNOWN:
            raise ValueError("approval decision build status must be pass or fail")
        if self.approval is not None and not isinstance(self.approval, ApprovalDecision):
            raise ValueError("approval decision build approval must be an ApprovalDecision")
        if self.reason_code is not None and not isinstance(
            self.reason_code, ApprovalDecisionBuildReasonCode
        ):
            raise ValueError("approval decision build reason_code must be valid")
        if self.approval_proof_reason_code is not None and not isinstance(
            self.approval_proof_reason_code, ApprovalProofReasonCode
        ):
            raise ValueError("approval decision build approval_proof_reason_code must be valid")
        if self.actor_permission_reason_code is not None and not isinstance(
            self.actor_permission_reason_code, ActorPermissionReasonCode
        ):
            raise ValueError("approval decision build actor_permission_reason_code must be valid")
        if self.actor_permission_transport_summary is not None and not isinstance(
            self.actor_permission_transport_summary, ActorPermissionTransportSummary
        ):
            raise ValueError("approval decision build transport summary must be valid")
        _require_optional_non_empty(self.reason, "approval decision build reason")
        if self.reason is not None and not _is_safe_actor_permission_reason(self.reason):
            raise ValueError("approval decision build reason must be allowlisted")
        if self.status == GateStatus.PASS:
            if self.approval is None:
                raise ValueError("approval decision build pass requires approval")
            if (
                self.reason_code is not None
                or self.approval_proof_reason_code is not None
                or self.actor_permission_reason_code is not None
            ):
                raise ValueError("approval decision build pass must not include reason codes")
            if self.actor_permission_transport_summary is not None or self.reason is not None:
                raise ValueError("approval decision build pass must not include failure diagnostics")
        else:
            if self.approval is not None:
                raise ValueError("approval decision build failure must not include approval")
            if self.reason_code is None:
                raise ValueError("approval decision build failure requires reason_code")
            if (
                self.reason_code == ApprovalDecisionBuildReasonCode.ACTOR_PERMISSION_GATE_FAILED
                and self.actor_permission_reason_code is None
            ):
                raise ValueError("approval decision build actor gate failure requires actor reason code")
            if (
                self.reason_code == ApprovalDecisionBuildReasonCode.APPROVAL_PROOF_FAILED
                and self.approval_proof_reason_code is None
            ):
                raise ValueError("approval decision build approval proof failure requires proof reason code")


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
class WriterReleaseItemDiagnostic:
    item_id: str
    reason_code: WriterReleaseItemReasonCode
    destination: PostingDestination | None = None
    source_classification: str | None = None
    public_payload_eligible: bool | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.item_id, "writer release item diagnostic item_id")
        if not isinstance(self.reason_code, WriterReleaseItemReasonCode):
            raise ValueError("writer release item diagnostic reason_code must be valid")
        if self.destination is not None and not isinstance(self.destination, PostingDestination):
            raise ValueError("writer release item diagnostic destination must be valid")
        _require_optional_non_empty(
            self.source_classification,
            "writer release item diagnostic source_classification",
        )
        if self.public_payload_eligible is not None and type(self.public_payload_eligible) is not bool:
            raise ValueError("writer release item diagnostic public_payload_eligible must be bool")


@dataclass(frozen=True)
class WriterReleasePreflightResult:
    status: GateStatus
    writer_input_released: bool
    eligible_for_finalization: bool = False
    approved_item_ids: tuple[str, ...] = ()
    reason_code: WriterReleasePreflightReasonCode | None = None
    nested_reason_code: ApprovalDecisionBuildReasonCode | None = None
    nested_approval_proof_reason_code: ApprovalProofReasonCode | None = None
    nested_actor_permission_reason_code: ActorPermissionReasonCode | None = None
    item_diagnostics: tuple[WriterReleaseItemDiagnostic, ...] = ()
    final_payload_hash: str | None = None
    writer_result: GitHubWriterResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, GateStatus):
            raise ValueError("writer release preflight status must be a GateStatus")
        if self.status == GateStatus.UNKNOWN:
            raise ValueError("writer release preflight status must be pass or fail")
        if type(self.writer_input_released) is not bool:
            raise ValueError("writer release preflight writer_input_released must be bool")
        if self.writer_input_released:
            raise ValueError("writer release preflight must not release writer input")
        if type(self.eligible_for_finalization) is not bool:
            raise ValueError("writer release preflight eligible_for_finalization must be bool")
        _require_string_tuple(self.approved_item_ids, "writer release preflight approved_item_ids")
        if self.reason_code is not None and not isinstance(self.reason_code, WriterReleasePreflightReasonCode):
            raise ValueError("writer release preflight reason_code must be valid")
        if self.nested_reason_code is not None and not isinstance(
            self.nested_reason_code,
            ApprovalDecisionBuildReasonCode,
        ):
            raise ValueError("writer release preflight nested_reason_code must be valid")
        if self.nested_approval_proof_reason_code is not None and not isinstance(
            self.nested_approval_proof_reason_code,
            ApprovalProofReasonCode,
        ):
            raise ValueError("writer release preflight nested_approval_proof_reason_code must be valid")
        if self.nested_actor_permission_reason_code is not None and not isinstance(
            self.nested_actor_permission_reason_code,
            ActorPermissionReasonCode,
        ):
            raise ValueError("writer release preflight nested_actor_permission_reason_code must be valid")
        _require_instance_tuple(
            self.item_diagnostics,
            "writer release preflight item_diagnostics",
            WriterReleaseItemDiagnostic,
        )
        if self.final_payload_hash is not None:
            raise ValueError("writer release preflight must not carry final_payload_hash")
        if self.writer_result is not None:
            raise ValueError("writer release preflight must not carry writer_result")
        if self.status == GateStatus.PASS:
            if not self.eligible_for_finalization:
                raise ValueError("writer release preflight pass requires eligible_for_finalization")
            _require_string_tuple(
                self.approved_item_ids,
                "writer release preflight approved_item_ids",
                allow_empty=False,
            )
            if self.reason_code is not None:
                raise ValueError("writer release preflight pass must not include reason_code")
            if (
                self.nested_reason_code is not None
                or self.nested_approval_proof_reason_code is not None
                or self.nested_actor_permission_reason_code is not None
                or self.item_diagnostics
            ):
                raise ValueError("writer release preflight pass must not include diagnostics")
        else:
            if self.eligible_for_finalization:
                raise ValueError("writer release preflight failure must not be eligible")
            if self.approved_item_ids:
                raise ValueError("writer release preflight failure must not include approved_item_ids")
            if self.reason_code is None:
                raise ValueError("writer release preflight failure requires reason_code")


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
    post_interaction_gate: PostInteractionGateResult | None
    writer_release_preflight: WriterReleasePreflightResult | None
    actor_permission_gate: ActorPermissionGateResult | None
    actor_permission_finalization_check: ActorPermissionFinalizationCheckResult | None
    target_freshness_check: TargetFreshnessCheckResult | None
    payload_validation: PayloadValidationResult | None
    marker_reconciliation: MarkerReconciliationResult | None
    finalization_status: FinalizationStatus | None
    candidate_github_payload: CandidateIssueCommentPayload | None
    final_github_payload: FinalIssueCommentPayload | None
    final_payload_hash: str | None
    approval: ApprovalDecision | None
    writer_result: GitHubWriterResult | None
    errors: list[GraphError]

    @classmethod
    def field_names(cls) -> tuple[str, ...]:
        return tuple(field.name for field in fields(cls))
