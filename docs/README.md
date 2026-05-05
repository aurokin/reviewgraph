# ReviewGraph Documentation

This directory uses progressive disclosure: start broad, then follow the narrowest document needed for the current task.

## Read in order

1. [Product Vision](product/vision.md) — what the product is and why it exists.
2. [Product Rules](product/rules.md) — durable behavior constraints.
3. [Architecture Overview](architecture/overview.md) — system boundaries and modules.
4. [State Graph](architecture/state-graph.md) — LangGraph workflow and routing.
5. [Review Agent Config](architecture/reviewer-config.md) — configurable reviewer roster, stages, and triggers.
6. [Review Quality](architecture/review-quality.md) — finding eligibility, comment shape, and reviewer skill set.
7. [LLM Data Handling](architecture/llm-data-handling.md) — live LLM opt-in, minimization, and redaction.
8. [PRDs](prds/README.md) — independently plannable product slices.
9. [Harness Engineering](harnesses/harness-engineering.md) — proof strategy before code.
10. [Implementation Plan](plans/implementation-plan.md) — bite-sized implementation sequence.

## By task

- Adding a new reviewer agent -> `architecture/reviewer-config.md`
- Changing reviewer prompt/context boundaries -> `prds/0010-agent-context-and-adapter-boundaries.md` and `architecture/reviewer-config.md`
- Changing graph routing -> `architecture/state-graph.md`
- Changing GitHub access -> `architecture/github-integration.md`
- Changing output format -> `architecture/findings-contract.md`
- Changing finding quality policy -> `architecture/review-quality.md`
- Changing live LLM behavior -> `architecture/llm-data-handling.md`
- Changing PR conversation memory -> `architecture/overview.md` and `architecture/state-graph.md`
- Adding tests -> `harnesses/harness-engineering.md`
- Deciding whether to post to GitHub -> `product/rules.md` and `architecture/side-effects.md`
- Breaking work into implementation slices -> `prds/README.md`
