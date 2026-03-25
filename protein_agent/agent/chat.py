from __future__ import annotations

from time import time
from typing import Any


def latest_user_content(messages: list[dict[str, Any]] | None) -> str:
    for item in reversed(messages or []):
        if str(item.get("role") or "") == "user":
            return str(item.get("content") or "").strip()
    return ""


def normalize_chat_context(
    latest_result: dict[str, Any] | None,
    previous_best_design: str | None,
    reasoning_context: dict[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    latest_result = latest_result or {}
    previous_best_design = previous_best_design or ""
    reasoning_context = reasoning_context or {}
    if not latest_result and isinstance(reasoning_context.get("latest_result"), dict):
        latest_result = reasoning_context["latest_result"]
    if not previous_best_design and isinstance(reasoning_context.get("previous_best_design"), str):
        previous_best_design = reasoning_context["previous_best_design"]
    return latest_result, previous_best_design


def best_design_from_result(latest_result: dict[str, Any] | None) -> dict[str, Any]:
    latest_result = latest_result or {}
    if isinstance(latest_result.get("best_design"), dict):
        return latest_result["best_design"]
    ranking = latest_result.get("ranking")
    if isinstance(ranking, list) and ranking and isinstance(ranking[0], dict):
        return ranking[0]
    return {}


def build_reasoning_context(
    chat_mode: str,
    latest_result: dict[str, Any] | None,
    previous_best_design: str | None,
    *,
    current_mode: str = "full_pipeline",
) -> dict[str, Any]:
    context = {
        "version": 1,
        "chat_mode": chat_mode,
        "current_mode": current_mode,
        "latest_result": latest_result or {},
        "previous_best_design": previous_best_design or "",
    }
    best = best_design_from_result(latest_result)
    if best.get("pdb"):
        context["latest_best_design"] = best["pdb"]
    return context


def extras_from_latest_result(latest_result: dict[str, Any] | None) -> dict[str, Any]:
    latest_result = latest_result or {}
    best = best_design_from_result(latest_result)
    request = latest_result.get("request") if isinstance(latest_result.get("request"), dict) else {}
    extra: dict[str, Any] = {"module": latest_result.get("module")}
    if best:
        extra["best_design"] = best
    if request:
        extra["request"] = request
    ranking = latest_result.get("ranking")
    if isinstance(ranking, list):
        extra["ranking_count"] = len(ranking)
    return extra


def is_reasoning_query(content: str) -> bool:
    text = content.lower().strip()
    if not text:
        return False
    keywords = (
        "why",
        "explain",
        "compare",
        "reason",
        "better",
        "summary",
        "recommend",
        "为什么",
        "解释",
        "比较",
        "分析",
        "哪个更好",
        "推荐",
    )
    return any(keyword in text for keyword in keywords)


def build_chat_completion(
    content: str,
    *,
    model: str = "protein-binder-design-agent",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": f"chatcmpl-{int(time())}",
        "object": "chat.completion",
        "created": int(time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
    for key, value in (extra or {}).items():
        payload[key] = value
    return payload
