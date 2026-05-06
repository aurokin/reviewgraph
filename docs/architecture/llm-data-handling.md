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

Required redaction targets include:

- API keys and bearer tokens
- GitHub tokens
- private keys
- `.env`-style assignments
- authorization headers

## Harness

Tests should include fixture PR titles, PR bodies, diffs, review summaries, review comments, and PR comments containing token-like values and prove that provider-bound live LLM payloads, logs, traces, rendered markdown, candidate/final GitHub payloads, JSON error payloads, and default output redact them.
