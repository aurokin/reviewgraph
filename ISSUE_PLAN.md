# ISSUE PLAN: AUR-242 Add Validation Command And Marker Contracts

Active issue plan for `AUR-242` / `RG-053: Add Validation Command And Marker Contracts`.

Linear is the durable source for issue status, evidence comments, and blocker relationships. This issue should make the harness contract easier to run and audit without adding new live behavior.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0009: Harness Strategy`
- Milestone ID: `9c76d492-a6f2-479d-bfee-37c00c5ef0b8`
- Issue: `AUR-242`
- Status when planned: `In Progress`
- Upstream blocker: `AUR-260` / `Complete PRD 0008: Live LLM` / `Done`
- Downstream gate: `AUR-262` / `Complete PRD 0009: Harness Strategy` / `Backlog`

## Objective

Define a default implementation-agent validation command and supporting docs that prove the existing local harness families without credentials, live provider calls, GitHub writes, or human input. Keep live read, live LLM, and live post smoke paths explicitly opt-in and skipped by default.

## Acceptance Criteria

- Default validation command covers fixture, schema/config, graph, quality, redaction, approval, marker/hash, fake writer, real-writer contract, GitHub dry-run, and live smoke prerequisite contracts without credentials.
- `live_read`, `live_llm`, and `live_post` markers are registered and skipped by default.
- Manual live post remains represented as an opt-in disposable-target contract, not a default command.
- Marker/hash golden tests remain named as default validation coverage.
- Real writer tests remain default-safe through fake transports only.
- An unmarked marker-contract test proves `live_read`, `live_llm`, and `live_post` are registered in `pyproject.toml` and wired to default skip conditions in `tests/conftest.py`.
- Documentation names the command an implementation agent should run before handing off a slice.
- Full default suite, docs check, py-compile, and diff check pass.

## Plan

1. Audit existing validation surfaces:
   - `pyproject.toml`
   - `tests/conftest.py`
   - `README.md`
   - `docs/harnesses/harness-engineering.md`
   - `docs/implementation/README.md`
   - `docs/architecture/github-integration.md`
   - `docs/architecture/side-effects.md`
   - marker/hash, writer, live-read, live-LLM, and live-post tests
2. Name one real default handoff validation sequence:
   - `.venv/bin/python -m pytest -q`
   - `.venv/bin/python -m py_compile src/reviewgraph/*.py`
   - `.venv/bin/python scripts/check_docs.py`
   - `git diff --check`
3. Prefer a docs-first implementation unless audit proves a wrapper command is needed.
4. If adding a wrapper command, make it default-safe:
   - no credentials required;
   - no live GitHub write;
   - no live LLM call;
   - no human prompt by default;
   - exits non-zero on failed local checks.
5. Add or update unmarked marker-contract coverage for all live markers and their default skip wiring.
6. Update narrow durable docs so the default handoff command and opt-in live command separation are discoverable. Reconcile any docs that imply a nonexistent pytest flag such as `--requires-human-approval`.
7. Run focused validation:
   - `.venv/bin/python -m pytest tests/test_tracer_fixture_run.py tests/test_config.py tests/test_stage_cursor.py tests/test_routing.py tests/test_reviewer_runs.py -q`
   - `.venv/bin/python -m pytest tests/test_findings.py tests/test_reviewer_json_repair.py tests/test_quality.py tests/test_diff_anchor.py tests/test_quality_testing.py tests/test_clarification.py tests/test_clarification_resume.py tests/test_optional_reviewer_failure.py tests/test_verdict.py -q`
   - `.venv/bin/python -m pytest tests/test_reviewer_context.py tests/test_prompt_injection_memory.py tests/test_redaction.py tests/test_contract_boundaries.py tests/test_adapter_boundaries.py -q`
   - `.venv/bin/python -m pytest tests/test_payload_hashes.py tests/test_markers.py tests/test_marker_hardening.py tests/test_payload_validation.py tests/test_posting.py tests/test_approval.py tests/test_permissions.py tests/test_actor_permission_binding.py tests/test_target_freshness.py tests/test_non_interactive_posting.py -q`
   - `.venv/bin/python -m pytest tests/test_no_approved_findings.py tests/test_fake_writer.py tests/test_post_mode_graph.py tests/test_github_writer.py tests/test_live_post_contract.py -q`
   - `.venv/bin/python -m pytest tests/test_github_fake_read.py tests/test_github_read_gaps.py tests/test_github_pagination.py tests/test_github_memory_trust.py tests/test_conversation_routing.py tests/test_github_dry_run_cli.py tests/test_live_read_smoke.py tests/test_live_llm_adapter.py -q`
   - `.venv/bin/python -m pytest tests/test_validation_contract.py -q`
   - `.venv/bin/python -m pytest -q`
   - `.venv/bin/python -m py_compile src/reviewgraph/*.py`
   - `.venv/bin/python scripts/check_docs.py`
   - `git diff --check`
8. Use fresh subagents to review the issue implementation and docs until no material findings remain.
9. Commit implementation/docs and any review fixes separately.
10. Move `AUR-242` to `In Review`, add evidence comment, then move it to `Done`.

## Expected Implementation Shape

Likely durable edits:

- `docs/harnesses/harness-engineering.md`: name the default handoff command and the focused command families; keep live API discipline separate.
- `docs/implementation/README.md`: explain local validation versus backlog-order validation for agents working from Linear.
- `README.md`: surface the default validation command near useful validation commands if needed.
- `tests/test_validation_contract.py` or equivalent: unmarked proof that all live markers are registered and skipped by default.

Potential code/script edit only if docs are insufficient:

- Add a tiny validation script that runs the default-safe checks and documents its exact scope. Do not add live/manual flags unless the existing docs need a stable command name for them.

## Out Of Scope

- Running live read, live LLM, or live post smoke by default.
- Adding a production GitHub posting command.
- Changing marker grammar, hash domains, approval semantics, or writer behavior unless the audit finds a direct documentation mismatch.
- Reworking the fixture corpus or graph behavior.
- Adding CI provider configuration.
