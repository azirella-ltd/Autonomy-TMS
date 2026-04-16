# TMS — Tier 3 Addendum to the Constrained Solver Port

**Status**: Foundational architectural correction. Read before or alongside `CONSTRAINED_SOLVER_PORT.md`.
**Date**: 2026-04-16.

## Why this addendum exists

The original `CONSTRAINED_SOLVER_PORT.md` described porting SCP's LP / MILP work to TMS as if the solver were the endpoint. It is not. Autonomy's tactical planner is a **GraphSAGE policy trained by reinforcement learning on the digital twin** (AlphaZero / Leela pattern applied to supply chain and transportation planning). The LP / MILP is a baseline, a safety net, and a bootstrap — never a teacher.

This addendum restates the foundational invariant for TMS and lays out the Tier 3 target architecture for transportation planning.

---

## 1. Foundational invariant — NEVER CHALLENGE

Autonomy's tactical transportation planner on TMS is a **GraphSAGE policy trained end-to-end by reinforcement learning against a transportation digital twin**. The LP / MILP solver is:

- a **development baseline** — the benchmark the GNN must match or exceed before promotion,
- an **optional production safety net** — projects a GNN plan onto the feasible region for rare hard-constraint violations,
- a **bootstrap** — first planner for a new TMS tenant before its twin has produced enough training data.

The LP is never a label generator in the training loop. The GNN is never trained to imitate LP output.

A GNN trained on LP labels inherits all of the LP's limitations: linear objectives, fixed horizons, no strategic consolidation reasoning, no disruption playbooks. AlphaZero beat Stockfish because it was not trained on Stockfish.

## 2. Why the data objection does not apply

Autonomy's digital twin is designed to generate training corpora at scale — including for TMS-specific decisions. Phase 0 validation on SCP (Generic TRM PoC, 70.3% vs 0% heuristic) demonstrated the approach. TMS inherits the same twin infrastructure — see the SCP-side [DIGITAL_TWIN_AUDIT.md](https://github.com/azirella-ltd/Autonomy-SCP/blob/main/docs/internal/architecture/DIGITAL_TWIN_AUDIT.md) for baseline.

## 3. Ingredient mapping for TMS

| Chess / AlphaZero | TMS tactical planning |
|---|---|
| Board position | Graph state — shipments queued, equipment at each site, dock slots, carrier committed capacity, in-flight flows, active disruptions |
| Legal moves | Feasible decisions — load-build assignments, carrier choice, dispatch timing, routing, dock slot booking, equipment reposition |
| Rules of chess | Twin physics — driver hours (HOS), dock slot availability, carrier capacity, equipment balance, lane transit times |
| Winning | BSC utility — on-time delivery + cost per load + trailer utilisation + override rate, weighted per tenant |
| Self-play | Stochastic rollouts through TMS twin with shipment arrival distributions, carrier availability shocks, weather disruptions |
| Policy network | GraphSAGE — movement, capacity, and equipment tGNNs jointly trained end-to-end |
| Training | PPO / actor-critic on trajectory returns |

## 4. The three tiers for TMS

Same progression as SCP, different substance:

### Tier 1 — LP primary

- Small TMS tenants (<1K lane-period cells)
- Classical solver (HiGHS) handles load-building and carrier selection in milliseconds
- GraphSAGE not in the planning path
- Default starting state for every new TMS tenant

### Tier 2 — LP with GraphSAGE assist

- Medium TMS tenants (10K – 100K cells)
- LP still produces the plan; GNN accelerates via warmstart and critiques afterwards
- Specific assists:
  - Warmstart — GNN predicts load assignments from graph state; LP tightens variable bounds around those predictions
  - Critique — GNN flags lanes / carriers / equipment pools that look anomalous; feeds strategic proposals (LANE_REBALANCE, SUPPLIER_DIVERSIFY)

### Tier 3 — GraphSAGE primary, LP repair

- Enterprise TMS tenants (>100K cells, complex multi-carrier networks)
- GNN produces the movement plan directly
- LP runs only as repair — projects GNN's plan onto feasible region when hard constraints (driver HOS, dock slot, carrier contract minimums) are violated
- Sub-second plans on networks that would take hours with classical LP

