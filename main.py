from datetime import (
    datetime,
    time,
)
from dateutil.relativedelta import relativedelta
import pandas as pd
from enum import Enum
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import streamlit as st
from typing import Any
import os
from pathlib import Path
from src.utils import (
    format_datetime,
    combine_and_save_csv,
    is_periodic_occurence_ignored,
    apply_ignore_to_period,
)
from src.balance import (
    get_real_period,
    get_budget_period,
    get_daily_balance,
    get_offset,
)
from streamlit_calendar import calendar

# region INIT

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

# region |---| Config TODO

ALL_CATEGORIES = {
    "Logement": "red", 
    "Nourriture": "green", 
    "Salaire": "blue"
}

MONEY_FORMAT = "dollar"
MONEY_SYMBOL = "$"

FIRST_DAY = 6

# endregion

# region |---| Offset

# TODO load from config
REF_DAY = None
if "ref_day" not in st.session_state :
    st.session_state.ref_day = REF_DAY

if "ref_balance" not in st.session_state :
    st.session_state.ref_balance = None

# endregion

# region |---| Period

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

# region |---| Budget

BUDGETS_PATH = USER_PATH / "budgets"
if not BUDGETS_PATH.exists() :
    os.mkdir(BUDGETS_PATH)

ALL_BUDGETS = [None] + [
    budget_folder.stem 
    for budget_folder in BUDGETS_PATH.iterdir() 
    if budget_folder.is_dir() 
]

if not "budget" in st.session_state :
    st.session_state.budget = None

if not st.session_state.budget is None :

    CURRENT_BUDGET_PATH = BUDGETS_PATH / st.session_state.budget
    if not CURRENT_BUDGET_PATH.exists() :
        os.mkdir(CURRENT_BUDGET_PATH)
        ALL_BUDGETS.append(st.session_state.budget)

else :

    CURRENT_BUDGET_PATH = None

# endregion

# region |---| Load data

# region |---|---| Periodics

PERIODICS_PATH = USER_PATH / "periodics.csv"
if PERIODICS_PATH.exists() :
    FULL_PERIODICS = pd.read_csv(PERIODICS_PATH)

    # Typing
    FULL_PERIODICS["category"].astype(str)
    FULL_PERIODICS["description"] = FULL_PERIODICS["description"].fillna("").astype(str)
    FULL_PERIODICS["amount"].astype(float)
    FULL_PERIODICS["first"] = format_datetime(FULL_PERIODICS["first"])
    FULL_PERIODICS["last"] = format_datetime(FULL_PERIODICS["last"])
    FULL_PERIODICS["days"] = FULL_PERIODICS["days"].fillna(0).astype(int)
    FULL_PERIODICS["months"] = FULL_PERIODICS["months"].fillna(0).astype(int)

    periodics_in_period_mask =  (
        ( format_datetime(FULL_PERIODICS["first"]) < st.session_state.period_end ) &
        ( format_datetime(FULL_PERIODICS["last"])  >= st.session_state.period_start )
    )

    PERIODICS = FULL_PERIODICS[periodics_in_period_mask].reset_index(drop=True) 
    ISOLATED_PERIODICS = FULL_PERIODICS[~periodics_in_period_mask].reset_index(drop=True) 

else :
    FULL_PERIODICS = pd.DataFrame(columns=["category", "description", "amount", "first", "last", "days", "months"])
    PERIODICS = pd.DataFrame(columns=["category", "description", "amount", "first", "last", "days", "months"])
    ISOLATED_PERIODICS = pd.DataFrame(columns=["category", "description", "amount", "first", "last", "days", "months"])



if not "periodics" in st.session_state :
    st.session_state.periodics = PERIODICS

# endregion

# region |---|---| Ponctuals

PONCTUALS_PATH = USER_PATH / "ponctuals.csv"
if PONCTUALS_PATH.exists() :
    FULL_PONCTUALS = pd.read_csv(PONCTUALS_PATH)

    # Typing
    FULL_PONCTUALS["category"].astype(str)
    FULL_PONCTUALS["description"] = FULL_PONCTUALS["description"].fillna("").astype(str)
    FULL_PONCTUALS["amount"].astype(float)
    FULL_PONCTUALS["date"] = format_datetime(FULL_PONCTUALS["date"])

    ponctuals_in_period_mask =  (
        ( format_datetime(FULL_PONCTUALS["date"]) >= st.session_state.period_start ) &
        ( format_datetime(FULL_PONCTUALS["date"]) < st.session_state.period_end )
    )

    PONCTUALS = FULL_PONCTUALS[ponctuals_in_period_mask].reset_index(drop=True) 
    ISOLATED_PONCTUALS = FULL_PONCTUALS[~ponctuals_in_period_mask].reset_index(drop=True) 

