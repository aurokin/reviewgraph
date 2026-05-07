# Side-Effect Boundaries

The most important production boundary is between review generation and GitHub mutation.

## Rule

The graph may prepare a GitHub payload, but only the side-effect adapter may post it.

Clarification is not a GitHub write in MVP. If a reviewer needs human input, the graph should stop with a local question or structured clarification output rather than posting that question to the PR automatically.

## Posting plan

The renderer produces a `PostingPlan` before approval. Each output item has one destination:

- `local_only`
- `top_level_summary_item`
- `review_body_item`
- `inline_candidate`
- `suggested_reply`

MVP supports one write shape only: a top-level PR comment. Formal PR reviews, inline comments, and replies to human comments remain dry-run candidates until later side-effect decisions approve them.

## Approval contract

The approval gate receives a candidate payload:

- rendered markdown
- JSON findings
- selected postable finding IDs
- local notes excluded from posting
- clarification requests and answers
- local verdict
- posting plan
- candidate GitHub issue-comment payload with visible-body and findings hash inputs
- review target
- authenticated GitHub actor and permission summary
- redaction status for rendered output and candidate payloads

It returns:

```json
{
  "approved": true,
  "mode": "post_comment",
  "approved_finding_ids": ["finding-1", "finding-3"],
  "approved_final_payload_hash": "sha256:...",
  "approved_review_target_hash": "sha256:...",
  "approved_review_target": {
    "owner_repo": "owner/repo",
    "pr_number": 123,
    "base_sha": "def456",
    "head_sha": "abc123",
    "merge_base_sha": "789abc",
    "diff_basis": "merge_base"
  },
  "approved_github_actor": "reviewgraph-bot",
  "approved_permission": "write",
  "approved_permission_checked_at": "...",
  "include_public_verdict": false,
  "approved_by": "local-user",
  "timestamp": "..."
}
```

The final GitHub payload is built deterministically from `approved_finding_ids` and the candidate payload only after preflight passes. Candidate payloads expose visible-body and findings hash inputs only; they do not carry final payload hashes and are never writer input. `approved_final_payload_hash` binds to the full final issue-comment body after item selection, including the hidden ReviewGraph marker line. The marker's own `payload` field stores a separate visible-body hash that excludes the marker, avoiding a self-referential hash. Before the writer is invoked, ReviewGraph must either show the final payload or prove that its hash equals `approved_final_payload_hash`. If approving a subset changes the final body hash, previously computed final payload hashes must be rejected.

The actor and permission summary is endpoint-specific. It must identify the authenticated actor, credential principal/source, repo or installation permission, ability to call `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`, check method, checked target, checked-at time, and stable failure code when blocked. A broad repository role is not enough if the token or app cannot create the top-level issue comment.

`finalize_github_payload` owns the last pre-writer gate. It first validates approval shape, approved IDs, non-empty approved findings, and duplicate approved fingerprints. It then re-reads current actor, endpoint permission, and target freshness. If any current read or preflight check fails, finalization records failure without setting `final_github_payload` or `final_payload_hash`; the writer adapter is unreachable and ReviewGraph emits dry-run output with the fail-closed reason.

Only after preflight passes may finalization build the final issue-comment body, compute the final hash, validate redaction status, reconcile markers, and release writer input.

External read failures during approval or finalization fail closed. Timeout, rate limit, forbidden, not found, unavailable service, malformed response, unknown credential source, stale cached data, or missing checked-at timestamp cannot be treated as approval or freshness proof. These failures must emit redacted transport summaries with endpoint kind, retryability, stable failure code, and request ID when available.

## Non-interactive mode

In CI, webhook, config-only, or non-TTY CLI mode, MVP refuses post mode before approval input and before final payload construction. Do not infer approval from config alone, environment variables, previous approvals, or automation context. This is an explicit graph routing gate between `render_review` and `approval_gate`, not a prompt convention.

## Freshness and idempotency

`finalize_github_payload` must fail closed when the PR head/base/merge-base state no longer matches the approved review target. `post_or_emit` must only receive finalized payloads that already passed freshness checks.

Freshness includes owner/repo, PR number, base SHA, head SHA, merge-base SHA when available, and diff basis. Unknown merge-base freshness in post mode is a failure, not a warning.

Every postable finding must have a stable fingerprint, target SHA, and body hash. Duplicate postable or approved finding fingerprints are rejected before marker generation, approval final-hash validation, or writer reachability.

The writer must fetch existing ReviewGraph artifacts before posting and create at most one top-level comment for the approved run/retry sequence while preserving per-finding fingerprints for reconciliation. If a network timeout occurs after GitHub accepted a write, retry must reconcile by payload hash and finding fingerprint/body hash instead of posting a duplicate.

This is not a global cross-process locking guarantee. Two independent approved runs can race if they both scan before either comment exists. Global duplicate prevention requires external storage or locking and is deferred. If a later scan observes multiple trusted identical markers, ReviewGraph treats the payload as reconciled, emits duplicate-marker metadata, and posts zero additional comments. Trusted marker conflicts fail closed.

Embedded marker reconciliation is trusted only for comments authored by the approved GitHub actor or a configured trusted ReviewGraph bot. Markers from other authors are ignored. Malformed markers are inert unless they appear on a trusted-author comment for the same target and cannot be safely interpreted; in that case the graph fails closed rather than posting a duplicate.

## GitHub Artifact Discipline

MVP may post only a top-level PR comment after approval. `COMMENT` reviews, `APPROVE`, and `REQUEST_CHANGES` are deferred side effects even if the local verdict recommends them.

The local verdict is separate from the GitHub artifact kind and public markdown. MVP must not include request-changes wording in a GitHub comment unless `include_public_verdict` is explicitly approved.

Approval must be item-level. The user should be able to approve, reject, or defer each postable finding before the GitHub payload is submitted.

`suggested_reply` is local-only in MVP. It is never eligible for candidate or final GitHub payloads, including mixed runs that also contain approved findings.

If `approved_finding_ids` is empty, or the run has only local notes, suggested replies, suppressed findings, or clarification requests, the writer must not be invoked.
