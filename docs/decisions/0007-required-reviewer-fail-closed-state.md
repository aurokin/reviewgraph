# Decision 0007: Required reviewer failure is fail-closed graph state

## Status

Accepted

## Context

PRD 0004 distinguishes required and optional reviewer failures. A required reviewer failure means the review is incomplete enough that public posting should not proceed, but default dry-run behavior should still be useful: the operator needs to see what failed, what other reviewers produced, and why posting is disabled.

At the same time, malformed fixture data and malformed raw-output schema are harness/input errors. Treating those as successful dry-run output would hide broken tests or invalid fixtures.

## Decision

An explicit required reviewer failure is graph-owned fail-closed state. The run records a durable `GraphError`, preserves the failed `ReviewerResult` and failed `ReviewerRunStatus`, sets `post_enabled=false`, omits candidate GitHub payloads, and converts the posting plan to local-only while still rendering local dry-run output.

An optional reviewer failure records a failed `ReviewerResult` and a local note, but it does not create a top-level `GraphError` or block post eligibility by itself.

Malformed fixture data or malformed raw-output schema remains an input error and keeps nonzero CLI behavior. It is not downgraded into fail-closed dry-run output.

## Consequences

- Later approval and writer slices can treat any top-level graph error as non-writable state.
- Operators get inspectable dry-run output for incomplete required-reviewer runs.
- Optional reviewer failures do not erase useful findings from other reviewers.
- Harnesses must separately cover explicit reviewer failure and invalid fixture/schema behavior.
