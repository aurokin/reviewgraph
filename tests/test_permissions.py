import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from reviewgraph.models import ActorPermissionReasonCode, GateStatus, ReviewTarget
from reviewgraph.permissions import ActorPermissionProbeResult, evaluate_actor_permission_gate, issue_comment_endpoint


EVALUATED_AT = "2026-05-07T00:05:00Z"
CHECKED_AT = "2026-05-07T00:03:00Z"


def test_pat_gate_passes_with_endpoint_bound_target_and_redacted_summary() -> None:
    target = _target()

    gate = evaluate_actor_permission_gate(_probe(target), expected_target=target, evaluated_at=EVALUATED_AT)

    assert gate.status == GateStatus.PASS
    assert gate.actor == "reviewgraph-bot"
    assert gate.permission == "write"
    assert gate.reason_code is None
    assert gate.credential_principal == "gh-user:reviewgraph-bot"
    assert gate.credential_source == "pat"
    assert gate.repo_permission == "write"
    assert gate.installation_permission is None
    assert gate.endpoint_permission is None
    assert gate.issue_comment_write is True
    assert gate.check_method == "fake_issue_comment_permission_probe"
    assert gate.endpoint_method == "POST"
    assert gate.checked_target == target.to_ordered_dict()
    assert gate.checked_target_hash == target.target_hash()
    assert gate.endpoint == "/repos/acme/widgets/issues/42/comments"
    assert gate.endpoint_kind == "issue_comment"
    assert gate.transport_summary is not None
    assert gate.transport_summary.endpoint_kind == "issue_comment_permission"
    assert gate.transport_summary.retryable is False
    assert gate.transport_summary.reason_code is None
    assert gate.transport_summary.request_id == "REQ-1"


@pytest.mark.parametrize(
    ("repo_permission", "expected_status"),
    [
        ("read", GateStatus.FAIL),
        ("triage", GateStatus.FAIL),
        ("write", GateStatus.PASS),
        ("maintain", GateStatus.PASS),
        ("admin", GateStatus.PASS),
    ],
)
def test_repo_permission_is_not_enough_without_issue_comment_write(
    repo_permission: str,
    expected_status: GateStatus,
) -> None:
    target = _target()

    gate = evaluate_actor_permission_gate(
        _probe(target, repo_permission=repo_permission),
        expected_target=target,
        evaluated_at=EVALUATED_AT,
    )

    assert gate.status == expected_status
    if expected_status == GateStatus.FAIL:
        assert gate.reason_code == ActorPermissionReasonCode.INSUFFICIENT_ENDPOINT_PERMISSION

    missing_endpoint_write = evaluate_actor_permission_gate(
        _probe(target, repo_permission="write", issue_comment_write=False),
        expected_target=target,
        evaluated_at=EVALUATED_AT,
    )
    assert missing_endpoint_write.status == GateStatus.FAIL
    assert missing_endpoint_write.reason_code == ActorPermissionReasonCode.INSUFFICIENT_ENDPOINT_PERMISSION


@pytest.mark.parametrize(
    ("credential_source", "installation_permission", "endpoint_permission"),
    [
        ("fine_grained_pat", None, "issues:write"),
        ("fine_grained_pat", None, "pull_requests:write"),
        ("github_app_installation", "issues:write", None),
        ("github_app_installation", "pull_requests:write", None),
        ("github_app_installation", "issues:write", "issues:write"),
        ("github_app_installation", "pull_requests:write", "pull_requests:write"),
        ("github_app_user", None, "issues:write"),
        ("github_app_user", None, "pull_requests:write"),
    ],
)
def test_fine_grained_and_github_app_endpoint_write_permissions_pass(
    credential_source: str,
    installation_permission: str | None,
    endpoint_permission: str,
) -> None:
    target = _target()

    gate = evaluate_actor_permission_gate(
        _probe(
            target,
            credential_source=credential_source,
            repo_permission=None,
            installation_permission=installation_permission,
            endpoint_permission=endpoint_permission,
        ),
        expected_target=target,
        evaluated_at=EVALUATED_AT,
    )

    assert gate.status == GateStatus.PASS
    assert gate.permission == (installation_permission or endpoint_permission)


