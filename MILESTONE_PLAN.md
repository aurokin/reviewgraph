# MILESTONE PLAN: PRD 0010 Agent Context And Adapter Boundaries

Active execution artifact for this milestone. Linear remains the durable source for issue status, milestone order, blockers, and handoff details; if this file conflicts with Linear, Linear wins. Re-fetch current Linear state before starting each issue.

## Linear Scope Snapshot

- Milestone: `PRD 0010: Agent Context And Adapter Boundaries`
- Milestone ID: `0dea2cdd-6433-41d8-b1a4-b91b07d3acc9`
- Current status: `AUR-231` complete; `AUR-233` active; `AUR-255` gate blocked until all PRD 0010 implementation issues are complete.
- Implementation issues:
  - `AUR-231` / `RG-042: Define Reviewer Context Package`
  - `AUR-233` / `RG-044: Add Prompt Injection Memory Harness`
- Gate issue:
  - `AUR-255` / `Complete PRD 0010: Agent Context And Adapter Boundaries`
- Current issue statuses:
  - `AUR-231`: `Done`
  - `AUR-233`: `In Progress`
  - `AUR-255`: `Backlog`
- Known Linear note: `AUR-231` has a PRD 0003 gate comment explaining that the existing `src/reviewgraph/reviewer_context.py` is only the minimal context-budget stub from `AUR-211`. The fuller reviewer context package contract remains valid PRD 0010 work.

## Milestone Intent

PRD 0010 makes reviewer agents explicit context boundaries. A reviewer should receive a scoped package of prompt inputs, bounded diff context, memory references, truncation state, selected-reviewer metadata, and capability policy. It should not receive GitHub transports, approval state, payload builders, finalization code, writer clients, or ambient process state.

The milestone also hardens the design point that PR conversation memory is shared data, not an instruction stream. Trusted actionable memory may help route reviewers when configured. Untrusted memory must remain passive in MVP: it cannot select reviewers, override prompts, satisfy evidence, influence verdicts, approve posting, or enter public payload text.

## Current Code Snapshot

- `src/reviewgraph/reviewer_context.py` now defines the post-`AUR-231` reviewer context package contract: review target, active stage, selected reviewer, changed files, trusted/passive memory references, truncation notices, omitted context, local notes, context budget, reviewer config metadata, read-only capability policy, trace metadata, prompt-input construction, and non-live provider request preview.
- `src/reviewgraph/models.py` has `ReviewTarget`, `SelectedReviewer`, `MemoryReference`, `ContextBudget`, `ReviewerAgentConfig`, `ReviewerResult`, raw/classified reviewer contracts, and inert `future-*` tool metadata validation. Keep graph-owned decisions out of reviewer output.
- `src/reviewgraph/config.py` validates optional `model`, inert `tools`, `context`, and `capabilities`. Tool names are recorded metadata only; they do not grant execution rights, live calls, GitHub access, repository access, or write capability.
- `src/reviewgraph/memory.py` already computes trusted/passive/actionable memory from typed PR context and allowlists.
- `src/reviewgraph/context_budget.py` already applies file, patch, memory, reviewer-count, and live-call budget decisions before reviewer execution and emits omitted-context markers/local notes.
- `src/reviewgraph/runner.py` still executes fixture raw outputs directly after routing; reviewer adapters are not implemented yet. PRD 0010 should not build live adapter execution, but it should make the package that future fake/live adapters receive testable.
- `tests/test_reviewer_context.py` and `tests/test_contract_boundaries.py` now carry the focused reviewer-context and adapter-boundary proof from `AUR-231`. `AUR-233` should add the missing named prompt-injection memory harness without redoing the AUR-231 contract.

## Execution Order

