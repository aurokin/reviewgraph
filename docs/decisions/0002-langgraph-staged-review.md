# Decision 0002: Staged LangGraph review

## Status

Accepted

## Context

ReviewGraph is meant to demonstrate LangGraph as an explicit orchestration layer for PR review, even if a simpler linear pipeline could handle the earliest MVP. The product interest is not only code review; it is staged logic review with reviewer agents introduced under different conditions and at different points in the workflow.

## Decision

Use LangGraph as a first-class part of the product architecture. Reviewer agents are encapsulated contexts that may start as prompts, and later may use reviewer-specific tools, models, or retrieval. PR comments and review threads should be converted into shared graph memory so agents can account for existing discussion instead of reviewing the diff in isolation.

## Consequences

- The MVP should prove graph state, staged routing, and reviewer selection reasons early.
- Reviewer agents must record the stage and conditions that introduced them.
- Clarification requests are part of the graph, not markdown-only prose.
- The implementation may be more orchestration-heavy than a minimal PR reviewer, because the project is also a LangGraph example.
