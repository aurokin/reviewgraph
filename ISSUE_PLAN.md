# ISSUE PLAN: AUR-207 Compute Local Verdict

Active issue plan for `AUR-207` / `RG-018: Compute Local Verdict`.

Linear remains the source of truth for issue state and relationships.

## Linear Snapshot

- Issue: `AUR-207`
- Status at plan time: `In Progress`
- Milestone: `PRD 0005: Review Quality`
- Title: `RG-018: Compute Local Verdict`
- Harness: `python -m pytest tests/test_verdict.py`
- Out of scope from Linear: public GitHub review events.

## Intent

Extract local verdict and post-eligibility policy from `runner.py` into an explicit module so the graph owns the private recommendation separately from GitHub artifact behavior.

This slice should not implement GitHub `REQUEST_CHANGES`, approval, finalization, or writer behavior. The local verdict is dry-run/private state. Candidate payloads remain top-level issue-comment previews and continue to exclude request-changes wording by default.

## Current Baseline

- `ReviewVerdict` already supports `comment`, `request_changes`, `needs_clarification`, and `no_findings`.
- `runner.py` currently has a private `_local_verdict` helper:
  - blocking pending clarification -> `needs_clarification`;
  - any postable finding -> `comment`;
  - no findings -> `no_findings`.
- `runner.py` computes `post_enabled` inline from:
  - no graph errors;
  - no blocking clarification;
  - local verdict is `comment`;
  - at least one classified finding.
- Existing tests already prove many integration outputs, but there is no focused `tests/test_verdict.py` and no durable `src/reviewgraph/verdict.py`.
- `posting.py` already excludes local request-changes verdict text from candidate payloads by default and rejects explicit public request-changes verdict inclusion.

## Decisions

1. Create `src/reviewgraph/verdict.py` with narrow, deterministic policy helpers.
2. Keep `request_changes` computation conservative for this milestone:
   - Do not generate `request_changes` from low-confidence findings.
   - Do not generate `request_changes` from ambiguous issues; those should be clarification requests and produce `needs_clarification`.
   - In this slice, default postable findings continue to produce `comment` unless a future policy explicitly authorizes request-changes recommendations.
3. Add `compute_post_enabled` beside verdict computation so required reviewer failures and clarification blocks remain explicit graph-owned policy instead of inline runner booleans.
4. Required reviewer failure semantics do not change: top-level `GraphError`s keep `post_enabled=false` while dry-run output remains renderable.
5. Public GitHub artifact kind stays `issue_comment`. Local verdict must not imply a GitHub review event.

## Implementation Plan

1. Add `src/reviewgraph/verdict.py`.
   - `compute_local_verdict(findings, clarification_gate)` returns `needs_clarification`, `comment`, or `no_findings`.
   - `compute_post_enabled(errors, clarification_gate, local_verdict, findings)` returns false for graph errors, blocking clarification, non-comment verdict, or no findings.
   - Keep signatures small and based on existing typed outputs.

2. Wire `runner.py` to the new module.
   - Remove the private `_local_verdict` helper.
   - Preserve the existing output shape and dry-run behavior.
   - Keep `partial_review` metadata available before verdict/post-enabled computation, but do not make optional failures block posting.

3. Add focused harness `tests/test_verdict.py`.
   - Unit-test `compute_local_verdict` and `compute_post_enabled`.
   - Prove blocking clarification yields `needs_clarification`, not `request_changes`.
   - Prove low-confidence or suppressed/no finding paths cannot generate `request_changes`.
   - Prove graph errors disable posting even if findings exist.
   - Prove optional partial review does not disable posting by itself through an integration fixture if needed.
   - Prove dry-run output renders local verdict and candidate payload artifact remains `issue_comment`.
   - Prove public request-changes wording remains excluded from candidate payloads by default.

4. Update durable docs narrowly.
   - `docs/architecture/review-quality.md` should mention local verdict as private policy state.
   - `docs/harnesses/harness-engineering.md` should name `tests/test_verdict.py`.
   - Avoid broader milestone docs refactor until the PRD 0005 gate.

## Verification

- Focused: `python -m pytest tests/test_verdict.py -q`
- Related regression: `python -m pytest tests/test_clarification.py tests/test_required_reviewer_failure.py tests/test_optional_reviewer_failure.py tests/test_posting.py tests/test_render.py -q`
- Full: `python -m pytest -q`
- Hygiene: `python -m py_compile src/reviewgraph/*.py && python scripts/check_docs.py && git diff --check`

## Out Of Scope

- GitHub `REQUEST_CHANGES`, `COMMENT`, or `APPROVE` review submission.
- Approval/finalization/writer behavior.
- New ranking policy beyond existing graph-owned finding priority.
- Public request-changes wording.
- Live GitHub or live LLM behavior.
