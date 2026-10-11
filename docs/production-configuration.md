# SmartDex production configuration

This is the Azure Container Apps configuration contract. It does not provision
infrastructure and contains no real credentials.

## Required production variables

| Variable | Purpose and validation | Safe example | Security notes |
|---|---|---|---|
| `DJANGO_ENV` | Selects strict production validation; must be `production` | `production` | Production checks do not depend on `DEBUG` inference. |
| `DJANGO_DEBUG` | Django debug mode; must be false | `False` | A true value fails startup. |
| `DJANGO_LOAD_DOTENV` | Local `.env` loading; must be false | `False` | Production secrets come from the process environment/Azure secrets. |
| `DJANGO_SECRET_KEY` | Django signing secret; non-empty and non-placeholder | `<Azure secret reference>` | Generate a long random value; never bake it into the image. |
| `ALLOWED_HOSTS` | Exact comma-separated hosts; must include `api.smartdex.ma` | `api.smartdex.ma,<app>.<region>.azurecontainerapps.io` | Add the generated Azure host after creation. Wildcards, schemes, paths, and parent-domain forms are rejected. The frontend is not an API host. |
| `CORS_ALLOWED_ORIGINS` | Exact HTTPS origins; must include the production frontend | `https://www.smartdex.ma` | The apex domain is distinct and is not authorized by default. No regex/wildcard origins. |
| `DATABASE_URL` | Supabase PostgreSQL URL | `postgresql://<user>:<password>@<pooler-host>:5432/<db>?sslmode=require` | Mandatory, PostgreSQL-only, TLS-required, and stored as an Azure secret. |
| `OPENAI_API_KEY` | OpenAI credential | `<Azure secret reference>` | Mandatory, non-placeholder, and never logged. |
| `USE_X_FORWARDED_PROTO` | Trust Azure's `X-Forwarded-Proto` | `True` | Enable only after verifying ingress overwrites the header and the container cannot be reached around ingress. Required with HTTPS redirect. |

## Optional production variables

| Variable | Default / safe example | Purpose and validation |
|---|---|---|
| `CORS_ALLOW_CREDENTIALS` | `False` | Must remain false. Public APIs do not need cross-origin cookies; admin sessions are same-origin. |
| `CSRF_TRUSTED_ORIGINS` | empty | Add only an exact HTTPS origin if a future cross-origin session/CSRF flow requires it. |
| `SECURE_SSL_REDIRECT` | `True` | Redirects HTTP after trusted proxy recognition. |
| `SECURE_HSTS_SECONDS` | `3600` | Initial limited HSTS rollout; increase after observation. |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `False` | Deferred because it affects every present and future `smartdex.ma` subdomain. |
| `SECURE_HSTS_PRELOAD` | `False` | Deferred because browser preload is long-lived and requires domain-wide readiness. |
| `SESSION_COOKIE_SAMESITE` / `CSRF_COOKIE_SAMESITE` | `Lax` | Secure cookies are forced in production. |
| `DB_POOL_MODE` | `transaction` | Supabase transaction pooler mode; disables server-side cursors. Use `direct`/`session` only for matching endpoints. |
| `DB_CONN_MAX_AGE` | `60` | Bounded persistent lifetime; tune against replica count and Supabase limits. |
| `DB_CONN_HEALTH_CHECKS` | `True` | Checks a reused connection before use. |
| `DB_CONNECT_TIMEOUT_SECONDS` | `10` | Positive PostgreSQL connection timeout. |
| `DB_STATEMENT_TIMEOUT_MS` | `30000` | Positive PostgreSQL statement timeout. |
| `DRF_NUM_PROXIES` | `1` | Trusted proxy count for DRF client identification; revalidate after deployment. |
| `THROTTLE_RATE_CONTACT` | `5/hour` | Public contact submission rate. |
| `THROTTLE_RATE_DEVIS_CREATE` | `10/hour` | Public quote creation rate. |
| `THROTTLE_RATE_DEVIS_GENERATE` | `10/hour` | Public quote generation rate. |
| `THROTTLE_RATE_CHATBOT` | `30/hour` | Public chatbot rate. Local-memory throttles are per replica. |
| `DJANGO_LOG_LEVEL` | `INFO` | Django logs go to stderr; avoid debug logging in production. |
| `WHITENOISE_MAX_AGE` | `31536000` | Hashed static asset cache lifetime. |

