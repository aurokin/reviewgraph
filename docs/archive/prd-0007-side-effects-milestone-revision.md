# PRD 0007: Side Effects (milestone revision)

Archived. This is a later revision of [PRD 0007](../prds/0007-side-effects.md) that was kept as the milestone brief while the side-effect work landed. It is kept for history. Where it differs from current docs, the current docs win: [PRD 0007](../prds/0007-side-effects.md), [Side Effects](../architecture/side-effects.md), [GitHub Integration](../architecture/github-integration.md), and [Decision 0008](../decisions/0008-finalization-owns-writer-release.md).

The Problem Statement and most user stories match PRD 0007. The differences are below.

## Solution

Implement side effects only after dry-run, quality classification, posting plan rendering, item-level approval, final payload hash validation, actor/permission proof, review target freshness, marker reconciliation, and writer-release finalization. MVP writes only one top-level PR comment for the approved payload, and only through non-default proof/manual paths until a later milestone adds a public production posting command.

## User Story Change

5. As a maintainer, I want retries to avoid duplicate comments in one approved run/retry sequence, so that ambiguous write outcomes do not spam PRs.

## Implementation Decisions

- MVP artifact kind is `issue_comment`.
- MVP endpoint is `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`.
- Formal PR review `COMMENT`, inline comments, labels, statuses, approvals, request changes, automatic replies, editing/deleting comments, and long-term storage are deferred.
- Posting plan destinations include local only, top-level summary item, review body item, inline candidate, and suggested reply.
- Candidate payloads are render/approval inputs only. They expose visible-body and findings hash inputs and must never be accepted as writer input.
- `approval_gate` records approved item IDs and approval metadata only, including final full-body hash, target binding, actor, endpoint-specific permission, checked-at time, approver, and public-verdict choice.
- `finalize_github_payload` owns the last pre-writer gate: approval shape, approved IDs, non-empty approved public findings, duplicate fingerprints, current actor/permission re-check, current target freshness re-check, final body/hash construction, redaction validation, marker reconciliation, and finalized writer-input release.
- Finalization uses an embedded hidden marker as the final comment line. Marker fields include run ID, target hash, visible-payload hash, and approved-findings hash.
- Finalization fetches and paginates existing PR comments before writer release and reconciles trusted matching markers. `SAFE_TO_POST` is the only marker outcome that releases writer input; `RECONCILED_EXISTING` is terminal no-post; `FAILED_CLOSED` blocks writer reachability.
- The writer receives only finalized top-level issue-comment writer input. It does not own approval, target freshness, marker policy, item selection, or pre-write marker reconciliation.
- The real writer may rescan markers only as writer-local recovery after an ambiguous accepted-write POST outcome, and it must not issue a second POST in the same approved run/retry sequence.
- Manual live post smoke is opt-in, skipped by default, disposable-PR-only, exact-target allowlisted, TTY/human approved, typed-final-hash confirmed, and uses the real writer only after live post-approval actor/permission, target freshness, marker pagination, and finalization gates pass.
- If the PR target changes or cannot be freshly proven before posting, ReviewGraph fails closed and emits dry-run output.
- If no findings are approved, the writer is not invoked.
- Global cross-process duplicate prevention is deferred until an external lock or storage design exists.

## Testing Decisions

- Payload hash tests cover canonical visible body, final full body, marker payload, review target, approved-findings hash domains, newline normalization, marker whitespace, target ordering, and duplicate fingerprints.
- Posting and payload-validation tests cover candidate/final split, top-level issue-comment-only payloads, local-only exclusion, suggested-reply exclusion, public request-changes wording guards, and rejection of formal PR review endpoints/events.
- Approval tests cover item-level approval, final-hash binding, subset hash changes, actor/permission snapshot binding, and stale/invalid approval failure.
- Actor/permission and target freshness tests use fake probes, endpoint-specific issue-comment permission, deterministic checked-at freshness, transport failure taxonomy, stale-cache rejection, role/token mismatch, actor drift, permission drift, and target drift.
- Marker tests cover exact final-line grammar, pagination, author trust, malformed trusted markers, trusted conflicts, duplicate trusted matches, cap/timeouts, redacted summaries, and duplicate-fingerprint failure before marker scan or writer reachability.
- Non-interactive and no-approved-finding tests prove no approval input, final payload, marker reconciliation, or writer calls occur in blocked/local-only paths.
- Fake writer/post-mode graph tests prove dry-run writes zero times, blocked paths write zero times, and an approved finalized top-level comment calls the fake writer at most once.
- Real writer adapter tests use fake transports by default, assert exact issue-comment POST shape, validate response author binding, prove no ambient network/shell/credential dependency, and prove ambiguous accepted-write recovery performs no second POST in the same approved run/retry sequence.
- Manual live-post contract tests are fake/default-safe by default; the marked live smoke is skipped unless explicitly opted into against a disposable exact target with typed hash confirmation.

## Out of Scope

- Formal PR reviews.
- Inline comments.
- Request changes and approvals.
- Labels, statuses, automatic replies, editing, or deleting prior ReviewGraph comments.
- Public production posting command.
- Live LLM behavior.
- Long-term external storage or cross-process locking.

## Further Notes

Finalization owns writer release. The writer should stay small, transport-focused, boring, and heavily tested.
