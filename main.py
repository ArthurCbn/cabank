from datetime import (
    datetime,
    time,
)
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
    combine_and_save_csv,
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

BUDGET = None # TODO

BUDGETS_PATH = USER_PATH / "budgets"
if not BUDGETS_PATH.exists() :
    os.mkdir(BUDGETS_PATH)

# endregion

# region |---| Load data

# region |---|---| Periodics

PERIODICS_PATH = USER_PATH / "periodics.csv"
if PERIODICS_PATH.exists() :
    FULL_PERIODICS = pd.read_csv(PERIODICS_PATH)

    periodics_in_period_mask =  (
        ( format_datetime(FULL_PERIODICS["first"]) < st.session_state.period_end ) &
        ( format_datetime(FULL_PERIODICS["last"])  >= st.session_state.period_start )
    )

    PERIODICS = FULL_PERIODICS[periodics_in_period_mask].reset_index(drop=True) 
    ISOLATED_PERIODICS = FULL_PERIODICS[~periodics_in_period_mask].reset_index(drop=True) 

else :
    PERIODICS = pd.DataFrame(columns=["category", "description", "amount", "first", "last", "days", "months"])
    ISOLATED_PERIODICS = pd.DataFrame(columns=["category", "description", "amount", "first", "last", "days", "months"])

# Typing
PERIODICS["category"].astype(str)
PERIODICS["description"] = PERIODICS["description"].fillna("").astype(str)
PERIODICS["amount"].astype(float)
PERIODICS["first"] = format_datetime(PERIODICS["first"])
PERIODICS["last"] = format_datetime(PERIODICS["last"])
PERIODICS["days"] = PERIODICS["days"].fillna(0).astype(int)
PERIODICS["months"] = PERIODICS["months"].fillna(0).astype(int)

if not "periodics" in st.session_state :
    st.session_state.periodics = PERIODICS

# endregion

# region |---|---| Ponctuals

PONCTUALS_PATH = USER_PATH / "ponctuals.csv"
if PONCTUALS_PATH.exists() :
    FULL_PONCTUALS = pd.read_csv(PONCTUALS_PATH)

    ponctuals_in_period_mask =  (
        ( format_datetime(FULL_PONCTUALS["date"]) >= st.session_state.period_start ) &
        ( format_datetime(FULL_PONCTUALS["date"]) < st.session_state.period_end )
    )

    PONCTUALS = FULL_PONCTUALS[ponctuals_in_period_mask].reset_index(drop=True) 
    ISOLATED_PONCTUALS = FULL_PONCTUALS[~ponctuals_in_period_mask].reset_index(drop=True) 

else :
    PONCTUALS = pd.DataFrame(columns=["date", "category", "description", "amount"])
    ISOLATED_PONCTUALS = pd.DataFrame(columns=["date", "category", "description", "amount"])

# Typing
PONCTUALS["category"].astype(str)
PONCTUALS["description"] = PONCTUALS["description"].fillna("").astype(str)
PONCTUALS["amount"].astype(float)
PONCTUALS["date"] = format_datetime(PONCTUALS["date"])

if not "ponctuals" in st.session_state :
    st.session_state.ponctuals = PONCTUALS

# endregion

# endregion

# region |---| Categories

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
    
    col_settings = st.columns([1, 1, 1, 2, 1], vertical_alignment="bottom")

# region |---|---| User

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

# endregion

# region |---|---| Period

    def _update_period() :
        st.session_state.period_start = datetime.combine(st.session_state.input_period_start, time.min)
        st.session_state.horizon = st.session_state.input_horizon

        st.session_state.period_end = st.session_state.period_start + relativedelta(months=st.session_state.horizon)


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

# endregion

# region |---|---| Config

    with col_settings[4].popover("Configuration", use_container_width=True) :
        ...
        # TODO config

# endregion

# endregion

# region |---| Ponctuals

def display_ponctuals_editor() :

    st.subheader("Dépenses ponctuelles")

    edited_ponctuals = st.data_editor(
        PONCTUALS,
        num_rows="dynamic",
        use_container_width=True,
        key="edited_ponctuals",
        column_config={
            "date": st.column_config.DateColumn(
                "Date", 
                format="DD-MM-YYYY", 
                width="small", 
                default=st.session_state.period_start,
                required=True,
            ),
            "category": st.column_config.SelectboxColumn(
                "Catégorie", 
                options=ALL_CATEGORIES, 
                width="small",
                required=True
            ),
            "description": st.column_config.TextColumn(
                "Description", 
                width="large",
            ),
            "amount": st.column_config.NumberColumn(
                "Montant", 
                width="small",
                required=True,
            ),
        },
        hide_index=True,
    )

    st.session_state.ponctuals = edited_ponctuals

    button_save_ponctuals = st.button("Sauvegarder", key="button_save_ponctuals")
    if button_save_ponctuals :
        combine_and_save_csv(edited_ponctuals, ISOLATED_PONCTUALS, PONCTUALS_PATH)

# endregion

# region |---| Periodics

def display_periodics_editor() :

    st.subheader("Dépenses périodiques")

    edited_periodics = st.data_editor(
        PERIODICS,
        num_rows="dynamic",
        use_container_width=True,
        key="edited_periodics",
        column_config={
            "category": st.column_config.SelectboxColumn(
                "Catégorie", 
                options=ALL_CATEGORIES, 
                width="small",
                required=True
            ),
            "description": st.column_config.TextColumn(
                "Description", 
                width="medium",
                required=True,
            ),
            "amount": st.column_config.NumberColumn(
                "Montant", 
                width="small",
                required=True,
            ),
            "first": st.column_config.DateColumn(
                "Premier paiement", 
                format="DD-MM-YYYY", 
                width="small", 
                default=st.session_state.period_start,
                required=True,
            ),
            "last": st.column_config.DateColumn(
                "Dernier paiement", 
                format="DD-MM-YYYY", 
                width="small",
                default=( TODAY + relativedelta(years=100) ).date(),
                required=True,
                
            ),
            "days": st.column_config.NumberColumn(
                "Jours", 
                width="small",
                default=0,
                required=False,
                step=1,
            ),
            "months": st.column_config.NumberColumn(
                "Mois", 
                width="small",
                default=0,
                required=False,
                step=1,
            ),
        },
        hide_index=True,
    )

    st.session_state.periodics = edited_periodics

    button_save_periodics = st.button("Sauvegarder", key="button_save_periodics")
    if button_save_periodics :
        combine_and_save_csv(edited_periodics, ISOLATED_PERIODICS, PERIODICS_PATH)


# endregion    

# region |---| Main

def run_ui() :

    st.set_page_config(layout="wide")

    col_title = st.columns([2, 8])

    col_title[0].title("Cabank")

    with col_title[1].container(border=True) :
        display_settings()
    
    col_main_ui = st.columns([7, 3])

    with col_main_ui[0].container() :

        with st.expander("Dépenses périodiques") :
            display_periodics_editor()

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
