# Phase 3: Full ATP/CTP Integration Plan

**Duration**: 3 weeks (Week 8-10)
**Prerequisites**: Phase 0 ✅, Phase 1 ✅, Phase 2 ✅
**Start Date**: 2026-01-28
**Target Completion**: 2026-02-18

---

## Executive Summary

Phase 3 integrates **Available to Promise (ATP)** and **Capable to Promise (CTP)** calculations into The Beer Game's planning and execution workflows. This provides real-time inventory availability checks, capacity-constrained promise dates, and multi-period projection capabilities.

### Key Objectives

1. **Real-Time ATP Calculation**: Connect ATP logic to game state for instant availability checks
2. **CTP for Manufacturers**: Add production capacity constraints and capable-to-promise dates
3. **Multi-Period ATP Projection**: Rolling horizon ATP forecasts (4-8 weeks ahead)
4. **Allocation Conflict Resolution**: Handle competing customer demands when ATP < Total Demand

### Value Proposition

- **Improved Decision Quality**: Human players see real-time inventory constraints before committing
- **Capacity Awareness**: Manufacturers understand production bottlenecks
- **Proactive Planning**: Multi-period projections enable better replenishment decisions
- **Realistic Simulation**: ATP/CTP logic mirrors real-world supply chain systems (SAP, Kinaxis, AWS SC)

---

## Background: ATP vs CTP

### Available to Promise (ATP)

**Definition**: Uncommitted inventory available for new customer orders

**Formula**:
```
ATP = On-Hand Inventory + Scheduled Receipts - Allocated Orders - Safety Stock Reserve
```

**Use Case**: Distribution/inventory nodes (Retailer, Wholesaler, Distributor, DC)

**Example**:
- On-hand: 500 units
- Pipeline: 200 units arriving Week 15
- Allocated: 300 units (committed to existing customers)
- Safety stock: 50 units (reserved buffer)
- **ATP = 500 + 200 - 300 - 50 = 350 units**

### Capable to Promise (CTP)

**Definition**: Production capacity available for new orders, considering lead times and resource constraints

**Formula**:
```
CTP = Available Production Capacity × Yield Rate × BOM Ratios
```

**Use Case**: Manufacturing nodes (Factory, Component Supplier, Case Manufacturer)

**Example**:
- Production capacity: 1000 units/week
- Current commitments: 600 units/week
- Yield rate: 95% (5% scrap)
- **CTP = (1000 - 600) × 0.95 = 380 units available to promise**

### Time-Phased ATP/CTP

**Multi-Period View**:
```
Week | On-Hand | Receipts | Demand | ATP | Cumulative ATP
-----|---------|----------|--------|-----|----------------
 15  |   500   |   200    |  300   | 400 |      400
 16  |   400   |   150    |  250   | 300 |      700
 17  |   300   |   200    |  200   | 300 |     1000
 18  |   300   |     0    |  350   |  -50|      950
```

**Insight**: Week 18 shows ATP shortfall (-50), triggering expedite recommendation.

---

## Architecture

### Current State (Before Phase 3)

**ATP Calculation**:
- Basic calculation in `mixed_game_service.py:_calculate_atp()`
- Single-period only (current round)
- No safety stock consideration
- No allocation conflict resolution

**Limitations**:
- No forward-looking projection
- No manufacturer capacity checks
- Manual conflict resolution (human must decide allocations)
- No integration with planning workflows (MPS/MRP)

### Target State (After Phase 3)

**ATP Service** (`backend/app/services/atp_service.py`):
- Real-time ATP calculation with safety stock reserves
- Multi-period rolling horizon projection (4-8 weeks)
- Allocation logic for competing demands
- Integration with game state and planning data

**CTP Service** (`backend/app/services/ctp_service.py`):
- Production capacity modeling
- BOM explosion for component ATP
- Yield rate and scrap handling
- Lead time offsetting for promise dates

