# AWS Supply Chain Data Model Reference

## Overview

The Autonomy platform implements the AWS Supply Chain data model as its core data foundation. All supply chain entities — from organizations and products to forecasts and supply plans — follow AWS SC field naming conventions and table structures. Extensions for simulation (Beer Game), AI agents (Powell/TRM), and stochastic planning are added as additional columns, never replacing the base AWS SC fields.

**Implementation Status**: ~60% (21/35 AWS SC entities implemented)

## Entity Catalog

### Organization Entities

#### company
Top-level organizational entity. Maps to AWS SC `company`.

| Field | Type | Description |
|-------|------|-------------|
| id | String(100) | Primary key — company identifier |
| description | String(500) | Company name/description |
| address_1, address_2, address_3 | String(255) | Address lines |
| city, state_prov, postal_code, country | String | Location |
| phone_number | String(50) | Contact |
| time_zone | String(50) | Business time zone |
| calendar_id | String(100) | Reference to business calendar |

#### geography
Geographical hierarchies for regional planning.

| Field | Type | Description |
|-------|------|-------------|
| id | String(100) | PK |
| company_id | FK(company) | Parent company |
| parent_geo_id | FK(geography) | Self-referencing hierarchy |
| latitude, longitude | Double | Coordinates |

#### trading_partners
Suppliers, customers, carriers, 3PLs.

| Field | Type | Description |
|-------|------|-------------|
| _id | Integer | Surrogate PK (Beer Game simplification) |
| id | String(100) | Business key (unique) |
| tpartner_type | String(50) | vendor, customer, 3PL, carrier |
| geo_id | FK(geography) | Location reference |
| os_id | String(100) | Open Supplier Hub org ID |
| duns_number | String(20) | D&B identifier |

### Network Entities

#### site
Physical or logical locations in the supply chain. Defined in `supply_chain_config.py` with Integer PK for Beer Game compatibility.

| Field | Type | Description |
|-------|------|-------------|
| id | Integer | PK (auto-increment) |
| name | String | Site name |
| config_id | FK(supply_chain_configs) | Network topology reference |
| sc_site_type | String | Human-friendly type (Retailer, Wholesaler, DC, Factory, etc.) |
| master_type | String | Routing type: MARKET_SUPPLY, MARKET_DEMAND, INVENTORY, MANUFACTURER |
| position | Integer | Echelon position in network |
| company_id | FK(company) | Company reference |
| site_hierarchy_id | FK(site_hierarchy) | Hierarchy position (Company > Region > Country > Site) |

**Master Type Routing Logic**:
- **MARKET_SUPPLY**: Upstream source (infinite supply), no upstream ordering
- **MARKET_DEMAND**: Terminal sink (demand generator), no downstream
- **INVENTORY**: Storage/fulfillment (DC, Wholesaler, Retailer), passes demand upstream
- **MANUFACTURER**: Transform site with BOM, converts components → finished goods

#### transportation_lane
Material flow edges connecting sites.

| Field | Type | Description |
|-------|------|-------------|
| id | Integer | PK |
| config_id | FK(supply_chain_configs) | Network reference |
| from_site_id | FK(site) | Origin |
| to_site_id | FK(site) | Destination |
| lead_time | Integer | Transit time (periods) |
| transport_cost | Float | Per-unit cost |
| capacity | Float | Maximum throughput |

### Product Entities

#### product_hierarchy
Product grouping with hierarchical structure (Category > Family > Group > Product).

| Field | Type | Description |
|-------|------|-------------|
| id | String(100) | PK |
| parent_product_group_id | FK(product_hierarchy) | Self-referencing |
| level | Integer | Hierarchy depth |

#### product
Individual SKUs with attributes.

| Field | Type | Description |
|-------|------|-------------|
| id | String(100) | PK — SKU identifier |
| company_id | FK(company) | Company |
| product_group_id | FK(product_hierarchy) | Group membership |
| unit_cost, unit_price | Double | Financial |
| product_type | String(50) | Type classification |
| item_type | String(50) | standard, phantom, kit |
| base_uom | String(20) | EA, CS, PAL |
| weight, volume | Double | Physical attributes |
| category, family, product_group_name | String | Breadcrumb hierarchy |

### Supply Planning Entities

#### sourcing_rules
Network topology rules: who supplies what to whom, and how.

| Field | Type | Description |
|-------|------|-------------|
| id | String(100) | PK |
| product_id | FK(product) | What product |
| from_site_id | FK(site) | Source |
| to_site_id | FK(site) | Destination |
| sourcing_rule_type | String(20) | transfer, buy, manufacture |
| sourcing_priority | Integer | Lower = higher priority |
| sourcing_ratio | Double | Multi-sourcing split |
| lot_size | Double | Minimum lot |
| transportation_lane_id | FK(transportation_lane) | For transfers |
| production_process_id | FK(production_process) | For manufacturing |

