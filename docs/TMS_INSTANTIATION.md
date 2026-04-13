# TMS as an Autonomy Product

**Audience:** Engineers and architects working on Autonomy TMS.
**Prerequisite:** [Autonomy-Core/docs/PLATFORM_OVERVIEW.md](../../Autonomy-Core/docs/PLATFORM_OVERVIEW.md) and [BUSINESS_FUNCTION_MODELING.md](../../Autonomy-Core/docs/BUSINESS_FUNCTION_MODELING.md).
**Scope:** How TMS instantiates the Autonomy platform for transportation management. Everything product-agnostic is in Core; this doc covers the six product-level choices for TMS.

---

## 1. Relationship to Core

Autonomy TMS is a **sibling product** to Autonomy SCP, not a fork. Both consume the same platform (agent stack, AIIO, conformal, digital twin, governance, training lifecycle, integration pattern, Azirella UX) via:

- `@azirella-ltd/autonomy-frontend` — shared React components, decision-stream shell, navigation
- `@azirella-ltd/autonomy-data-model` (in progress) — canonical data model, AIIO governance types, tenant/RBAC
- `@azirella-ltd/powell-core` (planned) — TRM base classes, hive signals, conformal framework

TMS has its own database (`tms-db`), backend, and frontend app. Cross-app coordination with SCP happens via MCP.

---

## 2. The six product choices (TMS)

### 2.1 Canonical data model

**Base:** AWS Supply Chain Data Model subset relevant to transportation (sites, transportation_lanes, shipments). Plus transportation-specific extensions:

- Lane graph (origin × destination × mode × carrier)
- Shipment lifecycle (tender → accepted → picked-up → in-transit → delivered)
- Carrier entities (scorecards, rate tables, capacity commitments)
- EDI / API integration entities

See [TMS_DATA_MODEL.md](TMS_DATA_MODEL.md) for the full schema.

### 2.2 Agent specializations

**L1 — TRMs (TMS-specific set).** The canonical list is still converging. Expected:

- **RateCommit TRM** — commit / decline a carrier rate offer.
- **Dispatch TRM** — assign a shipment to a carrier within a tender window.
- **Consolidation TRM** — combine shipments onto a single load where economic.
- **ModeSelect TRM** — truckload vs LTL vs parcel vs intermodal per shipment.
- **Routing TRM** — choose lane path within the lane graph.
- **Exception TRM** — in-transit disruption response (delay, reroute, substitute).

**L2 — Node coordinator.** A node in TMS is a **lane hub** (origin or destination with material shipment volume). Same GATv2+GRU shape as SCP.

**L3 — Tactical domain models.** Probably two or three (final TBD):
- **Demand** (shipment volume forecast by lane)
- **Capacity** (carrier capacity by lane × mode × week)
- **Rate** (expected rate distribution by lane × mode)

**L4 — Strategic.** Network-wide policy: preferred carriers, mode mix targets, lane-level service-cost trade-offs.

**AAP.** Inter-hub coordination for load consolidation across proximate origins; cross-product AAP with SCP for inbound/outbound alignment.

### 2.3 Decision classes

Groups for the governance envelope:

- Rate commitments (by magnitude tier)
- Dispatch decisions (by carrier / lane / urgency)
- Consolidation bundles
- Mode changes
- Exception responses
- Carrier scorecard-driven actions

### 2.4 Integration adapters

Primary systems of record differ from SCP:

- **TMS source systems:** Oracle OTM, SAP TM, MercuryGate, BluJay, homegrown.
- **Carrier APIs:** project44 (visibility), FourKites, direct EDI 990/214/990.
- **Rate repositories:** SMC3, DAT, broker marketplaces.

Same three-mode pattern (bulk extract / CDC / MCP write-back) per [INTEGRATION_MODEL.md](../../Autonomy-Core/docs/INTEGRATION_MODEL.md). TMS-specific details in [TMS_ERP_INTEGRATION.md](TMS_ERP_INTEGRATION.md).

### 2.5 Role taxonomy

Mapped onto the platform's five tiers:

| Tier | TMS roles | Landing |
|---|---|---|
| Strategic | `TRANSPORTATION_VP`, `LOGISTICS_DIRECTOR` | Strategy briefing |
| Tactical | `NETWORK_PLANNER`, `LANE_STRATEGIST` | Tactical worklist |
| Operational / domain | `DISPATCHER`, `ROUTING_ANALYST`, `MODE_SPECIALIST` | Operations hub with tabs |
| Execution | `TENDER_ANALYST`, `CARRIER_MANAGER` | Per-function worklist |
| Specialist | `RATE_ANALYST`, `EXCEPTION_HANDLER` | Per-TRM worklist |
| Walkthrough | `DEMO_ALL` | Full Decision Stream |

### 2.6 Demo scenarios

