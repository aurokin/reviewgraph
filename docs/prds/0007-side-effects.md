# PRD 0007: Side Effects

## Problem Statement

GitHub write behavior is the highest trust risk. A stale approval, duplicate retry, wrong artifact type, or public request-changes wording could undermine the product even if review quality is good.

## Solution

Implement side effects only after dry-run, quality classification, posting plan rendering, item-level approval, final payload hash validation, actor/permission proof, review target freshness, and idempotency reconciliation. MVP writes only one top-level PR comment for the approved payload.

## User Stories

1. As a maintainer, I want to see the exact public payload before posting, so that I know what ReviewGraph will write.
2. As a maintainer, I want item-level approval, so that I can approve only specific findings.
3. As a maintainer, I want approval bound to the PR target, so that a new push invalidates stale approval.
4. As a maintainer, I want final payload hash validation, so that approved text cannot drift.
5. As a maintainer, I want retries to avoid duplicate comments, so that network timeouts do not spam PRs.
6. As a maintainer, I want actor and permission shown before approval, so that I know which GitHub identity will post.
7. As a PR author, I want MVP comments to be top-level only, so that early inline mapping errors cannot produce misleading review comments.
8. As a developer, I want formal PR reviews rejected by schema in MVP, so that implementation cannot accidentally submit `COMMENT` reviews.
9. As a developer, I want no-approved-finding paths to skip the writer, so that local notes never become empty comments.

## Implementation Decisions

- MVP artifact kind is `issue_comment`.
- MVP endpoint is `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`.
- Formal PR review `COMMENT`, inline comments, labels, statuses, approvals, and request changes are deferred.
- Posting plan destinations include local only, top-level summary item, review body item, inline candidate, and suggested reply.
- `approval_gate` records approved item IDs and metadata only.
- `finalize_github_payload` builds the final body after item-level selection and validates the final hash.
- `approved_final_payload_hash` binds to the final issue-comment body after item selection.
- Finalization uses an embedded hidden marker as the final comment line.
- Marker fields include run ID, target hash, payload hash, and findings hash.
- Finalization fetches existing PR comments before writer release and reconciles matching markers.
- The writer receives only finalized writer input after marker reconciliation returns `SAFE_TO_POST`.
- The real writer may perform marker rescans only as writer-local recovery after an ambiguous accepted-write POST result; normal pre-write marker reconciliation remains finalization-owned, and ambiguous recovery must not issue a second POST in the same approved run/retry sequence.
- The real writer uses typed redacted transport evidence and records a same-sequence one-POST guard before potentially accepted write attempts.
- Manual live post smoke is opt-in, skipped by default, disposable-PR-only, exact-target allowlisted, TTY/human approved, typed-final-hash confirmed, and uses the real writer only after live post-approval actor/permission, target freshness, marker pagination, and finalization gates pass.
- If the PR target changes before posting, ReviewGraph fails closed and emits dry-run output.
- If no findings are approved, the writer is not invoked.

## Testing Decisions

- Fake writer tests cover approval rejection, empty approval, local-notes-only output, stale SHA, actor/permission failure, and idempotent retry.
- Tests assert `event: COMMENT` and `/pulls/{pr}/reviews` payloads are rejected.
- Tests assert approving a subset changes the final payload hash and stale final payload hashes are rejected. Candidate payloads expose only visible-body and findings hash inputs; they are never accepted as writer input.
- Tests assert a pre-seeded marker prevents duplicate posting after process restart.
- Live post smoke tests are fake-contract/default-safe by default; the marked live smoke is manual and only against disposable exact-target PRs. The smoke records source dry-run artifact hash, approved-post artifact hash, final hash, one-POST evidence, marker pagination evidence, actor/permission display evidence, and manual cleanup expectations.

## Out of Scope

- Formal PR reviews.
- Inline comments.
- Request changes and approvals.
- Editing or deleting prior ReviewGraph comments.
- Long-term external storage.

## Further Notes

This PRD can wait until dry-run review quality is useful. The writer should be small, boring, and heavily tested.
