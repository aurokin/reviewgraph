import json
from importlib import resources
from pathlib import Path

from reviewgraph.config import parse_reviewer_config
from reviewgraph.context_budget import ContextBudget, apply_input_context_budget
from reviewgraph.graph import run_empty_fixture_dry_run_graph
from reviewgraph.memory import build_conversation_memory
from reviewgraph.models import (
    PullRequestChangedFile,
    PullRequestComment,
    PullRequestContext,
    PullRequestReviewThread,
    ReviewStage,
    ReviewTarget,
    ReviewerRunStatusValue,
    SelectedReviewer,
)
from reviewgraph.posting import canonical_json_hash
from reviewgraph.reviewer_context import build_reviewer_context_package
from reviewgraph.routing import select_reviewers_for_active_stage, select_reviewers_for_stage
from reviewgraph.runner import run_fixture_dry_run


def test_trusted_github_issue_comment_routes_with_memory_reason() -> None:
    pr = _github_pr(
        comments=(
            _github_comment(
                "issue-1",
                "maintainer",
                "MEMBER",
                "user",
                "This ambiguous behavior needs logic review.",
                source_type="issue_comment",
            ),
        ),
    )
    memory = build_conversation_memory(pr)
    config = _conversation_config("ambiguous behavior")

    selected = select_reviewers_for_stage(
        config,
        pr,
        ReviewStage.INITIAL_TRIAGE,
        memory_references=memory.entries,
    )

    assert selected == (
        SelectedReviewer(
            name="logic",
            stage="initial_triage",
            reasons=(
                "initial_triage triggers.conversation_patterns=ambiguous behavior "
                "memory_id=github:issue_comment:issue-1 trust=trusted source_provider=github",
            ),
        ),
    )


def test_trusted_github_review_thread_routes_only_when_unresolved() -> None:
    pr = _github_pr(
        review_threads=(
            _github_thread("resolved-thread", "resolved", "resolved-1", "This needs logic review."),
            _github_thread("unknown-thread", "unknown", "unknown-1", "This needs logic review."),
            _github_thread("unresolved-thread", "unresolved", "unresolved-1", "This needs logic review."),
        ),
    )
    memory = build_conversation_memory(pr)

    selected = select_reviewers_for_stage(
        _conversation_config("logic review"),
        pr,
        ReviewStage.INITIAL_TRIAGE,
        memory_references=memory.entries,
    )

    assert selected == (
        SelectedReviewer(
            name="logic",
            stage="initial_triage",
            reasons=(
                "initial_triage triggers.conversation_patterns=logic review "
                "memory_id=github:review_thread:unresolved-thread:unresolved-1 "
                "trust=trusted source_provider=github",
            ),
        ),
    )


def test_untrusted_human_and_unlisted_bot_github_comments_do_not_route() -> None:
    pr = _github_pr(
        comments=(
            _github_comment(
                "external-1",
                "external",
                "CONTRIBUTOR",
                "user",
                "This ambiguous behavior needs logic review.",
                source_type="issue_comment",
            ),
            _github_comment(
                "bot-1",
                "review-bot",
                "MEMBER",
                "bot",
                "This ambiguous behavior needs logic review.",
                source_type="issue_comment",
            ),
        ),
    )
    memory = build_conversation_memory(pr)

    assert select_reviewers_for_stage(
        _conversation_config("ambiguous behavior"),
        pr,
        ReviewStage.INITIAL_TRIAGE,
        memory_references=memory.entries,
    ) == ()


