# syntax=docker/dockerfile:1
# Backend image: one image, three roles (api | worker | beat) chosen by command.

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /usr/local/bin/uv
# ffmpeg/ffprobe validate uploaded video/audio and render video projects (content studio);
# DejaVu provides the font for burned-in text overlays and subtitles (VIDEO_FONT_FILE).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# --- development: all deps, source is bind-mounted by docker-compose -------
FROM base AS development
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-install-project
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# --- production: runtime deps only, non-root ------------------------------
FROM base AS production
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY . .
RUN useradd --system --uid 10001 --no-create-home app \
    && DJANGO_SETTINGS_MODULE=config.settings.production \
       DJANGO_SECRET_KEY=build-only-placeholder-not-used-at-runtime-0123456789abcdef \
       DJANGO_ALLOWED_HOSTS=build DATABASE_URL=sqlite:////tmp/build.db REDIS_URL=redis://build:6379/0 \
       python manage.py collectstatic --noinput \
    && chown -R app /app
USER app
ENV DJANGO_SETTINGS_MODULE=config.settings.production
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
