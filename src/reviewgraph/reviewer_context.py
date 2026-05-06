from __future__ import annotations

from dataclasses import dataclass

from reviewgraph.context_budget import BudgetedInputContext
from reviewgraph.models import (
    ContextBudget,
    LocalNote,
    MemoryReference,
    OmittedContextMarker,
    PullRequestChangedFile,
    ReviewTarget,
    SelectedReviewer,
    TruncationNotice,
)


@dataclass(frozen=True)
class ReviewerContextPackage:
    review_target: ReviewTarget
    active_stage: str
    reviewer: SelectedReviewer
    changed_files: tuple[PullRequestChangedFile, ...]
    memory_references: tuple[MemoryReference, ...]
    truncation_notices: tuple[TruncationNotice, ...]
    omitted_context: tuple[OmittedContextMarker, ...]
    local_notes: tuple[LocalNote, ...]
    context_budget: ContextBudget


def build_reviewer_context_package(
    *,
    active_stage: str,
    reviewer: SelectedReviewer,
    budgeted_context: BudgetedInputContext,
) -> ReviewerContextPackage:
    return ReviewerContextPackage(
        review_target=budgeted_context.pr.review_target,
        active_stage=active_stage,
        reviewer=reviewer,
        changed_files=budgeted_context.pr.changed_files,
        memory_references=budgeted_context.memory.entries,
        truncation_notices=budgeted_context.context_budget.truncation,
        omitted_context=budgeted_context.context_budget.omitted_context,
        local_notes=budgeted_context.local_notes,
        context_budget=budgeted_context.context_budget,
    )
