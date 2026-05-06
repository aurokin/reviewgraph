# PRD 0004: Graph Orchestration

## Problem Statement

ReviewGraph must demonstrate LangGraph as a real orchestration layer. A simple linear script would not show staged agent introduction, clarification resume, stateful routing, or side-effect gates. At the same time, graph behavior must be precise enough that implementation does not invent state-machine semantics.

## Solution

Implement the LangGraph workflow around explicit stage cursor state, reviewer run keys/status, clarification scheduling, and dry-run/post branches. The graph owns routing and side-effect decisions; reviewers only produce structured output.

## User Stories

1. As a LangGraph evaluator, I want graph nodes to own routing, so that prompts cannot secretly decide control flow.
2. As a developer, I want stage cursor state to be durable, so that fixture runs and resumes are deterministic.
3. As a developer, I want reviewer run status keyed by target/config/stage/reviewer, so that retries and resumes do not duplicate work.
4. As a maintainer, I want required reviewer failures to block posting, so that partial review does not become public feedback.
5. As a maintainer, I want optional reviewer failures recorded but non-terminal, so that one weak reviewer does not kill the run.
6. As a reviewer, I want clarification requests to stop posting, so that ambiguous issues do not become high-confidence findings.
7. As a developer, I want answered clarifications to resume only affected reviewers, so that unrelated stages are not rerun.
8. As a maintainer, I want dry-run mode to bypass approval and writer paths, so that default behavior is safe.
9. As a maintainer, I want final payload construction after approval, so that item-level selection cannot post unapproved findings.
10. As a developer, I want graph traces for stage cursor transitions, so that resume bugs are visible in tests.

## Implementation Decisions

- Valid MVP stages are `initial_triage`, `specialized_review`, `logic_review`, and `clarification_review`.
- Normal initial state is `active_stage=None`, `stage_queue=["initial_triage", "specialized_review", "logic_review"]`, and `completed_stages=[]`.
- `stage_queue` contains only future normal stages, never the active stage.
- `clarification_review` is transient and non-queue.
- `advance_or_finish_stage` is the only node that mutates `active_stage`, `suspended_stage`, `stage_queue`, or `completed_stages`.
- `ingest_clarification_answer` records the answer and schedules clarification resume but does not mutate stage cursor fields.
- Clarification resume routes through `advance_or_finish_stage`, then `select_reviewers`, then normal reviewer execution.
- `reviewer_run_status` distinguishes selected, running, completed, failed, and skipped.
- `approval_gate` records approvals only; `finalize_github_payload` builds and validates the final payload.
- `finalize_github_payload` owns final hash, actor/permission, redaction, and target freshness checks before any writer is reachable.
- `post_or_emit` emits dry-run output unless run mode is post and it receives an already-finalized payload.

## Testing Decisions

- Graph tests assert dry-run cannot reach writer branch.
- Stage cursor tests assert first-stage initialization, future-only queue semantics, and completed stages never rerun.
- Clarification tests assert resumed clarification does not pop unrelated queued stages.
- Reviewer status tests assert selected-but-not-run is not treated as completed.
- Payload finalization tests assert candidate payloads are not posted after item-level selection.

## Out of Scope

- Live GitHub.
- Live LLM.
- Hosted workflow/webhook mode.

## Further Notes

This PRD is the core LangGraph demonstration. It should stay rigorous even if individual reviewer logic remains fake or deterministic in early slices.

## Implementation Status

The PRD 0004 milestone completed the fixture-backed orchestration slice, not every future graph node named in the full product design.

Implemented:

- empty fixture dry-run graph initialization with no-writer proof;
- normal stage cursor invariants and transition traces for `initial_triage`, `specialized_review`, and `logic_review`;
- active-stage reviewer selection for always, path, diff, label, risk, and size triggers;
- deterministic risk/size graph state before risk gates;
- reviewer run keys, selected/running/completed/failed/skipped statuses, retry selection, and retry exhaustion semantics;
- deterministic fake reviewer execution through `ReviewerContextPackage`;
- required fake reviewer failure as fail-closed graph state that preserves dry-run output and disables posting eligibility;
- optional fake reviewer failure as a non-terminal failed reviewer result plus local note;
- dry-run bypass of approval and writer paths.

Deferred intentionally:

- answered clarification resume through `clarification_review` moved to PRD 0005 review-quality graph primitives;
- approval, final payload construction, actor/permission checks, target freshness checks, marker reconciliation, and writer reachability belong to PRD 0007 side effects;
- live GitHub reads belong to PRD 0006;
- live LLM reviewer execution belongs to PRD 0008.
