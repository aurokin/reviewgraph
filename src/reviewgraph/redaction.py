from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


REDACTION_TOKEN = "[REDACTED]"


@dataclass(frozen=True)
class RedactionResult:
    text: str
    replacement_count: int
    categories: tuple[str, ...]

    @property
    def redacted(self) -> bool:
        return self.replacement_count > 0


@dataclass(frozen=True)
class RedactionSummary:
    replacement_count: int
    categories: tuple[str, ...]

    @property
    def redacted(self) -> bool:
        return self.replacement_count > 0


@dataclass(frozen=True)
class RedactedDataResult:
    data: Any
    redaction_status: RedactionSummary


@dataclass(frozen=True)
class RedactedSurfaceResult:
    surface: str
    text: str | None
    data: Any | None
    redaction_status: RedactionSummary
    raw_provider_submission_enabled: bool
    raw_trace_persistence_enabled: bool


class RedactionPolicyError(ValueError):
    pass


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
    ),
    ("authorization_header", re.compile(r"(?im)^(\s*authorization\s*:\s*)(?:bearer|basic)\s+\S+")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}")),
    ("github_token", re.compile(r"\b(?:gh[psuor]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    (
        "api_key",
        re.compile(
            r"(?i)([\"']?\b(?:api[_-]?key|token|secret)[\"']?\s*[:=]\s*)[\"']?[A-Za-z0-9._~+/=_-]{12,}[\"']?"
        ),
    ),
    ("env_assignment", re.compile(r"(?im)^([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*).+$")),
    (
        "standalone_api_key",
        re.compile(r"\b(?:(?:sk|rk|pk)_(?:live|test|prod)_[A-Za-z0-9_-]{12,}|(?:sk|rk|pk|xox[baprs])-[A-Za-z0-9_-]{12,})\b"),
    ),
)


def redact_text(text: str) -> RedactionResult:
    redacted = text
    replacement_count = 0
    categories: list[str] = []

    for category, pattern in _PATTERNS:
        if category in {"authorization_header", "env_assignment", "api_key"}:
            redacted, count = pattern.subn(lambda match: f"{match.group(1)}{REDACTION_TOKEN}", redacted)
        else:
            redacted, count = pattern.subn(REDACTION_TOKEN, redacted)
        if count:
            replacement_count += count
            categories.append(category)

    return RedactionResult(
        text=redacted,
        replacement_count=replacement_count,
        categories=tuple(categories),
    )


def redact_data(data: Any) -> RedactedDataResult:
    redacted, replacement_count, categories = _redact_data_value(data)
    return RedactedDataResult(
        data=redacted,
        redaction_status=RedactionSummary(
            replacement_count=replacement_count,
            categories=tuple(dict.fromkeys(categories)),
        ),
    )


def redact_provider_bound_text(
    text: str,
    *,
    surface: str = "provider_request",
    raw_provider_submission_enabled: bool = False,
    raw_trace_persistence_enabled: bool = False,
) -> RedactedSurfaceResult:
    redaction = redact_text(text)
    return RedactedSurfaceResult(
        surface=surface,
        text=text if raw_provider_submission_enabled else redaction.text,
        data=None,
        redaction_status=_summary_from_text(redaction),
        raw_provider_submission_enabled=raw_provider_submission_enabled,
        raw_trace_persistence_enabled=raw_trace_persistence_enabled,
    )


def redact_trace_data(
    data: Any,
    *,
    surface: str = "trace",
    raw_trace_persistence_enabled: bool = False,
    raw_provider_submission_enabled: bool = False,
) -> RedactedSurfaceResult:
    redaction = redact_data(data)
    return RedactedSurfaceResult(
        surface=surface,
        text=None,
        data=data if raw_trace_persistence_enabled else redaction.data,
        redaction_status=redaction.redaction_status,
        raw_provider_submission_enabled=raw_provider_submission_enabled,
        raw_trace_persistence_enabled=raw_trace_persistence_enabled,
    )


def require_passing_redaction_status(redaction_status: object, *, surface: str) -> None:
    from reviewgraph.models import GateStatus, RedactionStatus

    if not isinstance(redaction_status, RedactionStatus):
        raise RedactionPolicyError(f"{surface} requires redaction status before payload validation")
    if redaction_status.status != GateStatus.PASS:
        raise RedactionPolicyError(f"{surface} redaction status must pass before payload validation")


def require_state_redaction_before_payload_validation(state: object) -> None:
    require_passing_redaction_status(
        getattr(state, "redaction_status", None),
        surface="review_state",
    )


def _redact_data_value(value: Any) -> tuple[Any, int, list[str]]:
    if isinstance(value, str):
        result = redact_text(value)
        return result.text, result.replacement_count, list(result.categories)
    if isinstance(value, list):
        return _redact_sequence(value, list)
    if isinstance(value, tuple):
        return _redact_sequence(value, tuple)
    if isinstance(value, dict):
        replacement_count = 0
        categories: list[str] = []
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            redacted_key, key_count, key_categories = _redact_data_value(key)
            redacted_item, item_count, item_categories = _redact_data_value(item)
            replacement_count += key_count + item_count
            categories.extend(key_categories)
            categories.extend(item_categories)
            redacted[_unique_key(redacted, redacted_key)] = redacted_item
        return redacted, replacement_count, categories
    return value, 0, []


def _redact_sequence(value: list[Any] | tuple[Any, ...], factory: type[list[Any]] | type[tuple[Any, ...]]) -> tuple[Any, int, list[str]]:
    replacement_count = 0
    categories: list[str] = []
    redacted_items: list[Any] = []
    for item in value:
        redacted_item, item_count, item_categories = _redact_data_value(item)
        redacted_items.append(redacted_item)
        replacement_count += item_count
        categories.extend(item_categories)
    if factory is tuple:
        return tuple(redacted_items), replacement_count, categories
    return redacted_items, replacement_count, categories


def _summary_from_text(redaction: RedactionResult) -> RedactionSummary:
    return RedactionSummary(
        replacement_count=redaction.replacement_count,
        categories=redaction.categories,
    )


def _unique_key(data: dict[Any, Any], key: Any) -> Any:
    if key not in data:
        return key
    if not isinstance(key, str):
        suffix = 2
        candidate = (key, suffix)
        while candidate in data:
            suffix += 1
            candidate = (key, suffix)
        return candidate
    suffix = 2
    candidate = f"{key}#{suffix}"
    while candidate in data:
        suffix += 1
        candidate = f"{key}#{suffix}"
    return candidate
