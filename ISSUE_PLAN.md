# ISSUE PLAN: AUR-258 Complete PRD 0002 MVP Tracer Bullet

Historical execution artifact for this issue. Linear remains the durable source for issue status, blockers, and handoff details; if this file conflicts with Linear, Linear wins. Fetch current state from Linear before acting on this plan.

## Linear issue snapshot

- Issue: `AUR-258` / `Complete PRD 0002: MVP Tracer Bullet`
- Milestone: `PRD 0002: MVP Tracer Bullet`
- Status at planning: `In Progress`
- Gate rule: close only after all implementation issues in this PRD milestone are complete.

## Read evidence

- Milestone read: `PRD 0002: MVP Tracer Bullet`
- Linked implementation issues read: `AUR-208`, `AUR-209`, `AUR-210`, `AUR-238`
- Gate issue read: `AUR-258`
- Issue comments read:
  - `AUR-208`: implementation and final review/validation comments
  - `AUR-209`: implementation and final review/validation comments
  - `AUR-210`: start, implementation, and final review/validation comments
  - `AUR-238`: implementation and final acceptance comments
  - `AUR-258`: no prior comments before starting gate work
- Repo docs read:
  - `README.md`
  - `docs/product/vision.md`
  - `docs/product/rules.md`
  - `docs/architecture/overview.md`
  - `docs/architecture/state-graph.md`
  - `docs/harnesses/harness-engineering.md`
  - `docs/plans/implementation-plan.md`
  - `docs/prds/README.md`
  - `docs/implementation/README.md`
- Code and harness surfaces read:
  - `src/reviewgraph/fixtures.py`
  - `src/reviewgraph/runner.py`
  - `src/reviewgraph/cli.py`
  - `src/reviewgraph/posting.py`
  - `src/reviewgraph/render.py`
  - `src/reviewgraph/models.py`
  - `tests/test_posting.py`
  - `tests/test_render.py`
  - `tests/test_cli.py`
  - `tests/test_tracer_fixture_run.py`

## Acceptance criteria mapping

1. All implementation issues in PRD 0002 are complete.
   - Evidence target: Linear statuses for `AUR-208`, `AUR-209`, `AUR-210`, and `AUR-238` are `Done`.
2. The gate does not hide missing milestone requirements behind issue status alone.
   - Evidence target: run a prompt-to-artifact audit mapping PRD 0002 and issue acceptance criteria to concrete tests, code, comments, and docs.
3. The tracer demo remains runnable and credential-free.
   - Evidence target: `python -m pytest tests/test_tracer_fixture_run.py`, `python -m pytest tests/test_cli.py`, and a direct CLI smoke command.
4. The dry-run side-effect boundary remains proven.
   - Evidence target: tracer and CLI tests assert zero writer calls; code read confirms fixture dry-run does not call the writer sentinel.
5. The Linear-derived milestone queue is validated.
   - Evidence target: create a temporary canonical backlog export for PRD 0002 and run `python scripts/check_docs.py --backlog-export <export>`.
6. Default repo validation passes.
   - Evidence target: `python -m pytest`, `python -m py_compile src/reviewgraph/*.py`, `python scripts/check_docs.py`, and `git diff --check`.
7. Milestone-end documentation audit is performed.
   - Evidence target: compare PRD 0002 implementation against docs and update the narrowest durable docs where agents would otherwise be misled. Known candidate: `README.md` still says "Scaffold-only. No runtime implementation exists yet."
8. Fresh subagents review the plan before gate work and review the final gate/doc changes before Done.
   - Evidence target: plan-review and code/docs-review subagent summaries show no material blockers.

## Scope

This issue is a milestone gate and documentation-audit issue, not a new product feature. It owns:

- verifying PRD 0002 completion against Linear, tests, code, and docs;
- closing documentation drift caused by the tracer implementation;
- committing the gate audit and any narrow durable doc refactor required by the milestone;
- moving `AUR-258` to `Done` only after validation and fresh review are clean.

