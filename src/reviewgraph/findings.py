from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from reviewgraph.models import (
    ClarificationRequest,
    ClarificationState,
    GRAPH_OWNED_REVIEWER_FIELDS,
    LocalNote,
    NormalizationError,
    OutputClassification,
    RawReviewerFinding,
    ReviewStage,
    ReviewerRunKey,
    SuggestedReply,
    SuppressedReviewerOutput,
)


GRAPH_OWNED_SUPPRESSION_REASON = "Raw reviewer finding attempted to set graph-owned fields and was suppressed."
RAW_ITEM_GRAPH_OWNED_FIELDS = GRAPH_OWNED_REVIEWER_FIELDS | frozenset(
    {
        "reviewer",
        "resume_target",
        "resume_target_reviewers",
        "resume_target_stage",
        "source_run_key",
        "source_stage",
        "stage",
        "status",
    }
)


@dataclass(frozen=True)
class NormalizationResult:
    raw_output: Mapping[str, Any]
    run_key: ReviewerRunKey
    findings: tuple[RawReviewerFinding, ...] = ()
    clarification_requests: tuple[ClarificationRequest, ...] = ()
    local_notes: tuple[LocalNote, ...] = ()
    suggested_replies: tuple[SuggestedReply, ...] = ()
    suppressed_outputs: tuple[SuppressedReviewerOutput, ...] = ()
    errors: tuple[NormalizationError, ...] = ()

    @property
    def fatal_errors(self) -> tuple[NormalizationError, ...]:
        return tuple(error for error in self.errors if error.fatal)


def normalize_reviewer_output(
    raw_output: Mapping[str, Any],
    run_key: ReviewerRunKey,
) -> NormalizationResult:
    items = raw_output.get("items")
    if not isinstance(items, list):
        return _fatal_result(
            raw_output,
            run_key,
            code="invalid_items",
            message="fake reviewer output requires an items list",
            repairable=True,
        )

    findings: list[RawReviewerFinding] = []
    clarification_requests: list[ClarificationRequest] = []
    local_notes: list[LocalNote] = []
    suggested_replies: list[SuggestedReply] = []
    suppressed_outputs: list[SuppressedReviewerOutput] = []
    errors: list[NormalizationError] = []

    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            return _fatal_result(
                raw_output,
                run_key,
                code="invalid_item",
                message="raw reviewer output items must be objects",
                repairable=True,
                item_index=index,
            )
        item_type = _required_str(item, "type", "raw reviewer output item", raw_output, run_key, index)
        if isinstance(item_type, NormalizationResult):
            return item_type
        if item_type == "finding":
            raw_finding = _finding(item, raw_output=raw_output, run_key=run_key, item_index=index)
            if isinstance(raw_finding, NormalizationResult):
                return raw_finding
            if isinstance(raw_finding, _RejectedFinding):
                suppressed_outputs.append(raw_finding.suppressed)
                errors.append(raw_finding.error)
                continue
            findings.append(raw_finding)
        elif item_type == "local_note":
            note = _local_note(item, raw_output=raw_output, run_key=run_key, item_index=index)
            if isinstance(note, NormalizationResult):
                return note
            if isinstance(note, _RejectedArtifact):
                suppressed_outputs.append(note.suppressed)
                errors.append(note.error)
                continue
            local_notes.append(note)
        elif item_type == "clarification_request":
            request = _clarification_request(item, raw_output=raw_output, run_key=run_key, item_index=index)
            if isinstance(request, NormalizationResult):
                return request
            if isinstance(request, _RejectedArtifact):
                suppressed_outputs.append(request.suppressed)
                errors.append(request.error)
                continue
            clarification_requests.append(request)
        elif item_type == "suggested_reply":
            reply = _suggested_reply(item, raw_output=raw_output, run_key=run_key, item_index=index)
            if isinstance(reply, NormalizationResult):
                return reply
            if isinstance(reply, _RejectedArtifact):
                suppressed_outputs.append(reply.suppressed)
                errors.append(reply.error)
                continue
            suggested_replies.append(reply)
        elif item_type in {"suppressed", "non_finding"}:
            suppressed = _suppressed_output(item, raw_output=raw_output, run_key=run_key, item_index=index)
            if isinstance(suppressed, NormalizationResult):
                return suppressed
            if isinstance(suppressed, _RejectedArtifact):
                suppressed_outputs.append(suppressed.suppressed)
                errors.append(suppressed.error)
                continue
            suppressed_outputs.append(suppressed)
        else:
            return _fatal_result(
                raw_output,
                run_key,
                code="unsupported_item_type",
                message=f"unsupported raw reviewer output type: {item_type}",
                repairable=True,
                item_id=_optional_item_id(item),
                item_index=index,
            )

    return NormalizationResult(
        raw_output=raw_output,
        run_key=run_key,
        findings=tuple(findings),
        clarification_requests=tuple(clarification_requests),
        local_notes=tuple(local_notes),
        suggested_replies=tuple(suggested_replies),
        suppressed_outputs=tuple(suppressed_outputs),
        errors=tuple(errors),
    )


