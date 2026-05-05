# Architecture Overview

ReviewGraph is split into transport, orchestration, review, synthesis, and side-effect layers.

```text
CLI / webhook event
  -> GitHub context adapter
  -> LangGraph orchestration
  -> reviewer agent runners
  -> finding normalizer
  -> dedupe/ranking/verdict policy
  -> human approval gate
  -> output renderer / GitHub side-effect adapter
```

## Modules

### CLI

Parses PR references, config paths, dry-run/post flags, and output options.

### GitHub context adapter

Fetches PR metadata, changed files, patches, labels, author, base/head SHAs, and review state. This layer should be replaceable by fixtures in tests.

### LangGraph orchestration

Owns state transitions, routing, retries, and approval gates. Routing decisions should be represented in state, not hidden in prompts.

### Reviewer agent runners

Run focused LLM prompts against scoped PR context. Reviewers should return structured findings, not free-form markdown.

### Finding normalizer

Validates reviewer output into the canonical finding schema.

### Dedupe/ranking/verdict policy

Merges duplicate findings, ranks severity/confidence, and recommends a review verdict.

### Human approval gate

Displays the exact side-effect payload and requires explicit approval before posting.

### Output renderer

Renders markdown summaries, JSON findings, and optional GitHub API payloads.

### GitHub side-effect adapter

Posts comments/reviews only after approval. This adapter is never called in default dry-run mode.
