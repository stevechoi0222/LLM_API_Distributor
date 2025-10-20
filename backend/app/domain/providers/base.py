"""Base provider client interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class ProviderResult:
    """Result from provider invocation."""
    text: str
    citations: List[str]
    usage: Dict[str, int]  # prompt_tokens, completion_tokens
    latency_ms: int
    cost_cents: float  # TICKET 3 - computed cost
    raw_response: Any  # Original provider response
    validated_json: Optional[Dict[str, Any]] = None  # TICKET 2 - validated JSON response


class ProviderClient(ABC):
    """Base class for provider clients."""

    name: str

    @abstractmethod
    async def prepare_prompt(
        self,
        question: str,
        persona: Dict[str, Any],
        topic: Dict[str, Any],
        prompt_version: str = "v1",
    ) -> Dict[str, Any]:
        """Prepare prompt for provider.
        
        Args:
            question: Question text
            persona: Persona data
            topic: Topic data
            prompt_version: Prompt template version
            
        Returns:
            Prepared prompt data (system, user messages, etc.)
        """
        pass

    @abstractmethod
    async def invoke(
        self,
        request: Dict[str, Any],
        **settings: Any,
    ) -> ProviderResult:
        """Invoke provider API.
        
        Args:
            request: Prepared request
            **settings: Provider-specific settings
            
        Returns:
            Provider result
        """
        pass

    @abstractmethod
    def compute_cost(
        self,
        model: str,
        usage: Dict[str, int],
    ) -> float:
        """Compute cost from token usage.
        
        Args:
            model: Model name
            usage: Token usage data
            
        Returns:
            Cost in cents
        """
        pass


