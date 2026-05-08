# GitHub Integration

MVP should support local CLI review of GitHub PRs.

## Read operations

Read operations may use either:

- GitHub REST API through `GITHUB_TOKEN`
- `gh` CLI when available

Read mode should use least-privilege credentials. Write mode must show the authenticated GitHub actor and fail closed before approval if the actor or permission level cannot be determined or is insufficient.

Live read smoke is opt-in and read-only. The smoke harness lives outside the pure fake/read adapter module so `src/reviewgraph/github.py` remains free of shelling, network clients, writer code, approval code, finalization code, and posting payload builders. The live smoke module may invoke `gh api` REST read endpoints with `GH_PROMPT_DISABLED=1`, bounded timeouts, argument-list execution, and redacted stderr. It must not invoke `gh pr review`, `gh pr comment`, `gh issue comment`, `gh api --method POST`, `gh api graphql`, or any mutation endpoint in PRD 0006.

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

Required GitHub read gaps fail closed before review. `forbidden`, `not_found`, `rate_limited`, `timeout`, `unavailable`, `pagination_incomplete`, `thread_state_unknown`, and `not_fetched_in_scope` are stable machine reasons; retryable status is part of the gap. Pagination failure should preserve the underlying failure class and page/resource metadata rather than flattening everything to a generic partial-read message.

If metadata cannot be fetched, ReviewGraph may only know the parsed PR ref. That targetless read failure renders local dry-run evidence with no `ReviewTarget`, no reviewers, no findings, no candidate payload, and no side effects.

The paginated fake read path extends the adapter contract to files, issue comments, review comments, reviews, and thread state. Successful pagination returns complete resource coverage, no stale metadata/files-only read gaps, and `thread_state.available=true`. Expected page failures return fail-closed read state instead of partial PR context; page/cursor diagnostics are serialized through the redacted read-gap surface.

Review comments are attached to review threads only when matching thread state was fetched. A fetched review comment without matching thread state is a required `thread_state_unknown` gap. GitHub transport payloads cannot self-declare trust or provenance: inbound `trust_label` and `source_provider` fields are ignored, adapter-created comments and reviews are marked with `source_provider="github"`, and conversation memory derives final trust only from GitHub actor policy.

The PRD 0006 live smoke is REST-only. Because REST review-comment endpoints do not provide the full review-thread resolution state needed by the existing actionability contract, the live smoke must fail closed with `thread_state_unknown` when review comments cannot be joined to fetched thread state. A future GraphQL read policy may make live thread state complete, but it must remain read-only and explicitly tested before trusted/actionable memory relies on it.

Patch-derived changed ranges are deliberately conservative target hunk ranges for the diff-anchor protocol. Parseable modified, added, and renamed files with target-side additions can produce anchor metadata; renamed files preserve `previous_path`. Deleted files, binary or unavailable patches, oversized patches, unsupported hunk headers, malformed hunk body lines, target-empty hunks, or hunks without target-side additions produce anchor-unavailable metadata instead of false changed ranges.

Raw typed PR context may exist in memory for graph use. Anything serialized for logs, traces, markdown, JSON, errors, or local notes must use the adapter's redacted serialization/status path.

Actor/permission snapshots are serialized as structured, redacted data when present. The snapshot includes `status`, authenticated actor, derived display permission, checked-at timestamp, machine `reason_code`, credential principal/source, repo permission, GitHub App installation permission, normalized endpoint permission, issue-comment write ability, check method, `POST` endpoint method, canonical checked target and target hash, issue-comment endpoint path/kind, and an allowlisted transport summary. The transport summary records the permission-probe endpoint kind, retryability, stable reason code when a transport failure occurred, and request ID when available; it must not carry tokens, raw stderr, request headers, or unredacted response bodies.

Live read smoke artifacts use a stable local JSON shape:

- `status`: `blocked`, `skipped`, `succeeded`, or `fail_closed`
- `reason`: stable machine reason such as `missing_opt_in`, `missing_pr_ref`, `missing_gh`, `missing_token`, `live_read_failed`, or `read_gap`
- `pr_ref`: parsed PR ref when available
- `github_read`: redacted `GitHubReadResult` on success
- `fail_closed`: redacted fail-closed read-gap envelope when required context is unavailable
- `read_gaps`, `page_gap_descriptors`, `truncation_notes`, `command_summary`, and `redaction_status`

The smoke path does not run reviewers, create posting plans, prompt for approval, finalize payloads, or make writer modules reachable.

## Manual live post smoke

