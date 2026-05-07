# ISSUE PLAN: AUR-241 Add Real Top-Level Comment Writer Adapter

Active issue plan for `AUR-241` / `RG-052: Add Real Top-Level Comment Writer Adapter`.

Linear is the durable source for status, blockers, and handoff. Durable behavior comes from `docs/architecture/side-effects.md`, `docs/architecture/github-integration.md`, `docs/architecture/state-graph.md`, `docs/harnesses/harness-engineering.md`, and `docs/prds/0007-side-effects.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-241`
- Title: `RG-052: Add Real Top-Level Comment Writer Adapter`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-07: none
- Upstream blockers complete: `AUR-244`, `AUR-218`, `AUR-217`, `AUR-219`, `AUR-243`, `AUR-220`, `AUR-221`, `AUR-245`, `AUR-246`, `AUR-223`, and `AUR-222`.
- Downstream issues: `AUR-224` owns manual live post smoke; `AUR-261` owns milestone closure.
- Linear description has stale wording from before AUR-222 review fixes: it says the writer receives a marker reconciliation plan and permits a second POST after an ambiguous accepted-write recovery scan. This issue will update Linear to match the current durable contract before completion.

## Objective

Implement the real top-level issue-comment writer adapter contract using fake transports only. The adapter should transform finalized writer input into the exact GitHub issue-comment POST request shape, execute it through an injected transport, and return structured writer results with redacted transport evidence.

This issue must not introduce live GitHub writes, a public production `--post` CLI, manual live smoke, formal PR reviews, inline comments, labels, statuses, approvals, request-changes writes, edits, deletes, or cross-process locking.

## Contracts To Preserve

- Dry-run remains the default and public CLI remains dry-run-only.
- The writer receives only `FinalizedIssueCommentWriterInput` after finalization-owned marker reconciliation returns `SAFE_TO_POST`.
- The writer does not receive a pre-write marker reconciliation plan and is not invoked for `RECONCILED_EXISTING`.
- The writer cannot accept raw candidate payloads, raw final payloads, formal PR review payloads, inline comment payloads, label/status/review/approval/request-changes payloads, or non-finalized state.
- The writer uses only `POST /repos/{owner}/{repo}/issues/{pr_number}/comments` with a JSON body containing the approved final comment body.
- The writer must validate the final issue-comment payload immediately before transport.
- Writer attempts must emit redacted transport summaries: endpoint/method class, retryability, stable failure code, request ID when available, and marker scan page/comment counts when recovery scans happen.
- Transport summaries must not include tokens, raw stderr, request headers, unredacted payload bodies, or unredacted comment bodies.
- Ambiguous accepted-write recovery is writer-local and only after a POST attempt may have reached GitHub. It uses shared marker parsing/reconciliation primitives and the finalized input's expected target/payload/findings hashes.
- After an ambiguous accepted-write outcome, a second POST is forbidden in the same approved run/retry sequence even if recovery finds no accepted artifact.
- Incomplete, empty, unavailable, timed-out, rate-limited, malformed, conflicting, or otherwise failed recovery scans return `FAILED` with stable error evidence and zero additional POSTs.
- If recovery finds a matching trusted marker, the writer returns `RECONCILED` or posted/reconciled evidence with zero additional POSTs.
- Multiple trusted identical markers reconcile with duplicate metadata and zero additional POSTs.

## Implementation Shape

1. Add `tests/test_github_writer.py` before implementation:
   - Reuse fixture helpers from `tests/test_fake_writer.py` only where the helper remains deterministic and does not couple to harness-only routes.
   - Cover request shape, endpoint, method, body, redaction, transport summary, posted result, validation failure, raw payload rejection, actor mismatch, and all ambiguous recovery paths.
2. Add `src/reviewgraph/writer_github.py`:
   - Define a narrow writer transport protocol for `post_issue_comment(owner_repo, pr_number, body, timeout_seconds)` and optional recovery marker scan transport compatible with existing marker pagination.
   - Define redacted transport summary/result structures if existing `GitHubWriterResult` is too small to preserve required evidence.
   - Accept only `FinalizedIssueCommentWriterInput`.
   - Validate `approved_actor`, target hash, payload hash, artifact kind, endpoint shape, and final payload validation before any transport call.
   - Build the issue-comment request as `POST /repos/{owner}/{repo}/issues/{pr_number}/comments` with body `{"body": final_payload.body}`.
   - Never store raw final body in result metadata.
