# GitHub Integration

MVP should support local CLI review of GitHub PRs.

## Read operations

Read operations may use either:

- GitHub REST API through `GITHUB_TOKEN`
- `gh` CLI when available

Required context:

- owner/repo
- PR number
- title/body/author
- base/head refs and SHAs
- labels
- changed files
- patch/diff snippets

## Write operations

Write operations are optional and gated.

Allowed side effects after approval:

- top-level PR comment
- formal PR review comment

Deferred side effects:

- inline comments
- labels
- status checks
- request changes
- approvals

## Dry-run payload

Before posting, render:

- endpoint/action that would be called
- markdown body
- verdict/event
- selected reviewers
- finding counts

No side-effect adapter should be reachable unless `post_enabled=True` and `approval.approved=True`.