**API Endpoints**:
- `GET /api/mixed-games/{game_id}/atp/{player_id}` - Current ATP
- `GET /api/mixed-games/{game_id}/atp-projection/{player_id}?periods=8` - Multi-period ATP
- `GET /api/mixed-games/{game_id}/ctp/{player_id}` - Manufacturer CTP
- `POST /api/mixed-games/{game_id}/allocate-atp` - Resolve allocation conflicts

**Frontend Components**:
- `ATPProjectionChart.jsx` - Visual timeline of ATP over next 8 weeks
- `AllocationConflictDialog.jsx` - UI for resolving competing customer demands
- Enhanced `FulfillmentForm.jsx` with ATP warnings

---

## Implementation Phases

### Week 8: Backend ATP/CTP Services

#### Task 8.1: ATP Service (Day 1-2)
**File**: `backend/app/services/atp_service.py` (NEW, ~400 lines)

**Core Methods**:
```python
class ATPService:
    def calculate_current_atp(
        self, player: Player, include_safety_stock: bool = True
    ) -> ATPResult:
        """
        Calculate single-period ATP for player node.

        Returns:
            ATPResult with on_hand, receipts, allocated, safety_stock, atp
        """
        pass

    def project_atp_multi_period(
        self, player: Player, periods: int = 8
    ) -> List[ATPPeriod]:
        """
        Project ATP over rolling horizon (4-8 weeks).

        Uses:
        - Demand forecast (from agent or historical avg)
        - Scheduled receipts (pipeline shipments)
        - Planned allocations (future commitments)

        Returns:
            List of ATPPeriod objects with week-by-week breakdown
        """
        pass

    def allocate_to_customers(
        self, player: Player, demands: List[CustomerDemand]
    ) -> AllocationResult:
        """
        Allocate available ATP to competing customer demands.

        Logic:
        1. Priority-based (high-priority customers first)
        2. Proportional (split ATP proportionally)
        3. FCFS (first-come-first-served)

        Returns:
            AllocationResult with customer_id → allocated_qty mapping
        """
        pass
```

**Data Structures**:
```python
@dataclass
class ATPResult:
    on_hand: int
    scheduled_receipts: int
    allocated_orders: int
    safety_stock: int
    atp: int
    timestamp: str

@dataclass
class ATPPeriod:
    period: int  # Week number
    starting_inventory: int
    scheduled_receipts: int
    forecasted_demand: int
    planned_allocations: int
    ending_atp: int
    cumulative_atp: int

@dataclass
class AllocationResult:
    allocations: Dict[int, int]  # customer_id → qty
    unmet_demand: Dict[int, int]  # customer_id → unmet qty
    allocation_method: str  # "priority", "proportional", "fcfs"
```

#### Task 8.2: CTP Service (Day 3-4)
**File**: `backend/app/services/ctp_service.py` (NEW, ~350 lines)

**Core Methods**:
```python
class CTPService:
    def calculate_current_ctp(
        self, player: Player, item_id: int
    ) -> CTPResult:
        """
        Calculate CTP for manufacturer node.

        Steps:
        1. Get production capacity from node configuration
        2. Subtract current commitments (WIP + scheduled production)
        3. Apply yield rate (account for scrap)
        4. Check component ATP (BOM explosion)

        Returns:
            CTPResult with capacity, commitments, available, earliest_date
        """
        pass

    def project_ctp_multi_period(
        self, player: Player, item_id: int, periods: int = 8
    ) -> List[CTPPeriod]:
        """
        Project CTP over rolling horizon.

        Considers:
        - Capacity loading (scheduled production)
        - Component availability (BOM)
        - Maintenance windows (capacity reductions)

        Returns:
            List of CTPPeriod objects
        """
        pass

    def calculate_promise_date(
        self, player: Player, item_id: int, quantity: int
    ) -> PromiseDateResult:
        """
        Calculate earliest possible delivery date for quantity.

        Logic:
        1. Check if quantity <= immediate CTP → promise today + lead time
        2. If not, find future period where CTP >= quantity
        3. Account for production lead time + shipping lead time

        Returns:
            PromiseDateResult with earliest_date, confidence, constraints
        """
        pass
```