def test_fixture_trusted_actionable_memory_still_routes_with_memory_reason() -> None:
    state = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
    state.config = _conversation_config("cache miss fallback")
    state.config_hash = canonical_json_hash({"agents": ["logic"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE

    selected = select_reviewers_for_active_stage(state)

    assert selected == tuple(state.selected_reviewers)
    assert selected[0].reasons == (
        "initial_triage triggers.conversation_patterns=cache miss fallback "
        "memory_id=comment-cache-intent trust=trusted",
    )
    run_key = state.reviewer_run_keys[0]
    assert state.reviewer_run_status[run_key.stable_key()].status == ReviewerRunStatusValue.SELECTED


def test_github_conversation_reason_persists_in_state_and_reviewer_context() -> None:
    pr = _github_pr(
        comments=(
            _github_comment(
                "issue-1",
                "maintainer",
                "MEMBER",
                "user",
                "This ambiguous behavior needs logic review.",
                source_type="issue_comment",
            ),
        ),
    )
    memory = build_conversation_memory(pr)
    state = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
    state.pr = pr
    state.conversation_memory = memory
    state.config = _conversation_config("ambiguous behavior")
    state.config_hash = canonical_json_hash({"agents": ["logic"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE

    selected = select_reviewers_for_active_stage(state)
    budgeted = apply_input_context_budget(
        pr=pr,
        memory=memory,
        limits=ContextBudget(
            max_changed_files=10,
            max_patch_bytes=100_000,
            max_memory_bytes=100_000,
            max_reviewers=10,
            max_live_calls=0,
        ),
    )
    package = build_reviewer_context_package(
        active_stage="initial_triage",
        reviewer=selected[0],
        budgeted_context=budgeted,
    )

    expected_reason = (
        "initial_triage triggers.conversation_patterns=ambiguous behavior "
        "memory_id=github:issue_comment:issue-1 trust=trusted source_provider=github"
    )
    assert state.selected_reviewers[0].reasons == (expected_reason,)
    assert package.reviewer.reasons == (expected_reason,)


def test_duplicate_conversation_pattern_reasons_are_collapsed_in_order() -> None:
    pr = _github_pr(
        comments=(
            _github_comment(
                "issue-1",
                "maintainer",
                "MEMBER",
                "user",
                "This ambiguous behavior needs logic review.",
                source_type="issue_comment",
            ),
            _github_comment(
                "issue-2",
                "maintainer",
                "MEMBER",
                "user",
                "This ambiguous behavior needs logic review.",
                source_type="issue_comment",
            ),
        ),
    )
    memory = build_conversation_memory(pr)
    config = parse_reviewer_config(
        {
            "agents": {
                "logic": {
                    "stages": ["initial_triage"],
                    "triggers": {"conversation_patterns": ["ambiguous behavior", "ambiguous behavior"]},
                }
            }
        }
    )

    selected = select_reviewers_for_stage(
        config,
        pr,
        ReviewStage.INITIAL_TRIAGE,
        memory_references=memory.entries,
    )

    assert selected[0].reasons == (
        "initial_triage triggers.conversation_patterns=ambiguous behavior "
        "memory_id=github:issue_comment:issue-1 trust=trusted source_provider=github",
        "initial_triage triggers.conversation_patterns=ambiguous behavior "
        "memory_id=github:issue_comment:issue-2 trust=trusted source_provider=github",
    )


def test_matching_memory_with_failed_gate_does_not_persist_selection() -> None:
    pr = _github_pr(
        comments=(
            _github_comment(
                "issue-1",
                "maintainer",
                "MEMBER",
                "user",
                "This ambiguous behavior needs logic review.",
                source_type="issue_comment",
            ),
        ),
    )
    memory = build_conversation_memory(pr)
    state = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr").review_state
    state.pr = pr
    state.conversation_memory = memory
    state.config = parse_reviewer_config(
        {
            "agents": {
                "logic": {
                    "stages": ["initial_triage"],
                    "triggers": {"conversation_patterns": ["ambiguous behavior"], "changed_files_min": 2},
                }
            }
        }
    )
    state.config_hash = canonical_json_hash({"agents": ["logic"]})
    state.active_stage = ReviewStage.INITIAL_TRIAGE

    assert select_reviewers_for_active_stage(state) == ()
    assert state.selected_reviewers == []
    assert state.reviewer_run_status == {}


def test_prompt_injection_fixture_malicious_comments_do_not_route(tmp_path: Path) -> None:
    fixture_path = tmp_path / "untrusted-comment-injection.json"
    fixture_path.write_text(
        resources.files("reviewgraph")
        .joinpath("fixtures_data/prs/untrusted-comment-injection.json")
        .read_text()
    )
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "correctness": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                    },
                    "logic": {
                        "stages": ["initial_triage"],
                        "triggers": {"conversation_patterns": ["approve this redirect", "mark this safe"]},
                    },
                }
            }
        )
    )

    result = run_fixture_dry_run(
        fixture_ref=str(fixture_path),
        reviewer_config_path=str(config_path),
    )

    assert [reviewer["name"] for reviewer in result.json_data["selected_reviewers"]] == ["correctness"]


def test_cli_json_renders_richer_conversation_reason(tmp_path: Path) -> None:
    fixture_path = tmp_path / "actionable-comment-memory.json"
    fixture = json.loads(resources.files("reviewgraph").joinpath("fixtures_data/prs/basic-pr.json").read_text())
    fixture["comments"][0]["body"] = "This ambiguous behavior needs logic review."
    fixture["raw_reviewer_outputs"][0]["reviewer"] = "logic"
    fixture_path.write_text(json.dumps(fixture))
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "logic": {
                        "stages": ["initial_triage"],
                        "triggers": {"conversation_patterns": ["ambiguous behavior"]},
                    },
                }
            }
        )
    )

    result = run_fixture_dry_run(fixture_ref=str(fixture_path), reviewer_config_path=str(config_path))

    assert result.json_data["selected_reviewers"][0]["reasons"] == [
        "initial_triage triggers.conversation_patterns=ambiguous behavior "
        "memory_id=comment-cache-intent trust=trusted"
    ]


