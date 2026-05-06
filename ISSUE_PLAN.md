# ISSUE PLAN: AUR-256 Complete PRD 0004 Graph Orchestration

Active issue plan for `AUR-256` / `Complete PRD 0004: Graph Orchestration`.

## Linear Snapshot

- Issue: `AUR-256`
- Status at plan time: `Backlog`
- Milestone: `PRD 0004: Graph Orchestration`
- Comments at plan time: none
- Linear description: milestone gate; close only after all implementation issues in this PRD milestone are complete.

## Goal

Close the PRD 0004 milestone only after proving the implementation issues are complete in Linear, validating the code and harnesses, and refactoring durable documentation so a future agent can understand the graph orchestration contracts without reading temporary planning artifacts.

This is a gate and documentation slice, not a new behavior implementation slice.

## Acceptance Mapping

- All PRD 0004 implementation issues are done:
  - Re-fetch the milestone issue inventory and confirm `AUR-194`, `AUR-195`, `AUR-196`, `AUR-197`, `AUR-235`, `AUR-198`, `AUR-199`, `AUR-200`, and `AUR-225` are `Done` with evidence comments.
- Focused and full validation passes:
  - Run the PRD 0004 focused harness families plus full suite, docs check, py-compile, and diff check.
- Documentation is refactored for progressive disclosure and harness engineering:
  - Update the narrow durable docs that an implementation agent needs: README current slice, architecture/state graph, harness strategy, implementation plan, and any decision docs needed for PRD 0004.
- Temporary planning artifacts are handled:
  - Keep `MILESTONE_PLAN.md` and `ISSUE_PLAN.md` as active committed history for the gate. Do not recreate `.ws/` or add Linear export artifacts.
- Fresh subagent review reports no material issues:
  - Use fresh subagents for gate/docs review until findings are none or non-issues.
- Linear is updated:
  - Move `AUR-256` through an appropriate in-progress/review/done flow with an evidence comment.

## Implementation Plan

1. Move `AUR-256` to `In Progress`.
2. Re-fetch PRD 0004 milestone state, linked issues, and issue comments for evidence.
3. Commit this gate plan before making documentation changes.
4. Use a fresh subagent to review the gate plan.
5. Inspect current docs and code to identify durable PRD 0004 details that should be in progressive disclosure docs rather than only in plans or Linear comments.
6. Refactor documentation in small commits:
   - README current runnable slice/status.
   - `docs/architecture/state-graph.md` for implemented PRD 0004 graph contracts and remaining future graph work.
   - `docs/harnesses/harness-engineering.md` for implemented PRD 0004 harness families and fail-closed proof.
   - `docs/plans/implementation-plan.md` for sequencing narrative updates, without copying Linear as the backlog.
   - Add or update ADRs only for durable orchestration decisions that future implementers need.
7. Run docs and code validation.
8. Use fresh subagents to review code/tests/docs/Linear evidence until no material findings remain.
9. Add a Linear evidence comment and move `AUR-256` to `Done`.
10. Push only after the milestone gate and documentation refactor are complete.

## Out Of Scope

- No new runtime behavior unless validation exposes a blocker.
- No live GitHub, live LLM, approval, finalization, or writer features.
- No copy of the full Linear backlog into durable docs.
- No `.ws/` or temporary export artifacts.

## Validation Plan

```bash
python -m pytest tests/test_graph_empty.py tests/test_stage_cursor.py tests/test_routing.py tests/test_routing_risk.py tests/test_risk.py tests/test_reviewer_runs.py tests/test_reviewers_fake.py tests/test_required_reviewer_failure.py -q
python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py tests/test_render.py -q
python -m pytest tests/test_reviewer_context.py tests/test_contract_boundaries.py tests/test_context_budget.py tests/test_prompt_injection_memory.py -q
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Collect

- Linear milestone inventory proving implementation issues are `Done`.
- Focused, regression, full, docs, py-compile, and diff-check outputs.
- Documentation refactor commit SHAs.
- Fresh subagent review results with no material findings.
- Final Linear evidence comment for `AUR-256`.
