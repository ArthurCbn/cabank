from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
from cabank.utils import (
    safe_get,
    safe_concat,
    apply_modifs_to_period,
    split_amount,
)
import uuid
from decimal import Decimal, ROUND_HALF_UP


# region PERIODICS

def get_all_occurences_in_period(
        periodic: pd.Series,
        period_start: datetime,
        period_end: datetime) -> list[datetime] :
    
    days_interval = safe_get(periodic, "days", 0)
    months_interval = safe_get(periodic, "months", 0)

    assert days_interval >= 0
    assert months_interval >= 0

    if days_interval + months_interval == 0 :
        return []
    
    interval_dt = relativedelta(months=months_interval, days=days_interval)

    if ( first_day := safe_get(periodic, "first", None) ) is None :
        first_day = period_start

    if not ( ( last_day := safe_get(periodic, "last", None) ) is None ) :
        period_end = min(period_end, last_day + relativedelta(days=1)) # +1d because we check '< period_end' but last_day is included
    
    occurence = first_day
    while occurence < period_start :
        occurence += interval_dt

    all_occurences = []
    while occurence < period_end :
        all_occurences.append(occurence)
        occurence += interval_dt

    return all_occurences        


def get_all_periodics_in_period(
        period_start: datetime,
        period_end: datetime,
        data: pd.DataFrame) -> pd.DataFrame :
    
    all_periodics = pd.DataFrame(columns=["category", "tags", "description", "amount", "date", "periodic_id"])
    for i, periodic in data.iterrows() :
        
        occurences = get_all_occurences_in_period(periodic, period_start, period_end)
        for occurence in occurences :
            all_periodics.loc[len(all_periodics)] = [
                safe_get(periodic, "category", "NO CATEGORY"),
                safe_get(periodic, "tags", []),
                safe_get(periodic, "description", "NO DESCRIPTION"),
                safe_get(periodic, "amount", 0),
                occurence,
                safe_get(periodic, "id", None)
            ]
    
    return all_periodics

# endregion


# region AGGREGATION

def get_aggregated_period(
        period_start: datetime,
        period_end: datetime,
        periodics: pd.DataFrame,
        ponctuals: pd.DataFrame,
        modify_periodic_occurences: dict[str, dict[str, float|None]]) -> pd.DataFrame :

    period_items = ponctuals[ponctuals.apply(lambda row: period_start <= row["date"] < period_end, axis=1)].copy()
    
    if not period_items.empty :
        period_items.loc[:, "amount"] *= -1
        period_items.loc[:, "periodic_id"] = None

    period_periodics = get_all_periodics_in_period(period_start, period_end, periodics)

    period = safe_concat(period_items, period_periodics).reset_index(drop=True)
    
    if period.empty :
        period["is_ignored"] = pd.Series(dtype="bool")
        return period
    
    period.loc[:, "is_ignored"] = False
    
    adjusted_period = apply_modifs_to_period(
        period=period,
        modify_periodic_occurences=modify_periodic_occurences,
    )

    return adjusted_period 


def get_real_period(
        period_start: datetime,
        period_end: datetime,
        periodics: pd.DataFrame,
        ponctuals: pd.DataFrame,
        modify_periodic_occurences: dict[str, dict[str, float|None]]) -> pd.DataFrame :

    return get_aggregated_period(
        period_start=period_start, 
        period_end=period_end, 
        periodics=periodics, 
        ponctuals=ponctuals, 
        modify_periodic_occurences=modify_periodic_occurences
    )


def get_budget_period(
        period_start: datetime,
        period_end: datetime,
        periodics: pd.DataFrame,
        budget_periodics: pd.DataFrame,
        budget_ponctuals: pd.DataFrame) -> pd.DataFrame :
    
    corrected_budget_periodics = budget_periodics.copy()
    corrected_budget_periodics.loc[:, "amount"] *= -1

    return get_aggregated_period(
        period_start=period_start, 
        period_end=period_end, 
        periodics=safe_concat(periodics, corrected_budget_periodics), 
        ponctuals=budget_ponctuals,
        modify_periodic_occurences={}
    )

# endregion


# region BALANCE

def get_daily_balance(
        period_start: datetime,
        period_end: datetime,
        aggregated_period: pd.DataFrame,
        start_offset: float=0.) -> pd.DataFrame :

    one_day = relativedelta(days=1)
    daily_balance = pd.DataFrame(columns=["date", "balance"])

    day = period_start - one_day # TO SHOW THE FIRST BUMP
    while day < period_end :

        expenses_before_day = (
            ( aggregated_period["date"] <= day ) & 
            ( aggregated_period["is_ignored"] == False )
        )

        balance = aggregated_period[expenses_before_day]["amount"].sum() + start_offset
        daily_balance.loc[len(daily_balance)] = [day, balance]
        
        day+=one_day
    
    return daily_balance

# endregion


# region OFFSET

