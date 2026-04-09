# Shared Core vs. TMS-Specific Boundaries

This document defines exactly which code is shared with the parent Autonomy (SC Planning) repo and which is TMS-specific. It serves as the guide for developers deciding where to make changes and how to keep repos in sync.

## Decision Framework

**Before making any change, ask:**
1. Does this change apply to BOTH supply chain planning AND transportation management?
   → Make it in `upstream` (Autonomy) and merge here
2. Is this change transportation-specific?
   → Make it here only
3. Is this a refactor that EXTRACTS shared logic from domain-specific code?
   → Coordinate across both repos

---

## Shared Core (Sync with Upstream)

### Infrastructure & Framework

| Path | What It Does | Sync Strategy |
|------|-------------|---------------|
| `backend/app/core/config.py` | Settings, env vars, feature flags | Merge upstream; add TMS-specific flags only |
| `backend/app/core/security.py` | JWT, CSRF, encryption | Always sync from upstream |
| `backend/app/core/db_urls.py` | Database URL resolution | Always sync |
| `backend/app/db/session.py` | SQLAlchemy session factory | Always sync |
| `backend/app/db/init_db.py` | Database initialization | Merge; TMS may add init steps |
| `backend/app/middleware/` | CORS, auth, logging middleware | Always sync |
| `backend/app/utils/` | Generic helpers | Always sync; add TMS-specific utils separately |

### Auth, Users, Tenants

| Path | What It Does | Sync Strategy |
|------|-------------|---------------|
| `backend/app/models/user.py` | User, Role, Permission models | Always sync |
| `backend/app/models/rbac.py` | RBAC definitions | Sync; TMS may add new capabilities |
| `backend/app/models/tenant.py` | Tenant model | Always sync |
| `backend/app/api/endpoints/auth.py` | Login, register, MFA | Always sync |
| `backend/app/services/auth_service.py` | Auth logic | Always sync |
| `backend/app/services/tenant_service.py` | Tenant management | Always sync |

### Agent Framework (Architecture, NOT Domain Logic)

| Path | What It Does | Sync Strategy |
|------|-------------|---------------|
| `backend/app/services/powell/site_agent.py` | Site agent architecture (deterministic + TRM + Skills + CDC) | Sync framework; TMS overrides domain logic |
| `backend/app/services/powell/powell_training_service.py` | TRM training pipeline | Sync training loop; TMS provides own data/rewards |
| `backend/app/services/powell/trm_trainer.py` | TRM training orchestrator | Always sync |
| `backend/app/services/powell/simulation_rl_trainer.py` | RL fine-tuning in digital twin | Always sync |
| `backend/app/services/powell/hive_signal.py` | Stigmergic hive coordination | Always sync |
| `backend/app/services/agent_orchestrator_service.py` | Multi-agent coordination | Always sync |
| `backend/app/ml/` | ML model definitions (TRM, GNN architectures) | Always sync |
| `external/tiny-recursive-model/` | TRM model artifacts | Always sync |

### Conformal Prediction & Uncertainty

| Path | What It Does | Sync Strategy |
|------|-------------|---------------|
| `backend/app/services/conformal_prediction/` | Distribution-free prediction | Always sync |
| `backend/app/services/conformal_orchestrator.py` | Conformal feedback loop | Always sync |
| `backend/app/services/stochastic_sampling.py` | Distribution sampling | Always sync |
| `backend/app/services/monte_carlo/` | Monte Carlo engine | Always sync |

### Decision Stream & Governance

| Path | What It Does | Sync Strategy |
|------|-------------|---------------|
| `backend/app/services/decision_stream_service.py` | Decision inbox, routing | Always sync |
| `backend/app/services/decision_governance_service.py` | Governance pipeline | Always sync |
| `backend/app/services/decision_service.py` | Decision logic | Always sync |
| `backend/app/services/authorization_service.py` | RBAC enforcement | Always sync |
| `backend/app/models/powell_decisions.py` | Decision records | Always sync |
| `backend/app/models/decision_tracking.py` | Audit trail | Always sync |

### Causal AI

| Path | What It Does | Sync Strategy |
|------|-------------|---------------|
| `backend/app/services/causal/` | Counterfactual, propensity matching | Always sync |
| `backend/app/services/agent_context_explainer.py` | Explainability orchestrator | Sync framework; TMS adds templates |
| `backend/app/services/explanation_templates.py` | Jinja2 explanation templates | TMS replaces with transport-specific templates |

### Frontend Shell

