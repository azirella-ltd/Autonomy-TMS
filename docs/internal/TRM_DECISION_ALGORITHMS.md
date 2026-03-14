# TRM Decision Algorithms — Heuristic Logic, Urgency, and Likelihood

> **Audience**: Engineers implementing, debugging, or extending TRM agents.
> This document specifies the **deterministic heuristic algorithms** for all 11 TRM engines,
> how **urgency** is calculated per TRM, and how **likelihood / confidence** is derived.
> For agent architecture overview, reward functions, and training pipeline see
> [TRM_AGENTS_EXPLAINED.md](TRM_AGENTS_EXPLAINED.md).
> For cross-tier coordination see [GNN_DECISION_ARCHITECTURE.md](GNN_DECISION_ARCHITECTURE.md).

---

## Urgency and Likelihood — Shared Definitions

### What They Mean

**Urgency** (0.0–1.0) — *time-sensitivity of the decision*.
High urgency = something bad happens soon if no action is taken. The clock is ticking.

**Likelihood** (0.0–1.0) — *agent confidence that the recommended action resolves the issue*.
High likelihood = the agent is confident its recommendation is correct.

These two scores drive the Decision Stream routing:

| Urgency | Likelihood | Routing |
|---------|-----------|---------|
| High | Low | **Decision Stream — top priority.** Human judgment needed; time-sensitive + uncertain. |
| High | High | Agent acts autonomously within guardrails (logged, auditable). |
| Low | High | Agent acts autonomously within guardrails (logged). |
| Low | Low | Abandoned — not worth human attention. Available on audit/training pages. |

The Decision Stream sorts by `urgency DESC, likelihood ASC` — the topmost item is always the
most time-sensitive one where the agent is least confident. Abandonment uses:
`urgency + likelihood > 0.5` (configurable threshold). High urgency decisions are never
abandoned regardless of likelihood.

### Urgency Sources (per TRM)

Urgency is computed from **three inputs** that are summed or max-merged per TRM:

1. **Exception severity** — the deterministic engine assigns a severity level (CRITICAL/HIGH/WARNING/INFO)
   that maps directly to a base urgency value.
2. **UrgencyVector state** — the current urgency slot for this TRM, which may have been
   adjusted by Site tGNN (±0.30) or boosted by an upstream HiveSignalBus event.
3. **TRM-specific state** — additional urgency contributions unique to each TRM's domain
   (e.g., ATP: `shortage_qty / requested_qty`; Inventory Buffer: `|multiplier - 1.0| × 2.0`).

### Likelihood Sources

**Deterministic heuristic path** (no trained TRM model):
`likelihood = 1.0` — the heuristic is deterministic; it returns the same answer given the same
inputs. "Confidence" is not meaningful in the frequentist sense. The score is set to 1.0 to
avoid unnecessary escalation for rule-based decisions.

**Trained TRM model path**:
`likelihood = confidence` from the TRM's output head. The TRM network outputs a
`(action, confidence)` tuple. Confidence is typically a sigmoid output over the selected
action class, normalized to [0, 1].

**Conformal Decision Theory (CDT) overlay** (when calibrated):
`risk_bound = P(loss > τ)` is computed from the CDT wrapper. This is mapped to likelihood:
```
likelihood = 1.0 - risk_bound
```
A tight conformal interval (small `risk_bound`) → high likelihood. A wide interval →
low likelihood → escalation to Claude Skills (threshold: `risk_bound > 0.40` by default).

**Escalation routing** (`SiteAgent._should_escalate_to_skills()`):
```python
# CDT-based escalation
if cdt_wrapper.is_calibrated and risk_bound > (1 - skill_escalation_threshold):
    return True  # → Claude Skills

# Confidence-based escalation
if trm_confidence < skill_escalation_threshold:
    return True
```

---

## 1. ATP Executor TRM

**File**: `backend/app/services/powell/atp_executor.py`
**Engine**: `AATPEngine` — Allocated Available-to-Promise

### Deterministic Heuristic Algorithm

```
Input:
  order_priority:   int          [1=highest, 5=lowest]
  requested_qty:    float
  allocation:       {priority → available_qty}

Step 1 — Build consumption sequence:
  sequence = [order_priority]                    # Try own tier first
  for p in range(max_priority, 0, -1):           # Bottom-up (5 → 4 → 3 → ...)
      if p != order_priority:
          sequence.append(p)                      # Append lower priority tiers
  # Never consume above own tier (no element < order_priority in sequence)

Step 2 — Walk sequence, accumulate available:
  available_total = 0
  for tier in sequence:
      available_total += allocation.get(tier, 0)

  shortage_qty = max(0, requested_qty - available_total)
  can_fulfill  = shortage_qty == 0

Step 3 — Determine response:
  if can_fulfill:
      method = FULL_FILL
      promised_qty = requested_qty
  elif available_total > 0:
      method = PARTIAL_FILL
      promised_qty = available_total
  else:
      method = SHORTAGE
      promised_qty = 0
```

### Urgency Calculation

```python
if shortage_qty > 0:
    # Urgency proportional to unfulfilled fraction
    shortage_urgency = min(1.0, shortage_qty / requested_qty)
    urgency = shortage_urgency
    direction = "shortage"
    hive_signal = ATP_SHORTAGE
else:
    urgency = 0.1   # Minimal urgency on successful fill
    direction = "neutral"
    hive_signal = None
```

