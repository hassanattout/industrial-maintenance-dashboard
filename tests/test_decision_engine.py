import math

import pandas as pd
import pytest

from decision_engine import build_risk_register, data_quality_report, optimize_capex


def sample_fleet():
    return pd.DataFrame(
        [
            {
                "pays": "FRANCE",
                "site": "Plant A",
                "pont": "CRN-001",
                "age": 35,
                "evs_statut": "Obligatoire",
                "production_criticality": 5,
                "failure_count_12m": 4,
                "downtime_hours_12m": 60,
                "safety_severity": "Major",
                "estimated_intervention_cost": 100_000,
                "budget_total": 120_000,
            },
            {
                "pays": "FRANCE",
                "site": "Plant A",
                "pont": "CRN-002",
                "age": 22,
                "evs_statut": "Surveillance",
                "production_criticality": 4,
                "failure_count_12m": 3,
                "downtime_hours_12m": 40,
                "safety_severity": "Medium",
                "estimated_intervention_cost": 80_000,
                "budget_total": 90_000,
            },
            {
                "pays": "FRANCE",
                "site": "Plant B",
                "pont": "CRN-003",
                "age": 10,
                "evs_statut": "Non requis",
                "production_criticality": 2,
                "failure_count_12m": 1,
                "downtime_hours_12m": 5,
                "safety_severity": "Low",
                "estimated_intervention_cost": 40_000,
                "budget_total": 50_000,
            },
        ]
    )


def test_risk_register_is_explainable_and_bounded():
    register = build_risk_register(sample_fleet())

    assert set(["risk_score", "data_confidence", "risk_drivers", "recommended_action"]).issubset(register.columns)
    assert register["risk_score"].between(0, 100).all()
    assert register["data_confidence"].between(0, 100).all()
    assert register.iloc[0]["pont"] == "CRN-001"
    assert bool(register.iloc[0]["mandatory_action"]) is True
    assert register.iloc[0]["data_confidence"] == pytest.approx(100.0)
    assert "Compliance" in register.iloc[0]["risk_drivers"] or "Safety" in register.iloc[0]["risk_drivers"]


def test_missing_optional_evidence_reduces_confidence_not_risk_to_zero():
    sparse = pd.DataFrame(
        [{"pays": "FRANCE", "site": "Plant A", "pont": "CRN-X", "age": 45, "evs_statut": "Obligatoire", "budget_total": 50_000}]
    )

    register = build_risk_register(sparse)
    row = register.iloc[0]

    assert 0 < row["data_confidence"] < 100
    assert row["risk_score"] > 0
    assert math.isnan(row["score_safety"])
    assert math.isnan(row["score_production"])


def test_direct_intervention_cost_preferred_over_planned_budget_proxy():
    register = build_risk_register(sample_fleet())
    row = register[register["pont"] == "CRN-002"].iloc[0]

    assert row["intervention_cost_eur"] == pytest.approx(80_000)
    assert row["cost_source"] == "estimated_intervention_cost"


def test_budget_proxy_is_labeled_when_direct_cost_missing():
    fleet = sample_fleet().drop(columns=["estimated_intervention_cost"])
    register = build_risk_register(fleet)
    row = register[register["pont"] == "CRN-002"].iloc[0]

    assert row["intervention_cost_eur"] == pytest.approx(90_000)
    assert "proxy" in row["cost_source"]


def test_optimizer_reserves_mandatory_cost_before_discretionary_selection():
    register = build_risk_register(sample_fleet())
    result = optimize_capex(register, budget_eur=180_000, expected_reduction_fraction=0.40, budget_quantum_eur=5_000)

    assert result.mandatory_cost_eur == pytest.approx(100_000)
    assert result.discretionary_budget_eur == pytest.approx(80_000)
    assert result.selected_cost_eur <= result.discretionary_budget_eur
    assert set(result.selected["pont"]) == {"CRN-002"}
    assert "CRN-001" not in set(result.selected["pont"])


def test_optimizer_rejects_invalid_scenario_inputs():
    register = build_risk_register(sample_fleet())

    with pytest.raises(ValueError):
        optimize_capex(register, budget_eur=-1)
    with pytest.raises(ValueError):
        optimize_capex(register, budget_eur=100_000, expected_reduction_fraction=1.5)
    with pytest.raises(ValueError):
        optimize_capex(register, budget_eur=100_000, budget_quantum_eur=0)


def test_data_quality_report_flags_duplicates_and_signal_coverage():
    fleet = sample_fleet()
    fleet = pd.concat([fleet, fleet.iloc[[0]]], ignore_index=True)
    report = data_quality_report(fleet)

    assert report["rows"] == 4
    assert report["duplicate_asset_keys"] == 2
    assert report["optional_signal_coverage"]["production"] == pytest.approx(100.0)
    assert report["optional_signal_coverage"]["safety"] == pytest.approx(100.0)
