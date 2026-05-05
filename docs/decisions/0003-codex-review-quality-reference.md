# Decision 0003: Codex-inspired review quality bar

## Status

Accepted

## Context

The local upstream Codex checkout includes a dedicated review mode and review skills. The useful lessons are not the exact implementation language or UI behavior, but the review contract:

- findings should be discrete, actionable bugs the author would likely fix;
- comments should be brief, evidence-backed, and precisely located;
- low-confidence or intent-dependent issues should not be treated as blocking;
- reviewer contexts can be isolated and constrained;
- review output should be structured before any human-facing rendering;
- human review comments require extra care before automation replies.

## Decision

Adopt a Codex-inspired review quality bar for ReviewGraph. Reviewer output must pass a quality classification step before it can become postable GitHub feedback. The graph should preserve useful local notes and clarification requests without treating them as PR comments.

## Consequences

- ReviewGraph may produce no postable findings even when reviewers produce notes.
- Postable findings need precise changed-line locations where possible.
- Approval is item-level because not every valid local note should be posted.
- Reviewer capabilities default to constrained/read-only contexts.
- PR comments become structured memory and actionable feedback only after trust, seen-state, and resolved-state filtering.
