# ISSUE PLAN: AUR-236 Select Conversation Pattern Reviewers

Active issue plan for `AUR-236` / `RG-047: Select Conversation Pattern Reviewers`.

Linear remains the durable source of current issue status and relationships. This file is the committed execution plan for the issue.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0006: GitHub Read And Memory`
- Issue: `AUR-236`
- Title: `RG-047: Select Conversation Pattern Reviewers`
- Status when planned: `In Progress`
- Priority: `Medium`
- Linear comments fetched on 2026-05-07: none

## Acceptance Mapping

1. Trusted actionable comments can select eligible reviewers through `conversation_patterns`.
   - Re-enable `conversation_patterns` matching for all actionable memory, including GitHub-derived memory from AUR-215.
   - Preserve fixture trusted-memory routing.
   - Match only against memory body text when `MemoryReference.actionable=True`.
2. Resolved trusted threads do not select reviewers unless there is new unresolved follow-up.
   - Use existing thread-state actionability from AUR-215: resolved and unknown threads are passive, unresolved threads can be actionable if author trust passes.
   - In this issue, "new unresolved follow-up" means the adapter/memory model's current thread-level `resolved_status="unresolved"` state. ReviewGraph does not yet model per-comment resolution transitions or timestamps.
   - Prove resolved trusted GitHub thread memory with a matching body does not route.
   - Prove unresolved trusted GitHub thread memory with a matching body does route.
3. Untrusted comments and unlisted bot comments cannot satisfy `conversation_patterns`.
   - Prove untrusted human GitHub comments and unlisted bot GitHub comments with matching bodies do not select reviewers.
   - Keep passive/untrusted body text out of matching input rather than matching and filtering after the fact.
4. Selection reasons include matching memory IDs and trust status.
   - Replace conversation-pattern reason text with a richer deterministic reason that includes stage, pattern, `memory_id`, and `trust`.
   - Include `source_provider` when present so GitHub-derived routing is explainable.
   - Keep existing non-memory reason formats unchanged.
5. Prompt-injection fixture proves malicious comments do not route reviewers.
   - Add focused routing coverage for the existing untrusted injection fixture or equivalent GitHub-derived malicious memory.
   - Do not rely on prompt rendering tests alone; the selector must reject passive memory before reviewer selection.

## Design

AUR-215 intentionally blocked positive GitHub `conversation_patterns` routing until routing reasons could name the memory that matched. AUR-236 removes that temporary block and makes conversation-pattern routing inspectable.

Planned contract:

- `conversation_patterns` iterates memory entries, not a concatenated body string.
- Only `memory.actionable` entries are eligible. `trust_label` is still expected to be `trusted` by model validation for actionable memory, but routing should rely on the explicit `actionable` boundary.
- Passive/untrusted/resolved/unknown/review-summary entries are skipped before reading the body.
- Matching remains case-insensitive. Existing regex/literal behavior is not expanded for conversation memory in this issue; it remains simple substring matching unless current tests prove otherwise.
- For every matched pattern/memory pair, add a deterministic reason:

  ```text
  {stage} triggers.conversation_patterns={pattern} memory_id={memory.id} trust={memory.trust_label}
  ```

- If `memory.source_provider` is present, append:

  ```text
  source_provider={memory.source_provider}
  ```

- Multiple matching memory entries may produce multiple reasons. This is acceptable because it improves auditability and avoids hiding which shared-memory item introduced the reviewer.
- Ordering is deterministic: iterate configured `conversation_patterns` in config order, then memory entries in their existing conversation-memory order.
- Duplicate reason strings are collapsed in insertion order so duplicate configured patterns or duplicate memory entries do not inflate persisted output with identical reasons.
- Gate behavior remains unchanged: `risk_min`, `max_files`, `changed_lines_min`, and `changed_files_min` must pass before selectors can select.
- This issue does not alter prompt execution, reviewer context packaging, quality classification, approval, writer behavior, or durable deduplication.

## Files

Likely implementation files:

- `src/reviewgraph/routing.py`
- `docs/architecture/reviewer-config.md`
- `docs/architecture/state-graph.md`
- `docs/harnesses/harness-engineering.md`

Likely tests:

- `tests/test_conversation_routing.py`
- `tests/test_routing.py`
- `tests/test_cli.py`
- `tests/test_prompt_injection_memory.py`
- `tests/test_github_memory_trust.py`

## Implementation Steps

1. Add `tests/test_conversation_routing.py` with focused GitHub/fixture memory routing cases:
   - trusted actionable GitHub issue comment routes and reason includes memory ID/trust/source provider
   - trusted unresolved GitHub review-thread comment routes
   - trusted resolved and unknown GitHub review-thread comments do not route
   - untrusted human and unlisted bot GitHub comments do not route
   - malicious untrusted fixture/GitHub memory does not route
   - fixture trusted actionable memory still routes
   - duplicate pattern/memory matches are deterministic and do not duplicate identical reason strings
   - actionable memory plus a failing gate does not select or persist reviewer state
2. Update `routing.py` so conversation-pattern matching iterates eligible actionable memory entries and records matched-memory reason metadata.
3. Add active-stage persistence coverage proving the richer reason appears in `review_state.selected_reviewers`, reviewer run status remains registered, CLI JSON renders the richer reason, and reviewer context packages carry the selected-reviewer reason unchanged.
4. Update existing routing/CLI/prompt-injection tests that assert the old short conversation-pattern reason string.
5. Remove or invert the AUR-215 temporary negative GitHub-routing assertion in `tests/test_github_memory_trust.py`; AUR-236 owns positive routing.
6. Update docs where they currently say GitHub actionable memory cannot route until AUR-236.
7. Keep all passive-memory body suppression behavior unchanged.

## Validation Plan

Focused harness:

```bash
python -m pytest tests/test_conversation_routing.py -q
```

Regression harness:

```bash
python -m pytest tests/test_routing.py tests/test_github_memory_trust.py tests/test_prompt_injection_memory.py tests/test_cli.py -q
```

Full validation before completion:

```bash
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Out Of Scope

- Prompt execution or reviewer adapter behavior.
- Quality classification or finding evidence policy.
- Approval input, finalization, writer behavior, or GitHub posting.
- Semantic deduplication or durable seen-state storage.
- Regex support for `conversation_patterns` beyond the existing substring-style config semantics.
