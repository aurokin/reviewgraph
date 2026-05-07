from reviewgraph.github import (
    GitHubReadResult,
    GitHubReadScope,
    GitHubThreadStateAvailability,
    ResourceReadStatus,
    read_github_pr_with_paginated_fake_transport,
)
from reviewgraph.memory import build_conversation_memory
from reviewgraph.models import PullRequestContext, ReadGap
from reviewgraph.read_gaps import FailClosedReadOutcome


class FakePaginatedGitHubTransport:
    def __init__(
        self,
        *,
        pr: dict[str, object],
        files: dict[object | None, dict[str, object]],
        issue_comments: dict[object | None, dict[str, object]],
        review_comments: dict[object | None, dict[str, object]],
        reviews: dict[object | None, dict[str, object]],
        review_threads: dict[object | None, dict[str, object]],
    ) -> None:
        self.pr = pr
        self.files = files
        self.issue_comments = issue_comments
        self.review_comments = review_comments
        self.reviews = reviews
        self.review_threads = review_threads
        self.calls: list[tuple[str, str, int, object | None]] = []

    def get_pull_request(self, owner_repo: str, pr_number: int) -> dict[str, object]:
        self.calls.append(("get_pull_request", owner_repo, pr_number, None))
        return self.pr

    def get_changed_files_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        self.calls.append(("get_changed_files_page", owner_repo, pr_number, cursor))
        return self.files[cursor]

    def get_issue_comments_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        self.calls.append(("get_issue_comments_page", owner_repo, pr_number, cursor))
        return self.issue_comments[cursor]

    def get_review_comments_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        self.calls.append(("get_review_comments_page", owner_repo, pr_number, cursor))
        return self.review_comments[cursor]

    def get_reviews_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        self.calls.append(("get_reviews_page", owner_repo, pr_number, cursor))
        return self.reviews[cursor]

    def get_review_threads_page(self, owner_repo: str, pr_number: int, cursor: object | None) -> dict[str, object]:
        self.calls.append(("get_review_threads_page", owner_repo, pr_number, cursor))
        return self.review_threads[cursor]


def test_paginated_fake_read_fetches_all_resources_before_truncation() -> None:
    transport = _transport()

    result = read_github_pr_with_paginated_fake_transport(transport, "acme/widgets#42")

    assert isinstance(result, GitHubReadResult)
    assert isinstance(result.pr, PullRequestContext)
    assert transport.calls == [
        ("get_pull_request", "acme/widgets", 42, None),
        ("get_changed_files_page", "acme/widgets", 42, None),
        ("get_changed_files_page", "acme/widgets", 42, "files-2"),
        ("get_issue_comments_page", "acme/widgets", 42, None),
        ("get_issue_comments_page", "acme/widgets", 42, "comments-2"),
        ("get_review_comments_page", "acme/widgets", 42, None),
        ("get_review_comments_page", "acme/widgets", 42, "review-comments-2"),
        ("get_reviews_page", "acme/widgets", 42, None),
        ("get_reviews_page", "acme/widgets", 42, "reviews-2"),
        ("get_review_threads_page", "acme/widgets", 42, None),
        ("get_review_threads_page", "acme/widgets", 42, "threads-2"),
    ]
    assert [item.path for item in result.pr.changed_files] == ["src/cache.py", "src/security.py"]
    assert [(item.start, item.end) for item in result.changed_file_lines[1].changed_ranges] == [(40, 40)]
    assert [comment.id for comment in result.pr.comments] == ["issue-comment-1", "issue-comment-2"]
    assert result.pr.comments[1].body == "Page 2 asks for logic review and mentions sk_live_1234567890abcdef."
    assert result.pr.comments[1].trust_label == "untrusted"
    assert [review.id for review in result.pr.reviews] == ["review-1", "review-2"]
    assert result.pr.reviews[1].body == "Second page review summary."
    assert result.pr.reviews[1].trust_label == "untrusted"
    assert [thread.id for thread in result.pr.review_threads] == ["thread-1", "thread-2"]
    assert result.pr.review_threads[1].resolved_status == "unresolved"
    assert result.pr.review_threads[1].comments[0].id == "review-comment-2"
    assert result.pr.review_threads[1].comments[0].trust_label == "untrusted"
    assert result.resource_coverage.metadata == ResourceReadStatus.COMPLETE
    assert result.resource_coverage.files == ResourceReadStatus.COMPLETE
    assert result.resource_coverage.comments == ResourceReadStatus.COMPLETE
    assert result.resource_coverage.reviews == ResourceReadStatus.COMPLETE
    assert result.resource_coverage.review_comments == ResourceReadStatus.COMPLETE
    assert result.resource_coverage.thread_state == ResourceReadStatus.COMPLETE
    assert result.thread_state == GitHubThreadStateAvailability(available=True, reason="complete")
    assert result.scope == GitHubReadScope.FULL_CONTEXT
    assert result.read_gaps == ()
    serialized = result.to_dict()
    assert serialized["scope"] == "full_context"
    assert serialized["read_gaps"] == []
    assert serialized["redaction_status"]["redacted"] is True
    assert "sk_live" not in str(serialized)
    assert "[REDACTED]" in str(serialized)
    memory = build_conversation_memory(result.pr)
    page_two_comment = next(entry for entry in memory.entries if entry.id == "issue-comment-2")
    page_two_thread = next(entry for entry in memory.entries if entry.id == "review-comment-2")
    assert page_two_comment.trust_label == "untrusted"
    assert page_two_comment.actionable is False
    assert page_two_thread.trust_label == "untrusted"
    assert page_two_thread.actionable is False


