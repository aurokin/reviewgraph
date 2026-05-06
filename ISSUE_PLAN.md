# ISSUE PLAN: AUR-254 Complete PRD 0003 Contracts

Active issue plan for `AUR-254` / `Complete PRD 0003: Contracts`.

## Linear Snapshot

- Issue: `AUR-254`
- Status at start: `In Progress`
- Milestone: `PRD 0003: Contracts`
- Gate requirement: close only after implementation issues in this milestone are complete.
- Blocking context: this gate blocks the first issues in the next PRD milestone.
- Gate comment requires: confirm issue completion/evidence, re-fetch Linear state, build prompt-to-artifact checklist, run focused and full validation, run Linear-derived backlog export check, audit durable docs, use fresh subagent review, and confirm no live side effects.

## Milestone Issue Status

- `AUR-312` / `RG-059: Define Core Contract Models And Schema Harness`: `Done`; evidence comment present.
- `AUR-192` / `RG-003: Parse Fixture PR With Review Target`: `Done`; evidence comment present.
- `AUR-237` / `RG-048: Add Core Redaction Service`: `Done`; evidence comment present.
- `AUR-211` / `RG-022: Enforce Context Budget And Truncation Notes`: `Done`; evidence comment present.
- `AUR-254` / `Complete PRD 0003: Contracts`: active gate issue.

## Goal

Close PRD 0003 only if the repository and Linear state prove the contract milestone is complete, ordered, reviewed, and side-effect safe.

This issue should not add product behavior unless the gate audit finds a durable documentation or harness gap. If docs change, update only the narrowest durable docs needed by future implementation agents.

## Prompt-To-Artifact Checklist

- Typed graph/state contracts: `src/reviewgraph/models.py`, `tests/test_models.py`, `tests/test_contract_boundaries.py`.
- Review target and fixture PR contracts: `src/reviewgraph/fixtures.py`, packaged fixture corpus, `tests/test_fixtures.py`, `tests/test_fixture_manifest.py`.
- Reviewer config validation: `src/reviewgraph/config.py`, `tests/test_config.py`, `examples/review_agents.example.yaml`.
- Raw vs classified reviewer output and quality downgrade proof: `src/reviewgraph/models.py`, `src/reviewgraph/runner.py`, `tests/test_models.py`, `tests/test_cli.py`, `tests/test_tracer_fixture_run.py`.
- Redaction service and status gates: `src/reviewgraph/redaction.py`, `src/reviewgraph/render.py`, `tests/test_redaction.py`, `tests/test_render.py`.
- Context budget and reviewer context package contracts: `src/reviewgraph/context_budget.py`, `src/reviewgraph/reviewer_context.py`, `tests/test_context_budget.py`.
- Durable docs: `docs/prds/0003-contracts.md`, `docs/architecture/state-graph.md`, `docs/architecture/findings-contract.md`, `docs/architecture/side-effects.md`, `docs/architecture/llm-data-handling.md`, `docs/architecture/review-quality.md`, `docs/architecture/reviewer-config.md`, `docs/harnesses/harness-engineering.md`, and `docs/implementation/README.md`.
- Linear ordering proof: temporary PRD 0003 backlog export derived from freshly fetched Linear milestone, issue, relationship, and comment data, then checked with `python scripts/check_docs.py --backlog-export <tmp-file>`.

## Implementation Plan

1. Re-fetch `AUR-312`, `AUR-192`, `AUR-237`, `AUR-211`, `AUR-254`, their comments, and the PRD 0003 milestone from Linear immediately before final validation.
2. Generate a temporary canonical Linear backlog export for PRD 0003 from the fetched state, using the actual direct blocker relationships rather than inferred transitive blockers:
   - Expected chain from the milestone plan: `AUR-312` -> `AUR-192` -> `AUR-237` -> `AUR-211` -> `AUR-254`.
   - If fetched Linear direct blockers differ from this chain, use the fetched direct blockers in the export and document the mismatch in the gate comment.
3. Run the backlog export checker and remove the temporary export afterward.
4. Run focused gate harnesses:
   - `python -m pytest tests/test_models.py tests/test_config.py tests/test_contract_boundaries.py tests/test_fixtures.py tests/test_fixture_manifest.py tests/test_redaction.py tests/test_context_budget.py`
   - Include side-effect guard harnesses in the focused command or as separate checks: `tests/test_posting.py`, `tests/test_render.py`, and dry-run/no-writer coverage in `tests/test_cli.py` and `tests/test_tracer_fixture_run.py`.
5. Run full validation:
   - `python -m pytest`
   - `python -m py_compile src/reviewgraph/*.py`
   - `python scripts/check_docs.py`
   - `git diff --check`
6. Run a static no-live-side-effect audit over the repo:
   - Search for live GitHub, LLM, approval, finalization, writer, network, and subprocess transport introductions.
   - Confirm contract/config/context modules still avoid importing writer, approval/finalization implementations, live LLM clients, or transport modules.
   - Confirm dry-run/no-writer behavior remains covered by tests.
7. Audit durable docs against PRD 0003 and the gate checklist, including `findings-contract`, `side-effects`, `llm-data-handling`, and `review-quality`. Patch only durable gaps.
8. Use fresh subagent review of the fetched Linear proof, backlog export, validation results, side-effect audit, and any doc changes. Iterate until material findings are gone.
9. Commit any gate/doc proof changes.
10. Comment on AUR-254 with evidence, mark it `Done`, and update the milestone if Linear supports a completion status for milestones.

## Out Of Scope

- No live GitHub reads or writes.
- No live LLM calls.
- No approval UI.
- No finalization/writer implementation.
- No `.ws/` or temporary planning tree recreation.

## Validation Evidence To Collect

- Linear issue statuses and evidence comments.
- Backlog export check output.
- Focused harness output.
- Full validation output.
- Static no-live-side-effect audit output.
- Subagent final no-findings result.
- Confirmation that `.ws/` is absent and no temporary export remains in the repo.
