# Field Name Reference Guide

**Quick lookup for AWS Supply Chain standard field names vs current implementation**

---

## Core Entity Mappings

### Node/Site Entity

| Current Field | AWS Standard Field | Required | Notes |
|--------------|-------------------|----------|-------|
| `id` | `id` | ✅ Yes | ✅ Matches |
| `name` | `description` | ✅ Yes | ⚠️ Rename needed |
| `type` | `site_type` | Optional | ⚠️ Rename needed |
| N/A | `geo_id` | ✅ Yes | ❌ Missing - add FK to geography |
| N/A | `company_id` | Optional | ❌ Missing |
| N/A | `latitude` | Optional | ❌ Missing |
| N/A | `longitude` | Optional | ❌ Missing |
| N/A | `is_active` | ✅ Yes | ❌ Missing - default TRUE |
| N/A | `open_date` | Optional | ❌ Missing |
| N/A | `end_date` | Optional | ❌ Missing |
| `dag_type` | N/A | - | Custom field - keep in attributes |
| `master_type` | N/A | - | Custom field - keep in attributes |
| `priority` | N/A | - | Custom field - keep in attributes |

### Item/Product Entity

| Current Field | AWS Standard Field | Required | Notes |
|--------------|-------------------|----------|-------|
| `id` | `id` | ✅ Yes | ✅ Matches |
| `name` | `description` | ✅ Yes | ⚠️ Consider renaming |
| `description` | (additional detail) | Optional | ✅ Matches |
| N/A | `product_group_id` | ✅ Yes | ❌ Missing - add FK to product_hierarchy |
| N/A | `is_deleted` | ✅ Yes | ❌ Missing - default FALSE |
| N/A | `product_type` | Optional | ❌ Missing |
| N/A | `parent_product_id` | Optional | ❌ Missing - for hierarchy |
| N/A | `base_uom` | Optional | ❌ Missing |
| `unit_cost_range` | `unit_cost` | Optional | ⚠️ Convert range to single value |
| N/A | `unit_price` | Optional | ❌ Missing |
| `priority` | N/A | - | Custom field - keep |

### Lane/Transportation Lane Entity

| Current Field | AWS Standard Field | Required | Notes |
|--------------|-------------------|----------|-------|
| `id` | `id` | ✅ Yes | ✅ Matches |
| `upstream_node_id` | `from_site_id` | ✅ Yes | ⚠️ RENAME REQUIRED |
| `downstream_node_id` | `to_site_id` | ✅ Yes | ⚠️ RENAME REQUIRED |
| N/A | `product_group_id` | ✅ Yes | ❌ Missing |
| `supply_lead_time.value` | `transit_time` | ✅ Yes | ⚠️ Extract from JSON |
| `supply_lead_time.type` | `time_uom` | ✅ Yes | ⚠️ Extract from JSON |
| N/A | `distance` | Optional | ❌ Missing |
| N/A | `distance_uom` | Optional | ❌ Missing |
| N/A | `eff_start_date` | Optional | ❌ Missing |
| N/A | `eff_end_date` | Optional | ❌ Missing |
| N/A | `emissions_per_unit` | Optional | ❌ Missing |
| N/A | `from_geo_id` | ✅ Yes | ❌ Missing |
| N/A | `to_geo_id` | ✅ Yes | ❌ Missing |
| N/A | `carrier_tpartner_id` | ✅ Yes | ❌ Missing |
| N/A | `service_type` | ✅ Yes | ❌ Missing |
| N/A | `trans_mode` | ✅ Yes | ❌ Missing |
| N/A | `cost_per_unit` | Optional | ❌ Missing |
| `capacity` | N/A | - | Custom field - keep |
| `demand_lead_time` | N/A | - | Custom field - keep |

### ItemNodeConfig → Should split into inv_level + inv_policy

#### As inv_level (Transactional Inventory)

| Current Field | AWS Standard Field | Required | Notes |
|--------------|-------------------|----------|-------|
| N/A | `snapshot_date` | ✅ Yes | ❌ Missing - add timestamp |
| `node_id` | `site_id` | ✅ Yes | ⚠️ RENAME REQUIRED |
| `item_id` | `product_id` | ✅ Yes | ⚠️ RENAME REQUIRED |
| N/A | `company_id` | Optional | ❌ Missing |
| `initial_inventory_range` | `on_hand_inventory` | ✅ Yes | ⚠️ Convert range to value |
| N/A | `allocated_inventory` | Optional | ❌ Missing |
| N/A | `bound_inventory` | Optional | ❌ Missing (in-transit) |
| N/A | `lot_number` | ✅ Yes | ❌ Missing - use default |
| N/A | `expiry_date` | Optional | ❌ Missing |

