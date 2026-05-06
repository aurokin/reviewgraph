# ISSUE PLAN: AUR-247 Fail Closed On GitHub Read Gaps

Active issue plan for `AUR-247` / `RG-058: Fail Closed On GitHub Read Gaps`.

Linear remains the source of truth for issue state and relationships.

## Linear Snapshot

- Issue: `AUR-247`
- Status at plan time: `In Progress`
- Milestone: `PRD 0006: GitHub Read And Memory`
- Title: `RG-058: Fail Closed On GitHub Read Gaps`
- Harness from Linear: `python -m pytest tests/test_github_read_gaps.py`
- Linear comments at start: none.
- Out of scope from Linear: downstream quality/posting enforcement.

## Intent

Make incomplete GitHub read context impossible to mistake for graph-complete review input. GitHub read failures, partial pagination failures, unavailable required resources, and unknown required thread state should become explicit `ReadGap` and `GraphError` state before memory, routing, reviewers, quality, or posting can rely on partial context.

This issue should not implement real pagination or the end-to-end GitHub dry-run CLI path. It should create the policy and harness surface that later pagination and dry-run integration must call.

## Current Baseline

- `src/reviewgraph/github.py` now returns `GitHubReadResult` for fake metadata/files reads.
- Metadata/files-only reads already include required gaps for `comments`, `reviews`, `review_comments`, and `thread_state`.
- `ReadGap` currently stores `resource`, `required`, `reason`, and `retryable`, but there is no shared classifier for GitHub read failure reasons.
- `GraphError` already disables `post_enabled` through `compute_post_enabled()`.
- Existing fixture runner fail-closed paths preserve dry-run output by emitting errors, `post_enabled=false`, local-only posting plans, and no candidate payload.
- `render_review()` currently renders truncation, memory, posting plan, and candidate payload, but not read gaps directly.
- `AUR-214` will implement real pagination; `AUR-239` will wire GitHub PR refs into CLI/runner.

## Decisions

1. Add a small `src/reviewgraph/read_gaps.py` policy module rather than burying read-gap decisions inside GitHub adapter code, runner code, or prompts.
2. Keep `ReadGap` as the durable model for now. Do not expand `models.py` unless the policy cannot be expressed with existing fields.
3. Classify GitHub resource failures with deterministic reason codes:
   - `forbidden` / terminal 403;
   - `not_found` / terminal 404;
   - `rate_limited` / retryable;
   - `timeout` / retryable;
   - `unavailable` / terminal;
   - `pagination_incomplete` / retryable or terminal depending on source error;
   - `thread_state_unknown` / terminal until a later policy proves it safe;
   - `not_fetched_in_scope` / retryable for metadata/files-only placeholders.
4. Preserve underlying failure class for pagination failures. `ReadGap.reason` should remain the specific reason (`forbidden`, `timeout`, `rate_limited`, etc.); page/resource context should be carried in stable local metadata produced by `read_gaps.py`, not collapsed into a generic `pagination_incomplete` string.
5. Required gaps create one deterministic `GraphError` per required resource with code `github_read_gap`, a stable message naming resource and reason, and retryability copied from the gap. Optional gaps remain visible but must not create graph errors by themselves.
6. Add a concrete fail-closed read outcome API that later GitHub graph/CLI slices can call. It must produce:
   - parsed PR ref when available;
   - optional `ReviewTarget` when target metadata was read;
   - `read_gaps`;
   - `errors`;
   - `post_enabled=false`;
   - empty selected reviewers, reviewer statuses/results, findings, posting plan, and candidate payload;
   - a deterministic trace event such as `github_read_gap_fail_closed`.
7. Fetch failures before PR metadata are targetless read failures. Do not force a fake or nullable `ReviewTarget` into `render_review()`. Add a separate targetless read-failure rendering/envelope helper using parsed `GitHubPRRef` plus read gaps/errors. Normal `render_review()` can still gain generic read-gap/error sections for cases where a `ReviewTarget` exists.
8. Distinguish read gaps from context truncation. Pagination/read failures happen before context budgeting and are represented as `ReadGap`; configured budget truncation still uses `TruncationNotice`.
9. Satisfy the Linear pagination-fixture criterion with deterministic page-gap descriptors, not real pagination loops. The harness should define omitted later-page file/comment/review fixtures that would have affected routing, trust, or redaction and assert the missing later page creates a fail-closed read gap before that content can be used.
10. Optional gaps must carry enough marker metadata for later stages to know the resource cannot support routing, finding evidence, or public payload text. AUR-247 will not enforce those later stages, but it will lock the marker contract and render it.
11. Do not wire CLI `--github-pr`, live `gh`, real pagination loops, reviewer execution, quality classification, approval, finalization, posting, or writer behavior in this issue. Add boundary/negative tests where practical so the slice stays policy/render only.

