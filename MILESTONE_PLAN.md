# MILESTONE PLAN: PRD 0008 Live LLM

Active execution artifact for this milestone. Linear remains the durable source for issue status, blockers, comments, and milestone order. Repository docs remain the durable product, architecture, harness, and decision contracts. If Linear and durable docs disagree on behavior, stop and reconcile both before implementation.

## Linear Scope Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0008: Live LLM`
- Milestone ID: `5f47c10d-993c-452c-b71f-4a816e8a5b0a`
- Current milestone status when planned: `0%`
- Active implementation issues fetched from Linear:
  - `AUR-212` / `RG-023: Add Live LLM Data Handling Guardrails` / `Backlog`
  - `AUR-232` / `RG-043: Enforce Reviewer Adapter Boundaries` / `Backlog`
  - `AUR-240` / `RG-051: Add Opt-In Live LLM Reviewer Adapter` / `Backlog`
- Gate issue:
  - `AUR-260` / `Complete PRD 0008: Live LLM` / `Backlog`
- Downstream milestone:
  - `PRD 0009: Harness Strategy` is next in milestone order. `AUR-260` should block the first PRD 0009 implementation issue before PRD 0008 closes.

## Milestone Intent

PRD 0008 introduces live LLM reviewer capability without weakening the default deterministic/fake path. Live LLM review must be explicit opt-in, bounded by context budget, minimized through `ReviewerContextPackage`, redacted before provider submission, and isolated from GitHub read/write transports and side-effect code.

The milestone should prove:

- fake reviewers remain the default for tests and normal dry-runs;
- default commands never call live providers or require credentials;
- provider-bound payloads are previewable, minimized, redacted, and auditable;
- live provider calls consume explicit live-call budget;
- provider/model/reviewer/target/context/truncation/redaction state is recorded;
- fake and live reviewer adapters share the same input/output contract;
- live LLM smoke is opt-in and skipped by default;
- provider failures map into existing required/optional reviewer failure semantics instead of bypassing the graph.

## Current Code Snapshot

- `src/reviewgraph/reviewer_context.py` already builds `ReviewerContextPackage`, prompt input, and non-live `ProviderRequestPreview` values with redaction status and raw-provider/raw-trace flags.
- `src/reviewgraph/redaction.py` already redacts token-like text and structured data and separates raw provider submission from raw trace persistence.
- `src/reviewgraph/context_budget.py` already models `max_live_calls`, retained/deferred live-call reviewer IDs, and deterministic live-call deferral.
- `src/reviewgraph/config.py` already validates reviewer `model`, inert `tools`, `context`, `capabilities`, and `context_budget.max_live_calls`.
- `src/reviewgraph/reviewers.py` currently contains the fake reviewer adapter and execution path only; it has no live provider abstraction.
- `src/reviewgraph/runner.py` currently applies reviewer budgets without live-call costs because no live-enabled reviewer execution path exists yet. PRD 0008 must make live-call cost explicit before any provider execution can be added.
- `tests/test_reviewer_context.py`, `tests/test_redaction.py`, `tests/test_context_budget.py`, `tests/test_contract_boundaries.py`, and `tests/test_reviewers_fake.py` already cover much of the guardrail surface. PRD 0008 should extend these contracts without coupling reviewer code to side effects.
- `pyproject.toml` currently marks `live_read` and `live_post`, but not `live_llm`.

## Execution Order

1. `AUR-212` first: add the canonical live LLM data-handling policy gate. This should focus on policy/state/previews/failure summaries, not provider SDK calls. Expected implementation likely includes `src/reviewgraph/llm_policy.py` and `tests/test_llm_policy.py`, plus narrow updates to docs or existing helpers if needed. The policy gate must accept only `ReviewerContextPackage` plus explicit policy inputs and produce a passing provider execution plan or a blocked result with stable reason code.
   - The policy gate must also define the live-call reservation contract: callers pass the current run-level live-call ledger, each passing plan reserves one call, and the returned ledger is the only input that may be used for the next live reviewer. This prevents two independently passing reviewers from double-spending a cap of one.
   - Reservations must be keyed by reviewer execution identity, using the reviewer run key plus target/config/provider/model/request hash. Re-evaluating the same run key with the same request hash is idempotent and does not consume another call; re-evaluating the same run key with a different request hash blocks with a stable conflict reason. New retry attempts or clarification-bound runs use distinct run keys and consume fresh budget.
   - The policy result must separate in-memory provider execution data from default-persisted audit data. Default serialization records provider/model/reviewer/target/context/truncation/redaction/budget facts, hashes, sizes, retained context IDs, omitted-context IDs/reasons, and raw flags; it must not persist full provider request text unless raw trace persistence is explicitly approved.
2. `AUR-232` second: harden reviewer adapter boundaries for both fake and future live adapters. This should prove reviewer adapters accept only context packages or a passing live LLM policy result, return structured reviewer results, validate capabilities before execution, and cannot import/ambiently access GitHub transports, approval/finalization, posting payload builders, provider clients, shell/process handles, or side-effect modules. It should also make bypassing `llm_policy` a boundary-test failure for future live adapters.
3. `AUR-240` third: add the first opt-in live LLM reviewer adapter behind explicit CLI/config/API opt-in using the same context and output contracts as fake reviewers. The adapter must consume the `AUR-212` policy result before provider execution. Default tests use fake provider transports; the real live smoke is marked and skipped by default.
4. `AUR-260` last: close the milestone only after all active implementation issues are `Done`, Linear evidence exists, focused/full validation passes, durable docs explain live LLM contracts, and fresh subagent review reports no material gaps.

## Linear Relationship Plan

Before implementation begins, reconcile Linear blockers so the milestone enforces the sequence:

- `AUR-232` blocked by `AUR-212`.
- `AUR-240` blocked by `AUR-212` and `AUR-232`.
- `AUR-260` blocked by `AUR-240`.
- `AUR-260` blocks `AUR-242` in `PRD 0009: Harness Strategy`, unless Linear already has an equivalent first PRD 0009 blocker.

These are append-only relationship updates; do not remove unrelated user-authored relations without confirming they are stale.

## Issue Workflow

For each issue:

1. Re-fetch the issue, milestone, blockers, and relevant docs/code.
2. Move the issue to `In Progress` when starting active work.
3. Replace `ISSUE_PLAN.md` with a narrow issue plan and commit it before implementation.
4. Use fresh subagents to review the milestone/issue plan before code changes.
5. Implement the smallest contract/harness slice that satisfies the issue and does not implement later milestone scope.
6. Run the issue harness named in Linear plus regression tests for touched shared behavior.
7. Use fresh subagents for code/docs review until no material findings remain.
8. Commit the completed issue and every review-fix batch separately.
9. Move the issue to `In Review`, add a Linear evidence comment with commands and artifact coverage, then move it to `Done` only when acceptance criteria map to concrete evidence.

For milestone gates and blocker/order changes, also run `python scripts/check_docs.py --backlog-export path/to/linear-backlog-export.json` against a temporary canonical Linear export, then delete the export before handoff.

## Harness Strategy

- `AUR-212` focused harness: `python -m pytest tests/test_llm_policy.py -q`
- `AUR-232` focused harness: `python -m pytest tests/test_adapter_boundaries.py tests/test_contract_boundaries.py -q`
- `AUR-240` focused harness: `python -m pytest tests/test_live_llm_adapter.py -q`
- Milestone regression set after shared LLM/reviewer changes:
  - `python -m pytest tests/test_config.py tests/test_context_budget.py tests/test_reviewer_context.py tests/test_redaction.py -q`
  - `python -m pytest tests/test_reviewer_context.py tests/test_redaction.py tests/test_context_budget.py tests/test_reviewers_fake.py -q`
  - `python -m pytest tests/test_prompt_injection_memory.py tests/test_contract_boundaries.py -q`
  - `python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py -q`
  - `python -m pytest -q`
  - `python -m py_compile src/reviewgraph/*.py`
  - `python scripts/check_docs.py`
  - `git diff --check`

Default validation must not call live providers, require credentials, or require human input. Add a `live_llm` pytest marker before live smoke tests land; live smoke tests must be marked `live_llm` and skipped unless explicit environment opt-in is present.

## Contract Guardrails

- Fake reviewers remain default.
- Live LLM calls require explicit run-level opt-in; config metadata alone cannot trigger a live provider call.
- `AUR-212` owns the opt-in truth table: model without live opt-in is preview metadata only; live opt-in without provider/model fails closed; raw provider submission and raw trace persistence require separate explicit opt-ins.
- `llm_policy` is the canonical request-construction API for provider-bound execution. Future live adapters must consume its passing policy result before invoking any provider transport.
- Provider-bound request payloads must be built from `ReviewerContextPackage`, not raw PR objects, full config maps, GitHub transports, side-effect state, or ambient process state.
- Provider-bound request text is minimized and redacted by default.
- Raw provider submission and raw trace persistence are separate explicit opt-ins; neither implies the other, and live opt-in alone does not permit raw submission.
- Provider/model/reviewer/target/context policy/truncation/redaction status must be recorded for any provider-bound request or live adapter result.
- Live-call budget is graph/policy state and must fail closed or defer deterministically before provider execution. A passing live provider execution plan carries `live_call_budget_cost=1` unless a later policy proves a different cost.
- Live-call budget reservations are sequential run-level state, not independent per-reviewer checks. `llm_policy` owns a pure reservation ledger for AUR-212; AUR-240/AUR-232 must wire that ledger into graph/adapters before live execution.
- Live-call reservation ledgers are idempotent by reviewer run key and request hash. Duplicate same-key/same-request evaluation returns the existing reservation; same-key/different-request evaluation fails closed with `live_call_reservation_conflict`; retry attempts consume fresh budget because they have distinct reviewer run keys.
- Live adapter outputs must flow through the same normalization, repair/failure, quality classification, clarification, and required/optional reviewer failure policy as fake outputs.
- Provider timeout, rate limit, retry exhaustion, malformed response, unavailable service, missing credentials, missing opt-in, missing provider, missing model, live-call budget exceeded, raw provider not approved, or raw trace not approved cannot produce postable findings by themselves.
- Provider failures must use a redacted typed summary with stable reason codes and no raw request headers, raw response bodies, tokens, or private PR text.
- Policy/audit output must be default-safe: full request text may exist only in the in-memory execution plan for immediate provider submission, while persisted/default JSON audit records store content hashes, byte counts, redaction summaries, retained file paths, retained memory IDs, omitted-context markers, truncation notices, and raw opt-in proof.
- Tool-using agents, repository checkout, test execution, and provider-specific prompt optimization remain out of scope.
- Reviewer adapters must not import or accept GitHub read transports, GitHub write transports, approval/finalization state, posting payload builders, writer clients, provider clients outside the explicit live adapter transport boundary, shell handles, or ambient network/session clients.

## Documentation Work

Update the narrowest durable docs alongside behavior:

- Live LLM data handling -> `docs/architecture/llm-data-handling.md`.
- Reviewer context or adapter boundaries -> `docs/prds/0010-agent-context-and-adapter-boundaries.md`, `docs/architecture/reviewer-config.md`, and `docs/architecture/state-graph.md`.
- Harness expectations and live smoke discipline -> `docs/harnesses/harness-engineering.md`.
- Implementation sequencing -> `docs/plans/implementation-plan.md` only if the phase narrative changes materially.
- Durable tradeoffs -> `docs/decisions/` only when future agents need a rule that should not be rediscovered from Linear history.

## PRD 0008 Acceptance Surface

The milestone is complete when ReviewGraph proves:

- live LLM is explicit opt-in and disabled by default;
- fake reviewer adapters remain default for tests and normal dry-runs;
- provider-bound request previews and live calls use minimized `ReviewerContextPackage` data;
- token-like secrets are absent from provider-bound default payloads, logs/traces/default JSON, rendered markdown, and candidate/final payloads;
- provider/model/reviewer/target/context policy/truncation/redaction state is recorded;
- live-call caps defer or block reviewers deterministically before provider execution;
- raw provider submission and raw trace persistence are separately gated and recorded;
- provider failure summaries are typed and redacted;
- reviewer adapter boundaries cover both fake and live adapter paths;
- fake and live reviewer adapters share the same structured input/output result contract;
- provider failures map into existing reviewer result/status semantics;
- live LLM smoke is opt-in, marked, skipped by default, and safe without credentials;
- full default test suite is credential-free and does not make live provider calls.

## Deferred Scope

- Tool-using reviewer agents.
- Repository checkout and file retrieval outside PR context.
- Running repository tests.
- Provider-specific prompt optimization.
- Hosted/webhook live LLM policy.
- Public production posting command.

## Milestone Completion Criteria

`AUR-260` can close only when:

- Every active PRD 0008 implementation issue is `Done` in Linear with an evidence comment.
- Fresh Linear inventory proves blockers are complete and PRD 0009 remains blocked until PRD 0008 is closed.
- Focused validation for AUR-212, AUR-232, and AUR-240 passes.
- Full validation, docs check, py-compile, diff check, and backlog export check pass.
- Durable docs explain the final live LLM guardrail, adapter, opt-in, redaction, budget, and smoke-test contracts.
- Fresh subagent review of code, tests, docs, Linear evidence, and the milestone gate reports no material issues.
- Default commands still cannot call live providers, write GitHub, require credentials, or require human input.
- No `.ws/`, temporary Linear export, live LLM artifacts, live-post artifacts, audit scratch file, or subagent scratch file remains in the repository.
