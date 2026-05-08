from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from reviewgraph.findings import normalize_reviewer_output
from reviewgraph.llm_policy import LiveLLMBudgetLedger, LiveLLMPolicyResult, live_llm_package_fingerprint
from reviewgraph.models import (
    NormalizationError,
    ReviewerRepairRecord,
    ReviewerResult,
    ReviewerRunKey,
    ReviewerRunStatusValue,
)
from reviewgraph.reviewer_boundaries import (
    ReviewerAdapterBoundaryError,
    require_reviewer_run_key,
    require_context_package,
    validate_reviewer_adapter_input,
)
from reviewgraph.reviewer_context import ReviewerContextPackage, build_provider_request_preview


FakeReviewerRegistry = Mapping[tuple[str, str, str], Mapping[str, Any]]
REPAIRABLE_REVIEWER_OUTPUT_ERROR_CODES = frozenset(
    {
        "invalid_json",
        "invalid_output_type",
        "invalid_items",
        "invalid_item",
        "invalid_type",
        "unsupported_item_type",
        "invalid_finding",
        "invalid_local_note",
        "invalid_clarification_request",
        "invalid_suggested_reply",
        "invalid_non_finding",
        "normalizer_exception",
    }
)


@dataclass(frozen=True)
class FakeReviewerAdapter:
    fixture_id: str
    registry: Mapping[tuple[str, str, str], object]

    def run(self, package: ReviewerContextPackage) -> object:
        require_context_package(package)
        key = (self.fixture_id, package.reviewer.name, package.active_stage)
        if key not in self.registry:
            raise KeyError(
                "missing raw reviewer output for selected reviewer: "
                f"{package.reviewer.name}/{package.active_stage}"
            )
        return self.registry[key]


def execute_fake_reviewer(
    *,
    adapter: FakeReviewerAdapter,
    package: ReviewerContextPackage,
    run_key: ReviewerRunKey,
) -> ReviewerResult:
    validate_reviewer_adapter_input(package=package, run_key=run_key)
    try:
        output = adapter.run(package)
    except KeyError as exc:
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            errors=(str(exc).strip("'"),),
        )
    repair_output: object = None
    repair_envelope = False
    if isinstance(output, Mapping) and ("raw_output" in output or "repair_output" in output):
        _validate_repair_envelope(
            output,
            expected_reviewer=package.reviewer.name,
            expected_stage=package.active_stage,
        )
        repair_envelope = True
        repair_output = output["repair_output"]
        output = output.get("raw_output")
    result = _execute_unrepaired_fake_output(output, run_key=run_key)
    if repair_envelope and _should_attempt_repair(result):
        return _repair_fake_reviewer_output(
            original_result=result,
            original_output=output,
            repair_output=repair_output,
            run_key=run_key,
        )
    return result


