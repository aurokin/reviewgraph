# Product Rules

These are durable product constraints. Implementation details can change; these rules should not change casually.

## Safety rules

1. **Dry-run by default.** The default command must not post comments, submit reviews, edit labels, or mutate GitHub state.
2. **Human approval before write.** GitHub side effects require explicit confirmation after showing the exact payload.
3. **Follow GitHub review semantics.** If ReviewGraph uses GitHub review events, it must match GitHub's behavior for comments, approvals, and requested changes. MVP may recommend a verdict locally without submitting that verdict to GitHub.
4. **No autonomous request-changes.** Submitting a GitHub request-changes review is allowed only when GitHub semantics, ReviewGraph policy, and human approval all permit it. MVP should stop at a local recommendation.
5. **No secret exfiltration.** Diffs, file context, and PR comments may contain secrets or private information. Logs and traces must avoid recording tokens, env values, or private repo content unless the user explicitly enables it.
6. **Explain routing.** Every selected reviewer must include trigger reasons and the review stage that introduced it.
7. **Keep side effects last.** Review generation, ambiguity clarification, rendering, and approval must complete before any GitHub write adapter can be reached.
8. **Bind approval to a target.** Posting approval applies only to the exact review target and payload hash shown to the user. If the PR changes, ReviewGraph must fail closed and re-render.

## Review quality rules

1. Reviewer output must be classified as postable finding, local note, clarification request, or suppressed non-finding before rendering.
2. Postable findings must include priority, severity, confidence, rationale, concrete evidence, and a precise location that overlaps the diff when available.
3. High-severity findings require concrete evidence from the PR context.
4. Weak or speculative findings should be suggestions or local notes, not blocking warnings.
5. Ambiguous findings that would affect mergeability should request human clarification instead of pretending to be certain.
6. Generic findings that could apply to almost any PR should be suppressed.
7. The summary should distinguish blocking issues, clarification requests, local notes, and optional improvements.

## Scope rules

1. MVP reviews PR metadata, changed files, diffs, and available PR comments/review threads. Full repository checkout is a later phase.
2. MVP may print inline-comment candidates but does not need perfect GitHub inline mapping.
3. Live LLM calls are allowed, but deterministic fixture harnesses must exist.
4. Reviewer prompts are configuration-backed and versioned with the repo.
5. Semantic deduplication is deferred unless a deterministic policy is designed and tested.
6. Live LLM calls require explicit opt-in, provider/model disclosure, context minimization, and redaction proof before they are used on private PR content.