**Override Logic**: product_id > product_group_id > company_id (most specific wins)

#### inv_policy
Safety stock and inventory policies with 5 policy types.

| Field | Type | Description |
|-------|------|-------------|
| id | Integer | PK |
| site_id | FK(site) | Location |
| product_id | FK(product) | Product |
| ss_policy | String(20) | abs_level, doc_dem, doc_fcst, sl, conformal |
| ss_quantity | Double | For abs_level: fixed safety stock |
| ss_days | Integer | For doc_dem/doc_fcst: days of coverage |
| service_level | Double | For sl: target service level (0-1) |
| conformal_demand_coverage | Double | For conformal: demand coverage guarantee |
| conformal_lead_time_coverage | Double | For conformal: lead time coverage guarantee |
| review_period | Integer | Review cycle (days) |
| reorder_point | Double | Calculated reorder point |
| min_order_quantity | Double | MOQ constraint |

**Override Hierarchy**: Product-Site > Product > Site > Geography > Segment > Company

**Policy Types**:
1. **abs_level**: Fixed quantity safety stock — simplest, used when demand is stable
2. **doc_dem**: Days of coverage based on actual demand — responsive to demand changes
3. **doc_fcst**: Days of coverage based on forecast — forward-looking
4. **sl**: Service level with z-score — probabilistic but assumes normality
5. **conformal**: Conformal prediction — distribution-free coverage guarantees

#### inv_level
Inventory snapshots with position tracking.

| Field | Type | Description |
|-------|------|-------------|
| product_id | FK(product) | Product |
| site_id | FK(site) | Location |
| inventory_date | Date | Snapshot date |
| on_hand_qty | Double | Physical stock |
| in_transit_qty | Double | In-transit |
| on_order_qty | Double | On order |
| allocated_qty | Double | Reserved for orders |
| available_qty | Double | Available to promise |
| lot_number | String | Lot tracking |

### Manufacturing Entities

#### product_bom
Bill of Materials — component relationships and ratios.

| Field | Type | Description |
|-------|------|-------------|
| product_id | FK(product) | Parent/finished good |
| component_product_id | FK(product) | Component |
| production_process_id | FK(production_process) | Process reference |
| component_quantity | Double | Quantity per unit of parent |
| scrap_percentage | Double | Expected scrap rate |
| alternate_group | Integer | Alternate component group |
| is_key_material | String(10) | MPS rough-cut flag |

#### production_process
Manufacturing processes with timing.

| Field | Type | Description |
|-------|------|-------------|
| id | String(100) | PK |
| site_id | FK(site) | Manufacturing site |
| operation_time | Double | Hours per unit |
| setup_time | Double | Hours per changeover |
| lot_size | Double | Minimum batch |
| yield_percentage | Double | Expected yield |
| manufacturing_leadtime | Integer | Lead time (periods) |
| manufacturing_capacity_hours | Double | Available hours |

### Planning Output Entities

#### forecast
Demand forecasts with probabilistic percentiles.

| Field | Type | Description |
|-------|------|-------------|
| product_id | FK(product) | Product |
| site_id | FK(site) | Location |
| forecast_date | Date | Forecast period |
| forecast_type | String(50) | statistical, consensus, override |
| forecast_method | String(50) | moving_average, exponential_smoothing, arima, ml |
| forecast_quantity | Double | Point forecast |
| forecast_p10 | Double | 10th percentile (optimistic) |
| forecast_p50 | Double | 50th percentile (median) |
| forecast_p90 | Double | 90th percentile (pessimistic) |
| forecast_std_dev | Double | Standard deviation |
| forecast_error | Double | Actual vs forecast error |
| user_override_quantity | Double | Human override |
| override_reason | String(500) | Captured for RLHF |

#### supply_plan
Generated supply recommendations (PO/TO/MO requests).

| Field | Type | Description |
|-------|------|-------------|
| product_id | FK(product) | Product |
| site_id | FK(site) | Destination |
| plan_date | Date | Planned date |
| plan_type | String(50) | po_request, mo_request, to_request |
| demand_quantity | Double | Gross requirement |
| supply_quantity | Double | Planned supply |
| opening_inventory | Double | Period opening |
| closing_inventory | Double | Period closing |
| safety_stock | Double | Required safety stock |
| planned_order_quantity | Double | Order quantity |
| planned_order_date | Date | When to order |
| planned_receipt_date | Date | When to receive |
| from_site_id | FK(site) | Source site (for TO) |
| supplier_id | String | Supplier (for PO) |

### Order & Logistics Entities

