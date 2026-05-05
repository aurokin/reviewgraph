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
   - Validation target: script checks implementation plan mentions core MVP constraints: dry-run default, item-level approval, top-level issue comments, no formal PR review/request-changes writes in MVP, target freshness, actor/permission proof, redaction, idempotency markers, local verdict separation, structured findings, fake fixtures/adapters, live opt-in, side effects last, and Linear as executable backlog.
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
2. Make the script validate explicit required docs-index links, not only link existence:
   - `architecture/overview.md`
   - `architecture/state-graph.md`
   - `prds/README.md`
   - `decisions/README.md`
   - `harnesses/harness-engineering.md`
   - `plans/implementation-plan.md`
3. Make the script validate required MVP/doc-sync phrases from the implementation plan, `AGENTS.md`, decisions index, and docs index.
4. Make the script optionally accept `--backlog-export PATH` and validate a canonical queue-shaped Linear export.
   Canonical schema:
   ```json
   {
     "source": "Linear",
     "project": "ReviewGraph",
     "milestone": "PRD 0001: North Star",
     "exported_at": "2026-05-05T00:00:00Z",
     "issues": [
       {
         "id": "AUR-229",
         "title": "RG-040: Keep PRDs Architecture And Plan In Sync",
         "status_type": "backlog",
         "blocked_by": []
       }
     ]
   }
   ```
   Rules:
   - Ordered issues are taken from the JSON array order.
   - Dependency edges are `blocked_by` only. Parent, related, duplicate, and canceled relationships are ignored unless represented as `blocked_by`.
   - Issues whose `status_type` is `canceled` are filtered before dependency checks.
   - Duplicate active issue IDs or duplicate queue entries fail.
   - Missing blockers, cycles, and blocker-after-dependent inversions fail.
   - `source` must be `Linear` so hand-shaped generic JSON is not mistaken for canonical evidence.
   - Output reports source, project, milestone, exported timestamp, checked issue count, edge count, skipped canceled count, and concise failing edges. Add a `--verbose` flag for full order if useful.
5. Add small synthetic fixture exports under `docs/plans/fixtures/` so the command is executable in a fresh clone:
   - valid order fixture.
   - invalid duplicate or inversion fixture.
   These fixtures must be labeled synthetic and non-authoritative; they are parser/checker examples, not the ReviewGraph backlog.
6. Document the command in the narrowest docs:
   - `docs/implementation/README.md` for implementation-agent usage.
   - `docs/harnesses/harness-engineering.md` for proof strategy.
7. Run:
   - `python scripts/check_docs.py`
   - `python scripts/check_docs.py --backlog-export docs/plans/fixtures/linear-backlog-valid.example.json`
   - `python scripts/check_docs.py --backlog-export docs/plans/fixtures/linear-backlog-invalid-duplicate.example.json` and verify it fails
   - `git diff --check`

## Out of scope

- Do not query Linear live from the script in this slice.
- Do not add runtime ReviewGraph implementation.
- Do not mirror the full Linear backlog into the repo.
- Do not close `AUR-253` until after `AUR-229` is done and the milestone audit passes.

## Review plan

- Get fresh subagent plan review before implementation.
- After implementation, move `AUR-229` to `In Review`, run fresh code/docs review subagents, fix material issues, and commit after each review cycle.
