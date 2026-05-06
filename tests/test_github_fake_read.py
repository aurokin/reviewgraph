import json
import re

import pytest

from reviewgraph.diff_anchor import derive_diff_anchor
from reviewgraph.github import (
    GitHubReadError,
    GitHubReadScope,
    ResourceReadStatus,
    parse_github_pr_ref,
    read_github_pr_with_fake_transport,
)
from reviewgraph.models import (
    ActorPermissionGateResult,
    ClassifiedFinding,
    Confidence,
    GateStatus,
    PullRequestContext,
    ReadGap,
    ReviewTarget,
    Severity,
)


class FakeGitHubTransport:
    def __init__(self, *, pr: dict[str, object], files: list[dict[str, object]]) -> None:
        self.pr = pr
        self.files = files
        self.calls: list[tuple[str, str, int]] = []

    def get_pull_request(self, owner_repo: str, pr_number: int) -> dict[str, object]:
        self.calls.append(("get_pull_request", owner_repo, pr_number))
        return self.pr

    def get_changed_files(self, owner_repo: str, pr_number: int) -> list[dict[str, object]]:
        self.calls.append(("get_changed_files", owner_repo, pr_number))
        return self.files


def test_parses_owner_repo_number_refs_and_github_urls() -> None:
    short = parse_github_pr_ref("acme/widgets#42")
    url = parse_github_pr_ref("https://github.com/acme/widgets/pull/42")

    assert short == url
    assert short.owner == "acme"
    assert short.repo == "widgets"
    assert short.owner_repo == "acme/widgets"
    assert short.pr_number == 42


@pytest.mark.parametrize(
    "ref",
    [
        "acme/widgets#0",
        "acme/widgets#-1",
        "acme/widgets#abc",
        "acme#42",
        "https://gitlab.com/acme/widgets/pull/42",
        "http://github.com/acme/widgets/pull/42",
        "https://github.com/acme/widgets/pull/42?token=ghp_abcdefghijklmnopqrstuvwxyz123456",
        "https://github.com/acme/widgets/pull/42?access_token=abc123",
        "https://github.com/acme/widgets/pull/42#discussion",
        "https://github.com/acme/widgets/pull/42#access_token=abc123",
        "https://github.com/acme/widgets/pull/42/",
        "https://github.com/acme/widgets%2Fother/pull/42",
        "https://github.com/acme/%20widgets/pull/42",
    ],
)
def test_invalid_pr_refs_fail_with_redacted_errors(ref: str) -> None:
    with pytest.raises(GitHubReadError) as exc_info:
        parse_github_pr_ref(ref)

    message = str(exc_info.value)
    assert "invalid GitHub PR reference" in message
    assert "ghp_" not in message
    assert "abcdefghijklmnopqrstuvwxyz" not in message
    assert "abc123" not in message


def test_actor_permission_snapshot_serializes_when_present() -> None:
    result = read_github_pr_with_fake_transport(
        FakeGitHubTransport(
            pr=_pr_payload(),
            files=[
                {
                    "path": "src/cache.py",
                    "status": "modified",
                    "patch": "@@ -1 +1 @@\n+new\n",
                }
            ],
        ),
        "acme/widgets#42",
    )
    result = result.with_actor_permission(
        ActorPermissionGateResult(
            status=GateStatus.PASS,
            actor="octocat",
            permission="write",
            checked_at="2026-05-06T00:00:00Z",
        )
    )

    data = result.to_dict()

    assert data["actor_permission"] == {
        "status": "pass",
        "actor": "octocat",
        "permission": "write",
        "checked_at": "2026-05-06T00:00:00Z",
        "reason": None,
    }


def test_redaction_status_matches_serialized_result_surface() -> None:
    result = read_github_pr_with_fake_transport(
        FakeGitHubTransport(
            pr={
                **_pr_payload(),
                "base": {"ref": "main", "sha": "base123"},
                "head": {"ref": "feature/ghp_abcdefghijklmnopqrstuvwxyz123456", "sha": "head456"},
            },
            files=[
                {
                    "path": "src/cache.py",
                    "status": "modified",
                    "patch": "@@ -1 +1 @@\n+new\n",
                }
            ],
        ),
        "acme/widgets#42",
    )
    serialized = json.dumps(result.to_redacted_dict(), sort_keys=True)

    assert result.redaction_status.redacted is True
    assert result.redaction_status.replacement_count > 0
    assert "ghp_" not in serialized
    assert "[REDACTED]" in serialized


