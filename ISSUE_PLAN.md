# ISSUE PLAN: AUR-231 Define Reviewer Context Package

Active issue plan for `AUR-231` / `RG-042: Define Reviewer Context Package`.

## Linear Snapshot

- Issue: `AUR-231`
- Status: `In Progress`
- Milestone: `PRD 0010: Agent Context And Adapter Boundaries`
- Linear acceptance:
  - Context package includes review target, active stage, selected reviewer metadata, bounded diff context, trusted memory references, optional passive memory references, and truncation notes.
  - Context package records reviewer config fields: model, tools, context policy, capabilities, and verdict power.
  - Untrusted memory is labeled as passive data and cannot appear as instruction text.
  - Context package traces include included memory IDs, trust labels, resolved status, and truncation status.
  - MVP capabilities default to `diff_context`, with GitHub writes unavailable.
- Linear comment context: PRD 0003 only delivered the minimal `AUR-211` context-budget stub. This issue owns the fuller context package contract, passive-memory instruction boundary, traces, capability policy, and adapter-boundary details.

## Goal

Define a reviewer context package contract that future fake/live reviewer adapters can consume without ambient GitHub, approval, writer, payload-builder, repository, process, or provider access.

This issue should not implement reviewer adapter execution, live LLM calls, GitHub reads/writes, repository checkout access, approval/finalization flows, or tool execution. It should produce typed contracts and deterministic harnesses that make those future boundaries hard to violate.

## Design Decisions For This Slice

- `tools` become inert validated metadata. A reviewer config may name future tool identifiers as conservative non-empty slugs, but this does not grant any capability, call budget, callable handle, provider tool schema, process access, repository access, GitHub access, provider access, or write behavior.
- Capability policy is explicit and read-only. MVP supports `none` and `diff_context`; `github_write` is unavailable and must not be representable as a reviewer capability.
- Prompt inputs must separate instruction fields from context data fields. Memory bodies may appear only as labeled data. Passive/untrusted memory bodies must never appear in system/developer instructions.
- Passive memory may be included as explicitly labeled data or represented as excluded/passive metadata; either way, it cannot route reviewers, satisfy evidence, change verdicts, approve posting, or enter public payloads.
- Provider-bound request preview is non-live. It should build the minimized/redacted context data a later LLM adapter would send, prove default raw-provider/raw-trace-off policy, and have no network/client dependency. It must not invent provider identity from reviewer config; provider is absent/unconfigured unless a future live caller explicitly supplies one.

## Prompt-To-Artifact Checklist

- Context package fields:
  - `src/reviewgraph/reviewer_context.py`
  - `tests/test_reviewer_context.py`
- Reviewer config metadata:
  - `ReviewerAgentConfig.tools` or equivalent inert metadata in `src/reviewgraph/models.py`
  - `parse_reviewer_config` tool validation in `src/reviewgraph/config.py`
  - `tests/test_config.py`
- Prompt input contract:
  - `ReviewerPromptInput` or equivalent in `src/reviewgraph/reviewer_context.py`
  - golden tests proving instruction/data separation
- Provider-bound preview contract:
  - non-live provider request model/builder in `src/reviewgraph/reviewer_context.py` or a narrowly named prompt/context module
  - tests proving minimized/redacted provider-bound payloads, redaction status, `raw_provider_submission_enabled=False`, `raw_trace_persistence_enabled=False`, and no invented provider identity by default
- Trace contract:
  - included memory IDs, trust labels, resolved status, passive/actionable state, truncation status, omitted-context IDs, config metadata, and capability policy
- Boundary proof:
  - `tests/test_contract_boundaries.py`
  - AST import tests for context/prompt modules
  - field/signature tests preventing writer/client/approval/payload/LLM handles from entering package or prompt builders
- Routing regression:
  - existing conversation-pattern tests in `tests/test_cli.py` or a focused extraction
  - prove only trusted actionable memory selects reviewers
- Passive-memory negative regressions:
  - prove passive/untrusted memory copied into fake reviewer evidence cannot become postable/public text
  - prove passive/untrusted memory cannot change the local verdict or create approval/posting inputs in this slice
