# Decision 0005: Inert reviewer tool metadata

## Status

Accepted

## Context

PRD 0010 requires reviewer configs and context packages to preserve optional model, tool, context, and capability metadata before live reviewer adapters exist. At the same time, MVP reviewer agents must not gain ambient GitHub access, repository access, provider tool calls, process access, or write capability.

If `tools` are rejected completely, future live-agent configuration has no stable contract to build on. If `tools` are treated as executable capabilities too early, the reviewer boundary becomes unsafe and hard to test.

## Decision

`tools` are accepted only as inert future metadata. Tool identifiers use a conservative `future-*` namespace and are recorded in reviewer config metadata, context package traces, and provider-bound previews.

Tool metadata does not create callable handles, provider tool schemas, live-call budget, repository access, GitHub access, process access, approval access, payload-builder access, or write capability. MVP executable reviewer capabilities remain `none` and `diff_context`.

## Consequences

- Future tool policy can build on a validated config field without changing the context package shape.
- Tests must prove tool names remain metadata only.
- Any later executable tool support needs a separate policy, harness, and side-effect boundary review.
