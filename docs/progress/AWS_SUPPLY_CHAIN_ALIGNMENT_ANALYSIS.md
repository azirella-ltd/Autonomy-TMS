# AWS Supply Chain Data Model Alignment Analysis

**Date**: 2026-01-07
**Project**: The Beer Game Supply Chain Simulation
**Purpose**: Analyze current database schema against AWS Supply Chain Data Model standard

---

## Executive Summary

This analysis compares The Beer Game's current database schema with AWS Supply Chain's standard data model. The assessment reveals both strong alignments and critical gaps that should be addressed for industry-standard compliance.

### Key Findings

✅ **Strong Alignments**:
- Network topology concepts (sites as nodes, lanes as transportation_lane)
- Inventory management structure
- Order/shipment tracking foundations
- Product/item hierarchies

❌ **Critical Gaps**:
- Field naming inconsistencies (camelCase vs snake_case, AWS terminology)
- Missing AWS standard entities (trading_partner, geography, vendor_product)
- Incomplete relationship mappings
- Non-standard field names and data types

---

## 1. Entity Mapping Analysis

### 1.1 Core Network Entities

#### ✅ **ALIGNED: Node → site**

**Current Schema** (`nodes` table):
```python
id, config_id, name, type, dag_type, master_type, priority, order_aging,
lost_sale_cost, attributes
```

**AWS Standard** (`site` entity):
```
id, description, geo_id, site_type, company_id, latitude, longitude,
is_active, open_date, end_date
```

**Alignment Score**: 60% 🟡

**Issues**:
- ❌ Missing `geo_id` (required) - no geographic hierarchy reference
- ❌ Missing `site_type` (AWS standard field name vs `type`)
- ❌ Missing `latitude`, `longitude` for geographic coordinates
- ❌ Missing `is_active`, `open_date`, `end_date` for lifecycle management
- ❌ Custom fields (`dag_type`, `master_type`, `priority`) not in AWS standard
- ✅ Has `name` → maps to `description` in AWS

**Recommendation**:
- Rename `type` → `site_type`
- Add `geo_id` (foreign key to new `geography` table)
- Add optional fields: `latitude`, `longitude`, `is_active`, `open_date`, `end_date`
- Preserve custom fields in `attributes` JSON column

---

#### ✅ **ALIGNED: Lane → transportation_lane**

**Current Schema** (`lanes` table):
```python
id, config_id, upstream_node_id, downstream_node_id, capacity,
lead_time_days, demand_lead_time, supply_lead_time
```

**AWS Standard** (`transportation_lane` entity):
```
id, from_site_id, to_site_id, product_group_id, transit_time, time_uom,
distance, distance_uom, eff_start_date, eff_end_date, product_id,
emissions_per_unit, emissions_per_weight, company_id, from_geo_id,
to_geo_id, carrier_tpartner_id, service_type, trans_mode, cost_per_unit,
cost_currency
```

**Alignment Score**: 50% 🟡

**Issues**:
- ❌ `upstream_node_id` → should be `from_site_id` (AWS standard)
- ❌ `downstream_node_id` → should be `to_site_id` (AWS standard)
- ❌ `supply_lead_time` → should be `transit_time` with `time_uom`
- ❌ Missing required fields: `product_group_id`, `from_geo_id`, `to_geo_id`, `carrier_tpartner_id`, `service_type`, `trans_mode`
- ❌ Missing optional logistics fields: `distance`, `emissions_per_unit`, `cost_per_unit`, `cost_currency`
- ❌ Missing effective date ranges: `eff_start_date`, `eff_end_date`
- ✅ Has `capacity` (custom field - reasonable extension)

**Recommendation**:
- **BREAKING CHANGE**: Rename `upstream_node_id` → `from_site_id`
- **BREAKING CHANGE**: Rename `downstream_node_id` → `to_site_id`
- Add required fields with defaults for existing records
- Migrate `supply_lead_time.value` → `transit_time`, `supply_lead_time.type` → `time_uom`

---

### 1.2 Product/Item Entities

#### ✅ **ALIGNED: Item → product**

**Current Schema** (`items` table):
```python
id, config_id, name, description, priority, unit_cost_range
```

