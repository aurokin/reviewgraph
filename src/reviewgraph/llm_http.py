from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass

from reviewgraph.llm import LiveLLMProviderError, LiveLLMProviderRequest, LiveLLMProviderResponse
from reviewgraph.llm_policy import ProviderFailureReasonCode


DEFAULT_OPENAI_COMPATIBLE_BASE_URL = "https://api.openai.com/v1"


@dataclass(frozen=True)
class OpenAICompatibleLiveLLMTransport:
    api_key: str
    base_url: str = DEFAULT_OPENAI_COMPATIBLE_BASE_URL

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError("live LLM transport API key is required")
        if not self.base_url:
            raise ValueError("live LLM transport base URL is required")

    def __call__(self, request: LiveLLMProviderRequest) -> LiveLLMProviderResponse:
        payload = {
            "model": request.model,
            "messages": [
                {
                    "role": "user",
                    "content": request.request_text,
                }
            ],
            "temperature": 0,
        }
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        http_request = urllib.request.Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "reviewgraph-live-llm/0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=request.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
                request_id = response.headers.get("x-request-id")
        except TimeoutError as exc:
            raise _provider_error(ProviderFailureReasonCode.TIMEOUT, str(exc)) from exc
        except socket.timeout as exc:
            raise _provider_error(ProviderFailureReasonCode.TIMEOUT, str(exc)) from exc
        except urllib.error.HTTPError as exc:
            raise _provider_error(_http_status_reason(exc.code), _safe_http_error_message(exc), request_id=exc.headers.get("x-request-id")) from exc
        except urllib.error.URLError as exc:
            reason = ProviderFailureReasonCode.TIMEOUT if "timed out" in str(exc.reason).casefold() else ProviderFailureReasonCode.PROVIDER_UNAVAILABLE
            raise _provider_error(reason, str(exc.reason)) from exc
        except OSError as exc:
            raise _provider_error(ProviderFailureReasonCode.PROVIDER_UNAVAILABLE, str(exc)) from exc
        return LiveLLMProviderResponse(
            text=_completion_text(response_body),
            request_id=request_id,
        )


def transport_from_environment(*, provider: str | None) -> OpenAICompatibleLiveLLMTransport:
    if provider not in {"openai", "openai-compatible"}:
        raise ValueError("live LLM CLI currently supports provider 'openai' or 'openai-compatible'")
    api_key = os.environ.get("REVIEWGRAPH_LIVE_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Live LLM requires REVIEWGRAPH_LIVE_LLM_API_KEY or OPENAI_API_KEY")
    base_url = os.environ.get("REVIEWGRAPH_LIVE_LLM_BASE_URL") or DEFAULT_OPENAI_COMPATIBLE_BASE_URL
    return OpenAICompatibleLiveLLMTransport(api_key=api_key, base_url=base_url)


def _completion_text(response_body: str) -> str:
    try:
        data = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise _provider_error(ProviderFailureReasonCode.MALFORMED_RESPONSE, "provider response is not valid JSON") from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise _provider_error(ProviderFailureReasonCode.MALFORMED_RESPONSE, "provider response has no message content") from exc
    if not isinstance(content, str) or not content:
        raise _provider_error(ProviderFailureReasonCode.MALFORMED_RESPONSE, "provider response message content is empty")
    return content


def _http_status_reason(status: int) -> ProviderFailureReasonCode:
    if status in {401, 403}:
        return ProviderFailureReasonCode.MISSING_CREDENTIALS
    if status == 408:
        return ProviderFailureReasonCode.TIMEOUT
    if status == 429:
        return ProviderFailureReasonCode.RATE_LIMITED
    if 500 <= status <= 599:
        return ProviderFailureReasonCode.PROVIDER_UNAVAILABLE
    return ProviderFailureReasonCode.UNKNOWN_PROVIDER_ERROR


def _safe_http_error_message(exc: urllib.error.HTTPError) -> str:
    return f"HTTP {exc.code}: {exc.reason}"


def _provider_error(
    reason_code: ProviderFailureReasonCode,
    message: str,
    *,
    request_id: str | None = None,
) -> LiveLLMProviderError:
    return LiveLLMProviderError(reason_code, message, request_id=request_id)