- Docs:
  - update the narrowest durable docs for reviewer context package fields, inert tools metadata, prompt input separation, provider-bound preview, and boundary proof

## Implementation Plan

1. Add focused failing tests in `tests/test_reviewer_context.py` for:
   - package includes review target, active stage, selected reviewer, reviewer config metadata, bounded changed files, trusted actionable memory, passive memory/exclusion metadata, truncation notices, omitted context, and local budget notes.
   - context trace serializes memory IDs, trust labels, resolved status, actionable/passive state, truncation notices, omitted context, capabilities, model, tools, context policy, required flag, and verdict power.
   - prompt inputs keep instructions separate from data, and `untrusted-comment-injection` prompt-like bodies never appear in instruction fields.
   - provider-bound preview redacts secret-like fixture text, records model/reviewer/target/context policy/truncation/redaction status, records provider as absent/unconfigured by default, minimizes to package data, and records both `raw_provider_submission_enabled=False` and `raw_trace_persistence_enabled=False`.
2. Extend config/model tests:
   - accept omitted `tools` as `()`.
   - accept `tools: ["future-search"]` as inert metadata.
   - reject empty, non-string, duplicate, URL-like, dotted module-like, shell-like, or otherwise non-slug tool identifiers.
   - preserve existing rejection of unsupported capabilities such as `read_repo` and `github_write`.
3. Implement minimal contract models/builders:
   - add tool metadata to `ReviewerAgentConfig`.
   - add capability policy/context metadata types if needed.
   - expand `ReviewerContextPackage`.
   - add prompt-input and provider-preview builders with redaction/minimization.
4. Update `build_reviewer_context_package` so callers pass only the selected `ReviewerAgentConfig` or a narrowed immutable selected-reviewer metadata object. Do not allow the full config map into package, prompt, or provider-preview builders.
5. Add boundary tests:
   - context/prompt modules do not import forbidden side-effect roots/modules.
   - package/prompt/provider-preview dataclass fields and builder signatures do not accept side-effect handles such as writer, client, transport, approval, payload, finalization, github, llm, openai, request/session, process, or subprocess objects.
6. Add passive-memory negative tests without implementing approval/writer flows:
   - a fake reviewer output that copies an untrusted/passive memory body into finding evidence is suppressed or downgraded before any candidate payload.
   - local verdict remains driven by graph-classified findings, not passive memory.
   - no approval/final payload input is created from passive memory.
7. Add inert-tools negative tests:
   - tool names appear only as metadata in package/trace/prompt data.
   - tool names do not become provider tool schemas, callable handles, added capabilities, live-call budget, or adapter dependencies.
8. Keep routing behavior unchanged, but run and preserve evidence for trusted/untrusted conversation-pattern coverage.
9. Update docs only where the contract becomes durable:
   - `docs/architecture/reviewer-config.md`
   - `docs/architecture/state-graph.md`
   - `docs/harnesses/harness-engineering.md`
   - add an ADR only if the inert tools or prompt-input shape needs a durable tradeoff record beyond existing docs.
10. Validate with focused and regression commands.

## Out Of Scope

- Live LLM adapter implementation.
- Network/provider calls.
- GitHub read or write adapters.
- Reviewer tool execution.
- Repository checkout or test execution by reviewers.
- Approval, finalization, or writer behavior.
- Automatic replies to PR comments.

## Validation Plan

Focused issue harness:

```bash
python -m pytest tests/test_reviewer_context.py tests/test_config.py tests/test_contract_boundaries.py
```

Routing and tracer regressions:

```bash
python -m pytest tests/test_cli.py tests/test_context_budget.py tests/test_memory.py tests/test_tracer_fixture_run.py tests/test_render.py tests/test_redaction.py
```

Full validation before completion:

```bash
python -m pytest
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Collect

- Acceptance-criteria mapping from Linear to tests/code/docs.
- Focused harness output.
- Routing/tracer regression output.
- Full validation output.
- Static boundary audit output.
- Subagent code/docs review with no material findings.
- Linear evidence comment before moving `AUR-231` to Done.
