# L2 Phase 3 — Graph Construction + GATv2+GRU Training Plan

**Status:** Design draft, 2026-04-27. Not yet started; tracks the
prerequisites + planned scope.
**Layer:** L2 Operational (between L1 TRMs and L3 Tactical planners).
**Depends on:** L2 Phase 2 (hub-hour snapshot extractor — shipped),
TMS_TIER3_FIRST_PLAN.md Phase A (digital twin — in progress).

---

## 1. What Phase 3 ships

The trained Terminal Coordinator agent that replaces the deterministic
heuristic shipped in L2 Phase 1 (commit `c9f30d3`). Per the
[L2 design doc](L2_TERMINAL_COORDINATOR_DESIGN.md) §3:

  * **Architecture** — GATv2 (Graph Attention v2) + GRU per hub, ~25K
    parameters, <100ms p95 inference latency.
  * **Inputs** — One `hub_hour_snapshot` row at evaluation time
    (Phase 2 substrate; this doc ships the matching graph
    constructor).
  * **Outputs** — Identical shape to the Phase-1 coordinator:
    `terminal_urgency_override` rows, `terminal_health_signal` rows,
    HiveSignal directives (batching / dock re-sequencing /
    yard-placement). The agent slots in behind a feature flag
    (`L2_TERMINAL_COORDINATOR_MODE = trm | heuristic | off`) so
    rollout is per-tenant per-hub.

---

## 2. Prerequisites — what blocks Phase 3 today

### 2.1 Twin (Phase A, critical path)

PPO fine-tune needs episode rollouts. Per
[TMS_TIER3_FIRST_PLAN.md](TMS_TIER3_FIRST_PLAN.md) §3 the digital
twin is Phase A — 2-3 weeks of work to audit + extend the existing
SimPy-based twin so it can:

  * Generate hub-hour state at arbitrary timestamps
  * Apply an action (urgency-multiplier vector + HiveSignal directive
    set) and step the simulation forward
  * Produce reward signals (SLA-miss + tender-reject + dock-util +
    equipment-imbalance) at end of each step
  * Replay deterministically for offline batch generation

Without the twin we can do **BC warmup only** — train against
heuristic-teacher labels on twin-generated or live snapshots. PPO
fine-tune requires the twin's step+reward loop.

### 2.2 Hub-hour snapshot corpus

Phase 2 (shipped 2026-04-27) writes one `hub_hour_snapshot` row per
hub per hour to the production DB. To train a useful GATv2+GRU we
need ~4 weeks of data minimum (≥ 5K snapshots assuming ~5 hubs ×
24 hours × 30 days ≈ 3.6K rows; 50K is comfortable but requires
twin-generated rows alongside live ops).

Greenfield tenants (no live history) train against the twin
exclusively — Phase A delivers the same `hub_hour_snapshot` shape
from twin rollouts so the BC pipeline is data-source-agnostic.

### 2.3 Reward function design (lock before training)

`L2_TERMINAL_COORDINATOR_DESIGN.md` §3 lists four reward
components:

  * SLA-miss penalty
  * Tender-reject rate at this hub
  * Dock utilisation (too-low or too-high both penalize)
  * Equipment-imbalance penalty at end of shift

Locking the weighting + clamps is a Phase 3 design-review step.
Default proposal — equal weights, all clamped to [-1, 0]:

```python
reward = -(
    sla_miss_weight     * sla_miss_rate          # 0.30
    + tender_reject_weight * tender_reject_rate  # 0.25
    + dock_util_weight     * abs(util - 0.7)     # 0.20  (target 70%)
    + equipment_weight     * abs(imbalance) / 10 # 0.25
)
```

Weights re-derive from `policy_parameters.bsc_*` once that wiring
lands (BSC weights map onto the four-axis reward in the obvious way).

---

## 3. Graph construction — node + edge schema

Built from the `hub_hour_snapshot.node_features` JSONB. Phase 2 v1
populates the node half; the edge half lands as part of Phase 3
graph-constructor implementation.

### 3.1 Node types (already populated by Phase 2)

| Node type | Source field | Features (per node) |
|---|---|---|
| `dock_door` | `node_features.dock_door[]` | `is_active` (bool), `queue_depth` (int) |
| `outbound_lane` | `node_features.outbound_lane[]` | `destination_site_id`, `queued_loads`, `tender_reject_rate_1h` |
| `inbound_lane` | `node_features.inbound_lane[]` | `origin_site_id`, `expected_arrivals_4h` |
| `equipment_pool` | `node_features.equipment_pool[]` | `equipment_type`, per-status counts |
| `carrier_presence` | `node_features.carrier_presence[]` | `carrier_id`, `active_loads_4h` |
| `shipment_queue` | `node_features.shipment_queue[]` | `mode`, `queued_count` |
| `trm_agent` | `node_features.trm_agent[]` | `trm_type`, `urgency_multiplier` |

### 3.2 Edge types (Phase 3 lands these)

| Edge type | Source nodes | Adjacency rule |
|---|---|---|
| `dock_to_shipment` | `dock_door` × `shipment_queue` | dock equipment-type compatible with shipment mode |
| `lane_to_shipment` | `outbound_lane` × `shipment_queue` | lane destination matches shipment destination |
| `carrier_to_lane` | `carrier_presence` × `outbound_lane` | carrier has accepted contract on lane |
| `equipment_to_lane` | `equipment_pool` × `outbound_lane` | equipment type matches lane requirement |
| `trm_to_resource` | `trm_agent` × {`dock`, `lane`, `equipment`} | static — each TRM owns specific resource types |

