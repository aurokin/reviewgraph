# 0008: Finalization Owns Writer Release

## Status

Accepted.

## Context

PRD 0007 introduces enough GitHub write machinery that future implementation agents could accidentally move policy into the writer adapter: target freshness, actor permission, marker reconciliation, or approved item selection. That would make write safety harder to inspect and would blur the graph boundary that ReviewGraph is meant to demonstrate.

The milestone also adds a real writer adapter contract and a manual live-post smoke. Both are useful only if they preserve dry-run defaults and prove that live writes are reachable through explicit, typed, post-approval state rather than ambient credentials or prompt decisions.

## Decision

`finalize_github_payload` owns the last pre-writer gate. It validates approval shape, approved item IDs, non-empty public findings, duplicate fingerprints, current actor and endpoint permission, current review target freshness, redaction, final payload hash, and marker reconciliation before releasing writer input.

The writer adapter accepts only `FinalizedIssueCommentWriterInput` after marker reconciliation returns `SAFE_TO_POST`. It must not accept candidate payloads, raw final payloads, marker reconciliation plans, approval objects, GitHub read adapters, prompt output, or graph state. It may validate its input and report transport results, but it must not decide which findings are approved, whether target freshness is sufficient, whether a marker is safe to post over, or whether an approval is still valid.

Manual live-post smoke remains a harness boundary, not production posting. It must be opt-in, skipped by default, exact disposable-target allowlisted, TTY/human approved, typed-final-hash confirmed, and backed by post-approval live actor/permission, target freshness, and marker pagination proof before the real writer is reachable.

## Consequences

- Default runs and default tests cannot write to GitHub, require credentials, or require human input.
- Candidate payload models can evolve independently from finalized writer input, but a candidate payload must never become accepted writer input.
- Marker reconciliation is finalization-owned before a write. Writer-local marker scans are allowed only for recovery after an ambiguous accepted-write POST outcome, and they must not issue a second POST in the same approved run/retry sequence.
- The real writer can stay small and transport-focused. Policy regressions should be caught by finalization, marker, fake writer, real writer, and live-post contract harnesses.
- Global cross-process duplicate prevention is still deferred until an external lock or storage design exists.
