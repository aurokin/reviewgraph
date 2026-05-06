# ISSUE PLAN: AUR-213 Read GitHub PR Metadata With Fake Transport

Active issue plan for `AUR-213` / `RG-024: Read GitHub PR Metadata With Fake Transport`.

Linear remains the source of truth for issue state and relationships.

## Linear Snapshot

- Issue: `AUR-213`
- Status at plan time: `In Progress`
- Milestone: `PRD 0006: GitHub Read And Memory`
- Title: `RG-024: Read GitHub PR Metadata With Fake Transport`
- Harness from Linear: `python -m pytest tests/test_github_fake_read.py`
- Out of scope from Linear: live GitHub and comments pagination.

## Intent

Create the first GitHub read adapter contract using a deterministic fake transport. This slice should parse PR refs, fetch PR metadata and changed files, return `PullRequestContext` plus `ReviewTarget`, and require no write credentials.

This issue should also establish the early bridge shape required by the milestone plan so later GitHub dry-run work does not discover runner incompatibility late: an explicit read-result envelope, changed-line metadata or anchor-unavailable metadata, read gaps list, thread-state availability marker, optional actor/permission snapshot field, and redaction status for GitHub-sourced text/errors.

## Current Baseline

- There is no `src/reviewgraph/github.py`.
- `src/reviewgraph/fixtures.py` already parses fixtures into `PullRequestContext` and `ReviewTarget`.
- `src/reviewgraph/models.py` already has `ReviewTarget`, `PullRequestContext`, `PullRequestChangedFile`, `PullRequestComment`, `PullRequestReview`, `PullRequestReviewThread`, `ReadGap`, and `RedactionStatus`.
- `src/reviewgraph/runner.py` still expects fixture-specific `ChangedFile.changed_ranges` for diff anchors and fixture raw reviewer outputs for fake reviewer execution.
- `src/reviewgraph/redaction.py` provides shared redaction; adapter errors and GitHub-sourced text must use it before display or persistence.

## Decisions

1. Add `src/reviewgraph/github.py` as the read adapter boundary. Keep it independent of CLI, runner, approval, finalization, and writer code.
2. Use a protocol-style fake transport interface with read-only methods. It must not expose or require write credentials.
3. Parse both `owner/repo#number` and GitHub PR URLs into a typed reference. Invalid refs fail with redacted errors.
4. Return a `GitHubReadResult` envelope containing:
   - parsed PR ref;
   - `PullRequestContext`;
   - `ReviewTarget`;
   - PR author plus base/head ref names as GitHub metadata extras, because `PullRequestContext` currently stores SHAs but not these fields;
   - changed-line metadata derived from unified patches when possible;
   - anchor-unavailable metadata for files where changed lines cannot be derived;
   - a resource-coverage/read-scope marker that says this result is `metadata_files_only`, with `metadata` and `files` complete but `comments`, `reviews`, `review_comments`, and `thread_state` not fetched yet;
   - `read_gaps`, initially empty for metadata/files resources only;
   - `thread_state_available` with an explicit reason such as `not_fetched_in_scope`, distinct from future `unavailable_from_transport`;
   - optional `actor_permission` snapshot, initially `None`;
   - redaction status.
5. `GitHubChangedFileLines` must directly satisfy the current changed-file protocols used by `diff_anchor.py`: it should expose `path`, `changed_ranges`, `status`, `previous_path`, `patch_status`, and `contains_line()`. Unsupported or unavailable patch shapes must not create false anchors; they should produce explicit anchor-unavailable metadata.
6. Do not wire the adapter into CLI or runner in this issue; keep `AUR-239` responsible for the end-to-end GitHub dry-run path.
7. Do not fetch comments, reviews, review comments, or thread state in this issue. Later issues fill those resources and convert missing required resources into fail-closed read gaps before graph-ready use.
8. Support only `github.com` PR URLs for MVP. GitHub Enterprise host support is deferred until a host policy exists.
9. Preserve raw typed PR context in memory for later graph use, but expose redacted serialization/status/error helpers for any display, logging, trace, or persisted artifact.

## Implementation Plan

1. Add focused failing tests in `tests/test_github_fake_read.py`.
   - PR ref parsing for `owner/repo#number`.
   - PR URL parsing for `https://github.com/owner/repo/pull/123`.
   - Invalid refs reject `#0`, negative and non-integer PR numbers, missing owner/repo, unsupported hosts or schemes, query/fragment URLs, and redacted invalid input in error text.
   - Fake transport happy path returns metadata, PR author, base/head refs, labels, target SHAs, merge base, changed files, patches, and `ReviewTarget`.
   - `GitHubReadResult` records resource coverage as metadata/files only and cannot be mistaken for graph-ready complete context.
   - Fake transport records only read calls and has no writer/write API requirement.
   - Secret-like PR title/body/patch text and adapter error data are redacted in serializable envelope/status/error helpers, while raw typed context remains available only as in-memory data.
   - Changed ranges are derived from unified patch hunks and directly satisfy existing anchor protocols.
   - Multi-hunk patches and multiline finding ranges are supported.
   - Deleted, binary/no-patch, oversized/unavailable patch, unsupported hunk, and rename cases degrade to anchor-unavailable metadata instead of partial or false anchors.

2. Implement `src/reviewgraph/github.py`.
   - Define `GitHubPRRef`, `GitHubPRMetadata`, `GitHubChangedFileLines`, `GitHubReadResult`, resource coverage/status values, structured adapter errors, and a small fake transport contract.
   - Implement `parse_github_pr_ref`.
   - Implement `read_github_pr_with_fake_transport`.
   - Convert fake transport dictionaries into existing typed models.
   - Keep validation errors specific, structured, and redacted.

3. Add boundary and docs proof.
   - Add or extend static import tests so `src/reviewgraph/github.py` cannot import live transports, network clients, approval, finalization, posting writer, or side-effect code.
   - Document the new fake read contract, metadata extras, resource coverage, raw-vs-redacted result rule, and changed-line bridge in `docs/architecture/github-integration.md`.
   - Add the AUR-213 harness expectation to `docs/harnesses/harness-engineering.md`.

4. Keep package and default test posture unchanged.
   - No new runtime dependency unless unavoidable.
   - No live `gh`, network, `requests`, approval, finalization, or writer import.
   - No CLI behavior change yet.

## Verification

- Focused:
  - `python -m pytest tests/test_github_fake_read.py -q`
- Regression:
  - `python -m pytest tests/test_fixtures.py tests/test_memory.py tests/test_routing.py tests/test_cli.py tests/test_redaction.py tests/test_contract_boundaries.py tests/test_reviewer_context.py tests/test_context_budget.py tests/test_render.py -q`
- Hygiene:
  - `python -m py_compile src/reviewgraph/*.py`
  - `python scripts/check_docs.py`
  - `git diff --check`

## Out Of Scope

- Live GitHub reads.
- CLI GitHub PR target support.
- Runner integration for GitHub read results.
- Comments, reviews, review comments, and thread-state pagination.
- Fail-closed read-gap policy beyond carrying an empty read-gap list in the read-result envelope.
- Approval, finalization, writer behavior, inline comments, labels, statuses, and formal PR reviews.