**Data Structures**:
```python
@dataclass
class CTPResult:
    production_capacity: int
    current_commitments: int
    yield_rate: float
    available_capacity: int
    component_constraints: Dict[int, int]  # item_id → shortfall
    ctp: int
    timestamp: str

@dataclass
class CTPPeriod:
    period: int
    capacity: int
    commitments: int
    available: int
    component_atp: Dict[int, int]  # item_id → ATP
    ctp: int

@dataclass
class PromiseDateResult:
    earliest_date: int  # Round number
    quantity: int
    confidence: float  # 0.0-1.0
    constraints: List[str]  # ["capacity", "component_X", "lead_time"]
```

#### Task 8.3: Integration with Existing Services (Day 5)
**Files to Modify**:
1. `backend/app/services/mixed_game_service.py`
   - Replace `_calculate_atp()` with call to `ATPService.calculate_current_atp()`
   - Add CTP check for manufacturer nodes during replenishment phase

2. `backend/app/services/agent_recommendation_service.py`
   - Use `ATPService` for more accurate impact preview calculations
   - Use `CTPService` for manufacturer agent recommendations

3. `backend/app/services/business_impact_service.py`
   - Integrate ATP/CTP projections into decision impact simulation

### Week 9: API Endpoints & WebSocket Events

#### Task 9.1: ATP/CTP API Endpoints (Day 1-2)
**File**: `backend/app/api/endpoints/mixed_game.py` (Modify, +150 lines)

**New Endpoints**:
```python
@router.get("/mixed-games/{game_id}/atp/{player_id}")
def get_current_atp(game_id: int, player_id: int) -> ATPResult:
    """Get real-time ATP for player node"""
    pass

@router.get("/mixed-games/{game_id}/atp-projection/{player_id}")
def get_atp_projection(
    game_id: int,
    player_id: int,
    periods: int = 8
) -> List[ATPPeriod]:
    """Get multi-period ATP projection"""
    pass

@router.get("/mixed-games/{game_id}/ctp/{player_id}")
def get_current_ctp(
    game_id: int,
    player_id: int,
    item_id: int
) -> CTPResult:
    """Get CTP for manufacturer node"""
    pass

@router.post("/mixed-games/{game_id}/allocate-atp")
def allocate_atp_to_customers(
    game_id: int,
    player_id: int,
    demands: List[CustomerDemandRequest]
) -> AllocationResult:
    """Allocate available ATP to competing demands"""
    pass

@router.get("/mixed-games/{game_id}/promise-date/{player_id}")
def calculate_promise_date(
    game_id: int,
    player_id: int,
    item_id: int,
    quantity: int
) -> PromiseDateResult:
    """Calculate earliest delivery date for quantity"""
    pass
```

#### Task 9.2: WebSocket Events (Day 2-3)
**File**: `backend/app/api/endpoints/websocket.py` (Modify, +60 lines)

**New WebSocket Messages**:
```python
# ATP threshold breach
{
    "type": "atp_threshold_breach",
    "game_id": 1,
    "player_id": 3,
    "current_atp": 45,
    "threshold": 100,
    "message": "ATP below safety threshold (45 < 100). Consider expediting replenishment.",
    "severity": "warning"
}

# CTP capacity constraint
{
    "type": "ctp_capacity_constraint",
    "game_id": 1,
    "player_id": 4,
    "demand": 500,
    "available_ctp": 380,
    "shortfall": 120,
    "message": "Production capacity insufficient. Demand exceeds CTP by 120 units.",
    "severity": "error"
}

# Allocation conflict detected
{
    "type": "allocation_conflict",
    "game_id": 1,
    "player_id": 2,
    "total_demand": 600,
    "available_atp": 400,
    "customers": [
        {"customer_id": 1, "demand": 300},
        {"customer_id": 2, "demand": 300}
    ],
    "message": "Multiple customers requesting 600 units, but only 400 ATP available. Resolution required.",
    "severity": "warning"
}
```

#### Task 9.3: Database Schema Updates (Day 3)
**File**: `backend/alembic/versions/20260128_atp_ctp_tracking.py` (NEW)

