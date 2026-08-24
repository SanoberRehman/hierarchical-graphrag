# syntax=docker/dockerfile:1
# Build context is the repo root (so pyproject.toml, README.md, and backend/ are
# all available). The import root is `app` — matching tests (pythonpath=[backend])
# and CI — because backend/app is copied to /srv/app and WORKDIR is /srv.
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TIKTOKEN_CACHE_DIR=/srv/.tiktoken_cache

WORKDIR /srv

# Install runtime dependencies (declared in pyproject; packages=[] => deps only).
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && pip install .

# Pre-download the tiktoken encoding into a shared cache dir so the container
# works without runtime network access to the tiktoken CDN — and remains
# readable after we drop to the non-root user below.
RUN mkdir -p "$TIKTOKEN_CACHE_DIR" \
    && python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

# Application code.
COPY backend/app ./app

# Run as an unprivileged user (defense-in-depth; matches the frontend image).
RUN adduser --system --no-create-home --uid 1001 appuser \
    && chown -R appuser /srv
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
