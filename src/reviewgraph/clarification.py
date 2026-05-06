from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from reviewgraph.models import (
    ClarificationAnswer,
    ClarificationRequest,
    ClarificationState,
    ClarificationStatus,
    ReviewState,
)


@dataclass(frozen=True)
class ClarificationGateResult:
    pending_ids: tuple[str, ...]
    blocking_pending_ids: tuple[str, ...]
    status: dict[str, ClarificationStatus]
    blocks_posting: bool


def evaluate_clarification_gate(
    requests: Iterable[ClarificationRequest],
) -> ClarificationGateResult:
    pending_ids: list[str] = []
    blocking_pending_ids: list[str] = []
    status: dict[str, ClarificationStatus] = {}
    for request in requests:
        request_status = request.status or ClarificationState.PENDING
        status[request.id] = ClarificationStatus(
            request_id=request.id,
            status=request_status,
        )
        if request_status != ClarificationState.PENDING:
            continue
        pending_ids.append(request.id)
        if request.blocks_verdict:
            blocking_pending_ids.append(request.id)
    return ClarificationGateResult(
        pending_ids=tuple(pending_ids),
        blocking_pending_ids=tuple(blocking_pending_ids),
        status=status,
        blocks_posting=bool(blocking_pending_ids),
    )


def ingest_clarification_answer(review_state: ReviewState, answer: ClarificationAnswer) -> None:
    request_index, request = _pending_request(review_state, answer.request_id)
    review_state.clarifications.append(answer)
    answered_request = replace(request, status=ClarificationState.ANSWERED)
    review_state.clarification_requests[request_index] = answered_request
    review_state.clarification_status[answer.request_id] = ClarificationStatus(
        request_id=answer.request_id,
        status=ClarificationState.ANSWERED,
    )
    review_state.pending_clarification_ids[:] = [
        request_id
        for request_id in review_state.pending_clarification_ids
        if request_id != answer.request_id
    ]
    if answer.request_id not in review_state.ready_clarification_ids:
        review_state.ready_clarification_ids.append(answer.request_id)


def _pending_request(
    review_state: ReviewState,
    request_id: str,
) -> tuple[int, ClarificationRequest]:
    for index, request in enumerate(review_state.clarification_requests):
        if request.id != request_id:
            continue
        status = request.status or ClarificationState.PENDING
        if status != ClarificationState.PENDING:
            raise ValueError(f"clarification request {request_id} is not pending")
        return index, request
    raise ValueError(f"clarification request {request_id} was not found")
