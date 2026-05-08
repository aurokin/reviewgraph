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
- Config model metadata alone cannot call a live provider. Config may provide live defaults such as provider/model/timeouts, but public CLI execution must still receive `--live-llm` to create the run-level opt-in source before PR content can be sent to a provider. Any config-only live execution path fails closed unless a non-CLI caller supplies an equivalent explicit run-level opt-in source.
- Live execution requires run-level explicit opt-in, provider, model, an approved `LiveLLMPolicyResult`, and the exact current live-call ledger reservation proof.
- Live ledger and policy audit state are graph-owned. Add explicit `ReviewState` fields for redacted live LLM ledger state and policy audit records, plus default JSON output fields, so reservations and policy decisions are inspectable rather than hidden in helper locals.
- Provider-bound request text is built only by `llm_policy` from `ReviewerContextPackage`.
- The live adapter receives no GitHub transports, approval/finalization state, posting payload builders, writer clients, shell handles, or ambient network/session clients.
- Provider transport is injected into the adapter. The core adapter module must not import provider SDKs, `requests`, shell/process modules, `gh`, or construct ambient network clients. A separately imported opt-in HTTP transport may perform a real provider call only from live CLI/smoke paths.
- Provider/model/reviewer/target/context/truncation/redaction/budget metadata is recorded in a typed, redacted `LiveLLMReviewerEvidence` field on `ReviewerResult` and in policy audit data. Do not stuff provider evidence into free-form `errors` or unredacted `raw_output`.
- Raw provider response text is never persisted by default. Successful live output may retain only redacted parsed reviewer output as `ReviewerResult.raw_output`; live evidence records response hash, byte count, request ID, attempts, and response redaction status. Full raw response persistence is deferred until raw-trace opt-in has a typed policy.
- Provider timeout, retry exhaustion, rate limit, outage, malformed response, and missing credentials map to failed `ReviewerResult` values. Required/optional reviewer semantics remain owned by existing runner policy and must be proven for live failures.
- Live retry is graph-visible. The provider adapter performs one transport attempt for one approved policy result. A live reviewer attempt runner may schedule a bounded retry by creating a new `ReviewerRunKey.attempt` with `retry_of`, re-running policy, consuming a fresh ledger reservation, and appending each attempt to graph-owned `reviewer_run_keys`, `reviewer_run_status`, and `reviewer_results`. Classification uses only the successful final attempt; failed prior attempts remain evidence/status, not classified output.
- Resolved live settings participate in idempotency. Provider, model, timeout, max attempts, max live calls, and their CLI/env/config precedence-resolved values must be represented in the config/run contract and included in the existing `config_hash` path so run keys and live reservations cannot be reused across changed live settings.
- Live execution-mode selection is deterministic for this slice: public `--live-llm` attempts live execution for every selected reviewer retained by budget. There is no mixed fake/live per-reviewer mode in AUR-240. Effective model resolution is CLI model, then live config model, then reviewer config model; missing effective model fails closed before provider execution.
- Live-call budget is an admission cap over worst-case attempts and the policy ledger is the actual per-attempt reservation cap. With `max_attempts=2` and `max_live_calls=1`, the selected live reviewer is deferred before any provider call; users must set enough live-call budget for `selected_live_reviewers * max_attempts`.
- Live smoke tests are marked `live_llm` and skipped unless `REVIEWGRAPH_LIVE_LLM=1`.

## Current Code Context

- `src/reviewgraph/llm_policy.py` approves or blocks provider-bound execution plans, redacts provider-bound request text by default, reserves live-call budget, records audit metadata, and summarizes provider failures.
- `src/reviewgraph/reviewer_boundaries.py` validates `ReviewerContextPackage`, `ReviewerRunKey`, stage/reviewer/target binding, and read-only capability policy.
- `src/reviewgraph/reviewers.py` has `execute_fake_reviewer`, `validate_live_policy_adapter_input`, and a provider-free `execute_live_policy_reviewer_stub`.
- `src/reviewgraph/runner.py` always executes fake reviewers today; it already has reviewer-budget hooks for `live_call_costs` but does not pass costs because no live execution mode exists.
- `src/reviewgraph/cli.py` has no live LLM flags yet. Public CLI currently exposes fixture and fake GitHub dry-run paths only.
- `pyproject.toml` has `live_read` and `live_post` markers but no `live_llm` marker.
- `tests/conftest.py` skips `live_read` and `live_post`, but not `live_llm`; adding the marker alone is insufficient.

## Plan