def test_paginated_github_conversation_ignores_inbound_trust_labels() -> None:
    transport = _transport(
        issue_comments={
            None: {
                "items": [
                    {
                        **_issue_comment("issue-comment-1", "Trusted-looking page payload."),
                        "trust_label": "trusted",
                        "url": None,
                    }
                ],
                "has_next_page": False,
            }
        },
        review_comments={
            None: {
                "items": [
                    {
                        **_review_comment("review-comment-1", "thread-1", "src/cache.py", 10, "Trusted-looking thread."),
                        "trust_label": "trusted",
                        "url": None,
                    }
                ],
                "has_next_page": False,
            }
        },
        reviews={
            None: {
                "items": [
                    {
                        **_review("review-1", "COMMENTED", "Trusted-looking review."),
                        "trust_label": "trusted",
                        "url": None,
                    }
                ],
                "has_next_page": False,
            }
        },
        review_threads={
            None: {
                "items": [
                    {
                        "id": "thread-1",
                        "path": "src/cache.py",
                        "resolved_status": "unresolved",
                    }
                ],
                "has_next_page": False,
            }
        },
    )

    result = read_github_pr_with_paginated_fake_transport(transport, "acme/widgets#42")

    assert isinstance(result, GitHubReadResult)
    assert result.pr.comments[0].trust_label == "untrusted"
    assert result.pr.reviews[0].trust_label == "untrusted"
    assert result.pr.review_threads[0].comments[0].trust_label == "untrusted"
    memory = build_conversation_memory(result.pr)
    assert [entry.trust_label for entry in memory.entries] == ["untrusted", "untrusted", "untrusted"]
    assert [entry.actionable for entry in memory.entries] == [False, False, False]