@pytest.mark.parametrize(
    ("credential_source", "installation_permission", "endpoint_permission"),
    [
        ("fine_grained_pat", None, "issues:read"),
        ("fine_grained_pat", None, "pull_requests:read"),
        ("github_app_installation", "issues:read", "issues:read"),
        ("github_app_installation", "pull_requests:read", "pull_requests:read"),
        ("github_app_user", None, "issues:read"),
        ("github_app_user", None, "pull_requests:read"),
    ],
)
def test_fine_grained_and_github_app_read_permissions_fail_closed(
    credential_source: str,
    installation_permission: str | None,
    endpoint_permission: str,
) -> None:
    target = _target()

    gate = evaluate_actor_permission_gate(
        _probe(
            target,
            credential_source=credential_source,
            repo_permission=None,
            installation_permission=installation_permission,
            endpoint_permission=endpoint_permission,
        ),
        expected_target=target,
        evaluated_at=EVALUATED_AT,
    )

    assert gate.status == GateStatus.FAIL
    assert gate.reason_code == ActorPermissionReasonCode.INSUFFICIENT_ENDPOINT_PERMISSION


@pytest.mark.parametrize(
    ("credential_source", "updates"),
    [
        ("fine_grained_pat", {"repo_permission": "write", "endpoint_permission": None}),
        ("fine_grained_pat", {"repo_permission": None, "installation_permission": "issues:write", "endpoint_permission": None}),
        ("github_app_installation", {"repo_permission": "write", "installation_permission": None, "endpoint_permission": None}),
        ("github_app_installation", {"repo_permission": None, "installation_permission": "issues:read", "endpoint_permission": "issues:write"}),
        ("github_app_user", {"repo_permission": "write", "endpoint_permission": None}),
        ("github_app_user", {"repo_permission": None, "installation_permission": "issues:write", "endpoint_permission": None}),
        ("pat", {"repo_permission": "read", "endpoint_permission": "issues:write"}),
        ("pat", {"repo_permission": None, "endpoint_permission": "issues:write"}),
    ],
)
def test_credential_sources_reject_contradictory_permission_fields(
    credential_source: str,
    updates: dict[str, object],
) -> None:
    target = _target()

    gate = evaluate_actor_permission_gate(
        _probe(target, credential_source=credential_source, **updates),
        expected_target=target,
        evaluated_at=EVALUATED_AT,
    )

    assert gate.status == GateStatus.FAIL
    assert gate.reason_code == ActorPermissionReasonCode.MALFORMED_RESPONSE


@pytest.mark.parametrize(
    ("updates", "reason_code"),
    [
        ({"actor": None}, ActorPermissionReasonCode.UNKNOWN_ACTOR),
        ({"actor": "ghp_abcdefghijklmnopqrstuvwxyz123456"}, ActorPermissionReasonCode.UNKNOWN_ACTOR),
        ({"credential_source": "mystery"}, ActorPermissionReasonCode.UNKNOWN_CREDENTIAL_SOURCE),
        ({"credential_principal": None}, ActorPermissionReasonCode.MISSING_CREDENTIAL_PRINCIPAL),
        (
            {"credential_principal": "raw-token-ghp_abcdefghijklmnopqrstuvwxyz123456"},
            ActorPermissionReasonCode.MISSING_CREDENTIAL_PRINCIPAL,
        ),
        ({"credential_principal": 123}, ActorPermissionReasonCode.MALFORMED_RESPONSE),
        ({"check_method": None}, ActorPermissionReasonCode.MISSING_CHECK_METHOD),
        ({"endpoint": 123}, ActorPermissionReasonCode.MALFORMED_RESPONSE),
        ({"issue_comment_write": "true"}, ActorPermissionReasonCode.MALFORMED_RESPONSE),
        ({"checked_target": None}, ActorPermissionReasonCode.MISSING_CHECKED_TARGET),
        (
            {"checked_target": ReviewTarget("acme/widgets", 42, "base123", "head456", "merge789", "merge_base").to_ordered_dict()},
            ActorPermissionReasonCode.MALFORMED_RESPONSE,
        ),
        ({"checked_at": None}, ActorPermissionReasonCode.MISSING_CHECKED_AT),
        ({"repo_permission": None, "endpoint_permission": None}, ActorPermissionReasonCode.UNKNOWN_PERMISSION),
        ({"repo_permission": "owner"}, ActorPermissionReasonCode.UNKNOWN_PERMISSION),
    ],
)
def test_permission_gate_failures_have_stable_reason_codes(
    updates: dict[str, object],
    reason_code: ActorPermissionReasonCode,
) -> None:
    target = _target()

    gate = evaluate_actor_permission_gate(_probe(target, **updates), expected_target=target, evaluated_at=EVALUATED_AT)

    assert gate.status == GateStatus.FAIL
    assert gate.reason_code == reason_code
    assert gate.transport_summary is not None
    assert gate.transport_summary.reason_code is None
    assert gate.transport_summary.retryable is False


