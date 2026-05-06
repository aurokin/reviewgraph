# ISSUE PLAN: AUR-198 Select Gate-Based Risk And Size Reviewers

Active issue plan for `AUR-198` / `RG-009: Select Gate-Based Risk And Size Reviewers`.

## Linear Snapshot

- Issue: `AUR-198`
- Status at plan time: `In Progress`
- Milestone: `PRD 0004: Graph Orchestration`
- Comments at plan time: none
- Linear description: implement risk and size gates for staged reviewer selection, including reviewers that have only gates and no selector.

## Goal

Move risk and size gate evaluation onto the `AUR-235` `RiskAssessment` state so routing does not recompute risk policy from patches. Gate-only reviewers should be selectable when all configured gates pass, and selected reviewer reasons should show both selector matches and gate pass decisions.

## Acceptance Mapping

- `risk_min` gates selection based on deterministic risk assessment:
  - Add routing-risk tests that set `ReviewState.risk` from mixed-risk and oversized fixtures and assert `risk_min` pass/fail behavior.
- `max_files`, `changed_lines_min`, and `changed_files_min` gates are applied:
  - Add tests for pass/fail cases using `RiskAssessment.changed_file_count` and `changed_line_count`.
- Gate pass/fail decisions are recorded in selection reasons:
  - Assert selected reviewers include gate pass reasons. Non-selected gate failures remain non-selected because `SelectedReviewer` only persists selected reviewers.
- Gate-only reviewers can be selected when their gates pass:
  - Add a gate-only reviewer config with no selector fields and assert it is selected when all gates pass.

## Implementation Plan

1. Add `tests/test_routing_risk.py` focused on risk/size gate routing.
2. Update `src/reviewgraph/routing.py` so active-stage routing passes `ReviewState.risk` into trigger evaluation.
3. Remove the ad hoc routing risk heuristic and use `RiskAssessment.risk_level`, `changed_file_count`, and `changed_line_count` for gates.
4. Preserve existing selector behavior for always/path/label/diff/conversation tests.
5. Keep gate reasons stable and explicit: `triggers.risk_min>=...`, `triggers.max_files<=...`, `triggers.changed_lines_min>=...`, and `triggers.changed_files_min>=...`.
6. Keep this slice to selection only; do not change reviewer execution, quality classification, retry, or posting behavior.
7. Run routing-risk, routing, risk, tracer/CLI, and full validation.
8. Use subagent review before implementation and after code changes.
9. Commit the plan before implementation, then commit implementation separately.

## Out Of Scope

- No new risk classification policy.
- No fake reviewer adapter.
- No retry/exhaustion policy.
- No required reviewer failure policy.
- No live GitHub, live LLM, approval, finalization, or writer behavior.

## Validation Plan

```bash
python -m pytest tests/test_routing_risk.py -q
python -m pytest tests/test_routing.py tests/test_risk.py tests/test_tracer_fixture_run.py tests/test_cli.py -q
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Collect

- Focused routing-risk harness output.
- Regression/full validation output.
- Subagent review result with no material findings.
- Commit SHA for the implementation.
- Linear evidence comment mapping each acceptance criterion to code/tests.
