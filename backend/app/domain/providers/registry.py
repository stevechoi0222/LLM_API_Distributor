"""Provider registry with feature flag support (TICKET 4)."""
from typing import Dict, List
from app.core.config import settings
from app.core.logging import get_logger
from app.domain.providers.base import ProviderClient
from app.domain.providers.openai_client import OpenAIClient
from app.domain.providers.gemini_client import GeminiClient
from app.domain.providers.perplexity_client import PerplexityClient

logger = get_logger(__name__)


class ProviderRegistry:
    """Registry of available provider clients."""

    def __init__(self):
        """Initialize provider registry."""
        self._providers: Dict[str, ProviderClient] = {}
        self._enabled_providers: List[str] = []
        self._initialize()

    def _initialize(self):
        """Initialize providers based on feature flags."""
        # OpenAI
        if settings.enable_openai:
            self._providers["openai"] = OpenAIClient()
            self._enabled_providers.append("openai")
            logger.info("provider_enabled", name="openai")
        
        # Gemini (stub, disabled by default)
        if settings.enable_gemini:
            self._providers["gemini"] = GeminiClient()
            self._enabled_providers.append("gemini")
            logger.info("provider_enabled", name="gemini")
        
        # Perplexity (stub, disabled by default)
        if settings.enable_perplexity:
            self._providers["perplexity"] = PerplexityClient()
            self._enabled_providers.append("perplexity")
            logger.info("provider_enabled", name="perplexity")

        logger.info(
            "provider_registry_initialized",
            enabled_providers=self._enabled_providers
        )

    def get(self, name: str) -> ProviderClient:
        """Get provider by name.
        
        Args:
            name: Provider name
            
        Returns:
            Provider client
            
        Raises:
            ValueError: If provider not found or disabled
        """
        name = name.lower()
        
        if name not in self._enabled_providers:
            raise ValueError(
                f"Provider '{name}' is not enabled. "
                f"Enabled providers: {', '.join(self._enabled_providers)}"
            )
        
        return self._providers[name]

    def is_enabled(self, name: str) -> bool:
        """Check if provider is enabled.
        
        Args:
            name: Provider name
            
        Returns:
            True if enabled
        """
        return name.lower() in self._enabled_providers

    def get_enabled_providers(self) -> List[str]:
        """Get list of enabled provider names.
        
        Returns:
            List of provider names
        """
        return self._enabled_providers.copy()


# Global registry instance
provider_registry = ProviderRegistry()


