# ISSUE PLAN: AUR-239 Add GitHub PR Dry-Run Adapter Path

Active issue plan for `AUR-239` / `RG-050: Add GitHub PR Dry-Run Adapter Path`.

Linear remains the durable source of current issue status and relationships. This file is the committed execution plan for the issue.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0006: GitHub Read And Memory`
- Issue: `AUR-239`
- Title: `RG-050: Add GitHub PR Dry-Run Adapter Path`
- Status when planned: `In Progress`
- Priority: `Medium`
- Linear comments fetched on 2026-05-07: none

## Acceptance Mapping

1. CLI accepts `owner/repo#number` or PR URL as a review target.
   - Add a GitHub-target CLI option separate from `--fixture-pr`.
   - Accept both short refs and GitHub PR URLs through existing `parse_github_pr_ref()`.
   - Keep `--fixture-pr` as the default path for existing behavior.
2. Fake GitHub transport can satisfy the path without credentials.
   - Add an explicit fake-data JSON input for the GitHub CLI path.
   - The fake-data JSON models paginated fake transport pages, not a fixture PR file.
   - No `GITHUB_TOKEN`, `gh`, network client, writer, approval, or live LLM behavior is required or reachable.
3. Live read mode is opt-in and read-only.
   - Default GitHub target mode uses fake data only.
   - Add an explicit live-read flag or mode surface that fails closed with a clear "deferred to live-read smoke" error until AUR-216 implements it.
   - This proves live behavior cannot happen accidentally in AUR-239.
4. GitHub read output feeds the same `ReviewTarget`, memory, context budget, reviewer, quality, render, and dry-run path as fixtures.
   - Refactor the fixture runner just enough to accept already-read PR context, review target, changed-line metadata, truncation/read-gap metadata, and fake reviewer outputs.
   - Reuse existing memory builder, context budget, staged reviewer selection/execution, quality classification, local verdict, posting plan, candidate payload, and renderer.
   - Do not force GitHub data through fixture PR file loading.
5. No writer path is reachable from read-only GitHub dry-run.
   - Use writer sentinel tests to prove GitHub dry-run does not call writer code.
   - Keep GitHub dry-run output `run_mode="dry_run"`.

## Design

AUR-239 should not implement a real GitHub client. It should connect the already-proven fake read adapter to the existing dry-run graph path.

Planned contract:

- CLI options:
  - `--github-pr <owner/repo#number|https://github.com/.../pull/N>` selects the GitHub dry-run path.
  - `--github-fake-data <path>` supplies deterministic paginated fake transport data.
  - `--github-live-read` is explicit opt-in and currently fails closed with a clear deferred-live-read message.
- `--fixture-pr` and `--github-pr` are mutually exclusive. Existing default remains `--fixture-pr basic-pr`.
- Fake-data JSON contains:

  ```json
  {
    "pull_request": {},
    "files": {"pages": [...]},
    "issue_comments": {"pages": [...]},
    "review_comments": {"pages": [...]},
    "reviews": {"pages": [...]},
    "review_threads": {"pages": [...]},
    "raw_reviewer_outputs": [...]
  }
  ```

- The test transport built from fake-data JSON must expose only read methods required by `read_github_pr_with_paginated_fake_transport()`.
- If the paginated fake read returns a `FailClosedReadOutcome`, the CLI should render/emit that fail-closed JSON/markdown surface where available or return a redacted error without running reviewers. AUR-247 already covers the fail-closed read envelope; AUR-239 focused happy path can use complete fake pages.
- Add a runner entrypoint, likely `run_github_fake_dry_run()`, that:
  - reads fake transport data,
  - calls `read_github_pr_with_paginated_fake_transport()`,
  - builds conversation memory using reviewer config trust allowlists,
  - applies context budget,
  - runs the existing staged fake reviewer loop with `GitHubReadResult.pr`, `GitHubReadResult.review_target`, and `GitHubReadResult.changed_file_lines`,
  - renders through the existing dry-run renderer,
  - returns the same `DryRunResult` shape as fixture dry-run with extra GitHub read metadata in JSON.
- Raw reviewer outputs remain deterministic fake outputs supplied by fake-data JSON. This issue does not introduce live LLM.

## Files

Likely implementation files:

- `src/reviewgraph/cli.py`
- `src/reviewgraph/github.py`
- `src/reviewgraph/runner.py`
- `src/reviewgraph/fixtures.py` only if shared validation helpers are needed
- `docs/architecture/github-integration.md`
- `docs/harnesses/harness-engineering.md`

Likely tests:

- `tests/test_github_dry_run_cli.py`
- `tests/test_cli.py`
- `tests/test_github_pagination.py`
- `tests/test_tracer_fixture_run.py`

## Implementation Steps

1. Add focused failing tests in `tests/test_github_dry_run_cli.py`:
   - CLI accepts short GitHub PR ref with fake data and writes/prints dry-run output.
   - CLI accepts GitHub PR URL with fake data.
   - GitHub fake dry-run output includes GitHub `ReviewTarget`, selected reviewers, memory, context budget, reviewer output, render JSON, and no writer calls.
   - Missing fake data for `--github-pr` fails closed without credentials.
   - `--github-live-read` is explicit and currently fails closed/deferred.
   - `--fixture-pr` and `--github-pr` are mutually exclusive.
2. Refactor runner internals to make the dry-run core accept a generic read input without duplicating fixture behavior.
3. Add fake-data JSON transport loader for paginated GitHub fake reads.
4. Add CLI GitHub options and route into the new runner entrypoint.
5. Add read-only boundary tests proving the GitHub dry-run path does not import/call writer behavior and does not need credentials.
6. Update docs for CLI GitHub dry-run fake-data behavior and AUR-216 live-read deferral.

## Validation Plan

Focused harness:

```bash
python -m pytest tests/test_github_dry_run_cli.py -q
```

Regression harness:

```bash
python -m pytest tests/test_cli.py tests/test_github_pagination.py tests/test_tracer_fixture_run.py tests/test_conversation_routing.py -q
```

Full validation before completion:

```bash
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Out Of Scope

- Real GitHub live read implementation. AUR-216 owns live-read smoke.
- GitHub write mode, approval, finalization, writer adapters, inline comments, labels, statuses, formal reviews, or request changes.
- Live LLM reviewer execution.
- Long-running PR monitoring or webhooks.
