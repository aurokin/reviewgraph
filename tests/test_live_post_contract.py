import ast
import json
from pathlib import Path

import pytest

from reviewgraph.github_live import GhCommandResult
from reviewgraph.github_live_post import (
    DISPOSABLE_MARKER,
    LIVE_POST_ALLOWED_TARGET_ENV,
    LIVE_POST_CREDENTIAL_SOURCE_ENV,
    LIVE_POST_DISPOSABLE_MARKER_ENV,
    LIVE_POST_OPT_IN_ENV,
    LIVE_POST_PR_ENV,
    _assert_live_post_read_args,
    _assert_live_post_write_args,
    blocked_live_post_artifact,
    build_approved_post_artifact,
    load_approved_post_artifact,
    run_live_post_contract,
    run_live_post_smoke,
    SubprocessGhJsonPostRunner,
)
from reviewgraph.final_payload import build_approved_final_issue_comment
from reviewgraph.hashing import canonical_json_hash
from reviewgraph.models import ClassifiedFinding, Confidence, ReviewTarget, Severity
from reviewgraph.posting import build_candidate_issue_comment_payload, build_posting_plan


class FakeGhRunner:
    def __init__(
        self,
        responses: dict[tuple[str, ...], GhCommandResult | list[GhCommandResult]] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[tuple[str, ...], int, dict[str, str]]] = []

    def run(self, args: tuple[str, ...], *, timeout_seconds: int, env: dict[str, str]) -> GhCommandResult:
        self.calls.append((args, timeout_seconds, dict(env)))
        response = self.responses.get(args, GhCommandResult(returncode=0, stdout="{}"))
        if isinstance(response, list):
            if not response:
                return GhCommandResult(returncode=0, stdout="{}")
            return response.pop(0)
        return response


class FakeJsonPostRunner:
    def __init__(self, responses: dict[tuple[str, ...], GhCommandResult] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[tuple[str, ...], dict[str, object], int, dict[str, str]]] = []

    def run_json(
        self,
        args: tuple[str, ...],
        *,
        payload: dict[str, object],
        timeout_seconds: int,
        env: dict[str, str],
    ) -> GhCommandResult:
        self.calls.append((args, dict(payload), timeout_seconds, dict(env)))
        return self.responses.get(args, GhCommandResult(returncode=0, stdout="{}"))


class FakeApprovalPrompter:
    def __init__(self, typed_hash: str, runner: FakeGhRunner | None = None) -> None:
        self.typed_hash = typed_hash
        self.runner = runner
        self.prompts: list[str] = []
        self.expected_hashes: list[str] = []
        self.read_call_count_at_prompt: int | None = None

    def confirm_hash(self, *, prompt: str, expected_hash: str) -> str:
        self.prompts.append(prompt)
        self.expected_hashes.append(expected_hash)
        if self.runner is not None:
            self.read_call_count_at_prompt = len(self.runner.calls)
        return self.typed_hash


def test_live_post_blocked_without_explicit_opt_in() -> None:
    artifact = blocked_live_post_artifact(env={}, gh_path="/usr/bin/gh", runner=FakeGhRunner(), input_is_tty=True)

    assert artifact is not None
    data = artifact.to_dict()
    assert data["status"] == "blocked"
    assert data["reason"] == "missing_opt_in"


