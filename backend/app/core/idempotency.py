"""Redis-based idempotency management."""
import hashlib
import json
from typing import Any, Dict, Optional
import redis.asyncio as redis
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class IdempotencyManager:
    """Manage idempotency using Redis."""

    def __init__(self, redis_client: redis.Redis):
        """Initialize idempotency manager.
        
        Args:
            redis_client: Async Redis client
        """
        self.redis = redis_client
        self.ttl = 86400 * 7  # 7 days

    def generate_key(
        self,
        provider: str,
        model: str,
        prompt_version: str,
        question_id: str,
        persona_id: str,
        question_text: str,
        provider_settings: Dict[str, Any],
    ) -> str:
        """Generate idempotency key from request parameters.
        
        Hash function: hash(provider, model, prompt_version, question_id, 
                           persona_id, normalized_question_text, provider_settings)
        
        Args:
            provider: Provider name
            model: Model name
            prompt_version: Prompt template version
            question_id: Question ID
            persona_id: Persona ID
            question_text: Question text (will be normalized)
            provider_settings: Provider-specific settings
            
        Returns:
            SHA256 hash as hex string
        """
        # Normalize question text (lowercase, strip whitespace)
        normalized_text = " ".join(question_text.lower().split())
        
        # Create stable JSON representation of settings
        settings_json = json.dumps(provider_settings, sort_keys=True)
        
        # Combine all components
        components = [
            provider,
            model,
            prompt_version,
            str(question_id),
            str(persona_id),
            normalized_text,
            settings_json,
        ]
        
        # Generate hash
        hash_input = "|".join(components).encode("utf-8")
        return hashlib.sha256(hash_input).hexdigest()

    async def check_exists(self, idempotency_key: str) -> Optional[str]:
        """Check if idempotency key already exists.
        
        Args:
            idempotency_key: Idempotency key to check
            
        Returns:
            Existing run_item_id if found, None otherwise
        """
        redis_key = f"idempotency:{idempotency_key}"
        run_item_id = await self.redis.get(redis_key)
        
        if run_item_id:
            logger.info(
                "idempotency_hit",
                idempotency_key=idempotency_key[:16],
                run_item_id=run_item_id.decode() if isinstance(run_item_id, bytes) else run_item_id
            )
            return run_item_id.decode() if isinstance(run_item_id, bytes) else run_item_id
        
        return None

    async def store(self, idempotency_key: str, run_item_id: str) -> None:
        """Store idempotency key with run_item_id.
        
        Args:
            idempotency_key: Idempotency key
            run_item_id: Associated run_item_id
        """
        redis_key = f"idempotency:{idempotency_key}"
        await self.redis.setex(redis_key, self.ttl, run_item_id)
        
        logger.debug(
            "idempotency_stored",
            idempotency_key=idempotency_key[:16],
            run_item_id=run_item_id
        )

    async def delete(self, idempotency_key: str) -> None:
        """Delete idempotency key (for testing/cleanup).
        
        Args:
            idempotency_key: Idempotency key to delete
        """
        redis_key = f"idempotency:{idempotency_key}"
        await self.redis.delete(redis_key)


# Global instance (initialized in main.py)
_idempotency_manager: Optional[IdempotencyManager] = None


def get_idempotency_manager() -> IdempotencyManager:
    """Get global idempotency manager instance."""
    if _idempotency_manager is None:
        raise RuntimeError("Idempotency manager not initialized")
    return _idempotency_manager


def set_idempotency_manager(manager: IdempotencyManager) -> None:
    """Set global idempotency manager instance."""
    global _idempotency_manager
    _idempotency_manager = manager


