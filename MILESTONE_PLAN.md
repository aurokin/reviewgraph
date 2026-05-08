# MILESTONE PLAN: PRD 0007 Side Effects

Active execution artifact for this milestone. Linear remains the durable source for current issue status, milestone order, blockers, relationships, and handoff details. Repository docs remain the durable product, architecture, harness, and decision contracts. If Linear and durable docs disagree on behavior, stop and reconcile both before implementation. Re-fetch current Linear state before starting each issue.

## Linear Scope Snapshot

- Milestone: `PRD 0007: Side Effects`
- Milestone ID: `c6087171-c932-43a9-81b1-5cf3ddec025a`
- Current execution status as of 2026-05-08 after AUR-224 Linear completion: `AUR-244`, `AUR-218`, `AUR-217`, `AUR-219`, `AUR-243`, `AUR-220`, `AUR-221`, `AUR-245`, `AUR-246`, `AUR-223`, `AUR-222`, `AUR-241`, and `AUR-224` are done; `AUR-261` is the active milestone gate.
- Active implementation issues:
  - `AUR-244` / `RG-055: Define Payload Hash Domains And Golden Tests` / `Done`
  - `AUR-218` / `RG-029: Validate Top-Level Issue Comment Payloads` / `Done`
  - `AUR-217` / `RG-028: Model Item-Level Approval And Final Hash` / `Done`
  - `AUR-219` / `RG-030: Gate Posting On Actor And Permission` / `Done`
  - `AUR-243` / `RG-054: Bind Approval To Actor And Permission Snapshot` / `Done`
  - `AUR-220` / `RG-031: Fail Closed On Stale Review Target` / `Done`
  - `AUR-221` / `RG-032: Reconcile Embedded ReviewGraph Markers` / `Done`
  - `AUR-245` / `RG-056: Harden Marker Author Pagination Reconciliation` / `Done`
  - `AUR-246` / `RG-057: Block Non-Interactive Posting Mode` / `Done`
  - `AUR-223` / `RG-034: Suppress Writes With No Approved Findings` / `Done`
  - `AUR-222` / `RG-033: Implement Fake Top-Level Comment Writer` / `Done`
  - `AUR-241` / `RG-052: Add Real Top-Level Comment Writer Adapter` / `Done`
  - `AUR-224` / `RG-035: Add Manual Live Post Smoke Contract` / `Done`
- Gate issue:
  - `AUR-261` / `Complete PRD 0007: Side Effects` / `In Progress`
- Canceled duplicates known from earlier Linear inventory:
  - `AUR-248` / duplicate of `AUR-243` actor/permission approval binding scope; replacement coverage is approval snapshot binding and final actor/permission re-check.
  - `AUR-249` / duplicate of `AUR-244` payload hash domain scope; replacement coverage is canonical hash-domain primitives and golden tests.
  - `AUR-250` / duplicate of `AUR-245` hardened marker reconciliation scope; replacement coverage is pagination, author trust, malformed marker, conflict, and duplicate fingerprint hardening.
  - `AUR-251` / duplicate of `AUR-246` non-interactive posting block scope; replacement coverage is fail-closed non-TTY/CI/config-only post-mode gating.
- Downstream relation fetched during AUR-261 plan review:
  - `AUR-261` blocks `AUR-242` / `RG-053: Add Validation Command And Marker Contracts` in `PRD 0009: Harness Strategy`; do not start AUR-242 until PRD 0007 is closed.
- Linear descriptions for `AUR-219`, `AUR-243`, `AUR-245`, `AUR-246`, `AUR-222`, `AUR-241`, `AUR-224`, and `AUR-261` were tightened on 2026-05-07 so the high-risk side-effect guards in this plan are also represented in Linear.
- `AUR-228` from PRD 0005 was reconciled on 2026-05-07 as already implemented, with Linear evidence showing the context-budget and omitted-context harnesses pass. It no longer leaves the prior milestone chain inconsistent before PRD 0007 begins.
- The stale Linear blocker from `AUR-260` to `AUR-244` was removed on 2026-05-07 because live LLM work belongs to PRD 0008 and must not block PRD 0007 side-effect hash work.
- `AUR-218` now runs before `AUR-217` so the candidate/final payload schema split exists before approval final-hash binding.
- Linear blockers were also tightened on 2026-05-07: `AUR-244` blocks `AUR-218` and `AUR-221`; `AUR-218` blocks `AUR-217`.

## Milestone Intent

PRD 0007 introduces GitHub write behavior without weakening ReviewGraph's default dry-run posture. The milestone should prove that a GitHub write is reachable only after quality classification, posting-plan rendering, item-level human approval, final payload hash validation, actor/permission proof, target freshness proof, marker reconciliation, redaction, and idempotency checks.

The product point is controlled side effects. Reviewers do not write to GitHub, prompts do not decide whether to post, and candidate payloads are not final payloads. MVP writes only one approved top-level issue comment. Formal PR reviews, inline comments, labels, statuses, approvals, request changes, automatic replies, and hosted/webhook approval policies remain out of scope.

## Current Code Snapshot

- `src/reviewgraph/models.py` already defines schema primitives for `GitHubReviewPayload`, `ApprovalDecision`, `ActorPermissionGateResult`, `PayloadValidationResult`, `MarkerReconciliationResult`, `FinalizationStatus`, and `GitHubWriterResult`.
- `src/reviewgraph/posting.py` builds dry-run posting plans and candidate issue-comment payloads, validates MVP artifact kind, computes visible/full/findings hashes, and rejects public request-changes verdict text.
- `src/reviewgraph/runner.py` and `src/reviewgraph/targets.py` produce dry-run output and writer-call sentinel proof. Approval, finalization, marker reconciliation, and fake writer/post-mode harnesses now exist behind explicit non-default boundaries; public runs still do not expose a production post path.
- `docs/architecture/side-effects.md`, `docs/architecture/github-integration.md`, and `docs/architecture/state-graph.md` define the durable side-effect contract.
- Existing tests cover candidate/final payload construction, posting-plan local-only behavior, dry-run writer boundaries, approval/finalization gates, marker reconciliation, fake writer reachability, real writer adapter contracts with fake transports, manual live-post contract behavior with default-safe fake runners, payload schema primitives, redaction, and GitHub read/dry-run paths. Remaining PRD 0007 work must audit the milestone, refactor durable docs for agent handoff, and close the milestone gate.

## Execution Order

