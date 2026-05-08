# LLM Data Handling

Live LLM review is opt-in. Fixture and fake reviewer paths must remain the default development and test path.

## Live opt-in

The CLI must require an explicit live flag before sending PR content to an LLM provider, for example `--live-llm`. Dry-run output should disclose:

- provider
- model
- reviewer name
- review target
- context policy
- whether truncation occurred

`llm_policy` is the canonical provider-execution gate. A future live adapter must pass a `ReviewerContextPackage` plus explicit run-level policy input through that gate before invoking any provider transport. Config metadata such as `model` never enables live calls by itself; missing live opt-in, opt-in proof source, provider, or explicit policy model fails closed. The reviewer run key must also match the context package target, active stage, selected-reviewer stage, and reviewer name before request construction or budget reservation can pass.

Passing policy decisions reserve live-call budget before provider execution. Reservations are keyed by reviewer run identity plus target/config/provider/model/request hash. Repeating the same reviewer run with the same request hash reuses the existing reservation; repeating it with different request data fails closed. Retry attempts and clarification-bound runs have distinct reviewer run keys and consume fresh budget.

## Context minimization

Each reviewer receives the smallest context needed for its job:

- `diff_context`: PR metadata, changed-file list, bounded patch snippets, and trusted conversation memory.
- `github_read`: later phase; may fetch additional GitHub file or discussion context.
- `read_repo`: later phase; requires checkout/sandbox policy.
- `run_tests`: later phase; requires checkout/sandbox policy and explicit command contract.

MVP reviewer configs should use only `none` or `diff_context`.

## Redaction

Logs, traces, errors, rendered markdown, candidate GitHub payloads, final GitHub payloads, and default JSON output must redact token-like values from all external PR text fields, including PR title/body, labels when rendered, changed-file patches, issue comments, review summaries, review comments, and thread bodies. Private repo content should not be persisted in traces unless the user explicitly enables raw-content tracing.

Live LLM request payloads must also pass through the context minimization and redaction policy before provider submission. If a future mode permits raw provider submission, it must require an explicit human opt-in and the run must record that raw submission was enabled. The default behavior is redacted provider-bound context.

Raw provider submission and raw trace persistence are separate decisions. A run may not infer one from the other. Redaction proof for future adapters should record the surface, redaction status, and distinct `raw_provider_submission_enabled` and `raw_trace_persistence_enabled` flags.

Policy results separate in-memory execution data from default-persisted audit data. The provider execution plan may hold the explicit provider/model and redacted provider request text only long enough for immediate submission. Default JSON/audit output records redacted provider/model display values, reviewer, target, context policy, retained file paths, retained memory IDs, omitted-context markers, truncation notices, redaction status, request hash, byte count, raw opt-in proof source, and budget before/after counts; audit metadata is redacted before serialization. Policy audit objects do not retain request text unless raw trace persistence is explicitly approved.

Provider transport failures must become typed, redacted summaries with stable reason codes. Missing credentials, timeout, rate limit, retry exhaustion, malformed response, unavailable provider, and unknown provider errors cannot create postable findings by themselves.

Required redaction targets include:

- API keys and bearer tokens
- GitHub tokens
- private keys
- `.env`-style assignments
- authorization headers

## Harness

Tests should include fixture PR titles, PR bodies, diffs, review summaries, review comments, and PR comments containing token-like values and prove that provider-bound live LLM payloads, logs, traces, rendered markdown, candidate/final GitHub payloads, JSON error payloads, and default output redact them.
