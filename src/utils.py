import pandas as pd
from typing import Any
from datetime import datetime
from pathlib import Path
import plotly.graph_objects as go


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


def get_periodic_occurence_modifications(
        date: str,
        amount: float,
        periodic_id: str,
        modify_periodic_occurences: dict[str, dict[str, float|None]]) -> tuple[float, bool] :
    
    if periodic_id not in modify_periodic_occurences :
        return amount, False
    
    if date not in ( periodic_modifs := modify_periodic_occurences[periodic_id] ):
        return amount, False
        
    if not ( adjusted_amount := periodic_modifs[date] ) is None :
        return adjusted_amount, False
    
    return amount, True


def is_periodic_occurence_ignored(
        date: str,
        periodic_id: str,
        modify_periodic_occurences: dict[str, dict[str, float|None]]) -> bool :
    
    _, is_ignored = get_periodic_occurence_modifications(
        date=date, 
        amount=0,
        periodic_id=periodic_id,
        modify_periodic_occurences=modify_periodic_occurences
    )

    return is_ignored


def apply_modifs_to_period(
        period: pd.DataFrame,
        modify_periodic_occurences: dict[str, dict[str, float|None]]) -> pd.DataFrame :
    
    def _modify_row(
            row: pd.Series,
            modify_periodic_occurences: dict[str, dict[str, float|None]]=modify_periodic_occurences) -> tuple[float, bool] :
        
        amount  = row["amount"]
        if ( periodic_id := row["periodic_id"] ) is None :
            return amount, False
        
        date = row["date"].strftime("%Y-%m-%d")

        return get_periodic_occurence_modifications(date, amount, periodic_id, modify_periodic_occurences)

    modified_period = period.copy()
    modified_period[["amount", "is_ignored"]] = modified_period.apply(_modify_row, axis=1, result_type="expand")

    return modified_period


def update_category_name(
        old_name: str,
        new_name: str,
        user_folder: Path) :
    
    for data_file in user_folder.rglob("*.csv") :
        df = pd.read_csv(data_file)
        if "category" in df.columns :
            df.loc[:, "category"] = df["category"].replace(old_name, new_name)
            df.to_csv(data_file, index=False)


def plot_custom_waterfall(
        fig: go.Figure,
        categories: list[str],
        amounts: list[float],
        colors: list[str],
        amounts_budget: list[float]|None=None) :
    
    # Style parameters
    if amounts_budget is None :
        bar_width = 0.8
        offset = 0
    else :
        bar_width = 0.35
        offset = bar_width/2 +0.05

    # Cumulative heights
    y_base = []
    current = 0
    for amt in amounts[:-1]:
        y_base.append(current)
        current += amt
    
    # Last bar is a total => base at 0
    y_base.append(0)

    # First bar is shared
    fig.add_trace(go.Bar(
        x=[0],
        y=[amounts[0]],
        base=[0],
        width=0.8,
        marker=dict(color=colors[0]),
        name=categories[0],
        hovertemplate=f"{categories[0]}: {amounts[0]:,.0f}<extra></extra>"
    ))
    fig.add_shape(
        type="line",
        x0= 0.4,
        x1= offset + bar_width/2 + (1-bar_width),
        y0=y_base[0] + amounts[0],
        y1=y_base[1],
        line=dict(color="black", width=1)
    )

    # Draw the rest of the bars
    for i in range(1, len(categories)):
        fig.add_trace(go.Bar(
            x=[i - offset],
            y=[amounts[i]],
            base=[y_base[i]],
            width=bar_width,
            marker=dict(color=colors[i]),
            name=categories[i],
            hovertemplate=f"{categories[i]}: {amounts[i]:,.0f}<extra></extra>"
        ))

    # Draw connectors
    for i in range(1, len(categories) - 2):
        fig.add_shape(
            type="line",
            x0=i - offset + bar_width/2,
            x1=i - offset + bar_width/2 + (1-bar_width),
            y0=y_base[i] + amounts[i],
            y1=y_base[i + 1],
            line=dict(color="black", width=1)
        )

    # Draw last connector
    fig.add_shape(
        type="line",
        x0=len(categories)-2 - offset + bar_width/2,
        x1=len(categories)-2 - offset + bar_width/2 + (1-bar_width),
        y0=y_base[-2] + amounts[-2],
        y1=amounts[-1],
        line=dict(color="black", width=1)
    )

    if amounts_budget is None :
        return
    
    # Cumulative heights
    y_base_budget = []
    current_budget = 0
    for amt_b in amounts_budget[:-1]:
        y_base_budget.append(current_budget)
        current_budget += amt_b
    
    # Last bar is a total => base at 0
    y_base_budget.append(0)

    # Draw every bar (except the first one which is shared)
    for i in range(1, len(categories)):
        fig.add_trace(go.Bar(
            x=[i + offset],
            y=[amounts_budget[i]],
            width=bar_width,
            base=[y_base_budget[i]],
            marker=dict(color=colors[i]),
            name=categories[i],
            hovertemplate=f"{categories[i]}: {amounts_budget[i]:,.0f}<extra></extra>",
            opacity=0.3
        ))

    # Draw first connector
    fig.add_shape(
        type="line",
        x0= 0.4,
        x1= offset + bar_width/2 + (1-bar_width),
        y0=y_base_budget[0] + amounts_budget[0],
        y1=y_base_budget[1],
        line=dict(color="gray", width=1, dash="dot")
    )

    # Draw other connectors
    for i in range(1, len(categories) - 2):
        fig.add_shape(
            type="line",
            x0= i + offset + bar_width/2,
            x1= i + offset + bar_width/2 + (1-bar_width),
            y0=y_base_budget[i] + amounts_budget[i],
            y1=y_base_budget[i + 1],
            line=dict(color="gray", width=1, dash="dot")
        )

    # Draw last connector
    fig.add_shape(
        type="line",
        x0=len(categories)-2 + offset + bar_width/2,
        x1=len(categories)-2 + offset + bar_width/2 + (1-bar_width),
        y0=y_base_budget[-2] + amounts_budget[-2],
        y1=amounts_budget[-1],
        line=dict(color="gray", width=1, dash="dot")
    )
    