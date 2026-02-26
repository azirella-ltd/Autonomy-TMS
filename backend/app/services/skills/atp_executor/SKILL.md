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