OpenAI timeout, retry, token, input, and model variables are listed with safe
defaults in `.env.example`. The worst-case AI budget is validated below both
`UPSTREAM_REQUEST_TIMEOUT_SECONDS=110` and `GUNICORN_TIMEOUT=120`.

### OpenAI variables

| Variable | Required / default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | Required secret | Provider authentication; never log or bake into the image. |
| `OPENAI_EXTERNAL_CALLS_ENABLED` | Optional / `True` | Operational kill switch. Set false in isolated tests. |
| `OPENAI_CHAT_MODEL` | Optional / `gpt-4.1-mini` | Chat and structured-output model. |
| `OPENAI_EMBEDDING_MODEL` | Optional / `text-embedding-3-small` | Must match the packaged index manifest. |
| `OPENAI_REQUEST_TIMEOUT_SECONDS` | Optional / `8` | Per-attempt read/request timeout; positive. |
| `OPENAI_CONNECT_TIMEOUT_SECONDS` | Optional / `2` | Connection timeout; positive and no greater than request timeout. |
| `OPENAI_OPERATION_DEADLINE_SECONDS` | Optional / `17` | Total deadline per provider operation. |
| `OPENAI_MAX_RETRIES` | Optional / `1` | Bounded from zero through two. |
| `OPENAI_RETRY_BASE_DELAY_SECONDS` | Optional / `0.25` | Non-negative retry backoff base. |
| `OPENAI_RETRY_MAX_DELAY_SECONDS` | Optional / `1` | Non-negative retry backoff cap, at least the base. |
| `OPENAI_CHAT_MAX_OUTPUT_TOKENS` | Optional / `220` | Bounded chatbot output. |
| `OPENAI_REWRITE_MAX_OUTPUT_TOKENS` | Optional / `80` | Bounded query-rewrite output. |
| `OPENAI_STRUCTURED_MAX_OUTPUT_TOKENS` | Optional / `800` | Bounded structured quote output. |
| `OPENAI_EMBEDDING_BATCH_SIZE` | Optional / `64` | Embedding maintenance batch size; startup never embeds. |
| `OPENAI_MAX_INPUT_CHARACTERS` | Optional / `30000` | Provider input limit. |
| `OPENAI_RAG_CONTEXT_MAX_CHARACTERS` | Optional / `12000` | Retrieved context limit. |
| `OPENAI_RAG_MAX_TOP_K` | Optional / `12` | Maximum retrieval result count. |
| `UPSTREAM_REQUEST_TIMEOUT_SECONDS` | Optional / `110` | Shortest expected ingress/upstream deadline; must exceed the maximum AI path. |

Docker sets `CHROMA_SEED_DIR=/app/chroma_seed`,
`CHROMA_DIR=/tmp/smartdex/chroma_runtime`, and
`CHROMA_MANIFEST_PATH=/app/chroma_seed/manifest.json`. Startup validates and copies
the packaged `chroma-index-v1` seed. It does not ingest or call OpenAI.

The three Chroma path variables are required image defaults and should not be
overridden in Azure unless the image layout changes. `CHROMA_SEED_DIR` is the
read-only packaged source, `CHROMA_DIR` is the isolated writable runtime copy,
and `CHROMA_MANIFEST_PATH` identifies the checksum/version manifest.

For Supabase transaction pooling, `DISABLE_SERVER_SIDE_CURSORS` is enabled.
Django uses `psycopg2`, which does not automatically create psycopg3-style server
prepared statements. Persistent client-to-pooler connections are bounded by
`DB_CONN_MAX_AGE`; total connections must be recalculated when Azure replica or
worker counts change. Direct/session pooler endpoints must use the matching
`DB_POOL_MODE` rather than inheriting transaction-pool assumptions.

## Gunicorn baseline

The initial baseline is two synchronous workers, one thread each, a 120-second
timeout, 30-second graceful timeout, five-second keepalive, and recycling after
500 requests plus up to 50 requests of jitter. Review worker count against the
selected Azure CPU/memory size. Access logs omit query strings.