**New Tables**:
```sql
-- Track ATP snapshots for historical analysis
CREATE TABLE atp_snapshots (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    game_id INT NOT NULL,
    player_id INT NOT NULL,
    round_number INT NOT NULL,
    on_hand INT NOT NULL,
    scheduled_receipts INT NOT NULL,
    allocated_orders INT NOT NULL,
    safety_stock INT NOT NULL,
    atp INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(id),
    FOREIGN KEY (player_id) REFERENCES players(id),
    INDEX idx_atp_game_player_round (game_id, player_id, round_number)
);

-- Track CTP calculations for manufacturers
CREATE TABLE ctp_snapshots (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    game_id INT NOT NULL,
    player_id INT NOT NULL,
    item_id INT NOT NULL,
    round_number INT NOT NULL,
    production_capacity INT NOT NULL,
    current_commitments INT NOT NULL,
    yield_rate DECIMAL(5,4) NOT NULL,
    ctp INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(id),
    FOREIGN KEY (player_id) REFERENCES players(id),
    INDEX idx_ctp_game_player_round (game_id, player_id, round_number)
);

-- Track allocation decisions
CREATE TABLE atp_allocations (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    game_id INT NOT NULL,
    player_id INT NOT NULL,
    round_number INT NOT NULL,
    customer_id INT NOT NULL,  -- downstream player_id
    demand INT NOT NULL,
    allocated INT NOT NULL,
    unmet INT NOT NULL,
    allocation_method VARCHAR(50) NOT NULL,  -- priority, proportional, fcfs
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(id),
    FOREIGN KEY (player_id) REFERENCES players(id),
    INDEX idx_alloc_game_player_round (game_id, player_id, round_number)
);
```

### Week 10: Frontend UI Components & Integration

#### Task 10.1: ATP Projection Chart (Day 1-2)
**File**: `frontend/src/components/game/ATPProjectionChart.jsx` (NEW, ~280 lines)

**Features**:
- Line chart showing ATP over 8-week horizon
- Color-coded zones: green (healthy), yellow (low), red (stockout)
- Tooltips with detailed breakdown per week
- Safety stock threshold line
- Demand forecast overlay

**UI Design**:
```
ATP Projection (Next 8 Weeks)
┌─────────────────────────────────────────────────────────┐
│ 500 ┤                                                    │
│     │    ╭──╮                                            │
│ 400 ┤   ╱    ╰─╮                   ← Current ATP         │
│     │  ╱       ╰╮                                        │
│ 300 ┤─╯         ╰─╮              ← Safety Stock (100)   │
│     │             ╰──╮                                   │
│ 200 ┤                ╰───╮                               │
│     │                    ╰──╮                            │
│ 100 ┤                       ╰─────╮  ⚠ ATP Breach       │
│     │                              ╰───╮                 │
│   0 ┤                                  ╰──────           │
│     └────┬────┬────┬────┬────┬────┬────┬────            │
│          W15  W16  W17  W18  W19  W20  W21  W22         │
└─────────────────────────────────────────────────────────┘

Legend: ━ ATP  - - Safety Stock  ⚠ Projected Shortfall
```

#### Task 10.2: Allocation Conflict Dialog (Day 2-3)
**File**: `frontend/src/components/game/AllocationConflictDialog.jsx` (NEW, ~320 lines)

**Features**:
- Display competing customer demands
- Show available ATP and total shortfall
- Three allocation strategies: Priority, Proportional, FCFS
- Preview allocation outcome before confirming
- Business impact summary (which customers get shorted)

**UI Design**:
```
┌────────────────── Allocation Conflict ─────────────────────┐
│                                                             │
│  Total Demand: 600 units                                   │
│  Available ATP: 400 units                                  │
│  Shortfall: 200 units                                      │
│                                                             │
│  Customers Requesting:                                     │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Customer A (Priority: High)   300 units             │  │
│  │ Customer B (Priority: Medium) 300 units             │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  Select Allocation Strategy:                               │
│  ○ Priority-Based (High priority first)                    │
│  ● Proportional (Split 2:2 ratio)                          │
│  ○ First-Come-First-Served                                 │
│                                                             │
│  Preview Allocation:                                       │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ Customer A: 200 units (100 unmet) 67% fill rate     │  │
│  │ Customer B: 200 units (100 unmet) 67% fill rate     │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                             │
│  [Cancel] [Confirm Allocation]                             │
└─────────────────────────────────────────────────────────────┘
```