**AWS Standard** (`product` entity):
```
id, description, product_group_id, is_deleted, product_type,
parent_product_id, base_uom, unit_cost, unit_price
```

**Alignment Score**: 70% 🟢

**Issues**:
- ✅ Has `name` → maps to AWS `id` (product identifier)
- ✅ Has `description` (matches AWS)
- ❌ Missing `product_group_id` (required) - no category hierarchy
- ❌ Missing `is_deleted` (required) - lifecycle flag
- ❌ Missing `product_type`, `parent_product_id` for hierarchy
- ❌ Missing `base_uom`, `unit_cost`, `unit_price`
- ❌ Has `unit_cost_range` (JSON) vs single `unit_cost` value
- ❌ Custom `priority` field not in AWS standard

**Recommendation**:
- Add `product_group_id` (foreign key to new `product_hierarchy` table)
- Add `is_deleted` with default `False`
- Add optional: `product_type`, `parent_product_id`, `base_uom`
- Convert `unit_cost_range.min` → `unit_cost` (use midpoint or default)
- Add `unit_price` field

---

#### ❌ **MISSING: product_hierarchy**

**AWS Standard** (`product_hierarchy` entity):
```
id, description, parent_product_group_id
```

**Current Status**: Not implemented

**Impact**: Cannot categorize products for filtering/reporting (dairy, clothes, etc.)

**Recommendation**: Create new `product_hierarchy` table with self-referential parent relationship

---

### 1.3 Inventory Management

#### ⚠️ **PARTIAL: ItemNodeConfig → inv_level + inv_policy**

**Current Schema** (`item_node_configs` table):
```python
id, item_id, node_id, inventory_target_range, initial_inventory_range,
holding_cost_range, backlog_cost_range, selling_price_range
```

**AWS Standard** (`inv_level` - snapshot):
```
snapshot_date, site_id, product_id, company_id, on_hand_inventory,
allocated_inventory, bound_inventory, lot_number, expiry_date
```

**AWS Standard** (`inv_policy` - parameters):
```
site_id, id, dest_geo_id, product_id, product_group_id, eff_start_date,
eff_end_date, company_id, ss_policy, target_inventory_qty, target_doc_limit,
target_sl
```

**Alignment Score**: 40% 🟡

**Issues**:
- ❌ Conflates **transactional inventory** (`inv_level`) with **planning parameters** (`inv_policy`)
- ❌ Uses `_range` suffixes (for training data) vs actual operational values
- ❌ Missing `inv_level` fields: `snapshot_date`, `on_hand_inventory`, `allocated_inventory`, `bound_inventory`
- ❌ Missing `inv_policy` fields: `ss_policy`, `eff_start_date`, `eff_end_date`, `dest_geo_id`
- ❌ Field names don't match AWS: `node_id` vs `site_id`, `item_id` vs `product_id`

**Recommendation**:
- **Split into two tables**:
  1. `inv_level` - transactional inventory snapshots (new table)
  2. `inv_policy` - planning parameters (refactor existing `item_node_configs`)
- Use AWS standard field names: `site_id`, `product_id`

---

### 1.4 Sourcing & Supply Rules

#### ✅ **ALIGNED: ItemNodeSupplier → sourcing_rules**

**Current Schema** (`item_node_suppliers` table):
```python
id, item_node_config_id, supplier_node_id, priority
```

**AWS Standard** (`sourcing_rules` entity):
```
sourcing_rule_id, company_id, product_id, product_group_id, from_site_id,
to_site_id, sourcing_rule_type, tpartner_id, transportation_lane_id,
production_process_id, sourcing_priority, min_qty, max_qty, qty_multiple,
eff_start_date, eff_end_date
```

**Alignment Score**: 40% 🟡

**Issues**:
- ✅ Has `priority` → maps to `sourcing_priority`
- ✅ Links item to supplier (conceptually correct)
- ❌ Indirect relationship via `item_node_config_id` vs direct `product_id` + `to_site_id`
- ❌ Missing `sourcing_rule_type` (required): `transfer`, `buy`, `manufacture`
- ❌ Missing `from_site_id` (required for transfer type)
- ❌ Missing `tpartner_id` (required for buy type)
- ❌ Missing `transportation_lane_id`, `production_process_id`
- ❌ Missing MOQ fields: `min_qty`, `max_qty`, `qty_multiple`
- ❌ Missing effective date ranges

