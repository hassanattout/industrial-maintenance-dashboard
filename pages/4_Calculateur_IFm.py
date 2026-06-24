from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from utils import (
    COLORS,
    FEM_TIME_CLASSES,
    LOAD_SPECTRUM,
    PLOTLY_LAYOUT,
    apply_global_style,
    calc_hresid,
    calc_ifm,
    get_mechanism_group,
    get_recommendation,
    get_status,
)

apply_global_style()

st.markdown("# 🧮 Calculateur IFm / Hresid")
st.caption(
    "Calcul de fatigue des mécanismes, de la charpente et du chariot avec logique FEM / DWP."
)
st.divider()

with st.expander("📋 Informations générales du pont", expanded=True):
    c1, c2, c3, c4 = st.columns(4)

    pont_nom = c1.text_input(
        "Nom / ID du pont",
        placeholder="ex: Pont A12 63T CAILLARD"
    )

    pont_site = c2.text_input(
        "Site",
        placeholder="ex: LHA"
    )

    pont_mes = c3.number_input(
        "Année MES",
        min_value=1950,
        max_value=2030,
        value=2000
    )

    hu = c4.number_input(
        "Heures d'utilisation / an",
        min_value=100,
        max_value=8760,
        value=500,
        step=50,
        help="Exemple : 500 h/an pour usage standard, 1500 h/an pour usage intensif."
    )

st.divider()

st.markdown("## Classification FEM du mécanisme")
st.caption("Sélection de la classe d'utilisation T et du spectre L. Le groupe M est déduit automatiquement.")

fc1, fc2, fc3 = st.columns(3)

with fc1:
    selected_time_class = st.selectbox(
        "Classe d'utilisation T",
        list(FEM_TIME_CLASSES.keys()),
        index=6,
        help="T0 à T9 selon la durée totale d'utilisation du mécanisme."
    )

with fc2:
    selected_load_spectrum = st.selectbox(
        "Classe de spectre L",
        list(LOAD_SPECTRUM.keys()),
        index=1,
        help="L1 à L4 selon le facteur de spectre km."
    )

with fc3:
    R_global = st.number_input(
        "Rapport admissible R",
        min_value=0.10,
        max_value=1.50,
        value=1.00,
        step=0.05,
        help="R = 1,0 correspond à 100% de la capacité théorique admissible."
    )

    f1_global = st.number_input(
        "Facteur de sécurité f1",
        min_value=0.50,
        max_value=5.00,
        value=1.00,
        step=0.10,
        help="Appliqué à πr : πr = f1 × Hr × Kmr."
    )

Hc_default = FEM_TIME_CLASSES[selected_time_class]
Kmc_default = LOAD_SPECTRUM[selected_load_spectrum]
mechanism_group = get_mechanism_group(selected_time_class, selected_load_spectrum)

k1, k2, k3, k4 = st.columns(4)

with k1:
    st.metric("Hc retenu", f"{Hc_default:,.0f} h")

with k2:
    st.metric("Kmc retenu", f"{Kmc_default:.3f}")

with k3:
    st.metric("πc théorique", f"{Hc_default * Kmc_default:,.0f}")

with k4:
    st.metric("Groupe mécanisme", mechanism_group)

st.markdown("### Matrice de classification FEM")

fem_matrix_df = pd.DataFrame(
    {
        "T0": ["M1", "M1", "M1", "M2"],
        "T1": ["M1", "M1", "M2", "M3"],
        "T2": ["M1", "M2", "M3", "M4"],
        "T3": ["M2", "M3", "M4", "M5"],
        "T4": ["M3", "M4", "M5", "M6"],
        "T5": ["M4", "M5", "M6", "M7"],
        "T6": ["M5", "M6", "M7", "M8"],
        "T7": ["M6", "M7", "M8", "M8"],
        "T8": ["M7", "M8", "M8", "M8"],
        "T9": ["M8", "M8", "M8", "M8"],
    },
    index=["L1", "L2", "L3", "L4"]
)

st.dataframe(fem_matrix_df, use_container_width=True)

