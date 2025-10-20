"""Base mapper interface (TICKET 7 - versioning)."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseMapper(ABC):
    """Base class for partner API mappers."""

    version: str = "v1"

    @abstractmethod
    def map(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Map normalized result to partner schema.
        
        Args:
            result: Normalized result data
            
        Returns:
            Mapped payload for partner API
        """
        pass