@pytest.mark.parametrize(
    ("env_update", "input_is_tty", "expected_reason"),
    [
        ({}, True, "missing_pr_ref"),
        ({LIVE_POST_PR_ENV: "acme/widgets#42"}, True, "target_not_allowlisted"),
        ({LIVE_POST_PR_ENV: "acme/widgets#42", LIVE_POST_ALLOWED_TARGET_ENV: "acme/widgets#42"}, True, "missing_disposable_marker"),
        (
            {
                LIVE_POST_PR_ENV: "acme/widgets#42",
                LIVE_POST_ALLOWED_TARGET_ENV: "acme/widgets#42",
                LIVE_POST_DISPOSABLE_MARKER_ENV: DISPOSABLE_MARKER,
            },
            True,
            "unsupported_credential_source",
        ),
        (
            {
                LIVE_POST_PR_ENV: "acme/widgets#42",
                LIVE_POST_ALLOWED_TARGET_ENV: "acme/widgets#42",
                LIVE_POST_DISPOSABLE_MARKER_ENV: DISPOSABLE_MARKER,
                LIVE_POST_CREDENTIAL_SOURCE_ENV: "pat",
            },
            True,
            "missing_approved_post_artifact",
        ),
        (
            {
                LIVE_POST_PR_ENV: "acme/widgets#42",
                LIVE_POST_ALLOWED_TARGET_ENV: "acme/widgets#42",
                LIVE_POST_DISPOSABLE_MARKER_ENV: DISPOSABLE_MARKER,
                LIVE_POST_CREDENTIAL_SOURCE_ENV: "pat",
            },
            False,
            "missing_tty",
        ),
    ],
)
def test_live_post_prerequisite_blocks_before_gh_or_writer(
    env_update: dict[str, str],
    input_is_tty: bool,
    expected_reason: str,
) -> None:
    runner = FakeGhRunner()
    env = {LIVE_POST_OPT_IN_ENV: "1", **env_update}
    approved_artifact = _artifact().data if expected_reason == "missing_tty" else None
    source_artifact = _source_artifact(_artifact()) if expected_reason == "missing_tty" else None

    artifact = blocked_live_post_artifact(
        env=env,
        gh_path="/usr/bin/gh",
        runner=runner,
        input_is_tty=input_is_tty,
        approved_artifact=approved_artifact,
        source_dry_run_artifact=source_artifact,
    )

    assert artifact is not None
    assert artifact.reason == expected_reason
    assert runner.calls == []


def test_approved_post_artifact_preserves_full_candidate_findings_for_subset_approval() -> None:
    artifact = _artifact()

    assert artifact.approved_item_ids == ("finding-1",)
    assert [finding.id for finding in artifact.findings] == ["finding-1", "finding-2"]
    assert artifact.candidate_payload.item_fingerprints == ("fp-1", "fp-2")
    assert artifact.source_dry_run_artifact_hash.startswith("sha256:")
    assert artifact.artifact_hash.startswith("sha256:")

    tampered = dict(artifact.data)
    tampered["candidate_findings"] = tampered["candidate_findings"][:1]
    tampered["artifact_hash"] = _rehash(tampered)
    with pytest.raises(ValueError, match="approval proof failed|matching finding"):
        load_approved_post_artifact(tampered)


def test_approved_post_artifact_rejects_missing_source_dry_run_hash() -> None:
    artifact = dict(_artifact().data)
    artifact.pop("source_dry_run_artifact_hash")
    artifact["artifact_hash"] = _rehash(artifact)

    with pytest.raises(ValueError, match="source_dry_run_artifact_hash"):
        load_approved_post_artifact(artifact)


def test_missing_source_dry_run_artifact_blocks_before_gh() -> None:
    approved = _artifact()
    runner = FakeGhRunner()

    artifact = blocked_live_post_artifact(
        env=_env(),
        gh_path="/usr/bin/gh",
        runner=runner,
        input_is_tty=True,
        approved_artifact=approved.data,
    )

    assert artifact is not None
    assert artifact.reason == "missing_source_dry_run_artifact"
    assert runner.calls == []


@pytest.mark.parametrize(
    "field",
    ["target_hash", "candidate_visible_body_hash", "candidate_findings_hash", "final_payload_hash"],
)
def test_source_dry_run_artifact_mismatch_blocks_before_post(field: str) -> None:
    approved = _artifact()
    source = _source_artifact(approved)
    source[field] = "sha256:" + "2" * 64
    source["artifact_hash"] = _rehash(source)
    runner = FakeGhRunner(_responses())
    post_runner = FakeJsonPostRunner()

    artifact = run_live_post_contract(
        env=_env(),
        gh_path="gh",
        runner=runner,
        post_runner=post_runner,
        approved_artifact=approved.data,
        source_dry_run_artifact=source,
        input_is_tty=True,
        approval_prompter=FakeApprovalPrompter(approved.final_payload_hash),
    )

    assert artifact.status == "blocked"
    assert artifact.reason == "invalid_source_dry_run_artifact"
    assert runner.calls == []
    assert post_runner.calls == []


