# MILESTONE PLAN: PRD 0006 GitHub Read And Memory

Active execution artifact for this milestone. Linear remains the durable source for issue status, milestone order, blockers, relationships, and handoff details; if this file conflicts with Linear, Linear wins. Re-fetch current Linear state before starting each issue.

## Linear Scope Snapshot

- Milestone: `PRD 0006: GitHub Read And Memory`
- Milestone ID: `d5570b49-93a7-453b-af77-9e8a5396d21b`
- Current execution status as of 2026-05-07: `AUR-213`, `AUR-247`, and `AUR-214` are `Done`; `AUR-215` is `In Progress`; remaining active PRD 0006 issues are `Backlog`.
- Active implementation issues:
  - `AUR-213` / `RG-024: Read GitHub PR Metadata With Fake Transport` / `Done`
  - `AUR-247` / `RG-058: Fail Closed On GitHub Read Gaps` / `Done`
  - `AUR-214` / `RG-025: Paginate GitHub Files Comments And Reviews` / `Done`
  - `AUR-215` / `RG-026: Apply GitHub Trust Rules To Memory` / `In Progress`
  - `AUR-236` / `RG-047: Select Conversation Pattern Reviewers` / `Backlog`
  - `AUR-239` / `RG-050: Add GitHub PR Dry-Run Adapter Path` / `Backlog`
  - `AUR-216` / `RG-027: Add Opt-In Live Read Smoke` / `Backlog`
- Gate issue:
  - `AUR-259` / `Complete PRD 0006: GitHub Read And Memory` / `Backlog`
- Canceled duplicate:
  - `AUR-252` / `RG-058: Fail Closed On GitHub Read Gaps` / `Duplicate`
- Linear comments: `AUR-214` has implementation evidence; `AUR-215` had no comments when fetched on 2026-05-07.

## Milestone Intent

PRD 0006 moves ReviewGraph from fixture-only review targets toward GitHub PR read targets without introducing write behavior. The milestone should prove that PR metadata, changed files, comments, review comments, reviews, and thread state can be read through adapters, represented as explicit state, transformed into structured conversation memory, and fed into the existing dry-run graph safely.

The product point is safe memory. PR discussion is shared context across reviewer agents, but it is labeled data, not an instruction stream. Trusted actionable memory may route reviewers through explicit graph state. Untrusted, resolved, unknown, truncated, or partially-read memory remains passive and cannot create routing pressure, public findings, approval input, local verdict pressure, or provider instructions.

## Current Code Snapshot

- `src/reviewgraph/fixtures.py` parses fixture PRs into `PullRequestContext` and `ReviewTarget`.
- `src/reviewgraph/models.py` already defines `ReviewTarget`, `PullRequestContext`, `PullRequestComment`, `PullRequestReview`, `PullRequestReviewThread`, `PullRequestChangedFile`, `PRConversationMemory`, `MemoryReference`, and `ReadGap`.
- `src/reviewgraph/memory.py` builds conversation memory from parsed PR context. It trusts owner/member/collaborator users plus configured operators, trusts bots only by allowlist, treats unknown actor types as untrusted, and makes resolved or unknown thread state passive.
- `src/reviewgraph/routing.py` already supports `conversation_patterns`, but matching is currently body-text based over all actionable memory and does not include matched memory IDs or trust labels in selection reasons.
- `src/reviewgraph/runner.py` is fixture-oriented. It loads fixture data, builds memory, applies context budgets, runs staged fake reviewers, classifies quality, computes local verdict, builds a dry-run posting plan, and renders markdown/JSON. It is also coupled to fixture changed ranges for diff anchors and to fixture raw reviewer outputs for deterministic fake review.
- `src/reviewgraph/cli.py` accepts `--fixture-pr` only. GitHub PR refs/URLs are not yet accepted as review targets.
- `src/reviewgraph/github.py` now provides fake metadata/files reads, fail-closed read-gap envelopes, and paginated fake full-context reads for files, issue comments, review comments, reviews, and thread state.
- There is no generic runner input yet that can accept a GitHub-read `PullRequestContext` plus fake reviewer output source without going through fixture loading.
- Existing tests cover fixture parsing, memory trust basics, prompt-injection memory boundaries, context budgeting, routing, rendering, and CLI dry-run output. PRD 0006 should add focused GitHub-read harnesses without weakening existing fixture behavior.

