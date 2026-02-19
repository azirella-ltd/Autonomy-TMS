# AWS Supply Chain Platform - Architectural Refactoring Plan

**Date**: 2026-01-19
**Status**: 🔄 **PLANNING PHASE** - Major Architectural Refactoring
**Objective**: Transform from "Beer Game-centric" to "AWS SC-first with Simulation"

---

## Executive Summary

### Current State: "The Continuous Autonomous Planning Platform"
- **Primary Focus**: Beer Game simulation and gamification
- **Architecture**: Game-first with supply chain capabilities added on
- **Positioning**: Educational tool with professional features

### Target State: "AWS Supply Chain with AI & Simulation"
- **Primary Focus**: Professional AWS SC-compatible supply chain planning and execution
- **Architecture**: AWS SC-first with 3 unique differentiators:
  1. **AI Agents** replacing human planners
  2. **Stochastic Planning** with probabilistic outcomes
  3. **Simulation** (The Beer Game as training/validation module)
- **Positioning**: Enterprise supply chain platform with simulation-based learning

---

## Strategic Repositioning

### The 3-Pillar Value Proposition

```
┌─────────────────────────────────────────────────────────────┐
│          AWS Supply Chain Platform (Core)                    │
│  • Demand Planning          • Inventory Optimization         │
│  • Supply Planning           • Manufacturing Planning         │
│  • Master Production Scheduling                              │
├─────────────────────────────────────────────────────────────┤
│                    + 3 Unique Differentiators               │
├─────────────────────────────────────────────────────────────┤
│  1. AI Agents (Automated Planners)                          │
│     • TRM (7M param transformer)                            │
│     • GNN (128M param graph network)                        │
│     • LLM (GPT-4 multi-agent orchestrator)                  │
│     → Replace/assist human planners with AI                 │
├─────────────────────────────────────────────────────────────┤
│  2. Stochastic Planning (Probabilistic Results)             │
│     • 20 distribution types for uncertainty                 │
│     • Monte Carlo simulation (1000+ scenarios)              │
│     • Probabilistic balanced scorecard                      │
│     → Plan with likelihood instead of point estimates       │
├─────────────────────────────────────────────────────────────┤
│  3. Simulation (The Beer Game Module)                       │
│     • Validate AI agents in risk-free scenarios             │
│     • Train employees through competitive simulation        │
│     • Build confidence in AI recommendations                │
│     → Learn and validate through simulation                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Refactoring Scope

### Phase 1: Conceptual Reframing (2 weeks)

#### 1.1 Rename Project
**Current**: "The Continuous Autonomous Planning Platform"
**Target**: "AWS Supply Chain with AI & Gamification" or "Autonomy Platform"

**Changes**:
- Repository rename (optional)
- Documentation updates
- Marketing materials
- UI branding

#### 1.2 Restructure Navigation

**Current Navigation** (Game-first):
```
Overview
├── Dashboard
└── Analytics

Simulation ← PRIMARY
├── The Beer Game
├── Create Scenario
└── My Scenarios

Supply Chain Design
├── Network Configs
└── Inventory Models

Planning & Optimization
├── Order Planning
├── Demand Planning
├── Supply Planning
└── MPS
```

**Target Navigation** (AWS SC-first):
```
Overview
├── Dashboard
└── Supply Chain Insights

Planning ← PRIMARY
├── Demand Planning
├── Supply Planning
├── Master Production Scheduling (MPS)
├── Inventory Optimization
└── Capacity Planning

Execution
├── Order Management
├── Inventory Management
├── Manufacturing Execution
└── Shipment Tracking

Supply Chain Design
├── Network Configuration
├── Products & BOMs
├── Sourcing Rules
└── Transportation Lanes

AI & Agents
├── Agent Configuration
├── TRM Training
├── GNN Training
└── LLM Orchestrator

