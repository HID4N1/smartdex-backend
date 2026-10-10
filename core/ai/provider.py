from __future__ import annotations

import email.utils
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

import httpx
import openai
from django.conf import settings
from langchain_openai import ChatOpenAI
from openai import OpenAI


logger = logging.getLogger(__name__)
T = TypeVar("T")


class AIProviderError(RuntimeError):
    category = "provider_error"
    retryable = False
    public_status_code = 503
    public_message = "The AI service is temporarily unavailable. Please try again later."

    def __init__(self, *, provider_status_code: int | None = None):
        super().__init__(self.public_message)
        self.provider_status_code = provider_status_code


class AITimeoutError(AIProviderError):
    category = "timeout"
    retryable = True


class AIConnectTimeoutError(AITimeoutError):
    category = "connection_timeout"


class AIReadTimeoutError(AITimeoutError):
    category = "read_timeout"


class AIConnectionError(AIProviderError):
    category = "connection_failure"
    retryable = True


class AIRateLimitError(AIProviderError):
    category = "provider_rate_limit"
    retryable = True


class AIUnavailableError(AIProviderError):
    category = "provider_unavailable"
    retryable = True


class AIAuthenticationError(AIProviderError):
    category = "authentication_failure"
    public_message = "The AI service is not configured correctly."


class AIInvalidRequestError(AIProviderError):
    category = "invalid_provider_request"
    public_status_code = 502
    public_message = "The AI service could not process this request."


class AIMalformedResponseError(AIProviderError):
    category = "malformed_provider_response"
    public_status_code = 502
    public_message = "The AI service returned an unusable response."


class AIInputLimitError(AIProviderError):
    category = "input_limit"
    public_status_code = 400
    public_message = "The request is too large for AI processing."


class AIDeadlineExceededError(AIProviderError):
    category = "deadline_exhausted"


class AIUnexpectedProviderError(AIProviderError):
    category = "unexpected_provider_error"
    public_status_code = 502


class AIConfigurationError(AIProviderError):
    category = "configuration_failure"
    public_message = "The AI service is not configured correctly."


@dataclass(frozen=True)
class AIRetryPolicy:
    request_timeout: float
    operation_deadline: float
    max_retries: int
    base_delay: float
    max_delay: float

    @classmethod
    def from_settings(cls) -> "AIRetryPolicy":
        return cls(
            request_timeout=settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
            operation_deadline=settings.OPENAI_OPERATION_DEADLINE_SECONDS,
            max_retries=settings.OPENAI_MAX_RETRIES,
            base_delay=settings.OPENAI_RETRY_BASE_DELAY_SECONDS,
            max_delay=settings.OPENAI_RETRY_MAX_DELAY_SECONDS,
        )


def _provider_status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def classify_provider_error(exc: Exception) -> AIProviderError:
    if isinstance(exc, AIProviderError):
        return exc
    timeout_cause = exc.__cause__ if isinstance(exc, openai.APITimeoutError) else exc
    if isinstance(timeout_cause, httpx.ConnectTimeout):
        return AIConnectTimeoutError(provider_status_code=_provider_status_code(exc))
    if isinstance(timeout_cause, httpx.ReadTimeout):
        return AIReadTimeoutError(provider_status_code=_provider_status_code(exc))
    if isinstance(exc, (openai.APITimeoutError, httpx.TimeoutException)):
        return AITimeoutError(provider_status_code=_provider_status_code(exc))
    if isinstance(exc, openai.APIConnectionError):
        cause = exc.__cause__
        if isinstance(cause, httpx.TimeoutException):
            return AITimeoutError(provider_status_code=_provider_status_code(exc))
        return AIConnectionError(provider_status_code=_provider_status_code(exc))
    if isinstance(exc, openai.RateLimitError):
        return AIRateLimitError(provider_status_code=429)
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return AIAuthenticationError(provider_status_code=_provider_status_code(exc))
    if isinstance(
        exc,
        (
            openai.BadRequestError,
            openai.UnprocessableEntityError,
            openai.NotFoundError,
        ),
    ):
        return AIInvalidRequestError(provider_status_code=_provider_status_code(exc))
    if isinstance(exc, openai.APIStatusError):
        status_code = _provider_status_code(exc)
        if status_code is not None and status_code >= 500:
            return AIUnavailableError(provider_status_code=status_code)
        return AIInvalidRequestError(provider_status_code=status_code)
    return AIUnexpectedProviderError(provider_status_code=_provider_status_code(exc))


def _retry_after_seconds(exc: Exception, now: datetime | None = None) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            retry_at = email.utils.parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - (now or datetime.now(timezone.utc))).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