## Execution Order

1. `AUR-213` first: introduce a fake GitHub read adapter, PR ref parser, and read-result envelope for metadata and changed files. This establishes the adapter contract, `ReviewTarget` parity with fixtures, read-without-write-credentials posture, initial redaction coverage for adapter errors and PR text, and the bridge shape later needed by the dry-run runner. The adapter should either derive changed ranges from patches or mark changed-line anchoring unavailable explicitly so `AUR-239` does not discover the runner mismatch late.
2. `AUR-247` second: model GitHub read gaps and fail-closed partial reads before success-only pagination assumptions spread. Required read gaps should become durable state with deterministic downstream behavior: graph error, `post_enabled=false`, no candidate payload, and visible dry-run markdown/JSON output. Optional gaps remain visible local context and cannot support postable findings or routing.
3. `AUR-214` third: extend the fake adapter with pagination for files, issue comments, review comments, reviews, and thread state. Pagination must complete before context-budget truncation is applied, and pagination failure must use the `AUR-247` read-gap envelope.
4. `AUR-215` fourth: apply GitHub-derived trust, allowlisted bots, seen-state, and resolved/unknown thread-state behavior to conversation memory. Reuse and harden `memory.py`; do not move trust policy into prompts.
5. `AUR-236` fifth: allow trusted actionable GitHub memory to select reviewers through `conversation_patterns`, with selection reasons that name matching memory IDs and trust status. Untrusted, unlisted bot, resolved, and unknown-state memory must not route reviewers.
6. `AUR-239` sixth: wire GitHub PR refs/URLs into the CLI and graph dry-run path using fake transport by default. The GitHub read result must feed the same target, memory, context budget, reviewer, quality, render, and dry-run path as fixtures; no writer path should be reachable.
7. `AUR-216` seventh: add opt-in live-read smoke coverage. It must be skipped by default, read-only, clear when `gh` or token is missing, and separate from any write or approval behavior.
8. `AUR-259` last: close the milestone only after every active implementation issue is `Done`, focused/full validation passes, durable docs explain the final read/memory contracts, Linear evidence is complete, and fresh subagent review reports no material gaps.

## Issue Workflow

For each issue:

1. Re-fetch the issue, comments, blockers, and current milestone state from Linear.
2. Move the issue to `In Progress`.
3. Replace `ISSUE_PLAN.md` with a narrow plan for that issue and commit it before implementation.
4. Use fresh subagents to review the issue plan before code changes.
5. Implement the smallest contract/harness slice that satisfies the issue and does not implement later milestone scope.
6. Run the issue harness named by Linear plus regression tests covering touched shared behavior.
7. Use fresh subagents for code/docs review until no material findings remain.
8. Commit the completed issue, and commit separately after every review-fix batch.
9. Move the issue to `In Review`, add a Linear evidence comment with commands and artifact coverage, then move it to `Done` only when acceptance criteria are mapped to concrete evidence.

## Harness Strategy

- `AUR-213` focused harness: `python -m pytest tests/test_github_fake_read.py`
- `AUR-247` focused harness: `python -m pytest tests/test_github_read_gaps.py`
- `AUR-214` focused harness: `python -m pytest tests/test_github_pagination.py`
- `AUR-215` focused harness: `python -m pytest tests/test_github_memory_trust.py`
- `AUR-236` focused harness: `python -m pytest tests/test_conversation_routing.py`
- `AUR-239` focused harness: `python -m pytest tests/test_github_dry_run_cli.py`
- `AUR-216` focused harness: `python -m pytest -m live_read` only when explicitly enabled; default tests must prove it is skipped by default.
- Fixture/CLI regression harness:
  - `python -m pytest tests/test_fixtures.py tests/test_memory.py tests/test_routing.py tests/test_reviewer_context.py tests/test_context_budget.py tests/test_tracer_fixture_run.py tests/test_cli.py tests/test_render.py`
- Quality and side-effect boundary regression harness:
  - `python -m pytest tests/test_findings.py tests/test_quality.py tests/test_quality_testing.py tests/test_verdict.py tests/test_posting.py tests/test_prompt_injection_memory.py tests/test_redaction.py`
- Full validation after shared adapter or CLI changes:
  - `python -m pytest -q`
  - `python -m py_compile src/reviewgraph/*.py`
  - `python scripts/check_docs.py`
  - `git diff --check`

## Contract Guardrails

- Dry-run remains the default. PRD 0006 must not introduce GitHub writes, approval prompts, live LLM calls, inline comments, statuses, labels, or formal PR reviews.
- Fake GitHub transport is the default implementation harness. Live read is opt-in and read-only.
- GitHub read adapters may use REST API or `gh`, but the adapter contract must report whether thread resolution state is available.
- Required read context includes owner/repo, PR number, title/body/author, base/head SHAs, merge base, labels, changed files, patches, comments, reviews, review comments, and thread state where available.
- Adapter output must include an explicit read-result envelope with `PullRequestContext`, `ReviewTarget`, available changed-line metadata or anchor-unavailable metadata, read gaps, thread-state availability, optional actor/permission snapshot, and redaction status for external PR text.
- Adapters must paginate files, issue comments, review comments, reviews, and thread state. Partial pagination failure is a read gap, not context-budget truncation.
- Required resources for PRD 0006 are PR metadata, target SHAs, changed-file list, file patch availability metadata, issue comments, reviews, review comments, and thread-state availability. If a required resource cannot be read or pagination is incomplete, the graph must fail closed for post eligibility. Missing patch text for an individual file may be optional only when represented with `patch_status` and not used for anchoring or finding evidence.
- Conversation memory stores author, author association, timestamp, body, URL, path/line when available, source type, resolved status, trust label, actionable status, and passive reason.
- Trusted human authors are owner/member/collaborator plus configured authenticated operators.
- Trusted review bots are default-deny allowlisted. Unlisted bots are passive.
- Untrusted comments, missing/unknown actor types, resolved threads, and unknown thread state cannot trigger `conversation_patterns`.
- Unknown thread state is distinct from resolved/unresolved. It remains visible as passive memory but cannot support actionable routing or postable findings by default.
- Seen-state in PRD 0006 means preserving source comment, review, review-comment, and thread IDs in memory and rendered JSON so later slices can avoid reprocessing. It does not imply durable storage or semantic deduplication in this milestone.
- If truncation occurs after complete pagination, ReviewGraph emits local notes and avoids findings dependent on omitted context.
- If required read gaps occur before complete context is available, downstream review must fail closed: record `ReadGap` and `GraphError`, set `post_enabled=false`, produce no candidate payload, and render the gap explicitly. Optional read gaps are rendered as local context and cannot support routing, finding evidence, or public payload text.
- Selection reasons for conversation-pattern routing must be inspectable and include matching memory IDs and trust status.
- GitHub-read PR titles, bodies, labels, patches, comments, reviews, review comments, thread bodies, adapter errors, `gh` failures, markdown, JSON, traces, and local notes must pass through existing redaction before display or persistence.
- Actor/permission discovery in PRD 0006 is read-only and advisory. The adapter may return an actor/permission snapshot for later approval work, and unknown or insufficient permission must block any approval/posting path if post mode is attempted. Implementing approval prompts, finalization, or writer behavior remains PRD 0007.
- Reviewer prompts remain decoupled from GitHub transports and write code. Reviewer agents receive scoped context packages, not adapter clients.

## Documentation Work

Update the narrowest durable docs alongside behavior:

- Read adapter contract, PR ref parsing, thread-state availability, read-result envelope, actor/permission snapshot scope, redaction requirements, and live-read posture belong in `docs/architecture/github-integration.md`.
- Memory trust, resolved/unknown thread-state actionability, and conversation-pattern routing rules belong in `docs/architecture/state-graph.md` and `docs/architecture/reviewer-config.md` when config semantics change.
- Read-gap state and fail-closed behavior belong in `docs/architecture/state-graph.md` and, if a durable tradeoff is introduced, `docs/decisions/`.
- Harness expectations for fake read, pagination, read gaps, and opt-in live smoke belong in `docs/harnesses/harness-engineering.md`.
- Implementation sequencing belongs in `docs/plans/implementation-plan.md` only if the project phase narrative changes materially.
- Keep Linear as the executable backlog. Do not copy the full issue tree into durable product docs beyond this active execution plan.

## PRD 0006 Acceptance Surface

The milestone is complete when ReviewGraph proves:

- GitHub PR URL and `owner/repo#number` refs parse into a stable read target.
- Fake GitHub read adapter returns PR metadata, labels, base/head SHAs, merge base, changed files, patches, read-result envelope metadata, and redaction status without write credentials.
- Fake read output produces the same `ReviewTarget` and `PullRequestContext` shape used by fixtures.
- Fake read output includes changed-line metadata derived from patches, or explicit anchor-unavailable metadata that keeps GitHub-read dry-runs local/degraded rather than pretending inline anchors are valid.
- Adapter pagination covers files, issue comments, review comments, reviews, and thread state before truncation.
- Read failures, partial pagination, unknown required thread state, and unavailable thread-state data become explicit read-gap state. Required gaps create graph errors, set `post_enabled=false`, suppress candidate payloads, and render in markdown/JSON.
- GitHub-read external text and adapter errors are redacted before markdown, JSON, traces, local notes, or error output.
- Actor/permission data is read-only/advisory in this milestone; missing, unknown, or insufficient permission blocks any attempted approval/posting path, while approval/finalization/writer implementation remains deferred.
- GitHub conversation memory applies trusted-human, trusted-bot allowlist, untrusted-passive, source-ID seen-state preservation, resolved-thread, and unknown-thread rules.
- Trusted actionable memory can route reviewers through `conversation_patterns`; untrusted, unlisted bot, resolved, and unknown-state memory cannot.
- Selection reasons expose matching memory IDs and trust status.
- GitHub PR dry-run CLI path feeds the same graph and render contracts as fixture dry-run, using a generic run-input bridge rather than forcing all GitHub data through fixture file loading.
- Default tests need no GitHub credentials and cannot reach writer code.
- Live read smoke is opt-in, skipped by default, read-only, and clear about missing `gh` or token.

## Deferred Scope

- GitHub write behavior remains PRD 0007.
- Live LLM behavior remains PRD 0008.
- Long-running PR monitoring and webhooks remain out of scope.
- Inline comments, formal PR reviews, labels, status checks, approvals, and request changes remain deferred.

## Milestone Completion Criteria

`AUR-259` can close only when:

- Every active implementation issue listed in this plan is `Done` in Linear with an evidence comment.
- `AUR-252` remains documented as the canceled duplicate of `AUR-247`.
- A fresh Linear milestone inventory proves every active PRD 0006 blocker is complete or has an explicit stale/canceled/not-applicable rationale in Linear.
- Focused validation for all PRD 0006 harness families passes.
- Fixture/CLI, quality/boundary, full validation, docs check, py-compile, and diff check pass.
- Durable docs explain the final GitHub read, memory trust, read-gap, and live-read contracts an implementation agent needs when dropping into the repo.
- Fresh subagent review of code, tests, docs, Linear evidence, and the milestone gate reports no material issues.
- No GitHub writer, approval, inline-posting, live LLM, or unapproved live API behavior has been introduced.
- No `.ws/` or temporary export artifacts remain.
