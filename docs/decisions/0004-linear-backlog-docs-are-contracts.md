# Decision 0004: Linear backlog, docs as contracts

## Status

Accepted

## Context

ReviewGraph generated a large implementation backlog from PRDs and architecture review. The temporary `.ws/` issue tree was useful as staging material, but keeping it in the repository would create a second source of truth next to Linear.

## Decision

Linear is the durable source for implementation issues, milestone sequencing, issue relationships, and agent handoff details. Repository docs remain the durable product, architecture, harness, and decision contracts.

Docs should not duplicate the full Linear issue list. They should explain the invariant, proof strategy, and narrow behavior contract that implementation issues reference.

If an active execution workflow requires committed planning artifacts such as `MILESTONE_PLAN.md` or `ISSUE_PLAN.md`, those files are historical execution artifacts only. They must say Linear wins for current status, blockers, issue relationships, milestone order, and handoff details.

## Consequences

- Implementation agents should start from Linear for concrete tasks.
- Behavior-changing work still updates the narrowest durable doc.
- Harness docs describe proof patterns and gates, not every individual ticket.
- Temporary planning trees such as `.ws/` should be removed once represented in Linear.
