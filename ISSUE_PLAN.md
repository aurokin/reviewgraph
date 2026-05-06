# ISSUE PLAN: AUR-197 Select Path Diff And Label Reviewers

Active issue plan for `AUR-197` / `RG-008: Select Path Diff And Label Reviewers`.

## Linear Snapshot

- Issue: `AUR-197`
- Status at plan time: `In Progress`
- Milestone: `PRD 0004: Graph Orchestration`
- Comments at plan time: none
- Linear description: select reviewers based on changed paths, diff patterns, and labels against fixture PRs.

## Goal

Harden the active-stage routing boundary so path, diff pattern, and label selectors are covered by focused tests and persist the same selected-reviewer state shape introduced by `AUR-196`.

The code extracted during `AUR-196` already contains the selector mechanics. This issue should prove that behavior at the routing boundary without adding risk/size gates, conversation-pattern routing, fake reviewer execution, retries, or posting behavior.

## Acceptance Mapping

- Path triggers match changed files:
  - Add a routing test where a path selector matches a changed fixture file path.
- Diff pattern triggers match patch snippets case-insensitively:
  - Add a routing test where a mixed-case regex or literal pattern matches the casefolded patch text.
- Label triggers match PR labels:
  - Add a routing test where label matching is case-insensitive against fixture labels.
- Every matched selector appears in trigger reasons:
  - Assert all matching path, diff, and label selector reasons are present on the selected reviewer.
- Non-matching reviewers are not selected:
  - Add tests for non-matching path, diff, and label selectors returning no reviewers and leaving state unchanged.

## Implementation Plan

1. Add focused `tests/test_routing.py` coverage for path, diff pattern, and label selector behavior.
2. Adjust `src/reviewgraph/routing.py` only if the new tests expose a mismatch with the existing contract.
3. Keep selector reasons explicit and stable: `{stage} triggers.paths=...`, `{stage} triggers.diff_patterns=...`, `{stage} triggers.labels=...`.
4. Preserve existing state persistence behavior: selected reviewers, reviewer run keys, and selected run status are recorded only for runnable selected reviewers.
5. Run the routing harness plus tracer/CLI regressions and full validation.
6. Use subagent review before implementation and after code changes.
7. Commit the plan before implementation, then commit implementation separately.

## Out Of Scope

- No new risk or size classification.
- No risk/size gate selector acceptance.
- No conversation-pattern routing acceptance.
- No retry/exhaustion policy.
- No fake reviewer adapter.
- No live GitHub, live LLM, approval, finalization, or writer behavior.

## Validation Plan

```bash
python -m pytest tests/test_routing.py -q
python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py -q
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Collect

- Focused routing harness output.
- Regression/full validation output.
- Subagent review result with no material findings.
- Commit SHA for the implementation.
- Linear evidence comment mapping each acceptance criterion to code/tests.