st.info(
    "Hc et Kmc sont préremplis à partir de la classe T et du spectre L. "
    "Le groupe M est donné à titre de classification. Les valeurs peuvent être ajustées si une donnée constructeur plus précise existe."
)

st.divider()

st.markdown("## Indice de fatigue des mécanismes")

mecas = [
    ("levage", "⬆️ Levage"),
    ("direction", "🔄 Direction"),
    ("translation", "↔️ Translation"),
]

defaults = {
    "levage": dict(Hr=4278.0, Kmr=0.32, Kmf=0.32),
    "direction": dict(Hr=1455.0, Kmr=0.83, Kmf=0.83),
    "translation": dict(Hr=2137.0, Kmr=0.41, Kmf=0.41),
}

inputs = {}
tabs = st.tabs([label for _, label in mecas])

for tab, (key, label) in zip(tabs, mecas):
    d = defaults[key]

    with tab:
        st.markdown(f"### Paramètres du mécanisme : {label}")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**Données d'utilisation réelle**")

            Hr = st.number_input(
                "Hr - Heures réalisées",
                min_value=0.0,
                max_value=100000.0,
                value=d["Hr"],
                step=1.0,
                key=f"Hr_{key}"
            )

            Kmr = st.number_input(
                "Kmr - Spectre réel",
                min_value=0.0,
                max_value=1.0,
                value=d["Kmr"],
                step=0.01,
                key=f"Kmr_{key}",
                help="Facteur de sévérité du spectre de charge réel."
            )

        with col2:
            st.markdown("**Données de conception**")

            Hc = st.number_input(
                "Hc - Heures de conception",
                min_value=1.0,
                max_value=400000.0,
                value=float(Hc_default),
                step=100.0,
                key=f"Hc_{key}",
                help="Prérempli à partir de la classe d'utilisation T."
            )

            Kmc = st.number_input(
                "Kmc - Spectre de conception",
                min_value=0.0,
                max_value=1.0,
                value=float(Kmc_default),
                step=0.01,
                key=f"Kmc_{key}",
                help="Prérempli à partir du spectre de charge L."
            )

        with col3:
            st.markdown("**Projection future**")

            R = st.number_input(
                "R - Rapport admissible",
                min_value=0.10,
                max_value=1.50,
                value=float(R_global),
                step=0.05,
                key=f"R_{key}"
            )

            Kmf = st.number_input(
                "Kmf - Spectre futur estimé",
                min_value=0.0,
                max_value=1.0,
                value=d["Kmf"],
                step=0.01,
                key=f"Kmf_{key}",
                help="Hypothèse sur les conditions futures d'utilisation."
            )

        ifm, pi_r, pi_c = calc_ifm(Hr, Kmr, Hc, Kmc)
        pi_r = f1_global * pi_r
        ifm = pi_r / pi_c if pi_c > 0 else None

        hresid = calc_hresid(R, pi_c, pi_r, Kmf)
        status, badge_cls, status_color = get_status(ifm, hresid)
        annees = hresid / hu if hresid is not None and hu > 0 else None

        inputs[key] = {
            "label": label,
            "Hr": Hr,
            "Kmr": Kmr,
            "f1": f1_global,
            "Hc": Hc,
            "Kmc": Kmc,
            "R": R,
            "Kmf": Kmf,
            "ifm": ifm,
            "pi_r": pi_r,
            "pi_c": pi_c,
            "hresid": hresid,
            "status": status,
            "badge_cls": badge_cls,
            "status_color": status_color,
            "annees": annees,
            "reco": get_recommendation(ifm, hresid, hu),
        }

        st.divider()

        r1, r2, r3, r4, r5, r6 = st.columns(6)

        r1.metric("πr réel", f"{pi_r:,.0f}")
        r2.metric("πc conception", f"{pi_c:,.0f}")
        r3.metric("f1", f"{f1_global:.2f}")
        r4.metric("IFm", f"{ifm:.3f}" if ifm is not None else "—")
        r5.metric("Hresid", f"{hresid:,.0f} h" if hresid is not None else "—")
        r6.metric("Années résiduelles", f"{annees:.1f}" if annees is not None else "—")

        st.markdown(
            f"**Statut :** <span class='{badge_cls}'>{status}</span>",
            unsafe_allow_html=True
        )

        st.caption(get_recommendation(ifm, hresid, hu))

