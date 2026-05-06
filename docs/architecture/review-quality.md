# Review Quality

ReviewGraph should use LangGraph to improve review quality, not to produce more comments.

The review bar is inspired by Codex review mode and the local Codex review skills: findings should be discrete, actionable, evidence-backed, and likely to be fixed by the PR author if surfaced.

## Output classes

Reviewer output should be normalized into one of these classes:

- `postable_finding`: a concrete issue suitable for a PR review comment after approval.
- `local_note`: useful local advice that should not be posted as review feedback.
- `clarification_request`: a question that must be answered before a high-confidence mergeability recommendation.
- `suggested_reply`: a local-only draft response to a human PR comment; MVP never posts it automatically.
- `non_finding`: generic, unsupported, reviewer-declared duplicate, or speculative output that should be suppressed.

Only `postable_finding` items should be candidates for GitHub review payloads.

## Finding Eligibility

A finding is postable only when all of these are true:

1. It meaningfully affects correctness, security, performance, maintainability, compatibility, or user-visible behavior.
2. It was introduced or exposed by the PR, not merely discovered nearby.
3. It is discrete and actionable.
4. The reviewer can cite concrete PR evidence.
5. It does not depend on unstated assumptions about author intent.
6. It identifies the scenario, input, environment, or caller path needed for the issue to occur.
7. The original author would likely fix it if they saw the comment.
8. It is not just a style preference unless the style issue obscures meaning or violates documented project standards.

If any of these are uncertain and the issue affects mergeability, emit a clarification request instead of inflating confidence.

## Comment Shape

Postable review comments should be short, matter-of-fact, and scoped to one issue. Public titles and bodies should not tell GitHub to request changes or block merge; verdict pressure belongs in local verdict synthesis and approval, not in the finding text.

- Use one comment per distinct issue.
- Keep the body to one paragraph unless a tiny code fragment is necessary.
- Avoid praise, blame, and broad commentary.
- Explain why the issue matters and when it occurs.
- Do not include code blocks longer than a few lines.
- Use suggestion blocks only for exact replacement code.

## Location Discipline

Postable findings should have a precise location.

- Prefer a line range that overlaps the diff.
- Keep ranges as short as possible, usually one line and rarely more than 5-10 lines.
- If the issue is real but cannot be located precisely, keep it as a top-level local note unless the renderer has an approved top-level comment format for it.
- Logic reviewers may cite cross-file evidence, but the postable location should still point to the changed line that introduced the risk.
- Inline posting requires a validated `DiffAnchor`; MVP renders inline candidates only and posts approved findings in a top-level PR comment.

## Priority

ReviewGraph should track priority separately from severity. Schemas store priority as an integer from `0` to `3`; renderers may display the labels below:

- `P0`: drop everything; release, data, security, or major usage is broadly broken.
- `P1`: urgent; should be fixed before the next release or merge cycle.
- `P2`: normal; should be fixed, but not an emergency.
- `P3`: low; useful but non-blocking.

Critical or request-changes recommendations require high confidence and concrete evidence. Medium-confidence findings may be postable only when they are concrete and non-blocking. Low-confidence or ambiguous issues cannot be blocking.

## Testing Findings

Testing reviewer output is postable only when it names changed behavior, a concrete regression scenario, and identifiable missing coverage. Generic "add tests" comments should become `local_note` or `non_finding`.

## Context Limits

ReviewGraph should calculate a context budget before reviewer fanout. The budget should cap changed files, patch bytes, conversation memory bytes, reviewer count, and live LLM calls per run. When input is truncated, reviewers receive explicit truncation markers and the final output includes a local note. Truncated context should make postable findings more conservative, not more speculative.

## Reviewer Skill Set

The first useful reviewer roster should include Codex-inspired passes:

- `correctness`: logic, edge cases, error handling, and user-visible behavior.
- `testing`: missing coverage for changed behavior and likely regression tests.
- `breaking_changes`: external integration surfaces such as CLI flags, config, APIs, persisted state, and protocol compatibility.
- `context_budget`: model-visible context growth, unbounded fragments, and prompt/cache hazards.
- `change_size`: whether a PR is too large to review well and how it could be split.
- `security`: auth, injection, secrets, SSRF, unsafe eval, path traversal, and trust boundaries.
- `docs_api`: docs, public API changes, migration notes, and contract drift.

These are reviewer contexts, not necessarily independent tool-using agents on day one.