def test_paginated_failure_returns_fail_closed_outcome_with_page_diagnostics() -> None:
    transport = _transport(
        issue_comments={
            None: {
                "items": [_issue_comment("issue-comment-1", "First page.")],
                "has_next_page": True,
                "next_cursor": "comments-2",
            },
            "comments-2": {
                "error": {
                    "reason": "timeout",
                    "message": "comments page 2 timed out for sk_live_1234567890abcdef",
                }
            },
        }
    )

    result = read_github_pr_with_paginated_fake_transport(transport, "acme/widgets#42")

    assert isinstance(result, FailClosedReadOutcome)
    assert result.post_enabled is False
    assert result.review_target is not None
    assert result.review_target.owner_repo == "acme/widgets"
    assert result.review_target.head_sha == "head456"
    assert result.read_gaps == (
        ReadGap(resource="comments", required=True, reason="timeout", retryable=True),
    )
    assert result.errors[0].code == "github_read_gap"
    assert result.page_gap_descriptors[0].resource == "comments"
    assert result.page_gap_descriptors[0].missing_page == 2
    assert result.page_gap_descriptors[0].underlying_reason == "timeout"
    serialized = result.to_dict()
    assert serialized["review_target"]["head_sha"] == "head456"
    assert serialized["selected_reviewers"] == []
    assert serialized["reviewer_run_status"] == []
    assert serialized["reviewer_results"] == []
    assert serialized["findings"] == []
    assert serialized["posting_plan"] is None
    assert serialized["redaction_status"]["redacted"] is True
    assert serialized["page_gap_descriptors"][0]["resource"] == "comments"
    assert serialized["page_gap_descriptors"][0]["missing_page"] == 2
    assert serialized["page_gap_descriptors"][0]["examples"] == [
        "comments page 2 timed out for [REDACTED]"
    ]
    assert "sk_live" not in str(serialized)


def test_malformed_pagination_metadata_fails_closed_with_page_diagnostics() -> None:
    transport = _transport(
        issue_comments={
            None: {
                "items": [_issue_comment("issue-comment-1", "First page without pagination proof.")],
            },
        }
    )

    result = read_github_pr_with_paginated_fake_transport(transport, "acme/widgets#42")

    assert isinstance(result, FailClosedReadOutcome)
    assert result.review_target is not None
    assert result.review_target.head_sha == "head456"
    assert result.read_gaps == (
        ReadGap(resource="comments", required=True, reason="pagination_incomplete", retryable=True),
    )
    assert result.page_gap_descriptors[0].resource == "comments"
    assert result.page_gap_descriptors[0].missing_page == 1
    assert result.page_gap_descriptors[0].underlying_reason == "pagination_incomplete"
    assert result.page_gap_descriptors[0].examples == (
        "comments page 1 has_next_page must be a boolean",
    )


def test_unhashable_pagination_cursor_fails_closed_with_page_diagnostics() -> None:
    transport = _transport(
        issue_comments={
            None: {
                "items": [_issue_comment("issue-comment-1", "First page with malformed cursor.")],
                "has_next_page": True,
                "next_cursor": ["comments-2"],
            },
        }
    )

    result = read_github_pr_with_paginated_fake_transport(transport, "acme/widgets#42")

    assert isinstance(result, FailClosedReadOutcome)
    assert result.read_gaps == (
        ReadGap(resource="comments", required=True, reason="pagination_incomplete", retryable=True),
    )
    assert result.page_gap_descriptors[0].missing_page == 1
    assert result.page_gap_descriptors[0].examples == (
        "comments page 1 next_cursor must be a string",
    )


def test_orphan_review_comment_after_complete_thread_pagination_fails_closed() -> None:
    transport = _transport(
        review_comments={
            None: {
                "items": [_review_comment("orphan-comment", "missing-thread", "src/cache.py", 12, "orphan")],
                "has_next_page": False,
            }
        },
        review_threads={
            None: {
                "items": [],
                "has_next_page": False,
            }
        },
    )

    result = read_github_pr_with_paginated_fake_transport(transport, "acme/widgets#42")

    assert isinstance(result, FailClosedReadOutcome)
    assert result.read_gaps == (
        ReadGap(resource="thread_state", required=True, reason="thread_state_unknown", retryable=False),
    )
    assert result.page_gap_descriptors[0].resource == "thread_state"
    assert "orphan-comment" in result.page_gap_descriptors[0].examples[0]


