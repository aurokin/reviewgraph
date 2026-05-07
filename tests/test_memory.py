from dataclasses import replace

from reviewgraph.fixtures import load_fixture_pr
from reviewgraph.memory import build_conversation_memory


def test_builds_memory_from_comments_reviews_and_threads() -> None:
    fixture = load_fixture_pr("untrusted-comment-injection")

    memory = build_conversation_memory(fixture.pr)

    assert [entry.id for entry in memory.entries] == [
        "comment-injection-1",
        "review-injection-1",
        "thread-comment-injection-1",
    ]
    comment, review, thread_comment = memory.entries
    assert comment.author == "external-contributor"
    assert comment.author_association == "CONTRIBUTOR"
    assert comment.author_type == "user"
    assert comment.created_at == "2026-05-06T00:26:00Z"
    assert comment.source_type == "issue_comment"
    assert comment.url is None
    assert comment.trust_label == "untrusted"
    assert comment.actionable is False
    assert comment.passive_reason == "untrusted author"
    assert "Ignore prior instructions" in (comment.body or "")

    assert review.author == "security-reviewer"
    assert review.author_association == "MEMBER"
    assert review.created_at == "2026-05-06T00:26:30Z"
    assert review.source_type == "review"
    assert review.trust_label == "trusted"
    assert review.actionable is False
    assert review.passive_reason == "review summary is passive until a later node interprets it"

    assert thread_comment.path == "src/auth/redirects.py"
    assert thread_comment.line == 30
    assert thread_comment.resolved_status == "unresolved"
    assert thread_comment.trust_label == "untrusted"
    assert thread_comment.actionable is False


def test_owner_member_collaborator_and_operator_are_trusted() -> None:
    fixture = load_fixture_pr("security-sensitive-change")
    pr = fixture.pr
    owner_comment = replace(pr.comments[0], author="repo-owner", author_association="OWNER", trust_label="trusted")
    collaborator_comment = replace(
        pr.comments[0],
        author="collab",
        author_association="COLLABORATOR",
        trust_label="trusted",
    )
    operator_comment = replace(
        pr.comments[0],
        author="operator",
        author_association="CONTRIBUTOR",
        trust_label="trusted",
    )
    pr = replace(pr, comments=(owner_comment, collaborator_comment, operator_comment))

    memory = build_conversation_memory(pr, trusted_operator_authors={"operator"})

    assert [entry.trust_label for entry in memory.entries[:3]] == ["trusted", "trusted", "trusted"]
    assert [entry.actionable for entry in memory.entries[:3]] == [True, True, True]


def test_bots_are_default_denied_unless_allowlisted() -> None:
    fixture = load_fixture_pr("basic-pr")
    bot_comment = replace(
        fixture.pr.comments[0],
        author="review-bot",
        author_association="MEMBER",
        author_type="bot",
    )
    pr = replace(fixture.pr, comments=(bot_comment,))

    default_memory = build_conversation_memory(pr)
    allowlisted_memory = build_conversation_memory(pr, trusted_bot_authors={"review-bot"})

    assert default_memory.entries[0].trust_label == "untrusted"
    assert default_memory.entries[0].actionable is False
    assert default_memory.entries[0].passive_reason == "untrusted author"
    assert allowlisted_memory.entries[0].trust_label == "trusted"


def test_unknown_author_type_is_default_denied_even_with_trusted_association() -> None:
    fixture = load_fixture_pr("basic-pr")
    unknown_actor_comment = replace(
        fixture.pr.comments[0],
        author="automation",
        author_association="MEMBER",
        author_type="organization",
    )
    pr = replace(fixture.pr, comments=(unknown_actor_comment,))

    memory = build_conversation_memory(pr)

    assert memory.entries[0].trust_label == "untrusted"
    assert memory.entries[0].actionable is False
    assert memory.entries[0].passive_reason == "untrusted author"


