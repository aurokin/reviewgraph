import ast
import json
from dataclasses import replace
from pathlib import Path

from reviewgraph.context_budget import ContextBudget, apply_input_context_budget
from reviewgraph.fixtures import load_fixture_pr
from reviewgraph.llm_policy import (
    LiveLLMBudgetLedger,
    LiveLLMPolicyInput,
    ProviderFailureReasonCode,
    evaluate_live_llm_policy,
    summarize_provider_failure,
)
from reviewgraph.memory import build_conversation_memory
from reviewgraph.models import (
    MemoryReference,
    ReviewerAgentConfig,
    ReviewerRunKey,
    ReviewStage,
    ReviewerTriggers,
    SelectedReviewer,
)
from reviewgraph.reviewer_context import build_reviewer_context_package


SECRET = "sk_live_1234567890abcdef"


def _agent_config(*, model: str | None = "gpt-review") -> ReviewerAgentConfig:
    return ReviewerAgentConfig(
        name="logic",
        description="Reviews logic.",
        stages=(ReviewStage.INITIAL_TRIAGE,),
        triggers=ReviewerTriggers(always=True),
        required=True,
        verdict_power="request_changes",
        capabilities=("diff_context",),
        model=model,
        context="diff-plus-comments",
        tools=("future-search",),
    )


