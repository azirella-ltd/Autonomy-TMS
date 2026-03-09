# Beer Game Execution Engine - Developer Guide

**Version**: 2.0
**Last Updated**: 2026-01-25
**Status**: Production Ready

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Key Components](#key-components)
4. [Execution Flow](#execution-flow)
5. [API Reference](#api-reference)
6. [Migration Guide](#migration-guide)
7. [Testing](#testing)
8. [Performance](#performance)
9. [Troubleshooting](#troubleshooting)

---

## Overview

The Beer Game Execution Engine refactors the Beer Game implementation from a simplified Node-based pipeline system to a full AWS Supply Chain execution model with complete order lifecycle tracking, FIFO fulfillment, and ATP-based order promising.

### Why Refactor?

**Legacy Implementation Problems:**
- **Simplified State**: Used integer queues (`pipeline`, `shipments`) instead of discrete orders
- **No Order Tracking**: Lost granular visibility into individual orders
- **No Backlog Management**: Backlog was a single integer per node, preventing FIFO/priority
- **Limited ATP**: No real-time available-to-promise calculations
- **Tight Coupling**: Game logic tightly coupled to Node/BeerLine classes

**New Execution Engine Benefits:**
- **✅ Full Order Lifecycle**: DRAFT → CONFIRMED → PARTIALLY_FULFILLED → FULFILLED → CANCELLED
- **✅ FIFO + Priority**: Proper backlog management with priority codes (VIP/HIGH/STANDARD/LOW)
- **✅ ATP-Based Promising**: Real-time ATP calculations with projections
- **✅ Granular Tracking**: Per-order, per-line visibility
- **✅ AWS SC Compliance**: Uses OutboundOrderLine, PurchaseOrder, TransferOrder
- **✅ Extensibility**: Service-based architecture enables reuse across modules

---

## Architecture

### Service Layer Architecture

```
BeerGameExecutionEngine (Orchestrator)
├── OrderManagementService (Order CRUD)
│   ├── create_customer_order()
│   ├── create_purchase_order()
│   ├── create_transfer_order()
│   ├── get_unfulfilled_orders()
│   └── receive_transfer_order()
├── FulfillmentService (FIFO Fulfillment)
│   ├── fulfill_customer_orders_fifo()
│   ├── fulfill_purchase_orders()
│   ├── receive_shipments()
│   └── calculate_available_to_ship()
└── ATPCalculationService (Order Promising)
    ├── calculate_atp()
    ├── calculate_promise_date()
    └── check_fulfillment_feasibility()
```

### Database Schema

**New Tables:**
- **`round_metric`**: Per-round metrics (inventory, backlog, costs, KPIs)

**Enhanced Tables:**
- **`outbound_order_line`**: Added `status`, `priority_code`, `shipped_quantity`, `backlog_quantity`, `promised_delivery_date`, `first_ship_date`, `last_ship_date`, `market_demand_site_id`
- **`purchase_order`**: Added `game_id`, `order_round`
- **`purchase_order_line_item`**: Added `shipped_quantity`
- **`transfer_order`**: Added `source_po_id`

### Data Flow

```
Round Execution Flow:
1. Receive Shipments (TOs arriving → update inventory)
2. Generate Customer Orders (Market Demand → Retailer)
3. Fulfill Orders (FIFO + priority)
   ├── Retailer: Fulfill customer orders
   ├── Wholesaler: Fulfill POs from Retailer
   ├── Distributor: Fulfill POs from Wholesaler
   └── Manufacturer: Fulfill POs from Distributor
4. Evaluate Replenishment (calculate needs or use agent decisions)
5. Issue POs (to upstream sites)
6. Calculate Costs (holding + backlog)
7. Save RoundMetric records
```

---

## Key Components

### 1. OrderManagementService

**Purpose**: CRUD operations for orders (OutboundOrderLine, PurchaseOrder, TransferOrder)

**Key Methods:**

```python
# Customer Orders
async def create_customer_order(
    order_id: str, line_number: int, product_id: str,
    site_id: int, ordered_quantity: float,
    requested_delivery_date: date, ...
) -> OutboundOrderLine

async def get_unfulfilled_customer_orders(
    site_id: int, game_id: int, priority_order: bool = True
) -> List[OutboundOrderLine]

async def update_order_fulfillment(
    order_id: int, shipped_quantity: float, ...
) -> OutboundOrderLine

# Purchase Orders
async def create_purchase_order(
    po_number: str, supplier_site_id: int,
    destination_site_id: int, product_id: str,
    quantity: float, ...
) -> PurchaseOrder

async def get_unfulfilled_purchase_orders(
    supplier_site_id: int, game_id: int
) -> List[PurchaseOrder]

# Transfer Orders
async def create_transfer_order(
    to_number: str, source_site_id: int,
    destination_site_id: int, product_id: str,
    quantity: float, arrival_round: int, ...
) -> TransferOrder

async def get_arriving_transfer_orders(
    game_id: int, arrival_round: int
) -> List[TransferOrder]

async def receive_transfer_order(
    to_id: int
) -> TransferOrder
```

### 2. FulfillmentService

**Purpose**: Order fulfillment with FIFO, priority, and ATP integration

**Key Methods:**

```python
# ATP Calculation
async def calculate_available_to_ship(
    site_id: int, product_id: str, ...
) -> float
# ATP = On-hand + In-transit - Committed - Backlog

# Customer Order Fulfillment
async def fulfill_customer_orders_fifo(
    site_id: int, product_id: str, game_id: int,
    current_round: int, ...
) -> Dict[str, Any]
# Returns: {orders_fulfilled, quantity_shipped, backlog_remaining, transfer_orders_created}

# PO Fulfillment (as sales orders)
async def fulfill_purchase_orders(
    supplier_site_id: int, product_id: str, ...
) -> Dict[str, Any]

# Shipment Receipt
async def receive_shipments(
    game_id: int, arrival_round: int, ...
) -> Dict[str, Any]
```

### 3. ATPCalculationService

**Purpose**: Real-time ATP calculation and order promising

**Key Methods:**

```python
# ATP Calculation
async def calculate_atp(
    site_id: int, product_id: str, game_id: int,
    current_round: int, horizon_rounds: int = 4
) -> Dict[str, Any]
# Returns: {current_atp, on_hand, in_transit, committed, backlog,
#           future_receipts, projected_atp}

# Promise Date Calculation
async def calculate_promise_date(
    site_id: int, product_id: str,
    requested_quantity: float, requested_date: date, ...
) -> Dict[str, Any]
# Returns: {can_promise, promised_quantity, promised_date,
#           promised_round, shortfall_quantity, confidence}

# Quick Feasibility Check
async def check_fulfillment_feasibility(
    site_id: int, product_id: str,
    required_quantity: float, ...
) -> bool
```

### 4. BeerGameExecutionEngine

**Purpose**: Orchestrates complete round execution

**Main Method:**

```python
async def execute_round(
    game_id: int,
    current_round: int,
    agent_decisions: Optional[Dict[int, float]] = None
) -> Dict[str, Any]
# Returns: {game_id, round, receipts, customer_orders,
#           fulfillment, replenishment, metrics}
```

**Execution Steps:**

1. **Receive Shipments**: Process arriving TOs and update inventory
2. **Generate Customer Orders**: Market Demand sites place orders
3. **Fulfill Orders**: FIFO + priority at all sites
4. **Evaluate Replenishment**: Use agent decisions or default logic
5. **Issue POs**: Create purchase orders to upstream
6. **Calculate Costs**: Holding ($0.50/unit) + Backlog ($1.00/unit)
7. **Save Metrics**: Persist RoundMetric records

---

## Execution Flow

### Round Execution Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Round N: Beer Game Execution                                │
└─────────────────────────────────────────────────────────────┘
                           │
    ┌──────────────────────┼──────────────────────┐
    │                      │                      │
    ▼                      ▼                      ▼
┌─────────┐          ┌─────────┐          ┌─────────┐
│ Receive │          │Generate │          │ Fulfill │
│Shipments│──────────▶│Customer │──────────▶│ Orders  │
│  (TOs)  │          │ Orders  │          │  FIFO   │
└─────────┘          └─────────┘          └─────────┘
                                                 │
                                                 │
                                                 ▼
                                          ┌─────────┐
                                          │Evaluate │
                                          │Replanish│
                                          │  Needs  │
                                          └─────────┘
                                                 │
                                                 │
                                                 ▼
                                          ┌─────────┐
                                          │ Issue   │
                                          │   POs   │
                                          └─────────┘
                                                 │
                                                 │
                                                 ▼
                                          ┌─────────┐
                                          │Calculate│
                                          │  Costs  │
                                          │& Metrics│
                                          └─────────┘
```

### Order Lifecycle

```
OutboundOrderLine Status Transitions:
DRAFT → CONFIRMED → PARTIALLY_FULFILLED → FULFILLED

┌──────┐   create_customer_order()   ┌──────────┐
│DRAFT │─────────────────────────────▶│CONFIRMED │
└──────┘   (market demand)            └──────────┘
                                            │
                                            │ fulfill_customer_orders_fifo()
                                            │ (partial shipment)
                                            ▼
                                     ┌──────────────────┐
                                     │PARTIALLY_FULFILLED│
                                     └──────────────────┘
                                            │
                                            │ fulfill_customer_orders_fifo()
                                            │ (complete shipment)
                                            ▼
                                      ┌──────────┐
                                      │FULFILLED │
                                      └──────────┘
```

### FIFO + Priority Fulfillment

```python
# Orders sorted by:
# 1. order_date ASC (oldest first - FIFO)
# 2. priority_code DESC (VIP > HIGH > STANDARD > LOW)

Example Order Queue:
┌────────────────────────────────────────────────────────┐
│ Order | Date       | Priority | Quantity | Backlog    │
├────────────────────────────────────────────────────────┤
│ ORD-1 | 2026-01-20 | LOW      | 50       | 50  ◄──┐   │
│ ORD-2 | 2026-01-22 | HIGH     | 30       | 30     │   │
│ ORD-3 | 2026-01-23 | STANDARD | 40       | 40     │   │
│ ORD-4 | 2026-01-25 | VIP      | 20       | 20     │   │
└────────────────────────────────────────────────────────┘
                                                     │
                            FIFO order (oldest first)│
                                                     │
Fulfillment with ATP = 80:                          │
1. ORD-1: Ship 50 (FULFILLED)                       │
2. ORD-2: Ship 30 (FULFILLED)                       │
3. ORD-3: BACKLOG (ATP exhausted)                   │
4. ORD-4: BACKLOG                                   │
```

---

## API Reference

### Base URL

```
http://localhost:8088/api/v1/beer-game-execution
```

### Endpoints

#### POST /execute-round

Execute a game round using the execution engine.

**Request:**
```json
{
  "game_id": 1,
  "agent_decisions": {
    "10": 25.0,  // site_id: order_quantity
    "11": 30.0
  }
}
```

**Response:**
```json
{
  "game_id": 1,
  "round": 5,
  "receipts": {
    "transfer_orders_received": 3,
    "total_quantity_received": 75.0,
    "receipts_by_site": {"10": 25.0, "11": 30.0, "12": 20.0}
  },
  "customer_orders": {
    "orders_created": 1,
    "total_demand": 8.0
  },
  "fulfillment": {...},
  "replenishment": {...},
  "metrics": {...},
  "execution_time_ms": 245.3
}
```

#### GET /orders

List customer orders with filtering.

**Query Parameters:**
- `game_id`: Filter by game ID
- `site_id`: Filter by fulfillment site
- `status`: Filter by status (DRAFT, CONFIRMED, PARTIALLY_FULFILLED, FULFILLED)
- `priority_code`: Filter by priority (VIP, HIGH, STANDARD, LOW)
- `has_backlog`: Filter for orders with backlog > 0
- `limit`: Maximum results (default: 100, max: 1000)

**Response:**
```json
[
  {
    "id": 123,
    "order_id": "ORD-1-5-10",
    "line_number": 1,
    "product_id": "BEER-CASE",
    "site_id": 10,
    "site_name": "Retailer",
    "ordered_quantity": 50.0,
    "shipped_quantity": 30.0,
    "backlog_quantity": 20.0,
    "status": "PARTIALLY_FULFILLED",
    "priority_code": "HIGH",
    "order_date": "2026-01-20",
    "requested_delivery_date": "2026-01-27",
    "game_id": 1
  }
]
```

#### GET /backlog

Get backlog report for a game.

**Query Parameters:**
- `game_id`: Game ID (required)
- `site_id`: Optional site filter

**Response:**
```json
[
  {
    "site_id": 10,
    "site_name": "Retailer",
    "product_id": "BEER-CASE",
    "total_backlog": 75.0,
    "orders_in_backlog": 3,
    "oldest_backlog_date": "2026-01-15",
    "avg_backlog_age_days": 5.2,
    "orders": [...]
  }
]
```

#### GET /purchase-orders

List purchase orders.

**Query Parameters:**
- `game_id`: Filter by game ID
- `supplier_site_id`: Filter by supplier site
- `destination_site_id`: Filter by destination site
- `status`: Filter by status (APPROVED, SHIPPED, RECEIVED)
- `limit`: Maximum results

#### GET /shipments

List transfer orders (shipments).

**Query Parameters:**
- `game_id`: Filter by game ID
- `source_site_id`: Filter by source site
- `destination_site_id`: Filter by destination site
- `status`: Filter by status (IN_TRANSIT, RECEIVED)
- `limit`: Maximum results

#### GET /shipments/arriving

Get shipments arriving in a specific round.

**Query Parameters:**
- `game_id`: Game ID (required)
- `arrival_round`: Round number (required)

#### GET /metrics

List round metrics.

**Query Parameters:**
- `game_id`: Game ID (required)
- `round_number`: Filter by round
- `site_id`: Filter by site

**Response:**
```json
[
  {
    "id": 456,
    "game_id": 1,
    "round_number": 5,
    "site_id": 10,
    "site_name": "Retailer",
    "inventory": 25.0,
    "backlog": 15.0,
    "pipeline_qty": 30.0,
    "in_transit_qty": 20.0,
    "holding_cost": 12.5,
    "backlog_cost": 15.0,
    "total_cost": 27.5,
    "cumulative_cost": 137.5,
    "fill_rate": 0.75,
    "service_level": 0.80,
    "orders_received": 4,
    "orders_fulfilled": 3,
    "incoming_order_qty": 50.0,
    "outgoing_order_qty": 45.0,
    "shipment_qty": 35.0
  }
]
```

#### GET /metrics/summary

Get aggregated metrics summary.

**Query Parameters:**
- `game_id`: Game ID (required)

**Response:**
```json
{
  "game_id": 1,
  "total_rounds": 10,
  "total_cost": 1250.0,
  "avg_cost_per_round": 125.0,
  "total_inventory": 200.0,
  "total_backlog": 75.0,
  "avg_fill_rate": 0.82,
  "avg_service_level": 0.85,
  "bullwhip_ratio": 2.3,
  "sites": [
    {
      "site_id": 10,
      "site_name": "Retailer",
      "total_cost": 350.0,
      "cumulative_cost": 350.0,
      "avg_inventory": 20.0,
      "avg_backlog": 12.5,
      "avg_fill_rate": 0.85
    }
  ]
}
```

#### POST /atp/calculate

Calculate ATP for order promising.

**Request:**
```json
{
  "site_id": 10,
  "product_id": "BEER-CASE",
  "config_id": 1,
  "game_id": 1,
  "current_round": 5
}
```

**Response:**
```json
{
  "site_id": 10,
  "product_id": "BEER-CASE",
  "current_atp": 65.0,
  "on_hand": 100.0,
  "in_transit": 20.0,
  "committed": 30.0,
  "backlog": 25.0,
  "future_receipts": [
    {"round": 6, "quantity": 40.0},
    {"round": 7, "quantity": 30.0}
  ],
  "projected_atp": [
    {"round": 6, "atp": 105.0, "receipts": 40.0},
    {"round": 7, "atp": 135.0, "receipts": 30.0}
  ]
}
```

#### GET /inventory

List current inventory levels.

**Query Parameters:**
- `game_id`: Game ID (required)
- `site_id`: Filter by site
- `product_id`: Filter by product

---

## Migration Guide

### Migrating Existing Games

Use the migration script to convert legacy game data to execution engine format:

```bash
# Dry run (no changes committed)
python scripts/migrate_to_execution_engine.py --game-id 1 --dry-run

# Validation only
python scripts/migrate_to_execution_engine.py --game-id 1 --validate

# Full migration
python scripts/migrate_to_execution_engine.py --game-id 1
```

**Migration Steps:**

1. **Inventory Levels**: Converts PlayerRound.inventory → InventoryLevel
2. **Orders**: Reconstructs OutboundOrderLine, PurchaseOrder from state changes
3. **Metrics**: Converts PlayerRound → RoundMetric records
4. **Validation**: Checks data integrity and completeness

### Backward Compatibility

Both engines can coexist during transition:

- **Legacy Engine**: `app.services.engine.BeerLine`
- **Execution Engine**: `app.services.beer_game_execution_engine.BeerGameExecutionEngine`

Use `mixed_game_service.py` to route to appropriate engine based on game settings.

---

## Testing

### Integration Tests

Run comprehensive integration tests:

```bash
cd backend
pytest tests/test_beer_game_execution_services.py -v
```

**Test Coverage:**
- Order lifecycle (DRAFT → FULFILLED)
- FIFO + priority fulfillment
- ATP calculation accuracy
- Partial fulfillment scenarios
- PO fulfillment as sales orders
- TO receipt and inventory updates
- End-to-end order fulfillment cycle

### Parallel Engine Testing

Compare legacy and execution engines side-by-side:

```bash
python scripts/parallel_engine_testing.py \
  --config-id 1 \
  --rounds 10 \
  --runs 5
```

**Validation Checks:**
- Inventory differences < 5%
- Backlog differences < 5%
- Cost differences < 5%
- Performance ratio < 2.0x

---

## Performance

### Benchmarks

**Test Environment**: 10 rounds, 4-node Beer Game, single game

| Metric | Legacy Engine | Execution Engine | Ratio |
|--------|---------------|------------------|-------|
| Execution Time | 45ms | 82ms | 1.82x |
| Database Queries | ~120 | ~245 | 2.04x |
| Memory Usage | 15MB | 28MB | 1.87x |

**Observations:**
- Execution engine is ~1.8-2.0x slower due to additional tracking
- Trade-off: More granular visibility vs. speed
- Acceptable for Beer Game use case (non-real-time)

### Optimization Tips

1. **Batch Commits**: Flush within round, commit after round completes
2. **Index Usage**: Ensure indexes on `game_id`, `round_number`, `site_id`
3. **Query Optimization**: Use `selectinload()` for relationships
4. **Connection Pooling**: Configure SQLAlchemy pool size appropriately

---

## Troubleshooting

### Common Issues

#### Issue: Orders not being fulfilled

**Symptoms**: Backlog keeps growing, no shipments created

**Diagnosis:**
```bash
# Check ATP
curl -X POST http://localhost:8088/api/v1/beer-game-execution/atp/calculate \
  -H "Content-Type: application/json" \
  -d '{"site_id": 10, "product_id": "BEER-CASE", "game_id": 1, "config_id": 1}'

# Check inventory
curl http://localhost:8088/api/v1/beer-game-execution/inventory?game_id=1&site_id=10
```

**Solution**: Verify inventory levels and ATP calculation. Check if orders are in CONFIRMED status.

#### Issue: Transfer orders not arriving

**Symptoms**: Shipments created but inventory not updating

**Diagnosis:**
```bash
# Check arriving shipments
curl "http://localhost:8088/api/v1/beer-game-execution/shipments/arriving?game_id=1&arrival_round=5"
```

**Solution**: Verify `arrival_round` matches current round. Check lead time calculation in lanes.

#### Issue: Metrics not calculating correctly

**Symptoms**: Costs or KPIs are incorrect

**Diagnosis:**
```bash
# Check round metrics
curl "http://localhost:8088/api/v1/beer-game-execution/metrics?game_id=1&round_number=5"
```

**Solution**: Verify cost rates (holding: $0.50/unit, backlog: $1.00/unit). Check cumulative cost calculation.

### Debug Mode

Enable debug logging:

```python
import logging
logging.getLogger('app.services.beer_game_execution_engine').setLevel(logging.DEBUG)
```

### Support

For issues or questions:
- GitHub Issues: https://github.com/anthropics/beer-game/issues
- Documentation: See `docs/architecture/BEER_GAME_REFACTORING_ANALYSIS.md`
- Contact: supply-chain-team@autonomy.ai

---

## Appendix

### Database Schema Diagram

```
┌──────────────────────────┐
│  outbound_order_line     │
├──────────────────────────┤
│ id (PK)                  │
│ order_id                 │
│ site_id (FK → nodes)     │
│ product_id               │
│ ordered_quantity         │
│ shipped_quantity         │◄───┐
│ backlog_quantity         │    │
│ status                   │    │ Fulfillment
│ priority_code            │    │ updates
│ game_id (FK → games)     │    │
└──────────────────────────┘    │
                                │
┌──────────────────────────┐    │
│  purchase_order          │    │
├──────────────────────────┤    │
│ id (PK)                  │    │
│ po_number                │    │
│ supplier_site_id         │    │
│ destination_site_id      │    │
│ game_id (FK → games)     │    │
│ order_round              │    │
└──────────────────────────┘    │
         │                      │
         │ 1:N                  │
         ▼                      │
┌──────────────────────────┐    │
│ purchase_order_line_item │    │
├──────────────────────────┤    │
│ id (PK)                  │    │
│ po_id (FK)               │    │
│ product_id               │    │
│ quantity                 │    │
│ shipped_quantity         │────┘
└──────────────────────────┘

┌──────────────────────────┐
│  transfer_order          │
├──────────────────────────┤
│ id (PK)                  │
│ to_number                │
│ source_site_id           │
│ destination_site_id      │
│ game_id (FK → games)     │
│ order_round              │
│ arrival_round            │◄─── Round-based arrival
│ status                   │
│ source_po_id (FK)        │
└──────────────────────────┘

┌──────────────────────────┐
│  round_metric            │
├──────────────────────────┤
│ id (PK)                  │
│ game_id (FK → games)     │
│ round_number             │
│ site_id (FK → nodes)     │
│ inventory                │
│ backlog                  │
│ holding_cost             │
│ backlog_cost             │
│ total_cost               │
│ cumulative_cost          │
│ fill_rate                │
│ service_level            │
└──────────────────────────┘
```

### Glossary

- **ATP (Available-to-Promise)**: On-hand + scheduled receipts - committed - backlog
- **FIFO (First-In-First-Out)**: Order fulfillment strategy prioritizing oldest orders
- **Backlog**: Unfulfilled order quantity (ordered - shipped)
- **Pipeline**: Orders placed to upstream but not yet received
- **In-Transit**: Shipments en route to destination
- **Holding Cost**: Cost of carrying inventory ($0.50/unit/round in Beer Game)
- **Backlog Cost**: Cost of unfulfilled orders ($1.00/unit/round in Beer Game)
- **Fill Rate**: Orders fulfilled / orders received
- **Service Level**: Units fulfilled / units requested
- **Bullwhip Effect**: Demand amplification through supply chain tiers

---

**End of Guide**