@dataclass(frozen=True)
class _RejectedFinding:
    suppressed: SuppressedReviewerOutput
    error: NormalizationError


_RejectedArtifact = _RejectedFinding


def _finding(
    item: Mapping[str, Any],
    *,
    raw_output: Mapping[str, Any],
    run_key: ReviewerRunKey,
    item_index: int,
) -> RawReviewerFinding | _RejectedFinding | NormalizationResult:
    if rejected := _graph_owned_artifact(item, run_key=run_key, item_index=item_index):
        return rejected
    try:
        return RawReviewerFinding.from_mapping(dict(item))
    except ValueError as exc:
        return _fatal_result(
            raw_output,
            run_key,
            code="invalid_finding",
            message=str(exc),
            repairable=True,
            item_id=_optional_item_id(item),
            item_index=item_index,
        )


def _local_note(
    item: Mapping[str, Any],
    *,
    raw_output: Mapping[str, Any],
    run_key: ReviewerRunKey,
    item_index: int,
) -> LocalNote | _RejectedArtifact | NormalizationResult:
    if rejected := _graph_owned_artifact(item, run_key=run_key, item_index=item_index):
        return rejected
    try:
        return LocalNote(
            id=_required_str_value(item, "id", "local_note"),
            title=_required_str_value(item, "title", "local_note"),
            body=_required_str_value(item, "body", "local_note"),
            evidence=_required_str_value(item, "evidence", "local_note"),
        )
    except ValueError as exc:
        return _fatal_result(
            raw_output,
            run_key,
            code="invalid_local_note",
            message=str(exc),
            repairable=True,
            item_id=_optional_item_id(item),
            item_index=item_index,
        )


def _clarification_request(
    item: Mapping[str, Any],
    *,
    raw_output: Mapping[str, Any],
    run_key: ReviewerRunKey,
    item_index: int,
) -> ClarificationRequest | _RejectedArtifact | NormalizationResult:
    if rejected := _graph_owned_artifact(item, run_key=run_key, item_index=item_index):
        return rejected
    try:
        evidence_sources = _optional_str_tuple(item, "evidence_sources", "clarification_request")
        evidence_memory_ids = _optional_str_tuple(item, "evidence_memory_ids", "clarification_request")
        return ClarificationRequest(
            id=_required_str_value(item, "id", "clarification_request"),
            reviewer=run_key.reviewer,
            question=_required_str_value(item, "question", "clarification_request"),
            why_it_matters=_required_str_value(item, "why_it_matters", "clarification_request"),
            blocks_verdict=_optional_bool(item, "blocks_verdict", default=True),
            source_stage=run_key.stage.value,
            source_run_key=run_key,
            status=ClarificationState.PENDING,
            resume_target_stage=ReviewStage.CLARIFICATION_REVIEW,
            resume_target_reviewers=(run_key.reviewer,),
            evidence_sources=evidence_sources,
            evidence_memory_ids=evidence_memory_ids,
        )
    except ValueError as exc:
        return _fatal_result(
            raw_output,
            run_key,
            code="invalid_clarification_request",
            message=str(exc),
            repairable=True,
            item_id=_optional_item_id(item),
            item_index=item_index,
        )


def _suggested_reply(
    item: Mapping[str, Any],
    *,
    raw_output: Mapping[str, Any],
    run_key: ReviewerRunKey,
    item_index: int,
) -> SuggestedReply | _RejectedArtifact | NormalizationResult:
    if rejected := _graph_owned_artifact(item, run_key=run_key, item_index=item_index):
        return rejected
    try:
        return SuggestedReply(
            id=_required_str_value(item, "id", "suggested_reply"),
            source_comment_id=_required_str_value(item, "source_comment_id", "suggested_reply"),
            proposed_body=_required_str_value(item, "proposed_body", "suggested_reply"),
        )
    except ValueError as exc:
        return _fatal_result(
            raw_output,
            run_key,
            code="invalid_suggested_reply",
            message=str(exc),
            repairable=True,
            item_id=_optional_item_id(item),
            item_index=item_index,
        )


def _suppressed_output(
    item: Mapping[str, Any],
    *,
    raw_output: Mapping[str, Any],
    run_key: ReviewerRunKey,
    item_index: int,
) -> SuppressedReviewerOutput | _RejectedArtifact | NormalizationResult:
    if rejected := _graph_owned_artifact(item, run_key=run_key, item_index=item_index):
        return rejected
    try:
        return SuppressedReviewerOutput(
            id=_required_str_value(item, "id", "suppressed"),
            reason=_required_str_value(item, "reason", "suppressed"),
            classification=OutputClassification.NON_FINDING,
        )
    except ValueError as exc:
        return _fatal_result(
            raw_output,
            run_key,
            code="invalid_non_finding",
            message=str(exc),
            repairable=True,
            item_id=_optional_item_id(item),
            item_index=item_index,
        )


def _graph_owned_artifact(
    item: Mapping[str, Any],
    *,
    run_key: ReviewerRunKey,
    item_index: int,
) -> _RejectedArtifact | None:
    graph_owned_fields = sorted(RAW_ITEM_GRAPH_OWNED_FIELDS.intersection(item))
    if not graph_owned_fields:
        return None
    item_id = _optional_item_id(item)
    return _RejectedArtifact(
        suppressed=SuppressedReviewerOutput(
            id=f"suppressed-{item_id}" if item_id else "suppressed-invalid-raw-item",
            reason=GRAPH_OWNED_SUPPRESSION_REASON,
        ),
        error=NormalizationError(
            code="graph_owned_reviewer_fields",
            message=f"raw reviewer output item contains graph-owned fields: {', '.join(graph_owned_fields)}",
            run_key=run_key,
            repairable=False,
            fatal=False,
            item_id=item_id,
            item_index=item_index,
            rejected_fields=tuple(graph_owned_fields),
        ),
    )


def _fatal_result(
    raw_output: Mapping[str, Any],
    run_key: ReviewerRunKey,
    *,
    code: str,
    message: str,
    repairable: bool,
    item_id: str | None = None,
    item_index: int | None = None,
) -> NormalizationResult:
    return NormalizationResult(
        raw_output=raw_output,
        run_key=run_key,
        errors=(
            NormalizationError(
                code=code,
                message=message,
                run_key=run_key,
                repairable=repairable,
                fatal=True,
                item_id=item_id,
                item_index=item_index,
            ),
        ),
    )


def _required_str(
    item: Mapping[str, Any],
    field: str,
    label: str,
    raw_output: Mapping[str, Any],
    run_key: ReviewerRunKey,
    item_index: int,
) -> str | NormalizationResult:
    try:
        return _required_str_value(item, field, label)
    except ValueError as exc:
        return _fatal_result(
            raw_output,
            run_key,
            code=f"invalid_{field}",
            message=str(exc),
            repairable=True,
            item_id=_optional_item_id(item),
            item_index=item_index,
        )


def _required_str_value(item: Mapping[str, Any], field: str, label: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label}.{field} is required")
    return value


def _optional_str_tuple(item: Mapping[str, Any], field: str, label: str) -> tuple[str, ...]:
    if field not in item:
        return ()
    value = item[field]
    if not isinstance(value, list) or any(not isinstance(entry, str) or not entry for entry in value):
        raise ValueError(f"{label}.{field} must be an array of non-empty strings")
    return tuple(value)


def _optional_bool(item: Mapping[str, Any], field: str, *, default: bool) -> bool:
    value = item.get(field, default)
    if type(value) is not bool:
        raise ValueError(f"clarification_request.{field} must be a boolean")
    return value


def _optional_item_id(item: Mapping[str, Any]) -> str | None:
    item_id = item.get("id")
    return item_id if isinstance(item_id, str) and item_id else None
