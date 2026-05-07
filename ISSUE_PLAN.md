# ISSUE PLAN: AUR-223 Suppress Writes With No Approved Findings

Active issue plan for `AUR-223` / `RG-034: Suppress Writes With No Approved Findings`.

Linear is the durable source for status, blockers, and handoff. Durable behavior comes from `docs/architecture/side-effects.md`, `docs/architecture/state-graph.md`, `docs/architecture/github-integration.md`, `docs/harnesses/harness-engineering.md`, and `docs/prds/0007-side-effects.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-223`
- Title: `RG-034: Suppress Writes With No Approved Findings`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-07: none
- Upstream blockers complete: `AUR-244`, `AUR-218`, `AUR-217`, `AUR-219`, `AUR-243`, `AUR-220`, `AUR-221`, `AUR-245`, and `AUR-246`.
- Downstream issues: `AUR-222` owns the fake writer graph/CLI route; `AUR-241` owns the real writer adapter; `AUR-224` owns manual live post smoke.

## Objective

Prove that ReviewGraph never releases writer input when there is no approved public finding to post.

The current code already has approval proof and finalization preflight primitives, but there is no writer route yet. This issue should therefore harden the no-approved-finding contract at the approval/finalization boundary and in dry-run harness output, without adding fake writer, real writer, public post mode, or live GitHub writes.

## Contracts To Preserve

- Dry-run remains the default behavior.
- Candidate payloads are not final payloads and are never writer input.
- Approval is item-level and only public `postable_finding` items may be approved.
- `approved_finding_ids=[]`, rejected approval, unknown approved IDs, local notes, suggested replies, suppressed findings, and clarification requests cannot release writer input.
- Suggested replies remain local-only even when the same run has approved findings.
- Final payload construction stays after approval preflight, actor/permission re-check, and target freshness re-check.
- No writer module should be imported or reachable in this issue.
- Default dry-run output should explain why no public payload was prepared when everything is local-only.

## Implementation Shape

1. Add a focused no-approved-findings harness in `tests/test_no_approved_findings.py`:
   - `approved_finding_ids=[]` fails approval proof or finalization preflight before payload builder and before writer reachability.
   - rejected approval fails finalization preflight before current reads, payload builder, and writer reachability.
   - local-notes-only dry-run has `post_enabled=false`, no candidate payload preview, zero writer calls, and markdown explains no public payload was prepared.
   - suggested-reply-only dry-run has the same no-write proof and keeps the reply in local-only output.
   - suppressed-findings-only dry-run has no candidate payload preview, no writer call, and local-only posting-plan evidence.
   - clarification-only dry-run has no candidate payload preview, no writer call, and local-only posting-plan evidence.
   - mixed run with approved findings plus suggested reply keeps candidate payload/final approval proof restricted to the finding; suggested reply text must not enter candidate or final public payloads.
2. Tighten finalization preflight evidence if needed:
   - Preserve `_approval_preflight(...)` as the first finalization check.
   - Return stable dry-run/preflight evidence for empty or rejected approval.
   - Keep `final_payload_builder_calls=0` and `writer_input_released=false` for all preflight failures.
   - Do not import writer, GitHub transport, CLI, graph post-mode, marker scanning, or ambient process state.
3. Improve render/dry-run explanation if needed:
   - When `candidate_payload_preview` is absent because all items are local-only or no public findings are eligible, markdown should say no public GitHub payload was prepared and identify the local-only/no-post reason at a high level.
   - Keep existing JSON shape stable unless a small first-class explanation is clearly needed for tests.
4. Update narrow durable docs:
   - `docs/architecture/side-effects.md` for no-approved/local-only writer suppression.
   - `docs/architecture/state-graph.md` if finalization preflight behavior changes.
   - `docs/harnesses/harness-engineering.md` for the focused no-approved-findings harness.

## Focused Harness

Create `tests/test_no_approved_findings.py` covering:

- Empty approval cannot invoke payload builder or release writer input.
- Rejected approval cannot invoke payload builder or release writer input.
- Local-notes-only dry-run calls no writer and produces no candidate payload.
- Suggested-reply-only dry-run calls no writer, produces no candidate payload, and keeps the reply local-only.
- Suppressed-findings-only dry-run calls no writer and produces no candidate payload.
- Clarification-only dry-run calls no writer and produces no candidate payload.
- Mixed finding plus suggested reply run keeps suggested reply text out of candidate payload body and approval final body.
- Dry-run markdown explains why no public payload was prepared for local-only/no-post runs.
- Import-boundary proof: any touched no-approved/finalization code does not import writer, GitHub transport, live network clients, `os`, `subprocess`, or ambient stdin.

Update existing tests only when they already own the exact behavior:

- `tests/test_target_freshness.py` if finalization preflight evidence changes.
- `tests/test_cli.py` if dry-run markdown additions affect existing expectations.

## Validation

Focused:

```bash
python -m pytest tests/test_no_approved_findings.py -q
```

Regression:

```bash
python -m pytest tests/test_no_approved_findings.py tests/test_approval.py tests/test_target_freshness.py tests/test_cli.py tests/test_clarification.py tests/test_quality_testing.py -q
python scripts/check_docs.py
git diff --check
python -m py_compile src/reviewgraph/*.py
```

Run the full suite because this issue touches render/finalization side-effect safety contracts:

```bash
python -m pytest -q
```

## Out Of Scope

- Fake top-level comment writer.
- Real writer adapter.
- Live GitHub writes.
- Public CLI `--post`.
- Posting non-finding, local note, suggested reply, suppressed, or clarification content.
- Approval UI or human prompt flow.
- Marker scan/reconciliation changes beyond preserving existing no-writer state.
