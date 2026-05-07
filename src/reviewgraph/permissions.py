from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from reviewgraph.models import (
    ACTOR_PERMISSION_CHECK_METHOD,
    ACTOR_PERMISSION_ENDPOINT_KIND,
    ACTOR_PERMISSION_ENDPOINT_METHOD,
    ACTOR_PERMISSION_TRANSPORT_ENDPOINT_KIND,
    ALLOWED_ACTOR_PERMISSION_CREDENTIAL_SOURCES,
    ALLOWED_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS,
    ALLOWED_ACTOR_PERMISSION_REPO_PERMISSIONS,
    ActorPermissionGateResult,
    ActorPermissionReasonCode,
    ActorPermissionTransportSummary,
    GateStatus,
    ReviewTarget,
    WRITE_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS,
    WRITE_ACTOR_PERMISSION_REPO_PERMISSIONS,
)


CHECK_METHOD = ACTOR_PERMISSION_CHECK_METHOD
ENDPOINT_KIND = ACTOR_PERMISSION_ENDPOINT_KIND
ENDPOINT_METHOD = ACTOR_PERMISSION_ENDPOINT_METHOD
TRANSPORT_ENDPOINT_KIND = ACTOR_PERMISSION_TRANSPORT_ENDPOINT_KIND
DEFAULT_MAX_PROOF_AGE_SECONDS = 300
MAX_FUTURE_SKEW_SECONDS = 60

VALID_CREDENTIAL_SOURCES = ALLOWED_ACTOR_PERMISSION_CREDENTIAL_SOURCES
VALID_REPO_PERMISSIONS = ALLOWED_ACTOR_PERMISSION_REPO_PERMISSIONS
WRITE_REPO_PERMISSIONS = WRITE_ACTOR_PERMISSION_REPO_PERMISSIONS
VALID_ENDPOINT_PERMISSIONS = ALLOWED_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS
WRITE_ENDPOINT_PERMISSIONS = WRITE_ACTOR_PERMISSION_ENDPOINT_PERMISSIONS
TRANSPORT_REASON_CODES = frozenset(
    {
        ActorPermissionReasonCode.TIMEOUT,
        ActorPermissionReasonCode.RATE_LIMITED,
        ActorPermissionReasonCode.FORBIDDEN,
        ActorPermissionReasonCode.NOT_FOUND,
        ActorPermissionReasonCode.UNAVAILABLE,
        ActorPermissionReasonCode.MALFORMED_RESPONSE,
    }
)
RETRYABLE_REASON_CODES = frozenset(
    {
        ActorPermissionReasonCode.TIMEOUT,
        ActorPermissionReasonCode.RATE_LIMITED,
        ActorPermissionReasonCode.UNAVAILABLE,
    }
)
RFC3339_UTC_Z_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")


@dataclass(frozen=True)
class ActorPermissionProbeResult:
    actor: str | None = None
    credential_principal: str | None = None
    credential_source: str | None = None
    repo_permission: str | None = None
    installation_permission: str | None = None
    endpoint_permission: str | None = None
    issue_comment_write: bool | None = None
    check_method: str | None = None
    endpoint_method: str | None = None
    checked_target: ReviewTarget | None = None
    checked_at: str | None = None
    endpoint: str | None = None
    endpoint_kind: str | None = None
    transport_reason_code: ActorPermissionReasonCode | None = None
    request_id: str | None = None
    reason: str | None = None


def issue_comment_endpoint(target: ReviewTarget) -> str:
    owner, repo = target.owner_repo.split("/", 1)
    return f"/repos/{owner}/{repo}/issues/{target.pr_number}/comments"


