# ISSUE PLAN: AUR-260 Complete PRD 0008 Live LLM

Active gate plan for `AUR-260` / `Complete PRD 0008: Live LLM`.

Linear is the durable source for issue status, evidence comments, and milestone progress. This gate should not add new product scope unless the audit finds a concrete PRD 0008 gap. The expected output is a closed milestone gate with evidence, plus any narrow documentation/refactor commits needed to make PRD 0008 behavior discoverable for future agents.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0008: Live LLM`
- Milestone ID: `5f47c10d-993c-452c-b71f-4a816e8a5b0a`
- Gate issue: `AUR-260`
- Status when planned: `Backlog`
- Implementation issues:
  - `AUR-212` / `RG-023: Add Live LLM Data Handling Guardrails` / `Done`
  - `AUR-232` / `RG-043: Enforce Reviewer Adapter Boundaries` / `Done`
  - `AUR-240` / `RG-051: Add Opt-In Live LLM Reviewer Adapter` / `Done`
- Downstream milestone: `PRD 0009: Harness Strategy`; first downstream implementation issue remains `AUR-242`.

## Objective

Close PRD 0008 only after proving the implemented live LLM policy, adapter boundary, opt-in path, redaction/audit behavior, budget/retry behavior, and skipped-by-default live smoke discipline match the milestone contract.

## Gate Criteria

- Every active PRD 0008 implementation issue is `Done` in Linear with an evidence comment.
- Fresh Linear inventory proves no open PRD 0008 implementation issue remains besides the gate.
- PRD 0009 remains ordered after PRD 0008; `AUR-260` must block `AUR-242`, or an explicitly equivalent first-PRD-0009 blocker must exist, and no PRD 0009 issue may be started before this gate and its docs closeout are complete.
- Focused validation for AUR-212, AUR-232, and AUR-240 passes.
- Full validation, docs check, py-compile, diff check, and backlog export check pass.
- Durable docs explain the final live LLM guardrail, adapter, opt-in, redaction, budget, retry, failure, smoke-test, reviewer-context, and adapter-boundary contracts.
- The milestone-complete documentation refactor/audit is complete before `AUR-260` moves to `Done`.
- Fresh subagent review of code, tests, docs, Linear evidence, and gate evidence reports no material issues.
- Default commands still cannot call live providers, write GitHub, require credentials, or require human input.
- No `.ws/`, temporary Linear export, live LLM artifact, live-post artifact, audit scratch file, or subagent scratch file remains.

## Plan

1. Move `AUR-260` to `In Progress` after committing this plan.
2. Audit Linear:
   - Re-fetch PRD 0008 milestone and issues.
   - Re-read AUR-212/AUR-232/AUR-240 evidence comments.
   - Verify `AUR-260` blocks `AUR-242`, or record the exact equivalent first-PRD-0009 blocker.
   - Inventory every PRD 0009 issue and verify none is `In Progress` or `Done` before this gate/docs closeout finishes.
3. Audit repository docs:
   - `README.md`
   - `docs/architecture/llm-data-handling.md`
   - `docs/architecture/reviewer-config.md`
   - `docs/architecture/state-graph.md`
   - `docs/harnesses/harness-engineering.md`
   - `docs/plans/implementation-plan.md`
   - `docs/product/rules.md`
   - `docs/prds/0008-live-llm.md`
   - `docs/prds/0010-agent-context-and-adapter-boundaries.md`
   - `docs/decisions/`
4. Run validation:
   - `.venv/bin/python -m pytest tests/test_llm_policy.py -q`
   - `.venv/bin/python -m pytest tests/test_adapter_boundaries.py tests/test_contract_boundaries.py -q`
   - `.venv/bin/python -m pytest tests/test_live_llm_adapter.py -q`
   - `.venv/bin/python -m pytest tests/test_config.py tests/test_context_budget.py tests/test_reviewer_context.py tests/test_redaction.py -q`
   - `.venv/bin/python -m pytest tests/test_cli.py tests/test_tracer_fixture_run.py tests/test_render.py tests/test_posting.py tests/test_payload_validation.py tests/test_payload_hashes.py -q`
   - `.venv/bin/python -m pytest -q`
   - `.venv/bin/python -m py_compile src/reviewgraph/*.py`
   - `.venv/bin/python scripts/check_docs.py`
   - `git diff --check`
5. Create a temporary Linear backlog export for PRD 0008/0009 ordering evidence. The export must include `AUR-212`, `AUR-232`, `AUR-240`, `AUR-260`, `AUR-242`, and all other PRD 0009 issues with statuses and blocker/blocking relationships. Run `scripts/check_docs.py --backlog-export <temp>`, record the check output and export hash for Linear evidence, then delete the export.
6. Complete the milestone documentation refactor/audit before gate closure:
   - Reconcile durable docs so a future agent can discover final PRD 0008 behavior without reading Linear comments first.
   - Update only durable docs that are stale or missing key decisions; avoid changing docs that already state the contract accurately.
   - Ensure docs cover progressive disclosure: top-level current slice in `README.md`, product guardrails in `docs/product/`, architecture contracts in `docs/architecture/`, harness commands in `docs/harnesses/`, PRD contract in `docs/prds/0008-live-llm.md`, and durable tradeoffs in `docs/decisions/` only if needed.
   - Commit docs changes separately from validation/evidence commits.
7. Re-run post-doc validation after any docs closeout commit:
   - `.venv/bin/python scripts/check_docs.py`
   - `git diff --check`
   - Any focused docs-related tests or validators affected by changed docs.
8. Use fresh subagents to review the gate evidence, docs refactor/audit, Linear relationships, and issue/milestone closure decision.
9. Move `AUR-260` to `In Review`, add a Linear gate evidence comment, then move it to `Done` only after review is clean and the documentation refactor/audit is complete.
10. After `AUR-260` is `Done`, add a project/milestone status update if Linear exposes one, and do not start PRD 0009 until the final gate evidence is attached.

## Acceptance Mapping

- Live opt-in/default fake behavior -> AUR-240 evidence, `tests/test_live_llm_adapter.py`, `tests/test_cli.py`.
- Policy/audit/redaction/budget guardrails -> AUR-212 evidence, `tests/test_llm_policy.py`, `docs/architecture/llm-data-handling.md`.
- Adapter boundaries -> AUR-232 evidence, `tests/test_adapter_boundaries.py`, `tests/test_contract_boundaries.py`.
- Default-safe harness -> full default pytest, live markers skipped, docs harness text.
- Milestone sequencing -> Linear milestone inventory plus backlog export check proving `AUR-260` blocks `AUR-242` or equivalent first-PRD-0009 blocker.
- Documentation closeout -> durable docs audit/refactor completed before `AUR-260` is `Done`, with fresh subagent review and validation evidence.

## Required Linear Gate Evidence Comment

The final AUR-260 evidence comment must include:

- Implementation issue inventory: `AUR-212`, `AUR-232`, and `AUR-240` statuses plus links to their evidence comments.
- Validation matrix: focused AUR-212/AUR-232/AUR-240 commands, full test suite, py-compile, docs check, diff check, backlog export check outputs, and post-doc-closeout validation outputs.
- Backlog/export proof: temp export hash, included issues, relationship proof for `AUR-260 -> AUR-242` or equivalent, and confirmation the temp export was deleted.
- Documentation audit result: docs inspected, docs changed or explicitly left unchanged, commit hashes, and progressive-disclosure coverage.
- Fresh subagent review outcomes: names/ids and final clean result.
- Cleanup proof: no `.ws/`, temp export, live artifacts, live-post artifacts, audit scratch files, or subagent scratch files remain.
- Acceptance mapping: live opt-in/default fake, policy/audit/redaction/budget, adapter boundaries, live smoke, default-safe tests, and milestone sequencing.

## Out Of Scope

- New live provider capabilities beyond the first opt-in HTTP transport path.
- Tool-using reviewer agents.
- Repository checkout/test execution by reviewers.
- Public production posting.
- PRD 0009 implementation.
