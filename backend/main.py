"""CrisisWatch AI — main FastAPI application entry point.

Exposes the REST API for real-time global crisis monitoring: crisis events,
ML-powered predictions, situation reports, and severity alerts.

Run with (from the ``backend/`` directory):

    uvicorn main:app --reload
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

try:  # pragma: no cover
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

from db.database import AsyncSessionLocal, init_db

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


def _env(name: str, default: str) -> str:
    """Read an environment variable with a fallback default."""
    value = os.getenv(name)
    return value if value is not None else default


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable with a fallback default."""
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


APP_NAME = "CrisisWatch AI"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Real-Time Global Crisis Intelligence Platform"

CORS_ORIGINS = [
    origin.strip()
    for origin in _env(
        "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000"
    ).split(",")
    if origin.strip()
]

RATE_LIMIT_ENABLED = _env_bool("RATE_LIMIT_ENABLED", True)
RATE_LIMIT_REQUESTS = _env_int("RATE_LIMIT_REQUESTS", 120)
RATE_LIMIT_WINDOW_SECONDS = _env_int("RATE_LIMIT_WINDOW_SECONDS", 60)

LOG_LEVEL = _env("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("crisiswatch")

# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #


class InMemoryRateLimiter:
    """Sliding-window rate limiter keyed by client IP.

    This is a per-process, in-memory implementation suitable for a single
    application instance. For horizontally scaled deployments, swap it for a
    Redis-backed limiter.
    """

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """Return ``True`` if the key is within its rate budget."""
        now = time.monotonic()
        bucket = self._hits[key]
        while bucket and now - bucket[0] > self.window_seconds:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(now)
        return True

    def reset(self) -> None:
        """Clear all recorded requests (used in maintenance/logout paths)."""
        self._hits.clear()


rate_limiter = InMemoryRateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS)

# --------------------------------------------------------------------------- #
# Startup / shutdown helpers
# --------------------------------------------------------------------------- #


async def _check_database() -> bool:
    """Return ``True`` when the database answers a trivial query."""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - health reports, never raises
        logger.exception("Health check failed: database unreachable")
        return False


async def _load_ml_models() -> None:
    """Load ML models from the first available loader module.

    Searches common module paths; fails gracefully so the API still starts
    when the model toolkit has not been wired in yet — models are then loaded
    lazily on first prediction.
    """
    candidates = ("ml.model_loader", "ml.models", "ml")
    loader_attrs = ("load_models", "load_all_models", "initialize")

    for module_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for attr in loader_attrs:
            loader = getattr(module, attr, None)
            if not callable(loader):
                continue
            try:
                if asyncio.iscoroutinefunction(loader):
                    await loader()
                else:
                    await asyncio.to_thread(loader)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Model loader %s.%s failed; will retry on demand.",
                    module_name,
                    attr,
                    exc_info=True,
                )
                continue
            logger.info("ML models loaded via %s.%s", module_name, attr)
            return
    logger.warning(
        "No ML loader module found; models will be loaded lazily on "
        "first prediction request."
    )


async def _run_initial_ingestion() -> None:
    """Kick off the initial data ingestion pipeline from the first available source."""
    candidates = ("data.ingestion", "data.sources.ingestion", "data.sources")
    runner_attrs = ("run_initial_ingestion", "ingest_initial", "start_ingestion", "run")

    for module_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        for attr in runner_attrs:
            runner = getattr(module, attr, None)
            if not callable(runner):
                continue
            try:
                if asyncio.iscoroutinefunction(runner):
                    await runner()
                else:
                    await asyncio.to_thread(runner)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Initial ingestion via %s.%s failed.",
                    module_name,
                    attr,
                    exc_info=True,
                )
                continue
            logger.info("Initial data ingestion completed via %s.%s", module_name, attr)
            return
    logger.warning(
        "No initial-ingestion module found; skipping startup ingestion. "
        "Incoming feeds continue to populate the system."
    )


