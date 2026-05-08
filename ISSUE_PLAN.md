# ISSUE PLAN: AUR-240 Add Opt-In Live LLM Reviewer Adapter

Active issue plan for `AUR-240` / `RG-051: Add Opt-In Live LLM Reviewer Adapter`.

Linear is the durable source for status and acceptance criteria. Repository docs are the durable behavior contracts. This issue adds the first live reviewer adapter boundary and fake-provider harness; it must not add tool-using agents, repository checkout, test execution, or provider-specific prompt optimization.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0008: Live LLM`
- Issue: `AUR-240`
- Status when planned: `In Progress`
- Blocking issues: `AUR-212` and `AUR-232` are `Done`
- Linear handoff names likely files: `src/reviewgraph/llm.py`, `src/reviewgraph/reviewers.py`, `tests/test_live_llm_adapter.py`
- Focused harness from Linear: `python -m pytest tests/test_live_llm_adapter.py`; live smoke skipped by default
- Out of scope from Linear: tool-using agents and repository checkout

## Objective

Add the first live LLM reviewer adapter behind explicit opt-in, using `ReviewerContextPackage`, the AUR-212 live LLM policy result, the AUR-232 adapter boundary validator, and the same `ReviewerResult` output contract as fake reviewers.

The default behavior must remain fake reviewers, no credentials, no live provider calls, no GitHub writes, and no human input.

## Contracts To Preserve

- Fake reviewers remain the default for normal fixture/GitHub dry-runs and default tests.
- Config model metadata alone cannot call a live provider.
- Live execution requires run-level explicit opt-in, provider, model, an approved `LiveLLMPolicyResult`, and the exact current live-call ledger reservation proof.
- Provider-bound request text is built only by `llm_policy` from `ReviewerContextPackage`.
- The live adapter receives no GitHub transports, approval/finalization state, posting payload builders, writer clients, shell handles, or ambient network/session clients.
- Provider transport is injected into the adapter. The module must not import provider SDKs, `requests`, shell/process modules, or `gh`.
- Provider/model/reviewer/target/context/truncation/redaction/budget metadata is recorded on policy audit data and live adapter result evidence.
- Provider timeout, retry exhaustion, rate limit, outage, malformed response, and missing credentials map to failed `ReviewerResult` values. Required/optional reviewer semantics remain owned by existing runner policy.
- Live smoke tests are marked `live_llm` and skipped unless `REVIEWGRAPH_LIVE_LLM=1`.

## Current Code Context

- `src/reviewgraph/llm_policy.py` approves or blocks provider-bound execution plans, redacts provider-bound request text by default, reserves live-call budget, records audit metadata, and summarizes provider failures.
- `src/reviewgraph/reviewer_boundaries.py` validates `ReviewerContextPackage`, `ReviewerRunKey`, stage/reviewer/target binding, and read-only capability policy.
- `src/reviewgraph/reviewers.py` has `execute_fake_reviewer`, `validate_live_policy_adapter_input`, and a provider-free `execute_live_policy_reviewer_stub`.
- `src/reviewgraph/runner.py` always executes fake reviewers today; it already has reviewer-budget hooks for `live_call_costs` but does not pass costs because no live execution mode exists.
- `src/reviewgraph/cli.py` has no live LLM flags yet. Public CLI currently exposes fixture and fake GitHub dry-run paths only.
- `pyproject.toml` has `live_read` and `live_post` markers but no `live_llm` marker.

## Plan

1. Add `tests/test_live_llm_adapter.py` first:
   - fake reviewers remain default when config includes `model`;
   - live adapter execution requires approved policy result plus current ledger proof;
   - fake provider transport receives exactly the approved policy request text, provider, model, reviewer, target hash, request hash, timeout, and attempt metadata;
   - successful provider JSON becomes a `ReviewerResult` with normalized findings/local notes/clarifications/suggested replies/suppressed outputs;
   - malformed JSON/invalid schema becomes a failed `ReviewerResult`;
   - missing credentials, timeout, rate limit, provider outage, and retry exhaustion produce redacted typed failure evidence and failed `ReviewerResult`;
   - retryable provider failures are retried only up to the configured cap;
   - default adapter tests do not require credentials, network, or live provider calls;
   - the `live_llm` smoke test is marked and skipped by default.
2. Add `src/reviewgraph/llm.py`:
   - define provider request/response dataclasses and a `LiveLLMProviderTransport` protocol/callable contract;
   - define a deterministic fake provider transport for tests;
   - implement `execute_live_llm_reviewer(...)` that validates the AUR-232 live policy adapter boundary, calls only the injected transport, normalizes provider JSON into `ReviewerResult`, and maps provider failures with `summarize_provider_failure`;
   - implement bounded retry behavior for retryable provider failures, with stable reason codes and redacted evidence.
3. Refactor only the smallest shared reviewer-output normalization helper from `src/reviewgraph/reviewers.py` if needed so fake and live adapters share the output contract without duplicating normalization policy.
4. Add explicit CLI/config opt-in surface:
   - add `--live-llm`, `--live-llm-provider`, and `--live-llm-model`;
   - fail closed if live is requested without provider or model;
   - keep normal dry-run default fake-only;
   - if public CLI cannot safely provide a real transport in this slice, expose the live adapter through library/fake harnesses and make CLI live execution fail with a clear deferred-provider error before any provider call.
5. Add `live_llm` pytest marker to `pyproject.toml`.
6. Update narrow docs:
   - `docs/architecture/llm-data-handling.md` for live adapter opt-in, injected transport, audit/result evidence, and failure mapping;
   - `docs/architecture/state-graph.md` if runner/live adapter state changes;
   - `docs/harnesses/harness-engineering.md` for AUR-240 harness and skipped smoke discipline;
   - `README.md` if the current runnable slice/status changes.
7. Run focused and regression validation.
8. Use fresh subagents for plan review before implementation and code/docs review after implementation until no material findings remain.
9. Commit the plan before implementation, then commit implementation and any review-fix batches separately, then update Linear with evidence.

## Focused Harness

```bash
.venv/bin/python -m pytest tests/test_live_llm_adapter.py -q
```

## Regression Harness

```bash
.venv/bin/python -m pytest tests/test_live_llm_adapter.py tests/test_llm_policy.py tests/test_adapter_boundaries.py -q
.venv/bin/python -m pytest tests/test_reviewers_fake.py tests/test_reviewer_json_repair.py -q
.venv/bin/python -m pytest tests/test_config.py tests/test_context_budget.py tests/test_reviewer_context.py tests/test_redaction.py -q
.venv/bin/python -m pytest tests/test_cli.py tests/test_tracer_fixture_run.py -q
.venv/bin/python -m py_compile src/reviewgraph/*.py
.venv/bin/python scripts/check_docs.py
git diff --check
```

## Acceptance Mapping

- Fake reviewer default -> default runner/CLI tests plus live adapter tests proving config model alone stays fake.
- Explicit opt-in -> CLI arg validation and policy-input tests requiring `--live-llm`, provider, and model.
- Recorded provider/model/reviewer/target/context/truncation/redaction -> policy audit assertions and live adapter result evidence assertions.
- Minimized/redacted provider payload -> approved policy request assertions and no-secret serialization tests.
- Timeout/retry/rate-limit/outage mapping -> fake transport failure tests with bounded attempt counts and `ReviewerResult(status=FAILED)`.
- Live smoke skipped by default -> `pytest.mark.live_llm` test skipped unless `REVIEWGRAPH_LIVE_LLM=1`.

## Out Of Scope

- Real provider SDK integration.
- Tool-using agents.
- Repository checkout.
- Running repository tests from a reviewer.
- Public production posting.
- Provider-specific prompt tuning.
- Persisting raw provider request/response bodies by default.
