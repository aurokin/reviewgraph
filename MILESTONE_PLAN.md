# MILESTONE PLAN: PRD 0004 Graph Orchestration

Active execution artifact for this milestone. Linear remains the durable source for issue status, milestone order, blockers, and handoff details; if this file conflicts with Linear, Linear wins. Re-fetch current Linear state before starting each issue.

## Linear Scope Snapshot

- Milestone: `PRD 0004: Graph Orchestration`
- Milestone ID: `c8f7e842-fed0-477c-8877-e9dfbcaf27f4`
- Current status: `AUR-194` complete; `AUR-195` complete; `AUR-196` complete; `AUR-197` complete; `AUR-235` complete; `AUR-198` complete; `AUR-199` complete; `AUR-200` complete; `AUR-225` complete; `AUR-256` active.
- Implementation issues:
  - `AUR-194` / `RG-005: Run Empty Dry-Run Graph On Fixture` / `Done`
  - `AUR-195` / `RG-006: Implement Stage Cursor Invariants` / `Done`
  - `AUR-196` / `RG-007: Select Always-On Reviewers` / `Done`
  - `AUR-197` / `RG-008: Select Path Diff And Label Reviewers` / `Done`
  - `AUR-235` / `RG-046: Classify Change Risk And Size` / `Done`
  - `AUR-198` / `RG-009: Select Gate-Based Risk And Size Reviewers` / `Done`
  - `AUR-199` / `RG-010: Track Reviewer Run Status And Retries` / `Done`
  - `AUR-200` / `RG-011: Run Deterministic Fake Reviewers` / `Done`
  - `AUR-225` / `RG-036: Block Posting On Required Reviewer Failure` / `Done`
- Gate issue:
  - `AUR-256` / `Complete PRD 0004: Graph Orchestration` / `In Progress`

## Milestone Intent

PRD 0004 turns the fixture tracer into explicit graph orchestration. The milestone should make staged reviewer introduction, stage cursor state, reviewer run status, deterministic risk/size routing, fake reviewer execution, reviewer failure policy, and dry-run side-effect bypass visible in graph-owned state and harnesses.

The product point is not to add live integrations. It is to demonstrate that LangGraph-style orchestration owns routing and side-effect decisions while reviewer agents remain scoped prompt/context runners that return structured output.

## Current Code Snapshot

- `src/reviewgraph/graph.py` provides the empty LangGraph dry-run slice used to prove state initialization and no-writer reachability.
- `src/reviewgraph/state.py` owns stage cursor helpers and transition traces. `advance_or_finish_stage` is the only stage cursor mutator for implemented PRD 0004 behavior.
- `src/reviewgraph/routing.py` owns active-stage reviewer selection for always, path, diff pattern, label, conversation pattern, risk, and size triggers.
- `src/reviewgraph/risk.py` records deterministic risk/size facts before risk gates select reviewers.
- `src/reviewgraph/reviewer_runs.py` owns reviewer run keys, run status registration, completed/skipped suppression, retry decisions, and retry exhaustion semantics.
- `src/reviewgraph/reviewers.py` owns deterministic fake reviewer execution through `ReviewerContextPackage`; dry-run JSON records `reviewer_results`.
- `src/reviewgraph/runner.py` wires the fixture tracer through the graph-owned state contracts and preserves dry-run no-writer behavior.
- Required fake reviewer failures now record durable graph errors, force `post_enabled=false`, preserve local dry-run output, and make the posting plan local-only. Optional fake reviewer failures remain failed reviewer results plus local notes without blocking post eligibility by themselves.

## Execution Order

1. `AUR-194` first: establish the explicit empty dry-run graph path from fixture input to empty output. This can wrap the current runner behavior where useful, but the acceptance proof should be graph/state oriented: fixture target, `run_mode=dry_run`, `post_enabled=false`, empty review outputs, and writer branch unreachable.
2. `AUR-195` second: implement stage cursor invariants. Create the minimal state/cursor module before broad routing refactors so every later stage uses one cursor contract.
3. `AUR-196` third: select always-on reviewers for the active stage and persist selected reviewer state with trigger reasons.
4. `AUR-197` fourth: add path, diff pattern, and label selectors on top of the active-stage routing contract.
5. `AUR-235` fifth: extract deterministic risk and size classification before risk gates use it. Risk/size facts should be recorded separately from reviewer selection reasons.
6. `AUR-198` sixth: implement risk and size gates using the `AUR-235` risk assessment. Gate-only reviewers should become selectable when their gates pass.
7. `AUR-199` seventh: track reviewer run keys, statuses, idempotence, and retry exhaustion. This should happen before fake reviewer execution so execution can record selected/running/completed/failed/skipped instead of treating raw fixture output as implicit success.
8. `AUR-200` eighth: add deterministic fake reviewer execution through the scoped reviewer context package. Cover raw findings, local notes, clarification requests, suggested replies, non-findings, malformed output, required failures, and optional failures without live LLM calls.
9. `AUR-225` ninth: make required reviewer failure fail closed while optional reviewer failures remain non-terminal. Preserve local dry-run output and ensure posting-plan construction treats required failure as non-writable state.
10. `AUR-256` last: close the milestone only after all implementation issues are `Done`, focused/full validation passes, docs reflect the orchestration contracts, Linear evidence is complete, and fresh subagent review finds no material gaps.

## Issue Workflow

For each issue:

1. Re-fetch the issue, comments, blockers, and current milestone state from Linear.
2. Move the issue to `In Progress`.
3. Replace `ISSUE_PLAN.md` with a narrow plan for that issue and commit it before implementation.
4. Use fresh subagents to review the issue plan before code changes.
5. Implement the smallest contract/harness slice that satisfies the issue and does not implement later milestone scope.
6. Run the issue harness named by Linear plus regression tests covering touched shared behavior.
7. Use fresh subagents for code/docs review until no material findings remain.
8. Commit the completed issue, and commit separately after every review-fix batch.
9. Move the issue to `In Review`, add a Linear evidence comment with commands and artifact coverage, then move it to `Done` only when acceptance criteria are mapped to concrete evidence.

## Harness Strategy

- `AUR-194` focused harness: `python -m pytest tests/test_graph_empty.py`
- `AUR-195` focused harness: `python -m pytest tests/test_stage_cursor.py`
- `AUR-196` focused harness: `python -m pytest tests/test_routing.py`
- `AUR-197` focused harness: `python -m pytest tests/test_routing.py`
- `AUR-235` focused harness: `python -m pytest tests/test_risk.py`
- `AUR-198` focused harness: `python -m pytest tests/test_routing_risk.py`
- `AUR-199` focused harness: `python -m pytest tests/test_reviewer_runs.py`
- `AUR-200` focused harness: `python -m pytest tests/test_reviewers_fake.py`
- `AUR-225` focused harness: `python -m pytest tests/test_required_reviewer_failure.py`
- Tracer regression harness:
  - `python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py tests/test_render.py`
- Boundary regression harness:
  - `python -m pytest tests/test_reviewer_context.py tests/test_contract_boundaries.py tests/test_context_budget.py tests/test_prompt_injection_memory.py`
- Full validation after shared graph changes:
  - `python -m pytest -q`
  - `python -m py_compile src/reviewgraph/*.py`
  - `python scripts/check_docs.py`
  - `git diff --check`

## Contract Guardrails

- Dry-run remains the default. No PRD 0004 work should introduce live GitHub reads, live LLM calls, approval prompts, or writer reachability.
- Prompts can reason, but graph/state modules decide stage transitions, reviewer selection, retries, clarification stops, posting eligibility, and side-effect reachability.
- `advance_or_finish_stage` is the only code path that mutates `active_stage`, `suspended_stage`, `stage_queue`, or `completed_stages`.
- `clarification_review` is transient and never belongs in the normal stage queue.
- Reviewer selection must record reviewer name, active stage, and trigger reasons in state.
- Risk and size classification must be deterministic, fixture-testable, and recorded as graph-owned state before risk gates select reviewers.
- `ReviewerRunKey` must bind target hash, config hash, stage, reviewer, attempt, retry metadata, and clarification ID. A selected key is not completed until execution records completion.
- Required reviewer failures record durable graph errors and set `post_enabled=false`; optional reviewer failures may carry `ReviewerResult` errors and local notes but do not create top-level graph errors or stop local dry-run output by themselves.
- Fake reviewers receive only `ReviewerContextPackage`; no fake/live reviewer gets GitHub transports, approval state, finalization code, payload builders, writer clients, or ambient tool callables.
- Raw reviewer output remains structured input to quality classification. Reviewer output cannot self-declare public destination, postability, approval, blocking verdict, or GitHub review event.

## Documentation Work

Update the narrowest durable docs alongside behavior:

- Stage cursor, reviewer run status, clarification resume, and graph routing contracts belong in `docs/architecture/state-graph.md`.
- Orchestration module boundaries belong in `docs/architecture/overview.md`.
- Risk/size classification and routing proof belong in `docs/harnesses/harness-engineering.md` and, if durable enough, `docs/architecture/reviewer-config.md`.
- Fake reviewer and graph tracer behavior belongs in `docs/plans/implementation-plan.md` only if sequencing changes materially.
- Keep Linear as the executable backlog. Do not copy the issue tree into durable product docs beyond this active execution plan.

## PRD 0004 Acceptance Surface

- Implemented in this milestone:
  - Empty fixture dry-run graph initialization and no-writer proof.
  - Stage cursor invariants and transition traces for normal stages.
  - Active-stage reviewer selection with always/path/diff/label/risk/size gates and explainable trigger reasons.
  - Deterministic risk/size state before risk gate routing.
  - Reviewer run keys, statuses, idempotent completion suppression, and retry exhaustion semantics.
  - Deterministic fake reviewer execution behind `ReviewerContextPackage`.
  - Explicit required fake reviewer failure fail-closed behavior and optional failure non-terminal behavior.
- Already present from earlier tracer/context work and exercised by PRD 0004:
  - Clarification requests can stop dry-run posting eligibility in fixture runs.
  - Dry-run mode bypasses approval/writer paths.
- Deferred intentionally to later PRDs/milestones:
  - Answered clarification resume and rerunning only affected reviewers remains future graph work tied to review-quality/clarification slices.
  - Approval gate, final payload construction, actor/permission/freshness validation, marker reconciliation, and writer reachability are PRD 0007 side-effect work.
  - Live GitHub reads are PRD 0006; live LLM reviewers are PRD 0008.

## Milestone Completion Criteria

`AUR-256` can close only when:

- Every implementation issue listed in this plan is `Done` in Linear with an evidence comment.
- A fresh Linear milestone inventory proves every active PRD 0004 blocker is complete or has an explicit stale/canceled/not-applicable rationale in Linear.
- Focused validation for all PRD 0004 harness families passes.
- Tracer, boundary, full validation, docs check, py-compile, and diff check pass.
- Durable docs explain the final graph orchestration design an implementation agent needs when dropping into the repo.
- Fresh subagent review of code, tests, docs, Linear evidence, and the milestone gate reports no material issues.
- No unapproved live API, live LLM, approval, or GitHub writer behavior has been introduced.
- No `.ws/` or temporary export artifacts remain.
