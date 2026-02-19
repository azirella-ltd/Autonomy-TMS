# CTP Capabilities: Multi-Stage Capable-to-Promise & Full-Level Pegging

## Overview

The Autonomy platform implements **Kinaxis-style full-level pegging** and **multi-stage Capable-to-Promise (CTP)** across the entire supply chain network. Every unit of supply is traceable to demand (customer order or forecast), from vendor through factories and DCs to customer.

**Key Capabilities**:
- Multi-stage CTP with DAG traversal through the supply chain network
- Full-level pegging: demand-to-supply and supply-to-demand tracing
- BOM explosion at manufacturing stages with shared component detection
- Priority-based AATP consumption with persistent pegging records
- Real-time promise dates considering all upstream constraints
- Integration with the Powell Framework planning cascade

---

## 1. Multi-Stage CTP Engine

### 1.1 How It Works

When an order arrives for `Product P` at `Site S`, the CTP engine traverses the supply chain DAG upstream:

```
Customer Order (Product P, 100 units, Site S)
        |
        v
[Site S: DC-East (INVENTORY)]
  - On-hand: 200, Committed: 150, Safety Stock: 30
  - Available: 200 - 150 - 30 = 20 units
  - Shortfall: 80 units -> check upstream
        |
        v
[Site F: Factory-Central (MANUFACTURER)]
  - BOM: Product P = 2x Component A + 1x Component B
  - Capacity: 500/week, Yield: 95%
  - For 80 units of P, need 160 of A, 80 of B
  - Lead time: 3 days manufacturing
        |
        +---> [Site V1: Vendor-Steel (MARKET_SUPPLY)]
        |       - Component A available: 400 units
        |       - Vendor lead time: 5 days
        |
        +---> [Site V2: Vendor-Plastic (MARKET_SUPPLY)]
                - Component B available: 100 units
                - Vendor lead time: 7 days

Result:
  CTP Qty: 100 (feasible)
  Cumulative Lead Time: max(5,7) + 3 = 10 days
  Binding Constraint: Vendor-Plastic (Component B, 7-day lead time)
  Promise Date: Today + 10 days
```

### 1.2 Site Type Handling

The CTP engine dispatches to different logic based on site master type:

| Master Type | CTP Logic | Key Calculation |
|-------------|-----------|-----------------|
| **INVENTORY** | Check on-hand minus committed minus safety stock; recurse upstream via SourcingRules if shortfall | `available = on_hand - committed - safety_stock` |
| **MANUFACTURER** | BOM explosion; for each component, recurse upstream; constrain by capacity x yield | `ctp = min(capacity * yield, min(component_ctp / bom_ratio))` |
| **MARKET_SUPPLY** | Check vendor lead time; assume infinite supply | `available = requested_qty; lead_time = vendor_lead_time` |

### 1.3 Topology Support

| Topology | Description | Example |
|----------|-------------|---------|
| **Serial** | Linear chain | Vendor -> Factory -> DC -> Customer |
| **Convergent** | Multiple suppliers feed one site | 3 vendors -> 1 factory (binding = slowest) |
| **Divergent** | One site feeds multiple sites | 1 factory -> 4 DCs (supply split by allocation) |
| **Multi-stage manufacturing** | Product as spare AND as component | Engine sold separately AND assembled into Vehicle |
| **Multi-stage distribution** | Regional -> local | National DC -> Regional DC -> Local DC |

### 1.4 Data Classes

```python
@dataclass
class StageResult:
    site_id: int
    site_name: str
    site_type: str          # MANUFACTURER, INVENTORY, MARKET_SUPPLY
    product_id: str
    available_qty: float
    lead_time_days: int
    cumulative_lead_time_days: int
    constraint: Optional[str]  # "capacity", "component_A", "inventory", "vendor_lead_time"
    children: List[StageResult]  # BOM components or upstream suppliers

@dataclass
class MultiStageCTPResult:
    product_id: str
    site_id: int
    requested_qty: float
    ctp_qty: float              # Min across all stages
    promise_date: Optional[date]
    cumulative_lead_time_days: int
    binding_stage: Optional[StageResult]  # The tightest constraint
    stages: List[StageResult]   # Full tree
    pegging_preview: List[dict] # Proposed pegging links
    is_feasible: bool
    constraint_summary: str
```

---

## 2. Full-Level Pegging

### 2.1 Pegging Chain Structure

Every pegging chain has a unique `chain_id` (UUID) and links demand to supply across multiple stages:

```
chain_id: "a1b2c3d4..."
depth=0: demand=customer_order/ORD-001  -> supply=on_hand/DC-East       qty=80
depth=1: demand=inter_site_order/TO-001 -> supply=manufacturing_order/MO-001  qty=80
depth=2: demand=inter_site_order/PO-001 -> supply=purchase_order/PO-V001      qty=160 (BOM 2:1)
```