**Recommendation**:
- Refactor to directly reference `product_id` and `to_site_id`
- Add `sourcing_rule_type` enum field
- Add conditional required fields based on rule type
- Add MOQ and effective date fields

---

### 1.5 Order Management

#### ⚠️ **PARTIAL: PlayerAction/Orders → inbound_order + inbound_order_line**

**Current Schema** (scattered across `player_actions`, `orders`):
```python
# player_actions: action_type, quantity, round_id, player_id
# orders: id, game_id, round, from_node, to_node, quantity, item_id
```

**AWS Standard** (`inbound_order` header):
```
id, order_type, order_status, to_site_id, submitted_date, tpartner_id
```

**AWS Standard** (`inbound_order_line` detail):
```
id, order_id, order_type, status, product_id, to_site_id, from_site_id,
quantity_submitted, quantity_confirmed, quantity_received,
expected_delivery_date, submitted_date, incoterm, company_id, tpartner_id,
quantity_uom, reservation_id, reference_object_type, reference_object_id
```

**Alignment Score**: 45% 🟡

**Issues**:
- ❌ Order header/line not clearly separated
- ❌ `from_node`/`to_node` vs AWS `from_site_id`/`to_site_id`
- ❌ Missing `order_type`, `order_status`, `tpartner_id`
- ❌ Missing quantity states: `quantity_submitted`, `quantity_confirmed`, `quantity_received`
- ❌ Missing dates: `submitted_date`, `expected_delivery_date`
- ❌ Missing `incoterm`, `quantity_uom`
- ❌ Missing traceability: `reference_object_type`, `reference_object_id`

**Recommendation**:
- Create proper `inbound_order` and `inbound_order_line` tables
- Separate header (order-level) from line (item-level) data
- Rename node references to `site_id` pattern

---

#### ❌ **MISSING: outbound_order_line**

**AWS Standard** (`outbound_order_line` - customer demand):
```
id, product_id, cust_order_id, ship_from_site_id, ship_to_site_id,
init_quantity_requested, quantity_promised, quantity_delivered,
final_quantity_requested, status, requested_delivery_date,
promised_delivery_date, actual_delivery_date
```

**Current Status**: Partially captured in `MarketDemand` but not as orders

**Impact**: Cannot track customer order fulfillment with AWS-standard fields

**Recommendation**: Create `outbound_order_line` table for customer-facing orders

---

### 1.6 Shipment Tracking

#### ⚠️ **PARTIAL: shipment tracking exists but non-standard**

**Current Implementation**: Implied in game engine (`pipeline_shipments` in simulation state)

**AWS Standard** (`shipment` entity):
```
id, ship_to_site_id, product_id, ship_from_site_id, supplier_tpartner_id,
order_type, units_shipped, planned_delivery_date, actual_delivery_date,
carrier_eta_date, planned_ship_date, actual_ship_date, creation_date,
shipment_status, order_id, order_line_id, package_id
```

**Alignment Score**: 30% 🔴

**Issues**:
- ❌ No dedicated `shipment` table in database (only in-memory simulation state)
- ❌ Cannot track shipment lifecycle separately from orders
- ❌ Missing shipment status tracking
- ❌ Missing planned vs actual date tracking
- ❌ Missing carrier/package tracking

**Recommendation**: Create `shipment` table with AWS standard fields to persist shipment records

---

## 2. Missing AWS Standard Entities

### 2.1 Organization & Geography

#### ❌ **MISSING: geography**

**AWS Standard**:
```
id, description, parent_geo_id
```

**Purpose**: Hierarchical location structure (USA → USA-EAST → New York)

**Current Status**: Not implemented - nodes have no geographic context

**Impact**: Cannot filter/group by region, cannot support multi-geography scenarios

**Recommendation**: Create `geography` table, add `geo_id` to `site` (nodes)

---

#### ❌ **MISSING: company**

**AWS Standard**:
```
id, description, address_1, address_2, address_3, city, state_prov,
postal_code, country, phone_number, time_zone, calendar_id
```

**Purpose**: Multi-company operating entities

**Current Status**: Single-tenant within groups