st.divider()

st.markdown("## Synthèse des mécanismes")

rows = []

for key, r in inputs.items():
    rows.append({
        "Type": "Mécanisme",
        "Élément": r["label"],
        "Groupe M": mechanism_group,
        "Hr (h)": r["Hr"],
        "Kmr": r["Kmr"],
        "f1": r["f1"],
        "Hc (h)": r["Hc"],
        "Kmc": r["Kmc"],
        "R": r["R"],
        "Kmf": r["Kmf"],
        "πr": round(r["pi_r"], 1),
        "πc": round(r["pi_c"], 1),
        "IFm": round(r["ifm"], 4) if r["ifm"] is not None else None,
        "Hresid (h)": round(r["hresid"]) if r["hresid"] is not None else None,
        "Années résiduelles": round(r["annees"], 1) if r["annees"] is not None else None,
        "Statut": r["status"],
        "Recommandation": r["reco"],
    })

df_res = pd.DataFrame(rows)


def color_status(val):
    mapping = {
        "Normal": "background:#1a3a1a;color:#a6e3a1",
        "Suffisant": "background:#1a3a1a;color:#a6e3a1",
        "Surveillance": "background:#3a3010;color:#f9e2af",
        "Préventif": "background:#3a3010;color:#f9e2af",
        "Critique": "background:#3a1a0a;color:#fab387",
        "Urgent": "background:#3a0a0a;color:#f38ba8",
        "Épuisé": "background:#3a0a0a;color:#f38ba8",
        "Inconnu": "background:#2a2e3f;color:#9aa3b8",
    }
    return mapping.get(val, "")


styled = (
    df_res.style
    .map(color_status, subset=["Statut"])
    .format({
        "Hr (h)": "{:,.0f}",
        "Hc (h)": "{:,.0f}",
        "πr": "{:,.0f}",
        "πc": "{:,.0f}",
        "IFm": "{:.3f}",
        "Hresid (h)": "{:,.0f}",
        "Années résiduelles": "{:.1f}",
        "Kmr": "{:.2f}",
        "Kmc": "{:.2f}",
        "f1": "{:.2f}",
        "R": "{:.2f}",
        "Kmf": "{:.2f}",
    }, na_rep="—")
)

st.dataframe(styled, use_container_width=True, hide_index=True)

st.divider()

col_g1, col_g2 = st.columns(2)

with col_g1:
    st.markdown("## IFm par mécanisme")

    labels = [r["label"] for r in inputs.values()]
    ifm_vals = [r["ifm"] or 0 for r in inputs.values()]
    bar_colors = [r["status_color"] for r in inputs.values()]

    fig = go.Figure(go.Bar(
        x=labels,
        y=ifm_vals,
        marker=dict(
            color=bar_colors,
            opacity=0.9,
            line=dict(color="#0d0f16", width=1)
        ),
        text=[f"{v:.3f}" for v in ifm_vals],
        textposition="outside",
    ))

    fig.add_hline(
        y=0.50,
        line_dash="dash",
        line_color=COLORS["yellow"],
        annotation_text="Surveillance"
    )

    fig.add_hline(
        y=0.75,
        line_dash="dash",
        line_color=COLORS["orange"],
        annotation_text="Critique"
    )

    fig.add_hline(
        y=1.00,
        line_dash="dash",
        line_color=COLORS["red"],
        annotation_text="Limite théorique"
    )

    fig.update_layout(
        **PLOTLY_LAYOUT,
        height=390,
        yaxis_title="IFm"
    )

    fig.update_yaxes(range=[0, max(1.2, max(ifm_vals) + 0.15)])
    fig.update_xaxes(title="Mécanisme")

    st.plotly_chart(fig, use_container_width=True)

