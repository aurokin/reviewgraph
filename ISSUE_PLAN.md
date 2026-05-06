# ISSUE PLAN: AUR-255 Complete PRD 0010 Agent Context And Adapter Boundaries

Active issue plan for `AUR-255` / `Complete PRD 0010: Agent Context And Adapter Boundaries`.

## Linear Snapshot

- Issue: `AUR-255`
- Status: `In Progress`
- Milestone: `PRD 0010: Agent Context And Adapter Boundaries`
- Gate requirement: close only after all implementation issues in this PRD milestone are complete.
- Current milestone issue set from fresh Linear fetch must be recorded in final gate evidence:
  - `AUR-231` / `RG-042: Define Reviewer Context Package`: `Done`; evidence comment present with comment ID, timestamp, current commit SHA, validation summary, and acceptance-criteria mapping.
  - `AUR-255` / `Complete PRD 0010: Agent Context And Adapter Boundaries`: active gate issue.
- Related search noise outside this milestone includes PRD 0003, PRD 0004, PRD 0005, PRD 0006, PRD 0007, PRD 0008, and PRD 0009 gate/issues. Gate validation must filter by `projectMilestone.id == 0dea2cdd-6433-41d8-b1a4-b91b07d3acc9`.

## Goal

Close PRD 0010 only if Linear and the repository prove the full milestone is complete, reviewed, documented, and side-effect safe.

This gate should not add product behavior unless the audit finds a durable documentation or harness gap. If docs change, update only the narrowest durable docs needed by future implementation agents.

## Prompt-To-Artifact Checklist

- Linear implementation issue complete:
  - `AUR-231` is `Done`.
  - `AUR-231` has a fresh evidence comment mapping each acceptance criterion to current code, tests, docs, validation, and the current commit SHA.
- Context package contract:
  - `src/reviewgraph/reviewer_context.py`
  - `tests/test_reviewer_context.py`
- Reviewer config and inert tools:
  - `src/reviewgraph/config.py`
  - `src/reviewgraph/models.py`
  - `tests/test_config.py`
  - `docs/decisions/0005-inert-reviewer-tool-metadata.md`
- Boundary proof:
  - `tests/test_contract_boundaries.py`
  - no reviewer-context import or field/signature access to writer, approval/finalization, GitHub transports, payload builders, provider clients, repository handles, or process handles.
- Passive memory and public payload proof:
  - `tests/test_reviewer_context.py`
  - `tests/test_render.py`
  - `tests/test_cli.py` conversation-pattern tests
- Non-live provider-bound proof:
  - provider preview builder in `src/reviewgraph/reviewer_context.py`
  - redaction and raw-provider/raw-trace defaults in focused tests
- Durable docs:
  - `docs/prds/0010-agent-context-and-adapter-boundaries.md`
  - `docs/architecture/reviewer-config.md`
  - `docs/architecture/state-graph.md`
  - `docs/harnesses/harness-engineering.md`
  - `docs/decisions/0005-inert-reviewer-tool-metadata.md`
- Linear ordering proof:
  - raw PRD 0010 Linear snapshot JSON derived from freshly fetched milestone/issue/comment/blocker data
  - temporary PRD 0010 backlog export derived as a lossless projection of the raw snapshot for all non-canceled milestone issues
  - `python scripts/check_docs.py --backlog-export <tmp-file>`
  - recorded raw snapshot hash, export hash, canonical raw/export rows, exact Linear query/API/tool used, and explicit drift/equality result

## Implementation Plan

1. Re-fetch PRD 0010 milestone, all non-canceled milestone issues, blockers, and comments from Linear.
   - Record fetch timestamp, exact Linear query/API/tool used, milestone ID/name, issue IDs/URLs/statuses/`completedAt`, blocker IDs, comment IDs/timestamps, and current repository commit SHA.
   - Fail closed if any non-gate PRD 0010 issue is not `Done`.
   - Fail closed if `AUR-231` lacks a current evidence comment that maps every acceptance criterion to current files/tests/docs/validation.
