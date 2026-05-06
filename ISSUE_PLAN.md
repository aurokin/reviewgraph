# ISSUE PLAN: AUR-312 Core Contract Models And Schema Harness

Active issue plan for `AUR-312` / `RG-059: Define Core Contract Models And Schema Harness`.

## Linear Snapshot

- Issue: `AUR-312`
- Status at start: `In Progress`
- Milestone: `PRD 0003: Contracts`
- Blocks: `AUR-192`
- Blocked by: `AUR-258` (already Done)
- Comments at start: none
- Harness from Linear: `python -m pytest tests/test_models.py tests/test_config.py tests/test_contract_boundaries.py`

## Goal

Add schema-only contracts for PRD 0003 so later fixture, redaction, budget, graph, approval, live read, live LLM, and writer slices can depend on explicit state instead of prompt-shaped dictionaries.

This issue should produce boring dataclass/enum contracts, config validation coverage, deterministic target hashing, and import-boundary tests. It should not build runtime graph execution, fixture corpus expansion, context-budget enforcement, redaction traversal, approval UI, live GitHub reads, live LLM calls, or writer behavior.

## Contract Sources

- `docs/prds/0003-contracts.md`: primary acceptance source.
- `docs/architecture/state-graph.md`: state field parity source.
- `docs/architecture/findings-contract.md`: raw vs classified output separation, diff anchors, priority policy.
- `docs/architecture/reviewer-config.md`: config fields, trigger fields, capability policy, and `verdict_power` limits.
- `docs/architecture/side-effects.md`: approval, payload validation, marker reconciliation, finalization, and writer-result contract shape.
- `docs/architecture/llm-data-handling.md`: redaction and live LLM data handling fields that must be represented in state without enabling live calls.
- `docs/product/rules.md`: dry-run, approval, no secret exfiltration, side-effect-last, and routing-explainability guardrails.

## Implementation Plan

1. Expand `src/reviewgraph/models.py` with schema-only enums/dataclasses:
   - `RunMode`, `ReviewStage`, `ReviewerRunStatusValue`, gate/finalization status enums, and narrow validation helpers.
   - `ReviewTarget` hash helper using canonical JSON, stable key order, and explicit `merge_base_sha=None` handling.
   - `PostingTarget`, `ReadGap`, `RiskAssessment`, `ContextBudget`, `ReviewerRunKey`, `ReviewerResult`, raw reviewer output items, `ApprovalDecision`, `ActorPermissionGateResult`, `PayloadValidationResult`, `MarkerReconciliationResult`, `FinalizationStatus`, `GitHubReviewPayload`, `GitHubWriterResult`, `GraphError`, and `ReviewState`.
   - Keep existing public classes compatible with PRD 0002 tests where possible.
2. Add graph-state parity tests in `tests/test_models.py`:
   - Assert `ReviewState` exposes every field from `docs/architecture/state-graph.md` or a deliberate explicit defer list.
   - Assert default/fixture-safe construction keeps side-effect fields absent or disabled.
   - Assert invalid enum values and invalid priority values fail.
3. Add reviewer-output negative tests:
   - Raw reviewer findings must reject or quarantine graph-owned fields: `classification`, `blocking`, final `priority`, `fingerprint`, `github_destination`, or equivalent destination fields.
   - Classified findings retain graph-owned priority, diff anchor, fingerprint, and optional blocking field.
4. Add target hashing tests:
   - Hashes are stable across repeated calls.
   - Hashes change when owner/repo, PR number, base SHA, head SHA, merge-base SHA, or diff basis changes.
   - `merge_base_sha=None` is represented canonically.
5. Add config validation tests in `tests/test_config.py`:
   - Valid packaged JSON config and `examples/review_agents.example.yaml` validate.
   - Unknown trigger fields, `triggers.stages`, unsupported capabilities, unsupported tools, invalid stages, duplicate stages, and `verdict_power: approve` fail clearly.
   - If YAML support is needed for the example, add a lightweight config loader without pulling in live adapters.
6. Add import-boundary tests in `tests/test_contract_boundaries.py`:
   - Contract/config modules must not import GitHub writers, approval/finalization implementations, live LLM clients, `requests`, `openai`, `langgraph`, or GitHub transport modules.
   - Check transitive local imports where feasible by walking imported `reviewgraph.*` modules.
7. Keep PRD 0002 regression behavior intact:
   - Existing CLI/tracer/render/posting tests should keep passing.
   - Do not rename or remove current packaged fixture IDs.

## Out Of Scope

- No fixture corpus expansion; `AUR-192` owns that.
- No context-budget enforcement; `AUR-211` owns that.
- No redaction-service hardening beyond fields needed for state contracts; `AUR-237` owns focused redaction coverage.
- No live GitHub read, live LLM provider call, approval UI, finalization implementation, marker scanner, or writer adapter.
- No LangGraph runtime implementation.

## Validation

Focused:

```bash
python -m pytest tests/test_models.py tests/test_config.py tests/test_contract_boundaries.py
```

Regression:

```bash
python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py tests/test_render.py tests/test_posting.py
python -m pytest
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Comment On Linear

- Files changed.
- Acceptance checklist mapped to concrete tests.
- Focused harness output.
- Full regression output.
- Confirmation that no live API, live LLM, approval UI, finalization implementation, or writer behavior was introduced.
