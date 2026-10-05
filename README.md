# AERIS-X — AI-Enabled Fleet Readiness & Predictive Maintenance Platform

> **SIH26249 — Air Power: Predictive Maintenance & Fleet Availability**  
> **Ministry of Defence, Government of India**  
> *Tagline: From Aircraft Health to Fleet Readiness.*  
> *USP: Do not merely predict failure. Predict, explain, and optimize the maintenance decision that maximizes fleet availability.*

> [!IMPORTANT]
> **SYNTHETIC DEMONSTRATION DATA — NOT REAL AIRCRAFT PERFORMANCE**  
> This platform operates strictly on synthetic telemetry, simulated physics-based degradation models, and air-gapped algorithms. No real-world defence or aircraft telemetry is stored or utilized.

---

## Architecture Overview

```
Telemetry Stream (Simulated 30 Aircraft)
       │
       ▼
Data Quality Engine (Missing, Range, Drift, Sensor Health)
       │
       ▼
Hybrid Diagnostics & Prognostics
  ├── Isolation Forest (Unsupervised Anomaly Detection)
  ├── XGBoost Classifier + Logistic Regression (Failure Probability next 72h)
  ├── XGBoost Regressor (Remaining Useful Life - RUL)
  └── SHAP Explainer (Ranked Feature Contributions & Plain English Evidence)
       │
       ▼
Prescriptive Decision Engine
  ├── Maintenance Action Recommendation Rules
  ├── Multi-Resource Feasibility Engine (Spares, Techs, Bays, Horizon)
  └── Google OR-Tools CP-SAT Scheduler (Fleet Availability Maximization)
       │
       ▼
Readiness & What-If Simulation
  ├── Real-time What-If Scenarios (Delay, Tech & Spare Constraints)
  └── Reactive vs. Predictive Fleet Availability Delta Comparison
       │
       ▼
Human-in-the-Loop Cockpit Interface
  └── Approve / Modify / Reject Work Orders → Audit Log & Continuous Evaluation
```

---

## Execution Status & Phase Gates

| Phase | Description | Gate Requirement | Status |
|---|---|---|---|
| **Phase 1** | Foundation & Architecture | Docker Compose, env config, structured logging, error handling, `/ping` 200 | **PASSED** |
| **Phase 2** | Database & Migrations | SQLAlchemy 2.0 async models, Alembic migrations, indexes, constraints | **PASSED** |
| **Phase 3** | Auth & RBAC | JWT access/refresh, 6-role RBAC, audit trail middleware, seeded users | *Pending* |
| **Phase 4** | Synthetic Data Engine | 30 aircraft, 8 sensors, 90-day degradation, seed under 90s (SEED=42) | *Pending* |
| **Phase 5** | Data Quality & Health | 0-100 quality scoring, transparent weighted health formula | *Pending* |
| **Phase 6** | ML Services & SHAP | IsolationForest, XGBoost failure/RUL, top-5 SHAP explanations | *Pending* |
| **Phase 7** | Recommendation & CP-SAT | Action rules, feasibility, OR-Tools optimizer, what-if simulator | *Pending* |
| **Phase 8** | Monitoring & Realtime | Telemetry WebSocket `/ws/telemetry`, alert lifecycle, outcome recording | *Pending* |
| **Phase 9** | Full API Surface | All `/api/v1` endpoints with Pydantic v2 schemas and validation | *Pending* |
| **Phase 10** | Cockpit Design System | Aviation UI, `#0A1424` navy palette, arc gauges, instrument panels | *Pending* |
| **Phase 11** | Core Frontend Screens | 12 interactive screens including Command, Digital Twin, Gantt, Sim | *Pending* |
| **Phase 12** | Client Integration & E2E | Typed API client, TanStack Query, Zustand, Playwright smoke | *Pending* |

---

## Phase 1 Deliverables

- **Structured Configuration:** `app/core/config.py` using `pydantic-settings` with environment overrides.
- **Unified Error Handling:** `app/core/errors.py` with custom hierarchy mapping to `{error: {code, message, details}}`.
- **Structured Logging:** `app/core/logging.py` formatted with timestamps, module names, and log-levels.
- **FastAPI Core:** `app/main.py` with CORS, lifespan handlers, and `/docs` interactive OpenAPI interface.
- **Health & Annunciators:** `app/api/v1/health.py` exposing `/ping` and `/status` for live frontend system indicators.
- **Automated Tests:** `tests/test_phase1_foundation.py` covering docs, endpoints, and error handling.
