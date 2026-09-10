"""Explainable industrial asset risk and CAPEX scenario engine.

The module is intentionally deterministic and auditable. It does not claim to
predict failures. It combines available engineering signals into a normalized
risk score, reports how much of the intended evidence is actually available,
and supports budget-constrained scenario planning.

The CAPEX routine solves a discretized 0/1 knapsack problem. It is exact with
respect to the chosen budget quantum, not to the euro. Safety/compliance items
marked mandatory are kept outside the economic optimization and surfaced
separately.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
import unicodedata
from typing import Iterable

import numpy as np
import pandas as pd


BASE_WEIGHTS = {
    "compliance": 0.30,
    "safety": 0.25,
    "production": 0.15,
    "failures": 0.10,
    "downtime": 0.10,
    "age": 0.10,
}

COMPONENT_LABELS = {
    "compliance": "Compliance / EVS",
    "safety": "Safety severity",
    "production": "Production criticality",
    "failures": "Failure frequency",
    "downtime": "Unplanned downtime",
    "age": "Equipment age",
}

ALIASES = {
    "production": [
        "production_criticality",
        "criticite_production",
        "criticalite_production",
        "production criticality",
    ],
    "failures": [
        "failure_count_12m",
        "failures_12m",
        "pannes_12m",
        "nb_pannes_12m",
        "failure count 12m",
    ],
    "downtime": [
        "downtime_hours_12m",
        "downtime_12m",
        "heures_arret_12m",
        "heures_arret",
        "downtime hours 12m",
    ],
    "safety": [
        "safety_severity",
        "severite_securite",
        "gravite_securite",
        "safety severity",
    ],
    "intervention_cost": [
        "estimated_intervention_cost",
        "estimated_repair_cost",
        "cout_intervention",
        "cout_reparation",
        "intervention cost",
        "repair cost",
    ],
}


@dataclass(frozen=True)
class OptimizationResult:
    selected: pd.DataFrame
    mandatory: pd.DataFrame
    budget_eur: float
    discretionary_budget_eur: float
    mandatory_cost_eur: float
    selected_cost_eur: float
    expected_risk_points_reduced: float
    budget_quantum_eur: int


def _norm_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _find_column(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    normalized = {_norm_name(col): col for col in df.columns}
    for alias in aliases:
        key = _norm_name(alias)
        if key in normalized:
            return normalized[key]
    return None


def _as_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.replace("€", "").replace(" ", "").replace(",", ".")
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _clip100(value: float) -> float:
    return float(np.clip(value, 0.0, 100.0))


def _ordinal_score(value: object, mapping: dict[str, float]) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = _norm_name(value)
    for key, score in mapping.items():
        if key in text:
            return score
    numeric = _as_float(value)
    if numeric is None:
        return None
    if 0 <= numeric <= 5:
        return _clip100((numeric / 5.0) * 100.0)
    if 0 <= numeric <= 100:
        return _clip100(numeric)
    return None


def _compliance_score(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = _norm_name(value)
    mapping = {
        "obligatoire": 100.0,
        "overdue": 100.0,
        "non_conforme": 100.0,
        "nonconform": 100.0,
        "a_desinvestir": 90.0,
        "surveillance": 65.0,
        "non_requis": 20.0,
        "non_concerne": 10.0,
    }
    for key, score in mapping.items():
        if key in text:
            return score
    if text in {"", "nan", "non_renseigne", "unknown"}:
        return None
    return 40.0


def _safety_score(value: object) -> float | None:
    return _ordinal_score(
        value,
        {
            "critical": 100.0,
            "critique": 100.0,
            "major": 80.0,
            "majeur": 80.0,
            "high": 80.0,
            "eleve": 80.0,
            "medium": 55.0,
            "moyen": 55.0,
            "minor": 30.0,
            "mineur": 30.0,
            "low": 20.0,
            "faible": 20.0,
            "none": 0.0,
            "aucun": 0.0,
        },
    )


def _production_score(value: object) -> float | None:
    return _ordinal_score(
        value,
        {
            "critical": 100.0,
            "critique": 100.0,
            "very_high": 100.0,
            "tres_eleve": 100.0,
            "high": 80.0,
            "eleve": 80.0,
            "medium": 55.0,
            "moyen": 55.0,
            "low": 25.0,
            "faible": 25.0,
            "redundant": 15.0,
            "redondant": 15.0,
        },
    )


def _row_components(row: pd.Series, columns: dict[str, str | None]) -> dict[str, float | None]:
    age = _as_float(row.get("age"))
    failures = _as_float(row.get(columns["failures"])) if columns["failures"] else None
    downtime = _as_float(row.get(columns["downtime"])) if columns["downtime"] else None

    return {
        "compliance": _compliance_score(row.get("evs_statut")),
        "safety": _safety_score(row.get(columns["safety"])) if columns["safety"] else None,
        "production": _production_score(row.get(columns["production"])) if columns["production"] else None,
        "failures": _clip100((failures / 5.0) * 100.0) if failures is not None and failures >= 0 else None,
        "downtime": _clip100((downtime / 100.0) * 100.0) if downtime is not None and downtime >= 0 else None,
        "age": _clip100((age / 50.0) * 100.0) if age is not None and age >= 0 else None,
    }


def _recommendation(score: float, confidence: float, mandatory: bool) -> str:
    if mandatory:
        return "Mandatory engineering review / compliance action"
    if confidence < 40:
        return "Complete missing evidence before prioritization"
    if score >= 80:
        return "Immediate engineering review"
    if score >= 65:
        return "Prioritize inspection / intervention"
    if score >= 45:
        return "Reinforced monitoring"
    return "Standard periodic monitoring"


def build_risk_register(df: pd.DataFrame) -> pd.DataFrame:
    """Return an explainable risk register from the evidence available in ``df``.

    Missing components are never silently imputed. The score is renormalized
    over the evidence that exists, while ``data_confidence`` reports the share
    of the intended base model that was actually supported by data.
    """
    if df.empty:
        return df.copy()

    columns = {
        key: _find_column(df, aliases)
        for key, aliases in ALIASES.items()
    }

    rows: list[dict[str, object]] = []
    for idx, row in df.iterrows():
        components = _row_components(row, columns)
        available = {k: v for k, v in components.items() if v is not None}
        covered_weight = sum(BASE_WEIGHTS[k] for k in available)

        if covered_weight:
            weighted = sum(BASE_WEIGHTS[k] * float(v) for k, v in available.items())
            risk_score = weighted / covered_weight
        else:
            risk_score = 0.0

        contributions = {
            k: (BASE_WEIGHTS[k] * float(v) / covered_weight) if covered_weight else 0.0
            for k, v in available.items()
        }
        driver_keys = sorted(contributions, key=contributions.get, reverse=True)[:3]
        drivers = "; ".join(
            f"{COMPONENT_LABELS[k]} {available[k]:.0f}/100" for k in driver_keys
        ) or "No usable risk evidence"

        evs_text = _norm_name(row.get("evs_statut", ""))
        mandatory = "obligatoire" in evs_text or "overdue" in evs_text or "non_conforme" in evs_text

        intervention_cost_col = columns["intervention_cost"]
        direct_cost = _as_float(row.get(intervention_cost_col)) if intervention_cost_col else None
        planned_budget = _as_float(row.get("budget_total"))
        if direct_cost is not None and direct_cost > 0:
            intervention_cost = direct_cost
            cost_source = intervention_cost_col
        elif planned_budget is not None and planned_budget > 0:
            intervention_cost = planned_budget
            cost_source = "budget_total (planned-budget proxy)"
        else:
            intervention_cost = np.nan
            cost_source = "missing"

        confidence = covered_weight * 100.0
        result = row.to_dict()
        result.update(
            {
                "asset_key": " | ".join(
                    str(row.get(c, "?")) for c in ["pays", "site", "pont"]
                ),
                "risk_score": round(risk_score, 1),
                "data_confidence": round(confidence, 1),
                "mandatory_action": bool(mandatory),
                "risk_drivers": drivers,
                "recommended_action": _recommendation(risk_score, confidence, mandatory),
                "intervention_cost_eur": intervention_cost,
                "cost_source": cost_source,
            }
        )
        for component, value in components.items():
            result[f"score_{component}"] = np.nan if value is None else round(float(value), 1)
        rows.append(result)

    register = pd.DataFrame(rows, index=df.index)
    return register.sort_values(
        ["mandatory_action", "risk_score", "data_confidence"],
        ascending=[False, False, False],
    )


def data_quality_report(df: pd.DataFrame) -> dict[str, object]:
    """Summarize the data issues that can undermine a decision."""
    if df.empty:
        return {
            "rows": 0,
            "duplicate_asset_keys": 0,
            "missing_site": 0,
            "missing_asset_id": 0,
            "missing_age": 0,
            "missing_evs": 0,
            "optional_signal_coverage": {},
        }

    key_cols = [c for c in ["pays", "site", "pont"] if c in df.columns]
    duplicate_count = int(df.duplicated(subset=key_cols, keep=False).sum()) if key_cols else 0

    coverage = {}
    for key, aliases in ALIASES.items():
        if key == "intervention_cost":
            continue
        col = _find_column(df, aliases)
        coverage[key] = round(float(df[col].notna().mean() * 100), 1) if col else 0.0

    return {
        "rows": int(len(df)),
        "duplicate_asset_keys": duplicate_count,
        "missing_site": int(df["site"].isna().sum()) if "site" in df.columns else len(df),
        "missing_asset_id": int(df["pont"].isna().sum()) if "pont" in df.columns else len(df),
        "missing_age": int(df["age"].isna().sum()) if "age" in df.columns else len(df),
        "missing_evs": int(df["evs_statut"].isna().sum()) if "evs_statut" in df.columns else len(df),
        "optional_signal_coverage": coverage,
    }


def optimize_capex(
    register: pd.DataFrame,
    budget_eur: float,
    expected_reduction_fraction: float = 0.40,
    budget_quantum_eur: int = 5_000,
) -> OptimizationResult:
    """Optimize discretionary interventions under a budget constraint.

    Mandatory compliance items are excluded from the economic trade-off and
    their cost is reserved first when known. The remaining candidates are
    solved as a discretized 0/1 knapsack maximizing expected risk points
    reduced. ``expected_reduction_fraction`` is a scenario assumption, not a
    failure prediction.
    """
    if budget_eur < 0:
        raise ValueError("budget_eur must be non-negative")
    if not 0 <= expected_reduction_fraction <= 1:
        raise ValueError("expected_reduction_fraction must be between 0 and 1")
    if budget_quantum_eur <= 0:
        raise ValueError("budget_quantum_eur must be positive")
    if register.empty:
        empty = register.copy()
        return OptimizationResult(empty, empty, budget_eur, budget_eur, 0.0, 0.0, 0.0, budget_quantum_eur)

    work = register.copy()
    work["intervention_cost_eur"] = pd.to_numeric(work["intervention_cost_eur"], errors="coerce")
    work["risk_score"] = pd.to_numeric(work["risk_score"], errors="coerce").fillna(0.0)
    work["expected_risk_reduction"] = work["risk_score"] * expected_reduction_fraction

    mandatory = work[work["mandatory_action"]].copy()
    mandatory_known = mandatory[mandatory["intervention_cost_eur"].gt(0)]
    mandatory_cost = float(mandatory_known["intervention_cost_eur"].sum())
    discretionary_budget = max(0.0, float(budget_eur) - mandatory_cost)

    candidates = work[
        (~work["mandatory_action"])
        & work["intervention_cost_eur"].gt(0)
        & work["expected_risk_reduction"].gt(0)
    ].copy()

    if candidates.empty or discretionary_budget <= 0:
        return OptimizationResult(
            candidates.iloc[0:0].copy(), mandatory, float(budget_eur), discretionary_budget,
            mandatory_cost, 0.0, 0.0, budget_quantum_eur,
        )

    capacity = int(discretionary_budget // budget_quantum_eur)
    if capacity <= 0:
        return OptimizationResult(
            candidates.iloc[0:0].copy(), mandatory, float(budget_eur), discretionary_budget,
            mandatory_cost, 0.0, 0.0, budget_quantum_eur,
        )

    costs = np.ceil(candidates["intervention_cost_eur"].to_numpy(float) / budget_quantum_eur).astype(int)
    values = candidates["expected_risk_reduction"].to_numpy(float)

    dp = np.zeros(capacity + 1, dtype=float)
    picks: list[list[int]] = [[] for _ in range(capacity + 1)]

    for i, (cost, value) in enumerate(zip(costs, values)):
        if cost <= 0 or cost > capacity:
            continue
        for b in range(capacity, cost - 1, -1):
            candidate_value = dp[b - cost] + value
            if candidate_value > dp[b] + 1e-12:
                dp[b] = candidate_value
                picks[b] = picks[b - cost] + [i]

    best_budget_slot = int(np.argmax(dp))
    chosen_positions = picks[best_budget_slot]
    selected = candidates.iloc[chosen_positions].copy() if chosen_positions else candidates.iloc[0:0].copy()
    selected_cost = float(selected["intervention_cost_eur"].sum()) if not selected.empty else 0.0
    reduced = float(selected["expected_risk_reduction"].sum()) if not selected.empty else 0.0

    return OptimizationResult(
        selected=selected.sort_values("risk_score", ascending=False),
        mandatory=mandatory.sort_values("risk_score", ascending=False),
        budget_eur=float(budget_eur),
        discretionary_budget_eur=discretionary_budget,
        mandatory_cost_eur=mandatory_cost,
        selected_cost_eur=selected_cost,
        expected_risk_points_reduced=reduced,
        budget_quantum_eur=budget_quantum_eur,
    )
