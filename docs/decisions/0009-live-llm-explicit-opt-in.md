# Live LLM Requires Explicit Run-Level Opt-In

## Decision

Live LLM execution requires explicit run-level opt-in in addition to any reviewer config, model metadata, live provider settings, or injected transport.

## Context

Reviewer config needs to carry provider and model metadata so ReviewGraph can explain selected agents and produce stable audit records. That metadata is useful before live execution exists, but it is not enough to justify sending private PR content to an external provider.

## Consequences

- Fake reviewers remain the default for fixture runs, GitHub dry-runs, and the default test matrix.
- Public CLI live execution requires `--live-llm`, provider, model, and a positive live-call budget before lazy-loading the live HTTP transport.
- The runner requires a separate opt-in source and injected transport; either one alone fails closed.
- Live policy records provider/model, opt-in source, request hash, byte count, budget reservation, redaction status, and package fingerprint without persisting raw request text by default.
- Retry attempts are graph-visible reviewer runs with distinct run keys and fresh live-call reservations.
- Future tool-using or repository-reading agents need their own explicit capability and opt-in policies.
