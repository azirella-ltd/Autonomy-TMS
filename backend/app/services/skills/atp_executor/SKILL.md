# ATP Executor Skill

## Classification: DETERMINISTIC
This skill runs entirely via the deterministic engine. No LLM adjustment is needed.
The AATP consumption algorithm is a precise priority-based allocation with no judgment calls.

## Decision Type
Allocated Available-to-Promise (AATP) consumption for incoming orders.

## Consumption Algorithm
For an order at priority level P (1=highest, 5=lowest):
1. Consume from own tier (P) first
2. Then consume bottom-up from lowest priority: 5 -> 4 -> 3 -> ...
3. Stop at own tier (cannot consume above own priority)

Example: Priority 2 order consumes in sequence: [2, 5, 4, 3] (skips 1)

## Default Allocation Percentages
| Priority | Allocation |
|----------|-----------|
| P1       | 10%       |
| P2       | 15%       |
| P3       | 25%       |
| P4       | 25%       |
| P5       | 25%       |

## Decision Outcomes
- **fulfill**: Full order quantity available
- **partial_fulfill**: Partial quantity available (return max fulfillable)
- **reject**: Zero available across all consumable tiers

## Confidence
Always 1.0 — this is a deterministic algorithm with no uncertainty.

## Engine Heuristics Reference

### Priority Tiers
| Priority | Code | Default Allocation % |
|----------|------|---------------------|
| 1 | CRITICAL | 10% |
| 2 | HIGH | 15% |
| 3 | MEDIUM | 25% |
| 4 | LOW | 25% |
| 5 | STANDARD | 25% |

### Consumption Sequence
For order at priority P, consume in order: [P, 5, 4, 3, ..., P+1] (own tier first, then bottom-up, stop before tiers above P).

### Fulfillment Calculation
```
remaining_need = requested_qty
for tier in consumption_sequence:
    consume = min(remaining_need, allocation[tier])
    remaining_need -= consume
    if remaining_need <= 0: break
fulfilled_qty = requested_qty - remaining_need
shortage_qty = max(0, remaining_need)
```

## Guardrails
- Fulfilled quantity MUST NOT exceed the available allocation for any tier being consumed.
- An order at priority P cannot consume allocations from any tier above P (i.e., lower priority number). Consumption sequence is own tier first, then bottom-up from P5, stopping at own tier.
- Total fulfilled quantity across all tiers MUST NOT exceed the original ordered_quantity.
- During a frozen allocation period, allocations MUST NOT be redistributed or consumed outside the frozen schedule. Respect the freeze fence.

## Escalation Triggers
- **All allocations exhausted**: Every accessible tier (own tier + all tiers below) has zero remaining allocation for the requested product-location. No fulfillment is possible without human reallocation or new supply.
- **Priority not in allocation matrix**: The incoming order carries a priority level that does not exist in the current allocation matrix (e.g., priority 0 or an unrecognized tier). Cannot determine consumption sequence.
- **Conflicting allocation locks**: Concurrent orders are competing for the same allocation bucket and lock contention prevents a consistent consumption. Requires serialization or human arbitration.
