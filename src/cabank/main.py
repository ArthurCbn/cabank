from datetime import (
    datetime,
    time,
)
import uuid
from dateutil.relativedelta import relativedelta
import pandas as pd
from enum import Enum
import plotly.graph_objects as go
import streamlit as st
from typing import Any
import os
import shutil
import json
from pathlib import Path
from cabank.utils import (
    format_datetime,
    combine_and_save_csv,
    is_periodic_occurence_ignored,
    update_category_name,
    plot_custom_waterfall,
    hex_to_rgba,
    safe_concat
)
from cabank.balance import (
    get_real_period,
    get_budget_period,
    get_daily_balance,
    get_offset,
    build_checkpoint_adjustments,
)
from streamlit_calendar import calendar

# region INIT

# region |---| Root

SRC_PATH = Path(__file__).absolute().parent.parent
ROOT_PATH = SRC_PATH.parent

DATA_PATH = ROOT_PATH / "data"
if not DATA_PATH.exists() :
    os.mkdir(DATA_PATH)

DEFAULT_CONFIG_PATH = DATA_PATH / "default_config.json"

# endregion

# region |---| User

ALL_USERS = [
    user_folder.stem 
    for user_folder in sorted(DATA_PATH.iterdir()) 
    if ( user_folder.is_dir() and user_folder.stem != "default" ) 
]

if not "user" in st.session_state :
    st.session_state.user = ALL_USERS[0] if len(ALL_USERS) > 0 else "default"

USER_PATH = DATA_PATH / st.session_state.user
if not USER_PATH.exists() :
    os.mkdir(USER_PATH)
    ALL_USERS.append(st.session_state.user)

# endregion

# region |---| Config

CONFIG_PATH = USER_PATH / "config.json"
if not CONFIG_PATH.exists() :
    shutil.copy(DEFAULT_CONFIG_PATH, CONFIG_PATH)

with open(CONFIG_PATH, "r") as f :
    CONFIG = json.load(f)

MONEY_FORMAT = CONFIG.get("money_format", "")
MONEY_SYMBOL = CONFIG.get("money_symbol", "")

if "all_categories" not in st.session_state :
    st.session_state.all_categories = CONFIG.get("categories", {})

if "categories_id" not in st.session_state :
    st.session_state.categories_id = {
        uuid.uuid4(): cat 
        for cat in st.session_state.all_categories
    }

if "first_day" not in st.session_state :
    st.session_state.first_day = CONFIG.get("first_day", 1)

# endregion

# region |---| Period

TODAY = datetime.now()

if "horizon" not in st.session_state :
    st.session_state.horizon = 1

if "period_start" not in st.session_state :
    month = datetime.strptime(f"{st.session_state.first_day}/{TODAY.month}/{TODAY.year}", "%d/%m/%Y")
    
    if TODAY.day < st.session_state.first_day :
        st.session_state.period_start = month - relativedelta(month=st.session_state.horizon)
    else :   
        st.session_state.period_start = month

st.session_state.period_end = st.session_state.period_start + relativedelta(months=st.session_state.horizon) 

# endregion

# region |---| Checkpoints

CHECKPOINTS_PATH = USER_PATH / "checkpoints.csv"

if CHECKPOINTS_PATH.exists() :
    FULL_CHECKPOINTS = pd.read_csv(CHECKPOINTS_PATH)

    FULL_CHECKPOINTS["date"] = format_datetime(FULL_CHECKPOINTS["date"])
    FULL_CHECKPOINTS["net_position"] = FULL_CHECKPOINTS["net_position"].astype(float)

else :
    columns = {
        "date": "datetime64[ns]",
        "net_position": "float64",
    }
    FULL_CHECKPOINTS = pd.DataFrame({col: pd.Series(dtype=col_type) for col, col_type in columns.items()})

FULL_CHECKPOINTS = FULL_CHECKPOINTS.sort_values("date").reset_index(drop=True)

# Infer offset and ref_day
REF_DAY, REF_BALANCE = None, None

if len(FULL_CHECKPOINTS) > 0 :
    REF_DAY = FULL_CHECKPOINTS["date"].iloc[-1]
    REF_BALANCE = FULL_CHECKPOINTS["net_position"].iloc[-1]

    CHECKPOINTS_DURING_PERIOD = FULL_CHECKPOINTS[FULL_CHECKPOINTS["date"] >= st.session_state.period_start]
    LAST_CHECKPOINT_BEFORE_PERIOD = FULL_CHECKPOINTS[FULL_CHECKPOINTS["date"] < st.session_state.period_start].tail(1)
    
    CHECKPOINTS = safe_concat(LAST_CHECKPOINT_BEFORE_PERIOD, CHECKPOINTS_DURING_PERIOD)
else :
    CHECKPOINTS = FULL_CHECKPOINTS

st.session_state.ref_day = REF_DAY
st.session_state.ref_balance = REF_BALANCE
st.session_state.checkpoints = CHECKPOINTS

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
    FULL_PERIODICS["category"] = FULL_PERIODICS["category"].astype(str)
    FULL_PERIODICS["tags"] = FULL_PERIODICS["tags"].astype(str).apply(json.loads)
    FULL_PERIODICS["description"] = FULL_PERIODICS["description"].fillna("").astype(str)
    FULL_PERIODICS["amount"] = FULL_PERIODICS["amount"].astype(float)
    FULL_PERIODICS["first"] = format_datetime(FULL_PERIODICS["first"])
    FULL_PERIODICS["last"] = format_datetime(FULL_PERIODICS["last"])
    FULL_PERIODICS["days"] = FULL_PERIODICS["days"].fillna(0).astype(int)
    FULL_PERIODICS["months"] = FULL_PERIODICS["months"].fillna(0).astype(int)
    FULL_PERIODICS["id"] = FULL_PERIODICS["id"].fillna(uuid.uuid4()).astype(str)

    periodics_in_period_mask =  (
        ( format_datetime(FULL_PERIODICS["first"]) < st.session_state.period_end ) &
        ( format_datetime(FULL_PERIODICS["last"])  >= st.session_state.period_start )
    )

    PERIODICS = FULL_PERIODICS[periodics_in_period_mask].reset_index(drop=True)
    ISOLATED_PERIODICS = FULL_PERIODICS[~periodics_in_period_mask].reset_index(drop=True)