1. `AUR-231` first: define the full reviewer context package contract and harness. This should include:
   - review target
   - active stage
   - selected reviewer metadata
   - reviewer config metadata: model, tools/tool policy, context policy, capabilities, required flag, and verdict power
   - bounded diff context from the budgeted PR
   - trusted actionable memory references
   - passive memory references or explicit passive-memory exclusion metadata
   - truncation notices and omitted-context markers
   - capability policy that defaults to `diff_context` and disallows GitHub writes
   - trace data showing included memory IDs, trust labels, resolved status, passive/actionable state, and truncation status
   - prompt-input structure with separate instruction fields and data fields; memory bodies may appear only in labeled data fields, and passive/untrusted memory bodies must never appear in instruction fields
   - golden prompt-input tests using `untrusted-comment-injection` to prove prompt-like untrusted PR text remains passive data or explicit exclusion metadata
   - non-live provider request preview built from the context package, with minimized fields, redaction status, provider/model metadata, raw-provider submission disabled by default, and no network/client dependency
   - provider-bound golden tests proving secret-like fixture text is redacted and omitted/passive context remains governed before any later live LLM adapter can submit it
   - adapter-boundary tests proving reviewer context/prompt modules do not import or receive GitHub writer, approval, finalization, payload builder, live LLM, or transport clients
   - field/signature tests proving `ReviewerContextPackage`, prompt-input models, and builders cannot accept writer/client/approval/payload/LLM objects or ambient side-effect handles
2. `AUR-233` second: add the prompt-injection memory harness that proves untrusted PR comments remain shared data, not instructions. This should include:
   - a focused `tests/test_prompt_injection_memory.py` harness using the `untrusted-comment-injection` fixture
   - coverage proving untrusted comments cannot satisfy `conversation_patterns`
   - coverage proving untrusted prompt-like text cannot override reviewer prompt instructions or capability policy
   - coverage proving untrusted memory does not appear in reviewer instruction fields or satisfy reviewer evidence requirements
   - coverage proving trusted actionable memory can still be cited as reviewer-visible data without bypassing quality classification
   - harness output assertions showing included memory IDs, trust labels, passive/actionable state, roles, and truncation status through `ReviewerContextPackage.trace` and prompt-input data
   - no verdict, approval, payload-destination, public-payload, live LLM, live GitHub, or general web-security scanning scope
3. `AUR-255` third: close the milestone only after `AUR-231` and `AUR-233` are Done, focused and full validation pass, docs reflect the durable context boundary, a fresh milestone inventory proves no remaining PRD 0010 implementation issues are active, and fresh subagent review finds no material gaps.

## Issue Workflow

For each issue:

1. Re-fetch the issue, its comments, and current related milestone state from Linear.
2. Move the issue to `In Progress`.
3. Replace `ISSUE_PLAN.md` with a narrow plan for that issue and commit it before implementation.
4. Use fresh subagents to review the issue plan before code changes.
5. Implement the smallest contract/harness slice that satisfies the issue and does not implement later milestone scope.
6. Run the issue harness named by Linear, plus any broader tests that cover touched shared behavior.
7. Use fresh subagents for code/docs review until no material findings remain.
8. Commit the completed issue, and commit separately after every review-fix batch.
9. Move the issue to `In Review`, add a Linear evidence comment with commands and artifact coverage, then move it to `Done` only when the issue acceptance criteria are mapped to concrete evidence.

## Harness Strategy

- `AUR-231` focused harness: `python -m pytest tests/test_reviewer_context.py tests/test_config.py tests/test_contract_boundaries.py tests/test_cli.py`
- `AUR-233` focused harness: `python -m pytest tests/test_prompt_injection_memory.py tests/test_reviewer_context.py tests/test_memory.py tests/test_cli.py`
- Boundary regression harness: static AST tests proving context, prompt, and future reviewer-adapter boundary modules do not import forbidden side-effect modules.
- Boundary shape harness: tests inspect dataclass fields and builder signatures so reviewer context and prompt-input contracts cannot accept writer/client/approval/payload/LLM objects or side-effect handles.
- Prompt-input golden harness: tests prove system/developer instruction fields are separate from context data, trusted/actionable memory and passive memory are labeled, and untrusted prompt-like bodies from `untrusted-comment-injection` never appear as instructions.
- Provider-bound preview harness: non-live tests build the would-be provider request from `ReviewerContextPackage`, assert context minimization, redaction status, provider/model trace metadata, no raw-provider opt-in by default, no network/client dependency, and no secret-like raw fixture content.
- Trusted-memory routing harness: include the existing conversation-pattern tests, or move them into a focused routing test, so `conversation_patterns` are proven to match only trusted actionable memory as part of `AUR-231` evidence.
- Tracer regression harness: `python -m pytest tests/test_context_budget.py tests/test_memory.py tests/test_tracer_fixture_run.py tests/test_render.py`
- Full validation after shared contract changes:
  - `python -m pytest`
  - `python -m py_compile src/reviewgraph/*.py`
  - `python scripts/check_docs.py`
  - `git diff --check`
