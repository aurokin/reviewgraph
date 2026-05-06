from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from typing import Mapping

from reviewgraph.models import (
    ContextBudget,
    LocalNote,
    MemoryReference,
    OmittedContextMarker,
    PRConversationMemory,
    PullRequestChangedFile,
    PullRequestContext,
    SelectedReviewer,
    TruncationNotice,
)


DEFAULT_CONTEXT_BUDGET_LIMITS = {
    "max_changed_files": 50,
    "max_patch_bytes": 200_000,
    "max_memory_bytes": 100_000,
    "max_reviewers": 20,
    "max_live_calls": 0,
}


@dataclass(frozen=True)
class BudgetedInputContext:
    context_budget: ContextBudget
    pr: PullRequestContext
    memory: PRConversationMemory
    local_notes: tuple[LocalNote, ...]


@dataclass(frozen=True)
class BudgetedReviewers:
    context_budget: ContextBudget
    retained_reviewers: tuple[SelectedReviewer, ...]
    deferred_reviewers: tuple[SelectedReviewer, ...]
    local_notes: tuple[LocalNote, ...]

    @property
    def deferred_keys(self) -> tuple[tuple[str, str], ...]:
        return tuple((reviewer.name, reviewer.stage) for reviewer in self.deferred_reviewers)


def default_context_budget() -> ContextBudget:
    return ContextBudget(**DEFAULT_CONTEXT_BUDGET_LIMITS)