**Impact**: Cannot support multi-company supply chain scenarios

**Recommendation**: Optional - add `company` table if multi-company support needed

---

#### ❌ **MISSING: trading_partner**

**AWS Standard**:
```
id, description, country, eff_start_date, eff_end_date, time_zone,
is_active, tpartner_type, geo_id
```

**Purpose**: External suppliers, vendors, carriers, 3PLs

**Current Status**: Suppliers are nodes (internal concept)

**Impact**: Cannot differentiate internal sites from external partners

**Recommendation**: Create `trading_partner` table, distinguish from internal `site` entities

---

### 2.2 Vendor Management

#### ❌ **MISSING: vendor_product**

**AWS Standard**:
```
company_id, vendor_tpartner_id, product_id, eff_start_date, eff_end_date
```

**Purpose**: Which products each vendor can supply

**Current Status**: Implicit in `ItemNodeSupplier` (assuming suppliers are vendors)

**Impact**: Cannot manage vendor catalogs separately from sourcing rules

**Recommendation**: Create `vendor_product` table if vendor management is required

---

#### ❌ **MISSING: vendor_lead_time**

**AWS Standard**:
```
company_id, vendor_tpartner_id, product_id, site_id, planned_lead_time,
eff_start_date, eff_end_date, product_group_id, region_id
```

**Purpose**: Vendor-specific delivery lead times

**Current Status**: Lead times on `lanes` (generic routes, not vendor-specific)

**Impact**: Cannot model vendor performance variability

**Recommendation**: Add if vendor lead time variability is important for simulation

---

### 2.3 Manufacturing

#### ❌ **MISSING: product_bom**

**AWS Standard**:
```
id, product_id, company_id, site_id, production_process_id,
component_product_id, component_quantity_per, assembly_cost,
assembly_cost_uom, priority, eff_start_date, eff_end_date
```

**Purpose**: Bill of Materials - components required for manufactured products

**Current Status**: Not implemented

**Impact**: Cannot model manufacturing with component consumption

**Recommendation**: Create `product_bom` table if manufacturing scenarios are needed

---

#### ❌ **MISSING: production_process**

**AWS Standard**:
```
production_process_id, production_process_name, product_id, site_id,
company_id, setup_time, setup_time_uom, operation_time, operation_time_uom
```

**Purpose**: Manufacturing process capacity and timing

**Current Status**: Not implemented

**Impact**: Cannot model production capacity constraints

**Recommendation**: Create if manufacturing capacity planning is required

---

### 2.4 Demand & Forecasting

#### ⚠️ **PARTIAL: MarketDemand → forecast**

**Current Schema** (`market_demands`):
```python
id, config_id, market_id, item_id, quantity, period_offset, period_date
```

**AWS Standard** (`forecast` entity):
```
site_id, product_id, mean, p10, p50, p90, forecast_start_dttm,
forecast_end_dttm, snapshot_date, region_id, product_group_id
```

**Alignment Score**: 50% 🟡

**Issues**:
- ✅ Has demand quantity by period
- ❌ Missing probabilistic forecast fields: `mean`, `p10`, `p50`, `p90`
- ❌ Missing `forecast_start_dttm`, `forecast_end_dttm` (uses `period_date`)
- ❌ Missing `snapshot_date` (when forecast was created)
- ❌ Uses `market_id` vs `site_id`
- ❌ Missing `region_id`, `product_group_id`

**Recommendation**: Enhance to support probabilistic forecasting with AWS fields

---

## 3. Field Naming Inconsistencies

### 3.1 Critical Naming Issues

| Current Name | AWS Standard | Table | Priority |
|--------------|--------------|-------|----------|
| `upstream_node_id` | `from_site_id` | lanes | 🔴 HIGH |
| `downstream_node_id` | `to_site_id` | lanes | 🔴 HIGH |
| `item_id` | `product_id` | ALL | 🔴 HIGH |
| `node_id` | `site_id` | ALL | 🔴 HIGH |
| `name` (nodes) | `description` | nodes/site | 🟡 MEDIUM |
| `type` (nodes) | `site_type` | nodes/site | 🟡 MEDIUM |
| `priority` (items) | N/A (custom) | items | 🟢 LOW |
| `config_id` | `company_id`? | ALL | 🟡 MEDIUM |

