from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
from .utils import safe_get


# region PERIODICS

def get_all_occurences_in_period(
        periodic: pd.Series,
        period_start: datetime,
        period_end: datetime) -> list[datetime] :
    
    days_interval = safe_get(periodic, "days", 0)
    months_interval = safe_get(periodic, "months", 0)
    
    assert days_interval >= 0
    assert months_interval >= 0
    assert days_interval + months_interval > 0
    
    interval_dt = relativedelta(months=months_interval, days=days_interval)

    first_day = safe_get(periodic, "first", None)
    if first_day is None :
        first_day_dt = period_start
    else :
        first_day_dt = datetime.strptime(first_day, "%d/%m/%Y")

    occurence = first_day_dt
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
    
    all_periodics = pd.DataFrame(columns=["category", "description", "amount", "date"])
    for _, periodic in data.iterrows() :
        
        occurences = get_all_occurences_in_period(periodic, period_start, period_end)
        for occurence in occurences :
            all_periodics.loc[len(all_periodics)] = [
                safe_get(periodic, "category", "NO CATEGORY"),
                safe_get(periodic, "description", "NO DESCRIPTION"),
                safe_get(periodic, "amount", 0),
                occurence.strftime("%d/%m/%Y")
            ]
    
    return all_periodics

# endregion


# region AGGREGATION

def get_aggregated_period(
        period_start: datetime,
        period_end: datetime,
        periodics: pd.DataFrame,
        ponctuals: pd.DataFrame) -> pd.DataFrame :

    period_items = ponctuals[ponctuals.apply(lambda row: period_start <= datetime.strptime(row["date"], "%d/%m/%Y") < period_end, axis=1)]
    period_periodics = get_all_periodics_in_period(period_start, period_end, periodics)

    return pd.concat([period_items, period_periodics])


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
        periodics_budget: pd.DataFrame,
        ponctuals_budget: pd.DataFrame) -> pd.DataFrame :
    
    return get_aggregated_period(period_start, period_end, pd.concat([periodics, periodics_budget]), ponctuals_budget)

# endregion


# region BALANCE

def get_daily_balance(
        period_start: datetime,
        period_end: datetime,
        aggregated_period: pd.DataFrame) -> pd.DataFrame :

    aggregated_period["date_dt"] = pd.to_datetime(aggregated_period["date"], format="%d/%m/%Y")
    one_day = relativedelta(days=1)
    daily_balance = pd.DataFrame(columns=["date", "balance"])

    day = period_start
    while day < period_end :
        balance = aggregated_period[aggregated_period["date_dt"] <= day]["amount"].sum()
        daily_balance.loc[len(daily_balance)] = [day, balance]
        
        day+=one_day
    
    return daily_balance

# endregion
