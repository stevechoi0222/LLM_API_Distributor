"""Gemini provider client stub (disabled by default)."""
from typing import Any, Dict
from app.domain.providers.base import ProviderClient, ProviderResult


class GeminiClient(ProviderClient):
    """Gemini API client stub (TICKET 4 - disabled)."""

    name = "gemini"

    async def prepare_prompt(
        self,
        question: str,
        persona: Dict[str, Any],
        topic: Dict[str, Any],
        prompt_version: str = "v1",
    ) -> Dict[str, Any]:
        """Prepare prompt for Gemini.
        
        Stub implementation - not yet implemented.
        """
        raise NotImplementedError("Gemini provider not yet implemented (ENABLE_GEMINI=false)")

    async def invoke(
        self,
        request: Dict[str, Any],
        **settings: Any,
    ) -> ProviderResult:
        """Invoke Gemini API.
        
        Stub implementation - not yet implemented.
        """
        raise NotImplementedError("Gemini provider not yet implemented (ENABLE_GEMINI=false)")

    def compute_cost(
        self,
        model: str,
        usage: Dict[str, int],
    ) -> float:
        """Compute cost from token usage.
        
        Stub implementation - not yet implemented.
        """
        return 0.0


