# ISSUE PLAN: AUR-227 Repair Or Record Malformed Reviewer JSON

Active issue plan for `AUR-227` / `RG-038: Repair Or Record Malformed Reviewer JSON`.

## Linear Snapshot

- Issue: `AUR-227`
- Status at plan time: `In Progress`
- Milestone: `PRD 0005: Review Quality`
- Comments at plan time: none
- Linear description: handle malformed reviewer JSON with a deterministic fake repair path and error fallback.
- Focused harness requested by Linear: `python -m pytest tests/test_reviewer_json_repair.py`
- Upstream issue now complete: `AUR-201`, commit `7a0f44f`, introduced typed normalization and durable `normalization_errors`.

## Goal

Add one deterministic fake repair attempt for repairable selected-reviewer output failures. If repair succeeds, the repaired output flows through the normal `normalize_reviewer_output(...)` path and the runner classifies the typed artifacts exactly as any other valid reviewer output. If repair fails or returns invalid output, the reviewer result records structured errors; required reviewers block posting, optional reviewers continue as partial review.

The slice should make malformed reviewer output a controlled reviewer lifecycle, not an accidental raw string failure, while preserving hard fixture-structure validation for truly invalid fixtures.

## Acceptance Mapping

- Invalid reviewer JSON triggers one repair attempt:
  - Raw string outputs with invalid JSON and fatal repairable normalization failures should call a deterministic fake repair hook at most once.
  - Explicit reviewer failures (`failure: true`) are already intentional failures and should not be repaired.
  - Missing fixture/reviewer/stage keys and malformed fixture `raw_reviewer_outputs` entries remain fixture input errors, not repairable reviewer output.
- Successful repair proceeds to normalization:
  - A repaired mapping should enter `normalize_reviewer_output(...)`.
  - Valid repaired artifacts should become typed `ReviewerResult` artifacts and then flow through the existing runner safety/quality checks.
  - Repaired output must not bypass graph-owned field rejection, evidence provenance checks, changed-line assertions, or postability policy.
- Failed repair records an error:
  - Preserve the original raw output.
  - Record structured `NormalizationError` entries for the original failure and the failed repair result.
  - Include enough machine-readable repair metadata in `ReviewerResult` or `normalization_errors` to prove a single repair attempt happened without parsing prose.
- Required reviewer unrepaired failure blocks posting:
  - Required unrepaired failures should become graph-owned fail-closed dry-run state: failed reviewer result/status, durable graph error, `post_enabled=false`, no candidate payload, and local-only posting plan.
  - This changes only selected reviewer output repair exhaustion, not fixture structure errors.
- Optional reviewer unrepaired failure continues as partial review:
  - Optional unrepaired failures should record a failed reviewer result and local note.
  - Other reviewers and later stages should continue.
  - Optional unrepaired failure alone must not create a top-level graph error or block post eligibility.

## Current Baseline

- `src/reviewgraph/reviewers.py` returns failed `ReviewerResult`s for raw invalid JSON strings, non-mapping outputs, missing output, invalid item lists, invalid items, and normalizer exceptions. It does not attempt repair.
- `src/reviewgraph/findings.py` returns repairable fatal `NormalizationError`s for malformed mapping/item shapes and nonfatal errors for graph-owned field rejection.
- `src/reviewgraph/runner.py` currently treats explicit `failure: true` required reviewer failures as fail-closed dry-run output, but non-explicit reviewer failures still raise `RunnerError` for required reviewers.
- `src/reviewgraph/reviewer_runs.py` already models retry run keys, but this issue is about one deterministic output repair attempt, not rerunning the reviewer or adding live repair model calls.
- `docs/architecture/state-graph.md` currently says invalid reviewer JSON retries once with repair, but also says malformed fixture data/raw-output schema is not a successful review. AUR-227 should sharpen that distinction: selected reviewer output can repair/fail as reviewer state; broken fixture envelope/selection data remains an input error.

## Implementation Plan