def validate_live_policy_adapter_input(
    *,
    policy_result: LiveLLMPolicyResult,
    package: ReviewerContextPackage,
    run_key: ReviewerRunKey,
    current_ledger: LiveLLMBudgetLedger,
) -> LiveLLMPolicyResult:
    validate_reviewer_adapter_input(package=package, run_key=run_key)
    if not isinstance(current_ledger, LiveLLMBudgetLedger):
        raise ReviewerAdapterBoundaryError("live reviewer adapter requires current live-call ledger")
    if not isinstance(policy_result, LiveLLMPolicyResult):
        raise ReviewerAdapterBoundaryError("live reviewer adapter requires LiveLLMPolicyResult")
    require_reviewer_run_key(run_key)
    if policy_result.status != "approved" or policy_result.execution_plan is None:
        raise ReviewerAdapterBoundaryError("live reviewer adapter requires approved policy result with execution plan")
    if policy_result.execution_plan.reviewer_run_key != run_key:
        raise ReviewerAdapterBoundaryError("live reviewer adapter run key does not match policy result")
    if policy_result.execution_plan.package_fingerprint != live_llm_package_fingerprint(package):
        raise ReviewerAdapterBoundaryError("live reviewer adapter policy result does not match package")
    reservation = current_ledger.reservation_for_run_key(run_key.stable_key())
    if reservation is None:
        raise ReviewerAdapterBoundaryError("live reviewer adapter ledger is missing reservation")
    if reservation.reservation_key != policy_result.execution_plan.reservation_key:
        raise ReviewerAdapterBoundaryError("live reviewer adapter ledger reservation does not match policy result")
    if reservation.package_fingerprint != policy_result.execution_plan.package_fingerprint:
        raise ReviewerAdapterBoundaryError("live reviewer adapter ledger reservation does not match policy result")
    if reservation.request_hash != policy_result.execution_plan.request_hash:
        raise ReviewerAdapterBoundaryError("live reviewer adapter ledger reservation does not match policy result")
    if reservation.request_byte_count != policy_result.execution_plan.request_byte_count:
        raise ReviewerAdapterBoundaryError("live reviewer adapter ledger reservation does not match policy result")
    preview = build_provider_request_preview(
        package,
        provider=policy_result.execution_plan.provider,
        raw_provider_submission_enabled=policy_result.execution_plan.raw_provider_submission_enabled,
        raw_trace_persistence_enabled=policy_result.execution_plan.raw_trace_persistence_enabled,
    )
    if preview.request_text != policy_result.execution_plan.request_text:
        raise ReviewerAdapterBoundaryError("live reviewer adapter policy result does not match package")
    return policy_result


def execute_live_policy_reviewer_stub(
    *,
    policy_result: LiveLLMPolicyResult,
    package: ReviewerContextPackage,
    run_key: ReviewerRunKey,
    current_ledger: LiveLLMBudgetLedger,
) -> ReviewerResult:
    validate_live_policy_adapter_input(
        policy_result=policy_result,
        package=package,
        run_key=run_key,
        current_ledger=current_ledger,
    )
    return ReviewerResult(
        run_key=run_key,
        status=ReviewerRunStatusValue.FAILED,
        errors=("live reviewer provider execution is not implemented in AUR-232",),
    )


def _execute_unrepaired_fake_output(output: object, *, run_key: ReviewerRunKey) -> ReviewerResult:
    if output is None:
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            errors=("fake reviewer output is missing",),
            normalization_errors=(
                _normalization_error(
                    run_key,
                    code="missing_output",
                    message="fake reviewer output is missing",
                    repairable=True,
                ),
            ),
        )
    if isinstance(output, str):
        try:
            parsed_output = json.loads(output)
        except json.JSONDecodeError:
            return ReviewerResult(
                run_key=run_key,
                status=ReviewerRunStatusValue.FAILED,
                raw_output=output,
                errors=("fake reviewer output is not valid JSON",),
                normalization_errors=(
                    _normalization_error(
                        run_key,
                        code="invalid_json",
                        message="fake reviewer output is not valid JSON",
                        repairable=True,
                    ),
                ),
            )
        return _execute_parsed_reviewer_output(
            parsed_output,
            raw_output=output,
            parsed_from_json_string=True,
            run_key=run_key,
        )
    return _execute_parsed_reviewer_output(
        output,
        raw_output=output,
        parsed_from_json_string=False,
        run_key=run_key,
    )


