# MILESTONE PLAN: PRD 0009 Harness Strategy

Active execution artifact for this milestone. Linear remains the durable source for issue status, blockers, comments, and milestone order. Repository docs remain the durable product, architecture, harness, and decision contracts. If Linear and durable docs disagree on behavior, stop and reconcile both before implementation.

## Linear Scope Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0009: Harness Strategy`
- Milestone ID: `9c76d492-a6f2-479d-bfee-37c00c5ef0b8`
- Current milestone status when planned: `0%`
- Active implementation issues fetched from Linear:
  - `AUR-242` / `RG-053: Add Validation Command And Marker Contracts` / `Backlog`
- Gate issue:
  - `AUR-262` / `Complete PRD 0009: Harness Strategy` / `Backlog`
- Upstream milestone order:
  - `AUR-260` / `Complete PRD 0008: Live LLM` is `Done` and blocks `AUR-242`.
  - `AUR-242` blocks `AUR-262`.

## Milestone Intent

PRD 0009 closes the harness strategy by making the validation contract easy for future implementation agents to run and audit. The project already has broad fixture, fake-adapter, graph, quality, approval, writer, marker, live-read, live-LLM, and live-post harnesses. This milestone should turn that scattered proof into one named default validation surface plus explicit opt-in live command documentation.

The milestone should prove:

- the default handoff command covers fixture, schema/config, graph, quality, redaction, approval, marker/hash, fake writer, GitHub dry-run, live-read smoke prerequisites, live-LLM smoke prerequisites, and manual live-post contract tests without credentials;
- live-read, live-LLM, and live-post smoke tests are registered, marked, and skipped by default;
- marker/hash golden tests and writer idempotency contracts are part of the default validation set;
- real writer and manual live-post contracts are represented in docs as fake/default-safe or manual opt-in only;
- future implementation issues can name one default validation command before handoff instead of rediscovering the suite from issue history.

## Current Code Snapshot

- `pyproject.toml` registers `live_read`, `live_llm`, and `live_post` markers.
- `tests/conftest.py` skips those markers unless `REVIEWGRAPH_LIVE_READ=1`, `REVIEWGRAPH_LIVE_LLM=1`, or `REVIEWGRAPH_LIVE_POST=1`.
- `scripts/check_docs.py` validates durable docs and optional Linear backlog-order exports.
- `docs/harnesses/harness-engineering.md` defines the confidence ladder, required harness families, PRD 0007 validation matrix, live API discipline, and backlog export check.
- `README.md` lists useful validation commands, but it does not yet clearly identify one default handoff command for implementation agents.
- `docs/implementation/README.md` explains docs and backlog export checks, but not the complete local default validation matrix.
- Marker/hash harnesses exist in `tests/test_payload_hashes.py`, `tests/test_markers.py`, and `tests/test_marker_hardening.py`.
- Real writer and manual live-post contracts exist in `tests/test_github_writer.py` and `tests/test_live_post_contract.py`; default tests use fake transports and skip manual smoke.
- The current full default suite passes with `1291 passed, 3 skipped, 1 warning`.

## Execution Order

1. `AUR-242` first: add or tighten the validation command and marker contracts. Prefer the smallest durable change that makes the default handoff command explicit and executable. Likely scope is documentation plus, if needed, a small validation wrapper that delegates to existing commands without invoking credentials or live systems.
2. `AUR-262` last: close the milestone after AUR-242 is `Done`, backlog order is proven with a temporary Linear export, full validation passes, docs are audited, and fresh subagent review reports no material findings.

## Linear Relationship Plan

Linear blockers are already aligned for this final milestone:

- `AUR-242` is blocked by completed `AUR-260`.
- `AUR-242` blocks `AUR-262`.

Before closing `AUR-262`, run the backlog export check with `AUR-260`, `AUR-242`, and `AUR-262` in dependency order, then delete the temporary export.

## Issue Workflow

For each issue:

1. Re-fetch the issue, milestone, blockers, comments, and relevant docs/code.
2. Move the issue to `In Progress` when starting active work.
3. Replace `ISSUE_PLAN.md` with a narrow issue plan and commit it before implementation.
4. Use fresh subagents to review the milestone/issue plan before code changes.
5. Implement the smallest contract/harness slice that satisfies the issue and does not reopen earlier milestone scope.
6. Run the issue harness named in Linear plus regression tests for touched shared behavior.
7. Use fresh subagents for code/docs review until no material findings remain.
8. Commit the completed issue and every review-fix batch separately.
9. Move the issue to `In Review`, add a Linear evidence comment with commands and artifact coverage, then move it to `Done` only when acceptance criteria map to concrete evidence.

