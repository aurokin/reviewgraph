# LangGraph State Graph

The core product is the graph. Keep control flow explicit.

## State

```python
class ReviewState(TypedDict):
    run_id: str
    run_mode: Literal["dry_run", "post"]
    post_enabled: bool
    pr_ref: str
    review_target: ReviewTarget
    posting_target: PostingTarget | None
    pr: PullRequestContext | None
    conversation_memory: PRConversationMemory | None
    read_gaps: list[ReadGap]
    config: ReviewConfig
    config_hash: str
    stage_queue: list[ReviewStage]
    active_stage: ReviewStage | None
    suspended_stage: ReviewStage | None
    completed_stages: list[ReviewStage]
    risk: RiskAssessment | None
    selected_reviewers: list[SelectedReviewer]
    reviewer_run_keys: list[ReviewerRunKey]
    reviewer_run_status: dict[str, ReviewerRunStatus]
    reviewer_results: list[ReviewerResult]
    context_budget: ContextBudget
    redaction_status: RedactionStatus | None
    findings: list[Finding]
    local_notes: list[LocalNote]
    suggested_replies: list[SuggestedReply]
    suppressed_outputs: list[SuppressedReviewerOutput]
    clarification_requests: list[ClarificationRequest]
    pending_clarification_ids: list[str]
    clarifications: list[ClarificationAnswer]
    clarification_status: dict[str, ClarificationStatus]
    ranked_findings: list[Finding]
    local_verdict: ReviewVerdict | None
    rendered_markdown: str | None
    posting_plan: PostingPlan | None
    actor_permission_gate: ActorPermissionGateResult | None
    payload_validation: PayloadValidationResult | None
    marker_reconciliation: MarkerReconciliationResult | None
    finalization_status: FinalizationStatus | None
    candidate_github_payload: GitHubReviewPayload | None
    final_github_payload: GitHubReviewPayload | None
    candidate_payload_hash: str | None
    final_payload_hash: str | None
    approval: ApprovalDecision | None
    writer_result: GitHubWriterResult | None
    errors: list[GraphError]
```

## Nodes

1. `fetch_pr_context`
2. `build_conversation_memory`
3. `resolve_review_target`
4. `calculate_context_budget`
5. `classify_change_risk`
6. `select_reviewers`
7. `run_reviewers`
8. `normalize_reviewer_output`
9. `classify_review_quality`
10. `clarification_gate`
11. `advance_or_finish_stage`
12. `rank_findings`
13. `decide_local_verdict`
14. `build_posting_plan`
15. `render_review`
16. `ingest_clarification_answer`
17. `approval_gate`
18. `finalize_github_payload`
19. `post_or_emit`

## Routing

```text
START
  -> fetch_pr_context
  -> build_conversation_memory
  -> resolve_review_target
  -> calculate_context_budget
  -> classify_change_risk
  -> advance_or_finish_stage
  -> select_reviewers
  -> run_reviewers
  -> normalize_reviewer_output
  -> classify_review_quality
  -> clarification_gate
      clarification needed -> END with human question or resume after answer
      no clarification needed -> advance_or_finish_stage
  -> advance_or_finish_stage
      next review stage -> select_reviewers
      final synthesis -> rank_findings
  -> decide_local_verdict
  -> build_posting_plan
  -> render_review
      run_mode dry_run or post_enabled false -> post_or_emit dry-run
      run_mode post and post_enabled true -> approval_gate
  -> approval_gate
      approved -> finalize_github_payload
      rejected -> END with dry-run output
  -> finalize_github_payload
      hash/target/permission valid -> post_or_emit
      invalid -> END with dry-run output and error
  -> END
```

## Review target

Every run is bound to an immutable review target before reviewer execution. For a GitHub PR, the target includes owner/repo, PR number, base SHA, head SHA, merge-base SHA when available, and the diff basis used for findings. Rendered output and every postable finding should reference this target.

Before any GitHub write, `finalize_github_payload` must re-fetch the PR head/base/merge-base state and compare it to the approved review target. If the target changed after rendering or approval, the graph fails closed and emits a new dry-run result instead of posting. `post_or_emit` receives only an already-finalized payload or dry-run output; it does not own freshness, approval, or hash policy.

## Staged reviewer introduction

Valid MVP `ReviewStage` values are:

- `initial_triage`
- `specialized_review`
- `logic_review`
- `clarification_review`

Stage cursor invariant:

- `active_stage` is the current stage, or `None` before the first stage and after all stages complete.
- `stage_queue` contains only future normal stages, never the active stage.
- `completed_stages` contains only normal stages that finished all selected reviewers.
- `clarification_review` is a transient non-queue stage.

The normal initial state is:

```json
{
  "active_stage": null,
  "stage_queue": ["initial_triage", "specialized_review", "logic_review"],
  "completed_stages": []
}
```

