# Provisioning Stepper — Powell Cascade Warm-Start Pipeline

## Overview

The provisioning stepper bootstraps all AI layers for a supply chain config before they can receive directives or make decisions. It replaces the simple warm-start button with a full 14-step Powell Cascade pipeline with dependency tracking.

Each supply chain config has one `config_provisioning_status` row tracking the state of all 14 steps. Steps execute in dependency order — a step cannot run until all its prerequisites are complete.

**Why provisioning matters**: When a user issues a directive via [Azirella](TALK_TO_ME.md), the directive is routed to a specific Powell layer. If that layer hasn't been provisioned, the directive has nowhere to go:

| Directive Target | Required Steps |
|-----------------|----------------|
| Layer 4 (S&OP GraphSAGE) | warm_start, sop_graphsage |
| Layer 2 (Execution tGNN) | warm_start through inventory_tgnn |
| Layer 1.5 (Site tGNN) | warm_start through site_tgnn |
| Layer 1 (Individual TRM) | warm_start through trm_training |

## Steps and Dependencies

The pipeline is organized into four tiers:

### Tier 1 — Foundation

| # | Step | Label | Depends On | What It Does |
|---|------|-------|------------|--------------|
| 1 | `warm_start` | Historical Demand Simulation | — | Generates SimPy simulation data from the SC config's topology. Creates the historical demand/supply patterns that all subsequent training steps consume. |

### Tier 2 — Strategic Layer

| # | Step | Label | Depends On | What It Does |
|---|------|-------|------------|--------------|
| 2 | `sop_graphsage` | Strategic Network Planning Agent | warm_start | Trains the S&OP GraphSAGE model on the network topology. Produces criticality scores, concentration risk, resilience metrics, and safety stock multipliers per site. |
| 3 | `cfa_optimization` | Policy Parameter Optimization | sop_graphsage | Runs Differential Evolution over Monte Carlo scenarios to find optimal policy parameters θ (order-up-to levels, reorder points, safety stock multipliers). |
| 4 | `lgbm_forecast` | Demand Forecasting | cfa_optimization | Trains LightGBM demand forecasting model from historical data. Produces baseline forecasts that feed into the tGNN agents. |

### Tier 3 — Operational Layer

| # | Step | Label | Depends On | What It Does |
|---|------|-------|------------|--------------|
| 5 | `demand_tgnn` | Demand Planning Agent | lgbm_forecast, sop_graphsage | Trains the demand-side temporal GNN from LGBM forecasts and S&OP embeddings. |
| 6 | `supply_tgnn` | Supply Planning Agent | lgbm_forecast, sop_graphsage | Trains the supply-side temporal GNN for allocation and supply coordination. |
| 7 | `inventory_tgnn` | Inventory Optimization Agent | supply_tgnn | Trains the inventory optimization tGNN downstream of supply planning. |
| 8 | `trm_training` | Execution Role Agent Training | demand_tgnn, supply_tgnn, inventory_tgnn | Trains all 11 TRM agents (Phase 1 behavioral cloning). Requires tGNN outputs as context for training data generation. |
| 9 | `supply_plan` | Supply Plan Generation | cfa_optimization, trm_training | Generates the initial supply plan using optimized policy parameters and trained TRMs. Produces PO/TO/MO requests. |
| 10 | `rccp_validation` | Rough-Cut Capacity Validation | supply_plan | Validates the supply plan against rough-cut capacity profiles. Flags capacity violations before activation. |

### Tier 4 — Activation