| Gunicorn variable | Default | Purpose |
|---|---:|---|
| `PORT` | `8000` | Container listen port. |
| `WEB_CONCURRENCY` | `2` | Sync worker count; size against CPU, memory, and DB limits. |
| `GUNICORN_WORKER_CLASS` | `sync` | Worker model; intentionally synchronous in Step 5. |
| `GUNICORN_THREADS` | `1` | Threads per worker. |
| `GUNICORN_TIMEOUT` | `120` | Hard request timeout; exceeds the ~68-second legitimate AI path. |
| `GUNICORN_GRACEFUL_TIMEOUT` | `30` | Worker shutdown grace period. |
| `GUNICORN_KEEPALIVE` | `5` | HTTP keepalive seconds. |
| `GUNICORN_MAX_REQUESTS` | `500` | Worker recycle threshold. |
| `GUNICORN_MAX_REQUESTS_JITTER` | `50` | Staggers worker recycling. |
| `GUNICORN_PRELOAD` | `False` | Avoids preloading application state before workers fork. |
| `GUNICORN_LOG_LEVEL` | `info` | Gunicorn stdout/stderr verbosity. |
| `GUNICORN_FORWARDED_ALLOW_IPS` | `127.0.0.1` | Gunicorn proxy trust boundary; Azure guidance follows below. |

`GUNICORN_FORWARDED_ALLOW_IPS` defaults to `127.0.0.1`. Azure may require `*`
because ingress addresses are dynamic. Use that only after proving the app port is
not directly reachable and ingress replaces client forwarding headers.

## Health probes

- Liveness: `GET /api/health/live/` (or compatible `GET /api/health/`). It checks
  only the process and should drive restarts.
- Readiness: `GET /api/health/ready/`. It performs one `SELECT 1` and returns 503
  without details if PostgreSQL is unavailable. Remove the replica from service;
  do not restart it for a transient database outage.

Neither probe calls OpenAI or regenerates Chroma.

## Static files and generated media

WhiteNoise serves manifest-versioned admin assets with `DEBUG=False`.
`collectstatic` runs at image build without production secrets. Generated quote
PDFs and the Chroma runtime use container-local `/tmp` and are lost on replacement.
PDFs are generated on demand and returned, so current workflows do not treat them
as durable. Blob storage is intentionally deferred.

The `SMARTDEX_PRIVACY_NOTICE_VERSION` and five `SMARTDEX_*_RETENTION_*` variables
in `.env.example` are optional policy controls for notice version, contact data,
abandoned/completed quote data, chatbot data, and temporary PDFs. Their safe
examples are implementation defaults pending legal review. `DB_ENGINE`, `DB_NAME`,
`DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` are development-only fallback
settings and must not replace `DATABASE_URL` in production.

## Sample Azure Container Apps values

```text
DJANGO_ENV=production
DJANGO_DEBUG=False
DJANGO_LOAD_DOTENV=False
DJANGO_SECRET_KEY=secretref:django-secret-key
ALLOWED_HOSTS=api.smartdex.ma,<generated-app-hostname>
CORS_ALLOWED_ORIGINS=https://www.smartdex.ma
CORS_ALLOW_CREDENTIALS=False
CSRF_TRUSTED_ORIGINS=
DATABASE_URL=secretref:supabase-database-url
DB_POOL_MODE=transaction
OPENAI_API_KEY=secretref:openai-api-key
USE_X_FORWARDED_PROTO=True
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=3600
SECURE_HSTS_INCLUDE_SUBDOMAINS=False
SECURE_HSTS_PRELOAD=False
GUNICORN_FORWARDED_ALLOW_IPS=*
PORT=8000
WEB_CONCURRENCY=2
GUNICORN_TIMEOUT=120
UPSTREAM_REQUEST_TIMEOUT_SECONDS=110
DJANGO_LOG_LEVEL=INFO
```

Before proxy trust, verify Azure's effective remote address, header replacement,
direct-port isolation, and redirect behavior. Before increasing HSTS or enabling
`includeSubDomains`/preload, inventory every `smartdex.ma` subdomain and confirm
permanent HTTPS support.
