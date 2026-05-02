# TMS Twin Physics Design

**Status:** draft, 2026-05-02. Implementation kicks in at [TWIN_REWRITE_PLAN.md](TWIN_REWRITE_PLAN.md) PR-3.
**Owner:** TMS team.
**Architecture source:** [Autonomy-Core/docs/architecture/TWIN_AND_ENVELOPES.md](../../Autonomy-Core/docs/architecture/TWIN_AND_ENVELOPES.md) (cross-plane structure), [DIGITAL_TWIN.md](../../Autonomy-Core/docs/architecture/DIGITAL_TWIN.md) (twin invariants).
**Companion plan:** [TWIN_REWRITE_PLAN.md](TWIN_REWRITE_PLAN.md) (the PR sequence and Core pin bumps).
**Audit it answers:** [`tool-results/b85qxmzpk.txt`](../../Autonomy-Core/.claude/projects/-home-trevor-Documents-Autonomy-Core/4083ba00-9345-4afd-a287-39963b493e70/tool-results/b85qxmzpk.txt) — the 2026-05-02 audit found 1 of 11 TMS TRMs (FreightProcurement) ready for training-data generation; the other 10 are blocked on physics or outcome-measurement gaps this design closes.

---

## 1. Why this exists

[TWIN_REWRITE_PLAN.md](TWIN_REWRITE_PLAN.md) §4 lists PR-3 as a single bullet:

> Phase-1 `lane_flow_simulator.py`: lane queues, dock dynamics, carrier capacity, equipment flow. Action injection for load build / carrier / dispatch / reposition. Per-step reward (OTD%, cost-per-load, dock utilisation, equipment balance).

That hides four months of physics work in one line. PR-3 is not a single deliverable — it's seven distinct physics models that the audit identified as bottlenecks for ten of eleven TMS TRMs. This doc names each model, its inputs/outputs, its calibration source, the TRMs that depend on it, and the implementation order. It also specifies the outcome-feedback wiring that turns observed simulator transitions into TRM reward signals — without which RL training collapses to imitation of the heuristic teacher.

**The single-paragraph claim:** the audit's verdict — "training data isn't generable for ten of eleven TMS TRMs today" — is a statement about *physics* and *outcome measurement*, not about TRM design. The TRM heuristics, state schemas, and decision shapes are all in place (or close enough). What's missing is the simulator that lets you ask "what happens if the policy chooses ACCEPT here?" and get a stochastically-realistic answer the reward function can grade. This document specifies that simulator.

---

## 2. Scope

**In scope (this doc, PR-3 of the rewrite plan):**

- Seven concrete physics models composing the TMS lane-flow simulator.
- The reward-feedback path from simulator transitions to TRM outcomes.
- Conformal calibration of stochastic outputs (P10/P50/P90 bands).
- Phasing within PR-3 (which physics first, what each unblocks).
- Calibration sources and bootstrap priors when tenant data is unavailable.
- A short list of Core changes the design assumes (tracked in MIGRATION_REGISTER).

**Out of scope (other plans / future phases):**

- Driver / vehicle / HOS modelling — Phase E+ scope per [TMS_DECISION_HIERARCHY.md](TMS_DECISION_HIERARCHY.md). Dispatching is not a TRM today; revisit when Phase E lands the data model.
- Tenant-specific calibration parameter fitting — that's PR-6 of the rewrite plan; this doc specifies *what* parameters need fitting, not *how* the fitting service works.
- Producer-plane peer coupling — Phase 3 of the envelope ladder, not TMS's job.
- The shipment generator (PR-2). The generator emits the *exogenous arrival stream* the simulator consumes; this doc's models only run on what the generator emits.

---

## 3. The physics-model framework

Every physics model in the lane-flow simulator implements the same protocol:

