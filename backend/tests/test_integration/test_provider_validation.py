"""Integration tests for provider feature flag validation (TKT-002)."""
import pytest
from unittest.mock import patch
from app.domain.providers.registry import ProviderRegistry


@pytest.mark.integration
@pytest.mark.tkt002
class TestProviderValidation:
    """Test provider feature flag validation and registry."""

    def test_registry_only_enabled_providers(self):
        """Test registry only includes enabled providers."""
        # Mock settings with only OpenAI enabled
        with patch("app.domain.providers.registry.settings") as mock_settings:
            mock_settings.enable_openai = True
            mock_settings.enable_gemini = False
            mock_settings.enable_perplexity = False
            
            registry = ProviderRegistry()
            enabled = registry.get_enabled_providers()
            
            assert "openai" in enabled
            assert "gemini" not in enabled
            assert "perplexity" not in enabled

    def test_get_disabled_provider_raises_error(self):
        """Test accessing disabled provider raises ValueError."""
        # Mock settings with only OpenAI enabled
        with patch("app.domain.providers.registry.settings") as mock_settings:
            mock_settings.enable_openai = True
            mock_settings.enable_gemini = False
            mock_settings.enable_perplexity = False
            
            registry = ProviderRegistry()
            
            # Should succeed for enabled provider
            client = registry.get("openai")
            assert client is not None
            
            # Should fail for disabled providers
            with pytest.raises(ValueError) as exc_info:
                registry.get("gemini")
            assert "not enabled" in str(exc_info.value).lower()
            
            with pytest.raises(ValueError) as exc_info:
                registry.get("perplexity")
            assert "not enabled" in str(exc_info.value).lower()

    def test_is_enabled_check(self):
        """Test is_enabled method."""
        with patch("app.domain.providers.registry.settings") as mock_settings:
            mock_settings.enable_openai = True
            mock_settings.enable_gemini = False
            mock_settings.enable_perplexity = False
            
            registry = ProviderRegistry()
            
            assert registry.is_enabled("openai") is True
            assert registry.is_enabled("gemini") is False
            assert registry.is_enabled("perplexity") is False

    def test_registry_all_providers_enabled(self):
        """Test registry with all providers enabled."""
        with patch("app.domain.providers.registry.settings") as mock_settings:
            mock_settings.enable_openai = True
            mock_settings.enable_gemini = True
            mock_settings.enable_perplexity = True
            mock_settings.openai_api_key = "test-key"
            mock_settings.google_api_key = "test-key"
            mock_settings.perplexity_api_key = "test-key"
            
            registry = ProviderRegistry()
            enabled = registry.get_enabled_providers()
            
            assert len(enabled) == 3
            assert "openai" in enabled
            assert "gemini" in enabled
            assert "perplexity" in enabled
            
            # Should be able to get all providers
            openai_client = registry.get("openai")
            gemini_client = registry.get("gemini")
            perplexity_client = registry.get("perplexity")
            
            assert openai_client.name == "openai"
            assert gemini_client.name == "gemini"
            assert perplexity_client.name == "perplexity"

    def test_registry_case_insensitive(self):
        """Test registry handles case-insensitive provider names."""
        with patch("app.domain.providers.registry.settings") as mock_settings:
            mock_settings.enable_openai = True
            mock_settings.enable_gemini = False
            mock_settings.enable_perplexity = False
            
            registry = ProviderRegistry()
            
            # Should work with different cases
            assert registry.is_enabled("OpenAI") is True
            assert registry.is_enabled("OPENAI") is True
            assert registry.is_enabled("openai") is True
            
            # Get should also be case-insensitive
            client1 = registry.get("openai")
            client2 = registry.get("OPENAI")
            assert client1.name == client2.name


@pytest.mark.integration
@pytest.mark.tkt002
class TestProviderCostCalculation:
    """Test cost calculation across providers."""

    def test_openai_vs_gemini_vs_perplexity_cost(self):
        """Test cost differences between providers."""
        from app.domain.providers.openai_client import OpenAIClient
        from app.domain.providers.gemini_client import GeminiClient
        from app.domain.providers.perplexity_client import PerplexityClient
        
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_tokens": 1500
        }
        
        openai_client = OpenAIClient()
        gemini_client = GeminiClient()
        perplexity_client = PerplexityClient()
        
        openai_cost = openai_client.compute_cost("gpt-4o-mini", usage)
        gemini_cost = gemini_client.compute_cost("gemini-pro", usage)
        perplexity_cost = perplexity_client.compute_cost(
            "llama-3.1-sonar-small-128k-online", 
            usage
        )
        
        # All should return positive costs
        assert openai_cost > 0
        assert gemini_cost > 0
        assert perplexity_cost > 0
        
        # Costs should be different (different pricing)
        assert openai_cost != gemini_cost or gemini_cost != perplexity_cost


@pytest.mark.integration
@pytest.mark.tkt002  
class TestRunValidationWithDisabledProviders:
    """Test run creation validation rejects disabled providers."""

    @pytest.mark.asyncio
    async def test_run_rejects_disabled_gemini(self, client, auth_headers, db_session):
        """Test run creation rejects Gemini when disabled."""
        from app.db.models import Campaign
        
        # Create campaign
        campaign = Campaign(name="Test Campaign")
        db_session.add(campaign)
        await db_session.commit()
        
        # Try to create run with Gemini (disabled by default)
        run_data = {
            "campaign_id": campaign.id,
            "label": "Test Run",
            "providers": [
                {
                    "name": "gemini",
                    "model": "gemini-pro"
                }
            ],
            "prompt_version": "v1"
        }
        
        response = await client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json=run_data
        )
        
        # Should fail with validation error
        # Note: This requires the /runs endpoint to validate against enabled providers
        # The test documents the expected behavior
        assert response.status_code in [400, 422]  # Bad request or validation error

    @pytest.mark.asyncio
    async def test_run_accepts_enabled_openai(self, client, auth_headers, db_session):
        """Test run creation accepts OpenAI when enabled."""
        from app.db.models import Campaign, Topic, Persona, Question
        
        # Create campaign with questions
        campaign = Campaign(name="Test Campaign")
        db_session.add(campaign)
        await db_session.commit()
        
        topic = Topic(campaign_id=campaign.id, title="Test Topic")
        db_session.add(topic)
        
        persona = Persona(name="Test User")
        db_session.add(persona)
        await db_session.commit()
        
        question = Question(
            topic_id=topic.id,
            persona_id=persona.id,
            text="Test question?"
        )
        db_session.add(question)
        await db_session.commit()
        
        # Create run with OpenAI (enabled by default)
        run_data = {
            "campaign_id": campaign.id,
            "label": "Test Run",
            "providers": [
                {
                    "name": "openai",
                    "model": "gpt-4o-mini"
                }
            ],
            "prompt_version": "v1"
        }
        
        response = await client.post(
            "/api/v1/runs",
            headers=auth_headers,
            json=run_data
        )
        
        # Should succeed
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "pending"