3. Model writer transport outcomes:
   - `POSTED`: successful transport response with comment ID.
   - `FAILED`: writer-local validation failure, hard transport failure, unsafe response, trusted marker conflict, malformed trusted marker, incomplete recovery, empty recovery after ambiguous accepted-write, or forbidden second POST.
   - `RECONCILED`: ambiguous accepted-write recovery found an existing trusted matching marker; no new POST is made.
   - If new enum/status detail is needed to distinguish retryable unknown and transport failed without overloading `error`, add it narrowly and update tests/docs.
4. Implement ambiguous accepted-write recovery:
   - Transport may raise or return an explicit ambiguous accepted-write timeout outcome after one POST call.
   - The writer then performs a complete paginated marker recovery scan through the injected marker transport.
   - The scan uses `reconcile_paginated_trusted_markers(...)` with approved actor, trusted bot authors, and expected hashes from the finalized payload.
   - `RECONCILED_EXISTING` returns `GitHubWriterResult(status=RECONCILED, comment_id=existing_id, ...)`.
   - `SAFE_TO_POST` after recovery means no accepted artifact was found, but still returns fail-closed/retryable-unknown with zero additional POSTs.
   - `FAILED_CLOSED` returns failed/retryable evidence with zero additional POSTs.
5. Update durable docs narrowly:
   - `docs/architecture/github-integration.md` for real writer transport boundary and redacted request/result evidence.
   - `docs/architecture/side-effects.md` only if implementation reveals a missing durable rule.
   - `docs/harnesses/harness-engineering.md` for default fake-transport writer harness expectations.
   - `docs/prds/0007-side-effects.md` only if acceptance wording needs a durable correction.
6. Update Linear AUR-241 before completion:
   - Replace stale marker-plan and second-POST wording with finalized writer input plus no-second-POST recovery wording.
   - Add an evidence comment with commands, tests, fresh review result, and scope deferrals.

## Focused Harness

Create `tests/test_github_writer.py` covering:

- Real writer accepts valid finalized writer input and posts exactly one top-level issue comment through fake transport.
- Request shape is exactly `POST /repos/{owner}/{repo}/issues/{pr_number}/comments` with JSON body key `body`.
- Writer result includes status, artifact kind, target hash, payload hash, comment ID on success, and redacted transport summary evidence.
- Writer rejects raw final payloads, raw candidate payloads, non-issue-comment payloads, formal PR review-like shapes, and invalid final payload marker fields before transport.
- Writer rejects or fails actor mismatch before transport.
- Live network is not used by default tests.
- Successful transport response with missing/malformed comment ID fails with stable error and no raw body.
- Timeout/rate-limit/forbidden/not-found/unavailable/malformed-response/transport-unknown POST failures return stable redacted errors.
- Ambiguous accepted-write timeout performs exactly one recovery marker scan and zero additional POSTs.
- Ambiguous recovery with matching trusted marker returns reconciled existing and zero additional POSTs.
- Ambiguous recovery with duplicate trusted identical markers returns reconciled existing with duplicate metadata and zero additional POSTs.
- Ambiguous recovery with trusted conflicting marker fails closed and zero additional POSTs.
- Ambiguous recovery with incomplete pagination, timeout, rate limit, forbidden, not found, unavailable, malformed page, repeated cursor, page cap, comment cap, transport unknown, or marker-empty scan returns failed/retryable-unknown evidence and zero additional POSTs.
- Transport summaries are allowlisted and exclude raw body, raw stderr, request headers, and token-looking values.
- Public CLI still exposes no production `--post`.
- Default runner/import boundaries do not pull in the real writer unless an explicit harness or later live-post boundary imports it.

## Validation

Focused:

```bash
.venv/bin/python -m pytest tests/test_github_writer.py -q
```

Regression:

```bash
.venv/bin/python -m pytest tests/test_github_writer.py tests/test_fake_writer.py tests/test_post_mode_graph.py tests/test_marker_hardening.py tests/test_markers.py tests/test_payload_validation.py tests/test_contract_boundaries.py tests/test_cli.py -q
.venv/bin/python scripts/check_docs.py
git diff --check
.venv/bin/python -m py_compile src/reviewgraph/*.py
```

Run the full suite before completion:

```bash
.venv/bin/python -m pytest -q
```

## Out Of Scope

- Live GitHub write transport.
- Manual live post smoke.
- Public production post CLI.
- Formal PR reviews, inline comments, replies, labels, statuses, approvals, request-changes writes, editing/deleting comments, or automatic replies.
- Global cross-process duplicate prevention or external locks.
- Durable posted-comment storage.
