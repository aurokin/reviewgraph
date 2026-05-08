# ReviewGraph

ReviewGraph is a LangGraph-powered PR review orchestrator for staged, multi-agent code and logic review workflows.

The project is intentionally documentation-first. The first implementation should preserve the product contracts, harness strategy, and side-effect boundaries described in `docs/` before adding code.

## Product one-liner

ReviewGraph reads GitHub pull requests, uses the PR conversation as shared review memory, introduces reviewer agents under explicit graph conditions, runs targeted review stages, and gates GitHub writes behind human approval.

## Current runnable slice

The current implementation includes the PRD 0002 fixture tracer bullet, the PRD 0010 reviewer-context boundary harness, the PRD 0004 graph-orchestration slice, the PRD 0005 review-quality slice, the PRD 0006 GitHub read/memory slice, PRD 0007 side-effect contracts through fake/default-safe harnesses, and PRD 0008 live LLM policy plus an explicit opt-in live-adapter path. It does not perform production live GitHub review, public production posting, or default live GitHub writes. It proves the dry-run product shape with packaged fixtures, staged reviewer selection, deterministic risk/size routing, reviewer run status, deterministic fake reviewer output, scoped reviewer context packages, passive/trusted PR memory labeling, non-live provider request previews, strict reviewer-output normalization and repair, quality classification, diff anchors, clarification stop/resume, optional failure continuation, private local verdict policy, fake paginated GitHub PR reads, fail-closed read gaps, GitHub conversation trust rules, trusted-memory reviewer routing, GitHub PR dry-run, approval/finalization gates, marker reconciliation, fake post-mode writer proof, real writer adapter contract tests with fake transports only, opt-in read-only live smoke harnesses, injected fake-provider live LLM adapter tests, and a manual-only disposable live-post smoke contract that is skipped by default:

```bash
PYTHONPATH=src python -m reviewgraph.cli --fixture-pr basic-pr --print-markdown
```

Useful validation commands:

```bash
python -m pytest tests/test_tracer_fixture_run.py
python -m pytest tests/test_stage_cursor.py tests/test_routing.py tests/test_reviewer_runs.py
python -m pytest tests/test_reviewer_context.py tests/test_prompt_injection_memory.py
python -m pytest tests/test_findings.py tests/test_reviewer_json_repair.py tests/test_quality.py tests/test_diff_anchor.py tests/test_quality_testing.py tests/test_clarification.py tests/test_clarification_resume.py tests/test_optional_reviewer_failure.py tests/test_verdict.py -q
python -m pytest tests/test_github_fake_read.py tests/test_github_read_gaps.py tests/test_github_pagination.py tests/test_github_memory_trust.py tests/test_conversation_routing.py tests/test_github_dry_run_cli.py tests/test_live_read_smoke.py -q
python -m pytest tests/test_llm_policy.py tests/test_adapter_boundaries.py tests/test_live_llm_adapter.py -q
python -m pytest tests/test_live_post_contract.py -q
python -m pytest
python scripts/check_docs.py
```

## Side-effect status

Default commands remain non-mutating. The public CLI exposes fixture and GitHub dry-run review only; production posting is still future work.

Implemented PRD 0007 code is a proof boundary, not a public posting feature:

- candidate payloads are render/approval inputs, never writer inputs;
- finalization owns approval shape, approved item IDs, current actor/permission, target freshness, final payload hash, redaction, marker reconciliation, and writer release;
- the fake writer proves the allowed post route without GitHub;
- the real writer adapter is contract-tested with fake transports and accepts only finalized top-level issue-comment input;
- the manual live-post smoke is library-level, skipped by default, disposable-target-only, and requires human TTY approval plus typed final-hash confirmation.

Agents changing side-effect code should start with [Side-Effect Boundaries](docs/architecture/side-effects.md), [GitHub Integration](docs/architecture/github-integration.md), and [Harness Engineering](docs/harnesses/harness-engineering.md#prd-0007-validation).

Packaged fixture IDs currently cover:

- `basic-pr`: normal fixture dry run with a postable finding, local note, suppressed output, memory, redaction, posting plan, and no-writer proof.
- `specialized-review-pr`: path-triggered `specialized_review` reviewer introduction.
- `ambiguous-logic-pr`: diff-pattern-triggered `logic_review` clarification path that disables posting.

## Start here

Read in this order:

1. [Product Vision](docs/product/vision.md)
2. [Product Rules](docs/product/rules.md)
3. [Architecture Overview](docs/architecture/overview.md)
4. [State Graph](docs/architecture/state-graph.md)
5. [Review Quality](docs/architecture/review-quality.md)
6. [LLM Data Handling](docs/architecture/llm-data-handling.md)
7. [Reviewer Configuration](docs/architecture/reviewer-config.md)
8. [PRDs](docs/prds/README.md)
9. [Harness Engineering](docs/harnesses/harness-engineering.md)
10. [Implementation Plan](docs/plans/implementation-plan.md)

## Intended MVP

- CLI accepts a GitHub PR URL or `owner/repo#number`.
- Fetches PR metadata, changed files, diff, comments, and review threads where available.
- Loads `review_agents.yaml`.
- Selects relevant reviewer agents with explainable trigger reasons.
- Runs selected reviewers through encapsulated contexts, with fake reviewers available for deterministic harnesses.
- Classifies reviewer output into postable findings, local notes, clarification requests, and suppressed non-findings.
- Normalizes, ranks, and summarizes review output.
- Lets a human approve the exact postable items before any GitHub write.
- Emits markdown and JSON output.
- Runs dry by default; posting to GitHub requires explicit human approval.

## Out of scope for MVP

- Always-on GitHub App/webhook deployment.
- Auto-requesting changes without approval.
- Inline comments with perfect diff-line mapping.
- Repository checkout and full test execution.
- Formal GitHub review submission.
- Semantic deduplication across unrelated reviewer contexts.
- Long-term storage, dashboard UI, billing, teams, or hosted product features.

## Repository status

Fixture dry-run tracer, context budgeting, reviewer context package, inert reviewer tool metadata, passive-memory prompt boundaries, prompt-injection memory harness, provider preview redaction, staged reviewer selection, deterministic risk/size gates, reviewer run status, fake reviewer execution, review-quality classification, deterministic malformed-output repair, dry-run diff anchors, testing-feedback quality rules, required-reviewer fail-closed dry-run output, optional-reviewer partial-review metadata, clarification stop/resume primitives, private local verdict policy, side-effect import boundaries, fake paginated GitHub reads, GitHub read-gap fail-closed envelopes, GitHub memory trust/seen-state rules, conversation-pattern routing from trusted actionable memory, GitHub PR fake-read dry-run, approval/finalization gates, marker reconciliation, fake writer/post-mode harnesses, real top-level issue-comment writer adapter contract tests with fake transports, skipped-by-default live-read smoke boundaries, live LLM policy/adapter contracts with fake provider transports, and skipped-by-default manual live-post contract tests are implemented. Production live GitHub review, public production posting, and default live GitHub writes are still future milestones.
