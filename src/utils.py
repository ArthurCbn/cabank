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


def is_periodic_occurence_ignored(
        date: str,
        periodic_id: int,
        ignore_periodics: dict[int, list[str]]) -> bool :
    
    if periodic_id not in ignore_periodics :
        return False
    
    if date in ignore_periodics[periodic_id] :
        return True
    
    return False


def apply_ignore_to_period(
        period: pd.DataFrame,
        ignore_periodics: dict[str, list[str]]) -> pd.DataFrame :
    
    def _is_row_ignored(
            row: pd.Series,
            ignore_periodics: dict[int, list[str]]=ignore_periodics) -> bool :
        
        if ( periodic_id := row["periodic_id"] ) is None :
            return False
        
        date = row["date"].strftime("%Y-%m-%d")
        return is_periodic_occurence_ignored(date, periodic_id, ignore_periodics)

    period.loc[:, "is_ignored"] = period.apply(_is_row_ignored, axis=1)

    return period


def update_category_name(
        old_name: str,
        new_name: str,
        user_folder: Path) :
    
    for data_file in user_folder.rglob("*.csv") :
        df = pd.read_csv(data_file)
        if "category" in df.columns :
            df.loc[:, "category"] = df["category"].replace(old_name, new_name)
            df.to_csv(data_file, index=False)