async def _startup(app: FastAPI) -> None:
    """Run once at application startup."""
    logger.info("Starting %s v%s", APP_NAME, APP_VERSION)

    try:
        await init_db()
        logger.info("Database tables initialized.")
    except Exception:  # noqa: BLE001
        logger.exception("Failed to initialize database tables.")

    try:
        await _load_ml_models()
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error while loading ML models.")

    try:
        await _run_initial_ingestion()
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected error during initial ingestion.")

    app.state.started_at = time.time()
    logger.info("Startup sequence complete.")


async def _shutdown(app: FastAPI) -> None:
    """Run once at application shutdown."""
    logger.info("Shutting down %s", APP_NAME)
    rate_limiter.reset()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager that drives startup and shutdown events."""
    await _startup(app)
    try:
        yield
    finally:
        await _shutdown(app)


# --------------------------------------------------------------------------- #
# Application + middleware
# --------------------------------------------------------------------------- #

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next: Any):
    """Reject requests that exceed the per-client rate budget."""
    if not RATE_LIMIT_ENABLED:
        return await call_next(request)

    client = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client = forwarded_for.split(",")[0].strip() or client

    if rate_limiter.allow(client):
        return await call_next(request)

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded",
            "retry_after_seconds": RATE_LIMIT_WINDOW_SECONDS,
        },
        headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)},
    )


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next: Any):
    """Log every request with its method, path, status, and duration."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000.0
    logger.info(
        "%s %s -> %d (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials="*" not in CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a consistent JSON 500 for any unhandled exception."""
    logger.exception(
        "Unhandled exception while serving %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# --------------------------------------------------------------------------- #
# Routers
# --------------------------------------------------------------------------- #

_ROUTER_MODULES = ("crises", "predictions", "reports", "alerts")


def _register_routers() -> None:
    """Import and register the domain routers.

    Routers are registered as their modules become available so the API can
    boot during incremental development; missing routers log a warning rather
    than preventing startup. Each router module must expose a ``router``
    attribute.
    """
    for name in _ROUTER_MODULES:
        try:
            module = importlib.import_module(f"routers.{name}")
        except ImportError as exc:
            logger.warning(
                "Router 'routers.%s' is not available yet and was skipped (%s).",
                name,
                exc,
            )
            continue
        except Exception:  # noqa: BLE001
            logger.exception("Failed to import router 'routers.%s'.", name)
            continue

        router = getattr(module, "router", None)
        if router is None:
            logger.warning(
                "Module 'routers.%s' exists but does not expose a 'router'; skipped.",
                name,
            )
            continue
        app.include_router(router)
        logger.info("Registered router: %s", name)


_register_routers()

# --------------------------------------------------------------------------- #
# System endpoints
# --------------------------------------------------------------------------- #


@app.get("/", tags=["system"])
def root() -> dict[str, Any]:
    """Return basic API metadata."""
    up = getattr(app.state, "started_at", None)
    uptime_seconds = round(time.time() - up, 1) if up else None
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "description": APP_DESCRIPTION,
        "status": "operational",
        "uptime_seconds": uptime_seconds,
        "endpoints": {
            "docs": "/docs",
            "openapi": "/openapi.json",
            "health": "/health",
            "crises": "/api/crises",
            "predictions": "/api/predictions",
            "reports": "/api/reports",
            "alerts": "/api/alerts",
        },
    }


@app.get("/health", tags=["system"])
async def health_check() -> JSONResponse:
    """Health probe: verifies database connectivity and reports uptime."""
    database_ok = await _check_database()
    up = getattr(app.state, "started_at", None)
    uptime_seconds = round(time.time() - up, 1) if up else None

    payload: dict[str, Any] = {
        "status": "ok" if database_ok else "degraded",
        "version": APP_VERSION,
        "database": "ok" if database_ok else "unreachable",
        "uptime_seconds": uptime_seconds,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(payload, status_code=200 if database_ok else 503)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    host = _env("HOST", "0.0.0.0")
    port = _env_int("PORT", 8000)
    reload = _env_bool("AUTO_RELOAD", False)
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=_env("UVICORN_LOG_LEVEL", "info").lower(),
    )