# ISSUE PLAN: AUR-193 Build Trusted Conversation Memory

Active issue plan for `AUR-193` / `RG-004: Build Trusted Conversation Memory`.

## Linear Snapshot

- Issue: `AUR-193`
- Status at start: `In Progress`
- Milestone: `PRD 0003: Contracts`
- Blocks: `AUR-194`, `AUR-231`, `AUR-234`, `AUR-254`
- Blocked by: `AUR-192` (now Done)
- Comments at start: none
- Harness from Linear: `python -m pytest tests/test_memory.py`

## Goal

Convert typed fixture PR comments, review comments, reviews, and review-thread state into structured conversation memory.

This issue should preserve trust, source, timestamp, body, and location metadata for later reviewer context packages. It should not build prompts, select reviewers, call live GitHub, call live LLMs, or mutate GitHub conversation state.

## Implementation Plan

1. Add `src/reviewgraph/memory.py`:
   - Input: `PullRequestContext` from parsed fixtures and an optional authenticated operator allowlist.
   - Output: `PRConversationMemory` with `MemoryReference` entries.
   - Include top-level PR comments, PR reviews, and review-thread comments.
   - Preserve author, author association, timestamp, body, source type, resolved status, path, line, and URL when present.
2. Strengthen memory contracts in `src/reviewgraph/models.py` if needed:
   - `MemoryReference` should carry the metadata AUR-193 requires instead of only id/trust/source/body.
   - Trust and resolved/actionable state should be graph-owned structured fields, not inferred later from prose.
3. Trust policy:
   - Trusted human authors are `OWNER`, `MEMBER`, or `COLLABORATOR`.
   - The authenticated operator is trusted when explicitly provided.
   - Trusted review bots are configured by explicit allowlist and default deny.
   - Bot/unknown/external/contributor authors remain passive/untrusted unless the operator or trusted-bot allowlist says otherwise.
   - Fixture-provided `trust_label` must not upgrade an untrusted `author_association`; it can only preserve source metadata for tests.
4. Resolved/actionable policy:
   - Top-level comments and reviews are unresolved/passive memory by default unless their source says otherwise.
   - Review-thread comments inherit the thread's resolved status.
   - Resolved threads are non-actionable in this slice.
   - The “resolved thread with newer unresolved follow-up” exception is deferred until the typed model has explicit follow-up event metadata.
   - Unknown thread state remains passive for routing/actionability.
5. Add `tests/test_memory.py`:
   - Builds memory from the `untrusted-comment-injection`, `stale-approval-change`, `ambiguous-logic-change`, and `basic-pr` fixtures.
   - Asserts author, author association, timestamp, body, URL/path/line, source type, trust label, resolved status, and actionable/passive fields are preserved.
   - Asserts owner/member/collaborator/operator comments are trusted and contributor/external comments stay passive.
   - Asserts allowlisted bots are trusted and unlisted bots stay passive/default-deny.
   - Asserts fixture `trust_label=trusted` cannot upgrade a contributor/external author to trusted.
   - Asserts untrusted comments remain passive memory even if their body looks like an instruction.
   - Asserts generated memory comes only from `PullRequestContext`, not legacy fixture `memory` entries.
   - Asserts resolved and unknown threads are non-actionable.

## Out Of Scope

- No prompt construction or reviewer context package rendering. `AUR-231` owns context packaging.
- No reviewer selection/routing changes.
- No live GitHub read or pagination. `AUR-213` and follow-ups own fake/live transport.
- No redaction behavior changes; existing render/redaction protections remain regression coverage.
- No graph runtime changes.
- No resolved-thread follow-up event policy until the model can represent explicit follow-up metadata.

## Validation

Focused:

```bash
python -m pytest tests/test_memory.py
```

Regression:

```bash
python -m pytest tests/test_fixtures.py tests/test_fixture_manifest.py tests/test_cli.py tests/test_tracer_fixture_run.py
python -m pytest
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Comment On Linear

- Files changed.
- Focused memory harness output.
- Full regression output.
- Confirmation that untrusted comments remain passive and no prompt/reviewer/live integration behavior was introduced.
