from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
from enum import Enum
import matplotlib.pyplot as plt
import streamlit as st
from typing import Any
import os
from pathlib import Path
from src.utils import (
    format_datetime,
)
from src.balance import (
    get_real_period,
    get_budget_period,
    get_daily_balance,
)

# region INIT

# region |---| Period

FIRST_DAY = 6 # TODO config file

TODAY = datetime.now()

if "horizon" not in st.session_state :
    st.session_state.horizon = 1

if "period_start" not in st.session_state :
    month = datetime.strptime(f"{FIRST_DAY}/{TODAY.month}/{TODAY.year}", "%d/%m/%Y")
    
    if TODAY.day < FIRST_DAY :
        st.session_state.period_start = month - relativedelta(month=st.session_state.horizon)
    else :   
        st.session_state.period_start = month

if "period_end" not in st.session_state :
    st.session_state.period_end = st.session_state.period_start + relativedelta(months=st.session_state.horizon) 

# endregion

# region |---| Root

ROOT_PATH = Path(__file__).absolute().parent

DATA_PATH = ROOT_PATH / "data"
if not DATA_PATH.exists() :
    os.mkdir(DATA_PATH)

# endregion

# region |---| User

ALL_USERS = [
    user_folder.stem 
    for user_folder in DATA_PATH.iterdir() 
    if ( user_folder.is_dir() and user_folder.stem != "default" ) 
]

if not "user" in st.session_state :
    st.session_state.user = ALL_USERS[0] if len(ALL_USERS) > 0 else "default"

USER_PATH = DATA_PATH / st.session_state.user
if not USER_PATH.exists() :
    os.mkdir(USER_PATH)
    ALL_USERS.append(st.session_state.user)

# endregion

# region |---| Budget

BUDGET = None

BUDGETS_PATH = USER_PATH / "budgets"
if not BUDGETS_PATH.exists() :
    os.mkdir(BUDGETS_PATH)

# endregion

# region |---| Load data

PERIODICS_PATH = USER_PATH / "periodics.csv"
PONCTUALS_PATH = USER_PATH / "ponctuals.csv"

if PERIODICS_PATH.exists() :
    PERIODICS = pd.read_csv(PERIODICS_PATH)
else :
    PERIODICS = pd.DataFrame(columns=["category", "description", "amount", "first", "days", "months"])
PERIODICS["category"].astype(str)
PERIODICS["description"].astype(str)
PERIODICS["amount"].astype(float)
PERIODICS["first"] = format_datetime(PERIODICS["first"])
PERIODICS["days"].astype(int)
PERIODICS["months"].astype(int)

if not "periodics" in st.session_state :
    st.session_state.periodics = PERIODICS



if PONCTUALS_PATH.exists() :
    PONCTUALS = pd.read_csv(PONCTUALS_PATH) 
else :
    PONCTUALS = pd.DataFrame(columns=["category", "description", "amount", "date"])
PONCTUALS["category"].astype(str)
PONCTUALS["description"].astype(str)
PONCTUALS["amount"].astype(float)
PONCTUALS["date"] = format_datetime(PONCTUALS["date"])

if not "ponctuals" in st.session_state :
    st.session_state.ponctuals = PONCTUALS

# endregion

# region |---| Utils

class Category(str, Enum) :
    house="Logement"
    eat="Nourriture"
    pay="Salaire"


    def __str__(self):
        return self.value

ALL_CATEGORIES = [Category.house, Category.eat, Category.pay]

# endregion

# endregion


# region UI

# region |---| Settings

def display_settings() :
    
    def _update_period() :
        st.session_state.period_start = st.session_state.input_period_start
        st.session_state.horizon = st.session_state.input_horizon

        st.session_state.period_end = st.session_state.period_start + relativedelta(months=st.session_state.horizon)


    col_settings = st.columns([1, 1, 1, 2, 1], vertical_alignment="bottom")

    user = col_settings[0].selectbox(
        "Sélection du compte",
        options=ALL_USERS,
        key="user",
    )
    with col_settings[1].popover("Nouveau compte", use_container_width=True) :
        with st.form(key="new_user") :
            new_user = st.text_input(
                "Nouveau compte",
                key="new_user",
            )

            new_user_button = st.form_submit_button("Créer")
            if new_user_button :
                # TODO message de confirmation
                os.mkdir(DATA_PATH / new_user)
                st.rerun()
    
    input_period_start = col_settings[2].date_input(
        "Début de période",
        format="DD/MM/YYYY",
        key="input_period_start",
        value=st.session_state.period_start,
        on_change=_update_period
    )
    
    input_horizon = col_settings[3].slider(
        "Horizon (mois)",
        min_value=1,
        max_value=12,
        step=1,
        key="input_horizon",
        value=st.session_state.horizon,
        on_change=_update_period,
    )

    with col_settings[4].popover("Configuration", use_container_width=True) :
        ...
        # TODO config


# endregion

# region |---| Ponctuals

def display_ponctuals_editor() :

    edited_ponctuals = st.data_editor(
        PONCTUALS,
        num_rows="dynamic",
        use_container_width=True,
        key="edited_ponctuals",
        column_config={
            "category": st.column_config.SelectboxColumn("Catégorie", options=ALL_CATEGORIES),
            "description": st.column_config.TextColumn("Description"),
            "amount": st.column_config.NumberColumn("Montant"),
            "date": st.column_config.DateColumn("Date")
        }
    )
    st.session_state.ponctuals = edited_ponctuals

    button_save_ponctuals = st.button("Save", key="button_save_ponctuals")
    if button_save_ponctuals :
        edited_ponctuals.to_csv(PONCTUALS_PATH, index=False)

# endregion    

# region |---| Main

def run_ui() :

    st.set_page_config(layout="wide")

    col_title = st.columns([2, 8])

    col_title[0].title("Cabank")

    with col_title[1].container(border=True) :
        display_settings()
    
    with st.container(border=True) :
        display_ponctuals_editor()

# endregion

# endregion


# region MAIN

if __name__ == '__main__' :
    run_ui()

# endregion




# real = get_real_period(PERIOD_START, PERIOD_END, PERIODICS, PONCTUALS)
# budget = get_budget_period(PERIOD_START, PERIOD_END, PERIODICS, PERIODICS, PONCTUALS)

# balance_real = get_daily_balance(PERIOD_START, PERIOD_END, real)
# balance_budget = get_daily_balance(PERIOD_START, PERIOD_END, budget)

# plt.plot(balance_real["date"], balance_real["balance"])
# plt.plot(balance_budget["date"], balance_budget["balance"])

# TODO 
# Find a way to archive the past periodics : archive the whole history + balance of each month ?
