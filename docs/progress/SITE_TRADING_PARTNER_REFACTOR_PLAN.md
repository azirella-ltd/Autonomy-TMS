# Site vs. Trading Partner Refactoring Plan

**Status**: PLANNING
**Created**: 2026-03-11
**Author**: Architecture Review

---

## Problem Statement

Autonomy currently collapses external supply chain entities (suppliers and customers) into the `Site` table alongside internal company-controlled locations. This violates the AWS SC Data Model and creates semantic confusion.

### Current (Incorrect) Model

```
Site table (master_type)
  INVENTORY            ← DC, Warehouse, Retailer, Wholesaler
  MANUFACTURER         ← Factory, Plant
  MARKET_SUPPLY  ←  Should be TradingPartner (vendor)
  MARKET_DEMAND  ←  Should be TradingPartner (customer)
```

### Target (AWS SC DM Compliant) Model

```
Site table — ONLY company-controlled locations:
  INVENTORY            ← DC, Warehouse, Retailer, Wholesaler
  MANUFACTURER         ← Factory, Plant

TradingPartner table — ALL external parties:
  tpartner_type='vendor'    ← Suppliers (was MARKET_SUPPLY)
  tpartner_type='customer'  ← Customers (was MARKET_DEMAND)
```

### Why This Matters

1. **AWS SC DM compliance**: In the standard, `site` is explicitly a location the *company owns or controls*. External parties are `trading_partner` records. AWS SC entities like `inbound_order_line.vendor_id` and `outbound_order_line.customer_id` already correctly reference `trading_partner`.

2. **Semantic clarity**: A supplier is not a "site" — it has different attributes (DUNS number, OSH ID, performance records, contracts). A customer is not a "site" — it has demand patterns, contracts, service level agreements.

3. **SAP integration**: SAP exports vendors (LFA1) and customers (KNA1) as trading partners, not sites. The current model forces mapping SAP vendors into a fake Site record.

4. **Planning logic**: Planning correctly routes demand to customers and procurement to vendors. Mixing them into Site causes hacks like `if master_type not in (MARKET_SUPPLY, MARKET_DEMAND)` scattered everywhere.

5. **TRM hive composition**: Market nodes get only 1 TRM (order_tracking). External parties shouldn't be in the TRM hive at all — they're outside the company's authority boundary.

---

## AWS SC Data Model Reference

| Entity | Table | Purpose |
|--------|-------|---------|
| `site` | `site` | Company-owned/controlled locations |
| `trading_partner` | `trading_partners` | External suppliers, customers, carriers |
| `sourcing_rules` | `sourcing_rules` | Links site to vendor (buy) or site (transfer/make) |
| `inbound_order_line` | `inbound_order_line` | References `vendor_id → trading_partner` |
| `outbound_order_line` | `outbound_order_line` | References `customer_id → trading_partner` |
| `transportation_lane` | `transportation_lane` | Between sites (internal flow) |

**External material flow** is modeled via:
- **Buy**: SourcingRule with `supply_type='buy'` → references `vendor_id` (TradingPartner)
- **Sell**: OutboundOrderLine → references `customer_id` (TradingPartner)
- **Transfer**: SourcingRule with `supply_type='transfer'` → references another internal Site

---

## Current State Inventory

### Files with MARKET_SUPPLY / MARKET_DEMAND References (31 backend, 5 frontend)

**Core models** (highest priority):
- `backend/app/models/supply_chain_config.py` — `NodeType` enum, `Site` model, `Market`, `MarketDemand`
- `backend/app/models/participant.py` — `NodeType.MARKET_SUPPLY/DEMAND` re-export
- `backend/app/models/sc_entities.py` — Note: TradingPartner already correct; Site note says to import from supply_chain_config

**Config/setup**:
- `backend/app/services/sap_config_builder.py` — `MASTER_MARKET_SUPPLY/DEMAND` constants, `_infer_master_type()`
- `backend/app/services/synthetic_data_generator.py` — Creates Market/MARKET_DEMAND nodes
- `backend/app/services/food_dist_config_generator.py`