| Field | Description |
|-------|-------------|
| `chain_id` | UUID grouping all links in one end-to-end chain |
| `chain_depth` | 0 = terminal demand (customer order), increasing upstream |
| `upstream_pegging_id` | Self-FK linking each stage to its upstream supply |
| `demand_type` | customer_order, forecast, inter_site_order, safety_stock |
| `supply_type` | on_hand, purchase_order, transfer_order, manufacturing_order, planned_order, in_transit |
| `pegging_status` | firm, planned, tentative |
| `is_active` | Soft delete for re-pegging scenarios |

### 2.2 Pegging Queries

| Query | API Endpoint | Description |
|-------|-------------|-------------|
| **Demand-to-supply trace** | `GET /api/pegging/demand/{type}/{id}` | Follow chain downstream: customer order -> DC inventory -> factory MO -> vendor PO |
| **Supply-to-demand trace** | `GET /api/pegging/supply/{type}/{id}` | Reverse: which customer orders does this PO serve? |
| **Product@site summary** | `GET /api/pegging/product-site/{product}/{site}` | Total demand, pegged vs unpegged breakdown by type |
| **Chain lookup** | `GET /api/pegging/chain/{chain_id}` | Full end-to-end chain with all links |
| **Unpegged demand** | `GET /api/pegging/unpegged/{config_id}` | All demand not yet linked to supply (planning action list) |

### 2.3 AATP Consumption Persistence

When the AATP engine commits a consumption, two records are created:

1. **SupplyDemandPegging** row linking the order to on-hand inventory
2. **AATPConsumptionRecord** row capturing the priority-based consumption detail

```python
# Consumption sequence for order at priority P:
# 1. Own tier (P) first
# 2. Bottom-up from lowest priority (5 -> 4 -> 3 -> ...)
# 3. Stop at own tier (cannot consume above)
# Example: P=2 order -> [2, 5, 4, 3] (skips 1)
```

---

## 3. Agent Integration

### 3.1 CTP in the Planning Cascade

The CTP engine integrates with the Powell Framework planning cascade:

```
S&OP Agent (CFA: Policy Parameters theta)
    |
    v sets safety stock targets, OTIF floors, allocation reserves
MPS/MRP Agent (generates planned orders, BOM explosion)
    |
    v propagates demand_source_type, demand_source_id, demand_chain_id
Supply Agent (SupplyCommit: what to buy/make/transfer)
    |
    v supply_pegging populated from pegging links
Allocation Agent (AllocationCommit: distribute supply to demand segments)
    |
    v pegging_summary populated from pegging links
AATP Engine (priority-based consumption)
    |
    v creates pegging links + consumption records
CTP Engine (multi-stage promise checking)
    |
    v creates pegging chains on order promise
```

### 3.2 How Agents Use CTP

#### SO / ATP Agent

The Sales Order agent is the primary consumer of CTP:

| Action | CTP Usage | Authority |
|--------|-----------|-----------|
| **Promise a customer order** | Call `POST /api/pegging/ctp/promise` with order details | Unilateral if CTP shows all-green |
| **Check feasibility** | Call `POST /api/pegging/ctp/multi-stage` to evaluate without committing | Unilateral (read-only) |
| **Identify binding constraint** | Read `binding_stage` from CTP result to determine which stage limits fulfillment | Informational |
| **Request expedite** | When CTP shows lead time too long, request authorization from Logistics Agent to expedite | Requires authorization |
| **Partial promise** | When `ctp_qty < requested_qty`, promise partial and flag remainder as unpegged | Unilateral within policy |

#### Supply Agent

The Supply Agent uses pegging to validate supply plans:

| Action | CTP Usage | Authority |
|--------|-----------|-----------|
| **Validate supply plan** | Query pegging to ensure all demand is covered | Unilateral |
| **Identify unpegged demand** | Call `GET /api/pegging/unpegged/{config_id}` to find gaps | Unilateral |
| **Generate supply recommendations** | Use unpegged demand as input for PO/TO/MO creation | Unilateral |
| **Populate SupplyCommit.supply_pegging** | Pegging service builds JSON linking supply plan to pegging chain | Automatic |

#### Allocation Agent

The Allocation Agent uses pegging for demand prioritization:

| Action | CTP Usage | Authority |
|--------|-----------|-----------|
| **Demand prioritization** | Query pegging chains to see which demand is highest priority | Unilateral |
| **Allocation validation** | Ensure allocation quantities don't exceed pegged supply | Unilateral |
| **Cross-demand tracing** | Follow pegging chains to understand allocation impact on upstream | Informational |
| **Populate AllocationCommit.pegging_summary** | Pegging service builds JSON summarizing allocation-to-pegging links | Automatic |