def test_live_post_read_and_write_command_allowlists() -> None:
    allowed_reads = (
        ("gh", "api", "user"),
        ("gh", "api", "repos/acme/widgets"),
        ("gh", "api", "repos/acme/widgets/pulls/42"),
        ("gh", "api", "repos/acme/widgets/compare/base123...head456"),
        ("gh", "api", "repos/acme/widgets/issues/42/comments?per_page=100&page=1"),
    )
    for args in allowed_reads:
        _assert_live_post_read_args(args, gh_executable="gh")
    for args in (
        ("gh", "api", "graphql"),
        ("gh", "api", "--method", "POST", "repos/acme/widgets/issues/42/comments"),
        ("gh", "pr", "comment", "42"),
        ("gh", "api", "repos/acme/widgets/issues/42/comments"),
    ):
        with pytest.raises(ValueError):
            _assert_live_post_read_args(args, gh_executable="gh")

    _assert_live_post_write_args(
        ("gh", "api", "--method", "POST", "repos/acme/widgets/issues/42/comments", "--input", "-"),
        gh_executable="gh",
        owner_repo="acme/widgets",
        pr_number=42,
    )
    for args in (
        ("gh", "api", "--method", "PATCH", "repos/acme/widgets/issues/comments/1"),
        ("gh", "api", "repos/acme/widgets/issues/42/comments", "--method", "POST"),
        ("gh", "api", "--method", "POST", "repos/acme/widgets/pulls/42/reviews"),
    ):
        with pytest.raises(ValueError):
            _assert_live_post_write_args(args, gh_executable="gh", owner_repo="acme/widgets", pr_number=42)


def test_subprocess_json_post_runner_sends_exact_body_on_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    class Completed:
        returncode = 0
        stdout = '{"id":1001}'
        stderr = ""

    def fake_run(args: list[str], **kwargs: object) -> Completed:
        calls.append((args, kwargs))
        return Completed()

    monkeypatch.setattr("reviewgraph.github_live_post.subprocess.run", fake_run)

    result = SubprocessGhJsonPostRunner().run_json(
        ("gh", "api", "--method", "POST", "repos/acme/widgets/issues/42/comments", "--input", "-"),
        payload={"body": "approved body"},
        timeout_seconds=20,
        env={"PATH": "/usr/bin"},
    )

    assert result.returncode == 0
    assert calls == [
        (
            ["gh", "api", "--method", "POST", "repos/acme/widgets/issues/42/comments", "--input", "-"],
            {
                "check": False,
                "capture_output": True,
                "text": True,
                "input": '{"body":"approved body"}',
                "timeout": 20,
                "env": {"PATH": "/usr/bin", "GH_PROMPT_DISABLED": "1"},
            },
        )
    ]
    assert "shell" not in calls[0][1]


def test_typed_hash_mismatch_blocks_before_post() -> None:
    approved = _artifact()
    runner = FakeGhRunner(_responses())
    post_runner = FakeJsonPostRunner()
    prompter = FakeApprovalPrompter("sha256:" + "0" * 64, runner)
    artifact = run_live_post_contract(
        env=_env(),
        gh_path="gh",
        runner=runner,
        post_runner=post_runner,
        approved_artifact=approved.data,
        source_dry_run_artifact=_source_artifact(approved),
        input_is_tty=True,
        approval_prompter=prompter,
    )

    assert artifact.status == "blocked"
    assert artifact.reason == "typed_hash_mismatch"
    assert artifact.approval_evidence["typed_hash_matched"] is False
    assert "Final payload hash:" in prompter.prompts[0]
    assert approved.final_payload_hash in prompter.prompts[0]
    assert prompter.read_call_count_at_prompt == 6
    assert not any("--method" in call[0] for call in runner.calls)
    assert post_runner.calls == []