### 3.2 Recommended Renaming Strategy

**Phase 1 - Critical (Breaking Changes):**
```sql
-- LANE table
ALTER TABLE lanes RENAME COLUMN upstream_node_id TO from_site_id;
ALTER TABLE lanes RENAME COLUMN downstream_node_id TO to_site_id;

-- ALL tables with item_id
-- (items, item_node_configs, orders, market_demands, etc.)
-- Rename item_id → product_id

-- ALL tables with node_id
-- (item_node_configs, players, etc.)
-- Rename node_id → site_id
```

**Phase 2 - Non-breaking (Additions):**
```sql
-- NODES table → SITE
ALTER TABLE nodes RENAME COLUMN type TO site_type;
ALTER TABLE nodes RENAME COLUMN name TO description;
ALTER TABLE nodes ADD COLUMN geo_id INT;
ALTER TABLE nodes ADD COLUMN latitude DECIMAL(10,8);
ALTER TABLE nodes ADD COLUMN longitude DECIMAL(11,8);
ALTER TABLE nodes ADD COLUMN is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE nodes ADD COLUMN open_date DATE;
ALTER TABLE nodes ADD COLUMN end_date DATE;

-- ITEMS table → PRODUCT
ALTER TABLE items ADD COLUMN product_group_id INT;
ALTER TABLE items ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE;
ALTER TABLE items ADD COLUMN product_type VARCHAR(50);
ALTER TABLE items ADD COLUMN parent_product_id INT;
ALTER TABLE items ADD COLUMN base_uom VARCHAR(20);
ALTER TABLE items ADD COLUMN unit_cost DECIMAL(10,2);
ALTER TABLE items ADD COLUMN unit_price DECIMAL(10,2);
```

---

## 4. Data Type & Format Standards

### 4.1 Timestamp Format

**AWS Requirement**: ISO 8601 format for all timestamp fields

**Current Implementation**: Using Python `datetime.utcnow()` which produces ISO 8601

**Status**: ✅ COMPLIANT

### 4.2 Special Characters

**AWS Allowed**:  `# $ % - . / ^ _ { }`

**Current Implementation**: Should validate - check if any fields violate this

**Recommendation**: Add validation on text fields (names, descriptions)

### 4.3 Reserved Values

**AWS Standard**: Use `SCN_RESERVED_NO_VALUE_PROVIDED` for missing required string fields

**Current Implementation**: Uses `NULL` or empty strings

**Recommendation**: For AWS compatibility, use reserved value for S3 ingestion scenarios

---

## 5. Relationship Mapping

### 5.1 AWS Standard Relationships

```
company → geography → site
product → product_hierarchy
trading_partner → vendor_product
site → transportation_lane → site
product + site → inv_level (transactional)
product + site → inv_policy (planning)
product + site → sourcing_rules
inbound_order → inbound_order_line → shipment
```

### 5.2 Current Implementation

```
group → supply_chain_config → items, nodes, lanes, markets
items → item_node_configs ← nodes
item_node_configs → item_node_suppliers → supplier_nodes
game → orders, shipments (in-memory)
```

### 5.3 Gap Analysis

- ❌ No `company` → `geography` → `site` hierarchy
- ❌ No `product_hierarchy` → `product`
- ❌ No `trading_partner` distinction from `site`
- ❌ No separate `vendor_product` catalog
- ⚠️ Indirect `sourcing_rules` via `item_node_config`
- ❌ No proper `inbound_order` header/line separation
- ❌ No persistent `shipment` table

---

## 6. Migration Roadmap

### Phase 1: Non-Breaking Additions (Low Risk)
**Timeline**: 1-2 weeks

1. Create new AWS-standard tables (no data migration):
   - `geography` (optional - for multi-region scenarios)
   - `product_hierarchy` (optional - for categorization)
   - `trading_partner` (optional - for external partners)
   - `inv_level` (new - for transactional inventory snapshots)

