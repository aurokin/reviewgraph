from __future__ import annotations

import re
from fnmatch import fnmatch
from typing import Protocol

from reviewgraph.models import (
    MemoryReference,
    ReviewConfig,
    RiskAssessment,
    RiskLevel,
    ReviewerTriggers,
    ReviewStage,
    ReviewState,
    SelectedReviewer,
)
from reviewgraph.reviewer_runs import register_selected_reviewer


class ChangedFileLike(Protocol):
    path: str
    patch: str | None
    additions: int
    deletions: int


class PRLike(Protocol):
    labels: tuple[str, ...]
    changed_files: tuple[ChangedFileLike, ...]


def select_reviewers_for_stage(
    config: ReviewConfig,
    pr: PRLike,
    stage: str | ReviewStage,
    *,
    memory_references: tuple[MemoryReference, ...] = (),
    risk: RiskAssessment | None = None,
) -> tuple[SelectedReviewer, ...]:
    stage_value = _stage_value(stage)
    selected: list[SelectedReviewer] = []
    for name in sorted(config.agents):
        agent = config.agents[name]
        stages = tuple(agent_stage.value for agent_stage in agent.stages)
        if stage_value in stages:
            reasons = _trigger_reasons(
                stage=stage_value,
                triggers=agent.triggers,
                pr=pr,
                memory_references=memory_references,
                risk=risk,
            )
            if not reasons:
                continue
            selected.append(
                SelectedReviewer(
                    name=name,
                    stage=stage_value,
                    reasons=tuple(reasons),
                )
            )
    return tuple(selected)


def select_reviewers_for_active_stage(
    review_state: ReviewState,
    *,
    memory_references: tuple[MemoryReference, ...] | None = None,
) -> tuple[SelectedReviewer, ...]:
    if review_state.active_stage is None:
        return ()
    if review_state.active_stage == ReviewStage.CLARIFICATION_REVIEW:
        return _select_clarification_resume_reviewers(review_state)
    if review_state.pr is None:
        raise ValueError("review state pr is required for reviewer selection")
    if memory_references is None:
        memory_references = (
            review_state.conversation_memory.entries
            if review_state.conversation_memory is not None
            else ()
        )
    selected = select_reviewers_for_stage(
        review_state.config,
        review_state.pr,
        review_state.active_stage,
        memory_references=memory_references,
        risk=review_state.risk,
    )
    runnable_selection: list[SelectedReviewer] = []
    for reviewer in selected:
        run_key = register_selected_reviewer(review_state, reviewer)
        if run_key is None:
            continue
        runnable_selection.append(reviewer)
    return tuple(runnable_selection)


def _select_clarification_resume_reviewers(review_state: ReviewState) -> tuple[SelectedReviewer, ...]:
    clarification_id = review_state.active_clarification_id
    if clarification_id is None:
        raise ValueError("active_clarification_id is required during clarification_review")
    request = next(
        (
            request
            for request in review_state.clarification_requests
            if request.id == clarification_id
        ),
        None,
    )
    if request is None:
        raise ValueError(f"clarification request {clarification_id} was not found")
    if not request.resume_target_reviewers:
        raise ValueError(f"clarification request {clarification_id} has no resume target reviewers")
    missing_reviewers = [
        reviewer_name
        for reviewer_name in request.resume_target_reviewers
        if reviewer_name not in review_state.config.agents
    ]
    if missing_reviewers:
        missing = ", ".join(sorted(missing_reviewers))
        raise ValueError(f"clarification request {clarification_id} resume reviewers unavailable: {missing}")
    selected: list[SelectedReviewer] = []
    for reviewer_name in request.resume_target_reviewers:
        reviewer = SelectedReviewer(
            name=reviewer_name,
            stage=ReviewStage.CLARIFICATION_REVIEW.value,
            reasons=(f"clarification_review resume.clarification_id={clarification_id}",),
        )
        run_key = register_selected_reviewer(
            review_state,
            reviewer,
            clarification_id=clarification_id,
        )
        if run_key is None:
            continue
        selected.append(reviewer)
    return tuple(selected)


