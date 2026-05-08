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
- The human must see the live actor, credential source, endpoint-specific permission proof, target, marker scan result, dry-run artifact hash, exact final issue-comment payload, and final payload hash before typing the exact final payload hash. The exact payload may be printed to the TTY approval surface but must not be persisted in smoke evidence.
- Live pre-writer proofs for actor/permission, target freshness, and marker pagination must be produced by read-only live transports immediately before approval and finalization.
- Fixture state or prebuilt pass objects cannot substitute for live proof of actor, permission, target freshness, or marker pagination.
- Disposable safety must be proven before any approval prompt or writer call by an explicit allowlist and a disposable PR marker convention in the live PR metadata, such as title/body/head branch text.
- Live post verifies a dry-run artifact hash for the same owner/repo, PR number, target hash, and final payload hash immediately before writing.
- The evidence artifact must prove one POST max, marker seen/reconciled state, actor shown to the human, endpoint permission shown to the human, final hash shown or matched, and redacted transport summaries.
- All live read and writer attempt summaries are redacted and allowlisted: endpoint kind, page count when relevant, retryability, stable failure code, and GitHub request ID when available. No tokens, raw stderr, request headers, raw PR comment bodies, or raw final payload bodies.
- Live-post proof objects must be module-owned. `github_live_post.py` must not accept caller-supplied `ActorPermissionProbeResult`, `TargetFreshnessProbeResult`, `MarkerReconciliationResult`, approval pass objects, or finalized writer input as live proof; it must derive them internally from a private live-proof envelope produced by the injected `gh` runner in the same smoke attempt.
- The approval/finalization timing is two-phase: pre-approval live reads may be shown to the human, but after the typed approval hash is accepted the module must repeat the live actor/permission, target freshness, and marker reads and pass only those post-approval probes into `finalize_github_payload(...)`.
- Live post mutating command construction has an exact allowlist: the only allowed write command is `gh api --method POST repos/{owner}/{repo}/issues/{pr_number}/comments --input -` with JSON body supplied via stdin or an injected transport body object containing only `{"body": final_payload.body}`. No GraphQL, `gh pr review`, `gh pr comment`, `gh issue comment`, form flags, extra fields, alternate methods, edits, deletes, or raw shell strings are permitted.

## Implementation Shape

1. Add the focused harness tests first in `tests/test_live_post_contract.py`:
   - Unmarked fake-contract tests run in default `pytest -q` and never require network or credentials.
   - Only the real manual smoke test is marked `@pytest.mark.live_post`; default collection skips it unless `REVIEWGRAPH_LIVE_POST=1`.
   - `pytest -m live_post` is still blocked/skipped unless every manual prerequisite is present.
   - Contract tests use fake command runners/transports, not live network.
   - Tests assert no POST command is constructed before all disposable, live-proof, dry-run-hash, TTY, and typed-hash gates pass.
   - Register `live_post` in `pyproject.toml` and mirror the existing `tests/conftest.py` live-read skip pattern.
2. Add a manual live-post module, likely `src/reviewgraph/github_live_post.py`:
   - Keep it outside `src/reviewgraph/github.py` so the fake read adapter stays free of shell, network, approval, finalization, and writer imports.
   - Use injected runners/transports in tests and subprocess-backed `gh api` only in the opt-in manual path.
   - Define explicit env/config names such as `REVIEWGRAPH_LIVE_POST`, `REVIEWGRAPH_LIVE_POST_PR`, `REVIEWGRAPH_LIVE_POST_ALLOWED_TARGET`, `REVIEWGRAPH_LIVE_POST_DISPOSABLE_MARKER`, `REVIEWGRAPH_LIVE_POST_APPROVED_ARTIFACT`, and `REVIEWGRAPH_LIVE_POST_OUT`.
   - Add a `LivePostSmokeArtifact` with `status`, `reason`, `pr_ref`, redacted preflight/finalization/writer summaries, dry-run hash evidence, approval evidence, POST attempt count, marker page/comment counts, and redaction status.
   - Add an offline approved-post artifact builder/validator helper in the same module or a neutral helper module. The live smoke must reject hand-written, partial, candidate-only, or schema-drifted artifacts.