For milestone gates and blocker/order changes, also run `python scripts/check_docs.py --backlog-export path/to/linear-backlog-export.json` against a temporary canonical Linear export, then delete the export before handoff.

## Harness Strategy

`AUR-242` focused validation should include:

```bash
python -m pytest tests/test_tracer_fixture_run.py tests/test_config.py tests/test_stage_cursor.py tests/test_routing.py tests/test_reviewer_runs.py -q
python -m pytest tests/test_findings.py tests/test_reviewer_json_repair.py tests/test_quality.py tests/test_diff_anchor.py tests/test_quality_testing.py tests/test_clarification.py tests/test_clarification_resume.py tests/test_optional_reviewer_failure.py tests/test_verdict.py -q
python -m pytest tests/test_reviewer_context.py tests/test_prompt_injection_memory.py tests/test_redaction.py tests/test_contract_boundaries.py tests/test_adapter_boundaries.py -q
python -m pytest tests/test_payload_hashes.py tests/test_markers.py tests/test_marker_hardening.py tests/test_payload_validation.py tests/test_posting.py tests/test_approval.py -q
python -m pytest tests/test_no_approved_findings.py tests/test_fake_writer.py tests/test_post_mode_graph.py tests/test_github_writer.py tests/test_live_post_contract.py -q
python -m pytest tests/test_github_fake_read.py tests/test_github_read_gaps.py tests/test_github_pagination.py tests/test_github_memory_trust.py tests/test_conversation_routing.py tests/test_github_dry_run_cli.py tests/test_live_read_smoke.py tests/test_live_llm_adapter.py -q
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

If a wrapper command is added, it must run only default-safe checks unless explicitly passed a live/manual flag. It must not require credentials, mutate GitHub, call live LLMs, or require human input by default.

## Contract Guardrails

- Dry-run remains default.
- Default validation must not call GitHub live writes, live LLM providers, or credential-requiring live reads.
- Marked live tests must be skipped by default and must have prerequisite-blocked behavior when opt-in variables are incomplete.
- Marker/hash tests must stay in the default suite because idempotency and duplicate safety are part of the side-effect contract.
- Real writer adapter tests must use fake transports by default.
- Manual live-post smoke remains library-level, disposable-target-only, typed-final-hash gated, and skipped by default.
- Documentation should name the command an implementation agent runs before handoff, plus narrower focused commands when a slice changes only one contract family.
- Do not turn repository docs into the backlog; Linear remains the executable queue.

## Documentation Work

Update the narrowest durable docs alongside behavior:

- Validation command and handoff rules -> `docs/harnesses/harness-engineering.md`, `docs/implementation/README.md`, and possibly `README.md`.
- Test marker discipline -> `docs/harnesses/harness-engineering.md` and `pyproject.toml` only if marker definitions change.
- Side-effect or marker contract wording -> `docs/architecture/side-effects.md` or `docs/architecture/github-integration.md` only if behavior changes.
- Implementation sequencing -> `docs/plans/implementation-plan.md` only if the phase narrative changes materially.
- Durable tradeoffs -> `docs/decisions/` only when future agents need a rule that should not be rediscovered from Linear history.

## PRD 0009 Acceptance Surface

The milestone is complete when ReviewGraph proves:

- a documented default validation command covers the expected local harness families without credentials;
- live read, live LLM, and live post tests are marked and skipped by default;
- live opt-in commands are documented separately from default validation;
- marker/hash golden tests and fake writer/real writer contract tests are included in default-safe validation;
- manual live-post smoke remains represented as an opt-in contract, not a default command;
- full test suite, docs check, py-compile, diff check, and backlog export check pass;
- AUR-242 and AUR-262 both have Linear evidence comments before Done.

## Deferred Scope

- Full live CI matrix.
- Hosted environment tests.
- Browser/UI testing.
- Performance benchmarking beyond context budget and live-call caps.
- Any production GitHub posting command.
- Any always-on live LLM or live GitHub behavior.

## Milestone Completion Criteria

`AUR-262` can close only when:

- `AUR-242` is `Done` in Linear with an evidence comment.
- Fresh Linear inventory proves `AUR-242` is complete and no downstream gate remains unblocked incorrectly.
- Focused validation for `AUR-242` passes.
- Full validation, docs check, py-compile, diff check, and backlog export check pass.
- Durable docs explain the final default validation command, live marker discipline, marker/hash coverage, and opt-in live command separation.
- Fresh subagent review of docs, tests, Linear evidence, and the milestone gate reports no material issues.
- Default commands still cannot call live providers, write GitHub, require credentials, or require human input.
- No `.ws/`, temporary Linear export, live smoke artifact, audit scratch file, or subagent scratch file remains in the repository.