def evaluate_actor_permission_gate(
    probe: ActorPermissionProbeResult,
    *,
    expected_target: ReviewTarget,
    evaluated_at: str,
    max_proof_age_seconds: int = DEFAULT_MAX_PROOF_AGE_SECONDS,
) -> ActorPermissionGateResult:
    if not isinstance(probe, ActorPermissionProbeResult):
        raise ValueError("actor permission probe must be an ActorPermissionProbeResult")
    if not isinstance(expected_target, ReviewTarget):
        raise ValueError("expected target must be a ReviewTarget")
    if type(max_proof_age_seconds) is not int or max_proof_age_seconds <= 0:
        raise ValueError("max proof age seconds must be a positive integer")

    evaluated_time = _parse_required_utc_z(evaluated_at, "evaluated_at")
    expected_endpoint = issue_comment_endpoint(expected_target)

    malformed_field = _first_malformed_field(
        probe,
        (
            "actor",
            "credential_principal",
            "credential_source",
            "repo_permission",
            "installation_permission",
            "endpoint_permission",
            "check_method",
            "endpoint_method",
            "checked_at",
            "endpoint",
            "endpoint_kind",
            "request_id",
            "reason",
        ),
    )
    if malformed_field is not None:
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=ActorPermissionReasonCode.MALFORMED_RESPONSE,
            reason=f"permission probe field is malformed: {malformed_field}",
        )

    if probe.issue_comment_write is not None and not isinstance(probe.issue_comment_write, bool):
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=ActorPermissionReasonCode.MALFORMED_RESPONSE,
            reason="permission probe issue_comment_write is malformed",
        )

    if probe.transport_reason_code is not None:
        if not isinstance(probe.transport_reason_code, ActorPermissionReasonCode):
            return _fail(
                probe,
                expected_target=expected_target,
                expected_endpoint=expected_endpoint,
                reason_code=ActorPermissionReasonCode.MALFORMED_RESPONSE,
                transport_reason_code=ActorPermissionReasonCode.MALFORMED_RESPONSE,
                reason="permission probe returned a malformed transport reason",
            )
        if probe.transport_reason_code not in TRANSPORT_REASON_CODES:
            return _fail(
                probe,
                expected_target=expected_target,
                expected_endpoint=expected_endpoint,
                reason_code=ActorPermissionReasonCode.MALFORMED_RESPONSE,
                transport_reason_code=ActorPermissionReasonCode.MALFORMED_RESPONSE,
                reason="permission probe returned an invalid transport reason",
            )
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=probe.transport_reason_code,
            transport_reason_code=probe.transport_reason_code,
            reason=f"permission probe failed: {probe.transport_reason_code.value}",
        )

    actor = _safe_identity(probe.actor)
    if actor is None:
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=ActorPermissionReasonCode.UNKNOWN_ACTOR,
            reason="authenticated GitHub actor is unknown",
        )

    credential_source = _clean(probe.credential_source)
    if credential_source not in VALID_CREDENTIAL_SOURCES:
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=ActorPermissionReasonCode.UNKNOWN_CREDENTIAL_SOURCE,
            reason="credential source is unknown",
        )

    credential_principal = _safe_identity(probe.credential_principal)
    if credential_principal is None:
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=ActorPermissionReasonCode.MISSING_CREDENTIAL_PRINCIPAL,
            reason="credential principal is missing",
        )

    if _clean(probe.check_method) is None:
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=ActorPermissionReasonCode.MISSING_CHECK_METHOD,
            reason="permission check method is missing",
        )

    if probe.checked_target is None:
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=ActorPermissionReasonCode.MISSING_CHECKED_TARGET,
            reason="permission check target is missing",
        )
    if not isinstance(probe.checked_target, ReviewTarget):
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=ActorPermissionReasonCode.MALFORMED_RESPONSE,
            reason="permission check target is malformed",
        )

    if _clean(probe.checked_at) is None:
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=ActorPermissionReasonCode.MISSING_CHECKED_AT,
            reason="permission check timestamp is missing",
        )

    if (
        probe.check_method != CHECK_METHOD
        or probe.endpoint_method != ENDPOINT_METHOD
        or probe.endpoint_kind != ENDPOINT_KIND
        or probe.endpoint != expected_endpoint
        or probe.checked_target != expected_target
    ):
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=ActorPermissionReasonCode.TARGET_MISMATCH,
            reason="permission check target or endpoint did not match",
        )

    checked_time = _parse_optional_utc_z(probe.checked_at)
    if checked_time is None:
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=ActorPermissionReasonCode.MALFORMED_RESPONSE,
            reason="permission check timestamp is malformed",
        )
    age_seconds = (evaluated_time - checked_time).total_seconds()
    if age_seconds > max_proof_age_seconds or age_seconds < -MAX_FUTURE_SKEW_SECONDS:
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=ActorPermissionReasonCode.STALE_CACHED_PROOF,
            reason="permission proof timestamp is stale",
        )

    permission_result = _derive_permission(probe, credential_source)
    if permission_result.reason_code is not None:
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=permission_result.reason_code,
            reason=permission_result.reason,
        )

    if probe.issue_comment_write is not True:
        return _fail(
            probe,
            expected_target=expected_target,
            expected_endpoint=expected_endpoint,
            reason_code=ActorPermissionReasonCode.INSUFFICIENT_ENDPOINT_PERMISSION,
            reason="credential cannot write issue comments",
        )

    return ActorPermissionGateResult(
        status=GateStatus.PASS,
        actor=actor,
        permission=permission_result.permission,
        checked_at=probe.checked_at,
        reason=None,
        reason_code=None,
        credential_principal=credential_principal,
        credential_source=credential_source,
        repo_permission=_clean(probe.repo_permission),
        installation_permission=_clean(probe.installation_permission),
        endpoint_permission=_clean(probe.endpoint_permission),
        issue_comment_write=True,
        check_method=probe.check_method,
        endpoint_method=probe.endpoint_method,
        checked_target=expected_target.to_ordered_dict(),
        checked_target_hash=expected_target.target_hash(),
        endpoint=expected_endpoint,
        endpoint_kind=ENDPOINT_KIND,
        transport_summary=_transport_summary(probe, None),
    )