3. Implement prerequisite and disposable preflight:
   - Block when opt-in, PR ref, `gh`, token, approved-post artifact, TTY, allowlisted exact target, or disposable marker is missing.
   - Parse the PR ref and require it to match `REVIEWGRAPH_LIVE_POST_ALLOWED_TARGET` exactly as `owner/repo#pr_number`; owner/repo-only allowlists are insufficient.
   - Require the approved-post artifact target to match that exact target.
   - Require `REVIEWGRAPH_LIVE_POST_DISPOSABLE_MARKER` to match the exact marker text `reviewgraph-disposable-live-post-ok` and require that text in the live PR title, PR body, or head branch/ref. Fork PRs are rejected for MVP live post smoke unless a later policy explicitly models them.
   - Fetch live PR metadata through read-only `gh api` before prompting and require the disposable marker in title/body/head ref plus exact target match.
   - Reject fixture refs, non-GitHub refs, non-top-level issue-comment artifacts, candidate-only artifacts, and non-disposable targets.
4. Implement live read-only finalization proofs:
   - Actor proof: use read-only `GET /user` to identify the authenticated actor.
   - Permission proof: `REVIEWGRAPH_LIVE_POST_CREDENTIAL_SOURCE` must be explicitly set to `pat`. Fine-grained PATs, GitHub App installation tokens, GitHub App user tokens, unknown credential sources, and absent credential-source declarations fail closed in AUR-224. A later issue may add exact read-only proof for those credential classes.
   - For `pat`, use read-only `GET /repos/{owner}/{repo}` and its authenticated-user `permissions` shape to derive broad repo permission. Normalize `admin` to `admin`, `maintain` to `maintain`, `push` to `write`, `triage` to `triage`, and `pull` to `read`; if this endpoint cannot prove `write`, `maintain`, or `admin`, fail closed. Set `issue_comment_write=true` only from this proven broad write permission for `pat`; do not perform a write probe.
   - Permission proof must still normalize through `ActorPermissionProbeResult` / `evaluate_actor_permission_gate` for endpoint `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`.
   - Target freshness proof: re-fetch `GET /repos/{owner}/{repo}/pulls/{pr_number}` for owner/repo, PR number, base SHA, head SHA, and diff basis, then call exact read-only `GET /repos/{owner}/{repo}/compare/{base_sha}...{head_sha}` and map `merge_base_commit.sha` to `merge_base_sha`. Unknown, absent, or mismatched merge-base freshness fails closed.
   - Marker proof: paginate `GET /repos/{owner}/{repo}/issues/{pr_number}/comments` and pass mapped comments into `reconcile_paginated_trusted_markers(...)`.
   - Marker pagination uses explicit live smoke caps: `per_page=100`, `max_pages=5`, `max_comments=500`, `timeout_seconds=20`, with fail-closed reason codes for page cap, comment cap, timeout, rate limit, forbidden, not found, unavailable, malformed page, repeated cursor, and transport unknown.
   - Tests should prove fixture/precomputed pass objects cannot satisfy these proof objects without the module-private live transport envelope.
