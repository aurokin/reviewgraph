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

Add deterministic live LLM data-handling guardrails before any live provider adapter exists. The implementation should make it impossible for a future live adapter to skip explicit opt-in, provider/model disclosure, redacted provider-bound request construction, raw-provider/raw-trace opt-in separation, and live-call budget accounting.

## Contracts To Preserve

- Fake reviewers remain default for tests and normal dry-runs.
- Config metadata such as `model` or inert `tools` cannot trigger a live provider call.
- Provider-bound request data must come from `ReviewerContextPackage`, not raw PR objects, full config maps, GitHub transports, side-effect state, or ambient process state.
- Provider-bound request text is minimized and redacted by default.
- Raw provider submission and raw trace persistence are separate explicit choices.
- Live-call caps are enforced before provider execution.
- Default tests cannot call live providers, require credentials, write GitHub, or require human input.

## Current Code Context

- `build_provider_request_preview()` in `src/reviewgraph/reviewer_context.py` already serializes prompt input, applies provider-bound redaction, and records provider/model/reviewer/target/raw flags.
- `redact_provider_bound_text()` and `redact_trace_data()` in `src/reviewgraph/redaction.py` already separate raw provider submission from raw trace persistence.
- `apply_reviewer_budget()` in `src/reviewgraph/context_budget.py` already supports live-call costs and deterministic live-call deferral.
- `parse_reviewer_config()` in `src/reviewgraph/config.py` already accepts reviewer `model`, inert `tools`, `context`, and `context_budget.max_live_calls`.
- Existing tests cover provider preview redaction, context package boundaries, redaction, and context-budget live-call caps, but there is no explicit `llm_policy` module that future live adapters must pass through.

## Plan

1. Add focused tests in `tests/test_llm_policy.py` that define the guardrail contract before implementation:
   - live mode requires explicit opt-in;
   - provider and model are required for live-ready requests;
   - fake/default mode is not live-ready even when reviewer config contains a model;
   - provider-bound request is built from `ReviewerContextPackage` and is redacted by default;
   - raw provider submission and raw trace persistence are separately recorded;
   - live-call budget cost is explicit and rejected/deferred when `max_live_calls=0`;
   - guardrail output records provider, model, reviewer, target hash, context policy, truncation status, redaction status, and budget cost;
   - no provider client, network transport, GitHub transport, approval/finalization, posting, or writer module is imported.
2. Implement `src/reviewgraph/llm_policy.py` as a pure policy/preview module:
   - typed request/policy result dataclasses if existing models are not sufficient;
   - pure functions that evaluate opt-in, provider/model requirements, context package preview, redaction, raw opt-ins, and live-call budget cost;
   - no SDK/network/provider execution behavior.
3. Add boundary checks so `llm_policy` stays import-safe and default-safe.
4. Update narrow docs only if needed:
   - `docs/architecture/llm-data-handling.md` for policy result shape;
   - `docs/harnesses/harness-engineering.md` if the focused harness should be named under Live LLM discipline.
5. Run focused and regression validation.
6. Use fresh subagents for code/docs review until no material findings remain.
7. Commit implementation and review-fix batches separately, then update Linear with evidence.

## Focused Harness

```bash
.venv/bin/python -m pytest tests/test_llm_policy.py -q
```

## Regression Harness

```bash
.venv/bin/python -m pytest tests/test_reviewer_context.py tests/test_redaction.py tests/test_context_budget.py tests/test_contract_boundaries.py -q
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
- Live-call caps enforced -> policy/budget test with `max_live_calls=0` and cost `1`.

## Out Of Scope

- Provider SDK calls.
- Live LLM smoke execution.
- CLI `--live-llm` surface unless needed as a non-executing validation placeholder.
- Tool-using agents.
- Repository checkout or test execution.
- Changes to GitHub write/read behavior.
