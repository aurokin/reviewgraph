# ISSUE PLAN: AUR-195 Implement Stage Cursor Invariants

Active issue plan for `AUR-195` / `RG-006: Implement Stage Cursor Invariants`.

## Linear Snapshot

- Issue: `AUR-195`
- Status at plan time: `In Progress`
- Milestone: `PRD 0004: Graph Orchestration`
- Blocks: `AUR-196`, `AUR-256`
- Blocked by: `AUR-194`, now `Done`
- Comments at plan time: none

## Goal

Create the explicit stage cursor contract that later graph routing will use. The cursor should own `active_stage`, `stage_queue`, `suspended_stage`, and `completed_stages` transitions, produce traceable before/after records, and prevent completed normal stages from being run again.

This slice should stay focused on cursor state. It should not select reviewers, run reviewers, classify output, or implement clarification resume.

## Acceptance Mapping

- Initial cursor state is `active_stage=None` and `stage_queue=["initial_triage","specialized_review","logic_review"]`:
  - Reuse the AUR-194 empty graph state and add focused tests for the cursor fields.
- `stage_queue` contains only future normal stages:
  - Cursor helper validates that the active stage is not in the queue, completed stages are not in the queue, and `clarification_review` is not in the normal queue.
- `advance_or_finish_stage` is the only code path that mutates stage cursor fields:
  - Add `src/reviewgraph/state.py` with `advance_or_finish_stage` as the stage-cursor mutator and have graph code use exported initial-stage constants rather than duplicating queue literals.
- Completed stages are never rerun:
  - Tests should advance through all normal stages and assert completed stages are not reactivated; invalid queue state containing a completed stage should fail closed.
- Cursor transition traces include before/after stage and queue fields:
  - Add a `StageCursorTransition` trace model/dict with active stage, suspended stage, stage queue, completed stages, and transition reason before/after.

## Implementation Plan

1. Add `src/reviewgraph/state.py` with normal stage constants, cursor validation, `StageCursorTransition`, and `advance_or_finish_stage`.
2. Update `src/reviewgraph/graph.py` to use the shared initial normal stage queue constant for AUR-194 initialization.
3. Add `tests/test_stage_cursor.py` covering initial state, future-only queue invariant, normal stage advancement, final completion, completed-stage rerun prevention, and transition trace fields.
4. Keep `clarification_review` as a validation rule only in this issue: it is transient and not allowed in the normal queue, but full clarification scheduling/resume behavior remains later PRD 0004 graph work.
5. Run the focused harness and graph/tracer regressions.
6. Use subagent review before implementation and again after code changes.
7. Commit the plan before implementation, then commit the implementation separately.

## Out Of Scope

- No reviewer selection.
- No reviewer run status.
- No clarification resume implementation.
- No fake reviewer adapter.
- No quality classification.
- No live GitHub, live LLM, approval, finalization, or writer behavior.

## Validation Plan

```bash
python -m pytest tests/test_stage_cursor.py tests/test_graph_empty.py -q
python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py -q
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Collect

- Focused harness output.
- Regression/full validation output.
- Subagent review result with no material findings.
- Commit SHA for the implementation.
- Linear evidence comment mapping each acceptance criterion to code/tests.