@dataclass(frozen=True)
class _PermissionResult:
    permission: str | None = None
    reason_code: ActorPermissionReasonCode | None = None
    reason: str | None = None


def _derive_permission(probe: ActorPermissionProbeResult, credential_source: str) -> _PermissionResult:
    repo_permission = _clean(probe.repo_permission)
    installation_permission = _clean(probe.installation_permission)
    endpoint_permission = _clean(probe.endpoint_permission)

    if repo_permission is not None and repo_permission not in VALID_REPO_PERMISSIONS:
        return _PermissionResult(reason_code=ActorPermissionReasonCode.UNKNOWN_PERMISSION, reason="unknown repo permission")
    if installation_permission is not None and installation_permission not in VALID_ENDPOINT_PERMISSIONS:
        return _PermissionResult(
            reason_code=ActorPermissionReasonCode.UNKNOWN_PERMISSION,
            reason="unknown installation permission",
        )
    if endpoint_permission is not None and endpoint_permission not in VALID_ENDPOINT_PERMISSIONS:
        return _PermissionResult(
            reason_code=ActorPermissionReasonCode.UNKNOWN_PERMISSION,
            reason="unknown endpoint permission",
        )
    if credential_source == "pat":
        if installation_permission is not None or endpoint_permission is not None:
            return _PermissionResult(
                reason_code=ActorPermissionReasonCode.MALFORMED_RESPONSE,
                reason="classic PAT proof must use broad repo permission only",
            )
    elif credential_source == "fine_grained_pat":
        if repo_permission is not None or installation_permission is not None:
            return _PermissionResult(
                reason_code=ActorPermissionReasonCode.MALFORMED_RESPONSE,
                reason="fine-grained PAT proof must use endpoint permission",
            )
    elif credential_source == "github_app_installation":
        if repo_permission is not None:
            return _PermissionResult(
                reason_code=ActorPermissionReasonCode.MALFORMED_RESPONSE,
                reason="GitHub App installation proof must not use repo permission",
            )
        if installation_permission is None:
            return _PermissionResult(
                reason_code=ActorPermissionReasonCode.UNKNOWN_PERMISSION,
                reason="GitHub App installation permission is missing",
            )
        if endpoint_permission is not None and endpoint_permission != installation_permission:
            return _PermissionResult(
                reason_code=ActorPermissionReasonCode.MALFORMED_RESPONSE,
                reason="GitHub App endpoint permission must mirror installation permission",
            )
    elif credential_source == "github_app_user":
        if repo_permission is not None or installation_permission is not None:
            return _PermissionResult(
                reason_code=ActorPermissionReasonCode.MALFORMED_RESPONSE,
                reason="GitHub App user proof must use endpoint permission",
            )
    permission = repo_permission or installation_permission or endpoint_permission
    if permission is None:
        return _PermissionResult(reason_code=ActorPermissionReasonCode.UNKNOWN_PERMISSION, reason="permission is missing")

    broad_write = repo_permission in WRITE_REPO_PERMISSIONS
    endpoint_write = installation_permission in WRITE_ENDPOINT_PERMISSIONS or endpoint_permission in WRITE_ENDPOINT_PERMISSIONS
    if not broad_write and not endpoint_write:
        return _PermissionResult(
            reason_code=ActorPermissionReasonCode.INSUFFICIENT_ENDPOINT_PERMISSION,
            reason="credential does not have write permission for issue comments",
        )
    return _PermissionResult(permission=permission)


