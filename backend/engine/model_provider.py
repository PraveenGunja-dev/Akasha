"""Configured model-provider registry and normalized invocation API."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Callable, Iterable, Iterator, Mapping

import httpx
from langchain_core.language_models.chat_models import BaseChatModel

from engine.openrouter_config import (
    OpenRouterChatModel,
    openrouter_extra_body,
    openrouter_model_ids,
)
from engine.provider_errors import classify_provider_error


DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 2


class ProviderConfigurationError(RuntimeError):
    """The selected provider is unknown or incompletely configured."""


class ProviderCapabilityError(RuntimeError):
    """The selected model cannot perform an explicitly requested operation."""


class ProviderInvocationError(RuntimeError):
    """A provider failure reduced to an existing payload-safe category."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ModelIdentity:
    provider: str
    model: str


@dataclass(frozen=True)
class ProviderCapabilities:
    tool_calling: bool
    structured_json: bool
    streaming: bool
    vision: bool


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ModelInvocationResult:
    content: str | None
    identity: ModelIdentity
    usage: TokenUsage | None
    message: Any
    raw_response: Any


@dataclass(frozen=True)
class ModelStreamChunk:
    content: str | None
    identity: ModelIdentity
    usage: TokenUsage | None
    raw_chunk: Any


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ProviderConfigurationError(f"{name} must be configured for the selected AI provider.")
    return value


def _number(name: str, default: float, cast: Callable[[str], Any]) -> Any:
    value = os.getenv(name)
    if value is None:
        return cast(str(default))
    try:
        result = cast(value)
    except (TypeError, ValueError) as exc:
        raise ProviderConfigurationError(f"{name} must be a valid number.") from exc
    if result < 0:
        raise ProviderConfigurationError(f"{name} must not be negative.")
    return result


