# ISSUE PLAN: AUR-226 Continue After Optional Reviewer Failure

Active issue plan for `AUR-226` / `RG-037: Continue After Optional Reviewer Failure`.

Linear remains the source of truth for issue state and relationships.

## Linear Snapshot

- Issue: `AUR-226`
- Status at plan time: `In Progress`
- Milestone: `PRD 0005: Review Quality`
- Title: `RG-037: Continue After Optional Reviewer Failure`
- Harness: `python -m pytest tests/test_optional_reviewer_failure.py`
- Out of scope from Linear: required reviewer semantics.

## Intent

Make optional reviewer failure continuation a focused review-quality contract rather than behavior that is only incidentally covered by required-failure and JSON-repair tests.

The graph should record optional reviewer failures, keep classifying usable output from other reviewers, expose partial-review metadata for dry-run output and later verdict policy, and avoid treating optional failure alone as a post-eligibility blocker.

## Current Baseline

- `runner.py` already treats failed optional reviewers differently from required reviewers:
  - it marks the reviewer run failed;
  - it appends an "Optional reviewer failed" local note;
  - it continues to classify other reviewer output;
  - it does not append a top-level `GraphError`, so optional failure alone does not block `post_enabled`.
- Broad coverage already exists in:
  - `tests/test_required_reviewer_failure.py::test_optional_reviewer_failure_does_not_block_post_eligibility`;
  - `tests/test_reviewer_json_repair.py::test_optional_unrepaired_failure_continues_as_partial_review`.
- What is missing for this Linear issue:
  - a focused harness named by the issue;
  - a small explicit partial-review metadata summary derived from existing failed optional reviewer results, rather than relying on readers to infer partial review from local notes and raw reviewer-result arrays;
  - proof that later stages still run after an optional failure when selected reviewers remain eligible.

## Decisions

1. Keep required-reviewer behavior unchanged. Required failures remain fail-closed for post eligibility.
2. Do not retry optional failures in this slice. Retry policy is separate from continuation semantics.
3. Represent partial-review metadata as local dry-run data derived from `reviewer_results` and reviewer run status before the final JSON envelope is built, not as markdown prose hidden in rendering.
4. Keep the local note for human-readable dry-run output, but do not make it the only machine-readable signal.
5. Treat optional failure as local-only metadata. It should not become a postable finding, candidate payload item, GitHub review event, or public request-changes pressure.

## Implementation Plan

1. Add focused harness `tests/test_optional_reviewer_failure.py`.
   - Cover explicit optional reviewer failure with another reviewer producing a postable finding.
   - Cover optional unrepaired JSON failure as partial review.
   - Cover optional failure in an earlier stage with later-stage reviewer output still selected, executed, normalized, and classified.
   - Assert required-failure behavior stays covered by existing regression harness, not reimplemented here.

2. Add explicit partial-review metadata to dry-run JSON with a narrow helper.
   - Derive it from failed non-required reviewer results before final envelope rendering.
   - Include reviewer name, stage, status, redacted reason/error, and whether the failure is required.
   - Keep it local/dry-run only for now.
   - Use the existing reviewer config to distinguish optional vs required if needed.
   - Do not include raw reviewer output or unredacted adapter errors in the metadata summary.

3. Keep rendering behavior conservative.
   - Preserve existing local notes for optional failure.
   - Avoid adding public candidate payload text for optional failure metadata.
   - Treat JSON plus existing local notes as the dry-run rendering surface for this slice; do not add new markdown sections unless tests show the existing local note is insufficient.

4. Update durable docs narrowly.
   - `docs/harnesses/harness-engineering.md` should name the focused optional-failure harness.
   - `docs/architecture/review-quality.md` or existing architecture docs should mention optional failure as partial-review metadata only if the file already owns that policy.
   - Avoid broad docs refactors before the milestone gate.

## Verification

- Focused: `python -m pytest tests/test_optional_reviewer_failure.py -q`
- Related regression: `python -m pytest tests/test_required_reviewer_failure.py tests/test_reviewer_json_repair.py tests/test_reviewers_fake.py tests/test_reviewer_runs.py -q`
- Full: `python -m pytest -q`
- Hygiene: `python -m py_compile src/reviewgraph/*.py && python scripts/check_docs.py && git diff --check`

## Out Of Scope

- Required reviewer failure policy changes.
- Retry scheduling.
- Live LLM failures.
- Live GitHub reads or writes.
- Approval/finalization behavior.
- Public GitHub payload text for partial-review metadata.