def test_successful_live_post_uses_real_writer_after_finalization_and_records_evidence() -> None:
    approved = _artifact()
    runner = FakeGhRunner(_responses())
    post_runner = FakeJsonPostRunner(_post_responses(post_body=approved.final_payload_body))
    prompter = FakeApprovalPrompter(approved.final_payload_hash, runner)

    artifact = run_live_post_contract(
        env=_env(),
        gh_path="gh",
        runner=runner,
        post_runner=post_runner,
        approved_artifact=approved.data,
        source_dry_run_artifact=_source_artifact(approved),
        input_is_tty=True,
        approval_prompter=prompter,
    )

    data = artifact.to_dict()
    assert data["status"] == "succeeded"
    assert data["reason"] == "posted"
    assert data["source_dry_run_artifact_hash"] == approved.source_dry_run_artifact_hash
    assert data["approved_post_artifact_hash"] == approved.artifact_hash
    assert data["approval_evidence"]["shown_actor"] is True
    assert data["approval_evidence"]["shown_permission"] is True
    assert data["approval_evidence"]["shown_dry_run_artifact_hash"] is True
    assert data["approval_evidence"]["shown_final_payload_hash"] is True
    assert data["approval_evidence"]["typed_hash_matched"] is True
    prompt = prompter.prompts[0]
    assert "Actor: reviewgraph-bot" in prompt
    assert "Endpoint permission: write" in prompt
    assert "Marker scan: status=safe_to_post" in prompt
    assert approved.source_dry_run_artifact_hash in prompt
    assert approved.final_payload_hash in prompt
    assert approved.final_payload_body in prompt
    assert prompter.expected_hashes == [approved.final_payload_hash]
    assert prompter.read_call_count_at_prompt == 6
    assert data["writer_summary"]["post_attempt_count"] == 1
    assert data["writer_summary"]["endpoint_kind"] == "issue_comment"
    assert data["comment_id"] == "1001"
    assert data["cleanup"]["manual_cleanup_required"] is True
    assert "ReviewGraph approved findings" not in json.dumps(data)
    assert [call[0] for call in post_runner.calls] == [
        ("gh", "api", "--method", "POST", "repos/acme/widgets/issues/42/comments", "--input", "-")
    ]
    assert post_runner.calls[0][1] == {"body": approved.final_payload_body}
    read_args = [call[0] for call in runner.calls]
    assert read_args.count(("gh", "api", "user")) == 2
    assert read_args.count(("gh", "api", "repos/acme/widgets")) == 2
    assert read_args.count(("gh", "api", "repos/acme/widgets/pulls/42")) == 3
    assert read_args.count(("gh", "api", "repos/acme/widgets/compare/base123...head456")) == 2
    assert read_args.count(("gh", "api", "repos/acme/widgets/issues/42/comments?per_page=100&page=1")) == 2


def test_actor_change_after_prompt_fails_closed_before_post() -> None:
    approved = _artifact()
    responses = _responses()
    responses[("gh", "api", "user")] = [
        GhCommandResult(returncode=0, stdout=json.dumps({"login": "reviewgraph-bot"})),
        GhCommandResult(returncode=0, stdout=json.dumps({"login": "different-bot"})),
    ]
    runner = FakeGhRunner(responses)
    post_runner = FakeJsonPostRunner()
    prompter = FakeApprovalPrompter(approved.final_payload_hash)

    artifact = run_live_post_contract(
        env=_env(),
        gh_path="gh",
        runner=runner,
        post_runner=post_runner,
        approved_artifact=approved.data,
        source_dry_run_artifact=_source_artifact(approved),
        input_is_tty=True,
        approval_prompter=prompter,
    )

    assert artifact.status == "fail_closed"
    assert artifact.reason == "finalization_failed"
    assert "Actor: reviewgraph-bot" in prompter.prompts[0]
    assert post_runner.calls == []


