import ast
import inspect
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from reviewgraph.config import parse_reviewer_config
from reviewgraph.context_budget import ContextBudget, apply_input_context_budget
from reviewgraph.fixtures import load_fixture_pr
from reviewgraph.hashing import canonical_json_hash
from reviewgraph.llm_policy import (
    LiveLLMBudgetLedger,
    LiveLLMPolicyInput,
    evaluate_live_llm_policy,
    live_llm_package_fingerprint,
)
from reviewgraph.memory import build_conversation_memory
from reviewgraph.models import (
    ReviewerRunKey,
    ReviewerRunStatusValue,
    ReviewStage,
    SelectedReviewer,
)
from reviewgraph.reviewer_context import ReviewerContextPackage, build_reviewer_context_package
from reviewgraph.reviewer_runs import make_reviewer_run_key
from reviewgraph.reviewers import (
    FakeReviewerAdapter,
    ReviewerAdapterBoundaryError,
    execute_fake_reviewer,
    execute_live_policy_reviewer_stub,
    validate_live_policy_adapter_input,
)


def _package_and_key(
    *,
    reviewer_name: str = "correctness",
    active_stage: str = "initial_triage",
    capabilities: tuple[str, ...] = ("diff_context",),
):
    fixture = load_fixture_pr("basic-pr")
    memory = build_conversation_memory(fixture.pr)
    budgeted_context = apply_input_context_budget(
        pr=fixture.pr,
        memory=memory,
        limits=ContextBudget(
            max_changed_files=10,
            max_patch_bytes=1_000_000,
            max_memory_bytes=1_000_000,
            max_reviewers=10,
            max_live_calls=1,
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
                    "capabilities": list(capabilities),
                }
            }
        }
    )
    reviewer = SelectedReviewer(
        name=reviewer_name,
        stage="initial_triage",
        reasons=("initial_triage triggers.always=true",),
    )
    package = build_reviewer_context_package(
        active_stage=active_stage,
        reviewer=reviewer,
        reviewer_config=config.agents[reviewer_name],
        budgeted_context=budgeted_context,
    )
    state = type(
        "ReviewStateLike",
        (),
        {
            "review_target": fixture.review_target,
            "config_hash": canonical_json_hash({"agents": [reviewer_name]}),
        },
    )()
    run_key = make_reviewer_run_key(state, reviewer)
    return package, run_key


def _registry(reviewer: str = "correctness") -> dict[tuple[str, str, str], object]:
    return {
        (
            "basic-pr",
            reviewer,
            "initial_triage",
        ): {"reviewer": reviewer, "stage": "initial_triage", "items": []}
    }


def test_fake_raw_source_and_structured_execute_boundary_signatures_are_narrow() -> None:
    assert tuple(inspect.signature(FakeReviewerAdapter.run).parameters) == ("self", "package")
    assert tuple(inspect.signature(execute_fake_reviewer).parameters) == (
        "adapter",
        "package",
        "run_key",
    )
    assert inspect.signature(execute_fake_reviewer).parameters["adapter"].kind is inspect.Parameter.KEYWORD_ONLY


def test_execute_fake_reviewer_returns_structured_reviewer_result() -> None:
    package, run_key = _package_and_key()

    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=_registry()),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.COMPLETED
    assert result.run_key == run_key
    assert isinstance(result.raw_output, dict)


def test_fake_boundary_rejects_non_context_package_before_registry_lookup() -> None:
    package, run_key = _package_and_key()
    adapter = FakeReviewerAdapter(fixture_id="missing-fixture", registry={})

    with pytest.raises(ReviewerAdapterBoundaryError, match="ReviewerContextPackage"):
        execute_fake_reviewer(
            adapter=adapter,
            package=object(),  # type: ignore[arg-type]
            run_key=run_key,
        )

    with pytest.raises(ReviewerAdapterBoundaryError, match="ReviewerContextPackage"):
        adapter.run(object())  # type: ignore[arg-type]

    assert isinstance(package, ReviewerContextPackage)


