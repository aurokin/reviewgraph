# ISSUE PLAN: AUR-246 Block Non-Interactive Posting Mode

Active issue plan for `AUR-246` / `RG-057: Block Non-Interactive Posting Mode`.

Linear is the durable source for status, blockers, and handoff. Durable behavior comes from `docs/architecture/side-effects.md`, `docs/architecture/state-graph.md`, `docs/architecture/github-integration.md`, `docs/harnesses/harness-engineering.md`, and `docs/prds/0007-side-effects.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-246`
- Title: `RG-057: Block Non-Interactive Posting Mode`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-07: none
- Upstream blockers complete: `AUR-244`, `AUR-218`, `AUR-217`, `AUR-219`, `AUR-243`, `AUR-220`, `AUR-221`, and `AUR-245`.
- Downstream issues: `AUR-223` owns no-approved-finding writer suppression; `AUR-222` owns fake writer graph/CLI integration; `AUR-241` owns the real writer adapter; `AUR-224` owns manual live post smoke.

## Objective

Add a fail-closed post-mode interaction gate so non-interactive post attempts cannot infer approval, block waiting for input, construct final payloads, or call any writer.

Current code only exposes dry-run routes and the CLI intentionally has no post flag. This issue should therefore introduce the explicit gate/policy and a harnessed post-attempt path that proves the future route will stop between `render_review` and `approval_gate`. It must not introduce real approval UI, fake writer implementation, real writer implementation, live GitHub writes, or CI/webhook approval policy.

## Contracts To Preserve

- Dry-run remains the default behavior.
- Existing CLI dry-run behavior and JSON shape remain stable.
- CLI must still not expose a public `--post` flag in this issue.
- Non-interactive mode can still render dry-run output.
- `run_mode=post` with no interactive human approval surface fails closed after render and before approval input.
- CI, webhook, config-only, and non-TTY CLI contexts are explicitly non-interactive.
- Config values, environment state, fixture data, or prior approval data cannot imply approval.
- The gate must return structured state (`PostInteractionGateResult`) plus graph error/output evidence; it must not prompt, block, read stdin, inspect ambient TTY state, or sleep.
- Missing human approval fails closed before approval prompt/input, final payload construction, marker reconciliation, and writer reachability.
- Error output must say that non-interactive posting requires a future explicit approval policy.
- Writer sentinel/fake writer call count remains zero for all non-interactive post attempts.

## Implementation Shape

1. Add a small pure interaction-gate surface, likely in a new `src/reviewgraph/post_interaction.py` or in `runner.py` if the existing module shape is simpler:
   - `PostModeContext` or equivalent explicit input with `run_mode`, `interactive`, and `reason`.
   - `evaluate_post_mode_interaction_gate(...) -> PostInteractionGateResult`.
   - Use existing `PostInteractionGateResult` and `GateStatus`.
   - Reject `run_mode=post` when `interactive=False` with a stable reason such as `non_interactive_posting_requires_future_policy`.
   - Dry-run mode must not evaluate or record `post_mode_interaction_gate`; the state graph bypasses this gate unless `run_mode=post`.
2. Add a harness-only post-attempt runner path:
   - Keep `run_fixture_dry_run(...)` unchanged for default dry-run callers.
   - Add a narrow function such as `run_fixture_non_interactive_post_attempt(...)` or `run_fixture_review(..., run_mode=RunMode.POST, interactive=False)` that reuses dry-run rendering, then evaluates `post_mode_interaction_gate`.
   - The path should append a `post_mode_interaction_gate` trace event after rendering and before any approval/finalization fields can be set.
   - It should return rendered dry-run output plus structured fail-closed evidence, not raise, block, or prompt.
3. Preserve side-effect boundaries:
   - No imports from writer modules.
   - No finalization imports unless a test double proves final payload builder is not called; prefer avoiding finalization entirely in this issue.
   - No `input()`, `sys.stdin`, `isatty`, `os.environ`, or CI environment probing inside policy logic. Tests pass explicit `interactive=False` and explicit non-interactive reason.
4. Add CLI policy evidence without adding `--post`:
   - Keep `tests/test_cli.py::test_cli_does_not_expose_post_flag` passing.
   - Strengthen that test to assert `--post` is unrecognized, absent from parser actions, and absent from help text.
   - If needed, add an internal CLI helper or parser assertion proving config-only CLI cannot request post mode.
   - Do not add public post CLI flags before AUR-222/AUR-224 define the interactive approval route.
5. Update JSON/dry-run output for post attempts:
   - top-level `run_mode` should be `post` for the harnessed post-attempt result.
   - `post_enabled` should be `false` after the interaction gate fails.
   - include first-class `post_interaction_gate` data matching `ReviewState.post_interaction_gate`, and a `post_mode_interaction_gate` graph trace event.
   - include a `GraphError` with stable code such as `non_interactive_post_mode`.
   - `candidate_payload_preview` may still exist in the rendered review because rendering happened before the gate; final payload and approval fields must remain absent. If the implementation suppresses candidate payload after the gate, update docs/tests to prove the rendering-before-gate contract is still understandable.
6. Update narrow durable docs:
   - non-interactive policy in `docs/architecture/side-effects.md` and `docs/architecture/state-graph.md`
   - harness expectations in `docs/harnesses/harness-engineering.md`

## Focused Harness

Create `tests/test_non_interactive_posting.py` covering:

- Default dry-run remains renderable in non-interactive contexts and does not require a post gate.
- Default dry-run never evaluates or records `post_mode_interaction_gate`.
- CLI still does not expose a public `--post` flag: it is unrecognized, absent from parser actions, and absent from help text.
- Internal post-attempt path with `interactive=False` returns `run_mode=post`, `post_enabled=false`, and a failed `post_mode_interaction_gate`.
- CI, webhook, config-only, and non-TTY CLI reasons all fail closed without blocking.
- Error output explains that future explicit non-interactive approval policy is required.
- No approval prompt/input function is called; use a raising prompt sentinel if the implementation accepts one.
- Final payload builder sentinel is not called.
- Writer sentinel/fake writer is not called.
- Graph trace records `post_mode_interaction_gate` after render/review output and before any approval/finalization event, and JSON includes first-class `post_interaction_gate` data.
- Approval, final payload, final payload hash, marker reconciliation, and writer result remain unset in any returned state/json.
- Import-boundary proof: the non-interactive gate module does not import writer, GitHub transport, finalization, live network clients, `os`, `subprocess`, clocks, or ambient stdin.

Update existing tests as needed:

- `tests/test_cli.py` for CLI no-post flag expectations.
- `tests/test_models.py` if `PostInteractionGateResult` gains reason-code fields.
- Runner/trace tests if a harnessed post-attempt route adds a new trace event shape.

## Validation

Focused:

```bash
python -m pytest tests/test_non_interactive_posting.py -q
```

Regression:

```bash
python -m pytest tests/test_non_interactive_posting.py tests/test_cli.py tests/test_models.py tests/test_target_freshness.py -q
python scripts/check_docs.py
git diff --check
python -m py_compile src/reviewgraph/*.py
```

Run the full suite because this issue touches runner output and side-effect safety contracts:

```bash
python -m pytest -q
```

## Out Of Scope

- Real approval UI or approval prompt.
- Fake top-level comment writer.
- Real writer adapter.
- Live GitHub writes.
- CI/webhook approval policy.
- Manual live post smoke.
- Adding a public CLI `--post` flag.
- Finalizing payloads or releasing writer input.

## Completion Evidence

- Implemented pure post-mode interaction gate in `src/reviewgraph/post_interaction.py`.
- Added harness-only `run_fixture_non_interactive_post_attempt(...)` in `src/reviewgraph/runner.py`.
- Added `tests/test_non_interactive_posting.py` for dry-run bypass, absent public `--post`, CI/webhook/config-only/non-TTY fail-closed contexts, no prompt/final-payload-builder calls, no writer calls, graph trace ordering, unset approval/finalization/marker/writer fields, and side-effect import boundaries.
- Updated `docs/architecture/side-effects.md`, `docs/architecture/state-graph.md`, and `docs/harnesses/harness-engineering.md` with the non-interactive post gate contract.
- Implementation commit: `c12fdaf feat: block non-interactive post attempts`.
- Code-review subagents `019e0467-86a8-7640-bf01-1022621e7f51` and `019e0467-86c6-73b3-bfad-def313c95e52` reported no material issues.

Validation:

```bash
python -m pytest tests/test_non_interactive_posting.py -q
python -m pytest tests/test_non_interactive_posting.py tests/test_cli.py tests/test_models.py tests/test_target_freshness.py -q
python scripts/check_docs.py
git diff --check
python -m py_compile src/reviewgraph/*.py
python -m pytest -q
```

Results:

- `tests/test_non_interactive_posting.py`: 8 passed.
- Regression bundle: 405 passed.
- Docs, diff, and compile checks passed.
- Full suite: 1077 passed, 1 skipped, 209 warnings.
