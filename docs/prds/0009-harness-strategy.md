# PRD 0009: Harness Strategy

## Problem Statement

ReviewGraph is safety-sensitive and integration-heavy. Without deterministic harnesses, implementation will either depend on live GitHub/LLM behavior too early or miss subtle side-effect and routing bugs.

## Solution

Build a confidence ladder of fixtures, schema tests, fake adapters, graph tests, dry-run CLI tests, approval/writer tests, and opt-in live smoke tests. Harnesses should prove the product contract before live APIs are used.

## User Stories

1. As a developer, I want schema tests first, so that contracts fail fast.
2. As a developer, I want fixture PRs, so that routing and quality behavior can be deterministic.
3. As a developer, I want fake GitHub reads, so that graph tests do not need credentials.
4. As a developer, I want fake reviewers, so that reviewer outputs can cover edge cases.
5. As a maintainer, I want dry-run CLI tests, so that default behavior never writes.
6. As a maintainer, I want approval tests, so that rejected or empty approvals never write.
7. As a maintainer, I want idempotency tests, so that retry and restart do not duplicate comments.
8. As a maintainer, I want stale-SHA tests, so that stale approvals fail closed.
9. As a maintainer, I want redaction tests, so that secrets do not appear in outputs.
10. As a developer, I want pagination fixtures, so that first-page-only GitHub reads cannot pass.
11. As a LangGraph evaluator, I want stage cursor tests, so that graph resume behavior is concrete.
12. As a developer, I want live tests opt-in, so that normal test commands stay safe.

## Implementation Decisions

- Fixture PRs live under `tests/fixtures/prs/`.
- Required fixtures include frontend state, security-sensitive, docs-only, mixed-risk, ambiguous logic, breaking API, oversized, stale approval, untrusted comment injection, and paginated GitHub read.
- Fake reviewer outputs should cover postable finding, local note, clarification request, suggested reply, non-finding, malformed JSON, and reviewer failure.
- Fake GitHub transport should support paginated responses and actor/permission variants.
- Graph tests should exercise stage cursor, reviewer status, clarification resume, dry-run branch, and stale target branch.
- Writer tests use fake transport and embedded marker fixtures.
- Live read and live post tests are marked and skipped by default.

## Testing Decisions

- Test external behavior and contract boundaries, not internal helper call order.
- Prefer whole-object equality for models and rendered machine outputs.
- Golden markdown/JSON fixtures should be stable but not overfit prompt wording.
- Every live feature needs a fake equivalent first.
- Any GitHub write feature requires dry-run proof, approval proof, stale-target proof, and idempotency proof.

## Out of Scope

- Full live CI matrix.
- Hosted environment tests.
- Browser/UI testing.
- Performance benchmarking beyond context budget and live-call caps.

## Further Notes

This PRD should drive issue creation. Each implementation slice should identify the lightest harness that proves it and avoid live APIs until the fake path is solid.