else :
    columns = {
        "category": "str",
        "tags": "list",
        "description": "str", 
        "amount": "float64", 
        "first": "datetime64[ns]", 
        "last": "datetime64[ns]", 
        "days": "int64", 
        "months": "int64", 
        "id": "str"
    }
    FULL_PERIODICS = pd.DataFrame({col: pd.Series(dtype=col_type) for col, col_type in columns.items()})
    PERIODICS = pd.DataFrame({col: pd.Series(dtype=col_type) for col, col_type in columns.items()})
    ISOLATED_PERIODICS = pd.DataFrame({col: pd.Series(dtype=col_type) for col, col_type in columns.items()})

if "periodics" not in st.session_state :
    st.session_state.periodics = PERIODICS

# endregion

# region |---|---| Ignore periodic

PERIODIC_OCCURENCES_MODIFICATIONS_PATH = USER_PATH / "periodic_occurences_modifications.json"
if PERIODIC_OCCURENCES_MODIFICATIONS_PATH.exists() :

    with open(PERIODIC_OCCURENCES_MODIFICATIONS_PATH, "r") as f :
        PERIODIC_OCCURENCES_MODIFICATIONS = json.load(f)
    
else :
    PERIODIC_OCCURENCES_MODIFICATIONS = {}

if "modify_periodic_occurences" not in st.session_state :
    st.session_state.modify_periodic_occurences = PERIODIC_OCCURENCES_MODIFICATIONS

# endregion

# region |---|---| Ponctuals

PONCTUALS_PATH = USER_PATH / "ponctuals.csv"
if PONCTUALS_PATH.exists() :
    FULL_PONCTUALS = pd.read_csv(PONCTUALS_PATH)

    # Typing
    FULL_PONCTUALS["category"] = FULL_PONCTUALS["category"].astype(str)
    FULL_PONCTUALS["tags"] = FULL_PONCTUALS["tags"].astype(str).apply(json.loads)
    FULL_PONCTUALS["description"] = FULL_PONCTUALS["description"].fillna("").astype(str)
    FULL_PONCTUALS["amount"] = FULL_PONCTUALS["amount"].astype(float)
    FULL_PONCTUALS["date"] = format_datetime(FULL_PONCTUALS["date"])
    FULL_PONCTUALS["id"] = FULL_PONCTUALS["id"].astype(str)

    ponctuals_in_period_mask =  (
        ( format_datetime(FULL_PONCTUALS["date"]) >= st.session_state.period_start ) &
        ( format_datetime(FULL_PONCTUALS["date"]) < st.session_state.period_end )
    )

    PONCTUALS = FULL_PONCTUALS[ponctuals_in_period_mask].reset_index(drop=True) 
    ISOLATED_PONCTUALS = FULL_PONCTUALS[~ponctuals_in_period_mask].reset_index(drop=True) 

else :
    columns = {
        "date": "datetime64[ns]", 
        "category": "str",
        "tags": "list",
        "description": "str", 
        "amount": "float64", 
        "id": "str"
    }
    FULL_PONCTUALS = pd.DataFrame({col: pd.Series(dtype=col_type) for col, col_type in columns.items()})
    PONCTUALS = pd.DataFrame({col: pd.Series(dtype=col_type) for col, col_type in columns.items()})
    ISOLATED_PONCTUALS = pd.DataFrame({col: pd.Series(dtype=col_type) for col, col_type in columns.items()})

if "ponctuals" not in st.session_state :
    st.session_state.ponctuals = PONCTUALS

# endregion

# region |---|---| Budget

# region |---|---|---| Periodics

BUDGET_PERIODICS = pd.DataFrame(columns=["category", "tags", "description", "amount", "first", "last", "days", "months", "id"])

if not CURRENT_BUDGET_PATH is None :
    BUDGET_PERIODICS_PATH = CURRENT_BUDGET_PATH / "periodics.csv"
    if BUDGET_PERIODICS_PATH.exists() :
        BUDGET_PERIODICS = pd.read_csv(BUDGET_PERIODICS_PATH)

# Typing
BUDGET_PERIODICS["category"] = BUDGET_PERIODICS["category"].astype(str)
BUDGET_PERIODICS["tags"] = BUDGET_PERIODICS["tags"].astype(str).apply(json.loads)
BUDGET_PERIODICS["description"] = BUDGET_PERIODICS["description"].fillna("").astype(str)
BUDGET_PERIODICS["amount"] = BUDGET_PERIODICS["amount"].astype(float)
BUDGET_PERIODICS["first"] = format_datetime(BUDGET_PERIODICS["first"])
BUDGET_PERIODICS["last"] = format_datetime(BUDGET_PERIODICS["last"])
BUDGET_PERIODICS["days"] = BUDGET_PERIODICS["days"].fillna(0).astype(int)
BUDGET_PERIODICS["months"] = BUDGET_PERIODICS["months"].fillna(0).astype(int)
BUDGET_PERIODICS["id"] = BUDGET_PERIODICS["id"].astype(str)

if "budget_periodics" not in st.session_state :
    st.session_state.budget_periodics = BUDGET_PERIODICS

# endregion

# region |---|---|---| Ponctuals

BUDGET_PONCTUALS = pd.DataFrame(columns=["date", "category", "tags", "description", "amount", "id"])
if not CURRENT_BUDGET_PATH is None :
    BUDGET_PONCTUALS_PATH = CURRENT_BUDGET_PATH / "ponctuals.csv"
    if BUDGET_PONCTUALS_PATH.exists() :
        BUDGET_PONCTUALS = pd.read_csv(BUDGET_PONCTUALS_PATH)

# Typing
BUDGET_PONCTUALS["category"] = BUDGET_PONCTUALS["category"].astype(str)
BUDGET_PONCTUALS["tags"] = BUDGET_PONCTUALS["tags"].astype(str).apply(json.loads)
BUDGET_PONCTUALS["description"] = BUDGET_PONCTUALS["description"].fillna("").astype(str)
BUDGET_PONCTUALS["amount"] = BUDGET_PONCTUALS["amount"].astype(float)
BUDGET_PONCTUALS["date"] = format_datetime(BUDGET_PONCTUALS["date"])
BUDGET_PONCTUALS["id"] = BUDGET_PONCTUALS["id"].astype(str)

if "budget_ponctuals" not in st.session_state :
    st.session_state.budget_ponctuals = BUDGET_PONCTUALS

# endregion

# endregion

# region |---|---| Tags

# TODO -> BUG
# TODO MultiselectColumn when > 1.51 released ?

# BUG
# Quand on ajoute un nouvel élément avec un tag ça bug
# Si on ajoute l'élément puis qu'on enregistre, le champs "None" disparait et là on peut modifier le tag
# default=[] empire la situation parce que même si on rempli pas le champs, ça raise l'erreur

# periodic_tags = st.session_state.periodics["tags"].explode().dropna().unique().tolist()
# ponctual_tags = st.session_state.ponctuals["tags"].explode().dropna().unique().tolist()
# budget_periodic_tags = st.session_state.budget_periodics["tags"].explode().dropna().unique().tolist()
# budget_ponctual_tags = st.session_state.budget_ponctuals["tags"].explode().dropna().unique().tolist()

# st.session_state.all_tags = list(set(periodic_tags + ponctual_tags + budget_periodic_tags + budget_ponctual_tags))
st.session_state.all_tags = []

# endregion

# endregion

# region |---| Apply checkpoints
ADJUSTMENTS = build_checkpoint_adjustments(
    checkpoints=st.session_state.checkpoints,
    periodics=FULL_PERIODICS,
    ponctuals=FULL_PONCTUALS,
    modify_periodic_occurences=st.session_state.modify_periodic_occurences,
)
st.session_state.adjustments = ADJUSTMENTS
# endregion

# region |---| Calendars tweaks

# Trick to force update of the calendar when needed (it doesnt refresh alone)
if "calendar_state" not in st.session_state :
    st.session_state.calendar_state = 0

if "calendar_events" not in st.session_state :
    st.session_state.calendar_events = []

# endregion

# endregion


# region UI

# region |---| Header

# region |---|---| Settings

def display_settings() :

    col_settings = st.columns([1, 1, 2], vertical_alignment="top")

# region |---|---|---| User

    user_input = col_settings[0].selectbox(
        "Compte",
        options=ALL_USERS,
        key="user_input",
        accept_new_options=True,
        index=( ALL_USERS.index(st.session_state.user) if st.session_state.user in ALL_USERS else None ),
    )

    if st.session_state.user != user_input :
        st.session_state.user = user_input
        st.rerun()
     
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

# region |---|---| Checkpoints

@st.dialog("Solde ce jour")
def display_checkpoint_form() :

    with st.form("checkpoints_form", border=False) :

        col_checkpoints_form  = st.columns([2, 2, 1], vertical_alignment="bottom")

        acount_balance_input = col_checkpoints_form[0].number_input(
            "Solde compte", 
            format="%.2f", 
            step=1.,
        )
        credit_balance_input = col_checkpoints_form[1].number_input(
            "En cours CB", 
            format="%.2f", 
            step=1.,
        )

        ref_submit_button  = col_checkpoints_form[2].form_submit_button(
            "Valider", 
            width="stretch"
        )

        if ref_submit_button :
            
            st.session_state.checkpoints.loc[len(st.session_state.checkpoints)] = {
                "date": TODAY.date(), 
                "net_position": acount_balance_input - credit_balance_input
            }
            st.session_state.checkpoints.to_csv(CHECKPOINTS_PATH, index=False)
            st.rerun()

# endregion

# region |---|---| Config

def display_config() :
    
    col_config = st.columns(3, vertical_alignment="bottom")

# region |---|---|---| Categories

# region |---|---|---|---| Apply modifs

    def _apply_categories_modifications(new_categories: dict[uuid.UUID, tuple[str, str]]) :
        
        # Modifications
        cat_name_modifications = {
            c_id: (old_name, new_name)
            for c_id, (new_name, _) in new_categories.items()
            if (old_name := st.session_state.categories_id.get(c_id, None))
            if old_name != new_name
        }
        for c_id, (old_name, new_name) in cat_name_modifications.items() :
            st.session_state.categories_id[c_id] = new_name
            
            update_category_name(
                old_name=old_name,
                new_name=new_name,
                user_folder=USER_PATH
            )

        # New
        for c_id, (cat, _) in new_categories.items() :
            if not c_id in st.session_state.categories_id :
                st.session_state.categories_id[c_id] = cat

        st.session_state.all_categories = {
            cat: color
            for _, (cat, color) in new_categories.items()
        }
        
        CONFIG["categories"] = st.session_state.all_categories
        with open(CONFIG_PATH, "w") as f :
            json.dump(CONFIG, f, indent=4)

# endregion