Edge features (v1):
  * `weight` (float, [0,1]) — strength of the relationship
  * `last_update_minutes_ago` (float) — recency

Sparsity expected: <10% of all O(N²) possible edges per hub-hour;
GATv2 attention focuses on the live edges anyway.

### 3.3 Graph encoder

Two-layer GATv2 with multi-head attention (heads=4):

```python
encoder = nn.Sequential(
    GATv2Conv(in_dim, 32, heads=4, edge_dim=2),  # node → hub embedding
    GATv2Conv(32 * 4, 16, heads=2, edge_dim=2),  # hub-level rollup
)
hub_embedding = global_mean_pool(graph)  # 32-dim per hub
```

GRU consumes the hub_embedding sequence over a 24-hour rolling
window:

```python
gru = nn.GRU(32, hidden_size=24, num_layers=1)
state, _ = gru(hub_embedding_sequence)  # (T, 24)
action_head = nn.Linear(24, 11)  # urgency_multiplier per L1 TRM
```

**Parameter budget**: ~25K total — fits the design target.

---

## 4. Training plan

### 4.1 BC warmup (Phase 3a — unblocks immediately)

  * **Inputs**: `hub_hour_snapshot` rows (live + twin once Phase A).
  * **Targets**: `terminal_urgency_override` rows the heuristic
    coordinator emitted at the same (hub, observed_at). When no
    override exists, target is `multiplier=1.0` for every TRM.
  * **Loss**: MSE on the 11-dim urgency-multiplier vector.
  * **Stopping**: ≤10% MSE on a held-out validation set (matches the
    Phase-1 BC profile we already know works for the L1 TRMs).

This trains a model that *imitates* the heuristic. Useful as a
warm-start; not a behaviour improvement on its own.

### 4.2 PPO fine-tune (Phase 3b — needs twin)

  * Twin step interface: `twin.step(hub_state, action) →
    (next_state, reward, done)`.
  * Episode length: 24 hours (one full shift cycle).
  * Batch size: 32 episodes per update.
  * Learning rate: decoupled value-LR per
    [Core 2.x TwinRlTrainer pattern](https://github.com/azirella-ltd/Autonomy-Core/commit/9c96a01).
  * Stopping: average per-episode reward improves over BC baseline by
    ≥15% on a held-out scenario set.

### 4.3 Per-tenant per-hub checkpoints (Phase 3c)

Once real operational data flows (≥4 weeks per hub), fine-tune the
generic checkpoint on per-tenant data. Pattern:

  * Generic (network-pretrained) checkpoint: `{tenant_id}/{config_id}/generic_v1.pt`
  * Per-hub fine-tune: `{tenant_id}/{config_id}/{hub_id}/finetuned_v1.pt`
  * Inference resolution: try `{hub_id}/finetuned` → `generic` → `heuristic`.

---

## 5. Rollout

Per Phase 4 of [L2 design](L2_TERMINAL_COORDINATOR_DESIGN.md) §6.4:

1. Feature flag `L2_TERMINAL_COORDINATOR_MODE` per `(tenant, hub)`
   with values `heuristic` (default), `trm` (Phase-3 trained), `off`.
2. Canary on one tenant's lowest-traffic hub, observe
   `terminal_health_signal.composite_health` for ≥2 weeks.
3. Roll forward to higher-traffic hubs only when canary hub shows
   ≥10% reduction in tender-reject rate or ≥5% improvement in
   on-time-delivery vs heuristic-only.
4. Per-hub kill switch always available — flip back to `heuristic`
   on any regression.

---

## 6. What ships immediately (no twin needed)

Phase 3a (BC warmup against `hub_hour_snapshot` + heuristic-teacher
labels) can land as soon as we have ≥5K snapshots. The hub-hour
snapshot extractor (Phase 2) writes one row per hub per hour, so
expect ≥5K rows in 4-8 weeks of live operation depending on hub
count.

**Order of work for Phase 3a only** (does not need twin):

1. Add `train_hub_hour_bc.py` script under
   `backend/scripts/pretraining/` — mirrors `train_tms_trms.py`
   but loads from `hub_hour_snapshot` table instead of TRM-corpus
   parquet files.
2. Define `HubHourGraphConstructor` class (graph + edges from
   snapshot row).
3. Define `TerminalCoordinatorAgent` model class (GATv2 + GRU, 25K
   params).
4. BC warmup loop with MSE on the urgency-multiplier targets.
5. Save checkpoint at `training_data/checkpoints/l2_terminal_coordinator_bc_v1.pt`.

This is ~1-2 weeks of focused work once we have the snapshot data.

**What needs Phase A first**: Phase 3b (PPO fine-tune) and Phase 4
(rollout) — both need twin step+reward.

---

## 7. Cross-references

  * [L2_TERMINAL_COORDINATOR_DESIGN.md](L2_TERMINAL_COORDINATOR_DESIGN.md) §3 — full agent architecture
  * [TMS_TIER3_FIRST_PLAN.md](TMS_TIER3_FIRST_PLAN.md) §3 — twin
    (Phase A) prerequisites
  * [L4_POLICY_PARAMETERS_DESIGN.md](L4_POLICY_PARAMETERS_DESIGN.md) — BSC weight source for reward function
  * SCP `docs/internal/architecture/SITE_TGNN.md` — analog GATv2+GRU
    pattern + lessons learned