#### As inv_policy (Planning Parameters)

| Current Field | AWS Standard Field | Required | Notes |
|--------------|-------------------|----------|-------|
| `node_id` | `site_id` | ✅ Yes | ⚠️ RENAME REQUIRED |
| `id` | `id` | ✅ Yes | ✅ Matches |
| N/A | `dest_geo_id` | ✅ Yes | ❌ Missing |
| `item_id` | `product_id` | Optional* | ⚠️ RENAME REQUIRED |
| N/A | `product_group_id` | Optional* | ❌ Missing (either product_id OR product_group_id) |
| N/A | `eff_start_date` | ✅ Yes | ❌ Missing |
| N/A | `eff_end_date` | ✅ Yes | ❌ Missing |
| N/A | `ss_policy` | ✅ Yes | ❌ Missing (abs_level, doc_dem, doc_fcst, sl) |
| `inventory_target_range` | `target_inventory_qty` | Conditional | ⚠️ Convert range to value |
| N/A | `target_doc_limit` | Conditional | ❌ Missing |
| N/A | `target_sl` | Conditional | ❌ Missing |

### ItemNodeSupplier → sourcing_rules

| Current Field | AWS Standard Field | Required | Notes |
|--------------|-------------------|----------|-------|
| `id` | `sourcing_rule_id` | ✅ Yes | ⚠️ Rename for clarity |
| N/A | `company_id` | Optional | ❌ Missing |
| (via item_node_config) | `product_id` | Optional* | ⚠️ Flatten relationship |
| N/A | `product_group_id` | Optional* | ❌ Missing (either product_id OR product_group_id) |
| `supplier_node_id` | `from_site_id` | Optional† | ⚠️ RENAME (for transfer type) |
| (via item_node_config) | `to_site_id` | ✅ Yes | ⚠️ Flatten relationship |
| N/A | `sourcing_rule_type` | ✅ Yes | ❌ Missing (transfer, buy, manufacture) |
| N/A | `tpartner_id` | Optional† | ❌ Missing (for buy type) |
| N/A | `transportation_lane_id` | Optional† | ❌ Missing (for transfer type) |
| N/A | `production_process_id` | Optional† | ❌ Missing (for manufacture type) |
| `priority` | `sourcing_priority` | Optional | ⚠️ Rename for clarity |
| N/A | `min_qty` | Optional | ❌ Missing (MOQ) |
| N/A | `max_qty` | Optional | ❌ Missing |
| N/A | `qty_multiple` | Optional | ❌ Missing |
| N/A | `eff_start_date` | ✅ Yes | ❌ Missing |
| N/A | `eff_end_date` | ✅ Yes | ❌ Missing |

*† = Required based on `sourcing_rule_type` value*

---

## Cross-Cutting Field Renames

### Universal Renames (Apply Everywhere)

| Current Pattern | AWS Standard Pattern | Affected Tables |
|----------------|---------------------|-----------------|
| `item_id` | `product_id` | items, item_node_configs, market_demands, orders, shipments, etc. |
| `node_id` | `site_id` | item_node_configs, players, node_configs, etc. |
| `upstream_node_id` | `from_site_id` | lanes |
| `downstream_node_id` | `to_site_id` | lanes |
| `config_id` | (context-dependent) | Most tables - may map to company_id in AWS context |

### Relationship Field Patterns

| Purpose | Current Pattern | AWS Pattern | Example |
|---------|----------------|-------------|---------|
| Source location | `from_node`, `upstream_node_id` | `from_site_id`, `ship_from_site_id` | lanes, shipments |
| Destination location | `to_node`, `downstream_node_id` | `to_site_id`, `ship_to_site_id` | lanes, orders |
| Product reference | `item_id` | `product_id` | All product associations |
| Location reference | `node_id` | `site_id` | All site associations |
| Supplier reference | `supplier_node_id` | `supplier_tpartner_id` or `from_site_id` | Depends on if external partner |

