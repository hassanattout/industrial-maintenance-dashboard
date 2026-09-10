import pandas as pd
import pytest

from demo_data import build_demo_fleet


def test_demo_fleet_is_deterministic_and_complete():
    a = build_demo_fleet(n_assets=25, seed=7)
    b = build_demo_fleet(n_assets=25, seed=7)

    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 25
    assert a["pont"].is_unique
    assert {
        "pays",
        "site",
        "pont",
        "age",
        "evs_statut",
        "production_criticality",
        "failure_count_12m",
        "downtime_hours_12m",
        "safety_severity",
        "estimated_intervention_cost",
        "budget_total",
    }.issubset(a.columns)
    assert a["production_criticality"].between(1, 5).all()
    assert a["failure_count_12m"].ge(0).all()
    assert a["downtime_hours_12m"].ge(0).all()
    assert a["estimated_intervention_cost"].gt(0).all()


def test_demo_fleet_rejects_non_positive_size():
    with pytest.raises(ValueError):
        build_demo_fleet(n_assets=0)
