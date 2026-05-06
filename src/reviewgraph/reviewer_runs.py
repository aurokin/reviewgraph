from __future__ import annotations

from dataclasses import dataclass

from reviewgraph.context_budget import reviewer_key
from reviewgraph.models import (
    ReviewerRunKey,
    ReviewerRunStatus,
    ReviewerRunStatusValue,
    ReviewStage,
    ReviewState,
    SelectedReviewer,
)


TERMINAL_SUPPRESSING_STATUSES = frozenset(
    {
        ReviewerRunStatusValue.COMPLETED,
        ReviewerRunStatusValue.SKIPPED,
    }
)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int or self.max_attempts <= 0:
            raise ValueError("max_attempts must be a positive integer")


@dataclass(frozen=True)
class RetryDecision:
    run_key: ReviewerRunKey | None
    exhausted: bool
    reason: str


def make_reviewer_run_key(
    review_state: ReviewState,
    reviewer: SelectedReviewer,
    *,
    attempt: int = 1,
    retry_of: str | None = None,
    clarification_id: str | None = None,
) -> ReviewerRunKey:
    return ReviewerRunKey(
        target_hash=review_state.review_target.target_hash(),
        config_hash=review_state.config_hash,
        stage=ReviewStage(reviewer.stage),
        reviewer=reviewer.name,
        attempt=attempt,
        retry_of=retry_of,
        clarification_id=clarification_id,
    )


def register_selected_reviewer(
    review_state: ReviewState,
    reviewer: SelectedReviewer,
    *,
    clarification_id: str | None = None,
) -> ReviewerRunKey | None:
    run_key = make_reviewer_run_key(
        review_state,
        reviewer,
        clarification_id=clarification_id,
    )
    if has_suppressing_status_for_reviewer(review_state, run_key):
        return None
    stable_key = run_key.stable_key()
    existing_status = review_state.reviewer_run_status.get(stable_key)
    if existing_status is not None:
        return run_key
    review_state.reviewer_run_keys.append(run_key)
    review_state.reviewer_run_status[stable_key] = ReviewerRunStatus(
        status=ReviewerRunStatusValue.SELECTED,
        run_key=run_key,
        reason="selected by active-stage routing",
    )
    review_state.selected_reviewers.append(reviewer)
    return run_key


def record_reviewer_run_status(
    review_state: ReviewState,
    run_key: ReviewerRunKey,
    *,
    status: ReviewerRunStatusValue,
    reason: str,
) -> ReviewerRunStatus:
    run_status = ReviewerRunStatus(
        status=status,
        run_key=run_key,
        reason=reason,
    )
    review_state.reviewer_run_status[run_key.stable_key()] = run_status
    if run_key not in review_state.reviewer_run_keys:
        review_state.reviewer_run_keys.append(run_key)
    return run_status


def suppresses_rerun(status: ReviewerRunStatus) -> bool:
    return status.status in TERMINAL_SUPPRESSING_STATUSES or is_retry_exhausted_failure(status)


def is_retry_exhausted_failure(status: ReviewerRunStatus) -> bool:
    return (
        status.status == ReviewerRunStatusValue.FAILED
        and status.reason is not None
        and status.reason.startswith("retry exhausted:")
    )


def has_suppressing_status_for_reviewer(review_state: ReviewState, run_key: ReviewerRunKey) -> bool:
    return any(
        _same_reviewer_identity(status.run_key, run_key) and suppresses_rerun(status)
        for status in review_state.reviewer_run_status.values()
    )


def retry_after_failure(
    review_state: ReviewState,
    run_key: ReviewerRunKey,
    *,
    policy: RetryPolicy = RetryPolicy(),
    reason: str,
) -> RetryDecision:
    if run_key.attempt >= policy.max_attempts:
        record_reviewer_run_status(
            review_state,
            run_key,
            status=ReviewerRunStatusValue.FAILED,
            reason=f"retry exhausted: {reason}",
        )
        return RetryDecision(
            run_key=None,
            exhausted=True,
            reason=f"retry exhausted after attempt {run_key.attempt}",
        )
    next_key = ReviewerRunKey(
        target_hash=run_key.target_hash,
        config_hash=run_key.config_hash,
        stage=run_key.stage,
        reviewer=run_key.reviewer,
        attempt=run_key.attempt + 1,
        retry_of=run_key.stable_key(),
        clarification_id=run_key.clarification_id,
    )
    record_reviewer_run_status(
        review_state,
        next_key,
        status=ReviewerRunStatusValue.SELECTED,
        reason=f"retry selected after failure: {reason}",
    )
    return RetryDecision(
        run_key=next_key,
        exhausted=False,
        reason=f"retry attempt {next_key.attempt} selected",
    )


def reviewer_run_key_for_selection(review_state: ReviewState, reviewer: SelectedReviewer) -> ReviewerRunKey:
    candidates: list[ReviewerRunKey] = []
    for run_key in review_state.reviewer_run_keys:
        if run_key.reviewer != reviewer.name or run_key.stage.value != reviewer.stage:
            continue
        if run_key.stage == ReviewStage.CLARIFICATION_REVIEW:
            if run_key.clarification_id != review_state.active_clarification_id:
                continue
        candidates.append(run_key)
    if candidates:
        active_candidates = [
            run_key
            for run_key in candidates
            if (
                status := review_state.reviewer_run_status.get(run_key.stable_key())
            ) is None
            or status.status in {ReviewerRunStatusValue.SELECTED, ReviewerRunStatusValue.RUNNING}
        ]
        return max(active_candidates or candidates, key=lambda run_key: run_key.attempt)
    raise ValueError(f"reviewer run key missing for {reviewer_key(reviewer)}")


def _same_reviewer_identity(left: ReviewerRunKey, right: ReviewerRunKey) -> bool:
    if left.clarification_id is not None or right.clarification_id is not None:
        return (
            left.target_hash == right.target_hash
            and left.config_hash == right.config_hash
            and left.stage == right.stage
            and left.reviewer == right.reviewer
            and left.clarification_id == right.clarification_id
        )
    return (
        left.target_hash == right.target_hash
        and left.config_hash == right.config_hash
        and left.stage == right.stage
        and left.reviewer == right.reviewer
    )
