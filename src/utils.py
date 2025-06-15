import pandas as pd
from typing import Any
from datetime import datetime
from pathlib import Path


def safe_get(
        row: pd.Series,
        key: str,
        default: Any=None) -> Any :
    
    val = row.get(key, default)
    return default if pd.isna(val) else val


def format_datetime(serie: pd.Series) -> pd.Series :
    return pd.to_datetime(serie, format="%Y-%m-%d")


def safe_concat(
        df1: pd.DataFrame,
        df2: pd.DataFrame) -> pd.DataFrame :
    
    if len(df1) == 0 :
        return df2
    
    if len(df2) == 0 :
        return df1
    
    return pd.concat([df1, df2])


def combine_and_save_csv(
        modified_df: pd.DataFrame,
        path: Path,
        isolated_df: pd.DataFrame|None=None) :
    
    # Avoid useless warning
    if ( isolated_df is None ) or ( len(isolated_df) == 0 ) :
        modified_df.to_csv(path, index=False)
        return

    reunited_df = safe_concat(modified_df, isolated_df)
    reunited_df.to_csv(path, index=False)