| Path | What It Does | Sync Strategy |
|------|-------------|---------------|
| `frontend/src/components/TwoTierNav.jsx` | Navigation framework | Always sync |
| `frontend/src/components/CategoryBar.jsx` | Category navigation | Always sync |
| `frontend/src/components/PageBar.jsx` | Page navigation | Always sync |
| `frontend/src/contexts/` | Auth, theme, config contexts | Always sync |
| `frontend/src/hooks/` | Shared hooks (useAuth, useWebSocket, etc.) | Always sync |
| `frontend/src/services/api.js` | Axios client | Always sync |
| `frontend/src/theme/` | Material-UI theme | Always sync |

---

## TMS-Specific (This Repo Only)

### Data Models — Replace

| SC Path | TMS Replacement | What Changes |
|---------|----------------|--------------|
| `models/sc_entities.py` | `models/tms_entities.py` | Shipment, Load, Carrier, Equipment, FreightRate, Appointment, BOL, POD, Exception |
| `models/supply_chain_config.py` | `models/transportation_config.py` | Facility (replaces Site), Lane (shared), Mode, CarrierContract, ServiceLevel |
| `models/sc_planning.py` | `models/tms_planning.py` | ShippingForecast, CapacityPlan, TransportationPlan, LoadPlan |
| `models/mps.py` | `models/load_schedule.py` | Load scheduling, carrier assignment |
| `models/mrp.py` | — | No equivalent (no BOM explosion in transport) |
| `models/capacity_plan.py` | `models/carrier_capacity.py` | Carrier capacity by lane/mode/period |
| `models/pegging.py` | `models/shipment_pegging.py` | Shipment-to-load, load-to-carrier tracing |
| `models/transfer_order.py` | `models/intermodal_transfer.py` | Cross-mode transfer records |
| `models/purchase_order.py` | `models/freight_tender.py` | Carrier tender, acceptance, rejection |
| `models/production_order.py` | `models/load_build.py` | Load consolidation records |

### Services — Replace

| SC Service | TMS Replacement | What Changes |
|-----------|----------------|--------------|
| `services/aws_sc_planning/planner.py` | `services/transportation_planning/planner.py` | Forecast → Capacity → Load Build → Assign |
| `services/aws_sc_planning/demand_processor.py` | `services/transportation_planning/demand_processor.py` | Shipping volume aggregation by lane/mode |
| `services/aws_sc_planning/inventory_target_calculator.py` | `services/transportation_planning/capacity_target_calculator.py` | Carrier capacity targets by lane |
| `services/aws_sc_planning/net_requirements_calculator.py` | `services/transportation_planning/load_optimizer.py` | Load consolidation, route optimization |
| `services/atp_service.py` | `services/capacity_promise_service.py` | Available carrier capacity to promise |
| `services/ctp_service.py` | `services/multi_mode_promise_service.py` | Cross-mode capacity promise |
| `services/pegging_service.py` | `services/shipment_pegging_service.py` | Shipment-load-carrier tracing |
| `services/order_management_service.py` | `services/shipment_management_service.py` | Shipment lifecycle management |
| `services/fulfillment_service.py` | `services/delivery_service.py` | Last-mile delivery, POD |
| `services/forecast_pipeline_service.py` | `services/volume_forecast_service.py` | Lane volume forecasting |

### Powell TRM Engines — Replace

| SC Engine | TMS Engine | What Changes |
|-----------|-----------|--------------|
| `powell/engines/atp_executor.py` | `powell/engines/capacity_promise.py` | Lane/carrier capacity promise |
| `powell/engines/rebalancing.py` | `powell/engines/equipment_reposition.py` | Empty container/trailer moves |
| `powell/engines/po_creation.py` | `powell/engines/freight_procurement.py` | Carrier selection, tender, rate negotiation |
| `powell/engines/order_tracking.py` | `powell/engines/shipment_tracking.py` | In-transit tracking, ETA, exceptions |
| `powell/engines/mo_execution.py` | `powell/engines/load_build.py` | Load consolidation, optimization |
| `powell/engines/to_execution.py` | `powell/engines/intermodal_transfer.py` | Cross-mode coordination |
| `powell/engines/quality.py` | `powell/engines/exception_management.py` | Delay, damage, refusal, roll resolution |
| `powell/engines/maintenance.py` | `powell/engines/dock_scheduling.py` | Appointment management, dock optimization |
| `powell/engines/subcontracting.py` | `powell/engines/broker_routing.py` | Broker vs. asset carrier decision |
| `powell/engines/forecast_adjustment.py` | `powell/engines/demand_sensing.py` | Volume forecast signal adjustment |
| `powell/engines/safety_stock.py` | `powell/engines/capacity_buffer.py` | Reserve carrier capacity |

