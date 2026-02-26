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
