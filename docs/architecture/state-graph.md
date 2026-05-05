# LangGraph State Graph

The core product is the graph. Keep control flow explicit.

## State

```python
class ReviewState(TypedDict):
    pr_ref: str
    pr: PullRequestContext | None
    config: ReviewConfig
    risk: RiskAssessment | None
    selected_reviewers: list[SelectedReviewer]
    reviewer_results: list[ReviewerResult]
    findings: list[Finding]
    deduped_findings: list[Finding]
    verdict: ReviewVerdict | None
    rendered_markdown: str | None
    github_payload: GitHubReviewPayload | None
    approval: ApprovalDecision | None
    errors: list[GraphError]
```

## Nodes

1. `fetch_pr_context`
2. `classify_change_risk`
3. `select_reviewers`
4. `run_reviewers`
5. `normalize_findings`
6. `dedupe_and_rank`
7. `decide_verdict`
8. `render_review`
9. `approval_gate`
10. `post_or_emit`

## Routing

```text
START
  -> fetch_pr_context
  -> classify_change_risk
  -> select_reviewers
  -> run_reviewers
  -> normalize_findings
  -> dedupe_and_rank
  -> decide_verdict
  -> render_review
  -> approval_gate
      approved + post enabled -> post_or_emit
      rejected -> END with dry-run output
      needs_revision -> run_reviewers or render_review depending on reason
  -> END
```

## Error handling

- GitHub fetch failure -> terminal error with no review.
- One reviewer failure -> record error and continue unless required reviewer failed.
- Invalid reviewer JSON -> retry once with repair prompt, then record error.
- Dedupe failure -> fall back to normalized findings and mark confidence lower.
- Approval timeout/rejection -> no GitHub side effect.

## Principle

Prompts can reason, but graph nodes decide. Do not let a free-form LLM response secretly choose whether to post, request changes, or skip approval.