### Likelihood Calculation

- **Heuristic path**: `likelihood = 1.0` (rule is deterministic)
- **TRM model path**: `likelihood = trm.confidence` (output from fulfillment action head)
- **CDT overlay**: `likelihood = max(0, 1.0 - risk_bound)` when calibrated

### Signal Emitted

`ATP_SHORTAGE(urgency, magnitude=shortage_qty)` → propagates to PO Creation TRM and
Inventory Rebalancing TRM on the HiveSignalBus.

---

## 2. Inventory Rebalancing TRM

**File**: `backend/app/services/powell/inventory_rebalancing_trm.py`
**Engine**: `RebalancingEngine`

### Deterministic Heuristic Algorithm

```
Input:
  site_states:    {site_id → SiteInventoryState(on_hand, committed, in_transit,
                                                 demand_forecast, target_dos,
                                                 stockout_risk, dos)}
  lane_map:       {(source, dest) → LaneConstraints(min_qty, max_qty, lead_time)}

Step 1 — Classify sites:
  for each site:
      available = on_hand - committed
      dos = (available / demand_daily) if demand_daily > 0 else ∞

      if dos > target_dos × 1.5:     category = EXCESS
      elif dos < target_dos × 0.75:  category = DEFICIT
      else:                          category = BALANCED

Step 2 — Score transfer candidates:
  for each (source ∈ EXCESS, dest ∈ DEFICIT):
      if not lane_map[(source, dest)]:  skip  # No lane

      source_excess = available_source - safety_stock_source
      dest_deficit  = safety_stock_dest - available_dest
      transfer_qty  = min(source_excess, dest_deficit)
      transfer_qty  = clamp(transfer_qty, lane.min_qty, lane.max_qty)

      if transfer_qty <= 0:  skip

      # Post-transfer DOS
      source_dos_after = (available_source - transfer_qty) / demand_daily_source
      dest_dos_after   = (available_dest + transfer_qty) / demand_daily_dest

      benefit = stockout_cost × max(0, dest_deficit - transfer_qty)
                - holding_cost × source_excess × lane.lead_time_weeks

      if benefit > min_transfer_benefit:
          candidates.append((source, dest, transfer_qty, benefit))

Step 3 — Sort by benefit descending, yield top candidates.
```

### Urgency Calculation

```python
# Per recommendation:
dest_stockout_risk = site_states[dest].stockout_risk
dos_shortfall = max(0, 1 - dest.dos / dest.target_dos)

urgency = min(1.0, dest_stockout_risk + dos_shortfall)
direction = "relief"   # Rebalancing relieves shortage at destination
hive_signal = REBALANCE_INBOUND(urgency)
```

### Likelihood Calculation

- **Heuristic path**: `likelihood = 1.0`
- **TRM model path**: TRM outputs `(transfer_qty, confidence)`. `likelihood = confidence`.
- **CDT overlay**: Applied when rebalancing CDT wrapper is calibrated from historical
  outcome pairs (DOS improvement measured 24h after transfer completion).

---

## 3. PO Creation TRM

**File**: `backend/app/services/powell/po_creation_trm.py`
**Engine**: `MRPEngine` + `SafetyStockCalculator`

### Deterministic Heuristic Algorithm

#### Step 1 — Assess order need

```
Input:
  inv_position = on_hand + in_transit + on_order - committed - backlog
  safety_stock = SafetyStockCalculator.compute_safety_stock()
  reorder_point = safety_stock + demand_during_lead_time
  forecast_demand = forecast_next_30_days

if inv_position <= 0:
    need = True, trigger = EXPEDITE, severity = CRITICAL

elif inv_position < safety_stock:
    need = True, trigger = INVENTORY_BUFFER, severity = HIGH

elif inv_position <= reorder_point:
    need = True, trigger = REORDER_POINT, severity = NORMAL

elif inv_position - forecast_demand < safety_stock:
    need = True, trigger = FORECAST_DRIVEN, severity = NORMAL

else:
    need = False, trigger = SCHEDULED, severity = LOW
```

#### Step 2 — Evaluate supplier and compute quantity

```
For each supplier (sorted by: priority=primary first, then reliability, then cost):

  effective_lead_time = lead_time_days + z(service_level) × lead_time_variability_days
  demand_during_lt = (forecast_30d / 30) × effective_lead_time
  target_position = demand_during_lt + safety_stock
  quantity = max(0, target_position - current_position)

  # Lot sizing constraints:
  quantity = max(quantity, supplier.min_order_qty)
  quantity = min(quantity, supplier.max_order_qty or ∞)
  if supplier.order_multiple > 0:
      quantity = ceil(quantity / order_multiple) × order_multiple

  # Economic order quantity check:
  if EOQ_configured:
      eoq = sqrt(2 × demand_annual × ordering_cost / holding_cost_per_unit)
      quantity = max(quantity, eoq)
```

#### Step 3 — Select best supplier

