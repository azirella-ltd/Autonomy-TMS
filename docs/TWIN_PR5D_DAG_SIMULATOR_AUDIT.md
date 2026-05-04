# PR-5.D Audit — `dag_simulator.py` (deterministic SCP simulator)

**Status:** audit, 2026-05-04.
**Owner:** TMS team (acer-nitro session).
**Companion:** [TWIN_PR5_CALLER_MIGRATION_AUDIT.md](TWIN_PR5_CALLER_MIGRATION_AUDIT.md) — the
parent audit that delivered PR-5.A / 5.B / 5.C and explicitly flagged
`dag_simulator.py` as out of scope:

> 7. **Audit** [`backend/app/services/dag_simulator.py`](../backend/app/services/dag_simulator.py)
>    (the deterministic SCP simulator) — it's referenced by the
>    deletees plus a `replay_history`-style usage in SCP. Likely also
>    SCP-fork residue but lower priority and out of 5.B's scope; flag
>    for a follow-up.

This doc is that follow-up.

**Resolves:** Trevor's question — *"Please investigate the difference
between `dag_simulator.py` and `dag_simpy_simulator.py`. Why do both
exist?"*

---

## 1. Why both exist — the SCP-twin training-data architecture

The two files were **complementary halves of the SCP twin's
warm-start training-data pipeline**, splitting work along the
**deterministic vs stochastic** axis:

| | `dag_simulator.py` | `dag_simpy_simulator.py` |
|---|---|---|
| Style | Deterministic single-run | Stochastic Monte Carlo (SimPy) |
| Core class | `DAGSimulator` | `DAGSimPySimulator` |
| Output | One `SimulationResult` per ordering strategy | `MonteCarloResult` (N runs × P periods) |
| Per-period decisions | Picks via the chosen `OrderingStrategy` (BASE_STOCK / CONSERVATIVE / PID) | Same heuristic, but lead times / demand / supplier reliability / capacity disruptions are stochastic |
| Cost | Cheap (3 strategies × 52 periods ≈ seconds) | Expensive (128 runs × 52 periods ≈ minutes) |
| Role | Clean-baseline training labels | Variance / noise training data |
| Lifetime status | Lives in `app/services/dag_simulator.py` | Deleted by PR-5.C ([#38](https://github.com/azirella-ltd/Autonomy-TMS/pull/38)) |

The split was **structural**: `dag_simpy_simulator.py` literally
imported `LoadedTopology`, `SimulationResult`, `SimDecision`,
`SimPeriodState`, `SimKPIs`, `PipelineShipment`, `SiteProductState`,
`OrderingStrategy`, and the private `_is_supply` / `_is_demand` /
`_is_inventory` helpers from `dag_simulator.py` — the simpy file
couldn't exist without the deterministic file. The deterministic file
*could* exist standalone (and now does, post-PR-5.C).

Both came from the **SCP fork**. The TRM names produced by the
downstream `SimulationDataConverter` (`atp` / `po_creation` /
`safety_stock` / `inventory_rebalancing` / `mo_execution` / …) are
the SCP plane's decision shapes. PR-5.A's parent audit established
this; both simulators were SCP-shape contributors to that pipeline.

### 1.1 Where their output flowed

```
DAGSimulator.simulate()              ─┐
DAGSimPySimulator.run_monte_carlo()  ─┼─→ SimulationResult / MonteCarloResult
                                      │      ↓
                                      │   SimulationDataConverter   ← deleted PR-5.B
                                      │      ↓
                                      │   {GNN NPZ, TRM records}    ← SCP-shape, no TMS consumer
                                      │      ↓
                                      └─→ PowellTrainingService.train_*()
                                            (called from deployment_pipeline_service.py
                                             and train_food_dist_models.py — both deleted PR-5.B)
```

After PR-5.B + 5.C, that whole flow is gone. Which raises:
**why does `dag_simulator.py` survive?**

---

## 2. Post-PR-5 reality: `dag_simulator.py` is half dead

The file is 1,671 lines. After PR-5.B + 5.C land, only **two** Python
files in the entire TMS backend import from it:

```
$ grep -RIln 'from app.services.dag_simulator\|app\.services\.dag_simulator' \
  backend --include='*.py'

backend/app/services/sap_csv_exporter.py
backend/app/services/powell/sop_inference_service.py
```

Both import the **same single symbol**: `load_topology`. Neither
imports `DAGSimulator`, `SimulationResult`, `OrderingStrategy`, or any
of the SCP-shape simulator types.

### 2.1 What `load_topology` does

[`dag_simulator.py:226–302`](../backend/app/services/dag_simulator.py#L226-L302).
Pure DB query function. Loads:

- `SupplyChainConfig` row + its `sites` + `transportation_lanes`
- `Product` rows for the config
- Forecasts, inventory policies, initial inventory, vendor lead times — all SCP-shape

Returns a `LoadedTopology` dataclass which **mixes graph fields and inventory fields**:

| Field | Generic graph? | SCP-shape inventory? |
|---|---|---|
| `config`, `sites`, `lanes`, `products` | ✓ | |
| `supply_sites`, `inventory_sites`, `demand_sites` | ✓ | |
| `upstream_map`, `downstream_map`, `topo_order` | ✓ | |
| `forecasts` (per site × product weekly) | | ✓ |
| `inv_policies` (per site × product) | | ✓ |
| `initial_inventory` (per site × product) | | ✓ |
| `vendor_lead_times`, `vendor_reliability` | | ✓ |

### 2.2 What the live callers actually use

**`sap_csv_exporter.py:201`** — `_load_data` opens with
`self._topology = await load_topology(self.config_id, self.db)` and
then immediately queries `InvLevel`, `Forecast`, `ProductBOM`,
`TradingPartner`, `VendorProduct`, `VendorLeadTime`,
`InboundOrderLine`, `OutboundOrderLine`, `Shipment` directly via
ORM. Only the **graph fields** (`sites`, `lanes`) are read off the
LoadedTopology; the inventory fields are bypassed.

**`sop_inference_service.py:241`** — calls `load_topology` inside its
own `_load_topology` wrapper that returns the dict shape its tGNN
expects. Same pattern: graph-only consumption.

**Verdict:** the inventory fields on `LoadedTopology` are **dead
data**. The SCP-shape inventory loading paths
(`_load_forecasts` / `_load_inv_policies` / `_load_initial_inventory`
/ `_load_vendor_info`) run on every call but their output is never
consumed.

### 2.3 What the rest of the file is

| Block | Lines | Status |
|---|---:|---|
| `OrderingStrategy` enum (BASE_STOCK / CONSERVATIVE / PID) | ~3 | dead — no caller picks a strategy |
| `SiteProductState`, `PipelineShipment`, `SimDecision`, `SimPeriodState`, `SimKPIs`, `SimulationResult` dataclasses | ~120 | dead — nothing consumes the simulator output |
| `LoadedTopology` dataclass | ~25 | half-dead — graph fields used, inventory fields dead |
| `load_topology()` + `_load_*` private helpers | ~200 | live (graph half) + dead (inventory half) |
| `_topological_sort`, `_is_supply` / `_is_demand` / `_is_inventory` | ~50 | live |
| `DAGSimulator` class — `simulate()`, period loop, MRP / AATP / SafetyStock / Rebalancing / OrderTracking integration | **~1,100** | **dead** — no caller instantiates it |
| Imports of `app.services.powell.engines.{mrp,aatp,safety_stock,rebalancing,order_tracking}_engine` | ~30 | dead, transitively |

Roughly **~1,400 of 1,671 lines (84%) are unreferenced** in the
post-PR-5 graph.

---

## 3. Why this happened

The SCP-fork residue cleanup in PR-5 worked outward from
`SimulationDataConverter`. PR-5.A traced *forward* from the converter
to its callers (the three deletees) and *backward* to its inputs
(the two simulators). PR-5.C deleted `dag_simpy_simulator.py`
because every Python caller was a deletee. `dag_simulator.py` had
**one extra survivor reach** — `load_topology` is also imported by
the two non-SCP-shape callers in §2.2 — so the file as a whole got
a reprieve.

That reprieve was correct *as a delete decision* but it left ~1,400
lines of dead deterministic-simulator code in the file.

The pattern matches the parent audit's framing
([TWIN_PR5_CALLER_MIGRATION_AUDIT.md §6](TWIN_PR5_CALLER_MIGRATION_AUDIT.md))
of "convert implicit dead code into either explicit dead code (delete)
or actively maintained code (rewrite)". Today the deterministic
simulator class sits in the implicit-dead category — runnable, but
nothing runs it.

---

## 4. Recommendation — extract `topology_loader.py`, delete the rest

**Goal:** preserve the two live callers, delete the ~1,400 lines of
dead simulator + supporting types.

### 4.1 New file: `backend/app/services/topology_loader.py`

Contains:

- `LoadedTopology` dataclass — **slimmed** to just the graph fields
  (`config`, `sites`, `lanes`, `products`, `supply_sites`,
  `inventory_sites`, `demand_sites`, `upstream_map`, `downstream_map`,
  `topo_order`). Drop `forecasts`, `inv_policies`,
  `initial_inventory`, `vendor_lead_times`, `vendor_reliability` —
  no caller reads them.
- `load_topology(config_id, db)` — the same async function, but
  without the calls to `_load_forecasts` / `_load_inv_policies` /
  `_load_initial_inventory` / `_load_vendor_info`.
- `_topological_sort`, `_is_supply` / `_is_demand` / `_is_inventory`
  helpers.

Net: ~250 lines (vs the full file's 1,671). Plane-clean — the
graph loader is genuinely useful TMS infrastructure (it underpins
the TMS Powell tGNN inference services' own topology lookups too,
even though they don't import `dag_simulator` directly).

### 4.2 Delete: `backend/app/services/dag_simulator.py`

After 4.1 lands, switch the two callers to import from
`topology_loader` and delete the original file.

### 4.3 Sub-ticket sequencing

Mirrors the PR-5 sub-ticket pattern:

| | Sub-ticket | Scope |
|---|---|---|
| **5.D-i** | Create `topology_loader.py` with the slimmed `LoadedTopology` + `load_topology` + helpers. New file, no caller change yet. Tests for the slimmed shape (graph fields populated, no inventory fields). |
| **5.D-ii** | Cut `sap_csv_exporter.py` and `sop_inference_service.py` over to import from `topology_loader`. Verify no behaviour change. |
| **5.D-iii** | Delete `backend/app/services/dag_simulator.py` and its now-orphan imports of `app.services.powell.engines.*`. |

Each sub-ticket is small (~100–200 lines per PR), independent
review-wise, and reversible.

### 4.4 Why not delete the file directly today

Reasons to defer the actual surgery to a future PR:

1. The 1,400-line delete is review-sensitive even though most of it
   is dead. Reviewers need to confirm "nothing imports `DAGSimulator`"
   themselves.
2. The slim-down of `LoadedTopology` is technically backward-incompatible
   for any caller relying on the inventory fields. The audit shows
   none does today, but a confirmed split-then-delete sequence is
   safer than a single-PR rewrite.
3. PR-5.C ([#38](https://github.com/azirella-ltd/Autonomy-TMS/pull/38))
   isn't merged yet; until it lands, two of the legacy `dag_simulator.py`
   callers
   (`dag_simpy_simulator.py`, `train_food_dist_models.py`,
   `deployment_pipeline_service.py`) still exist on `main`. The clean
   "only-2-callers" state assumed by §2 is conditional on PR-5.B + 5.C
   merging first.

So 5.D's actual code surgery should land **after** PR-5.C merges.

---

## 5. Open question for the user

Do you want PR-5.D opened now (this audit only, with sub-tickets to
follow), or should I wait until PR-5.C merges before queuing 5.D-i
through 5.D-iii?

The audit doc itself is safe to ship in either order — it stands as
context for the future surgery without doing any code change.

---

## 6. Cross-references

- [TWIN_PR5_CALLER_MIGRATION_AUDIT.md](TWIN_PR5_CALLER_MIGRATION_AUDIT.md) — parent audit (5.A/5.B/5.C); §5.B item 7 flags this as the follow-up.
- [TWIN_REWRITE_PLAN.md](TWIN_REWRITE_PLAN.md) — PR sequence; this audit slots in as PR-5.D.
- [PR #36 (5.A)](https://github.com/azirella-ltd/Autonomy-TMS/pull/36), [PR #37 (5.B)](https://github.com/azirella-ltd/Autonomy-TMS/pull/37), [PR #38 (5.C)](https://github.com/azirella-ltd/Autonomy-TMS/pull/38) — the predecessor cuts.

---

*Last updated: 2026-05-04.*
