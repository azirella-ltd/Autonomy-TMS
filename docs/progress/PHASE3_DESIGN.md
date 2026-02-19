# Phase 3: Structural Refactoring Design

**Date**: 2026-01-07
**Status**: 🚧 IN PROGRESS
**Risk Level**: 🔴 HIGH (Major Structural Changes)
**Target Compliance**: 85%+

---

## Overview

Phase 3 involves splitting combined tables and creating new AWS-standard entities to achieve full structural compliance with the AWS Supply Chain Data Model.

---

## Structural Changes

### 1. Split `item_node_configs` → `inv_level` + `inv_policy`

**Current State**: `item_node_configs` combines inventory snapshot data with policy configuration.

**AWS Standard**: Separate concerns into two tables.

#### New Table: `inv_level` (Inventory Snapshot)
```sql
CREATE TABLE inv_level (
    id INT PRIMARY KEY AUTO_INCREMENT,
    product_id INT NOT NULL,           -- FK to items (product)
    site_id INT NOT NULL,              -- FK to nodes (site)
    on_hand_qty DECIMAL(10,2) DEFAULT 0,
    available_qty DECIMAL(10,2) DEFAULT 0,
    reserved_qty DECIMAL(10,2) DEFAULT 0,
    in_transit_qty DECIMAL(10,2) DEFAULT 0,
    backorder_qty DECIMAL(10,2) DEFAULT 0,
    safety_stock_qty DECIMAL(10,2),
    reorder_point_qty DECIMAL(10,2),
    snapshot_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_inv_level (product_id, site_id, snapshot_date),
    FOREIGN KEY (product_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (site_id) REFERENCES nodes(id) ON DELETE CASCADE
);
```

**Purpose**: Real-time inventory position tracking (current state).

#### New Table: `inv_policy` (Inventory Policy)
```sql
CREATE TABLE inv_policy (
    id INT PRIMARY KEY AUTO_INCREMENT,
    product_id INT NOT NULL,           -- FK to items (product)
    site_id INT NOT NULL,              -- FK to nodes (site)
    policy_type VARCHAR(50) NOT NULL DEFAULT 'base_stock',  -- base_stock, min_max, periodic_review
    target_qty DECIMAL(10,2),          -- Target inventory level (from inventory_target_range.avg)
    min_qty DECIMAL(10,2),             -- Minimum stock level
    max_qty DECIMAL(10,2),             -- Maximum stock level
    reorder_point DECIMAL(10,2),       -- When to reorder
    order_qty DECIMAL(10,2),           -- How much to order
    review_period INT,                 -- Periodic review period (days)
    service_level DECIMAL(5,2),        -- Target service level %
    holding_cost DECIMAL(10,2),        -- Cost per unit per period (from holding_cost_range.avg)
    backlog_cost DECIMAL(10,2),        -- Cost per unit per period (from backlog_cost_range.avg)
    selling_price DECIMAL(10,2),       -- Price per unit (from selling_price_range.avg)
    eff_start_date DATETIME DEFAULT '1900-01-01',
    eff_end_date DATETIME DEFAULT '9999-12-31 23:59:59',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_inv_policy (product_id, site_id, eff_start_date),
    FOREIGN KEY (product_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (site_id) REFERENCES nodes(id) ON DELETE CASCADE
);
```

**Purpose**: Configuration and policy rules (static configuration).

**Migration Strategy**:
- Copy `item_node_configs.product_id`, `item_node_configs.site_id` to both tables
- Map ranges to average values for `inv_policy`
- Initialize `inv_level` with zeros (will be populated during game runtime)

---

### 2. Flatten `item_node_suppliers` → `sourcing_rules`

**Current State**: `item_node_suppliers` is a junction table linking to `item_node_configs`.

**AWS Standard**: Direct `sourcing_rules` table without junction.

#### New Table: `sourcing_rules`
```sql
CREATE TABLE sourcing_rules (
    id INT PRIMARY KEY AUTO_INCREMENT,
    product_id INT NOT NULL,                -- FK to items (product)
    site_id INT NOT NULL,                   -- FK to nodes (destination site)
    supplier_site_id INT NOT NULL,          -- FK to nodes (supplier site)
    priority INT DEFAULT 0,                 -- 0 = highest priority
    sourcing_rule_type VARCHAR(50) DEFAULT 'transfer',  -- transfer, purchase, make
    allocation_percent DECIMAL(5,2) DEFAULT 100.00,     -- % of demand to source from this supplier
    min_qty DECIMAL(10,2),                  -- Minimum order quantity
    max_qty DECIMAL(10,2),                  -- Maximum order quantity
    qty_multiple DECIMAL(10,2),             -- Order quantity multiple (lot size)
    lead_time INT,                          -- Lead time in periods
    unit_cost DECIMAL(10,2),                -- Cost per unit
    eff_start_date DATETIME DEFAULT '1900-01-01',
    eff_end_date DATETIME DEFAULT '9999-12-31 23:59:59',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_sourcing_rule (product_id, site_id, supplier_site_id, eff_start_date),
    FOREIGN KEY (product_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (site_id) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (supplier_site_id) REFERENCES nodes(id) ON DELETE CASCADE
);
```

