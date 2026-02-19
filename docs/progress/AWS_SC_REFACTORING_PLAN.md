# AWS Supply Chain Data Model Refactoring Plan

## Executive Summary

This document outlines the comprehensive refactoring needed to align The Beer Game codebase with AWS Supply Chain (SC) Data Model terminology and logic, particularly around how "plans" (games) are generated and executed.

---

## 1. Core Terminology Mapping

### Current → AWS SC Data Model

| Current Term | AWS SC Term | Notes |
|--------------|-------------|-------|
| **Game** | **Supply Plan** | A game is essentially a supply planning simulation |
| **Round** | **Planning Period** | Each round represents a time bucket in the planning horizon |
| **Player** | **Site Assignment** | Each player represents a site with sourcing rules |
| **Item** | **Product** | Already correct! ✓ |
| **Node** | **Site** | Already correct! ✓ |
| **Lane** | **Transportation Lane** | Already correct! ✓ |
| **PlayerAction** | **Production/Transfer Order** | Player orders are essentially production or transfer plans |
| **PlayerRound** | **Period Snapshot** | Per-period, per-site inventory/metrics |
| **Market Demand** | **Forecast** | Demand signal driving the plan |
| **ItemNodeConfig** | **Inv_Policy + Sourcing_Rule** | Combination of inventory policy and sourcing configuration |

---

## 2. Planning Process Logic Comparison

### Current Beer Game Flow

```
1. Create Game
   ├─ Assign Players to Nodes
   ├─ Set initial inventory
   └─ Define demand pattern

2. Start Game
   └─ Initialize BeerLine engine

3. For Each Round (tick):
   ├─ Market generates demand
   ├─ Each node:
   │  ├─ Receives shipments → updates inventory
   │  ├─ Fulfills demand/backlog → ships downstream
   │  ├─ Receives orders from downstream
   │  └─ Agent decides order quantity → places order upstream
   └─ Save round metrics

4. Finish Game
   └─ Calculate final scores/metrics
```

### AWS SC Manufacturing Planning Flow

```
1. Define Supply Plan Configuration
   ├─ Define products (product table)
   ├─ Define sites (site table)
   ├─ Define transportation lanes (transportation_lane)
   ├─ Define BOMs (product_bom)
   ├─ Define production processes (production_process)
   ├─ Define sourcing rules (sourcing_rules)
   └─ Define inventory policies (inv_policy)

2. Input Planning Data
   ├─ Load inventory levels (inv_level)
   ├─ Load demand forecasts (forecast)
   ├─ Load inbound orders (inbound_order, inbound_order_line)
   └─ Load outbound orders (outbound_order_line)

3. Execute Planning Process (for each product-site combination):
   ├─ 1. Demand Processing
   │  └─ Aggregate forecast and actual orders
   │
   ├─ 2. Inventory Target Calculation
   │  └─ Based on inv_policy (safety stock policies)
   │
   ├─ 3. Production Requirements (if sourcing_rule_type = "manufacture")
   │  ├─ Check production_process for lead times
   │  ├─ Apply frozen horizon (freeze supply during frozen period)
   │  └─ Calculate net requirements
   │
   ├─ 4. BOM Explosion (if sourcing_rule_type = "manufacture")
   │  ├─ Traverse product_bom tree
   │  ├─ Calculate component requirements
   │  ├─ Apply component lead times
   │  └─ Handle alternate groups (prioritize one)
   │
   └─ 5. Net Requirements Calculation
      ├─ For each component:
      │  ├─ Apply demand processing
      │  ├─ Apply target inventory calculation
      │  └─ Consider:
      │     ├─ On-hand inventory
      │     ├─ On-order inventory
      │     ├─ Lead times
      │     └─ Inventory policy
      └─ Generate:
         ├─ Production plans
         ├─ Material plans (component requirements)
         └─ Transfer plans (inter-site movement)

4. Output Planning Results
   ├─ Production plans (what to make, when, where)
   ├─ Material plans (component requirements)
   ├─ Transfer plans (inter-site shipments)
   └─ Purchase recommendations (vendor orders)
```

---

## 3. Proposed Refactoring: Terminology Changes

### 3.1 Model/Table Names

| Current File/Model | Proposed Name | Rationale |
|-------------------|---------------|-----------|
| `models/game.py` → `Game` | `models/supply_plan.py` → `SupplyPlan` | Align with AWS SC "supply plan" concept |
| `models/game.py` → `Round` | `models/planning_period.py` → `PlanningPeriod` | AWS SC uses "planning period" for time buckets |
| `models/game.py` → `PlayerAction` | `models/supply_plan.py` → `PeriodOrder` | Orders placed during a period |
| `models/player.py` → `Player` | `models/site_assignment.py` → `SiteAssignment` | Player = site with strategy assignment |
| `models/player.py` → `PlayerRound` | `models/period_snapshot.py` → `PeriodSnapshot` | Per-period metrics at each site |

