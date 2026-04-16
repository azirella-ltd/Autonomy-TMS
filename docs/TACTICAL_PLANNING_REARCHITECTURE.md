# TMS Tactical Planning Re-Architecture

**Status:** Design proposal, not yet implemented.
**Parent context:** This document mirrors the SCP-side design conversation that produced [Path C: GraphSAGE-first constrained planning]. Read for the TMS team working on acer-nitro.
**Date:** 2026-04-16
**Sister document:** SCP-side decisions are in `/home/trevor/Documents/Autonomy-SCP` conversation — same architectural shape, different domain.

---

## 1. Why this document exists

SCP's tactical planning layer is honestly labelled "unconstrained MRP" today, with advisory tGNN directives sitting on top. The SCP team committed to Path C: evolve the tactical GraphSAGE layer into the primary constrained planner, with two named unconstrained reference views (demand potential, supply explosion) feeding it.

TMS needs the same re-architecture, in its own domain. This document captures:
- What TMS has today (audit).
- What the target architecture looks like, by analogy with SCP.
- What TMS-specific differences matter.
- Data gaps that must be closed before a constrained solver is useful.
- Implementation sequencing.

## 2. The architectural pattern (both products)

Three named plans, in a pipeline, not four agents negotiating:

| Plan | Question answered | Owner | Constrained by |
|---|---|---|---|
| **Demand Potential** | What could we sell / ship if supply were free? | Demand Planner agent | nothing |
| **Unconstrained Supply / Movement Plan** | What would we need to produce / move if capacity and inventory were free? | Supply Planner agent (SCP) / Movement Planner agent (TMS) | nothing |
| **Constrained Balanced Plan** | What *will* we do, given BSC trade-off? | **Integrated Balancer** (supervisory) | capacity + inventory + cost + service-level + BSC weights |

RCCP (SCP) / Capacity Gap Analyzer (TMS) is an **advisory peer**, not a replanner. It reads all three plans, identifies persistent bottlenecks, and proposes envelope changes to Strategic.

### Why three unconstrained views, not one

Different stakeholders need different "ideal world" numbers to negotiate against:
- Sales/commercial care about demand potential.
- Operations care about unconstrained movement plan.
- S&OP / exec care about the balanced commit.

Collapsing these into one view strips stakeholders of their reconciliation artefacts and makes the Balancer a black box nobody believes.

### Demand decomposition (applies to both products)

Demand Planner is ONE agent with multiple authored inputs:

```
Demand Planner
├── Baseline Sensing (ML forecast)
├── Lifecycle Overlay (NPI / EOL — authored by LIFECYCLE_MANAGER)
├── Shaping Overlay (promos, price, allocation — authored by DEMAND_SHAPING_MANAGER)
└── Consensus Reconciliation (baseline + sales + marketing + finance + customer, by CONSENSUS_PLANNER)
      → Demand Potential (unconstrained by supply)
```

For TMS the overlays are different substance (see §4) but the structural pattern is identical.

## 3. TMS current state — audit findings

### 3.1 Planning layer

**There is no MRP-equivalent in TMS today.** There is no algorithm that explodes shipments into a load plan. Transportation plans are produced **post-hoc** from TRM decisions:

- `tms_provisioning_adapter.py:75–125` → `adapt_transportation_plan()` sums pending shipments, groups them by already-assigned `load_id`, inserts `transportation_plan` + `transportation_plan_item` rows with `optimization_method='AGENT'`.
- Load building is a **TRM heuristic** (`dispatch.py _compute_load_build`). No bin packing, no VRP, no consolidation-window economics, no dwell-time reasoning.
- Carrier selection is a waterfall heuristic in `freight_procurement` TRM.

**Consequence:** TMS doesn't even have an "unconstrained reference" plan. It has decisions, which become the plan by virtue of being recorded.

### 3.2 Tactical tGNN layer

TMS shares the SCP tactical GraphSAGE stack (training service + coordinator live in shared code):

| tGNN | State |
|---|---|
| supply_planning_tgnn | Real, trained per-config, ~24K params |
| inventory_optimization_tgnn | Real, trained per-config, ~30K params |
| capacity_rccp_tgnn | Real, trained per-config, ~25K params |
| site_tgnn | Real, intra-site coordination |
| demand_planning_tgnn | **Removed April 2026** — demand handled analytically via LightGBM features |