with col_g2:
    st.markdown("## πr réel vs πc conception")

    fig2 = go.Figure()

    for key, r in inputs.items():
        fig2.add_trace(go.Bar(
            name=f"{r['label']} - πr",
            x=[r["label"]],
            y=[r["pi_r"]],
            marker_color=COLORS["blue"],
            opacity=0.9
        ))

        fig2.add_trace(go.Bar(
            name=f"{r['label']} - πc",
            x=[r["label"]],
            y=[r["pi_c"]],
            marker_color="#2a2e3f",
            marker_line=dict(color=COLORS["grey"], width=1)
        ))

    fig2.update_layout(
        **PLOTLY_LAYOUT,
        barmode="group",
        height=390,
        yaxis_title="Heures équivalentes",
        showlegend=False
    )

    fig2.update_xaxes(title="Mécanisme")

    st.plotly_chart(fig2, use_container_width=True)

st.divider()

st.markdown("## Indice de fatigue DWP - Charpente et Chariot")
st.caption("Calcul selon la logique : πr = Ca × Kpr, πc = DN × Kp, IF = πr / πc.")

dwp_defaults = {
    "charpente": {
        "label": "🏗️ Charpente / Quadrilatère",
        "Ca": 1361594.0,
        "Kpr": 0.23,
        "DN": 250000.0,
        "Kp": 0.50,
        "R": 0.90,
        "Kpf": 0.23,
        "cycles_an": 50000.0,
    },
    "chariot": {
        "label": "🚋 Chariot",
        "Ca": 603927.0,
        "Kpr": 0.27,
        "DN": 2000000.0,
        "Kp": 0.50,
        "R": 0.90,
        "Kpf": 0.27,
        "cycles_an": 50000.0,
    },
}

dwp_inputs = {}
dwp_tabs = st.tabs([d["label"] for d in dwp_defaults.values()])


def get_dwp_status(if_dwp, nresid):
    if nresid is not None and nresid <= 0:
        return "Épuisé", "Urgent", COLORS["red"]

    if if_dwp is None:
        return "—", "Normal", COLORS["grey"]

    if if_dwp < 0.50:
        return "Suffisant", "Normal", COLORS["green"]

    if if_dwp < 0.75:
        return "Surveillance", "Surveillance", COLORS["yellow"]

    if if_dwp < 1.00:
        return "Critique", "Critique", COLORS["orange"]

    return "Épuisé", "Urgent", COLORS["red"]


