# CLAUDE_REFERENCE.md

Detailed architecture, workflows, and reference material extracted from CLAUDE.md.
Claude Code reads this file on-demand, not on every message — keeping CLAUDE.md lean.

> **Fork Relationship**: This is the TMS-specific version. The SC Planning version lives in the upstream Autonomy repo. Shared infrastructure sections (Auth, Conformal, Decision Stream, Causal AI, Docker) are synced from upstream. TMS-specific sections (agents, data model, integrations, planning) are unique to this repo.

---

## Project Overview — Four Pillars

**Autonomy TMS — Decision Intelligence for Transportation Management** - Enterprise-grade freight transportation planning and execution built on four pillars. Extends the AWS Supply Chain data model foundation with transportation-specific entities.

### Core: Transportation Data Model

**Primary Focus**: Freight transportation management — shipment lifecycle, carrier management, load optimization, dock scheduling, and real-time visibility.

**Key Capabilities**:
- **Shipment Management**: Full lifecycle from booking through POD (20 entities, 14 enums)
- **Carrier Management**: Carrier onboarding, scorecards, lane coverage, contract management
- **Load Optimization**: Consolidation, multi-stop routing, weight/volume utilization
- **Dock Scheduling**: Appointment management, door assignment, dwell time optimization
- **Rate Management**: Contract rates, spot quotes, rate cards, accessorial charges
- **Freight Procurement**: Carrier waterfall tendering, broker routing, mini-bids
- **Real-Time Visibility**: project44 integration for tracking, ETA, and exception detection
- **Network Configuration**: Facility overlays (dock doors, yard, operating hours), lane profiles, carrier contracts
- **Planning**: Shipping forecast, capacity targets, transportation plan (Plan of Record)

**TMS Data Model**: 29 entities across 3 modules. See `models/tms_entities.py`, `models/transportation_config.py`, `models/tms_planning.py`.

**AWS SC Foundation**: Core infrastructure (Site, TransportationLane, Geography, Tenant, User) shared from upstream Autonomy repo.

### Pillar #1: AI Agents (Automated Planners)

**Purpose**: Replace or assist transportation planners with AI agents that optimize carrier selection, load building, dock scheduling, and exception resolution.

**Three-Tier AI Architecture** (Powell Framework):

```
S&OP GraphSAGE (CFA - Cost Function Approximation)
    ↓ carrier portfolio, lane strategy, mode mix (weekly)
Execution tGNN (CFA/VFA - Generates allocations)
    ↓ daily load assignments, carrier allocations, priority routing
Narrow TRMs (VFA - Value Function Approximation)
    └── 11 Engine-TRM pairs: CapacityPromise, ShipmentTracking,
        DemandSensing, CapacityBuffer, ExceptionMgmt,
        FreightProcurement, BrokerRouting, DockScheduling,
        LoadBuild, IntermodalTransfer, EquipmentReposition
```

**Agent Types**:

1. **Narrow TRM Agents** (Tiny Recursive Model) - Execution Level
   - 7M parameters, 2-layer transformer with 3-step recursive refinement
   - <10ms inference time (100+ decisions/second)
   - 90-95% accuracy vs optimal policies
   - **Research Foundation**: Architecture inspired by Samsung SAIL Montreal's TRM ([arxiv:2510.04871](https://arxiv.org/abs/2510.04871)). See [TRM_RESEARCH_SYNTHESIS.md](../TRM_RESEARCH_SYNTHESIS.md).
   - **Architecture Principles** (from Samsung TRM research):
     - Recursion multiplies compute without multiplying parameters
     - Post-normalization essential for recursion stability
     - Full backpropagation through all recursive steps
     - Deep supervision at each refinement step
     - Fewer parameters → better generalization
   - **11 TMS TRM Agents** (6-phase decision cycle: SENSE → ASSESS → ACQUIRE → PROTECT → BUILD → REFLECT):
     - **CapacityPromiseTRM** (SENSE): Available capacity to promise on lane/carrier/date
     - **ShipmentTrackingTRM** (SENSE): In-transit visibility, ETA prediction, exception detection (p44/EDI)
     - **DemandSensingTRM** (SENSE): Shipping volume forecast adjustments from signals
     - **CapacityBufferTRM** (ASSESS): Reserve carrier capacity above forecast, surge planning
     - **ExceptionManagementTRM** (ASSESS): Delay, damage, refusal, temperature excursion, customs hold resolution
     - **FreightProcurementTRM** (ACQUIRE): Carrier waterfall tendering, rate optimization
     - **BrokerRoutingTRM** (ACQUIRE): Broker vs. asset carrier decision, overflow routing
     - **DockSchedulingTRM** (PROTECT): Appointment scheduling, dock door optimization, detention avoidance
     - **LoadBuildTRM** (BUILD): Load consolidation, weight/volume optimization, multi-stop sequencing
     - **IntermodalTransferTRM** (BUILD): Cross-mode transfers (truck↔rail↔ocean), drayage coordination
     - **EquipmentRepositionTRM** (REFLECT): Empty container/trailer repositioning, deadhead minimization
   - TRM does NOT do: long-term planning, network-wide optimization, policy parameters
   - **Training**: BC warm-start → RL/VFA fine-tuning → CGAR curriculum → 50K samples/sub-phase
   - **CDC → Relearning Loop**: `cdc_monitor.py`, `outcome_collector.py`, `cdt_calibration_service.py`, `cdc_retraining_service.py`, `relearning_jobs.py`, `condition_monitor_service.py`
   - **Conformal Decision Theory (CDT)**: All 11 TRM agents carry `risk_bound` and `risk_assessment` on every decision.

2. **GNN Agent** (Graph Neural Network) - Three-Tier Architecture
   - **S&OP GraphSAGE** (Medium-Term): Network-wide lane optimization, carrier portfolio balance, mode mix. Powell CFA.
   - **Execution tGNN** (Short-Term): Daily load assignments, carrier allocations, priority routing. Powell CFA/VFA bridge.
   - **Site tGNN** (Intra-Site): 11 TRM-type nodes, GATv2+GRU, ~25K params, <5ms, hourly.

3. **LLM Agent** (Multi-Agent Orchestrator): Site agents, supervisor, global planner, NL explainability.

### Pillar #2: Conformal Prediction (Distribution-Free Uncertainty Guarantees)

Every agent decision carries a calibrated likelihood guarantee. CDT risk_bound = P(loss > threshold). Conformal prediction provides P10/P50/P90 bounds for ETA, capacity, and cost forecasts. 21 distribution types. Probabilistic Balanced Scorecard (Financial, Customer, Operational, Strategic).

### Pillar #3: Digital Twin (Stochastic Simulation Engine)

The digital twin replicates the customer's transportation network as a stochastic simulation. 9 triangular distributions per entity. Agents learn by watching heuristics fail. See [DIGITAL_TWIN.md](internal/DIGITAL_TWIN.md).

**TMS-Specific Simulation Games** (replacing Beer Game):
- **Freight Tender Game**: Carrier bidding simulation (shipper vs. carrier agents)
- **Network Disruption Game**: Port strike, weather event, capacity crunch response
- **Mode Selection Game**: Intermodal vs. direct routing optimization

### Pillar #4: Causal AI (Decision Outcome Attribution)

Three-tier causal inference: Analytical Counterfactual (CapacityPromise/DemandSensing/ExceptionMgmt), Statistical Matching (LoadBuild/IntermodalTransfer/FreightProcurement), Bayesian Prior (CapacityBuffer/DockScheduling/BrokerRouting).

Six systems: Counterfactual Computation, Propensity-Score Matching, Bayesian Override Effectiveness, CDT, Outcome Collection Pipeline, Experiential Knowledge Layer.

---

## Detailed Architecture

### Backend Structure (`backend/app/`)

