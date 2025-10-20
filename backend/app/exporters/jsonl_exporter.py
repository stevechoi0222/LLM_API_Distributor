"""JSONL exporter."""
import json
from typing import Any, Dict, List
from app.exporters.base import BaseExporter


class JSONLExporter(BaseExporter):
    """Export results to JSONL format."""

    async def export(
        self,
        data: List[Dict[str, Any]],
        output_path: str,
    ) -> str:
        """Export data to JSONL.
        
        Args:
            data: List of result dictionaries
            output_path: Output file path
            
        Returns:
            File path
        """
        with open(output_path, "w") as f:
            for item in data:
                f.write(json.dumps(item) + "\n")
        
        return output_path


