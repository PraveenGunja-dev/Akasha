import os
import sys
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine.model_provider import (  # noqa: E402
    AzureOpenAIProvider,
    GroqProvider,
    ModelProvider,
    OllamaProvider,
    OpenRouterProvider,
    ProviderCapabilities,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderInvocationError,
    configured_provider_name,
    get_model_provider,
)


class StubProvider(ModelProvider):
    name = "stub"

    def __init__(self, client, capabilities=None):
        super().__init__(
            model="configured-model",
            capabilities=capabilities or ProviderCapabilities(True, True, True, False),
        )
        self._client = client

    def _build_client(self):
        return self._client

    def chat_model(self, **_kwargs):
        raise NotImplementedError


def completion(*, content="answer", model="served-model", usage=None):
    message = SimpleNamespace(content=content, tool_calls=[])
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        model=model,
        usage=usage,
    )


class ModelProviderTests(unittest.TestCase):
    def test_provider_identity_is_normalized_and_unknown_provider_is_strict(self):
        with patch.dict(os.environ, {"AI_PROVIDER": " Azure_OpenAI "}, clear=False):
            self.assertEqual(configured_provider_name(), "azure")
        with self.assertRaisesRegex(ProviderConfigurationError, "Unsupported AI provider"):
            get_model_provider("not-a-provider")

    def test_ollama_is_selected_only_when_explicitly_configured_or_defaulted(self):
        with patch.dict(os.environ, {"AI_PROVIDER": "ollama", "OLLAMA_MODEL": "local/model"}):
            provider = get_model_provider()
        self.assertIsInstance(provider, OllamaProvider)
        self.assertEqual(provider.identity.provider, "ollama")
        self.assertEqual(provider.identity.model, "local/model")

    def test_all_builtin_adapters_resolve_configuration_without_network(self):
        cases = [
            (
                "azure",
                {
                    "AZURE_OPENAI_DEPLOYMENT_NAME": "deployment",
                    "AZURE_OPENAI_ENDPOINT": "https://azure.invalid",
                    "AZURE_OPENAI_API_KEY": "test-key",
                    "AZURE_OPENAI_API_VERSION": "2024-10-21",
                },
                AzureOpenAIProvider,
                "deployment",
            ),
            (
                "openrouter",
                {"OPENROUTER_MODEL": "primary/model", "OPENROUTER_API_KEY": "test-key"},
                OpenRouterProvider,
                "primary/model",
            ),
            (
                "groq",
                {"GROQ_MODEL": "groq/model", "AKASHA_AI_API_KEY": "test-key"},
                GroqProvider,
                "groq/model",
            ),
            (
                "ollama",
                {"OLLAMA_MODEL": "local/model"},
                OllamaProvider,
                "local/model",
            ),
        ]
        for name, environment, provider_type, model in cases:
            with self.subTest(provider=name), patch.dict(os.environ, environment, clear=True):
                provider = get_model_provider(name)
                self.assertIsInstance(provider, provider_type)
                self.assertEqual(provider.identity.model, model)

    def test_openrouter_vision_does_not_route_to_text_fallbacks(self):
        environment = {
            "OPENROUTER_MODEL": "text/model",
            "OPENROUTER_VISION_MODEL": "vision/model",
            "OPENROUTER_FALLBACK_MODELS": "fallback/a,fallback/b",
            "OPENROUTER_API_KEY": "test-key",
        }
        with patch.dict(os.environ, environment, clear=True):
            provider = get_model_provider("openrouter", vision=True)
            options = provider._completion_options()
        self.assertEqual(options, {"extra_body": {"provider": {"require_parameters": True}}})

    def test_ollama_graph_capabilities_require_explicit_approval(self):
        with patch.dict(os.environ, {"OLLAMA_MODEL": "local/model"}, clear=True):
            provider = get_model_provider("ollama")
            with self.assertRaises(ProviderCapabilityError):
                provider.require_capabilities("tool_calling", "structured_json")

        environment = {
            "OLLAMA_MODEL": "local/model",
            "OLLAMA_SUPPORTS_TOOL_CALLING": "true",
            "OLLAMA_SUPPORTS_STRUCTURED_JSON": "true",
        }
        with patch.dict(os.environ, environment, clear=True):
            provider = get_model_provider("ollama")
            provider.require_capabilities("tool_calling", "structured_json")

    def test_json_mode_and_retry_configuration_are_forwarded_without_network(self):
        create = Mock(return_value=completion())
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        provider = StubProvider(client)

        result = provider.invoke(
            [{"role": "user", "content": "question"}],
            json_mode=True,
            temperature=0.1,
            max_tokens=123,
        )

        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(kwargs["max_tokens"], 123)
        self.assertEqual(result.identity.model, "served-model")

    def test_invoke_normalizes_token_usage(self):
        response = completion(
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18)
        )
        create = Mock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

        result = StubProvider(client).invoke([{"role": "user", "content": "question"}])

        self.assertEqual(result.content, "answer")
        self.assertEqual(result.usage.input_tokens, 11)
        self.assertEqual(result.usage.output_tokens, 7)
        self.assertEqual(result.usage.total_tokens, 18)

    def test_explicit_unsupported_capability_fails_before_client_call(self):
        create = Mock()
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        provider = StubProvider(
            client,
            ProviderCapabilities(False, False, True, False),
        )

        with self.assertRaises(ProviderCapabilityError):
            provider.invoke([{"role": "user", "content": "question"}], json_mode=True)
        with self.assertRaises(ProviderCapabilityError):
            provider.invoke(
                [{"role": "user", "content": "question"}],
                tools=[{"type": "function"}],
            )
        self.assertFalse(create.called)

    def test_vision_requires_explicit_model_or_capability_configuration(self):
        with patch.dict(os.environ, {"OLLAMA_MODEL": "text-only"}, clear=True):
            with self.assertRaises(ProviderCapabilityError):
                get_model_provider("ollama", vision=True)

    def test_provider_failure_is_categorized_and_message_is_sanitized(self):
        create = Mock(side_effect=ValueError("secret upstream response"))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

        with self.assertRaises(ProviderInvocationError) as raised:
            StubProvider(client).invoke([{"role": "user", "content": "question"}])

        self.assertEqual(raised.exception.code, "chat_stream_failed")
        self.assertNotIn("secret", str(raised.exception))
        self.assertIsInstance(raised.exception.__cause__, ValueError)

    def test_stream_returns_normalized_chunks_without_network(self):
        chunks = [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="one"))],
                model="served-model",
                usage=None,
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=" two"))],
                model="served-model",
                usage=SimpleNamespace(prompt_tokens=2, completion_tokens=2, total_tokens=4),
            ),
        ]
        create = Mock(return_value=iter(chunks))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

        result = list(StubProvider(client).stream([{"role": "user", "content": "question"}]))

        self.assertEqual([chunk.content for chunk in result], ["one", " two"])
        self.assertEqual(result[-1].identity.model, "served-model")
        self.assertEqual(result[-1].usage.total_tokens, 4)
        self.assertTrue(create.call_args.kwargs["stream"])


if __name__ == "__main__":
    unittest.main()