else :
    FULL_PONCTUALS = pd.DataFrame(columns=["date", "category", "description", "amount"])
    PONCTUALS = pd.DataFrame(columns=["date", "category", "description", "amount"])
    ISOLATED_PONCTUALS = pd.DataFrame(columns=["date", "category", "description", "amount"])

if not "ponctuals" in st.session_state :
    st.session_state.ponctuals = PONCTUALS

# endregion

# region |---|---| Budget

# region |---|---|---| Periodics

BUDGET_PERIODICS = pd.DataFrame(columns=["category", "description", "amount", "first", "last", "days", "months"])

if not CURRENT_BUDGET_PATH is None :
    BUDGET_PERIODICS_PATH = CURRENT_BUDGET_PATH / "periodics.csv"
    if BUDGET_PERIODICS_PATH.exists() :
        BUDGET_PERIODICS = pd.read_csv(BUDGET_PERIODICS_PATH)

# Typing
BUDGET_PERIODICS["category"].astype(str)
BUDGET_PERIODICS["description"] = BUDGET_PERIODICS["description"].fillna("").astype(str)
BUDGET_PERIODICS["amount"].astype(float)
BUDGET_PERIODICS["first"] = format_datetime(BUDGET_PERIODICS["first"])
BUDGET_PERIODICS["last"] = format_datetime(BUDGET_PERIODICS["last"])
BUDGET_PERIODICS["days"] = BUDGET_PERIODICS["days"].fillna(0).astype(int)
BUDGET_PERIODICS["months"] = BUDGET_PERIODICS["months"].fillna(0).astype(int)

if not "budget_periodics" in st.session_state :
    st.session_state.budget_periodics = BUDGET_PERIODICS

# endregion

# region |---|---|---| Ponctuals

BUDGET_PONCTUALS = pd.DataFrame(columns=["date", "category", "description", "amount"])
if not CURRENT_BUDGET_PATH is None :
    BUDGET_PONCTUALS_PATH = CURRENT_BUDGET_PATH / "ponctuals.csv"
    if BUDGET_PONCTUALS_PATH.exists() :
        BUDGET_PONCTUALS = pd.read_csv(BUDGET_PONCTUALS_PATH)

# Typing
BUDGET_PONCTUALS["category"].astype(str)
BUDGET_PONCTUALS["description"] = BUDGET_PONCTUALS["description"].fillna("").astype(str)
BUDGET_PONCTUALS["amount"].astype(float)
BUDGET_PONCTUALS["date"] = format_datetime(BUDGET_PONCTUALS["date"])

if not "budget_ponctuals" in st.session_state :
    st.session_state.budget_ponctuals = BUDGET_PONCTUALS

# endregion

# endregion

# endregion

# region |---| Calendars tweaks

# Trick to force update of the calendar when needed (it doesnt refresh alone)
if "calendar_state" not in st.session_state :
    st.session_state.calendar_state = 0

if "calendar_events" not in st.session_state :
    st.session_state.calendar_events = []

if "ignore_periodics" not in st.session_state :
    st.session_state.ignore_periodics = {}

# endregion

# endregion


# region UI

# region |---| Header

# region |---|---| Settings

def display_settings() :

    col_settings = st.columns([1, 1, 2], vertical_alignment="bottom")

# region |---|---|---| User

    user = col_settings[0].selectbox(
        "Compte",
        options=ALL_USERS,
        key="user",
        accept_new_options=True,
        index=( ALL_USERS.index(st.session_state.user) if st.session_state.user in ALL_USERS else None ),
    )

# endregion

# region |---|---|---| Period

    def _update_period() :
        st.session_state.period_start = datetime.combine(st.session_state.input_period_start, time.min)
        st.session_state.horizon = st.session_state.input_horizon

        st.session_state.period_end = st.session_state.period_start + relativedelta(months=st.session_state.horizon)


    input_period_start = col_settings[1].date_input(
        "Début de période",
        format="DD/MM/YYYY",
        key="input_period_start",
        value=st.session_state.period_start,
        on_change=_update_period
    )
    
    input_horizon = col_settings[2].slider(
        "Horizon (mois)",
        min_value=1,
        max_value=12,
        step=1,
        key="input_horizon",
        value=st.session_state.horizon,
        on_change=_update_period,
    )

# endregion

# endregion

# region |---|---| Offset

