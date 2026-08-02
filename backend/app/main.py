"""FastAPI application factory for the TKP backend."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.app.api.deps import limiter
from backend.app.api.routes_documents import router as documents_router
from backend.app.api.routes_jobs import router as jobs_router
from backend.app.api.routes_stream import router as stream_router
from backend.app.config import get_settings
from backend.app.db.session import check_db_connection
from backend.app.logging_config import configure_logging, get_logger
from backend.app.schemas.tkp import HealthResponse

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("app_startup", environment=settings.environment)
    yield
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="GyanSetu Teacher Knowledge Package API",
        description=(
            "Upload educational documents and generate structured Teacher Knowledge "
            "Packages via a multi-stage LangGraph pipeline."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, cast(Any, _rate_limit_exceeded_handler))
    app.add_middleware(SlowAPIMiddleware)

    origins = settings.cors_origin_list
    if not origins:
        origins = ["http://localhost:8501"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(documents_router)
    api_v1.include_router(jobs_router)
    api_v1.include_router(stream_router)

    @api_v1.get(
        "/health",
        response_model=HealthResponse,
        summary="Health check (API v1)",
        tags=["health"],
    )
    async def health_v1() -> HealthResponse:
        """Check database connectivity and API key presence (no LLM calls)."""
        return await _health()

    app.include_router(api_v1)

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health_root() -> HealthResponse:
        """Root health endpoint mirroring ``/api/v1/health``."""
        return await _health()

    return app


async def _health() -> HealthResponse:
    settings = get_settings()
    db_ok = await check_db_connection()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        database="up" if db_ok else "down",
        gemini_key_present=bool(settings.gemini_api_key),
        groq_key_present=bool(settings.groq_api_key),
        environment=settings.environment,
    )


app = create_app()