- `tactical_hive_coordinator.py` runs 2-iteration lateral context exchange across supply/inventory/capacity tGNNs.
- Outputs are **advisory directives** written to `gnn_directive_reviews` (status=PROPOSED). Never auto-applied.
- **Not scheduled in the cascade.** Called on-demand via `GNNOrchestrationService`.
- No TMS-specific tGNN training data pipeline yet — supply/inventory/capacity semantics are SCP-flavoured. For TMS they need to learn transport-domain semantics (lanes, carriers, equipment pools, dock windows), which means TMS-specific training corpora.

### 3.3 11 TMS agents

All 11 exist with full capability declarations in `tms_agent_capabilities.py`:

| Agent | File | Phase | Decision table |
|---|---|---|---|
| capacity_promise | tms_agent_capabilities.py:43 | SENSE | powell_capacity_promise_decisions |
| shipment_tracking | :64 | SENSE | powell_shipment_tracking_decisions |
| demand_sensing | :91 | SENSE | powell_demand_sensing_decisions |
| capacity_buffer | :115 | ASSESS | powell_capacity_buffer_decisions |
| exception_management | :138 | ASSESS | powell_exception_decisions |
| freight_procurement | :165 | ACQUIRE | powell_freight_procurement_decisions |
| broker_routing | :190 | ACQUIRE | powell_broker_routing_decisions |
| dock_scheduling | :214 | PROTECT | powell_dock_scheduling_decisions |
| load_build | :241 | BUILD | powell_load_build_decisions |
| intermodal_transfer | :265 | BUILD | powell_intermodal_transfer_decisions |
| equipment_reposition | :290 | REFLECT | powell_equipment_reposition_decisions |

All 11 write both to per-agent `powell_*_decisions` tables **and** to the canonical `agent_decisions` table (TMS did this correctly; SCP still owes a back-fill). DecisionType enum values for the 11 agents are in PostgreSQL but were backfilled into the shared `azirella_data_model.governance.DecisionType` Python enum on 2026-04-15.

### 3.4 Constrained solver

**There is none.** Zero imports of `ortools`, `pulp`, `pyomo`, `gurobipy`, `cplex`. Some comments in `planning_cascade/allocation_agent.py` reference "would use LP solver" — aspirational, not real.

### 3.5 Data readiness

| Category | Table | Schema? | Populated? |
|---|---|---|---|
| Carrier capacity / fleet | carrier, carrier_lane, equipment | ✓ | Demo-only |
| Driver hours / HOS | — | ✗ | Missing entirely |
| Dock capacity / appointments | appointment, dock_door | ✓ | Schema only |
| Lane capacity windows | shipping_forecast, capacity_target | ✓ | Schema exists, no enforced windows |
| Carrier contracts / rate cards | freight_rate, rate_card | ✓ | Schema exists, no commit volumes |
| Service-level tiers per customer | — | ✗ | Implicit in buffer_policy only |
| Cost params (linehaul, detention, accessorial) per tenant | partial | ⚠ | Embedded in carrier_scorecard JSON |
| BSC weights | — | ✗ | No persistent config |

## 4. TMS-specific mapping of the three-plan architecture

Structure is identical to SCP. Substance is different.

### 4.1 Demand Potential (TMS)