**TMS Data Models** (`models/`):
- `tms_entities.py`: 20 transportation entities, 14 enums (Carrier, Shipment, Load, FreightRate, Appointment, TrackingEvent, ShipmentException, etc.)
- `transportation_config.py`: 5 network config entities (FacilityConfig, OperatingSchedule, YardLocation, LaneProfile, CarrierContract)
- `tms_planning.py`: 4 planning entities (ShippingForecast, CapacityTarget, TransportationPlan, TransportationPlanItem)
- `sc_entities.py`: Shared AWS SC foundation (Site, TransportationLane, Geography — synced from upstream)
- `supply_chain_config.py`: Network topology (shared)
- `user.py`, `tenant.py`, `rbac.py`: Auth and org (shared)
- `decision_tracking.py`: AIIO decision model (shared)
- `agent_config.py`: Agent configuration (shared)

**project44 Integration** (`integrations/project44/`):
- `connector.py`: OAuth 2.0 client credentials, async aiohttp, rate limiting, retry
- `tracking_service.py`: Shipment CRUD, ocean tracking, port intelligence, bulk operations
- `webhook_handler.py`: Inbound event processing, HMAC verification, deduplication, status transitions
- `data_mapper.py`: Bidirectional p44 schema ↔ TMS entity mapping
- `config_service.py`: Tenant-level integration settings management

**TMS Powell Agents** (`services/powell/`):
- `tms_agent_capabilities.py`: 11 TRM declarations with signal reads/emits, decision tables, facility applicability
- `tms_hive_signals.py`: 50+ TMS-specific signal types (scout, carrier, tracking, exception, dock, load, equipment, intermodal, network)
- `tms_site_capabilities.py`: 6 facility types → active TRM subset mapping (shipper, terminal, cross_dock, consignee, carrier_yard, port)
- `tms_heuristic_library/base.py`: 11 state dataclasses (one per TRM) with transportation-specific features
- `tms_heuristic_library/dispatch.py`: Deterministic decision rules for all 11 TRMs (carrier waterfall, load consolidation, dock optimization, etc.)

**Shared Powell Framework** (`services/powell/` — synced from upstream):
- `agent_contract.py`: Abstract TRM base class (AgentContract, AgentCapabilities)
- `site_agent.py`: TRM orchestrator + registration
- `decision_cycle.py`: 6-phase execution ordering (SENSE → ASSESS → ACQUIRE → PROTECT → BUILD → REFLECT)
- `hive_signal.py`: Stigmergic signal bus (shared infrastructure)
- `scenario_engine.py`: Machine-speed what-if (MCTS)
- `simulation_rl_trainer.py`: PPO fine-tuning inside digital twin

**AI Agent Services** (`services/` — shared):
- `llm_agent.py`: LLM agent wrapper with fallback to heuristic strategies
- `llm_payload.py`: OpenAI request/response handling for multi-agent system

**Core Services** (`services/` — shared):
- `conformal_orchestrator.py`: Automatic conformal prediction feedback loop
- `agent_context_explainer.py`: Context-aware explainability orchestrator for all 11 TRM agents and both GNN models
- `explanation_templates.py`: Jinja2-style templates for agent explanation verbosity levels
- `decision_stream_service.py`: Decision Stream inbox — Urgency/Likelihood/Benefit routing framework
- `decision_governance_service.py`: Governance pipeline (envelope, impact scoring, AIIO assignment, guardrails)
- `tenant_service.py`: Tenant and session management
- `auth_service.py`: JWT authentication and authorization

**API Endpoints** (`api/endpoints/`):
- `p44_integration.py`: project44 webhook receiver, config CRUD, tracking operations
- `auth.py`: Authentication (login, register, MFA) — shared
- `websocket.py`: Real-time updates — shared
- `provisioning.py`: Powell Cascade provisioning stepper — shared
- `governance.py`: Decision governance pipeline — shared
- `decision_stream.py`: Decision Stream API — shared

### Frontend Structure (`frontend/src/`)

**Two-Tier Navigation** (shared from upstream):
- CategoryBar (top-level) + PageBar (sub-pages). Capability-filtered via `getFilteredNavigation()`.
- Decision Stream pinned first for functional users.
- Files: `TwoTierNav.jsx`, `CategoryBar.jsx`, `PageBar.jsx`, `useNavStore.js`

