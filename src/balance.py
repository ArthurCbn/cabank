from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
from .utils import (
    safe_get,
    safe_concat,
    apply_ignore_to_period,
)


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
    
    all_periodics = pd.DataFrame(columns=["category", "description", "amount", "date", "periodic_id"])
    for i, periodic in data.iterrows() :
        
        occurences = get_all_occurences_in_period(periodic, period_start, period_end)
        for occurence in occurences :
            all_periodics.loc[len(all_periodics)] = [
                safe_get(periodic, "category", "NO CATEGORY"),
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
        ponctuals: pd.DataFrame) -> pd.DataFrame :

    period_items = ponctuals[ponctuals.apply(lambda row: period_start <= row["date"] < period_end, axis=1)].copy()
    
    if not period_items.empty :
        period_items.loc[:, "amount"] *= -1
        period_items.loc[:, "periodic_id"] = None

    period_periodics = get_all_periodics_in_period(period_start, period_end, periodics)

    period = safe_concat(period_items, period_periodics).reset_index(drop=True)
    
    if not period.empty :
        period.loc[:, "is_ignored"] = False
    else :
        period["is_ignored"] = pd.Series(dtype="bool")

    return period 


def get_real_period(
        period_start: datetime,
        period_end: datetime,
        periodics: pd.DataFrame,
        ponctuals: pd.DataFrame) -> pd.DataFrame :

    return get_aggregated_period(period_start, period_end, periodics, ponctuals)


def get_budget_period(
        period_start: datetime,
        period_end: datetime,
        periodics: pd.DataFrame,
        budget_periodics: pd.DataFrame,
        budget_ponctuals: pd.DataFrame) -> pd.DataFrame :
    
    corrected_budget_periodics = budget_periodics.copy()
    corrected_budget_periodics.loc[:, "amount"] *= -1

    return get_aggregated_period(period_start, period_end, safe_concat(periodics, corrected_budget_periodics), budget_ponctuals)

# endregion


# region BALANCE

def get_daily_balance(
        period_start: datetime,
        period_end: datetime,
        aggregated_period: pd.DataFrame,
        start_offset: float=0.) -> pd.DataFrame :

    one_day = relativedelta(days=1)
    daily_balance = pd.DataFrame(columns=["date", "balance"])

    day = period_start
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
        ignore_periodics: dict[str, list[str]]) -> float :
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
    )

    past_period_adjusted = apply_ignore_to_period(
        period=past_period,
        ignore_periodics=ignore_periodics
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
