FROM python:3.13.3-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_LOAD_DOTENV=false \
    DJANGO_DEBUG=false \
    HOME=/tmp \
    PORT=8000 \
    CHROMA_SEED_DIR=/app/chroma_seed \
    CHROMA_DIR=/tmp/smartdex/chroma_runtime \
    CHROMA_MANIFEST_PATH=/app/chroma_seed/manifest.json

WORKDIR /app

RUN groupadd --system smartdex \
    && useradd --system --gid smartdex --home-dir /app --shell /usr/sbin/nologin smartdex

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY . .

RUN DJANGO_DEBUG=true python manage.py collectstatic --noinput \
    && mv /app/chroma_db /app/chroma_seed \
    && mv /app/chroma_index_manifest.json /app/chroma_seed/manifest.json \
    && chown -R root:root /app/chroma_seed \
    && find /app/chroma_seed -type d -exec chmod 0555 {} + \
    && find /app/chroma_seed -type f -exec chmod 0444 {} + \
    && chmod 0555 /app/scripts/docker-entrypoint.sh

USER smartdex

EXPOSE 8000

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["gunicorn", "--config", "gunicorn.conf.py", "config.wsgi:application"]