def _optional_bool(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ProviderConfigurationError(f"{name} must be true or false.")


def _timeout() -> httpx.Timeout:
    total = _number("AKASHA_MODEL_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, float)
    connect = _number(
        "AKASHA_MODEL_CONNECT_TIMEOUT_SECONDS",
        DEFAULT_CONNECT_TIMEOUT_SECONDS,
        float,
    )
    return httpx.Timeout(total, connect=connect)


def _max_retries() -> int:
    return _number("AKASHA_MODEL_MAX_RETRIES", DEFAULT_MAX_RETRIES, int)


def _usage_value(usage: Any, *names: str) -> int | None:
    for name in names:
        value = usage.get(name) if isinstance(usage, Mapping) else getattr(usage, name, None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _token_usage(response: Any) -> TokenUsage | None:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, Mapping):
        usage = response.get("usage") or response.get("usage_metadata")
    if usage is None:
        return None
    result = TokenUsage(
        input_tokens=_usage_value(usage, "prompt_tokens", "input_tokens"),
        output_tokens=_usage_value(usage, "completion_tokens", "output_tokens"),
        total_tokens=_usage_value(usage, "total_tokens"),
    )
    return result if any(value is not None for value in result.__dict__.values()) else None


def _response_model(response: Any, fallback: str) -> str:
    model = getattr(response, "model", None)
    if not model and isinstance(response, Mapping):
        model = response.get("model")
    return str(model or fallback)


class ModelProvider:
    """OpenAI-compatible provider adapter with a LangChain model view."""

    name: str

    def __init__(self, *, model: str, capabilities: ProviderCapabilities):
        if not model.strip():
            raise ProviderConfigurationError("The configured AI model must not be blank.")
        self.model = model.strip()
        self.capabilities = capabilities
        self._client: Any = None

    @property
    def identity(self) -> ModelIdentity:
        return ModelIdentity(provider=self.name, model=self.model)

    def require_capabilities(self, *capabilities: str) -> None:
        for capability in capabilities:
            if not hasattr(self.capabilities, capability):
                raise ValueError(f"Unknown model capability: {capability}")
            if not getattr(self.capabilities, capability):
                label = capability.replace("_", " ")
                raise ProviderCapabilityError(
                    f"The configured {self.name} model does not support {label}."
                )

    def validate_chat_model_capabilities(
        self,
        model: BaseChatModel,
        *capabilities: str,
    ) -> None:
        self.require_capabilities(*capabilities)
        profile = getattr(model, "profile", None) or {}
        profile_fields = {
            "tool_calling": "tool_calling",
            "structured_json": "structured_output",
            "vision": "image_inputs",
        }
        for capability in capabilities:
            field = profile_fields.get(capability)
            if field and profile.get(field) is False:
                raise ProviderCapabilityError(
                    f"The configured {self.name} model does not support "
                    f"{capability.replace('_', ' ')}."
                )

    def _build_client(self):
        raise NotImplementedError

    def client(self):
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _completion_options(self) -> dict[str, Any]:
        return {}

    def create_completion(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        json_mode: bool = False,
        stream: bool = False,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        vision: bool = False,
    ):
        required = []
        if json_mode:
            required.append("structured_json")
        if stream:
            required.append("streaming")
        if tools:
            required.append("tool_calling")
        if vision:
            required.append("vision")
        self.require_capabilities(*required)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            **self._completion_options(),
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
        try:
            return self.client().chat.completions.create(**kwargs)
        except (ProviderConfigurationError, ProviderCapabilityError, ProviderInvocationError):
            raise
        except Exception as exc:
            public_error = classify_provider_error(exc)
            raise ProviderInvocationError(public_error.code, public_error.message) from exc

    def invoke(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        json_mode: bool = False,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        vision: bool = False,
    ) -> ModelInvocationResult:
        response = self.create_completion(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            tools=tools,
            tool_choice=tool_choice,
            vision=vision,
        )
        message = response.choices[0].message
        return ModelInvocationResult(
            content=getattr(message, "content", None),
            identity=ModelIdentity(self.name, _response_model(response, self.model)),
            usage=_token_usage(response),
            message=message,
            raw_response=response,
        )

    def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        json_mode: bool = False,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        vision: bool = False,
    ) -> Iterator[ModelStreamChunk]:
        chunks = self.create_completion(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            stream=True,
            tools=tools,
            tool_choice=tool_choice,
            vision=vision,
        )
        for chunk in chunks:
            choices = getattr(chunk, "choices", None) or []
            content = getattr(getattr(choices[0], "delta", None), "content", None) if choices else None
            yield ModelStreamChunk(
                content=content,
                identity=ModelIdentity(self.name, _response_model(chunk, self.model)),
                usage=_token_usage(chunk),
                raw_chunk=chunk,
            )

    def chat_model(
        self,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> BaseChatModel:
        raise NotImplementedError

    def discover_context_window(self, required_capabilities: Iterable[str] = ()) -> int | None:
        return None


class AzureOpenAIProvider(ModelProvider):
    name = "azure"

    def __init__(self, *, vision: bool = False):
        vision_override = _optional_bool("AZURE_OPENAI_SUPPORTS_VISION")
        standard_deployment = _required("AZURE_OPENAI_DEPLOYMENT_NAME")
        vision_deployment = os.getenv("AZURE_OPENAI_VISION_DEPLOYMENT_NAME", "").strip()
        if vision and not vision_deployment and vision_override is not True:
            raise ProviderCapabilityError(
                "Configure AZURE_OPENAI_VISION_DEPLOYMENT_NAME or enable "
                "AZURE_OPENAI_SUPPORTS_VISION for vision requests."
            )
        deployment = vision_deployment if vision and vision_deployment else standard_deployment
        model = os.getenv("AZURE_OPENAI_VISION_MODEL" if vision else "AZURE_OPENAI_MODEL", deployment)
        super().__init__(
            model=model,
            capabilities=ProviderCapabilities(
                True,
                True,
                True,
                bool(vision_deployment) or vision_override is True,
            ),
        )
        self.deployment = deployment
        self.endpoint = _required("AZURE_OPENAI_ENDPOINT")
        self.api_key = _required("AZURE_OPENAI_API_KEY")
        self.api_version = _required("AZURE_OPENAI_API_VERSION")

    def _build_client(self):
        import openai

        return openai.AzureOpenAI(
            azure_endpoint=self.endpoint,
            azure_deployment=self.deployment,
            api_key=self.api_key,
            api_version=self.api_version,
            timeout=_timeout(),
            max_retries=_max_retries(),
        )

    def chat_model(self, *, temperature: float = 0.2, max_tokens: int = 2048) -> BaseChatModel:
        from langchain_openai import AzureChatOpenAI

        return AzureChatOpenAI(
            azure_endpoint=self.endpoint,
            azure_deployment=self.deployment,
            api_key=self.api_key,
            api_version=self.api_version,
            model=self.model,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            timeout=_timeout(),
            max_retries=_max_retries(),
        )


class OpenRouterProvider(ModelProvider):
    name = "openrouter"

    def __init__(self, *, vision: bool = False):
        primary = _required("OPENROUTER_MODEL")
        vision_model = os.getenv("OPENROUTER_VISION_MODEL", "").strip()
        vision_override = _optional_bool("OPENROUTER_SUPPORTS_VISION")
        if vision and not vision_model and vision_override is not True:
            raise ProviderCapabilityError(
                "Configure OPENROUTER_VISION_MODEL or enable OPENROUTER_SUPPORTS_VISION "
                "for vision requests."
            )
        super().__init__(
            model=vision_model if vision and vision_model else primary,
            capabilities=ProviderCapabilities(
                True,
                True,
                True,
                bool(vision_model) or vision_override is True,
            ),
        )
        self.api_key = _required("OPENROUTER_API_KEY")
        self.vision_request = vision
        self.base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.headers = {
            "HTTP-Referer": os.getenv("OPENROUTER_APP_URL", "http://localhost:5173/akasha/"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "Akasha"),
        }

    def _build_client(self):
        import openai

        return openai.OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            default_headers=self.headers,
            timeout=_timeout(),
            max_retries=_max_retries(),
        )

    def _completion_options(self) -> dict[str, Any]:
        return {
            "extra_body": (
                {"provider": {"require_parameters": True}}
                if self.vision_request
                else openrouter_extra_body()
            )
        }

    def chat_model(self, *, temperature: float = 0.2, max_tokens: int = 2048) -> BaseChatModel:
        extra_body = (
            {"provider": {"require_parameters": True}}
            if self.vision_request
            else openrouter_extra_body()
        )
        return OpenRouterChatModel(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            default_headers=self.headers,
            extra_body=extra_body,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            timeout=_timeout(),
            max_retries=_max_retries(),
        )

    def discover_context_window(self, required_capabilities: Iterable[str] = ()) -> int | None:
        import requests

        response = requests.get(
            f"{self.base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=15,
        )
        response.raise_for_status()
        catalog = {item.get("id"): item for item in response.json().get("data", [])}
        windows = []
        parameter_names = {
            "tool_calling": {"tools", "tool_choice"},
            "structured_json": {"response_format"},
        }
        model_ids = [self.model] if self.model != os.getenv("OPENROUTER_MODEL", "").strip() else openrouter_model_ids()
        for model_name in model_ids:
            metadata = catalog.get(model_name)
            if metadata is None:
                raise ProviderConfigurationError(
                    f"Configured OpenRouter model does not exist: {model_name}"
                )
            supported = set(metadata.get("supported_parameters") or [])
            for capability in required_capabilities:
                required = parameter_names.get(capability)
                if required and not required.issubset(supported):
                    raise ProviderCapabilityError(
                        f"Configured OpenRouter model does not support {capability.replace('_', ' ')}: "
                        f"{model_name}"
                    )
            try:
                window = int(metadata.get("context_length"))
            except (TypeError, ValueError) as exc:
                raise ProviderConfigurationError(
                    f"Invalid model context window reported by OpenRouter model {model_name}."
                ) from exc
            windows.append(window)
        return min(windows) if windows else None


class GroqProvider(ModelProvider):
    name = "groq"

    def __init__(self, *, vision: bool = False):
        vision_model = os.getenv("GROQ_VISION_MODEL", "").strip()
        vision_override = _optional_bool("GROQ_SUPPORTS_VISION")
        if vision and not vision_model and vision_override is not True:
            raise ProviderCapabilityError(
                "Configure GROQ_VISION_MODEL or enable GROQ_SUPPORTS_VISION for vision requests."
            )
        super().__init__(
            model=(
                vision_model
                if vision and vision_model
                else os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
            ),
            capabilities=ProviderCapabilities(
                True,
                True,
                True,
                bool(vision_model) or vision_override is True,
            ),
        )
        self.api_key = _required("AKASHA_AI_API_KEY")
        self.base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

    def _build_client(self):
        import openai

        return openai.OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=_timeout(),
            max_retries=_max_retries(),
        )

    def chat_model(self, *, temperature: float = 0.2, max_tokens: int = 2048) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            timeout=_timeout(),
            max_retries=_max_retries(),
        )

    def discover_context_window(self, required_capabilities: Iterable[str] = ()) -> int | None:
        from groq import Groq

        metadata = Groq(api_key=self.api_key).models.retrieve(self.model)
        for field in ("context_window", "context_length", "max_input_tokens"):
            value = getattr(metadata, field, None)
            if value:
                return int(value)
        return None


