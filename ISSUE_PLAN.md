# ISSUE PLAN: AUR-232 Enforce Reviewer Adapter Boundaries

Active issue plan for `AUR-232` / `RG-043: Enforce Reviewer Adapter Boundaries`.

Linear is the durable source for status and acceptance criteria. Repository docs are the durable behavior contracts. This issue hardens reviewer adapter interfaces and harnesses only; it must not add a live LLM provider integration.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0008: Live LLM`
- Issue: `AUR-232`
- Status when planned: `Backlog`
- Blocking issue: `AUR-212` is `Done`
- Linear handoff names likely files: `src/reviewgraph/reviewers.py`, `tests/test_adapter_boundaries.py`
- Focused harness from Linear: `python -m pytest tests/test_adapter_boundaries.py`
- Out of scope from Linear: live LLM provider integration

## Objective

Add explicit interface and harness coverage proving reviewer adapters are decoupled from GitHub transports, side-effect payload builders, approval/finalization state, provider clients, and ambient process/network handles. This issue should create the adapter contract that both fake reviewers and future live reviewers must share.

## Contracts To Preserve

- Reviewer adapters accept only a scoped `ReviewerContextPackage` or, for future live adapters, a passing live LLM policy result built from that package.
- Reviewer adapters return structured `ReviewerResult` values from a graph-owned `ReviewerRunKey`.
- Reviewer adapters must not receive GitHub read transports, GitHub write transports, approval state, finalization state, posting payload builders, writer clients, provider clients, process handles, or ambient network/session clients.
- Reviewer capabilities must be validated before adapter execution. Unsupported capabilities remain config errors or pre-execution boundary failures, not prompt-time decisions.
- Fake reviewer behavior remains default, deterministic, provider-free, and compatible with existing fake reviewer repair/normalization semantics.
- `llm_policy` remains the canonical provider-bound request gate for future live adapters; bypassing it should be a boundary-test failure when live adapter code is introduced.

## Current Code Context

- `src/reviewgraph/reviewers.py` currently exposes `FakeReviewerAdapter.run(package)` and `execute_fake_reviewer(adapter, package, run_key)`.
- `FakeReviewerAdapter.run()` already accepts only `ReviewerContextPackage`, but `execute_fake_reviewer()` accepts an adapter object without a shared adapter protocol or explicit capability preflight.
- `tests/test_reviewers_fake.py` already asserts the fake adapter run signature accepts only `package` and that fake reviewers have no provider behavior.
- `tests/test_contract_boundaries.py` already contains import-boundary checks for models, config, findings, GitHub fake read, and reviewer context, but there is no `tests/test_adapter_boundaries.py` focused on reviewer adapter modules and shared adapter contracts.
- `src/reviewgraph/llm_policy.py` from AUR-212 is provider-SDK-free and returns policy results/failure summaries without provider execution.
- `src/reviewgraph/config.py` and `ReviewerAgentConfig` already reject unsupported capabilities during config parsing/model validation.

## Plan

1. Add focused tests in `tests/test_adapter_boundaries.py` before implementation:
   - `FakeReviewerAdapter.run` accepts only `package`;
   - `execute_fake_reviewer` accepts only `adapter`, `package`, and graph-owned `run_key`;
   - adapter functions reject non-`ReviewerContextPackage` package inputs before registry lookup or reviewer output parsing;
   - `execute_fake_reviewer` returns `ReviewerResult` for valid fake output and never a raw mapping/string;
   - reviewer adapter modules do not import GitHub read/write transports, approval/finalization/posting/writer modules, provider SDKs, network/process modules, or global client modules;
   - reviewer adapter callable signatures contain no forbidden handle-like parameter names such as `github_client`, `transport`, `writer`, `approval`, `finalization`, `payload`, `session`, `process`, or `provider_client`;
   - fake adapter package capability policy must match reviewer config capabilities and remain read-only/provider-off by default before execution;
   - unsupported or tool-like capabilities cannot be smuggled directly through a manually constructed package into adapter execution;
   - future live adapter contract is represented as a protocol/typing surface that accepts a passing AUR-212 policy result and a run key and returns `ReviewerResult`, without provider execution in this issue.
2. Implement narrow boundary support in `src/reviewgraph/reviewers.py`:
   - define adapter protocols or type aliases for fake and future live reviewers if useful;
   - add a pre-execution boundary validator for `ReviewerContextPackage` capability policy and selected reviewer metadata;
   - call the validator from `FakeReviewerAdapter.run()` or `execute_fake_reviewer()` before any fake registry lookup;
   - keep normalization/repair behavior unchanged.
3. Add static import/signature tests for `src/reviewgraph/reviewers.py`, `src/reviewgraph/reviewer_context.py`, and `src/reviewgraph/llm_policy.py` so future adapter code cannot bypass the intended boundaries.
4. Update narrow docs only if needed:
   - `docs/architecture/state-graph.md` reviewer context boundary;
   - `docs/harnesses/harness-engineering.md` reviewer boundary harness expectations.
5. Run focused and regression validation.
6. Use fresh subagents for code/docs review until no material findings remain.
7. Commit implementation and review-fix batches separately, then update Linear with evidence.

## Focused Harness

```bash
.venv/bin/python -m pytest tests/test_adapter_boundaries.py -q
```

## Regression Harness

```bash
.venv/bin/python -m pytest tests/test_adapter_boundaries.py tests/test_contract_boundaries.py -q
.venv/bin/python -m pytest tests/test_reviewers_fake.py tests/test_reviewer_json_repair.py -q
.venv/bin/python -m pytest tests/test_llm_policy.py tests/test_reviewer_context.py tests/test_prompt_injection_memory.py -q
.venv/bin/python -m py_compile src/reviewgraph/*.py
.venv/bin/python scripts/check_docs.py
git diff --check
```

## Acceptance Mapping

- Adapters accept only context package and return structured reviewer results -> adapter signature tests plus fake execution result tests.
- No GitHub transports/approval/writer payload builders -> static import and callable-parameter boundary tests.
- Capabilities validated before execution -> package/capability preflight tests, including manually constructed invalid package cases.
- Boundary tests fail on direct imports or ambient clients -> AST import tests and transitive import smoke tests.
- Fake/live share input/output contract -> fake protocol and future live policy-result protocol tests without provider SDK calls.

## Out Of Scope

- Live LLM provider calls.
- CLI `--live-llm` surface.
- Provider SDKs, retry loops, timeouts, or fake live transport execution.
- GitHub read/write behavior changes.
- Refactoring fake reviewer normalization, repair, quality classification, or runner stage flow beyond what the boundary validator requires.
