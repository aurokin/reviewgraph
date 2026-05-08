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
- Config model metadata alone cannot call a live provider. A config opt-in must be a distinct `live_llm.enabled=true` run setting, not a reviewer `model` field.
- Live execution requires run-level explicit opt-in, provider, model, an approved `LiveLLMPolicyResult`, and the exact current live-call ledger reservation proof.
- Provider-bound request text is built only by `llm_policy` from `ReviewerContextPackage`.
- The live adapter receives no GitHub transports, approval/finalization state, posting payload builders, writer clients, shell handles, or ambient network/session clients.
- Provider transport is injected into the adapter. The core adapter module must not import provider SDKs, `requests`, shell/process modules, `gh`, or construct ambient network clients. A separately imported opt-in HTTP transport may perform a real provider call only from live CLI/smoke paths.
- Provider/model/reviewer/target/context/truncation/redaction/budget metadata is recorded in a typed, redacted `LiveLLMReviewerEvidence` field on `ReviewerResult` and in policy audit data. Do not stuff provider evidence into free-form `errors` or unredacted `raw_output`.
- Raw provider response text is never persisted by default. Successful live output may retain only redacted parsed reviewer output as `ReviewerResult.raw_output`; live evidence records response hash, byte count, request ID, attempts, and response redaction status. Full raw response persistence is deferred until raw-trace opt-in has a typed policy.
- Provider timeout, retry exhaustion, rate limit, outage, malformed response, and missing credentials map to failed `ReviewerResult` values. Required/optional reviewer semantics remain owned by existing runner policy and must be proven for live failures.
- Live retry is graph-visible. The provider adapter performs one transport attempt for one approved policy result. A live reviewer attempt runner may schedule a bounded retry by creating a new `ReviewerRunKey.attempt` with `retry_of`, re-running policy, and consuming a fresh ledger reservation.
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
   - missing credentials, timeout, rate limit, provider outage, and retry exhaustion produce redacted typed failure evidence and failed `ReviewerResult`;
   - retryable provider failures are retried only by the graph-visible live attempt runner, up to the configured cap, with `ReviewerRunKey.attempt` and `retry_of` recorded;
   - required live reviewer failure becomes the same fail-closed graph error/local note shape as required fake reviewer failure, while optional live reviewer failure remains a partial local review;
   - default adapter tests do not require credentials, network, or live provider calls;
   - the `live_llm` smoke test is marked and skipped by default through `tests/conftest.py`, with a collection/default-skip assertion.
2. Add `src/reviewgraph/llm.py`:
   - define provider request/response dataclasses and a `LiveLLMProviderTransport` protocol/callable contract;
   - define a deterministic fake provider transport for tests;
   - implement `execute_live_llm_reviewer_attempt(...)` that validates the AUR-232 live policy adapter boundary, calls only the injected transport once, normalizes provider JSON into `ReviewerResult`, and maps provider failures with `summarize_provider_failure`;
   - implement `run_live_llm_reviewer_with_retries(...)` as graph-visible orchestration: default `max_attempts=2`, default `timeout_seconds=30`, each retry gets a distinct run key and policy reservation, and retry stops on non-retryable failure or success.
3. Add typed live evidence to the result contract:
   - add `LiveLLMReviewerEvidence` to `src/reviewgraph/models.py`;
   - add `live_llm_evidence: LiveLLMReviewerEvidence | None` to `ReviewerResult`;
   - update runner JSON serialization to include redacted live evidence without exposing raw request/response text.
4. Refactor only the smallest shared reviewer-output normalization helper from `src/reviewgraph/reviewers.py` if needed so fake and live adapters share the output contract without duplicating normalization policy.
5. Add explicit CLI/config opt-in surface:
   - add `--live-llm`, `--live-llm-provider`, and `--live-llm-model`;
   - add a distinct optional config object such as `live_llm.enabled`, `live_llm.provider`, `live_llm.model`, `live_llm.max_attempts`, and `live_llm.timeout_seconds`;
   - fail closed if live is requested without provider or model;
   - keep normal dry-run default fake-only;
   - implement an actual opt-in live transport path for the smoke test. Prefer an OpenAI-compatible HTTP transport isolated behind dynamic import/live path so default imports do not load network code or require credentials.
6. Add `live_llm` pytest marker to `pyproject.toml` and update `tests/conftest.py` to skip it unless `REVIEWGRAPH_LIVE_LLM=1`.
7. Broaden redaction validation:
   - assert live request/evidence/default JSON/JSON errors/rendered markdown/candidate payloads remain redacted;
   - include posting/render/payload-validation regression tests when live evidence touches serialized output.
8. Update narrow docs:
   - `docs/architecture/llm-data-handling.md` for live adapter opt-in, injected transport, audit/result evidence, and failure mapping;
   - `docs/architecture/state-graph.md` if runner/live adapter state changes;
   - `docs/harnesses/harness-engineering.md` for AUR-240 harness and skipped smoke discipline;
   - `README.md` if the current runnable slice/status changes.
9. Run focused and regression validation.
10. Use fresh subagents for plan review before implementation and code/docs review after implementation until no material findings remain.
11. Commit the plan before implementation, then commit implementation and any review-fix batches separately, then update Linear with evidence.

## Focused Harness

```bash
.venv/bin/python -m pytest tests/test_live_llm_adapter.py -q
```

## Regression Harness

```bash
.venv/bin/python -m pytest tests/test_live_llm_adapter.py tests/test_llm_policy.py tests/test_adapter_boundaries.py -q
.venv/bin/python -m pytest tests/test_reviewers_fake.py tests/test_reviewer_json_repair.py -q
.venv/bin/python -m pytest tests/test_config.py tests/test_context_budget.py tests/test_reviewer_context.py tests/test_redaction.py -q
.venv/bin/python -m pytest tests/test_cli.py tests/test_tracer_fixture_run.py tests/test_render.py tests/test_posting.py tests/test_payload_validation.py -q
.venv/bin/python -m py_compile src/reviewgraph/*.py
.venv/bin/python scripts/check_docs.py
git diff --check
```

## Acceptance Mapping

- Fake reviewer default -> default runner/CLI tests plus live adapter tests proving config model alone stays fake.
- Explicit opt-in -> CLI/config validation and policy-input tests requiring explicit live opt-in source, provider, and model.
- Recorded provider/model/reviewer/target/context/truncation/redaction -> policy audit assertions and typed `LiveLLMReviewerEvidence` assertions in default JSON.
- Minimized/redacted provider payload -> approved policy request assertions plus no-secret checks for request/evidence/default JSON/rendered markdown/candidate payloads/JSON errors.
- Timeout/retry/rate-limit/outage mapping -> fake transport failure tests with graph-visible bounded attempt keys and `ReviewerResult(status=FAILED)`.
- Required/optional live failure semantics -> runner tests proving required live failures fail closed while optional live failures stay partial/local.
- Live smoke skipped by default -> `pytest.mark.live_llm` plus `tests/conftest.py` skip unless `REVIEWGRAPH_LIVE_LLM=1`.

## Out Of Scope

- Provider SDK dependencies.
- Tool-using agents.
- Repository checkout.
- Running repository tests from a reviewer.
- Public production posting.
- Provider-specific prompt tuning.
- Persisting raw provider request/response bodies by default.
