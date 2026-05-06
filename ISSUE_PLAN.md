# ISSUE PLAN: AUR-235 Classify Change Risk And Size

Active issue plan for `AUR-235` / `RG-046: Classify Change Risk And Size`.

## Linear Snapshot

- Issue: `AUR-235`
- Status at plan time: `In Progress`
- Milestone: `PRD 0004: Graph Orchestration`
- Comments at plan time: none
- Linear description: add deterministic change risk and size classification so risk/size reviewer gates do not hide their own policy.

## Goal

Introduce a deterministic graph-owned risk/size classifier that produces `RiskAssessment` from fixture PR context. The classifier should record facts and threshold decisions separately from reviewer selection so `AUR-198` can later route on those facts without hiding policy inside prompts or trigger strings.

## Acceptance Mapping

- Risk assessment records changed file count, changed line count, touched surfaces, labels, and diff pattern hints:
  - Add `src/reviewgraph/risk.py` with `classify_change_risk(pr, thresholds=...) -> RiskAssessment`.
  - Add tests asserting exact fields for mixed-risk and oversized fixtures.
- Risk levels are deterministic for fixture PRs:
  - Assert stable low/medium/high outcomes for representative fixture PRs.
- Size thresholds are configurable and traceable:
  - Add default thresholds and a configurable `RiskThresholds` input at the classifier boundary; assert changed threshold values alter traceable serialized reasons.
- Risk and size decisions are recorded separately from reviewer selection reasons:
  - Store the assessment in `ReviewState.risk` during dry-run setup without changing `SelectedReviewer.reasons`.
  - Classify against full PR size facts before or independent of reviewer-context budgeting so oversized and omitted context still records original risk/size.
  - Assert JSON output has a `risk` envelope separate from `selected_reviewers`.
- Mixed-risk and oversized fixtures have golden expected risk output:
  - Add golden assertions in `tests/test_risk.py` for `mixed-risk-change` and `oversized-change`.

## Implementation Plan

1. Add `src/reviewgraph/risk.py` with deterministic surface detection, diff hint extraction, threshold defaults, and risk-level selection.
2. Keep the classifier pure: input PR context plus thresholds, output `RiskAssessment`; no reviewer config, no routing decisions, no side effects.
3. Wire `run_fixture_dry_run` and the empty graph state initializer to populate `ReviewState.risk` using default thresholds and full fixture PR facts, not the budget-retained reviewer context.
4. Add a stable JSON representation of risk assessment to the dry-run envelope for harness evidence.
5. Add `tests/test_risk.py` for golden mixed-risk and oversized fixture outputs, classifier-boundary configurable thresholds, budget-independent size facts, and separation from reviewer selection reasons.
6. Run risk, routing, tracer/CLI, and full validation.
7. Use subagent review before implementation and after code changes.
8. Commit the plan before implementation, then commit implementation separately.

## Out Of Scope

- No risk or size reviewer selection gates.
- No changes to `ReviewerTriggers.risk_min`, `max_files`, `changed_lines_min`, or `changed_files_min` semantics.
- No fake reviewer adapter.
- No retry/exhaustion policy.
- No live GitHub, live LLM, approval, finalization, or writer behavior.

## Validation Plan

```bash
python -m pytest tests/test_risk.py -q
python -m pytest tests/test_routing.py tests/test_tracer_fixture_run.py tests/test_cli.py -q
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Collect

- Focused risk harness output.
- Regression/full validation output.
- Subagent review result with no material findings.
- Commit SHA for the implementation.
- Linear evidence comment mapping each acceptance criterion to code/tests.