```
Score each supplier:
  score = w_reliability × supplier.on_time_rate
        + w_quality × (1 - supplier.defect_rate)
        + w_cost × (1 - supplier.unit_cost / max_unit_cost)
        + w_lead_time × (1 - supplier.lead_time / max_lead_time)

Select highest-scoring supplier with available capacity.
```

### Urgency Calculation

```python
severity_to_urgency = {
    CRITICAL: 0.9,   # Stock-out imminent; expedite NOW
    HIGH:     0.6,   # Below safety stock; urgent PO
    NORMAL:   0.3,   # Below ROP; standard order
    LOW:      0.1,   # Scheduled replenishment
}
urgency = severity_to_urgency[severity]
direction = "shortage" if urgency > 0.3 else "neutral"

if urgency >= 0.6:
    hive_signal = PO_EXPEDITE(urgency)
else:
    hive_signal = PO_DEFERRED(urgency)
```

### Likelihood Calculation

- **Heuristic path**: `likelihood = 1.0`
- **TRM model path**: TRM outputs `(order_decision, quantity, confidence)`.
  `likelihood = confidence` on the order_decision head.
- **CDT overlay**: Calibrated from 7-day outcome window (PO receipt vs. stockout event).

---

## 4. Order Tracking TRM

**File**: `backend/app/services/powell/order_tracking_trm.py`
**Engine**: `OrderTrackingEngine`

### Deterministic Heuristic Algorithm

Six threshold rules evaluated in priority order (first match wins):

```
Rule 1: STUCK_IN_TRANSIT
  Condition: status == IN_TRANSIT
             AND days_in_transit > typical_transit_days × 2.0
  Severity:  CRITICAL
  Action:    ESCALATE (contact carrier + customer notification)

Rule 2: MISSING_CONFIRMATION
  Condition: status == CREATED
             AND days_since_created > confirmation_timeout_days (default 2.0)
  Severity:  HIGH
  Action:    CONTACT_SUPPLIER

Rule 3: LATE_DELIVERY
  Condition: days_until_expected < -late_threshold_days (default -2.0)
  Severity:  WARNING if 2–5 days late
             HIGH if 5–10 days late
             CRITICAL if >10 days late
  Action:    WARNING → MONITOR
             HIGH → EXPEDITE
             CRITICAL → FIND_ALTERNATE

Rule 4: EARLY_DELIVERY
  Condition: days_until_expected > early_threshold_days (default 3.0)
  Severity:  INFO
  Action:    ADJUST_SCHEDULE (notify warehouse)

Rule 5: QUANTITY_SHORTAGE
  Condition: received_qty / ordered_qty < (1 - quantity_variance_threshold)
             (default threshold: 0.05 → accept ≥95%)
  Severity:  WARNING if fill rate 90–95%
             HIGH if fill rate < 90%
  Action:    WARNING → PARTIAL_RECEIPT
             HIGH → FIND_ALTERNATE or CANCEL_REORDER

Rule 6: PRICE_VARIANCE
  Condition: |actual_price - expected_price| / expected_price > price_variance_threshold
             (default 0.10 → ±10%)
  Severity:  WARNING if 10–20% variance
             HIGH if >20% variance
  Action:    REVIEW_PRICING

Default (no exception detected):
  Severity:  INFO
  Action:    CONTINUE_MONITORING
```

### TRM Heuristic Refinements

Applied after engine detection:

```python
# Severity escalation if downstream inventory is low:
if exception_type in (LATE_DELIVERY, STUCK_IN_TRANSIT):
    if downstream_dos < 3.0 and severity < CRITICAL:
        severity = CRITICAL
        recommended_action = FIND_ALTERNATE

# Action refinement based on supplier track record:
if recommended_action == EXPEDITE and partner_on_time_rate < 0.70:
    recommended_action = FIND_ALTERNATE   # Expediting unreliable supplier rarely works

# Escalation for recurring issues:
if recurring_exception_count >= 3:
    requires_escalation = True
```

### Urgency Calculation

```python
severity_urgency = {
    CRITICAL: 0.9,
    HIGH:     0.7,
    WARNING:  0.4,
    INFO:     0.1,
}
urgency = severity_urgency[severity]

# Boost if order is customer-facing:
if order_type == CUSTOMER_ORDER:
    urgency = min(1.0, urgency + 0.1)

direction = "shortage" if urgency > 0.5 else "risk"
hive_signal = ORDER_EXCEPTION(urgency, exception_type)
```

### Likelihood Calculation

- **Heuristic path**: `likelihood = 1.0`
- **TRM model path**: `likelihood = trm.confidence` on the recommended action class.
- **CDT overlay**: Calibrated from exception-resolution outcome pairs (was the exception
  resolved by the recommended action within the tracking horizon?).

---

## 5. MO Execution TRM

**File**: `backend/app/services/powell/mo_execution_trm.py`
**Engine**: `MOExecutionEngine` + `SetupMatrix` (Glenday Sieve + nearest-neighbor)

### Deterministic Heuristic Algorithm

#### Step 1 — Material and capacity readiness

```
material_ready = material_availability_pct >= material_threshold (default 0.95)
capacity_available = queue_total_hours + setup_time_hours + run_time_hours
                     <= available_capacity_hours × capacity_threshold (default 0.85)
```

#### Step 2 — Release / defer / expedite decision

