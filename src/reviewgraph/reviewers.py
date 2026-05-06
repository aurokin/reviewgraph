from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from reviewgraph.findings import normalize_reviewer_output
from reviewgraph.models import (
    NormalizationError,
    ReviewerResult,
    ReviewerRunKey,
    ReviewerRunStatusValue,
)
from reviewgraph.reviewer_context import ReviewerContextPackage


FakeReviewerRegistry = Mapping[tuple[str, str, str], Mapping[str, Any]]


@dataclass(frozen=True)
class FakeReviewerAdapter:
    fixture_id: str
    registry: Mapping[tuple[str, str, str], object]

    def run(self, package: ReviewerContextPackage) -> object:
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
    try:
        output = adapter.run(package)
    except KeyError as exc:
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            errors=(str(exc).strip("'"),),
        )
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
    if not isinstance(output, Mapping):
        message = "fake reviewer output must be a mapping"
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            raw_output={"value": repr(output)},
            errors=(message,),
            normalization_errors=(
                _normalization_error(
                    run_key,
                    code="invalid_output_type",
                    message=message,
                    repairable=True,
                ),
            ),
        )
    if output.get("failure") is True:
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            raw_output=output,
            errors=(_optional_error(output, "fake reviewer failed"),),
        )
    try:
        normalized = normalize_reviewer_output(output, run_key)
    except (TypeError, ValueError, KeyError) as exc:
        message = f"fake reviewer output malformed: {exc}"
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            raw_output=output,
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
            raw_output=output,
            errors=tuple(error.message for error in normalized.fatal_errors),
            normalization_errors=normalized.errors,
        )
    return ReviewerResult(
        run_key=run_key,
        status=ReviewerRunStatusValue.COMPLETED,
        raw_output=output,
        findings=normalized.findings,
        clarification_requests=normalized.clarification_requests,
        local_notes=normalized.local_notes,
        suggested_replies=normalized.suggested_replies,
        suppressed_outputs=normalized.suppressed_outputs,
        normalization_errors=normalized.errors,
    )


def fake_registry_from_fixture_outputs(
    *,
    fixture_id: str,
    outputs: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
) -> FakeReviewerRegistry:
    registry: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for output in outputs:
        reviewer = _required_str(output, "reviewer")
        stage = _required_str(output, "stage")
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