1. Add `tests/test_live_llm_adapter.py` first:
   - fake reviewers remain default when config includes `model`;
   - live adapter execution requires approved policy result plus current ledger proof;
   - fake provider transport receives exactly the approved policy request text, provider, model, reviewer, target hash, request hash, timeout, and attempt metadata;
   - live adapter evidence is typed, redacted, serializable, and separate from provider `raw_output`;
   - successful provider JSON becomes a `ReviewerResult` with normalized findings/local notes/clarifications/suggested replies/suppressed outputs;
   - successful provider raw response text is not retained; only the redacted parsed reviewer output, response hash, byte count, request ID, and redaction status are retained;
   - malformed JSON/invalid schema becomes a failed `ReviewerResult` with redacted typed evidence;
   - live malformed JSON is not repaired in AUR-240; no hidden repair LLM call or fake repair envelope is attempted;
   - missing credentials, timeout, rate limit, provider outage, and retry exhaustion produce redacted typed failure evidence and failed `ReviewerResult`;
   - retryable provider failures are retried only by the graph-visible live attempt runner, up to the configured cap, with every attempt recorded in `reviewer_run_keys`, `reviewer_run_status`, and `reviewer_results`;
   - required live reviewer failure becomes the same fail-closed graph error/local note shape as required fake reviewer failure, while optional live reviewer failure remains a partial local review;
   - changed resolved live settings from CLI/env/config precedence change `config_hash` and therefore reviewer run keys/reservation identities;
   - live-call budget costs selected live reviewers before execution using worst-case `max_attempts`; default `max_live_calls=0` blocks live execution unless config/CLI explicitly raises it;
   - default adapter tests do not require credentials, network, or live provider calls;
   - the `live_llm` smoke test is marked and skipped by default through `tests/conftest.py`, with a collection/default-skip assertion.
2. Add `src/reviewgraph/llm.py`:
   - define provider request/response dataclasses and a `LiveLLMProviderTransport` protocol/callable contract;
   - define a deterministic fake provider transport for tests;
   - implement `execute_live_llm_reviewer_attempt(...)` that validates the AUR-232 live policy adapter boundary, calls only the injected transport once, normalizes provider JSON into `ReviewerResult`, and maps provider failures with `summarize_provider_failure`;
   - implement `run_live_llm_reviewer_with_retries(...)` as graph-visible orchestration: default `max_attempts=2`, default `timeout_seconds=30`, optional total-time cap, no hidden transport retries, each retry gets a distinct run key and policy reservation, each attempt is returned for graph status/result recording, and retry stops on non-retryable failure or success.
3. Add typed live evidence to the result contract:
   - add `LiveLLMReviewerEvidence` to `src/reviewgraph/models.py`;
   - add `live_llm_evidence: LiveLLMReviewerEvidence | None` to `ReviewerResult`;
   - add graph-owned live LLM state fields to `ReviewState`, using leaf-safe summary types or redacted serializable dictionaries to avoid importing `llm_policy` into `models.py`;
   - update runner JSON serialization to include redacted live evidence, live ledger summary, and policy audit records without exposing raw request/response text.
4. Refactor only the smallest shared reviewer-output normalization helper from `src/reviewgraph/reviewers.py` if needed so fake and live adapters share the output contract without duplicating normalization policy.
5. Add explicit CLI/config opt-in surface without breaking default import fences:
   - add `--live-llm`, `--live-llm-provider`, and `--live-llm-model`;
   - add `--live-llm-max-calls` if needed to raise the default zero live-call cap explicitly;
   - add a distinct optional config object such as `live_llm.provider`, `live_llm.model`, `live_llm.max_attempts`, `live_llm.timeout_seconds`, and `live_llm.max_live_calls`; if an `enabled` field is accepted, it cannot bypass the public CLI `--live-llm` requirement;
   - fail closed if live is requested without provider, model, or positive live-call budget;
   - keep normal dry-run default fake-only;
   - implement an actual opt-in live transport path for the smoke test. Prefer an OpenAI-compatible HTTP transport in a separate live-only module and import it lazily/dynamically only inside the `--live-llm`/smoke path so importing or running default `reviewgraph.cli` and `reviewgraph.runner` cannot load `reviewgraph.llm` or network/provider modules.
   - define smoke prerequisites exactly: `REVIEWGRAPH_LIVE_LLM=1`, `REVIEWGRAPH_LIVE_LLM_PROVIDER`, `REVIEWGRAPH_LIVE_LLM_MODEL`, `REVIEWGRAPH_LIVE_LLM_API_KEY` or provider-specific `OPENAI_API_KEY`, optional `REVIEWGRAPH_LIVE_LLM_BASE_URL`, and redacted artifact output. When the marker is enabled but provider/model/key is missing, the smoke returns/asserts a blocked artifact with a stable reason and performs no provider call; only the marker being disabled skips collection.
