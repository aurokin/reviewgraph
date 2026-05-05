# PRD 0001: North Star

## Problem Statement

Senior engineers want AI-assisted PR review that is useful for code and logic review without handing merge authority to an opaque bot. Generic diff-reading prompts are easy to run, but they are hard to trust: they hide routing decisions, mix strong findings with weak advice, ignore prior PR conversation, and make side effects risky.

ReviewGraph should also serve as a strong LangGraph example. The product should demonstrate why explicit graph state, staged reviewer introduction, shared memory, clarification, and approval-gated side effects matter.

## Solution

ReviewGraph provides a documentation-first, LangGraph-powered PR review orchestrator. It reads a PR, builds structured memory from the PR conversation, introduces reviewer agents under explicit graph conditions, classifies output through a Codex-inspired quality gate, and renders local dry-run output by default. Any GitHub write is top-level comment only in MVP and requires item-level approval, target freshness proof, actor/permission proof, redaction, and idempotency.

## User Stories

1. As a senior engineer, I want ReviewGraph to explain which reviewers ran, so that I can trust why each review perspective was used.
2. As a senior engineer, I want ReviewGraph to use PR comments as memory, so that it does not repeat already-resolved discussion.
3. As a senior engineer, I want ambiguous merge-blocking issues to become clarification requests, so that the system does not overclaim.
4. As a senior engineer, I want dry-run output by default, so that I can inspect review quality before anything reaches GitHub.
5. As a maintainer, I want GitHub writes gated behind explicit approval, so that automation cannot surprise contributors.
6. As a maintainer, I want only high-quality findings to become postable comments, so that the bot does not generate review noise.
7. As a maintainer, I want local notes separated from public comments, so that useful advice does not become public pressure.
8. As a LangGraph evaluator, I want to see explicit graph state and routing, so that the project demonstrates real orchestration rather than prompt chaining.
9. As a LangGraph evaluator, I want staged reviewer introduction, so that the graph shows conditional agent participation over time.
10. As a LangGraph evaluator, I want a clarification/resume path, so that the graph demonstrates human-in-the-loop state transitions.
11. As a developer, I want deterministic fake adapters, so that implementation can be tested without live GitHub or LLM calls.
12. As a developer, I want live integrations opt-in, so that local development stays safe and reproducible.

## Implementation Decisions

- LangGraph is a first-class product requirement, not incidental plumbing.
- Reviewers are encapsulated contexts. In MVP they may be prompts over bounded context; later they may use tools, model choices, or retrieval.
- PR conversation memory is structured data, not an instruction stream.
- Reviewer output is not automatically postable. The graph classifies raw output into postable findings, local notes, clarification requests, suggested replies, or non-findings.
- Side effects are last. MVP writes only a top-level PR comment after item-level approval.
- The local verdict is separate from public GitHub comment text.
- Approval is bound to a review target and final payload hash.
- The writer uses embedded ReviewGraph markers for idempotency because long-term storage is out of scope.

## Testing Decisions

- Default tests use fixtures, fake GitHub adapters, and fake reviewer adapters.
- Tests should prove product behavior at module boundaries rather than internal prompt wording.
- Live read and live post tests are opt-in.
- The test suite should make it impossible for a dry-run path to reach a writer.
- The harness should prove noisy or speculative reviewer output is suppressed or downgraded.

## Out of Scope

- Hosted product, dashboards, teams, billing, long-term storage.
- Repository checkout and full test execution in MVP.
- Formal GitHub PR reviews, inline comments, labels, status checks, approvals, and request-changes submission in MVP.
- Semantic deduplication until a deterministic policy exists.

## Further Notes

The north star is review quality plus orchestration clarity. The product should not add graph complexity unless the graph makes the review more inspectable, staged, safer, or more correct.