for tab, (key, d) in zip(dwp_tabs, dwp_defaults.items()):
    with tab:
        st.markdown(f"### Paramètres : {d['label']}")

        c1, c2, c3 = st.columns(3)

        with c1:
            st.markdown("**Service réel**")

            Ca = st.number_input(
                "Ca - Nombre de cycles réalisés",
                min_value=0.0,
                max_value=10000000.0,
                value=d["Ca"],
                step=1000.0,
                key=f"Ca_{key}"
            )

            Kpr = st.number_input(
                "Kpr - Spectre de charge réalisé",
                min_value=0.0,
                max_value=1.0,
                value=d["Kpr"],
                step=0.01,
                key=f"Kpr_{key}"
            )

        with c2:
            st.markdown("**Données de conception**")

            DN = st.number_input(
                "DN - Nombre de cycles de conception",
                min_value=1.0,
                max_value=10000000.0,
                value=d["DN"],
                step=1000.0,
                key=f"DN_{key}"
            )

            Kp = st.number_input(
                "Kp - Spectre de charge de conception",
                min_value=0.0,
                max_value=1.0,
                value=d["Kp"],
                step=0.01,
                key=f"Kp_{key}"
            )

        with c3:
            st.markdown("**Durée de vie résiduelle**")

            R_dwp = st.number_input(
                "R - Rapport d'endommagement",
                min_value=0.10,
                max_value=1.50,
                value=d["R"],
                step=0.05,
                key=f"R_dwp_{key}"
            )

            Kpf = st.number_input(
                "Kpf - Spectre futur de charge",
                min_value=0.0,
                max_value=1.0,
                value=d["Kpf"],
                step=0.01,
                key=f"Kpf_{key}"
            )

            cycles_an = st.number_input(
                "Cycles estimés / an",
                min_value=1.0,
                max_value=1000000.0,
                value=d["cycles_an"],
                step=1000.0,
                key=f"cycles_an_{key}",
                help="Permet de convertir Nresid en années."
            )

        pi_r_dwp = Ca * Kpr
        pi_c_dwp = DN * Kp
        if_dwp = pi_r_dwp / pi_c_dwp if pi_c_dwp > 0 else None
        nresid = ((R_dwp * pi_c_dwp) - pi_r_dwp) / Kpf if Kpf > 0 else None
        annees_dwp = nresid / cycles_an if nresid is not None and cycles_an > 0 else None

        status_dwp, badge_dwp, color_dwp = get_dwp_status(if_dwp, nresid)

        dwp_inputs[key] = {
            "label": d["label"],
            "Ca": Ca,
            "Kpr": Kpr,
            "DN": DN,
            "Kp": Kp,
            "R": R_dwp,
            "Kpf": Kpf,
            "cycles_an": cycles_an,
            "pi_r": pi_r_dwp,
            "pi_c": pi_c_dwp,
            "if_dwp": if_dwp,
            "nresid": nresid,
            "annees": annees_dwp,
            "status": status_dwp,
            "badge": badge_dwp,
            "color": color_dwp,
        }

        st.divider()

        m1, m2, m3, m4, m5 = st.columns(5)

        m1.metric("πr réel", f"{pi_r_dwp:,.0f} cycles")
        m2.metric("πc conception", f"{pi_c_dwp:,.0f} cycles")
        m3.metric("IF DWP", f"{if_dwp:.2%}" if if_dwp is not None else "—")
        m4.metric("Nresid", f"{nresid:,.0f} cycles" if nresid is not None and nresid > 0 else "Épuisé")
        m5.metric("Années résiduelles", f"{annees_dwp:.1f}" if annees_dwp is not None and annees_dwp > 0 else "Épuisé")

        if nresid is not None and nresid <= 0:
            st.error("La durée de vie résiduelle théorique est épuisée.")
        elif annees_dwp is not None and annees_dwp > 10:
            st.success("La durée de vie résiduelle théorique est supérieure à 10 ans.")
        elif annees_dwp is not None:
            st.warning(f"La durée de vie résiduelle théorique est estimée à {annees_dwp:.1f} ans.")
        else:
            st.info("Durée de vie résiduelle non calculable avec les données actuelles.")

st.divider()

st.markdown("## Synthèse DWP - Charpente et Chariot")

dwp_rows = []

for key, r in dwp_inputs.items():
    dwp_rows.append({
        "Type": "DWP",
        "Élément": r["label"],
        "Ca": r["Ca"],
        "Kpr": r["Kpr"],
        "DN": r["DN"],
        "Kp": r["Kp"],
        "R": r["R"],
        "Kpf": r["Kpf"],
        "Cycles/an": r["cycles_an"],
        "πr": round(r["pi_r"], 1),
        "πc": round(r["pi_c"], 1),
        "IF DWP": round(r["if_dwp"], 4) if r["if_dwp"] is not None else None,
        "Nresid": round(r["nresid"]) if r["nresid"] is not None else None,
        "Années résiduelles": round(r["annees"], 1) if r["annees"] is not None else None,
        "Statut": r["status"],
    })

df_dwp = pd.DataFrame(dwp_rows)

styled_dwp = (
    df_dwp.style
    .map(color_status, subset=["Statut"])
    .format({
        "Ca": "{:,.0f}",
        "Kpr": "{:.2f}",
        "DN": "{:,.0f}",
        "Kp": "{:.2f}",
        "R": "{:.2f}",
        "Kpf": "{:.2f}",
        "Cycles/an": "{:,.0f}",
        "πr": "{:,.0f}",
        "πc": "{:,.0f}",
        "IF DWP": "{:.2%}",
        "Nresid": "{:,.0f}",
        "Années résiduelles": "{:.1f}",
    }, na_rep="—")
)

st.dataframe(styled_dwp, use_container_width=True, hide_index=True)

st.divider()

col_d1, col_d2 = st.columns(2)

with col_d1:
    st.markdown("## IF DWP par élément")

    dwp_labels = [r["label"] for r in dwp_inputs.values()]
    dwp_vals = [r["if_dwp"] or 0 for r in dwp_inputs.values()]
    dwp_colors = [r["color"] for r in dwp_inputs.values()]

    fig3 = go.Figure(go.Bar(
        x=dwp_labels,
        y=dwp_vals,
        marker=dict(
            color=dwp_colors,
            opacity=0.9,
            line=dict(color="#0d0f16", width=1)
        ),
        text=[f"{v:.0%}" for v in dwp_vals],
        textposition="outside",
    ))

    fig3.add_hline(
        y=1.00,
        line_dash="dash",
        line_color=COLORS["red"],
        annotation_text="Limite conception"
    )

    fig3.update_layout(
        **PLOTLY_LAYOUT,
        height=390,
        yaxis_title="IF DWP"
    )

    fig3.update_yaxes(range=[0, max(1.2, max(dwp_vals) + 0.25)])
    fig3.update_xaxes(title="Élément")

    st.plotly_chart(fig3, use_container_width=True)

with col_d2:
    st.markdown("## πr réel vs πc conception - DWP")

    fig4 = go.Figure()

    for key, r in dwp_inputs.items():
        fig4.add_trace(go.Bar(
            name=f"{r['label']} - πr",
            x=[r["label"]],
            y=[r["pi_r"]],
            marker_color=COLORS["blue"],
            opacity=0.9
        ))

        fig4.add_trace(go.Bar(
            name=f"{r['label']} - πc",
            x=[r["label"]],
            y=[r["pi_c"]],
            marker_color="#2a2e3f",
            marker_line=dict(color=COLORS["grey"], width=1)
        ))

    fig4.update_layout(
        **PLOTLY_LAYOUT,
        barmode="group",
        height=390,
        yaxis_title="Cycles équivalents",
        showlegend=False
    )

    fig4.update_xaxes(title="Élément")

    st.plotly_chart(fig4, use_container_width=True)

st.divider()

st.markdown("## Lecture technique")

st.markdown("""
### Mécanismes

- **T0 à T9** : classe d'utilisation selon la durée totale d'utilisation du mécanisme.
- **L1 à L4** : classe de spectre selon le facteur de spectre km.
- **M1 à M8** : groupe de mécanisme obtenu par combinaison de la classe T et de la classe L.
- **πr = f1 × Hr × Kmr** représente l'endommagement équivalent déjà consommé.
- **πc = Hc × Kmc** représente la capacité théorique de conception selon les hypothèses retenues.
- **IFm = πr / πc** compare ces deux valeurs et sert d'indicateur synthétique de fatigue.
- **Hresid = (R × πc - πr) / Kmf** estime les heures restantes dans les conditions futures supposées.

### Charpente et chariot - DWP

- **Ca** : nombre de cycles réalisés.
- **Kpr** : spectre de charge réalisé.
- **DN** : nombre de cycles de conception.
- **Kp** : spectre de charge de conception.
- **πr = Ca × Kpr** représente l'endommagement réel en cycles équivalents.
- **πc = DN × Kp** représente la limite de conception en cycles équivalents.
- **IF DWP = πr / πc** représente l'indice de fatigue global.
- **Nresid = (R × πc - πr) / Kpf** estime les cycles résiduels.
""")

st.warning(
    "Ce calcul est une aide à la décision. Il doit être complété par les données constructeur, "
    "les historiques d'inspection et l'expertise d'un organisme compétent."
)

st.divider()


def make_ifm_pdf(
    pont_nom,
    pont_site,
    pont_mes,
    hu,
    mechanism_group,
    selected_time_class,
    selected_load_spectrum,
    R_global,
    f1_global,
    df_res,
    df_dwp,
):
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=25,
    )

    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Rapport IFm / Hresid - Pont roulant", styles["Title"]))
    story.append(Spacer(1, 12))

    info_data = [
        ["Pont", pont_nom or "—"],
        ["Site", pont_site or "—"],
        ["Année MES", str(pont_mes)],
        ["Heures utilisation / an", f"{hu:,.0f} h/an"],
        ["Classe T", selected_time_class],
        ["Spectre L", selected_load_spectrum],
        ["Groupe mécanisme", mechanism_group],
        ["Rapport admissible R", f"{R_global:.2f}"],
        ["Facteur f1", f"{f1_global:.2f}"],
    ]

    info_table = Table(info_data, colWidths=[180, 520])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eeeeee")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 18))

    story.append(Paragraph("Synthèse des mécanismes", styles["Heading2"]))

    mech_cols = [
        "Élément", "Groupe M", "Hr (h)", "Kmr", "f1", "Hc (h)", "Kmc",
        "R", "Kmf", "πr", "πc", "IFm", "Hresid (h)", "Années résiduelles", "Statut"
    ]

    mech_data = [mech_cols]
    for _, row in df_res.iterrows():
        mech_data.append([
            str(row.get("Élément", "—")),
            str(row.get("Groupe M", "—")),
            f"{row.get('Hr (h)', 0):,.0f}",
            f"{row.get('Kmr', 0):.2f}",
            f"{row.get('f1', 0):.2f}",
            f"{row.get('Hc (h)', 0):,.0f}",
            f"{row.get('Kmc', 0):.2f}",
            f"{row.get('R', 0):.2f}",
            f"{row.get('Kmf', 0):.2f}",
            f"{row.get('πr', 0):,.0f}",
            f"{row.get('πc', 0):,.0f}",
            f"{row.get('IFm', 0):.3f}" if pd.notna(row.get("IFm")) else "—",
            f"{row.get('Hresid (h)', 0):,.0f}" if pd.notna(row.get("Hresid (h)")) else "—",
            f"{row.get('Années résiduelles', 0):.1f}" if pd.notna(row.get("Années résiduelles")) else "—",
            str(row.get("Statut", "—")),
        ])

    mech_table = Table(mech_data, repeatRows=1)
    mech_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dddddd")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(mech_table)
    story.append(Spacer(1, 18))

    story.append(Paragraph("Synthèse DWP - Charpente et Chariot", styles["Heading2"]))

    dwp_cols = [
        "Élément", "Ca", "Kpr", "DN", "Kp", "R", "Kpf",
        "Cycles/an", "πr", "πc", "IF DWP", "Nresid",
        "Années résiduelles", "Statut"
    ]

    dwp_data = [dwp_cols]
    for _, row in df_dwp.iterrows():
        dwp_data.append([
            str(row.get("Élément", "—")),
            f"{row.get('Ca', 0):,.0f}",
            f"{row.get('Kpr', 0):.2f}",
            f"{row.get('DN', 0):,.0f}",
            f"{row.get('Kp', 0):.2f}",
            f"{row.get('R', 0):.2f}",
            f"{row.get('Kpf', 0):.2f}",
            f"{row.get('Cycles/an', 0):,.0f}",
            f"{row.get('πr', 0):,.0f}",
            f"{row.get('πc', 0):,.0f}",
            f"{row.get('IF DWP', 0):.2%}" if pd.notna(row.get("IF DWP")) else "—",
            f"{row.get('Nresid', 0):,.0f}" if pd.notna(row.get("Nresid")) else "—",
            f"{row.get('Années résiduelles', 0):.1f}" if pd.notna(row.get("Années résiduelles")) else "—",
            str(row.get("Statut", "—")),
        ])

    dwp_table = Table(dwp_data, repeatRows=1)
    dwp_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dddddd")),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(dwp_table)
    story.append(Spacer(1, 18))

    story.append(Paragraph("Avertissement", styles["Heading2"]))
    story.append(Paragraph(
        "Ce calcul est une aide à la décision. Il doit être complété par les données constructeur, "
        "les historiques d'inspection et l'expertise d'un organisme compétent.",
        styles["Normal"]
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer

pdf_buffer = make_ifm_pdf(
    pont_nom=pont_nom,
    pont_site=pont_site,
    pont_mes=pont_mes,
    hu=hu,
    mechanism_group=mechanism_group,
    selected_time_class=selected_time_class,
    selected_load_spectrum=selected_load_spectrum,
    R_global=R_global,
    f1_global=f1_global,
    df_res=df_res,
    df_dwp=df_dwp,
)

st.download_button(
    "📄 Télécharger le rapport PDF",
    data=pdf_buffer,
    file_name=f"Rapport_IFm_DWP_{pont_nom or 'pont'}_{pont_site or 'site'}.pdf",
    mime="application/pdf"
)