2. Write a temporary raw Linear snapshot JSON and derive a temporary canonical PRD 0010 backlog export from that raw snapshot only.
   - Raw snapshot schema must include milestone ID/name, fetch timestamp, issue ID/key/title/URL/status/`completedAt`, blocker issue keys/IDs/statuses/milestone IDs, and evidence comment ID/timestamp/body hash for implementation issues.
   - The export must include every non-canceled PRD 0010 issue from the raw snapshot; no hand-written issue omission or fabricated blocker relationship is allowed.
   - The export must preserve exact current Linear blocker relationships.
   - `AUR-255.blocked_by` must include `AUR-231` in Linear, not only in the derived export.
   - Fail closed on any outside-milestone unresolved blocker unless it is canceled, duplicate, explicitly marked stale/not-applicable with a comment ID, or resolved before gate close.
   - Record raw snapshot hash, export hash, canonical raw issue/blocker/comment rows, canonical export rows, and an explicit equality/drift check proving the export is a complete projection of the snapshot.
3. Run the backlog export checker and keep the temporary raw snapshot/export until final refetch, subagent review, and `AUR-255` evidence posting are complete:
   - `python scripts/check_docs.py --backlog-export <tmp-file>`
   - Remove the temporary raw snapshot/export only after the final Linear evidence comment is posted.
4. Run focused PRD 0010 harness:
   - `python -m pytest tests/test_reviewer_context.py tests/test_config.py tests/test_contract_boundaries.py`
5. Run routing/render/redaction regressions:
   - `python -m pytest tests/test_cli.py tests/test_context_budget.py tests/test_memory.py tests/test_tracer_fixture_run.py tests/test_render.py tests/test_redaction.py`
6. Run full validation:
   - `python -m pytest`
   - `python -m py_compile src/reviewgraph/*.py`
   - `python scripts/check_docs.py`
   - `git diff --check`
7. Run a static no-live-side-effect audit:
   - Update or verify AST/import boundary tests so `reviewgraph.reviewer_context` is included in transitive forbidden-module coverage.
   - Enumerate final boundary modules from the codebase before auditing: context/package, prompt/provider-preview, config/model metadata, and any reviewer-adapter boundary module added by this milestone.
   - Primary proof is deterministic AST/import/signature coverage for all enumerated boundary modules.
   - Supplemental audit command: `rg -n "github|openai|anthropic|requests|httpx|urllib|socket|subprocess|writer|approval|finalization|payload|client|repository|repo_handle|process" <enumerated-boundary-modules> tests/test_contract_boundaries.py`
   - acceptable grep matches are test assertions, inert metadata, and docstrings/comments that reinforce the boundary.
   - source modules must not import live GitHub, live LLM, network, writer, approval, or finalization clients through the reviewer context/prompt/provider boundary.
   - reviewer context/provider preview must remain non-live and client-free.
   - dry-run writer-unreachable tests must still pass.
8. Audit durable docs against PRD 0010 and AUR-231 evidence. Patch only durable gaps; if any file changes after validation, rerun relevant focused checks and full validation.
   - Required doc coverage: context package fields, prompt instruction/data separation, passive memory rules, inert tools, provider-preview redaction defaults, and forbidden adapter dependencies.
9. Use fresh subagent review of the raw Linear snapshot proof, backlog export equality proof, final validation results, side-effect audit, and docs. Iterate until material findings are gone.
10. Commit any gate/doc/test proof changes.
11. Re-run required validation after the final commit if commit contents changed the validated tree; then require `git status --short` to show a clean tree, except for retained ignored temporary proof artifacts.
12. Re-fetch the full PRD 0010 milestone inventory, statuses, blockers, comments/evidence, and `AUR-255` status immediately before closing. Compare that snapshot with the validated export and fail closed on drift.
13. Comment on `AUR-255` with final evidence including issue IDs, blocker IDs, evidence comment IDs, canonical raw/export rows, raw snapshot hash, export hash, exact Linear query/API/tool used, clean-tree status, current commit SHA, validation commands, docs audit, static audit, and subagent review result. Move `AUR-255` to `Done`.

## Out Of Scope

- No live GitHub reads or writes.
- No live LLM calls.
- No reviewer tool execution.
- No approval UI, finalization, or writer implementation.
- No `.ws/` recreation.

## Validation Evidence To Collect

- Fresh Linear milestone inventory and issue status snapshot.
- Raw snapshot hash, canonical raw snapshot rows, backlog export equality proof, backlog export check output, canonical export rows, and export hash.
- `AUR-231` evidence comment ID/timestamp and acceptance-criteria mapping from current commit.
- Focused PRD 0010 harness output.
- Routing/render/redaction regression output.
- Full validation output.
- Static no-live-side-effect audit output.
- Clean `git status --short` bound to the validated commit SHA.
- Subagent final no-findings result.
- Confirmation that `.ws/` is absent and no temporary export remains.
