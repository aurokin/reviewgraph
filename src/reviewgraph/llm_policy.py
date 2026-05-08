from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from reviewgraph.models import RedactionStatus, ReviewerRunKey
from reviewgraph.redaction import redact_text
from reviewgraph.reviewer_boundaries import ReviewerAdapterBoundaryError, validate_reviewer_adapter_input
from reviewgraph.reviewer_context import (
    ProviderRequestPreview,
    ReviewerContextPackage,
    build_provider_request_preview,
)


LIVE_LLM_CALL_COST = 1


class LiveLLMBlockedReasonCode(StrEnum):
    MISSING_LIVE_OPT_IN = "missing_live_opt_in"
    MISSING_PROVIDER = "missing_provider"
    MISSING_MODEL = "missing_model"
    REVIEWER_RUN_KEY_MISMATCH = "reviewer_run_key_mismatch"
    REVIEWER_ADAPTER_BOUNDARY_FAILED = "reviewer_adapter_boundary_failed"
    LIVE_CALL_BUDGET_EXCEEDED = "live_call_budget_exceeded"
    LIVE_CALL_RESERVATION_CONFLICT = "live_call_reservation_conflict"
    RAW_PROVIDER_NOT_APPROVED = "raw_provider_not_approved"
    RAW_TRACE_NOT_APPROVED = "raw_trace_not_approved"


class ProviderFailureReasonCode(StrEnum):
    MISSING_CREDENTIALS = "missing_credentials"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    RETRY_EXHAUSTED = "retry_exhausted"
    MALFORMED_RESPONSE = "malformed_response"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    UNKNOWN_PROVIDER_ERROR = "unknown_provider_error"


RETRYABLE_PROVIDER_FAILURES = frozenset(
    {
        ProviderFailureReasonCode.TIMEOUT,
        ProviderFailureReasonCode.RATE_LIMITED,
        ProviderFailureReasonCode.PROVIDER_UNAVAILABLE,
    }
)


@dataclass(frozen=True)
class LiveLLMPolicyInput:
    reviewer_run_key: ReviewerRunKey
    live_llm_enabled: bool
    provider: str | None
    model: str | None = None
    live_llm_opt_in_source: str | None = None
    raw_provider_submission_enabled: bool = False
    raw_provider_submission_approved: bool = False
    raw_provider_submission_opt_in_source: str | None = None
    raw_trace_persistence_enabled: bool = False
    raw_trace_persistence_approved: bool = False
    raw_trace_persistence_opt_in_source: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reviewer_run_key, ReviewerRunKey):
            raise ValueError("reviewer_run_key must be a ReviewerRunKey")
        for name in (
            "live_llm_enabled",
            "raw_provider_submission_enabled",
            "raw_provider_submission_approved",
            "raw_trace_persistence_enabled",
            "raw_trace_persistence_approved",
        ):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean")
        _require_optional_non_empty(self.provider, "provider")
        _require_optional_non_empty(self.model, "model")
        _require_optional_non_empty(self.live_llm_opt_in_source, "live_llm_opt_in_source")
        _require_optional_non_empty(
            self.raw_provider_submission_opt_in_source,
            "raw_provider_submission_opt_in_source",
        )
        _require_optional_non_empty(
            self.raw_trace_persistence_opt_in_source,
            "raw_trace_persistence_opt_in_source",
        )


@dataclass(frozen=True)
class LiveLLMReservation:
    run_key_stable: str
    reservation_key: str
    provider: str
    model: str
    target_hash: str
    config_hash: str
    request_hash: str
    request_byte_count: int
    package_fingerprint: str

    def to_ordered_dict(self) -> dict[str, Any]:
        return {
            "run_key_stable": self.run_key_stable,
            "reservation_key": self.reservation_key,
            "provider": _redacted_scalar(self.provider),
            "model": _redacted_scalar(self.model),
            "target_hash": self.target_hash,
            "config_hash": self.config_hash,
            "request_hash": self.request_hash,
            "request_byte_count": self.request_byte_count,
            "package_fingerprint": self.package_fingerprint,
        }