**Planning/execution**:
- `backend/app/services/supply_plan_service.py`
- `backend/app/services/sc_planning/planner.py`
- `backend/app/services/sc_planning/simulation_execution_adapter.py`
- `backend/app/services/simulation_execution_engine.py`
- `backend/app/services/sc_execution/simulation_executor.py`
- `backend/app/services/sc_execution/order_promising.py`
- `backend/app/services/fulfillment_service.py`
- `backend/app/services/multi_stage_ctp_service.py`

**Agents/AI**:
- `backend/app/services/gnn_agent.py`
- `backend/app/services/powell/site_capabilities.py`
- `backend/app/services/powell/synthetic_trm_data_generator.py`
- `backend/app/models/gnn/scalable_graphsage.py`
- `backend/app/models/gnn/large_sc_data_generator.py`
- `backend/app/rl/aws_sc_config.py`
- `backend/app/rl/config.py`
- `backend/app/rl/data_generator.py`

**API endpoints**:
- `backend/app/api/endpoints/supply_chain_config.py`
- `backend/app/api/endpoints/auth.py`
- `backend/app/api/endpoints/simulation_execution.py`
- `backend/app/api/endpoints/conformal_prediction.py`

**Services**:
- `backend/app/services/hierarchical_metrics_service.py`
- `backend/app/services/sap_change_simulator.py`
- `backend/app/services/sap_csv_exporter.py`
- `backend/app/services/scenario_branching_service.py`
- `backend/app/services/simulation_data_converter.py`
- `backend/app/services/parallel_monte_carlo.py`
- `backend/app/services/agent_game_service.py`
- `backend/app/services/llm_suggestion_service.py`

**Frontend**:
- `frontend/src/components/supply-chain-config/SupplyChainConfigSankey.jsx`
- `frontend/src/components/cascade/PlanningCascadeSankey.jsx`
- `frontend/src/services/supplyChainConfigService.js`
- `frontend/src/pages/ScenarioReport.jsx`
- `frontend/src/pages/deployment/SAPConfigBuilder.jsx`

---

## Architecture Decision: Phased Proxy Pattern

A full immediate refactor is too risky (31+ backend files, live DB). We use a **proxy pattern** that correctly models the data while maintaining backward compatibility through a migration path.

### Core Principle

Every external party in the supply chain network is represented by a `TradingPartner` record. The `Site` table retains a thin "network endpoint" row for external parties (to preserve lane connectivity in the DAG) but that row now carries a mandatory `trading_partner_id` FK. Over time, Phase 3+ eliminates the proxy Site rows entirely.

### TransportationLane for External Flows

External material flow does NOT use TransportationLane (which is site-to-site). Instead:
- **Inbound (vendor → site)**: `SourcingRule` with `supply_type='buy'` + vendor lead time from `VendorLeadTime`
- **Outbound (site → customer)**: `OutboundOrderLine` + `FulfillmentOrder` with customer from `TradingPartner`

This means the Beer Game's "MARKET_SUPPLY → Retailer" lane becomes a `SourcingRule(buy)` on the first internal site, and "MARKET_DEMAND ← Retailer" becomes a demand source on the last internal site.

---

## Phases

### Phase 1: Add TradingPartner linkage to Site (Non-breaking)

**Goal**: Every MARKET_SUPPLY and MARKET_DEMAND site gets a linked TradingPartner record. No behavior changes.

**Changes**:

1. **`backend/app/models/supply_chain_config.py`**:
   - Add `trading_partner_id` column (Integer, FK → `trading_partners._id`, nullable=True) to `Site`
   - Add relationship `trading_partner` on `Site`
   - Rename `MARKET_SUPPLY` → `EXTERNAL_SUPPLY`, `MARKET_DEMAND` → `EXTERNAL_DEMAND` in `NodeType` (keep old values for migration)

2. **DB Migration**: Add `trading_partner_id` column to `site` table.

3. **`backend/app/services/synthetic_data_generator.py`** and **`food_dist_config_generator.py`**:
   - When creating MARKET_SUPPLY nodes, also create a `TradingPartner(tpartner_type='vendor')` and link via `trading_partner_id`
   - When creating MARKET_DEMAND nodes / Market entries, also create `TradingPartner(tpartner_type='customer')` and link

