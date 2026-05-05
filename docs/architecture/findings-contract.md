# Findings Contract

Reviewers return structured findings. Markdown is rendered later.

## Finding schema

```json
{
  "id": "stable-or-generated-id",
  "reviewer": "security",
  "severity": "critical | warning | suggestion | nit",
  "confidence": "high | medium | low",
  "path": "src/example.ts",
  "line": 42,
  "title": "User-controlled path reaches file read",
  "rationale": "The new code joins user input into a filesystem path without normalization.",
  "evidence": "diff excerpt or PR context reference",
  "suggested_fix": "Normalize and validate path under an allowed root before reading.",
  "blocking": true
}
```

## Severity policy

- `critical`: security, data loss, auth bypass, or severe correctness issue with high confidence.
- `warning`: should fix before merge, but not catastrophic.
- `suggestion`: useful improvement, not blocking.
- `nit`: tiny style/readability issue; should be rare.

## Confidence policy

- `high`: directly supported by diff or surrounding context.
- `medium`: likely issue but needs maintainer judgment.
- `low`: speculative; cannot block.

## Dedupe policy

Merge findings when they share the same root cause even if multiple reviewers found them. Preserve reviewer names in merged metadata.