@dataclass(frozen=True)
class LiveLLMBudgetLedger:
    reservations: tuple[LiveLLMReservation, ...] = ()

    @property
    def reserved_live_calls(self) -> int:
        return len(self.reservations)

    def reservation_for_run_key(self, run_key_stable: str) -> LiveLLMReservation | None:
        for reservation in self.reservations:
            if reservation.run_key_stable == run_key_stable:
                return reservation
        return None

    def reserve(self, reservation: LiveLLMReservation) -> "LiveLLMBudgetLedger":
        return LiveLLMBudgetLedger(reservations=self.reservations + (reservation,))

    def to_ordered_dict(self) -> dict[str, Any]:
        return {
            "reserved_live_calls": self.reserved_live_calls,
            "reservations": [reservation.to_ordered_dict() for reservation in self.reservations],
        }


@dataclass(frozen=True)
class LiveLLMProviderExecutionPlan:
    provider: str
    model: str
    reviewer: str
    reviewer_run_key: ReviewerRunKey
    reservation_key: str
    reservation_status: str
    target_hash: str
    context_policy: str | None
    request_text: str
    request_hash: str
    request_byte_count: int
    package_fingerprint: str
    redaction_status: RedactionStatus
    raw_provider_submission_enabled: bool
    raw_provider_submission_approved: bool
    raw_provider_submission_opt_in_source: str | None
    raw_trace_persistence_enabled: bool
    raw_trace_persistence_approved: bool
    raw_trace_persistence_opt_in_source: str | None
    live_call_budget_cost: int
    budget_before: int
    budget_after: int
    preview: ProviderRequestPreview


@dataclass(frozen=True)
class LiveLLMPolicyAuditRecord:
    status: str
    reason_code: str | None
    provider: str | None
    model: str | None
    reviewer: str
    reviewer_run_key: str
    reservation_key: str | None
    reservation_status: str
    target: dict[str, Any]
    target_hash: str
    context: dict[str, Any]
    redaction_status: dict[str, Any]
    raw_provider_submission: dict[str, Any]
    raw_trace_persistence: dict[str, Any]
    opt_in: dict[str, Any]
    budget: dict[str, Any]
    package_fingerprint: str
    request_hash: str | None
    request_byte_count: int | None
    trace_request_text: str | None = None

    def to_ordered_dict(self, *, include_request_text: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "status": self.status,
            "reason_code": self.reason_code,
            "provider": self.provider,
            "model": self.model,
            "reviewer": self.reviewer,
            "reviewer_run_key": self.reviewer_run_key,
            "reservation_key": self.reservation_key,
            "reservation_status": self.reservation_status,
            "target": self.target,
            "target_hash": self.target_hash,
            "context": self.context,
            "redaction_status": self.redaction_status,
            "raw_provider_submission": self.raw_provider_submission,
            "raw_trace_persistence": self.raw_trace_persistence,
            "opt_in": self.opt_in,
            "budget": self.budget,
            "package_fingerprint": self.package_fingerprint,
            "request_hash": self.request_hash,
            "request_byte_count": self.request_byte_count,
        }
        if (
            include_request_text
            and self.raw_trace_persistence["enabled"]
            and self.raw_trace_persistence["approved"]
            and self.trace_request_text is not None
        ):
            data["request_text"] = self.trace_request_text
        return data


@dataclass(frozen=True)
class LiveLLMPolicyResult:
    status: str
    reason_code: LiveLLMBlockedReasonCode | None
    execution_plan: LiveLLMProviderExecutionPlan | None
    ledger: LiveLLMBudgetLedger
    audit_record: LiveLLMPolicyAuditRecord

    def to_audit_dict(self, *, include_request_text: bool = False) -> dict[str, Any]:
        return self.audit_record.to_ordered_dict(include_request_text=include_request_text)


@dataclass(frozen=True)
class ProviderFailureSummary:
    reason_code: ProviderFailureReasonCode
    message: str
    retryable: bool
    redaction_status: RedactionStatus
    request_id: str | None = None

    def to_ordered_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code.value,
            "message": self.message,
            "retryable": self.retryable,
            "request_id": self.request_id,
            "redaction_status": _redaction_status_dict(self.redaction_status),
        }


