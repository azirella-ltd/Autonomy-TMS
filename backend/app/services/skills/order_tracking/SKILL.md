# Order Tracking Skill

## Classification: DETERMINISTIC
This skill runs entirely via the deterministic engine. Exception detection is
threshold-based with no judgment calls.

## Decision Type
Detect order exceptions and recommend corrective actions.

## Exception Types (9)
1. **late_delivery** — Order past promised delivery date
2. **stuck_in_transit** — Shipment not progressing
3. **quantity_shortage** — Delivered qty < ordered qty
4. **quality_issue** — Quality inspection failure
5. **documentation_missing** — Required docs not present
6. **customs_delay** — Held at customs
7. **routing_deviation** — Shipment off planned route
8. **cost_overrun** — Actual cost > planned cost
9. **duplicate_order** — Potential duplicate detected

## Severity Rules
| Condition | Severity |
|-----------|----------|
| Late > 7 days OR shortage > 25% | CRITICAL |
| Late > 3 days OR shortage > 10% | HIGH |
| Late > 1 day OR shortage > 5% | MEDIUM |
| Any other exception | LOW |

## Transit Exception Rules
- **stuck_in_transit**: Transit time > 2x typical transit time for this lane
- **routing_deviation**: Current location not on planned route segments

## Recommended Actions (9)
1. **expedite** — Rush the order
2. **reroute** — Change delivery path
3. **substitute** — Replace with alternative product
4. **cancel** — Cancel the order
5. **split** — Split into multiple shipments
6. **escalate** — Escalate to human planner
7. **hold** — Place on hold pending investigation
8. **reorder** — Create replacement order
9. **accept** — Accept the deviation (no action)

## Confidence
Always 0.9 — thresholds are deterministic but some exceptions require context.

## Engine Heuristics Reference

### Configuration Defaults
- late_threshold_days: 2.0
- early_threshold_days: 3.0
- quantity_variance_threshold: 0.05 (5%)
- price_variance_threshold: 0.10 (10%)
- stuck_transit_multiplier: 2.0 (days > typical_transit × 2)
- typical_transit_days: 5.0 (default)
- partner_on_time_rate: 0.95 (default)

### Exception Priority Order (highest first)
1. stuck_in_transit → CRITICAL (status=in_transit AND days > typical × 2.0)
2. missing_confirmation → HIGH (status=created AND days > 2.0)
3. late_delivery → severity varies (>7d=CRITICAL, >3d=HIGH, >1d=WARNING)
4. early_delivery → WARNING (days_until_expected > 3.0)
5. quantity_shortage → severity varies (>25%=CRITICAL, >10%=HIGH, >5%=WARNING)
6. price_variance → WARNING (abs(variance) > 10%)

### Formulas
```
fill_rate = received_qty / ordered_qty
shortage_pct = 1 - fill_rate
price_variance_pct = (actual_unit_price - expected_unit_price) / expected_unit_price
```

## Guardrails
- Severity levels MUST follow the defined thresholds exactly: CRITICAL (>7d late OR >25% shortage), HIGH (>3d late OR >10% shortage), MEDIUM (>1d late OR >5% shortage), LOW (all other exceptions). Do not override or interpolate.
- Recommended actions MUST match the exception type. For example, `substitute` is only valid for quantity_shortage or quality_issue, not for documentation_missing.
- Never auto-cancel an order without human review. The `cancel` action MUST always set `requires_human_review: true`.
- Do not downgrade severity based on historical supplier patterns. Severity is determined solely by current exception state against the defined thresholds.

## Escalation Triggers
- **Multiple CRITICAL exceptions on same order**: Two or more CRITICAL-severity exceptions detected on a single order indicate a systemic fulfillment failure requiring human intervention.
- **Supplier-wide exception pattern**: More than 20% of open orders from the same supplier have active exceptions. Indicates a supplier reliability issue beyond individual order tracking.
- **Stale order**: An order has had no status update for more than 14 days. The order may be lost or abandoned, and automated tracking cannot resolve the ambiguity.