```
if NOT material_ready:
    decision_type = DEFER
    defer_reason = AWAITING_COMPONENTS
    defer_days = estimated_material_arrival_days

elif NOT capacity_available:
    decision_type = DEFER
    defer_reason = CAPACITY_CONSTRAINT
    defer_days = estimated_capacity_gap_days

elif days_until_due <= setup_time_hours/8 + run_time_hours/8:
    decision_type = EXPEDITE
    release_now = True

else:
    decision_type = RELEASE
    release_now = True
```

#### Step 3 — Sequence optimization (when releasing)

```
Phase 1 — Glenday Sieve classification:
  Sort all MOs by historical production volume (cumulative).
  top_6pct_volume_skus = "Green"  (typically ~6% of SKUs = ~50% of volume)
  next_segment = "Yellow", then "Red", then "Blue"
  Green MOs get dedicated capacity windows; scheduled first.

Phase 2 — Nearest-neighbor changeover minimization:
  remaining = MOs not pinned by urgency or Glenday
  sequence = [current_product]
  while remaining:
      next_mo = argmin_{mo ∈ remaining} setup_matrix[current → mo.product]
      sequence.append(next_mo)
      current = next_mo.product

Urgency overrides:
  MOs with days_until_due ≤ 3 OR priority ∈ {1, 2} are pinned to front
  regardless of changeover cost.
```

#### Step 4 — TRM heuristic adjustments

```python
# Customer commitment urgency override:
if mo.customer_order_linked and days_until_due <= 5 and mo.priority > 2:
    priority_override = 2
    expedite = True

# Quantity overage for low-yield products:
if avg_yield < 0.90 and planned_qty > 100:
    yield_overage = planned_qty × (1 - avg_yield) × 1.2
    suggested_qty = planned_qty + yield_overage
```

### Urgency Calculation

```python
if decision_type in (RELEASE, EXPEDITE):
    # Urgency from priority tier (priority 1 → urgency 1.0, priority 5 → urgency 0.2)
    urgency = min(1.0, (5 - priority) / 4.0)
    direction = "relief"
    hive_signal = MO_RELEASED(urgency)

elif decision_type == DEFER:
    # Urgency from downstream service risk
    service_risk = 1.0 - material_availability_pct  # or capacity-based risk
    urgency = min(1.0, 0.4 + service_risk × 0.6)
    direction = "risk"
    hive_signal = MO_DELAYED(urgency)
```

### Likelihood Calculation

- **Heuristic path**: `likelihood = 1.0`
- **TRM model path**: TRM refines sequence position (max ±3 from engine baseline).
  `likelihood = trm.confidence` on the sequence/release action.
- **CDT overlay**: Calibrated from on-time delivery outcomes (7-day window).

---

## 6. TO Execution TRM

**File**: `backend/app/services/powell/to_execution_trm.py`
**Engine**: `TOExecutionEngine`

### Deterministic Heuristic Algorithm

```
Input:
  source.on_hand, source.dos, source.safety_stock
  dest.dos, dest.backlog, dest.demand_forecast
  days_until_needed, lane.transit_time_days, lane.transit_variability

Step 1 — Source readiness:
  source_available = source.on_hand - source.safety_stock
  source_dos_after = (source_available - planned_qty) / source.daily_demand
  source_safe = source_dos_after >= min_source_dos (default 3 days)

Step 2 — Destination urgency:
  dest_urgent = dest.dos < target_dos AND dest.backlog > 0

Step 3 — Release decision:
  if NOT source_safe:
      decision_type = DEFER
      defer_reason = SOURCE_DEPLETION_RISK

  elif dest_urgent AND source.dos > 7:
      decision_type = RELEASE_NOW

  elif days_until_needed <= lane.transit_time_days + 1:
      decision_type = RELEASE_NOW

  else:
      decision_type = SCHEDULE   # Release on planned date

Step 4 — Expedite decision (applied after release):
  if lane.transit_variability > 0.30 AND days_until_needed <= transit_time + 2:
      expedite = True   # Use premium/priority carrier

Step 5 — Consolidation check (within 24-hour window):
  if other_TOs exist for same lane within 24h AND consolidation_savings > 10%:
      consolidate_with = [list of TO IDs]
```

### Urgency Calculation

```python
if decision_type == RELEASE_NOW:
    urgency = min(1.0, (5 - priority) / 4.0)
    direction = "relief"
    hive_signal = TO_RELEASED(urgency)

elif decision_type == DEFER:
    dest_stockout_risk = max(0.0, 1.0 - dest.dos / target_dos)
    urgency = min(1.0, 0.3 + dest_stockout_risk × 0.7)
    direction = "risk"
    hive_signal = TO_DELAYED(urgency)
```

### Likelihood Calculation

- **Heuristic path**: `likelihood = 1.0`
- **TRM model path**: TRM adds transit variability awareness and alternative route scoring.
  `likelihood = trm.confidence`.
- **CDT overlay**: Calibrated from on-time delivery outcomes (transit_time + 2 day window).

---

## 7. Quality Disposition TRM

**File**: `backend/app/services/powell/quality_disposition_trm.py`
**Engine**: `QualityEngine`

### Deterministic Heuristic Algorithm