@pytest.mark.parametrize(
    "run_key",
    [
        ReviewerRunKey(
            target_hash="sha256:wrong",
            config_hash="config",
            stage=ReviewStage.INITIAL_TRIAGE,
            reviewer="correctness",
        ),
        ReviewerRunKey(
            target_hash="placeholder",
            config_hash="config",
            stage=ReviewStage.LOGIC_REVIEW,
            reviewer="correctness",
        ),
        ReviewerRunKey(
            target_hash="placeholder",
            config_hash="config",
            stage=ReviewStage.INITIAL_TRIAGE,
            reviewer="other",
        ),
    ],
)
def test_fake_boundary_rejects_mismatched_run_key_before_registry_lookup(run_key: ReviewerRunKey) -> None:
    package, valid_key = _package_and_key()
    if run_key.target_hash == "placeholder":
        run_key = replace(run_key, target_hash=valid_key.target_hash)

    with pytest.raises(ReviewerAdapterBoundaryError, match="run key"):
        execute_fake_reviewer(
            adapter=FakeReviewerAdapter(fixture_id="missing-fixture", registry={}),
            package=package,
            run_key=run_key,
        )


def test_fake_boundary_rejects_active_stage_mismatch_before_registry_lookup() -> None:
    package, run_key = _package_and_key(active_stage="logic_review")

    with pytest.raises(ReviewerAdapterBoundaryError, match="active stage"):
        execute_fake_reviewer(
            adapter=FakeReviewerAdapter(fixture_id="missing-fixture", registry={}),
            package=package,
            run_key=run_key,
        )


def test_fake_boundary_rejects_invalid_capability_policy_before_execution() -> None:
    package, run_key = _package_and_key()
    mismatched_package = replace(
        package,
        capability_policy=replace(package.capability_policy, capabilities=("github_write",)),
    )
    live_enabled_package = replace(
        package,
        capability_policy=replace(package.capability_policy, live_provider_calls_available=True),
    )

    for invalid_package in (mismatched_package, live_enabled_package):
        with pytest.raises(ReviewerAdapterBoundaryError, match="capabilit|provider"):
            execute_fake_reviewer(
                adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=_registry()),
                package=invalid_package,
                run_key=run_key,
            )


def test_fake_boundary_allows_none_capability() -> None:
    package, run_key = _package_and_key(capabilities=("none",))
    result = execute_fake_reviewer(
        adapter=FakeReviewerAdapter(fixture_id="basic-pr", registry=_registry()),
        package=package,
        run_key=run_key,
    )

    assert result.status == ReviewerRunStatusValue.COMPLETED
    assert package.capability_policy.capabilities == ("none",)


def test_live_policy_adapter_boundary_requires_approved_policy_result_and_returns_reviewer_result() -> None:
    package, run_key = _package_and_key()
    policy_input = LiveLLMPolicyInput(
        reviewer_run_key=run_key,
        live_llm_enabled=True,
        live_llm_opt_in_source="cli:--live-llm",
        provider="openai",
        model="gpt-review",
    )
    approved = evaluate_live_llm_policy(package, policy_input, ledger=LiveLLMBudgetLedger())
    bad_capability_package = replace(
        package,
        capability_policy=replace(package.capability_policy, live_provider_calls_available=True),
    )
    bad_capability_policy = evaluate_live_llm_policy(
        bad_capability_package,
        policy_input,
        ledger=LiveLLMBudgetLedger(),
    )
    blocked = evaluate_live_llm_policy(
        package,
        replace(policy_input, live_llm_enabled=False, live_llm_opt_in_source=None),
        ledger=LiveLLMBudgetLedger(),
    )

    assert bad_capability_policy.status == "blocked"
    assert bad_capability_policy.reason_code == "reviewer_adapter_boundary_failed"
    assert bad_capability_policy.execution_plan is None
    assert bad_capability_policy.ledger.reserved_live_calls == 0
    assert validate_live_policy_adapter_input(
        policy_result=approved,
        package=package,
        run_key=run_key,
        current_ledger=approved.ledger,
    ) is approved
    live_result = execute_live_policy_reviewer_stub(
        policy_result=approved,
        package=package,
        run_key=run_key,
        current_ledger=approved.ledger,
    )
    assert live_result.status == ReviewerRunStatusValue.FAILED
    assert live_result.run_key == run_key
    assert live_result.errors == ("live reviewer provider execution is not implemented in AUR-232",)
    with pytest.raises(ReviewerAdapterBoundaryError, match="approved"):
        validate_live_policy_adapter_input(
            policy_result=blocked,
            package=package,
            run_key=run_key,
            current_ledger=approved.ledger,
        )
    with pytest.raises(ReviewerAdapterBoundaryError, match="approved"):
        execute_live_policy_reviewer_stub(
            policy_result=blocked,
            package=package,
            run_key=run_key,
            current_ledger=approved.ledger,
        )
    with pytest.raises(ReviewerAdapterBoundaryError, match="provider"):
        execute_live_policy_reviewer_stub(
            policy_result=approved,
            package=bad_capability_package,
            run_key=run_key,
            current_ledger=approved.ledger,
        )
    with pytest.raises(ReviewerAdapterBoundaryError, match="run key"):
        validate_live_policy_adapter_input(
            policy_result=approved,
            package=package,
            run_key=replace(run_key, reviewer="other"),
            current_ledger=approved.ledger,
        )
    with pytest.raises(ReviewerAdapterBoundaryError, match="run key"):
        execute_live_policy_reviewer_stub(
            policy_result=approved,
            package=package,
            run_key=replace(run_key, reviewer="other"),
            current_ledger=approved.ledger,
        )


