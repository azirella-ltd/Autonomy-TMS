# Plan separation (TMS — strict)

Every `transportation_plan`-style row carries a `plan_version`. Never mix.

| plan_version | Purpose | Who creates |
|---|---|---|
| `live` | Plan of Record — active transportation plan | Transportation Planning Agent (conformal P50) |
| `tms_baseline` | Current TMS plan — comparison baseline | Extracted from TMS / ERP |
| `decision_action` | User overrides from Decision Stream | Human via AIIO override |
| `unconstrained_reference` | MRP / net-requirements reference | Deterministic planner |
| `constrained_live` | BSC-optimised commit | Integrated Balancer |

## Invariants

- **No Monte Carlo** in transport planning — uncertainty is quantified
  by conformal P10/P90 intervals (lead times, transit variability,
  capacity uncertainty).
- **Digital Twin simulation** is for TRM training, scenario
  exploration, and RL-environment — not plan generation.
- **Scenarios** use separate `config_id` branches.
