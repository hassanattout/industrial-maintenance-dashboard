# Industrial Maintenance Dashboard + Asset Risk & CAPEX Decision Engine

**Python/Streamlit engineering application for multi-site maintenance data, overhead-crane assessment, explainable risk prioritization, and budget-constrained CAPEX scenario planning.**

[Live Streamlit app](https://industrial-maintenance-dashboard.streamlit.app)

The original dashboard was developed during my apprenticeship at **Renault Group** to improve how overhead-crane maintenance and engineering data was consolidated, analysed, prioritised, and presented. The **Asset Risk & CAPEX Decision Engine** is a later portfolio extension built on top of that foundation to explore a more complete Forward Deployed Engineering workflow: messy industrial data → validated evidence → explainable prioritization → budget-constrained action planning.

The project is deliberately conservative about claims. It does **not** predict failures, estimate certified remaining life, or replace statutory inspection and engineering judgement. Instead, it makes assumptions visible, separates risk from data confidence, and keeps mandatory compliance actions outside the economic optimization.

![Dashboard overview](screenshots/dashboard-overview.png)

## Problem

Industrial maintenance decisions often start from heterogeneous Excel files, inconsistent site conventions, partial inspection data, and competing CAPEX requests. A useful engineering tool therefore has to do more than draw charts. It has to:

- ingest and normalize inconsistent data;
- expose data-quality gaps before calculations;
- distinguish missing evidence from low risk;
- turn available engineering signals into an explainable priority;
- preserve safety/compliance constraints;
- support transparent budget scenarios;
- show exactly why an asset was prioritized.

## What the application does

### 1. Excel ingestion and normalization

The application accepts a fleet workbook through the Streamlit interface and processes it in memory. The preprocessing layer handles:

- sheet detection;
- column-name normalization;
- removal of empty rows;
- text cleaning;
- country-name standardization;
- numeric type conversion;
- EVS status standardization;
- yearly budget aggregation;
- schema validation and clear rejection of malformed files.

### 2. Fleet overview

The overview page provides high-level indicators for equipment count, countries, industrial sites, average age, EVS status, and CAPEX/OPEX planning, with interactive Plotly visualizations and site/year budget analysis.

![Budget heatmap](screenshots/budget-heatmap.png)

### 3. Engineering prioritization

The existing prioritization page ranks equipment using the processed technical dataset and produces exportable engineering views.

### 4. Individual crane view

A dedicated equipment page supports asset-level review of technical, maintenance, EVS, and budget information.

### 5. IFm engineering calculator

A dedicated calculation page implements the project methodology around FEM operating-time classes, load-spectrum classes, mechanism groups, IFm, and residual-use indicators. The tool explicitly presents these outputs as engineering decision support, not certified fitness-for-service conclusions.

### 6. Asset Risk & CAPEX Decision Engine

The new decision-engine page adds four layers.

#### A. Data-quality gate

Before prioritization, the application reports issues such as duplicate asset keys, missing identifiers, missing age/EVS data, and coverage of optional decision signals.

Optional enriched columns are recognized automatically when available:

```text
production_criticality
failure_count_12m
downtime_hours_12m
safety_severity
estimated_intervention_cost
```

The existing workbook remains valid without these fields. When they are absent, the application does **not** invent them. Instead, the asset receives lower evidence coverage.

#### B. Explainable risk register

The risk engine combines only the signals actually available for each asset. The intended base model is:

| Signal | Base weight |
|---|---:|
| Compliance / EVS | 30% |
| Safety severity | 25% |
| Production criticality | 15% |
| Failure frequency | 10% |
| Unplanned downtime | 10% |
| Equipment age | 10% |

Missing components are excluded from the numerical score and the remaining weights are renormalized. A separate **data confidence / evidence coverage** value reports how much of the intended model was supported by actual fields.

This prevents a common failure mode in industrial analytics: treating missing information as zero risk.

Each asset receives:

- normalized risk score (0–100);
- evidence coverage (0–100%);
- mandatory-action flag;
- top risk drivers;
- recommended engineering action;
- intervention cost and provenance of that cost.

#### C. Safety/compliance separation

Mandatory compliance actions are not allowed to compete with discretionary projects in the economic optimizer. They are surfaced separately. When a mandatory item's cost is known, that cost is reserved before allocating the remaining discretionary budget.

This is intentional: the optimizer must not be able to 'optimize away' a mandatory safety/compliance action because another project appears to have better economic value.

#### D. CAPEX scenario optimizer

For costed discretionary interventions, the application solves a discretized 0/1 knapsack problem:

```text
maximize   Σ selected_i × expected_risk_reduction_i
subject to Σ selected_i × intervention_cost_i ≤ available_budget
```

The intervention-effectiveness factor is a **visible scenario assumption**, not a predicted probability of failure or a guaranteed ROI. The current implementation uses a configurable budget quantum (default €5k), so the optimization is exact at that discretization level rather than at single-euro precision.

The scenario page reports:

- known mandatory cost;
- remaining discretionary budget;
- optimized discretionary portfolio;
- selected cost;
- scenario risk-points reduced;
- cost source for each asset;
- mandatory queue kept outside the trade-off.

## Why this design is defensible

The application follows five principles:

1. **Evidence first.** Missing fields are surfaced, not silently imputed.
2. **Risk ≠ confidence.** A high-risk, low-evidence item means “investigate”, not “the model knows the truth”.
3. **Explainability.** Asset-level drivers are visible rather than hidden behind a black box.
4. **Safety before economics.** Mandatory engineering/compliance actions are not subject to cost-benefit trade-offs.
5. **Scenario planning, not fake prediction.** CAPEX optimization uses explicit assumptions and never claims to forecast failures without validated historical labels.

## Technology stack

- **Python**
- **Streamlit**
- **Pandas**
- **NumPy**
- **Plotly**
- **OpenPyXL**
- **ReportLab**
- **Pytest**
- **GitHub Actions**

## Repository structure

```text
industrial-maintenance-dashboard/
├── Accueil.py                   # Streamlit entry point
├── utils.py                     # Shared ingestion + engineering utilities
├── decision_engine.py           # Explainable risk + CAPEX optimization core
├── Capex pont Roadmap.xlsx      # Existing fleet workbook used by the original app
├── requirements.txt
├── README.md
├── .github/workflows/ci.yml     # Python 3.11 CI
├── tests/
│   ├── test_utils.py
│   └── test_decision_engine.py
└── pages/
    ├── 1_Vue_densemble.py       # Fleet overview
    ├── 2_Priorisation.py        # Existing prioritization
    ├── 3_Fiche_Pont.py          # Individual crane view
    ├── 4_Calculateur_IFm.py     # Engineering calculator
    ├── 5_Methodologie.py        # Existing assessment methodology
    └── 6_Decision_Engine.py     # Risk, evidence, and CAPEX scenario cockpit
```

## Running locally

```bash
git clone https://github.com/hassanattout/industrial-maintenance-dashboard.git
cd industrial-maintenance-dashboard
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
streamlit run Accueil.py
```

On Windows:

```bash
.venv\Scripts\activate
```

Then upload the fleet workbook from the application home page.

## Input validation

The dashboard accepts `.xlsx` workbooks up to 20 MB. It prefers a sheet named `Ponts`, reads the column header from row 10, and checks that the normalized equipment, country, site, age, and EVS-status fields are present. Invalid files are rejected with a clear message instead of producing partial calculations.

## Automated checks

GitHub Actions runs the test suite on Python 3.11 for every pull request and every push to `main`.

```bash
python -m compileall -q Accueil.py utils.py decision_engine.py pages tests
pytest -q
```

Tests cover input validation, engineering calculation edge cases, bounded risk scores, evidence coverage, cost provenance, mandatory-cost reservation, optimization constraints, and data-quality reporting.

## How I would validate this before operational use

This portfolio implementation is intentionally not presented as production-certified. Before using the decision engine to drive real maintenance or CAPEX decisions, I would:

1. validate the canonical schema with maintenance and plant engineers;
2. calibrate weights using workshops plus retrospective cases;
3. define authoritative sources for inspection, work-order, downtime, production-criticality, and cost data;
4. back-test prioritization against known historical interventions and incidents;
5. perform sensitivity analysis on weights and intervention-effectiveness assumptions;
6. add role-based access, audit logs, data lineage, and controlled model/version releases;
7. integrate with CMMS/ERP APIs instead of relying only on workbook uploads;
8. obtain formal engineering approval for any rule that could affect physical operations.

## Why this project matters

The project demonstrates the full path from industrial reality to software-supported decisions:

```text
fragmented operational data
        ↓
validation + normalization
        ↓
engineering evidence model
        ↓
explainable asset prioritization
        ↓
mandatory constraints
        ↓
budget-constrained action scenario
        ↓
asset-level rationale for technical users
```

The objective is not to make the most complex model possible. It is to make the **decision process more structured, auditable, and useful to engineers**.

## Author

**Hassan Attout**  
Mechanical Engineering, Sorbonne University  
Industrial Project Engineering experience, Renault Group
