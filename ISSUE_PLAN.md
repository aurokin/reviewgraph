# ISSUE PLAN: AUR-245 Harden Marker Author Pagination Reconciliation

Active issue plan for `AUR-245` / `RG-056: Harden Marker Author Pagination Reconciliation`.

Linear is the durable source for status, blockers, and handoff. Durable behavior comes from `docs/architecture/side-effects.md`, `docs/architecture/state-graph.md`, `docs/architecture/github-integration.md`, `docs/harnesses/harness-engineering.md`, and `docs/prds/0007-side-effects.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-245`
- Title: `RG-056: Harden Marker Author Pagination Reconciliation`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-07: none
- Upstream blockers complete: `AUR-244`, `AUR-218`, `AUR-217`, `AUR-219`, `AUR-243`, `AUR-220`, and `AUR-221`.
- Downstream issues: `AUR-246` owns non-interactive post-mode blocking; `AUR-222` owns fake writer graph/CLI integration; `AUR-241` owns the real writer adapter; `AUR-224` owns manual live post smoke.

## Objective

Turn AUR-221's trust-neutral marker primitive into a hardened, fake-transport reconciliation preflight that later finalization/writer code can consume without unsafe write behavior.

This issue must prove that marker scans paginate existing comments, restrict marker trust to the approved actor or configured ReviewGraph bot, fail closed on incomplete or ambiguous trusted marker state, and emit redacted transport summaries. It must not add real GitHub writes, post-mode graph routing, a fake writer, or live network behavior.

## Contracts To Preserve

- Dry-run remains default and no GitHub mutation is introduced.
- Marker parsing/generation remains exact v1 grammar and final-line only.
- AUR-221 trust-neutral helpers continue to be usable in pure tests.
- Marker trust is narrower than conversation memory trust:
  - trusted marker author = approved GitHub actor with `author_type=user`
  - or configured trusted ReviewGraph bot with `author_type=bot`
  - not every owner/member/collaborator and not every trusted PR commenter
- Untrusted/spoofed markers are ignored and cannot block or reconcile a post.
- Trusted same-target/same-findings/same-payload markers reconcile with no post.
- Trusted same-target/same-findings/different-payload markers fail closed.
- Trusted malformed ReviewGraph-looking final-line markers fail closed when they reference the expected target or when duplicate safety cannot be proven.
- Existing comment scans must either fully paginate within explicit page/comment caps or fail closed before any writer can post.
- Timeout, rate limit, forbidden, not found, unavailable, malformed page shape, pagination loop, page cap, comment cap, and stale/incomplete scan states must produce stable fail-closed reason codes.
- Transport summaries are redacted structured data only: endpoint kind, pages scanned, comments scanned, markers scanned, retryability, stable reason code, and allowlisted GitHub request ID. They must not include tokens, raw stderr, raw comment bodies, or payload bodies.
- Duplicate approved finding fingerprints inside one final payload fail before posting. If this is already covered by approval/finalization preflight, this issue adds an adversarial regression harness rather than inventing a second policy.

## Implementation Shape

1. Extend `src/reviewgraph/markers.py` with hardened reconciliation types:
   - reason-code enum for marker scan failures and conflicts
   - transport-summary dataclass with endpoint kind, page count, comment count, marker count, retryable, reason code, and request ID
   - author/provenance dataclass for existing comments
   - scan policy dataclass for page/comment caps and trusted bot authors
   - hardened reconciliation result that can express pass/reconciled, no-match, and fail-closed states without releasing writer input
2. Keep the new marker code pure:
   - no live GitHub client
   - no writer adapter
   - no graph imports
   - no shell, environment, subprocess, or clock reads
3. Add a fake paginated comment-scan adapter surface:
   - accept a deterministic fake transport that returns issue-comment pages
   - page shape includes comments, `next_cursor`, completion marker, optional request ID
   - failures are injected as structured transport failures, not real exceptions from network code
   - scan all pages before deciding `NO_MATCH`; partial scans fail closed
