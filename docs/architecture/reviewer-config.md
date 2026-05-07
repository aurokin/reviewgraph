# Reviewer Configuration

Reviewer agents are configured, not hardcoded.

In MVP, an agent may be a configured prompt with its own scoped context. Over time, an agent may also specify a model, tools, context window policy, or retrieval strategy. The important boundary is encapsulation: each reviewer receives a deliberate context and returns structured output to the graph.

## Example

```yaml
agents:
  security:
    description: Finds auth, injection, secrets, SSRF, unsafe eval, path traversal.
    stages: ["specialized_review"]
    triggers:
      paths: ["src/auth/**", "src/api/**", "server/**"]
      diff_patterns: ["password", "token", "jwt", "eval", "exec"]
      risk_min: medium
    required: false
    verdict_power: request_changes

  frontend_state:
    description: Reviews React/Vue state, async flows, loading/error states, UI regressions.
    stages: ["specialized_review"]
    triggers:
      paths: ["apps/web/**", "src/**/*.tsx", "src/**/*.vue"]
      labels: ["frontend"]
    required: false
    verdict_power: comment

  logic:
    description: Reviews non-local behavior, invariants, state transitions, and business logic.
    stages: ["logic_review"]
    triggers:
      risk_min: medium
      max_files: 20
    required: false
    verdict_power: request_changes

  tests:
    description: Checks test coverage, missing edge cases, and flaky patterns.
    stages: ["initial_triage", "specialized_review"]
    triggers:
      always: true
    required: true
    verdict_power: comment

  breaking_changes:
    description: Reviews external integrations, CLI flags, config, APIs, persisted state, and protocol compatibility.
    stages: ["specialized_review", "logic_review"]
    triggers:
      paths: ["src/config/**", "src/cli/**", "src/api/**", "docs/**"]
      risk_min: medium
    required: false
    verdict_power: request_changes

  change_size:
    description: Checks whether the PR is too large to review well and suggests smaller coherent stages.
    stages: ["initial_triage"]
    triggers:
      changed_lines_min: 500
    required: false
    verdict_power: comment

  context_budget:
    description: Reviews model-visible context growth, unbounded fragments, and prompt/cache hazards.
    stages: ["specialized_review", "logic_review"]
    triggers:
      paths: ["src/context/**", "src/prompts/**", "src/reviewgraph/**"]
      diff_patterns: ["prompt", "context", "history", "memory", "token"]
    required: false
    verdict_power: request_changes
```

## Trigger fields

- `always`: selects reviewer for every PR.
- `paths`: glob patterns matched against changed file paths.
- `labels`: GitHub labels that select reviewer.
- `diff_patterns`: case-insensitive regex or literal patterns matched against patches.
- `risk_min`: minimum risk assessment required.
- `max_files`: optional cap for noisy reviewers.
- `conversation_patterns`: optional patterns matched only against trusted actionable PR comments or review threads.
- `changed_lines_min`: minimum changed-line count required to select a reviewer.
- `changed_files_min`: minimum changed-file count required to select a reviewer.

## Agent fields

- `description`: human-readable purpose of the reviewer.
- `stages`: required list of graph stages where this reviewer is eligible. `stages` is not a trigger field; `triggers.stages` must be rejected by config validation.
- `triggers`: selector and gate fields described above.
- `required`: whether reviewer failure blocks posting.
- `verdict_power`: MVP supports `comment` and `request_changes`; `approve` must be rejected until a future approval policy exists.

## Trigger evaluation

Trigger fields are evaluated as selectors plus gates:

- Selectors: `always`, `paths`, `labels`, `diff_patterns`, and `conversation_patterns`.
- Gates: `risk_min`, `max_files`, `changed_lines_min`, and `changed_files_min`.

A reviewer is selected for an eligible stage when at least one selector matches and all configured gates pass. If a reviewer has only gates and no selector, the gates act as the selector. Every matched selector and every gate decision must be recorded in `SelectedReviewer.reasons`.

Untrusted PR comments may be retained as passive memory, but they must not satisfy `conversation_patterns` or contribute to request-changes recommendations. Conversation-pattern reasons must name the matching memory ID and trust label; GitHub-derived memory reasons also include source provider provenance. Example:

