# PRD 0008: Live LLM

## Problem Statement

Live LLM review is useful but risky. PR diffs and comments can contain private code, secrets, and sensitive discussion. Live calls also introduce cost, nondeterminism, and provider-specific behavior.

## Solution

Keep fake reviewers as the default. Add live LLM support only behind explicit opt-in, context minimization, provider/model disclosure, redaction, bounded context budgets, and deterministic adapter boundaries.

## User Stories

1. As a developer, I want fake reviewers by default, so that tests are deterministic.
2. As a maintainer, I want explicit live LLM opt-in, so that private PR content is not sent accidentally.
3. As a maintainer, I want provider and model disclosed, so that I know where data goes.
4. As a maintainer, I want context minimized per reviewer, so that each reviewer receives only relevant data.
5. As a maintainer, I want secrets redacted from outputs and traces, so that review artifacts do not leak credentials.
6. As a developer, I want live-call caps, so that a large PR cannot trigger unbounded model usage.
7. As a developer, I want truncation markers visible to reviewers, so that missing context affects confidence.
8. As a developer, I want provider/model recorded in state, so that runs are auditable.

## Implementation Decisions

- Live LLM requires an explicit flag such as `--live-llm`.
- The run records provider, model, reviewer, target, context policy, and truncation status.
- MVP reviewer capability is `diff_context`.
- Later capabilities such as `github_read`, `read_repo`, and `run_tests` require separate policies.
- Context budgets cap files, patch bytes, conversation memory bytes, reviewer count, and live calls.
- Logs, traces, rendered markdown, candidate/final GitHub payloads, JSON errors, and default JSON output must redact token-like values.
- Private repo raw-content tracing is disabled by default.

## Testing Decisions

- Fake adapter remains default in all non-live tests.
- Redaction fixtures include token-like values in diffs and comments.
- Tests assert rendered markdown and candidate/final payloads are redacted.
- Tests assert provider/model are recorded when live mode is enabled.
- Tests assert live-call caps skip/defer reviewers deterministically and emit local notes.
- Live LLM smoke tests are opt-in.

## Implemented Slice

The implemented PRD 0008 slice keeps fake reviewers as the default and adds live LLM execution only when a run provides explicit opt-in, provider, model, live-call budget, and a provider transport. The public CLI lazy-loads the HTTP transport only after `--live-llm` validation passes; config metadata or a transport handle alone cannot send PR content to a provider.

Live policy owns request minimization, redaction, provider/model audit, run-level opt-in proof, package fingerprinting, request hashing, byte counts, live-call reservations, and retry attempt identity. Live adapter evidence is typed and redacted; raw provider responses and request text are not persisted in default output. Provider failures, malformed responses, retry exhaustion, total-timeout caps, and budget exhaustion map into required/optional reviewer semantics without creating postable findings by themselves.

## Out of Scope

- Tool-using live reviewer agents.
- Repository checkout.
- Test execution.
- Provider-specific prompt optimization beyond the shared contract.

## Further Notes

Live LLM support should come after the quality classifier and redaction tests. Otherwise live review can generate plausible output that cannot be safely rendered or posted.