def _execute_parsed_reviewer_output(
    output: object,
    *,
    raw_output: object,
    parsed_from_json_string: bool,
    run_key: ReviewerRunKey,
) -> ReviewerResult:
    if not isinstance(output, Mapping):
        message = "fake reviewer output must be a mapping"
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            raw_output=_raw_output_for_result(raw_output),
            errors=(message,),
            normalization_errors=(
                _normalization_error(
                    run_key,
                    code="invalid_output_type",
                    message=message,
                    repairable=not parsed_from_json_string,
                ),
            ),
        )
    if output.get("failure") is True:
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            raw_output=_raw_output_for_result(raw_output),
            errors=(_optional_error(output, "fake reviewer failed"),),
        )
    try:
        normalized = normalize_reviewer_output(output, run_key)
    except (TypeError, ValueError, KeyError) as exc:
        message = f"fake reviewer output malformed: {exc}"
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            raw_output=_raw_output_for_result(raw_output),
            errors=(message,),
            normalization_errors=(
                _normalization_error(
                    run_key,
                    code="normalizer_exception",
                    message=message,
                    repairable=True,
                ),
            ),
        )
    if normalized.fatal_errors:
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            raw_output=_raw_output_for_result(raw_output),
            errors=tuple(error.message for error in normalized.fatal_errors),
            normalization_errors=normalized.errors,
        )
    return ReviewerResult(
        run_key=run_key,
        status=ReviewerRunStatusValue.COMPLETED,
        raw_output=_raw_output_for_result(raw_output),
        findings=normalized.findings,
        clarification_requests=normalized.clarification_requests,
        local_notes=normalized.local_notes,
        suggested_replies=normalized.suggested_replies,
        suppressed_outputs=normalized.suppressed_outputs,
        normalization_errors=normalized.errors,
    )


def _raw_output_for_result(output: object) -> Mapping[str, Any] | str | None:
    if output is None or isinstance(output, (Mapping, str)):
        return output
    return {"value": repr(output)}


def _should_attempt_repair(result: ReviewerResult) -> bool:
    if result.repair_record is not None:
        return False
    fatal_errors = tuple(error for error in result.normalization_errors if error.fatal)
    if not fatal_errors:
        return False
    return all(
        error.repairable and error.code in REPAIRABLE_REVIEWER_OUTPUT_ERROR_CODES
        for error in fatal_errors
    )


def _repair_fake_reviewer_output(
    *,
    original_result: ReviewerResult,
    original_output: object,
    repair_output: object,
    run_key: ReviewerRunKey,
) -> ReviewerResult:
    original_errors = original_result.normalization_errors
    repaired_mapping = _repair_output_mapping(repair_output, run_key=run_key)
    if isinstance(repaired_mapping, NormalizationError):
        repair_errors = original_errors + (repaired_mapping,)
        return _failed_repair_result(
            original_result=original_result,
            original_output=original_output,
            repaired_output=_repair_output_for_record(repair_output),
            repair_errors=repair_errors,
        )
    try:
        normalized = normalize_reviewer_output(repaired_mapping, run_key)
    except (TypeError, ValueError, KeyError) as exc:
        repair_errors = original_errors + (
            _normalization_error(
                run_key,
                code="repair_normalizer_exception",
                message=f"fake reviewer repair output malformed: {exc}",
                repairable=False,
            ),
        )
        return _failed_repair_result(
            original_result=original_result,
            original_output=original_output,
            repaired_output=repaired_mapping,
            repair_errors=repair_errors,
        )
    if normalized.fatal_errors:
        repair_errors = original_errors + tuple(
            _repair_normalization_error(error) for error in normalized.fatal_errors
        )
        return _failed_repair_result(
            original_result=original_result,
            original_output=original_output,
            repaired_output=repaired_mapping,
            repair_errors=repair_errors,
        )
    repair_record = ReviewerRepairRecord(
        attempt_count=1,
        status="succeeded",
        original_output=_repair_output_for_record(original_output),
        repaired_output=repaired_mapping,
        errors=original_errors,
    )
    return ReviewerResult(
        run_key=run_key,
        status=ReviewerRunStatusValue.COMPLETED,
        raw_output=original_result.raw_output,
        findings=normalized.findings,
        clarification_requests=normalized.clarification_requests,
        local_notes=normalized.local_notes,
        suggested_replies=normalized.suggested_replies,
        suppressed_outputs=normalized.suppressed_outputs,
        normalization_errors=normalized.errors,
        repair_record=repair_record,
    )