def _trigger_reasons(
    *,
    stage: str,
    triggers: ReviewerTriggers,
    pr: PRLike,
    memory_references: tuple[MemoryReference, ...],
    risk: RiskAssessment | None,
) -> list[str]:
    reasons: list[str] = []
    gate_failures: list[str] = []
    changed_file_count = risk.changed_file_count if risk is not None else _changed_file_count(pr)
    changed_line_count = risk.changed_line_count if risk is not None else _changed_line_count(pr)

    if triggers.max_files is not None:
        if changed_file_count > triggers.max_files:
            gate_failures.append(f"{stage} triggers.max_files>{triggers.max_files}")
        else:
            reasons.append(f"{stage} triggers.max_files<={triggers.max_files}")
    if triggers.changed_files_min is not None:
        if changed_file_count < triggers.changed_files_min:
            gate_failures.append(f"{stage} triggers.changed_files_min<{triggers.changed_files_min}")
        else:
            reasons.append(f"{stage} triggers.changed_files_min>={triggers.changed_files_min}")
    if triggers.changed_lines_min is not None:
        if changed_line_count < triggers.changed_lines_min:
            gate_failures.append(f"{stage} triggers.changed_lines_min<{triggers.changed_lines_min}")
        else:
            reasons.append(f"{stage} triggers.changed_lines_min>={triggers.changed_lines_min}")
    if triggers.risk_min is not None:
        risk_level = risk.risk_level if risk is not None else RiskLevel.LOW
        if _risk_rank(risk_level) < _risk_rank(triggers.risk_min):
            gate_failures.append(f"{stage} triggers.risk_min<{triggers.risk_min.value}")
        else:
            reasons.append(f"{stage} triggers.risk_min>={triggers.risk_min.value}")
    if gate_failures:
        return []

    selector_reasons: list[str] = []
    if triggers.always is True:
        selector_reasons.append(f"{stage} triggers.always=true")
    for pattern in triggers.paths:
        if any(_path_matches(changed_file.path, pattern) for changed_file in pr.changed_files):
            selector_reasons.append(f"{stage} triggers.paths={pattern}")
    patches = "\n".join(changed_file.patch or "" for changed_file in pr.changed_files).casefold()
    for pattern in triggers.diff_patterns:
        if _diff_pattern_matches(patches, pattern):
            selector_reasons.append(f"{stage} triggers.diff_patterns={pattern}")
    labels = {label.casefold() for label in pr.labels}
    for label in triggers.labels:
        if label.casefold() in labels:
            selector_reasons.append(f"{stage} triggers.labels={label}")
    trusted_memory = "\n".join(memory.body or "" for memory in memory_references if memory.actionable).casefold()
    for pattern in triggers.conversation_patterns:
        if pattern.casefold() in trusted_memory:
            selector_reasons.append(f"{stage} triggers.conversation_patterns={pattern}")

    has_explicit_selector = any(
        (
            triggers.always,
            triggers.paths,
            triggers.labels,
            triggers.diff_patterns,
            triggers.conversation_patterns,
        )
    )
    if not has_explicit_selector and reasons:
        return reasons
    return selector_reasons + reasons if selector_reasons else []


def _stage_value(stage: str | ReviewStage) -> str:
    return stage.value if isinstance(stage, ReviewStage) else stage


def _path_matches(path: str, pattern: str) -> bool:
    return path == pattern or fnmatch(path, pattern) or path.startswith(pattern.rstrip("/") + "/")


def _diff_pattern_matches(casefolded_patch: str, pattern: str) -> bool:
    try:
        return re.search(pattern, casefolded_patch, flags=re.IGNORECASE) is not None
    except re.error:
        return pattern.casefold() in casefolded_patch


def _changed_line_count(pr: PRLike) -> int:
    total = 0
    for changed_file in pr.changed_files:
        changed_ranges = getattr(changed_file, "changed_ranges", None)
        if changed_ranges is not None:
            total += sum(changed_range.end - changed_range.start + 1 for changed_range in changed_ranges)
        else:
            total += changed_file.additions + changed_file.deletions
    return total


def _changed_file_count(pr: PRLike) -> int:
    return len(pr.changed_files)


def _risk_rank(risk_level: RiskLevel) -> int:
    return {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}[risk_level]