Simulation & Training ← SECONDARY (Special Module)
├── The Beer Game
├── Training Scenarios
├── Agent Validation Scenarios
└── Leaderboards
```

#### 1.3 Home Page Redesign

**Current**: Scenario-focused landing with "Run The Beer Game" CTA

**Target**: AWS SC dashboard with AI & stochastic planning highlights
- **Hero**: "AI-Powered Supply Chain Planning with Probabilistic Outcomes"
- **3 Pillars**: AWS SC + AI Agents + Stochastic Planning + Simulation
- **CTA**: "Start Planning" (not "Run Scenario")
- **Secondary CTA**: "Try Simulation Mode"

---

### Phase 2: Data Model Refactoring (4 weeks)

#### 2.1 AWS SC Standard Entities (Priority: HIGH)

**Implement Full AWS SC Data Model** from [AWS_Supply_Chain_Data_Model_Complete.md](AWS_Supply_Chain_Data_Model_Complete.md):

##### **Organization Entities**
- [x] ✅ `company` (partially exists as `groups`)
- [ ] ❌ `geography`
- [x] ✅ `trading_partner` (exists)

##### **Network Entities**
- [x] ✅ `site` (exists as `nodes`)
- [x] ✅ `transportation_lane` (exists as `lanes`)

##### **Product Entities**
- [x] ✅ `product` (exists as `items`)
- [ ] ❌ `product_hierarchy`

##### **Supply Planning Entities** (CRITICAL)
- [x] ✅ `sourcing_rules`
- [ ] ❌ `sourcing_schedule`
- [ ] ❌ `sourcing_schedule_details`
- [x] ✅ `inv_policy`
- [x] ✅ `inv_level`
- [x] ✅ `vendor_product`
- [x] ✅ `vendor_lead_time`
- [x] ✅ `supply_planning_parameters`

##### **Manufacturing Entities**
- [x] ✅ `product_bom`
- [x] ✅ `production_process`

##### **Inbound Order Entities** (NEW)
- [ ] ❌ `inbound_order`
- [x] ✅ `inbound_order_line` (exists)
- [ ] ❌ `inbound_order_line_schedule`

##### **Shipment Entities** (NEW)
- [ ] ❌ `shipment`
- [ ] ❌ `shipment_stop`
- [ ] ❌ `shipment_lot`

##### **Outbound Fulfillment** (NEW)
- [ ] ❌ `outbound_order_line`
- [ ] ❌ `outbound_shipment`

##### **Planning Output**
- [x] ✅ `supply_plan`
- [x] ✅ `reservation`

##### **Forecast**
- [x] ✅ `forecast`
- [ ] ❌ `supplementary_time_series`

##### **Operations** (NEW - for Manufacturing)
- [ ] ❌ `process_header`
- [ ] ❌ `process_operation`
- [ ] ❌ `process_product`
- [ ] ❌ `work_order_plan`

##### **Cost Management** (NEW)
- [ ] ❌ `customer_cost`

##### **Segmentation** (NEW)
- [ ] ❌ `segmentation`

#### 2.2 Refactor Existing Tables

**Current Beer Game Tables** → **AWS SC Equivalent**:

| Current Table | AWS SC Standard | Action |
|---------------|-----------------|--------|
| `scenarios` | `simulation_session` | Rename + add metadata |
| `nodes` | `site` | Migrate to AWS SC schema |
| `items` | `product` | Migrate to AWS SC schema |
| `lanes` | `transportation_lane` | Migrate to AWS SC schema |
| `groups` | `company` | Migrate to AWS SC schema |
| `participants` | `user_simulation_role` | Refactor as special case |
| `periods` | `simulation_period` | Rename + context |
| `participant_actions` | `simulation_decision` | Refactor |
| `participant_periods` | `simulation_metrics` | Refactor |

#### 2.3 Add Missing AWS SC Entities

**Priority 1 (Weeks 1-2)**:
- `product_hierarchy` - Product categorization
- `inbound_order` - Purchase orders
- `inbound_order_line_schedule` - Delivery schedules
- `shipment` - Shipment tracking
- `outbound_order_line` - Customer orders

**Priority 2 (Weeks 3-4)**:
- `process_header` - Manufacturing processes
- `process_operation` - Operation details
- `work_order_plan` - Production orders
- `customer_cost` - Customer-specific pricing
- `segmentation` - ABC/XYZ classification

---

### Phase 3: Service Layer Refactoring (6 weeks)

#### 3.1 Core AWS SC Services

**New Service Architecture**:

```
backend/app/services/
├── aws_sc/                          ← NEW: AWS SC Core
│   ├── planning/
│   │   ├── demand_planning_service.py
│   │   ├── supply_planning_service.py
│   │   ├── mps_service.py           ← Master Production Scheduling
│   │   ├── mrp_service.py           ← Material Requirements Planning
│   │   └── capacity_planning_service.py
│   ├── execution/
│   │   ├── order_management_service.py
│   │   ├── inventory_management_service.py
│   │   ├── shipment_tracking_service.py
│   │   └── manufacturing_execution_service.py
│   ├── forecasting/
│   │   ├── statistical_forecasting_service.py
│   │   ├── ml_forecasting_service.py
│   │   └── consensus_forecasting_service.py
│   └── optimization/
│       ├── network_optimization_service.py
│       ├── inventory_optimization_service.py
│       └── production_optimization_service.py
├── ai_agents/                       ← AI-Powered Planners
│   ├── trm_agent_service.py
│   ├── gnn_agent_service.py
│   └── llm_agent_orchestrator.py
├── stochastic/                      ← Probabilistic Planning
│   ├── distribution_sampler.py
│   ├── monte_carlo_planner.py
│   └── scenario_generator.py
└── simulation/                      ← The Beer Game Module
    ├── beer_game_service.py
    ├── scenario_orchestrator.py
    ├── leaderboard_service.py
    └── achievement_service.py
