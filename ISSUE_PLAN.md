# ISSUE PLAN: AUR-259 Complete PRD 0006 GitHub Read And Memory

Active issue plan for `AUR-259` / `Complete PRD 0006: GitHub Read And Memory`.

Linear remains the durable source of status, relationships, and evidence. This gate closes only after real repo, docs, tests, Linear, and reviewer evidence prove the milestone contract.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0006: GitHub Read And Memory`
- Issue: `AUR-259`
- Title: `Complete PRD 0006: GitHub Read And Memory`
- Status when planned: `In Progress`
- Priority: `Medium`
- Linear comments fetched on 2026-05-07: none
- Implementation issues in milestone:
  - `AUR-213` / fake GitHub metadata read / `Done` with evidence comment
  - `AUR-247` / fail closed on read gaps / `Done` with evidence comment
  - `AUR-214` / paginated fake GitHub read resources / `Done` with evidence comment
  - `AUR-215` / GitHub memory trust rules / `Done` with evidence comment
  - `AUR-236` / conversation-pattern reviewer routing / `Done` with evidence comment
  - `AUR-239` / GitHub PR dry-run adapter path / `Done` with evidence comment
  - `AUR-216` / opt-in live read smoke / `Done` with evidence comment
- Canceled duplicate:
  - `AUR-252` / duplicate of `AUR-247` / `Duplicate`

## Gate Objective

Close PRD 0006 only if ReviewGraph actually proves safe GitHub read and memory behavior:

- GitHub PR refs and URLs resolve into stable read targets.
- Fake adapters read metadata, changed files, comments, reviews, review comments, and thread state with pagination before truncation.
- Required read gaps fail closed before downstream review, routing, payload, or writer eligibility.
- GitHub conversation memory preserves seen-state/source IDs, applies trust policy, handles resolved and unknown thread state, and keeps untrusted/passive memory from routing, verdicts, prompts, and public payloads.
- Trusted actionable memory can select reviewers through explicit state, with selection reasons including memory IDs and trust labels.
- GitHub PR dry-run uses the same graph/render contracts as fixture dry-run and remains writer-free by default.
- Live read smoke is opt-in, skipped by default, read-only, and produces clear blocked/fail-closed artifacts.
- Durable docs explain the final contracts an implementation agent needs without forcing them to read temporary planning files.

## Prompt-To-Artifact Checklist

Map every gate requirement to concrete evidence before closing:

- Milestone inventory: Linear `PRD 0006` milestone, active issue statuses, duplicate rationale for `AUR-252`, and evidence comments for `AUR-213`, `AUR-247`, `AUR-214`, `AUR-215`, `AUR-236`, `AUR-239`, and `AUR-216`.
- Product contract: `docs/prds/0006-github-read-memory.md`, `docs/product/rules.md`, and `docs/product/vision.md`.
- Architecture contract: `docs/architecture/github-integration.md`, `docs/architecture/state-graph.md`, `docs/architecture/reviewer-config.md`, `docs/architecture/side-effects.md`, and `docs/architecture/overview.md`.
- Harness contract: `docs/harnesses/harness-engineering.md` and the PRD 0006 focused tests.
- Implementation evidence: `src/reviewgraph/github.py`, `src/reviewgraph/github_live.py`, `src/reviewgraph/read_gaps.py`, `src/reviewgraph/memory.py`, `src/reviewgraph/routing.py`, `src/reviewgraph/targets.py`, `src/reviewgraph/runner.py`, and `src/reviewgraph/cli.py`.
- Side-effect boundary: no new GitHub writer, approval, finalization, inline posting, formal review, status, label, live LLM, or unapproved live API path is reachable from PRD 0006 read/dry-run/live-smoke code.
- Temporary artifacts: no `.ws/` tree, temporary Linear export, live-read artifact, audit scratch file, or subagent scratch file remains in the repository. Prefer writing any unavoidable scratch artifact outside the repo under `/tmp`.
- Validation commands: focused PRD 0006 harnesses, full suite, docs check, py-compile, and diff check.
- Linear queue verifier: a temporary canonical backlog export must be generated from current Linear milestone data, checked with `python scripts/check_docs.py --backlog-export <path>`, summarized in the final gate evidence, and removed before closure.
- Live-read decision: either run `REVIEWGRAPH_LIVE_READ=1 ... pytest -m live_read` against an explicit public PR target and record the artifact, or explicitly document that live network smoke was not executed and that the gate evidence is limited to skipped-by-default harness proof plus fake/read-only boundary proof.
- Commit reconciliation: verify every commit hash cited by PRD 0006 Linear evidence is reachable from current `HEAD`, record `git rev-parse HEAD`, prove the worktree is clean with `git status --short`, and rerun gate validation at the current gate commit rather than relying on earlier issue comments.
- Final evidence schema: the `AUR-259` Linear comment must include a table with issue ID, current status/status type, blocker or canceled/duplicate state, evidence comment ID, cited commits, and mapped PRD 0006 acceptance surface.
- Review gate: fresh subagents review code, tests, docs, Linear evidence, and this gate plan until they report no material findings.

## Audit Steps

1. Re-fetch Linear issue statuses and comments for the full PRD 0006 milestone.
2. Inspect the durable docs and compare them against PRD 0006 acceptance surface and the final implemented behavior.
3. Inspect key implementation files for contract coverage and side-effect boundaries.
4. Generate a temporary canonical Linear backlog export from current Linear data under `/tmp`, run `python scripts/check_docs.py --backlog-export <path> --verbose`, save the command result in the audit notes, and remove the temporary export before closing.
5. Verify the commit hashes referenced in implementation evidence comments are reachable from current `HEAD`.
6. Run focused harnesses:
   - `python -m pytest tests/test_github_fake_read.py -q`
   - `python -m pytest tests/test_github_read_gaps.py -q`
   - `python -m pytest tests/test_github_pagination.py -q`
   - `python -m pytest tests/test_github_memory_trust.py -q`
   - `python -m pytest tests/test_conversation_routing.py -q`
   - `python -m pytest tests/test_github_dry_run_cli.py -q`
   - `python -m pytest tests/test_live_read_smoke.py -q`
7. Decide live network smoke explicitly:
   - If `gh`, a token, and `REVIEWGRAPH_LIVE_READ_PR` are intentionally available, run `REVIEWGRAPH_LIVE_READ=1 REVIEWGRAPH_LIVE_READ_OUT=<tmp artifact> python -m pytest -m live_read tests/test_live_read_smoke.py -q` and record the artifact summary.
   - If not run, record the exact rationale in `AUR-259` evidence and do not describe skipped default tests as live network proof.
8. Run integration and repository checks at the current gate commit:
   - `python -m pytest tests/test_contract_boundaries.py tests/test_prompt_injection_memory.py tests/test_redaction.py tests/test_cli.py tests/test_render.py -q`
   - `python -m pytest -q`
   - `python -m py_compile src/reviewgraph/*.py`
   - `python scripts/check_docs.py`
   - `git diff --check`
9. Ask fresh subagents for independent milestone-gate review after local audit data is available.
10. If docs or implementation gaps are found, fix them in scoped commits and rerun affected checks and reviewer passes.
11. Run final repository-state proof: `git rev-parse HEAD`, `git status --short`, `find . -maxdepth 2 -type d -name .ws -print`, and a targeted check for repo-local temporary gate artifacts.
12. Move `AUR-259` to `In Review`, add a Linear evidence comment with the required gate evidence table, audit mapping, command results, live-read decision, commit reachability, backlog verifier result, current `HEAD`, clean-worktree proof, temporary-artifact cleanup proof, and final subagent review results. Move it to `Done` only after all findings are none-issues.

## Documentation Refactor Expectations

If the audit finds durable documentation gaps, refactor the narrowest docs using progressive disclosure:

- `README.md` and `docs/README.md`: only orientation and read order.
- Product docs: stable behavior and guardrails, not issue history.
- Architecture docs: state graph, adapter contracts, memory trust, side-effect boundaries, and reviewer routing.
- Harness docs: exact confidence ladder and opt-in live smoke posture.
- ADRs: only durable tradeoffs that future implementation agents must preserve.

Do not copy this whole plan into durable docs. Keep Linear and committed plan files as the execution record.

## Out Of Scope

- Starting PRD 0007 before `AUR-259` is closed.
- GitHub writes, approval prompts, writer adapters, inline comments, formal PR reviews, labels, statuses, approvals, or request-changes behavior.
- Live LLM execution.
- Pushing before the overall Linear milestone loop objective is complete.
