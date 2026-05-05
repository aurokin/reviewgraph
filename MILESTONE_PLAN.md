# MILESTONE PLAN: PRD 0001 North Star

## Linear scope

- Milestone: `PRD 0001: North Star`
- Implementation issue: `AUR-229` / `RG-040: Keep PRDs Architecture And Plan In Sync`
- Gate issue: `AUR-253` / `Complete PRD 0001: North Star`

## Milestone intent

PRD 0001 is not runtime implementation. It makes the repository safe for later implementation agents by ensuring the durable documentation contract is easy to find, aligned with the PRD set, and explicit about where process guidance belongs.

## Current evidence

- `docs/README.md` already points to product, architecture, PRDs, decisions, harness engineering, and the implementation plan.
- `docs/plans/implementation-plan.md` already states the MVP constraints and says Linear is the executable backlog.
- `AGENTS.md` already instructs agents to update the narrowest durable doc when behavior changes.
- `docs/decisions/README.md` and `docs/decisions/0004-linear-backlog-docs-are-contracts.md` already make the source-of-truth boundary durable.
- Missing evidence: there is no documented command or script that checks a Linear backlog queue export is dependency-ordered with auditable output.

## Plan

1. Review `AUR-229`, `AUR-253`, PRD 0001, and the current repository docs before making changes.
2. Add a lightweight repository validation script that proves the durable documentation links exist and checks a Linear backlog queue export for dependency-order violations with auditable output.
3. Update the narrowest docs so implementation agents can find the validation command without reading the whole repo.
4. Create `ISSUE_PLAN.md` for `AUR-229`, get a fresh plan review, then implement the smallest doc/check changes needed to satisfy the issue. `ISSUE_PLAN.md` is a per-issue historical plan artifact and does not replace Linear.
5. Run the documented validation command and any relevant markdown/link checks available locally.
6. Move `AUR-229` to `In Review` when implementation is ready for review. Use fresh subagents for code/docs review, fix until no material issues remain, then move `AUR-229` to `Done`.
7. Before touching `AUR-253`, re-fetch the current PRD 0001 milestone membership from Linear and verify all non-canceled, non-gate implementation issues in the milestone are complete.
8. Perform the milestone-end documentation audit required by the thread goal before closing `AUR-253`. If docs need refactoring after the issue is complete, do it in separate commits before considering PRD 0001 complete.
9. Close the milestone gate `AUR-253` only after the membership re-check, `AUR-229` audit, and milestone-end documentation audit all pass.

## Non-goals

- Do not implement ReviewGraph runtime behavior in this milestone.
- Do not mirror Linear issue data into repository docs.
- Do not recreate `.ws/` or any generated local backlog tree.
- Do not push until the larger active goal permits pushing.

## Validation target

The milestone is complete when:

- `AUR-229` is done.
- `AUR-253` is done.
- The repo contains a documented validation command or script covering documentation links and Linear backlog dependency-order verification from an explicit export/input format.
- The backlog-order check reports which issues and dependency edges were evaluated and fails on missing references, duplicate active issue IDs, cycles, or dependency inversions.
- `git diff --check` passes.
- The milestone-end documentation audit finds no missing PRD 0001 contract details.
