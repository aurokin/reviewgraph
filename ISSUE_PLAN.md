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
   - Add a read-only `gh` transport that shells out only to `gh api` for PR metadata and paginated read resources.
   - Reuse `read_github_pr_with_paginated_fake_transport()` by conforming the live transport to the same paginated page contract.
   - The live smoke test should target a configurable public PR, defaulting to a stable public PR ref when the harness is explicitly enabled.
3. Output includes target metadata and pagination/truncation notes.
   - Live smoke should serialize the redacted `GitHubReadResult` or fail-closed read-gap result to an artifact when an output path is provided.
   - The success artifact must include `review_target`, `resource_coverage`, `thread_state`, `read_gaps`, `anchor_unavailable`, and `redaction_status`.
   - The blocked/skipped artifact must include a stable reason such as missing `gh`, missing token, missing opt-in, or live read failure.
4. Missing `gh` or token produces a clear skipped/blocked result.
   - Add a small live-read smoke harness helper that checks `REVIEWGRAPH_LIVE_READ=1`, `gh` availability, and token availability before attempting `gh api`.
   - Missing prerequisites should call `pytest.skip()` in tests and return a structured blocked result in reusable helper code.
   - Do not treat missing credentials as a failing default test.
5. No writer code is available from live read.
   - Keep live read in `github.py` and/or a read-only target helper; do not import writer, approval, finalization, payload builders, or posting modules into the live transport.
   - Add an import-boundary test proving the live-read smoke module and GitHub read adapter do not import writer-side modules.

## Design

AUR-216 should add only a live read smoke path, not a production live review command. The product value is proving that the GitHub read adapter contract can be exercised against a real public PR without write behavior and without making default tests depend on network, `gh`, tokens, or repo state.

Planned contract:

- Default test collection skips `@pytest.mark.live_read` unless `REVIEWGRAPH_LIVE_READ=1` is set.
- Live smoke prerequisites:
  - `REVIEWGRAPH_LIVE_READ=1`
  - `gh` on `PATH`
  - `gh auth token` succeeds or `GITHUB_TOKEN`/`GH_TOKEN` is present
  - optional `REVIEWGRAPH_LIVE_READ_PR` set to `owner/repo#number` or GitHub PR URL
- The default PR target should be a public GitHub PR that is safe to read. The harness must allow override so it is not coupled to one upstream PR forever.
- The live transport should expose:
  - `get_pull_request(owner_repo, pr_number)`
  - `get_changed_files_page(owner_repo, pr_number, cursor)`
  - `get_issue_comments_page(owner_repo, pr_number, cursor)`
  - `get_review_comments_page(owner_repo, pr_number, cursor)`
  - `get_reviews_page(owner_repo, pr_number, cursor)`
  - `get_review_threads_page(owner_repo, pr_number, cursor)`
- The transport should shell out to `gh api` with `GET`-equivalent behavior only. It must not call `gh pr review`, `gh pr comment`, `gh issue comment`, `gh api --method POST`, or any mutation endpoint.
- REST payload mapping should be deliberately small:
  - PR metadata maps to the existing GitHub payload schema expected by `_review_target_from_payload()`.
  - Changed files map `filename` to `path`, preserve `patch`, `status`, `additions`, `deletions`, and `previous_filename`.
  - Issue comments and reviews map GitHub fields into the existing fake payload shape.
  - Review comments include `pull_request_review_id` or similar thread ID data when available.
  - Thread state may be fetched through GraphQL if practical; if not, the live smoke should produce a fail-closed `thread_state_unknown` or unavailable read-gap rather than pretending thread state is complete.
- A live read returning `FailClosedReadOutcome` is acceptable when GitHub thread-state cannot be resolved. The test should assert the fail-closed artifact shape, not force overconfident success.
- No CLI write behavior changes in this issue. AUR-239 intentionally deferred `--github-live-read`; this issue may either leave CLI live review deferred or make `--github-live-read` emit a read-only smoke artifact only. If CLI surface is touched, it must remain impossible to run reviewers or writers from a live read without fake reviewer outputs.

## Files

Likely implementation files:

- `src/reviewgraph/github.py`
- `tests/test_live_read_smoke.py`
- `tests/conftest.py`
- `pyproject.toml`
- `docs/architecture/github-integration.md`
- `docs/harnesses/harness-engineering.md`

Likely untouched or boundary-only files:

- `src/reviewgraph/cli.py`
- `src/reviewgraph/targets.py`
- writer/approval/finalization modules

## Implementation Steps

1. Add skipped-by-default live-read smoke tests first:
   - marker registration;
   - default skip behavior;
   - missing `gh` blocked/skipped helper behavior;
   - missing token blocked/skipped helper behavior;
   - import-boundary proof.
2. Add a small `gh` command runner abstraction or injectable function so tests can fake `gh` responses without invoking network.
3. Implement the read-only `gh` transport using the same paginated page shape consumed by `read_github_pr_with_paginated_fake_transport()`.
4. Add payload mapping tests for PR metadata, files, issue comments, reviews, and review comments from representative `gh api` JSON.
5. Add the opt-in live test that runs only when prerequisites are satisfied and writes/validates a redacted artifact.
6. Update docs for live-read opt-in, prerequisites, expected blocked/skipped states, and read-only boundaries.

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
