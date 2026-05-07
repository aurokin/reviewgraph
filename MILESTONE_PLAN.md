# MILESTONE PLAN: PRD 0007 Side Effects

Active execution artifact for this milestone. Linear remains the durable source for issue status, milestone order, blockers, relationships, and handoff details; if this file conflicts with Linear, Linear wins. Re-fetch current Linear state before starting each issue.

## Linear Scope Snapshot

- Milestone: `PRD 0007: Side Effects`
- Milestone ID: `c6087171-c932-43a9-81b1-5cf3ddec025a`
- Current execution status as of 2026-05-07: all active implementation issues are `Backlog`; `AUR-261` is the milestone gate.
- Active implementation issues:
  - `AUR-244` / `RG-055: Define Payload Hash Domains And Golden Tests` / `Backlog`
  - `AUR-217` / `RG-028: Model Item-Level Approval And Final Hash` / `Backlog`
  - `AUR-218` / `RG-029: Validate Top-Level Issue Comment Payloads` / `Backlog`
  - `AUR-219` / `RG-030: Gate Posting On Actor And Permission` / `Backlog`
  - `AUR-243` / `RG-054: Bind Approval To Actor And Permission Snapshot` / `Backlog`
  - `AUR-220` / `RG-031: Fail Closed On Stale Review Target` / `Backlog`
  - `AUR-221` / `RG-032: Reconcile Embedded ReviewGraph Markers` / `Backlog`
  - `AUR-245` / `RG-056: Harden Marker Author Pagination Reconciliation` / `Backlog`
  - `AUR-246` / `RG-057: Block Non-Interactive Posting Mode` / `Backlog`
  - `AUR-223` / `RG-034: Suppress Writes With No Approved Findings` / `Backlog`
  - `AUR-222` / `RG-033: Implement Fake Top-Level Comment Writer` / `Backlog`
  - `AUR-241` / `RG-052: Add Real Top-Level Comment Writer Adapter` / `Backlog`
  - `AUR-224` / `RG-035: Add Manual Live Post Smoke Contract` / `Backlog`
- Gate issue:
  - `AUR-261` / `Complete PRD 0007: Side Effects` / `Backlog`
- Canceled duplicates known from earlier Linear inventory:
  - `AUR-248` / duplicate of actor/permission approval binding scope
  - `AUR-249` / duplicate of payload hash domain scope
  - `AUR-250` / duplicate of hardened marker reconciliation scope
  - `AUR-251` / duplicate of non-interactive posting block scope

## Milestone Intent

PRD 0007 introduces GitHub write behavior without weakening ReviewGraph's default dry-run posture. The milestone should prove that a GitHub write is reachable only after quality classification, posting-plan rendering, item-level human approval, final payload hash validation, actor/permission proof, target freshness proof, marker reconciliation, redaction, and idempotency checks.

The product point is controlled side effects. Reviewers do not write to GitHub, prompts do not decide whether to post, and candidate payloads are not final payloads. MVP writes only one approved top-level issue comment. Formal PR reviews, inline comments, labels, statuses, approvals, request changes, automatic replies, and hosted/webhook approval policies remain out of scope.

## Current Code Snapshot

- `src/reviewgraph/models.py` already defines schema primitives for `GitHubReviewPayload`, `ApprovalDecision`, `ActorPermissionGateResult`, `PayloadValidationResult`, `MarkerReconciliationResult`, `FinalizationStatus`, and `GitHubWriterResult`.
- `src/reviewgraph/posting.py` builds dry-run posting plans and candidate issue-comment payloads, validates MVP artifact kind, computes visible/full/findings hashes, and rejects public request-changes verdict text.
- `src/reviewgraph/runner.py` and `src/reviewgraph/targets.py` produce dry-run output and writer-call sentinel proof, but do not yet implement post mode, approval, finalization, marker reconciliation, or writer adapters.
- `docs/architecture/side-effects.md`, `docs/architecture/github-integration.md`, and `docs/architecture/state-graph.md` define the durable side-effect contract.
- Existing tests cover candidate payload construction, posting-plan local-only behavior, dry-run writer boundaries, payload schema primitives, redaction, and GitHub read/dry-run paths. PRD 0007 must add approval/finalization/writer harnesses without making default runs post.

