import ast
import importlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from reviewgraph.config import parse_reviewer_config
from reviewgraph.context_budget import ContextBudget, apply_input_context_budget
from reviewgraph.fixtures import load_fixture_pr
from reviewgraph.llm import (
    FakeLiveLLMProviderTransport,
    LiveLLMProviderError,
    LiveLLMProviderRequest,
    LiveLLMProviderResponse,
    execute_live_llm_reviewer_attempt,
    run_live_llm_reviewer_with_retries,
)
from reviewgraph.llm_policy import LiveLLMBudgetLedger, LiveLLMPolicyInput, ProviderFailureReasonCode, evaluate_live_llm_policy
from reviewgraph.live_llm_smoke import live_llm_smoke_prerequisite_artifact
from reviewgraph.memory import build_conversation_memory
from reviewgraph.models import ReviewerRunKey, ReviewerRunStatusValue, ReviewStage, SelectedReviewer
from reviewgraph.redaction import REDACTION_TOKEN
from reviewgraph.reviewer_context import build_reviewer_context_package
from reviewgraph.runner import _review_config_hash, run_fixture_dry_run
from reviewgraph.cli import main


SECRET = "sk_live_1234567890abcdef"


def _package_and_key(*, max_live_calls: int = 2, reviewer_name: str = "correctness"):
    fixture = load_fixture_pr("basic-pr")
    secret_file = replace(
        fixture.pr.changed_files[0],
        patch=f'@@ -1 +1 @@\n+api_key = "{SECRET}"\n',
    )
    pr = replace(fixture.pr, changed_files=(secret_file,))
    memory = build_conversation_memory(pr)
    budgeted_context = apply_input_context_budget(
        pr=pr,
        memory=memory,
        limits=ContextBudget(
            max_changed_files=10,
            max_patch_bytes=1_000_000,
            max_memory_bytes=1_000_000,
            max_reviewers=10,
            max_live_calls=max_live_calls,
        ),
    )
    config = parse_reviewer_config(
        {
            "agents": {
                reviewer_name: {
                    "stages": ["initial_triage"],
                    "triggers": {"always": True},
                    "required": True,
                    "model": "gpt-review",
                    "context": "diff-plus-comments",
                    "capabilities": ["diff_context"],
                }
            },
            "live_llm": {
                "provider": "openai",
                "model": "gpt-review",
                "max_attempts": 2,
                "timeout_seconds": 30,
                "max_live_calls": max_live_calls,
            },
        }
    )
    reviewer = SelectedReviewer(
        name=reviewer_name,
        stage="initial_triage",
        reasons=("initial_triage triggers.always=true",),
    )
    package = build_reviewer_context_package(
        active_stage="initial_triage",
        reviewer=reviewer,
        reviewer_config=config.agents[reviewer_name],
        budgeted_context=budgeted_context,
    )
    run_key = ReviewerRunKey(
        target_hash=package.review_target.target_hash(),
        config_hash=_review_config_hash(config),
        stage=ReviewStage.INITIAL_TRIAGE,
        reviewer=reviewer_name,
    )
    return package, run_key, config


def _policy_input(package, run_key: ReviewerRunKey) -> LiveLLMPolicyInput:
    return LiveLLMPolicyInput(
        reviewer_run_key=run_key,
        live_llm_enabled=True,
        live_llm_opt_in_source="cli:--live-llm",
        provider="openai",
        model="gpt-review",
    )


def _provider_output(*, evidence: str = "Changed line 1 returns a stale cache value.") -> str:
    return json.dumps(
        {
            "items": [
                {
                    "type": "finding",
                    "id": "finding-live-cache",
                    "severity": "warning",
                    "confidence": "high",
                    "path": "src/cache.py",
                    "line": 12,
                    "title": "Cache miss returns stale data",
                    "body": "The new cache miss branch can return stale data.",
                    "evidence": evidence,
                }
            ]
        }
    )


def test_fake_reviewers_remain_default_when_config_has_model(tmp_path: Path) -> None:
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "correctness": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                        "required": True,
                        "model": "gpt-review",
                        "capabilities": ["diff_context"],
                    }
                }
            }
        )
    )

    result = run_fixture_dry_run(fixture_ref="basic-pr", reviewer_config_path=str(config_path))

    assert result.json_data["reviewer_results"][0]["status"] == "completed"
    assert result.json_data["reviewer_results"][0]["live_llm_evidence"] is None
    assert result.json_data["side_effects"]["writer_called"] is False


