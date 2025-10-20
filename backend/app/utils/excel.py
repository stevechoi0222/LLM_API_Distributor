"""Excel/CSV parsing utilities."""
from typing import Any, Dict, List
import pandas as pd
from io import BytesIO


def parse_excel(content: bytes) -> pd.DataFrame:
    """Parse Excel file to DataFrame.
    
    Args:
        content: File content as bytes
        
    Returns:
        Parsed DataFrame
    """
    return pd.read_excel(BytesIO(content))


def parse_csv(content: bytes) -> pd.DataFrame:
    """Parse CSV file to DataFrame.
    
    Args:
        content: File content as bytes
        
    Returns:
        Parsed DataFrame
    """
    return pd.read_csv(BytesIO(content))


def fuzzy_match_column(
    columns: List[str],
    candidates: List[str],
) -> Dict[str, str]:
    """Fuzzy match DataFrame columns to expected names.
    
    Args:
        columns: Actual column names
        candidates: Expected column names
        
    Returns:
        Mapping of expected -> actual column names
    """
    mapping = {}
    
    for candidate in candidates:
        # Exact match (case-insensitive)
        for col in columns:
            if col.lower() == candidate.lower():
                mapping[candidate] = col
                break
        
        # Partial match
        if candidate not in mapping:
            for col in columns:
                if candidate.lower() in col.lower() or col.lower() in candidate.lower():
                    mapping[candidate] = col
                    break
    
    return mapping


def dataframe_to_dict_list(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Convert DataFrame to list of dictionaries.
    
    Args:
        df: DataFrame
        
    Returns:
        List of row dictionaries
    """
    # Replace NaN with None
    df = df.where(pd.notna(df), None)
    return df.to_dict(orient="records")