def apply_input_context_budget(
    *,
    pr: PullRequestContext,
    memory: PRConversationMemory,
    limits: ContextBudget,
    existing_truncation: tuple[TruncationNotice, ...] = (),
) -> BudgetedInputContext:
    retained_files: list[PullRequestChangedFile] = []
    retained_memory: list[MemoryReference] = []
    omitted_file_paths: list[str] = []
    omitted_memory_ids: list[str] = []
    markers: list[OmittedContextMarker] = []
    truncation: list[TruncationNotice] = list(existing_truncation)
    local_notes: list[LocalNote] = []
    reasons: list[str] = []

    original_patch_bytes = sum(_patch_bytes(changed_file) for changed_file in pr.changed_files)
    retained_patch_bytes = 0
    patch_budget_remaining = limits.max_patch_bytes

    for changed_file in pr.changed_files:
        if len(retained_files) >= limits.max_changed_files:
            omitted_file_paths.append(changed_file.path)
            reasons.append("changed_file_count_exceeded")
            marker = _marker(
                "changed-files",
                reason_code="changed_file_count_exceeded",
                dimension="changed_files",
                affected_id=changed_file.path,
                original_count=len(pr.changed_files),
                retained_count=len(retained_files),
            )
            markers.append(marker)
            local_notes.append(_omitted_note(marker, f"Changed file omitted: {changed_file.path}"))
            continue

        if changed_file.patch is None and changed_file.patch_status != "available":
            retained_files.append(changed_file)
            omitted_file_paths.append(changed_file.path)
            reasons.append("fixture_patch_truncated")
            markers.append(
                _marker(
                    "patch",
                    reason_code="fixture_patch_truncated",
                    dimension="patch_bytes",
                    affected_id=changed_file.path,
                    original_bytes=None,
                    retained_bytes=0,
                )
            )
            continue

        patch_bytes = _patch_bytes(changed_file)
        if patch_bytes > patch_budget_remaining:
            retained_files.append(replace(changed_file, patch=None, patch_status="budget_truncated"))
            omitted_file_paths.append(changed_file.path)
            reasons.append("patch_byte_budget_exceeded")
            marker = _marker(
                "patch",
                reason_code="patch_byte_budget_exceeded",
                dimension="patch_bytes",
                affected_id=changed_file.path,
                original_bytes=patch_bytes,
                retained_bytes=0,
            )
            markers.append(marker)
            truncation.append(
                TruncationNotice(
                    resource=f"patch:{changed_file.path}",
                    truncated=True,
                    note="Patch omitted by context budget.",
                    original_bytes=patch_bytes,
                    retained_bytes=0,
                )
            )
            local_notes.append(_omitted_note(marker, f"Patch omitted: {changed_file.path}"))
            continue

        retained_files.append(changed_file)
        retained_patch_bytes += patch_bytes
        patch_budget_remaining -= patch_bytes

    original_memory_bytes = sum(_memory_bytes(memory_reference) for memory_reference in memory.entries)
    retained_memory_bytes = 0
    memory_budget_remaining = limits.max_memory_bytes

    for memory_reference in memory.entries:
        memory_bytes = _memory_bytes(memory_reference)
        if memory_bytes > memory_budget_remaining:
            retained_memory.append(replace(memory_reference, body=None))
            omitted_memory_ids.append(memory_reference.id)
            reasons.append("memory_byte_budget_exceeded")
            marker = _marker(
                "memory",
                reason_code="memory_byte_budget_exceeded",
                dimension="memory_bytes",
                affected_id=memory_reference.id,
                original_bytes=memory_bytes,
                retained_bytes=0,
            )
            markers.append(marker)
            truncation.append(
                TruncationNotice(
                    resource=f"memory:{memory_reference.id}",
                    truncated=True,
                    note="Conversation memory body omitted by context budget.",
                    original_bytes=memory_bytes,
                    retained_bytes=0,
                )
            )
            local_notes.append(_omitted_note(marker, f"Conversation memory omitted: {memory_reference.id}"))
            continue

        retained_memory.append(memory_reference)
        retained_memory_bytes += memory_bytes
        memory_budget_remaining -= memory_bytes

    budget = ContextBudget(
        max_changed_files=limits.max_changed_files,
        max_patch_bytes=limits.max_patch_bytes,
        max_memory_bytes=limits.max_memory_bytes,
        max_reviewers=limits.max_reviewers,
        max_live_calls=limits.max_live_calls,
        truncation=tuple(_dedupe_truncation(truncation)),
        omitted_context=tuple(_dedupe_markers(markers)),
        original_changed_file_count=len(pr.changed_files),
        retained_changed_file_count=len(retained_files),
        original_patch_bytes=original_patch_bytes,
        retained_patch_bytes=retained_patch_bytes,
        original_memory_count=len(memory.entries),
        retained_memory_count=len(retained_memory),
        original_memory_bytes=original_memory_bytes,
        retained_memory_bytes=retained_memory_bytes,
        retained_file_paths=tuple(changed_file.path for changed_file in retained_files),
        omitted_file_paths=tuple(_unique(omitted_file_paths)),
        retained_memory_ids=tuple(memory_reference.id for memory_reference in retained_memory),
        omitted_memory_ids=tuple(_unique(omitted_memory_ids)),
        generated_local_note_ids=tuple(note.id for note in local_notes),
        reasons=tuple(_unique(reasons)),
    )
    return BudgetedInputContext(
        context_budget=budget,
        pr=replace(pr, changed_files=tuple(retained_files)),
        memory=PRConversationMemory(entries=tuple(retained_memory)),
        local_notes=tuple(local_notes),
    )


