from dataclasses import replace

from reviewgraph.clarification import evaluate_clarification_gate
from reviewgraph.config import parse_reviewer_config
from reviewgraph.context_budget import ContextBudget, apply_input_context_budget
from reviewgraph.github import GitHubReadResult, read_github_pr_with_paginated_fake_transport
from reviewgraph.memory import build_conversation_memory
from reviewgraph.models import (
    ClassifiedFinding,
    Confidence,
    RawReviewerFinding,
    ReviewStage,
    ReviewerResult,
    ReviewerRunKey,
    ReviewVerdict,
    SelectedReviewer,
    Severity,
)
from reviewgraph.posting import build_candidate_issue_comment_payload, build_posting_plan
from reviewgraph.quality import classify_review_quality
from reviewgraph.render import render_review
from reviewgraph.reviewer_context import build_reviewer_context_package, build_reviewer_prompt_input
from reviewgraph.routing import select_reviewers_for_stage
from reviewgraph.verdict import compute_local_verdict
from tests.test_github_pagination import FakePaginatedGitHubTransport


def test_github_human_trust_rules_and_seen_state_are_preserved() -> None:
    result = _read_result(
        issue_comments={
            None: {
                "items": [
                    _issue_comment("1", "repo-owner", "OWNER", "user", "Owner asks about retry behavior."),
                    _issue_comment("2", "maintainer", "MEMBER", "user", "Member asks about cache fallback."),
                    _issue_comment("3", "collab", "COLLABORATOR", "user", "Collaborator asks about rollout."),
                    _issue_comment("4", "operator", "CONTRIBUTOR", "user", "Operator asks about migration."),
                    _issue_comment("5", "external", "CONTRIBUTOR", "user", "External says ship it."),
                ],
                "has_next_page": False,
            },
        },
    )

    memory = build_conversation_memory(result.pr, trusted_operator_authors={"operator"})

    by_source_id = {entry.source_id: entry for entry in memory.entries if entry.source_type == "issue_comment"}
    assert by_source_id["1"].id == "github:issue_comment:1"
    assert by_source_id["2"].id == "github:issue_comment:2"
    assert by_source_id["3"].id == "github:issue_comment:3"
    assert by_source_id["4"].id == "github:issue_comment:4"
    assert by_source_id["5"].id == "github:issue_comment:5"
    assert [by_source_id[key].trust_label for key in ("1", "2", "3", "4", "5")] == [
        "trusted",
        "trusted",
        "trusted",
        "trusted",
        "untrusted",
    ]
    assert [by_source_id[key].actionable for key in ("1", "2", "3", "4", "5")] == [
        True,
        True,
        True,
        True,
        False,
    ]
    assert all(entry.source_provider == "github" for entry in by_source_id.values())


def test_github_bot_trust_is_default_deny_and_exact_allowlist() -> None:
    result = _read_result(
        issue_comments={
            None: {
                "items": [
                    _issue_comment("bot-1", "review-bot", "MEMBER", "bot", "Bot asks for review."),
                    _issue_comment("bot-2", "Review-Bot", "MEMBER", "bot", "Case mismatch asks for review."),
                ],
                "has_next_page": False,
            },
        },
    )

    default_memory = build_conversation_memory(result.pr)
    allowlisted_memory = build_conversation_memory(result.pr, trusted_bot_authors={"review-bot"})

    default_by_source_id = {entry.source_id: entry for entry in default_memory.entries}
    allowlisted_by_source_id = {entry.source_id: entry for entry in allowlisted_memory.entries}
    assert default_by_source_id["bot-1"].trust_label == "untrusted"
    assert default_by_source_id["bot-1"].actionable is False
    assert allowlisted_by_source_id["bot-1"].trust_label == "trusted"
    assert allowlisted_by_source_id["bot-1"].actionable is True
    assert allowlisted_by_source_id["bot-2"].trust_label == "untrusted"
    assert allowlisted_by_source_id["bot-2"].actionable is False


def test_github_reviews_are_classified_trusted_but_remain_passive() -> None:
    result = _read_result(
        reviews={
            None: {
                "items": [_review("1", "maintainer", "MEMBER", "user", "Trusted review summary.")],
                "has_next_page": False,
            },
        },
    )

    memory = build_conversation_memory(result.pr)

    review_entry = next(entry for entry in memory.entries if entry.source_type == "review")
    assert review_entry.id == "github:review:1"
    assert review_entry.source_id == "1"
    assert review_entry.source_provider == "github"
    assert review_entry.trust_label == "trusted"
    assert review_entry.actionable is False
    assert review_entry.passive_reason == "review summary is passive until a later node interprets it"