def test_live_policy_adapter_boundary_rejects_stale_policy_result_from_different_package() -> None:
    package, run_key = _package_and_key()
    stale_package = replace(
        package,
        changed_files=(
            replace(
                package.changed_files[0],
                patch=package.changed_files[0].patch + "\n+changed after policy approval",
            ),
        ),
    )
    policy_input = LiveLLMPolicyInput(
        reviewer_run_key=run_key,
        live_llm_enabled=True,
        live_llm_opt_in_source="cli:--live-llm",
        provider="openai",
        model="gpt-review",
    )
    approved = evaluate_live_llm_policy(stale_package, policy_input, ledger=LiveLLMBudgetLedger())

    with pytest.raises(ReviewerAdapterBoundaryError, match="does not match package"):
        validate_live_policy_adapter_input(
            policy_result=approved,
            package=package,
            run_key=run_key,
            current_ledger=approved.ledger,
        )
    with pytest.raises(ReviewerAdapterBoundaryError, match="does not match package"):
        execute_live_policy_reviewer_stub(
            policy_result=approved,
            package=package,
            run_key=run_key,
            current_ledger=approved.ledger,
        )


def test_live_policy_adapter_boundary_rejects_stale_non_prompt_package_policy_result() -> None:
    package, run_key = _package_and_key()
    stale_package = replace(
        package,
        context_budget=replace(package.context_budget, max_live_calls=0),
    )
    policy_input = LiveLLMPolicyInput(
        reviewer_run_key=run_key,
        live_llm_enabled=True,
        live_llm_opt_in_source="cli:--live-llm",
        provider="openai",
        model="gpt-review",
    )
    approved = evaluate_live_llm_policy(package, policy_input, ledger=LiveLLMBudgetLedger())

    with pytest.raises(ReviewerAdapterBoundaryError, match="does not match package"):
        validate_live_policy_adapter_input(
            policy_result=approved,
            package=stale_package,
            run_key=run_key,
            current_ledger=approved.ledger,
        )