**TMS Pages** (`pages/planning/` — to be built):
- Load Board, Shipment Tracker, Lane Analytics, Dock Schedule
- Map-based visualization (Mapbox/Leaflet)
- Carrier Scorecards, Rate Analysis, Exception Dashboard

**Admin Pages** (`pages/admin/` — shared shell, TMS-specific content):
- Carrier Management, Rate Management, Network Config, Governance
- TRM/GNN/GraphSAGE dashboards (adapted for TMS agents)
- p44 Integration Settings

### Agent System Architecture

**TRM Hive Model**: Each facility's TRM agents form a self-organizing hive. Facility-specific composition based on `facility_type`. See `tms_site_capabilities.py`:
- Shipper: 10 TRMs (all except IntermodalTransfer)
- Terminal: 10 TRMs (all except BrokerRouting)
- Cross-Dock: 7 TRMs (core handling operations)
- Consignee: 4 TRMs (ShipmentTracking, DemandSensing, ExceptionMgmt, DockScheduling)
- Carrier Yard: 2 TRMs (EquipmentReposition, ShipmentTracking)
- Port: 5 TRMs (intermodal focus)

#### Multi-Site Coordination Stack (5 layers)

Context, guardrails, and targets flow **down** from strategic to execution. Feedback, outcomes, and escalations flow **up** from execution to strategic.

**Layer 1 — Intra-Hive (<10ms): Stigmergic Coordination**
- `tms_hive_signals.py`: 50+ typed signals across 9 categories (Scout, Carrier, Tracking, Exception, Dock, Load, Equipment, Intermodal, Network)
- `HiveSignalBus`: Shared ring buffer (200 signals) with exponential decay (pheromone model) — shared from upstream
- `UrgencyVector`: 11-slot shared array (one per TRM), thread-safe, decay threshold 0.05
- Decay math: `strength(t) = urgency × exp(-0.693 × elapsed_min / half_life_min)`
- Signal half-life default 30 min (intra-hive), 12 hours (inter-hive)
- TRMs emit signals on condition detection → other TRMs read active signals when deciding

**Layer 2 — Site tGNN (hourly): Learned Cross-TRM Causal Coordination**
- `site_tgnn.py`: GATv2+GRU, ~25K params, 22 directed causal edges, <5ms inference
- Always enabled (no feature flag). Cold-start returns neutral output (zero adjustments)
- Runs BEFORE each decision cycle — modulates UrgencyVector with [-0.3, +0.3] adjustments
- Training: 3-phase (BC from oracle → PPO in digital twin → calibration from outcomes)
- `site_tgnn_inference_service.py`: Loads checkpoint, persists GRU hidden state across ticks
- `site_tgnn_oracle.py`: MultiTRMCoordinationOracle generates 500+ BC samples per site

**Layer 2 — Network tGNN (daily): Inter-Facility Directives**
- `inter_hive_signal.py`: 8 inter-hive signal types with 12-hour half-lives
- `directive_broadcast_service.py`: Broadcasts tGNNSiteDirective to each facility's SiteAgent
- `tactical_hive_coordinator.py`: 3 parallel specialized tGNNs (capacity, carrier, routing) with lateral convergence

**Layer 3 — AAP Cross-Authority (seconds-minutes): Agentic Authorization Protocol**
- `authorization_protocol.py`: Three-phase protocol — EVALUATE → REQUEST → AUTHORIZE
- `authorization_service.py`: Production service with DB persistence
- `strategy_a2a_responder.py`: Routes authorization requests to domain-specific TRM evaluators
  - FreightProcurement TRM: spot rate vs threshold → AUTHORIZE/COUNTER_OFFER/DENY
  - LoadBuild TRM: consolidation opportunity window evaluation
  - EquipmentReposition TRM: fleet balance assessment