```
Input:
  defect_rate, severity_level: "minor" | "major" | "critical"
  defect_count, characteristics_passed / characteristics_tested
  rework_cost / unit_value, rework_success_rate
  vendor_quality_score, vendor_recent_reject_rate
  pending_customer_orders (bool), days_of_supply

Step 1 — Auto-accept / auto-reject thresholds:
  if defect_rate < accept_threshold (default 0.01):
      disposition = ACCEPT

  elif severity_level == CRITICAL:
      disposition = REJECT

  elif defect_count > reject_major_count (default 3) AND severity == MAJOR:
      disposition = REJECT

Step 2 — Rework evaluation:
  elif rework_cost / unit_value < rework_cost_ceiling (default 0.30):
      if rework_success_rate >= 0.80:
          disposition = REWORK
      else:
          disposition = SCRAP

Step 3 — Scrap threshold:
  elif scrap_cost / unit_value < scrap_cost_ceiling (default 0.50):
      disposition = SCRAP

  else:
      disposition = REJECT

Step 4 — Use-as-is consideration (TRM heuristic override):
  if disposition == ACCEPT AND defect_rate > 0.005:
      if use_as_is_complaint_rate > 0.10:  disposition = REWORK or REJECT
```

#### TRM Heuristic Overrides

```python
# Return to vendor for chronically poor suppliers:
if vendor_recent_reject_rate > 0.15 and severity_level != "minor":
    disposition = "return_to_vendor"

# Prevent use-as-is if historical complaints are high:
if disposition == "use_as_is" and use_as_is_complaint_rate > 0.10:
    if rework_cost / unit_value < 0.30:
        disposition = "rework"
    else:
        disposition = "reject"

# Skip rework if historically ineffective:
if rework_success_rate < 0.70:
    if defect_rate > 0.10:
        disposition = "scrap"
    else:
        disposition = "reject"

# Inventory pressure check (loosen threshold if stockout risk is high):
if pending_customer_orders and dos < 2.0 and defect_rate < 0.03:
    if disposition == "reject":
        disposition = "use_as_is"   # Accept under scarcity; flag for review
```

### Urgency Calculation

```python
severity_urgency = {
    "minor":    0.3,
    "major":    0.6,
    "critical": 0.9,
}
urgency = severity_urgency[severity_level]

if disposition in ("reject", "scrap"):
    hive_signal = QUALITY_REJECT(urgency)
elif disposition == "rework":
    urgency = urgency × 0.7   # Rework reduces urgency (action taken)
    hive_signal = QUALITY_HOLD(urgency)
elif disposition == "return_to_vendor":
    hive_signal = QUALITY_REJECT(urgency)   # Same priority as reject
```

### Likelihood Calculation

- **Heuristic path**: `likelihood = 1.0`
- **TRM model path**: TRM outputs disposition class probabilities. `likelihood = softmax_max`.
- **CDT overlay**: Calibrated from quality escape outcomes (was the disposition correct?
  Measured as: no downstream complaint within 30 days for accept/use_as_is; rework success
  rate for rework; returns processed for return_to_vendor).

---

## 8. Maintenance Scheduling TRM

**File**: `backend/app/services/powell/maintenance_scheduling_trm.py`
**Engine**: `MaintenanceEngine`

### Deterministic Heuristic Algorithm

```
Input:
  days_overdue, defer_count, asset_criticality, historical_breakdown_rate_after_defer
  asset_age_years, mtbf_days, recent_failure_count
  production_schedule_load_pct, next_production_gap_days
  estimated_downtime, spare_parts_available

Step 1 — Override threshold check (engine prevents deferral if):
  if defer_count >= max_defer_count (default 2):          defer_blocked = True
  if days_overdue > mtbf × overdue_fraction (default 0.3): defer_blocked = True
  if asset_criticality == CRITICAL:                        defer_blocked = True
  if recent_failure_count >= 2:                            defer_blocked = True

Step 2 — Calculate defer risk (0–1):
  if defer_count > 0:
      defer_risk = min(1.0,
          (days_overdue / mtbf_days) × 0.4
          + (recent_failure_count / 3) × 0.3
          + ((asset_age_years / design_life_years) × 0.2)
          + (defer_count / max_defer_count × 0.1)
      )

Step 3 — Decision:
  if defer_blocked OR defer_risk >= risk_threshold (default 0.30):
      decision_type = SCHEDULE
      preferred_date = next_production_gap within 14 days

  elif production_load > 0.85 AND next_production_gap_days > 3:
      decision_type = DEFER
      defer_to_date = next_production_gap_date

  elif can_combine (similar asset, same window, saves >= 15%):
      decision_type = COMBINE

  elif outsource_cost < own_cost × outsource_ceiling (default 1.5):
      decision_type = OUTSOURCE

  else:
      decision_type = SCHEDULE
```

#### TRM Heuristic Override

```python
# Override defer to schedule if historical breakdown rate is high:
if decision_type == "defer" and historical_breakdown_rate_after_defer > 0.30:
    decision_type = "schedule"

# Cost estimate correction using historical ratio:
estimated_cost = engine_cost_estimate × avg_actual_vs_estimated_ratio
```

### Urgency Calculation