def _repair_output_mapping(output: object, *, run_key: ReviewerRunKey) -> Mapping[str, Any] | NormalizationError:
    if isinstance(output, str):
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            return _normalization_error(
                run_key,
                code="repair_invalid_json",
                message="fake reviewer repair output is not valid JSON",
                repairable=False,
            )
        output = parsed
    if not isinstance(output, Mapping):
        return _normalization_error(
            run_key,
            code="repair_invalid_output_type",
            message="fake reviewer repair output must be a mapping",
            repairable=False,
        )
    return output


def _failed_repair_result(
    *,
    original_result: ReviewerResult,
    original_output: object,
    repaired_output: object,
    repair_errors: tuple[NormalizationError, ...],
) -> ReviewerResult:
    repair_record = ReviewerRepairRecord(
        attempt_count=1,
        status="failed",
        original_output=_repair_output_for_record(original_output),
        repaired_output=repaired_output,
        errors=repair_errors,
    )
    return ReviewerResult(
        run_key=original_result.run_key,
        status=ReviewerRunStatusValue.FAILED,
        raw_output=original_result.raw_output,
        errors=("fake reviewer output repair failed",),
        normalization_errors=repair_errors,
        repair_record=repair_record,
    )


def _repair_normalization_error(error: NormalizationError) -> NormalizationError:
    return NormalizationError(
        code=f"repair_{error.code}",
        message=f"fake reviewer repair output malformed: {error.message}",
        run_key=error.run_key,
        repairable=False,
        fatal=error.fatal,
        item_id=error.item_id,
        item_index=error.item_index,
        rejected_fields=error.rejected_fields,
    )


def _repair_output_for_record(output: object) -> object:
    if _is_json_value(output):
        return output
    return {"value": repr(output)}


def _is_json_value(output: object) -> bool:
    if output is None or isinstance(output, (str, int, float, bool)):
        return True
    if isinstance(output, Mapping):
        return all(isinstance(key, str) and _is_json_value(value) for key, value in output.items())
    if isinstance(output, list):
        return all(_is_json_value(value) for value in output)
    return False


def fake_registry_from_fixture_outputs(
    *,
    fixture_id: str,
    outputs: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
) -> FakeReviewerRegistry:
    registry: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for output in outputs:
        reviewer = _required_str(output, "reviewer")
        stage = _required_str(output, "stage")
        if "raw_output" in output or "repair_output" in output:
            _validate_repair_envelope(output, expected_reviewer=reviewer, expected_stage=stage)
        registry[(fixture_id, reviewer, stage)] = output
    return registry


def _normalization_error(
    run_key: ReviewerRunKey,
    *,
    code: str,
    message: str,
    repairable: bool,
) -> NormalizationError:
    return NormalizationError(
        code=code,
        message=message,
        run_key=run_key,
        repairable=repairable,
        fatal=True,
    )


def _required_str(item: Mapping[str, Any], field: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _validate_repair_envelope(
    output: Mapping[str, Any],
    *,
    expected_reviewer: str,
    expected_stage: str,
) -> None:
    allowed_keys = {"reviewer", "stage", "raw_output", "repair_output"}
    extra_keys = sorted(set(output) - allowed_keys)
    if extra_keys:
        raise ValueError(
            "fake reviewer repair envelope contains unsupported fields: "
            f"{', '.join(extra_keys)}"
        )
    reviewer = _required_str(output, "reviewer")
    stage = _required_str(output, "stage")
    if reviewer != expected_reviewer or stage != expected_stage:
        raise ValueError("fake reviewer repair envelope reviewer/stage must match the selected reviewer")
    if "raw_output" not in output:
        raise ValueError("fake reviewer repair envelope requires raw_output")
    if "repair_output" not in output:
        raise ValueError("fake reviewer repair envelope requires repair_output")


def _optional_str(item: Mapping[str, Any], field: str, *, default: str | None = None) -> str | None:
    value = item.get(field, default)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string or null")
    return value


def _optional_error(output: Mapping[str, Any], default: str) -> str:
    value = output.get("error", default)
    return value if isinstance(value, str) and value else default