#### Inventory Agent

The Inventory Agent uses CTP for replenishment decisions:

| Action | CTP Usage | Authority |
|--------|-----------|-----------|
| **Replenishment timing** | CTP shows upstream lead time for reorder point calculation | Unilateral |
| **Safety stock validation** | Compare safety stock targets against CTP available quantities | Unilateral |
| **Cross-DC transfer decisions** | CTP evaluates transfer feasibility through the network | Requires authorization from Logistics |

### 3.3 CTP as Balanced Scorecard Input

CTP results feed directly into the Probabilistic Balanced Scorecard:

| Scorecard Quadrant | CTP Input |
|--------------------|-----------|
| **Customer** | Promise date reliability (CTP feasible vs promised), OTIF projection |
| **Financial** | Expedite cost when standard CTP lead time exceeds target |
| **Operational** | Capacity utilization at binding stage, safety stock utilization |
| **Strategic** | Supply concentration risk (single-source binding constraint), revenue at risk from unfulfillable demand |

When an agent runs a what-if scenario, the CTP engine calculates the impact on promise dates and supply availability across the network. The balanced scorecard reflects these changes in real-time.

---

## 4. CTP Decision Graph

### 4.1 Decision Flow

```
Order Received (product_id, site_id, quantity, target_date)
    |
    v
[1] Calculate Multi-Stage CTP
    |
    +-- is_feasible? --YES--> [2] Promise Order
    |                               |
    |                               v
    |                         Create pegging chain
    |                         Return promise_date
    |
    +-- is_feasible? --NO---> [3] Evaluate Options
                                    |
                    +---------------+---------------+
                    |               |               |
                    v               v               v
              [3a] Partial     [3b] Expedite    [3c] Defer
              Promise          Request          Order
              (ctp_qty < req)  (reduce LT)     (wait for supply)
                    |               |               |
                    v               v               v
              Unilateral      Requires Auth    Unilateral
              (within policy) (from Logistics  (flag for
                              or Supply Agent)  review)
```

### 4.2 Binding Constraint Resolution

When CTP identifies a binding constraint, agents can take action:

| Binding Constraint | Responsible Agent | Resolution Options |
|--------------------|-------------------|-------------------|
| **Inventory shortage** at DC | Inventory Agent | Cross-DC transfer, safety stock exception |
| **Capacity limit** at factory | Plant Agent | Overtime, alternate line, outsource |
| **Component shortage** | Supply Agent | Rush PO, alternate supplier, substitution |
| **Vendor lead time** | Procurement Agent | Expedite fee, alternate vendor, safety stock |
| **Transportation delay** | Logistics Agent | Mode upgrade, alternate route, split shipment |

### 4.3 Re-Pegging

When supply or demand changes, pegging chains may need to be rebuilt:

| Trigger | Action | Impact |
|---------|--------|--------|
| **New higher-priority order** | Re-peg existing supply to new order; flag displaced orders as unpegged | Displaced orders enter unpegged demand list |
| **Supply shortfall** | Mark affected pegging links as inactive; recalculate CTP for affected orders | Affected orders may lose promise dates |
| **Supply increase** | Run pegging for unpegged demand list to fill gaps | Previously unpegged demand gets pegged |
| **Order cancellation** | Deactivate pegging chain; freed supply available for re-pegging | Unpegged supply becomes available |

---

## 5. API Reference

### 5.1 Multi-Stage CTP Calculation

```
POST /api/pegging/ctp/multi-stage
{
    "product_id": "SKU-001",
    "site_id": 42,
    "quantity": 100.0,
    "target_date": "2026-03-15",
    "config_id": 1,
    "group_id": 1
}

Response:
{
    "product_id": "SKU-001",
    "site_id": 42,
    "requested_qty": 100.0,
    "ctp_qty": 100.0,
    "promise_date": "2026-03-25",
    "cumulative_lead_time_days": 10,
    "is_feasible": true,
    "binding_stage": {
        "site_id": 15,
        "site_name": "Vendor-Plastic",
        "site_type": "MARKET_SUPPLY",
        "product_id": "COMP-B",
        "available_qty": 100.0,
        "lead_time_days": 7,
        "cumulative_lead_time_days": 10,
        "constraint": "vendor_lead_time"
    },
    "stages": [...],
    "pegging_preview": [...],
    "constraint_summary": "vendor_lead_time at Vendor-Plastic (available: 100)"
}
```

### 5.2 Order Promise with Pegging