def test_string_transport_reason_code_fails_closed_as_malformed_transport_summary() -> None:
    target = _target()

    gate = evaluate_actor_permission_gate(
        _probe(target, transport_reason_code="timeout"),
        expected_target=target,
        evaluated_at=EVALUATED_AT,
    )

    assert gate.status == GateStatus.FAIL
    assert gate.reason_code == ActorPermissionReasonCode.MALFORMED_RESPONSE
    assert gate.transport_summary is not None
    assert gate.transport_summary.reason_code == ActorPermissionReasonCode.MALFORMED_RESPONSE
    assert gate.transport_summary.retryable is False


@pytest.mark.parametrize(
    ("updates", "reason_code"),
    [
        ({"checked_at": "2026-05-07T00:03:00+00:00"}, ActorPermissionReasonCode.MALFORMED_RESPONSE),
        ({"checked_at": "2026-05-07 00:03:00Z"}, ActorPermissionReasonCode.MALFORMED_RESPONSE),
        ({"checked_at": "2026-05-07T00:03Z"}, ActorPermissionReasonCode.MALFORMED_RESPONSE),
        ({"checked_at": "2026-05-07T24:00:00Z"}, ActorPermissionReasonCode.MALFORMED_RESPONSE),
        ({"checked_at": "2026-02-31T00:03:00Z"}, ActorPermissionReasonCode.MALFORMED_RESPONSE),
        ({"checked_at": "not-a-time"}, ActorPermissionReasonCode.MALFORMED_RESPONSE),
        ({"checked_at": "2026-05-06T23:00:00Z"}, ActorPermissionReasonCode.STALE_CACHED_PROOF),
        ({"checked_at": "2026-05-07T00:07:00Z"}, ActorPermissionReasonCode.STALE_CACHED_PROOF),
    ],
)
def test_checked_at_must_be_fresh_utc_rfc3339_z(
    updates: dict[str, object],
    reason_code: ActorPermissionReasonCode,
) -> None:
    target = _target()

    gate = evaluate_actor_permission_gate(_probe(target, **updates), expected_target=target, evaluated_at=EVALUATED_AT)

    assert gate.status == GateStatus.FAIL
    assert gate.reason_code == reason_code


@pytest.mark.parametrize(
    "reason_code",
    [
        ActorPermissionReasonCode.TIMEOUT,
        ActorPermissionReasonCode.RATE_LIMITED,
        ActorPermissionReasonCode.FORBIDDEN,
        ActorPermissionReasonCode.NOT_FOUND,
        ActorPermissionReasonCode.UNAVAILABLE,
        ActorPermissionReasonCode.MALFORMED_RESPONSE,
    ],
)
def test_transport_failures_emit_redacted_retryable_summaries(reason_code: ActorPermissionReasonCode) -> None:
    target = _target()

    gate = evaluate_actor_permission_gate(
        _probe(target, transport_reason_code=reason_code, request_id="REQ-secret-safe"),
        expected_target=target,
        evaluated_at=EVALUATED_AT,
    )

    assert gate.status == GateStatus.FAIL
    assert gate.reason_code == reason_code
    assert gate.transport_summary is not None
    assert gate.transport_summary.endpoint_kind == "issue_comment_permission"
    assert gate.transport_summary.reason_code == reason_code
    assert gate.transport_summary.request_id == "REQ-secret-safe"
    assert gate.transport_summary.retryable is (
        reason_code
        in {
            ActorPermissionReasonCode.TIMEOUT,
            ActorPermissionReasonCode.RATE_LIMITED,
            ActorPermissionReasonCode.UNAVAILABLE,
        }
    )
    assert set(gate.transport_summary.__dataclass_fields__) == {
        "endpoint_kind",
        "retryable",
        "reason_code",
        "request_id",
    }


def test_transport_failures_do_not_copy_raw_reason_or_secret_request_id() -> None:
    target = _target()

    gate = evaluate_actor_permission_gate(
        _probe(
            target,
            transport_reason_code=ActorPermissionReasonCode.TIMEOUT,
            reason="raw stderr contains ghp_abcdefghijklmnopqrstuvwxyz123456",
            request_id="ghp_abcdefghijklmnopqrstuvwxyz123456",
        ),
        expected_target=target,
        evaluated_at=EVALUATED_AT,
    )

    assert gate.status == GateStatus.FAIL
    assert gate.reason == "permission probe failed: timeout"
    assert gate.transport_summary is not None
    assert gate.transport_summary.request_id is None
    assert "ghp_" not in gate.reason


