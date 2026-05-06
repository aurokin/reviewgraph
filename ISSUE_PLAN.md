# ISSUE PLAN: AUR-211 Enforce Context Budget And Truncation Notes

Active issue plan for `AUR-211` / `RG-022: Enforce Context Budget And Truncation Notes`.

## Linear Snapshot

- Issue: `AUR-211`
- Status at start: `In Progress`
- Milestone: `PRD 0003: Contracts`
- Blocks: milestone gate `AUR-254`
- Blocked by: `AUR-237` (Done)
- Comments at start: none
- Harness from Linear: `python -m pytest tests/test_context_budget.py`

## Goal

Apply explicit context-budget contracts before reviewer fanout and make truncation/deferred-reviewer decisions deterministic, structured, and visible to later renderer/reviewer-context work.

This issue should not add live GitHub reads, live LLM calls, approval UI, writer behavior, or quality/posting enforcement beyond budget state. It may add minimal reviewer-context package contracts so the budget output has a durable consumer.

## Current Code

- `ContextBudget` and `TruncationNotice` exist in `src/reviewgraph/models.py`, but budget decisions are not calculated by a dedicated module.
- Fixture parsing preserves changed files, patches, labels, PR comments/reviews/review threads, and fixture-authored truncation notices.
- `src/reviewgraph/runner.py` currently renders fixture truncation notices but does not calculate changed-file, patch-byte, memory-byte, reviewer-count, or live-call budgets.
- There is no `src/reviewgraph/context_budget.py`, no `src/reviewgraph/reviewer_context.py`, and no `tests/test_context_budget.py`.
- `oversized-change` already represents a fixture with omitted patch text and should be part of the focused harness.

## Implementation Plan

1. Add explicit budget limits and decisions:
   - Extend `ReviewConfig` parsing with an optional top-level `context_budget` object.
   - Support deterministic limits for `max_changed_files`, `max_patch_bytes`, `max_memory_bytes`, `max_reviewers`, and `max_live_calls`, with conservative defaults for fixture runs.
   - Reject unknown or non-positive budget fields.
   - Extend the state-facing `ContextBudget` contract so it records decisions, not just limits: original/retained counts and bytes, retained file paths, retained memory IDs, retained reviewer IDs, deferred reviewer IDs, planned live-call count, retained/deferred live-call reviewer IDs, omitted-context marker IDs, generated local-note IDs, truncation notices, and reasons.
2. Add `src/reviewgraph/context_budget.py`:
   - Input: typed `PullRequestContext`, `PRConversationMemory`, selected reviewer candidates, and budget limits/config.
   - Output: a budget result containing the state-facing `ContextBudget` decision object, retained changed files, retained memory entries, retained/deferred reviewers, structured `TruncationNotice` entries, omitted-context markers, and structured `LocalNote` candidates for deferred reviewers or omitted context.
   - Count patch bytes as UTF-8 bytes of raw fixture patch text before redaction; this is conservative and platform-stable.
   - Count memory bytes as UTF-8 bytes of deterministic reviewer-package memory text, including body and required metadata.
   - If a single file or memory entry exceeds its cap, retain marker-only metadata, omit the body/patch text, and emit an omitted-context marker plus truncation notice.
   - Treat missing/truncated fixture patches as explicit truncation input, not as an error.
   - Keep ordering stable: retain existing fixture/reviewer order and defer overflow deterministically.
   - Model live-call budgeting as a deterministic ledger only: fake reviewers have planned live-call cost `0` by default; tests can pass synthetic live-call costs to prove `max_live_calls` overflow without making provider calls.
   - Deferred reviewers are selected-then-skipped: preserve their trigger reasons in the budget decision, assign policy-approved `skipped` reviewer status/run-key data where available, generate local-note candidates, and do not execute raw reviewer outputs.
   - Omitted-context markers must include stable ID, source (`fixture` or `budget`), reason code, budget dimension, affected path or memory/reviewer ID, original/retained counts or bytes, and merge/dedupe by stable ID.
3. Add `src/reviewgraph/reviewer_context.py`:
   - Define a minimal `ReviewerContextPackage` that includes review target, active stage, selected reviewer metadata, retained changed files, retained memory references, truncation notices, omitted-context markers, local-note candidates, and the full `ContextBudget` decision object.
   - Keep this as a typed package/stub only; no prompt construction or live adapter behavior.
4. Integrate narrowly with the fixture runner:
   - Calculate context budget before reviewer execution/fanout.
   - Apply reviewer count caps before raw reviewer output execution.
   - Merge budget-generated truncation notices and local-note candidates into rendered dry-run output without changing posting policy.
   - Preserve existing fixture-authored truncation notices, but make budget-generated notices graph-owned and deterministic.
5. Add `tests/test_context_budget.py`:
   - Caps changed files, patch bytes, conversation memory bytes, reviewer count, and live-call count.
   - Proves `oversized-change` receives truncation markers.
   - Proves deferred reviewers are recorded as selected-then-skipped, become structured `LocalNote` candidates, and are not executed.
   - Proves reviewer context packages include truncation status and omitted-context markers.
   - Proves repeated runs produce identical `ContextBudget` decisions and rendered JSON.
   - Proves invalid budget config fails clearly.
   - Asserts budget decision objects directly, including retained/deferred IDs, omitted markers, generated local-note IDs, and planned live-call counts.
6. Update durable docs only where behavior changes:
   - `docs/architecture/reviewer-config.md` for top-level `context_budget` config.
   - `docs/architecture/review-quality.md` or `docs/harnesses/harness-engineering.md` if budget/deferred-reviewer semantics need clarification.

## Out Of Scope

- No live LLM adapter or provider budget consumption.
- No live GitHub read or pagination.
- No prompt construction.
- No quality/posting enforcement beyond adding local notes and truncation state.
- No side effects, approval, finalization, or writer behavior.

## Validation

Focused:

```bash
python -m pytest tests/test_context_budget.py
```

Regression:

```bash
python -m pytest tests/test_config.py tests/test_models.py tests/test_cli.py tests/test_tracer_fixture_run.py tests/test_render.py
python -m pytest
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Comment On Linear

- Files changed.
- Focused context-budget harness output.
- Regression/full validation output.
- Evidence that reviewers beyond budget are deferred as local notes and not executed.
- Evidence that no live provider, live GitHub, approval, or writer behavior was introduced.
- Subagent plan/code review results.