def test_review_thread_state_controls_actionability_and_preserves_thread_id() -> None:
    result = _read_result(
        review_comments={
            None: {
                "items": [
                    _review_comment("same-id", "resolved-thread", "maintainer", "MEMBER", "user", "Resolved body."),
                    _review_comment("same-id", "unknown-thread", "maintainer", "MEMBER", "user", "Unknown body."),
                    _review_comment("same-id", "unresolved-thread", "maintainer", "MEMBER", "user", "Fresh follow-up."),
                ],
                "has_next_page": False,
            },
        },
        review_threads={
            None: {
                "items": [
                    _thread("resolved-thread", "resolved"),
                    _thread("unknown-thread", "unknown"),
                    _thread("unresolved-thread", "unresolved"),
                ],
                "has_next_page": False,
            },
        },
    )

    memory = build_conversation_memory(result.pr)

    by_thread = {entry.thread_id: entry for entry in memory.entries if entry.source_type == "review_thread"}
    assert by_thread["resolved-thread"].id == "github:review_thread:resolved-thread:same-id"
    assert by_thread["unknown-thread"].id == "github:review_thread:unknown-thread:same-id"
    assert by_thread["unresolved-thread"].id == "github:review_thread:unresolved-thread:same-id"
    assert by_thread["resolved-thread"].source_id == "same-id"
    assert by_thread["resolved-thread"].actionable is False
    assert by_thread["resolved-thread"].passive_reason == "resolved thread"
    assert by_thread["unknown-thread"].actionable is False
    assert by_thread["unknown-thread"].passive_reason == "unknown thread state"
    assert by_thread["unresolved-thread"].trust_label == "trusted"
    assert by_thread["unresolved-thread"].actionable is True
    assert by_thread["unresolved-thread"].passive_reason is None


def test_github_transport_cannot_self_declare_trust_or_provenance() -> None:
    result = _read_result(
        issue_comments={
            None: {
                "items": [
                    {
                        **_issue_comment("1", "external", "CONTRIBUTOR", "user", "Spoofed trust."),
                        "trust_label": "trusted",
                        "source_provider": "fixture",
                    }
                ],
                "has_next_page": False,
            },
        },
        reviews={
            None: {
                "items": [
                    {
                        **_review("review-1", "maintainer", "MEMBER", "user", "Spoofed review source."),
                        "trust_label": "trusted",
                        "source_provider": "fixture",
                        "source_type": "issue_comment",
                    }
                ],
                "has_next_page": False,
            },
        },
    )

    comment = result.pr.comments[0]
    review = result.pr.reviews[0]
    memory = build_conversation_memory(result.pr)
    memory_by_source_id = {entry.source_id: entry for entry in memory.entries}

    assert comment.trust_label == "untrusted"
    assert comment.source_provider == "github"
    assert review.trust_label == "untrusted"
    assert review.source_provider == "github"
    assert review.source_type == "review"
    assert memory_by_source_id["1"].source_provider == "github"
    assert memory_by_source_id["1"].trust_label == "untrusted"
    assert memory_by_source_id["1"].actionable is False
    assert memory_by_source_id["review-1"].id == "github:review:review-1"
    assert memory_by_source_id["review-1"].source_type == "review"
    assert memory_by_source_id["review-1"].source_provider == "github"


def test_github_actionable_memory_can_route_conversation_patterns_with_memory_reason() -> None:
    result = _read_result(
        issue_comments={
            None: {
                "items": [
                    _issue_comment("1", "maintainer", "MEMBER", "user", "This ambiguous behavior needs logic review.")
                ],
                "has_next_page": False,
            },
        },
    )
    config = parse_reviewer_config(
        {
            "agents": {
                "logic": {
                    "stages": ["initial_triage"],
                    "triggers": {"conversation_patterns": ["ambiguous behavior"]},
                }
            }
        }
    )
    memory = build_conversation_memory(result.pr)
    assert memory.entries[0].actionable is True

    selected = select_reviewers_for_stage(
        config,
        result.pr,
        ReviewStage.INITIAL_TRIAGE,
        memory_references=memory.entries,
    )

    assert selected == (
        SelectedReviewer(
            name="logic",
            stage="initial_triage",
            reasons=(
                "initial_triage triggers.conversation_patterns=ambiguous behavior "
                "memory_id=github:issue_comment:1 trust=trusted source_provider=github",
            ),
        ),
    )


