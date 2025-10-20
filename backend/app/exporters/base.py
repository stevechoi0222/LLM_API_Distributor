"""Base exporter interface."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseExporter(ABC):
    """Base class for exporters."""

    @abstractmethod
    async def export(
        self,
        data: List[Dict[str, Any]],
        output_path: str,
    ) -> str:
        """Export data to file.
        
        Args:
            data: List of result dictionaries
            output_path: Output file path
            
        Returns:
            File path or URL
        """
        pass


