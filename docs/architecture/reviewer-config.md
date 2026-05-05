# Reviewer Configuration

Reviewer agents are configured, not hardcoded.

## Example

```yaml
agents:
  security:
    description: Finds auth, injection, secrets, SSRF, unsafe eval, path traversal.
    triggers:
      paths: ["src/auth/**", "src/api/**", "server/**"]
      diff_patterns: ["password", "token", "jwt", "eval", "exec"]
      risk_min: medium
    required: false
    verdict_power: request_changes

  frontend_state:
    description: Reviews React/Vue state, async flows, loading/error states, UI regressions.
    triggers:
      paths: ["apps/web/**", "src/**/*.tsx", "src/**/*.vue"]
      labels: ["frontend"]
    required: false
    verdict_power: comment

  tests:
    description: Checks test coverage, missing edge cases, and flaky patterns.
    triggers:
      always: true
    required: true
    verdict_power: comment
```

## Trigger fields

- `always`: selects reviewer for every PR.
- `paths`: glob patterns matched against changed file paths.
- `labels`: GitHub labels that select reviewer.
- `diff_patterns`: case-insensitive regex or literal patterns matched against patches.
- `risk_min`: minimum risk assessment required.
- `max_files`: optional cap for noisy reviewers.

## Selection output

Each selected reviewer must produce:

```json
{
  "name": "security",
  "reasons": [
    "changed path matched src/auth/**",
    "diff contained token"
  ]
}
```

## Verdict power

- `comment`: reviewer can produce comments and suggestions only.
- `request_changes`: reviewer can contribute to a request-changes verdict if findings meet policy.
- `approve`: reserved for future use; MVP should not let a single reviewer approve.
