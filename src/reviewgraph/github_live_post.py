from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from reviewgraph.approval import build_approval_decision, build_approval_proof
from reviewgraph.final_payload import build_approved_final_issue_comment
from reviewgraph.finalization import (
    BoundMarkerReconciliationResult,
    FinalizeGithubPayloadResult,
    TargetFreshnessProbeResult,
    finalize_github_payload,
)
from reviewgraph.github import parse_github_pr_ref
from reviewgraph.github_live import GhCommandResult, GhCommandRunner, SubprocessGhCommandRunner
from reviewgraph.hashing import canonical_json_hash
from reviewgraph.markers import (
    MarkerCommentPage,
    MarkerScanLimits,
    MarkerScanTransportFailure,
    PaginatedMarkerComment,
    PaginatedMarkerCommentTransport,
    reconcile_paginated_trusted_markers,
)
from reviewgraph.models import (
    ArtifactKind,
    CandidateIssueCommentPayload,
    ClassifiedFinding,
    Confidence,
    GateStatus,
    MarkerReconciliationReasonCode,
    PostingDestination,
    PostingPlan,
    PostingPlanItem,
    RedactionStatus,
    ReviewTarget,
    ReviewVerdict,
    Severity,
    WriterStatus,
)
from reviewgraph.permissions import ActorPermissionProbeResult, issue_comment_endpoint
from reviewgraph.redaction import redact_data, redact_text
from reviewgraph.writer_github import (
    GitHubIssueCommentPostResponse,
    GitHubIssueCommentPostTransportFailure,
    GitHubIssueCommentWriter,
    GitHubIssueCommentWriterReasonCode,
)
from reviewgraph.writer_input import build_finalized_issue_comment_writer_input


LIVE_POST_OPT_IN_ENV = "REVIEWGRAPH_LIVE_POST"
LIVE_POST_PR_ENV = "REVIEWGRAPH_LIVE_POST_PR"
LIVE_POST_ALLOWED_TARGET_ENV = "REVIEWGRAPH_LIVE_POST_ALLOWED_TARGET"
LIVE_POST_DISPOSABLE_MARKER_ENV = "REVIEWGRAPH_LIVE_POST_DISPOSABLE_MARKER"
LIVE_POST_CREDENTIAL_SOURCE_ENV = "REVIEWGRAPH_LIVE_POST_CREDENTIAL_SOURCE"
LIVE_POST_APPROVED_ARTIFACT_ENV = "REVIEWGRAPH_LIVE_POST_APPROVED_ARTIFACT"
LIVE_POST_SOURCE_DRY_RUN_ARTIFACT_ENV = "REVIEWGRAPH_LIVE_POST_SOURCE_DRY_RUN_ARTIFACT"
LIVE_POST_OUT_ENV = "REVIEWGRAPH_LIVE_POST_OUT"

DISPOSABLE_MARKER = "reviewgraph-disposable-live-post-ok"
APPROVED_POST_SOURCE = "reviewgraph-approved-post-artifact"
SOURCE_DRY_RUN_SOURCE = "reviewgraph-dry-run-artifact"
APPROVED_POST_SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_PER_PAGE = 100
DEFAULT_MAX_PAGES = 5
DEFAULT_MAX_COMMENTS = 500


class ApprovalPrompter(Protocol):
    def confirm_hash(self, *, prompt: str, expected_hash: str) -> str: ...


class GhJsonPostRunner(Protocol):
    def run_json(
        self,
        args: tuple[str, ...],
        *,
        payload: Mapping[str, object],
        timeout_seconds: int,
        env: Mapping[str, str],
    ) -> GhCommandResult: ...