```python
if decision_type in ("schedule", "expedite"):
    urgency = min(1.0, 0.3 + defer_risk × 0.7)
    direction = "risk"
    hive_signal = MAINTENANCE_URGENT(urgency) if urgency > 0.6 else MAINTENANCE_DUE(urgency)

elif decision_type == "defer":
    urgency = min(1.0, 0.2 + defer_risk × 0.5)
    direction = "neutral"
    hive_signal = MAINTENANCE_DEFERRED(urgency)
```

### Likelihood Calculation

- **Heuristic path**: `likelihood = 1.0`
- **TRM model path**: `likelihood = trm.confidence` on the schedule/defer decision.
- **CDT overlay**: Calibrated from breakdown-after-defer outcomes (14-day window).

---

## 9. Subcontracting TRM

**File**: `backend/app/services/powell/subcontracting_trm.py`
**Engine**: `SubcontractingEngine`

### Deterministic Heuristic Algorithm

```
Input:
  internal_capacity_pct, internal_cost, internal_lead_time, internal_quality_yield
  subcontractor: {cost, lead_time, quality_score, on_time_score}
  is_critical_product, has_special_tooling, ip_sensitivity
  required_quantity

Step 1 — Internal capacity check:
  if internal_capacity_pct < capacity_threshold (default 0.90):
      capacity_constrained = False   # Plenty of internal capacity
  else:
      capacity_constrained = True    # Consider subcontracting

Step 2 — Subcontractor qualification check:
  vendor_qualified = (
      vendor.quality_score >= quality_floor (default 0.85)
      AND vendor.on_time_rate >= otp_floor (default 0.80)
  )

Step 3 — Make-vs-buy decision:
  if NOT capacity_constrained AND NOT vendor_saves_cost:
      decision_type = KEEP_INTERNAL

  elif NOT vendor_qualified:
      decision_type = KEEP_INTERNAL

  elif ip_sensitivity == HIGH AND vendor.quality_score < 0.95:
      decision_type = KEEP_INTERNAL

  elif vendor.cost < internal_cost × (1 - savings_threshold (0.10)):
      decision_type = ROUTE_EXTERNAL

  elif capacity_constrained AND vendor.cost < internal_cost × 1.20:
      # Accept up to 20% premium for capacity relief
      decision_type = ROUTE_EXTERNAL

  elif capacity_constrained:
      # Split: fill internal capacity, route overflow external
      internal_qty = round(required_qty × internal_available_pct)
      external_qty = required_qty - internal_qty
      decision_type = SPLIT
```

#### TRM Heuristic Overrides

```python
# Quality/reliability overrides:
if vendor_historical_reject_rate > 0.10 or vendor_historical_late_rate > 0.20:
    if decision_type in ("route_external", "split"):
        decision_type = "keep_internal"

# Critical product protection:
if is_critical_product and vendor.quality_score < 0.92:
    decision_type = "keep_internal"
```

### Urgency Calculation

```python
if decision_type in ("route_external", "split"):
    delivery_risk = max(0, 1 - vendor.on_time_rate)
    urgency = min(1.0, 0.3 + delivery_risk × 0.5)
    direction = "relief" if delivery_risk < 0.3 else "risk"
    hive_signal = SUBCONTRACT_ROUTED(urgency)

elif decision_type == "keep_internal":
    urgency = min(1.0, internal_capacity_pct × 0.5)
    direction = "risk" if internal_capacity_pct > 0.90 else "neutral"
```

### Likelihood Calculation

- **Heuristic path**: `likelihood = 1.0`
- **TRM model path**: `likelihood = trm.confidence` on the routing decision.
- **CDT overlay**: Calibrated from delivery outcome pairs (quality + OTP for the routed
  quantity, measured at receipt).

---

## 10. Forecast Adjustment TRM

**File**: `backend/app/services/powell/forecast_adjustment_trm.py`
**Engine**: `ForecastAdjustmentEngine`

### Deterministic Heuristic Algorithm

```
Input:
  signal_type, source, direction, confidence (0–1), magnitude_hint (optional)
  current_forecast, historical_forecast_accuracy
  source_historical_accuracy, signal_type_historical_accuracy
  product_volatility_cv, product_trend, seasonality_factor

Step 1 — Filter low-confidence signals:
  if signal_confidence < min_confidence (default 0.30):
      should_adjust = False
      STOP

Step 2 — Base adjustment percentage by signal type:
  signal_type_multipliers = {
      "demand_increase":    0.15,   # +15% base
      "demand_decrease":    0.15,
      "supply_disruption":  0.35,   # Disruptions warrant larger adjustments
      "lead_time_change":   0.10,
      "discontinuation":    0.50,   # Full product exit
      "new_product":        0.20,
  }
  base_adj_pct = signal_type_multipliers.get(signal_type, 0.10)

Step 3 — Source reliability weighting:
  source_weights = {
      "email":                0.50,
      "market_intelligence":  0.80,
      "competitor_action":    0.60,
      "customer_feedback":    0.70,
      "news":                 0.40,
  }
  adj_pct = base_adj_pct × source_weights.get(source, 0.50)

Step 4 — Confidence scaling:
  adj_pct = adj_pct × signal_confidence   # Scale by signal confidence

Step 5 — Magnitude hint override:
  if magnitude_hint is not None:
      adj_pct = clamp(magnitude_hint, 0, max_adjustment_pct=0.50)

Step 6 — Apply:
  should_adjust = True
  auto_applicable = signal_confidence >= 0.80
```

