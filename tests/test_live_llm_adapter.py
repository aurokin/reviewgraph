import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest

from reviewgraph.config import parse_reviewer_config
from reviewgraph.context_budget import ContextBudget, apply_input_context_budget
from reviewgraph.fixtures import load_fixture_pr
from reviewgraph.hashing import canonical_json_hash
from reviewgraph.llm import (
    FakeLiveLLMProviderTransport,
    LiveLLMProviderError,
    LiveLLMProviderResponse,
    execute_live_llm_reviewer_attempt,
    run_live_llm_reviewer_with_retries,
)
from reviewgraph.llm_policy import LiveLLMBudgetLedger, LiveLLMPolicyInput, ProviderFailureReasonCode, evaluate_live_llm_policy
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
    assert "default CLI review remains fake-provider-free" in capsys.readouterr().err


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


def test_live_llm_marker_is_registered_and_skipped_by_conftest() -> None:
    pyproject = Path("pyproject.toml").read_text()
    conftest = Path("tests/conftest.py").read_text()

    assert "live_llm:" in pyproject
    assert "REVIEWGRAPH_LIVE_LLM" in conftest


@pytest.mark.live_llm
def test_opt_in_live_llm_smoke_contract_blocks_without_prereqs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REVIEWGRAPH_LIVE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("REVIEWGRAPH_LIVE_LLM_MODEL", raising=False)
    monkeypatch.delenv("REVIEWGRAPH_LIVE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    required = (
        "REVIEWGRAPH_LIVE_LLM_PROVIDER",
        "REVIEWGRAPH_LIVE_LLM_MODEL",
        "REVIEWGRAPH_LIVE_LLM_API_KEY or OPENAI_API_KEY",
    )
    assert required == (
        "REVIEWGRAPH_LIVE_LLM_PROVIDER",
        "REVIEWGRAPH_LIVE_LLM_MODEL",
        "REVIEWGRAPH_LIVE_LLM_API_KEY or OPENAI_API_KEY",
    )


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports
