# Vertical Urgency Propagation

## Overview

GNN decisions in the Decision Stream carry **propagated urgency** — urgency scores computed from lower-level execution signals that escalated upward because they couldn't be resolved locally. This replaces naive model-output-based urgency with urgency that reflects real operational pain.

**Principle**: A GNN decision is urgent NOT because the model says so, but because execution-level agents have been struggling with a problem that requires higher-level coordination to solve.

---

## The Problem GNN Urgency Solves

Without vertical propagation, GNN urgency would be:
- **Strategic (S&OP)**: Bottleneck risk score from GraphSAGE — a static network property, rarely urgent
- **Tactical (tGNN)**: Stockout probability — useful but misses the "why"
- **Result**: Most GNN decisions would appear low-urgency and be ignored

With vertical propagation:
- GNN urgency is **amplified by execution-level failure patterns**
- A tactical rebalancing decision becomes HIGH urgency because the MO agent at Site A has been capacity-stressed for 3 weeks AND the local Site tGNN couldn't add a shift (guardrail blocked)
- The human sees not just "rebalance inventory" but WHY: traced back to the specific TRM observations that created the need

---

## Architecture: Signal Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 1 — TRM Execution (<10ms)                                     │
│                                                                     │
│   MO Agent: OEE 95% for 3 weeks → CAPACITY_STRESS (urgency 0.85)   │
│   ATP Agent: Fill rate dropped 98%→91% → FILL_RATE_DEGRADATION      │
│   Buffer Agent: Safety stock depleted → BUFFER_BREACH (urgency 0.78)│
│                                                                     │
│   These are NOT standalone decisions in the stream — they are       │
│   execution-level observations that feed upward.                    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HiveSignalBus + UrgencyVector
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 1.5 — Site tGNN (hourly)                                      │
│                                                                     │
│   Receives: CAPACITY_STRESS + FILL_RATE_DEGRADATION                 │
│   Evaluates: Add extra shift at Site A?                             │
│   Result: BLOCKED — guardrail says min shift extension = 4 weeks    │
│                                                                     │
│   Emits: CAPACITY_CONSTRAINED_ESCALATION upward to Layer 2          │
│   with: source_signals, blocked_by, revenue_at_risk                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ InterHiveSignal
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Layer 2 — Network tGNN (daily)                                      │
│                                                                     │
│   Receives: Escalation from Site A                                  │
│   Evaluates: Rebalance inventory from Site B → Site A               │
│                                                                     │
│   Creates: GNNDirectiveReview with:                                 │
│     propagated_urgency = 0.85 (from MO agent's CAPACITY_STRESS)     │
│     source_signals = [{trm_type: "mo_execution",                    │
│       observation: "OEE 95% for 21 days", urgency: 0.85}, ...]     │
│     local_resolution_blocked_by = "Guardrail: min shift = 4 weeks"  │
│     revenue_at_risk = $180,000/week                                 │
│                                                                     │
│   → This appears in Decision Stream as TACTICAL / HIGH urgency      │
│     with full escalation context visible to MPS Manager             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Decision Level Field

Every decision in the Decision Stream now carries a `decision_level`:

| Level | Agent Layer | Scope | Cadence | Who Sees It |
|-------|------------|-------|---------|-------------|
| **strategic** | S&OP GraphSAGE | Network-wide policy parameters | Weekly | SC VP, Executive, S&OP Director |
| **tactical** | Execution tGNN | Multi-site allocation directives | Daily | SC VP, Executive, S&OP Director, MPS Manager, Allocation Manager |
| **execution** | TRM agents (11 types) | Role at site | Real-time | All roles (filtered by TRM type relevance) |

**Note**: Site tGNN (Layer 1.5, hourly) does NOT produce standalone decision cards. Its outputs modulate TRM urgency vectors (`urgency_at_time` on TRM decisions) and trigger escalations. This is by design — Site tGNN is coordination infrastructure, not a decision-maker visible to humans.

---

## GNN Urgency Computation

### Priority 1: Propagated Urgency (from lower-level signals)

```python
propagated_urgency = weighted_max(
    source_signal_urgencies,
    weights=[1.0 if local_resolution_attempted else 0.5]
)
```

When a GNN directive has `propagated_urgency > 0`, this takes absolute priority over model-derived urgency. It means execution-level agents observed a real problem that escalated because it couldn't be resolved locally.

**Amplification rule**: If `local_resolution_attempted = True` AND `local_resolution_blocked_by` is non-null, the propagated urgency is amplified by 1.2x (capped at 1.0). The reasoning: a problem that was identified, a solution was proposed, but a guardrail blocked it — this is MORE urgent than a problem that was simply observed, because the system has already tried and failed to self-correct.

### Priority 2: Model-Derived Urgency (fallback)

When no escalation context exists (e.g., periodic S&OP parameter refresh):
- **Strategic**: `max(bottleneck_risk, concentration_risk)` — how stressed is the network?
- **Tactical**: `stockout_probability` from exception vector — what's the demand risk?
- **Allocation**: Fixed 0.5 (routine refresh unless escalated)

---

## GNN Likelihood Computation

GNN likelihood = `model_confidence` from the GNN model output (0-1).

For S&OP GraphSAGE: Based on attention weight convergence — how consistent are the node embeddings?

For Tactical tGNNs: Based on prediction confidence — how certain is the model about supply/inventory/capacity exception forecasts? (Demand forecasts are produced by the Forecast Baseline + Forecast Adjustment TRMs, not by tGNNs; tGNNs receive demand as an input feature.)

**Key difference from TRM likelihood**: TRM confidence comes from CDT risk bounds (calibrated from historical decision-outcome pairs). GNN confidence is not yet CDT-calibrated — this is future work. For now, GNN confidence is the raw model output, which tends to be lower (more uncertain) than calibrated TRM confidence.

---

## Database Schema: New Columns on `gnn_directive_reviews`

| Column | Type | Description |
|--------|------|-------------|
| `decision_level` | String(20) | "strategic" / "tactical" / "operational" |
| `propagated_urgency` | Float | 0-1 urgency score propagated from lower-level signals |
| `escalation_id` | FK → `powell_escalation_log` | Link to the escalation event that triggered this directive |
| `source_signals` | JSON array | Lower-level signals that fed into this decision |
| `local_resolution_attempted` | Boolean | Whether a lower layer tried to resolve locally |
| `local_resolution_blocked_by` | String(200) | Why local resolution failed (guardrail, capacity, authority) |
| `revenue_at_risk` | Float | $ revenue at risk if not acted on |
| `cost_of_delay_per_day` | Float | $/day incremental cost of inaction |

### `source_signals` JSON Schema

```json
[
  {
    "trm_type": "mo_execution",
    "signal_type": "CAPACITY_STRESS",
    "site_key": "1710",
    "urgency": 0.85,
    "observation": "OEE 95% sustained for 21 days",
    "duration_hours": 504
  },
  {
    "trm_type": "atp_executor",
    "signal_type": "FILL_RATE_DEGRADATION",
    "site_key": "1710",
    "urgency": 0.72,
    "observation": "Fill rate dropped from 98% to 91% over 7 days",
    "duration_hours": 168
  }
]
```

---

## Decision Stream Rendering

When a GNN decision appears in the Decision Stream, the frontend shows:

```
┌──────────────────────────────────────────────────────────────────┐
│ TACTICAL  │  tGNN Directive  │  @ Plant 1 US                     │
│                                                                  │
│ Urgency: HIGH (0.85)  │  Likelihood: POSSIBLE (0.52)            │
│                                                                  │
│ Recommended: Transfer 47 units of Battery 9V from 1720 to 1710  │
│                                                                  │
│ ╔══════════════════════════════════════════════════════════════╗  │
│ ║ Escalated from:                                             ║  │
│ ║   • mo_execution: OEE 95% sustained 21 days (urgency 85%)  ║  │
│ ║   • atp_executor: Fill rate 98%→91% over 7 days (72%)      ║  │
│ ║ Local resolution blocked: Guardrail — min shift = 4 weeks   ║  │
│ ║ Revenue at risk: $180,000/week                               ║  │
│ ╚══════════════════════════════════════════════════════════════╝  │
│                                                                  │
│  [Inspect ▾]  [Override]                                    →   │
└──────────────────────────────────────────────────────────────────┘
```

The escalation context box only appears when `source_signals` is non-empty. For routine GNN decisions (periodic S&OP refresh), the card shows normally without the escalation section.

---

## Level-Based Role Filtering

**Principle**: You see decisions at YOUR level + escalations FROM the level below. You don't see routine noise two levels down.

### Default Views

| Role | Default Levels | Escalation From | What They See |
|------|:---:|:---:|------|
| **SC VP / Executive** | Governance + Strategic | Tactical escalations | Directives they issued. S&OP policy changes. Tactical issues that escalated to strategic. |
| **S&OP Director** | Strategic | Tactical escalations | S&OP policy decisions. tGNN issues that couldn't be resolved at tactical level. |
| **MPS Manager** | Tactical | Execution escalations | tGNN allocations. TRM issues that escalated (e.g., capacity stress). |
| **Allocation Manager** | Tactical | Execution escalations | Allocations, ATP, rebalancing. Execution issues affecting allocations. |
| **TRM Analyst** | Execution | None | Their TRM type only at their site. |
| **Tenant Admin** | All levels | N/A | Everything, filterable by level tabs. |

### Escalation Passthrough

When a role has `escalation_from`, decisions at that lower level appear ONLY if they have:
- `source_signals` populated (TRM observations that escalated)
- `escalation_id` linking to a `powell_escalation_log` entry
- `urgency_score >= 0.75` (high urgency implies escalation-worthy)

Example: S&OP Director's default view = strategic decisions. But if a tactical tGNN directive has `source_signals` (meaning TRM agents observed a problem that escalated through Site tGNN → Network tGNN), it passes through to the S&OP Director's stream.

### Level Drill-Down

The API supports `?level=execution` to override the default and show a specific level. This is for when a VP wants to investigate what's happening at execution level — they explicitly drill down.

### Frontend: Level Tabs

The digest response includes `level_counts`:
```json
{
  "level_counts": {"governance": 3, "strategic": 5, "tactical": 12, "execution": 47},
  "active_level": null
}
```

The frontend renders tabs:
```
[Governance 3]  [Strategic 5]  [Tactical 12]  [Execution 47]
```

Default tab depends on role. Clicking a tab passes `?level=<tab>` to the API.

## Governance Decisions

A fourth level for human-initiated policy decisions:

| Source | Decision Type | Example |
|--------|--------------|---------|
| `user_directives` (status=APPLIED) | `directive` | "Increase service level for frozen to 98%" |
| `site_agent_configs` changes | `guardrail_change` | "Min shift extension changed 2→4 weeks" |
| `policy_envelope_overrides` | `policy_envelope_change` | "OTIF floor raised to 95% for Q2" |

Governance decisions have:
- **Urgency**: Medium (informational — already enacted)
- **Likelihood**: 1.0 (human instruction, not a prediction)
- **Visibility**: SC VP, Executive, S&OP Director only

They appear in the stream to provide context: "this is WHY the agents are behaving differently now."

---

## Implementation Files

| File | What Changed |
|------|-------------|
| `backend/app/models/gnn_directive_review.py` | Added 8 vertical urgency columns |
| `backend/app/services/decision_stream_service.py` | GNN directive collection, DECISION_LEVEL map, propagated urgency logic, enriched reasoning |
| `backend/migrations/versions/20260319_gnn_vertical_urgency.py` | Schema migration |
| `docs/internal/VERTICAL_URGENCY_PROPAGATION.md` | This document |

---

## Relationship to Existing Architecture

- **Escalation Arbiter** (`escalation_arbiter.py`): Detects persistent TRM anomalies and logs to `powell_escalation_log`. The `escalation_id` FK on `gnn_directive_reviews` links the GNN action back to the escalation event.
- **HiveSignalBus**: TRM-to-TRM signals within a site. Some signals propagate to Site tGNN via `InterHiveSignal`, which may escalate further to Network tGNN.
- **Kahneman System 1/2**: TRM = System 1 (fast, automatic). When System 1 fails persistently, System 2 (GNN) activates. The propagated urgency captures the "System 2 activation energy."
- **Boyd OODA**: Inner OODA loop (TRM) anomaly triggers outer OODA loop (GNN). The source_signals provide the "Orient" phase context for the outer loop.
