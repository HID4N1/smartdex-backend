# External AI Reliability and Security

## Integration inventory

| Operation | Location | Model | Calls per request | Failure behavior |
| --- | --- | --- | --- | --- |
| Query embedding | `core/ai/rag/retriever.py` | `text-embedding-3-small` | 1 | Bounded retry, then local lexical retrieval |
| Follow-up rewrite | `core/ai/rag/chain.py` | `gpt-4.1-mini` | 0 or 1 | Bounded retry, then original query |
| Chat answer | `core/ai/rag/chain.py` | `gpt-4.1-mini` | 1, plus at most 1 validation repair | Bounded retry, then deterministic local answer |
| Devis requirements | `apps/devis/services/llm_service.py` | `gpt-4.1-mini` | 1 | Bounded retry, then deterministic heuristic extraction |
| Devis narrative | `apps/devis/services/llm_service.py` | `gpt-4.1-mini` | 1 | Bounded retry, then deterministic proposal text |
| Direct pricing extraction | `core/pricing/extractor.py` | `gpt-4.1-mini` | 1 | Safe typed provider error to caller |
| Maintenance embeddings | `core/ai/rag/vectorstore.py` | `text-embedding-3-small` | One call per bounded batch | Maintenance command fails without a partial Chroma insert |

All provider operations are synchronous. They occupy a Gunicorn worker while in
progress, so their retry and timeout budget is deliberately finite. There are no
Responses API calls or other external AI providers in the repository.

## Retry and deadline ownership

`core.ai.provider` is the only retry owner. Native OpenAI and LangChain clients are
created with SDK retries disabled (`max_retries=0`). The application retries only:

- connection failures and connection/read timeouts;
- provider rate limits;
- provider HTTP 5xx responses.

Authentication, authorization, invalid requests, unsupported resources, malformed
responses, input-limit failures, and configuration errors are never retried.
Exponential backoff includes jitter. A provider `Retry-After` value is honored only
when both the wait and another full request timeout fit inside the remaining operation
deadline.

Default timing:

- connection timeout: 2 seconds;
- complete SDK request timeout: 8 seconds;
- application retries: 1;
- retry delay cap: 1 second;
- per-operation deadline: 17 seconds.

The maximum provider time for one operation is therefore 16.25 seconds with the
default 0.25-second first backoff. The longest chatbot path has four provider
operations (rewrite, embedding, answer, repair), so its maximum AI budget is 68
seconds. Startup rejects a configuration where that budget reaches either the
configured upstream/reverse-proxy deadline (default 110 seconds) or Gunicorn timeout
(default 120 seconds). Azure deployments must set `UPSTREAM_REQUEST_TIMEOUT_SECONDS`
to the actual shortest ingress/proxy deadline.

## Resource controls

- Chat messages: 4,000 characters each.
- Stored chat context: 30,000 characters and 30 messages.
- Devis descriptions: 10,000 characters.
- Any single provider operation: 30,000 input characters.
- RAG context: 12,000 characters.
- RAG retrieval: maximum 12 documents; application default remains 8.
- Chat answer: 220 output tokens.
- Query rewrite: 80 output tokens.
- Structured devis/pricing result: 800 output tokens.
- Embedding maintenance batch: 64 inputs and 30,000 aggregate characters per call.
- Chat response validation can trigger only one repair generation.

The environment values are documented in `.env.example` and validated during Django
settings import. Negative timeouts, more than two retries, invalid sizes, unbounded
retry/deadline combinations, and AI budgets that exceed request-process deadlines stop
startup.

`OPENAI_EXTERNAL_CALLS_ENABLED=false` is an explicit test/incident kill switch. The
automated suite sets it to false so an accidental unmocked path fails locally without
network access. Production defaults to enabled and still requires a non-placeholder API
key.

## Error and privacy policy

Provider failures are categorized as timeout, connection failure, rate limit,
unavailability, authentication/configuration failure, invalid request, malformed
response, input limit, deadline exhaustion, or unexpected provider failure. Upstream
rate limiting maps to HTTP 503 rather than presenting it as client throttling. Public
messages never include raw exceptions, prompts, payloads, API keys, connection strings,
or stack traces.

Operational logs contain only operation name, model, duration, attempt count, error
category, retryability, and provider status code. Chat runtime logs no longer serialize
conversation state or transcripts.

## Business safety

AI output never sets quote prices. Requirement extraction can influence normalized
feature selection, but the pricing range and totals come from deterministic catalogs,
selectors, estimators, and quote builders. Malformed structured output is rejected and
the existing deterministic heuristics/text are used. Provider retries occur only around
idempotent model requests; database record creation and status transitions are outside
the retry runner, preventing duplicate devis records.