def test_failure_serialization_omits_unsafe_unknown_proof_fields() -> None:
    target = _target()

    gate = evaluate_actor_permission_gate(
        _probe(
            target,
            repo_permission="owner",
            endpoint=None,
        ),
        expected_target=target,
        evaluated_at=EVALUATED_AT,
    )

    assert gate.status == GateStatus.FAIL
    assert gate.permission is None
    assert gate.repo_permission is None
    assert gate.endpoint is None


def test_failure_serialization_drops_secret_like_or_unvalidated_fields() -> None:
    target = _target()

    gate = evaluate_actor_permission_gate(
        _probe(
            target,
            actor="ghp_abcdefghijklmnopqrstuvwxyz123456",
            credential_principal="raw stderr token=ghp_abcdefghijklmnopqrstuvwxyz123456",
            credential_source="mystery",
            check_method="other_probe",
            endpoint_method="GET",
            checked_at="raw ghp_abcdefghijklmnopqrstuvwxyz123456",
            endpoint="/repos/acme/widgets/issues/42/comments?token=ghp_abcdefghijklmnopqrstuvwxyz123456",
            endpoint_kind="other_kind",
        ),
        expected_target=target,
        evaluated_at=EVALUATED_AT,
    )

    assert gate.status == GateStatus.FAIL
    assert gate.actor is None
    assert gate.credential_principal is None
    assert gate.credential_source is None
    assert gate.check_method is None
    assert gate.endpoint_method is None
    assert gate.checked_at is None
    assert gate.endpoint is None
    assert gate.endpoint_kind is None


@pytest.mark.parametrize(
    "updates",
    [
        {"checked_target": ReviewTarget("acme/other", 42, "base123", "head456", "merge789", "merge_base")},
        {"checked_target": ReviewTarget("acme/widgets", 43, "base123", "head456", "merge789", "merge_base")},
        {"checked_target": ReviewTarget("acme/widgets", 42, "base999", "head456", "merge789", "merge_base")},
        {"endpoint": "/repos/acme/widgets/issues/43/comments"},
        {"endpoint_method": "GET"},
        {"endpoint_kind": "pull_request_review"},
    ],
)
def test_checked_target_and_endpoint_mismatch_fail_closed(updates: dict[str, object]) -> None:
    target = _target()

    gate = evaluate_actor_permission_gate(_probe(target, **updates), expected_target=target, evaluated_at=EVALUATED_AT)

    assert gate.status == GateStatus.FAIL
    assert gate.reason_code == ActorPermissionReasonCode.TARGET_MISMATCH


def test_actor_permission_permissions_module_has_no_live_or_write_imports() -> None:
    imports = _imports(Path("src/reviewgraph/permissions.py"))

    assert not (
        imports
        & {
            "github",
            "httpx",
            "openai",
            "requests",
            "socket",
            "subprocess",
            "reviewgraph.approval",
            "reviewgraph.finalization",
            "reviewgraph.github",
            "reviewgraph.graph",
            "reviewgraph.posting",
            "reviewgraph.writer",
        }
    )


def test_actor_permission_permissions_module_does_not_transitively_load_live_or_write_boundaries() -> None:
    script = """
import json
import sys
import reviewgraph.permissions
forbidden = sorted(
    name for name in sys.modules
    if name.startswith(('reviewgraph.approval', 'reviewgraph.finalization', 'reviewgraph.github', 'reviewgraph.graph', 'reviewgraph.posting', 'reviewgraph.writer'))
    or name.split('.', 1)[0] in {'github', 'httpx', 'openai', 'requests', 'socket', 'subprocess'}
)
print(json.dumps(forbidden))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "src"},
    )

    assert json.loads(completed.stdout) == []


def _target() -> ReviewTarget:
    return ReviewTarget("acme/widgets", 42, "base123", "head456", "merge789", "merge_base")


def _probe(target: ReviewTarget, **updates: object) -> ActorPermissionProbeResult:
    values = {
        "actor": "reviewgraph-bot",
        "credential_principal": "gh-user:reviewgraph-bot",
        "credential_source": "pat",
        "repo_permission": "write",
        "installation_permission": None,
        "endpoint_permission": None,
        "issue_comment_write": True,
        "check_method": "fake_issue_comment_permission_probe",
        "endpoint_method": "POST",
        "checked_target": target,
        "checked_at": CHECKED_AT,
        "endpoint": issue_comment_endpoint(target),
        "endpoint_kind": "issue_comment",
        "request_id": "REQ-1",
    }
    values.update(updates)
    return ActorPermissionProbeResult(**values)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports
