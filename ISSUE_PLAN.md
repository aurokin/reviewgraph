# ISSUE PLAN: AUR-212 Add Live LLM Data Handling Guardrails

Active issue plan for `AUR-212` / `RG-023: Add Live LLM Data Handling Guardrails`.

Linear is the durable source for status and acceptance criteria. Repository docs are the durable behavior contracts. This issue must not add provider SDK calls or a live adapter; it creates the guardrail layer that later live adapters must consume.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0008: Live LLM`
- Issue: `AUR-212`
- Status when planned: `Backlog`
- Linear handoff names likely files: `src/reviewgraph/llm_policy.py`, `tests/test_llm_policy.py`
- Focused harness from Linear: `python -m pytest tests/test_llm_policy.py`
- Out of scope from Linear: provider SDK calls

## Objective

Add deterministic live LLM data-handling guardrails before any live provider adapter exists. The implementation should define the canonical policy gate a future live adapter must consume before provider execution: explicit opt-in, provider/model disclosure, redacted provider-bound request construction, raw-provider/raw-trace opt-in gating, redacted provider failure summaries, and live-call budget accounting.

## Contracts To Preserve

- Fake reviewers remain default for tests and normal dry-runs.
- Config metadata such as `model` or inert `tools` cannot trigger a live provider call.
- AUR-212 defines policy inputs only; CLI/config/provider resolution and provider execution are deferred to AUR-240.
- Run-level live opt-in is required for live readiness. Live opt-in without provider/model fails closed.
- Provider-bound request data must come from `ReviewerContextPackage`, not raw PR objects, full config maps, GitHub transports, side-effect state, or ambient process state.
- Provider-bound request text is minimized and redacted by default.
- Raw provider submission and raw trace persistence are separate explicit choices; live opt-in alone does not permit raw submission.
- Live-call caps are enforced before provider execution. A passing provider execution plan carries explicit `live_call_budget_cost=1` and returns an updated run-level budget reservation ledger so later reviewers cannot double-spend the same cap.
- Provider execution data and persisted audit data are separate. Full request text may exist in memory for immediate provider submission, but default serialization records only audit-safe fields, hashes, sizes, context inventory, redaction status, raw flags, and opt-in proof.
- Provider failures are represented by typed redacted summaries with stable reason codes.
- Default tests cannot call live providers, require credentials, write GitHub, or require human input.

## Current Code Context

- `build_provider_request_preview()` in `src/reviewgraph/reviewer_context.py` already serializes prompt input, applies provider-bound redaction, and records provider/model/reviewer/target/raw flags.
- `redact_provider_bound_text()` and `redact_trace_data()` in `src/reviewgraph/redaction.py` already separate raw provider submission from raw trace persistence.
- `apply_reviewer_budget()` in `src/reviewgraph/context_budget.py` already supports live-call costs and deterministic live-call deferral.
- `parse_reviewer_config()` in `src/reviewgraph/config.py` already accepts reviewer `model`, inert `tools`, `context`, and `context_budget.max_live_calls`.
- Existing tests cover provider preview redaction, context package boundaries, redaction, and context-budget live-call caps, but there is no explicit `llm_policy` module that future live adapters must pass through.

## Plan

1. Add focused tests in `tests/test_llm_policy.py` that define the guardrail contract before implementation:
   - live mode requires explicit run-level opt-in;
   - provider and model are required for live-ready requests;
   - fake/default mode is not live-ready even when reviewer config contains a model;
   - opt-in truth table: no opt-in, config model only, live opt-in without provider, live opt-in without model, raw provider requested without raw-provider opt-in, raw trace requested without raw-trace opt-in, and passing redacted request;
   - provider-bound request is built from `ReviewerContextPackage` and is redacted by default;
   - raw provider submission and raw trace persistence are separately gated and recorded;
   - live-call budget cost is explicit and rejected/deferred when `max_live_calls=0`, cumulative planned calls would exceed the cap, or multiple reviewers would exceed a positive cap;
   - budget reservation is stateful: a cap of `1` with two live reviewer policy attempts passes the first, returns a ledger with one reserved call, and blocks/deferred the second before any provider execution plan can be used;
   - guardrail output records provider, model, reviewer, canonical target fields, target hash, context policy, retained file paths, retained memory IDs, omitted context IDs/reasons, truncation notices, redaction status, raw flags, opt-in proof, and budget cost;
   - default policy result serialization omits full provider request text and private PR content while retaining hashes, byte counts, context inventory, redaction categories, and raw opt-in proof;
   - provider failure summaries redact token-like text and expose stable reason codes for missing credentials, timeout, rate limit, malformed response, unavailable provider, and unknown provider error;
   - a fixture with token-like PR title/body/diff/review/comment data flows through the exact policy result serialization without leaking the token fragments by default;
   - no provider client, network transport, GitHub transport, approval/finalization, posting, or writer module is imported.
2. Implement `src/reviewgraph/llm_policy.py` as a pure policy/preview module:
   - typed policy input, run-level budget ledger/reservation, provider execution plan, blocked result, public audit record, and redacted provider failure dataclasses if existing models are not sufficient;
   - pure functions that evaluate opt-in, provider/model requirements, context package preview, redaction, raw opt-ins, live-call budget cost, and run-level reservation updates;
   - stable blocked reason codes such as `missing_live_opt_in`, `missing_provider`, `missing_model`, `live_call_budget_exceeded`, `raw_provider_not_approved`, and `raw_trace_not_approved`;
   - stable provider failure reason codes including `missing_credentials`, `timeout`, `rate_limited`, `retry_exhausted`, `malformed_response`, `provider_unavailable`, and `unknown_provider_error`;
   - a default-safe audit serialization method that excludes request text unless raw trace persistence is approved and otherwise records only hashes, byte counts, context inventory, redaction summaries, raw opt-in proof, and reason/status fields;
   - no SDK/network/provider execution behavior.
3. Define the persistence boundary in docs/tests for AUR-212:
   - `llm_policy` owns serializable per-reviewer policy audit records now;
   - AUR-240/AUR-232 own attaching those records to `ReviewState` or `ReviewerResult` when live adapters are wired;
   - until adapter wiring exists, AUR-212 proves the exact default audit JSON shape and keeps it free of full request text/private PR content.
4. Add boundary checks so `llm_policy` stays import-safe and default-safe.
5. Update narrow docs only if needed:
   - `docs/architecture/llm-data-handling.md` for policy result shape;
   - `docs/harnesses/harness-engineering.md` if the focused harness should be named under Live LLM discipline.
6. Run focused and regression validation.
7. Use fresh subagents for code/docs review until no material findings remain.
8. Commit implementation and review-fix batches separately, then update Linear with evidence.

## Focused Harness

```bash
.venv/bin/python -m pytest tests/test_llm_policy.py -q
```

## Regression Harness

```bash
.venv/bin/python -m pytest tests/test_config.py tests/test_reviewer_context.py tests/test_redaction.py tests/test_context_budget.py tests/test_contract_boundaries.py -q
.venv/bin/python -m pytest tests/test_reviewers_fake.py tests/test_cli.py -q
.venv/bin/python -m py_compile src/reviewgraph/*.py
.venv/bin/python scripts/check_docs.py
git diff --check
```

## Acceptance Mapping

- Live LLM requires explicit opt-in -> policy tests for missing opt-in and config metadata alone.
- Provider/model/reviewer/target/context/truncation recorded -> policy result serialization/assertions.
- Fake reviewers remain default -> existing fake reviewer tests plus new guardrail default-mode tests.
- Redaction covers provider-bound requests and default output surfaces -> provider preview/redaction tests plus existing redaction regressions.
- Provider-bound live request payloads minimized/redacted -> request preview built from `ReviewerContextPackage` only.
- Live-call caps enforced -> policy/budget tests with `max_live_calls=0`, cumulative planned calls, positive-cap multi-reviewer cases, and returned reservation ledger reuse.
- Default-safe recording -> policy audit serialization tests prove request text/private PR content is excluded while audit hashes/sizes/context inventory are retained.
- Provider failures redacted -> typed provider failure summary tests with token-like error text.

## Out Of Scope

- Provider SDK calls.
- Live LLM smoke execution.
- CLI `--live-llm` surface and provider/config resolution. AUR-212 defines the policy input shape; AUR-240 wires user-facing opt-in and adapter behavior.
- Tool-using agents.
- Reviewer-agent repository checkout or project test execution.
- Changes to GitHub write/read behavior.
