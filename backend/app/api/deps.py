"""API dependencies."""
from typing import AsyncGenerator
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import verify_api_key
from app.db.session import get_db_session


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency."""
    async for session in get_db_session():
        yield session


async def get_authenticated_session(
    api_key: str = Depends(verify_api_key),
    session: AsyncSession = Depends(get_session),
) -> AsyncSession:
    """Get authenticated database session."""
    return session


