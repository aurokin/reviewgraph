# Harness Engineering

Harnesses prove the product contract without requiring live GitHub or live LLM calls.

## Confidence ladder

Use the lightest harness that proves the change.

1. **Schema harness** — validate config, PR context, findings, verdicts, and payload models.
2. **Memory harness** — fixture PR comments and review threads become structured conversation memory.
3. **Routing harness** — fixture PRs select the expected reviewer agents with expected stages and reasons.
4. **Reviewer harness** — deterministic fake LLM responses normalize into findings, local notes, suppressed output, or clarification requests.
5. **Quality harness** — finding eligibility classifies postable findings separately from local advice and non-findings.
6. **Verdict harness** — high-confidence findings can affect local verdicts; low-confidence and ambiguous findings cannot.
7. **Graph harness** — full LangGraph run with fixture GitHub adapter and fake reviewer runners.
8. **Dry-run CLI harness** — command produces markdown + JSON and performs no side effects.
9. **Approval harness** — rejected approval never calls GitHub writer; approved approval creates at most one top-level PR comment for the approved payload.
10. **Live read smoke** — fetch a real public PR in read-only mode.
11. **Live post smoke** — only against a disposable test PR, after explicit human approval.

## Fixture PRs

Maintain fixtures under `tests/fixtures/prs/` once implementation starts:

- `frontend-state-change.json`
- `security-sensitive-change.json`
- `docs-only-change.json`
- `mixed-risk-change.json`
- `ambiguous-logic-change.json`
- `breaking-api-change.json`
- `oversized-change.json`
- `stale-approval-change.json`
- `untrusted-comment-injection.json`
- `paginated-github-read.json`

Each fixture should include metadata, labels, changed files, patch snippets, PR comments, review comments, and resolved/unresolved thread state when relevant.

## Tracer bullets

Build early vertical slices that exercise the graph end to end before expanding every policy:

1. **Fixture dry run:** fixture PR -> conversation memory -> always-on reviewers -> markdown/JSON -> no writer call.
2. **Specialized reviewer:** path or diff trigger introduces a security/frontend reviewer with recorded stage and reason.
3. **Logic ambiguity:** a logic reviewer returns a clarification request; graph stops before verdict/posting.
4. **Clarification resume:** a supplied human answer is recorded in state and the graph resumes review.
5. **Quality gate:** fake reviewer output is split into postable finding, local note, and suppressed non-finding.
6. **Allowed post proof:** item-approved top-level PR comment payload calls the fake GitHub writer once; rejected approval calls it zero times.

## Required tests before MVP is complete

- Config validation rejects unknown trigger fields.
- Config validation rejects `triggers.stages`; `stages` is valid only as a top-level agent field.
- Config validation rejects `verdict_power: approve` for MVP.
- Path triggers select matching reviewers.
- Diff patterns select matching reviewers.
- Always-on reviewers are selected for every PR.
- Stage eligibility is recorded for every selected reviewer.
- Stage cursor initializes with `active_stage=None` and advances to `initial_triage` before reviewer selection.
- `stage_queue` contains only future normal stages and completed stages are never rerun.
- Clarification resume restores the suspended source stage without popping an unrelated queued stage.
- PR comments and review threads are available as structured memory.
- Trusted/untrusted review authors are distinguished before comments become actionable feedback.
- Reviewer capabilities default to read-only and cannot call GitHub writers.
- Shipped example config validates.
- Failed optional reviewer records an error and continues.
- Failed required reviewer prevents posting.
- Low-confidence finding cannot request changes.
- Ambiguous mergeability issue becomes a clarification request, not a high-confidence finding.
- Generic finding without PR-specific evidence is suppressed.
- Reviewer self-declared postability/blocking is ignored by the quality gate.
- Generic missing-test feedback becomes a local note or non-finding.
- Finding introduced outside the PR diff is not postable.
- Postable finding includes a short changed-line location.
- Large PR fixture receives bounded reviewer context and emits truncation local notes.
- Context budget enforces reviewer-count and live-call caps deterministically, with local notes for skipped/deferred reviewers.
- Pagination fixtures prove GitHub files, issue comments, review comments, reviews, and review-thread state fetch all pages before truncation logic runs.
- Untrusted PR comments cannot trigger `conversation_patterns` routing.
- Unlisted review bot comments remain passive memory by default.
- Secret-like diff/comment content is redacted from logs, traces, JSON errors, and default output.
- Secret-like diff/comment content is redacted from rendered markdown and candidate/final GitHub payloads.
- Dry-run mode never invokes GitHub writer.
- Approval rejection never invokes GitHub writer.
- Approval acceptance creates at most one top-level PR comment artifact for the approved payload and does not duplicate finding fingerprints.
- Approval with no approved findings, local notes only, or suppressed findings only never invokes GitHub writer.
- Approval subset hashes bind to the final issue-comment body; stale candidate hashes are rejected.
- MVP payload schema rejects `event: COMMENT` and `/pulls/{pr}/reviews` endpoints.
- Unknown authenticated GitHub actor or insufficient/unknown permission blocks approval/posting.
- Local request-changes recommendation does not submit GitHub `REQUEST_CHANGES`.
- Stale head/base SHA between approval and posting prevents writer invocation.
- Retry after writer timeout reconciles by embedded ReviewGraph marker and does not duplicate comments.
- Fake writer seeded with an existing ReviewGraph marker skips duplicate posting after process restart.

## Live API discipline

Live tests are opt-in. They must never run as part of default test commands.

Recommended future commands:

```bash
pytest
pytest -m live_read
pytest -m live_post --requires-human-approval
```
