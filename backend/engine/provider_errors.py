"""Map provider failures to stable, payload-safe client errors."""

from dataclasses import dataclass

import openai
from langgraph.errors import GraphRecursionError


@dataclass(frozen=True)
class PublicProviderError:
    code: str
    message: str


def classify_provider_error(exc: BaseException) -> PublicProviderError:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, openai.RateLimitError):
            return PublicProviderError(
                "provider_rate_limited",
                "All configured AI models are currently rate limited. Please retry later.",
            )
        if isinstance(current, GraphRecursionError):
            return PublicProviderError(
                "agent_iteration_limit",
                "The analysis could not complete within the configured tool-call limit. Try a narrower scope.",
            )
        if isinstance(current, openai.AuthenticationError):
            return PublicProviderError(
                "provider_authentication_failed",
                "The configured AI provider could not authenticate the request.",
            )
        if isinstance(current, openai.NotFoundError):
            return PublicProviderError(
                "provider_route_unavailable",
                "No configured AI model route could serve this request.",
            )
        if isinstance(current, (openai.APITimeoutError, openai.APIConnectionError)):
            return PublicProviderError(
                "provider_unavailable",
                "The configured AI provider is temporarily unavailable.",
            )
        if isinstance(current, openai.APIStatusError) and current.status_code >= 500:
            return PublicProviderError(
                "provider_unavailable",
                "The configured AI provider is temporarily unavailable.",
            )
        current = current.__cause__ or current.__context__
    return PublicProviderError(
        "chat_stream_failed",
        "The chat response could not be completed.",
    )


def is_transient_provider_error(exc: BaseException) -> bool:
    """Return whether a provider failure is safe to retry on another provider."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if getattr(current, "code", None) in {
            "provider_rate_limited",
            "provider_unavailable",
        }:
            return True
        if isinstance(
            current,
            (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError),
        ):
            return True
        if isinstance(current, openai.APIStatusError) and current.status_code >= 500:
            return True
        current = current.__cause__ or current.__context__
    return False