1. `AUR-244` first: define canonical payload hash domains and golden tests for visible body, full final body, marker payload hash, findings hash, newline normalization, marker whitespace, target ordering, and duplicate fingerprints. `marker.payload` equals `visible_body_hash(final_body_without_marker)`, while `final_payload_hash` equals the hash of the full final body including the exact marker line. Duplicate postable or approved finding fingerprints are fail-closed input errors, not deduplicated lists or multisets. Later approval, finalization, marker, and writer code must reuse these primitives.
2. `AUR-218` second: validate top-level issue-comment payloads and reject formal PR review payloads/endpoints. Final payload schema includes explicit marker components and marker line. Candidate payload schema carries candidate visible body and findings hash inputs only; it must not contain a final marker line, expose candidate-owned final hash semantics, or be accepted as writer input. This split is now implemented; future issues must preserve the separate candidate/final payload models.
3. `AUR-217` third: model item-level approval and final hash binding using the `AUR-244` hash primitives and the `AUR-218` candidate/final schema split. Approval records approved item IDs, review target binding, final full payload hash, actor metadata placeholders, and rejects stale candidate hashes before any writer exists.
4. `AUR-219` fourth: add actor and permission discovery/gate state for write mode. `ActorPermissionGateResult` is endpoint-specific for top-level issue-comment posting: authenticated actor, credential principal/source, repo or installation permission, ability to call `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`, check method, checked target, checked-at time, and stable failure code. Unknown actor, unknown credential source, unknown permission, insufficient endpoint permission, missing check timestamp, timeout, rate limit, forbidden, not found, unavailable, malformed response, or stale cached data blocks approval/posting with a redacted transport summary. Fake cases must include repo-role-write but token/app lacks issue-comment write ability.
5. `AUR-243` fifth: bind approval to the actor/permission snapshot from `AUR-219` and require finalization to verify the current actor/permission still matches before writer reachability. Re-check failures use the same fail-closed transport taxonomy as `AUR-219`; cached success cannot substitute for an unknown or failed current check.
6. `AUR-220` sixth: implement target freshness finalization gates. Head, base, merge-base, owner/repo, PR number, and diff-basis drift all fail closed with dry-run output before writer invocation. Target refetch timeout, rate limit, forbidden, not found, unavailable, malformed response, or stale cached data also fail closed with stable machine reason, retryability, request ID when available, and zero final payload construction or writer reachability. Finalization order is preflight first: validate approval shape, approved IDs, non-empty approved findings, and duplicate fingerprints; re-read actor, permission, and target freshness; then, only if those checks pass, build the final body/hash, validate redaction, reconcile markers, and release writer input.
7. `AUR-221` seventh: implement embedded ReviewGraph marker grammar, generation, parsing, and happy-path duplicate detection using the `AUR-244` hash-domain primitives. Marker recognition must be exact final-line only.
8. `AUR-245` eighth: harden marker reconciliation for pagination, author trust, spoofed markers, malformed trusted markers, conflicting payload hashes, and duplicate fingerprints.
9. `AUR-246` ninth: block non-interactive posting mode before any graph/CLI post path is introduced. CI, webhook, config-only, or non-TTY mode must hit a pre-approval fail-closed routing gate that returns structured output instead of blocking for input, inferring approval, or reaching final payload construction.
10. `AUR-223` tenth: prove no writer is invoked for missing approval, rejected approval, empty approvals, local-notes-only, suggested-reply-only, suppressed-only, and clarification-only runs. Mixed runs with approved findings must keep suggested replies out of candidate/final payloads.
11. `AUR-222` eleventh: implement the fake top-level issue-comment writer after payload, approval, finalization, freshness, marker, and non-interactive policy exist. This issue must include an end-to-end graph/CLI fake-post harness proving `run_mode=post` follows `render_review -> post_mode_interaction_gate -> approval_gate -> writer_release_preflight -> finalize_github_payload -> post_or_emit`: dry-run writes zero times; non-interactive post mode, missing/rejected approval, and empty approval write zero times; approved item-level payload reaches fake writer exactly once; stale target, unknown target freshness, actor mismatch, permission re-check failure, redaction failure, and marker conflict fail before writer reachability; graph trace/JSON records interaction gate, approval, writer-release preflight, actor/permission finalization check, target freshness check, finalization, payload hashes, marker reconciliation, and writer result.
12. `AUR-241` twelfth: implement the real top-level issue-comment writer adapter. It receives only finalized writer input after marker reconciliation returns `SAFE_TO_POST` and supports only `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`. It must model outcomes such as posted, blocked/fail-closed, retryable-unknown, and transport-failed; reconciled-existing remains a terminal no-post state produced before writer invocation. Fake-transport tests must cover ambiguous POST timeout after GitHub may have accepted the write, followed by writer-local recovery that rescans markers using shared marker primitives and the finalized input's expected hashes. A second POST after an ambiguous accepted-write timeout is forbidden in the same approved run/retry sequence, even if recovery finds no accepted artifact; if the scan is unavailable, incomplete, rate-limited, timed out, or marker-empty after an ambiguous POST, the writer returns fail-closed or retryable-unknown with no additional POST. This recovery scan is not the pre-write marker reconciliation plan and must not rebuild payloads, widen approval, or decide `SAFE_TO_POST`. PRD 0007 guarantees at most one POST per approved run/retry sequence, not global cross-process locking; if a later scan observes multiple trusted identical markers, it reconciles existing with a duplicate-marker note and still posts zero times. Trusted conflicting markers fail closed.
13. `AUR-224` thirteenth: add the manual-only live post smoke contract for disposable PRs. It must be opt-in, skipped by default, require a TTY/manual approval proof plus typed final-hash confirmation, restrict targets through an explicit allowlist and disposable PR marker convention, and prove top-level issue-comment-only behavior through the real writer with evidence of one POST max, marker seen/reconciled state, actor shown to the human, and final hash shown or matched. Live post must use live read-only finalization transports immediately before approval/finalization for actor, endpoint-specific permission, current PR target, and existing-comment marker pagination; fixture or fake state cannot satisfy the manual live proof.
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

