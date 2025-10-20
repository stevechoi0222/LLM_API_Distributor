"""Hashing utilities for idempotency."""
import hashlib
import json
from typing import Any, Dict


def compute_idempotency_hash(
    provider: str,
    model: str,
    prompt_version: str,
    question_id: str,
    persona_id: str,
    question_text: str,
    provider_settings: Dict[str, Any],
) -> str:
    """Compute idempotency hash from request parameters.
    
    Args:
        provider: Provider name
        model: Model name
        prompt_version: Prompt version
        question_id: Question ID
        persona_id: Persona ID
        question_text: Question text
        provider_settings: Provider settings
        
    Returns:
        SHA256 hash as hex string
    """
    # Normalize question text
    normalized_text = " ".join(question_text.lower().split())
    
    # Create stable JSON
    settings_json = json.dumps(provider_settings, sort_keys=True)
    
    # Combine components
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