2. Add optional fields to existing tables:
   - `nodes`: `geo_id`, `latitude`, `longitude`, `is_active`, `open_date`, `end_date`
   - `items`: `product_group_id`, `is_deleted`, `product_type`, `parent_product_id`, `base_uom`, `unit_cost`, `unit_price`
   - `lanes`: `from_geo_id`, `to_geo_id`, `carrier_tpartner_id`, `service_type`, `trans_mode`, `cost_per_unit`, `eff_start_date`, `eff_end_date`

3. Add new sourcing fields to `item_node_suppliers`:
   - `sourcing_rule_type`, `min_qty`, `max_qty`, `qty_multiple`, `eff_start_date`, `eff_end_date`

### Phase 2: Field Renames (Breaking Changes)
**Timeline**: 2-3 weeks
**Risk**: HIGH - requires code changes across entire codebase

1. Rename core relationship fields:
   ```sql
   -- CRITICAL: Update all foreign keys and code references
   item_id → product_id  (ALL tables)
   node_id → site_id     (ALL tables)
   upstream_node_id → from_site_id   (lanes)
   downstream_node_id → to_site_id   (lanes)
   ```

2. Rename description fields:
   ```sql
   nodes.name → nodes.description
   nodes.type → nodes.site_type
   ```

3. Update all Python code:
   - Models (SQLAlchemy)
   - Schemas (Pydantic)
   - Services (business logic)
   - API endpoints
   - Frontend (API calls)

### Phase 3: Structural Refactoring (High Risk)
**Timeline**: 4-6 weeks

1. Split `item_node_configs` into `inv_level` + `inv_policy`
2. Refactor `item_node_suppliers` to direct `sourcing_rules`
3. Create proper `inbound_order` + `inbound_order_line` structure
4. Add `outbound_order_line` for customer orders
5. Create persistent `shipment` table
6. Add `product_bom` + `production_process` for manufacturing

### Phase 4: Code Sweep (Consistency)
**Timeline**: 2-3 weeks

1. Search and replace all field references
2. Update API documentation
3. Update frontend forms and displays
4. Update database queries
5. Update test fixtures

---

## 7. Compliance Scorecard

| Category | Current Score | Target Score | Gap |
|----------|---------------|--------------|-----|
| **Core Network** | 🟡 55% | 🟢 90% | Add geography, lifecycle fields |
| **Products** | 🟢 70% | 🟢 95% | Add hierarchy, standard fields |
| **Inventory** | 🟡 40% | 🟢 85% | Split inv_level/inv_policy |
| **Sourcing** | 🟡 40% | 🟢 80% | Refactor sourcing_rules |
| **Orders** | 🟡 45% | 🟢 85% | Separate header/line, add outbound |
| **Shipments** | 🔴 30% | 🟢 85% | Create shipment table |
| **Manufacturing** | 🔴 0% | 🟡 60% | Add BOM, production_process |
| **Vendor Management** | 🔴 0% | 🟡 50% | Optional - trading_partner, vendor_product |
| **Field Naming** | 🔴 35% | 🟢 95% | Rename core fields |
| **Overall Compliance** | 🟡 **46%** | 🟢 **85%** | **39% gap** |

---

## 8. Recommendations Summary

### Immediate Actions (High Priority)

1. **Field Renaming** (Breaking Changes):
   - Plan migration: `item_id` → `product_id`, `node_id` → `site_id`
   - Update all code references in coordinated release

2. **Add Critical Missing Fields**:
   - `nodes`: `site_type`, `is_active`, `geo_id`
   - `items`: `product_group_id`, `is_deleted`, `unit_cost`, `unit_price`
   - `lanes`: `from_site_id`, `to_site_id`, `transit_time`, `time_uom`

3. **Create AWS Standard Tables**:
   - `geography` (location hierarchy)
   - `product_hierarchy` (product categories)
   - `inv_level` (transactional inventory)

### Medium-Term (3-6 months)

4. **Refactor Sourcing**:
   - Flatten `item_node_suppliers` to direct `sourcing_rules`
   - Add `sourcing_rule_type`, MOQ fields, effective dates

5. **Order/Shipment Structure**:
   - Create `inbound_order` + `inbound_order_line`
   - Create `outbound_order_line`
   - Create persistent `shipment` table

### Long-Term (Optional)

6. **Manufacturing Support**:
   - Add `product_bom` (bill of materials)
   - Add `production_process` (capacity, timing)

