# ISSUE PLAN: AUR-254 Complete PRD 0003 Contracts

Active issue plan for `AUR-254` / `Complete PRD 0003: Contracts`.

## Linear Snapshot

- Issue: `AUR-254`
- Status: `In Progress`
- Milestone: `PRD 0003: Contracts`
- Gate requirement: close only after all implementation issues in this PRD milestone are complete.
- Gate comment requires issue evidence, focused harnesses, full validation, backlog export validation, docs audit, fresh subagent review, and no live side effects.

## Full Milestone Issue Set

Fresh Linear audit expanded the gate scope beyond the reduced issue list:

- `AUR-190` / `RG-001: Project Skeleton And Empty Test Harness`: `Done`; evidence comment present.
- `AUR-191` / `RG-002: Validate Example Reviewer Config`: `Done`; verified as stale blocker; evidence comment present.
- `AUR-230` / `RG-041: Seed Fixture Corpus Manifest`: `Done`; evidence comment present.
- `AUR-312` / `RG-059: Define Core Contract Models And Schema Harness`: `Done`; evidence comment present.
- `AUR-192` / `RG-003: Parse Fixture PR With Review Target`: `Done`; evidence comment present.
- `AUR-193` / `RG-004: Build Trusted Conversation Memory`: `Done`; evidence comment present.
- `AUR-237` / `RG-048: Add Core Redaction Service`: `Done`; evidence comment present.
- `AUR-234` / `RG-045: Add Minimal Context Budget Before Fanout`: `Done`; verified as stale blocker; evidence comment present.
- `AUR-211` / `RG-022: Enforce Context Budget And Truncation Notes`: `Done`; evidence comment present.
- `AUR-254` / `Complete PRD 0003: Contracts`: active gate issue.

## Goal

Close PRD 0003 only if the repository and Linear state prove the full contract milestone is complete, ordered, reviewed, and side-effect safe.

This issue should not add product behavior unless the gate audit finds a durable documentation or harness gap. If docs change, update only the narrowest durable docs needed by future implementation agents.

## Prompt-To-Artifact Checklist

- Package skeleton and default harness: `pyproject.toml`, `src/reviewgraph/__init__.py`, `python -m pytest`.
- Reviewer config validation: `src/reviewgraph/config.py`, `examples/review_agents.example.yaml`, `tests/test_config.py`.
- Fixture corpus manifest and schema-valid fixture PRs: `src/reviewgraph/fixtures_data/manifest.json`, packaged fixtures, `tests/test_fixture_manifest.py`, `tests/test_fixtures.py`.
- Typed graph/state contracts: `src/reviewgraph/models.py`, `tests/test_models.py`, `tests/test_contract_boundaries.py`.
- Review target and fixture PR contracts: `src/reviewgraph/fixtures.py`, `ReviewTarget` hashing tests, `tests/test_fixtures.py`.
- Trusted/passive conversation memory: `src/reviewgraph/memory.py`, `tests/test_memory.py`.
- Raw vs classified reviewer output and quality downgrade proof: `src/reviewgraph/models.py`, `src/reviewgraph/runner.py`, `tests/test_models.py`, `tests/test_cli.py`, `tests/test_tracer_fixture_run.py`.
- Redaction service and status gates: `src/reviewgraph/redaction.py`, `src/reviewgraph/render.py`, `tests/test_redaction.py`, `tests/test_render.py`.
- Context budget and reviewer context package contracts: `src/reviewgraph/context_budget.py`, `src/reviewgraph/reviewer_context.py`, `tests/test_context_budget.py`.
- Durable docs: `docs/prds/0003-contracts.md`, `docs/architecture/state-graph.md`, `docs/architecture/findings-contract.md`, `docs/architecture/side-effects.md`, `docs/architecture/llm-data-handling.md`, `docs/architecture/review-quality.md`, `docs/architecture/reviewer-config.md`, `docs/harnesses/harness-engineering.md`, and `docs/implementation/README.md`.
- Linear ordering proof: temporary PRD 0003 backlog export derived from freshly fetched Linear milestone, issue, relationship, and comment data, checked with `python scripts/check_docs.py --backlog-export <tmp-file>`.

## Implementation Plan

1. Re-fetch all PRD 0003 issues, comments, and the milestone from Linear immediately before final validation.
2. Generate a temporary canonical backlog export from fetched Linear data. Include all active PRD 0003 issues in dependency order. Filter `blocked_by` to blockers inside the exported PRD 0003 issue set and separately document any external blockers/status in the gate evidence.
   - Fail closed if any external blocker is active or unresolved unless there is a recorded Linear rationale that the blocker is stale, canceled, or not applicable to this milestone gate.
3. Run the backlog export checker and remove the temporary export afterward:
   - `python scripts/check_docs.py --backlog-export <tmp-file>`
4. Run focused gate harnesses:
   - `python -m pytest tests/test_models.py tests/test_config.py tests/test_contract_boundaries.py tests/test_fixture_manifest.py tests/test_fixtures.py tests/test_memory.py tests/test_redaction.py tests/test_context_budget.py`
5. Run side-effect guard harnesses:
   - `python -m pytest tests/test_posting.py tests/test_render.py tests/test_cli.py tests/test_tracer_fixture_run.py`
6. Run full validation:
   - `python -m pytest`
   - `python -m py_compile src/reviewgraph/*.py`
   - `python scripts/check_docs.py`
   - `git diff --check`
7. Run a static no-live-side-effect audit over the repo:
   - Search for live GitHub, LLM, approval, finalization, writer, network, and subprocess transport introductions.
   - Confirm contract/config/context modules still avoid importing writer, approval/finalization implementations, live LLM clients, or transport modules.
   - Confirm dry-run/no-writer behavior remains covered by tests.
8. Audit durable docs against PRD 0003 and the full issue set. Patch only durable gaps.
9. If any file changes after step 6, rerun the relevant focused checks plus the full final validation from step 6 after the last edit.
10. Use fresh subagent review of the fetched Linear proof, backlog export, final validation results, side-effect audit, and any doc changes. Iterate until material findings are gone.
11. If subagent review causes any file change, repeat steps 6, 9, and 10 until the final file state has green validation and no material review findings.
12. Commit any gate/doc proof changes.
13. Re-fetch the PRD 0003 milestone and all `AUR-254` blockers immediately before closing; fail closed if any blocker status or external-blocker rationale drifted.
14. Comment on `AUR-254` with evidence, mark it `Done`, and update the milestone if Linear supports a completion status for milestones.

## Out Of Scope

- No live GitHub reads or writes.
- No live LLM calls.
- No approval UI.
- No finalization/writer implementation.
- No `.ws/` or temporary planning tree recreation.

## Validation Evidence To Collect

- Full Linear issue status/comment snapshot.
- Backlog export check output and note about any external blockers filtered out.
- Focused harness output.
- Side-effect guard harness output.
- Full validation output.
- Static no-live-side-effect audit output.
- Subagent final no-findings result.
- Confirmation that `.ws/` is absent and no temporary export remains in the repo.