Likely files:

- Modify: `ISSUE_PLAN.md`
- Modify: `MILESTONE_PLAN.md`
- Likely modify: `README.md`
- Possibly modify: `docs/README.md`, `docs/harnesses/harness-engineering.md`, or `docs/plans/implementation-plan.md` only if the audit finds durable agent-facing drift.

## Completion audit checklist

- Linear:
  - `AUR-208` is `Done`.
  - `AUR-209` is `Done`.
  - `AUR-210` is `Done`.
  - `AUR-238` is `Done`.
  - `AUR-258` is moved through `In Progress`, `In Review`, and `Done`.
- Planning:
  - `MILESTONE_PLAN.md` reflects current gate/audit status.
  - `ISSUE_PLAN.md` reflects the AUR-258 gate plan.
  - Planning files are committed before implementation/audit changes.
- Harness evidence:
  - `tests/test_posting.py` proves posting-plan destinations, MVP issue-comment payloads, hash domains, and pure builders.
  - `tests/test_render.py` proves markdown/JSON rendering, redaction, candidate payload binding, and untrusted-memory exclusion.
  - `tests/test_cli.py` proves fixture dry-run CLI behavior, deterministic JSON, redacted errors/output, invalid inputs, and writer non-reachability.
  - `tests/test_tracer_fixture_run.py` proves the full PRD 0002 fixture tracer path and selected golden fields.
- Commands:
  - `python -m pytest tests/test_tracer_fixture_run.py`
  - `python -m pytest tests/test_cli.py tests/test_render.py tests/test_posting.py`
  - `python -m pytest`
  - `python -m py_compile src/reviewgraph/*.py`
  - `python scripts/check_docs.py`
  - `python scripts/check_docs.py --backlog-export <temporary-prd0002-export.json>`
  - `git diff --check`
  - CLI smoke: `python -m reviewgraph.cli --fixture-pr basic-pr --print-markdown`
- Documentation:
  - user-facing README does not falsely claim there is no runtime implementation.
  - docs keep Linear as executable backlog and avoid copying the full issue tree.
  - any new behavior note is placed in the narrowest durable doc.

## Implementation plan

1. Commit this AUR-258 plan plus current milestone-plan update.
2. Run fresh plan-review subagents against `ISSUE_PLAN.md`, `MILESTONE_PLAN.md`, Linear PRD 0002 data, and the current code/docs.
3. Resolve any material plan-review findings and commit those changes.
4. Build a temporary canonical PRD 0002 backlog export from Linear issue data and validate it with `scripts/check_docs.py`.
5. Run focused and full harness validation.
6. Perform the milestone documentation audit:
   - update `README.md` repository status and quick demo instructions;
   - update only additional durable docs if the audit finds agent-facing drift.
7. Commit documentation/audit changes.
8. Move `AUR-258` to `In Review` and add a Linear comment with the audit and validation evidence.
9. Run fresh code/docs-review subagents until no material findings remain.
10. Commit after each review-fix cycle.
11. Move `AUR-258` to `Done` only after validation and fresh review are clean.
12. Continue to the next Linear milestone; do not push again until the active goal's push gate is satisfied.

## Out of scope

- No new runtime behavior unless the audit exposes a direct gate blocker.
- No live GitHub read, live LLM, approval, or writer implementation.
- No broad docs rewrite for later PRDs; the full progressive-disclosure docs refactor happens after each milestone is complete, and this gate should update only PRD 0002 drift.
- No mirroring the full Linear backlog into repository docs.
- No push for this gate work.

## Review approach

- Use fresh plan-review subagents before gate/audit work.
- Close plan-review agents before opening final code/docs-review agents.
- Treat reviewer findings as blockers unless they are explicitly non-issues after evidence review.
- Keep Linear comments high signal: plan start, in-review validation, and final Done evidence.
