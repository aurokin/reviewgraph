from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Protocol

from reviewgraph.findings import normalize_reviewer_output
from reviewgraph.llm_policy import (
    LiveLLMBudgetLedger,
    LiveLLMPolicyInput,
    LiveLLMPolicyResult,
    ProviderFailureReasonCode,
    evaluate_live_llm_policy,
    summarize_provider_failure,
)
from reviewgraph.models import (
    LiveLLMReviewerEvidence,
    NormalizationError,
    RedactionStatus,
    ReviewerResult,
    ReviewerRunKey,
    ReviewerRunStatusValue,
)
from reviewgraph.redaction import redact_data, redact_text
from reviewgraph.reviewer_context import ReviewerContextPackage
from reviewgraph.reviewers import validate_live_policy_adapter_input


DEFAULT_LIVE_LLM_MAX_ATTEMPTS = 2
DEFAULT_LIVE_LLM_TIMEOUT_SECONDS = 30
DEFAULT_LIVE_LLM_TOTAL_TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class LiveLLMProviderRequest:
    provider: str
    model: str
    reviewer: str
    target_hash: str
    request_text: str
    request_hash: str
    timeout_seconds: int
    attempt: int
    run_key_stable: str


@dataclass(frozen=True)
class LiveLLMProviderResponse:
    text: str
    request_id: str | None = None


@dataclass(frozen=True)
class LiveLLMAttemptResult:
    policy_result: LiveLLMPolicyResult
    reviewer_result: ReviewerResult


@dataclass(frozen=True)
class LiveLLMRetryRunResult:
    attempts: tuple[LiveLLMAttemptResult, ...]
    ledger: LiveLLMBudgetLedger
    trace_events: tuple[dict[str, object], ...]

    @property
    def final_result(self) -> ReviewerResult:
        if not self.attempts:
            raise ValueError("live LLM retry run has no attempts")
        return self.attempts[-1].reviewer_result


class LiveLLMProviderTransport(Protocol):
    def __call__(self, request: LiveLLMProviderRequest) -> LiveLLMProviderResponse:
        ...


