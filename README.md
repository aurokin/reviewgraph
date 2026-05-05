# ReviewGraph

ReviewGraph is a LangGraph-powered PR review orchestrator for configurable, multi-agent code review workflows.

The project is intentionally documentation-first. The first implementation should preserve the product contracts, harness strategy, and side-effect boundaries described in `docs/` before adding code.

## Product one-liner

ReviewGraph reads GitHub pull requests, selects reviewer agents via configurable path/risk triggers, runs targeted review passes, deduplicates findings, and gates GitHub review posting behind human approval.

## Start here

Read in this order:

1. [Product Vision](docs/product/vision.md)
2. [Product Rules](docs/product/rules.md)
3. [Architecture Overview](docs/architecture/overview.md)
4. [State Graph](docs/architecture/state-graph.md)
5. [Harness Engineering](docs/harnesses/harness-engineering.md)
6. [Implementation Plan](docs/plans/implementation-plan.md)

## Intended MVP

- CLI accepts a GitHub PR URL or `owner/repo#number`.
- Fetches PR metadata, changed files, and diff.
- Loads `review_agents.yaml`.
- Selects relevant reviewer agents with explainable trigger reasons.
- Runs selected reviewers through LLM-backed prompts.
- Normalizes, deduplicates, ranks, and summarizes findings.
- Emits markdown and JSON output.
- Runs dry by default; posting to GitHub requires explicit human approval.

## Out of scope for MVP

- Always-on GitHub App/webhook deployment.
- Auto-requesting changes without approval.
- Inline comments with perfect diff-line mapping.
- Repository checkout and full test execution.
- Long-term storage, dashboard UI, billing, teams, or hosted product features.

## Repository status

Scaffold-only. No runtime implementation exists yet.
