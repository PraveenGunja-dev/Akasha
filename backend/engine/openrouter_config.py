"""Shared OpenRouter model fallback configuration."""

import os

from langchain_openai import ChatOpenAI


DEFAULT_OPENROUTER_FALLBACK_MODELS = (
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
)


class OpenRouterChatModel(ChatOpenAI):
    """ChatOpenAI adapter that preserves OpenRouter's `max_tokens` contract."""

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if "max_completion_tokens" in payload:
            payload["max_tokens"] = payload.pop("max_completion_tokens")
        return payload


def openrouter_fallback_models() -> list[str]:
    configured = os.getenv("OPENROUTER_FALLBACK_MODELS")
    values = DEFAULT_OPENROUTER_FALLBACK_MODELS if configured is None else configured.split(",")
    primary = os.getenv("OPENROUTER_MODEL", "").strip()
    fallbacks = []
    for value in values:
        model_name = value.strip()
        if model_name and model_name != primary and model_name not in fallbacks:
            fallbacks.append(model_name)
    return fallbacks


def openrouter_model_ids() -> list[str]:
    primary = os.environ["OPENROUTER_MODEL"].strip()
    if not primary:
        raise RuntimeError("OPENROUTER_MODEL must not be blank.")
    return [primary, *openrouter_fallback_models()]


def openrouter_extra_body() -> dict:
    body = {"provider": {"require_parameters": True}}
    fallbacks = openrouter_fallback_models()
    if fallbacks:
        body["models"] = fallbacks
    return body
