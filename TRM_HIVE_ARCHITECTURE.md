# TRM Hive Architecture: Collective Intelligence for Supply Chain Execution

**Status**: PROPOSED (2026-02-23)
**Author**: Architecture Analysis
**Dependencies**: [POWELL_APPROACH.md](POWELL_APPROACH.md), [TRM_AGENTS_EXPLAINED.md](TRM_AGENTS_EXPLAINED.md), [AGENTIC_AUTHORIZATION_PROTOCOL.md](docs/AGENTIC_AUTHORIZATION_PROTOCOL.md)
**Related**: Kinaxis RapidResponse concurrent planning architecture (Section 11), Scenario-based agent negotiation (Section 12)

---

## 1. The Hive Metaphor — Precise Domain Mapping

A bee colony is one of nature's most studied examples of decentralized intelligence. Individual bees are simple; the colony exhibits complex adaptive behavior through signal-mediated coordination. This maps remarkably well to the per-site TRM architecture.

### 1.1 Concept-to-Domain Mapping

| Bee Colony | Supply Chain Domain | Implementation Artifact |
|---|---|---|
| **Hive** | Supply Chain Site (DC, Factory, Warehouse) | `SiteAgent` instance (`site_agent.py`) |
| **Queen** | SiteAgent Coordinator — prioritizes, resolves conflicts, sets policy | SiteAgent orchestrator (`trm_confidence_threshold`, `agent_mode`, CDC trigger handler) |
| **11 Worker Castes** | 11 Narrow TRM Heads — each with functional specialization | `ATPExecutorTRM` through `SafetyStockTRM` |
| **Waggle Dance** | Intra-Hive Signal Bus — cross-TRM communication | NEW: `HiveSignalBus` (in-memory, per-site) |
| **Pheromone Trails** | Urgency/Risk Signals — decay over time, influence all workers | NEW: `UrgencyVector` (float[11]) |
| **Colony Memory** | Decision Log + Replay Buffer | `powell_site_agent_decisions` table + signal context |
| **Nectar/Pollen** | Inventory, Orders, Supply | `on_hand`, `pipeline`, `allocation buckets` |
| **Flower Patches** | Demand Sources, Supplier Sites | Market Demand sites, Market Supply sites |
| **Swarming** | CDC-triggered Replanning | `CDCRetrainingService` + `FULL_CFA` action |
| **Inter-Hive Communication** | tGNN Network Coordination | `SOPGraphSAGE` + `ExecutionTemporalGNN` |
| **Foraging Map** | S&OP Structural Analysis | `structural_embeddings` (64-dim), `criticality`, `bottleneck_risk` |
| **Scout Reports** | Execution tGNN Real-time Signals | `exception_probability`, `propagation_impact`, `demand_forecast` |
| **Nectar Distribution** | Allocation Service — priority-based resource flow | `PriorityAllocation` consumed by AATP consumption logic |

### 1.2 Worker Bee Functional Castes

In a bee colony, workers specialize by age and need. In the Hive, TRMs specialize by function:

| Caste | TRM Workers | Primary Function |
|---|---|---|
| **SCOUTS** (Demand Sensing) | `ATPExecutorTRM`, `OrderTrackingTRM` | Detect demand signals at the hive boundary. First to see incoming orders, first to detect exceptions. |
| **FORAGERS** (Resource Acquisition) | `POCreationTRM`, `InventoryRebalancingTRM`, `SubcontractingTRM` | Acquire resources from external sources (suppliers, other sites, subcontractors). |
| **NURSES** (Colony Health) | `SafetyStockTRM`, `ForecastAdjustmentTRM` | Maintain colony health parameters. Adjust buffers and beliefs to keep the hive resilient. |
| **GUARDS** (Production Integrity) | `QualityDispositionTRM`, `MaintenanceSchedulingTRM` | Protect production integrity. Prevent contamination (quality) and breakdown (maintenance). |
| **BUILDERS** (Execution) | `MOExecutionTRM`, `TOExecutionTRM` | Execute production and logistics. Transform inputs into outputs, move goods through the network. |

### 1.3 Why the Hive Metaphor Fits

The bee colony analogy is not decorative — it captures three structural properties of the TRM architecture:

1. **Narrow individual scope, collective intelligence**: Each TRM makes bounded decisions (<10ms, ±20% adjustment). No single TRM "understands" the whole site. But coordinated through signals, the colony adapts to complex disruptions.

2. **Stigmergy over direct communication**: Bees coordinate through environmental modification (pheromones), not point-to-point messages. Similarly, TRMs coordinate through shared state (urgency vector, signal bus) rather than calling each other's methods.

3. **Graceful degradation**: If a bee caste fails, the colony adapts. If a TRM model is unavailable (`model is None`), the deterministic engine handles the decision. The hive continues with reduced capability, not failure.

---

## 2. Intra-Hive Signal Bus (The Waggle Dance)

### 2.1 The Problem Today

Currently, TRM heads execute in isolation within the SiteAgent. The `SharedStateEncoder` computes a 128-dim embedding once from raw state (inventory, pipeline, backlog, demand_history, forecasts), and each head reads this embedding independently.

The critical gap: **no head knows what another head just decided**.

- ATP rejects 3 orders in a row, but POCreationTRM does not know demand is spiking
- SafetyStockTRM increases buffers, but RebalancingTRM does not know relief is being planned
- QualityTRM rejects a batch (reducing available inventory), but ATPExecutorTRM continues promising from the old availability figure

### 2.2 Signal Data Structure

```python
@dataclass
class HiveSignal:
    """A signal emitted by one TRM worker for consumption by others."""
    signal_id: str                    # UUID
    source_trm: str                   # "atp_executor", "po_creation", etc.
    signal_type: HiveSignalType       # Enum (see below)
    timestamp: datetime

    # Payload
    urgency: float                    # 0.0 (routine) to 1.0 (critical)
    direction: str                    # "shortage", "surplus", "risk", "relief"
    magnitude: float                  # Normalized impact magnitude
    product_id: Optional[str]         # Product context (if applicable)

    # Decay (pheromone behavior)
    half_life_minutes: float = 30.0   # Signal relevance decays over time

    # Metadata for downstream consumers
    payload: Dict[str, Any]           # TRM-specific details
    confidence: float = 1.0           # Source TRM confidence in this signal

    @property
    def current_strength(self) -> float:
        """Pheromone-like decay: strength diminishes over time."""
        elapsed = (datetime.utcnow() - self.timestamp).total_seconds() / 60
        return self.urgency * math.exp(-0.693 * elapsed / self.half_life_minutes)
```

### 2.3 Signal Types

```python
class HiveSignalType(str, Enum):
    # ── Scout signals (demand-side) ──
    DEMAND_SURGE       = "demand_surge"        # Incoming orders exceeding forecast
    DEMAND_DROP        = "demand_drop"         # Orders falling below forecast
    ATP_SHORTAGE       = "atp_shortage"        # Cannot fulfill from allocations
    ATP_EXCESS         = "atp_excess"          # Allocation utilization very low
    ORDER_EXCEPTION    = "order_exception"     # Late/short/stuck order detected

    # ── Forager signals (supply-side) ──
    PO_EXPEDITE        = "po_expedite"         # Emergency PO placed
    PO_DEFERRED        = "po_deferred"         # PO pushed out (supplier issue)
    REBALANCE_INBOUND  = "rebalance_inbound"   # Transfer arriving from other site
    REBALANCE_OUTBOUND = "rebalance_outbound"  # Transfer departing to other site
    SUBCONTRACT_ROUTED = "subcontract_routed"  # Work sent to subcontractor

    # ── Nurse signals (health) ──
    SS_INCREASED       = "ss_increased"        # Safety stock raised
    SS_DECREASED       = "ss_decreased"        # Safety stock lowered
    FORECAST_ADJUSTED  = "forecast_adjusted"   # Forecast changed

    # ── Guard signals (integrity) ──
    QUALITY_REJECT     = "quality_reject"      # Batch rejected/scrapped
    QUALITY_HOLD       = "quality_hold"        # Batch on hold (pending)
    MAINTENANCE_DEFERRED = "maintenance_deferred"  # Maintenance postponed
    MAINTENANCE_URGENT = "maintenance_urgent"  # Emergency maintenance needed

    # ── Builder signals (execution) ──
    MO_RELEASED        = "mo_released"         # Production started
    MO_DELAYED         = "mo_delayed"          # Production delayed
    TO_RELEASED        = "to_released"         # Transfer started
    TO_DELAYED         = "to_delayed"          # Transfer delayed

    # ── tGNN signals (from inter-hive layer) ──
    NETWORK_SHORTAGE   = "network_shortage"    # tGNN detects network-wide issue
    NETWORK_SURPLUS    = "network_surplus"     # tGNN detects available supply
    PROPAGATION_ALERT  = "propagation_alert"   # Disruption propagating toward site
    ALLOCATION_REFRESH = "allocation_refresh"  # New allocations from tGNN
```

### 2.4 Signal Production and Consumption Matrix

Each TRM worker produces signals after making decisions and consumes signals before making decisions:

| TRM Worker | PRODUCES | CONSUMES |
|---|---|---|
| **ATPExecutorTRM** (Scout) | `ATP_SHORTAGE` (on shortfall), `ATP_EXCESS` (low utilization), `DEMAND_SURGE` (high volume), `DEMAND_DROP` (low volume) | `QUALITY_REJECT` (reduces available), `REBALANCE_INBOUND` (relief), `MO_RELEASED` (future supply), `SS_INCREASED` (reserve more), `ALLOCATION_REFRESH` |
| **OrderTrackingTRM** (Scout) | `ORDER_EXCEPTION` (late, short, stuck) | `PO_EXPEDITE` (resolution), `TO_DELAYED` (impact), `SUBCONTRACT_ROUTED` (alt source) |
| **POCreationTRM** (Forager) | `PO_EXPEDITE`, `PO_DEFERRED` | `ATP_SHORTAGE` (urgency up), `DEMAND_SURGE` (order more), `SS_INCREASED` (target higher), `QUALITY_REJECT` (replace), `FORECAST_ADJUSTED` |
| **RebalancingTRM** (Forager) | `REBALANCE_INBOUND`, `REBALANCE_OUTBOUND` | `ATP_SHORTAGE` (pull needed), `ATP_EXCESS` (push possible), `NETWORK_SHORTAGE`, `NETWORK_SURPLUS` |
| **SubcontractingTRM** (Forager) | `SUBCONTRACT_ROUTED` | `MO_DELAYED` (capacity issue), `MAINTENANCE_URGENT` (asset down), capacity from tGNN |
| **SafetyStockTRM** (Nurse) | `SS_INCREASED`, `SS_DECREASED` | `ATP_SHORTAGE` (stockout risk), `DEMAND_SURGE` / `DEMAND_DROP`, `PO_DEFERRED` (supply risk), `FORECAST_ADJUSTED` |
| **ForecastAdjTRM** (Nurse) | `FORECAST_ADJUSTED` | `DEMAND_SURGE` / `DEMAND_DROP`, `ORDER_EXCEPTION`, external signals (email, market intel) |
| **QualityTRM** (Guard) | `QUALITY_REJECT`, `QUALITY_HOLD` | `MO_RELEASED` (incoming batch), `ATP_SHORTAGE` (pressure to accept borderline) |
| **MaintenanceTRM** (Guard) | `MAINTENANCE_DEFERRED`, `MAINTENANCE_URGENT` | `MO_RELEASED` (schedule around), capacity from tGNN, `QUALITY_REJECT` (asset issue?) |
| **MOExecutionTRM** (Builder) | `MO_RELEASED`, `MO_DELAYED` | `QUALITY_HOLD` (material held), `MAINTENANCE_URGENT` (asset unavailable), `ATP_SHORTAGE` (priority up), `SUBCONTRACT_ROUTED` (reduced internal load) |
| **TOExecutionTRM** (Builder) | `TO_RELEASED`, `TO_DELAYED` | `REBALANCE_INBOUND` / `REBALANCE_OUTBOUND`, `ATP_SHORTAGE` at destination, `NETWORK_*` signals from tGNN |

### 2.5 Signal Propagation Mechanisms

Signals propagate via three mechanisms, chosen based on latency requirements:

#### Mechanism 1: Shared Urgency Vector (Pheromone Layer) — <1ms

A fixed-size float vector (length 11, one per TRM type) that represents current urgency state. Updated atomically after every TRM decision. All TRMs read this before executing.

```python
class UrgencyVector:
    """Pheromone-like shared urgency state. All TRMs read, each TRM writes its slot."""

    TRM_INDICES = {
        "atp_executor": 0,  "order_tracking": 1,  "po_creation": 2,
        "rebalancing": 3,   "subcontracting": 4,  "safety_stock": 5,
        "forecast_adj": 6,  "quality": 7,          "maintenance": 8,
        "mo_execution": 9,  "to_execution": 10,
    }

    def __init__(self):
        self.values = [0.0] * 11            # Current urgency per TRM
        self.directions = ["neutral"] * 11  # shortage/surplus/risk/relief
        self.last_updated = [None] * 11
```

#### Mechanism 2: Signal Queue (Event-Driven) — <10ms

A bounded ring buffer of `HiveSignal` objects. Producers append; consumers filter by signal type. Signals decay over time (pheromone behavior).

```python
class HiveSignalBus:
    """Ring buffer of typed signals with pheromone decay."""

    def __init__(self, max_signals: int = 200):
        self.signals: collections.deque = collections.deque(maxlen=max_signals)
        self.urgency: UrgencyVector = UrgencyVector()

    def emit(self, signal: HiveSignal):
        """TRM emits a signal after making a decision."""
        self.signals.append(signal)
        self.urgency.update(signal.source_trm, signal.urgency, signal.direction)

    def read(self, consumer_trm: str, since: datetime,
             types: Optional[Set[HiveSignalType]] = None) -> List[HiveSignal]:
        """TRM reads relevant signals before making a decision."""
        return [s for s in self.signals
                if s.timestamp > since
                and s.current_strength > 0.05  # Decay filter
                and (types is None or s.signal_type in types)
                and s.source_trm != consumer_trm]  # Don't read own signals
```

#### Mechanism 3: Decision Log Query (Historical) — <500ms

For deeper context, TRMs can query the `powell_site_agent_decisions` table for recent decisions by other TRMs at the same site. This is the "colony memory" mechanism.

### 2.6 External Channel Signal Ingestion

The Hive's signal bus receives signals not only from internal TRM decisions but also from **external channels** captured by PicoClaw and OpenClaw (see [PICOCLAW_OPENCLAW_IMPLEMENTATION.md](PICOCLAW_OPENCLAW_IMPLEMENTATION.md) Phase 5).

#### Signal Sources and Capture Gateways

```
EXTERNAL WORLD                     CAPTURE GATEWAY              HIVE SIGNAL BUS
──────────────                     ───────────────              ───────────────
Email (customer PO update) ───┐
Slack (sales team @mention) ──┤
Teams (planner message) ──────┤    OpenClaw                    ┌──────────────┐
WhatsApp (field report) ──────┤    signal-capture     POST     │ Signal       │
Telegram (supplier update) ───┤    skill           ─────────►  │ Ingestion    │
Voice note (sales call) ──────┘    (LLM classifies)   /ingest │ Service      │
                                                               │              │
Weather API (severe alerts) ──┐                                │  Validates   │
Economic data (PMI, CPI) ────┤    PicoClaw                    │  → FcstAdj   │
News RSS (disruption) ───────┤    MARKET_SIGNAL.sh    POST    │    TRM eval  │
Commodity prices ─────────────┤    (deterministic)  ─────────►│  → Confidence│
IoT sensor (temperature) ────┘    No LLM              /ingest │    gate      │
                                                               │  → HiveSignal│
                                                               └──────────────┘
```

#### How External Signals Enter the Hive

External signals are ingested through the **Signal Ingestion Service** (new, see Phase 5) which:

1. **Validates** product_id and site_id against the supply chain config
2. **Creates** a `ForecastAdjustmentState` from the captured signal
3. **Evaluates** via ForecastAdjustmentTRM (source reliability × time decay × confidence)
4. **Gates** by confidence threshold:
   - ≥0.8: Auto-apply → emit `FORECAST_ADJUSTED` on HiveSignalBus
   - 0.3-0.8: Escalate to human via OpenClaw chat
   - <0.3: Reject and log
5. **Correlates** multi-channel signals (2+ signals about same product/direction within 2h boost combined confidence)

#### External Signal Types on the HiveSignalBus

When external signals pass the confidence gate, they appear on the signal bus as standard `HiveSignal` objects with `source_trm = "external"`:

| External Source | HiveSignalType | Consumed By | Example |
|---|---|---|---|
| Customer email: "doubling our Q2 order" | `DEMAND_SURGE` | POCreationTRM, SafetyStockTRM | Foragers pre-order, Nurses increase buffer |
| Supplier Slack: "factory fire, 3-week delay" | `INBOUND_DELAY` + `FORECAST_ADJUSTED` | POCreationTRM, RebalancingTRM | Foragers find alt source, Rebal pulls from network |
| Weather API: hurricane approaching | `DISRUPTION` | All TRMs (urgency broadcast) | Colony-wide alertness increase |
| Market feed: commodity price spike +15% | `FORECAST_ADJUSTED` (cost) | POCreationTRM, SubcontractingTRM | Foragers evaluate make-vs-buy shift |
| Sales voice note: "ACME confirms expansion" | `DEMAND_SURGE` | POCreationTRM, SafetyStockTRM, MOExecutionTRM | Full colony response to confirmed demand |

#### Security Boundary

