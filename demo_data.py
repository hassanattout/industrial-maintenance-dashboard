"""Deterministic synthetic fleet for demonstrating the decision engine.

This file contains no Renault or customer data. It exists so the advanced
risk/CAPEX workflow can be demonstrated without pretending that optional
production, failure, downtime, safety, or intervention-cost fields were present
in the original workbook.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_demo_fleet(n_assets: int = 60, seed: int = 17) -> pd.DataFrame:
    if n_assets <= 0:
        raise ValueError("n_assets must be positive")

    rng = np.random.default_rng(seed)
    countries = np.array(["FRANCE", "SPAIN", "TURKEY"])
    sites = {
        "FRANCE": np.array(["Factory Alpha", "Factory Beta"]),
        "SPAIN": np.array(["Factory Gamma"]),
        "TURKEY": np.array(["Factory Delta"]),
    }

    rows = []
    for i in range(n_assets):
        country = str(rng.choice(countries, p=[0.55, 0.20, 0.25]))
        site = str(rng.choice(sites[country]))
        age = int(rng.integers(3, 46))
        production_criticality = int(rng.integers(1, 6))

        # Synthetic operating-history signals. These relationships are only
        # for demo realism and are not predictive models.
        failure_lambda = 0.25 + age / 35.0 + production_criticality / 8.0
        failure_count = int(min(8, rng.poisson(failure_lambda)))
        downtime = round(
            max(0.0, rng.normal(4 + failure_count * 13 + production_criticality * 2, 8)),
            1,
        )

        safety_draw = rng.random()
        if safety_draw < 0.08:
            safety = "Major"
        elif safety_draw < 0.25:
            safety = "Medium"
        elif safety_draw < 0.65:
            safety = "Low"
        else:
            safety = "None"

        compliance_draw = rng.random()
        if compliance_draw < 0.12:
            evs = "Obligatoire"
        elif compliance_draw < 0.32:
            evs = "Surveillance"
        else:
            evs = "Non requis"

        base_cost = 15_000 + age * 1_800 + production_criticality * 8_000 + failure_count * 7_500
        intervention_cost = int(round(max(10_000, rng.normal(base_cost, 12_000)) / 1_000) * 1_000)
        planned_budget = int(round(intervention_cost * rng.uniform(0.9, 1.35) / 1_000) * 1_000)

        rows.append(
            {
                "pays": country,
                "site": site,
                "pont": f"DEMO-{i + 1:03d}",
                "age": age,
                "evs_statut": evs,
                "production_criticality": production_criticality,
                "failure_count_12m": failure_count,
                "downtime_hours_12m": downtime,
                "safety_severity": safety,
                "estimated_intervention_cost": intervention_cost,
                "budget_total": planned_budget,
            }
        )

    return pd.DataFrame(rows)
