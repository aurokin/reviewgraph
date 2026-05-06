# ISSUE PLAN: AUR-200 Run Deterministic Fake Reviewers

Active issue plan for `AUR-200` / `RG-011: Run Deterministic Fake Reviewers`.

## Linear Snapshot

- Issue: `AUR-200`
- Status at plan time: `In Progress`
- Milestone: `PRD 0004: Graph Orchestration`
- Comments at plan time: none
- Linear description: add a fake reviewer adapter that returns deterministic raw outputs for selected reviewers.

## Goal

Add a deterministic fake reviewer adapter boundary whose reviewer call consumes only `ReviewerContextPackage` and returns `ReviewerResult` records through graph execution metadata. This proves the live reviewer adapter shape without live LLM calls, GitHub transports, or prompt-owned control flow.

Existing runner code reads `raw_reviewer_outputs` directly and immediately classifies them. This issue should route the deterministic runner through the fake adapter and record `ReviewerResult`s while keeping quality classification policy and required-failure posting policy in their existing/later slices.

## Acceptance Mapping

- Fake reviewers can return raw findings, local notes, clarification requests, suggested replies, non-findings, malformed JSON, and failures:
  - Add deterministic fake output fixtures covering each output kind and adapter errors.
- Fake outputs are keyed by fixture and reviewer:
  - Key fake outputs by fixture ID, reviewer name, and stage in fake-adapter construction/harness configuration; assert missing keys return a failed result.
- Fake reviewers receive the same scoped context package used by live reviewer adapters:
  - Build the adapter call from `ReviewerContextPackage` only. Fixture ID, registry, and run key are execution/harness metadata outside the reviewer input.
  - Assert the adapter never receives fixture PR objects, GitHub clients, writer clients, approval state, or posting payload builders.
- Golden raw outputs cover postable findings, local notes, suppressed non-findings, clarification requests, suggested replies, malformed repair/failure, required reviewer failure, and optional reviewer failure:
  - Add `tests/test_reviewers_fake.py` golden cases for successful outputs and deterministic failure variants. Required/optional distinction can be represented as reviewer config metadata on the context package; posting effects remain out of scope.
- Reviewer results include run key, status, raw output, and errors:
  - Extend `ReviewerResult` minimally with `status`, opaque `raw_output`, and `errors` fields, preserving existing typed output tuples and malformed raw strings.
- No live LLM is used:
  - Ensure fake adapter has no provider/network dependency and emits a local deterministic result.

## Implementation Plan

1. Extend `ReviewerResult` with explicit `status`, `raw_output`, and `errors` fields.
2. Add `src/reviewgraph/reviewers.py` with a pure fake adapter configured with fixture ID and a deterministic fake output registry. Its reviewer-facing `run` method accepts only `ReviewerContextPackage`; the graph/executor attaches `ReviewerRunKey` to the resulting `ReviewerResult`.
3. Normalize fake output dicts into `ReviewerResult` typed tuples for findings, local notes, clarification requests, suggested replies, and suppressed non-findings.
4. Represent malformed JSON strings and reviewer failures as `failed` reviewer results with raw output/errors, not as live repair prompts.
5. Add `tests/test_reviewers_fake.py` with golden cases for success variants, malformed/failure variants, required/optional reviewer metadata, scoped context use, and no live LLM/provider behavior.
6. Wire the deterministic runner through the fake adapter, record `ReviewerResult`s in graph state/output, and then feed completed raw output into the existing quality classification path. Do not change quality classification policy.
7. Run fake reviewer, model, context-boundary, tracer/CLI, and full validation.
8. Use subagent review before implementation and after code changes.
9. Commit the plan before implementation, then commit implementation separately.

## Out Of Scope

- No live LLM adapter.
- No provider repair prompt for malformed output.
- No new quality classification policy.
- No required reviewer failure posting gate; `AUR-225` owns fail-closed posting behavior.
- No GitHub writer, approval, finalization, or side-effect behavior.

## Validation Plan

```bash
python -m pytest tests/test_reviewers_fake.py -q
python -m pytest tests/test_models.py tests/test_reviewer_context.py tests/test_contract_boundaries.py -q
python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py -q
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Collect

- Focused fake reviewer harness output.
- Regression/full validation output.
- Subagent review result with no material findings.
- Commit SHA for the implementation.
- Linear evidence comment mapping each acceptance criterion to code/tests.
