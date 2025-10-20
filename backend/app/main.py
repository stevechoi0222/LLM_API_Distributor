"""Main FastAPI application."""
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import redis.asyncio as redis
from app.core.config import settings
from app.core.logging import setup_logging, get_logger, bind_context, log_request, log_response
from app.core.idempotency import IdempotencyManager, set_idempotency_manager
from app.core.rate_limit import RateLimiter, set_rate_limiter
from app.db.session import init_db, close_db
from app.domain.schemas import HealthResponse
from app.api.v1 import routes_campaigns, routes_ingest, routes_runs, routes_exports

# Setup logging
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("application_starting", version=settings.app_version)

    # Initialize database
    await init_db()

    # Initialize Redis
    redis_client = redis.from_url(settings.redis_url)
    await redis_client.ping()
    logger.info("redis_connected")

    # Initialize global managers
    set_idempotency_manager(IdempotencyManager(redis_client))
    set_rate_limiter(RateLimiter(redis_client))

    logger.info("application_ready")

    yield

    # Shutdown
    logger.info("application_shutting_down")
    await close_db()
    await redis_client.close()
    logger.info("application_stopped")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Marketing/visibility engine for Generative Search Engines",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all requests and responses."""
    request_id = str(time.time())
    bind_context(request_id=request_id)

    start_time = time.time()
    log_request(request_id, request.method, request.url.path)

    response = await call_next(request)

    duration_ms = (time.time() - start_time) * 1000
    log_response(request_id, response.status_code, duration_ms)

    return response


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Health endpoint
@app.get("/healthz", response_model=HealthResponse, tags=["health"])
async def health_check():
    """Health check endpoint.
    
    Checks database and Redis connectivity.
    """
    from datetime import datetime
    from app.db.session import engine
    from sqlalchemy import text
    import redis.asyncio as redis

    # Check database
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.error("health_check_db_failed", error=str(e))
        db_status = f"unhealthy: {str(e)}"

    # Check Redis
    try:
        redis_client = redis.from_url(settings.redis_url)
        await redis_client.ping()
        await redis_client.close()
        redis_status = "healthy"
    except Exception as e:
        logger.error("health_check_redis_failed", error=str(e))
        redis_status = f"unhealthy: {str(e)}"

    # Overall status
    status = "healthy" if db_status == "healthy" and redis_status == "healthy" else "degraded"

    return HealthResponse(
        status=status,
        database=db_status,
        redis=redis_status,
        timestamp=datetime.utcnow(),
    )


# Include routers
app.include_router(routes_campaigns.router)
app.include_router(routes_ingest.router)
app.include_router(routes_runs.router)
app.include_router(routes_exports.router)


# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/healthz",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


