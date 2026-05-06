# MILESTONE PLAN: PRD 0003 Contracts

Active execution artifact for this milestone. Linear remains the durable source for issue status, milestone order, blockers, and handoff details; if this file conflicts with Linear, Linear wins. Re-fetch current Linear state before starting each issue.

## Linear Scope Snapshot

- Milestone: `PRD 0003: Contracts`
- Milestone ID: `1a431524-5899-43e1-9dce-e626d8de8796`
- Current status: 0% complete when this plan was drafted.
- Implementation issues:
  - `AUR-192` / `RG-003: Parse Fixture PR With Review Target`
  - `AUR-211` / `RG-022: Enforce Context Budget And Truncation Notes`
  - `AUR-237` / `RG-048: Add Core Redaction Service`
- Gate issue: `AUR-254` / `Complete PRD 0003: Contracts`
- Issue comments: none on `AUR-192`, `AUR-211`, `AUR-237`, or `AUR-254` at plan time.

## Milestone Intent

PRD 0003 turns the PRD 0002 tracer's intentionally thin contracts into durable schemas and validation harnesses. The milestone should make fixture parsing, review target binding, context budgeting, truncation notes, and redaction explicit enough that later graph, memory, live LLM, live GitHub read, approval, and writer milestones cannot smuggle safety decisions through prompts or ad hoc dictionaries.

This milestone does not need live adapters, prompt wording, persistence, formal approval UI, or provider-specific LLM calls. It should preserve the current fixture dry-run behavior while hardening the contracts underneath it.

## Current Code Snapshot

- `src/reviewgraph/models.py` has a minimal dataclass surface for `ReviewTarget`, `DiffAnchor`, classified outputs, selected reviewers, memory references, truncation notices, and redaction status. It does not yet contain the full PRD 0003 `ReviewState`, `ReviewerRunKey`, raw reviewer output, risk, read-gap, approval, finalization, permission, marker reconciliation, or writer-result contracts.
- `src/reviewgraph/fixtures.py` can load packaged JSON fixtures, validate a small fixture shape, validate reviewer config fields, parse changed files/ranges, and produce `FixturePR` records. It does not yet provide the required fixture corpus, target hash helpers, manifest consumption validation, PR metadata/comments/reviews/thread schemas, or typed `ReviewTarget` parsing.
- `src/reviewgraph/redaction.py` has deterministic regex redaction for private keys, authorization headers, bearer tokens, GitHub tokens, API-key-like assignments, `.env` assignments, and standalone key shapes. Coverage is currently exercised through tracer/render tests, not a dedicated redaction harness across all required surfaces.
- `src/reviewgraph/runner.py` owns a fixture-only dry-run shell. It should keep using fixture/fake data, but PRD 0003 work should move reusable contracts into focused modules instead of expanding runner-local policy.
- `src/reviewgraph/fixtures_data/manifest.json` contains only the PRD 0002 tracer fixtures: `basic-pr`, `specialized-review-pr`, and `ambiguous-logic-pr`. Harness engineering requires the broader corpus names before later milestones build on them.
- Current default tests prove the PRD 0002 slice. PRD 0003 should add focused harnesses instead of relying on tracer tests as proxy evidence.

## Execution Order

1. `AUR-192` first: fixture schema and immutable review target parsing are the foundation for the rest of this milestone. Add the required manifest scenarios, typed fixture PR context, stable target hash behavior, invalid-shape errors, and manifest consumption validation.
2. `AUR-211` second: context budgets depend on parsed changed files, patches, conversation memory, and fixture corpus entries. Add explicit budget models, deterministic truncation/defer decisions, omitted-context markers, and structured local-note candidates.
3. `AUR-237` third: redaction already exists, but it needs a focused service contract and harness coverage over fixture text, logs/traces/error payloads, rendered output, candidate/final payload text, and future provider-bound request text. Tie redaction status into state-facing contracts before payload validation.
4. `AUR-254` last: complete the milestone audit only after all implementation issues are `Done`, docs are refactored for PRD 0003 drift, default validation is green, Linear-derived backlog validation is green, and fresh subagent review reports no material issues.

