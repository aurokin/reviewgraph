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
   - changed-line metadata derived from unified patches when possible;
   - anchor-unavailable metadata for files where changed lines cannot be derived;
   - `read_gaps`, initially empty for this happy-path metadata/files slice;
   - `thread_state_available`, initially `False` until later pagination/thread work;
   - optional `actor_permission` snapshot, initially `None`;
   - redaction status.
5. Do not fetch comments, reviews, review comments, or thread state in this issue. Later issues fill those resources and read-gap semantics.
6. Do not wire the adapter into CLI or runner in this issue; keep `AUR-239` responsible for the end-to-end GitHub dry-run path.

## Implementation Plan

1. Add focused failing tests in `tests/test_github_fake_read.py`.
   - PR ref parsing for `owner/repo#number`.
   - PR URL parsing for `https://github.com/owner/repo/pull/123`.
   - Fake transport happy path returns metadata, labels, target SHAs, merge base, changed files, patches, and `ReviewTarget`.
   - Fake transport records only read calls and has no writer/write API requirement.
   - Secret-like PR text or adapter error data is redacted in errors/status fields exposed by the adapter.
   - Changed ranges are derived from simple unified patch hunks, or explicit anchor-unavailable metadata is recorded for unavailable patches.

2. Implement `src/reviewgraph/github.py`.
   - Define `GitHubPRRef`, `GitHubChangedFileLines`, `GitHubReadResult`, and a small fake transport contract.
   - Implement `parse_github_pr_ref`.
   - Implement `read_github_pr_with_fake_transport`.
   - Convert fake transport dictionaries into existing typed models.
   - Keep validation errors specific and redacted.

3. Keep package and default test posture unchanged.
   - No new runtime dependency unless unavoidable.
   - No live `gh`, network, `requests`, approval, finalization, or writer import.
   - No CLI behavior change yet.

4. Update narrow docs only if the code introduces durable names or semantics not already covered by `MILESTONE_PLAN.md`.

## Verification

- Focused:
  - `python -m pytest tests/test_github_fake_read.py -q`
- Regression:
  - `python -m pytest tests/test_fixtures.py tests/test_memory.py tests/test_routing.py tests/test_cli.py -q`
- Hygiene:
  - `python -m py_compile src/reviewgraph/*.py`
  - `git diff --check`

## Out Of Scope

- Live GitHub reads.
- CLI GitHub PR target support.
- Runner integration for GitHub read results.
- Comments, reviews, review comments, and thread-state pagination.
- Fail-closed read-gap policy beyond carrying an empty read-gap list in the read-result envelope.
- Approval, finalization, writer behavior, inline comments, labels, statuses, and formal PR reviews.