#### Task 10.3: Enhanced Fulfillment Form with ATP Warnings (Day 3-4)
**File**: `frontend/src/components/game/FulfillmentForm.jsx` (Modify, +120 lines)

**New Features**:
- Real-time ATP check as user types quantity
- Warning alert if shipment exceeds ATP
- Link to ATP projection chart
- Allocation conflict detection for multiple downstream customers

**Enhanced UI**:
```jsx
{/* ATP Warning Section */}
{fulfillQty > atp && (
  <Alert severity="warning" icon={<WarningIcon />}>
    <AlertTitle>ATP Exceeded</AlertTitle>
    <Typography variant="body2">
      You are shipping {fulfillQty - atp} units more than ATP ({atp} units).
      This may impact future customer commitments.
    </Typography>
    <Button
      size="small"
      startIcon={<InfoIcon />}
      onClick={() => setShowATPProjection(true)}
      sx={{ mt: 1 }}
    >
      View ATP Projection
    </Button>
  </Alert>
)}

{/* ATP Projection Chart (Collapsible) */}
<Collapse in={showATPProjection}>
  <ATPProjectionChart
    gameId={gameId}
    playerId={playerId}
    currentRound={currentRound}
  />
</Collapse>

{/* Allocation Conflict Detection */}
{hasMultipleCustomers && totalDemand > atp && (
  <Alert severity="error" icon={<WarningIcon />}>
    <AlertTitle>Allocation Conflict</AlertTitle>
    <Typography variant="body2">
      Multiple customers requesting {totalDemand} units, but only {atp} ATP available.
    </Typography>
    <Button
      size="small"
      onClick={() => setAllocationDialogOpen(true)}
      sx={{ mt: 1 }}
    >
      Resolve Allocation
    </Button>
  </Alert>
)}
```

#### Task 10.4: CTP Display for Manufacturers (Day 4)
**File**: `frontend/src/components/game/ReplenishmentForm.jsx` (Modify, +80 lines)

**New Features**:
- Display CTP for manufacturer nodes
- Show production capacity utilization
- Component ATP constraints (if BOM exists)
- Promise date calculation for large orders

**UI Addition**:
```jsx
{/* CTP Section (Manufacturers Only) */}
{nodeType === 'manufacturer' && (
  <Box sx={{ p: 2, backgroundColor: 'info.light', borderRadius: 1 }}>
    <Typography variant="subtitle2" gutterBottom>
      Capable to Promise (CTP)
    </Typography>
    <Stack direction="row" spacing={3}>
      <Box>
        <Typography variant="caption" color="text.secondary">
          Production Capacity
        </Typography>
        <Typography variant="body2">
          {ctpData.production_capacity} units/round
        </Typography>
      </Box>
      <Box>
        <Typography variant="caption" color="text.secondary">
          Current Commitments
        </Typography>
        <Typography variant="body2">
          {ctpData.current_commitments} units
        </Typography>
      </Box>
      <Box>
        <Typography variant="caption" color="text.secondary">
          Available CTP
        </Typography>
        <Typography variant="body2" color="primary.main">
          {ctpData.ctp} units
        </Typography>
        <Typography variant="caption" color="text.secondary">
          ({ctpData.ctp / ctpData.production_capacity * 100:.0f}% capacity)
        </Typography>
      </Box>
    </Stack>

    {/* Component Constraints */}
    {ctpData.component_constraints && Object.keys(ctpData.component_constraints).length > 0 && (
      <Alert severity="warning" sx={{ mt: 2 }} icon={<WarningIcon />}>
        <AlertTitle>Component Constraints</AlertTitle>
        <Typography variant="caption">
          Production limited by component availability:
          {Object.entries(ctpData.component_constraints).map(([item, shortfall]) => (
            <div key={item}>{item}: {shortfall} units short</div>
          ))}
        </Typography>
      </Alert>
    )}
  </Box>
)}
```

