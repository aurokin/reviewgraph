# ISSUE PLAN: AUR-238 Add Fixture Tracer Bullet Golden Run

Historical execution artifact for this issue. Linear remains the durable source for issue status, blockers, and handoff details; if this file conflicts with Linear, Linear wins. Fetch current state from Linear before acting on this plan.

## Linear issue snapshot

- Issue: `AUR-238` / `RG-049: Add Fixture Tracer Bullet Golden Run`
- Milestone: `PRD 0002: MVP Tracer Bullet`
- Status at planning: `In Progress`

## Acceptance criteria mapping

1. Full fixture run path is proved end to end.
   - Evidence target: `tests/test_tracer_fixture_run.py` calls `run_fixture_dry_run(fixture_ref="basic-pr")` and verifies fixture PR loading, memory, stage cursor, context budget/truncation, always-on fake reviewer selection, normalization/classification, local verdict, posting plan, markdown, JSON, and dry-run writer proof.
2. Output includes the durable product fields.
   - Evidence target: structured assertions cover selected reviewer reasons, postable finding, local note, suppressed count, memory IDs/trust/resolution/source metadata, review target metadata, local verdict, candidate posting plan, and candidate payload hashes.
3. Writer branch is unreachable in dry-run mode.
   - Evidence target: a raising writer sentinel is passed to the runner; tests assert zero per-run writer calls and persisted `side_effects.writer_called=false`.
4. Golden output compares stable structure and selected markdown sections, not prompt prose.
   - Evidence target: golden expectations are Python dictionaries/sets/lists inside the tracer test. Markdown checks use section presence and selected bullet snippets only.
5. Raw fake outputs are tied to expected normalized/classified/rendered results.
   - Evidence target: test loads the same fixture through `load_fixture_pr`, asserts raw fake reviewer output IDs/types, then verifies corresponding classified JSON, posting plan items, candidate preview fingerprints/hashes, and rendered markdown sections.
6. Clarification-specific behavior is out of scope here.
   - Evidence target: no new clarification fixture is added in this issue; existing AUR-210 coverage remains the narrow guard for clarification-only CLI behavior.
7. This becomes the demo baseline.
   - Evidence target: `python -m pytest tests/test_tracer_fixture_run.py` is the named harness command and should pass without credentials, network, live LLM, or writer code.

## Scope

This issue owns a golden harness, not a new graph implementation. AUR-210 already created the deterministic fixture CLI/runner path. AUR-238 freezes that path as the first tracer baseline so later reviewer-selection, GitHub-read, and graph-expansion slices can prove they have not regressed the product shape.

Likely files:

- Create: `tests/test_tracer_fixture_run.py`
- Reuse: `src/reviewgraph/fixtures_data/prs/basic-pr.json`
- Reuse: `src/reviewgraph/fixtures_data/reviewer-configs/basic-reviewers.json`
- Reuse: `src/reviewgraph/runner.py`, `src/reviewgraph/fixtures.py`, `src/reviewgraph/render.py`, `src/reviewgraph/posting.py`

## Golden assertions

The harness should assert these stable facts:

- Top-level envelope:
  - `run_mode == "dry_run"`
  - `post_enabled is True`
  - `fixture_id == "basic-pr"`
  - `fixture_ref == "fixture:basic-pr"`
  - `local_verdict == "comment"`
  - `side_effects == {"writer_called": False, "writer_call_count": 0}`
- Stage cursor:
  - before active stage is `None`
  - after active stage is `initial_triage`
  - queue transitions from `["initial_triage", "specialized_review", "logic_review"]` to `["specialized_review", "logic_review"]`
  - transition reason is `start_initial_triage`
- Reviewer selection:
  - selected reviewer is `correctness`
  - selected stage is `initial_triage`
  - reason is `initial_triage triggers.always=true`
- Raw fake output to classified output:
  - fixture raw output contains `finding-cache-stale`, `note-review-size`, and `suppressed-generic-tests`
  - rendered JSON classifies `finding-cache-stale` as `postable_finding`
  - rendered JSON includes one local note and suppressed count `1`
  - postable finding path/line is `src/cache.py:12` and already proves changed-line anchoring through the runner
- Memory/context budget:
  - memory IDs are `mem-trusted` and `mem-untrusted`
  - untrusted memory body is not rendered into public/body JSON
  - truncation includes `resource="patch"` and `truncated=false`
- Posting plan and candidate preview:
  - `finding-cache-stale` is a public `review_body_item`
  - `note-review-size` and `suppressed-generic-tests` are local-only
  - candidate preview kind is `issue_comment`
  - candidate preview has stable hash-shaped `visible_body_hash`, `full_body_hash`, and `findings_hash`
  - candidate preview includes the expected finding fingerprint after renderer redaction policy is applied
- Markdown:
  - contains `# ReviewGraph Dry Run`
  - contains `## Target`, `## Selected Reviewers`, `## Postable Findings`, `## Local Notes`, `## Suppressed Outputs`, `## Memory`, `## Truncation`, `## Posting Plan`, and `## Candidate Payload Preview`
  - contains selected stable snippets such as `Cache miss returns stale data`, `Review size`, `suppressed-generic-tests`, and `issue_comment`
- Redaction:
  - serialized markdown plus top-level and renderer JSON contains no `sk_live`, `ghp_`, `ghs_`, `SECRET_TOKEN`, or private token fragments from the fixture.

## Implementation plan

1. Create `tests/test_tracer_fixture_run.py`.
2. Add helper assertions for:
   - hash-shaped strings (`sha256:` prefix plus digest length);
   - selected markdown sections/snippets;
   - absence of secret-like fixture content.
3. Add `test_basic_fixture_tracer_golden_run()`:
   - load raw fixture via `load_fixture_pr("basic-pr")`;
   - run `run_fixture_dry_run(fixture_ref="basic-pr", writer_sentinel=RaisingWriter())`;
   - compare raw fake output IDs/types to classified/rendered outputs;
   - verify envelope, trace, reviewers, memory, truncation, posting plan, candidate preview, markdown snippets, and side-effect proof.
4. Add `test_basic_fixture_tracer_json_is_stable()` if not redundant:
   - run the fixture twice;
   - compare `json.dumps(result.json_data, sort_keys=True, indent=2)` across runs.
5. Keep existing AUR-210 malformed-input tests in `tests/test_cli.py`; do not duplicate every CLI validation case in this tracer harness.
6. Run validation:
   - `python -m pytest tests/test_tracer_fixture_run.py`
   - `python -m pytest`
   - `python -m py_compile src/reviewgraph/*.py`
   - `python scripts/check_docs.py`
   - `git diff --check`

## Out of scope

- No live GitHub reads.
- No live LLM calls.
- No writer execution.
- No new LangGraph dependency or full graph implementation.
- No clarification resume, ambiguous-logic golden, specialized reviewer golden, stale target proof, or fake writer proof; those belong to later issues.
- No full markdown snapshot or raw prompt text golden.
- No new fixture corpus manifest beyond the packaged fixture registry created by AUR-210.

## Review approach

- Commit this issue plan before implementation.
- Get fresh subagent plan review before implementation.
- Implement the tracer harness after plan review findings are resolved.
- Move `AUR-238` to `In Review` after implementation validation.
- Run fresh code-review subagents until no material findings remain, committing after each review-fix cycle.