### Integrations — Replace/Add

| SC Integration | TMS Integration | What Changes |
|---------------|----------------|--------------|
| `integrations/sap/` | `integrations/project44/` | Real-time visibility, ETA, exceptions. **DONE**: connector, tracking_service, webhook_handler, data_mapper, config_service, API endpoints |
| `integrations/d365/` | `integrations/carrier_edi/` | EDI 204/214/990 tender/track |
| `integrations/infor/` | `integrations/rate_sources/` | DAT, Greenscreens, SONAR |
| `integrations/odoo/` | `integrations/tms_connectors/` | BluJay, Oracle TMS, MercuryGate |
| `integrations/b1/` | `integrations/weather/` | NOAA, disruption prediction |

### Frontend Pages — Replace

| SC Page Area | TMS Page Area | What Changes |
|-------------|--------------|--------------|
| `pages/planning/demand/` | `pages/planning/volume_forecast/` | Lane volume forecasting views |
| `pages/planning/supply/` | `pages/planning/carrier_capacity/` | Carrier capacity views |
| `pages/planning/mps/` | `pages/planning/load_board/` | Load planning, assignment board |
| `pages/planning/inventory/` | `pages/planning/yard_management/` | Yard/dock views |
| `pages/planning/capacity/` | `pages/planning/lane_analytics/` | Lane performance, mode analysis |
| `pages/admin/sap_management/` | `pages/admin/carrier_management/` | Carrier onboarding, scorecards |
| — | `pages/planning/shipment_tracker/` | Map-based tracking (NEW) |
| — | `pages/planning/dock_schedule/` | Appointment management (NEW) |
| — | `pages/planning/rate_management/` | Freight rates, procurement (NEW) |
| — | `pages/planning/exception_mgmt/` | Exception resolution dashboard (NEW) |

### Demo Data Generators — Replace

| SC Generator | TMS Generator | What Changes |
|-------------|--------------|--------------|
| `services/food_dist_config_generator.py` | `services/freight_network_generator.py` | Transportation network: shippers, carriers, terminals, lanes |
| `services/food_dist_history_generator.py` | `services/freight_history_generator.py` | Historical shipments, rates, carrier performance |
| `simulation/mixed_scenario_service.py` | `simulation/freight_scenario_service.py` | Freight tender, disruption, mode selection games |

### Metrics — Replace

| SC Metric | TMS Metric | What It Measures |
|-----------|-----------|-----------------|
| OTIF (Order) | OTIF (Shipment) | On-time in-full delivery |
| Fill Rate | Tender Acceptance Rate | % tenders accepted by carriers |
| Inventory Turns | Equipment Utilization | Trailer/container turns per period |
| Days of Supply | Transit Time | Average origin-to-destination time |
| Total Cost | Cost per Mile/Shipment | Transportation cost efficiency |
| Bullwhip Ratio | Capacity Volatility | Demand-capacity matching stability |
| — | Empty Mile Ratio | % of miles driven without freight |
| — | Dwell Time | Time at facility (pickup/delivery) |
| — | Carrier Scorecard | Composite carrier performance |
| — | Carbon Intensity | CO2 per ton-mile by mode |

---

## Migration Roadmap

### Phase 1: Foundation (Complete)
- [x] Fork repo, set up remotes (upstream + origin)
- [x] Create TMS CLAUDE.md and boundary docs
- [x] Create `tms_entities.py` data model (20 entities, 14 enums)
- [x] Create `transportation_config.py` network model (5 entities, 3 enums)
- [x] Create `tms_planning.py` planning model (4 entities, 3 enums)
- [x] Add project44 integration adapter (connector, tracking, webhooks, data mapper, config service)
- [x] Add p44 API endpoints (webhook receiver, config management, tracking operations)

### Phase 2: Planning Engines (Current)
- [x] Create TMS Powell TRM agent framework (11 agents: capabilities, hive signals, site capabilities, heuristic library)
- [ ] Implement transportation planning service (replacing SC planner)
- [ ] Create freight network demo data generator
- [ ] Adapt provisioning pipeline for TMS

### Phase 3: Frontend
- [ ] Create TMS navigation structure
- [ ] Build load board, shipment tracker, dock scheduler pages
- [ ] Add map-based visualization (Mapbox/Leaflet)
- [ ] Adapt Decision Stream for transport exceptions

### Phase 4: Integration & Training
- [ ] Carrier EDI (204/214/990) adapter
- [ ] TRM training with freight execution data
- [ ] GNN training on transportation network