def test_fake_read_returns_pr_context_target_metadata_and_files() -> None:
    transport = FakeGitHubTransport(
        pr=_pr_payload(),
        files=[
            {
                "path": "src/cache.py",
                "status": "modified",
                "additions": 2,
                "deletions": 1,
                "patch": "@@ -10,2 +10,3 @@\n old\n+new\n context\n@@ -30 +31,2 @@\n+more\n done\n",
            }
        ],
    )

    result = read_github_pr_with_fake_transport(transport, "https://github.com/acme/widgets/pull/42")

    assert transport.calls == [
        ("get_pull_request", "acme/widgets", 42),
        ("get_changed_files", "acme/widgets", 42),
    ]
    assert result.scope == GitHubReadScope.METADATA_FILES_ONLY
    assert result.resource_coverage.metadata == ResourceReadStatus.COMPLETE
    assert result.resource_coverage.files == ResourceReadStatus.COMPLETE
    assert result.resource_coverage.comments == ResourceReadStatus.NOT_FETCHED_IN_SCOPE
    assert result.thread_state.reason == "not_fetched_in_scope"
    assert result.read_gaps == (
        ReadGap(resource="comments", required=True, reason="not_fetched_in_scope", retryable=True),
        ReadGap(resource="reviews", required=True, reason="not_fetched_in_scope", retryable=True),
        ReadGap(resource="review_comments", required=True, reason="not_fetched_in_scope", retryable=True),
        ReadGap(resource="thread_state", required=True, reason="not_fetched_in_scope", retryable=True),
    )
    assert result.actor_permission is None
    assert result.metadata.author == "octocat"
    assert result.metadata.base_ref == "main"
    assert result.metadata.head_ref == "feature/cache"
    assert isinstance(result.review_target, ReviewTarget)
    assert isinstance(result.pr, PullRequestContext)
    assert result.review_target.owner_repo == "acme/widgets"
    assert result.review_target.pr_number == 42
    assert result.review_target.base_sha == "base123"
    assert result.review_target.head_sha == "head456"
    assert result.review_target.merge_base_sha == "merge789"
    assert result.pr.title == "Fix cache fallback"
    assert result.pr.labels == ("backend",)
    assert result.pr.changed_files[0].path == "src/cache.py"
    assert result.pr.changed_files[0].patch_status == "available"
    assert result.changed_file_lines[0].path == "src/cache.py"
    assert [(item.start, item.end) for item in result.changed_file_lines[0].changed_ranges] == [(10, 12), (31, 32)]
    assert result.changed_file_lines[0].contains_line(11) is True
    assert result.changed_file_lines[0].contains_line(10) is True
    assert result.changed_file_lines[0].contains_line(20) is False


def test_fake_read_accepts_empty_pr_body() -> None:
    result = read_github_pr_with_fake_transport(
        FakeGitHubTransport(
            pr={**_pr_payload(), "body": ""},
            files=[
                {
                    "path": "src/cache.py",
                    "status": "modified",
                    "patch": "@@ -1 +1 @@\n+new\n",
                }
            ],
        ),
        "acme/widgets#42",
    )

    assert result.pr.body == ""


def test_changed_lines_allow_file_header_prefixes_as_hunk_content() -> None:
    transport = FakeGitHubTransport(
        pr=_pr_payload(),
        files=[
            {
                "path": "src/flags.py",
                "status": "modified",
                "patch": "@@ -1,2 +1,2 @@\n---old\n+++flag\n same\n",
            }
        ],
    )

    result = read_github_pr_with_fake_transport(transport, "acme/widgets#42")

    assert [(item.start, item.end) for item in result.changed_file_lines[0].changed_ranges] == [(1, 2)]
    assert result.anchor_unavailable == ()


def test_changed_lines_accept_new_file_hunks_with_zero_source_count() -> None:
    transport = FakeGitHubTransport(
        pr=_pr_payload(),
        files=[
            {
                "path": "src/new.py",
                "status": "added",
                "patch": "@@ -0,0 +1,2 @@\n+one\n+two\n",
            }
        ],
    )

    result = read_github_pr_with_fake_transport(transport, "acme/widgets#42")

    assert [(item.start, item.end) for item in result.changed_file_lines[0].changed_ranges] == [(1, 2)]
    assert result.anchor_unavailable == ()


def test_fake_read_transport_contract_is_read_only() -> None:
    transport = FakeGitHubTransport(
        pr=_pr_payload(),
        files=[
            {
                "path": "src/cache.py",
                "status": "modified",
                "patch": "@@ -1 +1 @@\n+new\n",
            }
        ],
    )

    read_github_pr_with_fake_transport(transport, "acme/widgets#42")

    assert [name for name, _, _ in transport.calls] == ["get_pull_request", "get_changed_files"]
    assert not hasattr(transport, "post_comment")
    assert not hasattr(transport, "create_review")


def test_empty_changed_files_fail_with_structured_read_error() -> None:
    with pytest.raises(GitHubReadError) as exc_info:
        read_github_pr_with_fake_transport(
            FakeGitHubTransport(pr=_pr_payload(), files=[]),
            "acme/widgets#42",
        )

    assert exc_info.value.code == "invalid_files_payload"
    assert "changed files must not be empty" in str(exc_info.value)


