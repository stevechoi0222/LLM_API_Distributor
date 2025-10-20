"""Example webhook mapper for partner API (TICKET 5)."""
from typing import Any, Dict
import httpx
from app.core.logging import get_logger
from app.exporters.mappers.base import BaseMapper

logger = get_logger(__name__)


class ExampleWebhookMapperV1(BaseMapper):
    """Example partner webhook mapper v1."""

    version = "v1"

    def map(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Map to example partner schema.
        
        Args:
            result: Normalized result
            
        Returns:
            Partner payload
        """
        # Extract data
        response_data = result.get("response", {})
        
        # Map to partner schema
        return {
            "query_id": result.get("run_item_id"),
            "question": result.get("question_text"),
            "answer": response_data.get("answer", ""),
            "sources": response_data.get("citations", []),
            "metadata": {
                "provider": result.get("provider"),
                "model": result.get("model"),
                "cost_usd": (result.get("cost_cents", 0) / 100),
                "latency_ms": result.get("latency_ms"),
            }
        }

    async def deliver(
        self,
        payload: Dict[str, Any],
        webhook_url: str,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """Deliver payload to webhook.
        
        Args:
            payload: Mapped payload
            webhook_url: Partner webhook URL
            timeout: Request timeout
            
        Returns:
            Response data
        """
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            
            logger.info(
                "webhook_delivered",
                url=webhook_url,
                status=response.status_code
            )
            
            return {
                "status_code": response.status_code,
                "body": response.text,
            }


# Mapper registry (TICKET 7)
MAPPER_REGISTRY = {
    "example_partner": {
        "v1": ExampleWebhookMapperV1(),
    }
}


def get_mapper(name: str, version: str = "v1") -> BaseMapper:
    """Get mapper by name and version.
    
    Args:
        name: Mapper name
        version: Mapper version
        
    Returns:
        Mapper instance
        
    Raises:
        ValueError: If mapper not found
    """
    if name not in MAPPER_REGISTRY:
        raise ValueError(f"Mapper '{name}' not found")
    
    if version not in MAPPER_REGISTRY[name]:
        raise ValueError(f"Mapper '{name}' version '{version}' not found")
    
    return MAPPER_REGISTRY[name][version]


