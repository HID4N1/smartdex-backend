import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


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
