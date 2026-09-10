import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).parent.parent))

from decision_engine import build_risk_register, data_quality_report, optimize_capex
from demo_data import build_demo_fleet
from utils import apply_global_style, load_data, require_uploaded_excel


apply_global_style()

st.title("Asset Risk & CAPEX Decision Engine")
st.caption(
    "Explainable engineering prioritization for a multi-site industrial fleet. "
    "The model is deterministic, auditable, and intentionally separates data confidence from risk."
)
st.info(
    "Decision-support tool only. It does not predict failures and does not replace statutory inspections, "
    "engineering judgement, or certified fitness-for-service decisions."
)

source = st.radio(
    "Data source",
    ["Uploaded workbook", "Synthetic demonstration"],
    horizontal=True,
    help="Synthetic mode demonstrates the complete workflow without using company/customer data.",
)

if source == "Synthetic demonstration":
    demo_assets = st.slider("Synthetic fleet size", 20, 120, 60, 10)
    df = build_demo_fleet(n_assets=demo_assets)
    st.success(
        "Synthetic mode: operating history, safety, criticality and intervention-cost fields are generated demo data. "
        "No Renault or customer data is used."
    )
else:
    require_uploaded_excel()
    df = load_data()

register = build_risk_register(df)
quality = data_quality_report(df)

if register.empty:
    st.warning("No valid assets are available for analysis.")
    st.stop()

mandatory_count = int(register["mandatory_action"].sum())
high_risk_count = int((register["risk_score"] >= 65).sum())
median_confidence = float(register["data_confidence"].median())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Assets", f"{len(register):,}")
c2.metric("Mandatory reviews", f"{mandatory_count:,}")
c3.metric("Risk score ≥ 65", f"{high_risk_count:,}")
c4.metric("Median evidence coverage", f"{median_confidence:.0f}%")

st.caption(
    "Evidence coverage is the share of the intended risk model supported by fields actually present for each asset. "
    "Missing evidence is not silently imputed."
)

cockpit, quality_tab, scenario_tab, methodology_tab = st.tabs(
    ["Decision cockpit", "Data quality", "CAPEX scenarios", "Methodology"]
)

with cockpit:
    st.subheader("Prioritized fleet")

    countries = sorted(register["pays"].dropna().astype(str).unique()) if "pays" in register.columns else []
    sites = sorted(register["site"].dropna().astype(str).unique()) if "site" in register.columns else []

    f1, f2, f3 = st.columns(3)
    selected_country = f1.selectbox("Country", ["All"] + countries)
    selected_site = f2.selectbox("Site", ["All"] + sites)
    minimum_confidence = f3.slider("Minimum evidence coverage", 0, 100, 0, 5)

    view = register.copy()
    if selected_country != "All" and "pays" in view.columns:
        view = view[view["pays"].astype(str) == selected_country]
    if selected_site != "All" and "site" in view.columns:
        view = view[view["site"].astype(str) == selected_site]
    view = view[view["data_confidence"] >= minimum_confidence]

    if view.empty:
        st.warning("No assets match the current filters.")
    else:
        chart_df = view.head(30).copy()
        chart_df["asset"] = (
            chart_df["pont"].astype(str)
            if "pont" in chart_df.columns
            else chart_df.index.astype(str)
        )

        # Plotly's marker-size validator rejects NaN/inf. Cost is optional in the
        # decision model, so sanitize it only for visualization and retain the
        # original intervention_cost_eur column for auditability.
        marker_cost = pd.to_numeric(
            chart_df.get("intervention_cost_eur", pd.Series(index=chart_df.index, dtype=float)),
            errors="coerce",
        )
        marker_cost = marker_cost.replace([np.inf, -np.inf], np.nan).fillna(0.0).clip(lower=0.0)
        chart_df["_marker_cost"] = marker_cost
        size_field = "_marker_cost" if marker_cost.gt(0).any() else None

        fig = px.scatter(
            chart_df,
            x="risk_score",
            y="data_confidence",
            size=size_field,
            size_max=36,
            color="mandatory_action",
            hover_name="asset",
            hover_data={
                **{
                    c: True
                    for c in ["site", "pays", "recommended_action", "risk_drivers", "cost_source", "intervention_cost_eur"]
                    if c in chart_df.columns
                },
                "_marker_cost": False,
            },
            labels={
                "risk_score": "Risk score / 100",
                "data_confidence": "Evidence coverage / 100",
                "intervention_cost_eur": "Intervention cost (€)",
                "mandatory_action": "Mandatory",
            },
            title="Risk versus evidence coverage (top 30 by priority)",
        )
        fig.add_vline(x=65, line_dash="dash")
        fig.add_hline(y=40, line_dash="dot")
        st.plotly_chart(fig, use_container_width=True)

        display_cols = [
            c
            for c in [
                "pays",
                "site",
                "pont",
                "risk_score",
                "data_confidence",
                "mandatory_action",
                "recommended_action",
                "risk_drivers",
                "intervention_cost_eur",
                "cost_source",
            ]
            if c in view.columns
        ]
        st.dataframe(
            view[display_cols].head(100),
            use_container_width=True,
            hide_index=True,
            column_config={
                "risk_score": st.column_config.ProgressColumn(
                    "Risk", min_value=0, max_value=100, format="%.1f"
                ),
                "data_confidence": st.column_config.ProgressColumn(
                    "Evidence", min_value=0, max_value=100, format="%.1f%%"
                ),
                "intervention_cost_eur": st.column_config.NumberColumn(
                    "Intervention cost", format="€ %.0f"
                ),
            },
        )

        st.subheader("Asset explanation")
        asset_options = view["asset_key"].astype(str).tolist()
        chosen_asset = st.selectbox("Select asset", asset_options)
        r = view[view["asset_key"].astype(str) == chosen_asset].iloc[0]

        a1, a2, a3 = st.columns(3)
        a1.metric("Risk", f"{r['risk_score']:.1f}/100")
        a2.metric("Evidence coverage", f"{r['data_confidence']:.0f}%")
        a3.metric("Mandatory", "Yes" if bool(r["mandatory_action"]) else "No")
        st.markdown(f"**Recommended action:** {r['recommended_action']}")
        st.markdown(f"**Main drivers:** {r['risk_drivers']}")
        if pd.notna(r.get("intervention_cost_eur")):
            st.markdown(
                f"**Cost used for scenario planning:** €{r['intervention_cost_eur']:,.0f} ({r['cost_source']})"
            )

        component_rows = []
        for key, label in [
            ("compliance", "Compliance / EVS"),
            ("safety", "Safety severity"),
            ("production", "Production criticality"),
            ("failures", "Failure frequency"),
            ("downtime", "Unplanned downtime"),
            ("age", "Equipment age"),
        ]:
            value = r.get(f"score_{key}")
            component_rows.append(
                {"Signal": label, "Score": value, "Available": pd.notna(value)}
            )
        st.dataframe(pd.DataFrame(component_rows), use_container_width=True, hide_index=True)

