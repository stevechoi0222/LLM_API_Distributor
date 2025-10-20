"""Database session management with async SQLAlchemy."""
import subprocess
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Create async engine
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,
    echo=False,
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Set search path on connection
@event.listens_for(engine.sync_engine, "connect")
def set_search_path(dbapi_conn, connection_record):
    """Set search path to app schema on each connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute(f"SET search_path TO {settings.db_schema}, public")
    cursor.close()
    logger.debug("search_path_set", schema=settings.db_schema)


async def init_db() -> None:
    """Initialize database - run migrations if enabled."""
    if settings.db_apply_migrations:
        logger.info("applying_migrations", mode="online")
        try:
            # Run alembic upgrade head
            result = subprocess.run(
                ["alembic", "upgrade", "head"],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info("migrations_applied", output=result.stdout)
        except subprocess.CalledProcessError as e:
            logger.error(
                "migration_failed",
                error=str(e),
                stdout=e.stdout,
                stderr=e.stderr
            )
            raise
    else:
        logger.info(
            "migrations_skipped",
            reason="DB_APPLY_MIGRATIONS=false (external DB mode)"
        )
    
    # Test connection
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        logger.info("db_connection_verified", result=result.scalar())


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
    logger.info("db_connections_closed")


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session.
    
    Yields:
        AsyncSession instance
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for database session."""
    async with get_db() as session:
        yield session


