# Decision Stream Routing: Three-Dimensional Framework

**Date**: 2026-03-18
**Status**: Implemented

---

## 1. Overview

The Decision Stream routes agent decisions through a three-dimensional framework that determines whether each decision is auto-actioned by the agent or surfaced to a human planner for review.

The three dimensions are:

| Dimension | Question | Source | Units |
|-----------|----------|--------|-------|
| **Urgency** | "How fast does the situation deteriorate if I do nothing?" | cost_of_inaction × time_pressure | $/period (normalized 0-1) |
| **Likelihood** | "How confident is the agent that its action will work?" | TRM confidence, CDT risk_bound | 0-1 probability |
| **Benefit** | "What is the net economic gain from this specific action?" | value_created - cost_of_action | $ absolute |

---

## 2. Theoretical Foundation: Kahneman's Prospect Theory

The routing framework is grounded in Daniel Kahneman and Amos Tversky's **Prospect Theory** (1979), which established that:

> **"Losses loom approximately twice as large as gains."**
> — Kahneman, D. & Tversky, A. (1979). "Prospect Theory: An Analysis of Decision under Risk." *Econometrica*, 47(2), 263-291.

### Key implications for decision routing:

1. **Loss aversion**: Human planners instinctively prioritize loss-prevention over gain-capture. A "$10K stockout risk" triggers faster action than a "$10K consolidation savings opportunity" — even though the dollar values are identical. The routing sort order reflects this: **urgency DESC** (losses first), then benefit DESC (gains second).

2. **Urgency ≠ Benefit**: A high-urgency problem with an expensive fix has **low benefit** (loss is large but so is the cost of the recommended action). A low-urgency opportunity with a cheap fix has **high benefit**. Collapsing these into a single score loses information that human planners need.

3. **Reference point framing**: Urgency represents deviation from the current state (loss exposure — the "what if we do nothing?" reference point). Benefit represents the improvement achievable by acting (gain relative to status quo). Prospect Theory predicts planners will weight urgency ~2× more than benefit, which the sort order enforces.

### Further reading:
- Kahneman, D. (2011). *Thinking, Fast and Slow*. Farrar, Straus and Giroux. — Chapters 25-26 on loss aversion in professional decision-making.
- Tversky, A. & Kahneman, D. (1992). "Advances in prospect theory: Cumulative representation of uncertainty." *Journal of Risk and Uncertainty*, 5(4), 297-323.

---

## 3. Urgency: Cost of Inaction × Time Pressure

Urgency answers: *"How bad does it get, how fast, if we do nothing?"*

```
urgency = cost_of_inaction × time_pressure
```

### Cost of Inaction ($/period)
The dollar cost per period of NOT acting. This varies by TRM type:

| TRM | Cost of Inaction Formula |
|-----|------------------------|
| ATP | shortage_qty × unit_price × stockout_penalty_rate |
| PO Creation | P(stockout) × expected_shortage × stockout_cost |
| Inventory Buffer | P(stockout\|current_buffer) × shortage × stockout_cost |
| Rebalancing | deficit_dos_gap × daily_demand × stockout_cost |
| MO Execution | daily_revenue_at_risk (from linked customer orders) |
| TO Execution | dest_shortage_cost_per_day |
| Quality | hold_cost_per_day + opportunity_cost (blocked inventory) |
| Maintenance | breakdown_prob × unplanned_downtime_cost/hr × 24 |
| Subcontracting | capacity_gap × lost_revenue_per_unit_per_day |
| Forecast Adj | forecast_error² × unit_cost × planning_horizon |
| Order Tracking | order_value × delay_penalty_rate |

### Time Pressure (0-1)
How fast the decision window closes:

```
time_pressure = max(0, 1 - days_remaining / decision_horizon)
```

- `1.0` = must act NOW (overdue, customer waiting)
- `0.0` = weeks of runway (routine scheduling)

### Normalization
Raw urgency ($/period × pressure) is normalized to 0-1 for routing by dividing by a scaling constant (default: $1000/day). The raw dollar values are preserved for display.

---

## 4. Likelihood: Agent Confidence

Likelihood answers: *"How confident is the agent that its recommended action will produce a positive outcome?"*

Sources:
- **TRM neural network output**: `confidence` from the model's output head
- **CDT risk_bound**: P(loss > threshold) from conformal decision theory
- **Conformal interval width**: Wide intervals → low confidence
- **Heuristic fallback**: Hard-coded confidence per rule (0.80-0.95)

This dimension is unchanged from the previous 2×2 matrix. It remains the primary gate for auto-actioning: if the agent is sufficiently confident, the decision can execute autonomously.

---

