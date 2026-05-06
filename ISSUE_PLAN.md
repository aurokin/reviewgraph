# ISSUE PLAN: AUR-205 Stop For Clarification Requests

Active issue plan for `AUR-205` / `RG-016: Stop For Clarification Requests`.

Linear remains the source of truth for issue state and relationships.

## Linear Snapshot

- Issue: `AUR-205`
- Status at plan time: `In Progress`
- Milestone: `PRD 0005: Review Quality`
- Title: `RG-016: Stop For Clarification Requests`
- Harness: `python -m pytest tests/test_clarification.py`
- Out of scope from Linear: answer ingestion and resume behavior from `AUR-206`.

## Intent

Make unanswered reviewer clarification an explicit graph stop state, not just a rendered request.

If a reviewer says it cannot make a high-confidence mergeability or confidence judgment without human context, ReviewGraph should preserve the request as pending state, disable posting, render the question and why it matters, and avoid converting that ambiguity into a blocking local verdict. The graph may still show postable findings and local notes in dry-run output, but they must be local-only while any blocking clarification remains pending.

Clarification requests with `blocks_verdict=false` are still pending/rendered state, but they do not stop the graph, disable posting, or force the private verdict to `needs_clarification` by themselves.

## Current Baseline

- `ClarificationRequest` already carries graph-owned `status`, `source_stage`, `source_run_key`, `resume_target_stage`, and `resume_target_reviewers` during normalization.
- `classify_review_quality` preserves safe clarification requests and suppresses unsafe or omitted-memory clarification requests.
- `runner._run_review_stages` already breaks the stage loop when any classified clarification request exists and appends a `clarification_needed_end` trace.
- `runner._local_verdict` currently returns `needs_clarification` when clarification requests exist, and `post_enabled` is false unless the verdict is `comment`.
- `build_posting_plan` already renders clarification requests as local-only items, and `render_review` includes clarification question/why-it-matters in markdown and JSON.
- Existing broad CLI tests prove clarification-only and finding-plus-clarification fixtures are not post enabled, but there is no focused `tests/test_clarification.py` harness and the top-level dry-run envelope does not expose `pending_clarification_ids` / `clarification_status` state.

## Decisions

1. Add a small `src/reviewgraph/clarification.py` policy helper rather than continuing to scatter clarification state derivation across runner/rendering.
2. The helper should only model unanswered pending state for AUR-205:
   - stable pending IDs from request IDs;
   - status map keyed by request ID;
   - blocking pending IDs;
   - whether any pending blocking request blocks posting/verdict confidence.
3. Do not implement human answers, status transitions to answered/resolved, transient `clarification_review` execution, or affected-reviewer reruns; those belong to AUR-206.
4. Preserve the current private verdict value `needs_clarification` for local dry-run output. The acceptance criterion means no `request_changes` / blocking verdict should be produced from ambiguous issues, not that the private verdict must be `None`.
5. If any pending blocking clarification exists, every posting-plan item should be local-only and `candidate_payload_preview` should be absent, even when there are otherwise postable findings.
6. Non-blocking pending clarifications remain visible and local-only in the posting plan, but they should not prevent otherwise eligible postable findings from producing a candidate payload.
7. Keep existing provenance rules: unsafe or omitted-memory clarification requests are suppressed and should not create pending state.

## Implementation Plan

1. Add `src/reviewgraph/clarification.py`.
   - Define a frozen result such as `ClarificationGateResult`.
   - Provide `evaluate_clarification_gate(requests)` that returns pending IDs, status map, blocking IDs, and a `blocks_posting` flag based only on pending `blocks_verdict=true` requests.
   - Keep the API pure and fixture-safe; no GitHub, no writer, no answer ingestion.

2. Wire the helper into `runner.py`.
   - Derive clarification gate state after output IDs are validated and before local verdict/posting-plan construction.
   - Use the gate result to keep `post_enabled=false` whenever a pending blocking clarification exists.
   - Use the gate result for stage-loop stop behavior so non-blocking clarifications do not emit `clarification_needed_end`.
   - Include top-level dry-run JSON fields for `pending_clarification_ids` and `clarification_status` so graph state is visible outside rendered review JSON.
   - Preserve the existing `clarification_needed_end` trace behavior.

3. Add focused harness `tests/test_clarification.py`.
   - Clarification-only fixture produces pending state with stable ID, `status=pending`, `post_enabled=false`, local verdict `needs_clarification`, no writer call, no candidate payload, and rendered question/why-it-matters.
   - Finding plus clarification keeps all posting-plan items local-only and produces no candidate payload.
   - Non-blocking clarification (`blocks_verdict=false`) becomes pending/rendered state but does not stop stage advancement, does not force `needs_clarification`, and does not suppress otherwise eligible candidate payloads.
   - Unsafe or omitted-memory clarification requests are suppressed and do not create pending IDs.
   - Graph trace stops at `clarification_needed_end` without advancing unrelated later stages.
   - No local `request_changes` verdict is produced from clarification ambiguity.

4. Update durable docs narrowly.
   - `docs/architecture/state-graph.md` should identify the pending clarification gate state that stops before posting.
   - `docs/harnesses/harness-engineering.md` should name `tests/test_clarification.py` as the focused stop-state harness.

## Verification

- Focused: `python -m pytest tests/test_clarification.py`
- Regression: `python -m pytest tests/test_quality.py tests/test_cli.py tests/test_tracer_fixture_run.py tests/test_render.py tests/test_posting.py`
- Full: `python -m pytest -q`
- Hygiene: `python -m py_compile src/reviewgraph/*.py && python scripts/check_docs.py && git diff --check`

## Out Of Scope

- Answer ingestion.
- Resume from answered clarification.
- `clarification_review` reviewer reruns.
- GitHub posting of clarification questions.
- Approval/finalization behavior.
- Local verdict extraction beyond the existing private `needs_clarification` value.