def _fail(
    probe: ActorPermissionProbeResult,
    *,
    expected_target: ReviewTarget,
    expected_endpoint: str,
    reason_code: ActorPermissionReasonCode,
    reason: str,
    transport_reason_code: ActorPermissionReasonCode | None = None,
) -> ActorPermissionGateResult:
    checked_target = None
    checked_target_hash = None
    if isinstance(probe.checked_target, ReviewTarget):
        checked_target = probe.checked_target.to_ordered_dict()
        checked_target_hash = probe.checked_target.target_hash()
    return ActorPermissionGateResult(
        status=GateStatus.FAIL,
        actor=_safe_identity(probe.actor),
        permission=_derive_safe_failure_permission(probe),
        checked_at=_safe_checked_at(probe.checked_at),
        reason=reason,
        reason_code=reason_code,
        credential_principal=_safe_identity(probe.credential_principal),
        credential_source=_safe_credential_source(probe.credential_source),
        repo_permission=_safe_repo_permission(probe.repo_permission),
        installation_permission=_safe_endpoint_permission(probe.installation_permission),
        endpoint_permission=_safe_endpoint_permission(probe.endpoint_permission),
        issue_comment_write=probe.issue_comment_write if isinstance(probe.issue_comment_write, bool) else None,
        check_method=_safe_check_method(probe.check_method),
        endpoint_method=_safe_endpoint_method(probe.endpoint_method),
        checked_target=checked_target,
        checked_target_hash=checked_target_hash,
        endpoint=_safe_endpoint(probe.endpoint, checked_target),
        endpoint_kind=_safe_endpoint_kind(probe.endpoint_kind),
        transport_summary=_transport_summary(probe, transport_reason_code),
    )


def _transport_summary(
    probe: ActorPermissionProbeResult,
    reason_code: ActorPermissionReasonCode | None,
) -> ActorPermissionTransportSummary:
    return ActorPermissionTransportSummary(
        endpoint_kind=TRANSPORT_ENDPOINT_KIND,
        retryable=reason_code in RETRYABLE_REASON_CODES,
        reason_code=reason_code,
        request_id=_safe_request_id(probe.request_id),
    )


def _derive_safe_failure_permission(probe: ActorPermissionProbeResult) -> str | None:
    repo_permission = _safe_repo_permission(probe.repo_permission)
    installation_permission = _safe_endpoint_permission(probe.installation_permission)
    endpoint_permission = _safe_endpoint_permission(probe.endpoint_permission)
    return repo_permission or installation_permission or endpoint_permission