5. Wire approval/finalization/writer narrowly:
   - Load an approved-post artifact, not generic dry-run JSON. The artifact schema must include `schema_version`, `artifact_kind="issue_comment"`, `source="reviewgraph-approved-post-artifact"`, `created_by_helper`, `source_dry_run_artifact_hash`, `run_id`, `target`, `target_hash`, `approved_item_ids`, sorted approved `finding_fingerprints`, `findings_hash`, `visible_body_hash`, `marker_payload_hash`, `marker_line`, `final_payload_hash`, canonical `artifact_hash`, plus the typed contract inputs needed to rerun existing builders: serialized full `PostingPlan` items, serialized full candidate `ClassifiedFinding` values for every public posting-plan/candidate item, serialized `CandidateIssueCommentPayload` binding fields, `local_verdict`, and `include_public_verdict`.
   - The approved subset is represented only by `approved_item_ids` and sorted approved `finding_fingerprints`; the artifact must preserve the full candidate plan/finding set. A two-public-finding candidate with one approved item must validate without shrinking the plan, and any artifact that drops unapproved public candidate findings to make validation pass fails closed.
   - `source_dry_run_artifact_hash` is distinct from the approved-post `artifact_hash`. The helper must bind `source_dry_run_artifact_hash` to the same target hash, candidate payload visible body hash, full candidate findings hash, and final payload hash; approved-post artifacts without source dry-run hash proof fail closed.
   - The approved-post artifact input may contain the exact canonical final issue-comment body because the writer needs the body that hashes to `final_payload_hash`; the live post output/evidence artifact must redact or omit that body and must never persist raw final body text in transport summaries or logs.
   - Define `artifact_hash` as `sha256:` over canonical JSON bytes for all fields except `artifact_hash`, with sorted keys, UTF-8, LF endings, and no insignificant whitespace.
   - Reconstruct typed `PostingPlan`, selected `ClassifiedFinding` objects, and `CandidateIssueCommentPayload` from the artifact and rerun `build_approval_proof(...)` / `build_approval_decision(...)` with live pre-approval actor-permission proof. Do not directly instantiate approval pass objects from artifact fields.
   - Rebuild the final payload through `build_approved_final_issue_comment(...)` and verify it equals the artifact body/hash before any approval prompt. Hand-written artifacts, partial artifacts, direct final-body-only artifacts, and artifacts that cannot pass the normal candidate/approval/final builders fail closed.
   - Verify artifact hash, exact target, target hash, selected item/finding hash, marker hashes, run ID, artifact kind, endpoint, final payload body hash, and final payload hash before any approval prompt.
   - Show actor, credential source, endpoint permission, target, marker state, dry-run artifact hash, exact final issue-comment payload, and final hash to the human.
   - Require a TTY/human approval surface and exact typed final-payload-hash confirmation.
   - Evidence must record approval-surface booleans without raw body text: `tty_required=true`, `shown_actor=true`, `shown_permission=true`, `shown_marker_scan=true`, `shown_dry_run_artifact_hash=true`, `shown_final_payload_hash=true`, and `typed_hash_matched=true`.
   - After typed hash confirmation, repeat live actor/permission, target freshness, and marker reads and only then call `finalize_github_payload(...)`.
   - Call `finalize_github_payload(...)`, `build_finalized_issue_comment_writer_input(...)`, and `GitHubIssueCommentWriter(...)` only after all preflight and approval checks pass.
   - Use the real writer adapter and an injected `gh api --method POST repos/{owner}/{repo}/issues/{pr_number}/comments --input -` transport only in the manual opt-in path.
   - Preserve the same one-POST guard and writer evidence from `AUR-241`.
   - `RECONCILED_EXISTING` reports no writer invocation and no POST command; `SAFE_TO_POST` is the only path that may build finalized writer input and reach the writer.
   - On `POSTED`, evidence must include comment ID or URL plus explicit manual cleanup/retention guidance. Automated cleanup is out of scope and must not delete or edit the comment.
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
- Unmarked fake-contract tests run in default `pytest -q`; only the real mutation smoke is marked `live_post`.
- `pytest -m live_post` marker exists and does not run live mutation unless manual prerequisites are present.
- Missing PR ref, missing `gh`, missing token, missing TTY, missing allowlist, missing disposable marker, or missing dry-run artifact blocks before approval and before writer transport.
- A non-allowlisted exact `owner/repo#pr`, fork PR, candidate-only artifact, hand-written artifact, or approved-post artifact target/hash mismatch blocks before approval.
- Fixture refs, caller-supplied probes, precomputed pass objects, or fake state cannot satisfy actor, permission, target freshness, or marker pagination proof.
- Live proof uses read-only `gh api` command construction for actor, permission, PR target, compare/merge-base, and existing issue-comment pagination before any POST command.
- Permission proof supports only explicit `REVIEWGRAPH_LIVE_POST_CREDENTIAL_SOURCE=pat` in AUR-224; fine-grained PAT, GitHub App, unknown, or absent credential source blocks before approval.
- Target freshness uses exact read-only compare endpoint `GET /repos/{owner}/{repo}/compare/{base_sha}...{head_sha}` and fails closed when `merge_base_commit.sha` is absent or mismatched.
- Mutating `gh api --method POST repos/{owner}/{repo}/issues/{pr_number}/comments --input -` is rejected unless all gates pass and exact typed final hash confirmation matches; alternate write commands, GraphQL, form flags, extra JSON fields, edit/delete methods, and shell strings are rejected.
- Approved-post artifacts must reconstruct the normal `PostingPlan`, `ClassifiedFinding`, candidate payload, approval proof, and final payload builder path; direct approval-object or final-body-only bypasses fail.
- Typed hash mismatch blocks before finalization/writer.
- Live post supports only top-level issue-comment artifact kind and endpoint.
- Existing marker reconciliation result is honored: `RECONCILED_EXISTING` reports no-post, `SAFE_TO_POST` can proceed, and marker failures block.
- The real writer adapter is used after finalized writer input is built; raw candidate/final payloads are never accepted as writer input.
- Evidence records one POST max, live actor, credential source, endpoint permission, source dry-run artifact hash, approved-post artifact hash, final payload hash, approval-surface booleans, marker page/comment counts, retryability, reason code, request ID, comment ID/URL when posted, manual cleanup/retention guidance, and redaction status.
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