**Baseline sensing**: shipment volume forecast by lane/origin/destination/service-class.
**Lifecycle overlay**: new-lane openings, DC closures, seasonal programme starts/ends, customer onboarding/offboarding ramps.
**Shaping overlay**: mode-shift incentives (rail vs truck vs LTL), consolidation policy changes, pricing actions on accessorial charges, customer appointment policy.
**Consensus**: reconcile baseline with sales commitments, customer-provided tender forecasts, carrier capacity commitments (what they've promised us), internal capacity forecasts.

Output: **Unconstrained shipment demand** — what we'd ship per lane per period if carrier capacity and internal fleet were unlimited.

### 4.2 Unconstrained Movement Plan (TMS)

TMS equivalent of SCP's unconstrained MRP. Takes unconstrained shipment demand and produces an idealised movement plan:
- Optimal consolidation (group shipments into ideal loads) **without** carrier capacity limits
- Optimal mode selection (truck / rail / intermodal / parcel) **without** carrier availability limits
- Optimal routing (stops, sequence) **without** driver HOS / equipment constraints
- Optimal dock scheduling **without** dock slot limits

This doesn't exist yet. It is the TMS-specific build.

Output: **Unconstrained movement plan** — load-level ideal dispatches, mode-split ideal, routing ideal.

### 4.3 Constrained Balanced Plan (TMS)

Integrated Balancer takes both unconstrained views plus the real constraint envelope:
- Carrier capacity commitments (contracted slots, spot availability)
- Equipment pool (fleet, pooled equipment, repositioning cost)
- Driver HOS (once we have the table)
- Dock slot availability
- Service-level commitments per customer
- Cost structure (linehaul rates, detention cost, accessorial, mode cost delta)
- BSC weights (Financial / Customer / Internal / Learning)

Produces the **committed movement plan** — the actual load build, carrier assignment, mode, routing, dock slots. This is what Execution-layer TRMs consume.

### 4.4 Capacity Gap Analyzer (TMS's RCCP)

Reads Demand Potential, Unconstrained Movement, Constrained Committed. Identifies:
- Persistent carrier-capacity shortfalls on specific lanes → propose new contracts / spot RFP / mode shift
- Persistent dock congestion at specific sites → propose dock expansion / appointment policy change
- Persistent equipment imbalance → propose permanent repositioning / fleet size change
- Persistent mode-optimal-vs-available gap → propose strategic mode-mix change

Proposals go to Strategic (S&OP) for evaluation. Do **not** replan autonomously.

## 5. Path C for TMS — GraphSAGE-first constrained planning

SCP chose Path C. TMS follows the same path. Training data and domain adaptation are TMS-specific.

### 5.1 Sequencing

**Phase 0 — Honest labelling (1 week, low risk): ✅ COMPLETE (2026-04-16)**
1. ✅ `transportation_plan.plan_version` widened to `VARCHAR(30)`, default flipped to
   `'constrained_live'`. Alembic migration `20260416_plan_version`. Canonical enum
   lives in `app.models.tms_planning.PlanVersion`.
2. ✅ Existing `plan_version='live'` rows back-filled to `'constrained_live'`
   (migration's `upgrade()` does the UPDATE).
3. ✅ UI toggle shipped: `/planning/transportation-plan` page has a 4-button toggle
   showing per-version counts. Honesty banner reads the
   `PLANNING_IS_CONSTRAINED` flag — currently `False`, flips to green
   `CheckCircle` when Phase 3 lands.
4. ✅ Frontend banner + `PLANNING_IS_CONSTRAINED = False` constant in
   `backend/app/models/tms_planning.py`. Endpoint returns the flag so any
   downstream service can read the honest state.

**Phase 1 — Unconstrained movement plan generator (2-3 months):**
5. Build TMS-equivalent of `NetRequirementsCalculator`: `UnconstrainedMovementPlanner`. Lives in `backend/app/services/tms_planning/`.
6. Input: committed-demand view of shipments (from Demand Planner Consensus output).
7. Algorithm: optimal consolidation (relaxed bin-pack), optimal mode split (rate-card only, no capacity), optimal routing (distance/time only).
8. Output: rows into `transportation_plan` with `plan_version='unconstrained_reference'`.
9. Scheduled daily alongside SCP's 5am cascade.

**Phase 2 — Tactical tGNN retraining for TMS domain (3-4 months):**
10. Build TMS-specific training corpora for supply_planning_tgnn, inventory_optimization_tgnn, capacity_rccp_tgnn. Replace SCP semantics (product-site-supplier) with TMS semantics (lane-carrier-equipment).
11. Specifically: supply_planning_tgnn → "movement_planning_tgnn" (lane throughput, carrier commit, consolidation ratio); capacity_rccp_tgnn → lane & dock capacity gap per period.
12. Train per-tenant on real shipment history + synthetic cold-start.
13. Keep 2-iteration lateral convergence from SCP's coordinator — reuse the infrastructure.

**Phase 3 — Constrained plan from tGNN (4-6 months):**
14. Upgrade tactical tGNNs from "signal generators" to "plan producers." Add an output head that emits constrained load-build decisions per lane-period.
15. Wire into cascade: Unconstrained Movement Planner → constrained tGNN → write `plan_version='constrained_live'`.
16. Switch TMS Execution TRMs (all 11) to read `constrained_live` instead of the current per-agent ad-hoc decisions.

**Phase 4 — Capacity Gap Analyzer (2 months, can overlap Phase 3):**
17. Replace `rccp_service.py` references with TMS-appropriate `CapacityGapAnalyzer` that consumes the three plans and writes strategic proposals.
18. Wire into Strategic (S&OP) UI: "network change proposals" inbox for exec review.

### 5.2 Data collection must run in parallel

Phases 2 and 3 are blocked on data. Start data collection on day 1:

| Data | Priority | Source |
|---|---|---|
| Driver HOS calendar per carrier | High — needed Phase 3 | Carrier onboarding form / FMCSA integration |
| Dock appointment slot capacity per site | High — needed Phase 3 | WMS integration / site config |
| Carrier committed capacity per lane per period | High — needed Phase 3 | Contract extraction / carrier portal |
| Rate-card with commit volumes (not just unit rates) | High — needed Phase 3 | Contract extraction |
| Service-level tier per customer | Medium — needed Phase 3 | CRM / sales system |
| Cost structure (detention, accessorial, mode delta) per tenant | Medium — needed Phase 3 | Finance / GL integration |
| BSC weights per tenant | Low — needed Phase 4 | Strategic config, admin UI |

### 5.3 Naming / terminology alignment

Keep these consistent between SCP and TMS:

| Concept | Name to use |
|---|---|
| The supervisory tactical agent | **Integrated Balancer** |
| Capacity change proposer | **Capacity Gap Analyzer** (not "RCCP" in new code — RCCP is the legacy SCP name, kept as alias) |
| Plan statuses | `unconstrained_reference`, `constrained_live`, `erp_baseline`, `decision_action` |
| Demand agent | **Demand Planner** (one agent, four sub-components: Baseline / Lifecycle / Shaping / Consensus) |

## 6. What does NOT change

- The 11 TMS Execution-layer TRMs keep their current phase assignments (SENSE / ASSESS / ACQUIRE / PROTECT / BUILD / REFLECT).
- The AIIO model (ACTIONED / INFORMED / INSPECTED / OVERRIDDEN) is unchanged.
- Provisioning pipeline structure (the shared 19-step cascade) unchanged; TMS-specific adapters at steps 9, 10, 17 stay.
- Canonical `agent_decisions` table is unchanged; DecisionType enum values already landed 2026-04-15.
- Decision Stream / worklist pages are unchanged — they already read `agent_decisions`.

## 7. Open questions for TMS team

Flag back to the SCP conversation when you have answers:

1. **Driver HOS**: is there any existing extraction path from ELD providers (Samsara, Motive, Geotab), or does this need a new integration?
2. **Carrier committed capacity**: do any current TMS tenants have machine-readable contracts, or is this a manual data-entry job per tenant?
3. **Dock appointment capacity**: does any WMS integration already provide this, or do we need site-admin config UI?
4. **BSC weights**: do TMS tenants have an existing BSC framework, or is this new to them? Shared config with SCP tenant, or per-product?
5. **Training corpus**: is there enough real shipment history per tenant to train TMS-domain tGNNs without extensive synthetic augmentation? For Infor TMS demo specifically — what's the shipment volume / horizon?
6. **Demand Planner sub-components**: do TMS tenants distinguish the four roles (baseline analyst, lifecycle manager, shaping manager, consensus planner) today, or are these collapsed? If collapsed, do we build the UI for all four roles anyway, mirroring SCP?

## 8. Cross-product coordination

- `azirella_data_model.governance.DecisionType` is shared. If Phase 1 introduces new decision types (e.g., `UNCONSTRAINED_MOVEMENT`), coordinate with SCP before landing.
- `tactical_hive_coordinator.py` is shared code. Phase 2's TMS-specific training should NOT fork the coordinator; extend it with domain config instead.
- `plan_version` enum values should match across both products for consistent UI.
- BSC weight schema, if introduced, should live in shared `azirella_data_model` — not SCP-private or TMS-private.

## 9. Summary

TMS is further from constrained planning than SCP, because SCP at least has unconstrained MRP; TMS has nothing but post-hoc decision records. But the architectural target is identical: three named plans (Demand Potential → Unconstrained Movement → Constrained Committed) produced by a Demand Planner + Movement Planner + Integrated Balancer + Capacity Gap Analyzer, with Execution TRMs reading the constrained commit.

Phase 0 (honest labelling) is 1 week. Phase 1 (unconstrained generator) is the first real build. Phases 2-3 require TMS-domain tactical tGNN training and the data collection in §5.2 must start in parallel on day 1.

---

**End of document.** For SCP-side equivalent decisions, see conversation history in `/home/trevor/Documents/Autonomy-SCP`.