```python
class PhysicsModel(Protocol):
    """Stochastic transition over a slice of TMS state.

    Composed inside ``lane_flow_simulator`` to advance the world one
    tick. Each model owns one piece of physics; the simulator is the
    composer, not the source of randomness."""

    def reset(self, *, scenario: Scenario, twin_mode: TwinMode) -> None:
        """Re-seed RNG, apply scenario disruptions, lock parameters
        for the episode. ``TwinMode.PLAN_PRODUCTION`` MUST disable
        all stochasticity (point estimates only)."""

    def step(self, state: SubState, action: SubAction, *, t: Tick) -> SubTransition:
        """Advance this model's slice of state by one tick. Output is
        a typed transition carrying the new SubState plus any
        observable outcomes the OutcomeCollector watches for."""

    def conformal_bands(
        self, state: SubState, *, horizon: int,
    ) -> ConformalBand:
        """P10/P50/P90 forecast over the next ``horizon`` ticks for
        any quantity the TRMs need as a feature. Used at inference
        time, not during simulation rollout."""

    def calibrate(self, history: HistoryHandle) -> None:
        """Fit parameters to tenant ERP/EDI history (PR-6). Optional —
        defaults to the bootstrap prior when no history is available."""
```

The protocol is **product-side** (it lives in `Autonomy-TMS/backend/app/services/digital_twin/physics/protocol.py`) because the typed `SubState` / `SubAction` / `SubTransition` are TMS-specific. The composing simulator is also TMS-side (per [TWIN_AND_ENVELOPES.md §4](../../Autonomy-Core/docs/architecture/TWIN_AND_ENVELOPES.md) — generators and simulators belong with the consuming plane). The only Core hooks the protocol needs are:

| Core type | Purpose | Lives in |
|---|---|---|
| `Scenario`, `Disruption`, `DisruptionKind` | Scenario sampler injects shocks | `azirella_data_model.ml.scenarios` (exists) |
| `TwinMode` | TRAINING vs PLAN_PRODUCTION enforcement | `azirella_data_model.digital_twin.twin_interface` (exists) |
| `ConformalBand` (new) | P10/P50/P90 wrapper for forecast outputs | `azirella_data_model.conformal` (proposed — see §10) |
| `HistoryHandle` (new) | Read-only access to ERP-extracted history for calibration | `azirella_data_model.ml.calibration` (proposed — see §10) |