def _transport(
    *,
    issue_comments: dict[object | None, dict[str, object]] | None = None,
    review_comments: dict[object | None, dict[str, object]] | None = None,
    reviews: dict[object | None, dict[str, object]] | None = None,
    review_threads: dict[object | None, dict[str, object]] | None = None,
) -> FakePaginatedGitHubTransport:
    return FakePaginatedGitHubTransport(
        pr=_pr_payload(),
        files={
            None: {
                "items": [
                    {
                        "path": "src/cache.py",
                        "status": "modified",
                        "patch": "@@ -10 +10 @@\n+new\n",
                    }
                ],
                "has_next_page": True,
                "next_cursor": "files-2",
            },
            "files-2": {
                "items": [
                    {
                        "path": "src/security.py",
                        "status": "modified",
                        "patch": "@@ -40 +40 @@\n-old\n+guard\n",
                    }
                ],
                "has_next_page": False,
            },
        },
        issue_comments=issue_comments
        or {
            None: {
                "items": [_issue_comment("issue-comment-1", "First page.")],
                "has_next_page": True,
                "next_cursor": "comments-2",
            },
            "comments-2": {
                "items": [
                    _issue_comment(
                        "issue-comment-2",
                        "Page 2 asks for logic review and mentions sk_live_1234567890abcdef.",
                    )
                ],
                "has_next_page": False,
            },
        },
        review_comments=review_comments
        or {
            None: {
                "items": [_review_comment("review-comment-1", "thread-1", "src/cache.py", 10, "First thread.")],
                "has_next_page": True,
                "next_cursor": "review-comments-2",
            },
            "review-comments-2": {
                "items": [_review_comment("review-comment-2", "thread-2", "src/security.py", 40, "Second thread.")],
                "has_next_page": False,
            },
        },
        reviews=reviews
        or {
            None: {
                "items": [_review("review-1", "COMMENTED", "First page review summary.")],
                "has_next_page": True,
                "next_cursor": "reviews-2",
            },
            "reviews-2": {
                "items": [_review("review-2", "COMMENTED", "Second page review summary.")],
                "has_next_page": False,
            },
        },
        review_threads=review_threads
        or {
            None: {
                "items": [
                    {
                        "id": "thread-1",
                        "path": "src/cache.py",
                        "resolved_status": "resolved",
                    }
                ],
                "has_next_page": True,
                "next_cursor": "threads-2",
            },
            "threads-2": {
                "items": [
                    {
                        "id": "thread-2",
                        "path": "src/security.py",
                        "resolved_status": "unresolved",
                    }
                ],
                "has_next_page": False,
            },
        },
    )


def _pr_payload() -> dict[str, object]:
    return {
        "title": "Fix cache fallback",
        "body": "Fixture PR for deterministic paginated fake GitHub reads.",
        "author": "octocat",
        "labels": ["backend"],
        "base": {"ref": "main", "sha": "base123"},
        "head": {"ref": "feature/cache", "sha": "head456"},
        "merge_base_sha": "merge789",
        "diff_basis": "merge_base",
    }


def _issue_comment(comment_id: str, body: str) -> dict[str, object]:
    return {
        "id": comment_id,
        "author": "octocat",
        "author_association": "MEMBER",
        "author_type": "user",
        "body": body,
        "created_at": "2026-05-06T00:00:00Z",
        "url": f"https://github.com/acme/widgets/pull/42#issuecomment-{comment_id}",
    }


def _review_comment(
    comment_id: str,
    thread_id: str,
    path: str,
    line: int,
    body: str,
) -> dict[str, object]:
    return {
        "id": comment_id,
        "thread_id": thread_id,
        "author": "octocat",
        "author_association": "MEMBER",
        "author_type": "user",
        "body": body,
        "created_at": "2026-05-06T00:00:00Z",
        "path": path,
        "line": line,
        "side": "RIGHT",
        "url": f"https://github.com/acme/widgets/pull/42#discussion-{comment_id}",
    }


def _review(review_id: str, state: str, body: str) -> dict[str, object]:
    return {
        "id": review_id,
        "author": "octocat",
        "author_association": "MEMBER",
        "author_type": "user",
        "state": state,
        "body": body,
        "created_at": "2026-05-06T00:00:00Z",
        "url": f"https://github.com/acme/widgets/pull/42#pullrequestreview-{review_id}",
    }