def test_config_live_llm_defaults_parse_and_change_config_hash() -> None:
    base = parse_reviewer_config(
        {
            "agents": {
                "correctness": {
                    "stages": ["initial_triage"],
                    "triggers": {"always": True},
                }
            }
        }
    )
    live = parse_reviewer_config(
        {
            "agents": {
                "correctness": {
                    "stages": ["initial_triage"],
                    "triggers": {"always": True},
                }
            },
            "live_llm": {"provider": "openai", "model": "gpt-review", "max_live_calls": 2},
        }
    )

    assert live.live_llm is not None
    assert live.live_llm.provider == "openai"
    assert live.live_llm.model == "gpt-review"
    assert _review_config_hash(base) != _review_config_hash(live)


def test_cli_live_llm_requires_explicit_provider_model_and_budget(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--live-llm"]) == 2
    assert "--live-llm-provider" in capsys.readouterr().err

    assert main(["--live-llm-provider", "openai"]) == 2
    assert "require --live-llm" in capsys.readouterr().err

    assert (
        main(
            [
                "--live-llm",
                "--live-llm-provider",
                "openai",
                "--live-llm-model",
                "gpt-review",
                "--live-llm-max-calls",
                "1",
            ]
        )
        == 2
    )
    assert "REVIEWGRAPH_LIVE_LLM_API_KEY or OPENAI_API_KEY" in capsys.readouterr().err


def test_live_runner_opt_in_executes_fake_transport_and_records_safe_state(tmp_path: Path) -> None:
    config_path = _single_reviewer_config(tmp_path, required=True)
    transport = FakeLiveLLMProviderTransport(
        [LiveLLMProviderResponse(_provider_output(evidence=f"Changed line redacts token={SECRET}"), request_id="req-ok")]
    )

    result = run_fixture_dry_run(
        fixture_ref="basic-pr",
        reviewer_config_path=str(config_path),
        live_llm_settings={
            "provider": "openai",
            "model": "gpt-review",
            "max_attempts": 1,
            "max_live_calls": 1,
        },
        live_llm_transport=transport,
        live_llm_opt_in_source="test:explicit-live-opt-in",
    )

    assert len(transport.calls) == 1
    assert result.json_data["reviewer_results"][0]["status"] == "completed"
    assert result.json_data["reviewer_results"][0]["live_llm_evidence"]["provider"] == "openai"
    assert result.json_data["live_llm"]["ledger"]["reserved_live_calls"] == 1
    assert result.json_data["live_llm"]["policy_audits"][0]["opt_in"]["source"] == "test:explicit-live-opt-in"
    assert any(event.get("event") == "live_llm_provider_attempt_succeeded" for event in result.json_data["graph_trace"])
    assert result.json_data["reviewer_run_status"][0]["reason"] == "live LLM reviewer execution completed"
    assert SECRET not in json.dumps(result.json_data, sort_keys=True)
    assert REDACTION_TOKEN in json.dumps(result.json_data["reviewer_results"], sort_keys=True)


def test_live_transport_without_explicit_run_opt_in_is_rejected(tmp_path: Path) -> None:
    config_path = _single_reviewer_config(tmp_path, required=True)
    transport = FakeLiveLLMProviderTransport([LiveLLMProviderResponse(_provider_output())])

    with pytest.raises(ValueError, match="explicit opt-in source"):
        run_fixture_dry_run(
            fixture_ref="basic-pr",
            reviewer_config_path=str(config_path),
            live_llm_settings={
                "provider": "openai",
                "model": "gpt-review",
                "max_attempts": 1,
                "max_live_calls": 1,
            },
            live_llm_transport=transport,
        )

    assert transport.calls == []


def test_live_runner_missing_model_records_policy_evidence_without_provider_call(tmp_path: Path) -> None:
    config_path = _single_reviewer_config(tmp_path, required=True, include_model=False)
    transport = FakeLiveLLMProviderTransport([LiveLLMProviderResponse(_provider_output())])

    result = run_fixture_dry_run(
        fixture_ref="basic-pr",
        reviewer_config_path=str(config_path),
        live_llm_settings={
            "provider": "openai",
            "max_attempts": 1,
            "max_live_calls": 1,
        },
        live_llm_transport=transport,
        live_llm_opt_in_source="test:explicit-live-opt-in",
    )

    assert transport.calls == []
    assert result.json_data["reviewer_results"][0]["status"] == "failed"
    evidence = result.json_data["reviewer_results"][0]["live_llm_evidence"]
    assert evidence["failure_reason"] == "missing_model"
    assert result.json_data["live_llm"]["policy_audits"][0]["reason_code"] == "missing_model"
    assert result.json_data["errors"][0]["code"] == "required_reviewer_failed"


def test_live_adapter_success_uses_policy_request_and_redacted_evidence() -> None:
    package, run_key, _ = _package_and_key()
    policy = _policy_input(package, run_key)
    approved = evaluate_live_llm_policy(package, policy, ledger=LiveLLMBudgetLedger())
    transport = FakeLiveLLMProviderTransport(
        [LiveLLMProviderResponse(_provider_output(evidence=f"token={SECRET}"), request_id=f"req-{SECRET}")]
    )

    result = execute_live_llm_reviewer_attempt(
        policy_result=approved,
        package=package,
        run_key=run_key,
        current_ledger=approved.ledger,
        transport=transport,
        timeout_seconds=17,
    )

    assert result.status == ReviewerRunStatusValue.COMPLETED
    assert result.findings[0].id == "finding-live-cache"
    assert SECRET not in result.findings[0].evidence
    assert len(transport.calls) == 1
    assert transport.calls[0].request_text == approved.execution_plan.request_text
    assert transport.calls[0].request_hash == approved.execution_plan.request_hash
    assert transport.calls[0].timeout_seconds == 17
    evidence = result.live_llm_evidence.to_ordered_dict()
    serialized = json.dumps({"evidence": evidence, "raw": result.raw_output}, sort_keys=True)
    assert evidence["provider"] == "openai"
    assert evidence["model"] == "gpt-review"
    assert evidence["raw_request_retained"] is False
    assert evidence["raw_response_retained"] is False
    assert evidence["response_hash"].startswith("sha256:")
    assert SECRET not in serialized
    assert REDACTION_TOKEN in serialized


def test_live_adapter_provider_failure_is_redacted_and_retryable() -> None:
    package, run_key, _ = _package_and_key()
    approved = evaluate_live_llm_policy(package, _policy_input(package, run_key), ledger=LiveLLMBudgetLedger())
    transport = FakeLiveLLMProviderTransport(
        [LiveLLMProviderError(ProviderFailureReasonCode.TIMEOUT, f"timeout token={SECRET}", request_id=f"req-{SECRET}")]
    )

    result = execute_live_llm_reviewer_attempt(
        policy_result=approved,
        package=package,
        run_key=run_key,
        current_ledger=approved.ledger,
        transport=transport,
    )

    evidence = result.live_llm_evidence.to_ordered_dict()
    assert result.status == ReviewerRunStatusValue.FAILED
    assert result.errors == ("live LLM provider failed: timeout",)
    assert evidence["failure_reason"] == "timeout"
    assert evidence["retryable"] is True
    assert SECRET not in json.dumps(evidence, sort_keys=True)


@pytest.mark.parametrize(
    ("reason_code", "retryable"),
    [
        (ProviderFailureReasonCode.TIMEOUT, True),
        (ProviderFailureReasonCode.RATE_LIMITED, True),
        (ProviderFailureReasonCode.PROVIDER_UNAVAILABLE, True),
        (ProviderFailureReasonCode.MISSING_CREDENTIALS, False),
    ],
)
def test_live_provider_failure_reason_mapping(reason_code: ProviderFailureReasonCode, retryable: bool) -> None:
    package, run_key, _ = _package_and_key()
    approved = evaluate_live_llm_policy(package, _policy_input(package, run_key), ledger=LiveLLMBudgetLedger())
    transport = FakeLiveLLMProviderTransport([LiveLLMProviderError(reason_code, f"failure token={SECRET}")])

    result = execute_live_llm_reviewer_attempt(
        policy_result=approved,
        package=package,
        run_key=run_key,
        current_ledger=approved.ledger,
        transport=transport,
    )

    evidence = result.live_llm_evidence.to_ordered_dict()
    assert result.status == ReviewerRunStatusValue.FAILED
    assert evidence["failure_reason"] == reason_code.value
    assert evidence["failure_summary"]["retryable"] is retryable
    assert SECRET not in json.dumps(evidence, sort_keys=True)


def test_live_unexpected_transport_exception_maps_to_redacted_unknown_failure() -> None:
    package, run_key, _ = _package_and_key()
    approved = evaluate_live_llm_policy(package, _policy_input(package, run_key), ledger=LiveLLMBudgetLedger())

    def broken_transport(request):
        raise RuntimeError(f"boom token={SECRET}")

    result = execute_live_llm_reviewer_attempt(
        policy_result=approved,
        package=package,
        run_key=run_key,
        current_ledger=approved.ledger,
        transport=broken_transport,
    )

    evidence = result.live_llm_evidence.to_ordered_dict()
    assert evidence["failure_reason"] == "unknown_provider_error"
    assert evidence["retryable"] is False
    assert SECRET not in json.dumps(evidence, sort_keys=True)


def test_live_retry_runner_records_distinct_attempt_keys_and_ledgers() -> None:
    package, run_key, _ = _package_and_key(max_live_calls=2)
    transport = FakeLiveLLMProviderTransport(
        [
            LiveLLMProviderError(ProviderFailureReasonCode.TIMEOUT, "timeout"),
            LiveLLMProviderResponse(_provider_output(), request_id="req-ok"),
        ]
    )

    result = run_live_llm_reviewer_with_retries(
        package=package,
        initial_run_key=run_key,
        policy_input=_policy_input(package, run_key),
        ledger=LiveLLMBudgetLedger(),
        transport=transport,
        max_attempts=2,
    )

    assert len(result.attempts) == 2
    assert result.attempts[0].reviewer_result.run_key.attempt == 1
    assert result.attempts[1].reviewer_result.run_key.attempt == 2
    assert result.attempts[1].reviewer_result.run_key.retry_of == run_key.stable_key()
    assert result.ledger.reserved_live_calls == 2
    assert result.final_result.status == ReviewerRunStatusValue.COMPLETED
    assert [call.attempt for call in transport.calls] == [1, 2]


def test_live_retry_exhaustion_is_final_non_retryable_failure() -> None:
    package, run_key, _ = _package_and_key(max_live_calls=2)
    transport = FakeLiveLLMProviderTransport(
        [
            LiveLLMProviderError(ProviderFailureReasonCode.TIMEOUT, "timeout one"),
            LiveLLMProviderError(ProviderFailureReasonCode.TIMEOUT, "timeout two"),
        ]
    )

    result = run_live_llm_reviewer_with_retries(
        package=package,
        initial_run_key=run_key,
        policy_input=_policy_input(package, run_key),
        ledger=LiveLLMBudgetLedger(),
        transport=transport,
        max_attempts=2,
    )

    evidence = result.final_result.live_llm_evidence.to_ordered_dict()
    assert result.final_result.errors == ("live LLM provider failed: retry_exhausted",)
    assert evidence["failure_reason"] == "retry_exhausted"
    assert evidence["last_failure_reason"] == "timeout"
    assert evidence["retryable"] is False


def test_live_retry_runner_requires_budget_for_effective_attempts_before_provider_call() -> None:
    package, run_key, _ = _package_and_key(max_live_calls=1)
    transport = FakeLiveLLMProviderTransport([LiveLLMProviderResponse(_provider_output())])

    with pytest.raises(ValueError, match="budget must cover effective max attempts"):
        run_live_llm_reviewer_with_retries(
            package=package,
            initial_run_key=run_key,
            policy_input=_policy_input(package, run_key),
            ledger=LiveLLMBudgetLedger(),
            transport=transport,
            max_attempts=2,
        )

    assert transport.calls == []


def test_live_total_timeout_caps_provider_attempts() -> None:
    package, run_key, _ = _package_and_key(max_live_calls=3)
    transport = FakeLiveLLMProviderTransport(
        [
            LiveLLMProviderError(ProviderFailureReasonCode.TIMEOUT, "timeout one"),
            LiveLLMProviderError(ProviderFailureReasonCode.TIMEOUT, "timeout two"),
            LiveLLMProviderResponse(_provider_output()),
        ]
    )

    result = run_live_llm_reviewer_with_retries(
        package=package,
        initial_run_key=run_key,
        policy_input=_policy_input(package, run_key),
        ledger=LiveLLMBudgetLedger(),
        transport=transport,
        max_attempts=3,
        timeout_seconds=30,
        total_timeout_seconds=60,
    )

    assert len(transport.calls) == 2
    assert result.final_result.live_llm_evidence.to_ordered_dict()["failure_reason"] == "retry_exhausted"
    assert any(event["event"] == "live_llm_total_timeout_exhausted" for event in result.trace_events)


def test_live_runner_deferred_by_worst_case_budget_before_provider_call(tmp_path: Path) -> None:
    config_path = _single_reviewer_config(tmp_path, required=True)
    transport = FakeLiveLLMProviderTransport([LiveLLMProviderResponse(_provider_output())])

    result = run_fixture_dry_run(
        fixture_ref="basic-pr",
        reviewer_config_path=str(config_path),
        live_llm_settings={
            "provider": "openai",
            "model": "gpt-review",
            "max_attempts": 2,
            "max_live_calls": 1,
        },
        live_llm_transport=transport,
        live_llm_opt_in_source="test:explicit-live-opt-in",
    )

    assert transport.calls == []
    assert result.json_data["live_llm"]["ledger"] is None
    assert result.json_data["review"]["context_budget"]["live_calls"]["deferred_reviewer_ids"] == [
        "initial_triage:correctness"
    ]


def test_live_required_and_optional_failures_follow_runner_semantics(tmp_path: Path) -> None:
    required_config = _single_reviewer_config(tmp_path, required=True, name="required-reviewers.json")
    optional_config = _single_reviewer_config(tmp_path, required=False, name="optional-reviewers.json")

    required = run_fixture_dry_run(
        fixture_ref="basic-pr",
        reviewer_config_path=str(required_config),
        live_llm_settings={
            "provider": "openai",
            "model": "gpt-review",
            "max_attempts": 1,
            "max_live_calls": 1,
        },
        live_llm_transport=FakeLiveLLMProviderTransport(
            [LiveLLMProviderError(ProviderFailureReasonCode.MISSING_CREDENTIALS, "missing")]
        ),
        live_llm_opt_in_source="test:explicit-live-opt-in",
    )
    optional = run_fixture_dry_run(
        fixture_ref="basic-pr",
        reviewer_config_path=str(optional_config),
        live_llm_settings={
            "provider": "openai",
            "model": "gpt-review",
            "max_attempts": 1,
            "max_live_calls": 1,
        },
        live_llm_transport=FakeLiveLLMProviderTransport(
            [LiveLLMProviderError(ProviderFailureReasonCode.MISSING_CREDENTIALS, "missing")]
        ),
        live_llm_opt_in_source="test:explicit-live-opt-in",
    )

    assert required.json_data["errors"][0]["code"] == "required_reviewer_failed"
    assert required.json_data["post_enabled"] is False
    assert optional.json_data["errors"] == []
    assert optional.json_data["partial_review"]["has_partial_review"] is True
    assert optional.json_data["review"]["classified_output"]["local_notes"][0]["title"] == "Optional reviewer failed"


def test_optional_live_retry_success_is_not_partial_review(tmp_path: Path) -> None:
    optional_config = _single_reviewer_config(tmp_path, required=False)

    result = run_fixture_dry_run(
        fixture_ref="basic-pr",
        reviewer_config_path=str(optional_config),
        live_llm_settings={
            "provider": "openai",
            "model": "gpt-review",
            "max_attempts": 2,
            "max_live_calls": 2,
        },
        live_llm_transport=FakeLiveLLMProviderTransport(
            [
                LiveLLMProviderError(ProviderFailureReasonCode.TIMEOUT, "timeout"),
                LiveLLMProviderResponse(_provider_output(), request_id="req-ok"),
            ]
        ),
        live_llm_opt_in_source="test:explicit-live-opt-in",
    )

    assert [item["status"] for item in result.json_data["reviewer_results"]] == ["failed", "completed"]
    assert result.json_data["partial_review"] == {
        "has_partial_review": False,
        "failed_optional_reviewers": [],
    }


def test_live_malformed_json_fails_without_repair_or_second_call() -> None:
    package, run_key, _ = _package_and_key()
    approved = evaluate_live_llm_policy(package, _policy_input(package, run_key), ledger=LiveLLMBudgetLedger())
    transport = FakeLiveLLMProviderTransport([LiveLLMProviderResponse('{"items": [', request_id="req-bad")])

    result = execute_live_llm_reviewer_attempt(
        policy_result=approved,
        package=package,
        run_key=run_key,
        current_ledger=approved.ledger,
        transport=transport,
    )

    assert result.status == ReviewerRunStatusValue.FAILED
    assert result.repair_record is None
    assert result.raw_output is None
    assert result.normalization_errors[0].repairable is False
    assert len(transport.calls) == 1


def test_live_evidence_redacts_provider_model_and_malformed_response_status() -> None:
    package, run_key, _ = _package_and_key()
    secret_policy = LiveLLMPolicyInput(
        reviewer_run_key=run_key,
        live_llm_enabled=True,
        live_llm_opt_in_source="test:explicit-live-opt-in",
        provider=f"openai-{SECRET}",
        model=f"model-{SECRET}",
    )
    approved = evaluate_live_llm_policy(package, secret_policy, ledger=LiveLLMBudgetLedger())
    transport = FakeLiveLLMProviderTransport([LiveLLMProviderResponse(f'{{"token":"{SECRET}"', request_id="req-bad")])

    result = execute_live_llm_reviewer_attempt(
        policy_result=approved,
        package=package,
        run_key=run_key,
        current_ledger=approved.ledger,
        transport=transport,
    )

    evidence = result.live_llm_evidence.to_ordered_dict()
    serialized = json.dumps(evidence, sort_keys=True)
    assert SECRET not in serialized
    assert evidence["response_redaction_status"]["redacted"] is True


def test_live_llm_module_import_boundary() -> None:
    imports = _imports(Path("src/reviewgraph/llm.py"))
    forbidden_roots = {"github", "httpx", "openai", "requests", "socket", "subprocess", "urllib"}
    forbidden_reviewgraph_modules = {
        "reviewgraph.approval",
        "reviewgraph.finalization",
        "reviewgraph.github",
        "reviewgraph.posting",
        "reviewgraph.writer",
    }

    assert not ({name.split(".", 1)[0] for name in imports} & forbidden_roots)
    assert not (imports & forbidden_reviewgraph_modules)


def test_default_cli_import_does_not_load_live_transport_modules() -> None:
    script = """
import json
import sys
import reviewgraph.cli
print(json.dumps(sorted(
    name for name in sys.modules
    if name in {'reviewgraph.llm', 'reviewgraph.llm_http'}
    or name.startswith(('reviewgraph.llm.', 'reviewgraph.llm_http.'))
)))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "src"},
    )

    assert json.loads(completed.stdout) == []


def test_live_llm_marker_is_registered_and_skipped_by_conftest() -> None:
    pyproject = Path("pyproject.toml").read_text()
    conftest = Path("tests/conftest.py").read_text()

    assert "live_llm:" in pyproject
    assert "REVIEWGRAPH_LIVE_LLM" in conftest


def test_live_llm_smoke_prereq_artifact_blocks_without_prereqs() -> None:
    artifact = live_llm_smoke_prerequisite_artifact({"REVIEWGRAPH_LIVE_LLM": "1"})

    assert artifact == {
        "status": "blocked",
        "reason_code": "missing_live_llm_smoke_prerequisites",
        "missing": [
        "REVIEWGRAPH_LIVE_LLM_PROVIDER",
        "REVIEWGRAPH_LIVE_LLM_MODEL",
        "REVIEWGRAPH_LIVE_LLM_API_KEY or OPENAI_API_KEY",
        ],
        "provider": None,
        "model": None,
        "api_key_present": False,
        "base_url_present": False,
    }


@pytest.mark.live_llm
def test_opt_in_live_llm_smoke_marker_is_reserved_for_real_provider_execution() -> None:
    artifact = live_llm_smoke_prerequisite_artifact(os.environ)

    if artifact["status"] == "blocked":
        assert artifact["reason_code"] == "missing_live_llm_smoke_prerequisites"
        assert artifact["missing"]
        pytest.skip(f"missing live LLM smoke prerequisites: {', '.join(artifact['missing'])}")

    module = importlib.import_module("reviewgraph.llm_http")
    transport = module.transport_from_environment(provider=os.environ.get("REVIEWGRAPH_LIVE_LLM_PROVIDER"))
    response = transport(
        LiveLLMProviderRequest(
            provider=os.environ["REVIEWGRAPH_LIVE_LLM_PROVIDER"],
            model=os.environ["REVIEWGRAPH_LIVE_LLM_MODEL"],
            reviewer="live-smoke",
            target_hash="sha256:live-smoke",
            request_text='Return exactly this JSON object and no other text: {"items":[]}',
            request_hash="sha256:live-smoke-request",
            timeout_seconds=30,
            attempt=1,
            run_key_stable="live-smoke",
        )
    )

    assert json.loads(response.text.strip()) == {"items": []}


def _single_reviewer_config(
    tmp_path: Path,
    *,
    required: bool,
    include_model: bool = True,
    name: str = "reviewers.json",
) -> Path:
    agent: dict[str, object] = {
        "stages": ["initial_triage"],
        "triggers": {"always": True},
        "required": required,
        "context": "diff-plus-comments",
        "capabilities": ["diff_context"],
    }
    if include_model:
        agent["model"] = "gpt-review"
    config_path = tmp_path / name
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "correctness": agent,
                }
            }
        )
    )
    return config_path


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports
