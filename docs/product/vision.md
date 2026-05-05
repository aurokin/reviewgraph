# Product Vision

ReviewGraph turns pull request review into an explicit, configurable LangGraph agent workflow.

Rather than one generic reviewer prompt, it uses LangGraph to route each PR through reviewer agents that match the change and the stage of review: security, correctness, tests, frontend state, docs/API contracts, performance, logic review, ambiguity resolution, or any project-defined reviewer.

This project is also intended to be a strong LangGraph example. The graph is not incidental plumbing; it is the way ReviewGraph demonstrates explicit state, staged agent introduction, conditional routing, shared memory, human clarification, and side-effect boundaries.

## Target user

A senior engineer or engineering team that wants AI-assisted PR review without handing merge authority to an opaque bot.

## Core promise

ReviewGraph should help a developer answer:

- What changed in this PR?
- What has already been discussed in the PR conversation?
- Which review perspectives matter for this change and this review stage?
- What did each reviewer find?
- Which findings are evidence-backed, ambiguous, weak, or blocking?
- Which issues need human clarification before an agent should make a recommendation?
- What should be posted publicly, and what should remain local advice?

Review quality matters more than graph novelty. LangGraph should make the review more inspectable, staged, and correct; it should not justify noisy reviewer output. The strongest output is often no finding when the evidence does not meet the bar.

## Differentiator

The bot is not just "LLM reads diff." It is a production-agent pattern:

- explicit state
- conditional routing
- staged reviewer introduction
- specialized reviewer contexts
- shared PR conversation memory
- optional reviewer-specific tools and models
- structured findings
- finding eligibility gates
- confidence and severity policy
- ambiguity escalation
- item-level approval for postable comments
- human approval before side effects
- reusable configuration

The review behavior is inspired by high-signal assistant code review practice: lead with concrete findings, ground claims in code evidence, avoid generic commentary, and separate blocking issues from advice. The project should be honest about that influence while keeping its own product contract explicit.

## MVP outcome

A user can run:

```bash
reviewgraph review https://github.com/owner/repo/pull/123 --config review_agents.yaml
```

and receive:

- selected reviewer agents and trigger reasons
- PR conversation memory used during review
- structured JSON findings
- markdown review summary
- recommended verdict
- dry-run GitHub posting payload
