import json
import inspect
from pathlib import Path
from io import BytesIO

import pandas as pd
import streamlit as st


COLORS = {
    "bg": "#0d0f16",
    "card": "#141824",
    "border": "#2a2e3f",
    "text": "#e8ecff",
    "muted": "#9aa3b8",
    "blue": "#89b4fa",
    "green": "#a6e3a1",
    "yellow": "#f9e2af",
    "orange": "#fab387",
    "red": "#f38ba8",
    "mauve": "#cba6f7",
    "teal": "#94e2d5",
    "sky": "#89dceb",
    "grey": "#6c7086",
}

PLOTLY_LAYOUT = dict(
    plot_bgcolor="#141824",
    paper_bgcolor="#0d0f16",
    font=dict(color="#e8ecff", family="IBM Plex Sans, Arial, sans-serif", size=13),
    margin=dict(t=55, b=45, l=55, r=30),
)

FEM_TIME_CLASSES = {
    "T0 (T ≤ 200 h)": 200,
    "T1 (200 < T ≤ 400 h)": 400,
    "T2 (400 < T ≤ 800 h)": 800,
    "T3 (800 < T ≤ 1 600 h)": 1600,
    "T4 (1 600 < T ≤ 3 200 h)": 3200,
    "T5 (3 200 < T ≤ 6 300 h)": 6300,
    "T6 (6 300 < T ≤ 12 500 h)": 12500,
    "T7 (12 500 < T ≤ 25 000 h)": 25000,
    "T8 (25 000 < T ≤ 50 000 h)": 50000,
    "T9 (T > 50 000 h)": 100000,
}

LOAD_SPECTRUM = {
    "L1 (km ≤ 0,125)": 0.125,
    "L2 (0,125 < km ≤ 0,250)": 0.25,
    "L3 (0,250 < km ≤ 0,500)": 0.50,
    "L4 (0,500 < km ≤ 1,000)": 1.00,
}

FEM_LOAD_SPECTRUM = LOAD_SPECTRUM

MECHANISM_GROUP_MATRIX = {
    "L1": ["M1", "M1", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"],
    "L2": ["M1", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M8"],
    "L3": ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M8", "M8"],
    "L4": ["M2", "M3", "M4", "M5", "M6", "M7", "M8", "M8", "M8", "M8"],
}

def has_uploaded_excel():
    return "uploaded_excel_bytes" in st.session_state


def clear_uploaded_excel():
    st.session_state.pop("uploaded_excel_bytes", None)
    st.session_state.pop("uploaded_excel_name", None)


def upload_excel_center():
    uploaded_file = st.file_uploader(
        "Importer le fichier Excel du parc",
        type=["xlsx"],
        key="central_excel_upload",
    )

    if uploaded_file is not None:
        st.session_state["uploaded_excel_bytes"] = uploaded_file.getvalue()
        st.session_state["uploaded_excel_name"] = uploaded_file.name
        st.success(f"Fichier chargé : {uploaded_file.name}")
        st.rerun()


def require_uploaded_excel():
    if not has_uploaded_excel():
        st.warning("Veuillez d'abord importer un fichier Excel depuis la page Accueil.")
        st.stop()


def get_uploaded_excel():
    if "uploaded_excel_bytes" in st.session_state:
        return BytesIO(st.session_state["uploaded_excel_bytes"])
    return None


def detect_sheet_name(excel_file):
    xls = pd.ExcelFile(excel_file)

    if "Ponts" in xls.sheet_names:
        return "Ponts"

    return xls.sheet_names[0]


def read_excel_file(excel_file):
    sheet_name = detect_sheet_name(excel_file)

    return pd.read_excel(
        excel_file,
        sheet_name=sheet_name,
        header=9,
    )


def clean_text_col(series):
    return (
        series.astype(str)
        .str.strip()
        .str.replace("\n", " ", regex=False)
        .str.replace("\r", " ", regex=False)
    )


def normalize_country(value):
    if pd.isna(value):
        return value

    value = str(value).strip()

    replacements = {
        "1-FRANCE": "FRANCE",
        "2-ESPAGNE": "ESPAGNE",
        "FRANCE": "FRANCE",
        "ESPAGNE": "ESPAGNE",
    }

    return replacements.get(value, value)


def load_data():
    uploaded_file = get_uploaded_excel()

    if uploaded_file is not None:
        df = read_excel_file(uploaded_file)

    else:
        st.error("Aucun fichier Excel importé.")
        return pd.DataFrame()

    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.replace("\n", " ", regex=False)
        .str.replace("\r", " ", regex=False)
    )

    df = df.dropna(how="all")

    rename_map = {
        "PAYS": "pays",
        "Pays": "pays",
        "SITE": "site",
        "Site": "site",
        "PONT": "pont",
        "Pont": "pont",
        "MES": "annee_mes",
        "Age": "age",
        "Âge": "age",
        "Evaluation Spéciale O/N": "evs_statut",
        "Evaluation Speciale O/N": "evs_statut",
        "Évaluation Spéciale O/N": "evs_statut",
        "EVS Année": "evs_annee",
        "EVS Annee": "evs_annee",
        "E/S Montant": "evs_montant",
    }

    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    if "pont" in df.columns:
        df = df[df["pont"].notna()]

    for col in ["pays", "site", "pont"]:
        if col in df.columns:
            df[col] = clean_text_col(df[col])

    if "pays" in df.columns:
        df["pays"] = df["pays"].apply(normalize_country)

    for col in ["annee_mes", "age", "evs_annee", "evs_montant"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "evs_statut" in df.columns:
        df["evs_statut"] = (
            df["evs_statut"]
            .astype(str)
            .str.strip()
            .replace({
                "O": "Obligatoire",
                "Oui": "Obligatoire",
                "N": "Non requis",
                "Non": "Non requis",
                "NC": "Non concerné",
                "nan": "Non renseigné",
                "": "Non renseigné",
            })
        )

    budget_keywords = ["OPEX", "RGE/RGM", "ACHAT NEUF"]

    years = sorted({
        int(str(col).strip()[:4])
        for col in df.columns
        if str(col).strip()[:4].isdigit()
        and 2025 <= int(str(col).strip()[:4]) <= 2100
    })

    for y in years:
        year_cols = [
            c for c in df.columns
            if str(y) in str(c)
            and any(k in str(c).upper() for k in budget_keywords)
        ]

        if year_cols:
            df[f"budget_{y}"] = (
                df[year_cols]
                .apply(pd.to_numeric, errors="coerce")
                .fillna(0)
                .sum(axis=1)
            )

    budget_cols = [
        c for c in df.columns
        if c.startswith("budget_")
        and c.replace("budget_", "").isdigit()
    ]

    if budget_cols:
        df["budget_total"] = df[budget_cols].sum(axis=1)
    else:
        montant_cols = [c for c in df.columns if "montant" in str(c).lower()]
        if montant_cols:
            df["budget_total"] = (
                df[montant_cols]
                .apply(pd.to_numeric, errors="coerce")
                .fillna(0)
                .sum(axis=1)
            )
        else:
            df["budget_total"] = 0

    if "evs_montant" not in df.columns:
        df["evs_montant"] = df["budget_total"]

    return df


def calc_ifm(*args):
    try:
        if len(args) == 2:
            pi_r, pi_c = args
            pi_r = float(pi_r)
            pi_c = float(pi_c)
            return round(pi_r / pi_c, 3) if pi_c > 0 else 0

        if len(args) == 4:
            hr, kmr, hc, kmc = map(float, args)
            pi_r = hr * kmr
            pi_c = hc * kmc
            ifm = pi_r / pi_c if pi_c > 0 else 0
            return round(ifm, 3), pi_r, pi_c

    except Exception:
        pass

    return 0


def calc_hresid(*args):
    try:
        if len(args) == 3:
            pi_r, pi_c, kmf = map(float, args)
            if pi_c <= 0 or kmf <= 0:
                return 100.0
            return max(0, round((1 - (pi_r / (pi_c * kmf))) * 100, 1))

        if len(args) == 4:
            r, pi_c, pi_r, kmf = map(float, args)
            if kmf <= 0:
                return None
            return max(0, round((r * pi_c - pi_r) / kmf, 1))

    except Exception:
        pass

    return 0.0


def get_mechanism_group(time_class, load_class):
    try:
        t_code = str(time_class).split()[0].replace("(", "").strip()
        l_code = str(load_class).split()[0].replace("(", "").strip()
        t_index = int(t_code.replace("T", ""))
        return MECHANISM_GROUP_MATRIX[l_code][t_index]
    except Exception:
        return "M1"


def get_recommendation(ifm, hresid=None, hu=None):
    """
    Recommandation aligned with the methodology page and the IFm chart:
    - IFm < 0.50: Normal
    - 0.50 <= IFm < 0.75: Surveillance
    - 0.75 <= IFm < 1.00: Critique
    - IFm >= 1.00 or no residual life: Urgent

    hresid is expressed in hours. It is only used as an additional urgent flag
    when the remaining theoretical life is zero or negative.
    """
    try:
        if ifm is None:
            return "Données insuffisantes"

        ifm = float(ifm)
        hresid = float(hresid) if hresid is not None else None

        if ifm >= 1.00 or (hresid is not None and hresid <= 0):
            return "🔴 Analyse immédiate : limite théorique atteinte ou durée résiduelle nulle"
        if ifm >= 0.75:
            return "🟠 EVS / expertise à planifier prioritairement"
        if ifm >= 0.50:
            return "🟡 Surveillance renforcée et suivi rapproché"
        return "🟢 Surveillance périodique standard"

    except Exception:
        return "Données insuffisantes"


def get_status(ifm, hresid=None):
    """
    Status aligned with the methodology page, the IFm chart, and the defense script.
    The status is a decision-support indicator, not a certified aptitude decision.
    """
    try:
        if ifm is None:
            return "Inconnu", "badge-normal", COLORS["grey"]

        ifm = float(ifm)
        hresid = float(hresid) if hresid is not None else None

        if ifm >= 1.00 or (hresid is not None and hresid <= 0):
            return "Urgent", "badge-urgent", COLORS["red"]
        if ifm >= 0.75:
            return "Critique", "badge-critical", COLORS["orange"]
        if ifm >= 0.50:
            return "Surveillance", "badge-watch", COLORS["yellow"]
        return "Normal", "badge-normal", COLORS["green"]

    except Exception:
        return "Inconnu", "badge-normal", COLORS["grey"]

def format_euro(value):
    if pd.isna(value) or value == 0:
        return "—"
    return f"{value:,.0f} €".replace(",", " ")


def apply_global_style():
    custom_css = f"""
    <style>
    .stApp {{
        background-color: {COLORS["bg"]};
        color: {COLORS["text"]};
    }}

    [data-testid="stSidebar"] {{
        background: #0b0d13;
        border-right: 1px solid #242635;
    }}

    [data-testid="stSidebar"] * {{
        color: #d7ddf2 !important;
    }}

    .block-container {{
        padding-top: 3rem;
        padding-left: 3rem;
        padding-right: 3rem;
        max-width: none;
        width: 100%;
    }}

    h1 {{
        color: #e8ecff !important;
        font-size: 2.6rem !important;
        font-weight: 700 !important;
    }}

    h2 {{
        color: #e8ecff !important;
        font-size: 1.35rem !important;
        font-weight: 700 !important;
    }}

    h3 {{
        color: #e8ecff !important;
        font-size: 1.05rem !important;
    }}

    hr {{
        border-color: #242635 !important;
    }}

    .hero-box {{
        background: linear-gradient(135deg, #141824 0%, #0f121a 100%);
        border: 1px solid #2a2e3f;
        border-radius: 22px;
        padding: 34px 38px;
        margin-top: 26px;
        margin-bottom: 28px;
        box-shadow: 0 18px 50px rgba(0,0,0,0.30);
    }}

    .hero-subtitle {{
        color: #aeb7cf;
        font-size: 1.05rem;
        line-height: 1.7;
        max-width: 980px;
    }}

    .kpi-card {{
        background: linear-gradient(180deg, #171b27 0%, #10131c 100%);
        border: 1px solid #31384d;
        border-radius: 18px;
        padding: 28px 26px;
        box-shadow: 0 18px 40px rgba(0,0,0,0.28);
        height: 100%;
    }}

    .kpi-value {{
        font-size: 2.35rem;
        font-weight: 700;
        color: #9cc7ff;
        line-height: 1;
    }}

    .kpi-label {{
        font-size: 0.78rem;
        color: #9aa3b8;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-top: 10px;
    }}

    .objective-box {{
        background: #101723;
        border-left: 4px solid #89b4fa;
        border-radius: 14px;
        padding: 18px 22px;
        color: #cdd6f4;
        margin-top: 28px;
        margin-bottom: 26px;
    }}


    .badge-normal, .badge-watch, .badge-critical, .badge-urgent {{
        display: inline-block;
        border-radius: 999px;
        padding: 6px 12px;
        font-weight: 700;
        font-size: 0.82rem;
        border: 1px solid transparent;
        white-space: nowrap;
    }}

    .badge-normal {{
        background: rgba(166, 227, 161, 0.14);
        color: #a6e3a1;
        border-color: rgba(166, 227, 161, 0.35);
    }}

    .badge-watch {{
        background: rgba(249, 226, 175, 0.14);
        color: #f9e2af;
        border-color: rgba(249, 226, 175, 0.35);
    }}

    .badge-critical {{
        background: rgba(250, 179, 135, 0.14);
        color: #fab387;
        border-color: rgba(250, 179, 135, 0.35);
    }}

    .badge-urgent {{
        background: rgba(243, 139, 168, 0.14);
        color: #f38ba8;
        border-color: rgba(243, 139, 168, 0.35);
    }}
    </style>
    """
    st.markdown(custom_css, unsafe_allow_html=True)