**Migration Strategy**:
- Join `item_node_suppliers` with `item_node_configs` to get `product_id` and `site_id`
- Copy priority and supplier_site_id
- Set default values for new fields

---

### 3. Add Persistent `shipment` Table

**Current State**: Shipments are transient (exist only in game state JSON).

**AWS Standard**: Persistent shipment tracking.

#### New Table: `shipment`
```sql
CREATE TABLE shipment (
    id INT PRIMARY KEY AUTO_INCREMENT,
    shipment_number VARCHAR(100) UNIQUE,    -- User-friendly identifier
    product_id INT NOT NULL,                -- FK to items (product)
    from_site_id INT NOT NULL,              -- FK to nodes (origin site)
    to_site_id INT NOT NULL,                -- FK to nodes (destination site)
    lane_id INT,                            -- FK to lanes (optional)
    quantity DECIMAL(10,2) NOT NULL,
    shipped_qty DECIMAL(10,2),              -- Actual shipped
    received_qty DECIMAL(10,2),             -- Actual received
    shipment_status VARCHAR(50) DEFAULT 'in_transit',  -- planned, in_transit, delivered, cancelled
    carrier_tpartner_id INT,                -- FK to trading_partner (carrier)
    ship_date DATETIME,                     -- When shipped
    scheduled_delivery_date DATETIME,       -- Expected delivery
    actual_delivery_date DATETIME,          -- Actual delivery
    transit_time INT,                       -- Actual transit time
    game_id INT,                            -- FK to games (for Beer Game tracking)
    round_number INT,                       -- Round when shipped
    arrival_round INT,                      -- Round when arriving
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES items(id) ON DELETE CASCADE,
    FOREIGN KEY (from_site_id) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (to_site_id) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (lane_id) REFERENCES lanes(id) ON DELETE SET NULL,
    FOREIGN KEY (carrier_tpartner_id) REFERENCES trading_partner(id) ON DELETE SET NULL,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
);
```

**Purpose**: Track all shipments with full lifecycle (planned → in_transit → delivered).

**Migration Strategy**:
- No data to migrate (shipments are currently transient)
- Update game engine to create `shipment` records
- Update game state serialization to query `shipment` table

---

### 4. Create `inbound_order` + `inbound_order_line` Tables

**Current State**: Orders tracked in game state JSON and `player_actions`.

**AWS Standard**: Persistent order tracking with header/line structure.

#### New Table: `inbound_order`
```sql
CREATE TABLE inbound_order (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_number VARCHAR(100) UNIQUE,       -- User-friendly identifier
    from_site_id INT NOT NULL,              -- FK to nodes (supplier)
    to_site_id INT NOT NULL,                -- FK to nodes (customer)
    order_type VARCHAR(50) DEFAULT 'transfer',  -- transfer, purchase, replenishment
    order_status VARCHAR(50) DEFAULT 'open',    -- open, confirmed, shipped, delivered, cancelled
    order_date DATETIME NOT NULL,
    requested_delivery_date DATETIME,
    promised_delivery_date DATETIME,
    actual_delivery_date DATETIME,
    total_qty DECIMAL(10,2),                -- Sum of line quantities
    priority INT DEFAULT 0,
    game_id INT,                            -- FK to games (for Beer Game tracking)
    round_number INT,                       -- Round when ordered
    due_round INT,                          -- Round when needed
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (from_site_id) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (to_site_id) REFERENCES nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
);
```

#### New Table: `inbound_order_line`
```sql
CREATE TABLE inbound_order_line (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL,                  -- FK to inbound_order
    line_number INT NOT NULL,               -- Line sequence
    product_id INT NOT NULL,                -- FK to items (product)
    quantity DECIMAL(10,2) NOT NULL,
    shipped_qty DECIMAL(10,2) DEFAULT 0,
    received_qty DECIMAL(10,2) DEFAULT 0,
    unit_price DECIMAL(10,2),
    line_status VARCHAR(50) DEFAULT 'open', -- open, partial, fulfilled, cancelled
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_order_line (order_id, line_number),
    FOREIGN KEY (order_id) REFERENCES inbound_order(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES items(id) ON DELETE CASCADE
);
```