class OllamaProvider(ModelProvider):
    name = "ollama"

    def __init__(self, *, vision: bool = False):
        vision_model = os.getenv("OLLAMA_VISION_MODEL", "").strip()
        vision_override = _optional_bool("OLLAMA_SUPPORTS_VISION")
        if vision and not vision_model and vision_override is not True:
            raise ProviderCapabilityError(
                "Configure OLLAMA_VISION_MODEL or enable OLLAMA_SUPPORTS_VISION for vision requests."
            )
        tool_calling = _optional_bool("OLLAMA_SUPPORTS_TOOL_CALLING")
        structured_json = _optional_bool("OLLAMA_SUPPORTS_STRUCTURED_JSON")
        super().__init__(
            model=(
                vision_model
                if vision and vision_model
                else os.getenv("OLLAMA_MODEL", "gemma4:latest")
            ),
            capabilities=ProviderCapabilities(
                tool_calling is True,
                structured_json is True,
                True,
                bool(vision_model) or vision_override is True,
            ),
        )
        self.base_url = os.getenv("OLLAMA_ENDPOINT", "http://192.168.0.59:11434/v1")

    def _build_client(self):
        import openai

        return openai.OpenAI(
            base_url=self.base_url,
            api_key="ollama",
            timeout=_timeout(),
            max_retries=_max_retries(),
        )

    def chat_model(self, *, temperature: float = 0.2, max_tokens: int = 2048) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.model,
            api_key="ollama",
            base_url=self.base_url,
            temperature=temperature,
            max_completion_tokens=max_tokens,
            timeout=_timeout(),
            max_retries=_max_retries(),
        )

    def discover_context_window(self, required_capabilities: Iterable[str] = ()) -> int | None:
        import requests

        endpoint = self.base_url.rstrip("/")
        if endpoint.endswith("/v1"):
            endpoint = endpoint[:-3]
        response = requests.post(
            f"{endpoint}/api/show",
            json={"model": self.model},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        reported = set(payload.get("capabilities") or [])
        if "tool_calling" in required_capabilities and "tools" not in reported:
            raise ProviderCapabilityError("The configured Ollama model does not support tool calling.")
        if "structured_json" in required_capabilities and not self.capabilities.structured_json:
            raise ProviderCapabilityError(
                "Set OLLAMA_SUPPORTS_STRUCTURED_JSON=true only after validating the configured model."
            )
        model_info = payload.get("model_info") or {}
        values = [value for key, value in model_info.items() if key.endswith(".context_length") and value]
        return int(max(values)) if values else None


ProviderFactory = Callable[[bool], ModelProvider]
_PROVIDER_REGISTRY: dict[str, ProviderFactory] = {}
_PROVIDER_ALIASES = {
    "azure_openai": "azure",
    "azure-openai": "azure",
    "open_router": "openrouter",
}


def register_model_provider(name: str, factory: ProviderFactory, *, replace: bool = False) -> None:
    normalized = name.strip().lower()
    if not normalized:
        raise ValueError("Provider name must not be blank.")
    if normalized in _PROVIDER_REGISTRY and not replace:
        raise ValueError(f"Model provider is already registered: {normalized}")
    _PROVIDER_REGISTRY[normalized] = factory


def configured_provider_name(provider: str | None = None) -> str:
    name = (provider or os.getenv("AI_PROVIDER", "ollama")).strip().lower()
    return _PROVIDER_ALIASES.get(name, name)


def get_model_provider(provider: str | None = None, *, vision: bool = False) -> ModelProvider:
    name = configured_provider_name(provider)
    factory = _PROVIDER_REGISTRY.get(name)
    if factory is None:
        raise ProviderConfigurationError(f"Unsupported AI provider: {name or '<blank>'}")
    return factory(vision)


register_model_provider("azure", lambda vision: AzureOpenAIProvider(vision=vision))
register_model_provider("openrouter", lambda vision: OpenRouterProvider(vision=vision))
register_model_provider("groq", lambda vision: GroqProvider(vision=vision))
register_model_provider("ollama", lambda vision: OllamaProvider(vision=vision))


__all__ = [
    "AzureOpenAIProvider",
    "GroqProvider",
    "ModelIdentity",
    "ModelInvocationResult",
    "ModelProvider",
    "ModelStreamChunk",
    "OllamaProvider",
    "OpenRouterProvider",
    "ProviderCapabilities",
    "ProviderCapabilityError",
    "ProviderConfigurationError",
    "ProviderInvocationError",
    "TokenUsage",
    "configured_provider_name",
    "get_model_provider",
    "register_model_provider",
]