## 5. Benefit: Net Economic Gain

Benefit answers: *"What is the expected dollar value of taking this specific action?"*

```
benefit = value_created_by_action - cost_of_action
```

| TRM | Value Created | Cost of Action | Benefit |
|-----|--------------|----------------|---------|
| ATP | Revenue preserved (fulfillment) | 0 (using existing allocation) | = value created |
| PO Creation | Stockout cost avoided | order_qty × unit_cost + ordering_cost | Avoided cost - procurement |
| Buffer | Expected stockout savings | buffer_increase × holding_cost × review_period | Savings - holding cost |
| Rebalancing | Dest shortage cost avoided | transport_cost + source depletion risk | Dest improvement - costs |
| MO Execution | Revenue from on-time delivery | Expedite premium (if any) | Revenue - premium |
| TO Execution | Revenue preserved | Expedite or consolidation cost | Revenue - cost delta |
| Quality | Best disposition value | Rework/scrap/hold cost | Best option - hold cost |
| Maintenance | Expected breakdown cost avoided | Planned maintenance cost | Avoided cost - PM cost |
| Subcontracting | Capacity recovery value | Outsourcing premium | Recovery - premium |
| Forecast Adj | Forecast error reduction value | ~0 (number change) | = error reduction |
| Order Tracking | Order value preserved | Investigation/remediation cost | Value - remediation |

---

## 6. Routing Logic

### Per-TRM-Type Thresholds

Each tenant can configure thresholds globally (via `tenant_bsc_config`) or per TRM type (via `tenant_decision_thresholds`). Per-TRM overrides take precedence.

| Threshold | Default | Meaning |
|-----------|---------|---------|
| `likelihood_threshold` | 0.70 | Min confidence to auto-action |
| `urgency_threshold` | 0.65 | Above this, surface even if moderately confident |
| `benefit_threshold` | 0.00 | Min $ benefit for auto-action (0 = disabled) |

### Surface Conditions

A decision is surfaced for human review if **any** of these hold:
1. `likelihood < likelihood_threshold` — agent is uncertain
2. `urgency >= urgency_threshold AND likelihood < (likelihood_threshold + 0.15)` — high urgency with only moderate confidence (Kahneman: don't auto-action loss-prevention when confidence is marginal)

### Queue Sort Order (Kahneman-Aligned)
1. **Urgency DESC** — loss prevention before gain capture
2. **Benefit DESC** — highest dollar value items next
3. **Likelihood ASC** — least confident first (where human judgment adds most value)

---

## 7. Database Schema

### Economic Columns on All 11 powell_*_decisions Tables

Added via `HiveSignalMixin`:

| Column | Type | Description |
|--------|------|-------------|
| `cost_of_inaction` | Float, nullable | $/period cost of doing nothing |
| `time_pressure` | Float, nullable | 0-1 how fast the window closes |
| `expected_benefit` | Float, nullable | $ net gain from recommended action |

### Per-TRM Threshold Table

`tenant_decision_thresholds`:

| Column | Type | Description |
|--------|------|-------------|
| `tenant_id` | Integer | FK to tenants |
| `trm_type` | String(50) | One of 11 TRM type keys |
| `urgency_threshold` | Float, nullable | Override (NULL = use tenant default) |
| `likelihood_threshold` | Float, nullable | Override |
| `benefit_threshold` | Float, nullable | Override |

Unique constraint: `(tenant_id, trm_type)`.

---

## 8. Implementation Files

| File | Change |
|------|--------|
| `backend/app/models/powell_decisions.py` | `HiveSignalMixin`: added `cost_of_inaction`, `time_pressure`, `expected_benefit` |
| `backend/app/models/bsc_config.py` | Added `benefit_threshold` to `TenantBscConfig`; new `TenantDecisionThreshold` model |
| `backend/app/services/decision_stream_service.py` | 3D routing logic, per-TRM threshold loading, Kahneman-aligned sort |
| `backend/migrations/versions/20260318_decision_economics.py` | Migration adding columns + table |

---

## 9. Migration Path

The implementation is fully backward-compatible:
- All new columns are nullable — existing decisions continue to work
- When economic columns are NULL, the routing falls back to legacy `urgency_at_time` / `confidence`
- `benefit_threshold` defaults to 0.0 (disabled) — existing tenants see no behavior change
- Per-TRM overrides only apply when rows exist in `tenant_decision_thresholds`

To enable the new routing for a tenant:
1. TRM engines populate `cost_of_inaction`, `time_pressure`, `expected_benefit` at decision time
2. Admin configures per-TRM thresholds via the Decision Stream settings panel
3. Queue sort immediately reflects the three-dimensional ordering