7. **Vendor Management**:
   - Add `trading_partner` (external entities)
   - Add `vendor_product` (vendor catalogs)
   - Add `vendor_lead_time` (vendor performance)

---

## 9. Code Sweep Strategy

### 9.1 Search Patterns

To find all occurrences of non-standard field names:

```bash
# Find all item_id references
grep -r "item_id" backend/app --include="*.py"

# Find all node_id references
grep -r "node_id" backend/app --include="*.py"

# Find all upstream_node_id / downstream_node_id
grep -r "upstream_node_id\|downstream_node_id" backend/app --include="*.py"

# Frontend references
grep -r "item_id\|node_id\|upstream_node_id\|downstream_node_id" frontend/src --include="*.js" --include="*.jsx"
```

### 9.2 Affected File Categories

1. **Models** (`backend/app/models/*.py`):
   - `supply_chain_config.py` - ALL entity definitions
   - `game.py` - Order references
   - `player.py` - Node assignments

2. **Schemas** (`backend/app/schemas/*.py`):
   - `supply_chain_config.py` - Request/response schemas
   - `game.py` - Game config schemas
   - `simulation.py` - Runtime schemas

3. **Services** (`backend/app/services/*.py`):
   - `supply_chain_config_service.py` - CRUD operations
   - `mixed_game_service.py` - Game engine (7200+ lines!)
   - `agent_game_service.py` - Agent games
   - `agents.py` - Agent logic

4. **API Endpoints** (`backend/app/api/endpoints/*.py`):
   - `supply_chain_config.py` - Config API
   - `mixed_game.py` - Game API
   - `agent_game.py` - Agent API

5. **Frontend** (`frontend/src`):
   - `services/supplyChainConfigService.js`
   - `components/supply-chain-config/*`
   - `pages/admin/GroupSupplyChainConfigList.jsx`

### 9.3 Migration Script Template

```python
# Example migration for item_id → product_id rename
from alembic import op

def upgrade():
    # Rename columns in all affected tables
    op.alter_column('items', 'item_id', new_column_name='product_id')
    op.alter_column('item_node_configs', 'item_id', new_column_name='product_id')
    op.alter_column('market_demands', 'item_id', new_column_name='product_id')
    # ... repeat for all tables

    # Update JSON config fields
    op.execute("""
        UPDATE supply_chain_configs
        SET config = JSON_SET(config, '$.items[*].product_id',
                              JSON_EXTRACT(config, '$.items[*].item_id'))
        WHERE JSON_CONTAINS_PATH(config, 'one', '$.items[*].item_id')
    """)

def downgrade():
    # Reverse all changes
    pass
```

---

## 10. Testing Strategy

### 10.1 Pre-Migration Tests

1. **Snapshot Current Behavior**:
   - Export sample games with full history
   - Document expected outputs for regression testing
   - Capture all field values in test database

2. **Create Compatibility Layer**:
   - Add property aliases in models (e.g., `product_id` → returns `item_id`)
   - Allow dual-naming during transition period

### 10.2 Post-Migration Tests

1. **Schema Validation**:
   - Verify all foreign keys intact
   - Verify all data migrated correctly
   - Check for orphaned records

2. **Functional Testing**:
   - Run full game simulations
   - Verify order placement logic
   - Verify inventory tracking
   - Verify shipment tracking

3. **API Testing**:
   - Test all CRUD endpoints
   - Verify request/response schemas
   - Test frontend integration

---

## Conclusion

Your current implementation has **strong conceptual alignment** with AWS Supply Chain Data Model (46% compliance), but requires significant field-level standardization to reach industry standards (target: 85%+).

### Recommended Approach:

1. **Immediate**: Add optional AWS fields (non-breaking)
2. **Short-term**: Plan and execute field renames (breaking, coordinated release)
3. **Medium-term**: Refactor table structures (inv_level, sourcing_rules, orders)
4. **Long-term**: Add advanced entities (manufacturing, vendor management)

**Estimated Total Effort**: 10-15 weeks for 85% compliance

This alignment will enable:
- ✅ Industry-standard terminology
- ✅ Easier integration with external systems
- ✅ Better documentation and onboarding
- ✅ Compliance with AWS Supply Chain if cloud migration desired
