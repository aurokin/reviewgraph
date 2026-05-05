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
- Missing or weak evidence: there is no documented command or script that checks the Linear backlog queue is dependency-ordered.

## Plan

1. Review `AUR-229`, `AUR-253`, PRD 0001, and the current repository docs before making changes.
2. Add a lightweight repository validation command that proves the durable documentation links exist and records the Linear backlog dependency-order check as an explicit external verification step.
3. Update the narrowest docs so implementation agents can find the validation command without reading the whole repo.
4. Create `ISSUE_PLAN.md` for `AUR-229`, get a fresh plan review, then implement the smallest doc/check changes needed to satisfy the issue.
5. Run the documented validation command and any relevant markdown/link checks available locally.
6. Use fresh subagents for code/docs review, fix until no material issues remain, then move `AUR-229` to `Done`.
7. Close the milestone gate `AUR-253` only after an audit maps every `AUR-229` acceptance criterion to concrete repository evidence.
8. Perform the milestone-end documentation audit required by the thread goal. If docs need refactoring after the issue is complete, do it in separate commits before considering PRD 0001 complete.

## Non-goals

- Do not implement ReviewGraph runtime behavior in this milestone.
- Do not mirror Linear issue data into repository docs.
- Do not recreate `.ws/` or any generated local backlog tree.
- Do not push until the larger active goal permits pushing.

## Validation target

The milestone is complete when:

- `AUR-229` is done.
- `AUR-253` is done.
- The repo contains a documented validation command or script covering documentation links and the backlog dependency-order verification expectation.
- `git diff --check` passes.
- The milestone-end documentation audit finds no missing PRD 0001 contract details.