### Transition criteria

- **Tier 1 → Tier 2**: when the tenant's daily LP solve crosses a threshold (e.g., 30 seconds) AND the tenant has ≥ 4 weeks of twin-generated training data.
- **Tier 2 → Tier 3**: when GraphSAGE plan matches or exceeds LP-optimal on a held-out scenario set for 4+ consecutive weeks.

Both gated via `tenant_solver_features.use_gnn_as_planner` (future flag).

## 5. The TMS twin

If TMS does not yet have a digital twin with the fidelity Tier 3 requires, **building it is the highest-leverage investment the TMS team can make.** Without a faithful twin, Tier 3 is not reachable; with one, it is a training-time away.

Required fidelity for TMS twin:

- Shipment arrival distributions (stochastic)
- Carrier capacity realisation (committed vs available, reliability distribution per carrier)
- Driver HOS constraints (real US FMCSA or equivalent)
- Dock slot availability (per site, per day, per shift)
- Transit time distributions per lane per mode
- Equipment balance and repositioning cost
- Disruption injection (weather, carrier strike, port congestion)
- Customer service-level tiers
- Accessorial cost realism (detention, layover, fuel surcharge)

SCP's twin audit covers this framework; TMS needs an equivalent audit. See [DIGITAL_TWIN_AUDIT.md](https://github.com/azirella-ltd/Autonomy-SCP/blob/main/docs/internal/architecture/DIGITAL_TWIN_AUDIT.md) for the shape.

## 6. Implementation order for TMS toward Tier 3

Mirrors the SCP order:

1. **Reward function** for TMS-domain BSC metrics (on-time, cost, utilisation, override rate). 1 week.
2. **State representation** — serialise twin state into a graph tensor the GraphSAGE consumes. 2 weeks.
3. **Rollout harness** — multi-process twin + policy evaluation, captures trajectories. 2-3 weeks.
4. **Training loop** — PPO on captured trajectories, curriculum over scenario difficulty. 1 month first pilot; 3-6 months to LP parity; 6-12 months to exceed LP.
5. **Deployment path** — flag-gated per tenant; `use_gnn_as_planner` in `tenant_solver_features`. 1 week.

These run **in parallel with** the LP port. Do not sequence them "LP first, then Tier 3 later." The LP port is quick (2-3 weeks); the twin + RL investment is longer (months). Start both on day one.

## 7. What not to do

1. **Do not build a GNN that imitates the LP.** Imitation learning is tempting because it's predictable, but it caps TMS's planner at LP performance forever.
2. **Do not defer the twin.** The twin is the load-bearing asset. Under-invest in the twin and Tier 3 is unreachable.
3. **Do not train on historical operational data only.** Real TMS logs are noisy and contain the mistakes of past planning. Use the twin to generate clean synthetic scenarios.
4. **Do not re-litigate this architecture** in future sessions without explicit reversal from the tenant owner.

## 8. What the LP port IS still good for on TMS

- Day-one planning capability while the twin bootstraps
- Reference-optimal baseline for benchmarking GNN outputs during training
- Production safety net (LP repair step)
- Bootstrap for new tenants with no twin history

The LP work is not wasted; it's infrastructure. But it is not the destination.

## 9. Cross-references

- SCP `docs/internal/architecture/TIER_3_GNN_FIRST_PLANNING.md` — the full internal spec
- SCP `docs/external/TACTICAL_PLANNER_POSITIONING.md` — customer-facing positioning
- SCP `docs/internal/architecture/DIGITAL_TWIN_AUDIT.md` — baseline twin audit; TMS should mirror this
- SCP `docs/internal/architecture/CONSTRAINED_SOLVER_DESIGN.md` — LP/MILP scope, positioned as baseline/safety-net
- This directory's `CONSTRAINED_SOLVER_PORT.md` — the per-file port plan

## 10. Summary

The correct read of the architecture is: **Tier 3 all along, LP as scaffolding.** Port the LP so TMS tenants have something working. Build the twin so Tier 3 becomes reachable. Train the GraphSAGE on twin rollouts so the tenant eventually gets the planner that beats every classical solver. Do not collapse the destination into the scaffolding.