- Authority boundaries per TRM role: UNILATERAL / REQUIRES_AUTHORIZATION / FORBIDDEN
- Balanced Scorecard net-benefit scoring: auto-AUTHORIZE if benefit > 1.1× threshold

**Layer 4 — S&OP Consensus Board (weekly): Policy Parameters**
- S&OP GraphSAGE computes network-wide policy parameters θ
- Parameters cascade: carrier_portfolio_mix, lane_capacity_target, mode_split_ratio, service_level_target, cost_per_mile_target, exception_tolerance

#### Downward Flow: Context, Targets, Guardrails

```
S&OP GraphSAGE (weekly) → policy parameters θ (carrier portfolio, lane strategy, mode mix)
    ↓
Network tGNN (daily) → tGNNSiteDirective per facility
    ↓ (directive_broadcast_service.py)
SiteAgent.apply_directive():
    1. Inject inter-hive signals into local HiveSignalBus
    2. Extract S&OP params (capacity_target, carrier_mix, cost_target, etc.)
    3. Push params to TRMs via apply_network_context()
    ↓
Site tGNN (hourly) → modulate UrgencyVector [-0.3, +0.3]
    ↓
11 TRM Agents → execution decisions (<10ms)
```

#### Upward Flow: Feedback, Escalation, Override

```
TRM detects persistent drift (48h lookback, ≥20 decisions)
    ↑ (escalation_arbiter.py)
Escalation Arbiter evaluates:
    - Direction, magnitude, consistency of adjustments
    - Cross-facility pattern (>30% of facilities = strategic)
    ↑
Routing:
    - Horizontal (CDC retrain): single facility/TRM drift
    - Operational (tGNN refresh): magnitude 20-35%, <30% facilities
    - Strategic (S&OP review): magnitude >35%, >30% facilities
    ↑
Human Override → Experiential Knowledge → agent retraining
```

#### Key Implementation Files

| Component | File | Notes |
|-----------|------|-------|
| TMS hive signals | `services/powell/tms_hive_signals.py` | 50+ TMS signal types |
| TMS agent capabilities | `services/powell/tms_agent_capabilities.py` | 11 TRM declarations |
| TMS site capabilities | `services/powell/tms_site_capabilities.py` | 6 facility types |
| TMS heuristic library | `services/powell/tms_heuristic_library/` | 11 state + dispatch |
| Hive signal bus (shared) | `services/powell/hive_signal.py` | Ring buffer + decay |
| Site tGNN model (shared) | `models/gnn/site_tgnn.py` | GATv2+GRU |
| Site agent (shared) | `services/powell/site_agent.py` | TRM orchestrator |
| Decision cycle (shared) | `services/powell/decision_cycle.py` | 6-phase ordering |
| Inter-hive signals (shared) | `services/powell/inter_hive_signal.py` | Cross-facility |
| AAP protocol (shared) | `services/authorization_protocol.py` | Cross-authority |
| Escalation arbiter (shared) | `services/powell/escalation_arbiter.py` | Drift routing |
| Scenario engine (shared) | `services/powell/scenario_engine.py` | MCTS what-if |

**TMS Heuristic Library**: 11 TRM types with deterministic fallback rules encoding industry best practices. Location: `backend/app/services/powell/tms_heuristic_library/`. Key rules: carrier waterfall tendering (primary → backup → spot → broker), load consolidation (weight/volume/compatibility), dock optimization (utilization/queue/detention), intermodal mode-shift (savings threshold + transit fit), equipment repositioning (ROI-based).

**Scenario Engine (MCTS)**: ScenarioEngine, ScenarioTrigger, CandidateGenerator, ContextualBSC. Shared from upstream.

### Database Schema

**TMS Entities** (`tms_entities.py` — 20 tables):
- Commodity: commodity, commodity_hierarchy
- Carrier: carrier, carrier_lane, equipment, carrier_scorecard
- Shipment: shipment, shipment_leg, load, load_item
- Rates: freight_rate, rate_card, spot_quote, freight_tender
- Dock: appointment, dock_door
- Exceptions: shipment_exception, exception_resolution
- Documents: bill_of_lading, proof_of_delivery
- Tracking: tracking_event, shipment_identifier

