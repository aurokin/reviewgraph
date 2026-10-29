# Decision 0010: Docs and GitHub are the backlog

## Status

Accepted. Supersedes [Decision 0004](0004-linear-backlog-docs-are-contracts.md).

## Context

Decision 0004 kept implementation issues, milestone order, and blocker relationships in an external tracker while repository docs held the durable contracts. That tracker is no longer used. Its milestone briefs were the same PRDs already in `docs/prds/`; the one later revision that differed is kept in `docs/archive/`.

## Decision

The repository is the single place for planning:

- `docs/plans/implementation-plan.md` holds the milestone sequence and durable ordering narrative.
- `docs/prds/` holds product slice intent and acceptance shape.
- GitHub issues and pull requests on this repository hold concrete tasks, discussion, and handoff details.

Repository docs remain the durable product, architecture, harness, and decision contracts. Docs should still explain invariants, proof strategy, and narrow behavior contracts rather than mirror every issue.

## Consequences

- Implementation agents start from the implementation plan, the relevant PRD, and the GitHub issue or PR for a concrete task.
- Behavior-changing work still updates the narrowest durable doc.
- Harness docs describe proof patterns and gates, not every individual ticket.
- Old `AUR-*` keys in code comments, fixtures, and history are historical references only.
- `scripts/check_docs.py` validates documentation contracts only; it no longer checks an exported issue queue.
