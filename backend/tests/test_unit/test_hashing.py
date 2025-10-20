"""Test idempotency hashing utilities."""
import pytest
from app.utils.hashing import compute_idempotency_hash


@pytest.mark.unit
class TestIdempotencyHash:
    """Test idempotency hash generation."""

    def test_deterministic_hash(self):
        """Test that same inputs produce same hash."""
        params = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "prompt_version": "v1",
            "question_id": "Q001",
            "persona_id": "P001",
            "question_text": "How does the battery perform?",
            "provider_settings": {"temperature": 0.0, "max_tokens": 1000},
        }
        
        hash1 = compute_idempotency_hash(**params)
        hash2 = compute_idempotency_hash(**params)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    def test_different_inputs_different_hash(self):
        """Test that different inputs produce different hashes."""
        base_params = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "prompt_version": "v1",
            "question_id": "Q001",
            "persona_id": "P001",
            "question_text": "How does the battery perform?",
            "provider_settings": {"temperature": 0.0},
        }
        
        hash1 = compute_idempotency_hash(**base_params)
        
        # Change question text
        modified_params = {**base_params, "question_text": "Different question?"}
        hash2 = compute_idempotency_hash(**modified_params)
        
        assert hash1 != hash2

    def test_normalized_question_text(self):
        """Test that whitespace differences don't affect hash."""
        base_params = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "prompt_version": "v1",
            "question_id": "Q001",
            "persona_id": "P001",
            "question_text": "How  does   the battery perform?",
            "provider_settings": {},
        }
        
        normalized_params = {
            **base_params,
            "question_text": "How does the battery perform?"
        }
        
        hash1 = compute_idempotency_hash(**base_params)
        hash2 = compute_idempotency_hash(**normalized_params)
        
        # Should be same after normalization
        assert hash1 == hash2

    def test_settings_order_independent(self):
        """Test that provider_settings dict order doesn't affect hash."""
        params1 = {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "prompt_version": "v1",
            "question_id": "Q001",
            "persona_id": "P001",
            "question_text": "Test?",
            "provider_settings": {"temperature": 0.0, "max_tokens": 1000},
        }
        
        params2 = {
            **params1,
            "provider_settings": {"max_tokens": 1000, "temperature": 0.0},
        }
        
        hash1 = compute_idempotency_hash(**params1)
        hash2 = compute_idempotency_hash(**params2)
        
        assert hash1 == hash2

