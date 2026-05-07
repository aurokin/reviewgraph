# ISSUE PLAN: AUR-222 Implement Fake Top-Level Comment Writer

Active issue plan for `AUR-222` / `RG-033: Implement Fake Top-Level Comment Writer`.

Linear is the durable source for status, blockers, and handoff. Durable behavior comes from `docs/architecture/side-effects.md`, `docs/architecture/state-graph.md`, `docs/architecture/github-integration.md`, `docs/harnesses/harness-engineering.md`, and `docs/prds/0007-side-effects.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-222`
- Title: `RG-033: Implement Fake Top-Level Comment Writer`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-07: none
- Upstream blockers complete: `AUR-244`, `AUR-218`, `AUR-217`, `AUR-219`, `AUR-243`, `AUR-220`, `AUR-221`, `AUR-245`, `AUR-246`, and `AUR-223`.
- Downstream issues: `AUR-241` owns the real GitHub writer adapter; `AUR-224` owns manual live post smoke; `AUR-261` owns milestone closure.

## Objective

Implement the fake top-level issue-comment writer and a harness-only post-mode path proving that writer reachability happens only after explicit interaction gating, item-level approval, writer-release preflight, finalization, marker reconciliation, and final payload validation.

This issue should create the first approved-post vertical slice, but it must stay fake and deterministic. Public dry-run behavior remains default, public CLI must still expose no production `--post` surface, and no live GitHub write adapter is introduced.

## Contracts To Preserve

- Dry-run is still the default and never calls any writer.
- Public CLI remains dry-run-only unless a harness-only entry point already exists or is explicitly hidden from normal users.
- Non-interactive post mode still fails before approval/final payload construction/writer reachability.
- Approval stays item-level and uses `approved_item_ids`.
- `writer_release_preflight` must pass before finalization and still records `writer_input_released=false`.
- `finalize_github_payload(...)` owns current actor/permission re-check, target freshness, payload hash validation, marker reconciliation, and final writer-input release.
- Only builder-owned `FinalizedIssueCommentWriterInput` wrapping a validated top-level `issue_comment` final payload can reach the fake writer.
- Candidate payloads, formal PR review payloads, inline comments, labels, statuses, approvals, request-changes writes, suggested replies, local notes, suppressed outputs, and clarification requests cannot reach the fake writer.
- Marker reconciliation must complete before posting. `SAFE_TO_POST` may release writer input; `RECONCILED_EXISTING` is terminal no-post/reconciled; `FAILED_CLOSED` blocks writer calls.
- `writer_result.status=RECONCILED` means the post path ended reconciled from marker state with no writer invocation. It is synthesized by `post_or_emit` from finalization/marker state, not returned by the fake writer.
- Fake writer invocation requires a narrow `FinalizedIssueCommentWriterInput` produced only after `finalize_github_payload(...)` reaches `FINALIZED` with marker reconciliation `SAFE_TO_POST`. A structurally valid `FinalIssueCommentPayload` alone is not writer input.
- Retry safety is scoped to one approved run/retry sequence. No cross-process locking or global dedupe claim.
- Real GitHub writer transport, live post smoke, manual disposable PR allowlists, and production post CLI are out of scope.

## Implementation Shape

1. Add focused fake writer tests before implementation:
   - `tests/test_fake_writer.py` owns the writer adapter contract.
   - `tests/test_post_mode_graph.py` owns the approved-post harness route and fail-closed zero-writer cases.
   - Reuse existing approval, permission, target freshness, marker, and payload fixture helpers where possible instead of creating parallel models.
2. Add `src/reviewgraph/writer_fake.py`:
   - Provide a deterministic in-memory fake issue-comment transport/writer.
   - Accept only `FinalizedIssueCommentWriterInput`, not raw `FinalIssueCommentPayload`.
   - `FinalizedIssueCommentWriterInput` must carry the final payload, final payload hash, target hash, marker reconciliation status/reason, approved actor, and body-free run metadata needed for result/debug output.
   - Construct `FinalizedIssueCommentWriterInput` only from a finalization result with `state=FINALIZED`, `writer_input_released=true`, `marker_reconciliation.status=SAFE_TO_POST`, and matching final payload/hash values.
   - Validate final issue-comment payloads with `validate_final_issue_comment_payload(...)` immediately before recording a fake write.
   - Reject candidate payloads, formal PR review-like shapes, non-issue-comment artifact kinds, missing final marker lines, invalid hashes, and marker-field mismatches.
   - Reject raw valid final payloads, `NOT_READY`, `FAILED_CLOSED`, `RECONCILED_EXISTING`, missing marker reconciliation, non-`SAFE_TO_POST`, or `writer_input_released=false` state before any fake transport call.
   - Return `GitHubWriterResult(status=POSTED, artifact_kind=issue_comment, target_hash=..., payload_hash=..., comment_id=...)` on fake posts.
   - Return `GitHubWriterResult(status=FAILED, ..., error=stable_reason)` only for writer-local validation/transport failures after finalization released writer input.
   - Never return `RECONCILED`; the fake writer is not invoked for marker-reconciled no-post paths.
   - Record no raw body text in result metadata; fake transport storage may keep body for marker retry simulation in test-only memory.
