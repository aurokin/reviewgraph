# PRD 0005: Review Quality

## Problem Statement

The biggest product risk is low-quality review noise. A multi-agent workflow can amplify weak comments if every reviewer output is treated as a finding. ReviewGraph needs a strict Codex-inspired quality gate before anything becomes public feedback.

## Solution

Classify all reviewer output into postable findings, local notes, clarification requests, suggested replies, or non-findings. Only postable findings are eligible for GitHub payloads, and even those require approval and side-effect gates.

## User Stories

1. As a PR author, I want only actionable issues posted, so that review comments are worth my attention.
2. As a maintainer, I want generic "add tests" comments suppressed, so that the bot does not create noise.
3. As a maintainer, I want findings grounded in changed code, so that the bot does not flag unrelated old issues.
4. As a reviewer, I want uncertain merge-blocking concerns to become clarification requests, so that I can answer intent questions.
5. As a reviewer, I want local notes preserved, so that useful non-postable advice is not lost.
6. As a developer, I want priority distinct from severity, so that ranking and rendering can be consistent.
7. As a developer, I want diff anchors modeled, so that future inline comments are built on a safe foundation.
8. As a maintainer, I want public request-changes wording excluded by default, so that a top-level comment does not become de facto requested changes.
9. As a maintainer, I want postable comments to be concise and matter-of-fact, so that they resemble high-signal code review.
10. As a maintainer, I want logic-review findings to prove a concrete changed behavior or invariant break, so that cross-file reasoning does not become generic architecture commentary.

## Implementation Decisions

- Postable findings must be discrete, actionable, introduced or exposed by the PR, evidence-backed, and likely to be fixed by the author.
- Findings that depend on unstated author intent become clarification requests when mergeability is affected.
- Generic, speculative, duplicate-without-new-analysis, locationless, or pre-existing issues become local notes or non-findings.
- Testing findings are postable only when they identify changed behavior, a concrete regression scenario, and missing coverage.
- Priority is stored as integer `0..3`; renderers may display `P0..P3`.
- Inline posting requires a validated diff anchor and is deferred.
- MVP top-level PR comments can include approved findings but not unapproved local verdict pressure.
- Suggested replies to human comments are local-only in MVP.
- Logic-review findings may cite cross-file or product-behavior evidence, but their postable location must anchor to changed code that introduced or exposed the risk.
- Logic-review output that depends on unstated product intent, migration expectations, or reviewer assumptions becomes a clarification request instead of a blocking finding.
- Generic architectural preferences, broad refactor advice, and non-local concerns without changed-code causality are local notes or non-findings.

## Testing Decisions

- Golden quality cases cover postable finding, local note, clarification request, suggested reply, and non-finding.
- Tests assert reviewer self-declared postability/blocking is ignored.
- Tests assert low-confidence and ambiguous issues cannot drive request-changes recommendations.
- Tests assert generic missing-test feedback is not postable.
- Tests assert postable findings require changed-code evidence and short locations.
- Tests assert secret-like evidence is redacted before rendering or posting.
- Logic-review golden cases cover cross-file invariant break, breaking API behavior, ambiguous product intent that becomes a clarification request, and generic architecture advice that is suppressed or local-only.
- Logic-review golden cases assert that cross-file evidence can support a finding, but the public location still anchors to the changed line or hunk that introduced the risk.

## Out of Scope

- Semantic deduplication.
- Inline GitHub comments.
- Automatic replies to human review comments.

## Further Notes

ReviewGraph should prefer no finding over a plausible weak finding. The product earns trust by being willing to suppress output.
