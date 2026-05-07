# ISSUE PLAN: AUR-216 Add Opt-In Live Read Smoke

Active issue plan for `AUR-216` / `RG-027: Add Opt-In Live Read Smoke`.

Linear remains the durable source of current issue status and relationships. This file is the committed execution plan for the issue.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0006: GitHub Read And Memory`
- Issue: `AUR-216`
- Title: `RG-027: Add Opt-In Live Read Smoke`
- Status when planned: `In Progress`
- Priority: `Medium`
- Linear comments fetched on 2026-05-07: none

## Acceptance Mapping

1. Live read tests are skipped by default.
   - Register a `live_read` pytest marker in `pyproject.toml`.
   - Add a `tests/conftest.py` collection hook that skips `live_read` tests unless an explicit environment opt-in is present.
   - Prove default `python -m pytest` reports the live smoke as skipped and does not need credentials.
2. Live read can fetch a public PR in read-only mode.
   - Add a separate read-only live smoke module, likely `src/reviewgraph/github_live.py`, so `src/reviewgraph/github.py` remains a live-free/fake-read contract module.
   - Add a read-only `gh` transport that shells out only to audited read commands for PR metadata and paginated read resources.
   - Reuse `read_github_pr_with_paginated_fake_transport()` by conforming the live transport to the same paginated page contract.
   - The live smoke test should require `REVIEWGRAPH_LIVE_READ_PR`; do not depend on a default third-party public PR.
3. Output includes target metadata and pagination/truncation notes.
   - Live smoke should always build a stable artifact object, and should write it when `REVIEWGRAPH_LIVE_READ_OUT` is provided.
   - The artifact schema must include `status`, `reason`, `pr_ref`, `github_read` or `fail_closed`, `read_gaps`, `page_gap_descriptors`, `truncation_notes`, `command_summary`, and `redaction_status`.
   - The blocked/skipped artifact must include a stable reason such as missing opt-in, missing PR target, missing `gh`, missing token, or live read failure.
4. Missing `gh` or token produces a clear skipped/blocked result.
   - Add a small live-read smoke harness helper that checks `REVIEWGRAPH_LIVE_READ=1`, `REVIEWGRAPH_LIVE_READ_PR`, `gh` availability, and token availability before attempting `gh api`.
   - Missing prerequisites should call `pytest.skip()` in tests and return a structured blocked result in reusable helper code.
   - Do not treat missing credentials as a failing default test.
5. No writer code is available from live read.
   - Keep shelling live read code outside `github.py`, `cli.py`, `targets.py`, and `runner.py`; do not import writer, approval, finalization, payload builders, posting, reviewer execution, or dry-run graph modules into the live transport.
   - Add an import-boundary test proving the live-read smoke module and GitHub read adapter do not import writer-side modules.

## Design

AUR-216 should add only a live read smoke path, not a production live review command. The product value is proving that the GitHub read adapter contract can be exercised against a real public PR without write behavior and without making default tests depend on network, `gh`, tokens, or repo state.

Planned contract:

- Default test collection skips `@pytest.mark.live_read` unless `REVIEWGRAPH_LIVE_READ=1` is set.
- Live smoke prerequisites:
  - `REVIEWGRAPH_LIVE_READ=1`
  - `REVIEWGRAPH_LIVE_READ_PR` set to `owner/repo#number` or GitHub PR URL
  - `gh` on `PATH`
  - `gh auth token` succeeds or `GITHUB_TOKEN`/`GH_TOKEN` is present
- `REVIEWGRAPH_LIVE_READ_OUT` is optional. When present, the live smoke writes the stable artifact JSON there.
- The live module should set `GH_PROMPT_DISABLED=1`, use bounded timeouts, pass command arguments as lists with no shell interpolation, redact stderr/errors, and never store token stdout.
- The live smoke must not define a default public PR. Missing `REVIEWGRAPH_LIVE_READ_PR` is a clear blocked/skipped result.
- The stable smoke artifact schema is:
  - `status`: `blocked`, `skipped`, `succeeded`, or `fail_closed`
  - `reason`: stable machine reason such as `missing_opt_in`, `missing_pr_ref`, `missing_gh`, `missing_token`, `live_read_failed`, or `read_gap`
  - `pr_ref`: parsed ref when available
  - `github_read`: redacted `GitHubReadResult.to_dict()` on success
  - `fail_closed`: redacted `FailClosedReadOutcome.to_dict()` when required read context is unavailable
  - `read_gaps`, `page_gap_descriptors`, `truncation_notes`, `command_summary`, and `redaction_status`
- The live transport should expose:
  - `get_pull_request(owner_repo, pr_number)`
  - `get_changed_files_page(owner_repo, pr_number, cursor)`
  - `get_issue_comments_page(owner_repo, pr_number, cursor)`
  - `get_review_comments_page(owner_repo, pr_number, cursor)`
  - `get_reviews_page(owner_repo, pr_number, cursor)`
  - `get_review_threads_page(owner_repo, pr_number, cursor)`
- The live transport should live in `src/reviewgraph/github_live.py`. It may import pure mapping/read functions from `github.py`, but `github.py` must not import `github_live.py`.
- The transport should shell out to `gh api` REST read endpoints only in AUR-216. It must not call `gh pr review`, `gh pr comment`, `gh issue comment`, `gh api --method POST`, `gh api graphql`, or any mutation endpoint.
- REST payload mapping should be deliberately small:
  - PR metadata maps to the existing GitHub payload schema expected by `_review_target_from_payload()`.
  - Changed files map `filename` to `path`, preserve `patch`, `status`, `additions`, `deletions`, and `previous_filename`.
  - Issue comments and reviews map GitHub fields into the existing fake payload shape.
  - Review comments cannot become complete/actionable thread memory unless fetched thread-state IDs are available.
  - AUR-216 is REST-only for the first live smoke. Because REST does not expose reliable review thread resolution state in the existing contract shape, live smoke should normally return a fail-closed `thread_state_unknown` result when review comments require thread state. A later GraphQL read policy can make thread state complete.
- A live read returning `FailClosedReadOutcome` is acceptable when GitHub thread-state cannot be resolved. The test should assert the fail-closed artifact shape, not force overconfident success.
- No CLI write behavior changes in this issue. Keep existing `--github-live-read` deferred behavior in `cli.py`; AUR-216 is a helper/test smoke path, not a production live review command.
- Pagination should use explicit per-resource page limits and timeout behavior. If limits are hit, return `pagination_incomplete` or `timeout` read-gap diagnostics rather than overclaiming full context.

## Files

Likely implementation files:

- `src/reviewgraph/github_live.py`
- `tests/test_live_read_smoke.py`
- `tests/conftest.py`
- `pyproject.toml`
- `docs/architecture/github-integration.md`
- `docs/harnesses/harness-engineering.md`

Likely untouched or boundary-only files:

- `src/reviewgraph/cli.py`
- `src/reviewgraph/github.py`
- `src/reviewgraph/targets.py`
- writer/approval/finalization modules

## Implementation Steps

1. Add skipped-by-default live-read smoke tests first:
   - marker registration;
   - default skip behavior;
   - structured blocked artifact behavior without invoking pytest skip;
   - missing `gh` blocked/skipped helper behavior;
   - missing token blocked/skipped helper behavior;
   - missing PR target blocked/skipped helper behavior;
   - import-boundary proof.
2. Add a small `gh` command runner abstraction or injectable function so tests can fake `gh` responses without invoking network.
3. Implement the read-only `gh` transport using the same paginated page shape consumed by `read_github_pr_with_paginated_fake_transport()`.
4. Add payload mapping tests for PR metadata, files, issue comments, reviews, and review comments from representative `gh api` JSON.
5. Add command construction tests proving there is no `gh pr review`, `gh pr comment`, `gh issue comment`, `--method POST`, `gh api graphql`, `mutation`, or shell interpolation.
6. Add the opt-in live test that runs only when prerequisites are satisfied and writes/validates a redacted artifact.
7. Leave CLI `--github-live-read` deferred; do not route live read into reviewers, runner, or writer paths.
8. Update docs for live-read opt-in, prerequisites, expected blocked/skipped states, REST-only thread-state fail-closed behavior, and read-only boundaries.

## Validation Plan

Focused default harness:

```bash
python -m pytest tests/test_live_read_smoke.py -q
```

Explicit live-read harness, only when prerequisites are intentionally supplied:

```bash
REVIEWGRAPH_LIVE_READ=1 python -m pytest -m live_read tests/test_live_read_smoke.py -q
```

Regression harness:

```bash
python -m pytest tests/test_github_fake_read.py tests/test_github_pagination.py tests/test_github_dry_run_cli.py tests/test_contract_boundaries.py -q
```

Full validation before completion:

```bash
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Out Of Scope

- GitHub write mode.
- Approval prompts, finalization, payload hash approval, marker reconciliation, or writer adapters.
- Live reviewer execution or live LLM calls.
- Making default tests depend on network, tokens, `gh`, or a stable third-party PR.
- Formal PR reviews, inline comments, labels, statuses, approvals, or request changes.
