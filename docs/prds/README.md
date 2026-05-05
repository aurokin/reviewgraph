# ReviewGraph PRDs

These PRDs turn the architecture docs into independently plannable product slices. They are not a single linear implementation plan. Each PRD should be small enough to become one or more issue sets while preserving the larger ReviewGraph product contract.

Implementation issues for these PRDs live in Linear. Keep this directory focused on product slice intent, durable decisions, and acceptance shape. Do not mirror the full Linear backlog here.

## Read Order

1. [North Star](0001-north-star.md)
2. [MVP Tracer Bullet](0002-mvp-tracer-bullet.md)
3. [Contracts](0003-contracts.md)
4. [Graph Orchestration](0004-graph-orchestration.md)
5. [Review Quality](0005-review-quality.md)
6. [GitHub Read And Memory](0006-github-read-memory.md)
7. [Side Effects](0007-side-effects.md)
8. [Live LLM](0008-live-llm.md)
9. [Harness Strategy](0009-harness-strategy.md)
10. [Agent Context And Adapter Boundaries](0010-agent-context-and-adapter-boundaries.md)

## Dependency Shape

- The MVP tracer bullet depends on contracts, fake adapters, a graph shell, review quality classification, and rendering.
- GitHub write support depends on posting plans, approval decisions, target freshness, actor/permission proof, and marker-based idempotency.
- Live LLM support depends on redaction, context minimization, provider/model recording, and fake/live adapter boundaries.
- Clarification resume depends on graph cursor semantics, reviewer run keys/status, and clarification models.
- GitHub read/memory can advance without live LLM or write support.
- Agent context packaging must land before live LLM reviewer adapters and before untrusted PR conversation is allowed into reviewer prompts.
- Side-effect implementation depends on a finalized write gate that owns approval hash, actor identity, target freshness, redaction status, and marker reconciliation before the writer adapter is reachable.

## Rule

When implementation behavior changes, update the narrowest PRD or durable architecture doc rather than expanding this index.

When implementation sequencing changes, update Linear relationships first. Update this index only when the durable dependency shape changes.