def get_offset(
        ref_day: datetime,
        ref_balance: float,
        target_day: datetime,
        periodics: pd.DataFrame,
        ponctuals: pd.DataFrame,
        modify_periodic_occurences: dict[str, dict[str, float|None]]) -> float :
    """
    Keep in mind that balance on day D is at the end of day D.
    Here we want the offset at the START of day target_day. 2 situations :

    
    1)   ref_day    target_day
         ___|___________|____
             
    We compute the following period :

    ref_day    target_day (END)
       |___________|
                  |
             target_day - 1 = START of target_day
    
    offset = balance(target_day - 1) + ref_balance - balance(ref_day)

    -----

    2)  target_day    ref_day
          ___|___________|____
             
    We compute the following period :

    target_day   ref_day (END)
        |___________|
    
    offset = ref_balance - balance(ref_day)
    """
    
    if ref_day < target_day :
        ref_period_start = ref_day
        ref_period_end = target_day
        start_of_target_day = target_day - relativedelta(days=1)
    else :
        ref_period_start = target_day
        ref_period_end = ref_day + relativedelta(days=1)

    past_period = get_real_period(
        period_start=ref_period_start,
        period_end=ref_period_end,
        periodics=periodics,
        ponctuals=ponctuals,
        modify_periodic_occurences=modify_periodic_occurences,
    )

    past_balance = get_daily_balance(
        period_start=ref_period_start,
        period_end=ref_period_end,
        aggregated_period=past_period,
    )

    ref_day_balance = past_balance[past_balance["date"] == ref_day]["balance"].iloc[0]
    
    if ref_day < target_day :
        start_of_target_day_balance = past_balance[past_balance["date"] == start_of_target_day]["balance"].iloc[0]
        offset = start_of_target_day_balance + ref_balance - ref_day_balance
    else :
        offset = ref_balance - ref_day_balance

    return offset

# endregion


# region CHECKPOINT

def build_checkpoint_adjustments(
    checkpoints: pd.DataFrame,
    periodics: pd.DataFrame,
    ponctuals: pd.DataFrame,
    modify_periodic_occurences: dict,
    category: str="Quotidien",
    tags: list[str]=[],
    adjustments_step_days: int|None=7,
) -> pd.DataFrame:
    """
    Build synthetic ponctual expenses that reconcile real balances
    between successive checkpoints.
    """

    if len(checkpoints) < 2:
        return pd.DataFrame(columns=[
            "date", "category", "tags", "description", "amount", "id"
        ])

    synthetic_rows = []

    for i in range(len(checkpoints) - 1):
        c_start = checkpoints.iloc[i]
        c_end = checkpoints.iloc[i+1]

        period_start = c_start["date"]
        period_end = c_end["date"]
        period_duration = (period_end - period_start).days

        # --- Real variation
        real_delta = c_end["net_position"] - c_start["net_position"]
        
        # --- Theoretical variation (from recorded expenses)
        aggregated_period = get_real_period(
            period_start=period_start + relativedelta(days=1), # This includes period_start but we want expenses starting from the next day
            period_end=period_end + relativedelta(days=1), # This excludes period_end but we include expenses on period_end day
            periodics=periodics,
            ponctuals=ponctuals,
            modify_periodic_occurences=modify_periodic_occurences,
        )

        theoretical_delta = aggregated_period["amount"].sum()

        adjustment = -(Decimal(real_delta) - Decimal(theoretical_delta)) # all amounts are entered negatively
        adjustment = float(adjustment.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP))

        # Ignore near-zero noise
        if abs(adjustment) < 0.01:
            continue
        
        # Only 1 adjustment if the interval between checkpoints is too short 
        if (adjustments_step_days is None) or (period_duration <= adjustments_step_days) :
            synthetic_rows.append({
                "date": period_end,
                "category": category,
                "tags": tags,
                "description": (
                    f"Ajustement auto checkpoint"
                    f"{period_start.date()} → {period_end.date()}"
                ),
                "amount": adjustment,
                "id": str(uuid.uuid4())
            })
            continue
        
        # Stretch the adjustments over the time between the checkpoints
        number_of_adjustments = period_duration // adjustments_step_days
        splitted_adjustment = split_amount(adjustment, number_of_adjustments)

        for i in range(number_of_adjustments) :
            adjustment_date = period_start + relativedelta(days=(i+1)*adjustments_step_days)
            synthetic_rows.append({
                "date": adjustment_date,
                "category": category,
                "tags": tags,
                "description": (
                    f"Ajustement auto checkpoint"
                    f"{period_start.date()} → {period_end.date()}"
                ),
                "amount": splitted_adjustment[i],
                "id": str(uuid.uuid4())
            })

    return pd.DataFrame(synthetic_rows)

# endregion

def get_provisions(
        period_start: datetime,
        period_end: datetime,
        periodics: pd.DataFrame,
        modify_periodic_occurences: dict[str, dict[str, float|None]]
) -> pd.DataFrame :
    
    period_duration_days = (period_end - period_start).days
    period_duration_months = round(period_duration_days/30)
    
    periodics_this_period = get_all_periodics_in_period(
        period_start=period_start,
        period_end=period_end,
        data=periodics,
    )
    periodics_this_period = apply_modifs_to_period(
        period=periodics_this_period,
        modify_periodic_occurences=modify_periodic_occurences,
    )

    periodics_this_year = get_all_periodics_in_period(
        period_start=period_start,
        period_end=period_start + relativedelta(years=1),
        data=periodics,
    )
    periodics_this_year = apply_modifs_to_period(
        period=periodics_this_year,
        modify_periodic_occurences=modify_periodic_occurences,
    )

    periodics_this_period_grouped = periodics_this_period[["amount", "periodic_id", "description"]].groupby(["periodic_id", "description"]).sum()
    periodics_this_year_grouped = periodics_this_year[["amount", "periodic_id", "description"]].groupby(["periodic_id", "description"]).sum()

    smoothed_periodics = periodics_this_year_grouped
    smoothed_periodics["amount"] = smoothed_periodics["amount"].apply(lambda x: round(x*(period_duration_months/12), 2))

    merged = (
        smoothed_periodics[["amount"]]
        .merge(
            periodics_this_period_grouped[["amount"]],
            left_index=True,
            right_index=True,
            how="outer",
            suffixes=("_smoothed", "_period")
        )
        .fillna(0)
        .droplevel("periodic_id")
    )

    if len(merged) == 0 :
        merged["provision"] = []
    else :
        merged["provision"] = round(merged["amount_smoothed"] - merged["amount_period"], 2)

    return merged[abs(merged["provision"]) > 1e-4]