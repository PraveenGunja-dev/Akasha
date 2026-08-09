"""Configured model-provider registry and normalized invocation API."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
import os
from typing import Any, Callable, Iterable, Iterator, Mapping

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import ConfigDict

from engine.openrouter_config import (
    OpenRouterChatModel,
    openrouter_extra_body,
    openrouter_model_ids,
)
from engine.provider_errors import classify_provider_error, is_transient_provider_error


DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_RETRIES = 2
ROUTED_PROVIDERS = ("openrouter", "openai")

logger = logging.getLogger(__name__)


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


def _item_value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _item_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, Mapping):
        return dict(item)
    model_dump = getattr(item, "model_dump", None)
    if callable(model_dump):
        return model_dump(exclude_none=True, mode="json")
    return {
        name: value
        for name, value in vars(item).items()
        if not name.startswith("_")
    }


def _responses_content_blocks(content: Any, *, assistant: bool = False) -> list[dict[str, Any]]:
    """Translate Chat Completions content blocks to Responses message content."""
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": "output_text" if assistant else "input_text", "text": content}]

    blocks = []
    for block in content:
        if not isinstance(block, Mapping):
            continue
        block_type = block.get("type")
        if block_type in {"input_text", "input_image", "input_file"}:
            blocks.append(dict(block))
        elif block_type in {"text", "output_text"} and block.get("text") is not None:
            blocks.append(
                {
                    "type": "output_text" if assistant else "input_text",
                    "text": str(block["text"]),
                }
            )
        elif block_type == "image_url":
            image = block.get("image_url")
            if isinstance(image, Mapping):
                image_url = image.get("url")
                detail = image.get("detail")
            else:
                image_url = image
                detail = None
            if image_url:
                converted = {"type": "input_image", "image_url": image_url}
                if detail:
                    converted["detail"] = detail
                blocks.append(converted)
        elif block_type == "file":
            file_value = block.get("file")
            if isinstance(file_value, Mapping):
                blocks.append({"type": "input_file", **file_value})
    return blocks


def _responses_input(messages: list[Any]) -> list[dict[str, Any]]:
    """Build stateless Responses input while retaining provider-neutral chat history."""
    result: list[dict[str, Any]] = []
    for message in messages:
        role = _item_value(message, "role") or _item_value(message, "type")
        if role == "bot":
            role = "assistant"

        if role == "tool":
            result.append(
                {
                    "type": "function_call_output",
                    "call_id": _item_value(message, "tool_call_id"),
                    "output": _item_value(message, "content", ""),
                }
            )
            continue

        if role == "assistant":
            # Responses output items are private replay metadata. Pydantic excludes
            # underscore attributes when the normalized message is sent to OpenRouter.
            response_items = getattr(message, "_responses_items", None)
            if response_items:
                result.extend(dict(item) for item in response_items)
                continue

            content = _responses_content_blocks(
                _item_value(message, "content"),
                assistant=True,
            )
            if content:
                result.append({"type": "message", "role": "assistant", "content": content})
            for tool_call in _item_value(message, "tool_calls", None) or []:
                function = _item_value(tool_call, "function", {})
                result.append(
                    {
                        "type": "function_call",
                        "call_id": _item_value(tool_call, "id"),
                        "name": _item_value(function, "name"),
                        "arguments": _item_value(function, "arguments", "{}"),
                    }
                )
            continue

        if role in {"system", "developer", "user"}:
            content = _responses_content_blocks(_item_value(message, "content"))
            if content:
                result.append({"type": "message", "role": role, "content": content})
            continue

        if isinstance(message, Mapping) and message.get("type"):
            result.append(dict(message))
    return result


def _validate_function_tools(tools: list[dict[str, Any]]) -> tuple[str, ...]:
    """Fail closed if a provider would receive a partial or malformed tool catalog."""
    names = []
    for tool in tools:
        function = tool.get("function") if isinstance(tool, Mapping) else None
        if tool.get("type") != "function" or not isinstance(function, Mapping):
            raise ProviderConfigurationError("Akasha model tools must use function-tool schemas.")
        name = str(function.get("name") or "").strip()
        parameters = function.get("parameters")
        if not name or not isinstance(parameters, Mapping):
            raise ProviderConfigurationError(
                "Every Akasha model tool requires a name and JSON-schema parameters."
            )
        if name in names:
            raise ProviderConfigurationError(f"Duplicate model tool name: {name}")
        names.append(name)
    return tuple(names)


def _responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected_names = _validate_function_tools(tools)
    converted = []
    for tool in tools:
        if tool.get("type") == "function" and isinstance(tool.get("function"), Mapping):
            converted.append({"type": "function", **dict(tool["function"])})
        else:
            converted.append(dict(tool))
    converted_names = tuple(str(tool.get("name") or "") for tool in converted)
    if converted_names != expected_names:
        raise ProviderConfigurationError(
            "OpenAI tool-schema translation changed the canonical tool catalog."
        )
    return converted


def _responses_tool_choice(choice: str | dict[str, Any]) -> str | dict[str, Any]:
    if (
        isinstance(choice, Mapping)
        and choice.get("type") == "function"
        and isinstance(choice.get("function"), Mapping)
    ):
        return {"type": "function", **dict(choice["function"])}
    return choice


def _stateless_response_items(items: Iterable[Any]) -> list[dict[str, Any]]:
    replay = []
    for item in items:
        value = _item_dict(item)
        item_type = value.get("type")
        if item_type == "message":
            value.pop("id", None)
        elif item_type == "reasoning" and not value.get("encrypted_content"):
            continue
        replay.append(value)
    return replay


class ModelProvider(ABC):
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

    @abstractmethod
    def _build_client(self):
        """Create the provider SDK client lazily."""

    def client(self):
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _completion_options(self) -> dict[str, Any]:
        return {}

    def _temperature_options(self, temperature: float) -> dict[str, float]:
        return {"temperature": temperature}

    def _token_limit_options(self, max_tokens: int) -> dict[str, int]:
        return {"max_tokens": max_tokens}

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
        if tools:
            _validate_function_tools(tools)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            **self._temperature_options(temperature),
            **self._token_limit_options(max_tokens),
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

    @abstractmethod
    def chat_model(
        self,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> BaseChatModel:
        """Return the LangChain view used by the chat graph."""

    def discover_context_window(self, required_capabilities: Iterable[str] = ()) -> int | None:
        return None


class TransientFallbackChatModel(BaseChatModel):
    """LangChain chat model that retries a call once on the alternate provider."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    primary: Any
    fallback: Any
    primary_name: str
    fallback_name: str

    @property
    def _llm_type(self) -> str:
        return "akasha-provider-router"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "primary_provider": self.primary_name,
            "fallback_provider": self.fallback_name,
        }

    def _invoke_with_fallback(self, messages, *, stop=None, **kwargs):
        try:
            return self.primary.invoke(messages, stop=stop, **kwargs)
        except Exception as exc:
            if not is_transient_provider_error(exc):
                raise
            logger.warning(
                "Model provider %s failed transiently; retrying with %s.",
                self.primary_name,
                self.fallback_name,
            )
            return self.fallback.invoke(messages, stop=stop, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        message = self._invoke_with_fallback(messages, stop=stop, **kwargs)
        return ChatResult(generations=[ChatGeneration(message=message)])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        emitted = False
        try:
            for message in self.primary.stream(messages, stop=stop, **kwargs):
                emitted = True
                yield ChatGenerationChunk(message=message)
            return
        except Exception as exc:
            if emitted or not is_transient_provider_error(exc):
                raise
            logger.warning(
                "Streaming provider %s failed before its first chunk; retrying with %s.",
                self.primary_name,
                self.fallback_name,
            )
        for message in self.fallback.stream(messages, stop=stop, **kwargs):
            yield ChatGenerationChunk(message=message)

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return TransientFallbackChatModel(
            primary=self.primary.bind_tools(
                tools,
                tool_choice=tool_choice,
                **kwargs,
            ),
            fallback=self.fallback.bind_tools(
                tools,
                tool_choice=tool_choice,
                **kwargs,
            ),
            primary_name=self.primary_name,
            fallback_name=self.fallback_name,
        )


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


class OpenAIProvider(ModelProvider):
    name = "openai"

    def __init__(self, *, vision: bool = False):
        primary = _required("OPENAI_MODEL")
        vision_model = os.getenv("OPENAI_VISION_MODEL", "").strip()
        vision_override = _optional_bool("OPENAI_SUPPORTS_VISION")
        if vision and not vision_model and vision_override is not True:
            raise ProviderCapabilityError(
                "Configure OPENAI_VISION_MODEL or enable OPENAI_SUPPORTS_VISION "
                "for vision requests."
            )
        super().__init__(
            model=vision_model if vision and vision_model else primary,
            capabilities=ProviderCapabilities(
                tool_calling=True,
                structured_json=True,
                streaming=True,
                vision=bool(vision_model) or vision_override is True,
            ),
        )
        self.api_key = _required("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
        self.model_profile = self._load_model_profile()
        configured_effort = os.getenv("OPENAI_REASONING_EFFORT", "").strip().lower()
        if not configured_effort and self.model.startswith("gpt-5.6"):
            configured_effort = "medium"
        supported_efforts = {"none", "low", "medium", "high", "xhigh", "max"}
        if configured_effort and configured_effort not in supported_efforts:
            raise ProviderConfigurationError(
                "OPENAI_REASONING_EFFORT must be none, low, medium, high, xhigh, or max."
            )
        self.reasoning = {"effort": configured_effort} if configured_effort else None

    def _load_model_profile(self) -> Mapping[str, Any]:
        from langchain_openai import ChatOpenAI

        options = {"model": self.model, "api_key": self.api_key}
        if self.base_url:
            options["base_url"] = self.base_url
        return getattr(ChatOpenAI(**options), "profile", None) or {}

    def _build_client(self):
        import openai

        options = {
            "api_key": self.api_key,
            "timeout": _timeout(),
            "max_retries": _max_retries(),
        }
        if self.base_url:
            options["base_url"] = self.base_url
        return openai.OpenAI(**options)

    def _temperature_options(self, temperature: float) -> dict[str, float]:
        if self.model_profile.get("temperature") is False or (
            self.reasoning and self.reasoning.get("effort") != "none"
        ):
            return {}
        return super()._temperature_options(temperature)

    def _request_options(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        stream: bool,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | dict[str, Any] | None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {
            "model": self.model,
            "input": _responses_input(messages),
            "max_output_tokens": max_tokens,
            "stream": stream,
            # Akasha owns history and manually replays output items. Do not make
            # checkpoints dependent on OpenAI's stored response identifiers.
            "store": False,
            **self._temperature_options(temperature),
        }
        if self.reasoning:
            options["reasoning"] = self.reasoning
        if json_mode:
            options["text"] = {"format": {"type": "json_object"}}
        if tools:
            options["tools"] = _responses_tools(tools)
            options["tool_choice"] = _responses_tool_choice(tool_choice or "auto")
        return options

    def _create_response(self, messages: list[dict[str, Any]], **kwargs):
        required = []
        if kwargs.get("json_mode"):
            required.append("structured_json")
        if kwargs.get("stream"):
            required.append("streaming")
        if kwargs.get("tools"):
            required.append("tool_calling")
        if kwargs.get("vision"):
            required.append("vision")
        self.require_capabilities(*required)
        if kwargs.get("tools"):
            _validate_function_tools(kwargs["tools"])

        options = self._request_options(
            messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
            json_mode=kwargs.get("json_mode", False),
            stream=kwargs.get("stream", False),
            tools=kwargs.get("tools"),
            tool_choice=kwargs.get("tool_choice"),
        )
        try:
            return self.client().responses.create(**options)
        except (ProviderConfigurationError, ProviderCapabilityError, ProviderInvocationError):
            raise
        except Exception as exc:
            public_error = classify_provider_error(exc)
            raise ProviderInvocationError(public_error.code, public_error.message) from exc

    @staticmethod
    def _message_from_response(response: Any):
        from openai.types.chat import ChatCompletionMessage, ChatCompletionMessageFunctionToolCall
        from openai.types.chat.chat_completion_message_function_tool_call import Function

        text = _item_value(response, "output_text") or ""
        output_items = _item_value(response, "output", []) or []
        tool_calls = []
        if not text:
            text_parts = []
            for item in output_items:
                if _item_value(item, "type") != "message":
                    continue
                for block in _item_value(item, "content", []) or []:
                    if _item_value(block, "type") == "output_text":
                        text_parts.append(str(_item_value(block, "text", "")))
                    elif _item_value(block, "type") == "refusal":
                        text_parts.append(str(_item_value(block, "refusal", "")))
            text = "".join(text_parts)
        for item in output_items:
            if _item_value(item, "type") == "function_call":
                tool_calls.append(
                    ChatCompletionMessageFunctionToolCall(
                        id=str(_item_value(item, "call_id")),
                        type="function",
                        function=Function(
                            name=str(_item_value(item, "name")),
                            arguments=str(_item_value(item, "arguments", "{}")),
                        ),
                    )
                )
        message = ChatCompletionMessage(
            role="assistant",
            content=text or None,
            tool_calls=tool_calls or None,
        )
        object.__setattr__(
            message,
            "_responses_items",
            _stateless_response_items(output_items),
        )
        return message

    @staticmethod
    def _completion_from_response(response: Any):
        from types import SimpleNamespace

        normalized = SimpleNamespace(
            choices=[SimpleNamespace(message=OpenAIProvider._message_from_response(response))],
            model=_response_model(response, ""),
            usage=_item_value(response, "usage"),
        )
        object.__setattr__(normalized, "_raw_response", response)
        return normalized

    @staticmethod
    def _normalized_stream_chunks(events: Iterable[Any], fallback_model: str):
        from types import SimpleNamespace

        for event in events:
            event_type = _item_value(event, "type", "")
            delta = SimpleNamespace(content=None, tool_calls=None)
            choices = []
            model = fallback_model
            usage = None
            if event_type == "response.output_text.delta":
                delta.content = _item_value(event, "delta")
                choices = [SimpleNamespace(delta=delta)]
            elif event_type == "response.refusal.delta":
                delta.content = _item_value(event, "delta")
                choices = [SimpleNamespace(delta=delta)]
            elif event_type == "response.output_text.annotation.added":
                delta.annotations = [_item_value(event, "annotation")]
                choices = [SimpleNamespace(delta=delta)]
            elif event_type == "response.output_item.added":
                item = _item_value(event, "item")
                if _item_value(item, "type") == "function_call":
                    delta.tool_calls = [SimpleNamespace(
                        index=_item_value(event, "output_index", 0),
                        id=_item_value(item, "call_id"),
                        type="function",
                        function=SimpleNamespace(
                            name=_item_value(item, "name"),
                            arguments=_item_value(item, "arguments", ""),
                        ),
                    )]
                    choices = [SimpleNamespace(delta=delta)]
            elif event_type == "response.function_call_arguments.delta":
                delta.tool_calls = [SimpleNamespace(
                    index=_item_value(event, "output_index", 0),
                    id=None,
                    type="function",
                    function=SimpleNamespace(
                        name=None,
                        arguments=_item_value(event, "delta", ""),
                    ),
                )]
                choices = [SimpleNamespace(delta=delta)]
            elif event_type in {"response.completed", "response.incomplete"}:
                response = _item_value(event, "response")
                model = _response_model(response, fallback_model)
                usage = _item_value(response, "usage")
            else:
                continue
            yield (
                SimpleNamespace(choices=choices, model=model, usage=usage),
                event,
            )

    def _response_stream(self, messages: list[dict[str, Any]], **kwargs):
        events = self._create_response(messages, stream=True, **kwargs)
        try:
            yield from self._normalized_stream_chunks(events, self.model)
        except ProviderInvocationError:
            raise
        except Exception as exc:
            public_error = classify_provider_error(exc)
            raise ProviderInvocationError(public_error.code, public_error.message) from exc

    def create_completion(self, messages: list[dict[str, Any]], **kwargs):
        stream_options = dict(kwargs)
        wants_stream = bool(stream_options.pop("stream", False))
        if wants_stream:
            return (chunk for chunk, _event in self._response_stream(messages, **stream_options))
        response = self._create_response(messages, stream=False, **stream_options)
        return self._completion_from_response(response)

    def invoke(self, messages: list[dict[str, Any]], **kwargs) -> ModelInvocationResult:
        response = self._create_response(messages, stream=False, **kwargs)
        message = self._message_from_response(response)
        return ModelInvocationResult(
            content=message.content,
            identity=ModelIdentity(self.name, _response_model(response, self.model)),
            usage=_token_usage(response),
            message=message,
            raw_response=response,
        )

    def stream(self, messages: list[dict[str, Any]], **kwargs) -> Iterator[ModelStreamChunk]:
        for chunk, event in self._response_stream(messages, **kwargs):
            choices = chunk.choices or []
            content = getattr(choices[0].delta, "content", None) if choices else None
            yield ModelStreamChunk(
                content=content,
                identity=ModelIdentity(self.name, _response_model(chunk, self.model)),
                usage=_token_usage(chunk),
                raw_chunk=event,
            )

    def chat_model(self, *, temperature: float = 0.2, max_tokens: int = 2048) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        options = {
            "model": self.model,
            "api_key": self.api_key,
            "max_completion_tokens": max_tokens,
            "timeout": _timeout(),
            "max_retries": _max_retries(),
            "use_responses_api": True,
            "use_previous_response_id": False,
            "store": False,
            **self._temperature_options(temperature),
        }
        if self.reasoning:
            options["reasoning"] = self.reasoning
        if self.base_url:
            options["base_url"] = self.base_url
        return ChatOpenAI(**options)

    def discover_context_window(self, required_capabilities: Iterable[str] = ()) -> int | None:
        value = self.model_profile.get("max_input_tokens")
        return int(value) if value else None


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


class ModelRouter(ModelProvider):
    """Deep module that hides primary selection and transient provider fallback."""

    name = "model-router"

    def __init__(self, primary: ModelProvider, fallback: ModelProvider):
        if primary.name == fallback.name:
            raise ProviderConfigurationError(
                "The primary and fallback model providers must be different."
            )
        capabilities = ProviderCapabilities(
            **{
                field: bool(getattr(primary.capabilities, field))
                and bool(getattr(fallback.capabilities, field))
                for field in ProviderCapabilities.__dataclass_fields__
            }
        )
        super().__init__(model=primary.model, capabilities=capabilities)
        self.primary = primary
        self.fallback = fallback

    @property
    def identity(self) -> ModelIdentity:
        return self.primary.identity

    def _build_client(self):
        raise RuntimeError("Use the model router interface instead of requesting its SDK client.")

    def _with_fallback(self, operation: Callable[[ModelProvider], Any]) -> Any:
        try:
            return operation(self.primary)
        except Exception as exc:
            if not is_transient_provider_error(exc):
                raise
            logger.warning(
                "Model provider %s failed transiently; retrying with %s.",
                self.primary.name,
                self.fallback.name,
            )
            return operation(self.fallback)

    def create_completion(self, messages: list[dict[str, Any]], **kwargs):
        if kwargs.get("stream"):
            return self._stream_raw(messages, **kwargs)
        return self._with_fallback(
            lambda provider: provider.create_completion(messages, **kwargs)
        )

    def _stream_raw(self, messages: list[dict[str, Any]], **kwargs):
        emitted = False
        try:
            chunks = self.primary.create_completion(messages, **kwargs)
            for chunk in chunks:
                emitted = True
                yield chunk
            return
        except Exception as exc:
            if emitted or not is_transient_provider_error(exc):
                raise
            logger.warning(
                "Streaming provider %s failed before its first chunk; retrying with %s.",
                self.primary.name,
                self.fallback.name,
            )
        yield from self.fallback.create_completion(messages, **kwargs)

    def invoke(self, messages: list[dict[str, Any]], **kwargs) -> ModelInvocationResult:
        return self._with_fallback(lambda provider: provider.invoke(messages, **kwargs))

    def stream(self, messages: list[dict[str, Any]], **kwargs) -> Iterator[ModelStreamChunk]:
        emitted = False
        try:
            for chunk in self.primary.stream(messages, **kwargs):
                emitted = True
                yield chunk
            return
        except Exception as exc:
            if emitted or not is_transient_provider_error(exc):
                raise
            logger.warning(
                "Streaming provider %s failed before its first chunk; retrying with %s.",
                self.primary.name,
                self.fallback.name,
            )
        yield from self.fallback.stream(messages, **kwargs)

    def chat_model(self, *, temperature: float = 0.2, max_tokens: int = 2048) -> BaseChatModel:
        return TransientFallbackChatModel(
            primary=self.primary.chat_model(
                temperature=temperature,
                max_tokens=max_tokens,
            ),
            fallback=self.fallback.chat_model(
                temperature=temperature,
                max_tokens=max_tokens,
            ),
            primary_name=self.primary.name,
            fallback_name=self.fallback.name,
        )

    def validate_chat_model_capabilities(
        self,
        model: BaseChatModel,
        *capabilities: str,
    ) -> None:
        self.require_capabilities(*capabilities)
        if isinstance(model, TransientFallbackChatModel):
            self.primary.validate_chat_model_capabilities(
                model.primary,
                *capabilities,
            )
            self.fallback.validate_chat_model_capabilities(
                model.fallback,
                *capabilities,
            )

    def discover_context_window(self, required_capabilities: Iterable[str] = ()) -> int | None:
        required = tuple(required_capabilities)
        self.primary.require_capabilities(*required)
        self.fallback.require_capabilities(*required)
        windows = {
            self.primary.name: self.primary.discover_context_window(required),
            self.fallback.name: self.fallback.discover_context_window(required),
        }
        missing = [name for name, window in windows.items() if not window]
        if missing:
            raise ProviderConfigurationError(
                "Context-window metadata is unavailable for the configured "
                f"{', '.join(missing)} model. Select a model whose provider metadata is known."
            )
        return min(int(window) for window in windows.values() if window)


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
    if provider is not None:
        configured = provider
    elif "MODEL_PROVIDER" in os.environ:
        configured = os.getenv("MODEL_PROVIDER", "")
    else:
        configured = os.getenv("AI_PROVIDER", "openrouter")
    name = configured.strip().lower()
    return _PROVIDER_ALIASES.get(name, name)


def configured_fallback_provider_name(primary: str) -> str:
    configured = os.getenv("MODEL_FALLBACK_PROVIDER", "auto").strip().lower()
    if configured in {"", "auto"}:
        return next(name for name in ROUTED_PROVIDERS if name != primary)
    name = _PROVIDER_ALIASES.get(configured, configured)
    if name not in ROUTED_PROVIDERS:
        raise ProviderConfigurationError(
            "MODEL_FALLBACK_PROVIDER must be auto, openrouter, or openai."
        )
    if name == primary:
        raise ProviderConfigurationError(
            "MODEL_FALLBACK_PROVIDER must differ from MODEL_PROVIDER."
        )
    return name


def _build_provider(name: str, *, vision: bool) -> ModelProvider:
    factory = _PROVIDER_REGISTRY.get(name)
    if factory is None:
        raise ProviderConfigurationError(f"Unsupported AI provider: {name or '<blank>'}")
    return factory(vision)


def get_model_provider(provider: str | None = None, *, vision: bool = False) -> ModelProvider:
    name = configured_provider_name(provider)
    if provider is not None or "MODEL_PROVIDER" not in os.environ:
        return _build_provider(name, vision=vision)
    if name not in ROUTED_PROVIDERS:
        raise ProviderConfigurationError(
            "MODEL_PROVIDER must be openrouter or openai."
        )
    fallback_name = configured_fallback_provider_name(name)
    return ModelRouter(
        _build_provider(name, vision=vision),
        _build_provider(fallback_name, vision=vision),
    )


def validate_model_configuration() -> ModelProvider:
    """Fail startup when the selected chat route is incomplete or incapable."""
    provider = get_model_provider()
    provider.require_capabilities("tool_calling", "structured_json", "streaming")
    return provider


register_model_provider("azure", lambda vision: AzureOpenAIProvider(vision=vision))
register_model_provider("openrouter", lambda vision: OpenRouterProvider(vision=vision))
register_model_provider("openai", lambda vision: OpenAIProvider(vision=vision))
register_model_provider("groq", lambda vision: GroqProvider(vision=vision))
register_model_provider("ollama", lambda vision: OllamaProvider(vision=vision))


__all__ = [
    "AzureOpenAIProvider",
    "GroqProvider",
    "ModelIdentity",
    "ModelInvocationResult",
    "ModelProvider",
    "ModelRouter",
    "ModelStreamChunk",
    "OllamaProvider",
    "OpenAIProvider",
    "OpenRouterProvider",
    "ProviderCapabilities",
    "ProviderCapabilityError",
    "ProviderConfigurationError",
    "ProviderInvocationError",
    "TokenUsage",
    "configured_provider_name",
    "configured_fallback_provider_name",
    "get_model_provider",
    "register_model_provider",
    "validate_model_configuration",
]
