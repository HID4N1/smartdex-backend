from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import openai
from chromadb.errors import NotFoundError
from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIClient

from apps.chatbot.models import Conversation
from apps.devis.models import DevisRequest
from apps.devis.services.llm_service import LLMService
from core.ai.provider import (
    AIAuthenticationError,
    AIConnectionError,
    AIConfigurationError,
    AIConnectTimeoutError,
    AIDeadlineExceededError,
    AIInputLimitError,
    AIInvalidRequestError,
    AIMalformedResponseError,
    AIRateLimitError,
    AIReadTimeoutError,
    AIUnavailableError,
    AIOperationRunner,
    AIRetryPolicy,
    build_openai_client,
    chat_completion_text,
    create_embeddings,
    enforce_input_limit,
)
from core.utils.exception_handlers import public_exception_handler


def response_error(error_class, status_code, *, retry_after=None):
    headers = {"retry-after": str(retry_after)} if retry_after is not None else {}
    response = httpx.Response(
        status_code,
        headers=headers,
        request=httpx.Request("POST", "https://api.openai.test/v1/mock"),
    )
    return error_class("provider failure", response=response, body={})


def retry_policy(*, retries=1, timeout=1.0, deadline=5.0, delay=0.0):
    return AIRetryPolicy(
        request_timeout=timeout,
        operation_deadline=deadline,
        max_retries=retries,
        base_delay=delay,
        max_delay=delay,
    )