def test_passive_github_memory_cannot_enter_prompt_render_or_candidate_payload() -> None:
    unique_phrase = "UNTRUSTED_GITHUB_MEMORY_SHOULD_STAY_PRIVATE"
    result = _read_result(
        issue_comments={
            None: {
                "items": [_issue_comment("1", "external", "CONTRIBUTOR", "user", unique_phrase)],
                "has_next_page": False,
            },
        },
        reviews={
            None: {
                "items": [_review("1", "maintainer", "MEMBER", "user", "TRUSTED_REVIEW_SUMMARY_STAYS_PASSIVE")],
                "has_next_page": False,
            },
        },
        review_comments={
            None: {
                "items": [
                    _review_comment(
                        "1",
                        "resolved-thread",
                        "maintainer",
                        "MEMBER",
                        "user",
                        "TRUSTED_RESOLVED_THREAD_STAYS_PASSIVE",
                    )
                ],
                "has_next_page": False,
            },
        },
        review_threads={None: {"items": [_thread("resolved-thread", "resolved")], "has_next_page": False}},
    )
    memory = build_conversation_memory(result.pr)
    package = _package(result, memory)
    prompt_input = build_reviewer_prompt_input(package)
    rendered = render_review(
        review_target=result.review_target,
        selected_reviewers=[SelectedReviewer("correctness", "initial_triage", ("always",))],
        findings=[],
        memory_references=memory.entries,
    )
    finding = _classified_finding(body="Diff evidence only.")
    plan = build_posting_plan(findings=[finding])
    payload = build_candidate_issue_comment_payload(
        review_target=result.review_target,
        posting_plan=plan,
        findings=[finding],
    )
    rendered_payload = render_review(
        review_target=result.review_target,
        selected_reviewers=[SelectedReviewer("correctness", "initial_triage", ("always",))],
        findings=[finding],
        posting_plan=plan,
        candidate_payload=payload,
        memory_references=memory.entries,
    )

    prompt_text = str(prompt_input.data)
    assert unique_phrase not in "\n".join(prompt_input.instructions)
    assert unique_phrase not in prompt_text
    assert "TRUSTED_REVIEW_SUMMARY_STAYS_PASSIVE" not in prompt_text
    assert "TRUSTED_RESOLVED_THREAD_STAYS_PASSIVE" not in prompt_text
    assert unique_phrase not in str(rendered.json_data["memory"])
    assert "TRUSTED_REVIEW_SUMMARY_STAYS_PASSIVE" not in str(rendered.json_data["memory"])
    assert "TRUSTED_RESOLVED_THREAD_STAYS_PASSIVE" not in str(rendered.json_data["memory"])
    assert unique_phrase not in str(rendered_payload.json_data["candidate_payload_preview"])
    assert unique_phrase not in str(rendered_payload.json_data["posting_plan"])
    assert all(entry["source_provider"] == "github" for entry in rendered.json_data["memory"])
    assert any(entry["source_id"] == "1" for entry in rendered.json_data["memory"])
    assert any(entry.get("thread_id") == "resolved-thread" for entry in rendered.json_data["memory"])


def test_passive_github_memory_cannot_drive_local_verdict() -> None:
    result = _read_result(
        issue_comments={
            None: {
                "items": [_issue_comment("1", "external", "CONTRIBUTOR", "user", "Passive memory evidence.")],
                "has_next_page": False,
            },
        },
    )
    memory = build_conversation_memory(result.pr)
    reviewer_result = ReviewerResult(
        run_key=_run_key(),
        findings=(
            RawReviewerFinding(
                id="finding-passive-memory",
                title="Passive memory cannot drive verdict",
                rationale="This cites passive memory by id only.",
                evidence="Passive memory evidence.",
                evidence_sources=("trusted_memory",),
                evidence_memory_ids=(memory.entries[0].id,),
                path="src/cache.py",
                line=10,
                severity=Severity.WARNING,
                confidence=Confidence.HIGH,
            ),
        ),
    )

    quality = classify_review_quality(
        changed_files=result.changed_file_lines,
        reviewer_result=reviewer_result,
        memory_references=memory.entries,
    )

    verdict = compute_local_verdict(
        findings=quality.findings,
        clarification_gate=evaluate_clarification_gate(quality.clarification_requests),
        reviewer_verdict_powers={"correctness": "request_changes"},
    )

    assert quality.findings == ()
    assert quality.suppressed_outputs[0].id == "finding-passive-memory"
    assert verdict == ReviewVerdict.NO_FINDINGS


