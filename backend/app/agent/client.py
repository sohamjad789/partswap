"""The NVIDIA OpenAI-compatible client and per-model completion arguments (PLAN.md section 4.15)."""

import copy
from typing import Any, Optional

import openai

from app.config import Settings, get_settings

REQUEST_TIMEOUT_S = 60

MODEL_KWARGS: dict[str, dict[str, Any]] = {
    "super": {
        "temperature": 0.2,
        "top_p": 0.95,
        "max_tokens": 4096,
        "parallel_tool_calls": False,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": True}},
    },
    "fast": {
        "temperature": 0.2,
        "top_p": 0.95,
        "max_tokens": 4096,
        "parallel_tool_calls": False,
        "extra_body": {"skip_special_tokens": False, "chat_template_kwargs": {"enable_thinking": True}},
    },
}


def make_client(settings: Optional[Settings] = None) -> "openai.OpenAI":
    settings = settings or get_settings()
    return openai.OpenAI(base_url=settings.nvidia_base_url, api_key=settings.nvidia_api_key,
                         timeout=REQUEST_TIMEOUT_S, max_retries=0)


def completion_kwargs(model_id: str, settings: Optional[Settings] = None) -> dict[str, Any]:
    """`MODEL_KWARGS` for the model's role (fast when it is `NEMOTRON_FAST_MODEL`, else super), plus `model`."""
    settings = settings or get_settings()
    role = "fast" if model_id == settings.fast_model else "super"
    return {"model": model_id, **copy.deepcopy(MODEL_KWARGS[role])}
