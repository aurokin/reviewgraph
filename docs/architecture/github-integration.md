# GitHub Integration

MVP should support local CLI review of GitHub PRs.

## Read operations

Read operations may use either:

- GitHub REST API through `GITHUB_TOKEN`
- `gh` CLI when available

Read mode should use least-privilege credentials. Write mode must show the authenticated GitHub actor and fail closed before approval if the actor or permission level cannot be determined or is insufficient.

Required context:

- owner/repo
- PR number
- title/body/author
- base/head refs and SHAs
- merge base or equivalent comparison base when available
- labels
- changed files
- patch/diff snippets
- PR comments, review summaries, review comments, and thread resolution state when available

## Fake read adapter contract

The first GitHub read implementation is fake and read-only. It accepts `owner/repo#number` and `https://github.com/{owner}/{repo}/pull/{number}` references, then returns a `GitHubReadResult` envelope from deterministic transport data. GitHub Enterprise hosts are deferred until a host policy exists.

`GitHubReadResult` is not a writer payload and is not approval input. It carries:

- parsed PR ref
- `ReviewTarget`
- `PullRequestContext`
- PR metadata extras that the current `PullRequestContext` does not store: PR author, base ref, and head ref
- changed-line metadata for anchoring, represented by objects with `path`, `changed_ranges`, `status`, `previous_path`, `patch_status`, and `contains_line()`
- anchor-unavailable metadata for unsupported or unavailable patches
- resource coverage, initially `metadata_files_only`
- required read gaps for comments, reviews, review comments, and thread state while scope is `metadata_files_only`
- thread-state availability with an explicit reason
- optional actor/permission snapshot for later approval work
- redaction status for serializable/display surfaces

The metadata/files-only result is adapter-contract-ready, not graph-complete PRD 0006 context. Comments, reviews, review comments, and thread state remain `not_fetched_in_scope` until later slices fetch and paginate them. A later graph integration must not treat metadata/files-only coverage as a complete review context.

Patch-derived changed ranges are deliberately conservative target hunk ranges for the diff-anchor protocol. Parseable modified, added, and renamed files with target-side additions can produce anchor metadata; renamed files preserve `previous_path`. Deleted files, binary or unavailable patches, oversized patches, unsupported hunk headers, malformed hunk body lines, target-empty hunks, or hunks without target-side additions produce anchor-unavailable metadata instead of false changed ranges.

Raw typed PR context may exist in memory for graph use. Anything serialized for logs, traces, markdown, JSON, errors, or local notes must use the adapter's redacted serialization/status path.

Conversation data is review memory, not an instruction stream. The graph should preserve it as structured context and let reviewer agents cite it when relevant.

The review target should be explicit and stable in state. A run should know whether it reviewed a PR head SHA against a base SHA, a merge-base diff, or a custom fixture target; rendered output should include that target so findings can be interpreted against the right version of the diff.

Actionable review feedback should be filtered more carefully than passive memory:

- Trust explicit human authors with GitHub owner/member/collaborator associations, plus configured authenticated operators.
- Trust only approved review bots by configuration.
- Preserve seen comment/review IDs so already-processed feedback is not reprocessed.
- Treat resolved review threads as non-actionable unless new unresolved follow-up appears.
- Do not post replies to human-authored comments automatically. MVP may produce a local suggested reply for the human operator, but `suggested_reply` items are never included in ReviewGraph-created GitHub payloads.

Adapters must paginate files, comments, review comments, and reviews. If ReviewGraph truncates changed files, patches, or conversation memory because of configured limits, it must surface that fact as a local note and avoid postable findings that depend on omitted context.

Approved review bots are configured with a default-deny allowlist:

```yaml
trusted_operator_authors:
  - "octocat"
trusted_bot_authors:
  - "chatgpt-codex-connector[bot]"
```

Bot comments from unlisted accounts remain passive memory and cannot trigger `conversation_patterns` or actionable feedback. Comments with missing or unknown actor type also fail closed for trust.

## Write operations

Write operations are optional and gated.

GitHub review behavior has three review event types: comment, approve, and request changes. ReviewGraph should follow that model rather than inventing its own merge semantics. See GitHub's docs for [pull request reviews](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/about-pull-request-reviews) and the REST API for [pull request reviews](https://docs.github.com/en/rest/pulls/reviews).

Allowed MVP side effects after approval:

- top-level PR comment

Deferred side effects:

- formal PR review with `COMMENT`
- inline comments
- labels
- status checks
- request changes
- approvals

A local `request_changes` recommendation may appear in dry-run output, but submitting a GitHub `REQUEST_CHANGES` review is deferred until the side-effect policy, authorization model, and approval proof explicitly support it.

## Dry-run payload

Before posting, render:

- endpoint/action that would be called
- markdown body
- artifact kind, always `issue_comment` for MVP
- endpoint, `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`
- local verdict, excluded from public markdown unless explicitly approved
- selected reviewers
- selected postable finding IDs
- finding counts
- local notes excluded from posting
- clarification requests, if any
- review target SHAs
- payload hash
- idempotency fingerprints

No side-effect adapter should be reachable unless `post_enabled=True` and `approval.approved=True`.

MVP schema must reject Pull Request Review payload fields such as `event: COMMENT` and endpoints under `/pulls/{pr_number}/reviews`.

## Posted finding memory

MVP uses an embedded hidden marker in the top-level PR comment because long-term storage is out of scope. The marker must be the exact final line of the generated comment:

```markdown
<!-- reviewgraph:v1 run_id=review-run-id target=sha256:... payload=sha256:... findings=sha256:... -->
```

Fields:

- `run_id`: ReviewGraph run ID.
- `target`: hash of owner/repo, PR number, base SHA, head SHA, merge-base SHA, and diff basis.
- `payload`: hash of the exact posted body excluding the marker.
- `findings`: hash of sorted approved finding fingerprints.

The writer fetches existing PR comments before posting and must paginate that scan or fail closed. It recognizes markers only when the final line exactly matches the ReviewGraph marker grammar. A copied marker in the middle of a trusted comment body is inert. If a matching `target` and `findings` marker already exists on a comment authored by the approved GitHub actor or a configured trusted ReviewGraph bot, it treats the write as reconciled and does not post again. Markers from other authors are ignored. If a trusted marker exists with the same target and findings but a different payload hash, it fails closed and emits a local note rather than editing or duplicating the comment.

The marker `payload` field is the hash of the exact visible comment body excluding the marker line. The approval `final_payload_hash` is the hash of the full final issue-comment body including the marker line.

Hash inputs must be canonical bytes: UTF-8, LF line endings, one trailing newline before the marker, deterministic target field order, deterministic sorted finding fingerprints, and exact marker whitespace. Golden tests should cover CRLF normalization, trailing newline differences, marker whitespace, target field ordering, and duplicate finding fingerprints.

The writer also records in-memory result metadata for the current run:

```json
{
  "run_id": "review-run-id",
  "finding_fingerprint": "stable-fingerprint",
  "body_hash": "sha256:...",
  "target_head_sha": "abc123",
  "github_artifact_kind": "issue_comment",
  "github_artifact_id": "123456"
}
```

Before posting, the writer checks existing ReviewGraph markers for the same target and approved finding fingerprints.