**Purpose**: Full order lifecycle tracking (order → shipment → receipt).

**Migration Strategy**:
- No data to migrate (orders are currently transient)
- Update game engine to create `inbound_order` + `inbound_order_line` records
- Link orders to shipments when fulfilled

---

## Data Migration Plan

### Phase 3a: Create New Tables (Non-Breaking)

1. Create `inv_level` table (empty initially)
2. Create `inv_policy` table (migrate from `item_node_configs`)
3. Create `sourcing_rules` table (migrate from `item_node_suppliers`)
4. Create `shipment` table (empty initially)
5. Create `inbound_order` and `inbound_order_line` tables (empty initially)

**Impact**: None - old tables remain, new tables coexist

### Phase 3b: Update Code to Use New Tables

1. Update models to reference new tables
2. Update services to write to both old and new tables (dual-write)
3. Update game engine to populate `inv_level`, `shipment`, `inbound_order`
4. Comprehensive testing

**Impact**: Code changes, no data loss

### Phase 3c: Deprecate Old Tables (Optional - Future)

1. Mark `item_node_configs` as deprecated (keep for backward compatibility)
2. Mark `item_node_suppliers` as deprecated
3. Eventually drop old tables in future version

**Impact**: Clean up technical debt

---

## AWS Compliance Impact

| Entity | Before Phase 3 | After Phase 3 | AWS Alignment |
|--------|----------------|---------------|---------------|
| `inv_level` | ❌ Combined in `item_node_configs` | ✅ Separate table | 100% |
| `inv_policy` | ❌ Combined in `item_node_configs` | ✅ Separate table | 100% |
| `sourcing_rules` | 🟡 Via junction table | ✅ Direct table | 100% |
| `shipment` | ❌ Transient only | ✅ Persistent tracking | 100% |
| `inbound_order` | ❌ In game state JSON | ✅ Dedicated table | 100% |
| `inbound_order_line` | ❌ N/A | ✅ Dedicated table | 100% |

**Projected Compliance**: 85-90%

---

## Implementation Strategy

### Approach: Additive (Non-Destructive)

- **Keep old tables**: `item_node_configs`, `item_node_suppliers` remain
- **Add new tables**: Create all Phase 3 tables alongside old ones
- **Dual-write**: Services write to both old and new tables during transition
- **Gradual migration**: Move functionality table-by-table
- **Backward compatibility**: Old code continues to work

### Benefits

✅ **Zero downtime**: No breaking changes
✅ **Rollback-friendly**: Can revert at any point
✅ **Incremental testing**: Test each table migration independently
✅ **Safe**: Data exists in both old and new formats

### Risks

⚠️ **Increased complexity**: Dual-write adds code complexity
⚠️ **Data sync issues**: Must keep old and new tables in sync
⚠️ **Storage overhead**: Duplicate data during transition
⚠️ **Performance**: Additional writes may impact performance

---

## Timeline Estimate

| Phase | Tasks | Effort | Risk |
|-------|-------|--------|------|
| **3a: Create Tables** | Migrations + data copy | 2-3 days | 🟢 LOW |
| **3b: Update Models** | SQLAlchemy models + schemas | 1-2 days | 🟢 LOW |
| **3c: Update Services** | Dual-write logic | 3-4 days | 🟡 MEDIUM |
| **3d: Update Game Engine** | inv_level, shipment, orders | 5-7 days | 🔴 HIGH |
| **3e: Testing** | Comprehensive QA | 3-4 days | 🟡 MEDIUM |
| **3f: Deprecation** | Mark old tables deprecated | 1 day | 🟢 LOW |
| **Total** | | **15-21 days** | 🔴 HIGH |

---

## Success Criteria

✅ All new tables created and populated
✅ Old tables remain functional (backward compatibility)
✅ Game engine writes to new tables
✅ Inventory levels tracked in `inv_level`
✅ Shipments tracked in `shipment`
✅ Orders tracked in `inbound_order`/`inbound_order_line`
✅ No data loss or corruption
✅ Application performance maintained
✅ AWS compliance reaches 85%+

---

**Status**: Design complete, ready for implementation
**Next Step**: Create Phase 3 migration

🤖 Generated with [Claude Code](https://claude.com/claude-code)