#### TRM Heuristic Refinements

```python
# Apply learned source reliability (Bayesian posterior):
learned_reliability = config.learned_source_reliability.get(source)
if learned_reliability:
    adj_pct *= learned_reliability

# Dampen historically inaccurate sources:
if source_historical_accuracy < 0.50 and source_historical_accuracy > 0:
    adj_pct *= source_historical_accuracy

# High-volatility products require stronger signals:
if product_volatility_cv > 0.50 and adj_pct < 0.10:
    should_adjust = False   # Signal too weak for volatile product

# Trend alignment check:
if direction == "up" and product_trend < -0.10:
    adj_pct *= 0.70   # Reduce if signal contradicts established downward trend
elif direction == "down" and product_trend > 0.10:
    adj_pct *= 0.70   # Reduce if signal contradicts established upward trend
```

### Urgency Calculation

```python
# Urgency proportional to adjustment magnitude:
urgency = min(1.0, abs(adj_pct) × 2.0)
# E.g.: 15% adjustment → urgency 0.30; 50% → urgency 1.0

if direction == "up":
    direction_label = "surplus"   # "We're about to be short"
elif direction == "down":
    direction_label = "shortage"  # "We're going to have excess"
else:
    direction_label = "neutral"

hive_signal = FORECAST_ADJUSTED(urgency, adj_pct, direction)
```

### Likelihood Calculation

- **Heuristic path**: `likelihood = signal_confidence` — the signal confidence IS the
  likelihood for the heuristic. This is the only TRM where likelihood ≠ 1.0 on the
  heuristic path, because the heuristic itself is probabilistic (signal quality varies).
