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
- Completion status: `Done` after focused/full validation and fresh code-review subagents reported no material issues.
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
  - trusted marker author = exact approved GitHub actor with supported `author_type` of `user` or `bot`
  - or configured trusted ReviewGraph bot with `author_type=bot`
  - not every owner/member/collaborator and not every trusted PR commenter
- Untrusted/spoofed markers are ignored and cannot block or reconcile a post.
- Trusted same-target/same-findings/same-payload markers reconcile with no post.
- Trusted same-target/same-findings/different-payload markers fail closed.
- Trusted malformed ReviewGraph-looking final-line markers fail closed whenever the exact parser cannot prove a safe different target/findings/payload result; AUR-245 uses the stricter rule that any trusted final-line `<!-- reviewgraph:` parse failure fails closed.
- Existing comment scans must either fully paginate within explicit page/comment/timeout caps before any terminal result or fail closed before any writer can post. A match on page one cannot reconcile if page two later contains a trusted conflict, malformed trusted marker, or pagination failure.
- Timeout, rate limit, forbidden, not found, unavailable, malformed page shape, incomplete pagination, repeated cursor, page cap, comment cap, and unknown transport failure states must produce stable fail-closed reason codes.
- Transport summaries are redacted structured data on every outcome, including reconciled, no-match, ignored-spoof, and fail-closed outcomes. They contain endpoint kind, pages scanned, comments scanned, markers scanned, retryability, stable reason code, and one allowlisted GitHub request ID. On failure this is the failure page request ID; on pass/no-match this is the last safe page request ID. They must not include tokens, raw stderr, raw comment bodies, or payload bodies.
- Duplicate approved finding fingerprints inside one final payload fail before posting. If this is already covered by approval/finalization preflight, this issue adds an adversarial regression harness rather than inventing a second policy.

## Implementation Shape

1. Add a durable marker reconciliation handoff model used by the hardened scanner and later finalization/writer nodes:
   - status enum with `SAFE_TO_POST`, `RECONCILED_EXISTING`, and `FAILED_CLOSED`
   - reason/action-code enum with `safe_to_post`, `matched_existing`, `pagination_incomplete`, `repeated_cursor`, `page_cap_exceeded`, `comment_cap_exceeded`, `malformed_page`, `timeout`, `rate_limited`, `forbidden`, `not_found`, `unavailable`, `transport_unknown`, `trusted_marker_conflict`, and `trusted_marker_malformed`
   - transport-summary dataclass with endpoint kind, page count, comment count, marker count, retryable, reason code, and request ID
   - author/provenance dataclass for existing comments
   - scan policy dataclass for page/comment caps and trusted bot authors
   - hardened reconciliation result that can express safe-to-post, reconciled-existing/no-post, and fail-closed states without releasing writer input by itself
   - duplicate matching comment IDs and marker metadata, without retaining raw comment bodies
   - expand `src/reviewgraph/models.py` or add an explicitly documented conversion so `ReviewState.marker_reconciliation` can carry status, reason code, transport summary, trusted actor, existing comment ID, and duplicate comment IDs when AUR-222/AUR-241 wire the graph route
2. Keep the new marker code pure:
   - no live GitHub client
   - no writer adapter
   - no graph imports
   - no shell, environment, subprocess, or clock reads
3. Add a fake paginated comment-scan adapter surface:
   - define a protocol such as `get_issue_comments_page(owner_repo, pr_number, cursor)` with cursor start `None`
   - accept a deterministic fake transport implementing that protocol and returning issue-comment pages
   - page shape is concrete and validated: comments tuple, optional `next_cursor`, boolean `completed`, optional request ID
   - exactly one of `completed=True` or non-empty `next_cursor` is allowed; `completed=True` requires `next_cursor=None`
   - empty completed pages are valid; empty non-completed pages are valid only if the cursor advances
   - scanned comment shape includes `comment_id`, `body`, `author_login`, `author_type`, `source_provider`, and optional `author_association` for diagnostics only
   - failures are injected as structured transport failures, not real exceptions from network code
   - scan all pages before deciding any terminal status; partial scans fail closed even when an earlier page contained a match
   - call order and cursor progression are asserted in the harness
4. Add explicit caps and failure taxonomy:
   - define `MarkerScanLimits(max_pages, max_comments, timeout_seconds)` with default policy `max_pages=20`, `max_comments=1000`, `timeout_seconds=10`
   - exactly-at-cap scans can pass; cap-plus-one scans fail closed
   - repeated cursor, malformed page, page cap exceeded, comment cap exceeded, timeout, rate limit, forbidden, not found, unavailable, incomplete pagination, and unknown transport failure all fail closed
   - timeout/rate-limit/unavailable/transport_unknown are retryable; conflicts and malformed trusted markers are non-retryable
   - untrusted/spoofed markers are ignored and never fail the scan unless the transport/page itself is invalid
