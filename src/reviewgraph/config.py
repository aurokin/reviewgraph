from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from yaml import YAMLError

from reviewgraph.models import (
    ALLOWED_REVIEWER_CAPABILITIES,
    ALLOWED_REVIEWER_VERDICT_POWERS,
    ReviewConfig,
    ReviewerAgentConfig,
    ReviewerTriggers,
    ReviewStage,
    RiskLevel,
)


ALLOWED_TRIGGER_FIELDS = {
    "always",
    "changed_files_min",
    "changed_lines_min",
    "conversation_patterns",
    "diff_patterns",
    "labels",
    "max_files",
    "paths",
    "risk_min",
}


class ConfigError(ValueError):
    pass


def load_reviewer_config(path: str | Path) -> ReviewConfig:
    config_path = Path(path)
    data = _read_config_file(config_path)
    return parse_reviewer_config(data)


def parse_reviewer_config(data: dict[str, Any]) -> ReviewConfig:
    unknown_config_fields = set(data) - {"agents"}
    if unknown_config_fields:
        raise ConfigError(f"reviewer config has unsupported fields: {', '.join(sorted(unknown_config_fields))}")
    agents = data.get("agents")
    if not isinstance(agents, dict) or not agents:
        raise ConfigError("reviewer config agents must be a non-empty object")

    parsed_agents: dict[str, ReviewerAgentConfig] = {}
    for name, agent in agents.items():
        if not isinstance(name, str) or not name:
            raise ConfigError("reviewer config agent names must be non-empty strings")
        if not isinstance(agent, dict):
            raise ConfigError(f"reviewer config agent {name} must be an object")
        parsed_agents[name] = _parse_reviewer_agent(name, agent)
    return ReviewConfig(agents=parsed_agents)


def _read_config_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text()
    except OSError as exc:
        raise ConfigError(f"reviewer config file is not readable: {path}") from exc
    try:
        if path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(raw)
        else:
            data = json.loads(raw)
    except (json.JSONDecodeError, YAMLError) as exc:
        raise ConfigError(f"reviewer config file is invalid: {path}") from exc
    if not isinstance(data, dict):
        raise ConfigError("reviewer config must be an object")
    return data


def _parse_reviewer_agent(name: str, agent: dict[str, Any]) -> ReviewerAgentConfig:
    unknown_fields = set(agent) - {
        "capabilities",
        "context",
        "description",
        "model",
        "required",
        "stages",
        "tools",
        "triggers",
        "verdict_power",
    }
    if unknown_fields:
        raise ConfigError(f"reviewer config agent {name} has unsupported fields: {', '.join(sorted(unknown_fields))}")

    description = _optional_str(agent, "description", name)
    stages = _parse_stages(name, agent.get("stages"))
    triggers = _parse_triggers(name, agent.get("triggers"))
    required = agent.get("required", False)
    if type(required) is not bool:
        raise ConfigError(f"reviewer config agent {name}.required must be a boolean")
    verdict_power = agent.get("verdict_power", "comment")
    if not isinstance(verdict_power, str) or verdict_power not in ALLOWED_REVIEWER_VERDICT_POWERS:
        raise ConfigError(f"reviewer config agent {name} has unsupported verdict_power")
    capabilities = _parse_capabilities(name, agent.get("capabilities", ["diff_context"]))
    model = _optional_str(agent, "model", name)
    if "tools" in agent:
        raise ConfigError(f"reviewer config agent {name} has unsupported tools")
    context_value = agent.get("context")
    if context_value is not None and not isinstance(context_value, str):
        raise ConfigError(f"reviewer config agent {name}.context must be a string")
    return ReviewerAgentConfig(
        name=name,
        description=description,
        stages=stages,
        triggers=triggers,
        required=required,
        verdict_power=verdict_power,
        capabilities=capabilities,
        model=model,
        context=context_value,
    )


