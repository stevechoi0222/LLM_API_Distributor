"""Multi-sheet XLSX exporter for user_excel_v0_1 format (TKT-013)."""
from typing import Any, Dict, List
import pandas as pd
from app.core.logging import get_logger
from app.exporters.base import BaseExporter

logger = get_logger(__name__)


class XLSXMultiSheetExporter(BaseExporter):
    """Export results to multi-sheet Excel format."""

    async def export(
        self,
        data: List[Dict[str, Any]],
        output_path: str,
        mapper_data: Dict[str, Any] = None,
    ) -> str:
        """Export data to multi-sheet XLSX.
        
        Args:
            data: List of result dictionaries (not used if mapper_data provided)
            output_path: Output file path
            mapper_data: Pre-mapped data with query_rows and citation_rows
            
        Returns:
            File path
        """
        if mapper_data:
            # Use pre-mapped data from user_excel_v0_1 mapper
            return await self._export_multi_sheet(mapper_data, output_path)
        else:
            # Fallback to single sheet
            return await self._export_single_sheet(data, output_path)

    async def _export_multi_sheet(
        self,
        mapper_data: Dict[str, Any],
        output_path: str,
    ) -> str:
        """Export multi-sheet XLSX with exact column order.
        
        Args:
            mapper_data: Dictionary with query_rows, citation_rows, and column specs
            output_path: Output file path
            
        Returns:
            File path
        """
        query_rows = mapper_data.get("query_rows", [])
        citation_rows = mapper_data.get("citation_rows", [])
        query_columns = mapper_data.get("query_columns", [])
        citation_columns = mapper_data.get("citation_columns", [])
        
        # Create DataFrames with exact column order
        if query_rows:
            query_df = pd.DataFrame(query_rows)
            # Reorder columns to match spec
            query_df = query_df[query_columns]
        else:
            # Empty sheet with headers
            query_df = pd.DataFrame(columns=query_columns)
        
        if citation_rows:
            citation_df = pd.DataFrame(citation_rows)
            # Reorder columns to match spec
            citation_df = citation_df[citation_columns]
        else:
            # Empty sheet with headers
            citation_df = pd.DataFrame(columns=citation_columns)
        
        # Write to Excel with multiple sheets
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            query_df.to_excel(
                writer,
                sheet_name="AI_API_04_QUERY",
                index=False
            )
            citation_df.to_excel(
                writer,
                sheet_name="AI_API_08_CITATION",
                index=False
            )
        
        logger.info(
            "multi_sheet_xlsx_exported",
            output_path=output_path,
            query_rows=len(query_rows),
            citation_rows=len(citation_rows)
        )
        
        return output_path

    async def _export_single_sheet(
        self,
        data: List[Dict[str, Any]],
        output_path: str,
    ) -> str:
        """Export single-sheet XLSX (fallback).
        
        Args:
            data: List of result dictionaries
            output_path: Output file path
            
        Returns:
            File path
        """
        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False, engine="openpyxl")
        
        logger.info(
            "single_sheet_xlsx_exported",
            output_path=output_path,
            rows=len(data)
        )
        
        return output_path

