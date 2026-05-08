from __future__ import annotations

from collections.abc import Mapping


def live_llm_smoke_prerequisite_artifact(environ: Mapping[str, str]) -> dict[str, object]:
    missing: list[str] = []
    if environ.get("REVIEWGRAPH_LIVE_LLM") != "1":
        missing.append("REVIEWGRAPH_LIVE_LLM=1")
    if not environ.get("REVIEWGRAPH_LIVE_LLM_PROVIDER"):
        missing.append("REVIEWGRAPH_LIVE_LLM_PROVIDER")
    if not environ.get("REVIEWGRAPH_LIVE_LLM_MODEL"):
        missing.append("REVIEWGRAPH_LIVE_LLM_MODEL")
    if not (environ.get("REVIEWGRAPH_LIVE_LLM_API_KEY") or environ.get("OPENAI_API_KEY")):
        missing.append("REVIEWGRAPH_LIVE_LLM_API_KEY or OPENAI_API_KEY")
    return {
        "status": "ready" if not missing else "blocked",
        "reason_code": None if not missing else "missing_live_llm_smoke_prerequisites",
        "missing": missing,
        "provider": environ.get("REVIEWGRAPH_LIVE_LLM_PROVIDER"),
        "model": environ.get("REVIEWGRAPH_LIVE_LLM_MODEL"),
        "api_key_present": bool(environ.get("REVIEWGRAPH_LIVE_LLM_API_KEY") or environ.get("OPENAI_API_KEY")),
        "base_url_present": bool(environ.get("REVIEWGRAPH_LIVE_LLM_BASE_URL")),
    }