4. Add explicit caps and failure taxonomy:
   - max pages and max comments are required positive values
   - repeated cursor, malformed page, page cap exceeded, comment cap exceeded, timeout, rate limit, forbidden, not found, unavailable, and unknown transport failure all fail closed
   - timeout/rate-limit/unavailable are retryable; conflicts/malformed trusted markers/spoofing policy failures are non-retryable
5. Add marker author trust policy:
   - compare exact approved actor for user-authored comments
   - compare configured trusted ReviewGraph bot authors for bot-authored comments
   - ignore other authors, even if GitHub association is owner/member/collaborator
   - reject unknown or malformed author identity only for trust; do not let it become trusted
6. Compose with AUR-221 marker semantics:
   - only final-line exact markers count
   - body-middle markers are inert
   - same target/findings/payload trusted marker reconciles
   - same target/findings/different payload trusted marker fails closed
   - trusted malformed final-line ReviewGraph marker with the expected target fails closed
   - multiple trusted identical matching markers reconcile but record duplicate marker metadata if the result type supports it
7. Prove duplicate-fingerprint preflight:
   - add a focused regression that duplicate approved finding fingerprints fail before marker reconciliation can release writer input
   - reuse existing `finalize_github_payload` or approval preflight when possible instead of duplicating finalization policy
8. Update narrow durable docs:
   - marker trust, pagination fail-closed behavior, and transport summary shape in `docs/architecture/github-integration.md`
   - finalization/idempotency wording in `docs/architecture/side-effects.md`
   - harness bullet in `docs/harnesses/harness-engineering.md`

## Focused Harness

Create `tests/test_marker_hardening.py` covering:

- Paginated scan reads all pages before returning no-match.
- Matching trusted marker on a later page reconciles and posts zero in the fake retry helper.
- Page cap exceeded fails closed with stable reason code and no writer release.
- Comment cap exceeded fails closed with stable reason code and no writer release.
- Repeated cursor/incomplete pagination fails closed.
- Timeout, rate limit, forbidden, not found, unavailable, malformed response, and unknown transport failure classify to stable reason code, retryability, and redacted summary.
- Transport summary includes endpoint kind, page count, comment count, marker count, retryability, reason code, and safe request ID.
- Transport summary rejects or drops token-looking request IDs and never exposes raw stderr, comment body, payload body, or token fragments.
- Markers from unapproved users, unconfigured bots, and owner/member/collaborator commenters that are not the approved actor are ignored.
- Approved actor marker and configured trusted ReviewGraph bot marker are trusted.
- Trusted same-target/same-findings/different-payload marker fails closed.
- Trusted malformed ReviewGraph-looking final-line marker for the expected target fails closed.
- Spoofed malformed marker from an untrusted author is ignored.
- Body-middle copied marker remains inert.
- Multiple trusted identical matching markers reconcile with duplicate metadata and no extra post.
- Duplicate approved finding fingerprints fail before marker reconciliation/writer release.
- Import-boundary proof for `src/reviewgraph/markers.py`.

Update existing tests as needed:

- `tests/test_markers.py` if the trust-neutral result or marker comment model gains fields.
- `tests/test_finalization.py` if duplicate-fingerprint preflight gets a narrower regression there.
- `tests/test_models.py` if marker reconciliation model fields move into shared models.

## Validation

Focused:

```bash
python -m pytest tests/test_marker_hardening.py -q
```

Regression:

```bash
python -m pytest tests/test_marker_hardening.py tests/test_markers.py tests/test_payload_hashes.py tests/test_payload_validation.py tests/test_approval.py tests/test_target_freshness.py tests/test_finalization.py -q
python scripts/check_docs.py
git diff --check
python -m py_compile src/reviewgraph/*.py
```

Run the full suite because this issue touches side-effect safety contracts:

```bash
python -m pytest -q
```

## Out Of Scope

- Real network reads or writes.
- Fake top-level comment writer.
- Real writer adapter.
- Graph/CLI post-mode routing.
- Non-interactive posting policy.
- Manual live post smoke.
- Editing, deleting, or updating existing comments.
- Global cross-process duplicate prevention.