- Gate validation for `AUR-255`: re-run the focused and full validation, create a fresh Linear-derived PRD 0010 backlog export, run `python scripts/check_docs.py --backlog-export <tmp-file>`, record the export hash in Linear evidence, audit Linear status/comments/blockers immediately before closing, remove the temporary export, and confirm no `.ws/` or temporary export files remain.

## Contract Guardrails

- Preserve dry-run by default. No PRD 0010 work should introduce live GitHub reads, live LLM calls, approval prompts, or writer reachability.
- A reviewer agent is a configured prompt/context boundary that returns structured output. It does not mutate graph state and does not create GitHub payloads.
- Reviewer adapters receive only `ReviewerContextPackage` and return `ReviewerResult`.
- Reviewer context and prompt modules must not import GitHub transports, writer clients, approval/finalization code, or posting payload builders.
- Capabilities default to `diff_context`; MVP reviewer capabilities remain `none` and `diff_context`. GitHub writes are never a reviewer capability.
- `tools` are inert metadata in this milestone. They may be validated and recorded for future policy, but they must not grant live tool execution, repository reads, GitHub reads, GitHub writes, process access, or provider calls.
- `conversation_patterns` may match only trusted actionable memory. Untrusted memory cannot route reviewers or appear as instruction text.
- Passive memory may be included only as explicitly labeled data or represented by exclusion metadata; prompt instruction fields and public payload text must not include untrusted comment bodies in MVP.
- Context budget decisions remain graph-owned. Reviewers receive retained context plus explicit truncation/omitted-context markers, not silent omissions.
- Redaction status and context minimization must be proven in a non-live provider request preview before any context package can be used for provider-bound requests in later milestones.

## Documentation Work

Update the narrowest durable docs alongside behavior:

- Reviewer context package fields and adapter-boundary rules belong in `docs/architecture/state-graph.md`, `docs/architecture/reviewer-config.md`, `docs/prds/0010-agent-context-and-adapter-boundaries.md`, and `docs/harnesses/harness-engineering.md`.
- If the milestone settles a durable tradeoff around passive memory inclusion, tool metadata validation, or prompt-input shape, add or update an ADR in `docs/decisions/`.
- Keep Linear as the executable backlog. Do not copy the issue tree into repository docs beyond this active execution plan.

## Milestone Completion Criteria

`AUR-255` can close only when:

- `AUR-231` is `Done` in Linear with an evidence comment.
- `AUR-233` is `Done` in Linear with an evidence comment.
- A fresh Linear milestone inventory proves every active PRD 0010 non-gate issue is complete and every active blocker is resolved or has an explicit stale/canceled/not-applicable rationale in Linear.
- A fresh Linear-derived backlog export for PRD 0010 passes `python scripts/check_docs.py --backlog-export <tmp-file>`; the temporary export is removed after validation and its hash is recorded in the `AUR-255` evidence comment.
- `ReviewerContextPackage` has a focused contract and harness proving every `AUR-231` acceptance criterion.
- Reviewer config metadata, inert tool metadata, capability policy, prompt-input instruction/data separation, non-live provider-bound minimization/redaction preview, passive/trusted memory separation, truncation traces, and adapter-boundary behavior are represented in code and tests.
- Focused validation, tracer regression validation, full validation, docs check, py-compile, and diff check pass.
- Durable docs have been audited and refactored for the agent context boundary an implementation agent needs when dropping into the repo.
- Fresh subagent review of code, tests, docs, Linear issue evidence, and milestone gate plan reports no material issues.
- No unapproved live API, live LLM, approval, or GitHub writer behavior has been introduced.