- **TRM model path**: `likelihood = trm.confidence` on the should_adjust/direction decision.
- **CDT overlay**: Calibrated from forecast accuracy improvement outcomes (measured as:
  did the adjusted forecast outperform the unadjusted baseline over the signal's time horizon?).

---

## 11. Inventory Buffer TRM

**File**: `backend/app/services/powell/inventory_buffer_trm.py`
**Engine**: `SafetyStockCalculator`
*(Renamed from SafetyStockTRM, Feb 2026 — see CLAUDE.md Terminology Note)*

### Deterministic Heuristic Algorithm

```
Input:
  baseline_ss        = SafetyStockCalculator.compute_safety_stock()
  recent_stockout_count  (rolling 90-day count)
  recent_excess_days     (days with DOS > 2 × target in last 60 days)
  demand_cv, demand_trend
  seasonal_index     (current period demand / annual average)
  month_of_year
  forecast_bias      = (forecast - actual) / actual  (rolling 90-day)

Step 1 — Determine multiplier (first matching rule wins):

  if recent_stockout_count >= 3:        multiplier = 1.40, reason = RECENT_STOCKOUT
  elif recent_stockout_count >= 1:      multiplier = 1.20, reason = RECENT_STOCKOUT

  elif demand_cv > 0.50:                multiplier = 1.30, reason = HIGH_VOLATILITY
  elif demand_cv > 0.30:                multiplier = 1.15, reason = HIGH_VOLATILITY

  elif seasonal_index > 1.30:           multiplier = 1.20, reason = SEASONAL_PEAK
  elif seasonal_index < 0.70:           multiplier = 0.80, reason = SEASONAL_TROUGH

  elif demand_trend > 0.10:             multiplier = 1.10, reason = TREND_UP
  elif demand_trend < -0.10:            multiplier = 0.90, reason = TREND_DOWN

  elif recent_excess_days > 60:         multiplier = 0.85, reason = EXCESS_INVENTORY

  elif abs(forecast_bias) > 0.15:
      # Upward bias (we over-forecast): reduce buffer; downward bias: increase
      multiplier = 1.0 - min(0.30, -forecast_bias)
      reason = FORECAST_BIAS

  else:                                 multiplier = 1.00, reason = NO_ADJUSTMENT

Step 2 — Apply Site tGNN modulation:
  # Site tGNN provides _tgnn_ss_multiplier (0.5–2.0 scaling of bounds)
  lo = 0.50 × _tgnn_ss_multiplier   # Lower bound on multiplier
  hi = 2.00 × _tgnn_ss_multiplier   # Upper bound on multiplier
  multiplier = clamp(multiplier, lo, hi)

Step 3 — Compute adjusted buffer:
  adjusted_ss = baseline_ss × multiplier
  adjusted_rop = baseline_rop × multiplier
  adjusted_target = baseline_target × multiplier
```

### Urgency Calculation

```python
if multiplier > 1.05:
    # Increasing buffer: shortage risk detected
    urgency = min(1.0, (multiplier - 1.0) × 2.0)
    # E.g.: multiplier=1.40 → urgency = 0.80
    direction = "shortage"
    hive_signal = BUFFER_INCREASED(urgency, magnitude=adjusted_ss - baseline_ss)

elif multiplier < 0.95:
    # Decreasing buffer: excess detected
    urgency = min(1.0, (1.0 - multiplier) × 2.0)
    # E.g.: multiplier=0.80 → urgency = 0.40
    direction = "surplus"
    hive_signal = BUFFER_DECREASED(urgency, magnitude=baseline_ss - adjusted_ss)

else:
    urgency = 0.0
    direction = "neutral"
    # No signal emitted
```

### Likelihood Calculation

- **Heuristic path**: `likelihood = 1.0`
- **TRM model path**: TRM outputs `(multiplier, confidence)`. `likelihood = confidence`.
- **CDT overlay**: Calibrated from 14-day buffer effectiveness outcomes (stockout events
  and excess days in the 14 days following the buffer adjustment).

---

## UrgencyVector and HiveSignalBus Interaction

All 11 TRMs share a site-level `UrgencyVector` and `HiveSignalBus`. The interaction flow:

```
Phase 0 (SENSE):
  Each TRM reads:
    - Its current UrgencyVector slot (may have been adjusted by Site tGNN)
    - Recent signals on HiveSignalBus relevant to its domain

Phase 4 (BUILD):
  Each TRM makes its decision and updates:
    - UrgencyVector.update(trm_name, urgency, direction)
    - HiveSignalBus.emit(HiveSignal(...))

Between cycles (hourly):
  Site tGNN reads all 11 UrgencyVector slots as input features
  → outputs urgency_adjustment[11] ∈ [-0.30, +0.30]
  → UrgencyVector.adjust(trm_name, delta) applied to all slots
```

**Example cross-TRM propagation** (ATP shortage → PO Creation):

```
Cycle N:
  ATPExecutorTRM: order cannot be fulfilled
  → urgency = 0.70, signal = ATP_SHORTAGE(magnitude=150 units)
  → UrgencyVector["atp_executor"] = 0.70

  POCreationTRM (same cycle): reads ATP_SHORTAGE from bus
  → boosts reorder point estimate by 10%
  → places urgent order

Hourly Site tGNN update:
  Sees ATP urgency=0.70, PO urgency=0.30
  → urgency_adjustment["po_creation"] = +0.15
  → urgency_adjustment["atp_executor"] = -0.05 (order placed, relieve ATP urgency)

Cycle N+1:
  ATPExecutorTRM: UrgencyVector reads 0.65 (reduced by tGNN)
  POCreationTRM: UrgencyVector reads 0.45 (boosted by tGNN)
  → PO decision takes higher priority in decision cycle
```

---

## Decision Persistence Summary

| TRM | Table | Key state columns | Key outcome columns |
|-----|-------|-------------------|---------------------|
| ATP Executor | `powell_atp_decisions` | `priority`, `requested_qty`, `promised_qty`, `method` | `actual_shortfall`, `actual_fill_rate` |
| Rebalancing | `powell_rebalance_decisions` | `source_dos_before`, `dest_dos_before`, `transfer_qty` | `dest_dos_after`, `stockout_prevented` |
| PO Creation | `powell_po_decisions` | `trigger_reason`, `inv_position`, `supplier_id`, `order_qty` | `receipt_qty`, `receipt_date`, `stockout_event` |
| Order Tracking | `powell_order_exceptions` | `exception_type`, `severity`, `recommended_action` | `resolved`, `resolution_days` |
| MO Execution | `powell_mo_decisions` | `decision_type`, `sequence_position`, `priority` | `actual_completion_date`, `yield_actual` |
| TO Execution | `powell_to_decisions` | `decision_type`, `dest_stockout_risk`, `consolidate_with` | `actual_transit_days`, `dest_dos_after` |
| Quality | `powell_quality_decisions` | `disposition`, `defect_rate`, `severity` | `complaint_rate_after`, `rework_success` |
| Maintenance | `powell_maintenance_decisions` | `decision_type`, `defer_risk`, `breakdown_probability` | `breakdown_occurred`, `actual_cost` |
| Subcontracting | `powell_subcontracting_decisions` | `routing_decision`, `external_pct` | `vendor_otp_actual`, `quality_actual` |
| Forecast Adj | `powell_forecast_adjustment_decisions` | `adjustment_pct`, `source`, `direction` | `forecast_accuracy_improvement` |
| Inventory Buffer | `powell_buffer_decisions` | `multiplier`, `reason`, `demand_cv` | `stockout_count_after`, `excess_days_after` |

Outcome collection schedule: hourly at `:32` via `OutcomeCollectorService.collect_trm_outcomes()`.

---

## See Also

- [TRM_AGENTS_EXPLAINED.md](TRM_AGENTS_EXPLAINED.md) — Architecture, state vectors, action spaces, reward functions, training pipeline
- [GNN_DECISION_ARCHITECTURE.md](GNN_DECISION_ARCHITECTURE.md) — Site tGNN, Network tGNN, S&OP GraphSAGE decision algorithms
- [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md) — Hive signal bus, urgency vector, decision cycle phases
- [AGENT_TRAINING_LIFECYCLE.md](AGENT_TRAINING_LIFECYCLE.md) — Training pipeline, stochastic variables, oracle-based data generation
- [ESCALATION_ARCHITECTURE.md](ESCALATION_ARCHITECTURE.md) — When TRM urgency/CDT triggers escalation to higher tiers
