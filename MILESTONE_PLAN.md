# MILESTONE PLAN: PRD 0002 MVP Tracer Bullet

Historical execution artifact for this milestone. Linear remains the durable source for issue status, milestone order, blockers, and handoff details; if this file conflicts with Linear, Linear wins. Fetch current milestone state from Linear before acting on this plan.

## Linear scope snapshot

- Milestone: `PRD 0002: MVP Tracer Bullet`
- Implementation issues:
  - `AUR-208` / `RG-019: Build Posting Plan For Dry Run`
  - `AUR-209` / `RG-020: Render Redacted Markdown And JSON`
  - `AUR-210` / `RG-021: Add Fixture Dry-Run CLI`
  - `AUR-238` / `RG-049: Add Fixture Tracer Bullet Golden Run`
- Gate issue: `AUR-258` / `Complete PRD 0002: MVP Tracer Bullet`

## Current gate snapshot

As of the AUR-258 gate plan:

- `AUR-208`, `AUR-209`, `AUR-210`, and `AUR-238` are `Done` in Linear.
- `AUR-258` is `In Progress` and owns the final PRD 0002 completion audit.
- The local repository is clean on `main` at `208b0d5`.
- The public GitHub repository exists at `https://github.com/aurokin/reviewgraph`; no further push should happen for gate work until the active goal's push condition is satisfied.
- Known documentation drift to audit: `README.md` still describes the repo as scaffold-only even though PRD 0002 has added a runnable fixture dry-run CLI and tracer harness.
- Known coverage gap to audit: PRD 0002 asks for normal, specialized-review, and ambiguous logic fixture graph tests. The current committed tracer baseline proves the normal `basic-pr` path; AUR-258 must add the missing fixture graph proofs or record an explicit durable deferment with follow-up Linear scope before closing.

## Milestone intent

PRD 0002 should produce the first runnable ReviewGraph demo without live GitHub reads, live LLM calls, approval, or writers. The tracer path is:

```text
fixture PR
  -> conversation memory
  -> review target
  -> context budget
  -> staged reviewer selection
  -> fake reviewer outputs
  -> quality classification
  -> local verdict
  -> dry-run posting plan
  -> markdown and JSON output
  -> no writer reachable
```

## Sequencing risk

The durable PRD index says the MVP tracer bullet depends on contracts, fake adapters, a graph shell, review quality classification, and rendering. Several of those concerns have later PRD milestones. For this milestone, implement the smallest executable contract needed to make the tracer bullet real, and leave later PRDs to harden, expand, and live-integrate those surfaces.

Do not turn PRD 0002 into the full product. A thin but honest vertical slice is better than broad policy completeness.

The hidden-foundation work must be owned explicitly instead of being smuggled into the final golden test:

- `AUR-208` may create the Python skeleton, placeholder pytest harness, minimal shared models, redaction primitive, posting-plan destinations, candidate payload metadata, and a side-effect sentinel port needed to prove dry-run writer unreachability.
- `AUR-209` may create the renderer and secret-like fixture assertions for markdown, JSON, and candidate payload previews.
- `AUR-210` may create the minimal fixture runner/graph shell, fixture reference parsing, and a minimal fixture-specific reviewer config path.
- `AUR-238` should integrate and harden the already-existing foundations. It should not be the first owner of graph shell, fake reviewer output, normalization, quality classification, local verdict, or render behavior.

Later PRDs still own full schema completeness, full config validation, rich graph orchestration, fake/live adapter hardening, clarification resume, live reads, approval, and writers.

## Pre-implementation evidence snapshot

- The repository currently has documentation and examples only; there is no `pyproject.toml`, package skeleton, runtime graph, or pytest suite.
- `docs/prds/0002-mvp-tracer-bullet.md` requires fixture-only execution, deterministic fake reviewers, explicit dry-run mode, staged routing evidence, quality-classified output, markdown/JSON rendering, and no writer reachability.
- `docs/architecture/state-graph.md` defines the durable state fields and stage cursor semantics. This milestone may implement a minimal subset, but it must not contradict those names or routing boundaries.
- `docs/architecture/findings-contract.md`, `docs/architecture/review-quality.md`, and `docs/architecture/side-effects.md` define output classes, postability rules, local notes, suggested replies, and dry-run posting destinations.
- `examples/review_agents.example.yaml` exists but selects more than one always-on reviewer. PRD 0002 may add a narrower fixture config for the baseline golden run; the full example should remain a later config-validation target unless the issue explicitly needs it.