| # | Step | Label | Depends On | What It Does |
|---|------|-------|------------|--------------|
| 11 | `decision_seed` | Decision Stream Seeding | trm_training | Runs TRM agents against current state to generate initial decisions for the Decision Stream. Gives planners something to review immediately. |
| 12 | `site_tgnn` | Operational Site Agent Training | decision_seed | Trains the Site tGNN (Layer 1.5) from seeded decisions. Learns cross-TRM causal coordination within each site. |
| 13 | `conformal` | Uncertainty Calibration (CP + CDT) | warm_start | Hydrates the ConformalOrchestrator from `PowellBeliefState` (tenant-scoped) and runs batch CDT calibration across all 11 TRM types. See [Conformal Prediction details](#conformal-step-details) below. |
| 14 | `briefing` | Executive Briefing | supply_plan, decision_seed | Generates LLM-synthesized executive strategy briefing from supply plan results and initial decision analysis. |

### Dependency Graph

```
warm_start
├── sop_graphsage
│   └── cfa_optimization
│       ├── lgbm_forecast
│       │   ├── demand_tgnn ──┐
│       │   └── supply_tgnn ──┤
│       │       └── inventory_tgnn
│       │                     └── trm_training
│       │                         ├── supply_plan ── rccp_validation
│       │                         │       └──────────────┐
│       │                         ├── decision_seed ─────┼── briefing
│       │                         │       └── site_tgnn  │
│       └─────────────────────────┘                      │
└── conformal ───────────────────────────────────────────┘
```

## Conformal Step Details

The conformal step (13) performs two operations:

1. **Forecast-level CP hydration**: Loads calibration data from `powell_belief_state` table (filtered by `tenant_id`) into the `ConformalOrchestrator`. Requires ≥10 observations per entity for hydration.

2. **Decision-level CDT batch calibration**: Runs `CDTCalibrationService.calibrate_all()` (tenant-scoped) to calibrate CDT wrappers for all 11 TRM types from historical decision-outcome pairs in `powell_*_decisions` tables. Requires ≥30 pairs per TRM type for full calibration.

After completion, a **CDT Readiness Panel** shows per-TRM calibration status:
- **Calibrated**: ≥30 decision-outcome pairs, CDT wrapper active
- **Partial**: 1-29 pairs, accumulating (auto-calibrates at 30)
- **Uncalibrated**: 0 pairs, using conservative `risk_bound=0.50` (forces escalation)

The Decision Stream page also shows a **CDT Readiness Banner** when not all TRMs are calibrated, explaining that uncalibrated agents use conservative risk bounds which may trigger more escalations.

## Implementation

### Backend

| File | Purpose |
|------|---------|
| `backend/app/services/provisioning_service.py` | 14-step pipeline orchestrator with dependency resolution |
| `backend/app/api/endpoints/provisioning.py` | REST API — status, run, run-all, reset |
| `backend/app/models/user_directive.py` | `ConfigProvisioningStatus` model (STEP_ORDER, STEP_LABELS, STEP_DEPENDENCIES) |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/src/components/supply-chain-config/ProvisioningStepper.jsx` | Stepper modal with tier layout, CDT readiness panel |

### API Endpoints

```
GET  /api/v1/provisioning/status/{config_id}           — Full stepper state
POST /api/v1/provisioning/run/{config_id}/{step_key}   — Run single step
POST /api/v1/provisioning/run-all/{config_id}          — Run all in dependency order
POST /api/v1/provisioning/reset/{config_id}/{step_key} — Reset failed step to pending
```

### Database

**Table: `config_provisioning_status`** (one row per SC config)

Each step has three columns:
- `{step}_status`: pending / running / completed / error
- `{step}_at`: Timestamp of last status change
- `{step}_error`: Error message if status is "error"

### Frontend Features

The `ProvisioningStepper.jsx` modal shows:
- Progress bar (completed / total)
- Per-step status (pending / running / completed / error)
- Dependency warnings (greyed out until prerequisites met)
- Run / Reset / Retry per step
- "Run All" button for one-click provisioning
- CDT Readiness Panel (after conformal step completes)

## Related Documentation

- [Azirella](TALK_TO_ME.md) — Directive capture system that depends on provisioned layers
- [Conformal Prediction Framework Guide](../knowledge/Conformal_Prediction_Framework_Guide.md) — Two-level CP architecture and tenant scoping
- [POWELL_APPROACH.md](POWELL_APPROACH.md) — Full Powell SDAM framework including CDT calibration pipeline
