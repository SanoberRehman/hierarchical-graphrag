# syntax=docker/dockerfile:1
# Build context is the repo root (so pyproject.toml, README.md, and backend/ are
# all available). The import root is `app` — matching tests (pythonpath=[backend])
# and CI — because backend/app is copied to /srv/app and WORKDIR is /srv.
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# Install runtime dependencies (declared in pyproject; packages=[] => deps only).
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && pip install .

# Pre-download the tiktoken encoding so the container works without runtime
# network access to the tiktoken CDN.
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

# Application code.
COPY backend/app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
