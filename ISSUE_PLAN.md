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
  - rendered JSON exact selected finding fields match fixture expectations: `id`, `source_reviewer`, `source_stage`, `classification`, `priority`, `severity`, `confidence`, `title`, redacted `body`, `evidence`, `path`, `line`, and `fingerprint`
  - rendered JSON exact selected local-note fields match fixture expectations: `id`, `classification`, `title`, `body`, and `evidence`
  - rendered JSON exact selected suppressed-output fields match fixture expectations, and `suppressed_count == 1`
  - rendered JSON includes empty `clarification_requests` and `suggested_replies` arrays so the durable output shape distinguishes these categories even when the baseline has none
  - postable finding path/line is `src/cache.py:12` and already proves changed-line anchoring through the runner
- Memory/context budget:
  - memory IDs are `mem-trusted` and `mem-untrusted`
  - untrusted memory body is not rendered into public/body JSON
  - truncation includes `resource="patch"` and `truncated=false`
- Review target metadata:
  - exact target metadata is asserted in `review.review_target`
  - exact target metadata is asserted again in `candidate_payload_preview.review_target`
  - expected target is `owner_repo="acme/widgets"`, `pr_number=42`, `base_sha="base123"`, `head_sha="head456"`, `merge_base_sha="merge789"`, and `diff_basis="merge_base"`
- Posting plan and candidate preview:
  - exact selected posting-plan item fields are asserted for `finding-cache-stale`, `note-review-size`, and `suppressed-generic-tests`
  - candidate preview kind is `issue_comment`
  - candidate preview body contains the expected fixture finding text after redaction
  - candidate preview `visible_body_hash`, `full_body_hash`, and `findings_hash` are recomputed from the rendered body/fingerprint using posting helpers and must match exactly
  - candidate preview `item_fingerprints == ["fixture-basic-cache-stale"]`
- Markdown:
  - contains `# ReviewGraph Dry Run`
  - contains `## Target`, `## Selected Reviewers`, `## Postable Findings`, `## Local Notes`, `## Clarification Requests`, `## Suggested Replies`, `## Suppressed Outputs`, `## Memory`, `## Truncation`, `## Posting Plan`, and `## Candidate Payload Preview`
  - contains selected stable snippets such as `Cache miss returns stale data`, `Review size`, `suppressed-generic-tests`, and `issue_comment`
- Redaction:
  - serialized markdown plus top-level and renderer JSON contains no `sk_live`, `ghp_`, `ghs_`, `SECRET_TOKEN`, or private token fragments from the fixture.
- Fixture registry:
  - the `basic-pr` manifest entry lists both `tests/test_cli.py` and `tests/test_tracer_fixture_run.py` in `consumed_by`.

## Implementation plan

1. Create `tests/test_tracer_fixture_run.py`.
2. Add helper assertions for:
   - hash-shaped strings (`sha256:` prefix plus digest length);
   - selected markdown sections/snippets;
   - absence of secret-like fixture content.
3. Add `test_basic_fixture_tracer_golden_run()`:
   - load raw fixture via `load_fixture_pr("basic-pr")`;
   - run `run_fixture_dry_run(fixture_ref="basic-pr", writer_sentinel=RaisingWriter())`;
   - compare raw fake output IDs/types and exact selected machine fields to classified/rendered outputs;
   - verify exact target metadata, envelope, trace, reviewers, memory, truncation, posting plan, recomputed candidate preview hashes/body/fingerprints, empty output categories, markdown snippets, and side-effect proof.
4. Update `src/reviewgraph/fixtures_data/manifest.json` so `basic-pr.consumed_by` includes `tests/test_tracer_fixture_run.py`.
5. Add `test_basic_fixture_tracer_json_is_stable()` if not redundant:
   - run the fixture twice;
   - compare `json.dumps(result.json_data, sort_keys=True, indent=2)` across runs.
6. Keep existing AUR-210 malformed-input tests in `tests/test_cli.py`; do not duplicate every CLI validation case in this tracer harness.
7. Run validation:
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
