"""CSV exporter."""
from typing import Any, Dict, List
import pandas as pd
from app.exporters.base import BaseExporter


class CSVExporter(BaseExporter):
    """Export results to CSV format."""

    async def export(
        self,
        data: List[Dict[str, Any]],
        output_path: str,
    ) -> str:
        """Export data to CSV.
        
        Args:
            data: List of result dictionaries
            output_path: Output file path
            
        Returns:
            File path
        """
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Write CSV
        df.to_csv(output_path, index=False)
        
        return output_path


