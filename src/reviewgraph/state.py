from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from reviewgraph.models import ReviewStage


NORMAL_REVIEW_STAGES: tuple[ReviewStage, ...] = (
    ReviewStage.INITIAL_TRIAGE,
    ReviewStage.SPECIALIZED_REVIEW,
    ReviewStage.LOGIC_REVIEW,
)


class StageCursorError(ValueError):
    pass


class StageCursorFields(Protocol):
    active_stage: ReviewStage | None
    suspended_stage: ReviewStage | None
    stage_queue: list[ReviewStage]
    completed_stages: list[ReviewStage]


@dataclass
class StageCursor:
    active_stage: ReviewStage | None
    suspended_stage: ReviewStage | None
    stage_queue: list[ReviewStage]
    completed_stages: list[ReviewStage]


@dataclass(frozen=True)
class StageCursorTransition:
    active_stage_before: ReviewStage | None
    active_stage_after: ReviewStage | None
    suspended_stage_before: ReviewStage | None
    suspended_stage_after: ReviewStage | None
    stage_queue_before: tuple[ReviewStage, ...]
    stage_queue_after: tuple[ReviewStage, ...]
    completed_stages_before: tuple[ReviewStage, ...]
    completed_stages_after: tuple[ReviewStage, ...]
    transition_reason: str

    def to_json(self) -> dict[str, Any]:
        return {
            "active_stage_before": _stage_value(self.active_stage_before),
            "active_stage_after": _stage_value(self.active_stage_after),
            "suspended_stage_before": _stage_value(self.suspended_stage_before),
            "suspended_stage_after": _stage_value(self.suspended_stage_after),
            "stage_queue_before": [_stage_value(stage) for stage in self.stage_queue_before],
            "stage_queue_after": [_stage_value(stage) for stage in self.stage_queue_after],
            "completed_stages_before": [_stage_value(stage) for stage in self.completed_stages_before],
            "completed_stages_after": [_stage_value(stage) for stage in self.completed_stages_after],
            "transition_reason": self.transition_reason,
        }


def initial_stage_queue() -> list[ReviewStage]:
    return list(NORMAL_REVIEW_STAGES)


def initial_stage_cursor() -> StageCursor:
    return StageCursor(
        active_stage=None,
        suspended_stage=None,
        stage_queue=initial_stage_queue(),
        completed_stages=[],
    )


def validate_stage_cursor(cursor: StageCursorFields) -> None:
    active = cursor.active_stage
    suspended = cursor.suspended_stage
    queue = tuple(cursor.stage_queue)
    completed = tuple(cursor.completed_stages)

    _validate_stage_tuple(queue, "stage_queue")
    _validate_stage_tuple(completed, "completed_stages")
    if active is not None and not isinstance(active, ReviewStage):
        raise StageCursorError("active_stage must be a ReviewStage or None")
    if suspended is not None and not isinstance(suspended, ReviewStage):
        raise StageCursorError("suspended_stage must be a ReviewStage or None")
    if ReviewStage.CLARIFICATION_REVIEW in queue:
        raise StageCursorError("clarification_review must not be in stage_queue")
    if any(stage not in NORMAL_REVIEW_STAGES for stage in queue):
        raise StageCursorError("stage_queue may contain only normal review stages")
    if any(stage not in NORMAL_REVIEW_STAGES for stage in completed):
        raise StageCursorError("completed_stages may contain only normal review stages")
    if active in queue:
        raise StageCursorError("stage_queue must contain only future stages")
    if active in completed:
        raise StageCursorError("active_stage must not already be completed")
    overlap = set(queue).intersection(completed)
    if overlap:
        raise StageCursorError("stage_queue must not contain completed stages")
    _validate_no_duplicates(queue, "stage_queue")
    _validate_no_duplicates(completed, "completed_stages")
    _validate_normal_stage_order(active=active, queue=queue, completed=completed)


def advance_or_finish_stage(cursor: StageCursorFields) -> StageCursorTransition:
    validate_stage_cursor(cursor)
    before_active = cursor.active_stage
    before_suspended = cursor.suspended_stage
    before_queue = tuple(cursor.stage_queue)
    before_completed = tuple(cursor.completed_stages)

    if before_active is None:
        if not cursor.stage_queue:
            reason = "finish_review_stages"
            after_active = None
        else:
            after_active = cursor.stage_queue.pop(0)
            reason = f"start_{after_active.value}"
            cursor.active_stage = after_active
    elif before_active == ReviewStage.CLARIFICATION_REVIEW:
        raise StageCursorError("clarification_review resume is not implemented in this slice")
    else:
        cursor.completed_stages.append(before_active)
        if cursor.stage_queue:
            after_active = cursor.stage_queue.pop(0)
            cursor.active_stage = after_active
            reason = f"complete_{before_active.value}_start_{after_active.value}"
        else:
            cursor.active_stage = None
            after_active = None
            reason = "finish_review_stages"

    validate_stage_cursor(cursor)
    return StageCursorTransition(
        active_stage_before=before_active,
        active_stage_after=cursor.active_stage,
        suspended_stage_before=before_suspended,
        suspended_stage_after=cursor.suspended_stage,
        stage_queue_before=before_queue,
        stage_queue_after=tuple(cursor.stage_queue),
        completed_stages_before=before_completed,
        completed_stages_after=tuple(cursor.completed_stages),
        transition_reason=reason,
    )


def _stage_value(stage: ReviewStage | None) -> str | None:
    return stage.value if stage is not None else None


def _validate_stage_tuple(stages: tuple[ReviewStage, ...], label: str) -> None:
    if any(not isinstance(stage, ReviewStage) for stage in stages):
        raise StageCursorError(f"{label} must contain ReviewStage values")


def _validate_no_duplicates(stages: tuple[ReviewStage, ...], label: str) -> None:
    if len(set(stages)) != len(stages):
        raise StageCursorError(f"{label} must not contain duplicate stages")


def _validate_normal_stage_order(
    *,
    active: ReviewStage | None,
    queue: tuple[ReviewStage, ...],
    completed: tuple[ReviewStage, ...],
) -> None:
    completed_count = len(completed)
    if completed != NORMAL_REVIEW_STAGES[:completed_count]:
        raise StageCursorError("completed_stages must be an ordered normal-stage prefix")
    if active == ReviewStage.CLARIFICATION_REVIEW:
        expected_queue = NORMAL_REVIEW_STAGES[completed_count:]
        if queue != expected_queue:
            raise StageCursorError("stage_queue must preserve normal-stage order during clarification_review")
        return
    if active is None:
        if completed_count == 0:
            expected_queue = NORMAL_REVIEW_STAGES
        elif completed_count == len(NORMAL_REVIEW_STAGES):
            expected_queue = ()
        else:
            raise StageCursorError("active_stage cannot be None between normal stages")
        if queue != expected_queue:
            raise StageCursorError("stage_queue must preserve normal-stage order")
        return
    if completed_count >= len(NORMAL_REVIEW_STAGES):
        raise StageCursorError("active_stage cannot follow completed normal stages")
    expected_active = NORMAL_REVIEW_STAGES[completed_count]
    expected_queue = NORMAL_REVIEW_STAGES[completed_count + 1 :]
    if active != expected_active or queue != expected_queue:
        raise StageCursorError("stage cursor must preserve normal-stage order")
