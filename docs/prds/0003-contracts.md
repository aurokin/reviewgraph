# PRD 0003: Contracts

## Problem Statement

ReviewGraph has many safety and quality rules that depend on durable schemas. If implementation starts with ad hoc dictionaries or prompt-shaped blobs, routing, classification, approval, and posting behavior will drift.

## Solution

Define typed contracts for the core state and data models before building live integrations. These contracts should make graph state explicit, keep reviewer output separate from graph decisions, and preserve enough metadata for target binding, approval, redaction, and idempotency.

## User Stories

1. As a developer, I want a typed `ReviewState`, so that graph nodes cannot hide routing decisions in prompts.
2. As a developer, I want a typed `ReviewTarget`, so that every review is bound to a stable diff basis.
3. As a developer, I want reviewer config validation, so that invalid trigger fields fail early.
4. As a developer, I want raw reviewer findings separated from classified findings, so that reviewers cannot self-declare postability.
5. As a maintainer, I want approvals bound to final payload hashes, so that approved text cannot drift before posting.
6. As a maintainer, I want writer results modeled, so that retries can reconcile idempotently.
7. As a reviewer, I want local notes modeled, so that non-postable advice remains visible.
8. As a reviewer, I want clarification requests modeled, so that ambiguity can stop the graph safely.
9. As a developer, I want `ReviewerRunKey` and status models, so that resume/retry behavior is deterministic.
10. As a developer, I want `DiffAnchor` modeled separately from display location, so that future inline support has a safe path.
11. As a developer, I want risk assessment modeled as graph-owned state, so that risk-based reviewer routing is explainable and deterministic.

## Implementation Decisions

- `ReviewState` includes run ID, run mode, post-enabled flag, review target, posting target, read gaps, config hash, stage cursor, risk assessment, reviewer run status, context budget, redaction status, classified outputs, suggested replies, posting plan, actor/permission gate result, payload validation result, marker reconciliation result, finalization status, candidate/final payload contracts, final payload hash, approval, writer result, and errors.
- `ReviewTarget` includes owner/repo, PR number, base SHA, head SHA, merge-base SHA when available, and diff basis.
- `ReviewerRunKey` includes target hash, config hash, stage, reviewer name, attempt metadata, retry metadata, and clarification ID when applicable.
- Raw reviewer findings exclude graph-owned fields such as classification, blocking, final priority, fingerprint, and posting destination.
- Classified findings include graph-owned classification, priority integer, blocking flag, diff anchor, and fingerprint.
- `ApprovalDecision` stores approved item IDs, final payload hash, full review target or target hash, actor, timestamp, and public-verdict choice.
- `PostingPlan` stores destination per item: local only, top-level summary item, review body item, inline candidate, or suggested reply.
- `RiskAssessment` stores changed file count, changed line count, touched surfaces, labels, deterministic diff-pattern hints, configured thresholds, risk level, and traceable reasons.
- Fail-closed gate result models are graph-owned state, not helper-local booleans: `ReadGap`, `RedactionStatus`, `ActorPermissionGateResult`, `PayloadValidationResult`, `MarkerReconciliationResult`, and `FinalizationStatus`.
- MVP config supports `none` and `diff_context` capabilities; `read_repo`, `github_read`, and `run_tests` are later-phase capabilities.
- MVP config rejects `verdict_power: approve`.

## Testing Decisions

- Schema tests validate happy path and invalid enum values.
- Schema tests cover fail-closed gate result fields on `ReviewState`.
- Config tests reject unknown trigger fields, `triggers.stages`, unsupported capabilities, and `verdict_power: approve`.
- The shipped example config must validate.
- Raw reviewer output that attempts to claim postability/blocking must be ignored or downgraded by quality classification.
- Invalid priority values outside `0..3` must fail.

## Out of Scope

- Live adapter implementations.
- Prompt wording.
- Persistence beyond embedded GitHub markers and current-run writer result metadata.

## Further Notes

This PRD is a prerequisite for most other slices. Keep the models explicit and boring; their job is to make risky behavior impossible to smuggle through prompts.