def evaluate_live_llm_policy(
    package: ReviewerContextPackage,
    policy_input: LiveLLMPolicyInput,
    *,
    ledger: LiveLLMBudgetLedger,
) -> LiveLLMPolicyResult:
    if not isinstance(package, ReviewerContextPackage):
        raise ValueError("package must be a ReviewerContextPackage")
    if not isinstance(policy_input, LiveLLMPolicyInput):
        raise ValueError("policy_input must be a LiveLLMPolicyInput")
    if not isinstance(ledger, LiveLLMBudgetLedger):
        raise ValueError("ledger must be a LiveLLMBudgetLedger")

    provider = _normalized_non_empty(policy_input.provider)
    model = _normalized_non_empty(policy_input.model)

    try:
        validate_reviewer_adapter_input(package=package, run_key=policy_input.reviewer_run_key)
    except ReviewerAdapterBoundaryError as exc:
        return _blocked(
            package,
            policy_input,
            ledger=ledger,
            provider=provider,
            model=model,
            reason_code=(
                LiveLLMBlockedReasonCode.REVIEWER_RUN_KEY_MISMATCH
                if "run key" in str(exc)
                else LiveLLMBlockedReasonCode.REVIEWER_ADAPTER_BOUNDARY_FAILED
            ),
        )

    if not policy_input.live_llm_enabled or _normalized_non_empty(policy_input.live_llm_opt_in_source) is None:
        return _blocked(
            package,
            policy_input,
            ledger=ledger,
            provider=provider,
            model=model,
            reason_code=LiveLLMBlockedReasonCode.MISSING_LIVE_OPT_IN,
        )
    if provider is None:
        return _blocked(
            package,
            policy_input,
            ledger=ledger,
            provider=provider,
            model=model,
            reason_code=LiveLLMBlockedReasonCode.MISSING_PROVIDER,
        )
    if model is None:
        return _blocked(
            package,
            policy_input,
            ledger=ledger,
            provider=provider,
            model=model,
            reason_code=LiveLLMBlockedReasonCode.MISSING_MODEL,
        )
    if (
        policy_input.raw_provider_submission_enabled
        and not policy_input.raw_provider_submission_approved
        or policy_input.raw_provider_submission_approved
        and _normalized_non_empty(policy_input.raw_provider_submission_opt_in_source) is None
    ):
        return _blocked(
            package,
            policy_input,
            ledger=ledger,
            provider=provider,
            model=model,
            reason_code=LiveLLMBlockedReasonCode.RAW_PROVIDER_NOT_APPROVED,
        )
    if (
        policy_input.raw_trace_persistence_enabled
        and not policy_input.raw_trace_persistence_approved
        or policy_input.raw_trace_persistence_approved
        and _normalized_non_empty(policy_input.raw_trace_persistence_opt_in_source) is None
    ):
        return _blocked(
            package,
            policy_input,
            ledger=ledger,
            provider=provider,
            model=model,
            reason_code=LiveLLMBlockedReasonCode.RAW_TRACE_NOT_APPROVED,
        )

    preview = build_provider_request_preview(
        package,
        provider=provider,
        raw_provider_submission_enabled=policy_input.raw_provider_submission_enabled,
        raw_trace_persistence_enabled=policy_input.raw_trace_persistence_enabled,
    )
    preview = ProviderRequestPreview(
        provider=provider,
        model=model,
        reviewer=preview.reviewer,
        target_hash=preview.target_hash,
        request_text=preview.request_text,
        redaction_status=preview.redaction_status,
        raw_provider_submission_enabled=preview.raw_provider_submission_enabled,
        raw_trace_persistence_enabled=preview.raw_trace_persistence_enabled,
        tools=preview.tools,
        tool_schemas=preview.tool_schemas,
        live_call_budget_cost=LIVE_LLM_CALL_COST,
    )
    request_text = preview.request_text
    request_hash = _domain_json_hash(
        "reviewgraph.live_llm.request.v1",
        {
            "request_text": request_text,
        },
    )
    request_byte_count = len(request_text.encode("utf-8"))
    package_fingerprint = live_llm_package_fingerprint(package)
    reservation_key = _reservation_key(
        policy_input,
        provider=provider,
        model=model,
        request_hash=request_hash,
    )
    budget_before = ledger.reserved_live_calls
    existing = ledger.reservation_for_run_key(policy_input.reviewer_run_key.stable_key())
    if existing is not None:
        if existing.reservation_key != reservation_key:
            return _blocked(
                package,
                policy_input,
                ledger=ledger,
                provider=provider,
                model=model,
                reason_code=LiveLLMBlockedReasonCode.LIVE_CALL_RESERVATION_CONFLICT,
                request_hash=request_hash,
                request_byte_count=request_byte_count,
                package_fingerprint=package_fingerprint,
                reservation_key=reservation_key,
                reservation_status="conflict",
                redaction_status=preview.redaction_status,
            )
        if existing.package_fingerprint != package_fingerprint:
            return _blocked(
                package,
                policy_input,
                ledger=ledger,
                provider=provider,
                model=model,
                reason_code=LiveLLMBlockedReasonCode.LIVE_CALL_RESERVATION_CONFLICT,
                request_hash=request_hash,
                request_byte_count=request_byte_count,
                package_fingerprint=package_fingerprint,
                reservation_key=reservation_key,
                reservation_status="conflict",
                redaction_status=preview.redaction_status,
            )
        if ledger.reserved_live_calls > package.context_budget.max_live_calls:
            return _blocked(
                package,
                policy_input,
                ledger=ledger,
                provider=provider,
                model=model,
                reason_code=LiveLLMBlockedReasonCode.LIVE_CALL_BUDGET_EXCEEDED,
                request_hash=request_hash,
                request_byte_count=request_byte_count,
                package_fingerprint=package_fingerprint,
                reservation_key=reservation_key,
                reservation_status="blocked",
                redaction_status=preview.redaction_status,
            )
        return _approved(
            package,
            policy_input,
            preview=preview,
            ledger=ledger,
            provider=provider,
            model=model,
            request_text=request_text,
            request_hash=request_hash,
            request_byte_count=request_byte_count,
            package_fingerprint=package_fingerprint,
            reservation_key=reservation_key,
            reservation_status="existing",
            budget_before=budget_before,
            budget_after=budget_before,
        )

    if budget_before + LIVE_LLM_CALL_COST > package.context_budget.max_live_calls:
        return _blocked(
            package,
            policy_input,
            ledger=ledger,
            provider=provider,
            model=model,
            reason_code=LiveLLMBlockedReasonCode.LIVE_CALL_BUDGET_EXCEEDED,
            request_hash=request_hash,
            request_byte_count=request_byte_count,
            package_fingerprint=package_fingerprint,
            reservation_key=reservation_key,
            reservation_status="blocked",
            redaction_status=preview.redaction_status,
        )

    reservation = LiveLLMReservation(
        run_key_stable=policy_input.reviewer_run_key.stable_key(),
        reservation_key=reservation_key,
        provider=_redacted_scalar(provider) if provider is not None else None,
        model=_redacted_scalar(model) if model is not None else None,
        target_hash=policy_input.reviewer_run_key.target_hash,
        config_hash=policy_input.reviewer_run_key.config_hash,
        request_hash=request_hash,
        request_byte_count=request_byte_count,
        package_fingerprint=package_fingerprint,
    )
    next_ledger = ledger.reserve(reservation)
    return _approved(
        package,
        policy_input,
        preview=preview,
        ledger=next_ledger,
        provider=provider,
        model=model,
        request_text=request_text,
        request_hash=request_hash,
        request_byte_count=request_byte_count,
        package_fingerprint=package_fingerprint,
        reservation_key=reservation_key,
        reservation_status="new",
        budget_before=budget_before,
        budget_after=next_ledger.reserved_live_calls,
    )