class ExternalAIReliabilityTests(SimpleTestCase):
    def runner(self, **kwargs):
        return AIOperationRunner(
            policy=retry_policy(**kwargs),
            sleep=lambda _delay: None,
            jitter=lambda _low, high: high,
            allow_calls=True,
        )

    def test_successful_chat_completion_enforces_output_tokens(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Safe answer"))]
        )

        result = chat_completion_text(
            client=client,
            runner=self.runner(retries=0),
            operation="test_chat",
            model="gpt-test",
            messages=[{"role": "user", "content": "hello"}],
            max_output_tokens=123,
            temperature=0,
        )

        self.assertEqual(result, "Safe answer")
        self.assertEqual(
            client.chat.completions.create.call_args.kwargs["max_tokens"],
            123,
        )

    def test_successful_embedding_request(self):
        client = Mock()
        client.embeddings.create.return_value = SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])]
        )
        result = create_embeddings(
            client=client,
            runner=self.runner(retries=0),
            operation="test_embedding",
            model="embedding-test",
            inputs="hello",
        )
        self.assertEqual(result, [[0.1, 0.2, 0.3]])

    def test_connection_timeout_is_retried_and_classified(self):
        call = Mock(side_effect=httpx.ConnectTimeout("connect timeout"))
        with self.assertRaises(AIConnectTimeoutError):
            self.runner().run(operation="connect", model="test", call=call)
        self.assertEqual(call.call_count, 2)

    def test_connection_failure_is_retried_and_classified(self):
        request = httpx.Request("POST", "https://api.openai.test/v1/mock")
        call = Mock(side_effect=openai.APIConnectionError(request=request))
        with self.assertRaises(AIConnectionError):
            self.runner().run(operation="connection", model="test", call=call)
        self.assertEqual(call.call_count, 2)

    def test_read_timeout_is_retried_and_classified(self):
        call = Mock(side_effect=httpx.ReadTimeout("read timeout"))
        with self.assertRaises(AIReadTimeoutError):
            self.runner().run(operation="read", model="test", call=call)
        self.assertEqual(call.call_count, 2)

    def test_provider_rate_limit_maps_to_temporary_dependency_failure(self):
        call = Mock(side_effect=response_error(openai.RateLimitError, 429))
        with self.assertRaises(AIRateLimitError) as caught:
            self.runner(retries=0).run(operation="rate_limit", model="test", call=call)
        self.assertEqual(caught.exception.public_status_code, 503)

    def test_temporary_server_error_recovers_on_retry(self):
        call = Mock(
            side_effect=[
                response_error(openai.InternalServerError, 503),
                "recovered",
            ]
        )
        result = self.runner().run(operation="temporary", model="test", call=call)
        self.assertEqual(result, "recovered")
        self.assertEqual(call.call_count, 2)

    def test_authentication_failure_is_not_retried(self):
        call = Mock(side_effect=response_error(openai.AuthenticationError, 401))
        with self.assertRaises(AIAuthenticationError):
            self.runner(retries=2).run(operation="auth", model="test", call=call)
        self.assertEqual(call.call_count, 1)

    def test_invalid_request_is_not_retried(self):
        call = Mock(side_effect=response_error(openai.BadRequestError, 400))
        with self.assertRaises(AIInvalidRequestError):
            self.runner(retries=2).run(operation="invalid", model="test", call=call)
        self.assertEqual(call.call_count, 1)

    def test_malformed_chat_output_is_rejected_without_retry(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(choices=[])
        with self.assertRaises(AIMalformedResponseError):
            chat_completion_text(
                client=client,
                runner=self.runner(retries=2),
                operation="malformed",
                model="test",
                messages=[{"role": "user", "content": "hello"}],
                max_output_tokens=20,
                temperature=0,
            )
        self.assertEqual(client.chat.completions.create.call_count, 1)

    def test_empty_chat_output_is_rejected(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="  "))]
        )
        with self.assertRaises(AIMalformedResponseError):
            chat_completion_text(
                client=client,
                runner=self.runner(retries=0),
                operation="empty",
                model="test",
                messages=[{"role": "user", "content": "hello"}],
                max_output_tokens=20,
                temperature=0,
            )

    def test_maximum_retry_count_is_bounded(self):
        call = Mock(side_effect=AIUnavailableError(provider_status_code=503))
        with self.assertRaises(AIUnavailableError):
            self.runner(retries=2).run(operation="bounded", model="test", call=call)
        self.assertEqual(call.call_count, 3)

    def test_retry_after_cannot_exceed_remaining_deadline(self):
        call = Mock(
            side_effect=response_error(
                openai.RateLimitError,
                429,
                retry_after=30,
            )
        )
        with self.assertRaises(AIDeadlineExceededError):
            self.runner(retries=1, timeout=1, deadline=3).run(
                operation="deadline",
                model="test",
                call=call,
            )
        self.assertEqual(call.call_count, 1)

    @override_settings(OPENAI_MAX_INPUT_CHARACTERS=10)
    def test_input_length_is_enforced_before_provider_call(self):
        with self.assertRaises(AIInputLimitError):
            enforce_input_limit("x" * 11)

    def test_logs_never_include_raw_provider_exception_or_secret(self):
        raw_secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
        call = Mock(side_effect=RuntimeError(f"prompt text and key={raw_secret}"))
        with self.assertLogs("core.ai.provider", level="WARNING") as logs:
            with self.assertRaises(Exception):
                self.runner(retries=0).run(
                    operation="sensitive",
                    model="test",
                    call=call,
                )
        output = "\n".join(logs.output)
        self.assertNotIn(raw_secret, output)
        self.assertNotIn("prompt text", output)
        self.assertIn("category=unexpected_provider_error", output)

    def test_safe_api_error_mapping_uses_503_not_429(self):
        response = public_exception_handler(AIRateLimitError(provider_status_code=429), {})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["error"], "ai_dependency_unavailable")
        self.assertNotIn("provider", response.data["detail"].lower())

    @override_settings(OPENAI_API_KEY="")
    def test_missing_api_key_fails_without_network_access(self):
        with self.assertRaises(AIConfigurationError):
            build_openai_client()

    @override_settings(OPENAI_EXTERNAL_CALLS_ENABLED=False)
    def test_explicit_test_kill_switch_prevents_provider_call(self):
        call = Mock(return_value="must not execute")
        with self.assertRaises(AIConfigurationError):
            AIOperationRunner().run(operation="disabled", model="test", call=call)
        call.assert_not_called()

    def test_llm_service_uses_fallback_for_malformed_structured_output(self):
        fallback = {"title": "Fallback"}
        service = LLMService(ai_runner=self.runner(retries=0))
        client = Mock()
        client.with_structured_output.return_value.invoke.return_value = "invalid"
        with patch.object(service, "_build_client", return_value=client):
            result = service.generate_quote_text(prompt="safe prompt", fallback=fallback)
        self.assertEqual(result, fallback)


class AIDuplicateBusinessRecordTests(TestCase):
    @patch("apps.devis.views.DevisService.generate_quote_from_request")
    def test_ai_failure_does_not_duplicate_devis_request(self, generate_quote):
        generate_quote.return_value = {
            "request_id": 1,
            "status": "failed",
            "detail": "Could not generate devis. Please try again.",
        }
        response = APIClient().post(
            "/api/devis/generate-from-chat/",
            {"description": "I need a booking website with online payments."},
            format="json",
        )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(DevisRequest.objects.count(), 1)
        generate_quote.assert_called_once()

    @patch("apps.chatbot.views.RAGChain", side_effect=NotFoundError("missing collection"))
    def test_missing_chroma_collection_returns_safe_503_without_partial_chat(self, _rag):
        response = APIClient().post(
            "/api/chatbot/chat/",
            {"message": "Tell me about SmartDex services."},
            format="json",
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "knowledge_dependency_unavailable")
        self.assertEqual(Conversation.objects.count(), 0)
