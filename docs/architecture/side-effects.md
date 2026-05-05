# Side-Effect Boundaries

The most important production boundary is between review generation and GitHub mutation.

## Rule

The graph may prepare a GitHub payload, but only the side-effect adapter may post it.

## Approval contract

The approval gate receives:

- rendered markdown
- JSON findings
- recommended verdict
- exact GitHub payload

It returns:

```json
{
  "approved": true,
  "mode": "post_comment",
  "approved_by": "local-user",
  "timestamp": "..."
}
```

## Non-interactive mode

In CI or webhook mode, MVP should refuse posting unless an explicit future policy is designed. Do not infer approval from config alone.
