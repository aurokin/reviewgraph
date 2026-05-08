# ISSUE PLAN: AUR-224 Add Manual Live Post Smoke Contract

Active issue plan for `AUR-224` / `RG-035: Add Manual Live Post Smoke Contract`.

Linear is the durable source for status, blockers, and handoff. Durable behavior comes from `docs/architecture/side-effects.md`, `docs/architecture/github-integration.md`, `docs/architecture/state-graph.md`, `docs/harnesses/harness-engineering.md`, and `docs/prds/0007-side-effects.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-224`
- Title: `RG-035: Add Manual Live Post Smoke Contract`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-08: none
- Upstream side-effect issues complete in Linear: `AUR-244`, `AUR-218`, `AUR-217`, `AUR-219`, `AUR-243`, `AUR-220`, `AUR-221`, `AUR-245`, `AUR-246`, `AUR-223`, `AUR-222`, and `AUR-241`.
- Downstream issue: `AUR-261` owns PRD 0007 milestone closure.

## Objective

Add a manual-only live post smoke contract for a disposable PR. The default test suite must remain credential-free and non-mutating. The live post path must be opt-in, skipped or blocked by default, and usable only after it proves the same finalized top-level issue-comment payload that dry-run produced is still safe to write.

This issue should introduce a smoke harness and contract tests, not a production posting CLI. It must not add CI posting, webhook posting, config-only approval, formal PR reviews, inline comments, labels, statuses, approvals, request-changes writes, automatic replies, edits, deletes, live LLM calls, or global duplicate storage.

## Contracts To Preserve

- Dry-run remains the default behavior.
- Public CLI still exposes no production `--post` flag.
- Live post tests are marked `live_post` and skipped unless explicit opt-in is present.
- Live post can target only a top-level issue comment through the real writer adapter from `AUR-241`.
- The real writer receives only `FinalizedIssueCommentWriterInput` produced by the existing finalization gates.
- Approval is explicit, interactive, and human-owned. Non-TTY, CI, webhook, config-only, or fixture-only state cannot satisfy live post approval.
- The human must see the live actor, credential source, endpoint-specific permission proof, target, marker scan result, dry-run artifact hash, and final payload hash before typing the exact final payload hash.
- Live pre-writer proofs for actor/permission, target freshness, and marker pagination must be produced by read-only live transports immediately before approval and finalization.
- Fixture state or prebuilt pass objects cannot substitute for live proof of actor, permission, target freshness, or marker pagination.
- Disposable safety must be proven before any approval prompt or writer call by an explicit allowlist and a disposable PR marker convention in the live PR metadata, such as title/body/head branch text.
- Live post verifies a dry-run artifact hash for the same owner/repo, PR number, target hash, and final payload hash immediately before writing.
- The evidence artifact must prove one POST max, marker seen/reconciled state, actor shown to the human, endpoint permission shown to the human, final hash shown or matched, and redacted transport summaries.
- All live read and writer attempt summaries are redacted and allowlisted: endpoint kind, page count when relevant, retryability, stable failure code, and GitHub request ID when available. No tokens, raw stderr, request headers, raw PR comment bodies, or raw final payload bodies.

## Implementation Shape

1. Add the focused harness tests first in `tests/test_live_post_contract.py`:
   - Default collection and default execution block/skip without `REVIEWGRAPH_LIVE_POST=1`.
   - `pytest -m live_post` is still blocked unless every prerequisite is present.
   - Contract tests use fake command runners/transports, not live network.
   - Tests assert no POST command is constructed before all disposable, live-proof, dry-run-hash, TTY, and typed-hash gates pass.
2. Add a manual live-post module, likely `src/reviewgraph/github_live_post.py`:
   - Keep it outside `src/reviewgraph/github.py` so the fake read adapter stays free of shell, network, approval, finalization, and writer imports.
   - Use injected runners/transports in tests and subprocess-backed `gh api` only in the opt-in manual path.
   - Define explicit env/config names such as `REVIEWGRAPH_LIVE_POST`, `REVIEWGRAPH_LIVE_POST_PR`, `REVIEWGRAPH_LIVE_POST_ALLOWED_OWNER_REPO`, `REVIEWGRAPH_LIVE_POST_DISPOSABLE_MARKER`, `REVIEWGRAPH_LIVE_POST_DRY_RUN_ARTIFACT`, and `REVIEWGRAPH_LIVE_POST_OUT`.
   - Add a `LivePostSmokeArtifact` with `status`, `reason`, `pr_ref`, redacted preflight/finalization/writer summaries, dry-run hash evidence, approval evidence, POST attempt count, marker page/comment counts, and redaction status.
3. Implement prerequisite and disposable preflight:
   - Block when opt-in, PR ref, `gh`, token, dry-run artifact, TTY, allowlist, or disposable marker is missing.
   - Parse the PR ref and require it to match the allowlisted owner/repo and the dry-run artifact target.
   - Fetch live PR metadata through read-only `gh api` before prompting and require the disposable marker in title, body, or head branch/ref text.
   - Reject fixture refs, non-GitHub refs, non-top-level issue-comment artifacts, and non-disposable targets.
4. Implement live read-only finalization proofs:
   - Actor proof: use a read-only live endpoint such as `GET /user` to identify the authenticated actor.
   - Permission proof: use read-only permission metadata for the target repo and normalize it through `ActorPermissionProbeResult` / `evaluate_actor_permission_gate` for the issue-comment endpoint.
   - Target freshness proof: re-fetch PR metadata and a read-only compare/merge-base source immediately before finalization so `TargetFreshnessProbeResult` can satisfy the existing target freshness gate.
   - Marker proof: paginate `GET /repos/{owner}/{repo}/issues/{pr_number}/comments` and pass mapped comments into `reconcile_paginated_trusted_markers(...)`.
   - Tests should prove fixture/precomputed pass objects cannot satisfy these proof objects without live transport evidence.
5. Wire approval/finalization/writer narrowly:
   - Load the dry-run artifact's approved final issue-comment payload evidence and verify the artifact hash, target hash, selected item/finding hash, and final payload hash match the live target.
   - Show actor, credential source, endpoint permission, target, marker state, dry-run artifact hash, and final hash to the human.
   - Require a TTY/human approval surface and exact typed final-payload-hash confirmation.
   - Call `finalize_github_payload(...)`, `build_finalized_issue_comment_writer_input(...)`, and `GitHubIssueCommentWriter(...)` only after all preflight and approval checks pass.
   - Use the real writer adapter and an injected `gh api --method POST /repos/{owner}/{repo}/issues/{pr_number}/comments` transport only in the manual opt-in path.
   - Preserve the same one-POST guard and writer evidence from `AUR-241`.
6. Update durable docs narrowly:
   - `docs/architecture/github-integration.md` for manual live post transport boundaries, disposable PR preflight, read-only proof endpoints, and cleanup expectations.
   - `docs/architecture/side-effects.md` for live post approval/hash/disposable constraints if missing.
   - `docs/harnesses/harness-engineering.md` for the `live_post` harness contract and default skip/block behavior.
   - `docs/prds/0007-side-effects.md`, `README.md`, and `docs/plans/implementation-plan.md` only for current status and manual live-post references.
7. Update Linear before completion:
   - Check off AUR-224 acceptance criteria only after each is mapped to tests/docs.
   - Add an evidence comment with focused tests, default-suite validation, redaction/default-no-write proof, review outcome, and explicit non-run of live mutation.

## Focused Harness

Create `tests/test_live_post_contract.py` covering:

- `REVIEWGRAPH_LIVE_POST` opt-in is required and absent opt-in blocks/skips by default.
- `pytest -m live_post` marker exists and does not run live mutation unless manual prerequisites are present.
- Missing PR ref, missing `gh`, missing token, missing TTY, missing allowlist, missing disposable marker, or missing dry-run artifact blocks before approval and before writer transport.
- A non-allowlisted owner/repo or dry-run artifact target mismatch blocks before approval.
- Fixture refs or fake state cannot satisfy actor, permission, target freshness, or marker pagination proof.
- Live proof uses read-only `gh api` command construction for actor, permission, PR target, compare/merge-base, and existing issue-comment pagination before any POST command.
- Mutating `gh api --method POST` is rejected unless all gates pass and exact typed final hash confirmation matches.
- Typed hash mismatch blocks before finalization/writer.
- Live post supports only top-level issue-comment artifact kind and endpoint.
- Existing marker reconciliation result is honored: `RECONCILED_EXISTING` reports no-post, `SAFE_TO_POST` can proceed, and marker failures block.
- The real writer adapter is used after finalized writer input is built; raw candidate/final payloads are never accepted as writer input.
- Evidence records one POST max, live actor, credential source, endpoint permission, dry-run artifact hash, final payload hash, marker page/comment counts, retryability, reason code, request ID, and redaction status.
- Transport summaries and artifacts redact tokens, raw stderr, request headers, raw PR comment bodies, and raw final payload bodies.
- Public CLI still exposes no production `--post`.
- `src/reviewgraph/github_live.py` and `src/reviewgraph/github.py` remain free of live writer imports; only the manual live-post module imports finalization/writer code.

## Validation

Focused:

```bash
.venv/bin/python -m pytest tests/test_live_post_contract.py -q
```

Regression:

```bash
.venv/bin/python -m pytest tests/test_live_post_contract.py tests/test_live_read_smoke.py tests/test_github_writer.py tests/test_fake_writer.py tests/test_post_mode_graph.py tests/test_marker_hardening.py tests/test_permissions.py tests/test_target_freshness.py -q
.venv/bin/python scripts/check_docs.py
git diff --check
.venv/bin/python -m py_compile src/reviewgraph/*.py
```

Run the full suite before completion:

```bash
.venv/bin/python -m pytest -q
```

Do not run a real live post during automated validation. Manual live mutation remains a user-invoked smoke path for a disposable PR only.

## Out Of Scope

- Default live posting.
- CI, webhook, config-only, or non-interactive posting.
- Public production post CLI.
- Formal GitHub reviews, inline comments, replies, labels, statuses, approvals, request-changes writes, edits, deletes, or automatic replies.
- Live LLM calls.
- Fake-only live finalization proof.
- Global cross-process duplicate prevention or external locks.