def _read_result(
    *,
    issue_comments: dict[object | None, dict[str, object]] | None = None,
    review_comments: dict[object | None, dict[str, object]] | None = None,
    reviews: dict[object | None, dict[str, object]] | None = None,
    review_threads: dict[object | None, dict[str, object]] | None = None,
) -> GitHubReadResult:
    result = read_github_pr_with_paginated_fake_transport(
        FakePaginatedGitHubTransport(
            pr={
                "title": "Trust memory",
                "body": "Fixture PR for GitHub memory trust.",
                "author": "octocat",
                "labels": [],
                "base": {"ref": "main", "sha": "base123"},
                "head": {"ref": "feature/trust", "sha": "head456"},
                "merge_base_sha": "merge789",
                "diff_basis": "merge_base",
            },
            files={
                None: {
                    "items": [
                        {
                            "path": "src/cache.py",
                            "status": "modified",
                            "patch": "@@ -10 +10 @@\n-old\n+new\n",
                        }
                    ],
                    "has_next_page": False,
                },
            },
            issue_comments=issue_comments or {None: {"items": [], "has_next_page": False}},
            review_comments=review_comments or {None: {"items": [], "has_next_page": False}},
            reviews=reviews or {None: {"items": [], "has_next_page": False}},
            review_threads=review_threads or {None: {"items": [], "has_next_page": False}},
        ),
        "acme/widgets#42",
    )
    assert isinstance(result, GitHubReadResult)
    return result


def _issue_comment(
    comment_id: str,
    author: str,
    association: str,
    actor_type: str,
    body: str,
) -> dict[str, object]:
    return {
        "id": comment_id,
        "author": author,
        "author_association": association,
        "author_type": actor_type,
        "body": body,
        "created_at": "2026-05-06T00:00:00Z",
        "url": f"https://github.com/acme/widgets/pull/42#issuecomment-{comment_id}",
    }


def _review(
    review_id: str,
    author: str,
    association: str,
    actor_type: str,
    body: str,
) -> dict[str, object]:
    return {
        "id": review_id,
        "author": author,
        "author_association": association,
        "author_type": actor_type,
        "state": "COMMENTED",
        "body": body,
        "created_at": "2026-05-06T00:00:00Z",
        "url": f"https://github.com/acme/widgets/pull/42#pullrequestreview-{review_id}",
    }


def _review_comment(
    comment_id: str,
    thread_id: str,
    author: str,
    association: str,
    actor_type: str,
    body: str,
) -> dict[str, object]:
    return {
        **_issue_comment(comment_id, author, association, actor_type, body),
        "thread_id": thread_id,
        "path": "src/cache.py",
        "line": 10,
        "side": "RIGHT",
    }


def _thread(thread_id: str, resolved_status: str) -> dict[str, object]:
    return {
        "id": thread_id,
        "path": "src/cache.py",
        "resolved_status": resolved_status,
    }


def _package(result: GitHubReadResult, memory):
    budgeted = apply_input_context_budget(
        pr=result.pr,
        memory=memory,
        limits=ContextBudget(
            max_changed_files=10,
            max_patch_bytes=100_000,
            max_memory_bytes=100_000,
            max_reviewers=10,
            max_live_calls=0,
        ),
    )
    return build_reviewer_context_package(
        active_stage="initial_triage",
        reviewer=SelectedReviewer("correctness", "initial_triage", ("always",)),
        budgeted_context=budgeted,
    )


def _run_key() -> ReviewerRunKey:
    return ReviewerRunKey(
        target_hash="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        config_hash="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        stage=ReviewStage.INITIAL_TRIAGE,
        reviewer="correctness",
    )


def _classified_finding(body: str) -> ClassifiedFinding:
    return ClassifiedFinding(
        id="finding-1",
        source_reviewer="correctness",
        source_stage="initial_triage",
        title="Cache miss returns stale data",
        body=body,
        evidence="Changed line 10 returns stale data.",
        path="src/cache.py",
        line=10,
        priority=1,
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        fingerprint="sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    )
