# ISSUE PLAN: AUR-234 Add Minimal Context Budget Before Fanout

Active issue plan for `AUR-234` / `RG-045: Add Minimal Context Budget Before Fanout`.

## Linear Snapshot

- Issue: `AUR-234`
- Status at start: `In Progress`
- Milestone: `PRD 0003: Contracts`
- Direct blocker context: this stale blocker must be closed before `AUR-254` can complete.
- Comments at start: none.
- Harness from Linear: `python -m pytest tests/test_context_budget_contract.py`

## Goal

Verify and, if needed, complete the minimal context-budget contract that runs before reviewer selection and fanout.

This appears already superseded by the stricter AUR-211 implementation in `tests/test_context_budget.py`. Treat this as verification-only unless the existing context-budget harness misses an AUR-234 acceptance criterion.

## Acceptance Mapping

- Budget caps changed files, patch bytes, memory bytes, reviewer count, and live-call count:
  - Covered by `tests/test_context_budget.py::test_budget_caps_changed_files_patch_and_memory` and `test_reviewer_count_and_live_call_budgets_defer_reviewers`.
- Budget decisions are recorded before reviewer selection:
  - Covered by runner integration using budgeted fixture view before `_select_reviewers_for_stage`, plus `test_runner_routes_against_budgeted_changed_files`.
- Truncation markers are available to reviewer context packages:
  - Covered by `test_reviewer_context_package_contains_budget_truncation_and_markers`.
- Skipped or deferred reviewers can be represented as structured budget decisions:
  - Covered by `test_reviewer_count_and_live_call_budgets_defer_reviewers` and `test_runner_defers_reviewers_before_executing_raw_outputs`.
- No live calls are made when the live-call cap is zero:
  - Covered by the deterministic live-call ledger in `apply_reviewer_budget`, default `max_live_calls=0`, and full dry-run/no-writer regression tests. No live provider adapter exists in this milestone.

## Implementation Plan

1. Run the focused context-budget harness:
   - `python -m pytest tests/test_context_budget.py`
2. Run targeted runner/no-side-effect regression:
   - `python -m pytest tests/test_context_budget.py tests/test_tracer_fixture_run.py tests/test_cli.py tests/test_render.py`
3. Run static checks:
   - `python -m py_compile src/reviewgraph/*.py`
   - `python scripts/check_docs.py`
   - `git diff --check`
4. Use a fresh subagent review to verify the acceptance mapping is complete and this is safe to close as a verification-only stale blocker.
5. If no material findings remain, commit this issue plan, comment evidence on Linear, and mark `AUR-234` Done.

## Out Of Scope

- No rendered-note refinements beyond what AUR-211 already implemented.
- No downstream posting enforcement beyond the already-tested omitted-context suppression.
- No live GitHub reads, live LLM calls, approval UI, or writer behavior.
