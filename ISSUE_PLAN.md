# ISSUE PLAN: AUR-229 Keep PRDs Architecture And Plan In Sync

## Linear issue

- Issue: `AUR-229` / `RG-040: Keep PRDs Architecture And Plan In Sync`
- Milestone: `PRD 0001: North Star`
- Current status: `In Progress`

## Acceptance criteria mapping

1. Docs index points to PRDs and architecture docs.
   - Evidence target: `docs/README.md` read order and task index.
   - Validation target: script verifies linked docs exist.
2. Implementation plan references the same MVP constraints as PRDs.
   - Evidence target: `docs/plans/implementation-plan.md` goal/posture plus PRD index dependency shape.
   - Validation target: script checks implementation plan mentions core MVP constraints: dry-run, item-level approval, fake fixtures/adapters, live opt-in, and Linear as executable backlog.
3. `AGENTS.md` or equivalent says behavior-changing implementation PRs update the narrowest durable doc.
   - Evidence target: `AGENTS.md` documentation update section.
   - Validation target: script checks the durable-doc update rule exists.
4. `docs/decisions/` is linked from the docs index for durable side-effect tradeoffs.
   - Evidence target: `docs/README.md` links `decisions/README.md`, and decisions include dry-run/source-of-truth records.
   - Validation target: script checks decisions index exists and is linked.
5. A documented command or script checks that the issue backlog queue is dependency-ordered.
   - Evidence target: `scripts/check_docs.py` or equivalent, documented in `docs/implementation/README.md` and/or `docs/harnesses/harness-engineering.md`.
   - Validation target: command accepts a Linear backlog export JSON, reports checked issues/edges, and fails on duplicates, missing references, cycles, or dependency inversions.

## Implementation plan

1. Add `scripts/check_docs.py` using only the Python standard library.
2. Make the script validate durable documentation links and required MVP/doc-sync phrases.
3. Make the script optionally accept `--backlog-export PATH` and validate a queue-shaped Linear export:
   - Ordered issues are taken from the JSON array order.
   - Issue IDs may be `id`, `identifier`, or `key`.
   - Blockers may be `blockedBy`, `blocked_by`, `blocked_by_ids`, or `blockedByIds`.
   - Canceled/duplicate issues are ignored by default.
   - Output reports issue count, edge count, and evaluated queue order.
4. Add a small fixture export under `docs/plans/linear-backlog-order.example.json` so the command is executable in a fresh clone.
5. Document the command in the narrowest docs:
   - `docs/implementation/README.md` for implementation-agent usage.
   - `docs/harnesses/harness-engineering.md` for proof strategy.
6. Run:
   - `python scripts/check_docs.py`
   - `python scripts/check_docs.py --backlog-export docs/plans/linear-backlog-order.example.json`
   - `git diff --check`

## Out of scope

- Do not query Linear live from the script in this slice.
- Do not add runtime ReviewGraph implementation.
- Do not mirror the full Linear backlog into the repo.
- Do not close `AUR-253` until after `AUR-229` is done and the milestone audit passes.

## Review plan

- Get fresh subagent plan review before implementation.
- After implementation, move `AUR-229` to `In Review`, run fresh code/docs review subagents, fix material issues, and commit after each review cycle.
