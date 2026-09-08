import multiprocessing
import os


def env_int(name, default):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
wsgi_app = "config.wsgi:application"

workers = env_int("WEB_CONCURRENCY", min(2, multiprocessing.cpu_count()))
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "sync")
threads = env_int("GUNICORN_THREADS", 1)

timeout = env_int("GUNICORN_TIMEOUT", 120)
graceful_timeout = env_int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = env_int("GUNICORN_KEEPALIVE", 5)

max_requests = env_int("GUNICORN_MAX_REQUESTS", 500)
max_requests_jitter = env_int("GUNICORN_MAX_REQUESTS_JITTER", 50)
preload_app = os.getenv("GUNICORN_PRELOAD", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

accesslog = "-"
errorlog = "-"
capture_output = True
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