#### Task 10.5: Integration Testing & Documentation (Day 5)
**Activities**:
1. End-to-end test: 4-player game with ATP/CTP features
2. Test allocation conflict resolution workflow
3. Test ATP projection updates in real-time
4. Test CTP constraints for manufacturers
5. Update user documentation with ATP/CTP explanations
6. Update API documentation

---

## Success Criteria

### Backend ✅
- [ ] `ATPService` calculates accurate single-period ATP
- [ ] Multi-period ATP projection returns 8-week forecast
- [ ] `CTPService` calculates production capacity accurately
- [ ] Allocation logic resolves conflicts using 3 strategies
- [ ] API endpoints functional (5 new endpoints)
- [ ] Database snapshots record ATP/CTP history
- [ ] WebSocket events trigger on ATP threshold breach

### Frontend ✅
- [ ] ATP Projection Chart displays 8-week rolling horizon
- [ ] Allocation Conflict Dialog allows strategy selection
- [ ] FulfillmentForm shows ATP warnings in real-time
- [ ] ReplenishmentForm displays CTP for manufacturers
- [ ] Components integrate with GameRoom.jsx

### Integration ✅
- [ ] ATP updates in real-time during gameplay
- [ ] CTP checks constrain manufacturer production orders
- [ ] Allocation conflicts trigger resolution workflow
- [ ] ATP projections influence agent recommendations
- [ ] WebSocket broadcasts ATP/CTP events correctly

### Performance ✅
- [ ] ATP calculation: <50ms
- [ ] Multi-period projection: <200ms
- [ ] CTP calculation with BOM explosion: <150ms
- [ ] Allocation resolution: <100ms

### Testing ✅
- [ ] Unit tests passing (>85% coverage for new services)
- [ ] Integration tests passing (ATP/CTP workflows)
- [ ] Manual testing complete (all scenarios)

---

## Technical Specifications

### ATP Calculation Algorithm

**Single-Period ATP**:
```python
def calculate_current_atp(player: Player) -> int:
    """
    ATP = On-Hand + Scheduled Receipts - Allocated - Safety Stock
    """
    on_hand = player.current_stock

    # Scheduled receipts = in-transit shipments arriving this round
    scheduled_receipts = sum(
        shipment.quantity
        for shipment in player.pipeline_shipments
        if shipment.arrival_round == current_round
    )

    # Allocated orders = downstream orders already committed
    allocated = sum(
        order.quantity
        for order in player.downstream_commitments
        if order.status == 'CONFIRMED'
    )

    # Safety stock from inventory policy
    safety_stock = player.safety_stock_target or 0

    atp = on_hand + scheduled_receipts - allocated - safety_stock
    return max(0, atp)  # ATP cannot be negative
```

**Multi-Period ATP Projection**:
```python
def project_atp_multi_period(player: Player, periods: int = 8) -> List[ATPPeriod]:
    """
    Rolling horizon ATP projection.
    """
    projections = []

    # Initialize with current state
    current_inventory = player.current_stock

    for period in range(1, periods + 1):
        # Get scheduled receipts for this period
        receipts = sum(
            shipment.quantity
            for shipment in player.pipeline_shipments
            if shipment.arrival_round == current_round + period
        )

        # Forecast demand (use agent's forecast or historical avg)
        forecasted_demand = forecast_demand_for_period(player, period)

        # Planned allocations (future confirmed orders)
        allocations = sum(
            order.quantity
            for order in player.downstream_commitments
            if order.promised_round == current_round + period
        )

        # Calculate ending inventory
        ending_inventory = current_inventory + receipts - forecasted_demand

        # ATP = ending inventory - allocations - safety stock
        atp = max(0, ending_inventory - allocations - player.safety_stock_target)

        projections.append(ATPPeriod(
            period=current_round + period,
            starting_inventory=current_inventory,
            scheduled_receipts=receipts,
            forecasted_demand=forecasted_demand,
            planned_allocations=allocations,
            ending_atp=atp,
            cumulative_atp=sum(p.ending_atp for p in projections)
        ))

        # Update for next iteration
        current_inventory = ending_inventory

    return projections
```