def test_disposable_marker_removed_after_prompt_blocks_before_post() -> None:
    approved = _artifact()
    pull_key = ("gh", "api", "repos/acme/widgets/pulls/42")
    responses = _responses()
    responses[pull_key] = [
        _responses(disposable=True)[pull_key],
        _responses(disposable=True)[pull_key],
        _responses(disposable=False)[pull_key],
    ]
    runner = FakeGhRunner(responses)
    post_runner = FakeJsonPostRunner()

    artifact = run_live_post_contract(
        env=_env(),
        gh_path="gh",
        runner=runner,
        post_runner=post_runner,
        approved_artifact=approved.data,
        source_dry_run_artifact=_source_artifact(approved),
        input_is_tty=True,
        approval_prompter=FakeApprovalPrompter(approved.final_payload_hash),
    )

    assert artifact.status == "blocked"
    assert artifact.reason == "post_approval_not_disposable_pr"
    assert post_runner.calls == []


def test_fork_state_after_prompt_blocks_before_post() -> None:
    approved = _artifact()
    pull_key = ("gh", "api", "repos/acme/widgets/pulls/42")
    responses = _responses()
    responses[pull_key] = [
        _responses(disposable=True)[pull_key],
        _responses(disposable=True)[pull_key],
        _responses(disposable=True, fork=True)[pull_key],
    ]
    runner = FakeGhRunner(responses)
    post_runner = FakeJsonPostRunner()

    artifact = run_live_post_contract(
        env=_env(),
        gh_path="gh",
        runner=runner,
        post_runner=post_runner,
        approved_artifact=approved.data,
        source_dry_run_artifact=_source_artifact(approved),
        input_is_tty=True,
        approval_prompter=FakeApprovalPrompter(approved.final_payload_hash),
    )

    assert artifact.status == "blocked"
    assert artifact.reason == "post_approval_fork_pr_not_supported"
    assert post_runner.calls == []


def test_reconciled_existing_reports_no_post_command() -> None:
    approved = _artifact()
    responses = _responses(existing_body=approved.final_payload_body)
    runner = FakeGhRunner(responses)
    post_runner = FakeJsonPostRunner()
    prompter = FakeApprovalPrompter(approved.final_payload_hash)

    artifact = run_live_post_contract(
        env=_env(),
        gh_path="gh",
        runner=runner,
        post_runner=post_runner,
        approved_artifact=approved.data,
        source_dry_run_artifact=_source_artifact(approved),
        input_is_tty=True,
        approval_prompter=prompter,
    )

    assert artifact.status == "succeeded"
    assert artifact.reason == "reconciled_existing"
    assert artifact.writer_summary == {"post_attempt_count": 0, "writer_invoked": False}
    assert not any("--method" in call[0] for call in runner.calls)
    assert post_runner.calls == []


@pytest.mark.parametrize(
    ("response_kwargs", "expected_reason"),
    [
        ({"disposable": False}, "not_disposable_pr"),
        ({"fork": True}, "fork_pr_not_supported"),
        ({"missing_repo_identity": True}, "fork_pr_not_supported"),
        ({"repo_permission": "read"}, "approval_build_failed"),
        ({"missing_merge_base": True}, "live_post_failed"),
    ],
)
def test_live_preflight_failures_block_before_post(
    response_kwargs: dict[str, object],
    expected_reason: str,
) -> None:
    approved = _artifact()
    runner = FakeGhRunner(_responses(**response_kwargs))
    post_runner = FakeJsonPostRunner()

    artifact = run_live_post_contract(
        env=_env(),
        gh_path="gh",
        runner=runner,
        post_runner=post_runner,
        approved_artifact=approved.data,
        source_dry_run_artifact=_source_artifact(approved),
        input_is_tty=True,
        approval_prompter=FakeApprovalPrompter(approved.final_payload_hash),
    )

    assert artifact.status in {"blocked", "fail_closed"}
    assert artifact.reason == expected_reason
    assert post_runner.calls == []