The first call to `advance_or_finish_stage` moves `initial_triage` from `stage_queue` into `active_stage`. Later calls mark the current normal stage complete, append it to `completed_stages`, and move the next queued stage into `active_stage`. `clarification_review` is not part of the normal queue. `ingest_clarification_answer` schedules a clarification resume; only `advance_or_finish_stage` activates `clarification_review`.

Reviewer selection may happen more than once as state changes. Examples:

- `initial_triage`: always-on correctness and tests reviewers inspect the change shape.
- `specialized_review`: path, label, risk, or diff triggers introduce focused reviewers.
- `logic_review`: reviewers inspect cross-file reasoning, invariants, and product behavior when the diff suggests non-local risk. Postable logic findings still need changed-line anchoring and concrete evidence; unclear intent becomes a clarification request.
- `clarification_review`: reviewers that raised material ambiguity can ask a human for context before making a mergeability recommendation.

Each selected reviewer must record the stage and trigger reasons in state.

`select_reviewers` must use `ReviewerRunKey` for idempotence and resume safety:

```json
{
  "target_hash": "sha256:...",
  "config_hash": "sha256:...",
  "stage": "logic_review",
  "reviewer": "logic",
  "attempt": 1,
  "retry_of": null,
  "clarification_id": null
}
```

A reviewer is skipped when the key is already completed for the current review target/config, retried only under the explicit retry policy, and failed permanently after retry exhaustion. `advance_or_finish_stage` is the only node allowed to mutate `active_stage`, `suspended_stage`, `stage_queue`, or `completed_stages`.

`reviewer_run_status` is keyed by a stable serialization of `ReviewerRunKey` and must distinguish `selected`, `running`, `completed`, `failed`, and `skipped`. Selection may not skip a reviewer merely because a key was selected; only `completed` and policy-approved `skipped` statuses suppress execution.

## Clarification resume

Clarification requests are addressable state, not prose-only output. Each request has an ID, source reviewer, source stage, source run key, status, and resume target. A resumed run follows:

```text
ingest_clarification_answer
  -> advance_or_finish_stage
      enter clarification_review -> select_reviewers
  -> run_reviewers
  -> normalize_reviewer_output
  -> classify_review_quality
  -> clarification_gate
  -> advance_or_finish_stage
```

On resume, `ingest_clarification_answer` records the answer, changes the clarification status from `pending` to `answered`, removes the ID from `pending_clarification_ids`, and records the ID for the next clarification run, but it does not mutate stage cursor fields. The next `advance_or_finish_stage` stores the prior normal stage in `suspended_stage`, sets `active_stage` to `clarification_review`, and routes to `select_reviewers`. The resumed `ReviewerRunKey` includes the answered clarification ID, and `select_reviewers` runs only the affected reviewer(s). After `clarification_gate` passes, `advance_or_finish_stage` treats `clarification_review` as non-queue work: it restores `active_stage` from `suspended_stage`, clears `suspended_stage`, marks the clarification `in_review` or `resolved` according to reviewer output, and then completes or continues that source stage according to the source stage's reviewer statuses. It must not pop an unrelated queued stage or restart unrelated completed stages.

Graph traces should record `active_stage_before`, `active_stage_after`, `suspended_stage_before`, `suspended_stage_after`, `stage_queue_before`, `stage_queue_after`, and `transition_reason` for each cursor transition.

Unanswered clarification requests keep `post_enabled` false. A timeout or rejected clarification can produce local notes, but cannot produce a high-confidence blocking verdict for the ambiguous issue.

## Final payload

`approval_gate` records approved item IDs and approval metadata only, including the GitHub actor and permission snapshot shown to the human approver. `finalize_github_payload` builds the final issue-comment body from approved item IDs, computes the final hash, verifies it matches `approval.approved_final_payload_hash`, verifies the current GitHub actor still matches the approved actor, verifies permission and full review target freshness, verifies redaction status, and only then allows `post_or_emit` to call the writer.

The writer adapter receives a finalized top-level issue-comment payload plus a marker reconciliation plan. It must not perform its own policy decisions beyond transport errors and marker reconciliation.

## Error handling

- GitHub fetch failure -> terminal error with no review.
- One reviewer failure -> record error and continue unless required reviewer failed.
- Invalid reviewer JSON -> retry once with repair prompt, then record error.
- Quality classification failure -> fall back to local notes, not postable findings.
- Ranking failure -> fall back to quality-classified postable findings and mark the summary as lower confidence.
- Clarification timeout/rejection -> no GitHub side effect and no high-confidence blocking verdict from the ambiguous issue.
- Approval timeout/rejection -> no GitHub side effect.
- Target SHA drift before posting -> no GitHub side effect; emit stale-approval error and dry-run output.

## Principle

Prompts can reason, but graph nodes decide. Do not let a free-form LLM response secretly choose whether to post, request changes, skip approval, or introduce a new reviewer without recording that routing decision in state.