def apply_reviewer_budget(
    *,
    reviewers: tuple[SelectedReviewer, ...],
    limits: ContextBudget,
    live_call_costs: Mapping[str, int] | None = None,
    retained_reviewer_count: int = 0,
    planned_live_calls: int = 0,
) -> BudgetedReviewers:
    live_call_costs = live_call_costs or {}
    retained: list[SelectedReviewer] = []
    deferred: list[SelectedReviewer] = []
    retained_live_call_ids: list[str] = []
    deferred_live_call_ids: list[str] = []
    local_notes: list[LocalNote] = []
    markers: list[OmittedContextMarker] = []
    reasons: list[str] = []

    for reviewer in reviewers:
        reviewer_id = reviewer_key(reviewer)
        live_cost = _live_call_cost(live_call_costs, reviewer, reviewer_id)
        if retained_reviewer_count + len(retained) >= limits.max_reviewers:
            deferred.append(reviewer)
            reasons.append("reviewer_count_budget_exceeded")
            marker = _marker(
                "reviewer",
                reason_code="reviewer_count_budget_exceeded",
                dimension="reviewers",
                affected_id=reviewer_id,
                original_count=retained_reviewer_count + len(reviewers),
                retained_count=retained_reviewer_count + len(retained),
            )
            markers.append(marker)
            local_notes.append(_deferred_reviewer_note(reviewer, marker))
            continue
        if planned_live_calls + live_cost > limits.max_live_calls:
            deferred.append(reviewer)
            deferred_live_call_ids.append(reviewer_id)
            reasons.append("live_call_budget_exceeded")
            marker = _marker(
                "reviewer-live-call",
                reason_code="live_call_budget_exceeded",
                dimension="live_calls",
                affected_id=reviewer_id,
                original_count=planned_live_calls + live_cost,
                retained_count=planned_live_calls,
            )
            markers.append(marker)
            local_notes.append(_deferred_reviewer_note(reviewer, marker))
            continue
        retained.append(reviewer)
        planned_live_calls += live_cost
        if live_cost:
            retained_live_call_ids.append(reviewer_id)

    budget = ContextBudget(
        max_changed_files=limits.max_changed_files,
        max_patch_bytes=limits.max_patch_bytes,
        max_memory_bytes=limits.max_memory_bytes,
        max_reviewers=limits.max_reviewers,
        max_live_calls=limits.max_live_calls,
        omitted_context=tuple(_dedupe_markers(markers)),
        original_reviewer_count=len(reviewers),
        retained_reviewer_count=len(retained),
        planned_live_calls=sum(
            _live_call_cost(live_call_costs, reviewer, reviewer_key(reviewer)) for reviewer in retained
        ),
        retained_reviewer_ids=tuple(reviewer_key(reviewer) for reviewer in retained),
        deferred_reviewer_ids=tuple(reviewer_key(reviewer) for reviewer in deferred),
        retained_live_call_reviewer_ids=tuple(retained_live_call_ids),
        deferred_live_call_reviewer_ids=tuple(deferred_live_call_ids),
        generated_local_note_ids=tuple(note.id for note in local_notes),
        reasons=tuple(_unique(reasons)),
    )
    return BudgetedReviewers(
        context_budget=budget,
        retained_reviewers=tuple(retained),
        deferred_reviewers=tuple(deferred),
        local_notes=tuple(local_notes),
    )


def merge_context_budgets(base: ContextBudget, *budgets: ContextBudget) -> ContextBudget:
    original_reviewer_count = base.original_reviewer_count + sum(
        budget.original_reviewer_count for budget in budgets
    )
    retained_reviewer_count = base.retained_reviewer_count + sum(
        budget.retained_reviewer_count for budget in budgets
    )
    planned_live_calls = base.planned_live_calls + sum(budget.planned_live_calls for budget in budgets)
    return ContextBudget(
        max_changed_files=base.max_changed_files,
        max_patch_bytes=base.max_patch_bytes,
        max_memory_bytes=base.max_memory_bytes,
        max_reviewers=base.max_reviewers,
        max_live_calls=base.max_live_calls,
        truncation=tuple(
            _dedupe_truncation(
                base.truncation + tuple(notice for budget in budgets for notice in budget.truncation)
            )
        ),
        omitted_context=tuple(
            _dedupe_markers(base.omitted_context + tuple(marker for budget in budgets for marker in budget.omitted_context))
        ),
        original_changed_file_count=base.original_changed_file_count,
        retained_changed_file_count=base.retained_changed_file_count,
        original_patch_bytes=base.original_patch_bytes,
        retained_patch_bytes=base.retained_patch_bytes,
        original_memory_count=base.original_memory_count,
        retained_memory_count=base.retained_memory_count,
        original_memory_bytes=base.original_memory_bytes,
        retained_memory_bytes=base.retained_memory_bytes,
        original_reviewer_count=original_reviewer_count,
        retained_reviewer_count=retained_reviewer_count,
        planned_live_calls=planned_live_calls,
        retained_file_paths=base.retained_file_paths,
        omitted_file_paths=base.omitted_file_paths,
        retained_memory_ids=base.retained_memory_ids,
        omitted_memory_ids=base.omitted_memory_ids,
        retained_reviewer_ids=base.retained_reviewer_ids
        + tuple(reviewer_id for budget in budgets for reviewer_id in budget.retained_reviewer_ids),
        deferred_reviewer_ids=base.deferred_reviewer_ids
        + tuple(reviewer_id for budget in budgets for reviewer_id in budget.deferred_reviewer_ids),
        retained_live_call_reviewer_ids=tuple(
            base.retained_live_call_reviewer_ids
            + tuple(reviewer_id for budget in budgets for reviewer_id in budget.retained_live_call_reviewer_ids)
        ),
        deferred_live_call_reviewer_ids=tuple(
            base.deferred_live_call_reviewer_ids
            + tuple(reviewer_id for budget in budgets for reviewer_id in budget.deferred_live_call_reviewer_ids)
        ),
        generated_local_note_ids=tuple(
            _unique(
                base.generated_local_note_ids
                + tuple(note_id for budget in budgets for note_id in budget.generated_local_note_ids)
            )
        ),
        reasons=tuple(
            _unique(base.reasons + tuple(reason for budget in budgets for reason in budget.reasons))
        ),
    )


