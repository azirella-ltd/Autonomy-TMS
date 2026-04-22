# CapacityPromiseTRM — Design Note

**Status:** design, not built. Author: acer-nitro 2026-04-22. Precedes implementation.

## What it is

`CapacityPromiseTRM` is the TMS SENSE-phase TRM that maps to SCP's `ATPExecutorTRM`
(see [.claude/rules/trm-mapping.md](../../../.claude/rules/trm-mapping.md)).

Its job: given a shipment request, decide whether to *promise* a service
window and lane capacity before committing to it. The promise is the
transportation analog of "Available to Promise" — a commitment with confidence
bounds, not a carrier selection.

**Core substrate already in place:**

- `azirella_data_model.powell.tms.heuristic_library.base.CapacityPromiseState` —
  the input dataclass (lane, requested_date, requested_loads, priority,
  committed/total/buffer capacity, forecast/booked, primary carrier context,
  lane acceptance rate, market tightness, allocation compliance).
- `azirella_data_model.powell.tms.heuristic_library.dispatch._compute_capacity_promise` —
  the deterministic teacher (composite score with 5 weighted factors; priority
  overrides; 0.6 / 0.35 thresholds for ACCEPT / DEFER / REJECT).
- `azirella_data_model.powell.tms.agent_capabilities["capacity_promise"]` —
  declares `decision_table="powell_capacity_promise_decisions"` (not yet created
  in any DB schema).

## Open design decisions

### 1. Trigger entity

Three options, in order of invasiveness:

| Option | Trigger | Pros | Cons |
|---|---|---|---|
| A | Existing `Load` in `PLANNING` status | No new entity; mirrors FreightProcurement which fires on `PLANNING`/`READY` | A Load already exists — the promise decision has effectively been made. CapacityPromise collapses to a retroactive sanity check. |
| B | New `ShipmentRequest` entity (or repurpose some incoming-order form) | Models the real SENSE boundary: a request arrives before a Load is committed to the plan | New table, new ingestion path, new provisioning. Not in scope for Sprint 1. |
| C | Intercept at Load creation time — enforce that `Load` is only created in `PLANNING` if CapacityPromise returns ACCEPT | Reuses Load; moves the promise boundary earlier. DEFER can park the request in a staging queue. | Requires all Load writers to funnel through a `LoadCreationService` that consults the TRM. That service doesn't exist today; SAP extraction creates Loads directly. |

**Recommendation:** Option A for v1 (lowest friction, delivers a useful
"capacity-health" signal against the current plan). Revisit with Option C once a
proper Load-creation service exists — which aligns with the Sprint-2+
provisioning-framework split (MIGRATION_REGISTER 2.1).

### 2. Decision sink

Three options:

| Option | Where the decision lives | Fit |
|---|---|---|
| A | New TMS-side table `powell_capacity_promise_decisions` | Matches Core's agent-capabilities declaration. Requires Alembic migration + new model. Siloed from cross-plane visibility. |
| B | `core.agent_decisions` dual-write via PREPARE.3 | Canonical cross-plane sink. **Blocks on intersection-contract package (Core 1.8, Sprint 1 Week 4-5).** |
| C | Log-only for v1 (stdout + structured_logging), defer persistence until B is available | Ships the policy without schema commitments that may not be canonical. |

**Recommendation:** **C for v1**, B once 1.8 lands. Option A creates a
TMS-only table that either gets abandoned or has to be migrated into
`core.agent_decisions` within 3–4 weeks — pure sunk cost. The v1 endpoint
returns the decision; observability pipelines pick it up from logs until the
canonical sink is live.

### 3. Sequencing vs FreightProcurement

On a given `Load`:

```
Load (PLANNING)
  └─ CapacityPromiseTRM  →  ACCEPT / DEFER / REJECT
       ACCEPT   → Load.status = READY, FreightProcurementTRM fires on the waterfall
       DEFER    → Load.status = PLANNING (no tender), re-evaluated next cycle
       REJECT   → Load.status = REJECTED (terminal; exception escalated)
```

FreightProcurement **should not fire** when CapacityPromise has not returned
ACCEPT. Concretely: `FreightProcurementTRM.find_pending_loads` filters by
`LoadStatus.in_([PLANNING, READY])` today. After CapacityPromise lands, the
filter should narrow to `READY` only, with CapacityPromise being the sole
`PLANNING → READY` promoter. This is a one-line change in FreightProcurementTRM
queued alongside the CapacityPromise endpoint.

### 4. Feature vector population

`CapacityPromiseState` asks for 14 features; TMS today has clean sources for:

- `lane_id, requested_date, requested_loads, mode, priority` — from `Load`
- `primary_carrier_*` — from `CarrierLane` + `carrier_*` rolling aggregates
- `lane_acceptance_rate`, `primary_carrier_otp` — not yet computed; placeholder
  from `FreightTender.status` history, or hardcoded priors (0.85, 0.93) until
  Sprint 1 PREPARE.5 `lane_performance_actuals` feedback lands.
- `market_tightness`, `spot_rate_premium_pct` — no source yet; use 0.5 prior
  until DAT/Greenscreens integration lands.
- `committed_capacity`, `total_capacity`, `buffer_capacity` — need a rollup
  service (not today). For v1, derive from `CarrierLane.max_volume_daily` + a
  count of Loads already in READY+TENDERED on the same lane/date.
- `allocation_compliance_pct` — defer to 1.0 prior.

## v1 scope (≈150 lines + 80-line endpoint)

- `services/powell/capacity_promise_trm.py` — mirror `freight_procurement_trm.py`:
  - Constructor, BC checkpoint loading (stubbed — no BC model yet), heuristic
    fallback via `compute_tms_decision("capacity_promise", state)`.
  - `find_pending_loads()` — `Load.status == PLANNING`.
  - `evaluate_load(load)` — build `CapacityPromiseState` with the priors above,
    call dispatch, return decision dict.
  - `evaluate_and_promote(load)` — if ACCEPT, advance `Load.status = READY`.
    If DEFER, leave `PLANNING` (re-evaluated next cycle). If REJECT, advance to
    `REJECTED` and emit a Decision-Stream-bound structured log.
- `api/endpoints/capacity_promise.py` — three endpoints matching
  FreightProcurement: `evaluate/{load_id}`, `evaluate-all`, and
  `status/{load_id}` (returns the last promise decision + reasoning).
- Router registration in `main.py`.

**Not in v1:** `powell_capacity_promise_decisions` table, cross-plane dual-write,
BC checkpoint, `lane_performance_actuals` integration, market-signal ingestion.

## Dependencies before v1 can land

- **None blocking.** All Core substrate is already shipped; all TMS-side priors
  are acceptable placeholders. Implementation can start any time. An
  incremental ship followed by the 3–4 follow-ups above (PREPARE.3 dual-write,
  PREPARE.5 lane-performance, BC training) is the right cadence.

## What this design does NOT prescribe

- The `Load.status` extension for `REJECTED` — check whether `LoadStatus` enum
  already has a `REJECTED`/`CANCELLED` value; don't add one without audit.
- The Decision-Stream filter for capacity-promise decisions — wire up once the
  TMSDecisionStreamService subclass lands (separate item).
- The provisioning hook that runs CapacityPromise per site — defer to
  decision-cycle scheduler design, not a per-TRM endpoint question.
