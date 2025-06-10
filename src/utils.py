import pandas as pd
from typing import Any
from datetime import datetime


def safe_get(
        row: pd.Series,
        key: str,
        default: Any=None) -> Any :
    
    val = row.get(key, default)
    return default if pd.isna(val) else val


def format_datetime(serie: pd.Series) -> pd.Series :
    return pd.to_datetime(serie, format="%Y-%m-%d")