```
POST /api/pegging/ctp/promise
{
    "order_id": "ORD-2026-001",
    "product_id": "SKU-001",
    "site_id": 42,
    "quantity": 100.0,
    "target_date": "2026-03-15",
    "priority": 2,
    "config_id": 1,
    "group_id": 1
}

Response:
{
    "order_id": "ORD-2026-001",
    "promised": true,
    "promised_qty": 100.0,
    "promised_date": "2026-03-25",
    "pegging_chain_id": "a1b2c3d4-...",
    "ctp": { ... full CTP result ... }
}
```

### 5.3 Demand-to-Supply Trace

```
GET /api/pegging/demand/customer_order/ORD-2026-001

Response:
{
    "demand_type": "customer_order",
    "demand_id": "ORD-2026-001",
    "chains_count": 1,
    "chains": [{
        "chain_id": "a1b2c3d4-...",
        "demand_product": "SKU-001",
        "demand_site_name": "DC-East",
        "demand_quantity": 100.0,
        "demand_priority": 2,
        "total_stages": 3,
        "is_fully_pegged": true,
        "unpegged_quantity": 0.0,
        "links": [
            {
                "depth": 0,
                "product_id": "SKU-001",
                "demand_type": "customer_order",
                "demand_id": "ORD-2026-001",
                "supply_type": "on_hand",
                "supply_id": "DC-East-INV",
                "site_name": "DC-East",
                "pegged_quantity": 20.0,
                "status": "firm"
            },
            {
                "depth": 1,
                "product_id": "SKU-001",
                "demand_type": "inter_site_order",
                "demand_id": "TO-001",
                "supply_type": "manufacturing_order",
                "supply_id": "MO-001",
                "site_name": "Factory-Central",
                "pegged_quantity": 80.0,
                "status": "planned"
            }
        ]
    }]
}
```

---

## 6. Implementation Details

### 6.1 Database Tables

| Table | Purpose |
|-------|---------|
| `supply_demand_pegging` | Core pegging links (demand <-> supply with quantity, chain tracking) |
| `aatp_consumption_record` | Persisted AATP consumption decisions with priority breakdown |
| `mrp_requirement` (3 new columns) | `demand_source_type`, `demand_source_id`, `demand_chain_id` for traceability |

### 6.2 Key Indexes

```sql
ix_pegging_chain         (chain_id)                 -- Chain lookup
ix_pegging_demand        (demand_type, demand_id)    -- Demand trace
ix_pegging_supply        (supply_type, supply_id)    -- Supply trace
ix_pegging_product_site  (product_id, site_id)       -- Product@site summary
ix_pegging_config_active (config_id, is_active)      -- Active pegging for config
ix_pegging_group         (group_id)                  -- Group-scoped queries
```

### 6.3 Services

| Service | File | Purpose |
|---------|------|---------|
| `MultiStageCTPService` | `services/multi_stage_ctp_service.py` | DAG traversal, BOM explosion, promise calculation |
| `PeggingService` | `services/pegging_service.py` | Pegging creation, querying, cascade integration |
| `AATPEngine` | `services/powell/engines/aatp_engine.py` | Priority-based consumption with optional pegging hooks |

### 6.4 Cycle Detection & Caching

- **Cycle detection**: BFS with visited set `(product_id, site_id)` prevents infinite loops in cyclic SourcingRules
- **Caching**: Site, SourcingRules, BOM, inventory, and committed-quantity caches are valid for one CTP batch; cleared between calculations
- **Shared components**: When a component appears in multiple BOMs, the committed quantity (already-pegged) is subtracted from available inventory to prevent double-counting

---

## 7. Agent Authority Boundaries for CTP Actions

For detailed authority definitions, see [AGENTIC_AUTHORIZATION_PROTOCOL.md](AGENTIC_AUTHORIZATION_PROTOCOL.md).

| CTP Action | Agent | Authority Level | Authorization Required |
|------------|-------|----------------|----------------------|
| Run CTP calculation | Any agent | Unilateral | None (read-only) |
| Promise order (CTP feasible) | SO/ATP Agent | Unilateral | None |
| Promise order (partial) | SO/ATP Agent | Unilateral within policy | None if partial-fill policy allows |
| Request expedite (reduce CTP lead time) | SO/ATP Agent | Requires authorization | Logistics Agent or Supply Agent |
| Override safety stock (increase CTP available) | Inventory Agent | Requires authorization | S&OP Agent |
| Rush PO (reduce vendor lead time) | Supply Agent | Requires authorization | Procurement Agent |
| Cross-DC transfer (redistribute supply) | Inventory Agent | Requires authorization | Logistics Agent |
| Re-peg (reassign supply to higher priority) | Allocation Agent | Unilateral within priority rules | None if within allocated tier |
| Change allocation priority | S&OP Agent | Unilateral within guardrails | Executive for guardrail changes |