External signals pass through multiple security layers before reaching the hive (see [PICOCLAW_OPENCLAW_IMPLEMENTATION.md — Security](#security--risk-mitigation)):

1. **Channel authentication**: SPF/DKIM/DMARC for email, webhook secrets for Telegram, bot tokens for Slack
2. **Autonomy RBAC**: Signal Ingestion API requires authenticated service account
3. **Rate limiting**: 100 signals/hour/source, 500/hour global
4. **Input sanitization**: Control characters and prompt injection patterns stripped
5. **ForecastAdjustmentTRM confidence gate**: Only high-confidence signals auto-apply (0.8 threshold)
6. **Adjustment cap**: Maximum ±50% adjustment (±15% for low-confidence sources)

This layered defense ensures that even a compromised channel adapter cannot flood the hive with false signals or execute unauthorized adjustments.

---

## 3. Hive Decision Sequencing

### 3.1 Six-Phase Decision Cycle

Within a single execution cycle, TRMs execute in a defined sequence that respects information flow — scouts first (detect), then nurses (assess), then foragers (acquire), then guards (protect), then builders (execute), then the queen reflects:

```
DECISION CYCLE (triggered by: scheduled cadence, event, or CDC trigger)
=======================================================================

Phase 1: SENSE (Scouts detect demand/exception signals)
  │
  │  1a. OrderTrackingTRM  ── scan active orders for exceptions
  │  1b. ATPExecutorTRM    ── process pending orders, detect shortages
  │  │
  │  Emit: ORDER_EXCEPTION, ATP_SHORTAGE, DEMAND_SURGE, DEMAND_DROP
  │
  ▼
Phase 2: ASSESS (Nurses evaluate colony health given new signals)
  │
  │  2a. ForecastAdjustmentTRM  ── process external signals + scout signals
  │  2b. SafetyStockTRM         ── evaluate buffer adequacy
  │  │
  │  Emit: FORECAST_ADJUSTED, SS_INCREASED, SS_DECREASED
  │
  ▼
Phase 3: ACQUIRE (Foragers secure resources based on assessed needs)
  │
  │  3a. POCreationTRM       ── create/expedite purchase orders
  │  3b. RebalancingTRM      ── evaluate inter-site transfers
  │  3c. SubcontractingTRM   ── evaluate make-vs-buy alternatives
  │  │
  │  Emit: PO_EXPEDITE, REBALANCE_INBOUND/OUTBOUND, SUBCONTRACT_ROUTED
  │
  ▼
Phase 4: PROTECT (Guards ensure quality and asset health)
  │
  │  4a. QualityDispositionTRM      ── process quality orders
  │  4b. MaintenanceSchedulingTRM   ── evaluate maintenance needs
  │  │
  │  Emit: QUALITY_REJECT, QUALITY_HOLD, MAINTENANCE_URGENT
  │
  ▼
Phase 5: BUILD (Builders execute production and logistics)
  │
  │  5a. MOExecutionTRM  ── release/sequence/expedite MOs
  │  5b. TOExecutionTRM  ── release/consolidate/expedite TOs
  │  │
  │  Emit: MO_RELEASED, MO_DELAYED, TO_RELEASED, TO_DELAYED
  │
  ▼
Phase 6: REFLECT (Queen evaluates cycle outcome)
  │
  │  6a. SiteAgent aggregates signals, updates urgency_vector
  │  6b. Check for unresolved conflicts (e.g., quality reject + ATP shortage)
  │  6c. If conflicts: run micro-cycle with affected TRMs only
  │  6d. Persist decision log, emit tGNN feedback features
  │
  ═══════ END CYCLE ═══════
```

### 3.2 Reactive vs. Proactive TRMs

| TRM | Mode | Trigger |
|---|---|---|
| ATPExecutorTRM | **REACTIVE** | Incoming order event |
| OrderTrackingTRM | **REACTIVE** | Exception detected by engine check |
| QualityDispositionTRM | **REACTIVE** | Quality order created after inspection |
| MOExecutionTRM | **REACTIVE** | MO available for release |
| TOExecutionTRM | **REACTIVE** | TO available for release |
| POCreationTRM | **PROACTIVE** | Scheduled (4h cadence) or signal-triggered |
| RebalancingTRM | **PROACTIVE** | Scheduled (daily) or signal-triggered |
| SubcontractingTRM | **PROACTIVE** | Scheduled (daily) or capacity signal |
| SafetyStockTRM | **PROACTIVE** | Scheduled (weekly) or CDC trigger |
| ForecastAdjustmentTRM | **PROACTIVE** | External signal arrives or scheduled |
| MaintenanceSchedulingTRM | **PROACTIVE** | Scheduled + asset condition signals |

### 3.3 Cascading Decision Flows

**Cascade 1: ATP Shortage → PO Expedite → Rebalancing Check**

```
Customer order arrives
     │
ATPExecutorTRM: allocation exhausted, partial fill
     │
EMIT: ATP_SHORTAGE (urgency=0.8, direction="shortage", magnitude=500 units)
     │
POCreationTRM READS ATP_SHORTAGE ── urgency_boost = 0.8
     │
POCreationTRM: expedite PO, quantity = (shortage + safety_buffer)
     │
EMIT: PO_EXPEDITE (urgency=0.7, direction="relief", eta=5 days)
     │
RebalancingTRM READS ATP_SHORTAGE + PO_EXPEDITE
     │
RebalancingTRM: "relief arriving in 5d, but gap is 2d"
     │
EMIT: REBALANCE_INBOUND (urgency=0.6, direction="relief", eta=1 day)
```

**Cascade 2: Quality Reject → ATP Impact → MO Expedite**

```
Inspection completes
     │
QualityTRM: defect rate 8% > threshold, REJECT batch
     │
EMIT: QUALITY_REJECT (urgency=0.9, product_id="SKU-A", qty=200)
     │
ATPExecutorTRM: available inventory reduced by 200
     │
EMIT: ATP_SHORTAGE (urgency=0.7, magnitude=200)
     │
MOExecutionTRM READS QUALITY_REJECT + ATP_SHORTAGE
     │
MOExecutionTRM: expedite next production run for SKU-A
     │
EMIT: MO_RELEASED (urgency=0.5, direction="relief", eta=3 days)
```

**Cascade 3: Maintenance Urgent → Subcontract Route → MO Defer**

```
Asset condition degrades
     │
MaintenanceTRM: failure probability > threshold, SCHEDULE NOW
     │
EMIT: MAINTENANCE_URGENT (urgency=0.9, asset_id="LINE-3", downtime=16h)
     │
MOExecutionTRM READS MAINTENANCE_URGENT
     │
MOExecutionTRM: defer MO-456 (was scheduled on LINE-3)
     │
EMIT: MO_DELAYED (urgency=0.6, product_id="SKU-B")
     │
SubcontractingTRM READS MO_DELAYED + MAINTENANCE_URGENT
     │
SubcontractingTRM: route SKU-B to external vendor
     │
EMIT: SUBCONTRACT_ROUTED (urgency=0.4, direction="relief")
```

---

## 4. Shared Decision Log (Colony Memory)

### 4.1 Schema Extension

The colony memory extends the existing `powell_site_agent_decisions` table:

| Column | Type | Purpose |
|---|---|---|
| `decision_id` | VARCHAR | Unique decision identifier (existing) |
| `site_key` | VARCHAR | Which hive (existing) |
| `decision_type` | VARCHAR | Which worker / TRM type (existing) |
| `timestamp` | TIMESTAMP | When decided (existing) |
| `input_state` | JSONB | Raw state at decision time (existing) |
| `deterministic_result` | JSONB | Engine baseline result (existing) |
| `trm_adjustment` | JSONB | TRM delta from baseline (existing) |
| `confidence` | FLOAT | TRM confidence [0,1] (existing) |
| `final_result` | JSONB | Actual applied decision (existing) |
| `actual_outcome` | JSONB | What happened, filled later (existing) |
| `reward_signal` | FLOAT | Computed reward, filled later (existing) |
| **`signal_context`** | **JSONB** | **Active HiveSignals read before decision** |
| **`urgency_at_time`** | **FLOAT[11]** | **UrgencyVector snapshot at decision time** |
| **`triggered_by`** | **VARCHAR[]** | **Signal types that triggered this decision** |
| **`signals_emitted`** | **JSONB** | **HiveSignals produced by this decision** |
| **`cycle_phase`** | **INTEGER** | **Which phase (1-6) in decision cycle** |
| **`cycle_id`** | **VARCHAR** | **Groups decisions in same cycle** |

### 4.2 Hive Health Metrics

The SiteAgent maintains running metrics that all TRMs can read as context, updated after each decision cycle:

```python
@dataclass
class HiveHealthMetrics:
    """Running colony health metrics, updated each cycle."""
    site_key: str

    # Trend windows (rolling 7d, 30d)
    backlog_trend_7d: float        # Slope of backlog over 7 days
    backlog_trend_30d: float       # Slope of backlog over 30 days
    fill_rate_7d: float            # Average fill rate (7d rolling)
    fill_rate_30d: float           # Average fill rate (30d rolling)

    # Cost trajectory
    holding_cost_trend: float      # Slope of daily holding cost
    stockout_cost_trend: float     # Slope of daily stockout cost
    total_cost_trajectory: float   # Combined cost slope

    # Signal summary
    active_shortage_signals: int   # Count of active ATP_SHORTAGE signals
    active_relief_signals: int     # Count of active *_INBOUND / *_RELEASED signals
    net_urgency: float             # Sum of urgency_vector values
    dominant_urgency_source: str   # TRM with highest urgency

    # Performance
    decisions_last_24h: int
    trm_override_rate: float       # How often TRM changed engine result
    avg_confidence: float          # Average TRM confidence
```

---

## 5. tGNN as Inter-Hive Connective Tissue

### 5.1 Current Architecture Gap

The `HybridPlanningModel` (SOPGraphSAGE + ExecutionTemporalGNN) produces per-node outputs that the `AllocationService` converts into priority buckets. However:

1. **No coordination signals**: tGNN outputs per-node predictions but does not explicitly encode inter-site coordination needs
2. **No feedback loop**: TRM consumption patterns do not feed back to tGNN features
3. **S&OP parameters not consumed**: `safety_stock_multiplier` from SOPGraphSAGE is not read by SiteAgent's SafetyStockTRM
4. **No disruption propagation awareness**: If Site A's supplier fails, Site B's TRMs do not know until the daily tGNN refresh

### 5.2 Inter-Hive Communication Channels

```
┌────────────────────────────────────────────────────────────────────────┐
│                      NETWORK LAYER (tGNN)                              │
│                                                                        │
│   S&OP GraphSAGE (weekly)           Execution tGNN (daily)            │
│   ┌──────────────────────┐         ┌───────────────────────────┐      │
│   │ structural_embeddings│────────>│ + transactional features  │      │
│   │ criticality_score    │         │                           │      │
│   │ bottleneck_risk      │         │ Outputs per site:         │      │
│   │ concentration_risk   │         │ - order_recommendation    │      │
│   │ resilience_score     │         │ - demand_forecast         │      │
│   │ safety_stock_mult    │         │ - exception_probability   │      │
│   │ network_risk [4]     │         │ - propagation_impact      │      │
│   └──────────┬───────────┘         └─────────────┬─────────────┘      │
│              │                                   │                     │
└────────────────────────────────────────────────────────────────────────┘
               │                                   │
    ┌──────────▼───────────┐            ┌──────────▼───────────┐
    │ HIVE-A (DC-East)     │            │ HIVE-B (DC-West)     │
    │ Signal Bus           │            │ Signal Bus           │
    │  reads: ss_mult,     │            │  reads: ss_mult,     │
    │  criticality,        │            │  criticality,        │
    │  propagation_impact  │            │  propagation_impact  │
    └──────────┬───────────┘            └──────────┬───────────┘
               │                                   │
               └──────> FEEDBACK FEATURES <────────┘
                  (consumption patterns,
                   decision outcomes,
                   urgency_vector snapshots)
```

### 5.3 Inter-Hive Signal Types

The Execution tGNN produces coordination signals beyond allocations:

```python
class InterHiveSignalType(str, Enum):
    # Supply coordination
    UPSTREAM_DISRUPTION  = "upstream_disruption"   # Supplier problem propagating
    DOWNSTREAM_SURGE     = "downstream_surge"      # Demand spike propagating
    LATERAL_SURPLUS      = "lateral_surplus"        # Neighbor site has excess
    LATERAL_SHORTAGE     = "lateral_shortage"       # Neighbor site needs help

    # Allocation coordination
    ALLOCATION_REBALANCE = "allocation_rebalance"   # Shift allocation priorities
    PRIORITY_OVERRIDE    = "priority_override"      # Emergency priority change

    # Network health
    BOTTLENECK_FORMING   = "bottleneck_forming"     # Congestion detected
    RESILIENCE_WARNING   = "resilience_warning"     # Network vulnerability
    BULLWHIP_DETECTED    = "bullwhip_detected"      # Demand amplification
```

```python
@dataclass
class InterHiveSignal:
    """Signal from tGNN to a specific hive (site)."""
    target_site: str
    signal_type: InterHiveSignalType
    timestamp: datetime

    source_sites: List[str]         # Which sites generated the pattern
    urgency: float                  # 0-1
    confidence: float               # tGNN output confidence

    recommended_action: str         # "increase_ss", "pull_from_X", "defer_orders"
    allocation_adjustment: Optional[Dict[int, float]] = None  # Priority rebalance
    propagation_timeline: Optional[List[float]] = None  # Impact by period
```

### 5.4 tGNN Site Directive

Each hive receives a consolidated directive from the network layer:

```python
@dataclass
class tGNNSiteDirective:
    """Per-site directive from tGNN that the Hive consumes."""
    site_key: str

    # From S&OP GraphSAGE (cached weekly)
    structural_embedding: List[float]   # 64-dim embedding
    criticality_score: float            # How important is this site
    bottleneck_risk: float              # Congestion risk
    safety_stock_multiplier: float      # SS adjustment from network context
    resilience_score: float             # Network resilience around this site

    # From Execution tGNN (daily)
    demand_forecast: List[float]        # 4-period forecast
    exception_probability: List[float]  # [stockout, overstock, normal]
    propagation_impact: List[float]     # If disruption hits, when downstream feels it
    order_recommendation: float         # Suggested order quantity
    confidence: float                   # tGNN confidence for this site

    # Inter-hive coordination
    inter_hive_signals: List[InterHiveSignal]
    allocation_adjustments: Dict[int, float]  # Priority rebalance suggestions
```

**How each TRM uses the directive**:

| TRM | tGNN Directive Consumption |
|---|---|
| ATPExecutorTRM | `allocation_adjustments` → priority shift; `exception_probability` → threshold adjustment |
| SafetyStockTRM | `safety_stock_multiplier` → SS target; `resilience_score` → buffer sizing |
| POCreationTRM | `demand_forecast` → order quantity; `propagation_impact` → timing urgency |
| RebalancingTRM | `LATERAL_SURPLUS/SHORTAGE` signals; `criticality_score` → transfer priority |
| MOExecutionTRM | `bottleneck_risk` → sequencing priority; `demand_forecast` → production scheduling |
| ForecastAdjTRM | `demand_forecast` → baseline comparison; `exception_probability` → adjustment bias |

### 5.5 Propagation Example: Site A Supplier Failure → Network Response

```
t=0:  Supplier X fails to deliver to Site A (Factory)
      │
      Site A's OrderTrackingTRM detects:
        PO-123 is 3 days late, supplier_on_time_rate drops
      │
      EMIT to Signal Bus: ORDER_EXCEPTION(urgency=0.8)
      Site A's CDC Monitor fires: SUPPLIER_RELIABILITY trigger

      ═══ FEEDBACK TO tGNN (via daily feature refresh) ═══

t=1h: Site A's transactional features at next tGNN run:
        current_backlog: UP
        incoming_orders: UNCHANGED (demand still coming)
        actual_lead_time: INCREASED
        recent_reliability: DOWN
      │
      ExecutionTemporalGNN processes all sites simultaneously:
        Spatial GATv2 attention: Site A's disrupted features propagate
        to Site B (downstream DC) via edge message passing
      │
      tGNN outputs for Site B:
        exception_probability: [stockout=0.35, overstock=0.05, normal=0.60]
        propagation_impact: [0.0, 0.1, 0.4, 0.7]  (impact in T+1..T+4)
        order_recommendation: INCREASE (build buffer)

      ═══ INTER-HIVE SIGNAL TO SITE B ═══

      InterHiveSignal(
        target_site="site_B",
        signal_type=UPSTREAM_DISRUPTION,
        source_sites=["site_A"],
        urgency=0.6,
        propagation_timeline=[0.0, 0.1, 0.4, 0.7],
        recommended_action="increase_ss_temporarily"
      )

t=2h: Site B's Signal Bus receives UPSTREAM_DISRUPTION
      │
      Site B's SafetyStockTRM READS signal → increases SS multiplier
      Site B's POCreationTRM READS signal → expedites next PO
      Site B's RebalancingTRM READS signal → checks if Site C has surplus

t=3d: Site C (has surplus, received LATERAL_SHORTAGE from Site B via tGNN):
        RebalancingTRM: REBALANCE_OUTBOUND to Site B (500 units)
        TOExecutionTRM: TO_RELEASED (expedited, 1-day transit)

t=5d: Supplier repairs complete, delivers to Site A
        OrderTrackingTRM: exception resolved
        tGNN detects recovery → propagation_impact declining
        InterHiveSignal: resilience returning to Sites B, C
        Sites B, C: SafetyStockTRM reads recovery → SS_DECREASED over 2 weeks
```

### 5.6 Temporal Cadence Bridge

| Component | Cadence | Signal Half-Life |
|---|---|---|
| S&OP GraphSAGE | Weekly/Monthly | Permanent (until next refresh) |
| Execution tGNN | Daily (or CDC off-cadence) | 12-24 hours |
| Local HiveSignals | Real-time (per event) | 30-120 minutes |
| UrgencyVector | Real-time (per decision) | Instant (overwritten each update) |

**Bridging mechanism**: If accumulated local signals indicate tGNN outputs are stale (e.g., 5+ ATP_SHORTAGE signals when tGNN predicted `normal`), CDC Monitor triggers early tGNN refresh. This prevents the 24h gap from causing cascading failures.

---

## 6. Feedback Loops

### 6.1 Hive → tGNN (Per-Site Decisions Aggregate to Network Input)

Each SiteAgent compiles a daily feedback feature vector for tGNN consumption:

```python
@dataclass
class HiveFeedbackFeatures:
    """Feedback from a single hive to the tGNN input pipeline."""
    site_key: str
    date: date

    # Aggregated from decision log
    total_decisions: int
    decisions_by_type: Dict[str, int]       # {atp: 15, po: 3, ...}
    avg_confidence: float
    override_rate: float                    # % of TRM decisions overriding engine

    # Aggregated from signal bus
    shortage_signal_count: int
    relief_signal_count: int
    net_urgency_avg: float                  # Average net_urgency over day
    dominant_urgency_type: str

    # Consumption patterns (for allocation learning)
    allocation_utilization_by_priority: Dict[int, float]  # P1: 95%, P2: 80%...
    cross_priority_consumption_pct: float   # How often orders consumed lower tiers
    partial_fill_rate: float                # % of orders partially filled

    # Performance
    fill_rate: float
    otif_rate: float
    backlog_change: float                   # Delta from yesterday
    inventory_position_change: float

    # CDC triggers
    cdc_triggers_fired: int
    cdc_severity_max: str
```

**Extended tGNN input features** (8 existing + 8 new = 16 total):

| Feature | Source | Dim |
|---|---|---|
| `current_inventory` | DB query | existing |
| `current_backlog` | DB query | existing |
| `incoming_orders` | DB query | existing |
| `outgoing_shipments` | DB query | existing |
| `orders_placed` | DB query | existing |
| `actual_lead_time` | DB query | existing |
| `capacity_used` | DB query | existing |
| `demand_signal` | DB query | existing |
| **`net_urgency_avg`** | **HiveFeedbackFeatures** | **new** |
| **`shortage_signal_density`** | **shortage signals / total decisions** | **new** |
| **`allocation_utilization`** | **avg across priorities** | **new** |
| **`cross_priority_rate`** | **allocation mismatch indicator** | **new** |
| **`trm_override_rate`** | **TRM disagreed with engine** | **new** |
| **`fill_rate_7d`** | **recent fulfillment** | **new** |
| **`cdc_severity_score`** | **0=none, 1=low, 2=med, 3=high, 4=critical** | **new** |
| **`backlog_velocity`** | **rate of backlog change** | **new** |

### 6.2 tGNN → Hive (Network Insights to Per-Site Behavior)

Currently disconnected. The proposed connection via `tGNNSiteDirective` (Section 5.4) delivers:

| TRM | What It Reads | How It Changes Behavior |
|---|---|---|
| SafetyStockTRM | `safety_stock_multiplier` | Sets upper/lower bounds for TRM adjustment |
| ATPExecutorTRM | `exception_probability`, allocation adjustments | Adjusts partial fill thresholds |
| POCreationTRM | `demand_forecast`, `propagation_impact` | Timing urgency for new POs |
| RebalancingTRM | `LATERAL_SURPLUS/SHORTAGE` signals | Identifies transfer opportunities |
| MOExecutionTRM | `bottleneck_risk` | Sequences production to avoid congestion |
| SubcontractingTRM | Capacity signals | Routes externally when bottleneck forming |

### 6.3 Hive ↔ Hive (Cross-Site Direct Coordination)

Leverages the existing `ConditionMonitorService.SupplyRequest` pattern:

```
Site A detects ATP_SHORTFALL persisting for 24h
     │
ConditionMonitorService escalates to WARNING
     │
If can_request_supply == True:
     │
    SupplyRequest(
        requesting_entity="site_A",
        requested_entity="site_B",    # Neighbor with surplus (from tGNN)
        product_id="SKU-X",
        quantity_needed=500,
        needed_by=tomorrow,
        priority=2,
        context={"signal_type": "ATP_SHORTFALL", "duration_hours": 24}
    )
     │
    Site B's RebalancingTRM evaluates:
        - Do I have surplus? (Check urgency_vector, backlog)
        - What's the cost? (Transfer cost, impact on my fill rate)
        - Net benefit? (from Agentic Authorization Protocol)
     │
    If net_benefit > threshold:
        Accept → EMIT: REBALANCE_OUTBOUND
    Else:
        Reject with reason → feeds back to requesting site
```

---

## 7. Emergent Behavior: Collective Intelligence

### 7.1 Bullwhip Dampening

The bullwhip effect — demand amplification from downstream to upstream — emerges when sites order based only on their local view. The Hive architecture dampens this through three mechanisms:

```
WITHOUT HIVE:
  Retailer sees demand spike ──> orders 2x from Wholesaler
  Wholesaler sees 2x orders ──> orders 3x from Distributor
  Distributor sees 3x orders ──> orders 5x from Factory
  Factory sees 5x orders ──> massive overproduction

WITH HIVE:
  Retailer's ATPExecutorTRM sees demand spike
    │
  EMIT: DEMAND_SURGE (urgency=0.6, magnitude=+50%)
    │
  Retailer's ForecastAdjTRM evaluates:
    Historical signal accuracy: demand surges revert 70% of the time
    Conformal interval: [+20%, +80%] at 90% coverage
    → Adjusted forecast: +35% (dampened from raw +50%)
    │
  EMIT: FORECAST_ADJUSTED (magnitude=+35%, not +50%)
    │
  tGNN sees Retailer's features: demand_signal UP, but orders_placed
    proportional to dampened forecast (not raw spike)
    │
  tGNN propagation model: Wholesaler gets exception_probability
    adjusted for Retailer's dampened response
    │
  Wholesaler's POCreationTRM reads tGNN directive:
    order_recommendation = Retailer demand × 1.35 (not × 2.0)

  RESULT: 35% amplification vs 100%+ without coordination
```

**Mechanism**: Three layers of dampening:
1. **Intra-hive** (ForecastAdjTRM): Conformal intervals constrain forecast adjustments
2. **Inter-hive** (tGNN): Spatial attention propagates dampened signals, not raw orders
3. **Cross-hive** (SupplyRequest): Net benefit threshold prevents panic ordering

### 7.2 Self-Healing Supply Chains

When a site experiences disruption, the Hive network adapts without central planning:

```
t=0:  Factory fire at Site C (manufacturer)
      Site C's MaintenanceTRM: MAINTENANCE_URGENT (urgency=1.0)
      Site C's MOExecutionTRM: MO_DELAYED (all MOs deferred)

t=1h: tGNN daily features updated (off-cadence CDC trigger)
      ExecutionTemporalGNN detects:
        Site C: capacity_used=0, backlog=GROWING
        Propagation model: Sites D, E (downstream DCs) feel it in 2-4 days
      InterHiveSignals generated:
        Site D: UPSTREAM_DISRUPTION (eta=2d, severity=HIGH)
        Site E: UPSTREAM_DISRUPTION (eta=4d, severity=MEDIUM)

t=2h: Sites D and E hives respond independently:
      Site D (high urgency):
        SafetyStockTRM: SS_INCREASED (multiplier=1.5)
        POCreationTRM: PO_EXPEDITE to alternate supplier
        RebalancingTRM: pull excess from Site F
        SubcontractingTRM: evaluate external production
      Site E (medium urgency):
        SafetyStockTRM: SS_INCREASED (multiplier=1.2)
        POCreationTRM: schedule forward buy
        (No rebalancing yet — 4 day buffer)

t=3d: Site F (has surplus, received LATERAL_SHORTAGE from Site D):
        RebalancingTRM: REBALANCE_OUTBOUND to Site D (500 units)
        TOExecutionTRM: TO_RELEASED (expedited, 1-day transit)

t=5d: Factory repairs complete at Site C
        MaintenanceTRM: maintenance completed
        MOExecutionTRM: backlog clearing begins
        tGNN detects recovery → propagation_impact declining
        InterHiveSignal: UPSTREAM recovery to Sites D, E
        Sites D, E: SafetyStockTRM → SS_DECREASED (back to 1.0 over 2 weeks)
```

### 7.3 Autonomous Risk Redistribution

The network collectively redistributes risk based on each site's resilience and criticality:

```
S&OP GraphSAGE computes (weekly):
  Site A: criticality=0.9, resilience=0.4  → HIGH RISK (critical but fragile)
  Site B: criticality=0.3, resilience=0.8  → LOW RISK (non-critical, robust)
  Site C: criticality=0.7, resilience=0.6  → MEDIUM RISK

Network-level policy: Total SS budget = $10M

WITHOUT HIVE: Each site gets equal SS budget ($3.3M each)

WITH HIVE: SS budget allocated by risk-weighted criticality:
  Site A: $5M    (high criticality, low resilience = needs most buffer)
  Site B: $1.5M  (low criticality, high resilience = needs least)
  Site C: $3.5M  (medium both)

Implementation: S&OP safety_stock_multiplier flows through tGNNSiteDirective:
  Site A: 1.50 (50% above baseline)
  Site B: 0.75 (25% below baseline)
  Site C: 1.10 (10% above baseline)
```

---

## 8. Powell Framework Alignment

### 8.1 Five-Element Mapping

| Powell Element | Hive Implementation |
|---|---|
| **State (Sₜ)** | Physical state (inventory, backlog, pipeline) + Belief state (conformal intervals) + **Hive state** (urgency_vector, active signals, hive_health_metrics) + **Network state** (tGNNSiteDirective) |
| **Decision (xₜ)** | Per-TRM narrow decisions within authority bounds: ATP accept/partial/reject, PO create/expedite/defer, SS multiply ×[0.5, 2.0], etc. (bounded adjustments, not raw actions) |
| **Exogenous (Wₜ₊₁)** | Customer orders arriving, supplier delivery events, quality inspection results, external signals (email, market intel), **tGNN inter-hive signals** |
| **Transition (Sᴹ)** | Engine computation (MRP, AATP, Safety Stock) + TRM bounded adjustment + **HiveSignalBus state update** + **Colony memory (decision log) update** |
| **Objective (min C)** | Multi-objective: service level, cost, OTIF. Computed as reward by OutcomeCollector. Fed back through replay buffer. |

### 8.2 Policy Class Mapping

| Powell Policy Class | Hive Component | How It Works |
|---|---|---|
| **CFA** (Cost Function Approximation) | S&OP GraphSAGE + Deterministic Engines (MRP, AATP, SS) | S&OP computes policy parameters θ (safety_stock_multiplier, criticality) that parameterize ALL hive decisions. Engines implement CFA with fixed formulas parameterized by θ. Updated weekly. |
| **CFA/VFA Bridge** | Execution tGNN | Generates priority allocations (CFA: parameterized optimization) and propagation predictions (VFA: learned from outcomes). Bridges network-level policy to per-site execution. |
| **VFA** (Value Function Approximation) | 11 TRM Heads + Colony Memory | Each TRM learns a narrow value function through RL/TD. State = shared_embedding + **signal_context** + **tGNN_directive**. Action = bounded adjustment. Reward = outcome from collector. Replay buffer enriched with signal context for learning coordination patterns. |
| **PFA** (Policy Function Approximation) | Base-stock rules in engines | Deterministic engines implement PFA (reorder point, EOQ, safety stock formulas). TRM VFA learns **when to deviate** from PFA baselines. |
| **DLA** (Direct Lookahead) | Stochastic Program + MPC | Monte Carlo scenario evaluation for what-if analysis. Used when CDC triggers FULL_CFA and for human-facing Ask Why explanations. |

### 8.3 Signal Bus as State Transition Enrichment

In Powell's framework, the transition function `Sᴹ(Sₜ, xₜ, Wₜ₊₁)` updates the state given the decision and new information. The Signal Bus enriches this:

```
Traditional:   S_{t+1} = f(inventory, orders, shipments)
                         ^ only physical state

Hive-enriched: S_{t+1} = f(physical_state,
                            urgency_vector,
                            active_signals,
                            tGNN_directive,
                            hive_health_metrics)
                         ^ physical + belief + coordination state
```

This means the TRM's state representation now includes what other workers are doing and what the network says is happening, enabling it to learn contextually richer policies.

### 8.4 Colony Memory as Belief State Extension

Powell's belief state `Sᵇₜ` captures what we believe about uncertain quantities. The colony memory extends this:

| Standard Belief State (existing) | Colony Memory Extension (new) |
|---|---|
| demand_forecast + conformal interval | Recent TRM decision patterns (which TRMs fire most?) |
| lead_time_estimate + conformal interval | Signal frequency distribution (shortage signals increasing?) |
| yield_estimate + conformal interval | Cross-TRM interaction patterns (ATP shortage always followed by PO?) |
| | Network coordination success rate (did rebalancing help last time?) |
| | Reward trajectory (are decisions improving over cycles?) |

---

## 9. Implementation Sequencing

### Phase 1: Intra-Hive Signals (2-3 weeks)

1. Implement `HiveSignal`, `HiveSignalType`, `UrgencyVector` data structures
2. Implement `HiveSignalBus` with ring buffer and decay
3. Add signal emission hooks to existing TRM services (ATP, PO, SafetyStock first)
4. Add signal consumption to `SharedStateEncoder` (extend input features)
5. Add `signal_context` and `urgency_at_time` columns to `powell_site_agent_decisions`

### Phase 2: Decision Sequencing (1-2 weeks)

1. Implement phase-based execution ordering in SiteAgent
2. Add conflict detection (Phase 6 micro-cycle)
3. Wire `cycle_id` and `cycle_phase` to decision log

### Phase 3: tGNN Inter-Hive Signals (2-3 weeks)

1. Extend `ExecutionTemporalGNN` input features from 8 to 16 dimensions
2. Add `InterHiveSignal` generation from tGNN output post-processing
3. Implement `tGNNSiteDirective` and cache at each SiteAgent
4. Wire `safety_stock_multiplier` from S&OP to SafetyStockTRM bounds
5. Implement CDC-triggered off-cadence tGNN refresh

### Phase 4: Feedback Loops (2-3 weeks)

1. Implement `HiveFeedbackFeatures` aggregation (daily)
2. Wire feedback features into tGNN training pipeline
3. Extend `OutcomeCollectorService` to include signal_context in reward computation
4. Implement cross-TRM reward attribution (did the PO expedite caused by ATP shortage signal result in better fill rate?)

### Phase 5: Colony Learning (Ongoing)

1. Extend TRM training to include signal_context as input features
2. Implement joint optimization: reward includes not just own outcome but downstream TRM outcomes
3. Curriculum learning: Phase 1 = single TRM, Phase 2 = TRM + signals, Phase 3 = TRM + signals + tGNN directives

---

## 10. Hive-to-AAP Integration (Agent-to-Agent Authorization)

### 10.1 Architectural Relationship

The Hive architecture and the Agentic Authorization Protocol (AAP, see [AGENTIC_AUTHORIZATION_PROTOCOL.md](docs/AGENTIC_AUTHORIZATION_PROTOCOL.md)) operate at different layers of the same decision architecture:

| Layer | Mechanism | Scope | Speed | Metaphor |
|---|---|---|---|---|
| **Intra-Hive Signals** | HiveSignalBus, UrgencyVector | Within a single site | <10ms | Nervous system (reflexive) |
| **Hive-Level Decisions** | TRM bounded adjustments | Single TRM within authority | ms-seconds | Worker bee acting on pheromone |
| **Inter-Hive Coordination** | tGNN + InterHiveSignal | Cross-site passive | daily refresh | Foraging map (shared knowledge) |
| **AAP Authorization** | AuthorizationRequest/Response | Cross-authority negotiation | seconds-minutes | Treaty negotiation between colonies |
| **Human Escalation** | Pre-digested options | Unresolvable contention | minutes-hours | Beekeeper intervention |
| **S&OP Consensus Board** | PolicyEnvelope parameter negotiation | Enterprise-wide policy | hours-days | Colony federation governance |

**The Hive is the detection and execution layer. The AAP is the deliberation and authorization layer.** Signals detect that something needs to change; the AAP negotiates who has authority to change it and whether the change is worth making.

### 10.2 Caste-to-Authority Mapping

Each TRM worker caste maps to specific AAP agent authority boundaries:

| Caste | TRM Workers | AAP Agent Authority | Unilateral Actions | Requires Authorization From |
|---|---|---|---|---|
| **Scouts** | ATPExecutorTRM, OrderTrackingTRM | SO/ATP Agent | Reallocate within priority tier, partial fill within policy | Logistics (expedite), Inventory (cross-DC transfer) |
| **Foragers** | POCreationTRM, RebalancingTRM, SubcontractingTRM | Supply Agent, Procurement Agent | Select supplier within approved list, adjust PO timing | Procurement (new supplier), Logistics (freight mode), S&OP (policy exception) |
| **Nurses** | SafetyStockTRM, ForecastAdjustmentTRM | Inventory Agent, Demand Agent | Adjust SS within policy bounds, revise forecast within confidence band | S&OP (SS exception), Finance (working capital impact) |
| **Guards** | QualityDispositionTRM, MaintenanceSchedulingTRM | Quality Agent, Maintenance Agent | Place material on hold, schedule PM within window | Plant (production rerun), Finance (write-off), Supply (return to vendor) |
| **Builders** | MOExecutionTRM, TOExecutionTRM | Plant Agent, Logistics Agent | Schedule within approved plan, sequence within rules | Supply (rush order insertion), Quality (release hold), Maintenance (schedule around) |

### 10.3 Signal-to-Authorization Escalation

When a HiveSignal indicates a condition that cannot be resolved within the hive's unilateral authority, it triggers an AAP AuthorizationRequest:

```
INTRA-HIVE SIGNAL DETECTION
     │
     │  ATPExecutorTRM detects ATP_SHORTAGE (urgency=0.8)
     │  POCreationTRM reads signal → creates PO_EXPEDITE
     │  BUT: Preferred supplier requires Procurement authorization
     │         (new supplier, or concentration limit breach)
     │
     ▼
SIGNAL → AUTHORIZATION ESCALATION
     │
     │  POCreationTRM's unilateral authority: select supplier within approved list
     │  Best option (secondary supplier, -$2K premium): REQUIRES_AUTH from Procurement
     │
     │  HiveSignal context becomes AuthorizationRequest trigger_context:
     │  {
     │    "trigger_signal": "ATP_SHORTAGE",
     │    "urgency": 0.8,
     │    "signal_chain": ["ATP_SHORTAGE → PO_EXPEDITE"],
     │    "hive_health": { "fill_rate_7d": 0.89, "backlog_trend": "increasing" }
     │  }
     │
     ▼
AAP PROTOCOL (Evaluate → Request → Authorize)
     │
     │  POCreationTRM (via Supply Agent) runs what-if on all options:
     │    Option A: Approved supplier, 3-week lead time → NET_BENEFIT = +$5K
     │    Option B: Secondary supplier, 5-day lead time, $2K premium → NET_BENEFIT = +$18K
     │    Option C: Spot buy, 2-day delivery, $5K premium → NET_BENEFIT = +$12K
     │
     │  Best option (B) requires Procurement Agent authorization
     │
     │  AuthorizationRequest sent to Procurement Agent
     │  with full Balanced Scorecard + hive signal context
     │
     ▼
RESOLUTION → FEEDS BACK TO HIVE
     │
     │  Procurement Agent: AUTHORIZE (concentration limit still met)
     │  PO placed with secondary supplier
     │  EMIT: PO_EXPEDITE (urgency=0.7, direction="relief", eta=5d)
     │  Signal propagates to ATPExecutorTRM, SafetyStockTRM via Signal Bus
```

### 10.4 Inter-Hive Coordination via AAP

The tGNN's InterHiveSignals provide passive coordination (directional hints), but some situations require active negotiation between hives. This is where the AAP's cross-site authorization surfaces activate:

```
tGNN PASSIVE COORDINATION (InterHiveSignal)
     │
     │  tGNN detects Site A has LATERAL_SURPLUS of SKU-X
     │  InterHiveSignal to Site B: LATERAL_SURPLUS available
     │
     │  Site B's RebalancingTRM reads signal
     │  Evaluates: "I need 500 units, Site A has 800 excess"
     │
     ▼
CONDITION: Can resolve within unilateral authority?
     │
     ├── YES: ConditionMonitorService.SupplyRequest
     │         (existing pattern, <500ms, DB-backed)
     │         Site B requests → Site A evaluates → Accept/Reject
     │
     └── NO:  Requires authorization (e.g., transfer crosses budget,
              depletes Site A below safety stock, requires Logistics expedite)
              │
              ▼
         AAP AuthorizationThread
              │
              Site B's Inventory Agent → Site A's Inventory Agent:
              "Transfer 500 units SKU-X, cost $3,200, ETA 2 days"
              │
              Site A evaluates: "500 units depletes my SS to 60% (RED)"
              │
              COUNTER_OFFER: "Transfer 300 units (SS stays at 80%)"
              │
              Board Service auto-joins Finance Agent (tag: expedite_cost)
              Finance Agent: AUTHORIZE ($3,200 within budget)
              │
              Site B accepts counter-offer → REBALANCE_INBOUND (300 units)
```

### 10.5 Board-as-Substrate for Hive Federation

The AAP's Board Service (AuthorizationThread/Message tables) serves as the inter-hive "parliament" for decisions that require deliberation beyond tGNN passive coordination:

| Coordination Type | Mechanism | When Used |
|---|---|---|
| **Intra-hive** | HiveSignalBus | Always — reflexive coordination between TRM workers |
| **Inter-hive passive** | tGNN InterHiveSignal + ConditionMonitorService.SupplyRequest | When tGNN identifies coordination opportunities and both sites agree unilaterally |
| **Inter-hive active** | AAP AuthorizationThread via Board Service | When coordination crosses authority boundaries (budget, policy, capacity) |
| **Multi-hive** | AAP Multi-Party Authorization | When resolution requires 3+ sites (e.g., Site A shortage → Site B transfer → Site C upstream supply) |
| **Policy-level** | AAP Consensus Board | When hive patterns indicate Policy Envelope parameters need adjustment (S&OP level) |

### 10.6 Hive Feedback to AAP Learning

The Hive's signal patterns provide rich training data for AAP agent learning:

| Hive Data | AAP Learning Signal |
|---|---|
| Signal frequency distribution | Predicts which authorization surfaces will activate (proactive resolution) |
| Signal cascade patterns | Identifies common multi-party authorization chains (coalition prediction) |
| Cross-TRM urgency correlation | Calibrates net benefit thresholds (urgent hives should have lower thresholds) |
| Hive health trajectory | Auto-adjusts agent autonomy (healthy hives get more autonomy, stressed hives get more oversight) |
| Decision-outcome pairs with signal context | Trains AAP agents on signal-to-action mappings (when ATP_SHORTAGE + QUALITY_REJECT co-occur, what authorization pattern works best?) |

---

## 11. Embedded Scenario Architecture (Kinaxis-Inspired)

### 11.1 Kinaxis Design Principles

Research into Kinaxis RapidResponse / Maestro reveals a fundamentally different approach to scenarios than Autonomy's current architecture:

| Kinaxis Approach | Autonomy Current State | Gap |
|---|---|---|
| Scenarios are embedded in every workflow | Scenarios are a separate "Simulation" nav item | Scenarios are siloed, not integrated into planning workflows |
| Any planner can create a what-if from any screen | Only Beer Game simulation supports scenario creation | No ad-hoc what-if from planning screens |
| Git-like branching: scenarios are data branches | Scenarios are separate simulation runs | No branching model for planning state |
| Instant propagation across the entire network | Changes isolated to single scenario run | No cross-function propagation |
| Side-by-side comparison against live plan | Compare scenarios post-hoc via reports | No in-context comparison |
| Collaborative resolution: share, compare, approve | Single-user scenario experience | No collaborative scenario workflow |
| Purpose-built hybrid DB (relational + graph + network) | Standard PostgreSQL | No specialized scenario storage engine |

**Key Kinaxis technical insights**:
- **In-memory database with efficient versioning engine** — scenarios are branches, creating one is instant because only the delta from the live state is stored
- **Foreign key traversal is virtually free** — the hybrid data model (relational + network + graph) optimizes the supply chain graph traversal needed for propagation
- **Single data model for all planning functions** — demand, supply, inventory, capacity, S&OP all share one model, so a scenario change in demand instantly propagates to supply, inventory, etc.
- **Private sandboxes** — planners can work in isolated scenarios without affecting the live plan or other users
- **Historical scenario pinning** — any point-in-time state can be frozen as a reference scenario

### 11.2 Scenario Architecture for Autonomy

Adapting the Kinaxis model to Autonomy's agent-centric architecture:

```
                         LIVE STATE (production plan)
                              │
               ┌──────────────┼──────────────┐
               │              │              │
          ┌────▼────┐    ┌───▼────┐    ┌────▼────┐
          │Scenario │    │Scenario│    │Scenario │
          │   A     │    │   B    │    │   C     │
          │(Agent)  │    │(Agent) │    │(Agent)  │
          └────┬────┘    └───┬────┘    └─────────┘
               │             │
          ┌────┼────┐   ┌────┼────┐
          │         │   │         │
     ┌────▼──┐ ┌───▼──┐ ┌──▼───┐ ┌──▼───┐
     │  A.1  │ │  A.2 │ │ B.1  │ │ B.2  │
     │Δ+more │ │Δ+alt │ │Δ+adj │ │Δ+adj │
     └───────┘ └──────┘ └──────┘ └──┬───┘
                                    │
                               ┌────┼────┐
                               │         │
                          ┌────▼──┐ ┌───▼───┐
                          │ B.2.1 │ │ B.2.2 │
                          │Δ+fine │ │Δ+fine │
                          └───────┘ └───────┘

     Each node stores ONLY its delta from its parent.
     Effective state = chain of deltas: LIVE → B → B.2 → B.2.1

     When B.2.1 is PROMOTED:
       1. B.2.1 deltas merge into B.2  (B.2.2 PRUNED)
       2. B.2 deltas merge into B      (B.1 PRUNED)
       3. B deltas merge into LIVE      (A, C and all children PRUNED)
       4. Decision record captures WHY B.2.1 won at each level
```

**Core data structure**:

```python
@dataclass
class PlanningScenario:
    """A branched planning state for what-if evaluation.

    Scenarios form a tree rooted at LIVE. Each scenario stores only its
    delta from its parent — the effective state at any node is computed by
    walking the chain of deltas from LIVE down to that node (like Git commits).
    """
    scenario_id: str                   # UUID
    parent_scenario_id: Optional[str]  # None = branched from LIVE
    root_scenario_id: Optional[str]    # The top-level branch (for tree traversal)
    name: str
    created_by: str                    # agent_type or user_id
    created_at: datetime
    depth: int                         # 0 = branched from LIVE, 1 = child of branch, etc.

    # Lifecycle
    status: str                        # DRAFT, EVALUATING, SHARED, APPROVED,
                                       # PROMOTED, PRUNED, ARCHIVED

    # What changed (delta from parent ONLY — not cumulative)
    variable_deltas: Dict[str, Any]    # {"safety_stock.SKU-A.DC-East": 150, ...}
    scope: str                         # SITE, MULTI_SITE, NETWORK

    # Evaluation results (populated by what-if engine)
    balanced_scorecard: Optional[Dict]
    net_benefit_vs_live: Optional[float]   # Cumulative benefit vs LIVE (not just parent)
    net_benefit_vs_parent: Optional[float] # Benefit vs immediate parent
    kpi_impact: Optional[Dict]         # {"otif": +2.1%, "cost": -$3.4K, ...}

    # Collaboration
    shared_with: List[str]             # agent_types or user_ids
    comments: List[Dict]               # Thread of discussion
    authorization_thread_id: Optional[int]  # Link to AAP thread if cross-authority

    # Tree navigation (populated by ScenarioTreeService)
    child_scenario_ids: List[str]      # Direct children of this scenario
    sibling_scenario_ids: List[str]    # Other scenarios sharing same parent

    # Promotion / Pruning (populated on lifecycle transitions)
    promoted_at: Optional[datetime]    # When this scenario was promoted
    promoted_by: Optional[str]         # Agent or user that promoted
    pruned_at: Optional[datetime]      # When this scenario was pruned
    pruned_reason: Optional[str]       # Why pruned (sibling promoted, expired, etc.)
    superseded_by: Optional[str]       # scenario_id of the winning sibling

    # Knowledge capture (populated on promotion — the critical learning artifact)
    decision_record: Optional['ScenarioDecisionRecord']


@dataclass
class ScenarioDecisionRecord:
    """Captures WHY a scenario was chosen over alternatives.

    This is the knowledge artifact that feeds back into agent learning.
    It records not just what was decided, but the comparative reasoning
    that led to the choice — the agent's evolving judgment.
    """
    decision_id: str                   # UUID
    timestamp: datetime
    decided_by: str                    # agent_type or user_id

    # The choice
    promoted_scenario_id: str          # Which scenario won
    pruned_scenario_ids: List[str]     # Which scenarios were rejected

    # Comparative analysis (why this one?)
    scenario_scorecards: Dict[str, Dict]  # {scenario_id: balanced_scorecard}
    scenario_net_benefits: Dict[str, float]  # {scenario_id: net_benefit}
    ranking_rationale: str             # Natural language explanation of choice

    # Negotiation context
    authorization_thread_ids: List[int]  # AAP threads involved
    negotiation_rounds: int            # How many counter-offers before consensus
    counter_scenarios_considered: int  # Total branches explored

    # Hive context at decision time
    urgency_vector_snapshot: List[float]  # UrgencyVector[11] at decision time
    active_signals_summary: Dict[str, int]  # Signal type counts
    hive_health_snapshot: Dict[str, float]  # Key health metrics

    # Learning signals
    confidence: float                  # Agent confidence in this choice [0,1]
    decision_difficulty: str           # ROUTINE, MODERATE, COMPLEX, NOVEL
    is_expert_decision: bool           # True if human decided (higher training weight)
    expected_outcome: Dict[str, float] # Predicted KPI values post-promotion
    actual_outcome: Optional[Dict]     # Filled by OutcomeCollector after feedback horizon
    outcome_delta: Optional[Dict]      # expected - actual (calibration signal)
```

### 11.3 Scenarios Embedded in Every Agent Workflow

**The critical Kinaxis lesson**: Scenarios should not be a separate navigation item. Every agent's decision workflow should naturally support scenario creation and evaluation.

```
CURRENT AGENT WORKFLOW:
  Agent detects condition → Evaluates options → Executes best option

EMBEDDED SCENARIO WORKFLOW:
  Agent detects condition → Creates scenario branch → Modifies variables
  → What-if engine evaluates → Balanced Scorecard comparison
  → If within authority: promote scenario to LIVE
  → If cross-authority: attach scenario to AuthorizationRequest
  → If uncertain: share scenario for collaborative review
```

**How each TRM caste uses scenarios**:

| Caste | Scenario Trigger | Variables Changed | Evaluation |
|---|---|---|---|
| **Scouts** | Demand surge detected | Order promises, allocation priorities | "What if we prioritize strategic customers and partial-fill standard?" |
| **Foragers** | Supply shortage | PO quantities, supplier selection, rebalancing targets | "What if we expedite from Supplier B instead of waiting for Supplier A?" |
| **Nurses** | Forecast deviation | Safety stock levels, forecast adjustments | "What if we increase SS by 20% for the next 2 weeks?" |
| **Guards** | Quality reject | Disposition (scrap vs rework), maintenance timing | "What if we rework instead of scrap? Cost vs. time impact?" |
| **Builders** | Capacity constraint | Production sequence, transfer routing | "What if we split MO-456 across two lines?" |

### 11.4 Scenario Propagation via Hive Signal Bus

When an agent creates a scenario and modifies variables, the what-if engine propagates the changes through the Hive:

```
SafetyStockTRM creates scenario: "Increase SS for SKU-A from 100 to 150"
     │
     ▼
WHAT-IF ENGINE propagates through hive:
     │
     ├── POCreationTRM: higher SS target → earlier reorder point
     │   Impact: PO timing moves forward 2 days, $1,200 additional holding cost
     │
     ├── ATPExecutorTRM: more reserved stock → fewer units available for orders
     │   Impact: 3 standard orders may be partially filled
     │
     ├── RebalancingTRM: higher inventory target → reduced transfer-out eligibility
     │   Impact: Site B's lateral surplus from this site decreases
     │
     └── MOExecutionTRM: higher target → may trigger additional production run
         Impact: Line utilization increases from 78% to 85%

BALANCED SCORECARD:
  Financial: AMBER ($1,200 holding cost + $800 production)
  Customer: GREEN (fill rate +2.1%, OTIF +1.8%)
  Operational: GREEN (fewer stockouts projected)
  Strategic: GREEN (reduced revenue at risk)

NET BENEFIT: +$8,400
```

This is the Kinaxis "instant propagation" principle applied to the Hive architecture — changes cascade through the signal bus and each TRM evaluates its impact.

---

## 12. Scenario-Based Agent Negotiation Protocol

### 12.1 Design Principle

**"Any agent should be able to change any variable to which they have access in a new scenario in order to evaluate a change, and then communicate with the agent in charge of that variable to reach agreement and consensus."**

This combines three capabilities:
1. **Embedded scenarios** (Section 11) — agents create scenarios as part of their normal workflow
2. **Balanced Scorecard evaluation** — the what-if engine shows full cross-functional impact
3. **AAP authorization** (Section 10) — structured negotiation when changes cross authority boundaries

### 12.2 Protocol Flow

```
Phase 1: DETECT (Hive Signal Bus)
     │
     │  Agent detects a condition via HiveSignal or tGNN InterHiveSignal
     │  that could be improved by changing a variable outside its authority
     │
     ▼
Phase 2: BRANCH (Scenario Creation)
     │
     │  Agent creates a PlanningScenario (branch from LIVE state)
     │  Modifies variables within its own authority first
     │  Identifies variables outside its authority that would improve outcome
     │  Creates the "proposed" state including cross-authority changes
     │
     ▼
Phase 3: EVALUATE (What-If Engine)
     │
     │  What-if engine runs scenario through the Hive model:
     │  - Propagates changes through all TRM impact assessments
     │  - Computes Balanced Scorecard (Financial, Customer, Operational, Strategic)
     │  - Computes net benefit vs. LIVE state
     │  - Identifies which authority boundaries are crossed
     │
     ▼
Phase 4: NEGOTIATE (AAP + Scenario Evidence)
     │
     │  AuthorizationRequest includes:
     │  - proposed_scenario_id (the full branched state)
     │  - balanced_scorecard (complete impact assessment)
     │  - variables_requiring_authorization (specific changes + owning agent)
     │  - net_benefit (weighted across all quadrants)
     │  - fallback_scenario_id (best option within unilateral authority)
     │
     │  Target agent can:
     │  ├── AUTHORIZE: Accept scenario as-is
     │  ├── COUNTER_SCENARIO: Create their own branch with modifications
     │  │   (e.g., "I'll accept the SS increase but at 130, not 150")
     │  │   → Both scorecards shown side-by-side
     │  ├── DENY: Reject with reasoning
     │  └── ESCALATE: Route to human with both scenarios + scorecards
     │
     ▼
Phase 5: CONSENSUS (Scenario Promotion)
     │
     │  When agreement is reached:
     │  - Winning scenario promoted from DRAFT → APPROVED → PROMOTED
     │  - Variable changes applied to LIVE state
     │  - HiveSignalBus emits appropriate signals
     │  - Decision recorded with scenario context for RL training
     │
     │  When escalated to human:
     │  - Human sees: Live state, Agent A's scenario, Agent B's counter-scenario
     │  - All three with full Balanced Scorecards side-by-side
     │  - Human selects or creates hybrid → feeds back to agent learning
```

### 12.3 Scenario Negotiation Example: Safety Stock Dispute

```
SITUATION: Site A's fill rate is declining. SafetyStockTRM wants to increase
SS, but the increase would consume working capital that Finance Agent manages.

Step 1: DETECT
  SafetyStockTRM reads HiveSignals:
    - 5× ATP_SHORTAGE in last 24h (urgency_vector[0] = 0.8)
    - fill_rate_7d: 0.89 (below 0.92 target)
    - backlog_trend_7d: +15% (increasing)

Step 2: BRANCH
  SafetyStockTRM creates PlanningScenario "SS-2026-0223-001":
    parent: LIVE
    variable_deltas: {
      "safety_stock.SKU-A.DC-East": 100 → 150 (+50%),
      "safety_stock.SKU-B.DC-East": 200 → 260 (+30%),
    }

Step 3: EVALUATE
  What-if engine propagates:
    Financial: working_capital += $45K (AMBER)
    Customer: otif_strategic = 97.2% → 98.8% (GREEN)
    Operational: fill_rate = 89% → 94% (GREEN)
    Strategic: revenue_at_risk -= $120K (GREEN)
    NET BENEFIT: +$75K

  Authority check:
    SafetyStockTRM authority: adjust SS within ±20% of policy → 50% exceeds
    Requires authorization: Finance Agent (working capital impact > $25K threshold)

Step 4: NEGOTIATE
  SafetyStockTRM → Finance Agent (via AuthorizationRequest):
    "Scenario SS-2026-0223-001: Increase SS for 2 SKUs at DC-East.
     Working capital impact: +$45K. Net benefit: +$75K.
     Revenue at risk reduced by $120K."

  Finance Agent evaluates:
    Working capital budget: $1.8M, utilized: $1.72M
    $45K increase → $1.765M (98% of budget) → AMBER but within cap
    No competing capital requests this week

  Finance Agent: COUNTER_SCENARIO "SS-2026-0223-002":
    "Authorize $30K (SKU-A to 140, SKU-B to 240). Phase remaining
     $15K based on next week's fill rate data."
    variable_deltas: {
      "safety_stock.SKU-A.DC-East": 100 → 140 (+40%),
      "safety_stock.SKU-B.DC-East": 200 → 240 (+20%),
    }
    NET BENEFIT: +$62K (slightly lower, but budget stays at 97%)

  SafetyStockTRM evaluates counter-scenario:
    fill_rate improves to 92.5% (meets target)
    NET BENEFIT still positive (+$62K)
    → ACCEPT_COUNTER

Step 5: CONSENSUS
  Scenario "SS-2026-0223-002" promoted to LIVE
  SafetyStockTRM emits: SS_INCREASED (SKU-A: +40%, SKU-B: +20%)
  POCreationTRM reads signal → adjusts reorder quantities
  Decision recorded with scenario chain for RL training
```

### 12.4 Multi-Agent Scenario Cascade

Complex situations may require cascading scenarios across multiple agents:

```
TRIGGER: Customer mega-order arrives (3x normal volume)

ATPExecutorTRM (Scout):
  └── Creates scenario "ATP-MEGA-001":
      Cannot fill from current allocations
      Variable: "allocation.P1.SKU-X.DC-East": request +200%
      Requires: Allocation Agent authorization

      Allocation Agent evaluates:
      └── Creates counter-scenario "ALLOC-MEGA-001":
          Can shift 60% from P3/P4 tiers
          Variable: "allocation.P3.SKU-X": -40%, "allocation.P4.SKU-X": -60%
          BUT: Remaining 40% requires additional supply
          Requires: Supply Agent authorization

          Supply Agent evaluates:
          └── Creates scenario "SUPPLY-MEGA-001":
              Option A: Expedite from approved supplier ($5K premium)
              Option B: Spot buy from secondary supplier ($8K premium)
              Option C: Rebalance from Site B (transfer cost $3K)

              Runs what-if on all three against Balanced Scorecard
              Best: Option C (net benefit +$45K, all GREEN except Financial AMBER)
              Requires: Site B's Inventory Agent authorization

              Site B's Inventory Agent (inter-hive negotiation):
              └── Evaluates: "Do I have surplus?"
                  urgency_vector[5] (safety_stock) = 0.2 (low urgency)
                  backlog_trend = stable
                  → AUTHORIZE transfer of 500 units
                  → REBALANCE_OUTBOUND signal emitted at Site B

RESOLUTION: Cascade of scenarios resolve bottom-up:
  Site B authorizes → Supply Agent selects Option C
  → Allocation Agent promotes ALLOC-MEGA-001 with supply secured
  → ATPExecutorTRM promotes ATP-MEGA-001 with allocation secured
  → Customer order fulfilled, all authorization threads closed
  → Full scenario chain recorded for training
```

### 12.5 Human-in-the-Loop Scenario Review

When agents can't reach consensus, humans see pre-digested scenario comparisons:

```
ESCALATION: Scenario Disagreement
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Thread: AT-2026-0223-001
From: SafetyStockTRM (Inventory Agent)
To: Finance Agent
Status: COUNTER_REJECTED → ESCALATED

LIVE STATE                    SCENARIO A (Inventory)        SCENARIO B (Finance)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SS SKU-A: 100                 SS SKU-A: 150 (+50%)          SS SKU-A: 120 (+20%)
SS SKU-B: 200                 SS SKU-B: 260 (+30%)          SS SKU-B: 220 (+10%)

FINANCIAL                     FINANCIAL                     FINANCIAL
Working Capital: $1.72M       Working Capital: $1.77M       Working Capital: $1.74M
Budget Util: 96%              Budget Util: 98% ●AMBER       Budget Util: 97%
                              +$45K investment              +$18K investment

CUSTOMER                      CUSTOMER                      CUSTOMER
OTIF: 93% ●RED               OTIF: 98.8% ●GREEN           OTIF: 95.5% ●GREEN
Fill Rate: 89% ●RED          Fill Rate: 94% ●GREEN         Fill Rate: 91% ●AMBER

NET BENEFIT vs LIVE:          +$75K                         +$35K

RECOMMENDATION: Scenario A (higher net benefit, resolves RED flags)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Accept A]  [Accept B]  [Create Hybrid]  [Reject Both]
```

### 12.6 Scenario Architecture and Kinaxis Parity

| Kinaxis Capability | Autonomy Implementation | Status |
|---|---|---|
| **Git-like branching** | `PlanningScenario` with `parent_scenario_id` + `variable_deltas` | Proposed |
| **Instant propagation** | What-if engine propagates through HiveSignalBus simulation | Proposed |
| **Side-by-side comparison** | Balanced Scorecard comparison (up to 3 scenarios) | Extends existing `run_what_if()` |
| **Private sandbox** | `PlanningScenario.status = DRAFT` (visible only to creator) | Proposed |
| **Collaborative review** | `PlanningScenario.shared_with` + AAP AuthorizationThread | Extends existing AAP |
| **Promote to LIVE** | `PlanningScenario.status = PROMOTED` → apply deltas | Proposed |
| **Historical pinning** | `PlanningScenario.status = ARCHIVED` with snapshot | Proposed |
| **Embedded in every workflow** | Every TRM can create/evaluate scenarios as part of decision cycle | Proposed |
| **Unlimited concurrent scenarios** | Bounded by agent decision cadence + authorization SLA | Proposed |

**Critical differentiator from Kinaxis**: In Kinaxis, humans create and evaluate scenarios. In Autonomy, **agents create and evaluate scenarios at machine speed**, escalating to humans only for unresolvable contention. This is the AAP's core value proposition applied to scenario management — the Kinaxis workflow at machine speed.

### 12.7 Scenario Lifecycle: Promotion, Pruning, and Knowledge Capture

This section defines the algorithms that govern how scenario trees evolve — from creation through evaluation, promotion to LIVE, sibling/descendant pruning, and knowledge capture for agent learning.

#### 12.7.1 Lifecycle State Machine

```
                        ┌─────────────────────────────────────────┐
                        │                                         │
                        ▼                                         │
  CREATE ──► DRAFT ──► EVALUATING ──► SHARED ──► APPROVED ──► PROMOTED
                │              │          │          │              │
                │              │          │          │              ▼
                │              │          │          │         (merge deltas
                │              │          │          │          into parent,
                │              │          │          │          prune siblings)
                │              │          │          │
                ▼              ▼          ▼          ▼
             EXPIRED       WITHDRAWN   DENIED     PRUNED
                │              │          │          │
                └──────────────┴──────────┴──────────┘
                                     │
                                     ▼
                                  ARCHIVED
                           (retained for learning)
```

**State transitions**:

| From | To | Trigger | Effect |
|---|---|---|---|
| — | DRAFT | Agent or human creates branch | `variable_deltas` populated, `depth` set, parent linked |
| DRAFT | EVALUATING | What-if engine invoked | Balanced Scorecard + net_benefit computed |
| EVALUATING | SHARED | Creator shares for review | `shared_with` populated, visible to reviewers |
| SHARED | APPROVED | Authority holder accepts | Ready for promotion |
| APPROVED | PROMOTED | `ScenarioTreeService.promote()` | Deltas merged into parent, siblings pruned, decision record created |
| Any active | PRUNED | Sibling promoted at same level | `superseded_by` set, `pruned_reason` recorded |
| Any active | EXPIRED | Authorization SLA exceeded | Auto-cleaned by scheduled job |
| Any active | WITHDRAWN | Creator cancels | Creator chose not to proceed |
| Any active | DENIED | Authority holder rejects | Rejection reason captured |
| Any terminal | ARCHIVED | Retention policy | Moved to cold storage, available for learning |

#### 12.7.2 ScenarioTreeService

```python
class ScenarioTreeService:
    """Manages the scenario tree lifecycle: creation, navigation,
    promotion, pruning, and knowledge capture.

    The tree is rooted at the LIVE state (an implicit root with no
    scenario_id). All depth-0 scenarios are branches from LIVE.
    """

    def create_branch(
        self,
        parent_scenario_id: Optional[str],  # None = branch from LIVE
        created_by: str,
        name: str,
        variable_deltas: Dict[str, Any],
        scope: str = "SITE",
    ) -> PlanningScenario:
        """Create a new scenario as a child of the given parent.

        If parent_scenario_id is None, creates a depth-0 branch from LIVE.
        Otherwise, creates a child at parent.depth + 1.

        Sets root_scenario_id to the top-level ancestor for fast
        tree traversal. Updates parent's child_scenario_ids.
        """
        ...

    def get_effective_state(
        self, scenario_id: str
    ) -> Dict[str, Any]:
        """Compute the effective state at a scenario node.

        Walks the delta chain from LIVE down to this node,
        applying each ancestor's variable_deltas in order:

            effective = LIVE_state.copy()
            for ancestor in [root, ..., parent, self]:
                effective.update(ancestor.variable_deltas)

        This is the Git-like 'checkout' — reconstructing full
        state from the chain of commits.
        """
        ...

    def get_ancestry(
        self, scenario_id: str
    ) -> List[PlanningScenario]:
        """Return the ordered list [root, ..., parent, self]
        from LIVE down to this scenario. Used by get_effective_state
        and by the promotion algorithm.
        """
        ...

    def get_subtree(
        self, scenario_id: str
    ) -> List[PlanningScenario]:
        """Return all descendants of a scenario (BFS/DFS).
        Used by prune_subtree to find everything to archive.
        """
        ...

    def promote(
        self,
        scenario_id: str,
        decided_by: str,
        ranking_rationale: str,
    ) -> ScenarioDecisionRecord:
        """Promote a scenario by merging its deltas into its parent,
        pruning all siblings and their subtrees, then recursing upward
        until LIVE is reached.

        This is the core lifecycle operation. It implements the user's
        requirement: "the scenario containing the change selected needs
        to be promoted to the parent. All the children scenarios then
        need to be pruned."

        Algorithm (recursive, leaf-to-root):

        1. VALIDATE: scenario.status must be APPROVED
        2. CAPTURE: Create ScenarioDecisionRecord at this level
           - Record scorecards for this scenario + all siblings
           - Record ranking_rationale explaining why this one won
           - Snapshot urgency_vector, active_signals, hive_health
        3. MERGE: Apply scenario.variable_deltas into parent
           - If parent is a PlanningScenario: parent.variable_deltas.update(scenario.variable_deltas)
           - If parent is LIVE: apply deltas to the production state
        4. PRUNE SIBLINGS: For each sibling of this scenario:
           - Set sibling.status = PRUNED
           - Set sibling.superseded_by = scenario.scenario_id
           - Set sibling.pruned_reason = "Sibling {scenario.name} promoted"
           - prune_subtree(sibling) — recursively prune all descendants
        5. MARK PROMOTED: Set scenario.status = PROMOTED, promoted_at, promoted_by
        6. RECURSE: If parent is a PlanningScenario (not LIVE):
           - Set parent.status = APPROVED (auto-approve with merged deltas)
           - promote(parent.scenario_id, decided_by, rationale)
           → This continues until we reach a depth-0 scenario whose
             parent is LIVE, at which point deltas are applied to
             production state.
        7. EMIT SIGNALS: Emit HiveSignals for the changes applied to LIVE

        Returns the root-level ScenarioDecisionRecord (which links
        to child decision records at each level).
        """
        ...

    def prune_subtree(
        self, scenario_id: str, reason: str
    ) -> int:
        """Recursively prune a scenario and all its descendants.

        For each node in the subtree (BFS):
          - Set status = PRUNED
          - Set pruned_at = now
          - Set pruned_reason = reason
          - If the node had an active AuthorizationThread, close it

        Returns the count of scenarios pruned.
        Pruned scenarios are retained in ARCHIVED state for learning —
        they represent paths-not-taken, which are valuable negative
        examples for training.
        """
        ...

    def merge_deltas_to_parent(
        self,
        child: PlanningScenario,
        parent: PlanningScenario
    ) -> None:
        """Merge child's variable_deltas into parent's variable_deltas.

        Simple dict update — child values override parent values
        for the same keys. For nested structures (e.g., allocation
        matrices), deep merge with child priority.

        After merge, the parent's effective state includes everything
        the child changed, plus the parent's own prior changes.
        """
        ...

    def apply_to_live(
        self, scenario: PlanningScenario
    ) -> None:
        """Apply a depth-0 scenario's accumulated deltas to LIVE state.

        This is the final step of promotion — the scenario's changes
        become the new production state. Dispatches each delta to the
        appropriate engine/service:

          "safety_stock.*"    → SafetyStockTRM.apply_override()
          "allocation.*"      → AllocationService.update()
          "forecast.*"        → ForecastAdjustmentTRM.apply()
          "po.*"              → POCreationTRM.apply()
          "production.*"      → MOExecutionTRM.apply()
          etc.
        """
        ...
```

#### 12.7.3 Promotion Algorithm — Detailed Walk-through

The promotion algorithm is **recursive and bottom-up**: it starts at the accepted leaf scenario and merges upward through every ancestor until reaching LIVE. At each level, the winning scenario's siblings (and their entire subtrees) are pruned.

```
BEFORE PROMOTION — Tree state:

    LIVE STATE
      ├── A  (depth 0, EVALUATING)
      │   ├── A.1  (depth 1, DRAFT)
      │   └── A.2  (depth 1, EVALUATING)
      │
      ├── B  (depth 0, EVALUATING)
      │   ├── B.1  (depth 1, SHARED)
      │   └── B.2  (depth 1, EVALUATING)
      │       ├── B.2.1  (depth 2, APPROVED)  ← THIS GETS PROMOTED
      │       └── B.2.2  (depth 2, EVALUATING)
      │
      └── C  (depth 0, DRAFT)


STEP 1 — promote(B.2.1):
    Level: depth 2 → merge into depth 1 parent (B.2)

    Decision Record DR-1 created:
      promoted: B.2.1
      pruned:   [B.2.2]
      rationale: "B.2.1 reduces cost by $12K vs B.2.2's $8K,
                  both achieve fill rate target"
      scorecards: {B.2.1: {...}, B.2.2: {...}}

    Actions:
      B.2.variable_deltas.update(B.2.1.variable_deltas)
      B.2.2.status = PRUNED, superseded_by = B.2.1
      B.2.1.status = PROMOTED
      B.2.status = APPROVED (auto, ready for next level)


STEP 2 — promote(B.2) (auto-triggered by Step 1):
    Level: depth 1 → merge into depth 0 parent (B)

    Decision Record DR-2 created:
      promoted: B.2  (now carrying merged B + B.2 + B.2.1 deltas)
      pruned:   [B.1]
      rationale: "B.2 (with B.2.1 refinement) achieves 94% fill rate
                  vs B.1's 91%. Cost impact comparable."
      scorecards: {B.2: {...}, B.1: {...}}

    Actions:
      B.variable_deltas.update(B.2.variable_deltas)
      B.1.status = PRUNED, superseded_by = B.2
      B.2.status = PROMOTED
      B.status = APPROVED


STEP 3 — promote(B) (auto-triggered by Step 2):
    Level: depth 0 → merge into LIVE

    Decision Record DR-3 created:
      promoted: B  (now carrying merged B + B.2 + B.2.1 deltas)
      pruned:   [A, C]  (and all their subtrees: A.1, A.2)
      rationale: "B addresses the critical ATP shortage with combined
                  SS increase + supplier diversification. A focused only
                  on SS. C was still in draft."
      scorecards: {B: {...}, A: {...}, C: {...}}

    Actions:
      apply_to_live(B)  → deltas applied to production state
      A.status = PRUNED, superseded_by = B
        A.1.status = PRUNED (subtree)
        A.2.status = PRUNED (subtree)
      C.status = PRUNED, superseded_by = B
      B.status = PROMOTED

      HiveSignalBus.emit(signals from applied deltas)


AFTER PROMOTION — Tree state:

    LIVE STATE  ← now includes B + B.2 + B.2.1 deltas
      ├── A  (PRUNED, superseded_by=B)
      │   ├── A.1  (PRUNED)
      │   └── A.2  (PRUNED)
      │
      ├── B  (PROMOTED)
      │   ├── B.1  (PRUNED, superseded_by=B.2)
      │   └── B.2  (PROMOTED)
      │       ├── B.2.1  (PROMOTED)
      │       └── B.2.2  (PRUNED, superseded_by=B.2.1)
      │
      └── C  (PRUNED, superseded_by=B)

    Decision Records: DR-1 → DR-2 → DR-3 (linked chain)
    All pruned scenarios retained in ARCHIVED state for learning
```

#### 12.7.4 Knowledge Capture and Agent Learning

The ScenarioDecisionRecord is the critical artifact that closes the learning loop. It captures not just what was decided, but **why** — and feeds that judgment back into agent training.

**Knowledge capture flow**:

```
promote(scenario)
    │
    ├── 1. ScenarioDecisionRecord created at each level
    │      Records: winning scenario, pruned scenarios, all scorecards,
    │      ranking rationale, negotiation context, hive state snapshot
    │
    ├── 2. Decision records stored in powell_scenario_decisions table
    │      (extends powell_site_agent_decisions with scenario context)
    │
    ├── 3. OutcomeCollector observes actual results after feedback horizon
    │      Fills actual_outcome and outcome_delta fields:
    │        - Did fill rate actually improve as predicted?
    │        - Was the cost impact accurate?
    │        - Did the chosen scenario outperform pruned alternatives?
    │
    ├── 4. Calibration signal: expected_outcome vs actual_outcome
    │      High delta → agent's scenario evaluation was poor
    │      Low delta  → agent's judgment is well-calibrated
    │
    └── 5. Feeds into TRM training via replay buffer
           Each decision record becomes a training example:
             State:  hive state + signal context at decision time
             Action: which scenario was promoted
             Reward: actual_outcome (from OutcomeCollector)

           Pruned scenarios provide counterfactual training data:
             "In state S, you chose scenario B over A.
              B yielded reward R. Here's what A's scorecard predicted."

           Expert decisions (is_expert_decision=True from human
           escalation) receive higher training weight — this is
           the judgment capture loop that builds the competitive moat.
```

**What agents learn from scenario decision records**:

| Learning Signal | Source | What the Agent Learns |
|---|---|---|
| **Scenario selection accuracy** | outcome_delta | "Am I picking the right scenarios? My fill rate predictions are consistently 3% too optimistic." |
| **Negotiation efficiency** | negotiation_rounds, counter_scenarios | "Counter-offers at ±10% converge faster than ±30%. Start closer to the middle." |
| **Authority boundary intuition** | authorization success/deny rates | "Working capital requests >$30K get denied 40% of the time. Pre-split into phased increases." |
| **Scorecard weighting** | which quadrant drove the winning choice | "At this site, Customer metrics outweigh Financial when urgency > 0.7." |
| **Pruned-scenario value** | pruned scenario scorecards vs actual | "Scenarios I rejected actually had better outcomes 15% of the time — my evaluation is biased toward cost reduction." |
| **Human override patterns** | is_expert_decision records | "Humans consistently override my SS decisions when backlog_trend > +20%. Adjust threshold." |

#### 12.7.5 Partial Promotion (Selective Delta Merge)

Not all promotions are all-or-nothing. An agent or human may want to promote **some** of a scenario's deltas while rejecting others:

```python
def promote_partial(
    self,
    scenario_id: str,
    accepted_delta_keys: List[str],
    decided_by: str,
    ranking_rationale: str,
) -> ScenarioDecisionRecord:
    """Promote selected deltas from a scenario, creating a filtered
    version that contains only the accepted changes.

    Use case: Human reviews scenario with 5 variable changes,
    accepts 3, rejects 2. The accepted changes are promoted,
    rejected changes remain as a 'residual' child scenario
    that can be re-evaluated or abandoned.

    Algorithm:
    1. Split variable_deltas into accepted and rejected sets
    2. Create child scenario "residual" with rejected deltas
    3. Replace scenario's deltas with accepted-only
    4. Proceed with normal promote() on the filtered scenario
    """
    ...
```

This handles the common case where a counter-offer scenario has some good ideas and some that need more work — the good parts can be promoted immediately while the rest remain as a branch for further refinement.

#### 12.7.6 Concurrent Promotion Conflict Resolution

When two agents try to promote competing scenarios simultaneously:

```
Agent X promotes Scenario A (depth 0, modifies safety_stock.SKU-A)
Agent Y promotes Scenario B (depth 0, modifies safety_stock.SKU-A)
                                      ↑ CONFLICT: same variable

Resolution protocol:
  1. First-to-commit wins (optimistic locking on LIVE state)
  2. Loser's promotion fails with CONFLICT status
  3. Loser's scenario is automatically rebased:
     - Recompute effective state against new LIVE (which now includes winner's deltas)
     - Re-run what-if evaluation (scorecard may change)
     - If still net-positive: re-enter EVALUATING state for re-approval
     - If net-negative: auto-WITHDRAW with reason "obsoleted by {winner}"

  This mirrors Git's merge conflict resolution — rebase and re-evaluate.
```

### 12.8 End-to-End Example: Supplier Disruption → Resolution → Knowledge Capture

This walkthrough follows a complete lifecycle from detection through tree branching, negotiation, recursive promotion, pruning, and knowledge capture.

```
═══════════════════════════════════════════════════════════════════
CONTEXT
═══════════════════════════════════════════════════════════════════

Site: DC-East (Distribution Center)
Problem: Key supplier (Supplier Alpha) notifies of 2-week delay
         on SKU-X (high-velocity item, 500 units/week demand)
Current state: 3 weeks of SS on hand, but fill rate will drop
               to ~80% by week 3 without intervention

═══════════════════════════════════════════════════════════════════
PHASE 1: DETECT — Hive Signal Bus
═══════════════════════════════════════════════════════════════════

OrderTrackingTRM (Scout) detects:
  ASN update from Supplier Alpha: PO-8842 delayed 14 days
  Emits HiveSignal:
    type: INBOUND_DELAY
    urgency: 0.75
    direction: shortage
    payload: {po_id: "PO-8842", sku: "SKU-X", delay_days: 14, qty: 1000}

UrgencyVector updates: [0.75, 0.3, 0.6, 0.1, 0.1, 0.4, 0.2, 0.1, 0.1, 0.3, 0.4]
                        ↑ATP  ↑OT  ↑PO       ...              ↑FcstAdj ↑SS

POCreationTRM (Forager) reads INBOUND_DELAY signal → raises own urgency
SafetyStockTRM (Nurse) reads INBOUND_DELAY signal → begins evaluation
ATPExecutorTRM (Scout) reads INBOUND_DELAY signal → flags at-risk orders

═══════════════════════════════════════════════════════════════════
PHASE 2: BRANCH — Three agents create scenarios from LIVE
═══════════════════════════════════════════════════════════════════

                         LIVE STATE
                              │
               ┌──────────────┼──────────────┐
               │              │              │
          ┌────▼────┐    ┌───▼────┐    ┌────▼────┐
          │  SC-A   │    │  SC-B  │    │  SC-C   │
          │(PO-TRM) │    │(SS-TRM)│    │(Rebal)  │
          │Expedite │    │+Buffer │    │Transfer │
          │SupplrB  │    │+30%SS  │    │from West│
          └─────────┘    └───┬────┘    └─────────┘
                             │
                        ┌────┼────┐
                        │         │
                   ┌────▼──┐ ┌───▼───┐
                   │ SC-B1 │ │ SC-B2 │
                   │+20%SS │ │+30%SS │
                   │+Exped │ │+Fcst↓ │
                   └───────┘ └───────┘

SC-A: POCreationTRM creates "Expedite-SupplierB"
  depth: 0, parent: LIVE
  variable_deltas: {
    "po.SKU-X.DC-East.supplier": "Supplier-Beta",
    "po.SKU-X.DC-East.qty": 800,
    "po.SKU-X.DC-East.expedite": true,
    "po.SKU-X.DC-East.premium": 4200,   // $4.2K expedite premium
  }

SC-B: SafetyStockTRM creates "Buffer-Increase"
  depth: 0, parent: LIVE
  variable_deltas: {
    "safety_stock.SKU-X.DC-East": 150 → 195 (+30%),
  }

SC-C: RebalancingTRM creates "Transfer-from-West"
  depth: 0, parent: LIVE
  variable_deltas: {
    "rebalance.SKU-X.DC-West→DC-East": 400,
    "rebalance.SKU-X.DC-East.transfer_cost": 1800,
  }

═══════════════════════════════════════════════════════════════════
PHASE 2b: BRANCH DEEPER — SafetyStockTRM explores sub-options
═══════════════════════════════════════════════════════════════════

SafetyStockTRM branches from SC-B to explore two refinements:

SC-B1: "Buffer + Expedite Combo" (child of SC-B)
  depth: 1, parent: SC-B
  variable_deltas: {
    "safety_stock.SKU-X.DC-East": 195 → 170 (-13%, less buffer than parent),
    "po.SKU-X.DC-East.supplier": "Supplier-Beta",
    "po.SKU-X.DC-East.qty": 400,
    "po.SKU-X.DC-East.expedite": true,
    "po.SKU-X.DC-East.premium": 2100,
  }
  // Note: SS delta relative to parent SC-B is -25 (195→170)
  // Effective vs LIVE: SS 150→170 (+13%) AND partial expedite

SC-B2: "Buffer + Demand Dampening" (child of SC-B)
  depth: 1, parent: SC-B
  variable_deltas: {
    "forecast_adj.SKU-X.DC-East.direction": "decrease",
    "forecast_adj.SKU-X.DC-East.magnitude": -15,  // dampen demand signal
    "forecast_adj.SKU-X.DC-East.duration_weeks": 3,
  }
  // SS stays at parent's +30%, but dampened forecast reduces pressure

═══════════════════════════════════════════════════════════════════
PHASE 3: EVALUATE — What-if engine scores all scenarios
═══════════════════════════════════════════════════════════════════

What-if engine evaluates each scenario's Balanced Scorecard:

                    │ Financial │ Customer │ Operational│ Strategic  │ Net Benefit
────────────────────┼───────────┼──────────┼────────────┼────────────┼───────────
LIVE (do nothing)   │  $0       │ OTIF 80% │ FR 80%     │ Risk: HIGH │ $0
                    │           │ ●RED     │ ●RED       │ ●RED       │
SC-A  Expedite      │ -$4.2K    │ OTIF 96% │ FR 95%     │ Risk: LOW  │ +$42K
                    │ ●AMBER    │ ●GREEN   │ ●GREEN     │ ●GREEN     │
SC-B  Buffer+30%    │ -$6.8K    │ OTIF 92% │ FR 91%     │ Risk: MED  │ +$28K
                    │ ●AMBER    │ ●GREEN   │ ●GREEN     │ ●AMBER     │
SC-C  Transfer      │ -$1.8K    │ OTIF 89% │ FR 88%     │ Risk: MED  │ +$22K
                    │ ●GREEN    │ ●AMBER   │ ●AMBER     │ ●AMBER     │
SC-B1 Buffer+Exped  │ -$5.9K    │ OTIF 95% │ FR 94%     │ Risk: LOW  │ +$39K
                    │ ●AMBER    │ ●GREEN   │ ●GREEN     │ ●GREEN     │
SC-B2 Buffer+Damp   │ -$6.8K    │ OTIF 88% │ FR 87%     │ Risk: MED  │ +$18K
                    │ ●AMBER    │ ●AMBER   │ ●AMBER     │ ●AMBER     │

═══════════════════════════════════════════════════════════════════
PHASE 4: NEGOTIATE — Cross-authority authorization
═══════════════════════════════════════════════════════════════════

SC-A requires Procurement Agent authorization (new supplier expedite)
SC-B1 requires Procurement Agent authorization (partial expedite)
  + Finance Agent authorization (working capital: $5.9K)
SC-C requires DC-West Inventory Agent authorization (surplus transfer)

POCreationTRM shares SC-A with Procurement Agent:
  Procurement evaluates → Supplier Beta concentration = 28% → within 30% cap
  → AUTHORIZE

SafetyStockTRM shares SC-B1 with Procurement + Finance Agents:
  Procurement: Partial expedite from Beta → AUTHORIZE
  Finance: $5.9K within budget → AUTHORIZE
  SC-B1 status → APPROVED

RebalancingTRM shares SC-C with DC-West Inventory Agent:
  DC-West evaluates: surplus exists but only 250 units (not 400)
  → COUNTER_SCENARIO SC-C': transfer 250 units instead
  SC-C' net benefit: +$15K (lower because partial transfer)
  RebalancingTRM: ACCEPT_COUNTER, SC-C updated to 250 units

═══════════════════════════════════════════════════════════════════
PHASE 5: CONSENSUS — SiteAgent selects and promotion begins
═══════════════════════════════════════════════════════════════════

SiteAgent (Queen) reviews approved scenarios:
  SC-A:  APPROVED, net benefit +$42K  (highest individual)
  SC-B1: APPROVED, net benefit +$39K  (close second, more balanced)
  SC-C': APPROVED, net benefit +$15K  (useful but insufficient alone)

SiteAgent selects SC-B1 (depth 1 child of SC-B):
  Rationale: "SC-B1 combines SS buffer increase (+13% ongoing
  resilience) with targeted partial expedite. SC-A is $3K better
  short-term but provides no ongoing resilience improvement.
  SC-B1 addresses both the immediate shortage AND the structural
  fragility that caused it."

═══════════════════════════════════════════════════════════════════
PHASE 6: RECURSIVE PROMOTION
═══════════════════════════════════════════════════════════════════

Step 1: promote(SC-B1) — depth 1 → depth 0

  ScenarioDecisionRecord DR-1:
    decided_by: "SiteAgent:DC-East"
    promoted: SC-B1
    pruned: [SC-B2]
    scorecards: {SC-B1: {net: +$39K, ...}, SC-B2: {net: +$18K, ...}}
    rationale: "SC-B1 outperforms SC-B2 on all four quadrants.
                Demand dampening in SC-B2 risks under-serving
                actual demand if the disruption resolves early."
    confidence: 0.82
    difficulty: MODERATE
    expected_outcome: {fill_rate_4w: 0.94, cost_delta: -5900}

  Actions:
    SC-B.variable_deltas.update(SC-B1.variable_deltas)
    SC-B2.status = PRUNED, superseded_by = SC-B1
    SC-B1.status = PROMOTED
    SC-B.status = APPROVED

Step 2: promote(SC-B) — depth 0 → LIVE (auto-triggered)

  ScenarioDecisionRecord DR-2:
    decided_by: "SiteAgent:DC-East"
    promoted: SC-B (now carrying merged SC-B + SC-B1 deltas)
    pruned: [SC-A, SC-C]
    scorecards: {
      SC-B: {net: +$39K},  // merged effective benefit
      SC-A: {net: +$42K},
      SC-C: {net: +$15K},
    }
    rationale: "SC-B (with SC-B1 refinement) selected over SC-A despite
                $3K lower net benefit. SC-B provides structural resilience
                (SS increase persists beyond disruption). SC-A is a
                one-time fix. Strategic quadrant favors SC-B."
    confidence: 0.78
    difficulty: COMPLEX
    expected_outcome: {fill_rate_4w: 0.94, cost_delta: -5900,
                       ss_improvement: +13%, supplier_diversification: true}

  Actions:
    apply_to_live(SC-B)  → production state updated:
      safety_stock.SKU-X.DC-East: 150 → 170
      PO created: Supplier Beta, 400 units, expedite
    SC-A.status = PRUNED, superseded_by = SC-B
    SC-C.status = PRUNED, superseded_by = SC-B
    SC-B.status = PROMOTED

    HiveSignalBus emits:
      SS_INCREASED (SKU-X, +13%, source: scenario promotion)
      PO_EXPEDITE (SKU-X, 400 units, Supplier Beta, ETA 5 days)

═══════════════════════════════════════════════════════════════════
PHASE 7: KNOWLEDGE CAPTURE — Learning from the decision
═══════════════════════════════════════════════════════════════════

Decision records DR-1 and DR-2 are persisted to powell_scenario_decisions.

4 weeks later — OutcomeCollector fills actual outcomes:
  actual_outcome: {fill_rate_4w: 0.92, cost_delta: -6100}
  outcome_delta: {fill_rate_4w: -0.02, cost_delta: -200}
  // Fill rate was 2% lower than predicted (supplier was 1 day later)
  // Cost was $200 more than predicted (freight variance)

Learning signals extracted:
  1. Agent's scenario evaluation was well-calibrated (outcome_delta small)
  2. Agent correctly valued structural resilience over one-time fix
  3. The pruned SC-A (expedite-only) would have scored: actual fill_rate 0.95
     → SC-A would have been slightly better short-term, but SS increase
       from SC-B prevented a second shortage event in week 6
  4. Decision difficulty was correctly classified as COMPLEX

Replay buffer entry created with:
  state: {urgency_vector, signals, hive_health} at decision time
  action: promote SC-B1/SC-B over SC-A, SC-C
  reward: composite_reward(fill_rate=0.92, cost=-6100, ss_resilience=+0.13)
  counterfactual: SC-A outcome for contrastive learning

  Pruned scenarios (SC-A, SC-B2, SC-C) become negative/contrastive
  examples — "paths not taken" that enrich the training distribution.

═══════════════════════════════════════════════════════════════════
FINAL STATE — Tree archived for learning
═══════════════════════════════════════════════════════════════════

    LIVE STATE  ← SS: 170, PO to Supplier Beta in flight
      ├── SC-A  (PRUNED → ARCHIVED, superseded_by=SC-B)
      ├── SC-B  (PROMOTED → ARCHIVED)
      │   ├── SC-B1  (PROMOTED → ARCHIVED)
      │   └── SC-B2  (PRUNED → ARCHIVED, superseded_by=SC-B1)
      └── SC-C  (PRUNED → ARCHIVED, superseded_by=SC-B)

    Decision Chain: DR-1 (B1 beat B2) → DR-2 (B beat A and C)
    Outcome: Filled after 4-week feedback horizon
    Training: 1 positive + 3 contrastive examples generated
```

---

## 13. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| **Signal cascade loops** (ATP→PO→SS→ATP...) | Decay mechanism (half_life) prevents infinite loops. Cycle phases enforce ordering. Max 50 signals per cycle. |
| **State space explosion** (too many signals for TRM to learn from) | Urgency vector is fixed at 11 dims. Signal bus summary (not raw signals) fed to TRM. Pheromone decay keeps active signals bounded. |
| **Stale tGNN signals** (daily cadence too slow) | CDC monitor detects when local signals diverge from tGNN predictions. Triggers off-cadence tGNN refresh. |
| **Signal noise** | Confidence-gated emission: only signals with TRM confidence > 0.7 are emitted. Low-confidence signals are logged but not propagated. |
| **Training distribution shift** when signals added | Signal context recorded in decision log enables gradual curriculum introduction. Offline RL (CQL) prevents distribution shift from new feature dimensions. |
| **Scenario sprawl** (too many agent-created scenarios) | Scenarios auto-expire after authorization SLA. Max 10 active scenarios per site. Max depth 3 (no branches-of-branches-of-branches). Cleanup job archives resolved/expired scenarios. |
| **Promotion race conditions** | Optimistic locking on LIVE state. First-to-commit wins, loser auto-rebases and re-evaluates (Section 12.7.6). |
| **Deep tree merge conflicts** | Max tree depth of 3 limits merge complexity. Partial promotion (Section 12.7.5) handles cases where only some deltas should merge. |
| **Stale scenario evaluations** | Scenarios older than authorization SLA are auto-expired. Promotion requires re-evaluation if scorecard is >1h old. |
| **Scenario-AAP coupling complexity** | Scenario creation is optional — TRMs can still operate without scenarios using direct signal-based decisions. Scenarios add deliberation, not replace reflexive action. |
| **Authorization latency for time-critical decisions** | Time-critical decisions (ATP, order tracking) use unilateral authority first. Scenarios are for proactive/planned changes, not reactive responses. |

---

## 14. Neural Architecture for the Hive: Research-Informed Recommendations

**Context**: The current `SiteAgentModel` uses a `SharedStateEncoder` (2-layer transformer, 128-dim, 4 heads) feeding 3 independent per-task heads (ATP, Inventory, PO). Heads have no cross-communication. This section evaluates candidate architectures from current research to determine what best fits the hive's 11-TRM coordination requirements.

### 14.1 Candidate Architectures Evaluated

| Architecture | Source | Core Idea | Fit for Hive |
|---|---|---|---|
| **A. HydraNet (Shared Encoder + Independent Heads)** | M3ViT, HydraLoRA, current implementation | Single shared backbone, task-specific heads | **Current state** — baseline to improve from |
| **B. Sparse MoE with Per-Task Routing** | PEER (DeepMind), Switch Transformer | Router selects subset of experts per input; task-dependent gating | Medium — adds routing overhead, good for heterogeneous inputs |
| **C. Stigmergic MARL (S-MADRL)** | [arxiv:2510.03592](https://arxiv.org/abs/2510.03592), Phormica | Virtual pheromone traces for indirect coordination; no explicit messaging | **High** — maps directly to UrgencyVector + HiveSignalBus |
| **D. Heterogeneous Graph Attention (HetNet)** | [arxiv:2108.09568](https://arxiv.org/abs/2108.09568), MAGAT | Graph attention over heterogeneous agent types; learned communication | **High** — models 11 different TRM types as heterogeneous nodes |
| **E. CTDE with MAPPO/QMIX** | [MAPPO](https://arxiv.org/abs/2103.01955), [QMIX](https://arxiv.org/abs/1803.11485) | Centralized training, decentralized execution; value factorization | Medium — good for training, less relevant to inference architecture |
| **F. Knocking-Heads Attention** | [arxiv:2510.23052](https://arxiv.org/abs/2510.23052) | Cross-head projections for inter-head coordination; zero inference overhead | **High** — enables head coordination with no latency cost |
| **G. Recursive Multi-Head (Samsung TRM-style)** | [arxiv:2510.04871](https://arxiv.org/abs/2510.04871), TRM_RESEARCH_SYNTHESIS.md | Single network applied recursively; scratchpad z + answer y | High — recursion already validated for our TRM heads |

### 14.2 Recommended Architecture: Hybrid Stigmergic-Graph-Recursive

The hive's 11 TRMs are **heterogeneous agents with different input/output shapes, operating frequencies, and functional specializations** — yet they share physical state context and must coordinate without explicit messaging. No single off-the-shelf architecture fits perfectly. The recommendation is a **three-layer hybrid**:

```
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 3: STIGMERGIC COORDINATION (Runtime, <1ms)                   │
│                                                                     │
│  UrgencyVector[11] ← pheromone-like shared state                   │
│  HiveSignalBus     ← typed event queue with decay                  │
│                                                                     │
│  Each TRM READS urgency + relevant signals BEFORE deciding         │
│  Each TRM WRITES its urgency slot + emits signals AFTER deciding   │
│                                                                     │
│  Design source: S-MADRL virtual pheromones                         │
│  Advantage: Zero communication overhead, emergent coordination     │
│  Latency: <1ms (UrgencyVector), <10ms (SignalBus read)            │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 2: HETEROGENEOUS GRAPH ATTENTION (Encoder, per-cycle)       │
│                                                                     │
│  11 TRM nodes as heterogeneous graph (5 caste types)               │
│  Edges: signal production/consumption matrix (Section 2.4)         │
│  GAT attention: edge-type-specific attention weights               │
│                                                                     │
│  Extends SharedStateEncoder with cross-head context:               │
│    state_embedding = Encoder(raw_state)                  [128-dim] │
│    cross_context   = HetGAT(state, urgency, signals)     [64-dim] │
│    head_input      = [state_embedding ‖ cross_context]   [192-dim] │
│                                                                     │
│  Design source: HetNet heterogeneous graph attention               │
│  Advantage: Learned, type-aware inter-head communication           │
│  Latency: ~2-5ms per cycle (single GAT pass)                      │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 1: RECURSIVE PER-HEAD REFINEMENT (Per-decision, <10ms)      │
│                                                                     │
│  Each TRM head applies Samsung TRM-style recursion:                │
│    z ← head_net(head_input, y, z)    # latent reasoning            │
│    y ← head_net(y, z)                # answer refinement           │
│  Repeat for R steps (default R=3, adaptive halting for urgency)    │
│                                                                     │
│  Design source: Samsung TRM (2510.04871)                           │
│  Advantage: Iterative refinement without parameter increase        │
│  Latency: R × ~1ms = 3ms per head                                 │
└─────────────────────────────────────────────────────────────────────┘
```

### 14.3 Why This Hybrid

**Why not pure MoE?** Mixture-of-Experts assumes homogeneous input → different expert pathways. Our 11 TRMs have *different* input shapes (ATP needs order context, PO needs supplier context, SS needs demand history). MoE routing adds complexity without solving the heterogeneity problem. However, the PEER insight (millions of tiny experts > few large experts) validates our choice of 11 tiny specialized models over 1 large general model.

**Why not pure CTDE (MAPPO/QMIX)?** CTDE is a training paradigm, not an inference architecture. We use CTDE principles already — our centralized training (BC → CQL → TD) with decentralized execution (per-head inference) aligns with MAPPO. But QMIX's value factorization doesn't apply because our TRM heads have different action spaces (discrete actions for ATP, continuous multiplier for SS).

**Why stigmergy as the coordination layer?** Research on S-MADRL demonstrates that stigmergic (pheromone-based) coordination scales better than explicit messaging (MADDPG, MAPPO collapse beyond 3-4 agents, S-MADRL scales to 8+). Our UrgencyVector is exactly a virtual pheromone field — 11 slots, each updated atomically, read by all. The key insight from [S-MADRL](https://arxiv.org/html/2510.03592v1): agents self-organize into asymmetric workload distributions that reduce congestion. This maps to our caste system where different TRMs naturally specialize.

**Why heterogeneous graph attention for the encoder?** [HetNet](https://arxiv.org/abs/2108.09568) achieved 200× reduction in communication bandwidth while improving coordination by 5-707%. Our TRM types are genuinely heterogeneous (Scouts have different observation spaces than Guards). A heterogeneous GAT naturally models the production/consumption matrix from Section 2.4 — edges between TRM types carry type-specific attention weights that learn which cross-TRM signals matter most.

**Why recursive refinement per head?** Samsung TRM research ([TRM_RESEARCH_SYNTHESIS.md](TRM_RESEARCH_SYNTHESIS.md)) demonstrates that recursive refinement dramatically improves decision quality with minimal parameter cost. Our 3-step refinement is already aligned. The critical insight from [arxiv:2512.11847](https://arxiv.org/abs/2512.11847): 94.4% of accuracy is at step 1, with diminishing returns by step 4. For latency-critical paths (ATP: <10ms), we can adaptively reduce to 1-2 steps. For less time-pressured decisions (SafetyStock, PO), full 3-step refinement maximizes quality.

### 14.4 Architectural Specification

#### SharedStateEncoder (Enhanced)

```python
class EnhancedSharedStateEncoder(nn.Module):
    """Shared encoder + heterogeneous cross-head context.

    Extension of current SharedStateEncoder (128-dim, 2 layers, 4 heads)
    with a lightweight HetGAT layer for cross-head coordination.

    Design sources:
    - SharedStateEncoder: current implementation (site_agent_model.py)
    - HetGAT: HetNet (arxiv:2108.09568) — type-aware attention
    - UrgencyVector conditioning: S-MADRL (arxiv:2510.03592) pheromone model
    """

    # Existing encoder (unchanged)
    state_dim: int = 64
    embedding_dim: int = 128
    encoder_layers: int = 2
    encoder_heads: int = 4

    # NEW: Cross-head coordination
    urgency_dim: int = 11             # UrgencyVector input
    signal_summary_dim: int = 22      # Aggregated signal features (count per type)
    cross_context_dim: int = 64       # Output of HetGAT

    # Total head input: 128 (state) + 64 (cross-context) = 192
```

**Forward pass (enhanced)**:

```
Raw State (64 features)
  ↓
SharedStateEncoder (existing)  ──────────► state_embedding [128-dim]
  │
  │  + UrgencyVector[11]
  │  + signal_summary[22]
  │  + tGNN_directive_embedding[32]
  │
  ↓
HetGAT Layer:
  11 TRM nodes, 5 edge types (caste-to-caste)
  Node features: state_embedding + urgency_slot + caste_embedding
  Edge features: signal flow strength (from signal bus)
  ↓
cross_context [64-dim]
  ↓
head_input = [state_embedding ‖ cross_context]  [192-dim]
  ↓
Per-Head Recursive Refinement (R steps)
```

#### Heterogeneous GAT Layer

```python
class HiveHetGAT(nn.Module):
    """Lightweight heterogeneous graph attention for inter-TRM coordination.

    Models the 11 TRM types as heterogeneous nodes in a graph.
    Edges are defined by the signal production/consumption matrix
    from TRM_HIVE_ARCHITECTURE.md Section 2.4.

    Design source: HetNet (arxiv:2108.09568)
    - Type-specific attention: different weight matrices per edge type
    - 200x communication bandwidth reduction in original HetNet
    - 5-707% performance improvement over homogeneous baselines

    Adaptation: Instead of full per-agent-type parameters, we use
    5 caste-level edge types (SCOUT→FORAGER, NURSE→GUARD, etc.)
    to keep parameters manageable.
    """

    NUM_CASTES = 5     # Scout, Forager, Nurse, Guard, Builder
    NUM_EDGE_TYPES = 5 * 5  # Caste × Caste (25, but sparse ~15 active)
    HIDDEN_DIM = 64
    NUM_HEADS = 2

    # Parameters: ~25 edge types × (64 × 64) attention matrices = ~100K
    # Plus node projection: 5 caste types × (192 → 64) = ~60K
    # Total: ~160K additional parameters (2.5% of overall model)
```

**Edge type definition** (derived from Section 2.4 signal matrix):

| Source Caste | Target Caste | Key Signals | Edge Semantics |
|---|---|---|---|
| SCOUT → FORAGER | `ATP_SHORTAGE` → triggers PO | "We need resources" |
| SCOUT → NURSE | `DEMAND_SURGE` → triggers SS review | "Health check needed" |
| FORAGER → SCOUT | `PO_EXPEDITE` → relief signal | "Help is coming" |
| FORAGER → BUILDER | `REBALANCE_OUTBOUND` → TO needed | "Move this" |
| NURSE → FORAGER | `SS_INCREASED` → higher targets | "Order more" |
| NURSE → SCOUT | `FORECAST_ADJUSTED` → recalibrate | "Expect different demand" |
| GUARD → SCOUT | `QUALITY_REJECT` → reduced availability | "We lost inventory" |
| GUARD → BUILDER | `MAINTENANCE_URGENT` → asset down | "Can't produce" |
| BUILDER → SCOUT | `MO_RELEASED` → future supply | "Supply coming" |
| BUILDER → FORAGER | `MO_DELAYED` → may need external | "Supply delayed" |

#### Per-Head Recursive Refinement

```python
class RecursiveTRMHead(nn.Module):
    """Per-task TRM head with Samsung-style recursive refinement.

    Each head maintains latent scratchpad z and answer y,
    iteratively refining through R recursive steps.

    Design source: Samsung TRM (arxiv:2510.04871)
    - 2-layer network applied R times → 2R effective layers
    - Post-norm for recursion stability (arxiv:2602.12078)
    - Full backprop through all recursive steps
    - Adaptive halting based on confidence (optional)

    Key difference from Samsung TRM:
    - Samsung: z = net(x, y, z), y = net(y, z)
    - Ours: z = head(head_input, y, z), y = head(y, z)
    - head_input includes cross-context from HetGAT (not just raw state)
    """

    # Per-head parameters
    head_input_dim: int = 192    # state_embedding + cross_context
    latent_dim: int = 64         # Scratchpad z dimension
    recursive_steps: int = 3     # Default R (adaptable per urgency)

    # Architecture: 2-layer transformer block (shared across steps)
    head_layers: int = 2
    head_heads: int = 2

    # Post-norm (critical for recursion stability per arxiv:2602.12078)
    use_post_norm: bool = True

    # Adaptive halting (from Samsung TRM ACT mechanism)
    adaptive_halt: bool = True   # Stop early if confident
    halt_threshold: float = 0.95 # Confidence threshold for early exit

    # Parameters per head: ~25K (2 layers × 64-dim × 2 heads)
    # 11 heads × 25K = 275K additional for recursive refinement
```

**Recursive forward pass per head**:

```
head_input [192-dim]   ←── from HetGAT (state + cross-context)
  │
  ├── Initialize: y₀ = initial_answer(head_input)  [task-specific shape]
  │              z₀ = zeros(64)                     [latent scratchpad]
  │
  ├── Step 1:  z₁ = PostNorm(head_block(head_input, y₀, z₀))
  │            y₁ = PostNorm(answer_block(y₀, z₁))
  │            if adaptive_halt and confidence(y₁) > 0.95: STOP
  │
  ├── Step 2:  z₂ = PostNorm(head_block(head_input, y₁, z₁))
  │            y₂ = PostNorm(answer_block(y₁, z₂))
  │            if adaptive_halt and confidence(y₂) > 0.95: STOP
  │
  └── Step 3:  z₃ = PostNorm(head_block(head_input, y₂, z₂))
               y₃ = PostNorm(answer_block(y₂, z₃))

  Output: y₃ (action + continuous values + confidence)
```

### 14.5 Parameter Budget

| Component | Current | Proposed | Delta |
|---|---|---|---|
| SharedStateEncoder | ~30K | ~30K (unchanged) | 0 |
| HetGAT Layer | 0 | ~160K | +160K |
| 3 Task Heads (non-recursive) | ~35K | 0 (replaced) | -35K |
| 11 Recursive TRM Heads | 0 | ~275K | +275K |
| UrgencyVector embedding | 0 | ~3K | +3K |
| Signal summary projection | 0 | ~5K | +5K |
| **Total** | **~65K** | **~473K** | **+408K** |

**Result**: ~473K parameters — still tiny (0.5M). Well within the 7M budget validated by Samsung TRM research. The model remains deployable on edge hardware and maintains <10ms inference even with 3-step recursion.

### 14.6 Latency Budget

| Phase | Operation | Latency | Frequency |
|---|---|---|---|
| State encoding | SharedStateEncoder forward | ~1ms | Once per cycle |
| Urgency read | UrgencyVector.read() | <0.1ms | Per head |
| Signal read | HiveSignalBus.read() | <1ms | Per head |
| HetGAT | Cross-head attention pass | ~2ms | Once per cycle |
| Recursive head (3 steps) | 3 × head_block forward | ~3ms | Per head |
| Signal emit | HiveSignalBus.emit() | <0.1ms | Per head |
| **Total per decision** | | **~7ms** | <10ms target ✅ |

With adaptive halting (1-2 steps for high-confidence decisions):

| Decision Type | Typical Steps | Latency |
|---|---|---|
| ATP (reactive, time-critical) | 1-2 | ~4-5ms |
| PO (proactive, can deliberate) | 3 | ~7ms |
| SafetyStock (weekly, thorough) | 3 | ~7ms |
| OrderTracking (reactive) | 1-2 | ~4-5ms |

### 14.7 Training Implications

#### CGAR Curriculum (from [arxiv:2511.08653](https://arxiv.org/abs/2511.08653))

Apply progressive recursion depth during training:

| Training Phase | Recursion Steps | Effective Depth | Purpose |
|---|---|---|---|
| 0-30% | R=1 | 2 layers | Learn basic mappings |
| 30-60% | R=2 | 4 layers | Learn refinement |
| 60-100% | R=3 | 6 layers | Full recursive reasoning |

Expected benefit: ~40% FLOPs reduction during training (per CGAR Sudoku results).

#### Stigmergic Curriculum

Introduce signal context gradually during training:

| Training Phase | Signal Context | Purpose |
|---|---|---|
| Phase 1 | No signals (isolated heads) | Learn individual TRM policies |
| Phase 2 | UrgencyVector only (11 floats) | Learn urgency-aware adjustments |
| Phase 3 | UrgencyVector + signal summaries | Learn cross-head coordination |
| Phase 4 | Full HetGAT + recursive refinement | Learn graph-mediated coordination |

This prevents distribution shift when adding signal features (risk identified in Section 13).

#### Centralized Training, Decentralized Execution (CTDE)

The training paradigm follows MAPPO principles:
- **Centralized**: During training, the HetGAT layer has access to all TRM states and signals (global view)
- **Decentralized**: At inference, each TRM head executes independently using only its portion of the cross-context vector
- **Shared critic**: A single critic network evaluates the joint hive outcome (total site cost, service level) for all 11 heads
- **Per-head actor**: Each head maintains its own policy, trained via PPO with the shared critic

### 14.8 Architecture Comparison Summary

| Dimension | Current (HydraNet) | Proposed (Stigmergic-Graph-Recursive) | Improvement |
|---|---|---|---|
| Cross-head communication | None | UrgencyVector + HiveSignalBus + HetGAT | Full coordination |
| Head architecture | Linear FC layers | Recursive 2-layer blocks (3 steps) | 6× effective depth |
| Parameter count | 65K | 473K | 7.3× (still tiny) |
| Inference latency | ~3ms | ~7ms | 2.3× (within 10ms budget) |
| Coordination mechanism | None | Three-layer (pheromone + graph + recursion) | Stigmergic emergence |
| Edge deployment | ✅ | ✅ (0.5M params, <10ms) | Still edge-viable |
| Heterogeneous agent support | No | Yes (5 caste types, type-aware attention) | First-class |
| Adaptive compute | No | Yes (adaptive halting per urgency) | Latency optimization |
| Training efficiency | Standard BC/RL | CGAR + stigmergic curriculum | ~40% training FLOPs reduction |

### 14.9 Key Research References for This Architecture

| Paper | Contribution to Hive Architecture |
|---|---|
| [Samsung TRM (arxiv:2510.04871)](https://arxiv.org/abs/2510.04871) | Recursive refinement per head, post-norm stability, 7M param validation |
| [CGAR (arxiv:2511.08653)](https://arxiv.org/abs/2511.08653) | Progressive recursion depth curriculum for training efficiency |
| [S-MADRL (arxiv:2510.03592)](https://arxiv.org/abs/2510.03592) | Virtual pheromone coordination, scales to 8+ agents |
| [HetNet (arxiv:2108.09568)](https://arxiv.org/abs/2108.09568) | Heterogeneous graph attention, 200× bandwidth reduction |
| [Knocking-Heads (arxiv:2510.23052)](https://arxiv.org/abs/2510.23052) | Zero-overhead inter-head coordination projections |
| [PEER (arxiv:2407.04153)](https://arxiv.org/abs/2407.04153) | Fine-grained expertise: many tiny experts > few large |
| [MAPPO (arxiv:2103.01955)](https://arxiv.org/abs/2103.01955) | CTDE training paradigm for shared-parameter multi-agent |
| [Mamba-2 TRM (arxiv:2602.12078)](https://arxiv.org/abs/2602.12078) | Post-norm critical for recursion; Mamba hybrid for diversity |
| [TRM Critical Analysis (arxiv:2512.11847)](https://arxiv.org/abs/2512.11847) | 94.4% accuracy at step 1 → adaptive halting justified |
| [Agentic LLM Consensus (tandfonline:2025)](https://www.tandfonline.com/doi/full/10.1080/00207543.2025.2604311) | Multi-agent consensus-seeking for supply chain (validates hive approach) |

---

## 15. Digital Twin Training Pipeline: From Synthetic Data to Production-Ready Hive

### 15.1 The Cold-Start Problem

The TRM Hive cannot be trained from production data because production data does not exist until the hive is deployed. This is a classic chicken-and-egg problem in AI-as-Labor systems. The platform solves it through a **digital twin pipeline** — a stack of simulation capabilities that generates progressively more realistic training data without requiring a single real transaction.

The critical insight for hive training: **stigmergic coordination cannot be learned from isolated decision logs**. If you train each TRM head independently on historical ATP, PO, and inventory decisions, the heads learn individual policies but never learn to respond to each other's signals. The HiveSignalBus, UrgencyVector, and cross-head coordination patterns can only emerge from multi-head execution traces where all 11 TRMs run simultaneously against the same site state.

This is why the digital twin is not optional — it is the only way to generate the coordinated multi-agent traces that the hive architecture requires.

### 15.2 Digital Twin Data Sources

The platform provides five simulation capabilities that compose into a complete digital twin:

| Source | What It Simulates | Output Format | Volume per Run | Training Use |
|---|---|---|---|---|
| **SimPy DAG Simulator** | Full supply chain with stochastic lead times, demand, yields, supplier failures, capacity disruptions | `SimulationResult` → per-site per-product time series (inventory, backlog, pipeline, orders, costs) | 128 runs × 52 weeks × N sites = 100K+ state snapshots | GNN pre-training, demand/supply pattern generation |
| **Beer Game Engine** | Multi-echelon order/shipment dynamics with agent strategies (naive, bullwhip, conservative, ML, LLM) | `ParticipantRound` records (order, inventory, backlog, cost per site per period) | 52 rounds × 4-8 sites × diverse strategies | Behavioral cloning baselines, multi-agent interaction traces |
| **Synthetic TRM Data Generator** | Per-TRM decision scenarios with curriculum-controlled complexity (simple → moderate → full) | `TrainingRecord` (state, action, reward, next_state, expert_action) per TRM type | 365 days × 50-100 decisions/day = 36.5K decision logs | Warm-start behavioral cloning for individual TRM heads |
| **AWS SC Planning Engine** | 3-step planning cycle (demand → targets → net requirements) with stochastic sampling | `SupplyPlan` records (PO/TO/MO requests, probabilistic balanced scorecard) | Per planning run: full horizon of planned actions | Expert labels for PO, MO, TO, Rebalancing TRMs |
| **Synthetic Data Generator** | Complete company archetypes (retailer, distributor, manufacturer) with network, products, forecasts, policies | Full `SupplyChainConfig` + forecasts + inv_policies + sourcing_rules | 1 company = 160-720 SKUs, 10-50 sites, full network topology | Topology diversity for GNN generalization |

### 15.3 Five-Phase Digital Twin Training Pipeline

The pipeline progresses from zero data to a production-ready hive through five phases. Each phase builds on the artifacts of the previous phase. The first three phases use purely synthetic data; Phase 4 introduces copilot feedback; Phase 5 runs autonomously.

```
Phase 1: Individual Head Warm-Start (Behavioral Cloning)
    ↓ each TRM head learns to match deterministic engine baseline
Phase 2: Multi-Head Simulation Traces (Coordinated BC)
    ↓ heads learn to run together; signals begin flowing
Phase 3: Stochastic Stress-Testing (RL Fine-Tuning)
    ↓ Monte Carlo disruptions teach robustness and coordination
Phase 4: Copilot Calibration (Human-in-the-Loop)
    ↓ human overrides correct systematic biases
Phase 5: Autonomous CDC Relearning (Continuous Improvement)
    ↓ production outcomes close the feedback loop
```

#### Phase 1: Individual Head Warm-Start (1-2 days compute)

**Goal**: Each TRM head independently matches the deterministic engine baseline (MRP, AATP, safety stock formulas).

**Data Source**: `SyntheticTRMDataGenerator` curriculum (3 complexity levels per TRM type)

**Process**:
```
For each TRM type in [ATP, Rebalancing, PO, OrderTracking, MO, TO,
                       Quality, Maintenance, Subcontracting,
                       ForecastAdjustment, SafetyStock]:

    1. Generate curriculum data (5000+ scenarios per complexity level)
       ├── Simple: single product, abundant inventory, stable demand
       ├── Moderate: multi-product, scarce inventory, variable demand
       └── Full: disruptions, multi-priority, constraint networks

    2. Train via behavioral cloning
       ├── Loss: MSE(TRM_output, engine_baseline)
       ├── Epochs: 20-30
       ├── Batch size: 64
       └── LR: 1e-4

    3. Validate: TRM output ≈ engine output within ±5%
```

**Output**: 11 independently warm-started TRM head checkpoints. Each head outputs bounded adjustments (±20%) to its engine baseline.

**Why this works**: The deterministic engines (MRP, AATP, safety stock formulas) are always-correct baselines. If a TRM head can reproduce the engine's decision, it has learned the fundamental domain logic. RL fine-tuning in later phases can then improve beyond the engine by exploiting patterns the formulas miss.

**No signals involved**: UrgencyVector and HiveSignalBus are zeroed out. Heads operate in isolation. This is deliberate — you cannot learn coordination until you have competent individuals.

#### Phase 2: Multi-Head Simulation Traces (2-3 days compute)

**Goal**: Generate coordinated execution traces where all 11 TRMs run simultaneously against the same site state, producing the signal interaction data that stigmergic learning requires.

**Data Source**: Beer Game Engine + SimPy DAG Simulator running with all TRM heads active

**Process**:
```
1. Create N supply chain configs (diverse topologies)
   ├── Use SyntheticDataGenerator archetypes (retailer, distributor, manufacturer)
   ├── Vary: number of sites (4-50), products (10-200), echelons (2-5)
   └── Each config gets its own SimPy stochastic parameters

2. For each config, run M simulation episodes (M=100-500):
   a. Initialize BeerLine/DAG with Phase 1 TRM checkpoints at each site
   b. For each period t = 1..T:
      ├── Process shipments, fulfill demand (engine step)
      ├── Run ALL 11 TRM heads at each site (coordinated execution)
      │   ├── ATPExecutorTRM decides → emits signal → updates UrgencyVector[0]
      │   ├── OrderTrackingTRM reads urgency → decides → emits signal → updates UrgencyVector[1]
      │   ├── POCreationTRM reads signals → decides → emits signal → updates UrgencyVector[2]
      │   ├── ... (all 11 heads in phase-ordered sequence)
      │   └── Each decision includes signal_context and urgency_at_time
      ├── Record MultiHeadTrace:
      │   {
      │     site_key, period, config_id,
      │     urgency_vector_before: float[11],
      │     urgency_vector_after: float[11],
      │     signals_emitted: List[HiveSignal],
      │     signals_consumed: Dict[trm_type → List[HiveSignal]],
      │     per_head_decisions: Dict[trm_type → {state, action, confidence}],
      │     site_metrics: {inventory, backlog, service_level, cost}
      │   }
      └── Advance simulation clock

3. Compute cross-head rewards:
   ├── Standard per-head reward (fill_rate, OTIF, cost)
   ├── Cross-head attribution: did PO expedite triggered by ATP shortage signal
   │   actually improve fill rate 3 periods later?
   └── Hive-level reward: total site cost + service level (shared critic target)
```

**Output**: Multi-head trace dataset — the critical artifact that no other training source provides.

**Volume**: 100 configs × 500 episodes × 52 periods × 11 TRMs = 28.6M coordinated decision records. Each record includes the signal context (what other TRMs were doing), enabling the model to learn cross-head coordination.

**Training on traces**:
```
For each MultiHeadTrace in dataset:
    1. Encode site state → SharedStateEncoder → state_embedding [128-dim]
    2. Construct UrgencyVector from trace.urgency_vector_before
    3. Construct signal_summary from trace.signals_consumed
    4. Run HetGAT (if using proposed architecture) → cross_context [64-dim]
    5. For each TRM head:
       ├── Input: [state_embedding ‖ cross_context ‖ urgency_slot]
       ├── Target: trace.per_head_decisions[trm_type].action
       ├── Loss: MSE + cross-head attribution bonus
       └── Backprop through HetGAT (shared gradients)
```

**Key insight**: This is where stigmergic coordination emerges. The model learns that when ATP emits a SHORTAGE signal (urgency=0.8), POCreationTRM should respond with expedite, SafetyStockTRM should increase buffers, and RebalancingTRM should look for cross-site transfers. These patterns only appear in multi-head traces.

#### Phase 3: Stochastic Stress-Testing (3-5 days compute)

**Goal**: Use Monte Carlo disruptions to teach the hive robustness — how to coordinate under uncertainty, not just under steady-state.

**Data Source**: SimPy DAG Simulator with aggressive stochastic configuration

**Process**:
```
1. Configure extreme stochastic scenarios:
   ├── Lead time CV: 0.30-0.50 (vs 0.20 normal)
   ├── Demand CV: 0.25-0.40 (vs 0.15 normal)
   ├── Supplier reliability: 0.70-0.90 (vs 0.95 normal)
   ├── Capacity disruptions: 5-10% probability (vs 2% normal)
   ├── Yield variability: 0.10-0.15 CV (vs 0.05 normal)
   └── Demand pattern shocks: step changes, seasonal spikes, bullwhip amplification

2. Run Monte Carlo campaigns:
   ├── 2500 runs per config (matches existing SimPy pipeline)
   ├── Each run: 64 periods with different random seeds
   ├── All 11 TRM heads active with Phase 2 checkpoints
   └── Full signal bus and urgency vector recording

3. RL fine-tuning on stress traces:
   ├── Method: Offline RL (Conservative Q-Learning / CQL)
   ├── Replay buffer: 100K most recent experiences per TRM type
   ├── Conservative penalty prevents overestimation of unseen actions
   ├── Shared critic on hive-level reward (site cost + service level)
   └── Per-head actor trained via PPO with shared critic
```

**Stress scenarios and what they teach**:

| Disruption | TRM Coordination Pattern Learned |
|---|---|
| **Supplier failure** (reliability=0.70) | ATP detects shortfall → PO switches to alternate supplier → Rebalancing pulls from sibling sites → SafetyStock increases buffer |
| **Demand spike** (step change +50%) | ATP rejects low-priority orders → ForecastAdjustment signals upward revision → PO increases quantities → MO releases additional production |
| **Capacity disruption** (factory down 3 days) | Maintenance flags asset unavailable → MO defers/splits orders → TO reroutes to alternate plant → Subcontracting engages external manufacturer |
| **Quality batch failure** (scrap 20% of lot) | Quality rejects batch → ATP reduces available inventory → Rebalancing pulls replacements → PO expedites replenishment |
| **Lead time spike** (+50% on key lane) | OrderTracking detects late shipments → SafetyStock increases buffer → PO adjusts timing → ForecastAdjustment accounts for pipeline delay |
| **Bullwhip amplification** (demand variance ×3 at upstream) | ForecastAdjustment dampens upstream signal → PO smooths order quantities → SafetyStock moderates buffer swings → Rebalancing absorbs local excess |

**Output**: Stress-tested hive checkpoints that have experienced thousands of disruption combinations. The hive learns not just individual response to disruption but coordinated multi-TRM response patterns.

**Validation metric**: Compare hive performance (total cost, service level) under stress against:
- Deterministic engine baseline (no TRM adjustments)
- Phase 1 checkpoints (individual heads, no coordination)
- Phase 2 checkpoints (coordination but no stress exposure)

Expected improvement: 20-35% cost reduction vs deterministic baseline under stochastic conditions (per CLAUDE.md performance targets).

#### Phase 4: Copilot Calibration (Ongoing, 2-4 weeks)

**Goal**: Deploy the Phase 3 hive in copilot mode. Human planners review and override TRM decisions. Override patterns correct systematic biases the digital twin could not capture.

**Data Source**: Production decisions with human feedback

**Process**:
```
1. Deploy hive in copilot mode (agent_mode=COPILOT):
   ├── TRM suggests decisions (bounded ±20%)
   ├── Human planner reviews via Worklist UI
   ├── Accept → decision executes, recorded as AI_ACCEPTED
   ├── Override → human provides correction + reason, recorded as AI_MODIFIED
   └── Reject → human provides alternative, recorded as AI_REJECTED

2. Capture override patterns:
   ├── powell_site_agent_decisions.is_expert = True for overrides
   ├── override_reason stored for RLHF-style learning
   ├── Human Override Rate tracked per TRM type
   └── Patterns aggregated daily

3. Fine-tune on expert data:
   ├── Behavioral cloning on override decisions (expert_action = human choice)
   ├── Weight expert data 3-5× higher than synthetic data
   ├── Focus on TRM types with highest override rate
   └── Update hive checkpoint when loss improves >5%
```

**What copilot calibration captures that the digital twin cannot**:
- Customer-specific preferences (always prioritize customer X)
- Seasonal business rules (no PO changes during fiscal close)
- Supplier relationship context (preferred vendor even if not cheapest)
- Regulatory constraints (country-specific quality rules)
- Organizational politics (protect capacity for VIP product line)

**Key metric**: Human Override Rate should decrease from ~40-60% (initial copilot) to ~10-20% (calibrated hive) over 2-4 weeks. Below 10% signals readiness for autonomous mode.

#### Phase 5: Autonomous CDC Relearning (Continuous)

**Goal**: The hive runs autonomously. The CDC → Relearning feedback loop continuously improves models from actual production outcomes.

**Data Source**: Production outcomes via `OutcomeCollectorService`

**Process**:
```
SiteAgent decisions (11 TRMs per site, continuous)
    ↓ stored in powell_site_agent_decisions with signal_context
    ↓
OutcomeCollectorService (hourly :30)
    ↓ waits for feedback horizon per TRM type:
    │   ATP: 4 hours (order fulfillment observable)
    │   Inventory: 24 hours (next-day snapshot)
    │   PO: 7 days (delivery receipt)
    │   MO: 24-72 hours (production completion)
    │   Quality: 4-24 hours (inspection result)
    ↓ computes actual outcome + reward signal
    ↓
CDCMonitor (6 real-time conditions)
    ↓ triggers when:
    │   Demand vs forecast: ±15%
    │   Service level: <(target - 5%)
    │   Inventory: <70% or >150% of target
    │   Lead time: +30% vs expected
    │   Backlog: 2+ consecutive days growth
    │   Forecast accuracy: >20% deviation
    ↓
CDCRetrainingService (every 6h or on trigger)
    ↓ evaluates: ≥100 experiences + trigger + cooldown elapsed
    ↓ executes: TRMTrainer.train() with Offline RL (CQL)
    ↓ safety: reject if regression >10% vs current checkpoint
    ↓
New checkpoint → SiteAgent.reload_model()
```

**Digital twin role in Phase 5**: The digital twin does not disappear in production. It serves three ongoing functions:

1. **Counterfactual evaluation**: Before deploying a new CDC-retrained checkpoint, run it against the same disruption scenarios from Phase 3. If stress-test performance degrades, reject the checkpoint even if production loss improved. This prevents catastrophic forgetting — the model should not "forget" how to handle supplier failures just because none occurred recently.

2. **Scenario pre-screening**: When CDCMonitor detects a condition (e.g., demand spike), immediately run the Phase 3 stress simulator with that specific scenario. Compare current hive behavior against the stress-trained baseline. If the hive already handles it well, suppress the CDC trigger (avoid unnecessary retraining).

3. **Exploration budget**: Periodically (weekly) run the digital twin with randomized epsilon-greedy exploration on 5% of decisions. This generates training data for actions the production hive would never take, preventing the replay buffer from becoming too narrow. The explored decisions are evaluated in simulation, not production — no risk to real operations.

### 15.4 Data Volume Requirements

| Phase | Records Generated | Compute Time | Storage |
|---|---|---|---|
| Phase 1 (Individual BC) | 11 TRMs × 15K curriculum records = 165K | 1-2 days (CPU) | ~50MB |
| Phase 2 (Multi-head traces) | 100 configs × 500 episodes × 52 periods × 11 heads = 28.6M | 2-3 days (GPU) | ~8GB |
| Phase 3 (Stress-testing) | 2500 runs × 64 periods × 11 heads = 1.76M per config, ×10 configs = 17.6M | 3-5 days (GPU) | ~5GB |
| Phase 4 (Copilot) | ~200-500 human-reviewed decisions/day × 20 days = 4K-10K | Ongoing | ~10MB |
| Phase 5 (CDC relearning) | ~100-1000 decisions/day with outcomes | Ongoing | ~1MB/day |
| **Total synthetic** | **~46M records** | **~7-10 days** | **~13GB** |

The total dataset is modest by modern ML standards. For reference, Samsung's TRM was trained on 10K Sudoku puzzles (tiny). Our 46M records provide orders of magnitude more coverage because supply chain state spaces are lower-dimensional than general reasoning tasks.

### 15.5 Multi-Topology Training for Generalization

A single supply chain topology produces biased training data. A hive trained only on a 4-site linear Beer Game will fail on a 50-site convergent/divergent manufacturer network. The digital twin pipeline addresses this through topology diversity:

```
SyntheticDataGenerator.generate() with varied archetypes:

  Retailer Topologies:
  ├── 2 CDCs → 8 RDCs → 40 Stores (divergent, high fan-out)
  ├── 1 NDC → 4 RDCs → 12 Stores + 4 Online (hybrid)
  └── Direct-to-consumer (2-echelon, minimal)

  Distributor Topologies:
  ├── 3 NDCs → 6 RDCs → 12 LDCs (balanced tree)
  ├── Hub-and-spoke (1 NDC → 20 LDCs)
  └── Cross-dock (pass-through with minimal holding)

  Manufacturer Topologies:
  ├── 3 Plants → 2 Sub-Assy → 5 Component Suppliers (convergent)
  ├── Single mega-plant → 10 DCs → 30 Customers (divergent)
  └── Multi-tier BOM (3+ levels, 160+ SKUs)

  Beer Game (linear baseline):
  ├── Classic 4-site: Retailer → Wholesaler → Distributor → Factory
  ├── Extended 6-site with component supplier and raw material
  └── Variable lead-time and demand patterns (step, seasonal, random)
```

**Training strategy**: Mix topologies in each training batch. The SharedStateEncoder learns topology-invariant features (relative inventory position, demand-to-capacity ratio, days-of-supply). The HetGAT learns that coordination patterns (SCOUT→FORAGER signals) transfer across topologies even if absolute inventory levels differ.

**Validation**: Hold out 2-3 topologies never seen during training. Measure hive performance on unseen topologies. Generalization gap should be <10% cost degradation.

### 15.6 Hive Signal Training: The Coordination Curriculum

Standard behavioral cloning produces heads that make good isolated decisions but ignore signals. The coordination curriculum introduces signal awareness gradually to prevent distribution shift:

**Stage 1 — Silent Hive** (Phase 1 data):
```
Input:  [state_embedding(128) | zeros(64)]  = 192-dim
Target: engine baseline action
Signal bus: disabled
```
Each head learns its own policy. No coordination. This is the foundation.

**Stage 2 — Passive Listeners** (early Phase 2 data):
```
Input:  [state_embedding(128) | urgency_vector(11) | zeros(53)]  = 192-dim
Target: engine baseline action (same labels as Stage 1)
Signal bus: read-only (heads see urgency but don't respond to it yet)
```
The urgency vector is presented as additional input features but the training labels remain the same (engine baselines). The model learns to encode urgency without being pressured to act on it. This prevents catastrophic forgetting of Stage 1 policies.

**Stage 3 — Active Coordination** (late Phase 2 data):
```
Input:  [state_embedding(128) | urgency_vector(11) | signal_summary(22) | tGNN_directive(31)]  = 192-dim
Target: coordinated action from multi-head trace (may differ from engine baseline)
Signal bus: fully active (read + write)
Cross-head reward: included in loss (did your signal help a downstream TRM?)
```
Now the training labels come from the coordinated multi-head traces, not from the engine baseline. The model learns that when ATP urgency is high, PO should expedite — because the trace data shows this correlation leads to better hive-level outcomes.

**Stage 4 — Stress-Adapted Coordination** (Phase 3 data):
```
Input:  full 192-dim with disruption indicators
Target: stress-tested coordinated action
Signal bus: high-urgency signals dominate
RL fine-tuning: CQL on disruption replay buffer
```
The model learns crisis coordination — how to rapidly reprioritize when multiple TRMs fire high-urgency signals simultaneously.

### 15.7 Integration with Existing Training Infrastructure

The digital twin pipeline connects to existing platform components without requiring new infrastructure:

| Pipeline Step | Existing Component | File |
|---|---|---|
| Generate topologies | `SyntheticDataGenerator` | `backend/app/services/synthetic_data_generator.py` |
| Generate curriculum data | `SyntheticTRMDataGenerator` | `backend/app/services/powell/synthetic_trm_data_generator.py` |
| Run stochastic simulations | `DAGSimPySimulator` | `backend/app/services/dag_simpy_simulator.py` |
| Run Beer Game episodes | `BeerLine.tick()` | `backend/app/services/engine.py` |
| Configure stochasticity | `StochasticConfig` | `backend/app/services/aws_sc_planning/stochastic_sampler.py` |
| Train individual TRMs | `TRMTrainer` (BC, CQL, Hybrid) | `backend/app/services/powell/trm_trainer.py` |
| Train GNN | `train_gpu_default.py` | `backend/scripts/training/train_gpu_default.py` |
| Generate GNN training tensors | `SimPyAdapter` | `backend/app/rl/data_generator.py` |
| Collect outcomes | `OutcomeCollectorService` | `backend/app/services/powell/outcome_collector.py` |
| Monitor conditions | `CDCMonitor` | `backend/app/services/powell/cdc_monitor.py` |
| Retrain autonomously | `CDCRetrainingService` | `backend/app/services/powell/cdc_retraining_service.py` |
| Calibrate uncertainty | `ConformalOrchestrator` | `backend/app/services/conformal_orchestrator.py` |
| Aggregate hierarchies | `AggregationService` | `backend/app/services/aggregation_service.py` |

**New components required** (for multi-head trace generation):

| Component | Purpose | Estimated Effort |
|---|---|---|
| `MultiHeadTraceRecorder` | Record all 11 TRM decisions + signals per site per period during simulation | 1-2 days |
| `CoordinatedSimRunner` | Orchestrate SimPy/BeerGame with all TRM heads active and signal bus enabled | 2-3 days |
| `CrossHeadRewardCalculator` | Compute attribution: which TRM's signal improved which other TRM's outcome | 2-3 days |
| `HiveTrainingDataLoader` | PyTorch DataLoader for multi-head traces with signal context | 1-2 days |
| `StressScenarioLibrary` | Curated disruption configurations for Phase 3 | 1 day |

Total new infrastructure: **~1.5-2 weeks** of implementation.

### 15.8 Conformal Prediction Integration

The digital twin generates not just training data but also the calibration data for conformal prediction intervals. These intervals are critical for TRM confidence — they define the range within which TRM adjustments are trustworthy.

**During Phase 3 (stress-testing)**:
```
For each stochastic variable (lead_time, demand, yield, capacity):
    1. Digital twin generates predicted distribution (P10/P50/P90)
    2. Simulation produces actual value
    3. ConformalOrchestrator records (predicted, actual) pair
    4. After 1000+ pairs: calibrate conformal intervals
    5. Store in powell_belief_state table
```

**At inference**: Each TRM decision includes a conformal prediction interval. If the TRM's confidence falls outside the calibrated interval, the decision is flagged for human review (in copilot mode) or clamped to the engine baseline (in autonomous mode). The digital twin provides the calibration data that makes this safety mechanism possible.

### 15.9 Makefile Integration

```makefile
# Generate multi-head training traces
make generate-hive-traces CONFIG_NAME="Default TBG" \
    NUM_CONFIGS=10 EPISODES_PER_CONFIG=500 PERIODS=52

# Train hive from scratch (all 5 phases, synthetic only)
make train-hive-cold-start CONFIG_NAME="Default TBG" \
    TRAIN_DEVICE=cuda TRAIN_EPOCHS=50

# Stress-test current hive checkpoint
make stress-test-hive CHECKPOINT=latest \
    STRESS_LEVEL=high NUM_RUNS=2500

# Validate hive on held-out topologies
make validate-hive-generalization CHECKPOINT=latest \
    HOLDOUT_CONFIGS="retailer_large,manufacturer_complex"

# Run counterfactual evaluation before deploying CDC checkpoint
make counterfactual-eval CHECKPOINT=cdc_latest \
    BASELINE=production_current STRESS_SCENARIOS=phase3
```

### 15.10 Summary: Digital Twin as Training Substrate

The digital twin is not a separate system — it is the supply chain platform itself, running in simulation mode. The same engines that execute real planning decisions (MRP, AATP, safety stock) generate the expert labels for behavioral cloning. The same SimPy simulator that evaluates stochastic plans generates the disruption scenarios for stress-testing. The same CDC monitor that triggers production retraining also validates checkpoints against simulated baselines.

This architectural unity means that as the platform's planning capabilities improve (new engines, better stochastic models, more accurate forecasts), the digital twin automatically produces better training data. The hive gets smarter not just from production feedback but from every improvement to the simulation substrate it trains on.

```
┌──────────────────────────────────────────────────────────────────┐
│                     DIGITAL TWIN PIPELINE                        │
│                                                                  │
│  ┌─────────────┐   ┌───────────────┐   ┌──────────────────┐    │
│  │ Synthetic    │   │ SimPy DAG     │   │ Beer Game        │    │
│  │ Data Gen     │   │ Simulator     │   │ Engine           │    │
│  │ (topologies) │   │ (stochastic)  │   │ (multi-echelon)  │    │
│  └──────┬──────┘   └───────┬───────┘   └────────┬─────────┘    │
│         │                  │                     │               │
│         └──────────────────┼─────────────────────┘               │
│                            │                                     │
│                   ┌────────▼────────┐                            │
│                   │ CoordinatedSim  │                            │
│                   │ Runner          │                            │
│                   │ (all 11 TRMs    │                            │
│                   │  + signal bus)  │                            │
│                   └────────┬────────┘                            │
│                            │                                     │
│              ┌─────────────┼─────────────┐                      │
│              ▼             ▼             ▼                       │
│    ┌─────────────┐ ┌────────────┐ ┌──────────────┐              │
│    │ Multi-Head  │ │ Stochastic │ │ Conformal    │              │
│    │ Traces      │ │ Stress     │ │ Calibration  │              │
│    │ (28.6M      │ │ Traces     │ │ Data         │              │
│    │  records)   │ │ (17.6M)    │ │ (intervals)  │              │
│    └──────┬──────┘ └─────┬──────┘ └──────┬───────┘              │
│           │              │               │                       │
│           └──────────────┼───────────────┘                       │
│                          ▼                                       │
│              ┌───────────────────────┐                           │
│              │ TRM Hive Training     │                           │
│              │ ├── Phase 1: BC       │                           │
│              │ ├── Phase 2: Coord BC │                           │
│              │ ├── Phase 3: RL/CQL   │                           │
│              │ ├── Phase 4: Copilot  │◄── Human overrides       │
│              │ └── Phase 5: CDC      │◄── Production outcomes   │
│              └───────────┬───────────┘                           │
│                          ▼                                       │
│              ┌───────────────────────┐                           │
│              │ Production-Ready Hive │                           │
│              │ (11 TRMs per site,    │                           │
│              │  stigmergic coord,    │                           │
│              │  <10ms inference)     │                           │
│              └───────────────────────┘                           │
└──────────────────────────────────────────────────────────────────┘
```

### 15.11 Digital Twin Training per Architecture Variant

Section 14 evaluated seven candidate architectures for intra-hive coordination. The digital twin training pipeline adapts to each — simpler architectures require substantially less training data and compute because they have fewer coordination mechanisms to learn.

#### Architecture A: HydraNet — Current State (Minimal Training)

**What it is**: SharedStateEncoder + independent heads. No cross-head communication.

**Training data needed**: Only Phase 1 (individual BC) and Phase 3 (RL fine-tuning with stochastic data). No multi-head traces needed because there is no coordination to learn.

```
Phase 1: BC warm-start per head          → 165K records, 1-2 days
Phase 3: RL fine-tuning per head         → 1.76M records per config, 2-3 days
Skip Phase 2 entirely (no signals exist)
Total: ~2M records, ~3-5 days compute
```

**Digital twin role**: SimPy generates independent decision scenarios per TRM type. Beer Game provides multi-echelon context but each head trains on its own slice. This is what the platform does today.

**Limitation**: Each head is blind to what other heads decided. ATP may promise inventory that Quality just rejected. PO may expedite a replenishment that SafetyStock already covered through rebalancing.

#### Architecture B: Sparse MoE with Per-Task Routing (Moderate Training)

**What it is**: Router network selects which expert sub-networks activate for each input. Tasks share some experts but have task-specific routing.

**Training data needed**: Standard per-task data (same as Architecture A) plus router training data that teaches the gating network which experts to activate for which state patterns.

```
Phase 1: BC warm-start per expert        → 165K records, 1-2 days
Phase 2: Router training                 → 500K records with task labels, 1-2 days
Phase 3: End-to-end RL fine-tuning       → 2M records, 2-3 days
Total: ~2.7M records, ~4-7 days compute
```

**Digital twin role**: The key challenge is generating training data with sufficient task diversity — the router must learn that a "demand spike + low inventory" state should route to ATP+PO+SafetyStock experts simultaneously. SimPy Monte Carlo with varied disruption profiles provides this diversity. No multi-head coordination traces are needed because MoE routes within a single forward pass; experts do not emit signals to each other.

**Limitation**: MoE assumes homogeneous input shapes. Our 11 TRMs have different input shapes (ATP needs order context, PO needs supplier context). MoE routing adds overhead without solving the heterogeneity problem. The PEER insight validates many tiny experts, but MoE does not provide inter-expert communication.

#### Architecture C: Stigmergic MARL / S-MADRL (Phase A — Pragmatic Choice)

**What it is**: UrgencyVector + HiveSignalBus provide indirect coordination via virtual pheromones. No neural coordination layer — heads communicate through shared environmental state.

**Training data needed**: Phase 1 (individual BC) + Phase 2 (multi-head traces with signal context). Phase 2 is lighter than the full hybrid because there is no HetGAT to train — the model only needs to learn input features that include urgency and signal summaries.

```
Phase 1: BC warm-start per head          → 165K records, 1-2 days
Phase 2: Multi-head traces with signals  → 5M records (100 configs × 100 episodes × 52 periods × ~10 active heads), 2-3 days
Phase 3: RL fine-tuning on stress data   → 5M records, 2-3 days
Total: ~10M records, ~5-8 days compute
```

**Digital twin adaptation for stigmergic training**:

The critical difference from Architecture A: the digital twin must run all heads simultaneously to generate the signal interaction data.

```
CoordinatedSimRunner (simplified for stigmergic-only):

For each simulation period:
    1. Encode site state → SharedStateEncoder → state_embedding [128-dim]

    2. Construct input for each head:
       head_input = [state_embedding | urgency_vector[11] | signal_summary[22]]
       (Total: 128 + 11 + 22 = 161 features per head)

    3. Execute heads in phase order (Section 4):
       SCOUTS first  → ATP, OrderTracking emit signals
       FORAGERS next → PO, Rebalancing, Subcontracting read + emit
       NURSES        → SafetyStock, ForecastAdjustment read + emit
       GUARDS        → Quality, Maintenance read + emit
       BUILDERS last → MO, TO read + emit

    4. Record per-head:
       {state, urgency_before, signals_consumed, action, urgency_after, signals_emitted}

    5. No HetGAT pass needed — heads read urgency/signals as raw input features
```

**Why this is the recommended starting point**: S-MADRL research shows stigmergic coordination scales to 8+ agents where explicit messaging (MADDPG, MAPPO) collapses at 3-4. The UrgencyVector is exactly a virtual pheromone field — 11 slots, each updated atomically, read by all. The heads learn to respond to urgency patterns without any neural graph layer. Training data requirements are 5× less than the full hybrid.

**What the digital twin teaches the stigmergic model**:

| Simulation Scenario | Stigmergic Pattern Learned |
|---|---|
| ATP rejects 3 orders in a row | PO reads urgency[ATP]=0.8 → expedites next order |
| Quality rejects batch (urgency[Quality]=0.9) | ATP reads high quality urgency → reduces available inventory promises |
| SafetyStock increases buffer (emits SS_INCREASED) | Rebalancing reads signal → checks if sister sites can provide |
| MO delayed by maintenance (urgency[Maintenance]=0.7) | TO reads delay signal → reroutes to alternate production site |

Each pattern emerges from multi-head simulation traces — they cannot be learned from isolated decision logs.

#### Architecture D: Heterogeneous Graph Attention (HetGAT Only)

**What it is**: 11 TRM types modeled as nodes in a heterogeneous graph with caste-to-caste edge types. Learned attention weights replace the implicit stigmergic coordination with explicit graph-mediated communication.

**Training data needed**: Full multi-head traces with cross-head attribution (same as Phase 2 of the full pipeline, but without recursive refinement).

```
Phase 1: BC warm-start per head          → 165K records, 1-2 days
Phase 2: Multi-head traces with graph    → 28.6M records (full trace dataset), 3-4 days
Phase 3: RL fine-tuning on stress data   → 17.6M records, 3-5 days
Total: ~46M records, ~7-11 days compute
```

**Digital twin adaptation**: Same as full hybrid Phase 2, but each head is a simple FC network (not recursive). The HetGAT layer requires backpropagation through the graph, so multi-head traces must include per-head gradients. The `CrossHeadRewardCalculator` computes attribution: when ATP emits a shortage signal and PO responds with expedite, did the expedite improve the ATP fill rate 3 periods later? This cross-head reward is the training signal for the HetGAT edge attention weights.

**Trade-off vs stigmergic**: HetGAT learns richer coordination patterns (attention weights reveal which TRM relationships matter most), but requires ~5× more training data and the HetGAT layer adds ~160K parameters and ~2ms latency. For hives with only 3-4 active heads, the overhead is not justified. For full 11-head hives, the learned attention may outperform fixed stigmergic coupling.

#### Architecture E: CTDE with MAPPO/QMIX (Training Paradigm, Not Architecture)

**What it is**: Not a model architecture but a training paradigm. Centralized training (shared critic with global state view), decentralized execution (per-head actors with local state only).

**Training data needed**: Same as whatever architecture CTDE wraps. CTDE changes how the model trains, not what data it needs. The shared critic needs hive-level rewards (total site cost, service level) which the digital twin naturally produces from SimPy/Beer Game episodes.

**Digital twin adaptation**: The shared critic is trained on site-level outcomes (not per-head outcomes). The digital twin records per-episode site metrics:
```python
site_outcome = {
    "total_cost": holding_cost + backlog_cost + ordering_cost,
    "service_level": fulfilled / demanded,
    "bullwhip_ratio": upstream_order_variance / downstream_demand_variance,
    "inventory_turns": demand / avg_inventory,
}
# Shared critic learns: Q(all_11_head_states, all_11_head_actions) → site_outcome
```

**Key insight**: CTDE is compatible with any of the other architectures. Apply it to Architecture C (stigmergic) for the simplest CTDE setup, or to the full hybrid for maximum coordination.

#### Architecture F: Knocking-Heads Attention (Zero-Overhead Cross-Head)

**What it is**: Cross-head projections within the existing transformer attention layers. No additional parameters, no additional latency — coordination happens inside the attention mechanism.

**Training data needed**: Multi-head traces (similar to Architecture D) but without a separate HetGAT layer. The cross-head projections learn from the same data that trains individual heads — they just need the heads to run simultaneously.

```
Phase 1: BC warm-start per head          → 165K records, 1-2 days
Phase 2: Multi-head traces (lighter)     → 10M records, 2-3 days
Phase 3: RL fine-tuning                  → 5M records, 2-3 days
Total: ~15M records, ~5-8 days compute
```

**Digital twin adaptation**: The key difference from Architecture D is that Knocking-Heads does not require a separate graph construction step. The cross-head projections are part of the existing transformer layers — they learn which attention heads in one TRM should attend to which attention heads in another TRM. The digital twin generates standard multi-head traces; the coordination emerges from the training process, not from explicit graph structure.

**Trade-off**: Zero latency overhead (appealing for the <10ms budget), but the coordination patterns are less interpretable than HetGAT attention weights or stigmergic urgency vectors.

#### Architecture G: Recursive Multi-Head / Samsung TRM-Style (Per-Head Enhancement)

**What it is**: Each head applies recursive refinement (z/y scratchpad loop for R steps) within its own decision. This is an intra-head enhancement, not inter-head coordination.

**Training data needed**: Same as Architecture A (independent per-head) but with recursive target labels — the curriculum must include problems that benefit from iterative reasoning.

```
Phase 1: BC warm-start with CGAR curriculum → 200K records (progressive R), 2-3 days
Phase 3: RL fine-tuning with recursive heads → 2M records, 3-5 days
Skip Phase 2 (no inter-head coordination)
Total: ~2.2M records, ~5-8 days compute
```

**Digital twin adaptation for recursive training**: The CGAR curriculum (Section 14.7) requires progressive recursion depth during training. The digital twin generates problems of increasing difficulty:

```
Training 0-30%:  R=1 (2 effective layers)
    Digital twin: simple scenarios, obvious decisions, stable demand
    Purpose: learn basic state→action mapping

Training 30-60%: R=2 (4 effective layers)
    Digital twin: moderate scenarios, trade-offs, variable demand
    Purpose: learn to refine initial guess via latent scratchpad

Training 60-100%: R=3 (6 effective layers)
    Digital twin: complex scenarios, disruptions, conflicting signals
    Purpose: learn full iterative reasoning under uncertainty
```

The `SyntheticTRMDataGenerator` already produces three complexity levels (simple, moderate, full) — these map directly to the CGAR curriculum phases.

**Trade-off**: Recursive refinement is an orthogonal enhancement that can be combined with any coordination mechanism. Add it to Architecture C (stigmergic + recursive) for low-overhead improvement, or to Architecture D (HetGAT + recursive) for the full hybrid.

#### Summary: Training Effort per Architecture

| Architecture | Training Data | Compute | New Infrastructure | Coordination Quality |
|---|---|---|---|---|
| **A. HydraNet (current)** | 2M records | 3-5 days | None (exists today) | None |
| **B. Sparse MoE** | 2.7M records | 4-7 days | Router training loop | Within-forward-pass only |
| **C. Stigmergic (Phase A)** | 10M records | 5-8 days | CoordinatedSimRunner | Emergent via pheromones |
| **D. HetGAT only** | 46M records | 7-11 days | HetGAT + CrossHeadReward | Learned graph attention |
| **E. CTDE (any base)** | Same as base | +1-2 days | Shared critic network | Training paradigm |
| **F. Knocking-Heads** | 15M records | 5-8 days | Cross-head projections | Implicit in attention |
| **G. Recursive (per-head)** | 2.2M records | 5-8 days | CGAR curriculum | None (intra-head only) |
| **C+D+G Hybrid (Section 14.2)** | 46M records | 7-10 days | All of the above | Three-layer full stack |
| **C+G (Pragmatic hybrid)** | 10M records | 5-8 days | CoordinatedSimRunner + CGAR | Stigmergic + recursive |

**Recommended progression**: Start with **C (stigmergic)**, which provides the best value-to-effort ratio. Add **G (recursive)** to individual heads as a per-head enhancement. Defer **D (HetGAT)** until 6+ heads are active and stigmergic coordination patterns are validated. This matches the Phase A → B → C progression from the effort estimate discussion.

---

## 16. Multi-Site Physical Architecture: The Complete Coordination Stack

### 16.1 The Physical Reality

In production, the Autonomy platform manages a network of supply chain sites — factories, distribution centers, warehouses, retail locations, suppliers. A mid-market manufacturer might have 10-50 sites; a large distributor could have 200+. Each site runs its own TRM hive (11 agents). The question is: **how do 550 agents across 50 sites coordinate?**

The answer is a four-layer coordination stack, where each layer operates at a different speed and scope:

```
┌───────────────────────────────────────────────────────────────────────────┐
│  LAYER 4: S&OP CONSENSUS BOARD (Policy Parameters)                       │
│  Scope: Enterprise-wide    Cadence: Weekly/Monthly    Latency: Hours     │
│                                                                          │
│  Functional agents negotiate Policy Envelope parameters:                 │
│  safety_stock_targets, OTIF_floors, allocation_reserves, expedite_caps   │
│  Output: PolicyParameters θ → consumed by all downstream layers          │
│  Implementation: Agentic Consensus Board (AAP Section 10)                │
│  Who: VP Supply Chain, S&OP Director review                              │
├───────────────────────────────────────────────────────────────────────────┤
│  LAYER 3: AGENTIC AUTHORIZATION PROTOCOL (Cross-Authority Negotiation)   │
│  Scope: Cross-site, cross-function    Cadence: On-demand    Latency: s-m │
│                                                                          │
│  When a TRM decision exceeds its authority boundary:                     │
│  Site A's RebalancingTRM wants to pull from Site B →                     │
│    AuthorizationRequest → Site B evaluates → Accept/Reject               │
│  Net benefit threshold governs autonomy vs escalation                    │
│  Implementation: AGENTIC_AUTHORIZATION_PROTOCOL.md                       │
│  Who: Agents negotiate autonomously; humans review edge cases            │
├───────────────────────────────────────────────────────────────────────────┤
│  LAYER 2: tGNN INTER-HIVE COORDINATION (Network Intelligence)            │
│  Scope: All sites simultaneously    Cadence: Daily    Latency: minutes   │
│                                                                          │
│  Two-tier GNN processes the entire supply chain graph:                   │
│  S&OP GraphSAGE (weekly) → structural embeddings, criticality, risk     │
│  Execution tGNN (daily)  → priority allocations, exception forecasts    │
│  Output: tGNNSiteDirective per site (demand forecast, propagation        │
│          impact, allocation adjustments, inter-hive signals)             │
│  Implementation: planning_execution_gnn.py, allocation_service.py        │
│  Who: Fully automated; humans see via Dashboards UX primitive            │
├───────────────────────────────────────────────────────────────────────────┤
│  LAYER 1: INTRA-HIVE SIGNALS (Per-Site Reflexive Coordination)           │
│  Scope: Single site only    Cadence: Per-decision    Latency: <10ms      │
│                                                                          │
│  11 TRM agents coordinate via UrgencyVector + HiveSignalBus:            │
│  ATP detects shortage → PO expedites → SafetyStock adjusts              │
│  No cross-site visibility — only local state + tGNN directives           │
│  Implementation: site_agent.py, HiveSignalBus (proposed)                 │
│  Who: Fully automated; humans see via Worklist UX primitive              │
└───────────────────────────────────────────────────────────────────────────┘
```

### 16.2 The tGNN as Inter-Hive Connective Tissue

The tGNN is the primary mechanism for cross-site coordination. It operates at a different timescale than intra-hive signals and serves a fundamentally different purpose.

**Intra-hive signals** (Layer 1) answer: "What is happening at THIS site right now?"
**tGNN directives** (Layer 2) answer: "What is happening ACROSS THE NETWORK that this site should know about?"

#### How the tGNN Sees the Network

The tGNN processes the supply chain as a graph where:
- **Nodes** = sites (each with 16 input features — 8 transactional + 8 hive feedback)
- **Edges** = transportation lanes (material flow, with lead time and capacity attributes)
- **Edge direction** = upstream→downstream (supply flow) and downstream→upstream (order flow)

```
Supplier A ──────┐
                  ├──→ Factory C ──→ DC D ──→ Retailer F
Supplier B ──────┘              \
                                 └──→ DC E ──→ Retailer G

tGNN graph representation:
  Nodes: [A, B, C, D, E, F, G]
  Edges: [(A→C), (B→C), (C→D), (C→E), (D→F), (E→G)]
         + reverse edges for order flow
  Node features: [inventory, backlog, demand, pipeline, urgency_avg,
                   shortage_signals, allocation_util, fill_rate, ...]
```

#### What the tGNN Computes

**S&OP GraphSAGE** (weekly/monthly):
```
Input:  Node features + edge topology (static structure)
Output per site:
  structural_embedding[64]    — encodes network position and connectivity
  criticality_score           — how important is this site to overall network
  bottleneck_risk             — congestion/capacity constraint risk
  safety_stock_multiplier     — SS adjustment from network context
  resilience_score            — how well the network absorbs disruption at this site
  concentration_risk          — supplier/customer concentration vulnerability
```

**Execution tGNN** (daily):
```
Input:  Node features (daily transactional) + S&OP embeddings (cached)
        + HiveFeedbackFeatures from each site (Section 6.1)
Output per site:
  demand_forecast[4]          — 4-period demand forecast
  exception_probability[3]    — [stockout, overstock, normal]
  propagation_impact[4]       — if disruption hits, when downstream feels it
  order_recommendation        — suggested order quantity
  allocation_adjustments      — priority rebalance suggestions

Output as InterHiveSignals:
  UPSTREAM_DISRUPTION         — supplier/factory problems propagating downstream
  LATERAL_SURPLUS/SHORTAGE    — sister sites with excess/deficit
  DEMAND_WAVE                 — demand pattern propagating upstream
  CAPACITY_CONSTRAINT         — bottleneck forming at a production site
```

#### How tGNN Directives Reach Individual TRMs

The tGNN does not communicate directly with individual TRMs. It produces a per-site `tGNNSiteDirective` (Section 5.4), which the SiteAgent unpacks and injects into the signal bus:

```
tGNN daily run (processes all sites simultaneously)
    ↓
tGNNSiteDirective per site (cached in SiteAgent)
    ↓
SiteAgent unpacks directive into:
    ├── InterHiveSignals → injected into HiveSignalBus
    ├── allocation_adjustments → fed to AllocationService
    ├── safety_stock_multiplier → bounds for SafetyStockTRM
    ├── demand_forecast → input feature for ForecastAdjustmentTRM
    └── exception_probability → threshold for ATPExecutorTRM

Individual TRM heads read signals and features:
    ├── ATPExecutorTRM sees: allocation adjustment + exception probability
    ├── POCreationTRM sees: demand forecast + propagation impact
    ├── SafetyStockTRM sees: SS multiplier bounds + resilience score
    └── RebalancingTRM sees: LATERAL_SURPLUS/SHORTAGE inter-hive signals
```

**Key design principle**: TRMs never call across sites. They only see their local state + whatever the tGNN told them about the network. This is the CTDE principle — centralized training (tGNN sees everything), decentralized execution (each TRM sees only its site + directives).

### 16.3 Cross-Site Agent Communication Paths

There are exactly three ways agents at one site communicate with agents at another site:

#### Path 1: tGNN Passive Propagation (Daily, Automatic)

```
Site A's hive state (urgency, shortages, performance)
    ↓ (daily feature refresh)
HiveFeedbackFeatures aggregated
    ↓ (fed as tGNN input features)
Execution tGNN processes all sites simultaneously
    ↓ (spatial attention propagates information across graph edges)
Site B receives tGNNSiteDirective with:
    - InterHiveSignal: UPSTREAM_DISRUPTION from Site A
    - propagation_impact: [when Site B will feel it]
    ↓
Site B's TRMs respond locally (no acknowledgement to Site A)
```

**Speed**: Daily cadence (or CDC off-cadence trigger). Latency = tGNN inference time (~seconds) + feature collection.

**Direction**: Unidirectional. Site A does not know that Site B received its signal. This is sufficient for most coordination because the tGNN already computed the optimal response for Site B.

**Analogy**: Weather forecast. You do not negotiate with a weather system — you read the forecast and adjust your plans accordingly.

#### Path 2: AAP Authorization Request (On-Demand, Negotiated)

```
Site A's RebalancingTRM needs inventory from Site B
    ↓
RebalancingTRM determines: transfer exceeds unilateral authority
    (e.g., quantity > 500 units, or Site B is not a pre-approved source)
    ↓
SiteAgent escalates to AAP:
    AuthorizationRequest(
        originator="site_A.rebalancing_trm",
        target="site_B.rebalancing_trm",
        action="TRANSFER_500_UNITS_SKU_X",
        scorecard={
            "site_A_service_improvement": +12%,
            "site_B_inventory_impact": -8%,
            "network_net_benefit": +$15K,
            "transport_cost": -$2K
        }
    )
    ↓
Site B's SiteAgent evaluates:
    - Do I have surplus? (local inventory check)
    - What's the impact on my performance? (scorecard)
    - Is there contention? (other sites requesting same inventory)
    ↓
AuthorizationResponse: APPROVED / REJECTED (with reason)
    ↓
If approved: Site A's TOExecutionTRM releases transfer order
             Site B's RebalancingTRM emits REBALANCE_OUTBOUND signal
```

**Speed**: Seconds to minutes (agent-to-agent). Hours if escalated to human.

**Direction**: Bidirectional. Both sites participate in the decision. The AAP scorecard ensures both sites understand the network-level impact.

**When used**: Only when a TRM decision crosses authority boundaries — transferring between sites, changing shared resource allocations, requesting priority override from another function. Most routine decisions (>90%) stay within Layer 1 (intra-hive) and never trigger cross-site communication.

#### Path 3: ConditionMonitor SupplyRequest (Threshold-Based, Semi-Automated)

```
Site A's ConditionMonitorService detects:
    ATP shortfall persisting for 24 hours
    service_level < target - 5%
    ↓
ConditionMonitor checks can_request_supply:
    - Are there sibling sites with surplus? (from tGNN LATERAL_SURPLUS signals)
    - Is the shortfall above minimum threshold?
    ↓
SupplyRequest(
    requesting_entity="site_A",
    requested_entity="site_B",
    product_id="SKU-X",
    quantity_needed=500,
    needed_by=tomorrow,
    priority=2,
    context={"signal_type": "ATP_SHORTFALL", "duration_hours": 24}
)
    ↓
Site B's RebalancingTRM evaluates (same as AAP Path 2)
```

**Speed**: Hours (condition must persist past threshold). Faster than waiting for next tGNN daily run.

**Direction**: Request-response between specific sites. The ConditionMonitor identifies the best partner site using tGNN data.

**Relationship to Path 2**: This is a specific, automated trigger for AAP authorization. The ConditionMonitor generates the AuthorizationRequest automatically when conditions breach thresholds — no manual escalation needed.

### 16.4 What Each Layer Cannot See

Understanding the boundaries is as important as understanding the connections:

| Layer | Can See | Cannot See |
|---|---|---|
| **Intra-Hive (Layer 1)** | Own site inventory, backlog, demand, all 11 TRM urgencies and signals | Other sites' inventory, other sites' TRM decisions, network topology |
| **tGNN (Layer 2)** | All sites' aggregate features (daily snapshot), full network graph | Individual TRM decisions, real-time urgency changes within a site |
| **AAP (Layer 3)** | Both sites' scorecards for a specific proposed action | Global optimum (only evaluates pairwise, not network-wide) |
| **S&OP Board (Layer 4)** | Enterprise-wide KPIs, policy parameter impacts | Execution-level details (individual orders, per-TRM decisions) |

**Critical gap the tGNN bridges**: Intra-hive signals are invisible outside the site. The tGNN observes the *effects* of intra-hive coordination (via HiveFeedbackFeatures: urgency averages, shortage signal density, override rate) without seeing the signals themselves. This is by design — the tGNN learns network-level patterns from aggregated site behavior, not from individual TRM decisions.

### 16.5 Multi-Site Physical Deployment Topology

In production, the coordination stack maps to concrete deployment infrastructure:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CENTRAL SERVICES                                  │
│                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────┐    │
│  │ S&OP GraphSAGE   │  │ Execution tGNN   │  │ S&OP Consensus     │    │
│  │ (weekly batch)    │  │ (daily batch)    │  │ Board              │    │
│  │                   │  │                   │  │ (PolicyEnvelope)   │    │
│  │ Input: all site   │  │ Input: all site   │  │ Input: agent       │    │
│  │ structural data   │  │ transactional +   │  │ proposals +        │    │
│  │                   │  │ hive feedback     │  │ KPI actuals        │    │
│  │ Output: embed-    │  │ Output:           │  │                    │    │
│  │ dings, criticality│  │ directives,       │  │ Output: policy     │    │
│  │ risk scores       │  │ allocations,      │  │ parameters θ       │    │
│  │                   │  │ inter-hive signals│  │                    │    │
│  └────────┬─────────┘  └────────┬─────────┘  └─────────┬──────────┘    │
│           │ cached weekly        │ cached daily          │ cached weekly │
│           └──────────────────────┼──────────────────────┘               │
│                                  │                                       │
│                    ┌─────────────┴─────────────┐                        │
│                    │ Directive Distribution     │                        │
│                    │ Service                    │                        │
│                    │ (pushes tGNNSiteDirective  │                        │
│                    │  to each site's SiteAgent) │                        │
│                    └───────────┬────────────────┘                        │
│                                │                                         │
└────────────────────────────────┼─────────────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ SITE A: Factory  │ │ SITE B: DC       │ │ SITE C: Retail   │
│                  │ │                  │ │                  │
│ ┌──────────────┐ │ │ ┌──────────────┐ │ │ ┌──────────────┐ │
│ │ SiteAgent    │ │ │ │ SiteAgent    │ │ │ │ SiteAgent    │ │
│ │              │ │ │ │              │ │ │ │              │ │
│ │ 11 TRM Heads │ │ │ │ 11 TRM Heads │ │ │ │ 11 TRM Heads │ │
│ │ HiveSignalBus│ │ │ │ HiveSignalBus│ │ │ │ HiveSignalBus│ │
│ │ UrgencyVector│ │ │ │ UrgencyVector│ │ │ │ UrgencyVector│ │
│ │              │ │ │ │              │ │ │ │              │ │
│ │ Deterministic│ │ │ │ Deterministic│ │ │ │ Deterministic│ │
│ │ Engines:     │ │ │ │ Engines:     │ │ │ │ Engines:     │ │
│ │ MRP, AATP,   │ │ │ │ MRP, AATP,   │ │ │ │ MRP, AATP,   │ │
│ │ SS, Capacity │ │ │ │ SS, Capacity │ │ │ │ SS, Capacity │ │
│ │              │ │ │ │              │ │ │ │              │ │
│ │ CDC Monitor  │ │ │ │ CDC Monitor  │ │ │ │ CDC Monitor  │ │
│ │ Outcome      │ │ │ │ Outcome      │ │ │ │ Outcome      │ │
│ │ Collector    │ │ │ │ Collector    │ │ │ │ Collector    │ │
│ └──────────────┘ │ │ └──────────────┘ │ │ └──────────────┘ │
│                  │ │                  │ │                  │
│ ← tGNNDirective │ │ ← tGNNDirective │ │ ← tGNNDirective │
│ → FeedbackFeat  │ │ → FeedbackFeat  │ │ → FeedbackFeat  │
│ ↔ AAP Requests  │ │ ↔ AAP Requests  │ │ ↔ AAP Requests  │
└──────────────────┘ └──────────────────┘ └──────────────────┘
```

**Deployment options**:
- **Centralized** (current): All SiteAgents run in the same backend process. Cross-site communication is in-process function calls. tGNN and SiteAgents share the same database.
- **Distributed** (future): Each site runs its own SiteAgent process (or container). tGNN runs centrally. Directives distributed via message queue (Kafka/RabbitMQ). AAP requests via REST API between sites.
- **Edge** (PicoClaw): Ultra-lightweight SiteAgents run on edge hardware at physical sites. tGNN runs in cloud. Directives pushed via MQTT. CDC alerts via Telegram/Slack.

### 16.6 Digital Twin Training for Multi-Site Coordination

The digital twin pipeline (Section 15) generates training data for Layers 1 and 2 simultaneously. Here is how multi-site coordination is trained:

#### Training the tGNN (Layer 2)

The tGNN learns from full-network simulation traces:

```
1. Generate diverse network topologies (SyntheticDataGenerator):
   ├── 4-site Beer Game (linear)
   ├── 10-site retailer (divergent)
   ├── 30-site manufacturer (convergent + divergent)
   └── 50-site mixed (realistic enterprise)

2. Run SimPy Monte Carlo on each topology:
   ├── 2500 runs × 64 periods = 160K state snapshots per topology
   ├── Each state snapshot = all sites' features simultaneously
   ├── Stochastic disruptions create cross-site propagation patterns
   └── Record: which site was disrupted → how all other sites were affected

3. Build graph tensors:
   ├── X: [batch, T=52, N=sites, F=16] node features
   ├── A: [2, edges] adjacency (supply + order flow)
   ├── Y: [batch, N, H=4] action targets (orders, allocations)
   └── Feed to SupplyChainTemporalGNN for supervised training

4. Validate:
   ├── tGNN predicts Site B exception_probability[stockout]
   ├── Compare to actual stockout in simulation
   ├── Target: 85-92% prediction accuracy
   └── Generalization: test on held-out topologies
```

**Key insight for multi-site training**: The tGNN's spatial attention mechanism (GATv2) must learn that disruption at an upstream factory propagates faster to nearby DCs than to distant ones, and that convergent topologies (many suppliers → one factory) are more resilient than serial ones. This can only be learned from multi-topology training data.

#### Training Hive-tGNN Integration (Layer 1+2)

Once both the tGNN and individual TRM hives are trained, they must learn to work together:

```
End-to-end training loop:

For each simulation episode:
    1. tGNN daily run → produces tGNNSiteDirective per site
    2. Each site's SiteAgent unpacks directive into signals
    3. Each site's 11 TRMs execute with directive context
    4. Decisions produce outcomes (fill_rate, cost, etc.)
    5. Outcomes become next day's HiveFeedbackFeatures
    6. HiveFeedbackFeatures feed into next tGNN run
    7. Loop: tGNN → Hives → Feedback → tGNN

Trained jointly:
    - tGNN loss: prediction accuracy of site-level outcomes
    - Hive loss: per-TRM reward + hive-level shared critic
    - Integration loss: did the tGNN directive improve hive performance
      vs the hive running without tGNN context?
```

This end-to-end loop can only run in the digital twin — it requires full-network simulation with all hives active simultaneously.

#### Training AAP Negotiation (Layer 3)

AAP authorization is a higher-level protocol that does not require neural training — it uses rule-based evaluation with scorecard comparison. However, the digital twin can calibrate AAP parameters:

```
For each cross-site scenario (supplier failure, demand spike, etc.):
    1. Run simulation WITHOUT AAP → observe cascade failure cost
    2. Run simulation WITH AAP (different net_benefit thresholds) →
       observe cost with cross-site coordination
    3. Find optimal net_benefit_threshold that maximizes network
       performance while minimizing AAP negotiation overhead
    4. Store as AAP policy parameter in PolicyEnvelope
```

The digital twin's Monte Carlo capability is essential here — it quantifies the **value of cross-site coordination** by comparing network performance with and without AAP authorization.

### 16.7 Scaling Properties

| Network Size | Sites | TRM Agents | tGNN Complexity | AAP Requests/Day | Training Data |
|---|---|---|---|---|---|
| **Beer Game** (baseline) | 4 | 44 | O(4²)=16 edges | 0-2 | 2M records |
| **Mid-Market** (target) | 10-50 | 110-550 | O(N×E) ~500 edges | 5-20 | 10-50M records |
| **Enterprise** (future) | 50-200 | 550-2200 | O(N×E) ~5K edges | 20-100 | 50-200M records |

**What scales linearly**: Number of SiteAgents (each independent), intra-hive signal processing (per-site), CDC monitoring (per-site).

**What scales with graph size**: tGNN inference (edges), S&OP GraphSAGE (node embeddings). GraphSAGE was chosen specifically because it samples neighborhoods rather than processing all nodes — O(edges) not O(N²).

**What does not scale**: AAP negotiation (pairwise, on-demand). Most cross-site decisions are handled by tGNN passive propagation (Path 1), keeping AAP requests to <1% of total decisions.

### 16.8 Summary: How Site A Talks to Site B

A concrete summary of all communication channels between two sites:

| Channel | Mechanism | Latency | Direction | What Flows |
|---|---|---|---|---|
| **tGNN passive** | Site A's features → tGNN graph attention → Site B's directive | Daily | A→tGNN→B (indirect) | Exception forecasts, propagation impact, allocation adjustments |
| **InterHiveSignal** | tGNN detects A's disruption → generates signal → delivered in B's directive | Daily | A→tGNN→B (indirect) | UPSTREAM_DISRUPTION, LATERAL_SURPLUS/SHORTAGE, DEMAND_WAVE |
| **AAP authorization** | A's TRM sends AuthorizationRequest → B's SiteAgent evaluates | Seconds-minutes | A↔B (direct) | Transfer requests, priority overrides, capacity sharing |
| **ConditionMonitor** | A's persistent shortfall → automatic SupplyRequest to B | Hours | A→B (direct) | Inventory relief requests |
| **CDC off-cadence tGNN** | A's CDC trigger → forces early tGNN rerun → new directives for all sites | Minutes-hours | A→tGNN→all (broadcast) | Updated forecasts reflecting A's condition |
| **S&OP policy** | Consensus Board updates safety_stock_multiplier for A and B | Weekly | Board→A, Board→B | Policy parameter changes |

**What does NOT exist (by design)**:
- No direct TRM-to-TRM calls across sites (would create coupling and latency)
- No shared signal bus across sites (signals are local to each hive)
- No shared UrgencyVector across sites (urgency is per-site only)
- No real-time streaming between sites (tGNN operates on daily snapshots)

The tGNN is the connective tissue. Everything a site needs to know about the network arrives through its `tGNNSiteDirective`. Everything the network needs to know about a site is captured in its `HiveFeedbackFeatures`. These two data structures are the complete interface contract between per-site execution (Layer 1) and network intelligence (Layer 2).

---

## File Reference

| Component | File |
|---|---|
| SiteAgent orchestrator | `backend/app/services/powell/site_agent.py` |
| Shared encoder + heads | `backend/app/services/powell/site_agent_model.py` |
| tGNN models | `backend/app/models/gnn/planning_execution_gnn.py` |
| Allocation service | `backend/app/services/powell/allocation_service.py` |
| CDC monitor | `backend/app/services/powell/cdc_monitor.py` |
| Condition monitor (cross-site) | `backend/app/services/condition_monitor_service.py` |
| Decision integration | `backend/app/services/powell/integration/decision_integration.py` |
| Integration facade | `backend/app/services/powell/integration_service.py` |
| Context explainability | `backend/app/services/agent_context_explainer.py` |
| Agentic Authorization Protocol | `docs/AGENTIC_AUTHORIZATION_PROTOCOL.md` |
| Authorization models (proposed) | `AgentAuthority`, `AuthorizationThread`, `AuthorizationMessage` |
| Scenario models (proposed) | `PlanningScenario` with tree branching, `ScenarioDecisionRecord` for knowledge capture |
| Scenario tree service (proposed) | `ScenarioTreeService` — create, navigate, promote, prune, merge |
| Scenario decisions table (proposed) | `powell_scenario_decisions` — decision records with scorecards, outcomes, learning signals |
| All 11 TRM services | `backend/app/services/powell/*.py` |
