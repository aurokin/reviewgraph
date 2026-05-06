from __future__ import annotations

import re
from fnmatch import fnmatch
from typing import Protocol

from reviewgraph.models import (
    MemoryReference,
    ReviewConfig,
    ReviewerRunKey,
    ReviewerRunStatus,
    ReviewerRunStatusValue,
    ReviewerTriggers,
    ReviewStage,
    ReviewState,
    SelectedReviewer,
)


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
    )
    runnable_selection: list[SelectedReviewer] = []
    for reviewer in selected:
        run_key = ReviewerRunKey(
            target_hash=review_state.review_target.target_hash(),
            config_hash=review_state.config_hash,
            stage=review_state.active_stage,
            reviewer=reviewer.name,
        )
        stable_key = run_key.stable_key()
        existing_status = review_state.reviewer_run_status.get(stable_key)
        if existing_status is not None:
            if existing_status.status in {
                ReviewerRunStatusValue.COMPLETED,
                ReviewerRunStatusValue.SKIPPED,
            }:
                continue
        else:
            review_state.reviewer_run_keys.append(run_key)
            review_state.reviewer_run_status[stable_key] = ReviewerRunStatus(
                status=ReviewerRunStatusValue.SELECTED,
                run_key=run_key,
                reason="selected by active-stage routing",
            )
            review_state.selected_reviewers.append(reviewer)
        runnable_selection.append(reviewer)
    return tuple(runnable_selection)


def _trigger_reasons(
    *,
    stage: str,
    triggers: ReviewerTriggers,
    pr: PRLike,
    memory_references: tuple[MemoryReference, ...],
) -> list[str]:
    reasons: list[str] = []
    gate_failures: list[str] = []
    changed_file_count = len(pr.changed_files)
    changed_line_count = _changed_line_count(pr)
    risk_level = _pr_risk_level(pr)

    if triggers.max_files is not None:
        if changed_file_count > triggers.max_files:
            gate_failures.append(f"{stage} triggers.max_files>{triggers.max_files}")
        else:
            reasons.append(f"{stage} triggers.max_files<={triggers.max_files}")
    if triggers.changed_files_min is not None:
        if changed_file_count < triggers.changed_files_min:
            gate_failures.append(f"{stage} triggers.changed_files_min<{triggers.changed_files_min}")
        else:
            reasons.append(f"{stage} triggers.changed_files_min={triggers.changed_files_min}")
    if triggers.changed_lines_min is not None:
        if changed_line_count < triggers.changed_lines_min:
            gate_failures.append(f"{stage} triggers.changed_lines_min<{triggers.changed_lines_min}")
        else:
            reasons.append(f"{stage} triggers.changed_lines_min={triggers.changed_lines_min}")
    if triggers.risk_min is not None:
        if _risk_rank(risk_level) < _risk_rank(triggers.risk_min.value):
            gate_failures.append(f"{stage} triggers.risk_min<{triggers.risk_min.value}")
        else:
            reasons.append(f"{stage} triggers.risk_min={triggers.risk_min.value}")
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


def _pr_risk_level(pr: PRLike) -> str:
    changed_files = len(pr.changed_files)
    changed_lines = _changed_line_count(pr)
    patches = "\n".join(changed_file.patch or "" for changed_file in pr.changed_files).casefold()
    if changed_files >= 10 or changed_lines >= 500 or any(term in patches for term in ("auth", "token", "password")):
        return "high"
    if changed_files >= 3 or changed_lines >= 50 or any(term in patches for term in ("billing", "product intent")):
        return "medium"
    return "low"


def _risk_rank(risk_level: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}[risk_level]
