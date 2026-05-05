# PRD 0002: MVP Tracer Bullet

## Problem Statement

The architecture is broad enough that implementation could get trapped in models and policy before producing a useful runnable slice. ReviewGraph needs an early end-to-end path that proves the product shape without live APIs or side effects.

## Solution

Build the first vertical tracer bullet around fixtures and fake reviewers:

fixture PR -> conversation memory -> review target -> context budget -> staged reviewer selection -> fake reviewer outputs -> quality classification -> local verdict -> posting plan -> markdown/JSON dry-run output -> no writer reachable.

This tracer bullet should demonstrate the graph and the quality gate, not full GitHub or live LLM behavior.

## User Stories

1. As a developer, I want to run ReviewGraph on a fixture PR, so that I can validate the product without credentials.
2. As a developer, I want selected reviewers and trigger reasons in output, so that routing is inspectable.
3. As a developer, I want fake reviewer output to exercise findings, notes, suppressed output, and clarification requests, so that the graph path is realistic.
4. As a developer, I want JSON and markdown dry-run output, so that both machine and human consumers are supported.
5. As a maintainer, I want the dry-run path to prove no writer can be reached, so that side-effect discipline is testable early.
6. As a maintainer, I want stale approval/write logic excluded from this first slice, so that the initial demo stays focused.
7. As a LangGraph evaluator, I want to see staged routing in the first runnable demo, so that the graph value is visible immediately.
8. As a reviewer, I want local notes separated from postable findings, so that the output does not imply every useful observation should be posted.

## Implementation Decisions

- Use fixture PRs as the first GitHub adapter input.
- Use deterministic fake reviewers as the first reviewer adapter.
- Include the graph nodes needed to prove the product path, even when individual nodes use simple deterministic logic.
- Build posting plans in dry-run mode but do not implement live writer behavior in this PRD.
- Run mode must be explicit: `dry_run` cannot enter approval or writer code.
- The output should include review target metadata, selected reviewers, classified findings, local notes, suppressed counts, clarification requests, local verdict, and candidate posting plan.

## Testing Decisions

- Add fixture graph tests for a normal PR, a specialized-review PR, and an ambiguous logic PR.
- Assert dry-run mode never invokes a writer.
- Assert stage cursor initialization advances to `initial_triage` before selection.
- Assert fake reviewer output is classified before rendering.
- Assert local notes do not appear as approved/postable GitHub items.

## Out of Scope

- Live GitHub reads.
- Live LLM calls.
- GitHub posting.
- Inline comment mapping.
- Repository checkout.

## Further Notes

This PRD should produce the first demoable ReviewGraph command, even if the command initially accepts only fixture PR references.