```

#### 3.2 Refactor Beer Game as Simulation Module

**Current**: `services/mixed_game_service.py` (375KB monolith)

**Target**: Modular simulation services

```python
# backend/app/services/simulation/beer_game_service.py
class BeerGameService:
    """
    The Beer Game as a simulation layer for AWS SC platform.

    Purpose:
    - Validate AI agents in risk-free environment
    - Train employees through competitive simulation
    - Build confidence in AI recommendations

    Uses core AWS SC services underneath:
    - DemandPlanningService for forecasting
    - SupplyPlanningService for replenishment
    - InventoryManagementService for tracking
    """

    def __init__(self, aws_sc_config_id: int):
        self.demand_service = DemandPlanningService()
        self.supply_service = SupplyPlanningService()
        self.inventory_service = InventoryManagementService()

    def create_scenario_session(self, participants: List[User], ai_agents: List[AgentConfig]):
        """Create simulation session using AWS SC configuration"""
        pass

    def play_period(self, session_id: int, participant_decisions: Dict):
        """
        Execute one period:
        1. Participant/AI decisions
        2. Call AWS SC planning services
        3. Execute decisions
        4. Update scenario metrics
        """
        pass

    def get_leaderboard(self):
        """Simulation: rankings and achievements"""
        pass
```

---

### Phase 4: API Refactoring (4 weeks)

#### 4.1 AWS SC API Endpoints

**New API Structure**:

```
/api/v1/
├── planning/                        ← AWS SC Planning APIs
│   ├── demand/
│   │   ├── GET /forecasts
│   │   ├── POST /forecasts
│   │   └── PUT /forecasts/{id}
│   ├── supply/
│   │   ├── GET /plans
│   │   ├── POST /plans/generate
│   │   └── GET /plans/{id}
│   ├── mps/                         ← Master Production Scheduling
│   │   ├── GET /schedules
│   │   ├── POST /schedules
│   │   ├── POST /schedules/{id}/approve
│   │   └── GET /schedules/{id}/capacity-check
│   └── inventory/
│       ├── GET /policies
│       ├── POST /policies
│       └── GET /optimization-recommendations
├── execution/                       ← AWS SC Execution APIs
│   ├── orders/
│   │   ├── GET /inbound
│   │   ├── POST /inbound
│   │   ├── GET /outbound
│   │   └── POST /outbound
│   ├── inventory/
│   │   ├── GET /levels
│   │   ├── POST /adjustments
│   │   └── GET /availability (ATP/CTP)
│   └── shipments/
│       ├── GET /
│       ├── POST /
│       └── GET /{id}/tracking
├── ai-agents/                       ← AI Agent Management
│   ├── GET /agents
│   ├── POST /agents/configure
│   ├── POST /agents/train
│   └── GET /agents/{id}/performance
├── stochastic/                      ← Stochastic Planning
│   ├── POST /scenarios/generate
│   ├── POST /monte-carlo/run
│   └── GET /scorecard/{plan_id}
└── simulation/                      ← Beer Game Module
    ├── GET /scenarios
    ├── POST /scenarios/create
    ├── POST /scenarios/{id}/play-period
    ├── GET /leaderboard
    └── GET /achievements