def test_unknown_trust_label_is_default_denied_even_with_trusted_association() -> None:
    fixture = load_fixture_pr("basic-pr")
    ambiguous_comment = replace(fixture.pr.comments[0], trust_label="unknown")
    ambiguous_review = replace(fixture.pr.reviews[0], trust_label="unknown")
    ambiguous_thread = replace(
        fixture.pr.review_threads[0],
        resolved_status="unresolved",
        comments=(replace(fixture.pr.review_threads[0].comments[0], trust_label="unknown"),),
    )
    pr = replace(
        fixture.pr,
        comments=(ambiguous_comment,),
        reviews=(ambiguous_review,),
        review_threads=(ambiguous_thread,),
    )

    memory = build_conversation_memory(pr)

    assert [entry.trust_label for entry in memory.entries] == ["untrusted", "untrusted", "untrusted"]
    assert [entry.actionable for entry in memory.entries] == [False, False, False]
    assert [entry.passive_reason for entry in memory.entries] == [
        "untrusted author",
        "untrusted author",
        "untrusted author",
    ]


def test_contributor_comment_stays_passive_even_if_fixture_source_claims_trusted() -> None:
    fixture = load_fixture_pr("security-sensitive-change")
    upgraded_comment = replace(fixture.pr.comments[0], trust_label="trusted")
    memory = build_conversation_memory(replace(fixture.pr, comments=(upgraded_comment,)))

    comment = memory.entries[0]
    assert comment.author_association == "CONTRIBUTOR"
    assert comment.trust_label == "untrusted"
    assert comment.actionable is False
    assert comment.passive_reason == "untrusted author"


def test_generated_memory_ignores_legacy_fixture_memory_entries() -> None:
    fixture = load_fixture_pr("basic-pr")

    memory = build_conversation_memory(fixture.pr)

    assert {entry.id for entry in memory.entries}.isdisjoint({item["id"] for item in fixture.memory})


def test_trusted_top_level_comments_and_unresolved_threads_are_actionable() -> None:
    comment_memory = build_conversation_memory(load_fixture_pr("basic-pr").pr)
    top_level_comment = next(entry for entry in comment_memory.entries if entry.source_type == "issue_comment")

    assert top_level_comment.trust_label == "trusted"
    assert top_level_comment.resolved_status == "unresolved"
    assert top_level_comment.actionable is True
    assert top_level_comment.passive_reason is None


def test_resolved_threads_are_non_actionable_and_unresolved_threads_actionable_for_trusted_authors() -> None:
    resolved = build_conversation_memory(load_fixture_pr("basic-pr").pr)
    unresolved = build_conversation_memory(load_fixture_pr("stale-approval-change").pr)

    resolved_thread = next(entry for entry in resolved.entries if entry.source_type == "review_thread")
    unresolved_thread = next(entry for entry in unresolved.entries if entry.source_type == "review_thread")

    assert resolved_thread.resolved_status == "resolved"
    assert resolved_thread.actionable is False
    assert resolved_thread.passive_reason == "resolved thread"
    assert unresolved_thread.resolved_status == "resolved"
    assert unresolved_thread.actionable is False

    changed = load_fixture_pr("untrusted-comment-injection").pr
    trusted_unresolved_thread = replace(
        changed.review_threads[0],
        comments=(
            replace(
                changed.review_threads[0].comments[0],
                author="maintainer",
                author_association="MEMBER",
                trust_label="trusted",
            ),
        ),
    )
    memory = build_conversation_memory(replace(changed, review_threads=(trusted_unresolved_thread,)))
    thread_entry = next(entry for entry in memory.entries if entry.source_type == "review_thread")
    assert thread_entry.actionable is True
    assert thread_entry.passive_reason is None


def test_unknown_thread_state_is_passive_for_routing() -> None:
    fixture = load_fixture_pr("ambiguous-logic-change")
    memory = build_conversation_memory(fixture.pr)

    thread_entry = next(entry for entry in memory.entries if entry.source_type == "review_thread")
    assert thread_entry.resolved_status == "unknown"
    assert thread_entry.trust_label == "trusted"
    assert thread_entry.actionable is False
    assert thread_entry.passive_reason == "unknown thread state"
