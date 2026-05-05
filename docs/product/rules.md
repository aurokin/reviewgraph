# Product Rules

These are durable product constraints. Implementation details can change; these rules should not change casually.

## Safety rules

1. **Dry-run by default.** The default command must not post comments, submit reviews, edit labels, or mutate GitHub state.
2. **Human approval before write.** GitHub side effects require explicit confirmation after showing the exact payload.
3. **No autonomous request-changes.** Requesting changes is allowed only when both policy and human approval permit it.
4. **No secret exfiltration.** Diffs and file context may contain secrets. Logs and traces must avoid recording tokens, env values, or private repo content unless the user explicitly enables it.
5. **Explain routing.** Every selected reviewer must include trigger reasons.

## Review quality rules

1. Findings must include severity, confidence, rationale, location when available, and suggested fix.
2. High-severity findings require concrete evidence from the PR context.
3. Weak or speculative findings should be suggestions, not blocking warnings.
4. Duplicate findings must be merged before summary output.
5. The summary should distinguish blocking issues from optional improvements.

## Scope rules

1. MVP reviews PR metadata, changed files, and diffs. Full repository checkout is a later phase.
2. MVP may print inline-comment candidates but does not need perfect GitHub inline mapping.
3. Live LLM calls are allowed, but deterministic fixture harnesses must exist.
4. Reviewer prompts are configuration-backed and versioned with the repo.