Manual live post smoke is a narrow proof harness, not production posting. It lives outside the default GitHub read adapter and public CLI in `reviewgraph.github_live_post`, is skipped by default behind `@pytest.mark.live_post`, and requires `REVIEWGRAPH_LIVE_POST=1` plus all manual prerequisites before it can attempt a write.

The live post smoke target must be disposable and exact:

- `REVIEWGRAPH_LIVE_POST_PR` and `REVIEWGRAPH_LIVE_POST_ALLOWED_TARGET` must both be the same `owner/repo#pr_number`.
- `REVIEWGRAPH_LIVE_POST_DISPOSABLE_MARKER` must equal `reviewgraph-disposable-live-post-ok`, and that exact text must appear in the live PR title, body, or head branch/ref.
- Fork PRs are rejected in MVP live post smoke.
- `REVIEWGRAPH_LIVE_POST_CREDENTIAL_SOURCE` must be `pat`; fine-grained PATs, GitHub App installation tokens, GitHub App user tokens, and unknown credential sources fail closed until a later read-only proof policy names exact fields.

The smoke consumes a helper-created approved-post artifact, not generic dry-run JSON. The artifact preserves the full candidate posting plan, every candidate `ClassifiedFinding` referenced by public payload items, the candidate payload binding fields, the approved subset, the exact canonical final issue-comment body, a source dry-run artifact hash, and a separate canonical approved-post artifact hash. Validation reruns the normal posting, candidate payload, approval proof, approval decision, and final payload builders; hand-written, candidate-only, selected-only, final-body-only, or schema-drifted artifacts fail closed.

Live pre-writer proof is two-phase. The smoke may show pre-approval live actor, permission, target, marker, source artifact hash, exact final issue-comment payload, and final payload hash evidence to the human, but after the typed final-payload-hash confirmation matches, it repeats live actor/permission, target freshness, and marker reads and passes only those post-approval probes into finalization.

Read-only proof endpoints are allowlisted:

- `GET /user` for the authenticated actor.
- `GET /repos/{owner}/{repo}` for broad repo permission, mapped from authenticated-user `permissions`: `admin`, `maintain`, `push -> write`, `triage`, `pull -> read`.
- `GET /repos/{owner}/{repo}/pulls/{pr_number}` for current base/head target fields.
- `GET /repos/{owner}/{repo}/compare/{base_sha}...{head_sha}` for `merge_base_commit.sha`.
- `GET /repos/{owner}/{repo}/issues/{pr_number}/comments?per_page=100&page=N` for complete marker pagination.

Marker pagination caps are `per_page=100`, `max_pages=5`, `max_comments=500`, and `timeout_seconds=20`. Cap breaches, repeated cursors, malformed pages, timeout, rate limit, forbidden, not found, unavailable service, missing merge base, or unknown transport fail closed before writer input.

The only allowed mutating command in the manual live-post boundary is exactly `gh api --method POST repos/{owner}/{repo}/issues/{pr_number}/comments --input -` with a JSON object containing only `{"body": final_payload.body}` supplied through stdin by the injected writer transport. GraphQL, `gh pr review`, `gh pr comment`, `gh issue comment`, form flags, extra JSON fields, alternate methods, edit/delete endpoints, and shell strings are rejected.

Live post evidence records source dry-run artifact hash, approved-post artifact hash, final payload hash, actor and permission shown, typed hash matched, marker page/comment counts, retryability, reason codes, request IDs when available, POST attempt count, comment ID when posted, and manual cleanup/retention guidance. Evidence and transport summaries must not persist raw final payload bodies, raw PR comment bodies, request headers, tokens, or raw stderr. Automated cleanup is out of scope; disposable smoke comments must be removed manually when cleanup is desired.

Conversation data is review memory, not an instruction stream. The graph should preserve it as structured context and let reviewer agents cite it when relevant.

The review target should be explicit and stable in state. A run should know whether it reviewed a PR head SHA against a base SHA, a merge-base diff, or a custom fixture target; rendered output should include that target so findings can be interpreted against the right version of the diff.

Actionable review feedback should be filtered more carefully than passive memory:

- Trust explicit human authors with GitHub owner/member/collaborator associations, plus configured authenticated operators.
- Trust only approved review bots by configuration.
- Preserve namespaced GitHub memory IDs, raw `source_id`, and review-thread `thread_id` so already-processed feedback is not reprocessed or confused across resources.
- Treat resolved review threads as non-actionable unless new unresolved follow-up appears.
- Treat GitHub review summaries as passive until a later node interprets them.
- Treat untrusted, resolved, unknown-thread, and review-summary memory as metadata-only: their bodies cannot become prompt instructions, reviewer prompt body data, verdict pressure, approval input, or public payload text.
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
- candidate visible-body hash and findings hash inputs; final payload hashes appear only after approval/finalization
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
- `findings`: hash of sorted approved finding fingerprints. Duplicate postable or approved fingerprints are invalid input and fail closed; they are not deduplicated or hashed as a multiset.