### CTP Calculation Algorithm

**Single-Period CTP**:
```python
def calculate_current_ctp(player: Player, item_id: int) -> CTPResult:
    """
    CTP = (Capacity - Commitments) × Yield × Component_Availability
    """
    # Get production capacity from node configuration
    capacity = player.node.production_capacity_per_round

    # Current production commitments
    commitments = sum(
        order.quantity
        for order in player.production_schedule
        if order.status in ['IN_PROGRESS', 'SCHEDULED']
    )

    # Available capacity
    available_capacity = capacity - commitments

    # Apply yield rate (account for scrap)
    yield_rate = player.node.yield_rate or 1.0
    available_after_yield = int(available_capacity * yield_rate)

    # Check component ATP (BOM explosion)
    bom = get_bom_for_item(item_id)
    component_constraints = {}
    max_producible = available_after_yield

    for component in bom.components:
        component_atp = calculate_current_atp(
            player=get_component_supplier(component.item_id),
            include_safety_stock=False
        )
        component_required = component.quantity_per_unit
        max_from_component = component_atp // component_required

        if max_from_component < max_producible:
            component_constraints[component.item_id] = (
                max_producible - max_from_component
            ) * component_required
            max_producible = max_from_component

    ctp = max_producible

    return CTPResult(
        production_capacity=capacity,
        current_commitments=commitments,
        yield_rate=yield_rate,
        available_capacity=available_capacity,
        component_constraints=component_constraints,
        ctp=ctp,
        timestamp=datetime.utcnow().isoformat()
    )
```

---

## Integration with Existing Systems

### Integration with Phase 1 (DAG Sequential)
- ATP calculation called during **FULFILLMENT** phase
- CTP calculation called during **REPLENISHMENT** phase (manufacturers only)
- Allocation conflicts pause phase progression until resolved

### Integration with Phase 2 (Copilot Mode)
- Agent recommendations use ATP/CTP data for more accurate suggestions
- Impact preview calculations incorporate ATP constraints
- Explainability levels include ATP/CTP reasoning

### Integration with AWS SC Planning
- ATP projections feed into MPS (Master Production Schedule)
- CTP data used in MRP (Material Requirements Planning)
- Allocation conflicts trigger decision proposals (Phase 0)

---

## Risk Mitigation

### Risk 1: Performance Degradation
**Issue**: Multi-period projection may be slow (O(n×m) where n=periods, m=pipeline size)
**Mitigation**:
- Cache projections (5-minute TTL)
- Limit periods to 8 max
- Use database indexes on arrival_round

### Risk 2: Allocation Complexity
**Issue**: Priority-based allocation requires customer priority data not yet in database
**Mitigation**:
- Start with proportional allocation (simplest)
- Add priority field to customers table in migration
- Allow manual override for now

### Risk 3: BOM Explosion Depth
**Issue**: Multi-level BOMs (3+ levels) may cause deep recursion in CTP calculation
**Mitigation**:
- Limit BOM recursion to 3 levels
- Cache component ATP per round
- Use iterative (not recursive) BOM explosion

---

## Next Steps (After Phase 3)

### Phase 4: Multi-Agent Orchestration (Week 11-14)
- Dynamic agent mode switching (manual → copilot → autonomous)
- Multi-agent consensus (LLM + GNN + TRM voting)
- Agent performance benchmarking dashboard
- Real-time agent training from human overrides (RLHF)

---

## Contact & Timeline

**Start Date**: 2026-01-28
**Target Completion**: 2026-02-18 (3 weeks)
**Phase**: Phase 3 (ATP/CTP Integration)
**Prerequisites**: Phase 0 ✅, Phase 1 ✅, Phase 2 ✅

**Week 8**: Backend ATP/CTP services
**Week 9**: API endpoints and WebSocket events
**Week 10**: Frontend UI components and integration testing
