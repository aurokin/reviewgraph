from pathlib import Path

import pytest

from reviewgraph.config import ConfigError, parse_reviewer_config, load_reviewer_config
from reviewgraph.fixtures import default_reviewer_config_path
from reviewgraph.models import ReviewStage, RiskLevel


def test_packaged_and_example_reviewer_configs_validate() -> None:
    packaged = load_reviewer_config(default_reviewer_config_path())
    example = load_reviewer_config(Path("examples/review_agents.example.yaml"))

    assert packaged.agents["correctness"].capabilities == ("diff_context",)
    assert ReviewStage.CLARIFICATION_REVIEW in example.agents["logic"].stages
    assert example.agents["logic"].triggers.risk_min == RiskLevel.MEDIUM


def test_missing_capabilities_default_to_diff_context() -> None:
    config = parse_reviewer_config(
        {
            "agents": {
                "correctness": {
                    "stages": ["initial_triage"],
                    "triggers": {"always": True},
                    "verdict_power": "comment",
                }
            }
        }
    )

    assert config.agents["correctness"].capabilities == ("diff_context",)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda data: data.update({"unknown": True}), "unsupported fields"),
        (lambda data: data["agents"]["correctness"].update({"unknown": True}), "unsupported fields"),
        (lambda data: data["agents"]["correctness"]["triggers"].update({"stages": ["logic_review"]}), "unsupported trigger"),
        (lambda data: data["agents"]["correctness"].update({"capabilities": ["diff_context", "diff_context"]}), "duplicates"),
        (lambda data: data["agents"]["correctness"].update({"capabilities": ["read_repo"]}), "unsupported capabilities"),
        (lambda data: data["agents"]["correctness"].update({"tools": ["github"]}), "unsupported tools"),
        (lambda data: data["agents"]["correctness"].update({"context": {"mode": "diff_context"}}), "context must be a string"),
        (lambda data: data["agents"]["correctness"].update({"stages": ["unknown"]}), "unsupported stage"),
        (lambda data: data["agents"]["correctness"].update({"stages": ["initial_triage", "initial_triage"]}), "duplicate stages"),
        (lambda data: data["agents"]["correctness"]["triggers"].update({"risk_min": "severe"}), "unsupported risk"),
        (lambda data: data["agents"]["correctness"].update({"required": "yes"}), "required must be a boolean"),
        (lambda data: data["agents"]["correctness"]["triggers"].update({"always": "true"}), "always must be a boolean"),
        (lambda data: data["agents"]["correctness"]["triggers"].update({"changed_lines_min": 0}), "positive integer"),
        (lambda data: data["agents"]["correctness"].update({"verdict_power": "approve"}), "unsupported verdict_power"),
    ],
)
def test_invalid_reviewer_config_fails_clearly(mutation, match: str) -> None:
    data = _valid_config()
    mutation(data)

    with pytest.raises(ConfigError, match=match):
        parse_reviewer_config(data)


def test_config_requires_non_empty_agents_stages_and_triggers() -> None:
    with pytest.raises(ConfigError, match="agents"):
        parse_reviewer_config({"agents": {}})

    data = _valid_config()
    data["agents"]["correctness"]["stages"] = []
    with pytest.raises(ConfigError, match="stages"):
        parse_reviewer_config(data)

    data = _valid_config()
    data["agents"]["correctness"]["triggers"] = {}
    with pytest.raises(ConfigError, match="triggers"):
        parse_reviewer_config(data)


def _valid_config() -> dict[str, object]:
    return {
        "agents": {
            "correctness": {
                "description": "Checks correctness.",
                "stages": ["initial_triage"],
                "triggers": {"always": True},
                "required": True,
                "verdict_power": "comment",
                "capabilities": ["diff_context"],
            }
        }
    }