```text
initial_triage triggers.conversation_patterns=ambiguous behavior memory_id=github:issue_comment:123 trust=trusted source_provider=github
```

Top-level config may include `trusted_operator_authors` and `trusted_bot_authors`. Bot authors are default-deny even when their GitHub association is owner, member, or collaborator. Missing or unknown actor type fails closed for trust.

## Context budget config

Top-level config may include `context_budget` to bound the context package before reviewer fanout:

```yaml
context_budget:
  max_changed_files: 50
  max_patch_bytes: 200000
  max_memory_bytes: 100000
  max_reviewers: 20
  max_live_calls: 0
```

Fields may be omitted to use fixture-safe defaults. `max_changed_files`, `max_patch_bytes`, `max_memory_bytes`, and `max_reviewers` must be positive integers. `max_live_calls` may be zero; default dry-run and fake-reviewer execution must not require live provider calls. Unknown fields are rejected.

Budgeting is a graph decision, not a prompt convention. The graph records retained and omitted file paths, patch bytes, memory IDs, reviewer IDs, deferred reviewer IDs, planned live-call count, truncation notices, omitted-context markers, and generated local-note IDs in `ContextBudget`.

Reviewers beyond budget are selected-then-skipped: their trigger reasons remain explainable, their raw output is not executed, and a structured local note records the deferral. Oversized patches or conversation memory are represented as marker-only context with explicit truncation state.

## Optional agent fields

- `model`: preferred model for this reviewer.
- `tools`: inert future tool identifiers. In MVP, accepted tool names are metadata only and must not create callable handles, provider tool schemas, extra capabilities, repository access, GitHub access, live calls, or write access.
- `context`: context policy, such as diff-only, diff-plus-comments, or focused-files.
- `capabilities`: allowed reviewer capabilities. MVP supports `none` and `diff_context`; later phases may add `github_read`, `read_repo`, or `run_tests`.

These fields should be validated but do not need live implementations in the first tracer bullets. Tool identifiers use the `future-*` namespace until a later explicit tool policy exists.

Reviewer capabilities must default to `diff_context`, with GitHub writes unavailable to reviewer agents. `read_repo` means full checkout or repository file access and is out of scope for MVP. A reviewer may recommend a postable finding, but only the graph and side-effect adapter can create a GitHub payload.

## Reviewer Context Package

`ReviewerContextPackage` is the only input a reviewer adapter may receive. It includes:

- review target and active stage
- selected reviewer name, stage, and trigger reasons
- selected reviewer config metadata: model, inert tools, context policy, capabilities, required flag, and verdict power
- bounded changed-file context after context-budget decisions
- trusted actionable memory references
- passive memory references or explicit passive/excluded metadata
- truncation notices, omitted-context markers, and local budget notes
- a capability policy with GitHub writes, repository access, and live provider calls disabled by default
- a trace of memory IDs, trust labels, resolved status, passive/actionable state, truncation state, and omitted-context IDs

Prompt inputs built from the package must keep instructions separate from context data. PR conversation memory is labeled data, not instruction text. Passive or untrusted memory is represented as passive metadata only in MVP; bodies stay out of reviewer prompt data. Passive or untrusted memory must not appear in system/developer instructions, satisfy evidence, change verdicts, approve posting, or enter public payload text.

Provider-bound request previews are non-live harness artifacts. They serialize the minimized package data, apply redaction, record redaction status, and keep `raw_provider_submission_enabled` and `raw_trace_persistence_enabled` false by default. They do not create network clients or provider tool schemas.

## Selection output

Each selected reviewer must produce:

```json
{
  "name": "security",
  "stage": "specialized_review",
  "reasons": [
    "changed path matched src/auth/**",
    "diff contained token"
  ]
}
```

## Verdict power

- `comment`: reviewer can produce comments and suggestions only.
- `request_changes`: reviewer can contribute to a local request-changes recommendation if findings meet policy. Submitting a GitHub request-changes review is deferred until the side-effect policy explicitly supports it.
- `approve`: reserved for future use and invalid in MVP config.