**TMS Network Config** (`transportation_config.py` — 5 tables):
facility_config, operating_schedule, yard_location, lane_profile, carrier_contract

**TMS Planning** (`tms_planning.py` — 4 tables):
shipping_forecast, capacity_target, transportation_plan, transportation_plan_item

**Shared Network Configuration** (from upstream): supply_chain_configs, site, transportation_lane, geography, product_hierarchy_node

**Organization** (shared): users, tenants, roles, permissions, user_roles

**Powell Framework** (shared): powell_belief_state, powell_calibration_log, powell_policy_parameters, powell_value_function, agent_decisions, agent_scenarios, agent_scenario_actions, scenario_templates, experiential_knowledge

**Directive & Signal** (shared): user_directives, config_provisioning_status

---

## Common Workflows

### Transportation Planning Workflow

1. **Shipping Forecast**: DemandSensingTRM generates lane-level volume forecasts with conformal P10/P50/P90 bounds
2. **Capacity Targets**: CapacityBufferTRM sets committed load targets per lane/mode (buffer above P50)
3. **Transportation Plan**: FreightProcurementTRM generates Plan of Record with carrier assignments
4. **Execution**: 4-hour TRM decision cycle at each facility — tender, track, dock, exceptions
5. **Plan Versions**: `live` (agent P50), `tms_baseline` (current TMS/ERP), `decision_action` (user overrides)

### Adding a New TMS TRM Agent

1. Define state dataclass in `tms_heuristic_library/base.py`
2. Add heuristic function in `tms_heuristic_library/dispatch.py`
3. Declare capabilities in `tms_agent_capabilities.py` (signals, phase, decision table)
4. Add to facility type mapping in `tms_site_capabilities.py`
5. Add hive signal types in `tms_hive_signals.py` if needed
6. Implement TRM class extending `AgentContract`

### project44 Integration Workflow

1. **Configure**: PUT `/api/v1/p44/config` with client_id, client_secret, environment
2. **Enable**: POST `/api/v1/p44/config/enable`
3. **Test**: POST `/api/v1/p44/test-connection`
4. **Register Webhook**: GET `/api/v1/p44/webhook-info` → register URL in p44 portal
5. **Track**: POST `/api/v1/p44/track` with shipment_id → creates p44 tracked shipment
6. **Receive Events**: p44 → POST `/api/v1/p44/webhook/{tenant_id}` → TrackingEvent + status update + exception detection

### Carrier Waterfall Tendering (FreightProcurementTRM)

```
Load ready for tender
    ↓
1. Primary carrier (contract rate, acceptance history)
    ↓ Declined/Expired
2. Backup carriers (priority order, contract rates)
    ↓ All declined
3. Spot market (if premium < 30% over contract)
    ↓ No spot
4. BrokerRoutingTRM (reliability-adjusted cost scoring)
    ↓ Premium > 40%
5. Escalate to Decision Stream for human review
```

### Exception Resolution Flow (ExceptionManagementTRM)

```
Exception detected (p44 webhook / EDI / agent)
    ↓
Severity + Priority assessment:
    - CRITICAL + P1/P2 → immediate re-tender
    - Temperature excursion → escalate immediately
    - Late delivery + time remaining → attempt reroute
    - Minor delay, low priority → accept and monitor
    ↓
Create ShipmentException → link to AgentDecision (AIIO)
    ↓
Decision Stream surfaces to user if INFORM/INSPECT mode
```

---

## Planning Knowledge Base

**TMS-Specific References**:
- Carrier management and tendering best practices
- Load consolidation and optimization algorithms
- Intermodal routing and mode selection
- Dock scheduling and appointment management
- ETA prediction and conformal bounds
- Exception management workflows

