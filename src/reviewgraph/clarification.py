from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from reviewgraph.models import ClarificationRequest, ClarificationState, ClarificationStatus


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