TBD. Initial candidates:
- A retailer inbound lane network with SAP TM source.
- A manufacturer outbound distribution lane network with project44 visibility.
- A 3PL multi-customer consolidated lane network.

---

## 3. What TMS inherits from Core unchanged

Per Core platform docs — do not re-explain these in TMS docs:

- The AIIO model and the four-step governance pipeline → [AIIO_MODEL.md](../../Autonomy-Core/docs/AIIO_MODEL.md), [GUARDRAILS_AND_GOVERNANCE.md](../../Autonomy-Core/docs/GUARDRAILS_AND_GOVERNANCE.md)
- Five-layer coordination, AAP, Context Broker, upward feedback → [AGENT_ARCHITECTURE.md](../../Autonomy-Core/docs/AGENT_ARCHITECTURE.md), [CONTEXT_BROKER.md](../../Autonomy-Core/docs/CONTEXT_BROKER.md)
- Decision lifecycle (correlation_id, escalation, override classifier) → [DECISION_LIFECYCLE.md](../../Autonomy-Core/docs/DECISION_LIFECYCLE.md)
- Three stores (decision history, Temporal Knowledge, EK) → [KNOWLEDGE_AND_MEMORY.md](../../Autonomy-Core/docs/KNOWLEDGE_AND_MEMORY.md)
- Scenario engine, digital twin, conformal prediction → [SCENARIO_ENGINE.md](../../Autonomy-Core/docs/SCENARIO_ENGINE.md), [DIGITAL_TWIN.md](../../Autonomy-Core/docs/DIGITAL_TWIN.md), [CONFORMAL_PREDICTION.md](../../Autonomy-Core/docs/CONFORMAL_PREDICTION.md)
- Training lifecycle (pre-training / provisioning / continuous / periodic) → [TRAINING_LIFECYCLE.md](../../Autonomy-Core/docs/TRAINING_LIFECYCLE.md)
- User interaction model (tabbed shell, Decision Stream, Azirella) → [USER_INTERACTION_MODEL.md](../../Autonomy-Core/docs/USER_INTERACTION_MODEL.md)
- Claude Skills envelope → [CLAUDE_SKILLS_ENVELOPE.md](../../Autonomy-Core/docs/CLAUDE_SKILLS_ENVELOPE.md)

TMS docs that re-explain any of these are candidates for deletion.

---

## 4. What's unique about TMS (vs SCP)

These differences drive TMS-specific code and docs:

- **Shorter decision horizons.** Most TMS decisions are hours to days, not weeks. L4 is still weekly; L3 is more like 2–3× per week.
- **Carrier as first-class external party.** A lot of integration surface is carrier-facing, not ERP-facing.
- **EDI as a transport-of-truth alongside APIs.** 214, 990, 204, 210, 820 have to be read, written, and reconciled.
- **Real-time visibility dominates L2 input.** Telematics / position updates stream continuously; SCP's Context Broker pattern holds but the delivery rate is much higher.
- **Rate markets are a live exogenous signal.** The Rate domain model at L3 is closer to a forecasting surface on a financial-like market than to demand forecasting in SCP.

---

## 5. Current state of the TMS repo

The TMS repo originated as an SCP fork. Unwinding is in progress. Key TMS-specific docs already landed:

- [CLAUDE_REFERENCE.md](CLAUDE_REFERENCE.md) — TMS project rules (still SCP-derived in places; needs editing as Core docs mature).
- [SHARED_VS_TMS_BOUNDARIES.md](SHARED_VS_TMS_BOUNDARIES.md) — what's in Core vs TMS.
- [TMS_DATA_MODEL.md](TMS_DATA_MODEL.md) — canonical data model extensions for transportation.
- [TMS_ERP_INTEGRATION.md](TMS_ERP_INTEGRATION.md) — TMS-specific integration adapters.
- [TMS_P44_DATA_MODEL_COMPARISON.md](TMS_P44_DATA_MODEL_COMPARISON.md) — project44 integration reference.
- `SAP-S4HANA-FORK.md`, `ODOO-FORK.md`, `D365-FORK.md` — ERP integration fork notes.

32 SCP-copy docs in `docs/internal/` were deleted during the Core consolidation (they duplicated Core platform content). Four (`TRM_AGENTS_EXPLAINED.md`, `GNN_DECISION_ARCHITECTURE.md`, `AGENT_HIERARCHY_DIAGRAMS.md`, `architecture/GENERIC_TRM_PRETRAINING.md`) had TMS-specific content and were retained with pointer headers.

---

## 6. Open TMS authoring tasks

- Finalize the TRM set at L1 and commit to names.
- Finalize the domain-model decomposition at L3.
- Write `TMS_DEMO_SCENARIOS.md` once the first demo tenant is specified.
- Update CLAUDE_REFERENCE.md to match TMS realities, not SCP-derived defaults.
- Write TMS-specific override `reason_code` taxonomy.
- Write TMS-specific impact scoring functions per decision class.