def test_contract_rejects_subprocess_runners() -> None:
    from reviewgraph.github_live import SubprocessGhCommandRunner
    from reviewgraph.github_live_post import SubprocessGhJsonPostRunner

    approved = _artifact()
    artifact = run_live_post_contract(
        env=_env(),
        gh_path="gh",
        runner=SubprocessGhCommandRunner(),
        post_runner=SubprocessGhJsonPostRunner(),
        approved_artifact=approved.data,
        source_dry_run_artifact=_source_artifact(approved),
        input_is_tty=True,
        approval_prompter=FakeApprovalPrompter(approved.final_payload_hash),
    )

    assert artifact.status == "blocked"
    assert artifact.reason == "contract_rejects_subprocess_runners"


def test_public_cli_still_does_not_expose_post_flag() -> None:
    from reviewgraph.cli import _parser

    assert "--post" not in _parser().format_help()


def test_live_modules_keep_expected_import_boundaries() -> None:
    assert "reviewgraph.writer_github" not in _imports(Path("src/reviewgraph/github.py"))
    assert "reviewgraph.writer_github" not in _imports(Path("src/reviewgraph/github_live.py"))
    assert "reviewgraph.writer_github" in _imports(Path("src/reviewgraph/github_live_post.py"))


@pytest.mark.live_post
def test_opt_in_live_post_smoke_skips_when_blocked() -> None:
    artifact = run_live_post_smoke()
    data = artifact.to_dict()
    if data["status"] == "blocked":
        pytest.skip(f"live post smoke blocked: {data['reason']}")
    assert data["status"] in {"succeeded", "fail_closed"}


def _env() -> dict[str, str]:
    return {
        LIVE_POST_OPT_IN_ENV: "1",
        LIVE_POST_PR_ENV: "acme/widgets#42",
        LIVE_POST_ALLOWED_TARGET_ENV: "acme/widgets#42",
        LIVE_POST_DISPOSABLE_MARKER_ENV: DISPOSABLE_MARKER,
        LIVE_POST_CREDENTIAL_SOURCE_ENV: "pat",
        "GITHUB_TOKEN": "ghs_abcdefghijklmnopqrstuvwxyz123456",
    }


def _artifact():
    target = _target()
    findings = (_finding("finding-1", "fp-1", line=10), _finding("finding-2", "fp-2", line=12))
    plan = build_posting_plan(findings=findings)
    candidate = build_candidate_issue_comment_payload(review_target=target, posting_plan=plan, findings=findings)
    final_payload = build_approved_final_issue_comment(
        run_id="run-123",
        review_target=target,
        findings_by_id={finding.id: finding for finding in findings},
        selected_items=tuple(item for item in plan.items if item.id == "finding-1"),
        local_verdict=None,
        include_public_verdict=False,
    ).payload
    source_artifact = _source_artifact_data(
        target=target,
        run_id="run-123",
        candidate_visible_body_hash=candidate.visible_body_hash,
        candidate_findings_hash=candidate.findings_hash,
        candidate_item_fingerprints=candidate.item_fingerprints,
        final_payload_hash=final_payload.final_payload_hash,
    )
    return build_approved_post_artifact(
        source_dry_run_artifact_hash=source_artifact["artifact_hash"],
        run_id="run-123",
        review_target=target,
        posting_plan=plan,
        findings=findings,
        candidate_payload=candidate,
        approved_item_ids=("finding-1",),
    )


def _source_artifact(approved) -> dict[str, object]:
    return _source_artifact_data(
        target=approved.review_target,
        run_id=approved.run_id,
        candidate_visible_body_hash=approved.candidate_payload.visible_body_hash,
        candidate_findings_hash=approved.candidate_payload.findings_hash,
        candidate_item_fingerprints=approved.candidate_payload.item_fingerprints,
        final_payload_hash=approved.final_payload_hash,
    )


