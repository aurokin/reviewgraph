# Side-Effect Boundaries

The most important production boundary is between review generation and GitHub mutation.

## Rule

The graph may prepare a GitHub payload, but only the side-effect adapter may post it.

Clarification is not a GitHub write in MVP. If a reviewer needs human input, the graph should stop with a local question or structured clarification output rather than posting that question to the PR automatically.

## Implementation Agent Map

When changing side-effect behavior, keep ownership explicit:

- `posting.py` builds dry-run posting plans and candidate issue-comment payloads for rendering and approval.
- `hashing.py`, `markers.py`, and `payload_validation.py` define canonical hash domains, exact marker grammar, candidate/final payload validation, and marker reconciliation primitives.
- `approval.py` builds item-level approval proof and approval decisions from candidate payloads, selected public items, target binding, final full-body hash, actor/permission display proof, and approver metadata.
- `permissions.py` evaluates endpoint-specific issue-comment actor/permission proof before approval and during finalization.
- `finalization.py` owns writer-release preflight, current actor/permission re-check, target freshness re-check, final payload construction, final hash validation, redaction validation, marker reconciliation, and finalized writer-input release.
- `post_interaction.py` blocks non-interactive post mode before approval input or final payload construction.
- `writer_input.py` is the neutral finalized-input boundary between graph policy and writer adapters.
- `writer_fake.py` proves allowed post behavior without GitHub.
- `writer_github.py` is transport-focused. It receives finalized input only and handles POST result classification plus writer-local recovery after ambiguous accepted-write outcomes.
- `github_live_post.py` is a manual smoke harness, not production posting or a public CLI path.

Do not move approval, freshness, marker, redaction, routing, or item-selection decisions into reviewer prompts, renderers, GitHub read adapters, or writer adapters. Candidate payloads are approval/render artifacts only; they are not final payloads and are not writer inputs.

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
  "approved_item_ids": ["finding-1", "finding-3"],
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
  "approved_credential_principal": "gh-user:reviewgraph-bot",
  "approved_credential_source": "pat",
  "approved_repo_permission": "write",
  "approved_installation_permission": null,
  "approved_endpoint_permission": null,
  "approved_issue_comment_write": true,
  "approved_permission_check_method": "fake_issue_comment_permission_probe",
  "approved_permission_endpoint_method": "POST",
  "approved_permission_checked_target": {
    "owner_repo": "owner/repo",
    "pr_number": 123,
    "base_sha": "def456",
    "head_sha": "abc123",
    "merge_base_sha": "789abc",
    "diff_basis": "merge_base"
  },
  "approved_permission_checked_target_hash": "sha256:...",
  "approved_permission_endpoint": "/repos/owner/repo/issues/123/comments",
  "approved_permission_endpoint_kind": "issue_comment",
  "approved_permission_transport_summary": {
    "endpoint_kind": "issue_comment_permission",
    "retryable": false,
    "reason_code": null,
    "request_id": "REQ-123"
  },
  "include_public_verdict": false,
  "approved_by": "local-user",
  "timestamp": "..."
}
```

The final GitHub payload is built deterministically from `approved_item_ids` and the candidate payload only after preflight passes. Candidate payloads expose visible-body and findings hash inputs only; they do not carry final payload hashes and are never writer input. `approved_final_payload_hash` binds to the full final issue-comment body after item selection, including the hidden ReviewGraph marker line. The marker's own `payload` field stores a separate visible-body hash that excludes the marker, avoiding a self-referential hash. Before the writer is invoked, ReviewGraph must either show the final payload or prove that its hash equals `approved_final_payload_hash`. If approving a subset changes the final body hash, previously computed final payload hashes must be rejected.

The actor and permission summary is endpoint-specific. It must identify the authenticated actor, credential principal/source, broad repo permission or endpoint-specific permission, ability to call `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`, check method, checked target, checked-at time, and stable failure code when blocked. A broad repository role is not enough if the token or app cannot create the top-level issue comment.

Actor/permission proof uses a structured gate result before approval/finalization consumes it. The compatibility `permission` field is derived by ReviewGraph for display: broad repo permission first, then GitHub App installation permission, then normalized endpoint permission. Fake transport inputs must not provide a precomputed compatibility summary. `credential_source` distinguishes `pat`, `fine_grained_pat`, `github_app_installation`, and `github_app_user`.

The MVP endpoint check follows GitHub's issue-comment write behavior: broad repo `write`/`maintain`/`admin`, `issues:write`, or `pull_requests:write` can satisfy the permission summary, but only when the probe also proves `issue_comment_write=true`. Read-only endpoint permissions, unknown credential source, unknown permission, missing credential principal, missing check method, missing checked target, missing checked-at timestamp, target/endpoint mismatch, timeout, rate limit, forbidden, not found, unavailable service, malformed response, or stale cached proof fail closed with stable machine reason codes.

Actor/permission proof freshness is deterministic in harnesses. The evaluator receives an explicit `evaluated_at` timestamp and rejects checked-at values that are missing, not UTC RFC3339 with trailing `Z`, older than the allowed proof age, or more than 60 seconds in the future. The permission proof target is the full canonical `ReviewTarget.to_ordered_dict()` plus `ReviewTarget.target_hash()`. This binds the proof to the target supplied to the gate; live ref freshness remains the responsibility of target freshness finalization.

`finalize_github_payload` owns the last pre-writer gate. It first validates approval shape, approved IDs, non-empty approved findings, and duplicate approved fingerprints. It then re-reads current actor, endpoint permission, and target freshness. If any current read or preflight check fails, finalization records failure without setting `final_github_payload` or `final_payload_hash`; the writer adapter is unreachable and ReviewGraph emits dry-run output with the fail-closed reason.

Actor/permission re-checks have their own explicit preflight state, `actor_permission_finalization_check`. That result is not full payload finalization: a pass means only that the current actor/permission proof still matches the approval snapshot. It carries stable machine reason codes, current checked-at time, redacted transport summary, and allowlisted mismatched fields for actor, credential, permission, endpoint, or checked-at drift. It rejects unknown status and never carries final payload hashes, marker reconciliation, or writer state. Later target freshness, redaction, marker reconciliation, and writer-release checks compose with this preflight before `finalization_status` can become finalized.

Target freshness re-checks have their own explicit preflight state, `target_freshness_check`. The check consumes a current target probe and explicit evaluation time, rejects cached success from before approval, and compares owner/repo, PR number, base SHA, head SHA, merge-base SHA, and diff basis against the approved target. Missing merge-base freshness, unknown freshness, stale cache, future timestamps, transport failures, or target drift fail closed with stable reason code, retryability, request ID when available, and allowlisted mismatch fields. A passing target freshness check still does not release writer input while marker reconciliation is deferred.

Only after preflight passes may finalization build the final issue-comment body, compute the final hash, validate redaction status, reconcile markers, and release finalized writer input. Marker reconciliation has three durable outcomes: `SAFE_TO_POST`, `RECONCILED_EXISTING`, and `FAILED_CLOSED`. Only `SAFE_TO_POST` may produce `FinalizedIssueCommentWriterInput` for the writer. `RECONCILED_EXISTING` is a terminal no-post result tied to a trusted existing comment; `post_or_emit` may synthesize a reconciled writer result for reporting, but the writer is not invoked. `FAILED_CLOSED` leaves final payload and writer input unset.

External read failures during approval or finalization fail closed. Timeout, rate limit, forbidden, not found, unavailable service, malformed response, unknown credential source, stale cached data, or missing checked-at timestamp cannot be treated as approval or freshness proof. These failures must emit redacted transport summaries with endpoint kind, retryability, stable failure code, and request ID when available.

## Manual Live Post Smoke

Manual live post smoke uses the same approval, finalization, marker reconciliation, finalized writer-input, and real writer contracts as the fake writer route. It is not a production post mode and is not exposed through the public CLI.

The smoke can run only when a human opts in, a TTY is available, the target is an exact allowlisted disposable `owner/repo#pr_number`, the disposable marker `reviewgraph-disposable-live-post-ok` is present on the live PR, and the human types the exact final payload hash. Non-interactive contexts, fixture refs, fork PRs, missing approved-post artifacts, unsupported credential sources, stale target reads, missing merge-base proof, marker scan failure, or hash mismatch fail closed before writer reachability.

The approved-post artifact is a structured bridge between dry-run/fake approval proof and live finalization. It contains the full candidate posting plan and candidate findings, plus the approved subset. The live post module validates that artifact by rerunning normal candidate payload, approval proof, and final payload construction. It must not accept caller-supplied approval pass objects, target probes, actor probes, marker results, finalized writer input, or final-body-only artifacts as live proof.

Live proof is repeated after approval. Pre-approval reads are display evidence only; post-approval actor/permission, target freshness, and marker scans are the probes used by `finalize_github_payload`.

When the manual smoke posts, evidence records one POST max and the created comment ID. Automated cleanup, editing, or deletion is not part of MVP; the disposable PR comment remains until a human removes it.

## Non-interactive mode

In CI, webhook, config-only, or non-TTY CLI mode, MVP refuses post mode before approval input and before final payload construction. Do not infer approval from config alone, environment variables, previous approvals, or automation context. This is an explicit graph routing gate between `render_review` and `approval_gate`, not a prompt convention.

The policy input is explicit state, not ambient process inspection. Harnesses pass `run_mode=post`, `interactive=false`, and a concrete reason such as `ci`, `webhook`, `config_only`, or `non_tty_cli`; the gate records `post_interaction_gate.status=fail`, `post_enabled=false`, and a `non_interactive_post_mode` graph error. Dry-run mode bypasses this gate entirely and remains renderable in non-interactive contexts.

## Freshness and idempotency

`finalize_github_payload` must fail closed when the PR head/base/merge-base state no longer matches the approved review target. `post_or_emit` must only receive finalized payloads that already passed freshness checks.

Freshness includes owner/repo, PR number, base SHA, head SHA, merge-base SHA when available, and diff basis. Unknown merge-base freshness in post mode is a failure, not a warning.

Every postable finding must have a stable fingerprint, target SHA, and body hash. Duplicate postable or approved finding fingerprints are rejected before marker generation, approval final-hash validation, or writer reachability.

Finalization must fetch existing ReviewGraph artifacts before writer release and create at most one top-level comment for the approved run/retry sequence while preserving per-finding fingerprints for reconciliation. A no-post marker match requires target hash, findings hash, payload hash equality, trusted marker author, and complete paginated scan.

Ambiguous POST recovery is the only marker scan that may happen inside the real writer adapter. If the POST transport reports an ambiguous accepted-write outcome, such as a timeout after the request may have reached GitHub, the writer enters writer-local recovery to classify the result without posting again in the same approved run/retry sequence. That recovery uses the same marker parser/reconciliation primitives and the expected target, payload, and findings hashes already embedded in the finalized writer input. It may receive a comment-scan transport capability and trusted ReviewGraph author configuration, but it must not receive or own the pre-write marker reconciliation plan, change approved item selection, rebuild payloads, or decide `SAFE_TO_POST`. If the recovery scan finds the accepted artifact, the writer reports reconciled/posted evidence with zero additional POSTs; if the scan is incomplete, unavailable, rate-limited, timed out, marker-empty, or conflicting, it returns fail-closed or retryable-unknown with zero additional POSTs.

The real writer records a same-sequence POST guard before transport for every potentially accepted write attempt. The guard is keyed by run ID, target hash, payload hash, and findings hash. This covers ambiguous timeouts as well as malformed accepted responses, missing comment IDs, and response-author mismatches: a later call with the same finalized input is recovery-only and cannot issue a second POST.

This is not a global cross-process locking guarantee. Two independent approved runs can race if they both scan before either comment exists. Global duplicate prevention requires external storage or locking and is deferred. If a later scan observes multiple trusted identical markers, ReviewGraph treats the payload as reconciled, emits duplicate-marker metadata, and posts zero additional comments. Trusted marker conflicts fail closed.

Embedded marker reconciliation is trusted only for comments authored by the exact approved GitHub actor or a configured trusted ReviewGraph bot. Markers from other authors are ignored even when the author is an owner, member, collaborator, or trusted conversation-memory author. Malformed markers are inert for untrusted authors. A trusted final-line `<!-- reviewgraph:` marker that fails the exact parser fails closed rather than posting a duplicate.

## GitHub Artifact Discipline

MVP may post only a top-level PR comment after approval. `COMMENT` reviews, `APPROVE`, and `REQUEST_CHANGES` are deferred side effects even if the local verdict recommends them.

The local verdict is separate from the GitHub artifact kind and public markdown. MVP must not include request-changes wording in a GitHub comment unless `include_public_verdict` is explicitly approved.

Approval must be item-level. The user should be able to approve, reject, or defer each postable finding before the GitHub payload is submitted.

`suggested_reply` is local-only in MVP. It is never eligible for candidate or final GitHub payloads, including mixed runs that also contain approved findings.

If `approved_item_ids` is empty, or the run has only local notes, suggested replies, suppressed findings, or clarification requests, writer input must not be released.

`writer_release_preflight` is the pre-finalization handoff for later post-mode graph work. It records whether an approved item selection is eligible to enter finalization, but it does not release writer input by itself. Failures such as disabled posting, missing approval, rejected approval, failed approval build, duplicate approved item IDs/fingerprints, unknown approved IDs, or non-public approved items leave final payload, final payload hash, and writer result unset. Dry-run output also carries `public_payload_preparation` so local-only runs can explain that no public payload was prepared without confusing that state with missing human approval.
