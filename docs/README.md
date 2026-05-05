# ReviewGraph Documentation

This directory uses progressive disclosure: start broad, then follow the narrowest document needed for the current task.

## Read in order

1. [Product Vision](product/vision.md) — what the product is and why it exists.
2. [Product Rules](product/rules.md) — durable behavior constraints.
3. [Architecture Overview](architecture/overview.md) — system boundaries and modules.
4. [State Graph](architecture/state-graph.md) — LangGraph workflow and routing.
5. [Review Agent Config](architecture/reviewer-config.md) — configurable reviewer roster and triggers.
6. [Harness Engineering](harnesses/harness-engineering.md) — proof strategy before code.
7. [Implementation Plan](plans/implementation-plan.md) — bite-sized implementation sequence.

## By task

- Adding a new reviewer agent -> `architecture/reviewer-config.md`
- Changing graph routing -> `architecture/state-graph.md`
- Changing GitHub access -> `architecture/github-integration.md`
- Changing output format -> `architecture/findings-contract.md`
- Adding tests -> `harnesses/harness-engineering.md`
- Deciding whether to post to GitHub -> `product/rules.md` and `architecture/side-effects.md`