## Execution Order

1. `AUR-244` first: define canonical payload hash domains and golden tests for visible body, full final body, marker payload hash, findings hash, newline normalization, marker whitespace, target ordering, and duplicate fingerprints. Later approval, finalization, marker, and writer code must reuse these primitives.
2. `AUR-217` second: model item-level approval and final hash binding using the `AUR-244` hash primitives. Approval records approved item IDs, review target binding, final full payload hash, actor metadata placeholders, and rejects stale candidate hashes before any writer exists.
3. `AUR-218` third: validate top-level issue-comment payloads and reject formal PR review payloads/endpoints. Candidate and final payload schemas should include marker fields and remain redacted before any side-effect adapter sees them.
4. `AUR-219` fourth: add actor and permission discovery/gate state for write mode. Unknown actor, unknown permission, insufficient permission, or missing check timestamp blocks approval/posting.
5. `AUR-243` fifth: bind approval to the actor/permission snapshot from `AUR-219` and require finalization to verify the current actor/permission still matches before writer reachability.
6. `AUR-220` sixth: implement target freshness finalization gates. Head, base, merge-base, owner/repo, PR number, and diff-basis drift all fail closed with dry-run output before writer invocation.
7. `AUR-221` seventh: implement embedded ReviewGraph marker grammar, generation, parsing, and happy-path duplicate detection. Marker recognition must be exact final-line only.
8. `AUR-245` eighth: harden marker reconciliation for pagination, author trust, spoofed markers, malformed trusted markers, conflicting payload hashes, and duplicate fingerprints.
9. `AUR-246` ninth: block non-interactive posting mode before any graph/CLI post path is introduced. CI, webhook, config-only, or non-TTY mode cannot infer approval or reach final payload construction.
10. `AUR-223` tenth: prove no writer is invoked for missing approval, rejected approval, empty approvals, local-notes-only, suggested-reply-only, suppressed-only, and clarification-only runs. Mixed runs with approved findings must keep suggested replies out of candidate/final payloads.
11. `AUR-222` eleventh: implement the fake top-level issue-comment writer after payload, approval, finalization, freshness, marker, and non-interactive policy exist. This issue must include an end-to-end graph/CLI fake-post harness proving `render_review -> approval_gate -> finalize_github_payload -> post_or_emit`: dry-run writes zero times; missing/rejected approval writes zero times; approved item-level payload reaches fake writer once; stale target, actor mismatch, redaction failure, marker conflict, and empty approval fail before writer reachability; graph trace/JSON records approval, finalization, payload hashes, marker reconciliation, and writer result.
12. `AUR-241` twelfth: implement the real top-level issue-comment writer adapter. It receives only finalized payloads plus marker reconciliation plans and supports only `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`. It must model outcomes such as posted, reconciled-existing, blocked/fail-closed, retryable-unknown, and transport-failed. Fake-transport tests must cover ambiguous POST timeout after GitHub may have accepted the write, followed by paginated marker rescan and zero additional POSTs on retry.
13. `AUR-224` thirteenth: add the manual-only live post smoke contract for disposable PRs. It must be opt-in, skipped by default, require a TTY/manual approval proof plus typed final-hash confirmation, restrict targets through an explicit allowlist and disposable PR marker convention, and prove top-level issue-comment-only behavior through the real writer with evidence of one POST max, marker seen/reconciled state, actor shown to the human, and final hash shown or matched.
14. `AUR-261` last: close the milestone only after every active implementation issue is `Done`, focused/full validation passes, durable docs explain the final side-effect contracts, Linear evidence is complete, and fresh subagent review reports no material gaps.

## Issue Workflow

