# ISSUE PLAN: AUR-206 Resume From Clarification Answers

Active issue plan for `AUR-206` / `RG-017: Resume From Clarification Answers`.

Linear remains the source of truth for issue state and relationships.

## Linear Snapshot

- Issue: `AUR-206`
- Status at plan time: `In Progress`
- Milestone: `PRD 0005: Review Quality`
- Title: `RG-017: Resume From Clarification Answers`
- Harness: `python -m pytest tests/test_clarification_resume.py`
- Out of scope from Linear: live human UI or GitHub comment replies.

## Intent

Add the deterministic state-machine contract for answering a pending clarification and resuming only the affected reviewer through transient `clarification_review`.

This issue should not turn the fixture CLI into a full interactive product. The goal is to make the graph primitives true and testable: an answer updates clarification state without cursor mutation, `advance_or_finish_stage` can enter and leave `clarification_review`, resumed reviewer run keys carry the clarification ID, unrelated completed stages are not rerun, and answered/stale pending IDs no longer block posting.

## Current Baseline

- `AUR-205` added `evaluate_clarification_gate`, pending/blocking IDs, and blocking-stop behavior.
- `ClarificationRequest` already records `source_stage`, `source_run_key`, `status`, `resume_target_stage`, and `resume_target_reviewers`.
- `ClarificationAnswer` and `ClarificationStatus` models exist but no helper ingests answers yet.
- `advance_or_finish_stage` currently rejects `clarification_review` with `StageCursorError("clarification_review resume is not implemented in this slice")`.
- `make_reviewer_run_key` and `register_selected_reviewer` already accept `clarification_id`, but `select_reviewers_for_active_stage` does not pass one.
- `has_suppressing_status_for_reviewer` ignores clarification ID, so completed normal-stage runs would suppress resumed clarification runs unless that identity rule changes for clarification resumes.

## Decisions

1. Implement AUR-206 as pure graph/state primitives plus focused harness, not live UI.
2. Add `ingest_clarification_answer(review_state, answer)` to `clarification.py`.
   - It validates that the request exists and is pending.
   - It appends the answer, replaces the stored `ClarificationRequest` with `status=ANSWERED`, updates `clarification_status[request_id]` to `answered`, removes the request ID from `pending_clarification_ids`, and records the answered ID for the next clarification run.
   - It must not mutate `active_stage`, `suspended_stage`, `stage_queue`, or `completed_stages`.
3. Add an explicit field to `ReviewState` for scheduled answered clarification IDs, likely `ready_clarification_ids: list[str]`. This avoids overloading `pending_clarification_ids` and makes stale pending IDs testable.
4. Teach `advance_or_finish_stage` to:
   - enter `clarification_review` when `ready_clarification_ids` is non-empty and a normal stage is active;
   - set `suspended_stage` to the current normal stage;
   - consume exactly one ready clarification ID on entry by moving it into an active/scheduled resume slot, so the same answer cannot re-enter repeatedly;
   - restore the suspended stage after clarification review;
   - never put `clarification_review` in the normal queue or completed list.
5. Keep the resume selector narrow:
   - Provide a production helper/API that selects only reviewers named by the answered request's `resume_target_reviewers`.
   - Register resumed run keys with `stage=clarification_review` and the answered `clarification_id`.
   - Key selection to the specific active clarification ID, not just any pending/answered request.
   - Do not rerun unrelated completed normal stages or unrelated reviewers.
6. Adjust reviewer-run suppression so a completed normal-stage run does not suppress a clarification-resume run for the same reviewer when the new run key has a clarification ID.
7. Stale pending IDs should not keep `post_enabled=false`: answered IDs are removed from `pending_clarification_ids`, `ClarificationRequest.status` becomes `ANSWERED`, and `evaluate_clarification_gate` should only block on requests whose current request status is pending. The request object status is the authoritative source; `clarification_status` is a derived/indexed view that must match it.

## Implementation Plan

1. Extend models/state minimally.
   - Add `ready_clarification_ids` and `active_clarification_id` to `ReviewState`.
   - Update empty graph and runner initializers/tests for the new state field.

2. Extend `clarification.py`.
   - Keep `evaluate_clarification_gate` pure.
   - Add `ingest_clarification_answer` and small helpers for request lookup/status update.
   - Ensure it records answer state without cursor mutation.
   - Ensure gate evaluation treats answered request objects as non-blocking even if a stale pending ID list was not yet cleaned up.

3. Extend `state.py`.
   - Allow `clarification_review` as transient `active_stage` with a non-null `suspended_stage`.
   - Implement enter/exit transitions in `advance_or_finish_stage`.
   - Consume one `ready_clarification_ids` entry into `active_clarification_id` on entry, and clear `active_clarification_id` on exit after restoring the suspended stage.
   - Preserve normal-stage queue/completed invariants.

4. Add resume reviewer selection/key helpers.
   - Extend routing/reviewer-run production code with a clarification resume path.
   - Ensure resumed keys include `clarification_id` and only affected reviewers are selected.
   - Ensure completed normal-stage reviewer statuses do not suppress clarification-review runs for the same reviewer/target/config.

5. Add `tests/test_clarification_resume.py`.
   - Answer ingestion marks pending request answered and removes the pending ID without cursor mutation.
   - `advance_or_finish_stage` enters `clarification_review`, then restores the suspended stage.
   - Ready clarification IDs are consumed once; a second `advance_or_finish_stage` does not re-enter for the same answered ID.
   - Resumed run key includes the clarification ID.
   - A completed unrelated stage/reviewer is not rerun during clarification resume.
   - Answered/stale pending IDs do not keep the clarification gate blocking, and post eligibility can recover when findings exist and no pending blocking requests remain.

6. Update durable docs narrowly.
   - `docs/architecture/state-graph.md` should reflect the implemented answer ingestion and transient resume behavior.
   - `docs/harnesses/harness-engineering.md` should name `tests/test_clarification_resume.py`.

## Verification

- Focused: `python -m pytest tests/test_clarification_resume.py`
- Regression: `python -m pytest tests/test_clarification.py tests/test_stage_cursor.py tests/test_reviewer_runs.py tests/test_routing.py tests/test_graph_empty.py`
- Full: `python -m pytest -q`
- Hygiene: `python -m py_compile src/reviewgraph/*.py && python scripts/check_docs.py && git diff --check`

## Out Of Scope

- Live human answer UI.
- GitHub comment replies.
- Full CLI interactive resume command.
- Live LLM reruns.
- Approval/finalization behavior.
- Resolving clarification based on new reviewer output beyond state restoration and run-key proof.
