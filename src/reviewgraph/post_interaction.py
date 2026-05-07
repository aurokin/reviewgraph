from __future__ import annotations

from dataclasses import dataclass

from reviewgraph.models import GateStatus, PostInteractionGateResult, RunMode


NON_INTERACTIVE_POST_MODE_ERROR_CODE = "non_interactive_post_mode"
NON_INTERACTIVE_POSTING_REQUIRES_FUTURE_POLICY = "non_interactive_posting_requires_future_policy"


@dataclass(frozen=True)
class PostModeInteractionContext:
    run_mode: RunMode
    interactive: bool
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.run_mode, RunMode):
            raise ValueError("post interaction run_mode must be a RunMode")
        if not isinstance(self.interactive, bool):
            raise ValueError("post interaction interactive must be bool")
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("post interaction reason is required")


def evaluate_post_mode_interaction_gate(
    context: PostModeInteractionContext,
) -> PostInteractionGateResult:
    if context.run_mode != RunMode.POST:
        raise ValueError("post interaction gate only runs for post mode")
    if context.interactive:
        return PostInteractionGateResult(status=GateStatus.PASS, interactive=True)
    return PostInteractionGateResult(
        status=GateStatus.FAIL,
        interactive=False,
        reason=f"{NON_INTERACTIVE_POSTING_REQUIRES_FUTURE_POLICY}:{context.reason}",
    )