def display_offset() :

    with st.form("ref_form", border=False) :

        col_ref_form  = st.columns([2, 2, 1], vertical_alignment="bottom")

        ref_day_input = col_ref_form[0].date_input(
            "Jour de référence",
            format="DD-MM-YYYY",
            key="ref_day_input",
            value=REF_DAY
        )
        ref_balance_input = col_ref_form[1].number_input("Solde") # TODO better widget

        ref_submit_button  = col_ref_form[2].form_submit_button(
            "Valider", 
            use_container_width=True
        )

        if ref_submit_button :
            # TODO save in config file
            st.session_state.ref_day = datetime.combine(ref_day_input, time.min) # TODO dumbproof the date
            st.session_state.ref_balance = ref_balance_input

# endregion

# region |---|---| Config

def display_config() :
    ...
    # TODO

# endregion

# endregion

# region |---| Calendar

def display_calendar(period: pd.DataFrame) :
    
# region |---|---| Pop-up

    @st.dialog("Détails de la dépense")
    def _display_expense_details(
        index: int,
        expense: pd.Series) :

        st.subheader(f'{expense["category"]} : {expense["amount"]} {MONEY_SYMBOL}')
        st.write(expense["description"])

        # Periodic => Possibility to ignore
        if ( p_id := expense["periodic_id"] ) is not None :

            with st.form(key=f"ignore_form_{index}", border=False) :
                
                form_cols = st.columns(2, vertical_alignment="center")
                
                ignore = form_cols[0].checkbox(
                    "Ignorer occurence",
                    value=expense["is_ignored"],
                    key=f"ignore_{index}"
                )
                ignore_submit = form_cols[1].form_submit_button("Fermer", use_container_width=True)
                
                if ignore_submit :
                    date = expense["date"].strftime("%Y-%m-%d")

                    # Ignore
                    if ignore is True:
                        if p_id not in st.session_state.ignore_periodics :
                            st.session_state.ignore_periodics[p_id] = []
                        st.session_state.ignore_periodics[p_id].append(date)
                    
                    # Un-ignore
                    else :
                        if is_periodic_occurence_ignored(date, p_id, st.session_state.ignore_periodics) :
                            st.session_state.ignore_periodics[p_id].remove(date)
                    # TODO Write this in config
                    st.session_state.calendar_state += 1
                    st.rerun()

        else :
            if st.button("Fermer", use_container_width=True) :
                st.session_state.calendar_state += 1
                st.rerun()
    
    # Hide the 'x' button of the st.dialog
    st.html(
        '''
            <style>
                div[aria-label="dialog"]>button[aria-label="Close"] {
                    display: none;
                }
            </style>
        '''
    )

# endregion

# region |---|---| Calendar

    events = []
    for i, row in period.iterrows() :

        if row["is_ignored"] :
            bg_color = "#949494"
        else : 
            bg_color = "white"

        events.append({
            "id": i,
            "title": f"{row['amount']:+.2f} {MONEY_SYMBOL}",
            "start": row["date"].strftime("%Y-%m-%d"),
            "color": bg_color,
            "borderColor": ALL_CATEGORIES[row["category"]],
            "absolute_amount": abs(row["amount"]),
            "display": "list-item" if row["periodic_id"] is None else "block" 
        })
    
    if events != st.session_state.calendar_events :
        st.session_state.calendar_state += 1
        st.session_state.calendar_events = events

    calendar_options = {
        "initialView": "dayGridMonth",
        "editable": False,
        "blockEvent": True,
        "locale": "fr",
        "firstDay": 1,
        "dayMaxEvents": 3,
        "headerToolbar": {
            "left": "",
            "center": "title",
            "right": ""
        },
        "footerToolbar": {
            "left": "",
            "center": "",
            "right": "prev,next"
        },
        "validRange": {
            "start": st.session_state.period_start.strftime("%Y-%m-%d"),
            "end": st.session_state.period_end.strftime("%Y-%m-%d")
        },
        "aspectRatio": 2,
        "eventOrder": ["-absolute_amount"],
        "eventTextColor": "black"
    }
    # BUG when doing actions on other tabs
    calendar_response = calendar(
        events=events, 
        options=calendar_options, 
        key=f"calendar_{st.session_state.calendar_state}"
    )
    
    if event := calendar_response.get("eventClick") :

        event_id = int(event["event"]["id"])
        clicked_expense = period.iloc[event_id]
        _display_expense_details(event_id, clicked_expense)

# endregion

# endregion

# region |---| Real

# region |---|---| Ponctuals

def display_real_ponctuals_editor() :

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
                options=ALL_CATEGORIES.keys(), 
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
                format=MONEY_FORMAT,
            ),
        },
        hide_index=True,
    )

    st.session_state.ponctuals = edited_ponctuals

    button_save_ponctuals = st.button("Sauvegarder", key="button_save_ponctuals")
    if button_save_ponctuals :
        combine_and_save_csv(
            modified_df=edited_ponctuals, 
            isolated_df=ISOLATED_PONCTUALS, 
            path=PONCTUALS_PATH
        )

# endregion

# region |---|---| Periodics

def display_real_periodics_editor() :

    st.subheader("Virements/Prélèvements périodiques")

    edited_periodics = st.data_editor(
        PERIODICS,
        num_rows="dynamic",
        use_container_width=True,
        key="edited_periodics",
        column_config={
            "category": st.column_config.SelectboxColumn(
                "Catégorie", 
                options=ALL_CATEGORIES.keys(), 
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
                format=MONEY_FORMAT,
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
        combine_and_save_csv(
            modified_df=edited_periodics, 
            isolated_df=ISOLATED_PERIODICS, 
            path=PERIODICS_PATH
        )


# endregion    

# endregion

# region |---| Budget

# region |---|---| Selection

def display_budget_selection() :

    col_budget_selection = st.columns(2, vertical_alignment="bottom")

    budget = col_budget_selection[0].selectbox(
        "Sélection du budget",
        options=ALL_BUDGETS,
        key="budget",
        accept_new_options=True,
        index=ALL_BUDGETS.index(st.session_state.budget),
    )

# endregion

# region |---|---| Ponctuals

def display_budget_ponctuals_editor() :

    st.subheader("Dépenses ponctuelles budgettisées")

    edited_budget_ponctuals = st.data_editor(
        BUDGET_PONCTUALS,
        num_rows="dynamic",
        use_container_width=True,
        key="edited_budget_ponctuals",
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
                options=ALL_CATEGORIES.keys(), 
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
                format=MONEY_FORMAT,
            ),
        },
        hide_index=True,
    )

    st.session_state.budget_ponctuals = edited_budget_ponctuals

    button_save_budget_ponctuals = st.button("Sauvegarder", key="button_save_budget_ponctuals")
    if button_save_budget_ponctuals :
        combine_and_save_csv(
            modified_df=edited_budget_ponctuals, 
            path=BUDGET_PERIODICS_PATH,
        )

# endregion

# region |---|---| Periodics

def display_budget_periodics_editor() :

    st.subheader("Budget")

    edited_budget_periodics = st.data_editor(
        BUDGET_PERIODICS,
        num_rows="dynamic",
        use_container_width=True,
        key="edited_budget_periodics",
        column_config={
            "category": st.column_config.SelectboxColumn(
                "Catégorie", 
                options=ALL_CATEGORIES.keys(), 
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
                format=MONEY_FORMAT,
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

    st.session_state.budget_periodics = edited_budget_periodics

    button_save_budget_periodics = st.button("Sauvegarder", key="button_save_budget_periodics")
    if button_save_budget_periodics :
        combine_and_save_csv(
            modified_df=edited_budget_periodics, 
            isolated_df=None, 
            path=BUDGET_PERIODICS_PATH
        )


# endregion

# endregion

# region |---| Sidebar

# region |---|---| Daily Balance

def display_daily_balance(
        daily_balance: pd.DataFrame,
        budget_balance: pd.DataFrame|None=None) :
    
    past_balance = daily_balance[daily_balance["date"] <= TODAY]
    future_balance = daily_balance[daily_balance["date"] >= (TODAY - relativedelta(days=1))]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=past_balance["date"], 
        y=past_balance["balance"], 
        mode='lines', 
        name='Réel', 
        line=dict(color='black')
    ))

    fig.add_trace(go.Scatter(
        x=future_balance["date"], 
        y=future_balance["balance"], 
        mode='lines', 
        name='Prévisionnel', 
        line=dict(color='black', dash='dot')
    ))

    if not budget_balance is None :
        fig.add_trace(go.Scatter(
            x=budget_balance["date"], 
            y=budget_balance["balance"], 
            mode='lines', 
            name=f'Budget {st.session_state.budget}', 
            line=dict(color='gray', dash='dash')
        ))

    fig.update_xaxes(showgrid=True)
    fig.update_layout(
        title="Balance de la période",
        xaxis_title="Date",
        yaxis_title="Balance",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.25,
            xanchor="center",
            x=0.5
        ),
        margin=dict(b=100) 
    )

    st.plotly_chart(fig)

# endregion

# region |---|---| Stats

def display_stats(
        period: pd.DataFrame,
        budget_period: pd.DataFrame|None=None) :

    colors = [c for _, c in sorted(ALL_CATEGORIES.items())]

    spent_real = period[( period["amount"] < 0 ) & ( period["is_ignored"] == False )]

    spent_real.loc[:, "amount"] = spent_real["amount"].apply(lambda x : x*-1)
    spent_real_stats = spent_real[["category", "amount"]].groupby(["category"]).sum().sort_index()

    fig = go.Figure()

    if not budget_period is None :
        spent_budget = budget_period[budget_period["amount"] < 0]
        spent_budget.loc[:, "amount"] = spent_budget["amount"].apply(lambda x : x*-1)
        spent_budget_stats = spent_budget[["category", "amount"]].groupby(["category"]).sum().sort_index()

        fig.add_trace(go.Bar(
            y=spent_budget_stats.index,
            x=spent_budget_stats["amount"],
            name=f"Budget {st.session_state.budget}",
            orientation='h',
            marker=dict(color='lightgray'),
            width=0.6,
            hovertemplate=f'Budget {st.session_state.budget}'+': %{x}<extra></extra>',
        ))

    fig.add_trace(go.Bar(
        y=spent_real_stats.index,
        x=spent_real_stats["amount"],
        name='Dépenses réelles',
        orientation='h',
        marker=dict(color=colors),
        width=0.3,
        hovertemplate='Réel: %{x}<extra></extra>',
    ))

    fig.update_layout(
        barmode='overlay',
        title=f'Dépenses réelles vs Budget {st.session_state.budget}',
        xaxis_title='Montant',
        yaxis_title='Catégorie',
        height=400,
        showlegend=False,
    )

    st.plotly_chart(fig)
    
    # TODO Donut

# endregion

# endregion

# region |---| Main

def run_ui(
        period: pd.DataFrame,
        daily_balance: pd.DataFrame,
        budget_period: pd.DataFrame,
        budget_balance: pd.DataFrame) :

    st.set_page_config(layout="wide")

    col_title = st.columns([2, 8])

    col_title[0].title("Cabank")

    with col_title[1].container(border=True) :

        tab_settings, tab_offset, tab_config = st.tabs(["Paramètres", "Calibration", "Configuration"])
        with tab_settings :
            display_settings()
        
        with tab_offset :
            display_offset()
        
        with tab_config :
            display_config()

    with st.container() :

        tab_cal, tab_real, tab_budget = st.tabs(["Calendrier des dépenses", "Réel", "Budget"])

        with tab_cal :
            display_calendar(period)

        with tab_real :
            with st.expander("Virements/Prélèvements périodiques") :
                display_real_periodics_editor()

            display_real_ponctuals_editor()
        
        with tab_budget :

            display_budget_selection()
            
            if not st.session_state.budget is None :

                with st.expander("Dépenses ponctuelles budgettisées") :
                    display_budget_ponctuals_editor()

                display_budget_periodics_editor()

    with st.sidebar :
        # TODO Afficher valeure finale

        display_daily_balance(
            daily_balance=daily_balance,
            budget_balance=budget_balance,    
        )
        display_stats(
            period=period,
            budget_period=budget_period,
        )

# endregion

# endregion


# region MAIN

if __name__ == '__main__' :

# region |---| Offset

    offset = 0.
    if not st.session_state.ref_balance is None :
        offset = get_offset(
            ref_day=st.session_state.ref_day,
            ref_balance=st.session_state.ref_balance,
            target_day=st.session_state.period_start,
            periodics=FULL_PERIODICS,
            ponctuals=FULL_PONCTUALS
        )

# endregion

# region |---| Real

    period = get_real_period(
        period_start=st.session_state.period_start,
        period_end=st.session_state.period_end,
        periodics=st.session_state.periodics,
        ponctuals=st.session_state.ponctuals
    )

    period = apply_ignore_to_period(
        period, 
        st.session_state.ignore_periodics
    )

    daily_balance = get_daily_balance(
        period_start=st.session_state.period_start,
        period_end=st.session_state.period_end,
        aggregated_period=period,
        start_offset=offset
    )

# endregion

# region |---| Budget

    if not st.session_state.budget is None :
        budget_period = get_budget_period(
            period_start=st.session_state.period_start,
            period_end=st.session_state.period_end,
            periodics=st.session_state.periodics,
            budget_periodics=st.session_state.budget_periodics,
            budget_ponctuals=st.session_state.budget_ponctuals
        )
        budget_balance = get_daily_balance(
            period_start=st.session_state.period_start,
            period_end=st.session_state.period_end,
            aggregated_period=budget_period,
            start_offset=offset
        )
    else :
        budget_period = None
        budget_balance = None

# endregion

    run_ui(
        period=period,
        daily_balance=daily_balance,
        budget_period=budget_period,
        budget_balance=budget_balance
    )

# endregion