For each issue:

1. Re-fetch the issue, comments, blockers, and current milestone state from Linear.
2. Move the issue to `In Progress`.
3. Replace `ISSUE_PLAN.md` with a narrow plan for that issue and commit it before implementation.
4. Use fresh subagents to review the issue plan before code changes.
5. Implement the smallest contract/harness slice that satisfies the issue and does not implement later milestone scope.
6. Run the issue harness named by Linear plus regression tests covering touched shared behavior.
7. Use fresh subagents for code/docs review until no material findings remain.
8. Commit the completed issue, and commit separately after every review-fix batch.
9. Move the issue to `In Review`, add a Linear evidence comment with commands and artifact coverage, then move it to `Done` only when acceptance criteria are mapped to concrete evidence.

## Harness Strategy

- `AUR-244` focused harness: payload hash domain and marker hash golden tests, likely in `tests/test_posting_hashes.py` or `tests/test_posting.py`.
- `AUR-217` focused harness: approval model/final-hash binding tests, likely in `tests/test_approval.py`.
- `AUR-218` focused harness: payload validation tests rejecting formal PR reviews and non-issue-comment endpoints.
- `AUR-219` focused harness: actor/permission gate tests with fake permission transport.
- `AUR-243` focused harness: approval actor/permission snapshot binding and finalization mismatch tests.
- `AUR-220` focused harness: stale target/freshness finalization tests with fake current target transport.
- `AUR-221` focused harness: marker generation/parsing/reconciliation happy path tests.
- `AUR-245` focused harness: marker pagination, trusted-author, spoofing, malformed marker, conflict, page cap/timeout/rate-limit, transport-summary, and duplicate-fingerprint tests.
- `AUR-246` focused harness: non-interactive post-mode rejection tests proving final payload construction is unreachable.
- `AUR-223` focused harness: no-approved-finding, missing/rejected approval, and local-only writer suppression tests.
- `AUR-222` focused harness: fake writer tests for finalized top-level issue comments, idempotent retry, and graph/CLI allowed-post proof with trace/JSON state assertions.
- `AUR-241` focused harness: real writer adapter construction and retry/reconciliation tests with fake transport; no live network in default tests.
- `AUR-224` focused harness: manual live-post smoke contract tests skipped by default, including disposable-target preflight and typed confirmation proof.
- Full validation after shared side-effect changes:
  - `python -m pytest -q`
  - `python -m py_compile src/reviewgraph/*.py`
  - `python scripts/check_docs.py`
  - `git diff --check`

## Contract Guardrails

- Dry-run remains the default behavior.
- GitHub writes require explicit human approval.
- Candidate payloads are not final payloads and are not writer inputs.
- Approval is item-level and binds to the final full issue-comment body hash after approved item selection.
- Approval is also bound to the review target, actor, permission, and checked-at time shown to the human.
- `finalize_github_payload` owns the last pre-writer gate: final hash, actor, permission, target freshness, redaction, non-empty approved findings, and marker reconciliation.
- The writer receives only finalized payloads plus marker reconciliation plan; it must not own approval/freshness/policy decisions.
- MVP writer supports only top-level `issue_comment` payloads to `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`.
- Formal PR reviews, inline comments, replies, labels, statuses, approvals, and request-changes writes are rejected or deferred.
- Suggested replies are local-only and never eligible for candidate/final GitHub payloads in MVP.
- Empty approvals, local-note-only, suggested-reply-only, suppressed-only, and clarification-only runs never invoke a writer.
- Marker reconciliation must paginate existing comments or fail closed. Trusted marker conflicts fail closed; untrusted/spoofed markers are ignored.
- Marker scans, actor/permission checks, and writer attempts must emit redacted transport summaries with endpoint kind, page count, retryability, stable failure code, and request ID when available. They must not log tokens, raw stderr, or unredacted payload bodies.
- Marker and writer pagination must have explicit page caps, timeout handling, rate-limit classification, and fail-closed output for long PR comment histories.
- Non-interactive mode cannot infer approval from config, CI, webhook context, or non-TTY execution.
- Live post smoke is manual-only, allowlisted-disposable-PR-only, typed-final-hash-confirmed, one-POST-max, and skipped by default.