4. **Migrate existing data**: Script to backfill `trading_partner_id` for existing MARKET_SUPPLY/MARKET_DEMAND sites.

**Validation**: All existing tests pass. New `trading_partner_id` populated for all external sites.

---

### Phase 2: Update Planning Logic to Use TradingPartner

**Goal**: Planning services use `TradingPartner` attributes (lead times, reliability) rather than treating external nodes as generic Sites.

**Changes**:

1. **`backend/app/services/supply_plan_service.py`**:
   - For `supply_type='buy'` sourcing rules: resolve vendor lead time from `VendorLeadTime` (not Site attributes)
   - For demand: resolve customer demand from `TradingPartner` (customer) + `MarketDemand`

2. **`backend/app/services/sc_planning/planner.py`**:
   - Update demand sourcing to pull from `TradingPartner(customer)` records
   - Update supply sourcing to pull from `TradingPartner(vendor)` lead times

3. **`backend/app/services/fulfillment_service.py`** and **`order_promising.py`**:
   - When order `to_site` is EXTERNAL_DEMAND, resolve customer from linked TradingPartner

4. **`backend/app/services/sap_config_builder.py`**:
   - Map SAP vendors (LFA1) → `TradingPartner(vendor)` directly (not via Site)
   - Map SAP customers (KNA1) → `TradingPartner(customer)` directly
   - Remove `MASTER_MARKET_SUPPLY/DEMAND` constants and `_infer_master_type` paths that create Site rows for external entities

---

### Phase 3: Remove External Nodes from Site Table

**Goal**: `Site` table contains ONLY internal company locations. External parties live exclusively in `TradingPartner`.

**Changes**:

1. **`backend/app/models/supply_chain_config.py`**:
   - Remove `EXTERNAL_SUPPLY` and `EXTERNAL_DEMAND` from `NodeType`
   - Remove `MARKET_SUPPLY` and `MARKET_DEMAND` from `NodeType`

2. **`backend/app/models/supply_chain_config.py` — TransportationLane**:
   - Add `from_partner_id` (Integer, FK → `trading_partners._id`, nullable=True)
   - Add `to_partner_id` (Integer, FK → `trading_partners._id`, nullable=True)
   - Constraint: `(from_site_id IS NOT NULL OR from_partner_id IS NOT NULL)` and `(to_site_id IS NOT NULL OR to_partner_id IS NOT NULL)`

3. **Migrate existing data**:
   - For lanes with EXTERNAL_SUPPLY/DEMAND endpoints: move the Site FK to the new partner FK columns
   - Delete the proxy Site rows

4. **`backend/app/api/endpoints/supply_chain_config.py`**:
   - DAG validation: sources can be `TradingPartner(vendor)` (not Site), sinks can be `TradingPartner(customer)`
   - Topology response: include TradingPartner endpoints in Sankey data

5. **All 31 backend files**: Replace `master_type in (MARKET_SUPPLY, MARKET_DEMAND)` guards with TradingPartner-aware checks.

6. **`backend/app/services/powell/site_capabilities.py`**:
   - External TradingPartner nodes get 0 TRMs (no hive — outside company authority)
   - Remove `'MARKET_SUPPLY': []` and `'MARKET_DEMAND': []` mappings

---

### Phase 4: Market Table Migration

**Goal**: Merge `Market` and `MarketDemand` into TradingPartner-based demand records.

**Current**: `Market` table has `name`, `company`, `description` — basically a demand pool label.
**Target**: This is a `TradingPartner(tpartner_type='customer')` with `MarketDemand` records linked via `trading_partner_id` instead of `market_id`.

**Changes**:

1. **`backend/app/models/supply_chain_config.py`**:
   - Add `trading_partner_id` FK to `MarketDemand` (alongside existing `market_id` during transition)
   - Migrate `MarketDemand.market_id` → resolved `TradingPartner._id`
   - Deprecate `Market` table (keep for backward compatibility until all data migrated)

2. **`backend/app/services/synthetic_data_generator.py`**:
   - Create `TradingPartner(customer)` instead of `Market` entries

3. **API responses**: Return customer TradingPartner info where Market info was returned.

---

### Phase 5: Frontend Updates

