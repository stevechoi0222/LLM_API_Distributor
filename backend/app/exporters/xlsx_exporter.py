"""XLSX exporter."""
from typing import Any, Dict, List
import pandas as pd
from app.exporters.base import BaseExporter


class XLSXExporter(BaseExporter):
    """Export results to Excel format."""

    async def export(
        self,
        data: List[Dict[str, Any]],
        output_path: str,
    ) -> str:
        """Export data to XLSX.
        
        Args:
            data: List of result dictionaries
            output_path: Output file path
            
        Returns:
            File path
        """
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Write Excel
        df.to_excel(output_path, index=False, engine="openpyxl")
        
        return output_path


