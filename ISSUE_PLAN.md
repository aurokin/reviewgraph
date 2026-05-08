# ISSUE PLAN: AUR-262 Complete PRD 0009 Harness Strategy

Active gate plan for `AUR-262` / `Complete PRD 0009: Harness Strategy`.

Linear is the durable source for issue status, evidence comments, and milestone progress. This gate should not add new product behavior unless the audit finds a concrete PRD 0009 gap. The expected output is a closed final milestone gate with evidence and a complete validation/handoff contract.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0009: Harness Strategy`
- Milestone ID: `9c76d492-a6f2-479d-bfee-37c00c5ef0b8`
- Gate issue: `AUR-262`
- Status when planned: `In Progress`
- Implementation issue:
  - `AUR-242` / `RG-053: Add Validation Command And Marker Contracts` / `Done`
- Upstream milestone gate:
  - `AUR-260` / `Complete PRD 0008: Live LLM` / `Done`

## Objective

Close PRD 0009 only after proving the default handoff validation command, live marker discipline, marker/hash coverage, writer contract coverage, opt-in live command separation, Linear ordering, and durable docs match the final milestone contract.

## Gate Criteria

- `AUR-242` is `Done` in Linear with an evidence comment.
- Fresh Linear inventory proves no open PRD 0009 implementation issue remains besides the gate.
- Linear ordering remains valid: `AUR-260` blocks `AUR-242`, and `AUR-242` blocks `AUR-262`.
- Full default validation, docs check, py-compile, diff check, and backlog export check pass.
- Durable docs explain the final default validation sequence and live opt-in command separation.
- Fresh subagent review of docs, tests, Linear evidence, and gate evidence reports no material issues.
- Default commands still cannot call live providers, write GitHub, require credentials, or require human input.
- No `.ws/`, temporary Linear export, live smoke artifact, audit scratch file, or subagent scratch file remains.

## Plan

1. Re-fetch Linear issue inventory and comments for `AUR-242` and `AUR-262`.
2. Verify the AUR-242 evidence comment maps to all acceptance criteria.
3. Audit durable docs changed for PRD 0009:
   - `README.md`
   - `docs/harnesses/harness-engineering.md`
   - `docs/implementation/README.md`
   - `pyproject.toml`
   - `tests/conftest.py`
   - `tests/test_validation_contract.py`
4. Run gate validation:
   - `.venv/bin/python -m pytest tests/test_validation_contract.py -q`
   - `.venv/bin/python -m pytest -q`
   - `.venv/bin/python -m py_compile src/reviewgraph/*.py`
   - `.venv/bin/python scripts/check_docs.py`
   - `git diff --check`
5. Create a temporary canonical Linear backlog export containing `AUR-260`, `AUR-242`, and `AUR-262` in dependency order. Run `.venv/bin/python scripts/check_docs.py --backlog-export <temp>`, record output and hash, then delete the export.
6. Use fresh subagents to review the gate evidence, docs/tests, Linear relationships, and closure decision.
7. Move `AUR-262` to `In Review`, add a Linear gate evidence comment, then move it to `Done` only after review is clean.

## Acceptance Mapping

- Default handoff command -> `README.md`, `docs/harnesses/harness-engineering.md`, `docs/implementation/README.md`.
- Live marker registration/default skip -> `pyproject.toml`, `tests/conftest.py`, `tests/test_validation_contract.py`.
- Marker/hash and writer coverage -> default full suite plus harness docs.
- Manual live-post opt-in -> `docs/harnesses/harness-engineering.md`, `docs/architecture/github-integration.md`, `tests/test_live_post_contract.py`.
- Milestone sequencing -> Linear relationships plus backlog export check.
- Cleanup -> clean worktree, no `.ws/`, no temp export, no live artifacts.

## Required Linear Gate Evidence Comment

The final AUR-262 evidence comment must include:

- Implementation issue inventory: `AUR-242` status and evidence comment ID.
- Validation matrix: marker-contract test, full test suite, py-compile, docs check, diff check, and backlog export check.
- Backlog/export proof: temp export hash, included issues, relationship proof for `AUR-260 -> AUR-242 -> AUR-262`, and confirmation the temp export was deleted.
- Documentation audit result: docs inspected, commit hashes, and final command surface.
- Fresh subagent review outcomes: names/ids and final clean result.
- Cleanup proof: no `.ws/`, temp export, live artifacts, audit scratch files, or subagent scratch files remain.

## Out Of Scope

- New validation wrapper unless the gate audit finds docs are insufficient.
- Running live read, live LLM, or live post smoke.
- Production GitHub posting.
- CI provider setup.
- Further product or architecture scope beyond PRD 0009 closeout.