---

## New Required Entities

### Must Create

1. **geography** - Geographic hierarchy
   - `id`, `description`, `parent_geo_id`

2. **product_hierarchy** - Product categories
   - `id`, `description`, `parent_product_group_id`

3. **inv_level** - Transactional inventory (split from item_node_configs)
   - See inv_level mapping above

### Should Create (for compliance)

4. **trading_partner** - External suppliers, vendors, carriers
   - `id`, `description`, `country`, `eff_start_date`, `eff_end_date`, `time_zone`, `is_active`, `tpartner_type`, `geo_id`

5. **inbound_order** - Purchase order headers
   - `id`, `order_type`, `order_status`, `to_site_id`, `submitted_date`, `tpartner_id`

6. **inbound_order_line** - Purchase order line items
   - `id`, `order_id`, `order_type`, `status`, `product_id`, `to_site_id`, `from_site_id`, `quantity_submitted`, `quantity_confirmed`, `quantity_received`, `expected_delivery_date`, etc.

7. **shipment** - Shipment tracking (persist from in-memory state)
   - `id`, `ship_to_site_id`, `product_id`, `ship_from_site_id`, `supplier_tpartner_id`, `order_type`, `units_shipped`, `planned_delivery_date`, `actual_delivery_date`, etc.

### Optional (Advanced Features)

8. **product_bom** - Bill of materials for manufacturing
9. **production_process** - Manufacturing capacity and timing
10. **vendor_product** - Vendor product catalogs
11. **vendor_lead_time** - Vendor-specific lead times

---

## Migration Checklist

### Phase 1: Add Optional Fields (Non-Breaking)

- [ ] Add `nodes.geo_id` (FK to geography table)
- [ ] Add `nodes.latitude`, `nodes.longitude`
- [ ] Add `nodes.is_active` (default TRUE)
- [ ] Add `nodes.open_date`, `nodes.end_date`
- [ ] Add `items.product_group_id` (FK to product_hierarchy)
- [ ] Add `items.is_deleted` (default FALSE)
- [ ] Add `items.product_type`, `items.parent_product_id`
- [ ] Add `items.base_uom`, `items.unit_cost`, `items.unit_price`
- [ ] Add `lanes.from_geo_id`, `lanes.to_geo_id`
- [ ] Add `lanes.carrier_tpartner_id`, `lanes.service_type`, `lanes.trans_mode`
- [ ] Add `lanes.cost_per_unit`, `lanes.eff_start_date`, `lanes.eff_end_date`
- [ ] Add `item_node_suppliers.sourcing_rule_type`, `min_qty`, `max_qty`, `qty_multiple`, `eff_start_date`, `eff_end_date`

### Phase 2: Field Renames (Breaking Changes)

- [ ] Rename `nodes.name` → `nodes.description`
- [ ] Rename `nodes.type` → `nodes.site_type`
- [ ] Rename `lanes.upstream_node_id` → `lanes.from_site_id`
- [ ] Rename `lanes.downstream_node_id` → `lanes.to_site_id`
- [ ] Rename ALL `item_id` → `product_id` (global search/replace)
- [ ] Rename ALL `node_id` → `site_id` (global search/replace)
- [ ] Update Python models, schemas, services
- [ ] Update API endpoints
- [ ] Update frontend code

### Phase 3: Structure Refactoring

- [ ] Split `item_node_configs` into `inv_level` + `inv_policy`
- [ ] Create `geography` table
- [ ] Create `product_hierarchy` table
- [ ] Create `trading_partner` table
- [ ] Create `inbound_order` + `inbound_order_line` tables
- [ ] Create persistent `shipment` table
- [ ] Refactor `item_node_suppliers` to direct `sourcing_rules`

---

## SQL Migration Script Templates

### Template 1: Simple Column Rename

```sql
-- Rename nodes.name to nodes.description
ALTER TABLE nodes
  CHANGE COLUMN `name` `description` VARCHAR(100) NOT NULL;
```

### Template 2: Add New Column with Default

```sql
-- Add is_active to nodes table
ALTER TABLE nodes
  ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;
```

### Template 3: Add Foreign Key

```sql
-- Add geo_id to nodes (after creating geography table)
ALTER TABLE nodes
  ADD COLUMN geo_id INT NULL,
  ADD CONSTRAINT fk_nodes_geo_id
    FOREIGN KEY (geo_id) REFERENCES geography(id);
```

