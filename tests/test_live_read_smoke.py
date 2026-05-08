import ast
import json
from pathlib import Path

import pytest

from reviewgraph.github import GitHubReadResult
from reviewgraph.github_live import (
    GhCommandResult,
    _assert_read_only_gh_args,
    blocked_live_read_artifact,
    live_read_artifact,
    read_live_github_pr,
    run_live_read_smoke,
)
from reviewgraph.read_gaps import FailClosedReadOutcome


class FakeGhRunner:
    def __init__(self, responses: dict[tuple[str, ...], GhCommandResult] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[tuple[str, ...], int, dict[str, str]]] = []

    def run(self, args: tuple[str, ...], *, timeout_seconds: int, env: dict[str, str]) -> GhCommandResult:
        self.calls.append((args, timeout_seconds, dict(env)))
        return self.responses.get(args, GhCommandResult(returncode=0, stdout="[]"))


def test_live_read_blocked_without_explicit_opt_in() -> None:
    artifact = blocked_live_read_artifact(env={}, gh_path="/usr/bin/gh", runner=FakeGhRunner())

    assert artifact is not None
    data = artifact.to_dict()
    assert data["status"] == "blocked"
    assert data["reason"] == "missing_opt_in"


def test_live_read_blocked_without_pr_ref() -> None:
    artifact = blocked_live_read_artifact(
        env={"REVIEWGRAPH_LIVE_READ": "1"},
        gh_path="/usr/bin/gh",
        runner=FakeGhRunner(),
    )

    assert artifact is not None
    assert artifact.to_dict()["reason"] == "missing_pr_ref"


def test_live_read_blocked_without_gh() -> None:
    artifact = blocked_live_read_artifact(
        env={"REVIEWGRAPH_LIVE_READ": "1", "REVIEWGRAPH_LIVE_READ_PR": "acme/widgets#42"},
        gh_path="",
        runner=FakeGhRunner(),
    )

    assert artifact is not None
    data = artifact.to_dict()
    assert data["reason"] == "missing_gh"
    assert data["pr_ref"] == {"owner_repo": "acme/widgets", "pr_number": 42}


def test_live_read_blocked_without_token_redacts_auth_stderr() -> None:
    runner = FakeGhRunner(
        {
            ("/usr/bin/gh", "auth", "token"): GhCommandResult(
                returncode=1,
                stderr="missing token ghs_abcdefghijklmnopqrstuvwxyz123456",
            )
        }
    )

    artifact = blocked_live_read_artifact(
        env={
            "REVIEWGRAPH_LIVE_READ": "1",
            "REVIEWGRAPH_LIVE_READ_PR": "acme/widgets#42",
        },
        gh_path="/usr/bin/gh",
        runner=runner,
    )

    assert artifact is not None
    assert "ghs_" not in artifact.command_summary["message"]
    data = artifact.to_dict()
    assert data["reason"] == "missing_token"
    serialized = json.dumps(data)
    assert "ghs_" not in serialized
    assert "[REDACTED]" in serialized
    assert data["redaction_status"]["redacted"] is True


def test_live_read_prerequisites_accept_env_token_without_auth_command() -> None:
    runner = FakeGhRunner()

    artifact = blocked_live_read_artifact(
        env={
            "REVIEWGRAPH_LIVE_READ": "1",
            "REVIEWGRAPH_LIVE_READ_PR": "acme/widgets#42",
            "GITHUB_TOKEN": "ghs_abcdefghijklmnopqrstuvwxyz123456",
        },
        gh_path="/usr/bin/gh",
        runner=runner,
    )

    assert artifact is None
    assert runner.calls == []


def test_live_read_auth_check_uses_validated_gh_path_and_whitelisted_env() -> None:
    runner = FakeGhRunner(
        {
            ("/opt/bin/gh", "auth", "token"): GhCommandResult(returncode=0, stdout="gho_redacted\n")
        }
    )

    artifact = blocked_live_read_artifact(
        env={
            "REVIEWGRAPH_LIVE_READ": "1",
            "REVIEWGRAPH_LIVE_READ_PR": "acme/widgets#42",
            "OPENAI_API_KEY": "sk-live-should-not-reach-child",
            "GH_HOST": "enterprise.example.com",
            "GH_ENTERPRISE_TOKEN": "ghs_enterprise_token_should_not_reach_child",
            "PATH": "/opt/bin",
        },
        gh_path="/opt/bin/gh",
        runner=runner,
    )

    assert artifact is None
    assert runner.calls[0][0] == ("/opt/bin/gh", "auth", "token")
    assert "OPENAI_API_KEY" not in runner.calls[0][2]
    assert "GH_HOST" not in runner.calls[0][2]
    assert "GH_ENTERPRISE_TOKEN" not in runner.calls[0][2]
    assert runner.calls[0][2]["GH_PROMPT_DISABLED"] == "1"


