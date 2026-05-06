# ReviewGraph

ReviewGraph is a LangGraph-powered PR review orchestrator for staged, multi-agent code and logic review workflows.

The project is intentionally documentation-first. The first implementation should preserve the product contracts, harness strategy, and side-effect boundaries described in `docs/` before adding code.

## Product one-liner

ReviewGraph reads GitHub pull requests, uses the PR conversation as shared review memory, introduces reviewer agents under explicit graph conditions, runs targeted review stages, and gates GitHub writes behind human approval.

## Current runnable slice

The current implementation includes the PRD 0002 fixture tracer bullet, the PRD 0010 reviewer-context boundary harness, and the PRD 0004 graph-orchestration slice. It does not perform live GitHub reads, live LLM calls, approval, or posting. It proves the dry-run product shape with packaged fixtures, staged reviewer selection, deterministic risk/size routing, reviewer run status, deterministic fake reviewer output, required-reviewer fail-closed behavior, scoped reviewer context packages, passive/trusted PR memory labeling, and non-live provider request previews:

```bash
PYTHONPATH=src python -m reviewgraph.cli --fixture-pr basic-pr --print-markdown
```

Useful validation commands:

```bash
python -m pytest tests/test_tracer_fixture_run.py
python -m pytest tests/test_stage_cursor.py tests/test_routing.py tests/test_reviewer_runs.py
python -m pytest tests/test_reviewer_context.py tests/test_prompt_injection_memory.py
python -m pytest
python scripts/check_docs.py
```

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

Fixture dry-run tracer, context budgeting, reviewer context package, inert reviewer tool metadata, passive-memory prompt boundaries, prompt-injection memory harness, provider preview redaction, staged reviewer selection, deterministic risk/size gates, reviewer run status, fake reviewer execution, required-reviewer fail-closed dry-run output, clarification stop/resume primitives, and side-effect import boundaries are implemented. Live GitHub reads, live LLM reviewers, approval finalization, and GitHub writers are still future milestones.