**Goal**: UI shows Sites (internal) and Trading Partners (external) in separate sections.

**Changes**:

1. **`frontend/src/components/supply-chain-config/SupplyChainConfigSankey.jsx`**:
   - Color-code TradingPartner nodes differently from Site nodes
   - Show vendor node shape (diamond) vs site node shape (rectangle)
   - Tooltip shows TradingPartner attributes (DUNS, lead time, reliability score)

2. **`frontend/src/components/cascade/PlanningCascadeSankey.jsx`**:
   - Update to receive TradingPartner data for external endpoints
   - Remove MARKET_SUPPLY/DEMAND special-casing

3. **`frontend/src/services/supplyChainConfigService.js`**:
   - Update API calls to include TradingPartner data in config responses

4. **`frontend/src/pages/deployment/SAPConfigBuilder.jsx`**:
   - Show vendor/customer sections from TradingPartner records

---

## Terminology Changes

| Old Term | New Term | Notes |
|----------|----------|-------|
| `MARKET_SUPPLY` | `TradingPartner(vendor)` | External supplier |
| `MARKET_DEMAND` | `TradingPartner(customer)` | External customer |
| `NodeType.MARKET_SUPPLY` | (removed) | No Site equivalent |
| `NodeType.MARKET_DEMAND` | (removed) | No Site equivalent |
| `master_type='market_supply'` | `tpartner_type='vendor'` | On TradingPartner |
| `master_type='market_demand'` | `tpartner_type='customer'` | On TradingPartner |
| `Market` table | `TradingPartner(customer)` | Merge in Phase 4 |

---

## Impact on Existing Features

| Feature | Impact | Notes |
|---------|--------|-------|
| Beer Game (Learning Tenant) | Low | Factory's upstream = TradingPartner vendor. Retailer's downstream = TradingPartner customer. |
| Supply Planning | Medium | Demand sources from TradingPartner.customer instead of MARKET_DEMAND site |
| MRP/MPS | Medium | Buy sourcing rules already use vendor_id — just need to populate it |
| GNN training | Low | External nodes masked out of hive; GNN input graph excludes non-site nodes |
| TRM hive | Low | MARKET_SUPPLY/DEMAND already got 0 TRMs — no change to behavior |
| SAP integration | Positive | Direct LFA1→vendor, KNA1→customer mapping without fake Sites |
| Sankey diagrams | Medium | Need to show TradingPartner nodes with different visual treatment |
| DAG validation | Medium | Sources/sinks now TradingPartner instead of Site |

---

## DB Migration Script Outline

```sql
-- Phase 1: Add trading_partner_id to site
ALTER TABLE site ADD COLUMN trading_partner_id INTEGER REFERENCES trading_partners(_id);

-- Phase 1: Backfill - create TradingPartner records for existing external sites
-- (Run via Python migration script, not pure SQL)

-- Phase 3: Add partner columns to transportation_lane
ALTER TABLE transportation_lane ADD COLUMN from_partner_id INTEGER REFERENCES trading_partners(_id);
ALTER TABLE transportation_lane ADD COLUMN to_partner_id INTEGER REFERENCES trading_partners(_id);

-- Phase 3: Make site FKs on transportation_lane nullable
ALTER TABLE transportation_lane ALTER COLUMN from_site_id DROP NOT NULL;
ALTER TABLE transportation_lane ALTER COLUMN to_site_id DROP NOT NULL;
```

---

## Success Criteria

- [ ] Phase 1: All MARKET_SUPPLY/DEMAND sites have a linked TradingPartner. No test regressions.
- [ ] Phase 2: Planning services use VendorLeadTime for buy lead times (not Site attributes).
- [ ] Phase 3: `Site` table has 0 rows with `master_type IN ('MARKET_SUPPLY', 'MARKET_DEMAND')`.
- [ ] Phase 3: `NodeType` enum has no MARKET_SUPPLY/DEMAND values.
- [ ] Phase 4: `Market` table is empty; all demand linked via TradingPartner.
- [ ] Phase 5: Sankey diagrams distinguish internal Sites from external TradingPartners visually.
- [ ] All phases: AWS SC DM compliance check passes (35/35 entities, correct field usage).
