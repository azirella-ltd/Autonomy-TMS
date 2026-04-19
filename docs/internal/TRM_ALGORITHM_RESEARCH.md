# TMS TRM Algorithm Research — Industry-Standard Heuristics & Gap Analysis

**Date:** 2026-04-18
**Purpose:** Document the canonical OR problems, industry-standard algorithms, and production TMS heuristics for each of the 11 TMS TRM agents. Gap-analyse the current heuristic library (`services/powell/tms_heuristic_library/dispatch.py`) against these standards. Ensure training data generation uses correct decision logic.

**Why this matters:** The heuristic library is the *teacher policy* for behavioral cloning. If the heuristics encode wrong logic, we train wrong TRM models. Every gap identified here must be corrected before generating the final training dataset.

---

## Table of Contents

1. [CapacityPromiseTRM](#1-capacitypromisetrm) (SENSE)
2. [ShipmentTrackingTRM](#2-shipmenttrackingtrm) (SENSE)
3. [DemandSensingTRM](#3-demandsensingtrm) (SENSE)
4. [CapacityBufferTRM](#4-capacitybuffertrm) (ASSESS)
5. [ExceptionManagementTRM](#5-exceptionmanagementtrm) (ASSESS)
6. [FreightProcurementTRM](#6-freightprocurementtrm) (ACQUIRE)
7. [BrokerRoutingTRM](#7-brokerroutingtrm) (ACQUIRE)
8. [DockSchedulingTRM](#8-dockschedulingtrm) (PROTECT)
9. [LoadBuildTRM](#9-loadbuildtrm) (BUILD)
10. [IntermodalTransferTRM](#10-intermodaltransfertrm) (BUILD)
11. [EquipmentRepositionTRM](#11-equipmentrepositiontrm) (REFLECT)

---

## 1. CapacityPromiseTRM

### Canonical Problem
**Resource Allocation / Multi-Dimensional Knapsack** with temporal constraints — the transportation equivalent of Available-to-Promise (ATP). Given a shipment request (lane, date, mode), determine whether committed carrier capacity can fulfill it, and if so, from which tier of the routing guide.

### Industry-Standard Algorithm
Production TMS systems (Oracle OTM, SAP TM, BluJay) use a **greedy waterfall allocation with priority ordering**:
1. Check committed capacity from routing guide tier 1 (primary carrier)
2. If consumed, check tier 2 (backup), then tier 3, then spot
3. At each tier: decrement remaining capacity bucket, check constraints

The objective function is a **weighted composite score**, not pure cost minimization:
- Cost: 30–40% ($/mile vs. lane benchmark)
- Service: 20–25% (carrier on-time % trailing 90 days)
- Acceptance rate: 15–20% (historical 990-accept rate)
- Allocation compliance: 10–15% (actual vs. committed volume)
- Capacity availability: 5–10%

**Key heuristics:**
- Pre-compute capacity buckets daily; CTP is a decrement-and-check, not a solve
- Reserve 10–15% safety buffer; consumption >85% flags for review
- Cache feasible carrier lists per lane/mode/week

**EDI flow:** 204 (tender) → 990 (accept/decline) → 214 (status) → 210 (invoice)

### Current Implementation Review
`_compute_capacity_promise()` in dispatch.py (lines 99–150):
- ✅ Priority-based accept/reject logic (P1–P2 always promise)
- ✅ Available capacity = total - booked
- ✅ Spot rate premium threshold (20%)
- ✅ Buffer capacity consumption for critical priority
- ❌ **Missing: composite scoring model** — uses simple if/else, not weighted carrier score
- ❌ **Missing: allocation compliance tracking** — no check of carrier's volume commitment vs. actual
- ❌ **Missing: time-bucket capacity** — capacity is a single number, not per-day/week bucket
- ❌ **Missing: routing guide tier awareness** — no concept of primary/backup/spot tiers
- ❌ **Missing: carrier scorecard integration** — no OTP, claims ratio, acceptance rate in decision

### Training Data Implications
Current training data teaches the TRM a flat accept/reject decision. The TRM should learn a **tier-ranked allocation** with composite scoring. State dataclass needs:
- `carrier_otp_pct`, `carrier_acceptance_rate`, `allocation_compliance_pct` (some exist on state but unused in logic)
- Per-period capacity buckets (not just total)

### Gap Severity: **HIGH** — the core decision structure (flat accept/reject vs. scored waterfall) is wrong

---

## 2. ShipmentTrackingTRM

### Canonical Problem
**State estimation / sensor fusion** — combine signals from carrier EDI 214, GPS/telematics, visibility platforms (project44/FourKites), weather, and traffic into a single ETA point estimate + confidence interval. Anomaly detection for tracking-lost, route-deviation, temperature-excursion.

### Industry-Standard Algorithm
Visibility platforms use **ML regression** (XGBoost/LightGBM) trained on historical transits with real-time feature updates. Signal fusion is a **weighted ensemble** (not Kalman filtering — road networks don't fit linear state-space):
- GPS/telematics: highest weight (most current)
- Visibility platform ML prediction: second
- Carrier-provided ETA (EDI 214 code X1/X3/AF): weighted by carrier historical accuracy
- Planned transit adjusted for elapsed: fallback

Anomaly detection:
- **Tracking-lost:** no update > N× expected reporting interval (2–4h truck, 24–48h ocean)
- **Route deviation:** geofence corridor (25–50 mile buffer); point-in-polygon check
- **Temperature:** simple min/max threshold on IoT sensor

Conformal prediction provides distribution-free intervals: calibrate nonconformity scores on recent shipments, take P90 as interval width. Weekly recalibration.

### Current Implementation Review
`_compute_shipment_tracking()` in dispatch.py (lines 157–215):
- ✅ Tracking-lost detection (>4h no update for truck)
- ✅ Late delivery detection (ETA past delivery window)
- ✅ Temperature excursion (min/max threshold)
- ✅ At-risk detection (progress vs. time elapsed)
- ❌ **Missing: ML-based ETA** — uses only planned-vs-actual comparison, no ML regression
- ❌ **Missing: signal weighting by source reliability** — all sources treated equally
- ❌ **Missing: conformal prediction intervals** — `eta_p10`/`eta_p90` exist on state but unused in logic
- ❌ **Missing: carrier-specific accuracy weighting** — `carrier_otp_pct` exists but not used to adjust ETA confidence
- ❌ **Missing: route deviation detection** — no geofence corridor check

### Training Data Implications
Current data teaches simple threshold-based rules. The TRM should learn **adaptive ETA synthesis** weighted by source quality. The heuristic should at minimum:
- Use `carrier_reliability_score` to discount carrier-provided ETA
- Compute conformal intervals from `eta_p10`/`eta_p90` when available
- Differentiate urgency by mode (4h threshold for truck, 24h for ocean already coded but hardcoded)

### Gap Severity: **MEDIUM** — thresholds are correct, but ETA synthesis is too simple

---

## 3. DemandSensingTRM

### Canonical Problem
**Short-horizon time series forecast adjustment with exogenous regressors.** Distinct from demand planning (monthly/quarterly baseline) — demand sensing operates on a 1–7 day horizon using today's order book and leading indicators to override the plan.

### Industry-Standard Algorithm
- **Baseline:** Holt-Winters triple exponential smoothing (trend + seasonality)
- **Sensing overlay:** Pattern recognition / nearest-neighbor (E2open approach) or LightGBM/XGBoost with lagged demand + calendar + external regressors
- **Intermittent demand:** Croston's method or SBA (Syntetos-Boylan Approximation) for sporadic LTL lanes
- **Bias detection:** Trigg's tracking signal = cumulative error / MAD; trigger refit when |TS| > 4
- **Changepoint detection:** CUSUM or Bayesian Online Changepoint Detection for structural breaks (customer gained/lost)

**Signals ranked by predictive lift:**
1. Order pipeline / booking velocity (last 24–72h vs. prior period) — strongest signal
2. POS / sell-through data (CPFR / EDI 852)
3. Retailer signals (promotion calendars, DC inventory)
4. Seasonal/calendar (holiday, harvest, produce season)
5. Economic indicators (PMI, freight indices)
6. Weather (pre-storm stocking, post-disaster relief)

**Asymmetric loss:** under-forecasting (missed capacity) costs more than over-forecasting → target 60th–70th percentile, not median.

### Current Implementation Review
`_compute_demand_sensing()` in dispatch.py (lines 222–263):
- ✅ Forecast bias detection (over/under forecast threshold 15%)
- ✅ Week-over-week change detection (20% threshold)
- ✅ Peak season + MAPE interaction
- ✅ Partial correction (50% of bias, not full — prevents overcorrection)
- ❌ **Missing: tracking signal (Trigg's)** — uses one-shot bias, not cumulative tracking
- ❌ **Missing: asymmetric loss function** — treats over and under forecasting equally
- ❌ **Missing: changepoint detection** — no CUSUM or structural break detection
- ❌ **Missing: signal-type-specific adjustment magnitude** — `signal_type` and `signal_magnitude` exist on state but unused
- ❌ **Missing: order pipeline velocity** — the strongest signal is not consumed

### Training Data Implications
Current logic teaches threshold-based bias correction. Should teach:
- Cumulative tracking signal monitoring with regime detection
- Different correction strategies per signal source
- Asymmetric adjustment (bias correction should be larger for under-forecasting)

### Gap Severity: **MEDIUM** — direction is right but missing the strongest signal (order pipeline) and cumulative tracking

---

## 4. CapacityBufferTRM

### Canonical Problem
**Newsvendor Problem** extended to multi-period, multi-lane capacity reservation. How much extra carrier capacity to reserve above forecast on each lane to absorb variability and tender rejections.

### Industry-Standard Algorithm
Optimal buffer is the **newsvendor critical ratio**: `P(D ≤ Q*) = (C_spot - C_contract) / (C_spot + C_unused)`

Where `C_spot >> C_contract` and `C_unused` = opportunity cost of idle commitments.

**Key inputs:**
- **Tender reject rate** is the single most important signal. Industry average 15–20%. Minimum buffer = `forecast × r / (1-r)` to maintain first-tender fill
- **Market tightness:** DAT OTVI/OTRI. Rule: if OTRI > 15%, increase buffer by `(OTRI - baseline) × sensitivity_factor`
- **Demand CV:** Standard safety-stock formula `buffer = z_α × σ × √leadtime`. For CV > 0.5, use conformal P90–P50 instead of Gaussian
- **Seasonal calendar:** produce season, peak shipping, month-end surges

**Production heuristics (tiered):**
- Low CV (<0.3): 10% buffer
- Medium CV (0.3–0.6): 20% buffer
- High CV (>0.6): 30–40% buffer
- Reject-rate-reactive: `multiplier = 1 + (trailing_7day_reject_rate × 1.5)`
- Conformal interval: buffer = P90 - P50 forecast (best approach)

### Current Implementation Review
`_compute_capacity_buffer()` in dispatch.py (lines 270–320):
- ✅ Tender reject rate adjustment (>15% increases buffer 1.3×)
- ✅ Demand CV adjustment (>0.3 increases by CV×0.5)
- ✅ Peak season multiplier (1.2×)
- ✅ Demand trend adjustment
- ✅ Recent capacity miss count factor
- ✅ Oversupplied detection (reduce to 0.85× when quiet)
- ❌ **Missing: newsvendor critical ratio** — uses multiplicative heuristic, not the optimal stocking quantity
- ❌ **Missing: conformal P90–P50** — `forecast_p10`/`forecast_p90` exist on state but unused
- ❌ **Missing: market tightness index (OTRI)** — not in state or logic
- ❌ **Missing: cost-ratio-based optimization** — doesn't consider `C_spot / C_contract` ratio

### Training Data Implications
Current logic is the closest to correct of all TRMs — the multiplicative heuristic approximates the newsvendor result. Enhancement needed:
- Use `forecast_p90 - forecast_p10` as the volatility signal instead of demand_cv alone
- Add OTRI as a market signal
- When spot/contract cost ratio is available, compute the newsvendor quantile directly

### Gap Severity: **LOW** — directionally correct, needs conformal interval integration

---

## 5. ExceptionManagementTRM

### Canonical Problem
**Multi-criteria decision analysis (MCDA)** for resolution strategy selection + **dynamic job-shop rescheduling with disruptions** for cascading exception handling.

### Industry-Standard Algorithm
**Priority scoring model:**
`Priority = w1×Severity + w2×Financial_Impact + w3×Time_Criticality + w4×Customer_Importance + w5×Cascade_Risk`

Typical weights: Severity 0.25, Financial 0.20, Time 0.30, Customer 0.15, Cascade 0.10. Time criticality is dominant (determines if any resolution is feasible).

**Resolution waterfall (ordered by cost):**
1. Accept and absorb (within tolerance window)
2. Carrier intervention (contact carrier to expedite)
3. Re-tender to backup carrier (routing guide waterfall)
4. Reroute / mode shift
5. Split shipment
6. Expedite (premium service — hot shot, air)
7. Accept delay + notify customer
8. File claim (damage, loss, Carmack Amendment)

**Cascading exception handling:** constraint propagation — identify all shipments sharing resources with excepted shipment, flag as "at risk," re-run scheduling for affected subset.

**Exception taxonomy:** 7–10 categories, 50–200 specific codes (ANSI X12 EDI 214 status codes + NMFC exception codes).

### Current Implementation Review
`_compute_exception_management()` in dispatch.py (lines 327–377):
- ✅ Critical + P1/P2 → immediate re-tender
- ✅ Temperature excursion → escalate immediately
- ✅ Late delivery with time remaining → reroute
- ✅ Minor delay + low priority → accept and monitor
- ✅ Can-retender / alternate carriers check
- ❌ **Missing: composite priority scoring** — uses nested if/else, not weighted score
- ❌ **Missing: financial impact calculation** — `estimated_cost_impact` and `revenue_at_risk` exist on state but unused in triage
- ❌ **Missing: time criticality curve** — `delivery_window_remaining_hrs` used as simple threshold, not sigmoid/exponential ramp
- ❌ **Missing: cascading exception detection** — no check of downstream shipments sharing resources
- ❌ **Missing: resolution cost comparison** — doesn't compare expedite cost vs. penalty exposure
- ❌ **Missing: auto-resolution for tolerance-window exceptions** — no "accept and absorb" path for delays within appointment buffer

### Training Data Implications
Current logic teaches a correct triage tree but misses the scoring nuance. The TRM should learn:
- Continuous priority scoring, not categorical
- Time-criticality as the dominant factor (exponential urgency ramp)
- Financial impact gating (don't re-tender a $200 shipment for a 1-hour delay)
- Tolerance-based auto-close for minor delays

### Gap Severity: **MEDIUM-HIGH** — triage direction is right but missing the scoring model and financial gating

---

## 6. FreightProcurementTRM

### Canonical Problem
**Weighted bipartite matching with sequential fallback** — a variant of the Assignment Problem. Solved in production as a **priority-ranked sequential allocation** (routing guide waterfall), not global optimization.

### Industry-Standard Algorithm
**Carrier waterfall:** Pre-negotiated ranked list per lane from annual RFP/mini-bid. Walk the waterfall:
1. Primary carrier: EDI 204 tender → EDI 990 response (15–60 min window)
2. If declined/timeout: backup #2 receives 204
3. After 3–5 contract carriers exhaust: spot market

**Carrier scoring model:**

| Factor | Weight | Metric |
|---|---|---|
| Cost | 30–40% | $/mile vs. benchmark |
| Service (OTP%) | 20–25% | Trailing 90 days |
| Acceptance rate | 15–20% | 990-accept rate on this lane |
| Allocation compliance | 10–15% | Actual vs. committed volume |
| Capacity availability | 5–10% | Real-time equipment |
| Claims ratio | 5% | Cargo damage per 1,000 loads |

**Market-adjusted heuristics:**
- OTRI > 8–10%: shorten waterfall depth (carriers rejecting anyway)
- OTRI < 4%: extend waterfall (carriers hungry)
- Pickup < 4h: skip waterfall, go direct to spot
- Skip carriers with < 50% trailing acceptance on this lane

### Current Implementation Review
`_compute_freight_procurement()` in dispatch.py (lines 384–433):
- ✅ Tender attempt tracking (attempt 1 → primary, attempt N → backups)
- ✅ Waterfall cascade (primary → sorted backups → spot)
- ✅ Spot rate premium check (30% threshold before escalating)
- ✅ Escalation to broker when waterfall exhausted
- ❌ **Missing: composite carrier scoring** — backups sorted by `.priority`, not by weighted composite
- ❌ **Missing: acceptance-rate gating** — doesn't skip known-decliner carriers
- ❌ **Missing: OTRI/market-tightness adjustment** — no market signal in state or logic
- ❌ **Missing: lead-time rule** — no short-lead-time fast-path to spot
- ❌ **Missing: EDI transaction awareness** — `tender_attempt` tracks position but doesn't model response deadline timing
- ❌ **Missing: rate vs. DAT benchmark comparison** — `dat_benchmark_rate` exists on state but unused

### Training Data Implications
Current logic teaches correct waterfall structure but with naive carrier ranking. The TRM should learn:
- Dynamic re-ranking of waterfall based on carrier composite score
- Market-tightness-adjusted waterfall depth
- Lead-time-aware fast-path decisions
- Benchmark-anchored rate evaluation

### Gap Severity: **HIGH** — waterfall structure correct but scoring model absent, market signals unused

---

## 7. BrokerRoutingTRM

### Canonical Problem
**Newsvendor under incomplete information** — accept a known higher broker price now, or wait for uncertain spot? Also maps to **auction theory** when freight is posted to multiple brokers simultaneously.

### Industry-Standard Algorithm
**Decision waterfall:** Preferred broker panel (pre-vetted, margin-capped 12–18%) → DFM APIs (instant quotes) → Open spot boards (DAT, Truckstop.com)

**Broker scoring:**

| Factor | Weight | Metric |
|---|---|---|
| Reliability-adjusted cost | 35–40% | `rate × (1 + failure_prob × rebooking_premium)` |
| Coverage rate | 20–25% | % of tenders covered on this lane |
| Response time | 15% | Median tender-to-confirm (minutes) |
| Service quality | 10–15% | OTP of assigned carriers |
| Fallthrough rate | 5–10% | % of accepted tenders where broker fails to produce truck |

**Premium thresholds:**
- Accept up to 115–125% of DAT benchmark. Escalate above.
- Tight market (OTRI > 12%): widen to 130–140%
- **Parallel fan-out** is the dominant modern pattern: tender to top 3 panel brokers + 2 DFMs simultaneously, first acceptable quote wins

**Coverage-time urgency scaling:** If pickup < 6h, widen rate threshold by 10%/hour of remaining lead time.

### Current Implementation Review
`_compute_broker_routing()` in dispatch.py (lines 440–498):
- ✅ Reliability-adjusted cost scoring (`expected_cost = rate / reliability`)
- ✅ P1–P2 critical shipments → pick most reliable regardless of cost
- ✅ Premium threshold (40% over contract → escalate)
- ✅ No-brokers-available escalation
- ❌ **Missing: DAT benchmark gating** — threshold is vs. contract rate, not market benchmark
- ❌ **Missing: parallel fan-out** — sequential evaluation, not simultaneous
- ❌ **Missing: coverage-time urgency scaling** — no lead-time-adjusted threshold
- ❌ **Missing: fallthrough rate** — only `reliability` is used, not separate fallthrough metric
- ❌ **Missing: DFM vs. panel vs. spot board channel distinction** — all brokers treated identically
- ❌ **Missing: OTRI-adjusted threshold** — market tightness doesn't widen/narrow premium acceptance

### Training Data Implications
Current logic teaches correct reliability-adjusted scoring. Enhancements:
- Time-urgency-based threshold relaxation
- Market-tightness awareness (loosen/tighten thresholds)
- DAT benchmark anchoring rather than contract-rate anchoring

### Gap Severity: **MEDIUM** — core scoring is sound, market/time adjustments missing

---

## 8. DockSchedulingTRM

### Canonical Problem
**Parallel Machine Scheduling Problem (PMSP)** with time windows — variant of `P|r_j, d_j|C_max`. Production systems use **two-phase**: greedy constructive heuristic (EDD/SPT priority), then improvement via tabu search or simulated annealing.

### Industry-Standard Algorithm
- **Constructive:** priority dispatch rules (Earliest Due Date, Shortest Processing Time, or weighted combination)
- **Improvement:** tabu search or simulated annealing to reduce idle gaps
- **Constraints:** door-equipment compatibility, commodity segregation, live-load vs. drop-trailer, crew availability, staging area capacity
- **Objective:** minimize `detention_cost + door_idle_time + carrier_wait_time`
- **Detention:** industry standard 2h free time, then $50–$100/hour

**Key heuristics:**
- Block scheduling: group similar commodity types into time blocks
- No-show handling: 15-min grace then re-queue; slot released and reassigned
- Detention clock monitoring: flag trucks approaching 2h free-time, bump to next door

### Current Implementation Review
`_compute_dock_scheduling()` in dispatch.py (lines 505–554):
- ✅ Priority-based acceptance (P1–P2 always accommodate)
- ✅ Utilization threshold (>85% defers low-priority)
- ✅ Queue depth → drop-trailer recommendation (depth > 3)
- ✅ Detention risk scoring (`dwell - free_time`) — well-implemented
- ❌ **Missing: door-equipment compatibility matching** — no door type check
- ❌ **Missing: commodity segregation** — no check of food-grade/hazmat separation
- ❌ **Missing: no-show / late arrival re-sequencing** — no slot release logic
- ❌ **Missing: block scheduling** — no time-block grouping by commodity
- ❌ **Missing: staging area capacity** — no check of concurrent unload limits
- ❌ **Missing: crew availability** — no lumper/forklift staffing constraint
- ❌ **Missing: objective function** — single-appointment decision, not schedule optimization

### Training Data Implications
Current logic teaches per-appointment decisions. The TRM should learn:
- Multi-appointment schedule optimization (not just single-truck eval)
- Equipment-door compatibility matching
- Detention prevention as dominant driver (it's the most expensive mistake)

### Gap Severity: **MEDIUM** — detention logic is correct, but scheduling context (multi-door, multi-truck optimization) is missing

---

## 9. LoadBuildTRM

### Canonical Problem
**3D Bin Packing Problem + Shipment Consolidation Problem (Set Partitioning).** Two-stage: (1) cluster shipments by lane/window/commodity compatibility, (2) pack clusters onto equipment maximizing utilization. NP-hard; exact solutions intractable beyond ~50 shipments.

### Industry-Standard Algorithm
Production systems (Oracle OTM, Manhattan Associates) use:
1. **Pooling phase:** greedy clustering — same-lane → adjacent-lane → zone-based
2. **Loading phase:** weight/cube/pallet fill-rate maximization
3. **Multi-stop:** Clarke-Wright savings algorithm for stop sequencing

**FTL vs. LTL decision (industry crossover):**
- Below ~8,000–12,000 lbs or 10–12 linear feet: LTL is cheaper
- Above crossover: FTL or volume-LTL
- Zone-skip consolidation saves 15–30% for LTL

**Consolidation savings:** typically 15–35% vs. individual LTL for FTL consolidation

**Constraints:** weight (44,000 lbs payload max US), volume (3,000 cuft 53-ft), pallets (26 max), hazmat segregation (DOT 49 CFR 177.848), temperature compatibility, delivery window, max stops (3–5), stackability

### Current Implementation Review
`_compute_load_build()` in dispatch.py (lines 561–610):
- ✅ Hazmat and temperature conflict detection
- ✅ Consolidation savings check (`should_consolidate()`)
- ✅ Weight/volume utilization calculation
- ✅ Underutilized → hold for consolidation window
- ✅ Over-capacity → split
- ❌ **Missing: FTL vs. LTL crossover calculation** — no LTL rate comparison, no NMFC class rating
- ❌ **Missing: multi-stop optimization** — no Clarke-Wright savings, no stop sequencing
- ❌ **Missing: density-based packing** — no sort-by-density for balanced weight/cube fill
- ❌ **Missing: delivery window compatibility check** — `has_destination_conflict` exists but no time-window feasibility
- ❌ **Missing: stop-off charge modeling** — multi-stop cost not calculated
- ❌ **Missing: zone-skip consolidation** — no LTL-specific hub-bypass logic
- ❌ **Missing: stackability constraint** — `is_stackable` not in state

### Training Data Implications
Current logic teaches basic consolidate-or-not decisions. The TRM should learn:
- LTL vs. FTL threshold economics
- Multi-stop load sequencing
- Density-aware packing (avoid weight-out-first or cube-out-first)

### Gap Severity: **MEDIUM-HIGH** — basic consolidation correct but missing LTL economics and multi-stop

---

## 10. IntermodalTransferTRM

### Canonical Problem
**Multi-Modal Freight Network Flow** — discrete choice between OTR, intermodal, rail-carload, ocean. Simplified in production to a **cost comparison engine** evaluating pre-defined route templates.

### Industry-Standard Algorithm
Oracle OTM: label-correcting shortest path across a multi-modal graph. SAP TM: route determination engine with pre-defined multi-leg templates. IMCs (J.B. Hunt 360, Hub Group): proprietary door-to-door pricing engines.

**Key thresholds:**
- Distance: intermodal considered at **550+ miles**, sweet spot **800–1,500 miles**
- Cost: must beat OTR by at least 5–10% to justify service tradeoff
- Transit: intermodal adds 1–3 days vs. OTR
- Reliability: intermodal 85–93% OTP vs. OTR 90–95%
- Ramp proximity: >100 miles from ramp kills economics (drayage)

**Drayage estimation:** $250–$500 local (<30mi), $4–$6/mile beyond. Drayage = 25–40% of total intermodal cost.

**All-in cost:** `origin_drayage + ramp_fees + rail_linehaul + dest_drayage + container/chassis_fees`

### Current Implementation Review
`_compute_intermodal_transfer()` in dispatch.py (lines 617–672):
- ✅ Cost savings threshold (>15% → accept)
- ✅ Long-haul distance rule (>800 miles)
- ✅ Transit time feasibility check (`has_time_for_intermodal`)
- ✅ Ramp congestion rejection (>0.7)
- ✅ Reliability + tight delivery → stay on truck
- ✅ Cost savings % calculation
- ❌ **Missing: drayage cost decomposition** — `drayage_rate_origin`/`dest` exist on state but not used in decision
- ❌ **Missing: all-in cost calculation** — uses total intermodal rate vs. truck rate, doesn't decompose drayage/linehaul/fees
- ❌ **Missing: ramp proximity filter** — doesn't check origin/dest distance to nearest ramp
- ❌ **Missing: container balance / directional pricing** — no headhaul vs. backhaul adjustment
- ❌ **Missing: inventory carrying cost** — for high-value goods, transit time penalty has a $ value
- ❌ **Missing: commodity eligibility filter** — no hazmat or temperature restriction check for rail

### Training Data Implications
Current logic teaches correct cost/transit tradeoff. Enhancements:
- Decomposed drayage + linehaul pricing
- Ramp proximity as a hard filter
- Commodity eligibility gating (hazmat, reefer restrictions on rail)

### Gap Severity: **LOW-MEDIUM** — direction correct, needs cost decomposition and commodity gating

---

## 11. EquipmentRepositionTRM

### Canonical Problem
**Dynamic Multi-Commodity Minimum-Cost Network Flow** with stochastic demand — the empty vehicle redistribution problem (EVR). Modeled on a time-space network where nodes are (location, time-period) pairs.

**Minimize:** `Σ reposition_cost × empty_flow + Σ penalty × unmet_demand`

Subject to flow conservation: supply carried forward + inbound empties − outbound empties − loaded departures = demand met + surplus held.

### Industry-Standard Algorithm
- **Oracle OTM:** continuous-move optimizer chains loaded + empty legs into multi-stop tours, minimizing total deadhead via set-covering formulation
- **TMW/TruckMate:** rolling-horizon greedy dispatch via "power board" — nearest-load assignment ranked by deadhead distance
- **McLeod LoadMaster:** load-matching engine scoring by proximity, driver HOS, home-time

**Key heuristics:**
- **Headhaul matching:** before deadheading, search for a revenue load in the desired direction (any revenue > variable cost)
- **Triangle routing:** A→B (loaded) → B→C (loaded) → C→A instead of A→B→A
- **Power-only moves:** reposition tractor only, pick up preloaded trailer at destination
- **ROI threshold:** reposition justified when `(spot_premium_avoided + loaded_revenue) / reposition_cost ≥ 1.5×`. Some carriers use 1.3× for strategic lanes, 2.0× for speculative

**Container-specific:** street turns (skip depot), chassis pools (DCLI, Flexi-Van), per-diem avoidance

**Critical data input:** 7-day demand forecast by location and equipment type. 10% improvement in 72-hour demand accuracy → 3–5% reduction in total deadhead miles.

### Current Implementation Review
`_compute_equipment_reposition()` in dispatch.py (lines 679–739):
- ✅ Source surplus / target deficit calculation
- ✅ ROI-based decision (>1.5× threshold)
- ✅ Fleet utilization urgency (>90% + deficit → urgent)
- ✅ Short-reposition rule (ROI >1.0 and <200 miles)
- ✅ Economic justification (cost vs. spot premium avoided)
- ❌ **Missing: demand forecast integration** — `source_demand_next_7d` and `target_demand_next_7d` on state but the overlay generator sets them to 0
- ❌ **Missing: headhaul matching** — no search for revenue loads in the reposition direction
- ❌ **Missing: triangle routing** — no multi-leg chaining
- ❌ **Missing: power-only option** — no tractor-only reposition path
- ❌ **Missing: container-specific logic** — no street-turn, chassis-pool, per-diem handling
- ❌ **Missing: driver HOS constraint** — no hours-of-service feasibility check
- ❌ **Missing: time-space network formulation** — static snapshot, not rolling-horizon

### Training Data Implications
**Critical:** the heuristic logic is correct but the training data has **demand_next_7d = 0 for all locations**, so the TRM learns that demand is irrelevant to repositioning. This must be fixed before training:
- Compute rolling 7-day shipment volume per site from historical data
- Feed actual demand forecasts into `source_demand_next_7d` and `target_demand_next_7d`

### Gap Severity: **HIGH** (data, not logic) — heuristic is the best-implemented TRM, but training data feeds zeros for the most important input

---

## Summary: Gap Priority Matrix

| TRM | Logic Gaps | Data Gaps | Training Impact | Priority |
|---|---|---|---|---|
| **CapacityPromise** | HIGH (scoring model) | LOW | Teaches flat accept/reject instead of scored waterfall | **P1** |
| **FreightProcurement** | HIGH (scoring, market) | MEDIUM (no OTRI) | Teaches naive waterfall without composite ranking | **P1** |
| **ExceptionManagement** | MED-HIGH (scoring, finance) | LOW | Teaches triage tree without continuous scoring | **P2** |
| **LoadBuild** | MED-HIGH (LTL, multi-stop) | LOW | Misses LTL economics, multi-stop sequencing | **P2** |
| **EquipmentReposition** | LOW (logic good) | **HIGH** (demand=0) | Teaches that demand is irrelevant — most dangerous | **P1 (data)** |
| **DemandSensing** | MEDIUM (signals) | LOW | Misses order pipeline velocity, tracking signal | **P3** |
| **ShipmentTracking** | MEDIUM (ETA fusion) | LOW | ETA too simple, no conformal intervals used | **P3** |
| **BrokerRouting** | MEDIUM (market/time) | LOW | Core scoring sound, needs market context | **P3** |
| **DockScheduling** | MEDIUM (multi-door) | LOW | Per-appointment, not schedule-level | **P3** |
| **IntermodalTransfer** | LOW-MED (decompose) | LOW | Direction correct, cost model needs detail | **P4** |
| **CapacityBuffer** | LOW (close to optimal) | LOW | Needs conformal intervals, otherwise good | **P4** |

### Recommended Fix Order

1. **EquipmentReposition training data** — fix demand signals (zero → actual), most dangerous gap
2. **CapacityPromise heuristic** — add composite carrier scoring model
3. **FreightProcurement heuristic** — add composite scoring + market tightness + acceptance-rate gating
4. **ExceptionManagement heuristic** — add weighted priority scoring + financial gating
5. **LoadBuild heuristic** — add FTL/LTL crossover economics
6. All other TRMs — incremental improvements, lower urgency

---

## References

- Powell, W.B. (1996). "A Stochastic Formulation of the Dynamic Assignment Problem"
- Crainic, T.G., Gendreau, M., Dejax, P. (1993). "Dynamic and Stochastic Models for the Allocation of Empty Containers"
- Clarke, G., Wright, J.W. (1964). "Scheduling of Vehicles from a Central Depot to a Number of Delivery Points"
- ANSI X12 EDI: 204, 214, 990, 210, 492, 852
- NMFC (National Motor Freight Classification)
- FreightWaves SONAR: OTVI, OTRI indices
- DAT RateView / Greenscreens benchmarks
- DOT 49 CFR 177.848 (hazmat segregation)
- ELD mandate FMCSA 395.8
- GS1/VICS CPFR standards
