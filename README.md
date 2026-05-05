# ReviewGraph

ReviewGraph is a LangGraph-powered PR review orchestrator for staged, multi-agent code and logic review workflows.

The project is intentionally documentation-first. The first implementation should preserve the product contracts, harness strategy, and side-effect boundaries described in `docs/` before adding code.

## Product one-liner

ReviewGraph reads GitHub pull requests, uses the PR conversation as shared review memory, introduces reviewer agents under explicit graph conditions, runs targeted review stages, and gates GitHub writes behind human approval.

## Start here

Read in this order:

1. [Product Vision](docs/product/vision.md)
2. [Product Rules](docs/product/rules.md)
3. [Architecture Overview](docs/architecture/overview.md)
4. [State Graph](docs/architecture/state-graph.md)
5. [Review Quality](docs/architecture/review-quality.md)
6. [LLM Data Handling](docs/architecture/llm-data-handling.md)
7. [Reviewer Configuration](docs/architecture/reviewer-config.md)
8. [PRDs](docs/prds/README.md)
9. [Harness Engineering](docs/harnesses/harness-engineering.md)
10. [Implementation Plan](docs/plans/implementation-plan.md)

## Intended MVP

- CLI accepts a GitHub PR URL or `owner/repo#number`.
- Fetches PR metadata, changed files, diff, comments, and review threads where available.
- Loads `review_agents.yaml`.
- Selects relevant reviewer agents with explainable trigger reasons.
- Runs selected reviewers through encapsulated contexts, with fake reviewers available for deterministic harnesses.
- Classifies reviewer output into postable findings, local notes, clarification requests, and suppressed non-findings.
- Normalizes, ranks, and summarizes review output.
- Lets a human approve the exact postable items before any GitHub write.
- Emits markdown and JSON output.
- Runs dry by default; posting to GitHub requires explicit human approval.

## Out of scope for MVP

- Always-on GitHub App/webhook deployment.
- Auto-requesting changes without approval.
- Inline comments with perfect diff-line mapping.
- Repository checkout and full test execution.
- Formal GitHub review submission.
- Semantic deduplication across unrelated reviewer contexts.
- Long-term storage, dashboard UI, billing, teams, or hosted product features.

## Repository status

Scaffold-only. No runtime implementation exists yet.