def test_gh_transport_builds_read_only_rest_commands_and_maps_success() -> None:
    runner = FakeGhRunner(_success_responses())
    result = read_live_github_pr(
        "acme/widgets#42",
        runner=runner,
        env={"GITHUB_TOKEN": "present"},
        max_pages=2,
    )

    assert isinstance(result, GitHubReadResult)
    assert result.review_target.owner_repo == "acme/widgets"
    assert result.review_target.head_sha == "head456"
    assert result.pr.title == "Fix cache fallback"
    assert result.pr.changed_files[0].path == "src/cache.py"
    assert result.pr.comments[0].source_provider == "github"
    assert result.pr.reviews[0].state == "COMMENTED"
    commands = [call[0] for call in runner.calls]
    assert commands == [
        ("gh", "api", "repos/acme/widgets/pulls/42"),
        ("gh", "api", "repos/acme/widgets/pulls/42/files?per_page=100&page=1"),
        ("gh", "api", "repos/acme/widgets/issues/42/comments?per_page=100&page=1"),
        ("gh", "api", "repos/acme/widgets/pulls/42/comments?per_page=100&page=1"),
        ("gh", "api", "repos/acme/widgets/pulls/42/reviews?per_page=100&page=1"),
    ]
    for command in commands:
        joined = " ".join(command)
        assert command[:2] == ("gh", "api")
        assert "--method" not in command
        assert "graphql" not in command
        assert "mutation" not in joined.casefold()
        assert " pr review" not in joined
        assert " pr comment" not in joined
        assert " issue comment" not in joined
    assert all(call[2]["GH_PROMPT_DISABLED"] == "1" for call in runner.calls)


def test_live_read_rest_guard_rejects_mutating_gh_api_options() -> None:
    blocked_commands = (
        ("gh", "api", "repos/acme/widgets/issues/42/comments", "--method=POST"),
        ("gh", "api", "graphql"),
        ("gh", "api", "repos/acme/widgets/issues/42/comments", "-f", "body=test"),
        ("gh", "api", "--method=POST"),
    )

    for command in blocked_commands:
        with pytest.raises(ValueError):
            _assert_read_only_gh_args(command, gh_executable="gh")


def test_live_page_failures_preserve_non_timeout_read_gap_reason() -> None:
    responses = _success_responses()
    responses[("gh", "api", "repos/acme/widgets/issues/42/comments?per_page=100&page=1")] = GhCommandResult(
        returncode=1,
        stderr="HTTP 403: forbidden",
    )

    result = read_live_github_pr(
        "acme/widgets#42",
        runner=FakeGhRunner(responses),
        env={"GITHUB_TOKEN": "present"},
    )

    assert isinstance(result, FailClosedReadOutcome)
    assert result.read_gaps[0].resource == "comments"
    assert result.read_gaps[0].reason == "forbidden"
    assert result.read_gaps[0].retryable is False


def test_live_metadata_failure_returns_targetless_fail_closed_read_gap() -> None:
    responses = {
        ("gh", "api", "repos/acme/widgets/pulls/42"): GhCommandResult(
            returncode=1,
            stderr="HTTP 404: not found",
        )
    }

    result = read_live_github_pr(
        "acme/widgets#42",
        runner=FakeGhRunner(responses),
        env={"GITHUB_TOKEN": "present"},
    )

    assert isinstance(result, FailClosedReadOutcome)
    assert result.review_target is None
    assert result.read_gaps[0].resource == "metadata"
    assert result.read_gaps[0].reason == "not_found"
    artifact = live_read_artifact(result).to_dict()
    assert artifact["status"] == "fail_closed"
    assert artifact["fail_closed"]["review_target"] is None
    assert artifact["fail_closed"]["read_gaps"][0]["resource"] == "metadata"


def test_empty_live_review_body_remains_optional() -> None:
    responses = _success_responses()
    reviews = json.loads(responses[("gh", "api", "repos/acme/widgets/pulls/42/reviews?per_page=100&page=1")].stdout)
    reviews[0]["body"] = ""
    responses[("gh", "api", "repos/acme/widgets/pulls/42/reviews?per_page=100&page=1")] = GhCommandResult(
        returncode=0,
        stdout=json.dumps(reviews),
    )

    result = read_live_github_pr(
        "acme/widgets#42",
        runner=FakeGhRunner(responses),
        env={"GITHUB_TOKEN": "present"},
    )

    assert isinstance(result, GitHubReadResult)
    assert result.pr.reviews[0].body is None