#### outbound_order_line
Customer orders with fulfillment tracking.

| Field | Type | Description |
|-------|------|-------------|
| order_id | String(100) | Order reference |
| product_id | FK(product) | Ordered product |
| site_id | FK(site) | Fulfillment site |
| ordered_quantity | Double | Original quantity |
| promised_quantity | Double | ATP-promised |
| shipped_quantity | Double | Fulfilled |
| backlog_quantity | Double | Unfulfilled |
| status | String(20) | DRAFT, CONFIRMED, PARTIALLY_FULFILLED, FULFILLED, CANCELLED |
| priority_code | String(20) | VIP, HIGH, STANDARD, LOW |
| requested_delivery_date | Date | Customer want date |
| promised_delivery_date | Date | ATP promise date |

#### inbound_order_line
Purchase orders and transfer orders received.

#### shipment
In-transit shipment tracking with risk assessment.

| Field | Type | Description |
|-------|------|-------------|
| order_id | String(100) | Reference order |
| product_id | String(100) | Product |
| from_site_id, to_site_id | FK(site) | Route |
| status | String(20) | planned, in_transit, delivered, delayed, exception |
| delivery_risk_score | Double | 0-100 risk score |
| risk_level | String(20) | LOW, MEDIUM, HIGH, CRITICAL |
| tracking_events | JSON | Event history |
| recommended_actions | JSON | Mitigation options |

### Supplier Entities

#### vendor_product
Vendor-specific product information (pricing, MOQs).

#### vendor_lead_time
Vendor lead times by product and site.

#### supplier_performance
Supplier reliability tracking (OTIF, quality, lead time adherence).

## Supply Chain Configuration (DAG Model)

### supply_chain_configs
Network topology definitions. Each config defines a complete supply chain network.

### 4 Master Types
The DAG model uses 4 master types for routing:

1. **MARKET_SUPPLY** → Source of raw materials (infinite supply)
2. **MANUFACTURER** → Transforms components into finished goods (has BOM)
3. **INVENTORY** → Stores and fulfills (DC, Wholesaler, Retailer)
4. **MARKET_DEMAND** → Demand generator (customer/market)

### Topology Types
- **Serial**: Factory → DC → Retailer → Customer (classic Beer Game)
- **Convergent**: Multiple suppliers → Factory (multi-sourcing)
- **Divergent**: Factory → Multiple DCs (distribution)
- **Mixed**: Real-world networks combining all patterns

## Powell Framework Tables

Powell framework extensions live alongside AWS SC tables:

| Table | Purpose |
|-------|---------|
| powell_belief_state | Conformal prediction calibration per entity |
| powell_calibration_log | Plan vs actual audit trail |
| powell_policy_parameters | CFA policy parameters (θ) |
| powell_value_function | VFA state values |
| powell_allocations | Priority × Product × Location from tGNN |
| powell_atp_decisions | ATP TRM decision history |
| powell_rebalance_decisions | Inventory rebalancing history |
| powell_po_decisions | PO creation history |
| powell_order_exceptions | Order tracking exceptions |
| powell_mo_decisions | Manufacturing order decisions |
| powell_to_decisions | Transfer order decisions |
| powell_quality_decisions | Quality disposition decisions |
| powell_maintenance_decisions | Maintenance scheduling |
| powell_subcontracting_decisions | Make-vs-buy decisions |
| powell_forecast_adjustment_decisions | Signal-driven forecast adjustments |

## 3-Step AWS SC Planning Process

### Step 1: Demand Processing
- Aggregate demand from `forecast` + `outbound_order_line`
- Net out committed/allocated from `inv_level`
- Time-phase across planning horizon

### Step 2: Inventory Target Calculation
- Read `inv_policy` for each product-site
- Apply hierarchical overrides (most specific wins)
- Calculate safety stock using policy type formula
- Generate target inventory levels

### Step 3: Net Requirements Calculation
- Time-phased netting: gross - on_hand - scheduled_receipts
- Multi-level BOM explosion from `product_bom`
- Apply `sourcing_rules` (buy/transfer/manufacture)
- Lead time offsetting from `vendor_lead_time` / `production_process`
- Generate `supply_plan` entries (PO/TO/MO requests)

## Key Relationships

```
company ──→ geography
         ──→ site ──→ inv_level
                   ──→ inv_policy
                   ──→ transportation_lane (from/to)
         ──→ product ──→ product_bom (parent/component)
                     ──→ forecast
                     ──→ supply_plan
                     ──→ outbound_order_line
                     ──→ sourcing_rules
         ──→ trading_partners ──→ vendor_product
                              ──→ vendor_lead_time
         ──→ production_process ──→ product_bom
                                ──→ sourcing_rules
```