def _source_artifact_data(
    *,
    target: ReviewTarget,
    run_id: str,
    candidate_visible_body_hash: str,
    candidate_findings_hash: str,
    candidate_item_fingerprints: tuple[str, ...],
    final_payload_hash: str,
) -> dict[str, object]:
    data: dict[str, object] = {
        "source": "reviewgraph-dry-run-artifact",
        "run_id": run_id,
        "target": target.to_ordered_dict(),
        "target_hash": target.target_hash(),
        "candidate_visible_body_hash": candidate_visible_body_hash,
        "candidate_findings_hash": candidate_findings_hash,
        "candidate_item_fingerprints": list(candidate_item_fingerprints),
        "final_payload_hash": final_payload_hash,
    }
    data["artifact_hash"] = canonical_json_hash(data)
    return data


def _finding(finding_id: str, fingerprint: str, *, line: int) -> ClassifiedFinding:
    return ClassifiedFinding(
        id=finding_id,
        source_reviewer="correctness",
        source_stage="initial_triage",
        title=f"Finding {finding_id}",
        body=f"Body for {finding_id}.",
        evidence="Changed code evidence.",
        path="src/app.py",
        line=line,
        priority=1,
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        fingerprint=fingerprint,
    )


def _target() -> ReviewTarget:
    return ReviewTarget("acme/widgets", 42, "base123", "head456", "merge789", "merge_base")


def _responses(
    *,
    existing_body: str | None = None,
    disposable: bool = True,
    fork: bool = False,
    missing_repo_identity: bool = False,
    repo_permission: str = "write",
    missing_merge_base: bool = False,
) -> dict[tuple[str, ...], GhCommandResult]:
    issue_comments = []
    if existing_body is not None:
        issue_comments.append({"id": "existing-1", "body": existing_body, "user": {"login": "reviewgraph-bot", "type": "User"}})
    title = f"{DISPOSABLE_MARKER} test PR" if disposable else "ordinary test PR"
    head_ref = f"{DISPOSABLE_MARKER}-branch" if disposable else "ordinary-branch"
    head_repo = "acme/forked-widgets" if fork else "acme/widgets"
    head_repo_payload: dict[str, object] = {} if missing_repo_identity else {"full_name": head_repo}
    permissions = {
        "admin": repo_permission == "admin",
        "maintain": repo_permission == "maintain",
        "push": repo_permission == "write",
        "triage": repo_permission in {"triage", "write", "maintain", "admin"},
        "pull": True,
    }
    compare_payload = {} if missing_merge_base else {"merge_base_commit": {"sha": "merge789"}}
    responses = {
        ("gh", "api", "repos/acme/widgets/pulls/42"): GhCommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "title": title,
                    "body": "Disposable live post smoke.",
                    "base": {"sha": "base123", "repo": {"full_name": "acme/widgets"}},
                    "head": {
                        "sha": "head456",
                        "ref": head_ref,
                        "repo": head_repo_payload,
                    },
                }
            ),
        ),
        ("gh", "api", "user"): GhCommandResult(
            returncode=0,
            stdout=json.dumps({"login": "reviewgraph-bot"}),
        ),
        ("gh", "api", "repos/acme/widgets"): GhCommandResult(
            returncode=0,
            stdout=json.dumps({"permissions": permissions}),
        ),
        ("gh", "api", "repos/acme/widgets/compare/base123...head456"): GhCommandResult(
            returncode=0,
            stdout=json.dumps(compare_payload),
        ),
        ("gh", "api", "repos/acme/widgets/issues/42/comments?per_page=100&page=1"): GhCommandResult(
            returncode=0,
            stdout=json.dumps(issue_comments),
        ),
    }
    return responses


def _post_responses(*, post_body: str) -> dict[tuple[str, ...], GhCommandResult]:
    return {
        ("gh", "api", "--method", "POST", "repos/acme/widgets/issues/42/comments", "--input", "-"): GhCommandResult(
            returncode=0,
            stdout=json.dumps({"id": "1001", "body": post_body, "user": {"login": "reviewgraph-bot"}}),
        )
    }


def _rehash(data: dict[str, object]) -> str:
    return canonical_json_hash({key: value for key, value in data.items() if key != "artifact_hash"})


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports
