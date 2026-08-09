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
    ModelRouter,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
    ProviderCapabilities,
    ProviderCapabilityError,
    ProviderConfigurationError,
    ProviderInvocationError,
    TransientFallbackChatModel,
    configured_provider_name,
    get_model_provider,
)


class StubProvider(ModelProvider):
    name = "stub"

    def __init__(self, client, capabilities=None, *, name="stub"):
        self.name = name
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


def responses_response(*, content="answer", model="served-model", usage=None, output=None):
    if output is None:
        output = [
            SimpleNamespace(
                type="message",
                id="msg_1",
                content=[SimpleNamespace(type="output_text", text=content)],
            )
        ]
    return SimpleNamespace(
        output=output,
        output_text=content,
        model=model,
        usage=usage,
    )


class ModelProviderTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()

    def tearDown(self):
        self.environment.stop()

    def test_provider_identity_is_normalized_and_unknown_provider_is_strict(self):
        with patch.dict(os.environ, {"AI_PROVIDER": " Azure_OpenAI "}, clear=False):
            self.assertEqual(configured_provider_name(), "azure")
        with self.assertRaisesRegex(ProviderConfigurationError, "Unsupported AI provider"):
            get_model_provider("not-a-provider")

    def test_blank_model_provider_fails_instead_of_using_legacy_setting(self):
        with patch.dict(
            os.environ,
            {"MODEL_PROVIDER": " ", "AI_PROVIDER": "openrouter"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                ProviderConfigurationError,
                "MODEL_PROVIDER must be openrouter or openai",
            ):
                get_model_provider()

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
                "openai",
                {"OPENAI_MODEL": "gpt-test", "OPENAI_API_KEY": "test-key"},
                OpenAIProvider,
                "gpt-test",
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

    def test_model_provider_setting_builds_primary_and_automatic_fallback(self):
        environment = {
            "MODEL_PROVIDER": "openrouter",
            "OPENROUTER_MODEL": "router/model",
            "OPENROUTER_API_KEY": "router-key",
            "OPENAI_MODEL": "gpt-test",
            "OPENAI_API_KEY": "openai-key",
        }
        with patch.dict(os.environ, environment, clear=True):
            provider = get_model_provider()

        self.assertIsInstance(provider, ModelRouter)
        self.assertEqual(provider.primary.identity, provider.identity)
        self.assertEqual(provider.primary.name, "openrouter")
        self.assertEqual(provider.fallback.name, "openai")

    def test_switching_single_setting_reverses_primary_and_fallback(self):
        environment = {
            "MODEL_PROVIDER": "openai",
            "OPENROUTER_MODEL": "router/model",
            "OPENROUTER_API_KEY": "router-key",
            "OPENAI_MODEL": "gpt-test",
            "OPENAI_API_KEY": "openai-key",
        }
        with patch.dict(os.environ, environment, clear=True):
            provider = get_model_provider()

        self.assertEqual(provider.primary.name, "openai")
        self.assertEqual(provider.fallback.name, "openrouter")

    def test_openai_uses_responses_api_and_provider_specific_options(self):
        create = Mock(return_value=responses_response())
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        with patch.dict(
            os.environ,
            {"OPENAI_MODEL": "gpt-test", "OPENAI_API_KEY": "test-key"},
            clear=True,
        ):
            provider = OpenAIProvider()
        provider._client = client

        provider.invoke([{"role": "user", "content": "question"}], max_tokens=321)

        self.assertEqual(create.call_args.kwargs["model"], "gpt-test")
        self.assertEqual(create.call_args.kwargs["max_output_tokens"], 321)
        self.assertEqual(
            create.call_args.kwargs["input"],
            [{
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "question"}],
            }],
        )
        self.assertFalse(create.call_args.kwargs["store"])
        self.assertFalse(create.call_args.kwargs["stream"])
        self.assertNotIn("messages", create.call_args.kwargs)

    def test_openai_omits_temperature_when_model_profile_rejects_it(self):
        create = Mock(return_value=responses_response())
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        with patch.dict(
            os.environ,
            {"OPENAI_MODEL": "gpt-5.6-luna", "OPENAI_API_KEY": "test-key"},
            clear=True,
        ):
            provider = OpenAIProvider()
        provider._client = client

        provider.invoke(
            [{"role": "user", "content": "question"}],
            temperature=0.2,
        )
        chat_model = provider.chat_model(temperature=0.2)

        self.assertFalse(provider.model_profile["temperature"])
        self.assertNotIn("temperature", create.call_args.kwargs)
        self.assertIsNone(chat_model.temperature)
        self.assertTrue(chat_model.use_responses_api)
        self.assertFalse(chat_model.use_previous_response_id)
        self.assertFalse(chat_model.store)
        self.assertEqual(chat_model.reasoning, {"effort": "medium"})

    def test_openai_langgraph_model_builds_stateless_responses_tool_round_trip(self):
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        with patch.dict(
            os.environ,
            {"OPENAI_MODEL": "gpt-5.6-luna", "OPENAI_API_KEY": "test-key"},
            clear=True,
        ):
            model = OpenAIProvider().chat_model(max_tokens=123)

        payload = model._get_request_payload([
            HumanMessage(content="Find the project"),
            AIMessage(
                content="",
                tool_calls=[{"name": "lookup", "args": {"id": 1}, "id": "call_1"}],
            ),
            ToolMessage(content='{"name":"Alpha"}', tool_call_id="call_1"),
        ])

        self.assertEqual(payload["max_output_tokens"], 123)
        self.assertEqual(payload["reasoning"], {"effort": "medium"})
        self.assertFalse(payload["store"])
        self.assertNotIn("previous_response_id", payload)
        self.assertIn(
            {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": '{"name":"Alpha"}',
            },
            payload["input"],
        )

    def test_openai_keeps_temperature_when_model_profile_supports_it(self):
        create = Mock(return_value=responses_response())
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        with patch.dict(
            os.environ,
            {"OPENAI_MODEL": "gpt-4.1-mini", "OPENAI_API_KEY": "test-key"},
            clear=True,
        ):
            provider = OpenAIProvider()
        provider._client = client

        provider.invoke(
            [{"role": "user", "content": "question"}],
            temperature=0.2,
        )
        chat_model = provider.chat_model(temperature=0.2)

        self.assertTrue(provider.model_profile["temperature"])
        self.assertEqual(create.call_args.kwargs["temperature"], 0.2)
        self.assertEqual(chat_model.temperature, 0.2)

    def test_openai_normalizes_tool_calls_and_replays_tool_outputs_with_call_id(self):
        reasoning = SimpleNamespace(
            type="reasoning",
            id="rs_1",
            encrypted_content="opaque",
            model_dump=lambda **_kwargs: {
                "type": "reasoning",
                "id": "rs_1",
                "encrypted_content": "opaque",
            },
        )
        function_call = SimpleNamespace(
            type="function_call",
            id="fc_1",
            call_id="call_1",
            name="lookup_project",
            arguments='{"name":"Alpha"}',
            model_dump=lambda **_kwargs: {
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call_1",
                "name": "lookup_project",
                "arguments": '{"name":"Alpha"}',
            },
        )
        first = responses_response(content="", output=[reasoning, function_call])
        second = responses_response(content="done")
        create = Mock(side_effect=[first, second])
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        with patch.dict(
            os.environ,
            {"OPENAI_MODEL": "gpt-5.6-luna", "OPENAI_API_KEY": "test-key"},
            clear=True,
        ):
            provider = OpenAIProvider()
        provider._client = client

        initial = [{"role": "user", "content": "Find Alpha"}]
        result = provider.invoke(
            initial,
            tools=[{
                "type": "function",
                "function": {
                    "name": "lookup_project",
                    "description": "Find a project",
                    "parameters": {"type": "object"},
                },
            }],
        )
        self.assertEqual(result.message.tool_calls[0].id, "call_1")
        self.assertEqual(result.message.tool_calls[0].function.name, "lookup_project")

        provider.invoke([
            *initial,
            result.message,
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "name": "lookup_project",
                "content": '{"id": 7}',
            },
        ])

        replay = create.call_args.kwargs["input"]
        self.assertEqual(replay[1]["type"], "reasoning")
        self.assertEqual(replay[2]["call_id"], "call_1")
        self.assertEqual(replay[3], {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": '{"id": 7}',
        })
        # Provider-private replay data is not part of the provider-neutral message dump.
        self.assertNotIn("_responses_items", result.message.model_dump())

    def test_openai_translates_json_tools_and_vision_request_shapes(self):
        create = Mock(return_value=responses_response(content='{"ok":true}'))
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        with patch.dict(
            os.environ,
            {
                "OPENAI_MODEL": "gpt-5.6-luna",
                "OPENAI_API_KEY": "test-key",
                "OPENAI_SUPPORTS_VISION": "true",
            },
            clear=True,
        ):
            provider = OpenAIProvider(vision=True)
        provider._client = client

        provider.invoke(
            [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Inspect"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,abc", "detail": "high"},
                    },
                ],
            }],
            json_mode=True,
            vision=True,
            tools=[{
                "type": "function",
                "function": {
                    "name": "record",
                    "parameters": {"type": "object"},
                    "strict": True,
                },
            }],
            tool_choice={"type": "function", "function": {"name": "record"}},
        )

        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["text"], {"format": {"type": "json_object"}})
        self.assertEqual(kwargs["tools"][0]["name"], "record")
        self.assertNotIn("function", kwargs["tools"][0])
        self.assertEqual(kwargs["tool_choice"], {"type": "function", "name": "record"})
        self.assertEqual(kwargs["input"][0]["content"][1], {
            "type": "input_image",
            "image_url": "data:image/png;base64,abc",
            "detail": "high",
        })

    def test_openai_stream_normalizes_text_tool_deltas_and_usage(self):
        events = [
            SimpleNamespace(type="response.output_text.delta", delta="one"),
            SimpleNamespace(
                type="response.output_item.added",
                output_index=1,
                item=SimpleNamespace(
                    type="function_call",
                    call_id="call_1",
                    name="lookup",
                    arguments="",
                ),
            ),
            SimpleNamespace(
                type="response.function_call_arguments.delta",
                output_index=1,
                delta='{"id":',
            ),
            SimpleNamespace(
                type="response.completed",
                response=responses_response(
                    content="one",
                    usage=SimpleNamespace(input_tokens=2, output_tokens=3, total_tokens=5),
                ),
            ),
        ]
        create = Mock(return_value=iter(events))
        client = SimpleNamespace(responses=SimpleNamespace(create=create))
        with patch.dict(
            os.environ,
            {"OPENAI_MODEL": "gpt-test", "OPENAI_API_KEY": "test-key"},
            clear=True,
        ):
            provider = OpenAIProvider()
        provider._client = client

        chunks = list(provider.stream([{"role": "user", "content": "question"}]))

        self.assertEqual([chunk.content for chunk in chunks], ["one", None, None, None])
        self.assertEqual(chunks[-1].usage.total_tokens, 5)
        self.assertTrue(create.call_args.kwargs["stream"])

    def test_router_falls_back_only_for_transient_failures(self):
        primary_create = Mock(
            side_effect=ProviderInvocationError("provider_unavailable", "temporarily unavailable")
        )
        fallback_create = Mock(return_value=completion(content="fallback answer"))
        primary = StubProvider(
            SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=primary_create))),
            name="primary",
        )
        fallback = StubProvider(
            SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fallback_create))),
            name="fallback",
        )

        result = ModelRouter(primary, fallback).invoke(
            [{"role": "user", "content": "question"}]
        )

        self.assertEqual(result.content, "fallback answer")
        self.assertEqual(result.identity.provider, "fallback")
        fallback_create.reset_mock()
        primary_create.side_effect = ProviderInvocationError(
            "provider_authentication_failed",
            "authentication failed",
        )
        with self.assertRaises(ProviderInvocationError):
            ModelRouter(primary, fallback).invoke(
                [{"role": "user", "content": "question"}]
            )
        fallback_create.assert_not_called()

    def test_openai_responses_failure_falls_back_to_openrouter_chat_completions(self):
        openai_create = Mock(
            side_effect=ProviderInvocationError("provider_unavailable", "temporarily unavailable")
        )
        openrouter_create = Mock(return_value=completion(content="fallback answer"))
        environment = {
            "OPENAI_MODEL": "gpt-5.6-luna",
            "OPENAI_API_KEY": "openai-key",
            "OPENROUTER_MODEL": "router/model",
            "OPENROUTER_API_KEY": "router-key",
        }
        with patch.dict(os.environ, environment, clear=True):
            primary = OpenAIProvider()
            fallback = OpenRouterProvider()
        primary._client = SimpleNamespace(responses=SimpleNamespace(create=openai_create))
        fallback._client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=openrouter_create))
        )

        result = ModelRouter(primary, fallback).invoke(
            [{"role": "user", "content": "question"}]
        )

        self.assertEqual(result.content, "fallback answer")
        self.assertEqual(result.identity.provider, "openrouter")
        openai_create.assert_called_once()
        openrouter_create.assert_called_once()
        self.assertIn("messages", openrouter_create.call_args.kwargs)
        self.assertNotIn("input", openrouter_create.call_args.kwargs)

    def test_langchain_model_retries_transient_failure(self):
        from langchain_core.messages import AIMessage, HumanMessage

        primary = SimpleNamespace(
            invoke=Mock(
                side_effect=ProviderInvocationError(
                    "provider_rate_limited",
                    "rate limited",
                )
            )
        )
        fallback = SimpleNamespace(invoke=Mock(return_value=AIMessage(content="fallback")))
        model = TransientFallbackChatModel(
            primary=primary,
            fallback=fallback,
            primary_name="openrouter",
            fallback_name="openai",
        )

        response = model.invoke([HumanMessage(content="question")])

        self.assertEqual(response.content, "fallback")
        fallback.invoke.assert_called_once()

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
