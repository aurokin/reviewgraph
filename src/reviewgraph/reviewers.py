from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from reviewgraph.models import (
    ClarificationRequest,
    GRAPH_OWNED_REVIEWER_FIELDS,
    LocalNote,
    OutputClassification,
    RawReviewerFinding,
    ReviewerResult,
    ReviewerRunKey,
    ReviewerRunStatusValue,
    SuggestedReply,
    SuppressedReviewerOutput,
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
        )
    if isinstance(output, str):
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            raw_output=output,
            errors=("fake reviewer output is not valid JSON",),
        )
    if not isinstance(output, Mapping):
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            raw_output={"value": repr(output)},
            errors=("fake reviewer output must be a mapping",),
        )
    if output.get("failure") is True:
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            raw_output=output,
            errors=(_optional_error(output, "fake reviewer failed"),),
        )
    items = output.get("items")
    if not isinstance(items, list):
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            raw_output=output,
            errors=("fake reviewer output requires an items list",),
        )
    try:
        return _result_from_items(
            run_key=run_key,
            raw_output=output,
            reviewer=_required_str(output, "reviewer"),
            items=items,
        )
    except (TypeError, ValueError, KeyError) as exc:
        return ReviewerResult(
            run_key=run_key,
            status=ReviewerRunStatusValue.FAILED,
            raw_output=output,
            errors=(f"fake reviewer output malformed: {exc}",),
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


def _result_from_items(
    *,
    run_key: ReviewerRunKey,
    raw_output: Mapping[str, Any],
    reviewer: str,
    items: list[Any],
) -> ReviewerResult:
    findings: list[RawReviewerFinding] = []
    clarification_requests: list[ClarificationRequest] = []
    local_notes: list[LocalNote] = []
    suggested_replies: list[SuggestedReply] = []
    suppressed_outputs: list[SuppressedReviewerOutput] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("items must be mappings")
        item_type = _required_str(item, "type")
        if item_type == "finding":
            findings.append(_finding(item))
        elif item_type == "local_note":
            local_notes.append(_local_note(item))
        elif item_type == "clarification_request":
            clarification_requests.append(_clarification_request(item, reviewer=reviewer))
        elif item_type == "suggested_reply":
            suggested_replies.append(_suggested_reply(item))
        elif item_type in {"suppressed", "non_finding"}:
            suppressed_outputs.append(_suppressed_output(item))
        else:
            raise ValueError(f"unsupported fake reviewer item type: {item_type}")
    return ReviewerResult(
        run_key=run_key,
        status=ReviewerRunStatusValue.COMPLETED,
        raw_output=raw_output,
        findings=tuple(findings),
        clarification_requests=tuple(clarification_requests),
        local_notes=tuple(local_notes),
        suggested_replies=tuple(suggested_replies),
        suppressed_outputs=tuple(suppressed_outputs),
    )


def _finding(item: Mapping[str, Any]) -> RawReviewerFinding:
    return RawReviewerFinding.from_mapping(
        {
            key: value
            for key, value in item.items()
            if key not in GRAPH_OWNED_REVIEWER_FIELDS
        }
    )


def _local_note(item: Mapping[str, Any]) -> LocalNote:
    return LocalNote(
        id=_required_str(item, "id"),
        title=_required_str(item, "title"),
        body=_required_str(item, "body"),
        evidence=_required_str(item, "evidence"),
    )


def _clarification_request(item: Mapping[str, Any], *, reviewer: str) -> ClarificationRequest:
    return ClarificationRequest(
        id=_required_str(item, "id"),
        reviewer=reviewer,
        question=_required_str(item, "question"),
        why_it_matters=_required_str(item, "why_it_matters"),
        blocks_verdict=bool(item.get("blocks_verdict", item.get("blocking", True))),
    )


def _suggested_reply(item: Mapping[str, Any]) -> SuggestedReply:
    return SuggestedReply(
        id=_required_str(item, "id"),
        source_comment_id=_required_str(item, "source_comment_id"),
        proposed_body=_required_str(item, "proposed_body"),
    )


def _suppressed_output(item: Mapping[str, Any]) -> SuppressedReviewerOutput:
    return SuppressedReviewerOutput(
        id=_required_str(item, "id"),
        reason=_required_str(item, "reason"),
        classification=OutputClassification.NON_FINDING,
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