def summarize_provider_failure(
    reason_code: ProviderFailureReasonCode,
    *,
    message: str,
    request_id: str | None = None,
) -> ProviderFailureSummary:
    if not isinstance(reason_code, ProviderFailureReasonCode):
        raise ValueError("reason_code must be a ProviderFailureReasonCode")
    _require_non_empty(message, "message")
    _require_optional_non_empty(request_id, "request_id")
    message_redaction = redact_text(message)
    request_id_redaction = redact_text(request_id) if request_id is not None else None
    safe_request_id = request_id
    if request_id_redaction is not None and request_id_redaction.redacted:
        safe_request_id = None
    replacement_count = message_redaction.replacement_count
    categories = list(message_redaction.categories)
    if request_id_redaction is not None:
        replacement_count += request_id_redaction.replacement_count
        categories.extend(request_id_redaction.categories)
    return ProviderFailureSummary(
        reason_code=reason_code,
        message=message_redaction.text,
        retryable=reason_code in RETRYABLE_PROVIDER_FAILURES,
        request_id=safe_request_id,
        redaction_status=RedactionStatus(
            redacted=replacement_count > 0,
            replacement_count=replacement_count,
            categories=tuple(dict.fromkeys(categories)),
        ),
    )


def _approved(
    package: ReviewerContextPackage,
    policy_input: LiveLLMPolicyInput,
    *,
    preview: ProviderRequestPreview,
    ledger: LiveLLMBudgetLedger,
    provider: str,
    model: str,
    request_text: str,
    request_hash: str,
    request_byte_count: int,
    package_fingerprint: str,
    reservation_key: str,
    reservation_status: str,
    budget_before: int,
    budget_after: int,
) -> LiveLLMPolicyResult:
    plan = LiveLLMProviderExecutionPlan(
        provider=provider,
        model=model,
        reviewer=package.reviewer.name,
        reviewer_run_key=policy_input.reviewer_run_key,
        reservation_key=reservation_key,
        reservation_status=reservation_status,
        target_hash=package.review_target.target_hash(),
        context_policy=package.reviewer_config.context_policy,
        request_text=request_text,
        request_hash=request_hash,
        request_byte_count=request_byte_count,
        package_fingerprint=package_fingerprint,
        redaction_status=preview.redaction_status,
        raw_provider_submission_enabled=policy_input.raw_provider_submission_enabled,
        raw_provider_submission_approved=policy_input.raw_provider_submission_approved,
        raw_provider_submission_opt_in_source=policy_input.raw_provider_submission_opt_in_source,
        raw_trace_persistence_enabled=policy_input.raw_trace_persistence_enabled,
        raw_trace_persistence_approved=policy_input.raw_trace_persistence_approved,
        raw_trace_persistence_opt_in_source=policy_input.raw_trace_persistence_opt_in_source,
        live_call_budget_cost=LIVE_LLM_CALL_COST,
        budget_before=budget_before,
        budget_after=budget_after,
        preview=preview,
    )
    return LiveLLMPolicyResult(
        status="approved",
        reason_code=None,
        execution_plan=plan,
        ledger=ledger,
        audit_record=_audit_record(
            package,
            policy_input,
            status="approved",
            reason_code=None,
            provider=provider,
            model=model,
            reservation_key=reservation_key,
            reservation_status=reservation_status,
            budget_before=budget_before,
            budget_after=budget_after,
            request_hash=request_hash,
            request_byte_count=request_byte_count,
            package_fingerprint=package_fingerprint,
            redaction_status=preview.redaction_status,
            request_text=request_text,
        ),
    )