### 3.2 Field Names

#### SupplyPlan (formerly Game)

| Current Field | Proposed Field | AWS SC Alignment |
|---------------|----------------|------------------|
| `name` | `plan_name` | Clearer purpose |
| `status` | `plan_status` | Standard AWS SC naming |
| `max_rounds` | `planning_horizon_periods` | AWS SC uses "planning horizon" |
| `current_round` | `current_period` | AWS SC uses "period" |
| `supply_chain_config_id` | ✓ Keep | Already correct |

#### PlanningPeriod (formerly Round)

| Current Field | Proposed Field | AWS SC Alignment |
|---------------|----------------|------------------|
| `game_id` | `supply_plan_id` | Parent reference |
| `round_number` | `period_number` | AWS SC terminology |
| `created_at` | `period_start_dttm` | AWS SC datetime naming |

#### SiteAssignment (formerly Player)

| Current Field | Proposed Field | AWS SC Alignment |
|---------------|----------------|------------------|
| `game_id` | `supply_plan_id` | Parent reference |
| `role` | `site_type` | AWS SC uses site_type (from site table) |
| `player_type` | `assignment_type` | HUMAN/AI assignment |
| `strategy` | `sourcing_strategy` | More specific term |
| `node_id` | `site_id` | AWS SC uses site_id |
| `item_id` | `product_id` | AWS SC uses product_id |

#### PeriodSnapshot (formerly PlayerRound)

| Current Field | Proposed Field | AWS SC Alignment |
|---------------|----------------|------------------|
| `player_id` | `site_assignment_id` | Parent reference |
| `round_id` | `period_id` | Parent reference |
| `inventory` | `on_hand_inventory` | AWS SC inv_level field |
| `backlog` | `backlog_qty` | More explicit |
| `incoming_shipment` | `in_transit_qty` | AWS SC terminology |
| `outgoing_shipment` | `shipped_qty` | More explicit |
| `order_quantity` | `order_qty` | Consistent with AWS SC qty suffix |
| `holding_cost` | `holding_cost_incurred` | Clarify it's actual cost, not rate |
| `backlog_cost` | `backlog_cost_incurred` | Clarify it's actual cost, not rate |

---

## 4. Database Schema Refactoring

### Phase 1: Add New Columns (Non-Breaking)

```sql
-- Supply Chain Config (already aligned)
-- No changes needed ✓

-- Games → Supply Plans
ALTER TABLE games ADD COLUMN plan_name VARCHAR(100);
ALTER TABLE games ADD COLUMN plan_status VARCHAR(20);
ALTER TABLE games ADD COLUMN planning_horizon_periods INT;
ALTER TABLE games ADD COLUMN current_period INT;

-- Populate new columns from existing data
UPDATE games SET
  plan_name = name,
  plan_status = status,
  planning_horizon_periods = max_rounds,
  current_period = current_round;

-- Rounds → Planning Periods
ALTER TABLE rounds ADD COLUMN period_number INT;
ALTER TABLE rounds ADD COLUMN period_start_dttm DATETIME;
ALTER TABLE rounds ADD COLUMN supply_plan_id INT;

UPDATE rounds SET
  period_number = round_number,
  period_start_dttm = created_at,
  supply_plan_id = game_id;

-- Players → Site Assignments
ALTER TABLE players ADD COLUMN site_assignment_type VARCHAR(20);
ALTER TABLE players ADD COLUMN sourcing_strategy VARCHAR(50);
ALTER TABLE players ADD COLUMN supply_plan_id INT;
ALTER TABLE players ADD COLUMN site_id INT;
ALTER TABLE players ADD COLUMN product_id INT;

UPDATE players SET
  site_assignment_type = player_type,
  sourcing_strategy = strategy,
  supply_plan_id = game_id,
  site_id = node_id,
  product_id = item_id;

-- Player Rounds → Period Snapshots
ALTER TABLE player_rounds ADD COLUMN site_assignment_id INT;
ALTER TABLE player_rounds ADD COLUMN period_id INT;
ALTER TABLE player_rounds ADD COLUMN on_hand_inventory INT;
ALTER TABLE player_rounds ADD COLUMN backlog_qty INT;
ALTER TABLE player_rounds ADD COLUMN in_transit_qty INT;
ALTER TABLE player_rounds ADD COLUMN shipped_qty INT;
ALTER TABLE player_rounds ADD COLUMN order_qty INT;
ALTER TABLE player_rounds ADD COLUMN holding_cost_incurred FLOAT;
ALTER TABLE player_rounds ADD COLUMN backlog_cost_incurred FLOAT;

UPDATE player_rounds SET
  site_assignment_id = player_id,
  period_id = round_id,
  on_hand_inventory = inventory,
  backlog_qty = backlog,
  in_transit_qty = incoming_shipment,
  shipped_qty = outgoing_shipment,
  order_qty = order_quantity,
  holding_cost_incurred = holding_cost,
  backlog_cost_incurred = backlog_cost;
```