```

#### 4.2 Deprecate Scenario-First Endpoints

**Mark as deprecated** (keep for backward compatibility):
- `/api/v1/games/*` → Redirect to `/api/v1/simulation/scenarios/*`
- `/api/v1/mixed-games/*` → Deprecated
- `/api/v1/agent-games/*` → Deprecated

---

### Phase 5: Frontend Refactoring (6 weeks)

#### 5.1 Navigation Restructuring

**Update** [frontend/src/components/Sidebar.jsx](frontend/src/components/Sidebar.jsx):

```javascript
const getNavigationStructure = (user, hasCapability) => {
  return [
    {
      id: 'overview',
      label: 'Overview',
      items: [
        { label: 'Dashboard', path: '/dashboard' },
        { label: 'Supply Chain Insights', path: '/insights' },
      ],
    },
    {
      id: 'planning',  // ← PRIMARY SECTION (was 'gamification')
      label: 'Planning',
      icon: <PlanningIcon />,
      items: [
        { label: 'Demand Planning', path: '/planning/demand' },
        { label: 'Supply Planning', path: '/planning/supply' },
        { label: 'Master Production Scheduling', path: '/planning/mps' },
        { label: 'Inventory Optimization', path: '/planning/inventory' },
        { label: 'Capacity Planning', path: '/planning/capacity' },
      ],
    },
    {
      id: 'execution',  // ← NEW SECTION
      label: 'Execution',
      icon: <ExecutionIcon />,
      items: [
        { label: 'Order Management', path: '/execution/orders' },
        { label: 'Inventory Management', path: '/execution/inventory' },
        { label: 'Manufacturing Execution', path: '/execution/manufacturing' },
        { label: 'Shipment Tracking', path: '/execution/shipments' },
      ],
    },
    {
      id: 'ai-agents',  // ← NEW SECTION
      label: 'AI & Agents',
      icon: <AIIcon />,
      items: [
        { label: 'Agent Configuration', path: '/agents/config' },
        { label: 'TRM Training', path: '/agents/trm' },
        { label: 'GNN Training', path: '/agents/gnn' },
        { label: 'LLM Orchestrator', path: '/agents/llm' },
        { label: 'Performance Analytics', path: '/agents/performance' },
      ],
    },
    {
      id: 'simulation',  // ← MOVED TO SECONDARY
      label: 'Simulation & Training',
      icon: <SimulationIcon />,
      items: [
        { label: 'The Beer Game', path: '/simulation/beer-game' },
        { label: 'Training Scenarios', path: '/simulation/scenarios' },
        { label: 'Agent Validation', path: '/simulation/validation' },
        { label: 'Leaderboards', path: '/simulation/leaderboards' },
      ],
    },
    // ... other sections
  ];
};
```

#### 5.2 New Page Components

**Planning Pages** (Priority: HIGH):
- `pages/planning/DemandPlanning.jsx` - Demand forecasting UI
- `pages/planning/SupplyPlanning.jsx` - Supply plan generation (exists as prototype)
- `pages/planning/MasterProductionScheduling.jsx` - ✅ Created
- `pages/planning/InventoryOptimization.jsx` - Safety stock optimization
- `pages/planning/CapacityPlanning.jsx` - Resource capacity planning

**Execution Pages** (Priority: MEDIUM):
- `pages/execution/OrderManagement.jsx` - Inbound/outbound orders
- `pages/execution/InventoryManagement.jsx` - Inventory levels, adjustments
- `pages/execution/ManufacturingExecution.jsx` - Work orders, production
- `pages/execution/ShipmentTracking.jsx` - Shipment status tracking

**AI Agent Pages** (Priority: MEDIUM):
- `pages/agents/AgentConfiguration.jsx` - Configure agent strategies
- `pages/agents/TRMTraining.jsx` - ✅ Exists ([pages/admin/TRMDashboard.jsx](frontend/src/pages/admin/TRMDashboard.jsx))
- `pages/agents/GNNTraining.jsx` - ✅ Exists ([pages/admin/GNNDashboard.jsx](frontend/src/pages/admin/GNNDashboard.jsx))
- `pages/agents/LLMOrchestrator.jsx` - LLM agent management
- `pages/agents/PerformanceAnalytics.jsx` - Agent performance dashboards

**Simulation Pages** (Priority: LOW - already exist):
- `pages/simulation/BeerGame.jsx` - Rename from `pages/ScenarioBoard.jsx`
- `pages/simulation/TrainingScenarios.jsx` - NEW
- `pages/simulation/AgentValidation.jsx` - NEW
- `pages/simulation/Leaderboards.jsx` - NEW

#### 5.3 Dashboard Redesign

**Current**: Scenario-focused dashboard with scenario cards

**Target**: AWS SC dashboard with planning insights

```
┌──────────────────────────────────────────────────────────┐
│  AWS Supply Chain Dashboard                              │
├──────────────────────────────────────────────────────────┤
│  KPI Cards                                               │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐          │
│  │Service │ │Inventory│ │Forecast│ │Bullwhip│          │
│  │ Level  │ │ Turns   │ │Accuracy│ │ Ratio  │          │
│  │  96%   │ │  12.3   │ │  85%   │ │  1.8   │          │
│  └────────┘ └────────┘ └────────┘ └────────┘          │
├──────────────────────────────────────────────────────────┤
│  Active Supply Plans                                     │
│  • Supply Plan Q1 2026 (Pending Approval)               │
│  • MPS Week 3 (Approved, In Execution)                  │
│  • Demand Plan Jan 2026 (Draft)                         │
├──────────────────────────────────────────────────────────┤
│  AI Agent Performance                                    │
│  • TRM Agent: 94% accuracy, 22% cost reduction          │
│  • GNN Agent: 89% accuracy, 18% cost reduction          │
│  • LLM Agent: Pending validation                        │
├──────────────────────────────────────────────────────────┤
│  Simulation Corner (Secondary)                           │
│  Try The Beer Game | Leaderboard | Progress             │
└──────────────────────────────────────────────────────────┘
```

---

### Phase 6: Documentation Refactoring (2 weeks)

#### 6.1 Update Core Documentation

**CLAUDE.md** → Major rewrite:
```markdown
# AWS Supply Chain Platform with AI & Gamification

This platform provides enterprise-grade AWS Supply Chain planning and execution
with 3 unique differentiators:

1. **AI Agents**: Automated planners powered by TRM, GNN, and LLM
2. **Stochastic Planning**: Probabilistic outcomes with Monte Carlo simulation
3. **Simulation**: The Beer Game for training and validation

## Project Overview

The platform implements AWS Supply Chain standard functionality:
- Demand Planning & Forecasting
- Supply Planning & Replenishment
- Master Production Scheduling (MPS)
- Inventory Optimization
- Capacity Planning
- Order Management & Execution

**Plus unique features**:
- AI agents replace/assist human planners
- Stochastic modeling with 20 distribution types
- The Beer Game as gamified training module
```

**README.md** → Reposition:
- Hero: "AWS Supply Chain with AI-Powered Planning"
- 3 Pillars section
- Simulation as feature #3 (not primary focus)

#### 6.2 Create New Documentation

**AWS_SC_IMPLEMENTATION_STATUS.md**:
- Checklist of all 35 AWS SC entities
- Implementation status for each
- Compliance percentage
- Roadmap to 100% compliance

**AI_AGENT_GUIDE.md**:
- How AI agents work
- When to use TRM vs GNN vs LLM
- Training workflows
- Performance benchmarks

**STOCHASTIC_PLANNING_GUIDE.md**:
- Distribution types and use cases
- Monte Carlo simulation setup
- Probabilistic balanced scorecard interpretation
- Risk analysis workflows

**SIMULATION_MODULE_GUIDE.md**:
- The Beer Game as training tool
- Creating validation scenarios
- Leaderboards and achievements
- Agent vs Human competitions

---

### Phase 7: Branding & Marketing (1 week)

#### 7.1 Rename Components

**Current**:
- Project: "The Continuous Autonomous Planning Platform"
- Primary focus: Gaming

**Target**:
- Project: "Autonomy" or "AWS SC with AI"
- Primary focus: Professional supply chain planning

#### 7.2 Update Branding Assets

- Logo redesign (professional, not game-focused)
- Color scheme (enterprise blue/green, not playful)
- Typography (professional, not casual)
- Landing page hero image (supply chain network, not beer bottles)

#### 7.3 Value Proposition Messaging

**Old**: "Learn supply chain management through The Beer Game"

**New**: "Enterprise AWS Supply Chain planning with AI agents, stochastic modeling, and gamified training"

**Elevator Pitch**:
> "We've taken AWS Supply Chain and added three game-changers: AI agents that can plan as well as humans, stochastic modeling that shows you likelihood instead of guessing, and The Beer Game for risk-free validation. It's professional supply chain planning with a safety net."

---

## Migration Strategy

### Phase 1-2: Parallel Operation (Month 1-2)

- Keep existing Beer Game simulation functionality working
- Add new AWS SC pages alongside
- Dual navigation (legacy + new)
- Feature flags to toggle between modes

### Phase 3: Gradual Transition (Month 3-4)

- Default to new AWS SC navigation
- "Classic Beer Game" mode available via toggle
- Migrate users to new workflows
- Deprecation warnings on old endpoints

### Phase 4: Full Cutover (Month 5-6)

- Remove dual navigation
- Beer Game fully integrated as simulation module
- Old endpoints removed (breaking change, major version bump)
- Documentation fully updated

---

## Database Migration Plan

### Option A: In-Place Migration (Recommended)

**Advantages**:
- No data loss
- Gradual transition
- Rollback possible

**Steps**:
1. Create new AWS SC tables alongside existing
2. Add foreign keys linking old→new
3. Create migration scripts to copy data
4. Run migration in phases
5. Update application to use new tables
6. Deprecate old tables (keep for 6 months)
7. Final cleanup

### Option B: Blue-Green Migration

**Advantages**:
- Clean slate
- Test fully before cutover
- Fast rollback

**Steps**:
1. Deploy new AWS SC schema in parallel database
2. Sync data continuously
3. Test new application version against new DB
4. Cutover during maintenance window
5. Keep old DB as backup for 30 days

---

## Risk Mitigation

### Risk 1: User Confusion

**Mitigation**:
- Clear communication about changes
- Training materials and videos
- Side-by-side comparison docs
- "What's New" highlights in UI

### Risk 2: Data Migration Errors

**Mitigation**:
- Extensive testing in staging
- Automated validation scripts
- Rollback procedures documented
- Data integrity checks

### Risk 3: Breaking Existing Integrations

**Mitigation**:
- API versioning (keep v1 for 12 months)
- Deprecation warnings
- Migration guides for API consumers
- Backward compatibility layer

### Risk 4: Loss of Beer Game Essence

**Mitigation**:
- Beer Game gets dedicated section (Simulation)
- All existing scenario features preserved
- Enhanced with AI validation use case
- Positioned as unique strength, not afterthought

---

## Success Metrics

### Technical Metrics

- [ ] AWS SC entity coverage: 100% (currently ~60%)
- [ ] API endpoint parity: 35+ AWS SC endpoints
- [ ] Database migration: Zero data loss
- [ ] Backward compatibility: 12 months API support

### User Experience Metrics

- [ ] User adoption: 80% on new navigation within 3 months
- [ ] Training completion: 90% complete onboarding tutorials
- [ ] Satisfaction: >4.5/5 rating for new UI
- [ ] Support tickets: <10% increase during transition

### Business Metrics

- [ ] Positioning: "AWS SC with AI" instead of "Beer Game"
- [ ] Enterprise interest: 50% increase in enterprise demos
- [ ] Revenue: 2x increase from professional features
- [ ] Market perception: Recognized as AWS SC alternative

---

## Timeline Summary

| Phase | Duration | Key Deliverables |
|-------|----------|------------------|
| **Phase 1: Conceptual Reframing** | 2 weeks | Navigation redesign, branding update, messaging |
| **Phase 2: Data Model Refactoring** | 4 weeks | AWS SC entities, table migrations |
| **Phase 3: Service Layer Refactoring** | 6 weeks | AWS SC services, Beer Game modularization |
| **Phase 4: API Refactoring** | 4 weeks | AWS SC endpoints, deprecation plan |
| **Phase 5: Frontend Refactoring** | 6 weeks | New pages, navigation, dashboard |
| **Phase 6: Documentation Refactoring** | 2 weeks | Docs update, guides, migration docs |
| **Phase 7: Branding & Marketing** | 1 week | Branding, landing page, messaging |
| **Total** | **25 weeks (~6 months)** | Full transformation complete |

---

## Next Steps (Immediate Actions)

### Week 1: Planning & Design
1. [ ] Review and approve this refactoring plan
2. [ ] Create detailed Phase 1 task list
3. [ ] Design new navigation structure
4. [ ] Mockup new dashboard
5. [ ] Draft new messaging and value prop

### Week 2: Begin Implementation
1. [ ] Update CLAUDE.md with new project overview
2. [ ] Rename navigation sections
3. [ ] Create new capability flags for AWS SC features
4. [ ] Start database schema design for missing AWS SC entities
5. [ ] Create migration scripts (Phase 2 prep)

### Week 3-4: Data Model Foundation
1. [ ] Implement missing AWS SC entities
2. [ ] Create migration scripts
3. [ ] Test data integrity
4. [ ] Update ORM models
5. [ ] Validate with sample data

---

## Decision Points

### Decision 1: Project Name
- [ ] **Option A**: Rename to "Autonomy"
- [ ] **Option B**: Keep "The Beer Game" name but reposition
- [ ] **Option C**: Hybrid "AWS SC by Autonomy" with Beer Game module

### Decision 2: Migration Approach
- [ ] **Option A**: In-place migration (gradual, safer)
- [ ] **Option B**: Blue-green migration (fast, riskier)

### Decision 3: Beer Game Positioning
- [ ] **Option A**: Dedicated "Simulation" top-level section
- [ ] **Option B**: Sub-feature under "Training & Validation"
- [ ] **Option C**: Optional add-on module (enterprise license)

### Decision 4: Timeline
- [ ] **Option A**: Aggressive (4 months, higher risk)
- [ ] **Option B**: Standard (6 months, balanced)
- [ ] **Option C**: Conservative (9 months, safest)

---

**Status**: ✅ **Plan Complete - Awaiting Approval**

**Recommendation**: Proceed with **6-month standard timeline**, **in-place migration**, **dedicated Simulation section**, and rebranding as **"Autonomy Platform"**.

**Next**: Review this plan → Approve decisions → Begin Week 1 tasks

