FROM python:3.13.3-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_LOAD_DOTENV=false \
    DJANGO_DEBUG=false \
    HOME=/tmp \
    PORT=8000

WORKDIR /app

RUN groupadd --system smartdex \
    && useradd --system --gid smartdex --home-dir /app --shell /usr/sbin/nologin smartdex

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY . .

RUN DJANGO_DEBUG=true python manage.py collectstatic --noinput \
    && chown -R smartdex:smartdex /app/chroma_db

USER smartdex

EXPOSE 8000

CMD ["gunicorn", "--config", "gunicorn.conf.py", "config.wsgi:application"]