def _package(
    *,
    max_live_calls: int = 1,
    model: str | None = "gpt-review",
    reviewer_name: str = "logic",
):
    fixture = load_fixture_pr("untrusted-comment-injection")
    secret_file = replace(
        fixture.pr.changed_files[0],
        path="src/auth/secret_redirects.py",
        patch=f'@@ -1 +1 @@\n+api_key = "{SECRET}"\n',
    )
    pr = replace(fixture.pr, changed_files=(secret_file,))
    memory = build_conversation_memory(pr)
    memory = replace(
        memory,
        entries=(
            MemoryReference(
                id="trusted-secret-comment",
                trust_label="trusted",
                resolved_status="unresolved",
                source_type="issue_comment",
                body=f"Reviewer context contains token={SECRET}",
                author="octocat",
                author_type="User",
                actionable=True,
                source_provider="github",
                source_id="issue-comment-1",
            ),
        )
        + memory.entries,
    )
    budgeted = apply_input_context_budget(
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
    return build_reviewer_context_package(
        active_stage="initial_triage",
        reviewer=SelectedReviewer(
            name=reviewer_name,
            stage="initial_triage",
            reasons=("initial_triage triggers.always=true",),
        ),
        reviewer_config=_agent_config(model=model),
        budgeted_context=budgeted,
    )


def _run_key(package, *, attempt: int = 1, retry_of: str | None = None) -> ReviewerRunKey:
    return ReviewerRunKey(
        target_hash=package.review_target.target_hash(),
        config_hash="config-hash",
        stage=ReviewStage.INITIAL_TRIAGE,
        reviewer=package.reviewer.name,
        attempt=attempt,
        retry_of=retry_of,
    )


def _policy(
    package,
    *,
    live_llm_enabled: bool = True,
    provider: str | None = "openai",
    model: str | None = "gpt-review",
    raw_provider_submission_enabled: bool = False,
    raw_provider_submission_approved: bool = False,
    raw_trace_persistence_enabled: bool = False,
    raw_trace_persistence_approved: bool = False,
    run_key: ReviewerRunKey | None = None,
) -> LiveLLMPolicyInput:
    return LiveLLMPolicyInput(
        reviewer_run_key=run_key or _run_key(package),
        live_llm_enabled=live_llm_enabled,
        live_llm_opt_in_source="cli:--live-llm" if live_llm_enabled else None,
        provider=provider,
        model=model,
        raw_provider_submission_enabled=raw_provider_submission_enabled,
        raw_provider_submission_approved=raw_provider_submission_approved,
        raw_provider_submission_opt_in_source=(
            "tty-confirmation" if raw_provider_submission_approved else None
        ),
        raw_trace_persistence_enabled=raw_trace_persistence_enabled,
        raw_trace_persistence_approved=raw_trace_persistence_approved,
        raw_trace_persistence_opt_in_source=("tty-confirmation" if raw_trace_persistence_approved else None),
    )


def test_live_llm_policy_requires_run_level_opt_in_provider_and_model() -> None:
    package = _package(model="gpt-review")

    missing_opt_in = evaluate_live_llm_policy(
        package,
        _policy(package, live_llm_enabled=False),
        ledger=LiveLLMBudgetLedger(),
    )
    config_model_only = evaluate_live_llm_policy(
        package,
        _policy(package, live_llm_enabled=False, provider="openai"),
        ledger=LiveLLMBudgetLedger(),
    )
    missing_provider = evaluate_live_llm_policy(
        package,
        _policy(package, provider=None),
        ledger=LiveLLMBudgetLedger(),
    )
    missing_model = evaluate_live_llm_policy(
        package,
        _policy(package, provider="openai", model=None),
        ledger=LiveLLMBudgetLedger(),
    )
    assert missing_opt_in.status == "blocked"
    assert missing_opt_in.reason_code == "missing_live_opt_in"
    assert config_model_only.reason_code == "missing_live_opt_in"
    assert missing_provider.reason_code == "missing_provider"
    assert missing_model.reason_code == "missing_model"
    assert missing_opt_in.execution_plan is None


def test_live_llm_policy_requires_live_opt_in_source() -> None:
    package = _package()
    policy = LiveLLMPolicyInput(
        reviewer_run_key=_run_key(package),
        live_llm_enabled=True,
        live_llm_opt_in_source=None,
        provider="openai",
        model="gpt-review",
    )

    result = evaluate_live_llm_policy(package, policy, ledger=LiveLLMBudgetLedger())

    assert result.status == "blocked"
    assert result.reason_code == "missing_live_opt_in"


def test_policy_builds_redacted_execution_plan_and_default_safe_audit_record() -> None:
    package = _package(max_live_calls=1)
    result = evaluate_live_llm_policy(package, _policy(package), ledger=LiveLLMBudgetLedger())

    assert result.status == "approved"
    assert result.reason_code is None
    assert result.execution_plan is not None
    assert result.execution_plan.provider == "openai"
    assert result.execution_plan.model == "gpt-review"
    assert result.execution_plan.reviewer == "logic"
    assert result.execution_plan.live_call_budget_cost == 1
    assert result.execution_plan.budget_before == 0
    assert result.execution_plan.budget_after == 1
    assert SECRET not in result.execution_plan.request_text
    assert "[REDACTED]" in result.execution_plan.request_text
    assert result.ledger.reserved_live_calls == 1

    audit = result.to_audit_dict()
    serialized_audit = json.dumps(audit, sort_keys=True)
    assert "request_text" not in audit
    assert SECRET not in serialized_audit
    assert "src/auth/secret_redirects.py" in audit["context"]["retained_file_paths"]
    assert "trusted-secret-comment" in audit["context"]["retained_memory_ids"]
    assert audit["provider"] == "openai"
    assert audit["model"] == "gpt-review"
    assert audit["reviewer"] == "logic"
    assert audit["target"] == package.review_target.to_ordered_dict()
    assert audit["target_hash"] == package.review_target.target_hash()
    assert audit["context"]["context_policy"] == "diff-plus-comments"
    assert audit["redaction_status"]["redacted"] is True
    assert audit["request_hash"].startswith("sha256:")
    assert audit["request_byte_count"] == len(result.execution_plan.request_text.encode("utf-8"))
    assert audit["raw_provider_submission"]["enabled"] is False
    assert audit["raw_trace_persistence"]["enabled"] is False


def test_policy_uses_explicit_model_on_execution_plan_and_preview() -> None:
    package = _package(max_live_calls=1, model="config-model")
    result = evaluate_live_llm_policy(
        package,
        _policy(package, model="policy-model"),
        ledger=LiveLLMBudgetLedger(),
    )

    assert result.execution_plan is not None
    assert result.execution_plan.model == "policy-model"
    assert result.execution_plan.preview.model == "policy-model"
    assert result.to_audit_dict()["model"] == "policy-model"


def test_provider_model_metadata_is_redacted_on_persisted_surfaces() -> None:
    package = _package(max_live_calls=1)
    result = evaluate_live_llm_policy(
        package,
        _policy(package, provider=f"openai-{SECRET}", model=f"gpt-{SECRET}"),
        ledger=LiveLLMBudgetLedger(),
    )

    serialized_audit = json.dumps(result.to_audit_dict(), sort_keys=True)
    serialized_ledger = json.dumps(result.ledger.to_ordered_dict(), sort_keys=True)
    assert result.execution_plan is not None
    assert SECRET in result.execution_plan.provider
    assert SECRET in result.execution_plan.model
    assert SECRET not in serialized_audit
    assert SECRET not in serialized_ledger
    assert "[REDACTED]" in serialized_audit
    assert "[REDACTED]" in serialized_ledger


def test_default_audit_record_does_not_retain_request_text_on_dataclass() -> None:
    package = _package(max_live_calls=1)
    result = evaluate_live_llm_policy(
        package,
        _policy(
            package,
            raw_provider_submission_enabled=True,
            raw_provider_submission_approved=True,
            raw_trace_persistence_enabled=False,
        ),
        ledger=LiveLLMBudgetLedger(),
    )

    assert result.execution_plan is not None
    assert SECRET in result.execution_plan.request_text
    assert result.audit_record.trace_request_text is None
    assert "request_text" not in result.to_audit_dict(include_request_text=True)


def test_audit_metadata_is_redacted_by_default() -> None:
    package = _package(max_live_calls=1)
    package = replace(
        package,
        context_budget=replace(
            package.context_budget,
            retained_file_paths=(f"src/{SECRET}.py",),
            retained_memory_ids=(f"memory-{SECRET}",),
        ),
    )
    result = evaluate_live_llm_policy(package, _policy(package), ledger=LiveLLMBudgetLedger())

    serialized_audit = json.dumps(result.to_audit_dict(), sort_keys=True)
    assert SECRET not in serialized_audit
    assert "[REDACTED]" in serialized_audit


def test_raw_trace_opt_in_can_serialize_request_text_only_when_explicitly_requested() -> None:
    package = _package()
    result = evaluate_live_llm_policy(
        package,
        _policy(package, raw_trace_persistence_enabled=True, raw_trace_persistence_approved=True),
        ledger=LiveLLMBudgetLedger(),
    )

    assert result.execution_plan is not None
    assert result.audit_record.trace_request_text == result.execution_plan.request_text
    assert "request_text" not in result.to_audit_dict()
    assert result.to_audit_dict(include_request_text=True)["request_text"] == result.execution_plan.request_text


def test_raw_provider_and_raw_trace_modes_require_separate_approval_proof() -> None:
    package = _package()

    raw_provider = evaluate_live_llm_policy(
        package,
        _policy(package, raw_provider_submission_enabled=True),
        ledger=LiveLLMBudgetLedger(),
    )
    raw_trace = evaluate_live_llm_policy(
        package,
        _policy(package, raw_trace_persistence_enabled=True),
        ledger=LiveLLMBudgetLedger(),
    )
    raw_provider_missing_source = evaluate_live_llm_policy(
        package,
        LiveLLMPolicyInput(
            reviewer_run_key=_run_key(package),
            live_llm_enabled=True,
            live_llm_opt_in_source="cli:--live-llm",
            provider="openai",
            model="gpt-review",
            raw_provider_submission_enabled=True,
            raw_provider_submission_approved=True,
            raw_provider_submission_opt_in_source=None,
        ),
        ledger=LiveLLMBudgetLedger(),
    )
    raw_trace_missing_source = evaluate_live_llm_policy(
        package,
        LiveLLMPolicyInput(
            reviewer_run_key=_run_key(package),
            live_llm_enabled=True,
            live_llm_opt_in_source="cli:--live-llm",
            provider="openai",
            model="gpt-review",
            raw_trace_persistence_enabled=True,
            raw_trace_persistence_approved=True,
            raw_trace_persistence_opt_in_source=None,
        ),
        ledger=LiveLLMBudgetLedger(),
    )
    approved = evaluate_live_llm_policy(
        package,
        _policy(
            package,
            raw_provider_submission_enabled=True,
            raw_provider_submission_approved=True,
            raw_trace_persistence_enabled=True,
            raw_trace_persistence_approved=True,
        ),
        ledger=LiveLLMBudgetLedger(),
    )

    assert raw_provider.reason_code == "raw_provider_not_approved"
    assert raw_trace.reason_code == "raw_trace_not_approved"
    assert raw_provider_missing_source.reason_code == "raw_provider_not_approved"
    assert raw_trace_missing_source.reason_code == "raw_trace_not_approved"
    assert approved.status == "approved"
    assert approved.execution_plan is not None
    assert SECRET in approved.execution_plan.request_text
    audit = approved.to_audit_dict()
    assert "request_text" not in audit
    assert audit["raw_provider_submission"]["enabled"] is True
    assert audit["raw_provider_submission"]["approved"] is True
    assert audit["raw_provider_submission"]["opt_in_source"] == "tty-confirmation"
    assert audit["raw_trace_persistence"]["enabled"] is True
    assert audit["raw_trace_persistence"]["approved"] is True


def test_live_call_budget_ledger_blocks_caps_and_is_keyed_by_run_identity() -> None:
    first_package = _package(max_live_calls=1, reviewer_name="logic")
    second_package = _package(max_live_calls=1, reviewer_name="security")
    first = evaluate_live_llm_policy(
        first_package,
        _policy(first_package),
        ledger=LiveLLMBudgetLedger(),
    )
    assert first.status == "approved"
    assert first.ledger.reserved_live_calls == 1

    second = evaluate_live_llm_policy(
        second_package,
        _policy(second_package),
        ledger=first.ledger,
    )
    assert second.status == "blocked"
    assert second.reason_code == "live_call_budget_exceeded"
    assert second.execution_plan is None
    assert second.ledger.reserved_live_calls == 1

    duplicate = evaluate_live_llm_policy(
        first_package,
        _policy(first_package),
        ledger=first.ledger,
    )
    assert duplicate.status == "approved"
    assert duplicate.execution_plan is not None
    assert duplicate.execution_plan.reservation_status == "existing"
    assert duplicate.ledger.reserved_live_calls == 1

    conflict = evaluate_live_llm_policy(
        first_package,
        _policy(first_package, provider="anthropic"),
        ledger=first.ledger,
    )
    assert conflict.status == "blocked"
    assert conflict.reason_code == "live_call_reservation_conflict"


def test_policy_rejects_run_key_that_does_not_match_context_package() -> None:
    package = _package()
    wrong_target = ReviewerRunKey(
        target_hash="sha256:wrong",
        config_hash="config-hash",
        stage=ReviewStage.INITIAL_TRIAGE,
        reviewer=package.reviewer.name,
    )
    wrong_reviewer = ReviewerRunKey(
        target_hash=package.review_target.target_hash(),
        config_hash="config-hash",
        stage=ReviewStage.INITIAL_TRIAGE,
        reviewer="other-reviewer",
    )
    wrong_stage = ReviewerRunKey(
        target_hash=package.review_target.target_hash(),
        config_hash="config-hash",
        stage=ReviewStage.LOGIC_REVIEW,
        reviewer=package.reviewer.name,
    )
    wrong_active_stage_package = replace(package, active_stage="logic_review")

    for run_key in (wrong_target, wrong_reviewer, wrong_stage):
        result = evaluate_live_llm_policy(
            package,
            _policy(package, run_key=run_key),
            ledger=LiveLLMBudgetLedger(),
        )
        assert result.status == "blocked"
        assert result.reason_code == "reviewer_run_key_mismatch"

    active_stage_mismatch = evaluate_live_llm_policy(
        wrong_active_stage_package,
        _policy(package),
        ledger=LiveLLMBudgetLedger(),
    )
    assert active_stage_mismatch.status == "blocked"
    assert active_stage_mismatch.reason_code == "reviewer_run_key_mismatch"


def test_retry_run_key_consumes_fresh_live_call_budget() -> None:
    package = _package(max_live_calls=2)
    first = evaluate_live_llm_policy(package, _policy(package), ledger=LiveLLMBudgetLedger())
    assert first.status == "approved"

    retry_key = _run_key(package, attempt=2, retry_of=_run_key(package).stable_key())
    retry = evaluate_live_llm_policy(
        package,
        _policy(package, run_key=retry_key),
        ledger=first.ledger,
    )

    assert retry.status == "approved"
    assert retry.execution_plan is not None
    assert retry.execution_plan.reservation_status == "new"
    assert retry.execution_plan.budget_before == 1
    assert retry.execution_plan.budget_after == 2
    assert retry.ledger.reserved_live_calls == 2


def test_context_budget_zero_blocks_before_provider_execution_plan() -> None:
    package = _package(max_live_calls=0)
    result = evaluate_live_llm_policy(package, _policy(package), ledger=LiveLLMBudgetLedger())

    assert result.status == "blocked"
    assert result.reason_code == "live_call_budget_exceeded"
    assert result.execution_plan is None
    assert result.to_audit_dict()["budget"]["before"] == 0
    assert result.to_audit_dict()["budget"]["after"] == 0


def test_provider_failure_summary_is_typed_retryable_and_redacted() -> None:
    summary = summarize_provider_failure(
        ProviderFailureReasonCode.RATE_LIMITED,
        message=f"Authorization: bearer ghp_abcdefghijklmnopqrstuvwxyz0123456789 {SECRET}",
        request_id="req_123",
    )
    unsafe_request_id = summarize_provider_failure(
        ProviderFailureReasonCode.TIMEOUT,
        message="timeout",
        request_id=SECRET,
    )
    unknown = summarize_provider_failure(
        ProviderFailureReasonCode.UNKNOWN_PROVIDER_ERROR,
        message=f"Provider returned token={SECRET}",
    )
    retry_exhausted = summarize_provider_failure(
        ProviderFailureReasonCode.RETRY_EXHAUSTED,
        message="provider retries exhausted",
    )

    assert summary.reason_code == "rate_limited"
    assert summary.retryable is True
    assert summary.request_id == "req_123"
    assert unsafe_request_id.request_id is None
    assert SECRET not in summary.message
    assert "ghp_" not in summary.message
    assert summary.redaction_status.redacted is True
    assert unknown.retryable is False
    assert retry_exhausted.retryable is False


def test_llm_policy_has_no_provider_network_github_or_side_effect_imports() -> None:
    source = Path("src/reviewgraph/llm_policy.py").read_text()
    tree = ast.parse(source)
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    forbidden = {
        "github",
        "httpx",
        "openai",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    assert imported_roots.isdisjoint(forbidden)
    assert "posting" not in source
    assert "writer" not in source
    assert "approval" not in source
