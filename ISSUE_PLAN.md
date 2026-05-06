# ISSUE PLAN: AUR-225 Block Posting On Required Reviewer Failure

Active issue plan for `AUR-225` / `RG-036: Block Posting On Required Reviewer Failure`.

## Linear Snapshot

- Issue: `AUR-225`
- Status at plan time: `In Progress`
- Milestone: `PRD 0004: Graph Orchestration`
- Comments at plan time: none
- Linear description: make required reviewer failure record a fail-closed review state while preserving local dry-run output.

## Goal

Convert required reviewer failures from process-aborting exceptions into graph-owned failure state. The default dry-run should still render useful local output, expose the failed reviewer and error, force `post_enabled=false`, and make the generated posting plan local-only. Optional reviewer failures should keep the current non-terminal local-note behavior.

This issue should not implement the later live writer, approval gate, or posting-plan finalization policy. It should create the state/output contract those later slices must respect.

## Acceptance Mapping

- Required reviewer failure records an error:
  - Record a `GraphError` for required reviewer execution or classification failure, and preserve the failed `ReviewerResult` plus failed `ReviewerRunStatus`.
- Required reviewer failure sets `post_enabled=false`:
  - Thread a required-failure flag/error collection from reviewer execution into final dry-run synthesis and force posting eligibility off even if other postable findings exist.
- Dry-run output includes the failure:
  - Add JSON output assertions for `errors`, failed `reviewer_results`, failed `reviewer_run_status`, and local-only posting destinations. Add markdown coverage only if the current renderer has an appropriate section; otherwise keep the failure visible in machine output without inventing renderer copy.
- Later posting-plan construction must treat required reviewer failure as non-writable state:
  - Build the posting plan normally for classified output, then convert it to local-only when required failures exist. Candidate GitHub payload must be absent/disabled through the existing `post_enabled=false` path.
- Optional reviewers remain unaffected:
  - Keep optional reviewer failures as local notes, not graph errors, and preserve post eligibility when an optional failure is the only failure and postable findings remain.

## Implementation Plan

1. Add `tests/test_required_reviewer_failure.py` with a fixture mutation helper that can force required/optional fake reviewer failures and mixed success/failure runs.
2. Extend the stage-run result with graph errors or a required-failure marker so `run_fixture_dry_run` can decide posting eligibility after all local output is collected.
3. Replace required reviewer failure raises in `_run_review_stages` with fail-closed state recording where the fixture and selection are otherwise valid. Keep malformed fixture/config errors as exceptions.
4. Ensure required failures mark reviewer status `failed`, append the failed `ReviewerResult`, record a `GraphError`, and continue enough to produce dry-run JSON/markdown. Stop consuming later stages only if continuing would hide or duplicate raw output accounting.
5. Force `post_enabled=false` when required reviewer errors exist, and pass the posting plan through the existing local-only conversion.
6. Include top-level dry-run JSON `errors` so the fail-closed reason is machine-visible. Keep redaction on the existing envelope path.
7. Preserve optional failure behavior and add regression coverage proving optional failure alone does not disable posting when a postable finding exists.
8. Run the focused harness, tracer/CLI regressions, fake reviewer tests, full suite, docs check, py-compile, and diff check.
9. Use a fresh subagent for plan review before code changes and fresh code-review subagents until no material issues remain.
10. Commit the plan before implementation, then commit implementation and any review-fix batches separately.

## Out Of Scope

- No live GitHub writer or approval flow.
- No retry/repair changes beyond preserving existing retry status semantics.
- No new quality classifier rules.
- No renderer redesign unless required for machine-visible failure evidence.
- No broad graph refactor.

## Validation Plan

```bash
python -m pytest tests/test_required_reviewer_failure.py -q
python -m pytest tests/test_reviewers_fake.py tests/test_reviewer_runs.py -q
python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py -q
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Collect

- Focused required-failure harness output.
- Regression/full validation output.
- Subagent review result with no material findings.
- Commit SHA for the implementation.
- Linear evidence comment mapping each acceptance criterion to code/tests.