def test_live_review_comments_without_thread_state_fail_closed() -> None:
    responses = _success_responses()
    responses[("gh", "api", "repos/acme/widgets/pulls/42/comments?per_page=100&page=1")] = GhCommandResult(
        returncode=0,
        stdout=json.dumps(
            [
                {
                    "id": 301,
                    "pull_request_review_id": 201,
                    "user": {"login": "reviewer", "type": "User"},
                    "author_association": "MEMBER",
                    "body": "Thread feedback.",
                    "created_at": "2026-05-06T00:01:00Z",
                    "html_url": "https://github.com/acme/widgets/pull/42#discussion_r301",
                    "path": "src/cache.py",
                    "line": 11,
                    "side": "RIGHT",
                    "commit_id": "head456",
                    "position": 1,
                }
            ]
        ),
    )

    result = read_live_github_pr(
        "acme/widgets#42",
        runner=FakeGhRunner(responses),
        env={"GITHUB_TOKEN": "present"},
    )

    assert isinstance(result, FailClosedReadOutcome)
    assert result.read_gaps[0].resource == "thread_state"
    assert result.read_gaps[0].reason == "thread_state_unknown"
    artifact = live_read_artifact(result).to_dict()
    assert artifact["status"] == "fail_closed"
    assert artifact["reason"] == "read_gap"
    assert artifact["fail_closed"]["selected_reviewers"] == []
    assert artifact["fail_closed"]["candidate_payload_preview"] is None


def test_live_read_smoke_writes_blocked_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / "live-read.json"

    artifact = run_live_read_smoke(env={}, gh_path="/usr/bin/gh", runner=FakeGhRunner(), output_path=output_path)

    assert artifact.status == "blocked"
    data = json.loads(output_path.read_text())
    assert data["status"] == "blocked"
    assert data["reason"] == "missing_opt_in"


def test_live_module_does_not_import_writer_side_modules() -> None:
    imports = _imports(Path("src/reviewgraph/github_live.py"))
    forbidden = {
        "reviewgraph.approval",
        "reviewgraph.finalization",
        "reviewgraph.llm",
        "reviewgraph.posting",
        "reviewgraph.runner",
        "reviewgraph.targets",
        "reviewgraph.writer",
    }

    assert not (imports & forbidden)


@pytest.mark.live_read
def test_opt_in_live_read_smoke() -> None:
    artifact = run_live_read_smoke()
    data = artifact.to_dict()
    if data["status"] == "blocked":
        pytest.skip(f"live read smoke blocked: {data['reason']}")
    assert data["status"] in {"succeeded", "fail_closed"}
    assert data["pr_ref"] is not None
    if data["status"] == "succeeded":
        assert data["github_read"]["review_target"]["owner_repo"]
        assert data["github_read"]["resource_coverage"]
    else:
        assert data["fail_closed"]["read_gaps"]
        if data["fail_closed"]["read_gaps"][0]["resource"] != "metadata":
            assert data["fail_closed"]["review_target"] is not None


def _success_responses() -> dict[tuple[str, ...], GhCommandResult]:
    return {
        ("gh", "api", "repos/acme/widgets/pulls/42"): GhCommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "title": "Fix cache fallback",
                    "body": "PR body",
                    "user": {"login": "contributor", "type": "User"},
                    "labels": [{"name": "backend"}],
                    "base": {"ref": "main", "sha": "base123"},
                    "head": {"ref": "fix-cache", "sha": "head456"},
                }
            ),
        ),
        ("gh", "api", "repos/acme/widgets/pulls/42/files?per_page=100&page=1"): GhCommandResult(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "filename": "src/cache.py",
                        "status": "modified",
                        "additions": 1,
                        "deletions": 1,
                        "patch": "@@ -10,2 +10,2 @@\n def read_cache():\n-    return None\n+    return stale_value",
                    }
                ]
            ),
        ),
        ("gh", "api", "repos/acme/widgets/issues/42/comments?per_page=100&page=1"): GhCommandResult(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "id": 101,
                        "user": {"login": "maintainer", "type": "User"},
                        "author_association": "MEMBER",
                        "body": "Please check the fallback.",
                        "created_at": "2026-05-06T00:00:00Z",
                        "html_url": "https://github.com/acme/widgets/pull/42#issuecomment-101",
                    }
                ]
            ),
        ),
        ("gh", "api", "repos/acme/widgets/pulls/42/comments?per_page=100&page=1"): GhCommandResult(
            returncode=0,
            stdout="[]",
        ),
        ("gh", "api", "repos/acme/widgets/pulls/42/reviews?per_page=100&page=1"): GhCommandResult(
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "id": 201,
                        "user": {"login": "reviewer", "type": "User"},
                        "author_association": "MEMBER",
                        "state": "COMMENTED",
                        "body": "Review summary.",
                        "submitted_at": "2026-05-06T00:02:00Z",
                        "html_url": "https://github.com/acme/widgets/pull/42#pullrequestreview-201",
                    }
                ]
            ),
        ),
    }


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports
