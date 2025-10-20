"""Test cost tracking functionality (TICKET 3)."""
import pytest
from app.core.config import settings
from app.domain.providers.openai_client import OpenAIClient


@pytest.mark.unit
@pytest.mark.ticket3
class TestCostTracking:
    """Test cost calculation from token usage (TICKET 3)."""

    def test_compute_cost_gpt4o_mini(self):
        """Test cost calculation for gpt-4o-mini."""
        client = OpenAIClient()
        
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
        }
        
        cost_cents = client.compute_cost("gpt-4o-mini", usage)
        
        # (100/1000 * 0.15) + (50/1000 * 0.60) = 0.015 + 0.030 = 0.045 USD = 4.5 cents
        expected = (100 / 1000 * 0.15 + 50 / 1000 * 0.60) * 100
        
        assert abs(cost_cents - expected) < 0.01  # Allow small floating point errors

    def test_compute_cost_gpt4o(self):
        """Test cost calculation for gpt-4o."""
        client = OpenAIClient()
        
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
        }
        
        cost_cents = client.compute_cost("gpt-4o", usage)
        
        # (1000/1000 * 2.50) + (500/1000 * 10.00) = 2.50 + 5.00 = 7.50 USD = 750 cents
        expected = (1000 / 1000 * 2.50 + 500 / 1000 * 10.00) * 100
        
        assert abs(cost_cents - expected) < 0.01

    def test_compute_cost_zero_tokens(self):
        """Test cost calculation with zero tokens."""
        client = OpenAIClient()
        
        usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }
        
        cost_cents = client.compute_cost("gpt-4o-mini", usage)
        
        assert cost_cents == 0.0

    def test_compute_cost_unknown_model(self):
        """Test cost calculation for unknown model returns zero."""
        client = OpenAIClient()
        
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
        }
        
        cost_cents = client.compute_cost("unknown-model", usage)
        
        assert cost_cents == 0.0

    def test_get_model_pricing_config(self):
        """Test that pricing config is accessible."""
        pricing = settings.get_model_pricing("openai", "gpt-4o-mini")
        
        assert "input_per_1k" in pricing
        assert "output_per_1k" in pricing
        assert pricing["input_per_1k"] > 0
        assert pricing["output_per_1k"] > 0

