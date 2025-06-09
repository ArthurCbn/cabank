from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
from enum import Enum
import matplotlib.pyplot as plt
import streamlit as st
from typing import Any

class Category(str, Enum) :
    xyz="test xyz"
    abc="test abc"

    def __str__(self):
        return self.value

FIRST_DAY = 6
PERIODICS = pd.DataFrame({
    "category": [Category.xyz, Category.abc],
    "description": ["abc", "def"],
    "amount": [1500, -1300],
    "first": ["05/06/2025", "01/03/2025"],
    "days": [14, None],
    "months": [None, 1]

})
PONCTUALS_REAL = pd.DataFrame({
    "category": [Category.xyz, Category.abc],
    "description": ["abc -15", "def -280"],
    "amount": [-150, -280],
    "date": ["09/08/2025", "28/08/2025"]
})
PERIODICS_BUDGET = PERIODICS
PONCTUALS_BUDGET = pd.DataFrame({
    "category": [Category.xyz, Category.abc],
    "description": ["abc -15 budg", "def -280 budg"],
    "amount": [-12, -19],
    "date": ["15/08/2025", "31/08/2025"]
})

# region Utils
def safe_get(
        row: pd.Series,
        key: str,
        default: Any=None) -> Any :
    
    val = row.get(key, default)
    return default if pd.isna(val) else val
# endregion

# region periodics

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
        periodics: pd.DataFrame=PERIODICS,
        ponctuals: pd.DataFrame=PONCTUALS_REAL) -> pd.DataFrame :

    return get_aggregated_period(period_start, period_end, periodics, ponctuals)


def get_budget_period(
        period_start: datetime,
        period_end: datetime,
        periodics: pd.DataFrame=PERIODICS,
        periodics_budget: pd.DataFrame=PERIODICS_BUDGET,
        ponctuals_budget: pd.DataFrame=PONCTUALS_BUDGET) -> pd.DataFrame :
    
    return get_aggregated_period(period_start, period_end, pd.concat([periodics, periodics_budget]), ponctuals_budget)


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



month_dt = datetime.strptime(f"{FIRST_DAY}/08/2025", "%d/%m/%Y")
end_month_dt = month_dt + relativedelta(months=1)


# LIVE EDIT EVERY CSV !!!
# edited_df = st.data_editor(
#     PONCTUALS_REAL,
#     num_rows="dynamic",
#     use_container_width=True,
#     key="csv_editor"
# )


real = get_real_period(month_dt, end_month_dt)
budget = get_budget_period(month_dt, end_month_dt)

balance_real = get_daily_balance(month_dt, end_month_dt, real)
balance_budget = get_daily_balance(month_dt, end_month_dt, budget)

plt.plot(balance_real["date"], balance_real["balance"])
plt.plot(balance_budget["date"], balance_budget["balance"])
plt.show()

# TODO 
# Find a way to archive the past periodics : archive the whole history + balance of each month ?