### Phase 2: Update Python Models

```python
# backend/app/models/supply_plan.py (formerly game.py)

class SupplyPlanStatus(str, Enum):
    CREATED = "CREATED"
    STARTED = "STARTED"
    PERIOD_IN_PROGRESS = "PERIOD_IN_PROGRESS"  # Changed from ROUND_IN_PROGRESS
    PERIOD_COMPLETED = "PERIOD_COMPLETED"      # Changed from ROUND_COMPLETED
    FINISHED = "FINISHED"

class SupplyPlan(Base):
    __tablename__ = "supply_plans"  # New table name

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plan_name: Mapped[str] = mapped_column(String(100), index=True)
    plan_status: Mapped[SupplyPlanStatus] = mapped_column(SQLEnum(SupplyPlanStatus), default=SupplyPlanStatus.CREATED)
    planning_horizon_periods: Mapped[int] = mapped_column(Integer, default=20)
    current_period: Mapped[int] = mapped_column(Integer, default=0)
    supply_chain_config_id: Mapped[int] = mapped_column(Integer, ForeignKey("supply_chain_configs.id"))

    # Relationships
    periods: Mapped[List["PlanningPeriod"]] = relationship("PlanningPeriod", back_populates="supply_plan", cascade="all, delete-orphan")
    site_assignments: Mapped[List["SiteAssignment"]] = relationship("SiteAssignment", back_populates="supply_plan", cascade="all, delete-orphan")
    supply_chain_config: Mapped["SupplyChainConfig"] = relationship("SupplyChainConfig", back_populates="supply_plans")

class PlanningPeriod(Base):
    __tablename__ = "planning_periods"  # New table name

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    supply_plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("supply_plans.id", ondelete="CASCADE"))
    period_number: Mapped[int] = mapped_column(Integer)
    period_start_dttm: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.utcnow())

    # Relationships
    supply_plan: Mapped["SupplyPlan"] = relationship("SupplyPlan", back_populates="periods")
    snapshots: Mapped[List["PeriodSnapshot"]] = relationship("PeriodSnapshot", back_populates="period", cascade="all, delete-orphan")
```

### Phase 3: Update Services

```python
# backend/app/services/supply_plan_service.py (formerly mixed_game_service.py)

class SupplyPlanService:
    """
    Service for executing supply plans (simulations).

    Aligns with AWS SC Manufacturing Planning Process:
    1. Demand Processing
    2. Inventory Target Calculation
    3. Production Requirements (if sourcing_rule_type = "manufacture")
    4. BOM Explosion (if sourcing_rule_type = "manufacture")
    5. Net Requirements Calculation
    """

    def create_supply_plan(self, config_id: int, plan_name: str, ...) -> SupplyPlan:
        """Create a new supply plan from a supply chain configuration."""
        pass

    def start_supply_plan(self, plan_id: int) -> SupplyPlan:
        """Initialize supply plan execution."""
        pass

    def execute_planning_period(self, plan_id: int) -> PlanningPeriod:
        """Execute one planning period (tick) of the supply plan."""
        pass

    def process_site_demand(self, site_assignment: SiteAssignment, period: PlanningPeriod):
        """Process demand for a site (AWS SC Step 1: Demand Processing)."""
        pass

    def calculate_inventory_target(self, site_assignment: SiteAssignment):
        """Calculate target inventory based on inv_policy (AWS SC Step 2)."""
        pass

    def calculate_production_requirements(self, site_assignment: SiteAssignment):
        """Calculate production requirements (AWS SC Step 3)."""
        pass

    def explode_bom(self, site_assignment: SiteAssignment, product_id: int, quantity: float):
        """Explode BOM to calculate component requirements (AWS SC Step 4)."""
        pass

    def calculate_net_requirements(self, site_assignment: SiteAssignment):
        """Calculate net requirements considering inventory (AWS SC Step 5)."""
        pass
```

---

## 5. Code Refactoring Strategy

### 5.1 Backward Compatibility Approach

