# ISSUE PLAN: AUR-255 Complete PRD 0010 Agent Context And Adapter Boundaries

Active issue plan for `AUR-255` / `Complete PRD 0010: Agent Context And Adapter Boundaries`.

## Linear Snapshot

- Issue: `AUR-255`
- Status at plan time: `In Progress`
- Milestone: `PRD 0010: Agent Context And Adapter Boundaries`
- Milestone ID: `0dea2cdd-6433-41d8-b1a4-b91b07d3acc9`
- Gate condition: close only after all implementation issues in this PRD milestone are complete.
- Current milestone inventory from Linear project issue list:
  - `AUR-231` / `RG-042: Define Reviewer Context Package` / `Done` / completed `2026-05-06T05:18:07.212Z`
  - `AUR-233` / `RG-044: Add Prompt Injection Memory Harness` / `Done` / completed `2026-05-06T15:19:01.862Z`
  - `AUR-255` / `Complete PRD 0010: Agent Context And Adapter Boundaries` / `In Progress`
- `AUR-231` evidence comment: `221f0721-6960-45ce-99dd-b6cb62811eda`
- `AUR-233` evidence comment: `a299d649-6afe-4940-973d-c3d9335c64a2`
- `.ws/` status at plan time: absent.

## Goal

Close PRD 0010 only after proving the milestone is actually complete in Linear, code, tests, and docs.

This gate should not add new product behavior. It should produce audit artifacts, durable documentation cleanup, validation evidence, and a Linear completion comment that maps every PRD 0010 requirement to concrete committed evidence.

## Acceptance Mapping

- All PRD 0010 implementation issues are complete in Linear.
- Every implementation issue has an evidence comment mapping acceptance criteria to code/tests/docs.
- No active non-gate PRD 0010 issue remains in the milestone inventory.
- The repo contains the reviewer context package contract and harness from `AUR-231`.
- The repo contains the prompt-injection memory harness and passive-memory body exclusion from `AUR-233`.
- Durable docs explain the final PRD 0010 design: reviewer context package, adapter boundaries, inert tool metadata, prompt input instruction/data separation, passive memory metadata-only policy, evidence provenance, provider preview, and harness expectations.
- Focused validation, full validation, docs check, py-compile, and diff check pass.
- Fresh subagent review finds no material gate, docs, test, or implementation gaps.
- Temporary exports or workspace artifacts are removed before closure.

## Implementation Plan

1. Re-read current Linear state for `AUR-231`, `AUR-233`, `AUR-255`, their comments, and the PRD 0010 milestone inventory.
2. Update `MILESTONE_PLAN.md` to reflect `AUR-233` Done and `AUR-255` active.
3. Commit this `ISSUE_PLAN.md` and milestone-plan refresh before executing the gate.
4. Use fresh subagents to review this gate plan before changing docs or closing Linear.
5. Build a temporary Linear-derived PRD 0010 backlog export from the current issue inventory and comments. Keep it outside durable docs or remove it before commit if it is only a validation artifact.
6. Run `python scripts/check_docs.py --backlog-export <tmp-file>` if the script supports the export, otherwise record the unsupported shape explicitly and run `python scripts/check_docs.py`.
7. Audit current docs against what an implementation agent needs when dropping into the repo:
   - `README.md`
   - `docs/product/vision.md`
   - `docs/product/rules.md`
   - `docs/architecture/overview.md`
   - `docs/architecture/state-graph.md`
   - `docs/architecture/reviewer-config.md`
   - `docs/architecture/findings-contract.md`
   - `docs/harnesses/harness-engineering.md`
   - `docs/decisions/0005-inert-reviewer-tool-metadata.md`
   - `docs/prds/0010-agent-context-and-adapter-boundaries.md`
   - `docs/plans/implementation-plan.md`
8. Refactor only durable docs that are stale, misleading, or insufficient for PRD 0010. Prefer progressive disclosure: README/product summary first, architecture contract next, harness detail deeper, ADRs for durable tradeoffs.
9. Run focused PRD 0010 validation:
   - `python -m pytest tests/test_reviewer_context.py tests/test_config.py tests/test_contract_boundaries.py tests/test_prompt_injection_memory.py tests/test_memory.py tests/test_cli.py -q`
10. Run boundary/regression validation:
    - `python -m pytest tests/test_context_budget.py tests/test_tracer_fixture_run.py tests/test_render.py tests/test_redaction.py -q`
11. Run full validation:
    - `python -m pytest -q`
    - `python -m py_compile src/reviewgraph/*.py`
    - `python scripts/check_docs.py`
    - `git diff --check`
12. Use fresh subagents for gate review of docs, Linear evidence, and validation. Iterate until no material findings remain.
13. Commit docs/gate changes after each review-fix batch.
14. Move `AUR-255` to `In Review`, add a Linear evidence comment with milestone inventory, validation output, docs changes, export hash if applicable, and subagent review result.
15. Move `AUR-255` to `Done` only after final Linear fetch confirms `AUR-231` and `AUR-233` are still Done and no active non-gate PRD 0010 issue remains.

## Out Of Scope

- No new reviewer adapter execution.
- No live LLM calls.
- No live GitHub reads or writes.
- No approval, finalization, writer, or payload-destination implementation.
- No `.ws/` recreation.
- No broad rewrite of unrelated PRD milestones.

## Validation Plan

```bash
python -m pytest tests/test_reviewer_context.py tests/test_config.py tests/test_contract_boundaries.py tests/test_prompt_injection_memory.py tests/test_memory.py tests/test_cli.py -q
python -m pytest tests/test_context_budget.py tests/test_tracer_fixture_run.py tests/test_render.py tests/test_redaction.py -q
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

If a temporary Linear export is created:

```bash
python scripts/check_docs.py --backlog-export <tmp-file>
sha256sum <tmp-file> || shasum -a 256 <tmp-file>
rm <tmp-file>
```

## Completion Evidence To Collect

- Current Linear milestone inventory.
- `AUR-231` and `AUR-233` evidence comment IDs.
- Focused validation output.
- Boundary/regression validation output.
- Full validation output.
- Docs-check output, including backlog-export result if supported.
- Subagent gate review result with no material findings.
- Git status proving no `.ws/` or temporary export remains.
- Commit SHA(s) for gate docs/refactor changes.