@dataclass(frozen=True)
class SubprocessGhJsonPostRunner:
    def run_json(
        self,
        args: tuple[str, ...],
        *,
        payload: Mapping[str, object],
        timeout_seconds: int,
        env: Mapping[str, str],
    ) -> GhCommandResult:
        try:
            completed = subprocess.run(
                list(args),
                check=False,
                capture_output=True,
                text=True,
                input=json.dumps(dict(payload), sort_keys=True, separators=(",", ":")),
                timeout=timeout_seconds,
                env={**dict(env), "GH_PROMPT_DISABLED": "1"},
            )
        except subprocess.TimeoutExpired as exc:
            return GhCommandResult(
                returncode=124,
                stdout=exc.stdout if isinstance(exc.stdout, str) else "",
                stderr=exc.stderr if isinstance(exc.stderr, str) else "gh api post timed out",
                timed_out=True,
            )
        return GhCommandResult(returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


@dataclass(frozen=True)
class LivePostSmokeArtifact:
    status: str
    reason: str
    pr_ref: dict[str, object] | None = None
    source_dry_run_artifact_hash: str | None = None
    approved_post_artifact_hash: str | None = None
    final_payload_hash: str | None = None
    approval_evidence: dict[str, object] | None = None
    preflight_summary: dict[str, object] | None = None
    finalization_summary: dict[str, object] | None = None
    writer_summary: dict[str, object] | None = None
    comment_id: str | None = None
    cleanup: dict[str, object] | None = None
    redaction_status: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        data = {
            "status": self.status,
            "reason": self.reason,
            "pr_ref": self.pr_ref,
            "source_dry_run_artifact_hash": self.source_dry_run_artifact_hash,
            "approved_post_artifact_hash": self.approved_post_artifact_hash,
            "final_payload_hash": self.final_payload_hash,
            "approval_evidence": self.approval_evidence or {},
            "preflight_summary": self.preflight_summary or {},
            "finalization_summary": self.finalization_summary or {},
            "writer_summary": self.writer_summary or {},
            "comment_id": self.comment_id,
            "cleanup": self.cleanup or {},
            "redaction_status": self.redaction_status or _empty_redaction_status(),
        }
        redacted = redact_data(data)
        if not isinstance(redacted.data, dict):
            raise ValueError("live post smoke artifact must serialize to an object")
        redacted.data["redaction_status"] = {
            "redacted": redacted.redaction_status.redacted
            or bool((self.redaction_status or {}).get("redacted")),
            "replacement_count": redacted.redaction_status.replacement_count
            + _replacement_count(self.redaction_status),
            "categories": sorted(
                set(redacted.redaction_status.categories)
                | {
                    item
                    for item in (self.redaction_status or {}).get("categories", ())
                    if isinstance(item, str)
                }
            ),
        }
        return redacted.data


@dataclass(frozen=True)
class ApprovedPostArtifact:
    data: dict[str, object]
    review_target: ReviewTarget
    posting_plan: PostingPlan
    findings: tuple[ClassifiedFinding, ...]
    candidate_payload: CandidateIssueCommentPayload
    final_payload_body: str
    final_payload_hash: str
    source_dry_run_artifact_hash: str
    artifact_hash: str
    run_id: str
    approved_item_ids: tuple[str, ...]
    local_verdict: ReviewVerdict | None
    include_public_verdict: bool
    approved_by: str
    timestamp: str


@dataclass(frozen=True)
class _LiveProofEnvelope:
    actor_probe: ActorPermissionProbeResult
    target_probe: TargetFreshnessProbeResult
    marker_result: object
    actor: str
    permission: str
    credential_source: str
    disposable_marker_present: bool
    fork_pr: bool
    command_count: int


class LivePostCommandError(RuntimeError):
    def __init__(
        self,
        reason_code: str,
        *,
        endpoint_kind: str,
        retryable: bool,
        request_id: str | None = None,
        message: str = "",
    ) -> None:
        self.reason_code = reason_code
        self.endpoint_kind = endpoint_kind
        self.retryable = retryable
        self.request_id = request_id
        super().__init__(message or reason_code)


def build_approved_post_artifact(
    *,
    source_dry_run_artifact_hash: str,
    run_id: str,
    review_target: ReviewTarget,
    posting_plan: PostingPlan,
    findings: tuple[ClassifiedFinding, ...],
    candidate_payload: CandidateIssueCommentPayload,
    approved_item_ids: tuple[str, ...],
    approved_by: str = "local-user",
    timestamp: str = "2026-05-07T00:04:30Z",
    local_verdict: ReviewVerdict | None = None,
    include_public_verdict: bool = False,
) -> ApprovedPostArtifact:
    _require_hash(source_dry_run_artifact_hash, "source_dry_run_artifact_hash")
    proof = build_approval_proof(
        approved_item_ids=approved_item_ids,
        review_target=review_target,
        posting_plan=posting_plan,
        findings=findings,
        candidate_payload=candidate_payload,
        run_id=run_id,
        approved_by=approved_by,
        timestamp=timestamp,
        local_verdict=local_verdict,
        include_public_verdict=include_public_verdict,
    )
    if proof.status != GateStatus.PASS:
        raise ValueError(f"approved-post artifact approval proof failed: {proof.reason_code}")
    findings_by_id = {finding.id: finding for finding in findings}
    selected_items = tuple(item for item in posting_plan.items if item.id in approved_item_ids)
    final_build = build_approved_final_issue_comment(
        run_id=run_id,
        review_target=review_target,
        findings_by_id=findings_by_id,
        selected_items=selected_items,
        local_verdict=local_verdict,
        include_public_verdict=include_public_verdict,
    )
    data: dict[str, object] = {
        "schema_version": APPROVED_POST_SCHEMA_VERSION,
        "artifact_kind": ArtifactKind.ISSUE_COMMENT.value,
        "source": APPROVED_POST_SOURCE,
        "created_by_helper": "build_approved_post_artifact",
        "source_dry_run_artifact_hash": source_dry_run_artifact_hash,
        "run_id": run_id,
        "target": review_target.to_ordered_dict(),
        "target_hash": review_target.target_hash(),
        "approved_item_ids": list(approved_item_ids),
        "finding_fingerprints": sorted(findings_by_id[item_id].fingerprint for item_id in approved_item_ids),
        "findings_hash": final_build.payload.findings_hash,
        "visible_body_hash": final_build.visible_body_hash,
        "marker_payload_hash": final_build.payload.marker_payload_hash,
        "marker_line": final_build.payload.marker_line,
        "final_payload_hash": final_build.payload.final_payload_hash,
        "final_payload_body": final_build.payload.body,
        "posting_plan_items": [_posting_plan_item_to_dict(item) for item in posting_plan.items],
        "candidate_findings": [_classified_finding_to_dict(finding) for finding in findings],
        "candidate_payload": _candidate_payload_to_dict(candidate_payload),
        "local_verdict": local_verdict.value if local_verdict is not None else None,
        "include_public_verdict": include_public_verdict,
        "approved_by": approved_by,
        "timestamp": timestamp,
    }
    data["artifact_hash"] = canonical_json_hash({key: value for key, value in data.items() if key != "artifact_hash"})
    return load_approved_post_artifact(data)


def load_approved_post_artifact(data: Mapping[str, object]) -> ApprovedPostArtifact:
    if not isinstance(data, Mapping):
        raise ValueError("approved-post artifact must be an object")
    artifact_hash = _required_str(data, "artifact_hash")
    expected_hash = canonical_json_hash({key: value for key, value in data.items() if key != "artifact_hash"})
    if artifact_hash != expected_hash:
        raise ValueError("approved-post artifact hash mismatch")
    if data.get("schema_version") != APPROVED_POST_SCHEMA_VERSION:
        raise ValueError("approved-post artifact schema_version mismatch")
    if data.get("source") != APPROVED_POST_SOURCE or data.get("created_by_helper") != "build_approved_post_artifact":
        raise ValueError("approved-post artifact must be helper-created")
    if data.get("artifact_kind") != ArtifactKind.ISSUE_COMMENT.value:
        raise ValueError("approved-post artifact kind must be issue_comment")
    source_hash = _required_str(data, "source_dry_run_artifact_hash")
    _require_hash(source_hash, "source_dry_run_artifact_hash")
    target = _review_target_from_dict(_required_mapping(data, "target"))
    if data.get("target_hash") != target.target_hash():
        raise ValueError("approved-post artifact target hash mismatch")
    run_id = _required_str(data, "run_id")
    approved_item_ids = _required_str_tuple(data, "approved_item_ids")
    posting_plan = PostingPlan(
        items=tuple(_posting_plan_item_from_dict(item) for item in _required_mapping_list(data, "posting_plan_items"))
    )
    findings = tuple(_classified_finding_from_dict(item) for item in _required_mapping_list(data, "candidate_findings"))
    candidate_payload = _candidate_payload_from_dict(_required_mapping(data, "candidate_payload"))
    local_verdict = _optional_verdict(data.get("local_verdict"))
    include_public_verdict = data.get("include_public_verdict")
    if type(include_public_verdict) is not bool:
        raise ValueError("approved-post artifact include_public_verdict must be bool")
    approved_by = _required_str(data, "approved_by")
    timestamp = _required_str(data, "timestamp")
    proof = build_approval_proof(
        approved_item_ids=approved_item_ids,
        review_target=target,
        posting_plan=posting_plan,
        findings=findings,
        candidate_payload=candidate_payload,
        run_id=run_id,
        approved_by=approved_by,
        timestamp=timestamp,
        local_verdict=local_verdict,
        include_public_verdict=include_public_verdict,
    )
    if proof.status != GateStatus.PASS:
        raise ValueError(f"approved-post artifact approval proof failed: {proof.reason_code}")
    findings_by_id = {finding.id: finding for finding in findings}
    selected_items = tuple(item for item in posting_plan.items if item.id in approved_item_ids)
    if len(selected_items) != len(approved_item_ids):
        raise ValueError("approved-post artifact approved items must exist in posting plan")
    final_build = build_approved_final_issue_comment(
        run_id=run_id,
        review_target=target,
        findings_by_id=findings_by_id,
        selected_items=selected_items,
        local_verdict=local_verdict,
        include_public_verdict=include_public_verdict,
    )
    final_body = _required_str(data, "final_payload_body")
    if final_body != final_build.payload.body:
        raise ValueError("approved-post artifact final payload body mismatch")
    for field_name, expected in (
        ("finding_fingerprints", sorted(findings_by_id[item_id].fingerprint for item_id in approved_item_ids)),
        ("findings_hash", final_build.payload.findings_hash),
        ("visible_body_hash", final_build.visible_body_hash),
        ("marker_payload_hash", final_build.payload.marker_payload_hash),
        ("marker_line", final_build.payload.marker_line),
        ("final_payload_hash", final_build.payload.final_payload_hash),
    ):
        actual = data.get(field_name)
        if actual != expected:
            raise ValueError(f"approved-post artifact {field_name} mismatch")
    return ApprovedPostArtifact(
        data=dict(data),
        review_target=target,
        posting_plan=posting_plan,
        findings=findings,
        candidate_payload=candidate_payload,
        final_payload_body=final_body,
        final_payload_hash=final_build.payload.final_payload_hash,
        source_dry_run_artifact_hash=source_hash,
        artifact_hash=artifact_hash,
        run_id=run_id,
        approved_item_ids=approved_item_ids,
        local_verdict=local_verdict,
        include_public_verdict=include_public_verdict,
        approved_by=approved_by,
        timestamp=timestamp,
    )


def blocked_live_post_artifact(
    *,
    env: Mapping[str, str] | None = None,
    gh_path: str | None = None,
    runner: GhCommandRunner | None = None,
    input_is_tty: bool = False,
    approved_artifact: Mapping[str, object] | None = None,
    source_dry_run_artifact: Mapping[str, object] | None = None,
) -> LivePostSmokeArtifact | None:
    env = dict(os.environ if env is None else env)
    if env.get(LIVE_POST_OPT_IN_ENV) != "1":
        return _blocked("missing_opt_in", env=env)
    pr_ref_text = env.get(LIVE_POST_PR_ENV)
    if not pr_ref_text:
        return _blocked("missing_pr_ref", env=env)
    pr_ref = _parsed_ref_or_none(pr_ref_text)
    if pr_ref is None:
        return _blocked("invalid_pr_ref", env=env)
    allowed = env.get(LIVE_POST_ALLOWED_TARGET_ENV)
    if allowed != pr_ref_text:
        return _blocked("target_not_allowlisted", env=env, pr_ref=pr_ref)
    if env.get(LIVE_POST_DISPOSABLE_MARKER_ENV) != DISPOSABLE_MARKER:
        return _blocked("missing_disposable_marker", env=env, pr_ref=pr_ref)
    if env.get(LIVE_POST_CREDENTIAL_SOURCE_ENV) != "pat":
        return _blocked("unsupported_credential_source", env=env, pr_ref=pr_ref)
    if approved_artifact is None and not env.get(LIVE_POST_APPROVED_ARTIFACT_ENV):
        return _blocked("missing_approved_post_artifact", env=env, pr_ref=pr_ref)
    if source_dry_run_artifact is None and not env.get(LIVE_POST_SOURCE_DRY_RUN_ARTIFACT_ENV):
        return _blocked("missing_source_dry_run_artifact", env=env, pr_ref=pr_ref)
    if not input_is_tty:
        return _blocked("missing_tty", env=env, pr_ref=pr_ref)
    if gh_path is None:
        gh_path = shutil.which("gh")
    if not gh_path:
        return _blocked("missing_gh", env=env, pr_ref=pr_ref)
    if any(env.get(name) for name in ("GITHUB_TOKEN", "GH_TOKEN")):
        return None
    runner = runner or SubprocessGhCommandRunner()
    token_result = runner.run((gh_path, "auth", "token"), timeout_seconds=DEFAULT_TIMEOUT_SECONDS, env=_gh_env(env))
    if token_result.returncode != 0 or token_result.timed_out or not token_result.stdout.strip():
        return _blocked("missing_token", env=env, pr_ref=pr_ref, message=token_result.stderr)
    return None


def run_live_post_smoke(
    *,
    env: Mapping[str, str] | None = None,
    output_path: str | Path | None = None,
    approval_prompter: ApprovalPrompter | None = None,
) -> LivePostSmokeArtifact:
    env = dict(os.environ if env is None else env)
    return _run_live_post_flow(
        env=env,
        gh_path=shutil.which("gh"),
        runner=SubprocessGhCommandRunner(),
        post_runner=SubprocessGhJsonPostRunner(),
        approved_artifact=_load_artifact_from_env(env),
        source_dry_run_artifact=_load_source_dry_run_artifact_from_env(env),
        input_is_tty=sys.stdin.isatty(),
        approval_prompter=approval_prompter or _StdinApprovalPrompter(),
        output_path=output_path,
    )


def run_live_post_contract(
    *,
    env: Mapping[str, str] | None = None,
    gh_path: str | None = None,
    runner: GhCommandRunner | None = None,
    post_runner: GhJsonPostRunner | None = None,
    approved_artifact: Mapping[str, object] | None = None,
    source_dry_run_artifact: Mapping[str, object] | None = None,
    input_is_tty: bool = False,
    approval_prompter: ApprovalPrompter | None = None,
    output_path: str | Path | None = None,
    now: Callable[[], str] | None = None,
) -> LivePostSmokeArtifact:
    env = dict(os.environ if env is None else env)
    if runner is None or post_runner is None or approval_prompter is None:
        artifact = _blocked("contract_requires_injected_fakes", env=env, pr_ref=_parsed_ref_or_none(env.get(LIVE_POST_PR_ENV, "")))
        _write_artifact_if_requested(artifact, env=env, output_path=output_path)
        return artifact
    if isinstance(runner, SubprocessGhCommandRunner) or isinstance(post_runner, SubprocessGhJsonPostRunner):
        artifact = _blocked("contract_rejects_subprocess_runners", env=env, pr_ref=_parsed_ref_or_none(env.get(LIVE_POST_PR_ENV, "")))
        _write_artifact_if_requested(artifact, env=env, output_path=output_path)
        return artifact
    return _run_live_post_flow(
        env=env,
        gh_path=gh_path,
        runner=runner,
        post_runner=post_runner,
        approved_artifact=approved_artifact,
        source_dry_run_artifact=source_dry_run_artifact,
        input_is_tty=input_is_tty,
        approval_prompter=approval_prompter,
        output_path=output_path,
        now=now,
    )


def _run_live_post_flow(
    *,
    env: Mapping[str, str],
    gh_path: str | None,
    runner: GhCommandRunner,
    post_runner: GhJsonPostRunner,
    approved_artifact: Mapping[str, object] | None,
    source_dry_run_artifact: Mapping[str, object] | None,
    input_is_tty: bool,
    approval_prompter: ApprovalPrompter,
    output_path: str | Path | None,
    now: Callable[[], str] | None = None,
) -> LivePostSmokeArtifact:
    env = dict(env)
    resolved_gh_path = gh_path if gh_path is not None else shutil.which("gh")
    blocked = blocked_live_post_artifact(
        env=env,
        gh_path=resolved_gh_path,
        runner=runner,
        input_is_tty=input_is_tty,
        approved_artifact=approved_artifact,
        source_dry_run_artifact=source_dry_run_artifact,
    )
    if blocked is not None:
        _write_artifact_if_requested(blocked, env=env, output_path=output_path)
        return blocked
    artifact_data = approved_artifact if approved_artifact is not None else _load_artifact_from_env(env)
    source_data = source_dry_run_artifact if source_dry_run_artifact is not None else _load_source_dry_run_artifact_from_env(env)
    assert artifact_data is not None
    assert source_data is not None
    try:
        approved = load_approved_post_artifact(artifact_data)
    except Exception as exc:
        artifact = _blocked("invalid_approved_post_artifact", env=env, pr_ref=_parsed_ref_or_none(env[LIVE_POST_PR_ENV]), message=str(exc))
        _write_artifact_if_requested(artifact, env=env, output_path=output_path)
        return artifact
    try:
        _verify_source_dry_run_artifact(source_data, approved)
    except Exception as exc:
        artifact = _blocked("invalid_source_dry_run_artifact", env=env, pr_ref=_parsed_ref_or_none(env[LIVE_POST_PR_ENV]), message=str(exc))
        _write_artifact_if_requested(artifact, env=env, output_path=output_path)
        return artifact
    pr_ref = parse_github_pr_ref(env[LIVE_POST_PR_ENV])
    if approved.review_target.owner_repo != pr_ref.owner_repo or approved.review_target.pr_number != pr_ref.pr_number:
        artifact = _blocked("approved_artifact_target_mismatch", env=env, pr_ref=_pr_ref_dict(pr_ref.owner_repo, pr_ref.pr_number))
        _write_artifact_if_requested(artifact, env=env, output_path=output_path)
        return artifact

    transport = _LivePostGhTransport(runner=runner, env=env, gh_executable=resolved_gh_path or "gh")
    try:
        pre_pr = transport.get_pull_request(pr_ref.owner_repo, pr_ref.pr_number)
        if not _has_disposable_marker(pre_pr):
            return _finish(_blocked("not_disposable_pr", env=env, pr_ref=_pr_ref_dict(pr_ref.owner_repo, pr_ref.pr_number)), env, output_path)
        if _is_fork_pr(pre_pr):
            return _finish(_blocked("fork_pr_not_supported", env=env, pr_ref=_pr_ref_dict(pr_ref.owner_repo, pr_ref.pr_number)), env, output_path)
        pre_checked_at = _now(now)
        pre_proof = transport.live_proof(approved.review_target, approved, checked_at=pre_checked_at)
        approval_evidence = {
            "tty_required": True,
            "shown_actor": True,
            "shown_permission": True,
            "shown_marker_scan": True,
            "shown_dry_run_artifact_hash": True,
            "shown_final_payload_hash": True,
            "pre_confirmation_actor": pre_proof.actor,
            "pre_confirmation_permission": pre_proof.permission,
            "pre_confirmation_marker": _marker_prompt_summary(pre_proof.marker_result),
            "pre_confirmation_checked_at": pre_checked_at,
        }
        typed_final_payload_hash = approval_prompter.confirm_hash(
            prompt=_approval_prompt(approved, pre_proof, pre_checked_at),
            expected_hash=approved.final_payload_hash,
        )
        approval_evidence["typed_hash_matched"] = typed_final_payload_hash == approved.final_payload_hash
        if typed_final_payload_hash != approved.final_payload_hash:
            return _finish(
                LivePostSmokeArtifact(
                    status="blocked",
                    reason="typed_hash_mismatch",
                    pr_ref=_pr_ref_dict(pr_ref.owner_repo, pr_ref.pr_number),
                    source_dry_run_artifact_hash=approved.source_dry_run_artifact_hash,
                    approved_post_artifact_hash=approved.artifact_hash,
                    final_payload_hash=approved.final_payload_hash,
                    approval_evidence=approval_evidence,
                ),
                env,
                output_path,
            )
        confirmed_at = _now(now)
        displayed_actor_gate = pre_proof.actor_probe_to_gate(approved.review_target, evaluated_at=confirmed_at)
        proof = build_approval_proof(
            approved_item_ids=approved.approved_item_ids,
            review_target=approved.review_target,
            posting_plan=approved.posting_plan,
            findings=approved.findings,
            candidate_payload=approved.candidate_payload,
            run_id=approved.run_id,
            approved_by=approved.approved_by,
            timestamp=confirmed_at,
            local_verdict=approved.local_verdict,
            include_public_verdict=approved.include_public_verdict,
        )
        decision = build_approval_decision(
            proof=proof,
            actor_permission_gate=displayed_actor_gate,
        )
        if decision.status != GateStatus.PASS or decision.approval is None:
            return _finish(_blocked("approval_build_failed", env=env, pr_ref=_pr_ref_dict(pr_ref.owner_repo, pr_ref.pr_number)), env, output_path)
        post_checked_at = _now(now)
        post_proof = transport.live_proof(approved.review_target, approved, checked_at=post_checked_at)
        if not post_proof.disposable_marker_present:
            return _finish(
                _blocked("post_approval_not_disposable_pr", env=env, pr_ref=_pr_ref_dict(pr_ref.owner_repo, pr_ref.pr_number)),
                env,
                output_path,
            )
        if post_proof.fork_pr:
            return _finish(
                _blocked("post_approval_fork_pr_not_supported", env=env, pr_ref=_pr_ref_dict(pr_ref.owner_repo, pr_ref.pr_number)),
                env,
                output_path,
            )

        final_build = build_approved_final_issue_comment(
            run_id=approved.run_id,
            review_target=approved.review_target,
            findings_by_id={finding.id: finding for finding in approved.findings},
            selected_items=tuple(item for item in approved.posting_plan.items if item.id in approved.approved_item_ids),
            local_verdict=approved.local_verdict,
            include_public_verdict=approved.include_public_verdict,
        )
        finalization = finalize_github_payload(
            approval=decision.approval,
            posting_plan=approved.posting_plan,
            approved_findings_by_id={finding.id: finding for finding in approved.findings},
            current_actor_permission_probe=post_proof.actor_probe,
            current_target_probe=post_proof.target_probe,
            evaluated_at=_now(now),
            final_payload_builder=lambda: final_build.payload,
            marker_reconciler=lambda payload: BoundMarkerReconciliationResult(
                result=post_proof.marker_result,
                expected_target_hash=payload.marker_target_hash,
                expected_payload_hash=payload.marker_payload_hash,
                expected_findings_hash=payload.marker_findings_hash,
            ),
        )
        if finalization.marker_reconciliation is not None and finalization.marker_reconciliation.status.value == "reconciled_existing":
            return _finish(
                LivePostSmokeArtifact(
                    status="succeeded",
                    reason="reconciled_existing",
                    pr_ref=_pr_ref_dict(pr_ref.owner_repo, pr_ref.pr_number),
                    source_dry_run_artifact_hash=approved.source_dry_run_artifact_hash,
                    approved_post_artifact_hash=approved.artifact_hash,
                    final_payload_hash=approved.final_payload_hash,
                    approval_evidence=approval_evidence,
                    finalization_summary=_finalization_summary(finalization),
                    writer_summary={"post_attempt_count": 0, "writer_invoked": False},
                    comment_id=finalization.marker_reconciliation.existing_comment_id,
                ),
                env,
                output_path,
            )
        if not finalization.writer_input_released:
            return _finish(
                LivePostSmokeArtifact(
                    status="fail_closed",
                    reason="finalization_failed",
                    pr_ref=_pr_ref_dict(pr_ref.owner_repo, pr_ref.pr_number),
                    source_dry_run_artifact_hash=approved.source_dry_run_artifact_hash,
                    approved_post_artifact_hash=approved.artifact_hash,
                    final_payload_hash=approved.final_payload_hash,
                    approval_evidence=approval_evidence,
                    finalization_summary=_finalization_summary(finalization),
                    writer_summary={"post_attempt_count": 0, "writer_invoked": False},
                ),
                env,
                output_path,
            )
        writer_input = build_finalized_issue_comment_writer_input(
            finalization=finalization,
            approval=decision.approval,
            run_id=approved.run_id,
        )
        writer = GitHubIssueCommentWriter(
            transport=_GhApiIssueCommentPostTransport(
                post_runner=post_runner,
                env=env,
                gh_executable=resolved_gh_path or "gh",
            ),
            recovery_marker_transport=transport,
            trusted_bot_authors=(),
        )
        writer_attempt = writer.post_issue_comment(writer_input)
        result = writer_attempt.writer_result
        return _finish(
            LivePostSmokeArtifact(
                status="succeeded" if result.status in {WriterStatus.POSTED, WriterStatus.RECONCILED} else "fail_closed",
                reason=result.status.value,
                pr_ref=_pr_ref_dict(pr_ref.owner_repo, pr_ref.pr_number),
                source_dry_run_artifact_hash=approved.source_dry_run_artifact_hash,
                approved_post_artifact_hash=approved.artifact_hash,
                final_payload_hash=approved.final_payload_hash,
                approval_evidence=approval_evidence,
                finalization_summary=_finalization_summary(finalization),
                writer_summary={
                    "writer_invoked": True,
                    "status": result.status.value,
                    "outcome_detail": writer_attempt.outcome_detail.value,
                    "post_attempt_count": writer_attempt.transport_summary.post_attempt_count,
                    "recovery_scan_count": writer_attempt.transport_summary.recovery_scan_count,
                    "endpoint_kind": writer_attempt.transport_summary.endpoint_kind,
                    "retryable": writer_attempt.transport_summary.retryable,
                    "reason_code": writer_attempt.transport_summary.reason_code,
                    "request_id": writer_attempt.transport_summary.request_id,
                },
                comment_id=result.comment_id,
                cleanup=_cleanup(result.comment_id),
            ),
            env,
            output_path,
        )
    except LivePostCommandError as exc:
        return _finish(
            LivePostSmokeArtifact(
                status="fail_closed",
                reason=exc.reason_code,
                pr_ref=_pr_ref_dict(pr_ref.owner_repo, pr_ref.pr_number),
                source_dry_run_artifact_hash=approved.source_dry_run_artifact_hash,
                approved_post_artifact_hash=approved.artifact_hash,
                final_payload_hash=approved.final_payload_hash,
                preflight_summary=_live_command_error_summary(exc),
            ),
            env,
            output_path,
        )
    except Exception as exc:
        return _finish(
            _blocked("live_post_failed", env=env, pr_ref=_pr_ref_dict(pr_ref.owner_repo, pr_ref.pr_number), message=str(exc)),
            env,
            output_path,
        )


def _finish(artifact: LivePostSmokeArtifact, env: Mapping[str, str], output_path: str | Path | None) -> LivePostSmokeArtifact:
    _write_artifact_if_requested(artifact, env=env, output_path=output_path)
    return artifact


@dataclass
class _LivePostGhTransport(PaginatedMarkerCommentTransport):
    runner: GhCommandRunner
    env: Mapping[str, str]
    gh_executable: str = "gh"
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    per_page: int = DEFAULT_PER_PAGE
    max_pages: int = DEFAULT_MAX_PAGES
    max_comments: int = DEFAULT_MAX_COMMENTS
    command_count: int = 0

    def get_pull_request(self, owner_repo: str, pr_number: int) -> dict[str, object]:
        return _dict_payload(self._get_json(f"repos/{owner_repo}/pulls/{pr_number}"))

    def live_proof(self, target: ReviewTarget, approved: ApprovedPostArtifact, *, checked_at: str) -> "_EvaluatedLiveProof":
        actor_payload = _dict_payload(self._get_json("user"))
        repo_payload = _dict_payload(self._get_json(f"repos/{target.owner_repo}"))
        pr_payload = self.get_pull_request(target.owner_repo, target.pr_number)
        compare_payload = _dict_payload(self._get_json(f"repos/{target.owner_repo}/compare/{target.base_sha}...{target.head_sha}"))
        current_target = _target_from_live_payload(target, pr_payload, compare_payload)
        repo_permission = _repo_permission_from_payload(repo_payload)
        actor = _text(actor_payload.get("login"))
        probe = ActorPermissionProbeResult(
            actor=actor,
            credential_principal=f"gh-user:{actor}",
            credential_source="pat",
            repo_permission=repo_permission,
            issue_comment_write=repo_permission in {"write", "maintain", "admin"},
            check_method="fake_issue_comment_permission_probe",
            endpoint_method="POST",
            checked_target=target,
            checked_at=checked_at,
            endpoint=issue_comment_endpoint(target),
            endpoint_kind="issue_comment",
            request_id=_request_id(repo_payload),
        )
        target_probe = TargetFreshnessProbeResult(
            current_target=current_target,
            checked_at=checked_at,
            check_method="fake_pull_request_target_probe",
            request_id=_request_id(pr_payload) or _request_id(compare_payload),
        )
        marker = reconcile_paginated_trusted_markers(
            transport=self,
            owner_repo=target.owner_repo,
            pr_number=target.pr_number,
            approved_actor=actor,
            trusted_bot_authors=(),
            expected_target_hash=target.target_hash(),
            expected_payload_hash=approved.data["marker_payload_hash"],
            expected_findings_hash=approved.data["findings_hash"],
            limits=MarkerScanLimits(max_pages=self.max_pages, max_comments=self.max_comments),
        )
        return _EvaluatedLiveProof(
            actor_probe=probe,
            target_probe=target_probe,
            marker_result=marker,
            actor=actor,
            permission=repo_permission,
            credential_source="pat",
            disposable_marker_present=_has_disposable_marker(pr_payload),
            fork_pr=_is_fork_pr(pr_payload),
            command_count=self.command_count,
        )

    def get_issue_comments_page(
        self,
        owner_repo: str,
        pr_number: int,
        cursor: object | None,
        timeout_seconds: int,
    ) -> MarkerCommentPage:
        page = 1 if cursor is None else int(cursor)
        if page > self.max_pages:
            raise MarkerScanTransportFailure(MarkerReconciliationReasonCode.PAGE_CAP_EXCEEDED)
        try:
            payload = self._get_json(f"repos/{owner_repo}/issues/{pr_number}/comments?per_page={self.per_page}&page={page}")
        except LivePostCommandError as exc:
            raise MarkerScanTransportFailure(
                _marker_reason_code(exc.reason_code),
                request_id=exc.request_id,
                raw_stderr=str(exc),
            ) from exc
        if not isinstance(payload, list):
            raise MarkerScanTransportFailure(MarkerReconciliationReasonCode.MALFORMED_PAGE)
        comments = tuple(_marker_comment(item) for item in payload if isinstance(item, Mapping))
        has_next = len(payload) == self.per_page
        return MarkerCommentPage(
            comments=comments,
            completed=not has_next,
            next_cursor=str(page + 1) if has_next else None,
            request_id=None,
        )

    def _get_json(self, resource: str) -> object:
        _assert_live_post_read_args((self.gh_executable, "api", resource), gh_executable=self.gh_executable)
        self.command_count += 1
        completed = self.runner.run((self.gh_executable, "api", resource), timeout_seconds=self.timeout_seconds, env=_gh_env(self.env))
        endpoint_kind = _endpoint_kind(resource)
        if completed.timed_out:
            raise LivePostCommandError(
                "timeout",
                endpoint_kind=endpoint_kind,
                retryable=True,
                message=_redacted_text(completed.stderr or "gh api timed out"),
            )
        if completed.returncode != 0:
            reason = _reason_from_gh_failure(completed.stderr, completed.returncode)
            raise LivePostCommandError(
                reason,
                endpoint_kind=endpoint_kind,
                retryable=_retryable_reason(reason),
                message=_redacted_text(completed.stderr or "gh api failed"),
            )
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise LivePostCommandError(
                "malformed_response",
                endpoint_kind=endpoint_kind,
                retryable=False,
                message=f"gh api returned invalid JSON: {exc.msg}",
            ) from exc


@dataclass(frozen=True)
class _EvaluatedLiveProof(_LiveProofEnvelope):
    def actor_probe_to_gate(self, target: ReviewTarget, *, evaluated_at: str):
        from reviewgraph.permissions import evaluate_actor_permission_gate

        return evaluate_actor_permission_gate(self.actor_probe, expected_target=target, evaluated_at=evaluated_at)


@dataclass
class _GhApiIssueCommentPostTransport:
    post_runner: GhJsonPostRunner
    env: Mapping[str, str]
    gh_executable: str = "gh"
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    calls: list[tuple[tuple[str, ...], dict[str, str]]] | None = None

    def post_issue_comment(
        self,
        owner_repo: str,
        pr_number: int,
        body: dict[str, str],
        timeout_seconds: int,
    ) -> GitHubIssueCommentPostResponse:
        if set(body) != {"body"} or not isinstance(body["body"], str):
            raise ValueError("live post body must be exactly {'body': str}")
        args = (
            self.gh_executable,
            "api",
            "--method",
            "POST",
            f"repos/{owner_repo}/issues/{pr_number}/comments",
            "--input",
            "-",
        )
        _assert_live_post_write_args(args, gh_executable=self.gh_executable, owner_repo=owner_repo, pr_number=pr_number)
        if self.calls is not None:
            self.calls.append((args, dict(body)))
        completed = self.post_runner.run_json(args, payload=body, timeout_seconds=timeout_seconds, env=_gh_env(self.env))
        if completed.timed_out:
            raise GitHubIssueCommentPostTransportFailure(GitHubIssueCommentWriterReasonCode.TIMEOUT)
        if completed.returncode != 0:
            raise GitHubIssueCommentPostTransportFailure(
                _writer_reason_code(_reason_from_gh_failure(completed.stderr, completed.returncode))
            )
        try:
            payload = _dict_payload(json.loads(completed.stdout))
        except json.JSONDecodeError as exc:
            raise GitHubIssueCommentPostTransportFailure(
                GitHubIssueCommentWriterReasonCode.MALFORMED_RESPONSE,
            ) from exc
        returned_body = payload.get("body")
        if isinstance(returned_body, str) and returned_body != body["body"]:
            raise GitHubIssueCommentPostTransportFailure(GitHubIssueCommentWriterReasonCode.MALFORMED_RESPONSE)
        return GitHubIssueCommentPostResponse(
            comment_id=str(payload.get("id") or ""),
            author_login=_user_login(payload.get("user")),
            request_id=_request_id(payload),
        )


def _assert_live_post_read_args(args: tuple[str, ...], *, gh_executable: str) -> None:
    if len(args) != 3 or args[0] != gh_executable or args[1] != "api":
        raise ValueError("live post reads may only run gh api REST reads")
    resource = args[2]
    if resource == "user":
        return
    parts = resource.split("/")
    if len(parts) < 3 or parts[0] != "repos":
        raise ValueError("live post read endpoint is not allowlisted")
    tail = "/".join(parts[3:])
    if tail == "":
        return
    if tail.startswith("pulls/") and "?" not in tail and len(tail.split("/")) == 2:
        return
    if tail.startswith("compare/") and "..." in tail:
        return
    if tail.startswith("issues/") and tail.endswith("/comments?per_page=100&page=1"):
        return
    if tail.startswith("issues/") and "/comments?per_page=100&page=" in tail:
        page = tail.rsplit("=", 1)[-1]
        if page.isdecimal() and int(page) > 0:
            return
    raise ValueError("live post read endpoint is not allowlisted")


def _assert_live_post_write_args(
    args: tuple[str, ...],
    *,
    gh_executable: str,
    owner_repo: str,
    pr_number: int,
) -> None:
    expected = (
        gh_executable,
        "api",
        "--method",
        "POST",
        f"repos/{owner_repo}/issues/{pr_number}/comments",
        "--input",
        "-",
    )
    if args != expected:
        raise ValueError("live post may only POST top-level issue comments with exact gh api args")


def _target_from_live_payload(target: ReviewTarget, pr_payload: Mapping[str, object], compare_payload: Mapping[str, object]) -> ReviewTarget:
    base = _dict_payload(pr_payload.get("base"))
    head = _dict_payload(pr_payload.get("head"))
    merge_base = _dict_payload(compare_payload.get("merge_base_commit")).get("sha")
    return ReviewTarget(
        owner_repo=target.owner_repo,
        pr_number=target.pr_number,
        base_sha=_text(base.get("sha")),
        head_sha=_text(head.get("sha")),
        merge_base_sha=_text(merge_base),
        diff_basis=target.diff_basis,
    )


def _repo_permission_from_payload(payload: Mapping[str, object]) -> str:
    permissions = _dict_payload(payload.get("permissions"))
    if permissions.get("admin") is True:
        return "admin"
    if permissions.get("maintain") is True:
        return "maintain"
    if permissions.get("push") is True:
        return "write"
    if permissions.get("triage") is True:
        return "triage"
    if permissions.get("pull") is True:
        return "read"
    return "read"


def _has_disposable_marker(payload: Mapping[str, object]) -> bool:
    texts = (
        str(payload.get("title") or ""),
        str(payload.get("body") or ""),
        str(_dict_payload(payload.get("head")).get("ref") or ""),
    )
    return any(DISPOSABLE_MARKER in text for text in texts)


def _is_fork_pr(payload: Mapping[str, object]) -> bool:
    head = _dict_payload(payload.get("head"))
    base = _dict_payload(payload.get("base"))
    head_repo = _dict_payload(head.get("repo")).get("full_name")
    base_repo = _dict_payload(base.get("repo")).get("full_name")
    if not isinstance(head_repo, str) or not head_repo or not isinstance(base_repo, str) or not base_repo:
        return True
    return head_repo != base_repo


def _marker_comment(item: Mapping[str, object]) -> PaginatedMarkerComment:
    return PaginatedMarkerComment(
        comment_id=str(item.get("id") or ""),
        body=str(item.get("body") or ""),
        author_login=_user_login(item.get("user")),
        author_type=_user_type(item.get("user")),
        source_provider="github",
    )


def _posting_plan_item_to_dict(item: PostingPlanItem) -> dict[str, object]:
    return {
        "id": item.id,
        "source_classification": item.source_classification,
        "destination": item.destination.value,
        "public_payload_eligible": item.public_payload_eligible,
        "fingerprint": item.fingerprint,
        "body": item.body,
    }


def _posting_plan_item_from_dict(data: Mapping[str, object]) -> PostingPlanItem:
    return PostingPlanItem(
        id=_required_str(data, "id"),
        source_classification=_required_str(data, "source_classification"),
        destination=PostingDestination(_required_str(data, "destination")),
        public_payload_eligible=_required_bool(data, "public_payload_eligible"),
        fingerprint=_optional_str(data.get("fingerprint")),
        body=_optional_str(data.get("body")),
    )


def _classified_finding_to_dict(finding: ClassifiedFinding) -> dict[str, object]:
    return {
        "id": finding.id,
        "source_reviewer": finding.source_reviewer,
        "source_stage": finding.source_stage,
        "title": finding.title,
        "body": finding.body,
        "evidence": finding.evidence,
        "path": finding.path,
        "line": finding.line,
        "priority": finding.priority,
        "severity": finding.severity.value,
        "confidence": finding.confidence.value,
        "fingerprint": finding.fingerprint,
        "blocking": finding.blocking,
        "line_end": finding.line_end,
    }


def _classified_finding_from_dict(data: Mapping[str, object]) -> ClassifiedFinding:
    return ClassifiedFinding(
        id=_required_str(data, "id"),
        source_reviewer=_required_str(data, "source_reviewer"),
        source_stage=_required_str(data, "source_stage"),
        title=_required_str(data, "title"),
        body=_required_str(data, "body"),
        evidence=_required_str(data, "evidence"),
        path=_required_str(data, "path"),
        line=_required_int(data, "line"),
        priority=_required_int(data, "priority"),
        severity=Severity(_required_str(data, "severity")),
        confidence=Confidence(_required_str(data, "confidence")),
        fingerprint=_required_str(data, "fingerprint"),
        blocking=_required_bool(data, "blocking"),
        line_end=_optional_int(data.get("line_end")),
    )


def _candidate_payload_to_dict(payload: CandidateIssueCommentPayload) -> dict[str, object]:
    return {
        "artifact_kind": payload.artifact_kind.value,
        "review_target": payload.review_target.to_ordered_dict(),
        "body": payload.body,
        "visible_body_hash": payload.visible_body_hash,
        "findings_hash": payload.findings_hash,
        "item_fingerprints": list(payload.item_fingerprints),
        "redaction_status": {
            "redacted": payload.redaction_status.redacted,
            "replacement_count": payload.redaction_status.replacement_count,
            "categories": list(payload.redaction_status.categories),
            "status": payload.redaction_status.status.value,
        },
    }


def _candidate_payload_from_dict(data: Mapping[str, object]) -> CandidateIssueCommentPayload:
    redaction = _required_mapping(data, "redaction_status")
    return CandidateIssueCommentPayload(
        artifact_kind=ArtifactKind(_required_str(data, "artifact_kind")),
        review_target=_review_target_from_dict(_required_mapping(data, "review_target")),
        body=_required_str(data, "body"),
        visible_body_hash=_required_str(data, "visible_body_hash"),
        findings_hash=_required_str(data, "findings_hash"),
        item_fingerprints=_required_str_tuple(data, "item_fingerprints"),
        redaction_status=RedactionStatus(
            redacted=_required_bool(redaction, "redacted"),
            replacement_count=_required_int(redaction, "replacement_count"),
            categories=_required_str_tuple(redaction, "categories"),
        ),
    )


def _review_target_from_dict(data: Mapping[str, object]) -> ReviewTarget:
    merge_base = data.get("merge_base_sha")
    return ReviewTarget(
        owner_repo=_required_str(data, "owner_repo"),
        pr_number=_required_int(data, "pr_number"),
        base_sha=_required_str(data, "base_sha"),
        head_sha=_required_str(data, "head_sha"),
        merge_base_sha=merge_base if isinstance(merge_base, str) else None,
        diff_basis=_required_str(data, "diff_basis"),
    )


def _finalization_summary(finalization: FinalizeGithubPayloadResult) -> dict[str, object]:
    marker = finalization.marker_reconciliation
    return {
        "state": finalization.finalization_status.state.value,
        "reason_code": finalization.finalization_status.reason_code.value
        if finalization.finalization_status.reason_code is not None
        else None,
        "writer_input_released": finalization.writer_input_released,
        "marker_reconciliation": marker.status.value if marker is not None else None,
        "marker_page_count": marker.transport_summary.page_count if marker is not None else None,
        "marker_comment_count": marker.transport_summary.comment_count if marker is not None else None,
        "marker_retryable": marker.transport_summary.retryable if marker is not None else None,
        "marker_reason_code": marker.reason_code.value if marker is not None and marker.reason_code is not None else None,
        "marker_request_id": marker.transport_summary.request_id if marker is not None else None,
    }


def _cleanup(comment_id: str | None) -> dict[str, object]:
    return {
        "manual_cleanup_required": True,
        "comment_id": comment_id,
        "automated_cleanup": False,
        "note": "Delete the disposable PR comment manually if the smoke artifact should not remain.",
    }


class _StdinApprovalPrompter:
    def confirm_hash(self, *, prompt: str, expected_hash: str) -> str:
        print(prompt, end="", flush=True)
        return input().strip()


def _approval_prompt(approved: ApprovedPostArtifact, proof: _LiveProofEnvelope, checked_at: str) -> str:
    return (
        "\nReviewGraph manual live post approval\n"
        f"Target: {approved.review_target.owner_repo}#{approved.review_target.pr_number}\n"
        f"Actor: {proof.actor}\n"
        f"Credential source: {proof.credential_source}\n"
        f"Endpoint permission: {proof.permission}\n"
        f"Marker scan: {_marker_prompt_summary(proof.marker_result)}\n"
        f"Source dry-run artifact hash: {approved.source_dry_run_artifact_hash}\n"
        f"Approved-post artifact hash: {approved.artifact_hash}\n"
        f"Final payload hash: {approved.final_payload_hash}\n"
        f"Pre-approval proof checked at: {checked_at}\n"
        "Exact final issue-comment payload:\n"
        f"{approved.final_payload_body}\n"
        "Type the exact final payload hash to post: "
    )


def _marker_prompt_summary(marker_result: object) -> str:
    status = getattr(getattr(marker_result, "status", None), "value", "unknown")
    reason_code = getattr(getattr(marker_result, "reason_code", None), "value", None)
    transport_summary = getattr(marker_result, "transport_summary", None)
    page_count = getattr(transport_summary, "page_count", None)
    comment_count = getattr(transport_summary, "comment_count", None)
    marker_count = getattr(transport_summary, "marker_count", None)
    return (
        f"status={status}; reason_code={reason_code}; "
        f"pages={page_count}; comments={comment_count}; markers={marker_count}"
    )


def _now(now: Callable[[], str] | None = None) -> str:
    if now is not None:
        value = now()
        if not isinstance(value, str) or not value:
            raise ValueError("live post clock must return a non-empty timestamp string")
        return value
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_artifact_from_env(env: Mapping[str, str]) -> dict[str, object] | None:
    path = env.get(LIVE_POST_APPROVED_ARTIFACT_ENV)
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("approved artifact file must contain a JSON object")
    return payload


def _load_source_dry_run_artifact_from_env(env: Mapping[str, str]) -> dict[str, object] | None:
    path = env.get(LIVE_POST_SOURCE_DRY_RUN_ARTIFACT_ENV)
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("source dry-run artifact file must contain a JSON object")
    return payload


def _verify_source_dry_run_artifact(data: Mapping[str, object], approved: ApprovedPostArtifact) -> None:
    if data.get("source") != SOURCE_DRY_RUN_SOURCE:
        raise ValueError("source dry-run artifact source mismatch")
    artifact_hash = _required_str(data, "artifact_hash")
    _require_hash(artifact_hash, "source dry-run artifact_hash")
    expected_hash = canonical_json_hash({key: value for key, value in data.items() if key != "artifact_hash"})
    if artifact_hash != expected_hash:
        raise ValueError("source dry-run artifact hash mismatch")
    if artifact_hash != approved.source_dry_run_artifact_hash:
        raise ValueError("approved artifact is not bound to source dry-run artifact")
    target = _review_target_from_dict(_required_mapping(data, "target"))
    if target != approved.review_target:
        raise ValueError("source dry-run artifact target mismatch")
    checks = {
        "target_hash": approved.review_target.target_hash(),
        "run_id": approved.run_id,
        "candidate_visible_body_hash": approved.candidate_payload.visible_body_hash,
        "candidate_findings_hash": approved.candidate_payload.findings_hash,
        "final_payload_hash": approved.final_payload_hash,
    }
    for name, expected in checks.items():
        if data.get(name) != expected:
            raise ValueError(f"source dry-run artifact {name} mismatch")
    fingerprints = data.get("candidate_item_fingerprints")
    if fingerprints is not None and tuple(fingerprints) != approved.candidate_payload.item_fingerprints:
        raise ValueError("source dry-run artifact candidate item fingerprints mismatch")


def _blocked(
    reason: str,
    *,
    env: Mapping[str, str],
    pr_ref: dict[str, object] | None = None,
    message: str | None = None,
) -> LivePostSmokeArtifact:
    redaction_status = _empty_redaction_status()
    redacted_message: str | None = None
    if message:
        redaction = redact_text(message)
        redacted_message = redaction.text
        redaction_status = {
            "redacted": redaction.redacted,
            "replacement_count": redaction.replacement_count,
            "categories": list(redaction.categories),
        }
    return LivePostSmokeArtifact(
        status="blocked",
        reason=reason,
        pr_ref=pr_ref,
        preflight_summary={
            "transport": "gh_api_rest",
            "live_post_opt_in": env.get(LIVE_POST_OPT_IN_ENV) == "1",
            "message": redacted_message,
        },
        redaction_status=redaction_status,
    )


def _live_command_error_summary(exc: LivePostCommandError) -> dict[str, object]:
    return {
        "transport": "gh_api_rest",
        "endpoint_kind": exc.endpoint_kind,
        "reason_code": exc.reason_code,
        "retryable": exc.retryable,
        "request_id": exc.request_id,
        "message": _redacted_text(str(exc)),
    }


def _endpoint_kind(resource: str) -> str:
    if resource == "user":
        return "actor"
    parts = resource.split("/")
    tail = "/".join(parts[3:]) if len(parts) >= 3 else ""
    if tail == "":
        return "repo_permission"
    if tail.startswith("pulls/"):
        return "pull_request_target"
    if tail.startswith("compare/"):
        return "pull_request_compare"
    if tail.startswith("issues/") and "/comments" in tail:
        return "issue_comments"
    return "unknown"


def _reason_from_gh_failure(stderr: str, returncode: int) -> str:
    text = stderr.casefold()
    if "403" in text or "forbidden" in text:
        return "forbidden"
    if "404" in text or "not found" in text:
        return "not_found"
    if "429" in text or "rate limit" in text or "rate_limited" in text:
        return "rate_limited"
    if returncode == 124 or "timed out" in text or "timeout" in text:
        return "timeout"
    return "unavailable"


def _retryable_reason(reason: str) -> bool:
    return reason in {"timeout", "rate_limited", "unavailable", "transport_unknown"}


def _marker_reason_code(reason: str) -> MarkerReconciliationReasonCode:
    return {
        "timeout": MarkerReconciliationReasonCode.TIMEOUT,
        "rate_limited": MarkerReconciliationReasonCode.RATE_LIMITED,
        "forbidden": MarkerReconciliationReasonCode.FORBIDDEN,
        "not_found": MarkerReconciliationReasonCode.NOT_FOUND,
        "unavailable": MarkerReconciliationReasonCode.UNAVAILABLE,
        "malformed_response": MarkerReconciliationReasonCode.MALFORMED_PAGE,
    }.get(reason, MarkerReconciliationReasonCode.TRANSPORT_UNKNOWN)


def _writer_reason_code(reason: str) -> GitHubIssueCommentWriterReasonCode:
    return {
        "timeout": GitHubIssueCommentWriterReasonCode.TIMEOUT,
        "rate_limited": GitHubIssueCommentWriterReasonCode.RATE_LIMITED,
        "forbidden": GitHubIssueCommentWriterReasonCode.FORBIDDEN,
        "not_found": GitHubIssueCommentWriterReasonCode.NOT_FOUND,
        "unavailable": GitHubIssueCommentWriterReasonCode.UNAVAILABLE,
        "malformed_response": GitHubIssueCommentWriterReasonCode.MALFORMED_RESPONSE,
    }.get(reason, GitHubIssueCommentWriterReasonCode.TRANSPORT_UNKNOWN)


def _write_artifact_if_requested(
    artifact: LivePostSmokeArtifact,
    *,
    env: Mapping[str, str],
    output_path: str | Path | None,
) -> None:
    destination = output_path or env.get(LIVE_POST_OUT_ENV)
    if destination is None:
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact.to_dict(), sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _gh_env(env: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in env.items()
        if key in {"PATH", "HOME", "GITHUB_TOKEN", "GH_TOKEN"}
    } | {"GH_PROMPT_DISABLED": "1"}


def _parsed_ref_or_none(value: str) -> dict[str, object] | None:
    try:
        ref = parse_github_pr_ref(value)
    except Exception:
        return None
    return _pr_ref_dict(ref.owner_repo, ref.pr_number)


def _pr_ref_dict(owner_repo: str, pr_number: int) -> dict[str, object]:
    return {"owner_repo": owner_repo, "pr_number": pr_number}


def _dict_payload(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("live post expected object JSON payload")
    return value


def _required_mapping(data: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = data.get(name)
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _required_mapping_list(data: Mapping[str, object], name: str) -> list[Mapping[str, object]]:
    value = data.get(name)
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{name} must be an array of objects")
    return value


def _required_str(data: Mapping[str, object], name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _required_int(data: Mapping[str, object], name: str) -> int:
    value = data.get(name)
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


def _required_bool(data: Mapping[str, object], name: str) -> bool:
    value = data.get(name)
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean")
    return value


def _required_str_tuple(data: Mapping[str, object], name: str) -> tuple[str, ...]:
    value = data.get(name)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"{name} must be an array of strings")
    return tuple(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("optional string must be non-empty")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise ValueError("optional int must be int")
    return value


def _optional_verdict(value: object) -> ReviewVerdict | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("local_verdict must be string or null")
    return ReviewVerdict(value)


def _require_hash(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a sha256 hash")


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("live post payload expected a non-empty string")
    return value


def _user_login(value: object) -> str:
    if not isinstance(value, Mapping):
        return "unknown"
    return _text(value.get("login"))


def _user_type(value: object) -> str:
    if not isinstance(value, Mapping):
        return "unknown"
    return str(value.get("type") or "unknown").lower()


def _request_id(payload: Mapping[str, object]) -> str | None:
    value = payload.get("request_id")
    return value if isinstance(value, str) and value else None


def _redacted_text(value: str) -> str:
    return redact_text(value).text


def _empty_redaction_status() -> dict[str, object]:
    return {"redacted": False, "replacement_count": 0, "categories": []}


def _replacement_count(value: object) -> int:
    if not isinstance(value, Mapping):
        return 0
    replacement_count = value.get("replacement_count")
    return replacement_count if type(replacement_count) is int else 0
