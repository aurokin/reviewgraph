# PRD 0006: GitHub Read And Memory

## Problem Statement

Reviewers need PR context beyond a raw diff, especially existing comments and review threads. But PR conversation can include untrusted text, resolved issues, bot noise, and secrets. ReviewGraph needs a safe read adapter and memory builder before live review can be trusted.

## Solution

Build GitHub read adapters that fetch PR metadata, changed files, diffs, comments, review comments, reviews, and thread state with pagination. Convert conversation into structured memory with trust metadata, seen-state, resolved-state, and truncation notes.

## User Stories

1. As a reviewer, I want existing PR comments included, so that ReviewGraph does not repeat already-discussed issues.
2. As a maintainer, I want resolved review threads treated as non-actionable, so that resolved feedback is not revived.
3. As a maintainer, I want untrusted comments retained only as passive memory, so that comment injection cannot steer routing.
4. As a maintainer, I want review bot trust to be allowlisted, so that arbitrary bot comments do not become actionable.
5. As a developer, I want pagination tested, so that first-page-only bugs cannot pass MVP.
6. As a developer, I want truncation surfaced as local notes, so that partial context is visible.
7. As a developer, I want read mode to work without write credentials, so that live-read smoke tests are safe.
8. As a maintainer, I want write mode to show authenticated actor and permission, so that approvals are informed.

## Implementation Decisions

- Read adapters may use GitHub REST API or `gh`.
- Required read context includes owner/repo, PR number, title/body/author, base/head SHAs, merge base, labels, changed files, patches, comments, reviews, review comments, and thread state where available.
- Adapters must paginate files, issue comments, review comments, reviews, and thread state.
- Conversation memory stores author, author association, timestamp, body, path/line when available, URL, resolved state, and trust classification.
- Trusted human authors are owner/member/collaborator plus authenticated operator.
- Trusted review bots are configured by allowlist and default deny.
- Untrusted comments cannot trigger `conversation_patterns`.
- If truncation occurs after pagination, ReviewGraph emits a local note and avoids postable findings dependent on omitted context.

## Testing Decisions

- Fake transport tests cover multi-page files, issue comments, review comments, reviews, and thread state.
- Tests assert pagination completes before truncation.
- Tests assert untrusted comments remain passive memory.
- Tests assert unlisted bots remain passive memory.
- Tests assert resolved threads are non-actionable unless new unresolved follow-up appears.
- Tests assert missing actor or insufficient/unknown permission blocks approval/posting.

## Out of Scope

- GitHub write behavior.
- Webhooks.
- Long-running PR babysitting.

## Further Notes

This PRD is independently useful: live read and memory can improve dry-run review quality before any writer exists.