5. Add marker author trust policy:
   - compare exact approved actor for supported user- or bot-authored comments
   - compare configured `trusted_bot_authors` as trusted ReviewGraph bot authors for bot-authored comments; do not add a broader marker-specific trust list in this issue
   - ignore other authors, even if GitHub association is owner/member/collaborator
   - ignore memory `trust_label` and do not call conversation-memory trust classification
   - reject unknown/missing author identity only for trust; do not let it become trusted
   - actor comparisons are exact and case-sensitive
6. Compose with AUR-221 marker semantics:
   - only final-line exact markers count
   - body-middle markers are inert
   - same target/findings/payload trusted marker reconciles
   - same target/findings/different payload trusted marker fails closed
   - trusted malformed final-line ReviewGraph marker fails closed
   - multiple trusted identical matching markers reconcile but record duplicate marker metadata
   - conflict/malformed trusted markers found on any later page override an earlier exact match
   - a page/cap/transport failure after an earlier exact match still fails closed because scan completeness was not proven
7. Prove duplicate-fingerprint preflight:
   - add a focused regression that duplicate approved finding fingerprints fail before marker scan, final payload construction, marker reconciliation, or writer input release
   - reuse existing `finalize_github_payload` or approval preflight when possible instead of duplicating finalization policy
8. Add the finalization transition contract without adding a writer:
   - `SAFE_TO_POST` is the only hardened marker outcome that can later let `finalize_github_payload` set `FinalizationState.FINALIZED`, `final_github_payload`, `final_payload_hash`, and writer input
   - `RECONCILED_EXISTING` is a terminal no-post reconciliation result with an existing comment ID and no writer input release
   - `FAILED_CLOSED` leaves `final_github_payload`, `final_payload_hash`, and writer input unset
   - AUR-245 may wire a narrow optional marker-reconciliation input into `finalize_github_payload` or leave the current deferred finalization state if the handoff model and tests prove later wiring; in either case, duplicate-fingerprint preflight must run before any marker transport call
9. Update narrow durable docs:
   - marker trust, pagination fail-closed behavior, and transport summary shape in `docs/architecture/github-integration.md`
   - finalization/idempotency wording in `docs/architecture/side-effects.md`
   - harness bullet in `docs/harnesses/harness-engineering.md`

## Focused Harness

Create `tests/test_marker_hardening.py` covering:

- Paginated scan reads all pages before returning `SAFE_TO_POST` or `RECONCILED_EXISTING`.
- Matching trusted marker on a later page reconciles without releasing writer input.
- Early matching trusted marker plus later trusted conflict fails closed.
- Early matching trusted marker plus later malformed trusted marker fails closed.
- Early matching trusted marker plus later page failure fails closed.
- Trusted conflict before or after an exact marker fails closed.
- Exactly-at-page-cap and exactly-at-comment-cap scans can pass.
- Page-cap-plus-one and comment-cap-plus-one scans fail closed.
- Empty completed pages can pass; missing completion marker and cursor-without-progress fail closed.
- Page cap exceeded fails closed with stable reason code and no writer release.
- Comment cap exceeded fails closed with stable reason code and no writer release.
- Repeated cursor/incomplete pagination fails closed.
- Timeout, rate limit, forbidden, not found, unavailable, malformed response, unknown transport failure, and injected timeout budget exhaustion classify to stable reason code, retryability, and redacted summary.
- Transport summary exists on every outcome and includes endpoint kind, page count, comment count, marker count, retryability, reason code, and safe request ID.
- Transport summary rejects or drops token-looking request IDs and never exposes raw stderr, comment body, payload body, or token fragments.
- Markers from unapproved users, unconfigured bots, missing authors, unknown author types, differently cased authors, and owner/member/collaborator commenters that are not the approved actor are ignored.
- Approved actor user marker, approved actor bot marker, and configured trusted ReviewGraph bot marker are trusted.
- Configured bot name with `author_type=user` is not trusted through bot policy.
- Trusted same-target/same-findings/different-payload marker fails closed.
- Trusted malformed ReviewGraph-looking final-line marker with missing, malformed, reordered, or unreadable target fields fails closed.
- Spoofed malformed marker from an untrusted author is ignored.
- Body-middle copied marker remains inert.
- Multiple trusted identical matching markers reconcile with duplicate metadata and `writer_input_released=False`.
- Duplicate approved finding fingerprints fail before marker reconciliation/writer release.
- Duplicate approved finding fingerprints fail before marker transport calls, final payload construction, marker reconciliation, or writer release.
- Import-boundary proof for `src/reviewgraph/markers.py`.

Update existing tests as needed:

- `tests/test_markers.py` if the trust-neutral result or marker comment model gains fields.
- `tests/test_target_freshness.py` if duplicate-fingerprint preflight gets a narrower regression near current finalization tests.
- `tests/test_models.py` if marker reconciliation model fields move into shared models.

## Validation

Focused:

```bash
python -m pytest tests/test_marker_hardening.py -q
```

Regression:

```bash
python -m pytest tests/test_marker_hardening.py tests/test_markers.py tests/test_payload_hashes.py tests/test_payload_validation.py tests/test_approval.py tests/test_target_freshness.py tests/test_models.py -q
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