def _blocked(
    package: ReviewerContextPackage,
    policy_input: LiveLLMPolicyInput,
    *,
    ledger: LiveLLMBudgetLedger,
    provider: str | None,
    model: str | None,
    reason_code: LiveLLMBlockedReasonCode,
    request_hash: str | None = None,
    request_byte_count: int | None = None,
    package_fingerprint: str | None = None,
    reservation_key: str | None = None,
    reservation_status: str = "not_reserved",
    redaction_status: RedactionStatus | None = None,
) -> LiveLLMPolicyResult:
    budget_before = ledger.reserved_live_calls
    return LiveLLMPolicyResult(
        status="blocked",
        reason_code=reason_code,
        execution_plan=None,
        ledger=ledger,
        audit_record=_audit_record(
            package,
            policy_input,
            status="blocked",
            reason_code=reason_code.value,
            provider=provider,
            model=model,
            reservation_key=reservation_key,
            reservation_status=reservation_status,
            budget_before=budget_before,
            budget_after=budget_before,
            request_hash=request_hash,
            request_byte_count=request_byte_count,
            package_fingerprint=package_fingerprint or live_llm_package_fingerprint(package),
            redaction_status=redaction_status or _empty_redaction_status(),
            request_text=None,
        ),
    )


def _audit_record(
    package: ReviewerContextPackage,
    policy_input: LiveLLMPolicyInput,
    *,
    status: str,
    reason_code: str | None,
    provider: str | None,
    model: str | None,
    reservation_key: str | None,
    reservation_status: str,
    budget_before: int,
    budget_after: int,
    request_hash: str | None,
    request_byte_count: int | None,
    package_fingerprint: str,
    redaction_status: RedactionStatus,
    request_text: str | None,
) -> LiveLLMPolicyAuditRecord:
    return LiveLLMPolicyAuditRecord(
        status=status,
        reason_code=reason_code,
        provider=_redacted_scalar(provider) if provider is not None else None,
        model=_redacted_scalar(model) if model is not None else None,
        reviewer=package.reviewer.name,
        reviewer_run_key=policy_input.reviewer_run_key.stable_key(),
        reservation_key=reservation_key,
        reservation_status=reservation_status,
        target=_redacted_data(package.review_target.to_ordered_dict()),
        target_hash=package.review_target.target_hash(),
        context=_redacted_data(_context_audit(package)),
        redaction_status=_redaction_status_dict(redaction_status),
        raw_provider_submission=_redacted_data({
            "enabled": policy_input.raw_provider_submission_enabled,
            "approved": policy_input.raw_provider_submission_approved,
            "opt_in_source": policy_input.raw_provider_submission_opt_in_source,
        }),
        raw_trace_persistence=_redacted_data({
            "enabled": policy_input.raw_trace_persistence_enabled,
            "approved": policy_input.raw_trace_persistence_approved,
            "opt_in_source": policy_input.raw_trace_persistence_opt_in_source,
        }),
        opt_in=_redacted_data({
            "live_llm_enabled": policy_input.live_llm_enabled,
            "source": policy_input.live_llm_opt_in_source,
        }),
        budget={
            "limit": package.context_budget.max_live_calls,
            "before": budget_before,
            "after": budget_after,
            "cost": LIVE_LLM_CALL_COST,
        },
        package_fingerprint=package_fingerprint,
        request_hash=request_hash,
        request_byte_count=request_byte_count,
        trace_request_text=(
            request_text
            if policy_input.raw_trace_persistence_enabled
            and policy_input.raw_trace_persistence_approved
            else None
        ),
    )


