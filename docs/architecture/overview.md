# Architecture Overview

ReviewGraph is split into transport, memory, orchestration, review, quality policy, synthesis, clarification, and side-effect layers.

```text
CLI / webhook event
  -> GitHub context adapter
  -> PR conversation memory builder
  -> LangGraph orchestration
  -> staged reviewer agent runners
  -> finding normalizer
  -> review quality classifier
  -> ranking/verdict/clarification policy
  -> output renderer / candidate GitHub payload builder
  -> human approval gate
  -> GitHub side-effect adapter
```

## Modules

### CLI

Parses PR references, config paths, dry-run/post flags, and output options.

### GitHub context adapter

Fetches PR metadata, changed files, patches, labels, author, base/head SHAs, review state, comments, and review threads. This layer should be replaceable by fixtures in tests.

### PR conversation memory builder

Converts PR comments and review threads into structured shared memory for the graph. Memory should preserve author, author association, timestamp, thread status, referenced files or lines when available, whether an issue appears resolved, and whether the author is trusted for actionable review feedback. Reviewer contexts may receive trusted actionable memory body text; passive or untrusted memory is metadata-only in MVP. Reviewers should not mutate GitHub conversation state directly.

### LangGraph orchestration

Owns state transitions, routing, staged reviewer introduction, retries, ambiguity escalation, and approval gates. Routing decisions should be represented in state, not hidden in prompts.

### Reviewer agent runners

Run focused reviewer contexts against scoped PR context and shared PR memory. A reviewer may be just a prompt and encapsulated context in the MVP; later reviewers may also use dedicated tools, models, or retrieval. Reviewers should return structured findings or clarification requests, not free-form markdown.

### Finding normalizer

Validates reviewer output into the canonical finding schema.

### Review quality classifier

Applies the finding eligibility policy from `review-quality.md`. Reviewer output becomes a postable finding, local note, clarification request, suggested reply, or suppressed non-finding before any renderer or GitHub payload sees it. Suggested replies are local-only in MVP and never become GitHub replies automatically.

### Ranking/verdict/clarification policy

Ranks priority/severity/confidence, identifies ambiguity that needs human clarification, and recommends a local review verdict. Semantic deduplication is deferred until there is a deterministic policy worth testing.

### Human approval gate

Displays the exact side-effect payload and requires explicit approval before posting. Approval is not a substitute for clarification: if a reviewer needs human input before forming a high-confidence finding, the graph should ask for clarification earlier and record the answer in state.

### Output renderer

Renders markdown summaries, JSON findings, and optional GitHub API payloads.

### GitHub side-effect adapter

Posts comments/reviews only after approval. This adapter is never called in default dry-run mode.
