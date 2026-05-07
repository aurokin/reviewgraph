# ISSUE PLAN: AUR-214 Paginate GitHub Files Comments And Reviews

Active issue plan for `AUR-214` / `RG-025: Paginate GitHub Files Comments And Reviews`.

Linear remains the source of truth for issue state and relationships.

## Linear Snapshot

- Issue: `AUR-214`
- Status at plan time: `In Progress`
- Milestone: `PRD 0006: GitHub Read And Memory`
- Title: `RG-025: Paginate GitHub Files Comments And Reviews`
- Harness from Linear: `python -m pytest tests/test_github_pagination.py`
- Linear comments at start: none.
- Out of scope from Linear: trust classification and live calls.

## Intent

Extend the fake GitHub read adapter to prove complete pagination across files, issue comments, review comments, reviews, and thread state before context-budget truncation can run. This issue should turn the AUR-247 read-gap policy into the adapter's partial-pagination failure behavior, without adding live GitHub calls or wiring GitHub reads into the CLI/runner.

## Current Baseline

- `src/reviewgraph/github.py` has `read_github_pr_with_fake_transport()` for metadata/files-only reads using non-paginated fake transport calls.
- `GitHubReadResult` carries `PullRequestContext`, `ReviewTarget`, changed-line metadata, resource coverage, read gaps, thread-state availability, and redaction status.
- Metadata/files-only reads intentionally produce required gaps for `comments`, `reviews`, `review_comments`, and `thread_state`.
- `src/reviewgraph/read_gaps.py` classifies read gaps, produces required `github_read_gap` errors, and provides fail-closed read outcomes/rendering.
- `PullRequestContext` already stores `comments`, `reviews`, and `review_threads`.
- `PullRequestComment`, `PullRequestReview`, and `PullRequestReviewThread` model the data needed by `memory.py`, but AUR-215 owns trust/actionability semantics for GitHub-derived memory.

## Decisions

1. Preserve the existing metadata/files-only fake adapter. Add a new paginated fake-read entry point rather than changing the existing AUR-213 contract out from under its tests.
2. Add a paginated fake transport protocol with page-based read methods for:
   - changed files;
   - issue comments;
   - review comments;
   - reviews;
   - review threads / thread state.
3. Keep pagination deterministic and local. The fake transport should return explicit page payloads with `items`, `has_next_page`, and a next-page cursor or number; no network, `gh`, live GitHub client, or writer code.
4. Pagination completes before truncation. AUR-214 proves this by fetching page 2 data that would exceed a later budget or change downstream context, while no `TruncationNotice` is created in the adapter.
5. Partial pagination failure uses AUR-247 policy: produce read gaps with underlying failure reason/page metadata and fail-closed state. Do not silently return first-page-only context.
6. A fully paginated read clears the metadata/files-only gaps for comments, reviews, review comments, and thread state; resource coverage becomes complete for all fetched resources.
7. Thread state availability is explicit. Complete thread-state pagination with concrete thread statuses sets `available=True`; unknown or unavailable required thread state creates a required read gap.
8. Review comments should be represented as `PullRequestComment` values inside `PullRequestReviewThread` where thread context exists. If a review comment page is read but matching thread state is unavailable, it must not become actionable memory later; this issue should mark that through read gaps/thread-state availability, not trust classification.
9. Do not implement trust labels beyond deterministic passthrough/default values required to construct model objects. AUR-215 owns human/bot trust rules, resolved/unknown actionability, and conversation-memory policy.
10. Do not wire CLI, runner, live read, approval, finalization, posting, or writer behavior.

## Implementation Plan

1. Add `tests/test_github_pagination.py` first.
   - Happy path with multi-page files proves every file page is fetched and `changed_files`/changed-line metadata include later-page files.
   - Multi-page issue comments are fetched and serialized into `PullRequestContext.comments`.
   - Multi-page review comments plus thread state are fetched and serialized into `PullRequestContext.review_threads`.
   - Multi-page reviews are fetched and serialized into `PullRequestContext.reviews`.
   - Resource coverage is complete and read gaps are empty after a successful full paginated read.
   - Thread-state availability is `available=True` when thread state pages complete.
   - Page 2 content includes text that would affect routing/trust/redaction later, proving first-page-only success would be observable.
   - Pagination failure on a later page returns a required read gap/fail-closed outcome instead of partial context, preserving the underlying failure reason and page metadata.
   - Tests prove pagination happens before truncation by asserting no adapter-level truncation is emitted while later-page items remain present.

2. Extend `src/reviewgraph/github.py`.
   - Add resource coverage constructor for all resources complete.
   - Add paginated fake transport protocol and page payload validation helpers.
   - Add `read_github_pr_with_paginated_fake_transport()` or equivalent.
   - Reuse existing PR metadata, file conversion, changed-line parsing, redaction, and read-result serialization.
   - Convert comment/review/thread payload dictionaries into existing model types.
   - Keep adapter errors structured and redacted.
   - Keep dependencies limited to models, redaction, and read-gap policy; do not import runner, CLI, memory trust policy, approval, finalization, posting, writer, or network clients.

3. Use AUR-247 for gap behavior.
   - Later-page failure should classify a `ReadGap` with the resource, required flag, specific reason, retryability, and page descriptor metadata where available.
   - Required pagination gaps should be usable by `build_fail_closed_read_outcome()`.
   - Successful full pagination should not carry stale metadata/files-only gaps.

4. Update durable docs.
   - `docs/architecture/github-integration.md`: paginated fake-read contract, complete coverage, and thread-state availability.
   - `docs/harnesses/harness-engineering.md`: `tests/test_github_pagination.py` coverage and pagination-before-truncation rule.

## Verification

- Focused:
  - `python -m pytest tests/test_github_pagination.py -q`
- Related regression:
  - `python -m pytest tests/test_github_fake_read.py tests/test_github_read_gaps.py tests/test_memory.py tests/test_contract_boundaries.py -q`
- Wider PRD 0006/runner regression:
  - `python -m pytest tests/test_fixtures.py tests/test_routing.py tests/test_cli.py tests/test_redaction.py tests/test_reviewer_context.py tests/test_context_budget.py tests/test_diff_anchor.py -q`
- Hygiene:
  - `python -m pytest -q`
  - `python -m py_compile src/reviewgraph/*.py`
  - `python scripts/check_docs.py`
  - `git diff --check`

## Out Of Scope

- Live GitHub reads.
- CLI GitHub PR target support.
- Runner integration for GitHub read results.
- Trust classification and memory actionability.
- Conversation-pattern reviewer routing from GitHub memory.
- Context-budget implementation changes beyond proving adapter pagination precedes truncation.
- Approval, finalization, writer behavior, inline comments, labels, statuses, and formal PR reviews.
