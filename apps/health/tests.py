import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client, SimpleTestCase, TestCase, override_settings
from rest_framework.test import APIRequestFactory

from apps.health.views import readiness_check
from core.utils.exception_handlers import public_exception_handler
from core.utils.privacy import redact_url_query, sanitize_for_log


BASE_DIR = Path(__file__).resolve().parents[2]


def run_settings_probe(env_overrides, code):
    env = os.environ.copy()
    env.update(
        {
            "DJANGO_LOAD_DOTENV": "false",
            "DJANGO_SETTINGS_MODULE": "config.settings",
            "DATABASE_URL": "",
            "OPENAI_API_KEY": "test-key",
        }
    )
    for name in (
        "ALLOWED_HOSTS",
        "CORS_ALLOWED_ORIGINS",
        "CORS_ALLOW_CREDENTIALS",
        "CSRF_TRUSTED_ORIGINS",
        "CSRF_COOKIE_SAMESITE",
        "DEBUG",
        "DJANGO_DEBUG",
        "DJANGO_SECRET_KEY",
        "SECRET_KEY",
        "SECURE_HSTS_INCLUDE_SUBDOMAINS",
        "SECURE_HSTS_PRELOAD",
        "SECURE_HSTS_SECONDS",
        "SECURE_SSL_REDIRECT",
        "SESSION_COOKIE_SAMESITE",
        "USE_X_FORWARDED_PROTO",
        "DJANGO_ENV",
        "DATABASE_URL",
        "DB_CONN_HEALTH_CHECKS",
        "DB_CONN_MAX_AGE",
        "DB_CONNECT_TIMEOUT_SECONDS",
        "DB_POOL_MODE",
        "DB_STATEMENT_TIMEOUT_MS",
        "OPENAI_API_KEY",
    ):
        if name not in env_overrides:
            env.pop(name, None)
    env.update(env_overrides)

    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BASE_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class ProductionSecuritySettingsTests(SimpleTestCase):
    production_env = {
        "DJANGO_ENV": "production",
        "DJANGO_DEBUG": "false",
        "DJANGO_SECRET_KEY": "test-production-secret-key",
        "OPENAI_API_KEY": "test-openai-key",
        "ALLOWED_HOSTS": "api.smartdex.ma,smartdex-backend.example.azurecontainerapps.io",
        "CORS_ALLOWED_ORIGINS": "https://www.smartdex.ma",
        "CSRF_TRUSTED_ORIGINS": "",
        "DATABASE_URL": "postgresql://user:password@db.example.com:5432/smartdex",
        "USE_X_FORWARDED_PROTO": "true",
    }

    def probe(self, code, env_overrides=None):
        env = dict(self.production_env)
        if env_overrides:
            env.update(env_overrides)
        result = run_settings_probe(env, code)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_debug_false_values_are_false(self):
        for value in ("false", "False", "0", "no", "off"):
            self.probe(
                "from django.conf import settings; assert settings.DEBUG is False",
                {"DJANGO_DEBUG": value},
            )

    def test_production_security_settings_are_enabled(self):
        self.probe(
            """
from django.conf import settings
assert settings.DEBUG is False
assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
assert settings.SECURE_SSL_REDIRECT is True
assert settings.SESSION_COOKIE_SECURE is True
assert settings.CSRF_COOKIE_SECURE is True
assert settings.SECURE_HSTS_SECONDS == 3600
assert settings.SECURE_HSTS_INCLUDE_SUBDOMAINS is False
assert settings.SECURE_HSTS_PRELOAD is False
assert settings.SECURE_CONTENT_TYPE_NOSNIFF is True
assert settings.SECURE_REFERRER_POLICY == "strict-origin-when-cross-origin"
assert settings.SECURE_CROSS_ORIGIN_OPENER_POLICY == "same-origin"
assert settings.X_FRAME_OPTIONS == "DENY"
assert settings.SESSION_COOKIE_HTTPONLY is True
assert settings.SESSION_COOKIE_SAMESITE == "Lax"
assert settings.CSRF_COOKIE_SAMESITE == "Lax"
""",
        )

    def test_production_api_and_cors_posture(self):
        self.probe(
            """
from django.conf import settings
assert settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] == ["rest_framework.renderers.JSONRenderer"]
assert settings.CORS_ALLOW_ALL_ORIGINS is False
assert settings.CORS_ALLOW_CREDENTIALS is False
assert settings.CORS_ALLOWED_ORIGINS == ["https://www.smartdex.ma"]
assert "x-devis-access-token" in settings.CORS_ALLOW_HEADERS
assert settings.CSRF_TRUSTED_ORIGINS == []
assert settings.ALLOWED_HOSTS == ["api.smartdex.ma", "smartdex-backend.example.azurecontainerapps.io"]
assert settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == ["rest_framework.authentication.SessionAuthentication"]
assert settings.REST_FRAMEWORK["PAGE_SIZE"] == 50
""",
        )

    def test_missing_production_secret_fails_clearly(self):
        env = dict(self.production_env)
        env.pop("DJANGO_SECRET_KEY")
        result = run_settings_probe(
            env,
            "import config.settings",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY or SECRET_KEY must be set", result.stderr)

    def test_placeholder_production_secret_fails_clearly(self):
        result = run_settings_probe(
            {**self.production_env, "DJANGO_SECRET_KEY": "change-me"},
            "import config.settings",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-placeholder value", result.stderr)

    def test_missing_production_openai_key_fails_clearly(self):
        env = dict(self.production_env)
        env.pop("OPENAI_API_KEY")
        result = run_settings_probe(env, "import config.settings")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OPENAI_API_KEY must be set", result.stderr)

    def test_placeholder_production_openai_key_fails_clearly(self):
        result = run_settings_probe(
            {**self.production_env, "OPENAI_API_KEY": "replace-with-openai-api-key"},
            "import config.settings",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OPENAI_API_KEY must be set", result.stderr)

    def test_negative_openai_timeout_fails_at_startup(self):
        result = run_settings_probe(
            {**self.production_env, "OPENAI_REQUEST_TIMEOUT_SECONDS": "-1"},
            "import config.settings",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OPENAI_REQUEST_TIMEOUT_SECONDS must be greater than zero", result.stderr)

    def test_unbounded_openai_retries_fail_at_startup(self):
        result = run_settings_probe(
            {**self.production_env, "OPENAI_MAX_RETRIES": "99"},
            "import config.settings",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("OPENAI_MAX_RETRIES must be between 0 and 2", result.stderr)

    def test_wildcard_production_allowed_hosts_fails_clearly(self):
        result = run_settings_probe(
            {**self.production_env, "ALLOWED_HOSTS": "*"},
            "import config.settings",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ALLOWED_HOSTS must list explicit production hostnames", result.stderr)

    def test_empty_production_allowed_hosts_fails_clearly(self):
        result = run_settings_probe(
            {**self.production_env, "ALLOWED_HOSTS": ""},
            "import config.settings",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ALLOWED_HOSTS must not be empty", result.stderr)

    def test_production_api_hostname_is_required(self):
        result = run_settings_probe(
            {**self.production_env, "ALLOWED_HOSTS": "example.azurecontainerapps.io"},
            "import config.settings",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must include api.smartdex.ma", result.stderr)

    def test_invalid_or_wildcard_cors_origin_fails(self):
        for origin in ("*", "https://*.smartdex.ma", "https://www.smartdex.ma/path"):
            result = run_settings_probe(
                {**self.production_env, "CORS_ALLOWED_ORIGINS": origin},
                "import config.settings",
            )
            self.assertNotEqual(result.returncode, 0)

    def test_apex_origin_does_not_replace_www_origin(self):
        result = run_settings_probe(
            {**self.production_env, "CORS_ALLOWED_ORIGINS": "https://smartdex.ma"},
            "import config.settings",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("https://www.smartdex.ma", result.stderr)

    def test_missing_production_database_url_fails_clearly(self):
        env = dict(self.production_env)
        env.pop("DATABASE_URL")
        result = run_settings_probe(env, "import config.settings")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DATABASE_URL must be set", result.stderr)

    def test_production_sqlite_database_is_rejected(self):
        result = run_settings_probe(
            {**self.production_env, "DATABASE_URL": "sqlite:///production.sqlite3"},
            "import config.settings",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must use PostgreSQL", result.stderr)

    def test_production_database_tls_cannot_be_disabled(self):
        result = run_settings_probe(
            {
                **self.production_env,
                "DATABASE_URL": "postgresql://user:password@db.example.com/smartdex?sslmode=disable",
            },
            "import config.settings",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("sslmode=require", result.stderr)

    def test_supabase_transaction_pooler_settings_are_explicit(self):
        self.probe(
            """
from django.conf import settings
database = settings.DATABASES["default"]
assert database["CONN_MAX_AGE"] == 60
assert database["CONN_HEALTH_CHECKS"] is True
assert database["DISABLE_SERVER_SIDE_CURSORS"] is True
assert database["OPTIONS"]["sslmode"] == "require"
assert database["OPTIONS"]["connect_timeout"] == 10
assert "statement_timeout=30000" in database["OPTIONS"]["options"]
""",
        )

    def test_invalid_integer_security_setting_fails_clearly(self):
        result = run_settings_probe(
            {**self.production_env, "SECURE_HSTS_SECONDS": "not-a-number"},
            "import config.settings",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECURE_HSTS_SECONDS must be an integer", result.stderr)

    def test_production_environment_cannot_silently_run_with_debug_true(self):
        result = run_settings_probe(
            {
                "DJANGO_DEBUG": "true",
                "DJANGO_ENV": "production",
                "DJANGO_SECRET_KEY": "test-production-secret-key",
            },
            "import config.settings",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_DEBUG must be false", result.stderr)

    def test_production_cannot_load_dotenv(self):
        result = run_settings_probe(
            {**self.production_env, "DJANGO_LOAD_DOTENV": "true"},
            "import config.settings",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_LOAD_DOTENV must be false", result.stderr)

    def test_trusted_proxy_header_marks_request_secure(self):
        self.probe(
            """
from django.test import RequestFactory
request = RequestFactory().get("/api/health/", HTTP_X_FORWARDED_PROTO="https")
assert request.is_secure() is True
""",
        )

    def test_forwarded_header_is_ignored_when_proxy_trust_is_disabled(self):
        self.probe(
            """
from django.test import RequestFactory
from django.conf import settings
assert settings.SECURE_PROXY_SSL_HEADER is None
request = RequestFactory().get("/api/health/", HTTP_X_FORWARDED_PROTO="https")
assert request.is_secure() is False
""",
            {
                "USE_X_FORWARDED_PROTO": "false",
                "SECURE_SSL_REDIRECT": "false",
            },
        )


class LocalDevelopmentSettingsTests(SimpleTestCase):
    def test_local_development_defaults_remain_usable(self):
        result = run_settings_probe(
            {"DJANGO_DEBUG": "true"},
            """
from django.conf import settings
assert settings.DEBUG is True
assert settings.SECURE_SSL_REDIRECT is False
assert settings.SECURE_HSTS_SECONDS == 0
assert settings.SESSION_COOKIE_SECURE is False
assert settings.CSRF_COOKIE_SECURE is False
assert settings.ALLOWED_HOSTS == ["localhost", "127.0.0.1"]
assert settings.CORS_ALLOWED_ORIGINS == ["http://localhost:3000", "http://127.0.0.1:3000"]
assert settings.CSRF_TRUSTED_ORIGINS == []
assert settings.SECURE_PROXY_SSL_HEADER is None
""",
        )

        self.assertEqual(result.returncode, 0, result.stderr)


class RuntimeSecurityPostureTests(SimpleTestCase):
    def test_admin_middleware_and_security_defaults_are_present(self):
        self.assertIn("django.middleware.security.SecurityMiddleware", settings.MIDDLEWARE)
        self.assertIn("corsheaders.middleware.CorsMiddleware", settings.MIDDLEWARE)
        self.assertIn("django.middleware.csrf.CsrfViewMiddleware", settings.MIDDLEWARE)
        self.assertIn("django.contrib.auth.middleware.AuthenticationMiddleware", settings.MIDDLEWARE)
        self.assertIn("django.middleware.clickjacking.XFrameOptionsMiddleware", settings.MIDDLEWARE)
        self.assertLess(
            settings.MIDDLEWARE.index("django.middleware.security.SecurityMiddleware"),
            settings.MIDDLEWARE.index("whitenoise.middleware.WhiteNoiseMiddleware"),
        )

    @override_settings(ALLOWED_HOSTS=["api.smartdex.ma"])
    def test_unexpected_host_header_is_rejected(self):
        response = Client().get("/api/health/", HTTP_HOST="attacker.example")
        self.assertEqual(response.status_code, 400)

    @override_settings(
        ALLOWED_HOSTS=["testserver"],
        CORS_ALLOWED_ORIGINS=["https://www.smartdex.ma"],
    )
    def test_authorized_cors_preflight_receives_cors_headers(self):
        response = Client().options(
            "/api/health/",
            HTTP_ORIGIN="https://www.smartdex.ma",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Access-Control-Allow-Origin"],
            "https://www.smartdex.ma",
        )

    @override_settings(
        ALLOWED_HOSTS=["testserver"],
        CORS_ALLOWED_ORIGINS=["https://www.smartdex.ma"],
    )
    def test_unauthorized_cors_origin_receives_no_cors_headers(self):
        response = Client().get(
            "/api/health/",
            HTTP_ORIGIN="https://attacker.example",
        )
        self.assertNotIn("Access-Control-Allow-Origin", response)

    def test_sensitive_routes_are_not_cacheable(self):
        response = Client().get("/api/health/")
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_static_admin_asset_is_discoverable_with_debug_false(self):
        with override_settings(DEBUG=False):
            self.assertIsNotNone(finders.find("admin/css/base.css"))

    @override_settings(DEBUG=False)
    def test_unhandled_api_error_response_is_sanitized(self):
        secret = "sensitive-client-description"
        response = public_exception_handler(RuntimeError(secret), {})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(secret, str(response.data))

    @patch("apps.health.views.connection")
    def test_readiness_uses_only_a_lightweight_database_query(self, connection):
        cursor = connection.cursor
        cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
        response = readiness_check(APIRequestFactory().get("/api/health/ready/"))
        cursor.return_value.__enter__.return_value.execute.assert_called_once_with("SELECT 1")
        self.assertEqual(response.status_code, 200)


class AdminCsrfTests(TestCase):
    def test_admin_login_rejects_post_without_csrf_token(self):
        response = Client(enforce_csrf_checks=True).post(
            "/admin/login/",
            {"username": "admin", "password": "invalid"},
        )
        self.assertEqual(response.status_code, 403)


class StartupAndGunicornTests(SimpleTestCase):
    def test_startup_does_not_run_migrations_ingestion_or_openai(self):
        entrypoint = (BASE_DIR / "scripts" / "docker-entrypoint.sh").read_text(encoding="utf-8")
        initializer = (BASE_DIR / "scripts" / "init_chroma.py").read_text(encoding="utf-8")
        startup = f"{entrypoint}\n{initializer}".lower()
        self.assertNotIn("migrate", startup)
        self.assertNotIn("ingest_docs", startup)
        self.assertNotIn("openai", startup)

    def test_docker_build_validates_chroma_seed(self):
        dockerfile = (BASE_DIR / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("validate_seed", dockerfile)

    def test_gunicorn_timeout_exceeds_ai_request_budget(self):
        namespace = {}
        exec((BASE_DIR / "gunicorn.conf.py").read_text(encoding="utf-8"), namespace)
        self.assertEqual(namespace["timeout"], 120)
        self.assertGreater(namespace["timeout"], 4 * settings.OPENAI_OPERATION_DEADLINE_SECONDS)
        self.assertEqual(namespace["access_log_format"].count("%(q)s"), 0)


class LogSanitizerTests(SimpleTestCase):
    def test_log_sanitizer_removes_email(self):
        self.assertNotIn("client@example.com", sanitize_for_log("Email client@example.com"))

    def test_log_sanitizer_removes_phone(self):
        self.assertNotIn("+212600000000", sanitize_for_log("Phone +212600000000"))

    def test_log_sanitizer_removes_bearer_token(self):
        sanitized = sanitize_for_log("Authorization: Bearer abc.def.ghi")

        self.assertNotIn("abc.def.ghi", sanitized)
        self.assertIn("[REDACTED", sanitized)

    def test_log_sanitizer_removes_devis_access_token_query_value(self):
        raw = "/api/devis/requests/7/generate/?format=pdf&token=123e4567-e89b-12d3-a456-426614174000"
        sanitized = sanitize_for_log(raw)

        self.assertNotIn("123e4567-e89b-12d3-a456-426614174000", sanitized)
        self.assertIn("token=[REDACTED_TOKEN]", sanitized)

    def test_log_sanitizer_removes_openai_style_api_key(self):
        raw_key = "sk-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ123456"

        self.assertNotIn(raw_key, sanitize_for_log(f"OpenAI key {raw_key}"))

    def test_log_sanitizer_removes_database_url(self):
        raw_url = "postgresql://user:secret-password@db.example.com:5432/smartdex"

        self.assertNotIn(raw_url, sanitize_for_log(f"DB {raw_url}"))

    def test_safe_business_text_remains_readable(self):
        sanitized = sanitize_for_log("booking website with payments, notifications, and 15000 MAD budget")

        self.assertIn("booking website", sanitized)
        self.assertIn("payments", sanitized)
        self.assertIn("15000 MAD", sanitized)

    def test_redact_url_query_preserves_path_and_safe_query_values(self):
        sanitized = redact_url_query(
            "/api/devis/requests/7/generate/?format=pdf&token=secret&lang=fr"
        )

        self.assertEqual(
            sanitized,
            "/api/devis/requests/7/generate/?format=pdf&token=%5BREDACTED_TOKEN%5D&lang=fr",
        )


class EnvironmentExampleTests(SimpleTestCase):
    def test_env_example_contains_only_safe_placeholders(self):
        text = (BASE_DIR / ".env.example").read_text(encoding="utf-8")

        self.assertNotRegex(text, r"sk-[A-Za-z0-9_-]{20,}")
        self.assertNotIn("aws-1-eu-west-1.pooler.supabase.com", text)
        self.assertIn("replace-with-openai-api-key", text)
        self.assertIn("replace-with-local-development-secret", text)
