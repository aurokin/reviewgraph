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
9. [Decisions](decisions/README.md) — durable tradeoffs and source-of-truth boundaries.
10. [Harness Engineering](harnesses/harness-engineering.md) — proof strategy before code.
11. [Implementation Plan](plans/implementation-plan.md) — bite-sized implementation sequence.

## Source of truth

- Product, architecture, harness, and decision contracts live in this repository.
- Concrete implementation tickets, milestone order, blockers, and agent handoff details live in Linear under the ReviewGraph project.
- Do not recreate temporary issue trees in the repo once Linear represents them.

## By task

- Adding a new reviewer agent -> `architecture/reviewer-config.md`
- Changing reviewer prompt/context boundaries -> `prds/0010-agent-context-and-adapter-boundaries.md` and `architecture/reviewer-config.md`
- Changing graph routing -> `architecture/state-graph.md`
- Changing GitHub access -> `architecture/github-integration.md`
- Changing approval, finalization, marker reconciliation, or writer reachability -> `architecture/side-effects.md`, `architecture/github-integration.md`, and `decisions/0008-finalization-owns-writer-release.md`
- Changing output format -> `architecture/findings-contract.md`
- Changing finding quality policy -> `architecture/review-quality.md`
- Changing live LLM behavior -> `architecture/llm-data-handling.md`
- Changing PR conversation memory -> `architecture/overview.md` and `architecture/state-graph.md`
- Recording a durable tradeoff -> `decisions/README.md`
- Choosing proof for an implementation slice -> `harnesses/harness-engineering.md`
- Adding tests -> `harnesses/harness-engineering.md`
- Deciding whether to post to GitHub -> `product/rules.md` and `architecture/side-effects.md`
- Breaking work into implementation slices -> `prds/README.md`
- Working a concrete implementation ticket -> Linear issue plus the narrowest linked durable doc

## By proof type

- Schema/model behavior -> `harnesses/harness-engineering.md#contracts`
- Graph cursor or resume behavior -> `harnesses/harness-engineering.md#graph-cursor`
- PR memory, trust, and read gaps -> `harnesses/harness-engineering.md#memory-and-trust`
- Reviewer context boundaries -> `harnesses/harness-engineering.md#reviewer-boundaries`
- Finding quality and logic review -> `harnesses/harness-engineering.md#review-quality`
- Rendering, redaction, and payload previews -> `harnesses/harness-engineering.md#rendering-and-redaction`
- Approval, finalization, and GitHub writes -> `harnesses/harness-engineering.md#side-effects`
- PRD 0007 side-effect milestone proof -> `harnesses/harness-engineering.md#prd-0007-validation`