For milestone gates and any issue that changes blockers/order, also run `python scripts/check_docs.py --backlog-export path/to/linear-backlog-export.json` against a canonical Linear export as described in `docs/implementation/README.md`.

## Harness Strategy

- `AUR-244` focused harness: payload hash domain and marker hash golden tests in `tests/test_payload_hashes.py`.
- `AUR-218` focused harness: payload validation tests rejecting formal PR reviews and non-issue-comment endpoints.
- `AUR-217` focused harness: approval model/final-hash binding tests using distinct candidate/final payload fixtures, likely in `tests/test_approval.py`.
- `AUR-219` focused harness: actor/permission gate tests with fake permission transport, endpoint-specific issue-comment write ability, transport failure taxonomy, stale-cache rejection, and role/token mismatch cases.
- `AUR-243` focused harness: approval actor/permission snapshot binding and finalization mismatch tests.
- `AUR-220` focused harness: stale target/freshness finalization tests with fake current target transport, transport failure taxonomy, stale-cache rejection, stable reason codes, and proof that final payload construction is unreachable on unknown freshness.
- `AUR-221` focused harness: marker generation/parsing/reconciliation happy path tests.
- `AUR-245` focused harness: marker pagination, trusted-author, spoofing, malformed marker, conflict, page cap/timeout/rate-limit, transport-summary, and duplicate-fingerprint tests.
- `AUR-246` focused harness: non-interactive post-mode rejection tests proving final payload construction is unreachable.
- `AUR-223` focused harness: no-approved-finding, missing/rejected approval, and local-only writer suppression tests.
- `AUR-222` focused harness: fake writer tests for finalized top-level issue comments, idempotent retry, and `run_mode=post` graph/CLI allowed-post proof with trace/JSON state assertions.
- `AUR-241` focused harness: real writer adapter construction and recovery/reconciliation tests with fake transport, including no-second-POST proof after ambiguous accepted-write outcomes, duplicate trusted identical marker observation, trusted conflict fail-closed behavior, and no live network in default tests.
- `AUR-224` focused harness: manual live-post smoke contract tests skipped by default, including disposable-target preflight, live read-only actor/permission/target/marker finalization proof, and typed confirmation proof.
- Full validation after shared side-effect changes:
  - `python -m pytest -q`
  - `python -m py_compile src/reviewgraph/*.py`
  - `python scripts/check_docs.py`
  - `git diff --check`

## Contract Guardrails

- Dry-run remains the default behavior.
- GitHub writes require explicit human approval.
- Candidate payloads are not final payloads and are not writer inputs.
- Candidate payloads carry candidate visible body and findings hash inputs only. They must not contain a final marker line.
- Final payloads carry explicit marker components and the exact marker line.
- Approval is item-level and binds to the final full issue-comment body hash after approved item selection.
- Approval is also bound to the review target, actor, permission, and checked-at time shown to the human.
- Actor and permission are endpoint-specific for top-level issue-comment posting, not a vague repository role string. Unknown credential source, missing endpoint write ability, failed transport, stale cached proof, or mismatched actor/permission blocks approval/posting.
- `finalize_github_payload` owns the last pre-writer gate: approval shape, approved IDs, non-empty approved findings, duplicate fingerprints, current actor, current permission, target freshness, final hash, redaction, and marker reconciliation.
- Final payload construction happens only after approval shape, approved IDs, non-empty/duplicate checks, current actor/permission, and current target freshness pass.
- External read failures during finalization fail closed. Timeout, rate limit, forbidden, not found, unavailable, malformed response, or stale cached data cannot fall back to an earlier success.
- The writer receives only finalized writer input after finalization-owned marker reconciliation returns `SAFE_TO_POST`; it must not own approval, freshness, marker policy, or reconciliation-plan decisions.
- MVP writer supports only top-level `issue_comment` payloads to `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`.
- Formal PR reviews, inline comments, replies, labels, statuses, approvals, and request-changes writes are rejected or deferred.
- Suggested replies are local-only and never eligible for candidate/final GitHub payloads in MVP.
- Empty approvals, local-note-only, suggested-reply-only, suppressed-only, and clarification-only runs never invoke a writer.
- Marker reconciliation must paginate existing comments or fail closed. Trusted marker conflicts fail closed; untrusted/spoofed markers are ignored.
- Marker trust is restricted to the approved actor or configured trusted ReviewGraph bot. It may reuse GitHub identity/provenance parsing, but it must not treat every trusted PR commenter as a trusted marker author.
- Marker scans, actor/permission checks, and writer attempts must emit redacted transport summaries with endpoint kind, page count, retryability, stable failure code, and request ID when available. They must not log tokens, raw stderr, or unredacted payload bodies.
- Marker and writer pagination must have explicit page caps, timeout handling, rate-limit classification, and fail-closed output for long PR comment histories.
- Non-interactive mode cannot infer approval from config, CI, webhook context, or non-TTY execution.
- Non-interactive post attempts fail closed before approval prompt/input and before final payload construction.
- Live post smoke is manual-only, allowlisted-disposable-PR-only, typed-final-hash-confirmed, one-POST-max, and skipped by default.
- Live post smoke must prove actor, endpoint-specific permission, target freshness, and marker pagination came from live read-only finalization transports immediately before approval/finalization.
- Idempotency is retry-safe per approved run/retry sequence. Cross-process duplicate prevention requires external locking or storage and is deferred; later duplicate trusted identical markers reconcile without another POST, while trusted conflicts fail closed.

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
- Duplicate postable or approved finding fingerprints are rejected before marker generation, approval final-hash validation, or writer reachability.
- Approval stores approved item IDs, target binding, final full payload hash, actor, permission, checked-at time, approver, timestamp, and public-verdict choice.
- Approving a subset changes the final payload hash and stale candidate hashes are rejected.
- Top-level issue-comment payloads are the only MVP GitHub artifact accepted.
- Formal PR review payloads, `/pulls/{pr}/reviews`, `COMMENT`, `APPROVE`, `REQUEST_CHANGES`, labels, statuses, inline comments, and replies are rejected or deferred.
- Actor/permission discovery is shown before approval and blocks approval/posting when unknown or insufficient.
- Actor/permission discovery proves endpoint-specific issue-comment write ability and fails closed for transport failures, stale cached proof, unknown credential source, or role/token mismatches.
- Finalization fails closed if actor, permission, target, redaction, payload hash, marker reconciliation, or approved finding set is invalid.
- Finalization also fails closed if current actor/permission or target freshness cannot be re-read from the required transport with a current, redacted, stable result.
- Marker generation/parsing/reconciliation is exact, paginated, author-aware, idempotent, and fail-closed on trusted conflicts.
- No-approved-finding and local-only paths never invoke writer code.
- Fake writer proves approved finalized top-level comments create at most one fake comment and reconcile retries.
- Writer idempotency is scoped to one approved run/retry sequence; concurrent independent runs are documented as deferred global-locking scope.
- Non-interactive post mode cannot approve or post by config alone.
- Graph/CLI post mode proves the real side-effect route with fake writer: dry-run and blocked paths call writer zero times, approved item-level payload calls fake writer once, and state/trace records approval, finalization, hashes, marker reconciliation, and writer result.
- Real writer adapter supports only finalized top-level issue comments and handles ambiguous accepted-write timeouts through writer-local marker recovery with no second POST in the same approved run/retry sequence.
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
