# Product Vision

ReviewGraph turns pull request review into an explicit, configurable agent workflow.

Rather than one generic reviewer prompt, it uses LangGraph to route each PR through the reviewer agents that match the change: security, correctness, tests, frontend state, docs/API contracts, performance, or any project-defined reviewer.

## Target user

A senior engineer or engineering team that wants AI-assisted PR review without handing merge authority to an opaque bot.

## Core promise

ReviewGraph should help a developer answer:

- What changed in this PR?
- Which review perspectives matter for this change?
- What did each reviewer find?
- Which findings are duplicated, weak, or blocking?
- What should be posted publicly, and what should remain local advice?

## Differentiator

The bot is not just "LLM reads diff." It is a production-agent pattern:

- explicit state
- conditional routing
- specialized agents
- structured findings
- deduplication
- confidence and severity policy
- human approval before side effects
- reusable configuration

## MVP outcome

A user can run:

```bash
reviewgraph review https://github.com/owner/repo/pull/123 --config review_agents.yaml
```

and receive:

- selected reviewer agents and trigger reasons
- structured JSON findings
- markdown review summary
- recommended verdict
- dry-run GitHub posting payload