### Template 4: Global Rename with Foreign Key Update

```sql
-- Rename item_id to product_id in item_node_configs
ALTER TABLE item_node_configs
  DROP FOREIGN KEY item_node_configs_ibfk_1,  -- Drop old FK
  CHANGE COLUMN `item_id` `product_id` INT NOT NULL,
  ADD CONSTRAINT fk_item_node_configs_product_id
    FOREIGN KEY (product_id) REFERENCES items(id);
```

### Template 5: Create New Table (geography)

```sql
CREATE TABLE geography (
  id INT AUTO_INCREMENT PRIMARY KEY,
  description VARCHAR(255) NOT NULL,
  parent_geo_id INT NULL,
  INDEX idx_geography_id (id),
  CONSTRAINT fk_geography_parent
    FOREIGN KEY (parent_geo_id) REFERENCES geography(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## Code Reference Patterns

### Python Models (SQLAlchemy)

```python
# OLD
class Node(Base):
    item_id = Column(Integer, ForeignKey("items.id"))
    upstream_node_id = Column(Integer, ForeignKey("nodes.id"))

# NEW
class Site(Base):  # or keep "Node" but use AWS fields
    product_id = Column(Integer, ForeignKey("products.id"))
    from_site_id = Column(Integer, ForeignKey("sites.id"))
```

### Python Schemas (Pydantic)

```python
# OLD
class ItemNodeConfigBase(BaseModel):
    item_id: int
    node_id: int

# NEW
class InvPolicyBase(BaseModel):
    product_id: int
    site_id: int
```

### Frontend API Calls

```javascript
// OLD
const config = {
  item_id: itemId,
  node_id: nodeId,
  upstream_node_id: fromNode,
  downstream_node_id: toNode
};

// NEW
const config = {
  product_id: productId,
  site_id: siteId,
  from_site_id: fromSite,
  to_site_id: toSite
};
```

---

## Search Patterns for Code Sweep

```bash
# Find all item_id references
rg "item_id" --type py
rg "item_id" --type js

# Find all node_id references
rg "node_id" --type py
rg "node_id" --type js

# Find all upstream/downstream_node_id
rg "upstream_node_id|downstream_node_id" --type py

# Find all from_node/to_node patterns
rg "from_node|to_node" --type py

# Case-insensitive search for "item" in field context
rg "\.item_id|\"item_id\"|'item_id'" --type py
```

---

## Timeline Estimates

| Phase | Tasks | Effort | Risk |
|-------|-------|--------|------|
| Phase 1: Add Fields | 20 new columns across 5 tables | 1-2 weeks | 🟢 Low |
| Phase 2: Renames | 500+ code references | 2-3 weeks | 🔴 High |
| Phase 3: Refactor | 7 new tables, split logic | 4-6 weeks | 🔴 High |
| **Total** | | **8-11 weeks** | |

---

## Priority Rankings

### P0 - Critical for AWS Compliance

1. Rename `item_id` → `product_id` (everywhere)
2. Rename `node_id` → `site_id` (everywhere)
3. Rename `upstream_node_id` → `from_site_id` (lanes)
4. Rename `downstream_node_id` → `to_site_id` (lanes)
5. Add `items.product_group_id` + create `product_hierarchy` table
6. Add `nodes.geo_id` + create `geography` table
7. Add `items.is_deleted`, `nodes.is_active`

### P1 - Important for Data Model Standards

8. Split `item_node_configs` → `inv_level` + `inv_policy`
9. Create `trading_partner` table
10. Refactor `item_node_suppliers` to flat `sourcing_rules`
11. Add effective date ranges to sourcing rules and lanes

### P2 - Nice to Have for Full Compliance

12. Create `inbound_order` + `inbound_order_line` structure
13. Create persistent `shipment` table
14. Add manufacturing entities (`product_bom`, `production_process`)
15. Add vendor management entities

---

## Final Notes

- **All renames are BREAKING CHANGES** - plan for coordinated release
- **Database migrations must be reversible** - write downgrade() functions
- **Test extensively** - snapshot current behavior before migration
- **Consider dual-field transition period** - use SQLAlchemy synonyms/properties
- **Document changes** - update API docs, frontend comments, README
