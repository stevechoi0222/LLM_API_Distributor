"""Security and authentication utilities."""
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# API key header
api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> str:
    """Verify API key from request header.
    
    Args:
        api_key: API key from x-api-key header
        
    Returns:
        Validated API key
        
    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not api_key:
        logger.warning("api_key_missing")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Include x-api-key header.",
        )
    
    valid_keys = settings.get_api_keys_list()
    if api_key not in valid_keys:
        logger.warning("api_key_invalid", key_prefix=api_key[:8])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    
    return api_key