class LiveLLMProviderError(RuntimeError):
    def __init__(
        self,
        reason_code: ProviderFailureReasonCode,
        message: str,
        *,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.request_id = request_id


@dataclass
class FakeLiveLLMProviderTransport:
    responses: list[LiveLLMProviderResponse | LiveLLMProviderError]

    def __post_init__(self) -> None:
        self.calls: list[LiveLLMProviderRequest] = []

    def __call__(self, request: LiveLLMProviderRequest) -> LiveLLMProviderResponse:
        self.calls.append(request)
        if not self.responses:
            raise LiveLLMProviderError(
                ProviderFailureReasonCode.PROVIDER_UNAVAILABLE,
                "fake live LLM transport has no response",
            )
        response = self.responses.pop(0)
        if isinstance(response, LiveLLMProviderError):
            raise response
        return response


def execute_live_llm_reviewer_attempt(
    *,
    policy_result: LiveLLMPolicyResult,
    package: ReviewerContextPackage,
    run_key: ReviewerRunKey,
    current_ledger: LiveLLMBudgetLedger,
    transport: LiveLLMProviderTransport,
    timeout_seconds: int = DEFAULT_LIVE_LLM_TIMEOUT_SECONDS,
) -> ReviewerResult:
    policy_result = validate_live_policy_adapter_input(
        policy_result=policy_result,
        package=package,
        run_key=run_key,
        current_ledger=current_ledger,
    )
    plan = policy_result.execution_plan
    if plan is None:
        return _failed_result(
            run_key,
            errors=("live LLM policy did not produce an execution plan",),
            evidence=_evidence(
                policy_result=policy_result,
                current_ledger=current_ledger,
                run_key=run_key,
                status="failed",
                response_text=None,
                response_request_id=None,
                failure_reason="missing_execution_plan",
            ),
        )
    request = LiveLLMProviderRequest(
        provider=plan.provider,
        model=plan.model,
        reviewer=plan.reviewer,
        target_hash=plan.target_hash,
        request_text=plan.request_text,
        request_hash=plan.request_hash,
        timeout_seconds=timeout_seconds,
        attempt=run_key.attempt,
        run_key_stable=run_key.stable_key(),
    )
    try:
        response = transport(request)
    except LiveLLMProviderError as exc:
        summary = summarize_provider_failure(
            exc.reason_code,
            message=str(exc),
            request_id=exc.request_id,
        )
        return _failed_result(
            run_key,
            errors=(f"live LLM provider failed: {summary.reason_code.value}",),
            evidence=_evidence(
                policy_result=policy_result,
                current_ledger=current_ledger,
                run_key=run_key,
                status="failed",
                response_text=None,
                response_request_id=summary.request_id,
                failure_reason=summary.reason_code.value,
                failure_summary=summary.to_ordered_dict(),
            ),
        )
    except Exception as exc:
        summary = summarize_provider_failure(
            ProviderFailureReasonCode.UNKNOWN_PROVIDER_ERROR,
            message=str(exc),
        )
        return _failed_result(
            run_key,
            errors=(f"live LLM provider failed: {summary.reason_code.value}",),
            evidence=_evidence(
                policy_result=policy_result,
                current_ledger=current_ledger,
                run_key=run_key,
                status="failed",
                response_text=None,
                response_request_id=summary.request_id,
                failure_reason=summary.reason_code.value,
                failure_summary=summary.to_ordered_dict(),
            ),
        )
    return _result_from_provider_text(
        response.text,
        request_id=response.request_id,
        policy_result=policy_result,
        current_ledger=current_ledger,
        run_key=run_key,
    )


def run_live_llm_reviewer_with_retries(
    *,
    package: ReviewerContextPackage,
    initial_run_key: ReviewerRunKey,
    policy_input: LiveLLMPolicyInput,
    ledger: LiveLLMBudgetLedger,
    transport: LiveLLMProviderTransport,
    max_attempts: int = DEFAULT_LIVE_LLM_MAX_ATTEMPTS,
    timeout_seconds: int = DEFAULT_LIVE_LLM_TIMEOUT_SECONDS,
    total_timeout_seconds: int = DEFAULT_LIVE_LLM_TOTAL_TIMEOUT_SECONDS,
) -> LiveLLMRetryRunResult:
    if type(max_attempts) is not int or max_attempts <= 0:
        raise ValueError("max_attempts must be a positive integer")
    if type(timeout_seconds) is not int or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be a positive integer")
    if type(total_timeout_seconds) is not int or total_timeout_seconds <= 0:
        raise ValueError("total_timeout_seconds must be a positive integer")
    if total_timeout_seconds < timeout_seconds:
        raise ValueError("total_timeout_seconds must be greater than or equal to timeout_seconds")
    attempts: list[LiveLLMAttemptResult] = []
    trace_events: list[dict[str, object]] = []
    current_ledger = ledger
    retry_of = initial_run_key.stable_key()
    effective_max_attempts = min(max_attempts, total_timeout_seconds // timeout_seconds)
    if package.context_budget.max_live_calls < effective_max_attempts:
        raise ValueError("live LLM budget must cover effective max attempts before provider execution")
    if effective_max_attempts < max_attempts:
        trace_events.append(
            {
                "event": "live_llm_total_timeout_cap_applied",
                "configured_max_attempts": max_attempts,
                "effective_max_attempts": effective_max_attempts,
                "timeout_seconds": timeout_seconds,
                "total_timeout_seconds": total_timeout_seconds,
            }
        )
    for attempt in range(1, effective_max_attempts + 1):
        run_key = replace(
            initial_run_key,
            attempt=attempt,
            retry_of=None if attempt == 1 else retry_of,
        )
        attempt_policy_input = replace(policy_input, reviewer_run_key=run_key)
        policy_result = evaluate_live_llm_policy(package, attempt_policy_input, ledger=current_ledger)
        current_ledger = policy_result.ledger
        trace_events.append(_policy_trace(policy_result, run_key=run_key))
        if policy_result.status != "approved":
            result = _failed_result(
                run_key,
                errors=(f"live LLM policy blocked: {policy_result.reason_code.value}",),
                evidence=_evidence(
                    policy_result=policy_result,
                    current_ledger=current_ledger,
                    run_key=run_key,
                    status="failed",
                    response_text=None,
                    response_request_id=None,
                    failure_reason=policy_result.reason_code.value if policy_result.reason_code else "blocked",
                ),
            )
            attempts.append(LiveLLMAttemptResult(policy_result=policy_result, reviewer_result=result))
            break
        trace_events.append({"event": "live_llm_provider_attempt_started", "run_key": run_key.stable_key()})
        result = execute_live_llm_reviewer_attempt(
            policy_result=policy_result,
            package=package,
            run_key=run_key,
            current_ledger=current_ledger,
            transport=transport,
            timeout_seconds=timeout_seconds,
        )
        attempts.append(LiveLLMAttemptResult(policy_result=policy_result, reviewer_result=result))
        if result.status == ReviewerRunStatusValue.COMPLETED:
            trace_events.append({"event": "live_llm_provider_attempt_succeeded", "run_key": run_key.stable_key()})
            break
        retryable = bool(result.live_llm_evidence and result.live_llm_evidence.data.get("retryable") is True)
        trace_events.append({"event": "live_llm_provider_attempt_failed", "run_key": run_key.stable_key()})
        if not retryable:
            break
        if attempt == effective_max_attempts:
            exhausted_evidence = _retry_exhausted_evidence(result.live_llm_evidence)
            attempts[-1] = LiveLLMAttemptResult(
                policy_result=policy_result,
                reviewer_result=replace(
                    result,
                    errors=("live LLM provider failed: retry_exhausted",),
                    live_llm_evidence=exhausted_evidence,
                ),
            )
            trace_events.append({"event": "live_llm_retry_exhausted", "run_key": run_key.stable_key()})
            if effective_max_attempts < max_attempts:
                trace_events.append({"event": "live_llm_total_timeout_exhausted", "run_key": run_key.stable_key()})
            break
        trace_events.append({"event": "live_llm_retry_scheduled", "run_key": run_key.stable_key()})
    return LiveLLMRetryRunResult(
        attempts=tuple(attempts),
        ledger=current_ledger,
        trace_events=tuple(trace_events),
    )


def _result_from_provider_text(
    text: str,
    *,
    request_id: str | None,
    policy_result: LiveLLMPolicyResult,
    current_ledger: LiveLLMBudgetLedger,
    run_key: ReviewerRunKey,
) -> ReviewerResult:
    redacted_text = redact_text(text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        evidence = _evidence(
            policy_result=policy_result,
            current_ledger=current_ledger,
            run_key=run_key,
            status="failed",
            response_text=text,
            response_request_id=request_id,
            failure_reason=ProviderFailureReasonCode.MALFORMED_RESPONSE.value,
        )
        return _failed_result(
            run_key,
            errors=("live LLM provider response is not valid JSON",),
            evidence=evidence,
            normalization_errors=(
                NormalizationError(
                    code="invalid_json",
                    message="live LLM provider response is not valid JSON",
                    run_key=run_key,
                    repairable=False,
                ),
            ),
        )
    if not isinstance(parsed, dict):
        return _failed_result(
            run_key,
            errors=("live LLM provider response must be a JSON object",),
            evidence=_evidence(
                policy_result=policy_result,
                current_ledger=current_ledger,
                run_key=run_key,
                status="failed",
                response_text=text,
                response_request_id=request_id,
                failure_reason=ProviderFailureReasonCode.MALFORMED_RESPONSE.value,
            ),
            normalization_errors=(
                NormalizationError(
                    code="invalid_output_type",
                    message="live LLM provider response must be a JSON object",
                    run_key=run_key,
                    repairable=False,
                ),
            ),
        )
    redacted_output = redact_data(parsed)
    if not isinstance(redacted_output.data, dict):
        redacted_parsed = {"value": repr(redacted_output.data)}
    else:
        redacted_parsed = redacted_output.data
    normalized = normalize_reviewer_output(redacted_parsed, run_key)
    evidence = _evidence(
        policy_result=policy_result,
        current_ledger=current_ledger,
        run_key=run_key,
        status="completed" if not normalized.fatal_errors else "failed",
        response_text=text,
        response_request_id=request_id,
        response_redaction=RedactionStatus(
            redacted=redacted_text.redacted or redacted_output.redaction_status.redacted,
            replacement_count=redacted_text.replacement_count + redacted_output.redaction_status.replacement_count,
            categories=tuple(
                dict.fromkeys(redacted_text.categories + redacted_output.redaction_status.categories)
            ),
        ),
    )
    if normalized.fatal_errors:
        return _failed_result(
            run_key,
            errors=tuple(error.message for error in normalized.fatal_errors),
            evidence=evidence,
            raw_output=redacted_parsed,
            normalization_errors=normalized.errors,
        )
    return ReviewerResult(
        run_key=run_key,
        status=ReviewerRunStatusValue.COMPLETED,
        raw_output=redacted_parsed,
        findings=normalized.findings,
        clarification_requests=normalized.clarification_requests,
        local_notes=normalized.local_notes,
        suggested_replies=normalized.suggested_replies,
        suppressed_outputs=normalized.suppressed_outputs,
        normalization_errors=normalized.errors,
        live_llm_evidence=evidence,
    )


def _failed_result(
    run_key: ReviewerRunKey,
    *,
    errors: tuple[str, ...],
    evidence: LiveLLMReviewerEvidence,
    raw_output: object = None,
    normalization_errors: tuple[NormalizationError, ...] = (),
) -> ReviewerResult:
    return ReviewerResult(
        run_key=run_key,
        status=ReviewerRunStatusValue.FAILED,
        raw_output=raw_output if isinstance(raw_output, (dict, str)) or raw_output is None else {"value": repr(raw_output)},
        errors=errors,
        normalization_errors=normalization_errors,
        live_llm_evidence=evidence,
    )


def _evidence(
    *,
    policy_result: LiveLLMPolicyResult,
    current_ledger: LiveLLMBudgetLedger,
    run_key: ReviewerRunKey,
    status: str,
    response_text: str | None,
    response_request_id: str | None,
    failure_reason: str | None = None,
    failure_summary: dict[str, object] | None = None,
    response_redaction: RedactionStatus | None = None,
) -> LiveLLMReviewerEvidence:
    plan = policy_result.execution_plan
    response_hash = _text_hash(response_text) if response_text is not None else None
    response_byte_count = len(response_text.encode("utf-8")) if response_text is not None else None
    response_redaction = response_redaction or _response_redaction_status(response_text)
    safe_response_request_id = response_request_id
    if response_request_id is not None:
        request_id_redaction = redact_text(response_request_id)
        if request_id_redaction.redacted:
            safe_response_request_id = request_id_redaction.text
            response_redaction = RedactionStatus(
                redacted=True,
                replacement_count=response_redaction.replacement_count + request_id_redaction.replacement_count,
                categories=tuple(
                    dict.fromkeys(response_redaction.categories + request_id_redaction.categories)
                ),
            )
    retryable = False
    if failure_summary is not None:
        retryable = bool(failure_summary.get("retryable") is True)
    return LiveLLMReviewerEvidence(
        data={
            "status": status,
            "provider": _safe_text(plan.provider) if plan is not None else policy_result.audit_record.provider,
            "model": _safe_text(plan.model) if plan is not None else policy_result.audit_record.model,
            "reviewer": run_key.reviewer,
            "target_hash": run_key.target_hash,
            "run_key": run_key.stable_key(),
            "attempt": run_key.attempt,
            "retry_of": run_key.retry_of,
            "context_policy": plan.context_policy if plan is not None else None,
            "policy_audit": policy_result.to_audit_dict(),
            "ledger": current_ledger.to_ordered_dict(),
            "request_hash": plan.request_hash if plan is not None else policy_result.audit_record.request_hash,
            "request_byte_count": (
                plan.request_byte_count if plan is not None else policy_result.audit_record.request_byte_count
            ),
            "response_hash": response_hash,
            "response_byte_count": response_byte_count,
            "response_request_id": safe_response_request_id,
            "response_redaction_status": {
                "redacted": response_redaction.redacted,
                "replacement_count": response_redaction.replacement_count,
                "categories": list(response_redaction.categories),
                "status": response_redaction.status.value,
            },
            "failure_reason": failure_reason,
            "failure_summary": failure_summary,
            "retryable": retryable,
            "raw_request_retained": False,
            "raw_response_retained": False,
        }
    )


def _policy_trace(policy_result: LiveLLMPolicyResult, *, run_key: ReviewerRunKey) -> dict[str, object]:
    return {
        "event": "live_llm_policy_" + policy_result.status,
        "run_key": run_key.stable_key(),
        "reason_code": policy_result.reason_code.value if policy_result.reason_code else None,
        "reservation_status": policy_result.audit_record.reservation_status,
        "ledger": policy_result.ledger.to_ordered_dict(),
    }


def _text_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _safe_text(text: str) -> str:
    return redact_text(text).text


def _response_redaction_status(text: str | None) -> RedactionStatus:
    if text is None:
        return RedactionStatus(redacted=False, replacement_count=0)
    redaction = redact_text(text)
    return RedactionStatus(
        redacted=redaction.redacted,
        replacement_count=redaction.replacement_count,
        categories=redaction.categories,
    )


def _retry_exhausted_evidence(evidence: LiveLLMReviewerEvidence | None) -> LiveLLMReviewerEvidence | None:
    if evidence is None:
        return None
    data = dict(evidence.to_ordered_dict())
    data["last_failure_reason"] = data.get("failure_reason")
    data["failure_reason"] = ProviderFailureReasonCode.RETRY_EXHAUSTED.value
    data["retryable"] = False
    failure_summary = data.get("failure_summary")
    if isinstance(failure_summary, dict):
        data["failure_summary"] = {
            **failure_summary,
            "reason_code": ProviderFailureReasonCode.RETRY_EXHAUSTED.value,
            "retryable": False,
        }
    return LiveLLMReviewerEvidence(data=data)
