from __future__ import annotations

from reviewgraph.models import (
    MemoryReference,
    PRConversationMemory,
    PullRequestComment,
    PullRequestContext,
    PullRequestReview,
    PullRequestReviewThread,
)


TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def build_conversation_memory(
    pr: PullRequestContext,
    *,
    trusted_operator_authors: set[str] | None = None,
    trusted_bot_authors: set[str] | None = None,
) -> PRConversationMemory:
    trusted_operator_authors = trusted_operator_authors or set()
    trusted_bot_authors = trusted_bot_authors or set()
    entries: list[MemoryReference] = []

    for comment in pr.comments:
        entries.append(
            _memory_from_comment(
                comment,
                resolved_status="unresolved",
                trusted_operator_authors=trusted_operator_authors,
                trusted_bot_authors=trusted_bot_authors,
            )
        )
    for review in pr.reviews:
        entries.append(
            _memory_from_review(
                review,
                trusted_operator_authors=trusted_operator_authors,
                trusted_bot_authors=trusted_bot_authors,
            )
        )
    for thread in pr.review_threads:
        thread_actionable = _thread_is_actionable(thread)
        for comment in thread.comments:
            entries.append(
                _memory_from_comment(
                    comment,
                    resolved_status=thread.resolved_status,
                    trusted_operator_authors=trusted_operator_authors,
                    trusted_bot_authors=trusted_bot_authors,
                    passive_reason=None if thread_actionable else _passive_thread_reason(thread),
                    force_passive=not thread_actionable,
                    fallback_path=thread.path,
                )
            )

    return PRConversationMemory(entries=tuple(entries))


def _memory_from_comment(
    comment: PullRequestComment,
    *,
    resolved_status: str,
    trusted_operator_authors: set[str],
    trusted_bot_authors: set[str],
    passive_reason: str | None = None,
    force_passive: bool = False,
    fallback_path: str | None = None,
) -> MemoryReference:
    trusted = _is_trusted(
        comment.author,
        comment.author_association,
        comment.author_type,
        trusted_operator_authors,
        trusted_bot_authors,
    )
    actionable = trusted and not force_passive and resolved_status == "unresolved"
    return MemoryReference(
        id=comment.id,
        trust_label="trusted" if trusted else "untrusted",
        resolved_status=resolved_status,
        source_type=comment.source_type,
        body=comment.body,
        author=comment.author,
        author_association=comment.author_association,
        author_type=comment.author_type,
        created_at=comment.created_at,
        url=comment.url,
        path=comment.path or fallback_path,
        line=comment.line,
        actionable=actionable,
        passive_reason=None if actionable else passive_reason or _passive_reason(trusted, resolved_status),
    )


def _memory_from_review(
    review: PullRequestReview,
    *,
    trusted_operator_authors: set[str],
    trusted_bot_authors: set[str],
) -> MemoryReference:
    trusted = _is_trusted(
        review.author,
        review.author_association,
        review.author_type,
        trusted_operator_authors,
        trusted_bot_authors,
    )
    return MemoryReference(
        id=review.id,
        trust_label="trusted" if trusted else "untrusted",
        resolved_status="unresolved",
        source_type=review.source_type,
        body=review.body,
        author=review.author,
        author_association=review.author_association,
        author_type=review.author_type,
        created_at=review.created_at,
        url=review.url,
        actionable=False,
        passive_reason="review summary is passive until a later node interprets it"
        if trusted
        else "untrusted author",
    )


def _is_trusted(
    author: str,
    author_association: str,
    author_type: str,
    trusted_operator_authors: set[str],
    trusted_bot_authors: set[str],
) -> bool:
    actor_type = author_type.casefold()
    if actor_type == "bot":
        return author in trusted_bot_authors
    if actor_type != "user":
        return False
    association = author_association.upper()
    return author in trusted_operator_authors or association in TRUSTED_ASSOCIATIONS


def _thread_is_actionable(thread: PullRequestReviewThread) -> bool:
    return thread.resolved_status == "unresolved"


def _passive_thread_reason(thread: PullRequestReviewThread) -> str:
    if thread.resolved_status == "resolved":
        return "resolved thread"
    if thread.resolved_status == "unknown":
        return "unknown thread state"
    return "thread is passive"


def _passive_reason(trusted: bool, resolved_status: str) -> str:
    if not trusted:
        return "untrusted author"
    if resolved_status == "resolved":
        return "resolved thread"
    if resolved_status == "unknown":
        return "unknown thread state"
    return "passive memory"