def reviewer_key(reviewer: SelectedReviewer) -> str:
    return f"{reviewer.stage}:{reviewer.name}"


def _patch_bytes(changed_file: PullRequestChangedFile) -> int:
    return len((changed_file.patch or "").encode("utf-8"))


def _memory_bytes(memory_reference: MemoryReference) -> int:
    parts = [
        memory_reference.id,
        memory_reference.trust_label,
        memory_reference.resolved_status,
        memory_reference.source_type,
        memory_reference.author or "",
        memory_reference.author_association or "",
        memory_reference.author_type or "",
        memory_reference.created_at or "",
        memory_reference.path or "",
        str(memory_reference.line or ""),
        memory_reference.body or "",
    ]
    return len("\n".join(parts).encode("utf-8"))


def _marker(
    namespace: str,
    *,
    reason_code: str,
    dimension: str,
    affected_id: str,
    original_count: int | None = None,
    retained_count: int | None = None,
    original_bytes: int | None = None,
    retained_bytes: int | None = None,
) -> OmittedContextMarker:
    return OmittedContextMarker(
        id=f"budget-{_slug(namespace)}-{_slug(affected_id)}-{_stable_suffix(affected_id)}",
        source="budget",
        reason_code=reason_code,
        dimension=dimension,
        affected_id=affected_id,
        original_count=original_count,
        retained_count=retained_count,
        original_bytes=original_bytes,
        retained_bytes=retained_bytes,
    )


def _omitted_note(marker: OmittedContextMarker, body: str) -> LocalNote:
    return LocalNote(
        id=f"note-{marker.id}",
        title="Context budget omitted input context",
        body=body,
        evidence=f"{marker.reason_code} on {marker.dimension}.",
    )


def _deferred_reviewer_note(reviewer: SelectedReviewer, marker: OmittedContextMarker) -> LocalNote:
    return LocalNote(
        id=f"note-{marker.id}",
        title="Reviewer deferred by context budget",
        body=f"{reviewer.name} was selected for {reviewer.stage} but skipped before execution.",
        evidence=f"{marker.reason_code}; trigger reasons: {', '.join(reviewer.reasons)}",
    )


def _live_call_cost(costs: Mapping[str, int], reviewer: SelectedReviewer, reviewer_id: str) -> int:
    value = costs.get(reviewer_id, costs.get(reviewer.name, 0))
    if type(value) is not int or value < 0:
        raise ValueError("reviewer live-call costs must be non-negative integers")
    return value


def _dedupe_markers(
    markers: list[OmittedContextMarker] | tuple[OmittedContextMarker, ...],
) -> list[OmittedContextMarker]:
    by_id: dict[str, OmittedContextMarker] = {}
    for marker in markers:
        by_id.setdefault(marker.id, marker)
    return list(by_id.values())


def _dedupe_truncation(notices: list[TruncationNotice] | tuple[TruncationNotice, ...]) -> list[TruncationNotice]:
    by_key: dict[tuple[str, str], TruncationNotice] = {}
    for notice in notices:
        by_key.setdefault((notice.resource, notice.note), notice)
    return list(by_key.values())


def _unique(values: tuple[str, ...] | list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "context"


def _stable_suffix(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