def _parse_stages(name: str, value: object) -> tuple[ReviewStage, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"reviewer config agent {name} must include stages")
    stages: list[ReviewStage] = []
    for stage in value:
        if not isinstance(stage, str):
            raise ConfigError(f"reviewer config agent {name} has unsupported stage")
        try:
            stages.append(ReviewStage(stage))
        except ValueError as exc:
            raise ConfigError(f"reviewer config agent {name} has unsupported stage") from exc
    if len(set(stages)) != len(stages):
        raise ConfigError(f"reviewer config agent {name} has duplicate stages")
    return tuple(stages)


def _parse_triggers(name: str, value: object) -> ReviewerTriggers:
    if not isinstance(value, dict) or not value:
        raise ConfigError(f"reviewer config agent {name}.triggers must be non-empty")
    unknown_trigger_fields = set(value) - ALLOWED_TRIGGER_FIELDS
    if unknown_trigger_fields:
        raise ConfigError(
            f"reviewer config agent {name} has unsupported trigger fields: "
            f"{', '.join(sorted(unknown_trigger_fields))}"
        )
    always = value.get("always", False)
    if type(always) is not bool:
        raise ConfigError(f"reviewer config agent {name}.triggers.always must be a boolean")
    return ReviewerTriggers(
        always=always,
        paths=_optional_list_of_str(value, "paths", f"{name}.triggers"),
        labels=_optional_list_of_str(value, "labels", f"{name}.triggers"),
        diff_patterns=_optional_list_of_str(value, "diff_patterns", f"{name}.triggers"),
        conversation_patterns=_optional_list_of_str(value, "conversation_patterns", f"{name}.triggers"),
        risk_min=_optional_risk(value, "risk_min", f"{name}.triggers"),
        max_files=_optional_positive_int(value, "max_files", f"{name}.triggers"),
        changed_lines_min=_optional_positive_int(value, "changed_lines_min", f"{name}.triggers"),
        changed_files_min=_optional_positive_int(value, "changed_files_min", f"{name}.triggers"),
    )


def _parse_capabilities(name: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"reviewer config agent {name}.capabilities must be a non-empty list")
    if not all(isinstance(capability, str) and capability for capability in value):
        raise ConfigError(f"reviewer config agent {name}.capabilities must contain non-empty strings")
    if len(set(value)) != len(value):
        raise ConfigError(f"reviewer config agent {name}.capabilities must not contain duplicates")
    unsupported = sorted(set(value) - ALLOWED_REVIEWER_CAPABILITIES)
    if unsupported:
        raise ConfigError(f"reviewer config agent {name} has unsupported capabilities")
    return tuple(value)


def _optional_str(data: dict[str, Any], field: str, label: str) -> str | None:
    if field not in data:
        return None
    value = data[field]
    if not isinstance(value, str) or not value:
        raise ConfigError(f"reviewer config agent {label}.{field} must be a non-empty string")
    return value


def _optional_list_of_str(data: dict[str, Any], field: str, label: str) -> tuple[str, ...]:
    if field not in data:
        return ()
    value = data[field]
    if not isinstance(value, list) or not value:
        raise ConfigError(f"reviewer config agent {label}.{field} must be a non-empty list")
    if not all(isinstance(item, str) and item for item in value):
        raise ConfigError(f"reviewer config agent {label}.{field} must contain non-empty strings")
    return tuple(value)


def _optional_positive_int(data: dict[str, Any], field: str, label: str) -> int | None:
    if field not in data:
        return None
    value = data[field]
    if type(value) is not int or value <= 0:
        raise ConfigError(f"reviewer config agent {label}.{field} must be a positive integer")
    return value


def _optional_risk(data: dict[str, Any], field: str, label: str) -> RiskLevel | None:
    if field not in data:
        return None
    value = data[field]
    if not isinstance(value, str):
        raise ConfigError(f"reviewer config agent {label}.{field} has unsupported risk level")
    try:
        return RiskLevel(value)
    except ValueError as exc:
        raise ConfigError(f"reviewer config agent {label}.{field} has unsupported risk level") from exc