with quality_tab:
    st.subheader("Data-quality gate")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Rows", quality["rows"])
    q2.metric("Duplicate asset keys", quality["duplicate_asset_keys"])
    q3.metric("Missing asset IDs", quality["missing_asset_id"])
    q4.metric("Missing age", quality["missing_age"])

    st.markdown("#### Optional decision-signal coverage")
    coverage_df = pd.DataFrame(
        [
            {"Signal": key.replace("_", " ").title(), "Coverage (%)": value}
            for key, value in quality["optional_signal_coverage"].items()
        ]
    )
    if coverage_df.empty:
        st.caption("No optional signals detected.")
    else:
        st.dataframe(
            coverage_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Coverage (%)": st.column_config.ProgressColumn(
                    "Coverage (%)", min_value=0, max_value=100, format="%.1f%%"
                )
            },
        )

    st.markdown("#### Why the gate exists")
    st.write(
        "A precise-looking score is dangerous when the underlying evidence is incomplete. "
        "The engine therefore reports both risk and evidence coverage, and never converts missing fields into zero risk."
    )

    st.markdown("#### Optional enriched columns")
    st.code(
        "production_criticality\n"
        "failure_count_12m\n"
        "downtime_hours_12m\n"
        "safety_severity\n"
        "estimated_intervention_cost",
        language="text",
    )
    st.caption(
        "The current workbook remains valid without these columns. Adding them increases evidence coverage and makes "
        "the scenario model more decision-relevant."
    )

with scenario_tab:
    st.subheader("Budget-constrained intervention portfolio")

    known_costs = pd.to_numeric(register["intervention_cost_eur"], errors="coerce").dropna()
    known_cost_sum = float(known_costs[known_costs > 0].sum()) if not known_costs.empty else 0.0
    suggested_max = int(max(500_000, min(10_000_000, known_cost_sum or 2_000_000)))
    default_budget = int(min(max(250_000, suggested_max // 2), suggested_max))

    s1, s2 = st.columns(2)
    budget = s1.number_input(
        "Available annual intervention budget (€)",
        min_value=0,
        value=default_budget,
        step=50_000,
    )
    reduction = s2.slider(
        "Scenario assumption: risk-score reduction after completed intervention",
        min_value=10,
        max_value=80,
        value=40,
        step=5,
        help="This is an explicit scenario assumption, not a predicted failure probability.",
    ) / 100.0

    result = optimize_capex(register, float(budget), expected_reduction_fraction=reduction)

    st.warning(
        "Mandatory compliance items are surfaced separately and are not traded off against discretionary economic value. "
        "When their costs are known, those costs are reserved before optimization."
    )

    s3, s4, s5, s6 = st.columns(4)
    s3.metric("Mandatory known cost", f"€{result.mandatory_cost_eur:,.0f}")
    s4.metric("Discretionary budget", f"€{result.discretionary_budget_eur:,.0f}")
    s5.metric("Selected discretionary cost", f"€{result.selected_cost_eur:,.0f}")
    s6.metric("Scenario risk points reduced", f"{result.expected_risk_points_reduced:,.1f}")

    if result.mandatory_cost_eur > float(budget):
        st.error(
            f"Known mandatory cost exceeds the entered budget by €{result.mandatory_cost_eur - float(budget):,.0f}. "
            "This is shown as a funding gap rather than allowing mandatory work to be dropped."
        )

    if not result.mandatory.empty:
        st.markdown("#### Mandatory / compliance queue")
        mandatory_cols = [
            c
            for c in [
                "pays", "site", "pont", "risk_score", "recommended_action",
                "intervention_cost_eur", "cost_source",
            ]
            if c in result.mandatory.columns
        ]
        st.dataframe(result.mandatory[mandatory_cols], use_container_width=True, hide_index=True)

    st.markdown("#### Optimized discretionary portfolio")
    if result.selected.empty:
        st.info("No costed discretionary interventions fit the current budget and assumptions.")
    else:
        selected_cols = [
            c
            for c in [
                "pays", "site", "pont", "risk_score", "expected_risk_reduction",
                "intervention_cost_eur", "cost_source", "recommended_action",
            ]
            if c in result.selected.columns
        ]
        st.dataframe(result.selected[selected_cols], use_container_width=True, hide_index=True)

    st.markdown("#### Budget frontier")
    frontier_max = max(float(budget), known_cost_sum, 250_000.0)
    frontier_rows = []
    for scenario_budget in np.linspace(0, frontier_max, 9):
        scenario = optimize_capex(
            register,
            float(scenario_budget),
            expected_reduction_fraction=reduction,
        )
        frontier_rows.append(
            {
                "Budget (€)": scenario_budget,
                "Scenario risk points reduced": scenario.expected_risk_points_reduced,
                "Selected discretionary cost (€)": scenario.selected_cost_eur,
            }
        )
    frontier_df = pd.DataFrame(frontier_rows)
    frontier_fig = px.line(
        frontier_df,
        x="Budget (€)",
        y="Scenario risk points reduced",
        markers=True,
        title="Decision frontier: budget versus scenario risk reduction",
    )
    st.plotly_chart(frontier_fig, use_container_width=True)

    st.caption(
        f"Optimization uses a 0/1 knapsack model with a €{result.budget_quantum_eur:,} budget quantum. "
        "It is therefore exact at that discretization level, not at single-euro precision."
    )

with methodology_tab:
    st.subheader("Model design")
    st.markdown(
        """
**1. Evidence first.** The engine uses only signals present in the dataset. Missing signals are not treated as healthy assets.

**2. Risk and confidence are separate.** A high-risk, low-evidence item means “investigate”, not “the model knows the truth”.

**3. Deterministic and explainable.** Each score is a weighted combination of interpretable engineering signals and the main drivers are exposed.

**4. Safety is not optimized away.** Mandatory compliance actions stay outside the discretionary economic trade-off.

**5. CAPEX is scenario planning, not prediction.** The optimizer maximizes an assumed reduction in risk points subject to a budget. The effectiveness assumption is visible and editable.
        """
    )

    st.markdown("#### Base weights")
    st.dataframe(
        pd.DataFrame(
            {
                "Signal": [
                    "Compliance / EVS",
                    "Safety severity",
                    "Production criticality",
                    "Failure frequency",
                    "Unplanned downtime",
                    "Equipment age",
                ],
                "Weight (%)": [30, 25, 15, 10, 10, 10],
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### Transparent normalization assumptions")
    st.dataframe(
        pd.DataFrame(
            [
                ["Age", "50 years → 100/100", "Clipped at 100; calibrate to fleet context"],
                ["Failures", "5 failures / 12 months → 100/100", "Monotonic scaling, not a probability"],
                ["Downtime", "100 h / 12 months → 100/100", "Monotonic scaling, not financial loss"],
                ["Production criticality", "1–5 ordinal scale", "5 maps to 100/100"],
                ["Safety severity", "None/Low/Medium/Major/Critical", "Ordinal engineering input"],
                ["Compliance", "EVS / compliance status", "Mandatory states are flagged explicitly"],
            ],
            columns=["Signal", "Current assumption", "Interpretation"],
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### Important limitations")
    st.write(
        "Weights and normalization thresholds are engineering assumptions. Before operational use they should be calibrated "
        "with plant experts and retrospective cases. The model does not estimate failure probability, certified remaining life, "
        "or guaranteed financial return."
    )