class AIOperationRunner:
    def __init__(
        self,
        policy: AIRetryPolicy | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
        allow_calls: bool | None = None,
    ):
        self.policy = policy or AIRetryPolicy.from_settings()
        self.clock = clock
        self.sleep = sleep
        self.jitter = jitter
        self.allow_calls = (
            settings.OPENAI_EXTERNAL_CALLS_ENABLED
            if allow_calls is None
            else allow_calls
        )

    def run(self, *, operation: str, model: str, call: Callable[[], T]) -> T:
        if not self.allow_calls:
            raise AIConfigurationError()
        started = self.clock()
        total_attempts = self.policy.max_retries + 1

        for attempt in range(1, total_attempts + 1):
            elapsed = self.clock() - started
            remaining = self.policy.operation_deadline - elapsed
            if remaining < self.policy.request_timeout:
                raise AIDeadlineExceededError()

            try:
                result = call()
            except Exception as exc:
                error = classify_provider_error(exc)
                duration_ms = int((self.clock() - started) * 1000)
                logger.warning(
                    "ai_operation_failed operation=%s model=%s category=%s "
                    "attempt=%s retryable=%s provider_status=%s duration_ms=%s",
                    operation,
                    model,
                    error.category,
                    attempt,
                    error.retryable,
                    error.provider_status_code,
                    duration_ms,
                )
                if not error.retryable or attempt >= total_attempts:
                    raise error from None

                exponential_cap = min(
                    self.policy.max_delay,
                    self.policy.base_delay * (2 ** (attempt - 1)),
                )
                delay = self.jitter(0.0, exponential_cap)
                retry_after = _retry_after_seconds(exc)
                if retry_after is not None:
                    delay = max(delay, retry_after)

                remaining = self.policy.operation_deadline - (self.clock() - started)
                if delay + self.policy.request_timeout > remaining:
                    raise AIDeadlineExceededError() from None
                self.sleep(delay)
                continue

            duration_ms = int((self.clock() - started) * 1000)
            logger.info(
                "ai_operation_succeeded operation=%s model=%s attempts=%s duration_ms=%s",
                operation,
                model,
                attempt,
                duration_ms,
            )
            return result

        raise AIDeadlineExceededError()


def _http_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        settings.OPENAI_REQUEST_TIMEOUT_SECONDS,
        connect=settings.OPENAI_CONNECT_TIMEOUT_SECONDS,
    )


def build_openai_client(api_key: str | None = None) -> OpenAI:
    resolved_key = api_key or settings.OPENAI_API_KEY
    if not resolved_key:
        raise AIConfigurationError()
    return OpenAI(
        api_key=resolved_key,
        timeout=_http_timeout(),
        max_retries=0,
    )


def build_chat_model(
    *,
    model: str,
    temperature: float,
    max_output_tokens: int,
    api_key: str | None = None,
) -> ChatOpenAI:
    resolved_key = api_key or settings.OPENAI_API_KEY
    if not resolved_key:
        raise AIConfigurationError()
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=resolved_key,
        timeout=_http_timeout(),
        max_retries=0,
        max_tokens=max_output_tokens,
    )


def enforce_input_limit(value: str | list[str], *, maximum: int | None = None) -> None:
    if isinstance(value, list):
        character_count = sum(len(item) for item in value)
    else:
        character_count = len(value)
    if character_count > (maximum or settings.OPENAI_MAX_INPUT_CHARACTERS):
        raise AIInputLimitError()


def chat_completion_text(
    *,
    client: OpenAI,
    runner: AIOperationRunner,
    operation: str,
    model: str,
    messages: list[dict[str, Any]],
    max_output_tokens: int,
    temperature: float,
    top_p: float | None = None,
) -> str:
    enforce_input_limit(
        [str(message.get("content") or "") for message in messages]
    )

    def request() -> str:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        if top_p is not None:
            kwargs["top_p"] = top_p
        response = client.chat.completions.create(**kwargs)
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError):
            raise AIMalformedResponseError() from None
        if not isinstance(content, str) or not content.strip():
            raise AIMalformedResponseError()
        return content.strip()

    return runner.run(operation=operation, model=model, call=request)


def create_embeddings(
    *,
    client: OpenAI,
    runner: AIOperationRunner,
    operation: str,
    model: str,
    inputs: str | list[str],
) -> list[list[float]]:
    input_items = [inputs] if isinstance(inputs, str) else inputs
    if not input_items or len(input_items) > settings.OPENAI_EMBEDDING_BATCH_SIZE:
        raise AIInputLimitError()
    enforce_input_limit(input_items)

    def request() -> list[list[float]]:
        response = client.embeddings.create(model=model, input=inputs)
        try:
            embeddings = [item.embedding for item in response.data]
        except (AttributeError, TypeError):
            raise AIMalformedResponseError() from None
        if len(embeddings) != len(input_items) or any(not item for item in embeddings):
            raise AIMalformedResponseError()
        return embeddings

    return runner.run(operation=operation, model=model, call=request)
