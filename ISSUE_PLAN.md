# ISSUE PLAN: AUR-221 Reconcile Embedded ReviewGraph Markers

Active issue plan for `AUR-221` / `RG-032: Reconcile Embedded ReviewGraph Markers`.

Linear is the durable source for status, blockers, and handoff. Durable behavior comes from `docs/architecture/side-effects.md`, `docs/architecture/state-graph.md`, `docs/architecture/github-integration.md`, `docs/harnesses/harness-engineering.md`, and `docs/prds/0007-side-effects.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-221`
- Title: `RG-032: Reconcile Embedded ReviewGraph Markers`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-07: none
- Upstream blockers complete: `AUR-244`, `AUR-218`, `AUR-217`, `AUR-219`, `AUR-243`, and `AUR-220`.
- Downstream hardening/writer issues: `AUR-245` owns adversarial marker trust and pagination failures; `AUR-222` owns fake writer and end-to-end post-mode routing.

## Objective

Add the marker primitive that lets ReviewGraph attach, parse, and reconcile the hidden final-line marker for top-level issue comments.

This is a harness-first marker slice. It should make marker generation/parsing reusable and prove happy-path duplicate detection, but it must not add a writer adapter, graph post-mode routing, live GitHub reads, pagination failure handling, author-trust policy, or adversarial conflict hardening.

## Contracts To Preserve

- Dry-run remains the default behavior and no GitHub mutation is introduced.
- Marker lines use the existing exact v1 grammar:
  `<!-- reviewgraph:v1 run_id=<id> target=<sha256> payload=<sha256> findings=<sha256> -->`
- Generated final comments place the marker as the exact final line.
- Marker `target`, `payload`, and `findings` fields must use the AUR-244 hash-domain primitives:
  - `ReviewTarget.target_hash()` / `reviewgraph.review_target.v1`
  - visible-body hash for marker `payload`
  - sorted approved-fingerprint hash for marker `findings`
  - final full-body hash includes the exact marker line.
- Scanner recognition is exact final-line only. A copied marker in the middle of a comment body is inert.
- Existing matching marker prevents duplicate posting in the happy path only when target hash, findings hash, and payload hash all match.
- Retry after an ambiguous timeout can reconcile by marker against a fake existing-comment list without posting again.
- Same-target/same-findings/different-payload markers must not return reconciled/no-post in AUR-221. They may return a trust-neutral non-reconciled/deferred-conflict result; `AUR-245` owns turning trusted conflicts into fail-closed policy.
- Author trust, pagination failure, malformed trusted markers, spoofed markers, marker-count transport summaries, and duplicate-fingerprint hardening beyond existing hash primitive rejection are deferred to `AUR-245`.
- The writer adapter remains unreachable in this issue. `AUR-221` produces trust-neutral marker scan data that later finalization/writer work can consume; it does not prove final marker reconciliation while author trust is deferred.

## Implementation Shape

1. Add `src/reviewgraph/markers.py` as a pure module:
   - no live GitHub client
   - no writer adapter
   - no graph imports
   - no shell, environment, subprocess, or clock reads
2. Define marker data contracts in `src/reviewgraph/models.py` only as needed:
   - likely `ReviewGraphMarker` for parsed/generated marker fields
   - optional `ExistingComment`/scan input model if a typed fake comment helps tests
   - prefer a trust-neutral marker scan/match result for AUR-221
   - reserve `MarkerReconciliationResult(PASS)` for later trusted reconciliation unless fake caller-supplied trust is explicit
3. Reuse one canonical grammar surface:
   - import marker regex helpers or expose parser helpers from `reviewgraph.hashing`
   - avoid a third independent regex that can drift from `hashing.py` and `payload_validation.py`
4. Add generation helpers:
   - `build_reviewgraph_marker_line(run_id, review_target, visible_body, finding_fingerprints)`
   - `attach_reviewgraph_marker(...)` or `build_final_issue_comment_payload(...)` if the cleaner seam is to return `FinalIssueCommentPayload`
   - generated body must canonicalize to one trailing newline after the final marker line
5. Add parsing/scanning helpers:
   - parse only exact marker lines
   - scan only the final line of each comment body
   - ignore body-middle marker copies
   - return structured no-match and match outcomes without throwing for ordinary no-marker comments
6. Add happy-path reconciliation:
   - matching target hash, findings hash, and payload hash means no new post is needed
   - matching payload can return existing comment ID and marker metadata
   - same target/findings with a different payload hash must return non-reconciled/deferred-conflict data, not a reconciled result
   - retry-after-timeout harness can feed existing fake comments and prove a matching marker reconciles
7. Keep `payload_validation.validate_final_issue_comment_payload(...)` aligned:
   - final payload marker validation should continue to enforce final-line-only and exact hash fields
   - update it to consume shared parser/helper functions if that removes regex duplication without widening behavior
8. Update narrow docs:
   - marker primitive and final-line-only behavior in `docs/architecture/github-integration.md`
   - marker reconciliation boundary in `docs/architecture/side-effects.md`
   - harness bullet in `docs/harnesses/harness-engineering.md` if the AUR-221 proof adds a new named harness

## Focused Harness

Create `tests/test_markers.py` covering:

- Generated marker line matches exact v1 grammar.
- Generated final body includes marker as the final line and exactly one trailing newline.
- Generated marker fields use AUR-244 hash-domain primitives.
- `FinalIssueCommentPayload` built through marker helper validates with `validate_final_issue_comment_payload`.
- Parser returns marker fields for exact marker lines.
- Parser rejects malformed markers, reordered fields, extra fields, wrong version, bad run IDs, uppercase hash characters, missing hashes, and wrong whitespace.
- Scanner recognizes only final-line markers.
- Copied middle-of-body marker is inert when the final line is not a marker.
- Existing target/findings/payload marker returns reconciled/no-post result with existing comment ID.
- Same-target/same-findings/different-payload marker returns a non-reconciled/deferred-conflict result, not no-post success.
- No existing marker returns a no-match result that does not fail closed yet.
- Retry-after-timeout fake comments can reconcile by marker without invoking any writer sentinel.
- Returned scan/reconciliation data is not writer input and is not a finalization pass while author trust is deferred.
- Import-boundary proof: `src/reviewgraph/markers.py` has no GitHub, writer, graph, subprocess, environment, or clock imports.

Update existing tests as needed:

- `tests/test_payload_hashes.py` if shared parser helpers change hashing exports.
- `tests/test_approval.py` if approval marker generation is refactored to use `markers.py`.
- `tests/test_models.py` if marker/reconciliation model fields change.
- `tests/test_posting.py` / payload validation tests if final payload helper centralizes final-body construction.

## Validation

Focused:

```bash
python -m pytest tests/test_markers.py -q
```

Regression:

```bash
python -m pytest tests/test_markers.py tests/test_payload_hashes.py tests/test_payload_validation.py tests/test_approval.py tests/test_models.py tests/test_target_freshness.py -q
python scripts/check_docs.py
git diff --check
python -m py_compile src/reviewgraph/*.py
```

Run the full suite because this issue touches shared marker/hash/final-payload contracts:

```bash
python -m pytest -q
```

## Out Of Scope

- Live GitHub reads or writes.
- Fake or real writer adapter.
- Graph/CLI post-mode route.
- Pagination, page/comment caps, scan transport summaries, timeout/rate-limit handling.
- Author-trust restrictions and spoofed-marker handling.
- Malformed trusted-marker fail-closed policy.
- Same-target/same-findings/different-payload conflict handling.
- Editing, deleting, or updating existing comments.