**Shared Frameworks**:
- **Powell SDAM**: Five elements (State, Decision, Exogenous, Transition, Objective). Four policy classes (PFA, CFA, VFA, DLA). State decomposition: Rₜ (physical), Iₜ (information), Bₜ (belief). See [POWELL_APPROACH.md](../POWELL_APPROACH.md).
- **Decision-Theoretic Frameworks**: Kahneman Dual-Process, Boyd OODA, SOFAI, Gartner DI. See [ESCALATION_ARCHITECTURE.md](ESCALATION_ARCHITECTURE.md).
- **Conformal Prediction**: Distribution-free uncertainty. See `docs/knowledge/Conformal_Prediction_Framework_Guide.md`.
- **Business Strategy**: Rumelt "Good Strategy Bad Strategy", Moore "Crossing the Chasm".

---

## Claude Skills Framework (Hybrid TRM + Skills)

Hybrid TRM + Claude Skills architecture. TRMs primary (~95%, <10ms), Claude Skills exception handler (~5%). LeCun JEPA mapping. Feature-flagged OFF by default (`USE_CLAUDE_SKILLS=false`).

**Execution Flow**: Engine → TRM → Conformal Router → (high confidence: accept, low confidence: escalate to Skills) → Skills decisions feed TRM meta-learning.

**Routing**: skill_escalation_threshold=0.6, risk_bound check, interval_width > 0.5.

**11 TMS Skills** (mapped from SC):
- Deterministic: capacity_promise, shipment_tracking
- Haiku: freight_procurement, equipment_reposition, capacity_buffer, intermodal_transfer
- Sonnet: load_build, exception_management, dock_scheduling, broker_routing, demand_sensing

**Files**: `services/skills/`, `decision_memory_service.py`, `decision_embeddings.py`.

**Env**: `CLAUDE_API_KEY`, `USE_CLAUDE_SKILLS=false`, `SKILL_ESCALATION_THRESHOLD=0.6`, `SKILL_MAX_DEVIATION=0.3`.

---

## MCP Live Operations Layer (Apr 2026)

**Purpose**: Bidirectional TMS/ERP communication via Model Context Protocol for ongoing operations. Bulk extraction retained for provisioning only.

**Inbound (CDC)**: MCP polls TMS/ERP every 1-5 min → DeltaClassifier → ContextEngine → HiveSignalBus (TMS TRM signals).

**Outbound (Write-back)**: TRM decisions → adaptive delay (urgency/confidence-scaled, business-hours-aware) → MCP tool call → TMS document (shipment update, tender, appointment, etc.).

**Key Design**: No decision is written to TMS/ERP immediately. Every decision gets an adaptive cooling period. Countdown only ticks during business hours. Humans can override pre-execution (cancel) or post-execution (compensating reversal).

**Adapters**: project44, Carrier EDI (204/214/990), TMS connectors (BluJay, Oracle TMS, MercuryGate). Planned: WMS connectors, rate platforms (DAT, Greenscreens).

---

## Unified Training Corpus (Apr 2026)

**Purpose**: Single source of truth for all agent training data across the four planning layers (Strategic S&OP, Tactical tGNNs, Operational Site tGNN, Execution TRMs). Replaces the previous architecture of four independent synthetic data pipelines.

**Anchor**: TMS baseline extracted at provisioning (open shipments, carrier contracts, lane profiles, rate cards, facility configs). This is the tenant's real operating reality.

**Generation**: ~500 perturbations around the baseline (volume +/-15%, transit times +/-20%, rates +/-10%, carrier availability, etc.). Each perturbation runs the Digital Twin with all 11 TRMs active. Every TRM decision is captured as a Layer 1 sample.

**Aggregation**: Pure data transformation upward:
- Layer 1 (TRM decisions) → Layer 2 (facility × time window aggregates for Site tGNN) → Layer 2 (network × domain × period for Tactical tGNNs) → Layer 4 (network × theta* for S&OP GraphSAGE)

**Continuous**: Real outcomes from `powell_*_decisions` append as new Layer 1 samples post-provisioning. Aggregator re-runs on new samples. All four layers retrain together when drift is detected.

**Key property**: All four layers train on the same reality → no cross-layer disagreement.

**Files**: `services/training_corpus/` (shared framework from upstream).
