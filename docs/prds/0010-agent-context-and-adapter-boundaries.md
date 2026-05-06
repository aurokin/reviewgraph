# PRD 0010: Agent Context And Adapter Boundaries

## Problem Statement

ReviewGraph's value depends on treating reviewer agents as isolated review contexts, not as arbitrary code paths with ambient access to GitHub, prompts, or process state. The existing docs describe configured prompts, staged selection, and shared PR conversation memory, but implementation agents need a dedicated product slice that makes the reviewer context boundary testable.

Without this boundary, untrusted PR comments could become instructions, reviewer prompts could accidentally receive too much context, and reviewer adapters could couple directly to GitHub read or write transports.

## Solution

Define a reviewer agent runtime contract around explicit prompt inputs, scoped context packages, read-only capabilities, model/tool metadata, and structured output. PR conversation memory is shared across agents as labeled data, not as instructions. Trusted memory may trigger reviewer selection when configured. Untrusted memory is passive metadata only in reviewer prompts; in MVP, untrusted comment bodies cannot affect routing, verdicts, approval, reviewer instructions, or public payload text.

MVP reviewer agents are mostly prompts plus deterministic fake outputs. Live LLM reviewers are a later adapter behind the same context package contract, context budget, redaction policy, and quality classifier.

## User Stories

1. As a LangGraph evaluator, I want each reviewer agent to receive an explicit context package, so that agent boundaries are visible in state.
2. As a maintainer, I want reviewer prompts decoupled from GitHub transports, so that a reviewer cannot write to GitHub.
3. As a maintainer, I want PR comments to be labeled as trusted, untrusted, resolved, or unresolved memory, so that comment injection cannot steer the graph.
4. As a reviewer, I want trusted PR discussion available as context, so that I can avoid repeating already-resolved feedback.
5. As a reviewer, I want untrusted PR discussion represented as passive metadata or excluded, so that I do not treat it as an instruction.
6. As a developer, I want prompt templates and fake reviewer outputs to share the same input contract, so that fake tests prove live behavior shape.
7. As a developer, I want reviewer configs to validate optional model, tool, context, and capability fields, so that later live agents can be introduced without changing the graph contract.
8. As a maintainer, I want reviewer capabilities to default read-only, so that GitHub writes remain graph-owned side effects.
9. As a maintainer, I want live LLM requests redacted or explicitly governed before provider submission, so that secrets in diffs and comments do not leak by default.
10. As a developer, I want context package traces to show included memory IDs and truncation status, so that review quality can be debugged.

## Implementation Decisions

- A reviewer agent is a configured prompt/context boundary that returns structured output; it is not allowed to mutate graph state or create GitHub payloads.
- `ReviewerContextPackage` should include review target, active stage, selected reviewer metadata, selected reviewer config metadata, bounded diff context, trusted memory references, passive/excluded memory metadata, truncation notes, omitted-context markers, and capability policy.
- Reviewer adapters receive `ReviewerContextPackage` and return `ReviewerResult`. They do not receive GitHub read transports, GitHub write transports, approval state, or writer payload builders.
- Prompt templates are stored separately from GitHub adapters and side-effect code.
- `conversation_patterns` may match only trusted actionable memory. Untrusted comments cannot select reviewers, affect verdicts, satisfy evidence requirements, appear in reviewer prompt body fields, or appear in public payloads in MVP. A later explicit quoting policy may relax this, but it is out of scope until it has deterministic tests.
- MVP capabilities are `none` and `diff_context`. `github_read`, `read_repo`, `run_tests`, and tool-using reviewer agents are future work.
- Optional `model`, `tools`, `context`, and `capabilities` config fields are validated early even when most are not implemented. Before a tool policy exists, `tools` is inert metadata only and cannot create callable handles, provider tool schemas, live calls, repository access, GitHub access, or write access.
- Live LLM reviewer requests must pass through context minimization and redaction policy before provider submission, or the run must explicitly record that raw provider submission was enabled by a human.

## Testing Decisions

- Add schema tests for `ReviewerContextPackage`, reviewer capability validation, and prompt/template selection.
- Add adapter-boundary tests proving reviewer adapters cannot import or receive GitHub writer transports.
- Add malicious-comment fixtures proving untrusted memory cannot select reviewers, override prompts, change verdicts, approve posting, or enter public payload text.
- Add trusted-memory routing tests proving `conversation_patterns` can select a reviewer only from trusted actionable comments or unresolved trusted review threads.
- Add context package golden tests showing included memory IDs, trust labels, resolved status, truncation status, and reviewer-specific context policy.
- Add non-live provider-bound preview tests proving would-be provider request data is minimized and redacted by default, records redaction status, and keeps raw-provider and raw-trace opt-ins disabled.

## Out of Scope

- Tool-using reviewer agents.
- Repository checkout access for reviewers.
- Running project tests from a reviewer agent.
- Automatic replies to PR comments.
- GitHub writes from any reviewer adapter.

## Further Notes

This PRD captures the user's main design point: an agent is not just a prompt, but a prompt running inside a deliberately scoped and encapsulated context.