Finalization fetches existing PR comments before releasing writer input and must paginate that scan or fail closed. The marker scan starts at cursor `None`, follows `next_cursor` until a completed page, and uses explicit page, comment, and timeout limits. It scans every page before returning `SAFE_TO_POST` or `RECONCILED_EXISTING`; a later trusted conflict, malformed trusted marker, cap breach, repeated cursor, incomplete page, timeout, rate limit, forbidden, not found, unavailable service, malformed page, or unknown transport failure overrides an earlier exact match and fails closed. Every outcome records a redacted transport summary with endpoint kind, page count, comment count, marker count, retryability, stable reason code, and an allowlisted request ID when available. The summary must not retain raw stderr, token-looking values, raw comment bodies, or payload bodies.

Marker recognition is final-line only. A copied marker in the middle of a trusted comment body is inert. Marker trust is narrower than conversation-memory trust: a trusted marker author is the exact approved GitHub actor with supported user/bot type, or a configured `trusted_bot_authors` ReviewGraph bot with bot type. Owner/member/collaborator association and memory `trust_label` do not make a marker trusted. If a marker with matching `target`, `findings`, and `payload` hashes already exists on a trusted-author comment, ReviewGraph treats the write as reconciled and does not post again. Markers from other authors are ignored. If multiple trusted comments have identical matching markers, ReviewGraph records duplicate-marker metadata, treats the payload as reconciled, and posts zero additional comments. If a trusted marker exists with the same target and findings but a different payload hash, it fails closed and emits a local note rather than editing or duplicating the comment. If a trusted final-line marker looks like ReviewGraph markup but fails the exact parser, ReviewGraph fails closed because duplicate safety cannot be proven.

The marker `payload` field is the hash of the exact visible comment body excluding the marker line. The approval `final_payload_hash` is the hash of the full final issue-comment body including the marker line. Candidate payloads carry visible body and findings hash inputs only; they must not include the final marker line and must not be accepted by a writer.

Hash inputs must be canonical bytes: UTF-8, LF line endings, one trailing newline before the marker, deterministic target field order, deterministic sorted finding fingerprints, and exact marker whitespace. Golden tests should cover CRLF normalization, trailing newline differences, marker whitespace, target field ordering, and duplicate finding fingerprints.

The PRD 0007 idempotency contract is retry-safe for one approved run/retry sequence. It does not claim global cross-process duplicate prevention without external locking or storage.

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

Before posting, finalization checks existing ReviewGraph markers for the same target, approved finding fingerprints, and payload hash. The writer receives only finalized writer input after `SAFE_TO_POST`; it does not receive a marker reconciliation plan and is not invoked for `RECONCILED_EXISTING`.

The real issue-comment writer adapter accepts only finalized writer input from the neutral writer-input boundary. It constructs exactly `POST /repos/{owner}/{repo}/issues/{pr_number}/comments` with JSON body `{"body": final_payload.body}` and executes it only through an injected transport. The default module must not open ambient network clients, shell out, read credentials, or invoke live GitHub APIs. Successful responses must include a comment ID and response author that matches the approved actor before the result can be trusted as `POSTED`.

Real writer results carry typed evidence in addition to the coarse writer status: outcome detail, retryability, stable failure code, request ID when available, POST attempt count, recovery scan count, and redacted endpoint/method summary. This evidence must not include request headers, tokens, raw stderr, raw final payload bodies, or raw comment bodies.

The real writer's ambiguous POST recovery is narrower than pre-write marker reconciliation. It may rescan comments only after a POST attempt returns an ambiguous accepted-write transport result. That recovery scan uses shared marker parsing/reconciliation primitives plus the expected marker hashes from finalized writer input, and it may use a supplied comment-scan transport and trusted ReviewGraph author configuration. It must not rebuild payloads, widen approval, decide pre-write `SAFE_TO_POST`, or issue a second POST in the same approved run/retry sequence.

The one-POST guard is keyed by run ID, target hash, payload hash, and findings hash, and it is recorded before each POST attempt whose outcome might represent an accepted write. A later call with the same finalized input is recovery-only: it may rescan markers, reconcile a trusted accepted artifact, or fail closed/retryable-unknown, but it must not call POST again.