## Issue Workflow

For each implementation issue:

1. Re-fetch the issue, its comments, and current related milestone state from Linear.
2. Move the issue to `In Progress`.
3. Replace `ISSUE_PLAN.md` with a narrow plan for that issue and commit it before implementation.
4. Use fresh subagents to review the issue plan before code changes.
5. Implement the smallest contract/harness slice that satisfies the issue and does not implement later milestone scope.
6. Run the issue harness named by Linear, plus any broader tests that cover touched shared behavior.
7. Use fresh subagents for code/docs review until no material findings remain.
8. Commit the completed issue, and commit separately after every review-fix batch.
9. Move the issue to `In Review`, add a Linear evidence comment with commands and artifact coverage, then move it to `Done` only when the issue acceptance criteria are mapped to concrete evidence.

## Harness Strategy

- `AUR-192` harness target: `python -m pytest tests/test_fixtures.py`
- `AUR-211` harness target: `python -m pytest tests/test_context_budget.py`
- `AUR-237` harness target: `python -m pytest tests/test_redaction.py`
- Regression target after each issue: run affected existing tests plus `python -m pytest` when shared contracts change.
- Documentation target after each behavior/doc shift: `python scripts/check_docs.py`
- Backlog target at gate: export the Linear-derived PRD 0003 order and run `python scripts/check_docs.py --backlog-export <tmp-file>`.

## Contract Guardrails

- Preserve dry-run by default. No PRD 0003 work should introduce live GitHub reads, live LLM calls, approval prompts, or writer reachability.
- Keep GitHub writes behind later side-effect gates. Fixture parsing, context budgeting, and redaction may prepare state, but must not call or import writer code.
- Keep reviewer output separated from graph-owned decisions. Raw reviewer contracts may propose issues; classified findings, postability, final priority, blocking, fingerprints, and destinations remain graph-owned.
- Keep `ReviewTarget` immutable and hashable from owner/repo, PR number, base SHA, head SHA, merge-base SHA, and diff basis. Hashes must change when base/head/diff basis changes.
- Keep untrusted PR comments passive. They may exist in fixture memory, but must not select reviewers, satisfy evidence, influence verdicts, approve posting, or enter public payload text in MVP.
- Redact secret-like content before rendering, tracing, errors, payload validation, future provider-bound requests, and public payload generation. Raw-content tracing or raw provider submission must remain opt-in and off by default.
- Do not couple reviewer prompts or context packages to GitHub transport or side-effect modules.

## Documentation Work

Update the narrowest durable docs alongside behavior:

- Fixture schema, manifest expectations, target hashing, and fixture corpus guidance belong in `docs/harnesses/harness-engineering.md`, `docs/plans/implementation-plan.md`, or a focused architecture doc if the contract needs one.
- State, gate, raw reviewer, approval, and writer-result schema decisions belong in `docs/architecture/state-graph.md`, `docs/architecture/findings-contract.md`, `docs/architecture/side-effects.md`, or a new ADR if the decision constrains future implementation.
- Redaction and live-data handling belong in `docs/architecture/llm-data-handling.md` and any relevant harness guidance.
- Do not copy the full Linear issue tree into repo docs. Keep Linear as the executable backlog and docs as progressive-disclosure contracts.

## Milestone Completion Criteria

PRD 0003 is complete when:

- `AUR-192`, `AUR-211`, and `AUR-237` are `Done` in Linear with evidence comments.
- `AUR-254` is `Done` only after the final gate audit.
- `MILESTONE_PLAN.md` and the historical committed `ISSUE_PLAN.md` versions document the plan used for each issue.
- Focused harnesses exist and pass for fixtures, context budget, and redaction.
- The full default test suite passes.
- `python scripts/check_docs.py`, `git diff --check`, and a PRD 0003 Linear-derived backlog export check pass.
- Documentation has been audited and refactored for the PRD 0003 contracts an implementation agent needs when dropping into the repo.
- Fresh subagent review of the final code/docs reports no material issues.
- No unapproved live API, live LLM, approval, or GitHub writer behavior has been introduced.
