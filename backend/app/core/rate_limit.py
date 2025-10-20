"""Redis-based token bucket rate limiting."""
import asyncio
import time
from typing import Dict, Optional
import redis.asyncio as redis
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class TokenBucket:
    """Token bucket rate limiter using Redis."""

    def __init__(
        self,
        redis_client: redis.Redis,
        key: str,
        qps: int,
        burst: int,
    ):
        """Initialize token bucket.
        
        Args:
            redis_client: Async Redis client
            key: Redis key for this bucket
            qps: Queries per second (token refill rate)
            burst: Burst capacity (max tokens)
        """
        self.redis = redis_client
        self.key = f"rate_limit:{key}"
        self.qps = qps
        self.burst = burst
        self.refill_interval = 1.0 / qps  # seconds per token

    async def acquire(self, tokens: int = 1, timeout: float = 30.0) -> bool:
        """Acquire tokens from the bucket, blocking if necessary.
        
        Args:
            tokens: Number of tokens to acquire
            timeout: Max time to wait in seconds
            
        Returns:
            True if tokens acquired, False if timeout
        """
        start_time = time.time()
        
        while True:
            # Try to acquire
            if await self._try_acquire(tokens):
                return True
            
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning(
                    "rate_limit_timeout",
                    key=self.key,
                    tokens=tokens,
                    elapsed=elapsed
                )
                return False
            
            # Wait before retry
            await asyncio.sleep(0.1)

    async def _try_acquire(self, tokens: int) -> bool:
        """Try to acquire tokens without blocking.
        
        Returns:
            True if tokens acquired, False otherwise
        """
        now = time.time()
        
        # Lua script for atomic token bucket update
        script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local tokens_requested = tonumber(ARGV[2])
        local burst = tonumber(ARGV[3])
        local refill_interval = tonumber(ARGV[4])
        
        -- Get current state
        local state = redis.call('HMGET', key, 'tokens', 'last_update')
        local tokens = tonumber(state[1]) or burst
        local last_update = tonumber(state[2]) or now
        
        -- Refill tokens based on elapsed time
        local elapsed = now - last_update
        local refill = math.floor(elapsed / refill_interval)
        tokens = math.min(burst, tokens + refill)
        
        -- Try to consume tokens
        if tokens >= tokens_requested then
            tokens = tokens - tokens_requested
            redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
            redis.call('EXPIRE', key, 60)
            return 1
        else
            return 0
        end
        """
        
        result = await self.redis.eval(
            script,
            1,
            self.key,
            now,
            tokens,
            self.burst,
            self.refill_interval,
        )
        
        success = bool(result)
        
        if not success:
            logger.debug(
                "rate_limit_throttled",
                key=self.key,
                tokens_requested=tokens
            )
        
        return success


class RateLimiter:
    """Manage rate limiters for multiple providers."""

    def __init__(self, redis_client: redis.Redis):
        """Initialize rate limiter.
        
        Args:
            redis_client: Async Redis client
        """
        self.redis = redis_client
        self.buckets: Dict[str, TokenBucket] = {}

    def get_bucket(self, provider: str) -> TokenBucket:
        """Get or create token bucket for a provider.
        
        Args:
            provider: Provider name
            
        Returns:
            TokenBucket instance
        """
        if provider not in self.buckets:
            limits = settings.get_provider_rate_limits(provider)
            self.buckets[provider] = TokenBucket(
                self.redis,
                key=provider,
                qps=limits["qps"],
                burst=limits["burst"],
            )
        
        return self.buckets[provider]

    async def acquire(self, provider: str, tokens: int = 1, timeout: float = 30.0) -> bool:
        """Acquire tokens for a provider.
        
        Args:
            provider: Provider name
            tokens: Number of tokens
            timeout: Max wait time
            
        Returns:
            True if acquired, False if timeout
        """
        bucket = self.get_bucket(provider)
        return await bucket.acquire(tokens, timeout)


# Global instance (initialized in main.py)
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    if _rate_limiter is None:
        raise RuntimeError("Rate limiter not initialized")
    return _rate_limiter


def set_rate_limiter(limiter: RateLimiter) -> None:
    """Set global rate limiter instance."""
    global _rate_limiter
    _rate_limiter = limiter