6. Add `live_llm` pytest marker to `pyproject.toml` and update `tests/conftest.py` to skip it unless `REVIEWGRAPH_LIVE_LLM=1`.
7. Broaden redaction validation:
   - assert live request/evidence/default JSON/JSON errors/rendered markdown/candidate payloads, graph trace, policy audit/log-like artifacts, and final payload harnesses remain redacted;
   - assert raw provider response text never appears in `raw_output`, `errors`, `repair_record`, local notes, graph trace, default JSON, rendered markdown, candidate payloads, or final payloads;
   - include posting/render/payload-validation/final-payload regression tests when live evidence or live findings touch serialized output.
   - include trace events for live policy blocked, live reservation created/reused/conflicted, provider attempt started/failed/succeeded, retry scheduled, retry exhausted, and live budget exhausted; trace payloads must be redacted and default-safe.
8. Add boundary tests for the new live modules:
   - `src/reviewgraph/llm.py` imports no GitHub read/write, approval/finalization/posting/writer modules, provider SDKs, `requests`, shell/process modules, or ambient clients;
   - default `reviewgraph.cli` and `reviewgraph.runner` imports do not transitively load `reviewgraph.llm`, live HTTP transports, provider SDKs, or network modules;
   - live-only HTTP transport imports are isolated to explicit opt-in paths.
9. Update narrow docs:
   - `docs/architecture/llm-data-handling.md` for live adapter opt-in, injected transport, audit/result evidence, and failure mapping;
   - `docs/architecture/state-graph.md` if runner/live adapter state changes;
   - `docs/harnesses/harness-engineering.md` for AUR-240 harness and skipped smoke discipline;
   - `README.md` if the current runnable slice/status changes.
10. Run focused and regression validation.
11. Use fresh subagents for plan review before implementation and code/docs review after implementation until no material findings remain.
12. Commit the plan before implementation, then commit implementation and any review-fix batches separately, then update Linear with evidence.

## Focused Harness

```bash
.venv/bin/python -m pytest tests/test_live_llm_adapter.py -q
```

## Regression Harness

```bash
.venv/bin/python -m pytest tests/test_live_llm_adapter.py tests/test_llm_policy.py tests/test_adapter_boundaries.py -q
.venv/bin/python -m pytest tests/test_reviewers_fake.py tests/test_reviewer_json_repair.py -q
.venv/bin/python -m pytest tests/test_config.py tests/test_context_budget.py tests/test_reviewer_context.py tests/test_redaction.py -q
.venv/bin/python -m pytest tests/test_cli.py tests/test_tracer_fixture_run.py tests/test_render.py tests/test_posting.py tests/test_payload_validation.py tests/test_payload_hashes.py -q
.venv/bin/python -m py_compile src/reviewgraph/*.py
.venv/bin/python scripts/check_docs.py
git diff --check
```

## Acceptance Mapping

- Fake reviewer default -> default runner/CLI tests plus live adapter tests proving config model alone stays fake.
- Explicit opt-in -> CLI/config validation and policy-input tests requiring explicit run-level live opt-in source, provider, model, and positive live-call budget; config-only defaults cannot bypass `--live-llm` in public CLI.
- Recorded provider/model/reviewer/target/context/truncation/redaction -> policy audit assertions and typed `LiveLLMReviewerEvidence` assertions in default JSON.
- Graph-owned live state -> tests proving `ReviewState` and default JSON expose redacted live ledger summaries, policy audit records, and trace events for each policy/attempt path.
- Minimized/redacted provider payload -> approved policy request assertions plus no-secret checks for request/evidence/default JSON/rendered markdown/candidate payloads/final payloads/graph trace/policy audit/JSON errors.
- Timeout/retry/rate-limit/outage mapping -> fake transport failure tests with graph-visible bounded attempt keys, per-attempt result/status evidence, and `ReviewerResult(status=FAILED)`.
- Required/optional live failure semantics -> runner tests proving required live failures fail closed while optional live failures stay partial/local.
- Budget/idempotency -> tests proving live settings affect `config_hash`, selected live reviewers are budgeted by worst-case `max_attempts`, and zero/insufficient `max_live_calls` blocks before provider execution.
- Import boundaries -> tests proving `llm.py` imports no GitHub/write/provider-network/process modules, default `reviewgraph.cli` and `reviewgraph.runner` imports do not transitively load live LLM or HTTP transport modules, and live HTTP transport imports occur only in explicit opt-in paths.
- Live selection semantics -> tests proving `--live-llm` applies to all selected retained reviewers for this slice, model resolution is deterministic, and missing effective model fails closed before provider execution.
- Malformed live output -> tests proving malformed/invalid provider output fails without repair and no second repair provider call occurs.
- Live smoke skipped by default -> `pytest.mark.live_llm` plus `tests/conftest.py` skip unless `REVIEWGRAPH_LIVE_LLM=1`.

## Out Of Scope

- Provider SDK dependencies.
- Tool-using agents.
- Repository checkout.
- Running repository tests from a reviewer.
- Public production posting.
- Provider-specific prompt tuning.
- Persisting raw provider request/response bodies by default.