**Option A: Gradual Migration (Recommended)**
1. Add new fields alongside old fields
2. Populate both during transition period
3. Update APIs to accept both terminologies
4. Deprecate old fields with warnings
5. Remove old fields in major version bump

**Option B: Big Bang Migration**
1. Create migration script
2. Update all code at once
3. Run migration on database
4. Higher risk, faster completion

### 5.2 File Renaming Plan

```
backend/app/
├── models/
│   ├── game.py → supply_plan.py
│   ├── player.py → site_assignment.py
│   └── supply_chain_config.py (no change ✓)
│
├── services/
│   ├── mixed_game_service.py → supply_plan_service.py
│   ├── agent_game_service.py → automated_plan_service.py
│   ├── engine.py → planning_engine.py
│   └── agents.py → sourcing_strategies.py
│
├── api/endpoints/
│   ├── mixed_game.py → supply_plan.py
│   └── agent_game.py → automated_plan.py
│
└── schemas/
    ├── game.py → supply_plan.py
    └── player.py → site_assignment.py
```

### 5.3 Frontend Terminology Updates

```javascript
// Current: Game, Round, Player
const game = await api.getGame(gameId);
const round = await api.playRound(gameId);
const players = game.players;

// Proposed: SupplyPlan, Period, SiteAssignment
const supplyPlan = await api.getSupplyPlan(planId);
const period = await api.executePlanningPeriod(planId);
const siteAssignments = supplyPlan.siteAssignments;
```

---

## 6. AWS SC Manufacturing Planning Integration

### 6.1 New Tables to Add (Optional, for full AWS SC compatibility)

```sql
-- Already have from supply_chain_config.py:
-- ✓ site (Node)
-- ✓ product (Item)
-- ✓ transportation_lane (Lane)
-- ✓ product_bom (Node.attributes.bill_of_materials)
-- ✓ inv_policy (ItemNodeConfig)
-- ✓ sourcing_rules (ItemNodeSupplier)

-- Need to add:

CREATE TABLE production_process (
    production_process_id VARCHAR(100) PRIMARY KEY,
    product_id INT REFERENCES items(id),
    site_id INT REFERENCES nodes(id),
    setup_time FLOAT,
    setup_time_uom VARCHAR(20),
    operation_time FLOAT,
    operation_time_uom VARCHAR(20),
    frozen_horizon_days INT DEFAULT 7
);

CREATE TABLE forecast (
    snapshot_date DATE NOT NULL,
    site_id INT REFERENCES nodes(id),
    product_id INT REFERENCES items(id),
    mean FLOAT,
    p10 FLOAT,
    p50 FLOAT,
    p90 FLOAT,
    forecast_start_dttm TIMESTAMP,
    forecast_end_dttm TIMESTAMP,
    PRIMARY KEY (snapshot_date, site_id, product_id)
);

CREATE TABLE inv_level (
    snapshot_date DATE NOT NULL,
    site_id INT REFERENCES nodes(id),
    product_id INT REFERENCES items(id),
    on_hand_inventory FLOAT,
    allocated_inventory FLOAT,
    bound_inventory FLOAT,
    PRIMARY KEY (snapshot_date, site_id, product_id)
);
```

### 6.2 Planning Process Implementation

```python
def execute_aws_sc_planning_process(self, plan: SupplyPlan, period: PlanningPeriod):
    """
    Execute AWS SC Manufacturing Planning Process for all product-site combinations.

    Reference: https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/manufacturing_plans_planning_process.html
    """

    # Get all site assignments (product-site combinations)
    site_assignments = plan.site_assignments

    for assignment in site_assignments:
        # Step 1: Demand Processing (shared with Auto Replenishment)
        demand = self.process_demand(assignment, period)

        # Step 2: Inventory Target Calculation
        target_inventory = self.calculate_inventory_target(assignment)

        # Get sourcing rule
        sourcing_rule = self.get_sourcing_rule(assignment.site_id, assignment.product_id)

        if sourcing_rule.sourcing_rule_type == "manufacture":
            # Step 3: Production Requirements
            production_req = self.calculate_production_requirements(
                assignment=assignment,
                demand=demand,
                target_inventory=target_inventory,
                period=period
            )

            # Step 4: BOM Explosion
            component_requirements = self.explode_bom(
                site_id=assignment.site_id,
                product_id=assignment.product_id,
                quantity=production_req.quantity,
                planning_horizon_start=period.period_start_dttm,
                planning_horizon_end=period.period_start_dttm + timedelta(days=30)
            )

            # Step 5: Net Requirements Calculation for each component
            for comp_req in component_requirements:
                self.process_demand(comp_req.component_assignment, period)
                self.calculate_inventory_target(comp_req.component_assignment)
                self.calculate_net_requirements(comp_req.component_assignment)

        elif sourcing_rule.sourcing_rule_type == "transfer":
            # Handle transfer from another site
            self.create_transfer_plan(assignment, period)

        elif sourcing_rule.sourcing_rule_type == "buy":
            # Handle external purchase
            self.create_purchase_recommendation(assignment, period)
```

