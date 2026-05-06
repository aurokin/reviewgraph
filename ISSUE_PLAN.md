# ISSUE PLAN: AUR-196 Select Always-On Reviewers

Active issue plan for `AUR-196` / `RG-007: Select Always-On Reviewers`.

## Linear Snapshot

- Issue: `AUR-196`
- Status at plan time: `In Progress`
- Milestone: `PRD 0004: Graph Orchestration`
- Blocks: `AUR-197`, `AUR-199`, `AUR-236`, `AUR-256`
- Blocked by: `AUR-231`, `AUR-195`, `AUR-191`; current repo/Linear state satisfies these prerequisites.
- Comments at plan time: none

## Goal

Make always-on reviewer selection an explicit routing boundary for the active graph stage. Selected reviewers should include name, stage, and trigger reasons, and the selection should be persisted in `ReviewState.selected_reviewers`.

This slice should not expand selector policy. Existing path, diff, label, conversation, risk, and size behavior may be moved out of `runner.py` if needed to remove duplicated routing code, but the focused AUR-196 harness should prove only always-on routing.

## Acceptance Mapping

- Always-on reviewers are selected for eligible stages:
  - Add routing tests where an `always: true` reviewer is selected only when its config includes the active stage.
- Selected reviewers include reviewer name, stage, and reasons:
  - Assert `SelectedReviewer(name, stage, reasons)` with reason `initial_triage triggers.always=true`.
- Non-eligible stages do not select the reviewer:
  - Assert a reviewer configured only for a different stage is not selected for the active stage.
- Selection output is persisted in graph state:
  - Add a graph-level select node/helper that appends selected reviewers to `ReviewState.selected_reviewers`, and assert state persistence.

## Implementation Plan

1. Add `src/reviewgraph/routing.py` with active-stage reviewer selection helpers.
2. Move the existing runner selection logic into routing or have runner call the new routing boundary, so `runner.py` does not remain the hidden owner of reviewer selection.
3. Add `tests/test_routing.py` focused on always-on selection and `ReviewState.selected_reviewers` persistence.
4. Keep path/diff/label/risk/conversation behavior unchanged for existing tracer/CLI tests; do not claim AUR-197/AUR-198/AUR-236 acceptance here.
5. Run the focused routing harness and tracer/CLI regressions.
6. Use subagent review before implementation and again after code changes.
7. Commit the plan before implementation, then commit implementation separately.

## Out Of Scope

- No new path, diff, label, risk, size, or conversation selector behavior.
- No reviewer run status.
- No fake reviewer adapter.
- No quality classification.
- No live GitHub, live LLM, approval, finalization, or writer behavior.

## Validation Plan

```bash
python -m pytest tests/test_routing.py -q
python -m pytest tests/test_stage_cursor.py tests/test_graph_empty.py tests/test_tracer_fixture_run.py tests/test_cli.py -q
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
