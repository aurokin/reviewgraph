# ISSUE PLAN: AUR-210 Add Fixture Dry-Run CLI

Historical execution artifact for this issue. Linear remains the durable source for issue status, blockers, and handoff details; if this file conflicts with Linear, Linear wins. Fetch current state from Linear before acting on this plan.

## Linear issue snapshot

- Issue: `AUR-210` / `RG-021: Add Fixture Dry-Run CLI`
- Milestone: `PRD 0002: MVP Tracer Bullet`
- Status at planning: `In Progress`

## Acceptance criteria mapping

1. CLI accepts a fixture PR reference.
   - Evidence target: `python -m reviewgraph.cli --fixture-pr <path-or-id>` resolves a deterministic fixture PR from a package fixture registry or explicit JSON file path.
2. CLI loads reviewer config.
   - Evidence target: CLI accepts `--reviewer-config <path>` and validates the minimal MVP fields needed to select fixture reviewers. The default fixture config is local and deterministic.
3. CLI outputs markdown and JSON.
   - Evidence target: CLI can write markdown and JSON to explicit paths and can print markdown to stdout for quick demo use. JSON is a stable top-level run envelope containing `run_mode`, `side_effects`, graph trace, and nested renderer output.
4. CLI defaults to dry-run and cannot reach writer code.
   - Evidence target: run mode defaults to `dry_run`; no `--post` mode exists in this issue; a writer sentinel object is installed in the fixture runner; tests assert it is not called and the persisted CLI JSON records `side_effects.writer_called=false`.
5. CLI exits non-zero for invalid config or fixture.
   - Evidence target: tests call the CLI entrypoint with malformed fixture/config inputs and assert non-zero return plus actionable stderr.

## Minimal foundation ownership

This issue owns only the thin runner/CLI needed by `AUR-238`:

- `src/reviewgraph/fixtures.py` or equivalent fixture-loading module.
- `src/reviewgraph/runner.py` or equivalent deterministic fixture dry-run orchestration.
- `src/reviewgraph/cli.py` with a pure `main(argv)` entrypoint and module execution support.
- package fixture/config files under `src/reviewgraph/fixtures_data/` so fixture IDs work from a normal checkout/package import.
- `pyproject.toml` package-data configuration for fixture JSON files.
- `tests/test_cli.py` plus malformed test-only fixture/config files under `tests/fixtures/` as needed.

The issue may add small shared models only when needed to describe the fixture run result or writer sentinel. It should reuse `ReviewTarget`, `SelectedReviewer`, `MemoryReference`, `ClassifiedFinding`, `LocalNote`, `ClarificationRequest`, `SuggestedReply`, `SuppressedOutput`, `TruncationNotice`, `build_posting_plan`, `build_candidate_issue_comment_payload`, and `render_review`.

## Fixture/runner contract

The fixture runner should be intentionally boring:

1. Load fixture PR JSON containing:
   - fixture ID, PR reference, owner/repo, PR number, base/head/merge-base SHAs, diff basis;
   - changed files with explicit changed-line ranges or hunk metadata sufficient to prove postable findings overlap changed code;
   - memory references with trust/resolution/source/body metadata;
   - optional truncation notice data;
   - deterministic raw fake reviewer outputs, separate from classified output.
2. Load a minimal reviewer config containing at least one always-on reviewer eligible for `initial_triage`.
3. Create a minimal graph trace without adding LangGraph yet:
   - initial cursor: `active_stage=null`, `stage_queue=["initial_triage","specialized_review","logic_review"]`, `completed_stages=[]`;
   - one transition advances to `initial_triage`;
   - selected reviewer records `stage="initial_triage"` and explicit trigger reasons;
   - trace entry records `active_stage_before`, `active_stage_after`, `suspended_stage_before`, `suspended_stage_after`, `stage_queue_before`, `stage_queue_after`, and `transition_reason`;
   - JSON envelope persists this trace.
4. Normalize and classify deterministic raw fake output without live LLMs:
   - one postable finding;
   - at least one local note;
   - optional clarification request/suppressed output when supplied by fixture data;
   - tests prove raw fake outputs pass through a narrow classifier/normalizer before rendering;
   - postable finding `path` and `line` must overlap a changed-line range/hunk in the fixture before rendering.
5. Build a posting plan using the existing posting module:
   - postable-finding runs may build a candidate top-level issue-comment payload;
   - clarification-only or no-finding runs keep `post_enabled=false`, retain local-only posting-plan items, and omit candidate payload preview so they cannot look postable.
6. Compute the first minimal local verdict rule:
   - clarification requests present -> `needs_clarification` as a dry-run/local status only, with `post_enabled=false`;
   - otherwise postable findings present -> `comment`;
   - otherwise -> `no_findings`.
7. Render markdown and JSON using the existing renderer.
8. Return a run result envelope that includes `run_mode="dry_run"`, `post_enabled`, selected reviewer/trace evidence, non-null local verdict, `writer_called=False`, and nested render output so tests can prove dry-run writer unreachability from persisted CLI artifacts.

## Implementation plan

1. Add fixture data:
   - `src/reviewgraph/fixtures_data/prs/basic-pr.json` for the built-in CLI harness;
   - `src/reviewgraph/fixtures_data/reviewer-configs/basic-reviewers.json` for a minimal JSON config. Use JSON in this issue to avoid adding dependencies and do not claim full YAML config validation;
   - `src/reviewgraph/fixtures_data/manifest.json` with a one-entry registry for `basic-pr`, its behavior, and the harness that consumes it. This is the narrow manifest seed required by harness engineering; the full fixture corpus remains AUR-238/later work;
   - secret-like fixture text in at least one raw fake output or memory body so the CLI harness proves redaction before persistence.
2. Add package-data support:
   - include fixture JSON files in `pyproject.toml` package data;
   - add a smoke test that builds/installs the package into an isolated temporary environment or otherwise proves `importlib.resources` can load the fixture data independent of source-relative paths.
3. Add fixture loading helpers:
   - strict JSON parsing with required-field validation;
   - explicit 1 MiB file-size cap for fixture/config JSON with a boundary test;
   - explicit errors for missing file, invalid JSON, missing target fields, changed-line range/hunk metadata, raw fake output fields, missing reviewer config fields, unsupported run mode, absent eligible reviewers, malformed manifest entries, missing default fixture/config, and fixture findings that do not anchor to changed-line metadata;
   - redact token-like content in errors before stderr output;
   - package fixture ID resolution through the manifest and explicit path resolution for test fixtures;
   - no network or environment credential reads.
4. Add deterministic runner:
   - `run_fixture_dry_run(fixture_ref, reviewer_config_path, writer_sentinel=None)` or similarly named API;
   - resolve built-in fixture IDs and direct paths;
   - default to `dry_run`;
   - initialize and persist the minimal stage cursor trace from `None` to `initial_triage`;
   - construct existing model objects;
   - select reviewer(s) from config with explainable reasons;
   - normalize fixture raw fake reviewer output into a small typed/validated intermediate and classify it into existing model objects;
   - validate every postable finding against fixture changed-line range/hunk metadata before posting-plan creation;
   - compute and pass the minimal non-null local verdict into the renderer;
   - build posting plan and build a candidate payload only when public postable findings exist and `post_enabled=true`;
   - for `needs_clarification`, render a posting plan with local-only clarification items, no candidate payload preview, `post_enabled=false`, and writer sentinel unreachable;
   - render markdown/JSON;
   - never call the writer sentinel in dry-run;
   - return a top-level primitive JSON envelope:

```json
{
  "run_mode": "dry_run",
  "post_enabled": false,
  "fixture_id": "basic-pr",
  "graph_trace": [
    {
      "active_stage_before": null,
      "active_stage_after": "initial_triage",
      "suspended_stage_before": null,
      "suspended_stage_after": null,
      "stage_queue_before": ["initial_triage", "specialized_review", "logic_review"],
      "stage_queue_after": ["specialized_review", "logic_review"],
      "transition_reason": "start_initial_triage"
    }
  ],
  "local_verdict": "comment",
  "side_effects": {"writer_called": false, "writer_call_count": 0},
  "review": {}
}
```

5. Add CLI:
   - `main(argv: list[str] | None = None) -> int`;
   - args: `--fixture-pr`, `--reviewer-config`, `--markdown-out`, `--json-out`, optional `--print-markdown`;
   - default reviewer config and fixture ID should work from the package fixture data without credentials;
   - JSON output must be deterministic and primitive-serializable;
   - errors should go to stderr and return non-zero with the failing field/path named.
6. Add tests in `tests/test_cli.py`:
   - fixture ID and explicit fixture path both work, including a packaged fixture-data smoke proof;
   - CLI writes byte-stable machine JSON files and selected markdown sections, not brittle full markdown goldens;
   - persisted output includes target metadata, selected reviewer reasons, classified outputs, local notes, posting plan, candidate preview, memory metadata, graph cursor trace, run mode, and dry-run writer proof;
   - default run is dry-run and writer sentinel is unreachable in both the runner object and persisted JSON envelope;
   - a writer sentinel that raises is never invoked;
   - CLI exposes no `--post` flag;
   - CLI/runner imports do not include writer, GitHub transport, approval, finalization, or marker modules;
   - fixture run does not read GitHub credential/env vars;
   - initial graph trace advances from `active_stage=None` to `active_stage="initial_triage"` without a LangGraph dependency;
   - graph trace includes before/after active stage, suspended stage, stage queue, and transition reason fields matching the state-graph doc;
   - raw fake reviewer output is normalized/classified before rendering;
   - local verdict is non-null and follows the deterministic rule for postable, clarification-only, and no-finding fixture outputs;
   - clarification-only fixtures persist `local_verdict="needs_clarification"`, `post_enabled=false`, local-only posting-plan items, `candidate_payload_preview=null`, and zero writer calls;
   - postable finding path/line must overlap fixture changed-line ranges/hunks; unchanged-line mismatches fail closed before rendering;
   - manifest/registry includes `basic-pr` and a test proves the built-in fixture is consumed by the CLI harness;
   - token-like fixture content is absent from stderr, markdown, JSON envelope, graph trace, nested renderer JSON, and candidate preview;
   - invalid fixture path, invalid JSON, missing required fixture fields, invalid reviewer config, no eligible reviewer, oversized fixture/config, unwritable output path, malformed manifest, and missing default fixture/config return non-zero with redacted actionable stderr;
   - import/purity check ensures CLI/runner do not import GitHub writer/approval/finalization modules.
7. Run validation:
   - `python -m pytest tests/test_cli.py`
   - `python -m pytest`
   - `python -m py_compile src/reviewgraph/*.py`
   - `python scripts/check_docs.py`
   - `git diff --check`

## Out of scope

- No live GitHub reads.
- No live LLM calls.
- No real LangGraph dependency or full graph implementation.
- No approval, finalization, marker reconciliation, or writer adapter.
- No `--post` or side-effecting mode.
- No full reviewer config validation beyond fields required by this fixture CLI.
- No complete fixture corpus manifest; `AUR-238` owns the full golden tracer proof.

## Review approach

- Get fresh subagent plan review before implementation.
- Commit the accepted issue plan.
- Implement the minimal CLI/runner slice.
- Move `AUR-210` to `In Review` after implementation validation.
- Run fresh code-review subagents until no material findings remain, committing after each review-fix cycle.