def test_redacted_result_serialization_hides_secret_pr_text_and_errors() -> None:
    transport = FakeGitHubTransport(
        pr={
            **_pr_payload(),
            "title": "Fix token ghp_abcdefghijklmnopqrstuvwxyz123456",
            "body": "api_key = sk_live_1234567890abcdef",
        },
        files=[
            {
                "path": "src/secret.py",
                "status": "modified",
                "patch": "@@ -1 +1 @@\n+Authorization: Bearer abcdefghijklmnopqrstuvwxyz\n",
            }
        ],
    )

    result = read_github_pr_with_fake_transport(transport, "acme/widgets#42")
    serialized = json.dumps(result.to_redacted_dict(), sort_keys=True)
    public_serialized = json.dumps(result.to_dict(), sort_keys=True)

    assert result.redaction_status.redacted is True
    assert "ghp_" not in serialized
    assert "sk_live" not in serialized
    assert "Bearer abcdef" not in serialized
    assert "[REDACTED]" in serialized
    assert "ghp_" not in public_serialized
    assert "sk_live" not in public_serialized
    assert "ghp_" in result.pr.title
    with pytest.raises(GitHubReadError) as exc_info:
        read_github_pr_with_fake_transport(
            BrokenGitHubTransport(error="failed for ghp_abcdefghijklmnopqrstuvwxyz123456"),
            "acme/widgets#42",
        )
    assert "ghp_" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)


def test_changed_line_bridge_supports_diff_anchor_protocol_multiline_and_renames() -> None:
    transport = FakeGitHubTransport(
        pr=_pr_payload(),
        files=[
            {
                "path": "src/new_cache.py",
                "previous_path": "src/cache.py",
                "status": "renamed",
                "patch": "@@ -20,2 +20,4 @@\n context\n+line one\n+line two\n context\n",
            }
        ],
    )
    result = read_github_pr_with_fake_transport(transport, "acme/widgets#42")
    finding = ClassifiedFinding(
        id="finding-cache",
        source_reviewer="correctness",
        source_stage="initial_triage",
        title="Cache behavior changed",
        body="The renamed file changes cache behavior.",
        evidence="Changed lines 21-22.",
        path="src/new_cache.py",
        line=21,
        line_end=22,
        priority=1,
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        fingerprint="fp-cache",
    )

    anchor = derive_diff_anchor(
        changed_files=result.changed_file_lines,
        review_target=result.review_target,
        finding=finding,
    )

    assert anchor is not None
    assert anchor.path == "src/new_cache.py"
    assert anchor.old_path == "src/cache.py"
    assert anchor.hunk_start == 20
    assert anchor.hunk_end == 23


@pytest.mark.parametrize(
    "file_payload",
    [
        {"path": "src/deleted.py", "status": "deleted", "patch": "@@ -1 +0,0 @@\n-old\n"},
        {"path": "src/binary.dat", "status": "modified", "patch": None, "patch_status": "binary"},
        {"path": "src/large.py", "status": "modified", "patch": None, "patch_status": "truncated"},
        {"path": "src/weird.py", "status": "modified", "patch": "diff without a hunk"},
        {"path": "src/empty.py", "status": "modified", "patch": "@@ -1 +0,0 @@\n+malformed\n"},
        {"path": "src/overflow.py", "status": "modified", "patch": "@@ -1 +1 @@\n+one\n+two\n"},
        {"path": "src/underflow.py", "status": "modified", "patch": "@@ -1 +1,2 @@\n+one\n"},
        {"path": "src/malformed.py", "status": "modified", "patch": "@@ -1 +1,2 @@\n+new\njunk\n"},
        {"path": "src/zero.py", "status": "modified", "patch": "@@ -1 +0,2 @@\n+one\n+two\n"},
        {"path": "src/extra.py", "status": "modified", "patch": "@@ -1 +1 @@malformed\n+one\n"},
        {"path": "src/at.py", "status": "modified", "patch": "@@ -1 +1 @@@\n+one\n"},
        {"path": "src/source-overflow.py", "status": "modified", "patch": "@@ -1 +1 @@\n-old\n-old2\n+new\n"},
    ],
)
def test_unanchorable_files_record_metadata_without_false_ranges(file_payload: dict[str, object]) -> None:
    result = read_github_pr_with_fake_transport(
        FakeGitHubTransport(pr=_pr_payload(), files=[file_payload]),
        "acme/widgets#42",
    )

    changed = result.changed_file_lines[0]
    assert changed.changed_ranges == ()
    assert changed.contains_line(1) is False
    assert result.anchor_unavailable[0]["path"] == file_payload["path"]
    assert result.anchor_unavailable[0]["reason"]


class BrokenGitHubTransport:
    def __init__(self, *, error: str) -> None:
        self.error = error

    def get_pull_request(self, owner_repo: str, pr_number: int) -> dict[str, object]:
        raise RuntimeError(self.error)

    def get_changed_files(self, owner_repo: str, pr_number: int) -> list[dict[str, object]]:
        return []


def _pr_payload() -> dict[str, object]:
    return {
        "title": "Fix cache fallback",
        "body": "Fixture PR for deterministic fake GitHub reads.",
        "author": "octocat",
        "labels": ["backend"],
        "base": {"ref": "main", "sha": "base123"},
        "head": {"ref": "feature/cache", "sha": "head456"},
        "merge_base_sha": "merge789",
        "diff_basis": "merge_base",
    }
