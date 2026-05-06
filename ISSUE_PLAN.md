# ISSUE PLAN: AUR-203 Classify Testing Feedback Quality

Active issue plan for `AUR-203` / `RG-014: Classify Testing Feedback Quality`.

Linear remains the source of truth for issue state and relationships.

## Linear Snapshot

- Issue: `AUR-203`
- Status at plan time: `In Progress`
- Milestone: `PRD 0005: Review Quality`
- Title: `RG-014: Classify Testing Feedback Quality`
- Harness: `python -m pytest tests/test_quality_testing.py`
- Out of scope from Linear: general classifier rewrites outside testing rules.

## Intent

Make testing-reviewer output earn public space instead of letting generic coverage advice through.

Testing findings are postable only when they prove all three parts of the contract:

1. the PR changed or introduced behavior;
2. there is a concrete regression scenario, input, caller path, or environment where that behavior matters;
3. the missing coverage is identifiable enough that the author knows what test gap to close.

Generic "add tests", vague "coverage for this change", location-only evidence, and non-postable testing notes must remain local-only or suppressed. The issue is not asking for live ranking, verdict extraction, approval behavior, or broader correctness/security classifier changes.

## Current Baseline

- `src/reviewgraph/quality.py` already detects testing advice when the reviewer is `testing` or when text uses testing/coverage terms.
- `_has_testing_finding_shape` requires missing coverage language, `_has_concrete_testing_shape`, and rejects a small set of vague scenarios.
- Existing broad tests in `tests/test_quality.py` and `tests/test_cli.py` cover several testing examples, but there is no focused `tests/test_quality_testing.py` harness.
- Current policy may still treat weak "missing coverage" text as postable when it has scenario words and changed-code evidence but does not identify a concrete missing test target.

## Decisions

1. Add a focused testing-quality harness instead of expanding broad CLI coverage first.
2. Keep testing-specific policy inside `quality.py` for this issue. Extracting a separate module is only justified if the implementation grows beyond a small helper-level refinement.
3. Treat `reviewer == "testing"` as authoritative testing-reviewer context. Non-testing findings that merely mention "test mode" should remain eligible for normal correctness policy, as existing tests require.
4. Require an identifiable missing coverage target, not just the words "coverage" or "test". Accept concrete targets such as a regression test for a named behavior/path, coverage that does not cover a named path, or no test covering a named scenario.
5. Preserve generic testing feedback as suppressed `non_finding` through the existing suppression path. Local-note pass-through remains available when a reviewer emits `local_note` directly.
6. Prove ranking/posting behavior through posting-plan output: suppressed testing findings should become local-only posting-plan items and must not appear in candidate payload previews.
7. Do not modify severity-to-priority ranking for postable findings unless the focused tests expose a specific bug. The acceptance criterion about ranking is satisfied by proving non-postable testing notes do not enter the postable finding list.

## Implementation Plan

1. Add `tests/test_quality_testing.py`.
   - Cover a concrete testing finding with changed behavior, scenario, and missing coverage target.
   - Cover generic "add tests" / "improve coverage" output.
   - Cover changed behavior and scenario without identifiable missing coverage.
   - Cover missing coverage language with a vague scenario such as "for this change".
   - Cover a local-note testing output remaining local-only.
   - Cover runner/posting-plan behavior for suppressed testing output.

2. Tighten testing quality policy only where focused tests fail.
   - Add a helper for identifiable missing coverage target if needed.
   - Keep the existing concrete behavior/scenario checks.
   - Avoid changing non-testing harmful behavior allowlists.

3. Update durable docs narrowly.
   - `docs/architecture/review-quality.md` should name the three-part testing bar.
   - `docs/harnesses/harness-engineering.md` should identify the focused testing-quality harness.

## Verification

- Focused: `python -m pytest tests/test_quality_testing.py`
- Regression: `python -m pytest tests/test_quality.py tests/test_cli.py tests/test_posting.py tests/test_render.py`
- Full: `python -m pytest -q`
- Hygiene: `python -m py_compile src/reviewgraph/*.py && git diff --check`

## Out Of Scope

- General review-quality rewrites outside testing rules.
- Local verdict extraction.
- Live ranking or approval policy.
- Inline GitHub comments.
- Semantic dedupe.
