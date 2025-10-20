"""Test provider registry and feature flags (TICKET 4)."""
import pytest
from app.domain.providers.registry import ProviderRegistry
from app.core.config import settings


@pytest.mark.unit
@pytest.mark.ticket4
class TestProviderRegistry:
    """Test provider feature flags (TICKET 4)."""

    def test_openai_enabled_by_default(self):
        """Test that OpenAI is enabled by default."""
        registry = ProviderRegistry()
        
        assert registry.is_enabled("openai")
        assert "openai" in registry.get_enabled_providers()

    def test_gemini_disabled_by_default(self):
        """Test that Gemini is disabled by default."""
        registry = ProviderRegistry()
        
        assert not registry.is_enabled("gemini")
        assert "gemini" not in registry.get_enabled_providers()

    def test_perplexity_disabled_by_default(self):
        """Test that Perplexity is disabled by default."""
        registry = ProviderRegistry()
        
        assert not registry.is_enabled("perplexity")
        assert "perplexity" not in registry.get_enabled_providers()

    def test_get_enabled_provider(self):
        """Test getting an enabled provider."""
        registry = ProviderRegistry()
        
        client = registry.get("openai")
        
        assert client is not None
        assert client.name == "openai"

    def test_get_disabled_provider_raises(self):
        """Test that getting disabled provider raises ValueError."""
        registry = ProviderRegistry()
        
        with pytest.raises(ValueError) as exc:
            registry.get("gemini")
        
        assert "not enabled" in str(exc.value).lower()

    def test_case_insensitive_provider_names(self):
        """Test that provider names are case-insensitive."""
        registry = ProviderRegistry()
        
        assert registry.is_enabled("OPENAI")
        assert registry.is_enabled("OpenAI")
        assert registry.is_enabled("openai")

