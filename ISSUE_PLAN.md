# ISSUE PLAN: AUR-257 Complete PRD 0005 Review Quality

Active issue plan for `AUR-257` / `Complete PRD 0005: Review Quality`.

Linear remains the source of truth for issue state and relationships.

## Linear Snapshot

- Issue: `AUR-257`
- Status at plan time: `In Progress`
- Milestone: `PRD 0005: Review Quality`
- Title: `Complete PRD 0005: Review Quality`
- Gate rule: close only after all implementation issues in the PRD milestone are complete.

## Intent

Close PRD 0005 only after proving the review-quality milestone is complete in code, tests, Linear evidence, and durable documentation.

This is a milestone gate, not a new feature slice. The work should focus on completion audit, progressive-disclosure docs refactor, final validation, fresh review, and Linear closure.

## Current Baseline

- All PRD 0005 implementation issues are `Done` in Linear:
  - `AUR-201` normalize reviewer output;
  - `AUR-227` repair or record malformed reviewer JSON;
  - `AUR-202` classify review quality;
  - `AUR-204` validate diff anchors for inline candidates;
  - `AUR-203` classify testing feedback quality;
  - `AUR-205` stop for clarification requests;
  - `AUR-206` resume from clarification answers;
  - `AUR-226` continue after optional reviewer failure;
  - `AUR-207` compute local verdict.
- Each completed issue has a Linear evidence comment with commits, focused harnesses, regression validation, and review status.
- No `.ws/` tree is present.
- Current local branch is ahead of `origin/main`; do not push until this gate and documentation work are complete.
- Durable docs have PRD 0005 content spread across README, findings contract, review quality, state graph, harness engineering, implementation plan, and ADR 0007. README still under-describes PRD 0005 as part of the current runnable slice.

## Decisions

1. Treat Linear issue evidence as milestone input, but do not copy the full issue tree into durable docs.
2. Refactor docs for progressive disclosure:
   - README tells a drop-in agent what exists now and where to start.
   - Architecture docs hold durable contracts and behavioral boundaries.
   - Harness docs hold focused test families and validation commands.
   - PRDs stay product-scope artifacts, not implementation changelogs.
   - ADRs capture durable tradeoffs future agents might reopen.
3. Keep docs concrete for implementation agents: name the modules, state fields, harnesses, and boundaries they must preserve.
4. Do not introduce live GitHub, live LLM, approval, writer, semantic dedupe, or inline posting scope during the docs pass.

## Implementation Plan

1. Perform milestone completion audit.
   - Reconfirm every PRD 0005 implementation issue is `Done`.
   - Reconfirm each issue has an evidence comment.
   - Reconfirm no temporary `.ws/` artifacts remain.
   - Reconfirm local validation and current git state.

2. Refactor durable docs in narrow commits.
   - Update README current runnable slice/repository status for PRD 0005.
   - Tighten `docs/architecture/review-quality.md` around normalization -> repair -> classification -> local verdict.
   - Tighten `docs/architecture/findings-contract.md` only where schema/partial-review/verdict details need better agent handoff.
   - Tighten `docs/architecture/state-graph.md` only for clarification stop/resume, reviewer failure, and verdict boundaries if needed.
   - Tighten `docs/harnesses/harness-engineering.md` so PRD 0005 focused harnesses are discoverable.
   - Add an ADR only if the final review finds a durable tradeoff not already covered by ADR 0007.

3. Run validation.
   - Focused PRD 0005 harness family.
   - Broader tracer/reviewer/failure/boundary regressions.
   - Full pytest, py-compile, docs check, and diff check.

4. Use fresh subagents for milestone review.
   - Review code/tests/docs/Linear evidence against PRD 0005 acceptance.
   - Fix all material findings and commit after each review-fix batch.

5. Rerun final validation after the last review-fix batch.
   - Focused PRD 0005 harness family.
   - Full pytest.
   - Py-compile, docs check, and diff check.

6. Close Linear gate and push only after the audit is clean.
   - Add AUR-257 evidence comment with checklist and validation commands.
   - Move AUR-257 to `In Review`, then `Done`.
   - Push the completed local commits.

## Verification

- Focused PRD 0005 harnesses:
  - `python -m pytest tests/test_findings.py tests/test_reviewer_json_repair.py tests/test_quality.py tests/test_diff_anchor.py tests/test_quality_testing.py tests/test_clarification.py tests/test_clarification_resume.py tests/test_optional_reviewer_failure.py tests/test_verdict.py -q`
- Regression harnesses:
  - `python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py tests/test_render.py -q`
  - `python -m pytest tests/test_reviewers_fake.py tests/test_required_reviewer_failure.py tests/test_reviewer_runs.py -q`
  - `python -m pytest tests/test_reviewer_context.py tests/test_contract_boundaries.py tests/test_context_budget.py tests/test_prompt_injection_memory.py tests/test_redaction.py -q`
- Full/hygiene:
  - `python -m pytest -q`
  - `python -m py_compile src/reviewgraph/*.py && python scripts/check_docs.py && git diff --check`

## Out Of Scope

- New review-quality behavior beyond doc corrections required by the audit.
- Live GitHub reads.
- Live LLM reviewers.
- Approval/finalization/writer behavior.
- Semantic deduplication.
- Inline GitHub posting.