def _safe_repo_permission(value: str | None) -> str | None:
    cleaned = _clean(value)
    if cleaned not in VALID_REPO_PERMISSIONS:
        return None
    return cleaned


def _safe_endpoint_permission(value: str | None) -> str | None:
    cleaned = _clean(value)
    if cleaned not in VALID_ENDPOINT_PERMISSIONS:
        return None
    return cleaned


def _safe_credential_source(value: str | None) -> str | None:
    cleaned = _clean(value)
    if cleaned not in VALID_CREDENTIAL_SOURCES:
        return None
    return cleaned


def _safe_check_method(value: str | None) -> str | None:
    cleaned = _clean(value)
    if cleaned != CHECK_METHOD:
        return None
    return cleaned


def _safe_endpoint_method(value: str | None) -> str | None:
    cleaned = _clean(value)
    if cleaned != ENDPOINT_METHOD:
        return None
    return cleaned


def _safe_endpoint_kind(value: str | None) -> str | None:
    cleaned = _clean(value)
    if cleaned != ENDPOINT_KIND:
        return None
    return cleaned


def _safe_endpoint(value: str | None, checked_target: dict[str, object] | None) -> str | None:
    cleaned = _clean(value)
    if cleaned is None or checked_target is None:
        return None
    expected_endpoint = _expected_endpoint_from_checked_target(checked_target)
    if expected_endpoint is None or cleaned != expected_endpoint:
        return None
    return cleaned


def _expected_endpoint_from_checked_target(checked_target: dict[str, object]) -> str | None:
    owner_repo = checked_target.get("owner_repo")
    pr_number = checked_target.get("pr_number")
    if not isinstance(owner_repo, str) or "/" not in owner_repo:
        return None
    if type(pr_number) is not int or pr_number <= 0:
        return None
    owner, repo = owner_repo.split("/", 1)
    return f"/repos/{owner}/{repo}/issues/{pr_number}/comments"


def _safe_checked_at(value: str | None) -> str | None:
    if _parse_optional_utc_z(value) is None:
        return None
    return value


def _safe_identity(value: str | None) -> str | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:/#[]@-")
    if len(cleaned) > 128 or any(char not in allowed for char in cleaned):
        return None
    if any(secret in cleaned.casefold() for secret in ("token", "ghp_", "github_pat_", "gho_", "ghs_", "ghu_")):
        return None
    return cleaned


def _safe_request_id(value: str | None) -> str | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._:/#-")
    if len(cleaned) > 128 or any(char not in allowed for char in cleaned):
        return None
    if any(secret in cleaned.casefold() for secret in ("token", "ghp_", "github_pat_", "gho_", "ghs_", "ghu_")):
        return None
    return cleaned


def _clean(value: str | None) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value


def _first_malformed_field(probe: ActorPermissionProbeResult, field_names: tuple[str, ...]) -> str | None:
    for field_name in field_names:
        value = getattr(probe, field_name)
        if value is not None and not isinstance(value, str):
            return field_name
    return None


def _parse_required_utc_z(value: str, field_name: str) -> datetime:
    parsed = _parse_optional_utc_z(value)
    if parsed is None:
        raise ValueError(f"{field_name} must be UTC RFC3339 with trailing Z")
    return parsed


def _parse_optional_utc_z(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not RFC3339_UTC_Z_PATTERN.fullmatch(value):
        return None
    date_time = value[:-1]
    date, time = date_time.split("T", 1)
    year = int(date[0:4])
    month = int(date[5:7])
    day = int(date[8:10])
    hour = int(time[0:2])
    minute = int(time[3:5])
    second = int(time[6:8])
    if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 23 and minute <= 59 and second <= 59):
        return None
    days_by_month = (31, 29 if _is_leap_year(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    if day > days_by_month[month - 1]:
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    if parsed.tzinfo != timezone.utc:
        return None
    return parsed


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