def _context_audit(package: ReviewerContextPackage) -> dict[str, Any]:
    return {
        "active_stage": package.active_stage,
        "context_policy": package.reviewer_config.context_policy,
        "capabilities": list(package.reviewer_config.capabilities),
        "retained_file_paths": list(
            package.context_budget.retained_file_paths
            or tuple(changed_file.path for changed_file in package.changed_files)
        ),
        "retained_memory_ids": list(
            package.context_budget.retained_memory_ids
            or tuple(memory.id for memory in package.memory_references)
        ),
        "omitted_file_paths": list(package.context_budget.omitted_file_paths),
        "omitted_memory_ids": list(package.context_budget.omitted_memory_ids),
        "omitted_context": list(package.trace.omitted_context),
        "truncation": list(package.trace.truncation),
    }


def live_llm_package_fingerprint(package: ReviewerContextPackage) -> str:
    return _domain_json_hash(
        "reviewgraph.live_llm.package.v1",
        {
            "active_stage": package.active_stage,
            "capability_policy": package.trace.capability_policy,
            "changed_files": [
                {
                    "additions": changed_file.additions,
                    "deletions": changed_file.deletions,
                    "patch": changed_file.patch,
                    "patch_status": changed_file.patch_status,
                    "path": changed_file.path,
                    "previous_path": changed_file.previous_path,
                    "status": changed_file.status,
                }
                for changed_file in package.changed_files
            ],
            "config": package.trace.config,
            "context_budget": _context_budget_fingerprint(package),
            "local_notes": [
                {
                    "body": note.body,
                    "evidence": note.evidence,
                    "id": note.id,
                    "title": note.title,
                }
                for note in package.local_notes
            ],
            "memory": [
                {
                    "actionable": memory.actionable,
                    "body": memory.body,
                    "id": memory.id,
                    "passive_reason": memory.passive_reason,
                    "resolved_status": memory.resolved_status,
                    "source_id": memory.source_id,
                    "source_provider": memory.source_provider,
                    "source_type": memory.source_type,
                    "thread_id": memory.thread_id,
                    "trust_label": memory.trust_label,
                }
                for memory in package.memory_references
            ],
            "omitted_context": package.trace.omitted_context,
            "review_target": package.review_target.to_ordered_dict(),
            "reviewer": {
                "name": package.reviewer.name,
                "reasons": list(package.reviewer.reasons),
                "stage": package.reviewer.stage,
            },
            "truncation": package.trace.truncation,
        },
    )