1. Create `tests/test_reviewer_json_repair.py` first with focused failing cases:
   - invalid raw string triggers one deterministic repair attempt;
   - successful repair normalizes and classifies a postable finding through the existing runner path;
   - failed repair records structured original and repair errors;
   - required unrepaired failure blocks posting without invoking writer;
   - optional unrepaired failure continues and records partial-review local note;
   - explicit `failure: true` is not repaired.
2. Add a small deterministic fake repair contract in `reviewers.py`.
   - Prefer an adapter method such as `repair(...)` or a script object over hidden global state.
   - Keep the adapter boundary scoped to `ReviewerContextPackage`; do not introduce GitHub, LLM, provider, approval, or writer handles.
   - Support fixture/fake definitions that can provide malformed raw output plus an optional repaired output.
3. Add a single repair-attempt helper around `execute_fake_reviewer`.
   - Initial raw/normalization failures that are fatal and repairable should call the repair hook once.
   - Repaired mapping outputs should call `normalize_reviewer_output(...)`.
   - Repaired strings/non-mappings/malformed mappings should fail with structured errors.
   - Nonfatal graph-owned field rejections should not trigger repair.
4. Extend the existing error carrier only as much as needed.
   - Reuse `NormalizationError` when possible.
   - If needed, add narrowly scoped fields so JSON output proves original-vs-repair error source and repair attempt count.
   - Avoid string-only repair state.
5. Update runner failure handling for repair-exhausted selected reviewer output.
   - Required reviewer repair exhaustion should follow the same fail-closed dry-run shape as explicit required reviewer failure.
   - Optional reviewer repair exhaustion should keep existing optional local-note continuation.
   - Fixture structure errors should still raise `RunnerError`.
6. Update `fake_registry_from_fixture_outputs(...)` only if needed to express repaired fake outputs in packaged fixtures/tests.
   - Preserve existing simple mapping outputs.
   - Do not change broad fixture behavior unless a focused repair fixture requires it.
7. Update durable docs narrowly:
   - `docs/architecture/state-graph.md` for selected-output repair/failure semantics vs fixture input errors.
   - `docs/architecture/findings-contract.md` if `ReviewerResult` repair metadata or normalization-error shape changes.
   - `docs/harnesses/harness-engineering.md` only if the fake repair proof shape needs durable guidance.
8. Keep `AUR-204`, `AUR-202`, `AUR-203`, `AUR-205`, `AUR-206`, `AUR-226`, and `AUR-207` out of scope.

## Out Of Scope

- No live repair model call or provider prompt.
- No quality-classifier extraction.
- No diff-anchor validation.
- No semantic deduplication.
- No clarification answer/resume implementation.
- No local verdict extraction.
- No live GitHub read, live LLM, approval, finalization, inline posting, or writer behavior.
- No repository checkout or test execution from reviewer agents.

## Validation Plan

```bash
python -m pytest tests/test_reviewer_json_repair.py
python -m pytest tests/test_findings.py tests/test_reviewers_fake.py
python -m pytest tests/test_required_reviewer_failure.py tests/test_reviewer_runs.py
python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py tests/test_render.py
python -m pytest tests/test_reviewer_context.py tests/test_contract_boundaries.py tests/test_context_budget.py tests/test_prompt_injection_memory.py tests/test_redaction.py
python scripts/check_docs.py
python -m py_compile src/reviewgraph/*.py
git diff --check
```

Run `python -m pytest -q` after the focused and regression harnesses are green.

## Completion Evidence To Collect

- Focused `tests/test_reviewer_json_repair.py` output.
- Focused reviewer/normalizer regression output.
- Required/optional failure regression output.
- Tracer/CLI/render regression output.
- Boundary and prompt-injection regression output.
- Docs, py-compile, diff, and full-suite checks.
- Subagent plan-review findings and fixes.
- Subagent code-review findings and fixes.
- Linear evidence comment mapping every AUR-227 acceptance criterion to code/tests.
