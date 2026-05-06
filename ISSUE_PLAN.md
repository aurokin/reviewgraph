# ISSUE PLAN: AUR-194 Run Empty Dry-Run Graph On Fixture

Active issue plan for `AUR-194` / `RG-005: Run Empty Dry-Run Graph On Fixture`.

## Linear Snapshot

- Issue: `AUR-194`
- Status at plan time: `In Progress`
- Milestone: `PRD 0004: Graph Orchestration`
- Blocks: `AUR-195`, `AUR-256`
- Blocked by in Linear: `AUR-255`, `AUR-192`, `AUR-193`
- Current repo reality: those prerequisites are represented in committed fixture parsing, target modeling, conversation memory, and the completed PRD 0010 gate.

## Goal

Add the smallest graph-facing fixture dry-run initialization slice. This issue should prove that a fixture PR can become explicit graph state with `run_mode=dry_run`, `post_enabled=false`, review target metadata, empty review output, and no writer reachability before reviewer selection or reviewer execution exists in the graph path.

This is a graph initialization slice, not the current full fixture reviewer dry run. The existing `run_fixture_dry_run` tracer must keep working unchanged.

## Acceptance Mapping

- Fixture PR can run through graph initialization:
  - Add a graph initializer that loads a fixture PR, builds conversation memory, resolves the review target, applies default context budget, and emits graph state/output without selecting or running reviewers.
- `run_mode=dry_run` and `post_enabled=false` are explicit in state:
  - Graph state/result exposes both fields directly.
- Graph emits review target metadata and empty review output:
  - Test target fields and empty findings/local notes/suggested replies/suppressed/clarifications/selected reviewers.
- Writer branch is unreachable in dry-run mode:
  - Test with a raising writer sentinel and assert zero calls.

## Implementation Plan

1. Add `src/reviewgraph/graph.py` with a narrow empty dry-run initialization function.
2. Keep this slice independent from reviewer selection and raw fixture reviewer output. It may use existing fixture, memory, target, budget, render/posting models where they are already stable.
3. Avoid changing `ReviewConfig` validation. Existing user configs should still require at least one reviewer; this issue proves an empty graph path, not a production empty reviewer config format.
4. Add `tests/test_graph_empty.py` focused on the acceptance criteria.
5. Run the focused harness and the existing tracer/CLI regressions to prove the new graph slice does not disturb the current runnable behavior.
6. Use subagent review before implementation and again after code changes.
7. Commit the plan before implementation, then commit the implementation separately.

## Out Of Scope

- No reviewer selection.
- No reviewer run status.
- No fake reviewer adapter.
- No quality classification.
- No posting plan construction beyond proving no writable branch.
- No live GitHub, live LLM, approval, finalization, or writer behavior.
- No change to CLI behavior in this issue.

## Validation Plan

```bash
python -m pytest tests/test_graph_empty.py
python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py -q
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Collect

- Focused harness output.
- Regression harness output.
- Confirmation that the existing full fixture dry-run still works.
- Subagent review result with no material findings.
- Commit SHA for the implementation.
- Linear evidence comment mapping each acceptance criterion to code/tests.