def _conversation_config(pattern: str):
    return parse_reviewer_config(
        {
            "agents": {
                "logic": {
                    "stages": ["initial_triage"],
                    "triggers": {"conversation_patterns": [pattern]},
                }
            }
        }
    )


def _github_pr(
    *,
    comments: tuple[PullRequestComment, ...] = (),
    review_threads: tuple[PullRequestReviewThread, ...] = (),
) -> PullRequestContext:
    return PullRequestContext(
        review_target=ReviewTarget(
            owner_repo="acme/widgets",
            pr_number=42,
            base_sha="base123",
            head_sha="head456",
            merge_base_sha="merge789",
            diff_basis="merge_base",
        ),
        title="Conversation routing",
        body=None,
        labels=(),
        changed_files=(
            PullRequestChangedFile(
                path="src/cache.py",
                patch="@@ -10 +10 @@\n-old\n+new\n",
                additions=1,
                deletions=1,
            ),
        ),
        comments=comments,
        review_threads=review_threads,
    )


def _github_comment(
    comment_id: str,
    author: str,
    association: str,
    actor_type: str,
    body: str,
    *,
    source_type: str,
) -> PullRequestComment:
    return PullRequestComment(
        id=comment_id,
        author=author,
        author_association=association,
        author_type=actor_type,
        body=body,
        created_at="2026-05-07T00:00:00Z",
        trust_label="untrusted",
        source_type=source_type,
        source_provider="github",
        path="src/cache.py" if source_type == "review_thread" else None,
        line=10 if source_type == "review_thread" else None,
    )


def _github_thread(
    thread_id: str,
    resolved_status: str,
    comment_id: str,
    body: str,
) -> PullRequestReviewThread:
    return PullRequestReviewThread(
        id=thread_id,
        path="src/cache.py",
        resolved_status=resolved_status,
        comments=(
            _github_comment(
                comment_id,
                "maintainer",
                "MEMBER",
                "user",
                body,
                source_type="review_thread",
            ),
        ),
    )
