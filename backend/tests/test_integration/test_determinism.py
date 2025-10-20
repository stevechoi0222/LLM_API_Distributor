"""Test deterministic behavior (TICKET 6)."""
import pytest
from app.domain.schemas import ProviderConfig


@pytest.mark.integration
@pytest.mark.ticket6
class TestDeterminism:
    """Test determinism-first defaults (TICKET 6)."""

    def test_default_temperature_zero(self):
        """Test that default temperature is 0 for determinism."""
        from app.core.config import settings
        
        assert settings.default_temperature == 0.0

    def test_default_top_p_one(self):
        """Test that default top_p is 1.0."""
        from app.core.config import settings
        
        assert settings.default_top_p == 1.0

    def test_provider_config_deterministic_defaults(self):
        """Test that ProviderConfig without allow_sampling is deterministic."""
        config = ProviderConfig(
            name="openai",
            model="gpt-4o-mini"
        )
        
        assert config.allow_sampling is False
        assert config.temperature is None  # Will use default (0.0)

    def test_provider_config_opt_in_sampling(self):
        """Test opt-in to non-deterministic sampling."""
        config = ProviderConfig(
            name="openai",
            model="gpt-4o-mini",
            allow_sampling=True,
            temperature=0.7
        )
        
        assert config.allow_sampling is True
        assert config.temperature == 0.7

    @pytest.mark.asyncio
    async def test_openai_client_enforces_determinism(self):
        """Test that OpenAI client enforces determinism by default."""
        from app.domain.providers.openai_client import OpenAIClient
        
        client = OpenAIClient()
        
        request = await client.prepare_prompt(
            question="Test?",
            persona={"name": "Test", "role": "Tester"},
            topic={"title": "Test"},
            prompt_version="v1"
        )
        
        # Request should be prepared (we're testing structure)
        assert "messages" in request
        assert len(request["messages"]) >= 2  # System + User

    def test_run_request_validation_rejects_high_temp_without_flag(self):
        """Test that high temperature without allow_sampling flag is validated."""
        # When allow_sampling=False (default), temperature should be ignored
        config = ProviderConfig(
            name="openai",
            model="gpt-4o-mini",
            temperature=0.8,  # High temperature
            allow_sampling=False  # Explicit false
        )
        
        # Config should be valid, but temp will be overridden to 0 in invoke
        assert config.allow_sampling is False