## Documentation Work

Update the narrowest durable docs alongside behavior:

- Approval/finalization, actor/permission, target freshness, non-interactive policy, no-approved-finding behavior, and writer reachability belong in `docs/architecture/side-effects.md` and `docs/architecture/state-graph.md`.
- GitHub artifact kinds, endpoints, marker grammar, marker reconciliation, and real writer adapter posture belong in `docs/architecture/github-integration.md`.
- Harness expectations for approval, finalization, fake writer, real writer construction, and manual live post belong in `docs/harnesses/harness-engineering.md`.
- Implementation sequencing belongs in `docs/plans/implementation-plan.md` only if the project phase narrative changes materially.
- Durable tradeoffs belong in `docs/decisions/` only when future agents need to preserve the decision.

## PRD 0007 Acceptance Surface

The milestone is complete when ReviewGraph proves:

- Payload hash domains are canonical and covered by golden tests.
- Approval stores approved item IDs, target binding, final full payload hash, actor, permission, checked-at time, approver, timestamp, and public-verdict choice.
- Approving a subset changes the final payload hash and stale candidate hashes are rejected.
- Top-level issue-comment payloads are the only MVP GitHub artifact accepted.
- Formal PR review payloads, `/pulls/{pr}/reviews`, `COMMENT`, `APPROVE`, `REQUEST_CHANGES`, labels, statuses, inline comments, and replies are rejected or deferred.
- Actor/permission discovery is shown before approval and blocks approval/posting when unknown or insufficient.
- Finalization fails closed if actor, permission, target, redaction, payload hash, marker reconciliation, or approved finding set is invalid.
- Marker generation/parsing/reconciliation is exact, paginated, author-aware, idempotent, and fail-closed on trusted conflicts.
- No-approved-finding and local-only paths never invoke writer code.
- Fake writer proves approved finalized top-level comments create at most one fake comment and reconcile retries.
- Non-interactive post mode cannot approve or post by config alone.
- Graph/CLI post mode proves the real side-effect route with fake writer: dry-run and blocked paths call writer zero times, approved item-level payload calls fake writer once, and state/trace records approval, finalization, hashes, marker reconciliation, and writer result.
- Real writer adapter supports only finalized top-level issue comments and reconciles ambiguous accepted-write timeouts by rescanning markers before retrying.
- Manual live post smoke is opt-in, skipped by default, requires explicit TTY/human approval and typed final-hash confirmation, and targets allowlisted disposable PRs only.

## Deferred Scope

- Formal GitHub reviews, inline comments, labels, statuses, approvals, request changes, editing/deleting comments, automatic replies, hosted webhooks, and long-term storage remain out of scope.
- Live LLM behavior remains PRD 0008.
- Broad harness strategy backlog remains PRD 0009.

## Milestone Completion Criteria

`AUR-261` can close only when:

- Every active implementation issue listed in this plan is `Done` in Linear with an evidence comment.
- Known canceled duplicate issues are documented with explicit duplicate rationale.
- A fresh Linear milestone inventory proves every active PRD 0007 blocker is complete or has an explicit stale/canceled/not-applicable rationale in Linear.
- Focused validation for all PRD 0007 harness families passes.
- Fixture/CLI, quality/boundary, GitHub read, full validation, docs check, py-compile, and diff check pass.
- Durable docs explain the final side-effect, approval, finalization, marker, fake writer, real writer, and manual live-post contracts an implementation agent needs when dropping into the repo.
- Fresh subagent review of code, tests, docs, Linear evidence, and the milestone gate reports no material issues.
- Default commands still cannot write to GitHub, call live LLMs, or require credentials.
- No `.ws/` or temporary export artifacts remain.