# region |---|---|---|---| Pop-up
  
    @st.dialog("Modifier les catégories")
    def _edit_categories(tmp_all_categories: dict[uuid.UUID, tuple[str, str]]) :

        for uid, (cat, color) in tmp_all_categories.items():
        
            cols_category = st.columns([4, 2, 1], vertical_alignment="bottom")

            cat_input = cols_category[0].text_input(
                f"Nom", 
                value=cat, 
                key=f"name_{uid}"
            )
            color_input = cols_category[1].color_picker(
                "Couleur", 
                value=color, 
                key=f"color_{uid}"
            )
            tmp_all_categories[uid] = (cat_input, color_input)
            
            if len(tmp_all_categories) > 1:
                if cols_category[2].button("🗑️", key=f"remove_{uid}"):
                    tmp_all_categories.pop(uid)
                    st.rerun(scope="fragment")
        
        if st.button("Ajouter une catégorie") :
            tmp_all_categories[uuid.uuid4()] = ("Nouvelle catégorie", "#000000")
            st.rerun(scope="fragment")

        col_buttons = st.columns(2)
        if col_buttons[0].button("Annuler", width="stretch") :
            st.rerun()
        
        if col_buttons[1].button("Confirmer", width="stretch") :
            
            # Check that there is no duplicates
            all_names = [cat for cat, _ in tmp_all_categories.values()]
            duplicates = set([name for name in all_names if all_names.count(name) > 1])
            if duplicates:
                st.error(f"Chaque catégorie doit avoir un nom différent ! (doublons : {', '.join(duplicates)})")
            
            else:
                _apply_categories_modifications(tmp_all_categories)
                st.rerun()

# endregion

    if col_config[2].button("Modifier les catégories", width="stretch") :
        tmp_all_categories = {
            c_id: (cat, st.session_state.all_categories[cat])
            for c_id, cat in st.session_state.categories_id.items()
        }
        _edit_categories(tmp_all_categories)

# endregion

# region |---|---|---| First day

    input_first_day = col_config[0].number_input(
        "Premier jour du mois",
        min_value=1,
        max_value=28,
        step=1,
        format="%.0d",
        value=st.session_state.first_day
    )
    if col_config[1].button("Confirmer", width="stretch", key="first_day_input_button") :
        
        st.session_state.first_day = input_first_day

        CONFIG["first_day"] = input_first_day
        with open(CONFIG_PATH, 'w') as f :
            json.dump(CONFIG, f, indent=4)

        st.rerun()
    
# endregion

# endregion

# endregion

# region |---| Calendar

@st.fragment
def display_calendar(period: pd.DataFrame) :
    
# region |---|---| Pop-up

    @st.dialog("Détails de la dépense")
    def _display_expense_details(
        index: int,
        expense: pd.Series) :

        amount = expense["amount"]
        tags = expense["tags"]

        st.subheader(f'{expense["category"]} : {amount} {MONEY_SYMBOL}')
        st.write(f"{expense["date"].strftime("%d/%m/%Y")} - {expense["description"]}")
        st.write(" ".join(f"#{t}" for t in tags))

        # Periodic => Possibility to ignore/modify
        if ( p_id := expense["periodic_id"] ) is not None :
            
            # Display periodic details
            periodic_search = st.session_state.periodics[st.session_state.periodics["id"] == p_id]
            if len(periodic_search) == 0 :
                st.write("Could not find periodic info...")
            else :
                periodic = periodic_search.iloc[0]
                st.write(f"Du **{periodic["first"].strftime("%d/%m/%Y")}** au **{periodic["last"].strftime("%d/%m/%Y")}**")
                st.write(f"Tous les : **{periodic["days"]} jours**, **{periodic["months"]} mois**")

            # Modification form
            with st.form(key=f"ignore_form_{index}", border=True, enter_to_submit=False) :
                
                form_cols = st.columns(2, vertical_alignment="bottom")
                
                modified_amount = form_cols[0].number_input(
                    "Montant de l'occurence",
                    value=amount,
                    format="%.2f",
                )
                ignore = form_cols[1].toggle(
                    "Ignorer occurence",
                    value=expense["is_ignored"],
                    key=f"ignore_{index}"
                )
                ignore_submit = st.form_submit_button("Valider et Fermer", width="stretch")
                
                if ignore_submit :
                    
                    date = expense["date"].strftime("%Y-%m-%d")

                    # Modify amount
                    if modified_amount != amount :
                        amount = modified_amount

                        if p_id not in st.session_state.modify_periodic_occurences :
                            st.session_state.modify_periodic_occurences[p_id] = {}
                        st.session_state.modify_periodic_occurences[p_id][date] = amount

                    # Ignore
                    if ignore is True:
                        if p_id not in st.session_state.modify_periodic_occurences :
                            st.session_state.modify_periodic_occurences[p_id] = {}
                        st.session_state.modify_periodic_occurences[p_id][date] = None
                    
                    # Un-ignore
                    else :
                        if is_periodic_occurence_ignored(date, p_id, st.session_state.modify_periodic_occurences) :
                            st.session_state.modify_periodic_occurences[p_id].pop(date)
                    
                    with open(PERIODIC_OCCURENCES_MODIFICATIONS_PATH, "w") as f :
                        json.dump(st.session_state.modify_periodic_occurences, f, indent=4)

                    st.session_state.calendar_state += 1
                    st.rerun()

        else :
            if st.button("Fermer", width="stretch") :
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
            bg_color = "#bbbbbb"
        else : 
            bg_color = "white"

        events.append({
            "id": i,
            "title": f"{row['amount']:+.2f} {MONEY_SYMBOL}",
            "start": row["date"].strftime("%Y-%m-%d"),
            "color": bg_color,
            "borderColor": st.session_state.all_categories.get(row["category"], "white"),
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

    calendar_response = calendar(
        events=events, 
        options=calendar_options, 
        key=f"calendar_{st.session_state.calendar_state}"
    )
    
    if event := calendar_response.get("eventClick") :

        event_id = int(event["event"]["id"])
        clicked_expense = period.iloc[event_id]
        _display_expense_details(event_id, clicked_expense)
    
    if st.button("Rafraîchir le calendrier") :
        st.session_state.calendar_state += 1
        st.rerun(scope="fragment")

# endregion

# endregion

# region |---| Real

# region |---|---| Ponctuals

def display_real_ponctuals_editor() :

    st.subheader("Dépenses ponctuelles")

    ponctuals_ids = PONCTUALS["id"]
    ponctuals_to_edit = PONCTUALS[["date", "category", "tags", "description", "amount"]]

    edited = st.data_editor(
        ponctuals_to_edit,
        num_rows="dynamic",
        width="stretch",
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
                options=st.session_state.all_categories.keys(), 
                width="small",
                required=True
            ),
            "tags": st.column_config.ListColumn( # TODO MultiselectColumn when > 1.51 released ?
                "Tags", 
                width="medium",
                #options=st.session_state.all_tags,
                #accept_new_options=True
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

    edited["tags"] = edited["tags"].apply(lambda x : x if isinstance(x, list) else [])

    edited_with_id = edited.join(ponctuals_ids, how="left")
    for i, row in edited_with_id.iterrows() :
        if pd.isna(row["id"]) :
            edited_with_id.loc[i, "id"] = str(uuid.uuid4())

    st.session_state.ponctuals = edited_with_id
    
    button_save_ponctuals = st.button("Sauvegarder", key="button_save_ponctuals")
    if button_save_ponctuals :
        combine_and_save_csv(
            modified_df=edited_with_id, 
            isolated_df=ISOLATED_PONCTUALS, 
            path=PONCTUALS_PATH
        )
        st.rerun()

# endregion

# region |---|---| Periodics

def display_real_periodics_editor() :

    st.subheader("Virements/Prélèvements périodiques")

    periodics_ids = PERIODICS["id"]
    periodics_to_edit = PERIODICS[["category", "tags", "description", "amount", "first", "last", "days", "months"]]

    edited = st.data_editor(
        periodics_to_edit,
        num_rows="dynamic",
        width="stretch",
        key="edited_periodics",
        column_config={
            "category": st.column_config.SelectboxColumn(
                "Catégorie", 
                options=st.session_state.all_categories.keys(), 
                width="small",
                required=True
            ),
            "tags": st.column_config.ListColumn( # TODO MultiselectColumn when > 1.51 released ?
                "Tags", 
                width="medium",
                #options=st.session_state.all_tags,
                #accept_new_options=True
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

    edited["tags"] = edited["tags"].apply(lambda x : x if isinstance(x, list) else [])

    edited_with_id = edited.join(periodics_ids, how="left")
    for i, row in edited_with_id.iterrows() :
        if pd.isna(row["id"]) :
            edited_with_id.loc[i, "id"] = str(uuid.uuid4())
    
    st.session_state.periodics = edited_with_id
    
    button_save_periodics = st.button("Sauvegarder", key="button_save_periodics")
    if button_save_periodics :
        combine_and_save_csv(
            modified_df=edited_with_id, 
            isolated_df=ISOLATED_PERIODICS, 
            path=PERIODICS_PATH
        )
        st.rerun()


# endregion    

# endregion

# region |---| Budget

# region |---|---| Selection

def display_budget_selection() :

    col_budget_selection = st.columns(2, vertical_alignment="bottom")

    budget_input = col_budget_selection[0].selectbox(
        "Sélection du budget",
        options=ALL_BUDGETS,
        key="budget_input",
        accept_new_options=True,
        index=ALL_BUDGETS.index(st.session_state.budget),
    )
    if budget_input != st.session_state.budget :
        st.session_state.budget = budget_input
        st.rerun()
    # TODO More explicit handling, possibility to rename a budget, etc.

# endregion

# region |---|---| Ponctuals

def display_budget_ponctuals_editor() :

    st.subheader("Dépenses ponctuelles budgettisées")

    budget_ponctuals_ids = BUDGET_PONCTUALS["id"]
    budget_ponctuals_to_edit = BUDGET_PONCTUALS[["date", "category", "tags", "description", "amount"]]

    edited = st.data_editor(
        budget_ponctuals_to_edit,
        num_rows="dynamic",
        width="stretch",
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
                options=st.session_state.all_categories.keys(), 
                width="small",
                required=True
            ),
            "tags": st.column_config.ListColumn( # TODO MultiselectColumn when > 1.51 released ?
                "Tags", 
                width="medium",
                #options=st.session_state.all_tags,
                #accept_new_options=True
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

    edited["tags"] = edited["tags"].apply(lambda x : x if isinstance(x, list) else [])

    edited_with_id = edited.join(budget_ponctuals_ids, how="left")
    for i, row in edited_with_id.iterrows() :
        if pd.isna(row["id"]) :
            edited_with_id.loc[i, "id"] = str(uuid.uuid4())

    st.session_state.budget_ponctuals = edited_with_id

    button_save_budget_ponctuals = st.button("Sauvegarder", key="button_save_budget_ponctuals")
    if button_save_budget_ponctuals :
        combine_and_save_csv(
            modified_df=edited_with_id, 
            path=BUDGET_PONCTUALS_PATH,
        )
        st.rerun()

# endregion

# region |---|---| Periodics

def display_budget_periodics_editor() :

    st.subheader("Budget")

    budget_periodics_ids = BUDGET_PERIODICS["id"]
    budget_periodics_to_edit = BUDGET_PERIODICS[["category", "tags", "description", "amount", "first", "last", "days", "months"]]

    edited = st.data_editor(
        budget_periodics_to_edit,
        num_rows="dynamic",
        width="stretch",
        key="edited_budget_periodics",
        column_config={
            "category": st.column_config.SelectboxColumn(
                "Catégorie", 
                options=st.session_state.all_categories.keys(), 
                width="small",
                required=True
            ),
            "tags": st.column_config.ListColumn( # TODO MultiselectColumn when > 1.51 released ?
                "Tags", 
                width="medium",
                #options=st.session_state.all_tags,
                #accept_new_options=True
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

    edited["tags"] = edited["tags"].apply(lambda x : x if isinstance(x, list) else [])

    edited_with_id = edited.join(budget_periodics_ids, how="left")
    for i, row in edited_with_id.iterrows() :
        if pd.isna(row["id"]) :
            edited_with_id.loc[i, "id"] = str(uuid.uuid4())

    st.session_state.budget_periodics = edited_with_id

    button_save_budget_periodics = st.button("Sauvegarder", key="button_save_budget_periodics")
    if button_save_budget_periodics :
        combine_and_save_csv(
            modified_df=edited_with_id, 
            isolated_df=None, 
            path=BUDGET_PERIODICS_PATH
        )
        st.rerun()

# endregion

# endregion

# region |---| Stats

def display_monthly_stats() :
    ... # TODO large period selector + stats by month by category (one plot per cat)

# endregion

# region |---| Sidebar

# region |---|---| Daily Balance

def display_daily_balance(
        daily_balance: pd.DataFrame,
        period: pd.DataFrame,
        budget_balance: pd.DataFrame|None=None,
        budget_period: pd.DataFrame|None=None) :
    
    past_balance = daily_balance[daily_balance["date"] <= TODAY]
    future_balance = daily_balance[daily_balance["date"] >= (TODAY - relativedelta(days=1))]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=past_balance["date"], 
        y=past_balance["balance"], 
        mode='lines', 
        name='Réel', 
        line=dict(color='black'),
        hovertemplate=(
            "Date : %{x}<br>"
            "Balance : %{y} " + MONEY_SYMBOL + "<extra></extra>"
        )
    ))

    fig.add_trace(go.Scatter(
        x=future_balance["date"], 
        y=future_balance["balance"], 
        mode='lines', 
        name='Prévisionnel', 
        line=dict(color='black', dash='dot'),
        hovertemplate=(
            "Date : %{x}<br>"
            "Prévision : %{y} " + MONEY_SYMBOL + "<extra></extra>"
        )
    ))

    if not budget_balance is None :
        fig.add_trace(go.Scatter(
            x=budget_balance["date"], 
            y=budget_balance["balance"], 
            mode='lines', 
            name=f'Budget {st.session_state.budget}', 
            line=dict(color='gray', dash='dash'),
            hovertemplate=(
                "Date : %{x}<br>"
                "Budget : %{y} " + MONEY_SYMBOL + "<extra></extra>"
            )
        ))

        fig.add_trace(go.Bar(
            x=budget_period["date"],
            y=budget_period["amount"],
            name=f'Budget {st.session_state.budget}',
            marker=dict(color=budget_period["category"].map(st.session_state.all_categories), pattern=dict(shape="/")),
            opacity=0.4,
            yaxis='y2',
            showlegend=False,
            customdata=budget_period["description"],
            hovertemplate=(
                "<b>%{customdata}</b><br>"
                "Date : %{x}<br>"
                "Montant : %{y} " + MONEY_SYMBOL + "<br>"
            )
        ))

    fig.add_trace(go.Bar(
        x=period["date"],
        y=period["amount"],
        name='Dépenses',
        marker=dict(color=period["category"].map(st.session_state.all_categories)),
        opacity=0.8,
        yaxis='y2',
        showlegend=False,
        customdata=period["description"],
        hovertemplate=(
            "<b>%{customdata}</b><br>"
            "Date : %{x}<br>"
            "Montant : %{y} " + MONEY_SYMBOL + "<br>"
        )
    ))

    fig.update_xaxes(showgrid=True)
    fig.update_layout(
        xaxis=dict(title="Date"), 
        yaxis=dict(title="Balance", showgrid=True, side='right'), # Axe principal
        yaxis2=dict(title="Dépenses", overlaying='y', side='left', showgrid=False), # Axe secondaire
        title=f"Balance de la période : {daily_balance.iloc[-1]['balance'] - st.session_state.offset:+.2f} {MONEY_SYMBOL}",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.25,
            xanchor="center",
            x=0.5
        ),
        margin=dict(b=100),
        barmode='group'
    )

    st.plotly_chart(fig)

# endregion

# region |---|---| Waterfall

def display_waterfall(
        period: pd.DataFrame,
        budget_period: pd.DataFrame|None=None) :

    def _sort_waterfall(row: pd.Series) :
        return row.apply(
            lambda x: ( max(x, 0), max(-x, 0) )
        )

    spent_real = period[( period["is_ignored"] == False )]
    spent_stats = spent_real[["category", "amount"]].groupby(["category"]).sum().rename(columns={"amount": "amount_real"})

    if not budget_period is None :
        spent_budget = budget_period[( budget_period["is_ignored"] == False )]
        spent_budget_stats = spent_budget[["category", "amount"]].groupby(["category"]).sum().rename(columns={"amount": "amount_budget"})

        spent_stats = spent_stats.join(spent_budget_stats, how="outer").fillna(0)

    sorted_spent_stats = spent_stats.sort_values(by="amount_real", key=_sort_waterfall, ascending=False)

    categories = list(sorted_spent_stats.index)
    amounts = list(sorted_spent_stats["amount_real"])
    colors = [st.session_state.all_categories.get(cat, "black") for cat in categories]
        
    # Insert "Start" bar at the beginning
    categories.insert(0, f"{st.session_state.period_start.strftime('%d/%m/%Y')}")
    amounts.insert(0, float(st.session_state.offset))
    colors.insert(0, "black")

    # Append total bar at the end
    categories.append(f"{st.session_state.period_end.strftime('%d/%m/%Y')}")
    amounts.append(sum(amounts))
    colors.append("black")

    amounts_budget = None
    if not budget_period is None :
        amounts_budget = list(sorted_spent_stats["amount_budget"])
        amounts_budget.insert(0, float(st.session_state.offset))
        amounts_budget.append(sum(amounts_budget))

    fig = go.Figure()
    
    plot_custom_waterfall(
        fig=fig,
        categories=categories,
        amounts=amounts,
        amounts_budget=amounts_budget,
        colors=colors
    )

    fig.update_layout(
        title="Détail de la balance" + (f" vs budget {st.session_state.budget}" if st.session_state.budget else ""),
        barmode='overlay',
        showlegend=False,
        yaxis=dict(title="Montant"),
        xaxis=dict(
            tickmode='array',
            tickvals=list(range(len(categories))),
            ticktext=categories,
        ),
    )

    st.plotly_chart(fig, width="stretch")

# endregion

# region |---|---| Sankey

def display_sankey(
        period: pd.DataFrame,
        budget_period: pd.DataFrame|None=None) :

    node_opacity = 0.6
    link_opacity = 0.3
    tag_color = "gray"
    total_node = ""
    total_node_color = "white"

# region |---|---|---| Build Sankey
    def _build_sankey_diagram(
            period: pd.DataFrame
    ) -> tuple[list[str], list[int], list[int], list[int], list[str], list[str]] :
        
        # Init nodes
        nodes_idx = {total_node: 0}
        node_colors = [total_node_color]
        labels = [total_node]

        for _, row in period.iterrows() :
            cat = row["category"]
            tags = row["tags"]

            amount = row["amount"]
            suffix = "in" if amount > 0 else "out"

            if not f"{cat}_{suffix}" in nodes_idx :
                nodes_idx[f"{cat}_{suffix}"] = len(nodes_idx)
                labels.append(cat)
                node_colors.append(hex_to_rgba(st.session_state.all_categories[cat], alpha=node_opacity))

            for tag in tags :
                if not f"{tag}_{suffix}" in nodes_idx :
                    nodes_idx[f"{tag}_{suffix}"] = len(nodes_idx)
                    labels.append(tag)
                    node_colors.append(tag_color)

        # Build links
        sources = []
        targets = []
        values = []
        link_colors = []
        links_idx = {}
        
        def __add_link(
                node1: int,
                node2: int,
                amount: float,
                cat: str|None=None,
                color: str|None=None) -> None :

            link = (node1, node2, cat)

            if not link in links_idx :
                links_idx[link] = len(links_idx)
                sources.append(node1)
                targets.append(node2)
                values.append(0)

                if color is None :
                    assert not cat is None
                    link_colors.append(hex_to_rgba(st.session_state.all_categories[cat], alpha=link_opacity))
                else :
                    link_colors.append(color)

            link_idx = links_idx[link]
            values[link_idx] += abs(amount)

            return
    

        for _, row in period.iterrows() :
            
            cat = row["category"]
            tags = row["tags"]
            amount = row["amount"]

            if amount >= 0 :

                current_node = nodes_idx[f"{cat}_in"]
                for t in tags :
                    next_node = nodes_idx[f"{t}_in"]
                    __add_link(current_node, next_node, amount, cat=cat)
                    current_node = next_node
                __add_link(current_node, nodes_idx[total_node], amount, cat=cat)
            
            else :
                current_node = nodes_idx[total_node]
                for t in tags :
                    next_node = nodes_idx[f"{t}_out"]
                    __add_link(current_node, next_node, amount, cat=cat)
                    current_node = next_node
                __add_link(current_node, nodes_idx[f"{cat}_out"], amount, cat=cat)

        # Excedent/Deficit
        balance = period["amount"].sum()
        
        if balance < 0 :
            nodes_idx["Déficit"] = len(nodes_idx)
            node_colors.append(f"rgba(200,0,0,{node_opacity})")
            labels.append("Déficit")
            __add_link(nodes_idx["Déficit"], nodes_idx[total_node], abs(balance), color=f"rgba(200,0,0,{link_opacity})")

        elif balance > 0 :
            nodes_idx["Excédent"] = len(nodes_idx)
            node_colors.append(f"rgba(0,160,0,{node_opacity})")
            labels.append("Excédent")
            __add_link(nodes_idx[total_node], nodes_idx["Excédent"], abs(balance), color=f"rgba(0,160,0,{link_opacity})")

        return labels, sources, targets, values, node_colors, link_colors
# endregion

    # Mise en forme
    period_real = period[( period["is_ignored"] == False ) & ( period["category"].isin(st.session_state.all_categories) )]
    period_real = period_real[["category", "tags", "amount"]]

    (labels, 
     sources, 
     targets,
     values,
     node_colors,
     link_colors) = _build_sankey_diagram(period_real)             

    fig = go.Figure(data=[go.Sankey(
        valueformat = ".0f",
        valuesuffix = MONEY_SYMBOL,
        arrangement="snap",
        node=dict(
            pad=40,
            thickness=10,
            line=dict(color="black", width=0.5),
            label=labels,
            color=node_colors
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colors,
            hovertemplate='%{source.label} → %{target.label}<br>%{value}<extra></extra>'
        )
    )])

    fig.update_layout(
        font_family="Courier New",
        font_size=12,
        font_shadow="",
        paper_bgcolor ="white"
    )

    st.plotly_chart(fig, width="stretch")
# endregion

# region |---|---| Stats

def display_amount_by_cat(
        period: pd.DataFrame,
        budget_period: pd.DataFrame|None=None) :


    title = "Dépenses par catégories"

    spent_real = period[( period["is_ignored"] == False ) & ( period["category"].isin(st.session_state.all_categories) )]
    spent_real_output = spent_real[spent_real["amount"] < 0]

    spent_real_stats = spent_real_output[["category", "amount"]].groupby(["category"]).sum().abs().sort_values("amount", ascending=False)

    colors = [st.session_state.all_categories[cat] for cat in spent_real_stats.index]

    fig = go.Figure()

    if not budget_period is None :

        title += f" vs budget {st.session_state.budget}"

        spent_budget = budget_period[( budget_period["amount"] < 0 ) & ( budget_period["category"].isin(st.session_state.all_categories) )]
        spent_budget_stats = spent_budget[["category", "amount"]].groupby(["category"]).sum().abs().sort_index()

        ordered_cat = list(spent_real_stats.index) 
        ordered_cat.extend([c for c in spent_budget_stats.index if c not in ordered_cat])
        spent_budget_stats = spent_budget_stats.reindex(ordered_cat)

        fig.add_trace(go.Bar(
            x=spent_budget_stats.index,
            y=spent_budget_stats["amount"],
            name=f"Budget {st.session_state.budget}",
            orientation='v',
            marker=dict(color='lightgray'),
            width=0.6,
            hovertemplate=f'Budget {st.session_state.budget}'+': %{y}' + MONEY_SYMBOL +'<extra></extra>',
        ))

    fig.add_trace(go.Bar(
        x=spent_real_stats.index,
        y=spent_real_stats["amount"],
        name='Dépenses réelles',
        orientation='v',
        marker=dict(color=colors),
        width=0.3,
        hovertemplate='Réel: %{y}' + MONEY_SYMBOL +'<extra></extra>',
    ))

    fig.update_layout(
        barmode='overlay',
        title=title,
        xaxis_title='Montant',
        yaxis_title='Catégorie',
        height=400,
        showlegend=False,
    )

    st.plotly_chart(fig)

# endregion

# endregion

# region |---| MAIN

# region |---|---| Input UI

def run_input_ui_and_get_mixed_placeholder() :
    """
    This part of the UI is exclusively for inputs, so it must be ran prior to the logic kernel.
    Since some mixed widget are displayed alongside input widgets (calendar for instance), we return their placeholders.
    """

    col_title = st.columns([2, 8], vertical_alignment="top")

    col_title[0].title("Cabank")

    with col_title[1].expander(label="Réglages", expanded=True) :

        tab_settings, tab_config = st.tabs(["Paramètres", "Configuration"])
        with tab_settings :
            display_settings()
        
        with tab_config :
            display_config()

    with st.container() :

        tab_cash_flow, tab_real, tab_budget, tab_cal, tab_stats = st.tabs(["Cash flow", "Réel", "Budget", "Calendrier", "Statistiques"])

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
    
    return tab_cash_flow, tab_cal, tab_stats

# endregion

# region |---|---| Output UI

def run_output_ui(
        tab_cash_flow,
        tab_cal,
        tab_stats,
        period: pd.DataFrame,
        daily_balance: pd.DataFrame,
        budget_period: pd.DataFrame,
        budget_balance: pd.DataFrame) :
    """
    This part of the UI is exclusively for outputs, so it must be ran AFTER the logic kernel.
    Since some mixed widget are displayed alongside input widgets (calendar for instance), we take their placeholders in args.
    """

    with tab_cash_flow :
        display_sankey(
            period=period,
            budget_period=budget_period
        )

    with tab_cal :
        display_calendar(period)
    
    with tab_stats : 
        display_monthly_stats()

    with st.sidebar :
        
        display_daily_balance(
            daily_balance=daily_balance,
            period=period,
            budget_balance=budget_balance,   
            budget_period=budget_period, 
        )

        if st.button("Ajouter un checkpoint", width="stretch") :
            display_checkpoint_form()

        # display_waterfall(
        #     period=period,
        #     budget_period=budget_period,
        # )
        display_amount_by_cat(
            period=period,
            budget_period=budget_period,
        )
        

# endregion

# endregion

# endregion


# region MAIN

if __name__ == '__main__' :

# region |---| Custom streamlit display

    st.set_page_config(layout="wide")

    st.markdown("""
        <style>
            [data-testid="stSidebarHeader"] {
                display: none;
            }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("""
        <style>
            [data-testid="stToolbar"] {
                display: none;
            }
        </style>
    """, unsafe_allow_html=True)
    
    st.markdown("""
        <style>
            [data-testid="stMainBlockContainer"] {
                padding-top: 0rem;
            }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("""
        <style>
            [data-testid="stSidebar"] {
                background-color: white;
            }   
        </style>
    """, unsafe_allow_html=True)

# endregion

    tab_cash_flow, tab_cal, tab_stats = run_input_ui_and_get_mixed_placeholder()

# region |---| Offset

    st.session_state.offset = 0.
    if not st.session_state.ref_balance is None :
        st.session_state.offset = get_offset(
            ref_day=st.session_state.ref_day,
            ref_balance=st.session_state.ref_balance,
            target_day=st.session_state.period_start,
            periodics=FULL_PERIODICS,
            ponctuals=safe_concat(FULL_PONCTUALS, st.session_state.adjustments),
            modify_periodic_occurences=st.session_state.modify_periodic_occurences
        )

# endregion

# region |---| Real

    period = get_real_period(
        period_start=st.session_state.period_start,
        period_end=st.session_state.period_end,
        periodics=st.session_state.periodics,
        ponctuals=safe_concat(st.session_state.ponctuals, st.session_state.adjustments),
        modify_periodic_occurences=st.session_state.modify_periodic_occurences,
    )

    daily_balance = get_daily_balance(
        period_start=st.session_state.period_start,
        period_end=st.session_state.period_end,
        aggregated_period=period,
        start_offset=st.session_state.offset
    )

# endregion

# region |---| Budget

    if not st.session_state.budget is None :
        budget_period = get_budget_period(
            period_start=st.session_state.period_start,
            period_end=st.session_state.period_end,
            periodics=st.session_state.periodics,
            budget_periodics=st.session_state.budget_periodics,
            budget_ponctuals=st.session_state.budget_ponctuals,
        )
        budget_balance = get_daily_balance(
            period_start=st.session_state.period_start,
            period_end=st.session_state.period_end,
            aggregated_period=budget_period,
            start_offset=st.session_state.offset
        )
    else :
        budget_period = None
        budget_balance = None

# endregion
    
    run_output_ui(
        tab_cash_flow=tab_cash_flow,
        tab_cal=tab_cal,
        tab_stats=tab_stats,
        period=period,
        daily_balance=daily_balance,
        budget_period=budget_period,
        budget_balance=budget_balance
    )

# endregion