def _context_budget_fingerprint(package: ReviewerContextPackage) -> dict[str, Any]:
    budget = package.context_budget
    return {
        "max_changed_files": budget.max_changed_files,
        "max_live_calls": budget.max_live_calls,
        "max_memory_bytes": budget.max_memory_bytes,
        "max_patch_bytes": budget.max_patch_bytes,
        "max_reviewers": budget.max_reviewers,
        "original_changed_file_count": budget.original_changed_file_count,
        "retained_changed_file_count": budget.retained_changed_file_count,
        "original_patch_bytes": budget.original_patch_bytes,
        "retained_patch_bytes": budget.retained_patch_bytes,
        "original_memory_count": budget.original_memory_count,
        "retained_memory_count": budget.retained_memory_count,
        "original_memory_bytes": budget.original_memory_bytes,
        "retained_memory_bytes": budget.retained_memory_bytes,
        "original_reviewer_count": budget.original_reviewer_count,
        "retained_reviewer_count": budget.retained_reviewer_count,
        "omitted_file_paths": list(budget.omitted_file_paths),
        "omitted_memory_ids": list(budget.omitted_memory_ids),
        "planned_live_calls": budget.planned_live_calls,
        "reasons": list(budget.reasons),
        "retained_file_paths": list(budget.retained_file_paths),
        "retained_memory_ids": list(budget.retained_memory_ids),
        "retained_reviewer_ids": list(budget.retained_reviewer_ids),
        "deferred_reviewer_ids": list(budget.deferred_reviewer_ids),
        "retained_live_call_reviewer_ids": list(budget.retained_live_call_reviewer_ids),
        "deferred_live_call_reviewer_ids": list(budget.deferred_live_call_reviewer_ids),
        "generated_local_note_ids": list(budget.generated_local_note_ids),
        "truncation": [
            {
                "note": notice.note,
                "original_bytes": notice.original_bytes,
                "original_count": notice.original_count,
                "resource": notice.resource,
                "retained_bytes": notice.retained_bytes,
                "retained_count": notice.retained_count,
                "truncated": notice.truncated,
            }
            for notice in budget.truncation
        ],
        "omitted_context": [
            {
                "affected_id": marker.affected_id,
                "dimension": marker.dimension,
                "id": marker.id,
                "original_bytes": marker.original_bytes,
                "original_count": marker.original_count,
                "reason_code": marker.reason_code,
                "retained_bytes": marker.retained_bytes,
                "retained_count": marker.retained_count,
                "source": marker.source,
            }
            for marker in budget.omitted_context
        ],
    }


def _reservation_key(
    policy_input: LiveLLMPolicyInput,
    *,
    provider: str,
    model: str,
    request_hash: str,
) -> str:
    return _domain_json_hash(
        "reviewgraph.live_llm.reservation.v1",
        {
            "config_hash": policy_input.reviewer_run_key.config_hash,
            "model": model,
            "provider": provider,
            "request_hash": request_hash,
            "run_key": policy_input.reviewer_run_key.stable_key(),
            "target_hash": policy_input.reviewer_run_key.target_hash,
        },
    )


def _domain_json_hash(domain: str, data: Any) -> str:
    payload = json.dumps(
        {"domain": domain, "data": data},
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _redaction_status_dict(redaction_status: RedactionStatus) -> dict[str, Any]:
    return {
        "redacted": redaction_status.redacted,
        "replacement_count": redaction_status.replacement_count,
        "categories": list(redaction_status.categories),
        "status": redaction_status.status.value,
    }


def _redacted_data(data: Any) -> Any:
    redaction = redact_text(json.dumps(data, sort_keys=True, separators=(",", ":")))
    return json.loads(redaction.text)


def _redacted_scalar(value: str) -> str:
    return redact_text(value).text


def _empty_redaction_status() -> RedactionStatus:
    return RedactionStatus(redacted=False, replacement_count=0)


def _normalized_non_empty(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_optional_non_empty(value: str | None, field_name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(f"{field_name} must be a non-empty string or None")
