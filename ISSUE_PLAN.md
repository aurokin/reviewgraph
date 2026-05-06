# ISSUE PLAN: AUR-199 Track Reviewer Run Status And Retries

Active issue plan for `AUR-199` / `RG-010: Track Reviewer Run Status And Retries`.

## Linear Snapshot

- Issue: `AUR-199`
- Status at plan time: `In Progress`
- Milestone: `PRD 0004: Graph Orchestration`
- Comments at plan time: none
- Linear description: track reviewer execution using `ReviewerRunKey` and run statuses so selection, retry, and resume behavior are idempotent.

## Goal

Consolidate reviewer run key/status behavior into an explicit policy module. Selection should register a durable run key, completed/skipped statuses should suppress rerun for the same target/config/stage/reviewer key, selected/running/failed should not be mistaken for completed, and retry exhaustion should record permanent failure.

Some basic status transitions already exist from earlier routing work. This issue should make them intentional, tested, and reusable without introducing the later fake reviewer adapter.

## Acceptance Mapping

- Reviewer run keys include target hash, config hash, stage, reviewer, attempt, retry metadata, and clarification ID:
  - Add `tests/test_reviewer_runs.py` asserting key creation and stable serialization for initial and retry/clarification keys.
- Run status distinguishes selected, running, completed, failed, and skipped:
  - Add transition helpers and tests for all status values.
- Selected-but-not-run reviewers are not treated as completed:
  - Assert selected/running/failed statuses remain runnable unless retry policy exhausts them.
- Completed reviewers are not rerun for the same target/config:
  - Assert completed and skipped statuses suppress runnable selection for the same stable key.
- Retry exhaustion records permanent failure:
  - Add retry policy helpers with a configurable max attempt count; assert exhausted failures record a final `failed` status with a reason and do not schedule another runnable key.

## Implementation Plan

1. Add `src/reviewgraph/reviewer_runs.py` with helpers for making run keys, registering selection, recording status, deciding runnable suppression, and advancing retry attempts.
2. Move routing key/status registration from `src/reviewgraph/routing.py` into the reviewer-run helper while preserving current selected/completed/skipped behavior.
3. Update runner status transitions to use the same helper for selected/running/completed/failed/skipped updates.
4. Add `tests/test_reviewer_runs.py` for key fields, stable keys, status transitions, selected-not-completed behavior, completed/skipped suppression, and retry exhaustion.
5. Keep the actual reviewer adapter and retrying malformed reviewer output out of scope; this slice models and tests the policy boundary.
6. Run reviewer-runs, routing, tracer/CLI, and full validation.
7. Use subagent review before implementation and after code changes.
8. Commit the plan before implementation, then commit implementation separately.

## Out Of Scope

- No fake reviewer adapter.
- No live reviewer execution or malformed-output repair prompt.
- No required reviewer failure posting policy.
- No clarification resume implementation beyond key fields.
- No live GitHub, live LLM, approval, finalization, or writer behavior.

## Validation Plan

```bash
python -m pytest tests/test_reviewer_runs.py -q
python -m pytest tests/test_routing.py tests/test_routing_risk.py tests/test_tracer_fixture_run.py tests/test_cli.py -q
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Collect

- Focused reviewer-run harness output.
- Regression/full validation output.
- Subagent review result with no material findings.
- Commit SHA for the implementation.
- Linear evidence comment mapping each acceptance criterion to code/tests.
