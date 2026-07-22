"""Central model-provider gateway for Akasha chatbot AI calls."""

from __future__ import annotations

import os
from typing import Any, Iterable

import httpx
from dotenv import load_dotenv


class ModelGatewayError(Exception):
    """Raised when the configured model provider cannot complete a request."""


def get_ai_provider() -> str:
    load_dotenv(override=True)
    return os.environ.get("AI_PROVIDER", "ollama").strip().lower()


def get_provider_model(provider: str | None = None, *, vision: bool = False) -> str:
    provider_name = (provider or get_ai_provider()).lower()
    if provider_name == "azure":
        return _required_env("AZURE_OPENAI_DEPLOYMENT_NAME", "Azure OpenAI deployment name is missing.")
    if provider_name == "groq":
        if vision:
            return os.environ.get("GROQ_VISION_MODEL", "llama-3.2-90b-vision-preview")
        return os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    if provider_name == "openrouter":
        if vision:
            return os.environ.get("OPENROUTER_VISION_MODEL") or os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
        return os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    if provider_name == "ollama":
        if vision:
            return os.environ.get("OLLAMA_VISION_MODEL", "qwen3-vl:32b")
        return os.environ.get("OLLAMA_MODEL", "gemma4:latest")
    raise ModelGatewayError(f"Unsupported AI_PROVIDER '{provider_name}'.")


def complete_text(
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    json_response: bool = False,
    provider: str | None = None,
    vision: bool = False,
) -> str:
    response = chat_completion(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_response=json_response,
        stream=False,
        provider=provider,
        vision=vision,
    )
    return response.choices[0].message.content or ""


def stream_text(
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    provider: str | None = None,
) -> Iterable[str]:
    response = chat_completion(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
        provider=provider,
    )
    for chunk in response:
        delta = chunk.choices[0].delta if chunk.choices else None
        content = getattr(delta, "content", None)
        if content:
            yield content


def chat_completion(
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    json_response: bool = False,
    stream: bool = False,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    provider: str | None = None,
    vision: bool = False,
) -> Any:
    provider_name = (provider or get_ai_provider()).lower()
    client = _client_for_provider(provider_name)
    kwargs: dict[str, Any] = {
        "model": get_provider_model(provider_name, vision=vision),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if json_response:
        kwargs["response_format"] = {"type": "json_object"}
    if tools:
        kwargs["tools"] = tools
    if tool_choice:
        kwargs["tool_choice"] = tool_choice

    try:
        return client.chat.completions.create(**kwargs)
    except Exception as exc:
        raise ModelGatewayError(f"{provider_name} model request failed: {exc}") from exc


def _client_for_provider(provider: str) -> Any:
    load_dotenv(override=True)
    if provider == "azure":
        from openai import AzureOpenAI

        return AzureOpenAI(
            azure_endpoint=_required_env("AZURE_OPENAI_ENDPOINT", "Azure OpenAI endpoint is missing."),
            api_key=_required_env("AZURE_OPENAI_API_KEY", "Azure OpenAI API key is missing."),
            api_version=_required_env("AZURE_OPENAI_API_VERSION", "Azure OpenAI API version is missing."),
            timeout=_timeout(),
        )

    if provider == "groq":
        from groq import Groq

        return Groq(
            api_key=os.environ.get("GROQ_API_KEY") or _required_env("AKASHA_AI_API_KEY", "Groq API key is missing."),
            timeout=_timeout(),
        )

    if provider == "openrouter":
        from openai import OpenAI

        headers = {
            "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", "http://localhost"),
            "X-Title": os.environ.get("OPENROUTER_APP_NAME", "Akasha"),
        }
        return OpenAI(
            base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key=_required_env("OPENROUTER_API_KEY", "OpenRouter API key is missing."),
            default_headers=headers,
            timeout=_timeout(),
        )

    if provider == "ollama":
        from openai import OpenAI

        return OpenAI(
            base_url=os.environ.get("OLLAMA_ENDPOINT", "http://localhost:11434/v1"),
            api_key=os.environ.get("OLLAMA_API_KEY", "ollama"),
            timeout=_timeout(default=300.0, connect=30.0),
        )

    raise ModelGatewayError(f"Unsupported AI_PROVIDER '{provider}'.")


def _timeout(default: float = 120.0, connect: float = 20.0) -> httpx.Timeout:
    timeout = float(os.environ.get("AI_REQUEST_TIMEOUT_SECONDS", default))
    connect_timeout = float(os.environ.get("AI_CONNECT_TIMEOUT_SECONDS", connect))
    return httpx.Timeout(timeout, connect=connect_timeout)


def _required_env(name: str, message: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ModelGatewayError(message)
    return value