3. Extend finalization for marker-aware writer release:
   - Keep existing approval preflight first.
   - Continue actor/permission and target freshness checks before body construction.
   - Add a shared final-body/payload builder boundary used by both `build_approval_proof(...)` and finalization so approved final hashes cannot drift through duplicated body construction.
   - Build the final issue-comment payload with the shared builder only after preflight passes.
   - Validate the final payload and ensure `payload.final_payload_hash == approval.approved_final_payload_hash`.
   - Invoke marker reconciliation after the final payload is built using the freshly computed target hash, final visible payload hash, and findings hash.
   - Do not accept an unbound precomputed `MarkerReconciliationResult` unless it carries or is wrapped with the exact expected target/payload/findings hash inputs and finalization verifies those bindings.
   - If marker reconciliation is `SAFE_TO_POST`, set `finalization_status.state=FINALIZED`, set `final_payload`, set `final_payload_hash`, store `payload_validation`, store `marker_reconciliation`, and set `writer_input_released=true`.
   - Add explicit finalization reason codes for marker terminal states, such as `MARKER_RECONCILED_EXISTING` and `MARKER_RECONCILIATION_FAILED`; do not reuse `MARKER_RECONCILIATION_DEFERRED` after marker reconciliation has actually run.
   - If marker reconciliation is `RECONCILED_EXISTING`, set finalization to terminal no-post state with the reconciled-existing reason, do not release writer input, and expose enough state for `post_or_emit` to synthesize `GitHubWriterResult(status=RECONCILED, ..., comment_id=existing_id)` with writer call count zero.
   - If marker reconciliation is `FAILED_CLOSED`, set `finalization_status.state=FAILED_CLOSED`, use the marker-failed finalization reason, include `marker_reconciliation.reason_code` in dry-run error evidence, and leave `final_payload`, `final_payload_hash`, and writer input unset.
   - Preserve the existing `MARKER_RECONCILIATION_DEFERRED` behavior only when the caller has not supplied marker reconciliation yet; that state must not reach the writer.
4. Add a harness-only approved post route:
   - Prefer a small pure function such as `run_fixture_fake_post_attempt(...)` or `run_fake_post_harness(...)` over exposing production CLI posting.
   - Route order must be visible in `graph_trace`: `render_review -> post_mode_interaction_gate -> approval_gate -> writer_release_preflight -> finalize_github_payload -> post_or_emit`.
   - The harness supplies deterministic interactive approval, current actor/permission probe, target freshness probe, marker scan transport, finalized writer-input builder, and fake writer.
   - JSON records `post_interaction_gate`, `approval`, `writer_release_preflight`, `actor_permission_finalization_check`, `target_freshness_check`, `payload_validation`, `marker_reconciliation`, `finalization_status`, `final_payload_hash`, and `writer_result`.
   - Approved valid item-level payload reaches fake writer exactly once.
   - `post_or_emit` defensively rejects any state where `final_github_payload` is present but `finalization_status.state != FINALIZED`, marker reconciliation is not `SAFE_TO_POST`, or `writer_input_released=false`; those states record no writer call.
   - Dry-run and all blocked post attempts record `writer_called=false`, `writer_call_count=0`, and typed no-post reason evidence distinguishing dry-run, reconciled-existing, marker-failed, and other fail-closed states.
5. Prove no writer reachability in blocked paths:
   - Dry-run.
   - Non-interactive post mode.
   - Missing approval.
   - Rejected approval.
   - Empty approval/failure build.
   - No approved public findings.
   - Stale target.
   - Unknown target freshness/read failure.
   - Actor mismatch.
   - Permission re-check failure.
   - Final payload hash/redaction/validation failure.
   - Marker conflict, trusted malformed marker, incomplete pagination, timeout/rate limit/forbidden/not found/unavailable/malformed marker page.
6. Prove retry/idempotency behavior in fake storage:
   - First approved attempt with `SAFE_TO_POST` stores one fake comment.
   - Retrying the same approved payload scans the stored marker and returns reconciled existing with zero new fake posts.
   - Ambiguous accepted-write timeout simulation is deferred to `AUR-241`; AUR-222 proves only deterministic fake retry after an already stored marker reconciles without another fake post.
   - Trusted duplicate matching markers return reconciled existing with duplicate metadata and post zero additional comments.
   - Trusted same target/findings but different payload hash fails closed before writer post.
7. Update narrow durable docs:
   - `docs/architecture/side-effects.md` for fake writer handoff and marker-aware writer release.
   - `docs/architecture/state-graph.md` for `post_or_emit` behavior and finalized/reconciled paths.
   - `docs/architecture/github-integration.md` is mandatory because marker reconciliation ownership moves to finalization and the writer receives only finalized writer input, not a marker reconciliation plan.
   - `docs/prds/0007-side-effects.md` is mandatory because it currently describes marker reconciliation as writer-owned durable behavior; update it to match finalization-owned marker reconciliation and finalized writer-input handoff.
   - `docs/harnesses/harness-engineering.md` for the fake writer and post-mode graph harness.

## Focused Harness

Create or update tests covering:

- Fake writer accepts one valid finalized top-level issue-comment payload.
- Fake writer rejects candidate payloads and non-final/final-marker-invalid payloads.
- Fake writer rejects a structurally valid raw `FinalIssueCommentPayload` when it is not wrapped in finalized writer input.
- Fake writer rejects `NOT_READY`, `FAILED_CLOSED`, `RECONCILED_EXISTING`, missing `SAFE_TO_POST`, and `writer_input_released=false` state before any fake transport call.
- Fake writer result includes stable status, target hash, payload hash, artifact kind, and fake comment ID without raw body text.
- Finalization with `SAFE_TO_POST` releases writer input and sets finalized state/final payload hash.
- Finalization with `RECONCILED_EXISTING` returns terminal no-post/reconciled evidence, and `post_or_emit` synthesizes `GitHubWriterResult(status=RECONCILED)` with writer call count zero.
- Finalization with `FAILED_CLOSED` leaves final payload/hash/writer input unset and exposes marker failure reason evidence.
- Finalization cannot consume stale marker reconciliation evidence computed for a different target hash, payload hash, or findings hash.
- Harness approved post route calls fake writer exactly once.
- `post_or_emit` rejects inconsistent state with a final payload but non-finalized status, non-`SAFE_TO_POST` marker reconciliation, or `writer_input_released=false`.
- Harness dry-run route calls fake writer zero times.
- Non-interactive post mode calls approval/finalization/writer zero times.
- Missing, rejected, failed-build, empty, unknown, or non-public approval calls writer zero times.
- Stale target, unknown target freshness, actor mismatch, permission re-check failure, payload validation failure, redaction failure, and marker conflict call writer zero times.
- Retry after a stored fake comment reconciles the existing marker and does not create a second fake comment.
- Public CLI still does not expose production `--post`.
- Import-boundary proof: reviewer, GitHub read, posting-plan, approval, permission, finalization, public CLI, and default runner modules do not import the fake writer unless they are explicitly part of the harness boundary.

## Validation

Focused:

```bash
python -m pytest tests/test_fake_writer.py tests/test_post_mode_graph.py -q
```

Regression:

```bash
python -m pytest tests/test_fake_writer.py tests/test_post_mode_graph.py tests/test_no_approved_findings.py tests/test_non_interactive_posting.py tests/test_target_freshness.py tests/test_marker_hardening.py tests/test_markers.py tests/test_payload_validation.py tests/test_approval.py tests/test_cli.py tests/test_models.py tests/test_contract_boundaries.py -q
python scripts/check_docs.py
git diff --check
python -m py_compile src/reviewgraph/*.py
```

Run the full suite because this issue wires the first post-mode writer path:

```bash
python -m pytest -q
```

## Out Of Scope

- Real GitHub writer adapter.
- Live GitHub writes.
- Manual live post smoke.
- Public production `--post` CLI.
- Formal PR reviews, inline comments, replies, labels, statuses, approvals, request-changes writes, editing/deleting comments, or automatic replies.
- Global cross-process duplicate prevention or external locks.
- Long-term durable writer storage.