---

## 7. Implementation Roadmap

### Phase 1: Non-Breaking Additions (Week 1-2)
- ✅ Add new columns to existing tables
- ✅ Populate new columns from existing data
- ✅ Update models to include both old and new fields
- ✅ Add aliases in Python models (e.g., `game` property returning `supply_plan`)
- ✅ Update documentation with new terminology

### Phase 2: Service Layer Refactoring (Week 3-4)
- Create new service files with AWS SC terminology
- Implement AWS SC planning process flow
- Keep old service files as wrappers calling new services
- Update business logic to use new field names internally
- Add deprecation warnings to old API endpoints

### Phase 3: API & Frontend Updates (Week 5-6)
- Create new API endpoints with new terminology
- Update frontend components to use new API endpoints
- Update UI labels (Game → Supply Plan, Round → Period, etc.)
- Keep old endpoints functional with deprecation notices
- Update all documentation and README files

### Phase 4: Database Migration (Week 7-8)
- Create comprehensive migration script
- Test migration on dev/staging environments
- Rename tables (games → supply_plans, etc.)
- Drop old columns after confirming no dependencies
- Update all foreign key references
- Final cleanup and verification

### Phase 5: Validation & Cleanup (Week 9-10)
- End-to-end testing of all workflows
- Performance testing with new schema
- Remove deprecated code
- Update all tests
- Final documentation review
- Release notes and migration guide for users

---

## 8. Key Benefits of Refactoring

1. **Industry Standard Alignment**: Terminology matches AWS SC, making it easier for supply chain professionals to understand
2. **Conceptual Clarity**: "Supply Plan" better describes what the system does than "Game"
3. **Scalability**: AWS SC data model is designed for enterprise-scale planning
4. **Integration Readiness**: Easier to integrate with real AWS SC instances or other planning systems
5. **BOM-Aware Planning**: Proper implementation of BOM explosion and component requirements
6. **Multi-Sourcing Support**: Native support for primary/secondary sourcing rules
7. **Frozen Horizon**: Implement production planning best practices (don't change supply during frozen period)

---

## 9. Migration Checklist

### Database
- [ ] Add new columns to existing tables
- [ ] Populate new columns from existing data
- [ ] Create indexes on new foreign keys
- [ ] Rename tables (if doing big bang migration)
- [ ] Drop old columns (final step)

### Backend Models
- [ ] Rename model files
- [ ] Update class names
- [ ] Update field names
- [ ] Update relationships
- [ ] Update enums (GameStatus → SupplyPlanStatus)

### Backend Services
- [ ] Rename service files
- [ ] Update method names
- [ ] Implement AWS SC planning process
- [ ] Update business logic
- [ ] Add BOM explosion logic
- [ ] Add frozen horizon support

### Backend APIs
- [ ] Create new endpoint files
- [ ] Update route paths (/games → /supply-plans)
- [ ] Update request/response schemas
- [ ] Add deprecation warnings to old endpoints
- [ ] Update API documentation

### Frontend
- [ ] Update API service calls
- [ ] Rename components (GameBoard → SupplyPlanDashboard)
- [ ] Update UI labels and text
- [ ] Update routes (/game → /supply-plan)
- [ ] Update state management

### Tests
- [ ] Update unit tests
- [ ] Update integration tests
- [ ] Update E2E tests
- [ ] Add tests for new AWS SC planning logic

### Documentation
- [ ] Update README
- [ ] Update API docs
- [ ] Update user guide
- [ ] Create migration guide
- [ ] Update CLAUDE.md

---

## 10. Recommendation

**Start with Gradual Migration (Option A)**:
1. Implement Phase 1 (Non-Breaking Additions) immediately
2. This allows both terminologies to coexist
3. Provides time to update frontend and tests
4. Lower risk of breaking existing functionality
5. Can complete full migration in 10 weeks with thorough testing

**Priority: Align with AWS SC Manufacturing Planning Process**
- The planning logic is more important than just terminology
- Implement proper BOM explosion
- Add frozen horizon support
- Support multi-sourcing rules
- These features add real value beyond just renaming

Would you like me to start implementing any specific phase of this refactoring plan?