## Implementation Plan

1. Add `tests/test_github_read_gaps.py` first.
   - Required GitHub metadata/files-only gaps from `GitHubReadResult` become graph errors and suppress review/posting.
   - Optional gaps are rendered but do not create graph errors.
   - Fetch failure before target metadata renders through a targetless read-failure envelope with parsed PR ref, no `PullRequestContext`, no `ReviewTarget`, no reviewers, no findings, no posting plan, no candidate payload, `post_enabled=false`, redacted error text, and graph trace `github_read_gap_fail_closed`.
   - Required failure classifications cover 403, 404, rate limit, timeout, unavailable, pagination incomplete, and unknown thread state, with expected retryable values.
   - Later-page descriptor fixtures include page-2 file/comment/review data that would affect routing, trust, and redaction if used; the test proves missing that page creates a read gap instead of first-page-only success.
   - Partial pagination failure is distinct from configured context truncation: read-gap JSON is populated while truncation stays empty unless a separate budget notice is supplied.
   - Dry-run markdown and JSON include read gaps, optional-gap usage restrictions, graph errors, and fail-closed trace reasons.
   - Read-gap text and adapter errors pass through redaction before render output.

2. Implement `src/reviewgraph/read_gaps.py`.
   - Define resource/failure constants or `StrEnum` values if useful.
   - Add helpers to build `ReadGap` values for GitHub resources.
   - Add a classifier from fake GitHub failure metadata/status to `ReadGap` plus stable page/resource metadata when the failure occurs during pagination.
   - Add `graph_errors_from_read_gaps(read_gaps)` for required gaps.
   - Add `build_fail_closed_read_outcome(...)` or equivalent as the public callable boundary for later AUR-214/AUR-239 integration.
   - Add a targetless read-failure render/envelope helper for pre-metadata failures.

3. Extend render support narrowly.
   - Add `read_gaps` and `errors` inputs to `render_review()` with defaults.
   - Render read gaps in JSON and markdown separately from truncation.
   - Render graph errors in JSON and markdown so GitHub read failure is visible even when no reviewers run.
   - Preserve existing render defaults and fixture dry-run outputs.

4. Integrate with the fake GitHub read envelope only where needed.
   - Reuse `GitHubReadResult.read_gaps`.
   - Keep `src/reviewgraph/github.py` read-only and free of runner/approval/writer imports.
   - If helper functions need a GitHub-specific wrapper, keep dependencies one-way: GitHub/read-gap policy can depend on models and redaction, but not on CLI, runner, posting, approval, finalization, or writer modules.

5. Update durable docs.
   - `docs/architecture/state-graph.md`: required read gaps create graph errors, stop reviewer execution for GitHub read targets once AUR-239 wires the graph path, set `post_enabled=false`, suppress candidate payloads, emit `github_read_gap_fail_closed`, and remain distinct from truncation.
   - `docs/architecture/github-integration.md`: failure classification and unknown thread-state behavior.
   - `docs/harnesses/harness-engineering.md`: AUR-247 focused harness and read-gap render expectations.

## Verification

- Focused:
  - `python -m pytest tests/test_github_read_gaps.py -q`
- Related regression:
  - `python -m pytest tests/test_github_fake_read.py tests/test_render.py tests/test_verdict.py tests/test_contract_boundaries.py -q`
- Wider PRD 0006/runner regression:
  - `python -m pytest tests/test_fixtures.py tests/test_memory.py tests/test_routing.py tests/test_cli.py tests/test_redaction.py tests/test_reviewer_context.py tests/test_context_budget.py tests/test_diff_anchor.py -q`
- Hygiene:
  - `python -m pytest -q`
  - `python -m py_compile src/reviewgraph/*.py`
  - `python scripts/check_docs.py`
  - `git diff --check`

## Out Of Scope

- Real GitHub pagination.
- Live GitHub reads.
- CLI GitHub PR target support.
- Building conversation memory from GitHub comments/reviews.
- Running reviewers from GitHub read results.
- Downstream quality/posting implementation beyond making required read gaps produce graph errors, `post_enabled=false`, no candidate payload, and renderable dry-run evidence.
- Approval, finalization, writer behavior, inline comments, labels, statuses, and formal PR reviews.
