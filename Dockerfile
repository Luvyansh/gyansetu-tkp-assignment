# Multi-stage backend image for Hugging Face Spaces / container hosts.
# Writable persistence must use /tmp or an external DB (Neon) — Spaces wipe local disk.

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

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    PORT=7860

RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/backend /app/backend
COPY --from=builder /app/migrations /app/migrations
COPY --from=builder /app/alembic.ini /app/alembic.ini
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

EXPOSE 7860

# HF Spaces expects the app to listen on $PORT (default 7860).
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