The two new Core types are minor additions; both pass the placement test (cross-product — SCP's twin will eventually need them too — and substrate — conformal calibration is already named substrate in CLAUDE.md "Four Pillars").

---

## 4. The seven physics models

Each model below carries: state space, output, calibration source, dependent TRMs, and a one-line stochastic specification.

### 4.1 Carrier Acceptance

**Question it answers:** when TMS tenders a load to a carrier on a given lane, will the carrier accept?

**State features:**
- `lane_id`, `carrier_id`, `equipment_type`
- `planned_pickup_date`, `hours_to_pickup`
- `rate_offered` vs `dat_benchmark_rate` (premium %)
- `market_tightness` (from the spot-rate model, §4.5)
- `carrier_recent_acceptance_rate` (rolling 30-day per-carrier-per-lane)
- `outstanding_commitment_count` (loads already tendered to this carrier in the same window)

**Output:** `Bernoulli(p_accept)` — accepted/rejected per tender event. `p_accept` is a logistic regression over the features above.

**Calibration source (PR-6):** historical `FreightTender.status` → `{ACCEPTED, REJECTED, EXPIRED}` per (carrier × lane × week). When a tenant has < 3 months of FreightTender history, fall back to the bootstrap prior.

**Bootstrap prior:**
- Contracted carrier: `p_accept = 0.85` (audit-noted prior; published industry baseline 0.82–0.88)
- Spot/broker carrier: `p_accept = 0.55`
- Premium adjustment: `p_accept *= 1 + 0.4 * tanh((rate_offered − benchmark) / benchmark)` — paying 25% over benchmark roughly doubles acceptance, paying 25% under halves it
- Tightness adjustment: `p_accept *= 1 − 0.3 * market_tightness` — a tight market reduces acceptance independently of the offered rate

**Dependent TRMs:** CapacityPromise (lane acceptance rate is a top-3 feature), BrokerRouting (broker selection conditioned on expected acceptance), FreightProcurement (waterfall ordering), CapacityBuffer (buffer sizing depends on expected reject rate).

**Phase:** 2.A.1 — first to build because four TRMs depend on it.

---

### 4.2 Lane Transit Time

**Question it answers:** given a load departed lane X at time t with equipment type Y, how long until it arrives?

**State features:**
- `lane_id`, `distance_miles`, `equipment_type`
- `departure_day_of_week`, `season_index` (week 1–52)
- `weather_index` (from scenario disruptions; default 0 for fair weather)

**Output:** transit-hours distribution per (lane × equipment × dow × season) bucket. Expressed as **conformal P10/P50/P90 bands** — the TRMs use these directly as features (e.g., ShipmentTracking's ETA bounds).

**Calibration source (PR-6):** p44 / MacroPoint historical traces, or `Shipment.actual_arrival - Shipment.actual_departure` aggregated when EDI 214 events are present. Bucket by lane × equipment × season; fit a log-normal per bucket.

**Bootstrap prior:** `μ = distance_miles / avg_speed_mph * (1 + season_factor + weather_factor)`, `σ = 0.15 * μ`. Default `avg_speed_mph` = 50 (truck), 35 (intermodal drayage), 30 (LTL with stops). Season factor varies ±10% (winter slow-down, summer construction). Weather factor 0–25% (clear → severe storm).

**Dependent TRMs:** ShipmentTracking (ETA + conformal bounds), CapacityPromise (acceptance-by-deadline depends on expected transit), IntermodalTransfer (transit-penalty days vs truck).

**Phase:** 2.A.2 — pairs with carrier acceptance because most TRMs that need acceptance also need transit-time bands.

---

### 4.3 Dock Queue

**Question it answers:** given an appointment requested at facility F for time t, what's the dwell time? Was a door available? Did the appointment incur detention?

**State (per facility, per tick):**
- `available_doors[t]` — count of free doors
- `queue[t]` — list of appointments waiting (FIFO unless priority overrides)
- `active_appointments` — list of `(appointment, dwell_remaining)`

**Transition:**
- An appointment arrives (from the shipment generator). If `available_doors > 0`: assign door, draw `dwell_time ~ Gamma(α_carrier, β_equipment_type)`. Else: enqueue.
- Each tick, decrement `dwell_remaining`. When zero: free door, mark appointment `COMPLETED`, emit `actual_dwell_time` and `detention_minutes_over_free_time`.

**Output observables (per appointment):**
- `actual_dwell_time` (minutes)
- `queue_wait_time` (minutes from arrival to door assignment)
- `detention_cost = max(0, actual_dwell − free_time_minutes) × detention_rate_per_hour / 60`

**Calibration source (PR-6):** appointment-completion timestamps from existing `Appointment.checked_in_at` / `Appointment.checked_out_at` (when those fields land — currently missing per audit). Per-carrier dwell-time distribution; per-facility door-count from `Facility.total_dock_doors`.

**Bootstrap prior:** Gamma(α=2, β=45min) for live load, Gamma(α=2, β=30min) for live unload, Gamma(α=3, β=15min) for drop+hook. Per-carrier dwell shifted by their reputation index (from `CarrierScorecard.avg_dwell` if populated, else 1.0× the prior).

**Dependent TRMs:** DockScheduling (detention cost is the reward), ExceptionManagement (queue wait > threshold → exception event).

**Phase:** 2.B.

---

### 4.4 Equipment Flow

**Question it answers:** at any tick, how many of equipment type E are available at site S? When a load consumes equipment, when does it free? When repositioning happens, when does the equipment arrive at the target?

**State (per site, per equipment type):**
- `available_count`, `in_transit_count`, `in_use_count`

**Transition:**
- A load tendered out of site S consumes 1 unit of its equipment type at S, which becomes `in_use_count`. The unit moves to the destination site after the lane-transit-time draw plus the dwell at destination, then becomes `available_count` at destination.
- A reposition decision moves N units from source site to target site; they're `in_transit` for the lane transit time, then available at target.

**Output observables:**
- Per-site equipment-balance time series (used as feature for EquipmentReposition).
- Per-load `equipment_wait_time` (time from tender to actual departure due to equipment unavailability).

**Calibration source (PR-6):** `Equipment` table when populated (per-equipment current_site_id + status), or aggregate from `Load` history (count loads departing per site per day, infer equipment turnover).

**Bootstrap prior:** Initialise each site with `floor(avg_daily_loads × 1.5)` units of its primary equipment type. Reposition lead time = lane transit time × 1.0 (empty miles same speed as loaded).

**Dependent TRMs:** EquipmentReposition (the entire decision space is over this state), FreightProcurement (constrained — can't tender if no equipment available), CapacityPromise (equipment availability is a hidden constraint behind committed_capacity).

**Phase:** 2.C.

---

### 4.5 Spot-Rate / Market-Tightness

**Question it answers:** what's the current spot rate on lane L, and how does it move?

**State (per lane × bucket):**
- `spot_rate` ($/mile)
- `tightness` (0–1, OTRI proxy: outbound load count / outbound truck count)

**Transition:** AR(1) with seasonal drift and shock injection.

```
spot_rate[t] = β · spot_rate[t-1] + (1-β) · (contract_rate × (1 + κ · tightness[t])) + ε
tightness[t] = α · tightness[t-1] + (1-α) · season_factor[t] + shock[t]
```

with `α = 0.85`, `β = 0.7`, `κ = 0.4`. Shocks come from `DisruptionKind.CARRIER_STRIKE`, `DisruptionKind.WEATHER_EVENT`, etc.

**Calibration source (PR-6):** DAT or proxy benchmark rates per lane × week. Fit α, β, κ, σ_ε from rolling history. When DAT isn't available, fit from the spread between accepted-tender rates and their contracts.

**Bootstrap prior:** start at `spot_rate = contract_rate`, `tightness = 0.5`, drift seasonally (Q4 retail surge → Q1 trough → produce season Q2 → Q3 baseline). σ_ε = 0.05 × contract_rate.

**Dependent TRMs:** BrokerRouting (premium decision), CapacityBuffer (buffer size scales with tightness), IntermodalTransfer (truck-vs-intermodal economics depend on truck spot rates).

**Phase:** 2.D.

---

### 4.6 Exception Generator

**Question it answers:** which shipments hit exceptions (delay, damage, missed pickup, missed delivery) and when?

**State (per carrier × lane × period):**
- `exception_rate_per_load` (Poisson lambda)
- `exception_kind_distribution` (multinomial over delay/damage/miss/refused)

**Transition:** for each in-flight shipment, draw a Bernoulli(`exception_rate_per_load`) per tick. On exception fire: emit `ShipmentException` with `kind`, `severity`, `recovery_options`. Severity drives the recovery cost (small delay → no recovery; major delay → expedite cost; refused → re-tender at spot rate).

**Calibration source (PR-6):** historical `ShipmentException` tagged by carrier + lane. Count/distribution per (carrier × lane × month).

**Bootstrap prior:** `λ = 0.05 / load` (5% of loads hit at least one exception). Distribution: 60% delay, 15% damage, 15% miss, 10% refused. Severity distribution: 70% recoverable without cost, 20% recoverable with expedite cost, 10% miss SLA → penalty.

**Dependent TRMs:** ExceptionManagement (it's the entire decision space), ShipmentTracking (exceptions trigger ETA recompute + escalation paths).

**Phase:** 2.E.

---

### 4.7 Intermodal Ramp

**Question it answers:** can shipment S use intermodal? Does the origin ramp accept it? What's the rail transit time? What's the all-in cost?

**State (per ramp × bucket):**
- `accepting_today` (boolean — operational status from scenario disruptions)
- `congestion_level` (0–1 — drives effective acceptance probability)
- `capacity_remaining` (decremented per accepted shipment)

**Transition:** for each tender to a ramp, draw `Bernoulli(p_ramp_accept)` where `p_ramp_accept = 1.0 − congestion_level` (with hard zero if `accepting_today = False`). On accept: decrement capacity, lookup rail-transit-time per (origin_ramp × dest_ramp × season), emit `intermodal_all_in_cost = drayage_origin + ramp_fee + rail + drayage_destination` with conformal bands on transit.

**Calibration source (PR-6):** vendor-specific (BNSF / UP / CSX / NS APIs), or derived from accepted-tender prices when an `IntermodalRate` table is populated.

**Bootstrap prior:** `p_ramp_accept = 0.92` baseline, `congestion_level` AR(1) with drift. Rail transit = truck transit × 1.5 with σ = 0.1 × μ. Drayage rate = $4.50/mile within 50 mile radius. Ramp fee = $50/container.

**Dependent TRMs:** IntermodalTransfer (the entire decision space).

**Phase:** 2.F. **Lowest priority** — IntermodalTransfer is the only consumer; everything else can train without it.

---

### 4.8 Tracking Event Generator

**Question it answers:** what tracking pings does the carrier emit and when? With what jitter?

**State (per shipment × time):** `last_event_at`, `last_known_location`.

**Transition:** at each tick, draw next `event_arrival_time ~ Exponential(λ_carrier)`. Emit event at `event_arrival_time + jitter ~ N(0, 30min)` with `last_known_location` = interpolated waypoint. Occasionally drop events (probability `p_drop_carrier`).

**Calibration source (PR-6):** historical `TrackingEvent` density per carrier (events / hour / load).

**Bootstrap prior:** `λ = 1 event / 4 hours` for premium carriers, `λ = 1 / 12 hours` for budget carriers. `p_drop = 0.02` (2% of expected events missing).

**Dependent TRMs:** ShipmentTracking (ETA confidence depends on event freshness; missed-event escalation triggered by stale tracking).

**Phase:** 2.G. **Lowest priority alongside 2.F** — ShipmentTracking is the only TRM that needs raw tracking-event jitter; the others use the lane-transit P10/P50/P90 directly.

---

## 5. Outcome feedback wiring

Per the audit, the gap that matters most isn't which physics models exist — it's whether the simulator's transitions get **observed as TRM rewards**. Today only FreightProcurement has outcome wiring (`TRM_OUTCOME_DELAY[po] = 7d`); the other ten TRMs compute reward inside their heuristic teacher and never observe the actual outcome.

The lane-flow simulator closes that loop by emitting typed `OutcomeEvent` records on every observable transition:

```python
@dataclass
class OutcomeEvent:
    decision_id: int          # the TRM decision this outcome grades
    decision_type: str        # po | capacity_promise | load_build | ...
    outcome_kind: str         # tender_accepted | dwell_recorded | reposition_landed | ...
    outcome_at: datetime      # when the outcome materialised in sim time
    payload: dict[str, Any]   # kind-specific; matches the TRM's reward schema
```

A new TMS-side `OutcomeCollectorService` (mirroring SCP's existing service) consumes these and writes to canonical `trm_outcome` tables. Each TRM's RL trainer reads its own outcomes by `decision_type` filter.

The mapping from physics observable → TRM reward is fixed:

| TRM | Physics model | Outcome event | Reward formula |
|---|---|---|---|
| CapacityPromise | Carrier Acceptance | `tender_accepted` | `+1 if accepted else −1; spot_premium_avoided = (spot_rate − accepted_rate) if accepted` |
| BrokerRouting | Carrier Acceptance + Spot-Rate | `broker_tender_accepted` | `+ premium_vs_dat_benchmark + spot_avoidance_value` |
| LoadBuild | Lane Transit + Carrier Acceptance | `load_completed` | `consolidation_savings_realised − stop_off_penalty − dwell_cost` |
| DockScheduling | Dock Queue | `appointment_completed` | `−detention_cost − queue_wait_penalty` |
| EquipmentReposition | Equipment Flow | `repositioned_equipment_used` | `Σ spot_premium_avoided over loads using moved equipment − reposition_cost` |
| ExceptionManagement | Exception Generator | `exception_resolved` | `−recovery_cost − sla_penalty if missed` |
| IntermodalTransfer | Intermodal Ramp | `intermodal_completed` | `cost_savings_realised − transit_penalty_value` |
| ShipmentTracking | Tracking Event + Lane Transit | `delivery_completed` | `−|actual_eta − predicted_eta_p50| if outside conformal band` |
| CapacityBuffer | Carrier Acceptance | `tender_acceptance_rate_lane_week` | `+improvement_vs_no_buffer − buffer_carrying_cost` |
| DemandSensing | (no direct physics — feedback from forecast accuracy) | `forecast_error_recorded_30d` | `+|old_error| − |new_error|` |
| FreightProcurement | Carrier Acceptance + Lane Transit | `delivery_completed` (existing) | unchanged |

**Outcome horizons** (delays from decision to observable outcome) match SCP's `TRM_OUTCOME_DELAY` pattern: 1–3 days for tender outcomes, 6h–1d for dock dwell, 7–30d for delivery / reposition utilisation. The simulator advances virtual-clock ticks at the appropriate cadence so outcomes materialise on the right horizon.

---

## 6. Conformal calibration

Every stochastic output a TRM consumes as a feature MUST be wrapped in a `ConformalBand` (P10/P50/P90). This is non-negotiable — it's the [Four Pillars](../../Autonomy-Core/CLAUDE.md) "Conformal Prediction" pillar in code.

Concretely:
- Lane-transit forecasts: P10/P50/P90 over transit hours, calibrated per (lane × equipment × season) bucket.
- Carrier acceptance: forecast `p_accept` is a calibrated logistic — return `p_accept` itself plus a calibration-error band (Brier-aligned).
- Spot rate forecasts: P10/P50/P90 over horizon `t+1 ... t+H` ticks.
- Dock dwell forecasts: P10/P50/P90 of expected dwell at requested time.

The bands are fit using Core's existing conformal infrastructure (`azirella_data_model.conformal`). For PR-3, use a simple split-conformal calibration on the Phase-1 bootstrap distributions; PR-6 (tenant calibration) replaces the bootstrap with empirical conformal-quantile regression on the tenant's history.

**The non-Monte-Carlo rule stands.** Conformal bands replace Monte Carlo across the platform. Twin rollouts at training time are stochastic by design (that's the whole point); conformal bands are how *inference-time* uncertainty is propagated to the TRM features without re-running the twin under noise.

---

## 7. Phasing within PR-3

The audit names ten gated TRMs; the seven physics models above unblock them in a clear dependency order. PR-3 splits into seven sub-PRs:

| Sub-PR | Physics model(s) | TRMs unblocked | Estimated effort |
|---|---|---|---|
| **PR-3.A** | Carrier Acceptance + Lane Transit | CapacityPromise, BrokerRouting (with broker seed), FreightProcurement (validates against current production), ShipmentTracking (ETA half — no event generator yet) | 1 week — these two ship together because the Lane-Transit conformal bands feed the Acceptance state |
| **PR-3.B** | Dock Queue | DockScheduling, ExceptionManagement (queue-overflow path) | 4 days |
| **PR-3.C** | Equipment Flow | EquipmentReposition, FreightProcurement (constrained), CapacityPromise (improved committed_capacity rollup) | 5 days |
| **PR-3.D** | Spot-Rate / Market-Tightness | BrokerRouting (rate decision), CapacityBuffer, IntermodalTransfer (truck-vs-rail economics) | 3 days |
| **PR-3.E** | Exception Generator | ExceptionManagement (full decision space), ShipmentTracking (exception triggers) | 4 days |
| **PR-3.F** | Intermodal Ramp | IntermodalTransfer (full decision space) | 4 days — gated on Ramp + IntermodalRate seed entities (see §9) |
| **PR-3.G** | Tracking Event | ShipmentTracking (full event-jitter feature space) | 2 days |

Total wall-clock estimate: ~5 weeks if sequenced linearly; closer to 3 weeks with concurrency (3.A → 3.B/3.C/3.D in parallel → 3.E → 3.F/3.G in parallel). Sequencing matters because **3.A unblocks the most TRMs** — start there.

---

## 8. Calibration source bootstrapping

Every model has a bootstrap prior usable when tenant data is unavailable. The priors are deliberately **conservative** (wider variance, weaker signal) so a poorly-calibrated simulator under-promises rather than over-promises.

**Bootstrap → tenant-fitted transition** happens at PR-6. Until then, all training is on bootstrap-prior data. Bootstrap-trained TRM policies are not production-ready; they're the seed weights for behaviour-cloning, refined later by RL on tenant-fitted simulator data.

**Per-tenant calibration drift detection** (open question, §11): how does the simulator know its parameters have gone stale relative to current ERP/EDI extracts? Likely a periodic Brier / MAPE check on held-out recent transactions, with alerts when drift exceeds a threshold. Not in PR-3 scope; revisit at PR-6.

---

## 9. Data-model prerequisites

Several physics models require entities or columns the audit flagged as missing. These are TMS-side schema work, additive, and trackable as their own PRs:

| Model | Missing entity / column | Where to add | Blocking PR |
|---|---|---|---|
| Dock Queue | `Appointment.checked_in_at`, `Appointment.checked_out_at`, `Yard` table, `YardSpot` table | `azirella_data_model` (Yard substrate — passes Rule 1) + TMS migration (Appointment columns) | PR-3.B |
| Equipment Flow | `Equipment.current_site_id`, `Equipment.status`, `EquipmentMove` table | `azirella_data_model.master.equipment` (extend existing) + TMS migration | PR-3.C |
| Intermodal Ramp | `Ramp` table, `IntermodalRate` seed rows, `RampCongestionSnapshot` | `azirella_data_model.master.ramp` (passes Rule 2 — substrate per AWS SC DM) + TMS seed | PR-3.F |
| Tracking Event | p44 / EDI 214 ingestion path | TMS `app/integrations/tracking/` | PR-3.G |
| Spot-Rate | DAT / OTRI feed adapter | TMS `app/integrations/dat/` (or Core if cross-product — likely Core) | PR-3.D |
| Carrier Acceptance | (existing — uses `FreightTender.status` history) | none | — |
| Lane Transit | (existing — uses `Shipment.actual_arrival/departure`) | none | — |

Each entity addition that lands in Core (Yard, Ramp, Equipment columns, DAT adapter) MUST be audited via the [`core-placement-auditor`](../../Autonomy-Core/CLAUDE.md) before merge — that's the rule we just added two sessions ago.

---

## 10. Core changes this design assumes

Three small Core additions that pass placement (cross-product utility, substrate status):

1. **`azirella_data_model.conformal.ConformalBand`** — typed wrapper for P10/P50/P90 outputs. Cross-product (SCP and DP also emit conformal bands today, in ad-hoc shapes). Substrate (named in CLAUDE.md Four Pillars). Tracked in MIGRATION_REGISTER §3.26 (proposed).
2. **`azirella_data_model.ml.calibration.HistoryHandle`** — read-only slice over ERP-extracted history scoped to a tenant + entity-class. Cross-product (SCP and DP need the same shape). Tracked in MIGRATION_REGISTER §3.26.
3. **`azirella_data_model.ml.outcome.OutcomeEvent`** — typed simulator-emitted outcome record. The producer side is product-specific (each plane's twin emits its own kinds) but the schema is cross-product. Cross-product (SCP also benefits when its outcome service is refactored onto this). Tracked in MIGRATION_REGISTER §3.26.

These three are the only Core changes the design depends on. Implementation order: Core ships them first (a single coordinated PR), TMS pin bumps, PR-3.A starts.

---

## 11. Validation

Before declaring PR-3 done, the lane-flow simulator must pass these checks:

| Check | Pass criterion | Where |
|---|---|---|
| **Carrier Acceptance** | Brier score ≤ 0.20 on held-out tender history (vs prior 0.30) | tests/twin/test_carrier_acceptance_calibration.py |
| **Lane Transit** | Conformal-band coverage ≥ 88% (P10–P90 contains actual arrivals 88% of the time) | tests/twin/test_lane_transit_coverage.py |
| **Dock Queue** | Wasserstein distance ≤ 30min on dwell-time distribution per (carrier × facility) | tests/twin/test_dock_queue_distribution.py |
| **Equipment Flow** | Conservation: equipment count is invariant (in-transit + at-site = total fleet) at every tick | tests/twin/test_equipment_conservation.py |
| **Spot-Rate** | AR(1) parameters within ±15% of empirical fit | tests/twin/test_spot_rate_ar1.py |
| **Outcome wiring** | For each TRM, decision → outcome → reward populates the `trm_outcome` table within the TRM's `TRM_OUTCOME_DELAY` horizon | tests/twin/test_outcome_round_trip.py |
| **Determinism (PLAN_PRODUCTION)** | Two runs of the simulator with `TwinMode.PLAN_PRODUCTION` produce byte-identical trajectories | tests/twin/test_plan_production_determinism.py |
| **End-to-end RL rollout** | All 11 TRMs successfully complete a 30-day episode with the simulator and write trajectories to the trainer | tests/twin/test_full_episode_rollout.py |

The first six are per-model; the last three are integration-level. The end-to-end test is the **definition of done** for PR-3 — it's what proves "training data for the TMS TRMs is generable."

---

## 12. Open questions

1. **Driver / HOS modelling.** Phase E+ adds dispatching as a TRM. Does the lane-flow simulator surface "available driver hours per carrier" as a state, or is that an embedded carrier-acceptance feature? Decide at Phase E spec time, not now. Tracking in [memory: project_tms_dispatching_open_question](../../Autonomy-Core/.claude/projects/-home-trevor-Documents-Autonomy-Core/memory/project_tms_dispatching_open_question.md).

2. **Multi-modal shipments.** A truck → rail → truck shipment touches three carrier-acceptance draws and three transit-time draws. Does the simulator stitch them automatically (one chained `step` call per leg), or does the TRM author the chain explicitly? **Recommendation:** simulator stitches; TRMs see one shipment, not three legs.

3. **Calibration drift detection.** When does the simulator alert "my parameters are stale relative to current data"? Out of PR-3 scope; revisit at PR-6.

4. **Cross-tenant calibration borrow-strength.** Tenant A has 6 months of history; tenant B has 2 weeks. Does B borrow A's parameters (with a downweight)? Avoids cold-start, but risks privacy contamination across tenants. Defer to PR-6 with a hard "no" default until SOC-II review.

5. **Ramp data sourcing.** Vendor APIs (BNSF / UP / CSX / NS) versus a derived approach from accepted-tender prices in `IntermodalRate`. Latter is cheaper, former is more accurate. Pick one at PR-3.F kickoff.

6. **Spot-rate feed adapter placement.** DAT adapter — Core (cross-product, every product backend benefits) or TMS (only TMS uses it today)? Likely Core per Rule 2 (it's substrate-grade market data), but confirm via the placement auditor at PR-3.D.

---

## 13. What this doc is **not**

- It is not the rewrite plan — that's [TWIN_REWRITE_PLAN.md](TWIN_REWRITE_PLAN.md). This is the inside of PR-3.
- It is not the TRM reference — that's [TMS_TRM_HEURISTIC_REFERENCE.md](TMS_TRM_HEURISTIC_REFERENCE.md). This grades TRM-feature *production* (the simulator side).
- It is not a calibration manual — PR-6 will be that. This specifies *what* needs calibration; *how* is later.
- It is not a Phase E dispatching spec — that's separate work after the data model lands.

---

## 14. Cross-references

- [TWIN_REWRITE_PLAN.md](TWIN_REWRITE_PLAN.md) — the PR sequence; this doc elaborates PR-3.
- [Autonomy-Core/docs/architecture/TWIN_AND_ENVELOPES.md](../../Autonomy-Core/docs/architecture/TWIN_AND_ENVELOPES.md) — cross-plane twin structure.
- [Autonomy-Core/docs/architecture/DIGITAL_TWIN.md](../../Autonomy-Core/docs/architecture/DIGITAL_TWIN.md) — twin invariants (training, not planning).
- [TMS_TRM_HEURISTIC_REFERENCE.md](TMS_TRM_HEURISTIC_REFERENCE.md) — per-TRM heuristic specs.
- [TMS_DECISION_HIERARCHY.md](TMS_DECISION_HIERARCHY.md) — pre-dispatch vs Phase E+ scoping.
- [Autonomy-Core/docs/MIGRATION_REGISTER.md §3.26](../../Autonomy-Core/docs/MIGRATION_REGISTER.md) (proposed) — Core hooks (ConformalBand, HistoryHandle, OutcomeEvent).
- [Autonomy-Core/docs/architecture/SEASONAL_ENVELOPE.md](../../Autonomy-Core/docs/architecture/SEASONAL_ENVELOPE.md) — adopted by PR-4 of the rewrite plan, used in carrier-acceptance season-factor computation.
- 2026-05-02 audit: `~/.claude/projects/-home-trevor-Documents-Autonomy-Core/4083ba00-9345-4afd-a287-39963b493e70/tool-results/b85qxmzpk.txt` — the readiness assessment this design closes.
