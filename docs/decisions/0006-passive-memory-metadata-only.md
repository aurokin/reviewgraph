# Decision 0006: Passive memory is metadata-only in reviewer prompts

## Status

Accepted

## Context

PRD 0010 treats PR conversation as shared graph memory, not as an instruction stream. Trusted actionable comments can improve routing and reviewer context, but untrusted comments, resolved threads, unlisted bot comments, and other passive memory can contain prompt injection, stale feedback, copied secrets, or misleading reviewer pressure.

An earlier design allowed passive memory bodies to appear as labeled prompt data. That proved too weak: even if labeled as passive, a reviewer could paraphrase the content into a finding or clarification request. Deterministic exact-copy checks can catch obvious leaks, but they cannot reliably prove that a verdict-affecting output was not influenced by passive text.

## Decision

In MVP reviewer prompt input, passive or untrusted memory is metadata-only. The prompt data may include memory ID, role, trust label, resolved status, source type, author/path/line metadata, and passive reason, but not the passive body text.

Trusted actionable memory may include body text as labeled data. If a reviewer cites memory as evidence, the raw output must identify `trusted_memory` and concrete actionable `evidence_memory_ids`; unknown, passive, untrusted, or uncited memory evidence is suppressed before rendering.

## Consequences

- Comment injection cannot reach reviewer instructions or reviewer prompt body data through passive memory.
- Reviewers may know passive memory exists, but they cannot quote or reason from its body text until a later explicit quoting policy exists.
- The renderer still protects public candidate payloads from non-actionable memory body overlap as defense in depth.
- A future policy that exposes passive body text needs its own PRD/ADR update and deterministic harnesses for routing, evidence, clarification, redaction, and public payload safety.
