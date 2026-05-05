from __future__ import annotations

import re
from dataclasses import dataclass


REDACTION_TOKEN = "[REDACTED]"


@dataclass(frozen=True)
class RedactionResult:
    text: str
    replacement_count: int
    categories: tuple[str, ...]

    @property
    def redacted(self) -> bool:
        return self.replacement_count > 0


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
    ("github_token", re.compile(r"\bgh[psuor]_[A-Za-z0-9_]{20,}\b")),
    ("api_key", re.compile(r"(?i)\b(?:api[_-]?key|token|secret)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{12,}['\"]?")),
    ("env_assignment", re.compile(r"(?im)^([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*).+$")),
)


def redact_text(text: str) -> RedactionResult:
    redacted = text
    replacement_count = 0
    categories: list[str] = []

    for category, pattern in _PATTERNS:
        if category in {"authorization_header", "env_assignment"}:
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
