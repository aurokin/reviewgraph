# ISSUE PLAN: AUR-244 Define Payload Hash Domains And Golden Tests

Active issue plan for `AUR-244` / `RG-055: Define Payload Hash Domains And Golden Tests`.

Linear is the durable source for status, blockers, and issue handoff. Durable behavior comes from `docs/architecture/github-integration.md`, `docs/architecture/side-effects.md`, `docs/architecture/state-graph.md`, and `docs/harnesses/harness-engineering.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-244`
- Title: `RG-055: Define Payload Hash Domains And Golden Tests`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-07: none
- Current blocker posture: PRD 0006 gate is complete; stale `AUR-260` blocker was removed; `AUR-244` blocks downstream payload validation and marker generation work.

## Objective

Create one canonical hash-domain surface for PRD 0007 so later approval, payload validation, marker, finalization, and writer slices cannot invent subtly different hashes.

This issue is pure hash/marker primitive work plus tests. It must not split candidate/final payload models, implement approval, build final payloads, reconcile markers, or add writer behavior.

## Contracts To Preserve

- Visible body hash excludes the hidden ReviewGraph marker line when it is the exact final-line marker.
- Marker `payload` stores `visible_body_hash(final_body_without_marker)`.
- Final payload hash stores the hash of the full final issue-comment body including the exact marker line.
- Findings hash uses sorted selected fingerprints supplied by the caller.
- Duplicate postable or approved fingerprints are invalid and fail closed; they are not deduplicated or treated as a multiset.
- Hash bytes are canonical UTF-8, LF line endings, deterministic review-target field order, deterministic sorted fingerprints, one trailing newline, and exact marker whitespace.
- Candidate/final payload schema debt remains for `AUR-218`; do not preserve or expand the current `CandidateIssueCommentPayload = GitHubReviewPayload` alias as part of this issue.
- Keep legacy candidate compatibility explicit: `posting.full_body_hash()` can remain a candidate compatibility wrapper until `AUR-218`, but it must not be the final writer/approval hash primitive.
- Add distinct canonical primitives for PRD 0007 final side effects, such as `marker_payload_hash(final_body_without_marker)` and `final_payload_hash(full_final_body)`.
- Add a strict ReviewGraph v1 marker-line recognizer for hash-domain use. It should accept only the documented exact final-line grammar: `<!-- reviewgraph:v1 run_id=... target=sha256:... payload=sha256:... findings=sha256:... -->`, with required field order and exact single-space separators.

## Implementation Shape

1. Add canonical helper functions in the existing hash/posting boundary, likely `src/reviewgraph/hashing.py` plus thin compatibility wrappers in `src/reviewgraph/posting.py`.
2. Keep existing public behavior compatible where current tests rely on candidate payload hashes, while adding separate final-side-effect hash helpers.
3. Add `tests/test_payload_hashes.py` covering:
   - Fixed expected `sha256:` digest constants for visible body hash, marker payload hash, final full-body hash including a literal final marker line, sorted findings hash, and review-target hash.
   - LF/CRLF/CR normalization and one trailing newline for canonical final-side-effect hashes.
   - Visible body hash excluding only an exact final-line ReviewGraph v1 marker.
   - Marker payload hash equal to visible body hash of the body without the marker.
   - Final payload hash equal to the canonical full body including the exact marker line.
   - Deterministic target hash field order, including a test that `ReviewTarget.target_hash()` matches the canonical target hash primitive or pinned fixture.
   - Findings hash sorting from caller-supplied selected fingerprints.
   - Duplicate selected-fingerprint rejection in the shared helper downstream approval/finalization must reuse.
   - Strict marker grammar sensitivity: malformed prefix-only markers, wrong version, missing fields, extra fields, reordered fields, changed whitespace, and marker-in-middle must not be treated as the exact final marker.
4. Run focused and regression checks.

## Validation

Focused:

```bash
python -m pytest tests/test_payload_hashes.py -q
```

Regression:

```bash
python -m pytest tests/test_posting.py tests/test_models.py -q
python scripts/check_docs.py
git diff --check
```

Run broader tests if shared hash helper changes affect more than posting/payload behavior.

## Out Of Scope

- Approval decision model or final-hash approval binding (`AUR-217`).
- Candidate/final payload model split or writer-input validation (`AUR-218`).
- Marker scanner/reconciliation implementation (`AUR-221`, `AUR-245`).
- Actor/permission gates, target freshness, non-interactive post mode, fake writer, real writer, or live post smoke.