def test_live_policy_adapter_boundary_rejects_stale_live_call_ledger() -> None:
    first_package, first_run_key = _package_and_key(reviewer_name="correctness")
    second_package, second_run_key = _package_and_key(reviewer_name="quality")
    first_policy = LiveLLMPolicyInput(
        reviewer_run_key=first_run_key,
        live_llm_enabled=True,
        live_llm_opt_in_source="cli:--live-llm",
        provider="openai",
        model="gpt-review",
    )
    second_policy = LiveLLMPolicyInput(
        reviewer_run_key=second_run_key,
        live_llm_enabled=True,
        live_llm_opt_in_source="cli:--live-llm",
        provider="openai",
        model="gpt-review",
    )
    first = evaluate_live_llm_policy(first_package, first_policy, ledger=LiveLLMBudgetLedger())
    stale_second = evaluate_live_llm_policy(second_package, second_policy, ledger=LiveLLMBudgetLedger())
    current_second = evaluate_live_llm_policy(second_package, second_policy, ledger=first.ledger)

    assert stale_second.status == "approved"
    assert current_second.status == "blocked"
    assert current_second.reason_code == "live_call_budget_exceeded"
    with pytest.raises(ReviewerAdapterBoundaryError, match="ledger"):
        validate_live_policy_adapter_input(
            policy_result=stale_second,
            package=second_package,
            run_key=second_run_key,
            current_ledger=first.ledger,
        )


def test_live_policy_adapter_boundary_rejects_stale_same_run_ledger_reservation() -> None:
    package, run_key = _package_and_key()
    policy_input = LiveLLMPolicyInput(
        reviewer_run_key=run_key,
        live_llm_enabled=True,
        live_llm_opt_in_source="cli:--live-llm",
        provider="openai",
        model="gpt-review",
    )
    approved = evaluate_live_llm_policy(package, policy_input, ledger=LiveLLMBudgetLedger())
    assert approved.execution_plan is not None
    stale_reservation = replace(
        approved.ledger.reservations[0],
        package_fingerprint="sha256:stale",
    )
    stale_ledger = LiveLLMBudgetLedger(reservations=(stale_reservation,))

    with pytest.raises(ReviewerAdapterBoundaryError, match="ledger reservation"):
        validate_live_policy_adapter_input(
            policy_result=approved,
            package=package,
            run_key=run_key,
            current_ledger=stale_ledger,
        )


def test_live_package_fingerprint_covers_full_context_budget_state() -> None:
    package, _ = _package_and_key()
    changed_budget = replace(
        package.context_budget,
        retained_live_call_reviewer_ids=("correctness:initial_triage",),
    )
    changed_package = replace(package, context_budget=changed_budget)

    assert live_llm_package_fingerprint(package) != live_llm_package_fingerprint(changed_package)


def test_reviewer_adapter_module_imports_no_side_effect_or_provider_boundaries() -> None:
    forbidden_roots = {
        "github",
        "httpx",
        "openai",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    forbidden_reviewgraph_modules = {
        "reviewgraph.approval",
        "reviewgraph.finalization",
        "reviewgraph.github",
        "reviewgraph.posting",
        "reviewgraph.writer",
    }
    for path in (
        Path("src/reviewgraph/reviewer_boundaries.py"),
        Path("src/reviewgraph/reviewers.py"),
        Path("src/reviewgraph/reviewer_context.py"),
        Path("src/reviewgraph/llm_policy.py"),
    ):
        imports = _imports(path)
        assert not ({name.split(".", 1)[0] for name in imports} & forbidden_roots)
        assert not (imports & forbidden_reviewgraph_modules)


def test_reviewer_adapter_callables_do_not_accept_handle_like_parameters() -> None:
    forbidden_fragments = {
        "approval",
        "client",
        "finalization",
        "github",
        "payload",
        "process",
        "provider_client",
        "session",
        "transport",
        "writer",
    }
    for function in (
        FakeReviewerAdapter.run,
        execute_fake_reviewer,
        execute_live_policy_reviewer_stub,
        validate_live_policy_adapter_input,
    ):
        parameter_names = set(inspect.signature(function).parameters)
        assert not any(
            fragment in name.casefold()
            for name in parameter_names
            for fragment in forbidden_fragments
        )


def test_reviewer_adapter_import_does_not_transitively_load_side_effect_modules() -> None:
    script = """
import json
import sys
import reviewgraph.reviewers
forbidden = sorted(
    name for name in sys.modules
    if name.startswith(('reviewgraph.approval', 'reviewgraph.finalization', 'reviewgraph.github', 'reviewgraph.posting', 'reviewgraph.writer'))
    or name.split('.', 1)[0] in {'github', 'httpx', 'openai', 'requests', 'socket', 'subprocess', 'urllib'}
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


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports
