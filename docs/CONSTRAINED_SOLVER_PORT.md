# TMS Constrained Solver Port

> **2026-04-16 addendum — FOUNDATIONAL CORRECTION. READ FIRST.**
>
> The LP/MILP solver is **not** Autonomy's tactical planner. The target architecture is **Tier 3 — GraphSAGE trained by reinforcement learning on the digital twin** (AlphaZero / Leela pattern). The LP is a baseline, a safety net, and a bootstrap for new tenants. It is **never** a teacher for the GNN.
>
> This document describes the LP port because LP is Tier 1 / Tier 2 infrastructure for the migration toward Tier 3 — not because LP is the endpoint. Port the LP to give TMS tenants something immediately useful; simultaneously, budget for the twin + RL investment that delivers Tier 3. See [CONSTRAINED_SOLVER_PORT_TIER_3_ADDENDUM.md](CONSTRAINED_SOLVER_PORT_TIER_3_ADDENDUM.md) for the full Tier 3 picture.
>
> Do not design TMS to rest on LP long-term. Do not train a GraphSAGE on LP-generated labels.

**Purpose.** Port SCP's Path C Phase 3 solver work to TMS on acer-nitro. Same architecture, TMS-domain substance. This is a concrete step-by-step derived from the SCP implementation shipped 2026-04-16.

**Reference reading before starting (SCP side):**
- [docs/internal/architecture/CONSTRAINED_SOLVER_DESIGN.md](https://github.com/azirella-ltd/Autonomy-SCP/blob/main/docs/internal/architecture/CONSTRAINED_SOLVER_DESIGN.md) — research, options, cadence/parallelism/likelihood
- [docs/internal/architecture/TACTICAL_PLANNING_REARCHITECTURE.md](https://github.com/azirella-ltd/Autonomy-SCP/blob/main/docs/internal/architecture/TACTICAL_PLANNING_REARCHITECTURE.md) — Path C phase structure
- `backend/app/services/tactical/` on SCP main — the working implementation to mirror

---

## 1. Architectural invariants (shared across both products)

These are settled on the SCP side and should hold on TMS too:

1. **BSC attainment range is [-1, 1], not [0, 1].** Solver needs gradient below baseline. Identical `bsc_attainment.py` formulas.
2. **Three-tier cadence** — Strategic (weekly) / Tactical (daily 5am) / Operational (every 4h, heuristic-only). Heuristics never re-solve the plan.
3. **Chance-constrained with service-level tiers** — solver consumes `demand_Q_alpha` per cell, where alpha comes from `customer_sla_tier` (Platinum P99 → Economy P80). No stochastic programming in the hot path.
4. **`ConstrainedSolver` abstract interface with pluggable backends.** Start with OR-Tools GLOP; Gurobi / cuOpt only when a tenant hits a scale wall.
5. **Every solver must implement `fallback_heuristic()`.** Daily cascade never fails — at worst it gets a heuristic plan flagged as FALLBACK.
6. **Parallelism** — tenant-parallel yes, scenario-parallel yes; pool of 2-3 workers; staggered schedule beats naive simultaneity.
7. **Cross-product enum coordination** — new decision types or plan statuses go through `CONSUMER_ADOPTION_LOG.md` on Autonomy-Core.

## 2. Domain mapping: SCP → TMS substance

| SCP concept | TMS equivalent |
|---|---|
| `supply_plan` (plan_version, is_constrained, produced_by) | `transportation_plan` (already has plan_version + is_constrained from acer-nitro Phase 0) |
| `NetRequirementsCalculator` → unconstrained_reference | `UnconstrainedMovementPlanner` → unconstrained_reference (per §5 Phase 1 of the TMS design doc) |
| `DemandCell(product_id, site_id, period, demand_quantile)` | `ShipmentCell(origin_site, dest_site, equipment_type, period, volume_quantile)` — or by lane: `LaneCell(lane_id, period, volume_quantile)` |
| `CapacityCell(site_id, period, capacity_units)` | Two capacity axes, both needed: `CarrierLaneCapacity(lane, period, committed_weight, committed_volume)` and `DockSlotCapacity(site, period, appointments_available)` |
| `site_work_center` (machines × hours × efficiency) | `carrier_lane` committed capacity + `dock_door` slot capacity + `equipment` pool concurrency |
| `product_cost_params` (holding, stockout, setup, expedite) | `lane_cost_params` (linehaul $/mile, fuel surcharge, detention, accessorial) + `dock_cost` (appointment penalty) + `equipment_reposition_cost` |
| `customer_sla_tier` (alpha per customer-product) | `customer_sla_tier` — same table shape works; alpha per customer or per shipment service class |
| `CapacityGapAnalyzer` → `strategic_proposal` | `CapacityGapAnalyzer` (TMS) → `strategic_proposal` (tenant-scoped, same table shape) |

Six strategic-proposal kinds on SCP map to TMS equivalents:
- `CAPACITY_EXPAND` → more overtime / spot-capacity / lane re-contract
- `CAPACITY_CONTRACT` → de-commit underused lanes
- `RESOURCE_REPAIR` → tractor/trailer/dock down
- `SUPPLIER_DIVERSIFY` → carrier concentration risk
- `DEMAND_SHAPE` → mode-shift incentives, appointment policy changes, consolidation
- `LANE_REBALANCE` → intra-network equipment / volume shift

## 3. What to port file-by-file

Everything under `backend/app/services/tactical/` on SCP has a TMS cousin.

### 3.1 `plan_versions.py` (trivial)

Already exists on TMS from Phase 0 per the acer-nitro handoff. Verify `PlanVersion` enum has the four values (UNCONSTRAINED_REFERENCE, CONSTRAINED_LIVE, ERP_BASELINE, DECISION_ACTION).

### 3.2 `bsc_attainment.py` (copy wholesale)

**Port as-is.** Same math, same table names. Migration `20260416_h_bsc_goal_attainment` creates `tenant_bsc_metric_goals` — that table is tenant-scoped (not product-family-scoped), so it's shared across SCP and TMS. Two options:

- **Option A**: Move `tenant_bsc_weights` + `tenant_bsc_metric_goals` to `azirella-data-model` canonical (Autonomy-Core). Both products point at the same table. Cleaner, avoids drift.
- **Option B**: Each product has its own copy. Simpler, risks divergence.

Recommend **Option A**. Add the two tables to `azirella_data_model.governance` and bump pin on both products. File a `CONSUMER_ADOPTION_LOG.md` entry.

Default seed metrics for TMS differ — recommend:
- FINANCIAL: `cost_per_mile_ratio` (lower, baseline = contract rate × 1.10, target = contract rate × 0.95)
- CUSTOMER: `on_time_delivery` (higher, baseline 0.90, target 0.98)
- INTERNAL: `trailer_utilisation` (higher, baseline 0.70, target 0.90)
- LEARNING: `plan_override_rate` (lower, baseline 0.20, target 0.05)

### 3.3 `constrained_solver.py` (port with TMS domain variables)

SCP uses: `supply[product, site, period]`, `shortfall[...]`, `inv[...]`. TMS uses:
- `load_volume[lane, equipment_type, period]` — volume (or weight) assigned to each lane-equipment-period combination
- `load_count[lane, equipment_type, period]` — integer count of loads (may stay continuous in LP v0, integer in MILP v1)
- `shortfall[lane, period]` — demand unassigned (soft SLA slack)
- `reposition[from_site, to_site, period]` — empty equipment movement (secondary cost)

**Constraints:**
- SLA: load_volume + shortfall ≥ demand_quantile per lane-period
- Carrier capacity: sum over lanes served by carrier c in period t of load ≤ committed capacity
- Dock capacity: sum over lanes arriving at site s in period t of load_count ≤ dock_slots
- Equipment balance: equipment entering site s = equipment leaving + net reposition (flow conservation)

**Objective:**
- + w_customer × fill_rate  (minus shortfall penalty)
- − w_financial × linehaul_cost × load_volume
- − w_financial × detention_cost × shortfall (proxy)
- − w_internal × reposition_cost × reposition_volume
- − w_learning × mode_deviation_penalty (where actual mode ≠ preferred mode)

### 3.4 `constrained_plan_generator.py` (same shape, different queries)

The SCP class has two methods: `generate()` (orchestrator) and `_generate_via_solver()` (gathers inputs, calls solver, writes rows). Port the orchestrator structure. Change the queries:
- Read from `transportation_plan WHERE plan_version='unconstrained_reference'` instead of `supply_plan`
- Read capacity from `carrier_lane` + `dock_door` + `equipment` instead of `site_work_center`
- Write back to `transportation_plan` with `plan_version='constrained_live'`, `is_constrained=True`, `produced_by='constrained_solver_glop_v0_tms'`

### 3.5 `capacity_gap_analyzer.py` (aggregate by lane, not by site)

SCP aggregates gap per site × period. TMS aggregates per **lane × period**. Persistent gap on a lane for N consecutive weeks → `CAPACITY_EXPAND` proposal recommending a spot RFP or contract re-negotiation for that lane.

Additional TMS proposal trigger not present in SCP: **carrier concentration risk** (`SUPPLIER_DIVERSIFY`). If one carrier handles >threshold% of lanes for a tenant, propose diversification. Compute from `freight_procurement_decisions` history plus `carrier_lane` table.

### 3.6 `synthetic_capacity_seeder.py` (port with TMS multipliers)

SCP formula: `capacity/day = peak_week_qty / working_days × headroom`.

TMS has **three axes** to seed:
1. **Carrier-lane capacity** — peak week's committed volume on a lane × headroom
2. **Dock slots per site per day** — peak week's appointments arriving at site / working_days × headroom
3. **Equipment pool** — peak concurrent equipment in use per site × headroom (round up)

Same regional calendar (`REGIONS` dict) works. Same idempotency pattern (delete rows with `source='synthetic_from_plan'`, re-insert).

Endpoint: `POST /api/v1/tactical/capacity/synthesize-tms/{config_id}?country_code=US&headroom=1.20`.

### 3.7 `strategic_proposal` table (migrate from Autonomy-Core)

SCP migration `20260416_i_strategic_proposals` creates the table. Two options again:

- **Option A**: Move `strategic_proposal` to canonical Autonomy-Core (both products read/write shared table — but tenant_id is the isolation key, so no cross-tenant concerns).
- **Option B**: TMS has its own `strategic_proposal` table in TMS DB.

Recommend **Option A**. The proposal schema is product-agnostic; a TMS-specific proposal just has `kind='LANE_REBALANCE'` instead of `CAPACITY_EXPAND`. Exec-level S&OP readers benefit from one unified queue across both products.

If Option A, add a `product_scope` column (`SCP` | `TMS` | `BOTH`) so UI can filter. Put this in the Autonomy-Core migration.

### 3.8 Admin UI pages (port UI shells)

Two SCP admin pages at `/admin/bsc-weights` and `/admin/product-cost-params`. Port the BSC page as-is (it reads/writes tenant-level weights, shared if Option A above). For cost params, build TMS-specific page `/admin/lane-cost-params` reading lane-keyed costs instead of product-keyed.

Gap analysis component: SCP's [`frontend/src/components/planning/GapAnalysisPanel.jsx`](https://github.com/azirella-ltd/Autonomy-SCP/blob/main/frontend/src/components/planning/GapAnalysisPanel.jsx) — three variants, drop-into-anywhere. Port to TMS's `frontend/src/components/planning/MovementGapPanel.jsx` reading from `/api/v1/transportation-plan/gap-analysis/{config_id}`. Same three variants, same prop contract.

## 4. Sequencing on acer-nitro

Roughly follows SCP's 9-11 week build plan but can be compressed if you reuse canonical pieces.

**Week 1 — canonical sync**
- Decide Option A vs B for `tenant_bsc_*` and `strategic_proposal`. Recommend A.
- If A: add tables to `azirella-data-model.governance`. Bump pin on both products.
- Add TMS-specific migrations that alembic-no-op if tables already exist (idempotent).

**Week 2 — solver interface + fallback**
- Port `constrained_solver.py` with TMS domain dataclasses (ShipmentCell, LaneCapacity, etc.).
- Fallback heuristic: priority-based lane consumption (Platinum SLA first).
- Unit test: 2-lane 2-period problem, verify fallback clips to capacity.

**Weeks 3-4 — LP v0 (no integers)**
- Implement `GlopLpSolver.solve()` with continuous load_volume variables.
- SLA soft constraint + carrier capacity + dock capacity.
- Skip equipment flow for v0 (add in v2).
- Objective: fill rate reward − linehaul cost.
- Smoke test on a minimal synthetic problem.

**Week 5 — capacity envelope data**
- Port `synthetic_capacity_seeder.py` with the three axes.
- Populate at least Infor TMS demo tenant.

**Week 6 — plan generator wiring**
- Port `constrained_plan_generator.py` to read `transportation_plan` and carrier/dock tables.
- Endpoint `POST /api/v1/tactical/movement-plan/solve/{config_id}`.

**Weeks 7-8 — rolling horizon + multi-period**
- 13 weeks forward horizon, weekly buckets.
- Warmstart from prior solve's solution (OR-Tools basis import).

**Week 9 — scheduler**
- Daily 5am tactical solve wired into APScheduler.
- Event triggers: CRITICAL strategic proposal, demand drift, manual re-plan.
- Debouncer (coalesce triggers within an hour).

**Weeks 10-11 — scenario parallelism + gap analyzer**
- Scenario branch solves.
- Port `capacity_gap_analyzer.py` with lane-level aggregation.
- Port `GapAnalysisPanel.jsx` → `MovementGapPanel.jsx`.

## 5. Gotchas I hit on SCP that TMS will repeat

1. **OR-Tools protobuf conflict.** `ortools==9.11.x` requires `protobuf<5.27`. If TMS pins a newer protobuf (e.g. `protobuf==6.x` like SCP does), use `ortools==9.15.6755` which supports protobuf 6.x.
2. **Force-recreate the container after rebuild.** `docker compose up -d backend` on its own won't replace a healthy container with a new image — use `docker compose up -d --force-recreate backend`.
3. **Canonical model changes require docker cp for local dev iteration.** After editing `azirella-data-model` source on the host, either rebuild the backend image (slow) or `docker cp` the file into the running container's site-packages (fast, ephemeral).
4. **Inventory balance equality bug.** My first LP pass had `inv[t] − inv[t-1] − supply[t] = -demand[t]` which misses the shortfall path. Correct form: `inv[t] − inv[t-1] − supply[t] − shortfall[t] = -demand[t]` (shortfall doesn't consume inventory). Same pattern applies to TMS equipment balance — unserved demand doesn't move equipment.
5. **SLA quantile comes from customer, not from product.** The demand-cell quantile is set by the customer's SLA tier lookup, not by the product. For TMS, it's the shipment's customer or service class.
6. **BSC weights can be NULL for a fresh tenant.** Treat that as defaults (F=0.4, C=0.3, I=0.2, L=0.1), not as an error. Log a warning and continue.

## 6. Verification checklist before shipping each phase

- [ ] LP v0: can solve 100 lanes × 13 weeks in <30 seconds.
- [ ] Fallback: takes <500ms on same-size problem.
- [ ] Infeasibility → FALLBACK, not 500 error.
- [ ] `is_constrained=True` only set when solver returns OPTIMAL or FEASIBLE.
- [ ] Solver name / version tagged in `produced_by` and `source_event_id`.
- [ ] Gap analyzer shows non-zero gap when capacity is binding.
- [ ] Strategic proposals raised for persistent gaps (3+ weeks).
- [ ] Admin UI reads from shared tables if Option A; no drift between SCP and TMS BSC weights for the same tenant.

## 7. When to escalate

Swap OR-Tools for Gurobi or NVIDIA cuOpt **only** when:
- A tenant's daily tactical solve exceeds 10 minutes consistently (GLOP usually handles low-millions-of-variables LPs in seconds).
- A scenario solve blocks the live pool for >30 minutes.
- MILP formulation (lot sizing / setup costs) exceeds OR-Tools CP-SAT's capability.

Until any of those fire, OR-Tools is the right answer.

---

**End of port guide.** Cross-reference with the SCP-side `CONSTRAINED_SOLVER_DESIGN.md` for the research context (Kinaxis journey, competitor matrix, why hybrid wins). The implementation shipped on SCP main at commits from 2026-04-16 — walk through those commit-by-commit to see the SCP equivalent of each step.
