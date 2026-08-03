# Multi-stage backend image for Render (Docker) / container hosts.
# Ephemeral disk — writable temps under /tmp; durable state in Postgres (Neon).

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
COPY backend ./backend
COPY migrations ./migrations
COPY alembic.ini ./

RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime

RUN useradd -m -u 1000 user

WORKDIR /app
# PORT default 8000 for local `docker run` without Render; Render injects PORT at runtime.
# Keep process count / BLAS threads at 1 so MiniLM+torch fit Render free-tier 512MB.
ENV PATH="/app/.venv/bin:/home/user/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    PORT=8000 \
    HOME=/home/user \
    WEB_CONCURRENCY=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false \
    HF_HOME=/tmp/hf_cache \
    HF_HUB_CACHE=/tmp/hf_cache/hub \
    SENTENCE_TRANSFORMERS_HOME=/tmp/hf_cache/sentence_transformers \
    TORCH_HOME=/tmp/hf_cache/torch \
    XDG_CACHE_HOME=/tmp/xdg_cache

RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder --chown=user:user /app/.venv /app/.venv
COPY --from=builder --chown=user:user /app/backend /app/backend
COPY --from=builder --chown=user:user /app/migrations /app/migrations
COPY --from=builder --chown=user:user /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=user:user /app/pyproject.toml /app/pyproject.toml

USER user

# Documents the local/default listen port; Render sets PORT dynamically at runtime.
EXPOSE 8000

# Shell form so HEALTHCHECK honors $PORT (Render injects it; default matches ENV/EXPOSE).
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT:-8000}/health || exit 1

# Render injects PORT; fallback 8000 for local docker run without that env var.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
