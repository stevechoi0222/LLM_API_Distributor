"""User Excel v0.1 mapper for multi-provider XLSX export (TKT-013)."""
import json
import re
from typing import Any, Dict, List
from app.core.logging import get_logger
from app.exporters.mappers.base import BaseMapper

logger = get_logger(__name__)


class UserExcelV01Mapper(BaseMapper):
    """Mapper for user_excel_v0_1 format with multi-sheet support."""

    version = "v1"
    
    # Exact column headers as specified
    QUERY_COLUMNS = [
        "campaign",
        "run_id",
        "question_id",
        "persona_name",
        "question_text",
        "provider",
        "model",
        "response_text",
        "latency_ms",
        "prompt_tokens",
        "completion_tokens",
        "cost_cents",
        "status"
    ]
    
    CITATION_COLUMNS = [
        "run_id",
        "question_id",
        "provider",
        "citation_index",
        "citation_url"
    ]
    
    MAX_CELL_LENGTH = 10000  # Truncate to avoid Excel issues

    def map(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Map single result - not used for this mapper.
        
        This mapper operates on batch of results via map_batch.
        """
        raise NotImplementedError(
            "user_excel_v0_1 mapper uses map_batch for multi-sheet export"
        )

    def map_batch(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Map batch of results to multi-sheet XLSX structure.
        
        Args:
            results: List of normalized result dictionaries
            
        Returns:
            Dictionary with:
                - query_rows: List of dicts for AI_API_04_QUERY sheet
                - citation_rows: List of dicts for AI_API_08_CITATION sheet
        """
        query_rows = []
        citation_rows = []
        
        for result in results:
            # Extract query row data
            query_row = self._build_query_row(result)
            if query_row:
                query_rows.append(query_row)
            
            # Extract citation rows
            citations = self._extract_citations(result)
            citation_rows.extend(citations)
        
        logger.info(
            "user_excel_v0_1_mapped",
            query_count=len(query_rows),
            citation_count=len(citation_rows)
        )
        
        return {
            "query_rows": query_rows,
            "citation_rows": citation_rows,
            "query_columns": self.QUERY_COLUMNS,
            "citation_columns": self.CITATION_COLUMNS
        }

    def _build_query_row(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Build single row for AI_API_04_QUERY sheet.
        
        Args:
            result: Normalized result dictionary
            
        Returns:
            Dictionary with query row data
        """
        # Extract campaign name (from topic or default)
        campaign = result.get("campaign_name", "Unknown Campaign")
        
        # Get response text: prefer JSON answer, fallback to raw text
        response_text = ""
        response_data = result.get("response", {})
        if isinstance(response_data, dict):
            response_text = response_data.get("answer", "")
        
        if not response_text:
            response_text = result.get("answer", "")
        
        # Truncate long text
        response_text = self._truncate(response_text)
        
        # Build row
        row = {
            "campaign": self._truncate(campaign),
            "run_id": result.get("run_id", ""),
            "question_id": result.get("question_id", ""),
            "persona_name": self._truncate(result.get("persona_name", "")),
            "question_text": self._truncate(result.get("question_text", "")),
            "provider": result.get("provider", ""),
            "model": result.get("model", ""),
            "response_text": response_text,
            "latency_ms": result.get("latency_ms", 0),
            "prompt_tokens": result.get("token_usage", {}).get("prompt_tokens", 0),
            "completion_tokens": result.get("token_usage", {}).get("completion_tokens", 0),
            "cost_cents": result.get("cost_cents", 0.0),
            "status": result.get("status", "")
        }
        
        return row

    def _extract_citations(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract citations from result for AI_API_08_CITATION sheet.
        
        Args:
            result: Normalized result dictionary
            
        Returns:
            List of citation row dictionaries
        """
        citation_rows = []
        
        run_id = result.get("run_id", "")
        question_id = result.get("question_id", "")
        provider = result.get("provider", "")
        
        # Get citations from response
        citations = result.get("citations", [])
        if not isinstance(citations, list):
            citations = []
        
        # Validate and create rows
        for idx, citation_url in enumerate(citations):
            if self._is_valid_url(citation_url):
                citation_rows.append({
                    "run_id": run_id,
                    "question_id": question_id,
                    "provider": provider,
                    "citation_index": idx,  # 0-based index
                    "citation_url": self._truncate(citation_url)
                })
        
        return citation_rows

    def _is_valid_url(self, url: str) -> bool:
        """Validate URL (http/https only).
        
        Args:
            url: URL string to validate
            
        Returns:
            True if valid http/https URL
        """
        if not isinstance(url, str):
            return False
        
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        return bool(url_pattern.match(url))

    def _truncate(self, text: str, max_length: int = None) -> str:
        """Truncate text to max length.
        
        Args:
            text: Text to truncate
            max_length: Maximum length (default: MAX_CELL_LENGTH)
            
        Returns:
            Truncated text
        """
        if not isinstance(text, str):
            text = str(text) if text is not None else ""
        
        max_len = max_length or self.MAX_CELL_LENGTH
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text


# Mapper registry
MAPPER_REGISTRY = {
    "user_excel_v0_1": {
        "v1": UserExcelV01Mapper(),
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

