# ISSUE PLAN: AUR-261 Complete PRD 0007 Side Effects

Active issue plan for `AUR-261` / `Complete PRD 0007: Side Effects`.

Linear is the durable source for milestone issue status, blockers, and completion evidence. Repository docs are the durable product, architecture, harness, and decision contracts. This gate must not add new side-effect scope; it audits PRD 0007, fixes documentation gaps, and closes the milestone only when evidence is complete.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-261`
- Status when planned: `In Progress`
- Active implementation issues currently fetched from Linear as `Done`: `AUR-244`, `AUR-218`, `AUR-217`, `AUR-219`, `AUR-243`, `AUR-220`, `AUR-221`, `AUR-245`, `AUR-246`, `AUR-223`, `AUR-222`, `AUR-241`, and `AUR-224`.
- Gate issue currently active: `AUR-261`.
- Known canceled duplicates currently fetched from Linear as `Duplicate`: `AUR-248`, `AUR-249`, `AUR-250`, and `AUR-251`.
- Current repo state at planning: clean working tree on `main`, ahead of `origin/main` by 19 commits before the planning commit and 20 commits after it, with no `.ws/` directory found by `find . -maxdepth 2 -type d -name .ws`.
- Downstream relation fetched during plan review: `AUR-261` blocks `AUR-242` in the later `PRD 0009: Harness Strategy` milestone. AUR-242 must not start until this PRD 0007 gate is closed.

## Objective

Close PRD 0007 only after proving every side-effect implementation slice is done, focused and full harnesses pass, default behavior remains non-mutating, durable docs explain the final contracts using progressive disclosure, and Linear contains a clear milestone evidence trail.

This is a gate and documentation-refactor issue. It should not implement PRD 0008 live LLM behavior, production public posting, CI/webhook posting policy, formal GitHub reviews, inline comments, labels, statuses, approvals, request-changes writes, global duplicate storage, or cross-process locking.

## Contracts To Preserve

- Dry-run remains the default behavior.
- Public CLI must not expose production `--post`.
- Default test collection must not require credentials, live GitHub, live LLM calls, or human input.
- GitHub writes remain reachable only through non-default harness/manual paths with explicit approval gates.
- Side-effect modules preserve the boundaries built in PRD 0007: candidate payloads are not writer input, finalization owns the last pre-writer gate, writer adapters receive finalized input only, marker reconciliation is idempotency proof, and manual live post remains disposable/opt-in.
- Documentation should be progressively disclosed: top-level docs orient agents quickly, architecture docs hold durable contracts, harness docs say how to prove behavior, PRDs preserve product scope, and ADRs capture decisions future agents must not rediscover.

## Plan

1. Refresh milestone planning artifacts:
   - Update `MILESTONE_PLAN.md` so Linear status is current: AUR-224 done, AUR-261 active, duplicates documented.
   - Keep this `ISSUE_PLAN.md` as the historical AUR-261 gate plan.
   - Commit the planning artifacts before implementation/docs refactor.
2. Plan review:
   - Use fresh subagents to review `MILESTONE_PLAN.md`, `ISSUE_PLAN.md`, AUR-261 gate criteria, and the fetched Linear inventory.
   - Fix material plan gaps and commit review fixes before audit/doc changes.
3. Completion audit:
   - Build a prompt-to-artifact checklist for every AUR-261 gate criterion.
   - Map every active PRD 0007 issue to status, evidence comment, focused harness, code/doc artifacts, and acceptance coverage.
   - Treat any active implementation issue without `Done` status or a Linear evidence comment as a hard blocker.
   - Map every canceled duplicate to duplicate rationale and replacement issue.
   - Required duplicate mapping: `AUR-248 -> AUR-243`, `AUR-249 -> AUR-244`, `AUR-250 -> AUR-245`, and `AUR-251 -> AUR-246`.
   - Check for temporary artifacts: `.ws/`, Linear exports, live-post artifacts, scratch files, and subagent scratch output.
4. Focused validation matrix:
   - Run PRD 0007 focused harnesses:
     - `.venv/bin/python -m pytest tests/test_payload_hashes.py -q`
     - `.venv/bin/python -m pytest tests/test_posting.py -q`
     - `.venv/bin/python -m pytest tests/test_payload_validation.py -q`
     - `.venv/bin/python -m pytest tests/test_approval.py -q`
     - `.venv/bin/python -m pytest tests/test_permissions.py -q`
     - `.venv/bin/python -m pytest tests/test_actor_permission_binding.py -q`
     - `.venv/bin/python -m pytest tests/test_target_freshness.py -q`
     - `.venv/bin/python -m pytest tests/test_markers.py tests/test_marker_hardening.py -q`
     - `.venv/bin/python -m pytest tests/test_non_interactive_posting.py -q`
     - `.venv/bin/python -m pytest tests/test_no_approved_findings.py -q`
     - `.venv/bin/python -m pytest tests/test_fake_writer.py tests/test_post_mode_graph.py -q`
     - `.venv/bin/python -m pytest tests/test_github_writer.py -q`
     - `.venv/bin/python -m pytest tests/test_live_post_contract.py -q`
   - Run broader gate validation:
     - `.venv/bin/python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py tests/test_github_dry_run_cli.py -q`
     - `.venv/bin/python -m pytest tests/test_reviewer_context.py tests/test_prompt_injection_memory.py tests/test_contract_boundaries.py -q`
     - `.venv/bin/python -m pytest tests/test_github_fake_read.py tests/test_github_read_gaps.py tests/test_github_pagination.py tests/test_github_memory_trust.py tests/test_live_read_smoke.py -q`
     - `.venv/bin/python -m pytest -q`
     - `.venv/bin/python -m py_compile src/reviewgraph/*.py`
     - `.venv/bin/python scripts/check_docs.py`
     - `.venv/bin/python scripts/check_docs.py --backlog-export <canonical-temporary-linear-export.json>`
     - `git diff --check`
   - The backlog export used for validation is temporary evidence only and must be deleted before final push.
5. Progressive-disclosure docs refactor:
   - Read current docs in AGENTS order plus PRD 0007, side-effect architecture, GitHub integration, harness engineering, decisions, and implementation plan.
   - Refactor only durable docs needed for agents dropping into side-effect code.
   - Ensure docs clearly answer:
     - What is safe by default?
     - Which module owns approval/finalization/marker/writer/live-post behavior?
     - Which commands prove the milestone?
     - Which side effects are in scope/out of scope?
     - Which ADRs/decisions must be preserved?
6. Code/docs review:
   - Use fresh subagents to review code, tests, docs, Linear evidence, and AUR-261 audit until no material issues remain.
   - Commit every review-fix batch separately.
7. Final validation after docs and review fixes:
   - Rerun the focused validation matrix, broader gate validation, docs checks, py-compile, and diff check after all docs changes and review-fix batches.
   - Record commit IDs and command timestamps/results in the final AUR-261 evidence comment.
   - Re-run temporary artifact cleanup checks after validation and delete the backlog export before push.
8. Linear closeout:
   - Move AUR-261 to `In Review` with an evidence comment containing checklist, validation commands, doc updates, and subagent review results.
   - The evidence comment must include the final gate table: Linear status, evidence comment presence, duplicate mapping, blocker/downstream relation, command results, doc changes, temp-artifact check, and final subagent review result.
   - Move AUR-261 to `Done` only after final review is clean.
   - Update the PRD 0007 milestone/project status if the Linear tools expose the necessary project/milestone status operation.
9. Push only after the milestone gate and documentation refactor are complete, the final completion audit passes, Linear is updated, temporary artifacts are removed, and no required work remains.

## Focused Evidence Checklist

- `AUR-244` hash domains: `src/reviewgraph/hashing.py`, `tests/test_payload_hashes.py`.
- `AUR-218` payload validation and candidate/final split: `src/reviewgraph/posting.py`, `src/reviewgraph/payload_validation.py`, `src/reviewgraph/final_payload.py`, `tests/test_posting.py`, `tests/test_payload_validation.py`.
- `AUR-217` item-level approval and final hash: `src/reviewgraph/approval.py`, `tests/test_approval.py`.
- `AUR-219` actor/permission gate: `src/reviewgraph/permissions.py`, `tests/test_permissions.py`.
- `AUR-243` approval actor/permission binding: `src/reviewgraph/approval.py`, `src/reviewgraph/finalization.py`, `tests/test_actor_permission_binding.py`.
- `AUR-220` target freshness: `src/reviewgraph/finalization.py`, `tests/test_target_freshness.py`.
- `AUR-221` marker grammar/happy path: `src/reviewgraph/markers.py`, `tests/test_markers.py`.
- `AUR-245` marker hardening: `src/reviewgraph/markers.py`, `tests/test_marker_hardening.py`.
- `AUR-246` non-interactive posting block: `src/reviewgraph/post_interaction.py`, `tests/test_non_interactive_posting.py`.
- `AUR-223` no approved findings: `src/reviewgraph/finalization.py`, `tests/test_no_approved_findings.py`.
- `AUR-222` fake writer/post-mode graph: `src/reviewgraph/writer_fake.py`, `src/reviewgraph/post_mode_harness.py`, `tests/test_fake_writer.py`, `tests/test_post_mode_graph.py`.
- `AUR-241` real writer adapter: `src/reviewgraph/writer_github.py`, `src/reviewgraph/writer_input.py`, `tests/test_github_writer.py`.
- `AUR-224` manual live post smoke: `src/reviewgraph/github_live_post.py`, `tests/test_live_post_contract.py`.

## Out Of Scope

- Starting PRD 0008.
- Adding production public posting.
- Running a real live GitHub mutation.
- Introducing new side-effect capabilities.
- Pushing before the milestone gate, docs refactor, final audit, and Linear closeout are complete.