## Implementation strategy

1. Re-fetch every PRD 0002 issue and the gate from Linear before starting each issue. Move each issue through `In Progress`, `In Review`, and `Done` as work advances.
2. Treat `AUR-208` as the first implementation issue because it can bootstrap the runtime surface and define posting-plan destinations, target metadata, finding IDs, hashes, redaction hooks, and the writer sentinel consumed by later issues.
3. Implement `AUR-209` after posting-plan models exist, keeping rendering deterministic and redacted. Markdown golden checks should compare meaningful sections, not every incidental word. Redaction tests must include token-like external PR text and verify markdown, JSON, and public payload preview fields.
4. Implement `AUR-210` after render output exists. The CLI should accept fixture references, default to dry-run, emit markdown and JSON, use a minimal baseline fixture config, and fail closed for invalid fixture/config input.
5. Implement `AUR-238` last as the milestone integration proof. It should assert the full fixture run covers the tracer path, includes clarification-request output at least as a classified/rendered item, and proves the dry-run graph cannot invoke the writer sentinel.
6. When a missing foundation is unavoidable, add the narrowest package/module support needed by the current issue and mark the future-hardening boundary in tests or docs. Do not silently implement later PRD scope.
7. Use fixture data and deterministic fake reviewer results only. No network credentials, live LLM calls, live GitHub reads, approvals, or real writer adapters.
8. After each issue implementation, run the issue harness plus the relevant broader test set, use fresh subagents for review until no material issues remain, commit, and update Linear with the exact harness evidence.
9. Before closing `AUR-258`, re-check milestone membership in Linear, validate a Linear-derived backlog export with `python scripts/check_docs.py --backlog-export ...`, run the full default validation suite, and perform the milestone-end documentation audit required by the active goal.

## Non-goals

- No live GitHub read adapter.
- No live LLM adapter.
- No real GitHub writer, approval storage, formal PR review payload, inline posting, or request-changes submission. A no-op/sentinel writer port is allowed only so tests can prove dry-run writer unreachability.
- No semantic deduplication.
- No full repository checkout or test execution of reviewed PRs.
- No local mirror of the Linear issue tree.
- No push until the larger active goal permits pushing.

## Validation target

The milestone is complete when:

- `AUR-208`, `AUR-209`, `AUR-210`, and `AUR-238` are done in Linear.
- `AUR-258` is done in Linear after the gate audit.
- The repo has a runnable fixture dry-run path that produces markdown and JSON without credentials.
- Tests prove the run includes selected reviewer reasons, memory IDs, target metadata, classified findings, local notes, clarification requests, suppressed counts, local verdict, posting plan, redacted markdown/JSON/payload previews, and writer-sentinel-unreachable dry-run behavior.
- Default local validation passes, including `python scripts/check_docs.py`, a Linear-derived backlog export check with `python scripts/check_docs.py --backlog-export ...`, the pytest suite added by this milestone, and `git diff --check`.
- The milestone-end documentation audit finds no missing durable PRD 0002 guidance for future implementation agents.

## Gate audit plan

`AUR-258` closes this milestone by proving the plan above against current artifacts:

1. Re-fetch PRD 0002 milestone state and linked issue comments from Linear.
2. Build a prompt-to-artifact checklist from PRD 0002, `AUR-208`, `AUR-209`, `AUR-210`, and `AUR-238`.
3. Map each checklist item to concrete evidence in tests, code, docs, or Linear comments.
4. Prove or explicitly defer each PRD 0002 testing decision, including specialized-review and ambiguous logic fixture graph tests.
5. Run focused tracer/CLI/render/posting harnesses plus full default validation.
6. Validate a temporary Linear-derived PRD 0002 backlog export with `scripts/check_docs.py --backlog-export` and preserve summary evidence in a Linear comment.
7. Update the narrowest durable docs for PRD 0002 drift, especially any agent-facing startup docs that still say there is no implementation or blur current fixture-only runtime with future LangGraph/live behavior.
8. Use fresh subagents for plan review and final code/docs review.
9. Move `AUR-258` to `Done` only after the audit has no missing, incomplete, weakly verified, or uncovered requirement.
