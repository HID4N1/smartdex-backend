import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

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
        "CSRF_TRUSTED_ORIGINS",
        "DEBUG",
        "DJANGO_DEBUG",
        "DJANGO_SECRET_KEY",
        "SECRET_KEY",
        "USE_X_FORWARDED_PROTO",
        "DJANGO_ENV",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_PROJECT_ID",
        "RAILWAY_SERVICE_ID",
        "DATABASE_URL",
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
        "DJANGO_DEBUG": "false",
        "DJANGO_SECRET_KEY": "test-production-secret-key",
        "ALLOWED_HOSTS": "api.smartdex.ma,smartdex-production.up.railway.app",
        "CORS_ALLOWED_ORIGINS": "https://smartdex.ma,https://www.smartdex.ma",
        "CSRF_TRUSTED_ORIGINS": "https://api.smartdex.ma,https://smartdex-production.up.railway.app",
        "DATABASE_URL": "postgresql://user:password@db.example.com:5432/smartdex",
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
assert settings.CORS_ALLOWED_ORIGINS == ["https://smartdex.ma", "https://www.smartdex.ma"]
assert "x-devis-access-token" in settings.CORS_ALLOW_HEADERS
assert settings.CSRF_TRUSTED_ORIGINS == ["https://api.smartdex.ma", "https://smartdex-production.up.railway.app"]
assert settings.ALLOWED_HOSTS == ["api.smartdex.ma", "smartdex-production.up.railway.app"]
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

    def test_wildcard_production_allowed_hosts_fails_clearly(self):
        result = run_settings_probe(
            {**self.production_env, "ALLOWED_HOSTS": "*"},
            "import config.settings",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ALLOWED_HOSTS must list explicit production hostnames", result.stderr)

    def test_missing_production_database_url_fails_clearly(self):
        env = dict(self.production_env)
        env.pop("DATABASE_URL")
        result = run_settings_probe(env, "import config.settings")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DATABASE_URL must be set", result.stderr)

    def test_invalid_integer_security_setting_fails_clearly(self):
        result = run_settings_probe(
            {**self.production_env, "SECURE_HSTS_SECONDS": "not-a-number"},
            "import config.settings",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECURE_HSTS_SECONDS must be an integer", result.stderr)

    def test_railway_deployment_cannot_silently_run_with_debug_true(self):
        result = run_settings_probe(
            {
                "DJANGO_DEBUG": "true",
                "RAILWAY_ENVIRONMENT": "production",
                "DJANGO_SECRET_KEY": "test-production-secret-key",
            },
            "import config.settings",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_DEBUG must be false", result.stderr)


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
        self.assertIn("your-openai-api-key", text)
        self.assertIn("change-me", text)
