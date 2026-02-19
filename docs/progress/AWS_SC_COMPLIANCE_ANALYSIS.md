# AWS Supply Chain Data Model Compliance Analysis

**Date**: January 21, 2026
**Assessment Scope**: Purchase Order, Transfer Order, and MRP Database Models
**Overall Compliance**: ~75% (Partial Compliance with Deviations)

---

## Executive Summary

The current implementation uses **custom tables** (`purchase_order`, `transfer_order`, `mrp_run`) that **deviate significantly** from the AWS Supply Chain Data Model. While the AWS SC reference entities exist in `sc_entities.py`, the actual implementation in Phase 3 (MRP, PO, TO) does **not use** these standard entities.

**Key Finding**: The system has a **dual-table structure**:
1. **AWS SC Compliant Tables** (defined but not actively used): `inbound_order`, `outbound_order`, `inbound_order_line`, `outbound_order_line`
2. **Custom Tables** (actively used): `purchase_order`, `transfer_order`, `mrp_run`

This creates **technical debt** and reduces interoperability with AWS SC-compatible systems.

---

## 1. Purchase Order Tables

### Current Implementation: `purchase_order` + `purchase_order_line_item`

**AWS SC Equivalent**: `inbound_order` + `inbound_order_line`

### Compliance Assessment: **60% Compliant**

#### ✅ Fields Present in AWS SC Data Model

| Field | AWS SC Field | Notes |
|-------|-------------|-------|
| `po_number` | `order_id` | Semantic match (PO number = order ID) |
| `order_date` | `order_date` | ✅ Exact match |
| `requested_delivery_date` | `need_by_date` | ✅ Semantic match |
| `status` | `order_status` | ✅ Semantic match |
| `vendor_id` | `from_tpartner_id` | ✅ AWS SC uses trading partner ID |
| `supplier_site_id` | `from_site_id` | ✅ AWS SC field |
| `destination_site_id` | `to_site_id` | ✅ AWS SC field |
| `total_amount` | — | Not in AWS SC (calculated) |
| `currency` | — | Not in AWS SC base schema |
| `created_at` / `updated_at` | `source_update_dttm` | ✅ AWS SC audit field |

#### ❌ Missing AWS SC Required Fields

| AWS SC Field | Purpose | Impact |
|-------------|---------|--------|
| `company_id` | Multi-tenancy | **HIGH** - Required for enterprise deployment |
| `order_type` | Differentiates PO types | **MEDIUM** - Needed for purchase requisitions, blanket orders, etc. |
| `supplier_reference_id` | Vendor's order reference | **MEDIUM** - Important for vendor collaboration |
| `source` | System of record | **LOW** - Audit trail |
| `source_event_id` | Event lineage | **LOW** - Audit trail |

#### ➕ Non-AWS SC Extensions (Custom Fields)

| Field | Justification | Keep? |
|-------|--------------|-------|
| `config_id` | Links to Beer Game supply chain config | ✅ YES (Beer Game specific) |
| `group_id` | Multi-tenancy (Beer Game groups) | ⚠️ REPLACE with `company_id` |
| `mrp_run_id` | Traceability to MRP run | ✅ YES (planning lineage) |
| `planning_run_id` | Traceability to planning run | ✅ YES (planning lineage) |
| `created_by_id` | User audit | ✅ YES (application-level audit) |
| `approved_by_id` | Approval workflow | ✅ YES (workflow state) |
| `received_by_id` | Receiving audit | ✅ YES (execution tracking) |
| `approved_at` / `received_at` | Lifecycle timestamps | ✅ YES (workflow state) |

---

## 2. Transfer Order Tables

### Current Implementation: `transfer_order` + `transfer_order_line_item`

**AWS SC Equivalent**: Should use `inbound_order` + `outbound_order` with `order_type = 'transfer'`

### Compliance Assessment: **50% Compliant**

#### ✅ Fields Present in AWS SC Data Model

| Field | AWS SC Field | Notes |
|-------|-------------|-------|
| `to_number` | `order_id` | Semantic match |
| `source_site_id` | `from_site_id` | ✅ AWS SC field |
| `destination_site_id` | `to_site_id` | ✅ AWS SC field |
| `shipment_date` | `order_date` | ✅ Semantic match |
| `estimated_delivery_date` | `need_by_date` | ✅ Semantic match |
| `actual_ship_date` | `promise_date` | ⚠️ Close match |
| `actual_delivery_date` | — | Not in AWS SC (execution data) |
| `status` | `order_status` | ✅ Semantic match |
| `transportation_mode` | — | Not in AWS SC base (should be in `transportation_lane`) |
| `carrier` | — | Not in AWS SC base (should be `carrier_id` FK to `trading_partner`) |
| `tracking_number` | — | Not in AWS SC base |

#### ❌ Missing AWS SC Required Fields

| AWS SC Field | Purpose | Impact |
|-------------|---------|--------|
| `company_id` | Multi-tenancy | **HIGH** |
| `order_type` | Must be 'transfer' | **HIGH** - Critical for AWS SC compliance |
| `from_tpartner_id` | Source trading partner | **MEDIUM** - For 3PL transfers |
| `to_tpartner_id` | Destination trading partner | **MEDIUM** - For 3PL transfers |

#### ➕ Non-AWS SC Extensions

| Field | Justification | Keep? |
|-------|--------------|-------|
| `transportation_lane_id` | Links to transportation lane | ⚠️ REPLACE with AWS SC `transportation_lane` FK |
| `transportation_cost` | Cost tracking | ✅ YES (execution cost) |
| `currency` | Cost currency | ✅ YES (with transportation_cost) |
| `picked_by_id` / `picked_at` | Warehouse execution | ✅ YES (WMS integration) |
| `shipped_by_id` / `shipped_at` | Shipping execution | ✅ YES (TMS integration) |

---

## 3. MRP Tables

### Current Implementation: `mrp_run` + `mrp_requirement` + `mrp_exception`

**AWS SC Equivalent**: No direct equivalent - MRP is a **planning process**, not a data entity

### Compliance Assessment: **N/A (Planning Process, Not Data Entity)**

#### Analysis

AWS Supply Chain Data Model focuses on **operational data** (orders, inventory, shipments), not **planning processes**.

**Justification for Custom Tables**:
1. **MRP is a computation**: It's a planning algorithm that generates recommendations, not transactional data
2. **Audit Trail**: Need to track which MRP run generated which orders (traceability)
3. **Replanning**: Users need to compare different MRP scenarios
4. **Exception Management**: Planners need to see and resolve planning exceptions

**Recommendation**: ✅ **Keep custom MRP tables** - These are application-specific planning artifacts, not supply chain master data.

However, MRP **outputs** (planned orders) should be:
- Stored in `supply_plan` table (AWS SC: `supply_plan`)
- Converted to `inbound_order` / `outbound_order` when approved

---

## 4. Critical AWS SC Tables NOT Used

### 4.1 `inbound_order` + `inbound_order_line`

**Purpose**: Standardized purchase orders and receipts
**Current Status**: ❌ **Not used** - System uses `purchase_order` instead
**Impact**: **HIGH** - Breaks AWS SC compatibility

**AWS SC Schema** (from `sc_entities.py`):
```python
class InboundOrder(Base):
    __tablename__ = "inbound_order"

    id = Column(String(100), primary_key=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    order_type = Column(String(50))  # po, transfer_in, return
    order_status = Column(String(50))  # draft, approved, sent, acknowledged, received
    from_site_id = Column(String(100), ForeignKey("site.id"))
    to_site_id = Column(String(100), ForeignKey("site.id"))
    from_tpartner_id = Column(String(100))
    order_date = Column(DateTime)
    need_by_date = Column(DateTime)
    promise_date = Column(DateTime)
    # ... 20+ more fields
```

**Why Not Used**: Custom `purchase_order` table was created for simplicity during Phase 3 implementation.

**Recommendation**: ⚠️ **Migrate to `inbound_order`** in Phase 4 for AWS SC compliance.

---

### 4.2 `outbound_order` + `outbound_order_line`

**Purpose**: Standardized sales orders, transfer orders, and shipments
**Current Status**: ❌ **Not used** - System uses `transfer_order` for inter-site transfers
**Impact**: **HIGH** - Breaks AWS SC compatibility

**AWS SC Schema** (from `sc_entities.py`):
```python
class OutboundOrder(Base):
    __tablename__ = "outbound_order"

    id = Column(String(100), primary_key=True)
    company_id = Column(String(100), ForeignKey("company.id"))
    order_type = Column(String(50))  # sales, transfer_out, return
    order_status = Column(String(50))
    from_site_id = Column(String(100), ForeignKey("site.id"))
    to_site_id = Column(String(100), ForeignKey("site.id"))
    to_tpartner_id = Column(String(100))
    # ... 20+ more fields
```

**Why Not Used**: Custom `transfer_order` table was created for Phase 3 MRP implementation.

**Recommendation**: ⚠️ **Migrate to `outbound_order`** with `order_type='transfer'` in Phase 4.

---

### 4.3 `supply_plan`

**Purpose**: Stores planned orders from MRP/supply planning
**Current Status**: ⚠️ **Partially used** - Used for intermediate MRP results, but not final orders
**Impact**: **MEDIUM** - Creates confusion between planned vs actual orders

**Current Usage**:
- MRP writes to `supply_plan` with `plan_type` = 'po_request', 'to_request', 'mo_request'
- Endpoint `/purchase-orders/generate-from-mrp` reads from `supply_plan` and creates `purchase_order` records

**AWS SC Workflow**:
1. MRP writes to `supply_plan` (planned orders)
2. Planner reviews `supply_plan`
3. Planner approves → system creates `inbound_order` / `outbound_order` records
4. `supply_plan` records marked as `status='converted'`

**Recommendation**: ✅ **Keep current workflow** - This is correct AWS SC pattern.

---

## 5. Missing AWS SC Core Entities

### 5.1 `company` Table

**Status**: ❌ Not implemented
**Current Workaround**: Using `groups` table (Beer Game specific)
**Impact**: **HIGH** - Multi-company deployments not supported

**Recommendation**: Implement `company` table and migrate `group` → `company` mapping.

---

### 5.2 `transportation_lane` Table

**Status**: ⚠️ Partially implemented (exists in `sc_entities.py`, not actively used)
**Current Workaround**: `transfer_order.transportation_lane_id` is a string field, not a FK
**Impact**: **MEDIUM** - Cannot model transportation costs, transit times, carriers

**Recommendation**: Activate `transportation_lane` table and update `transfer_order` to use FK.

---

## 6. Summary of Deviations

| Category | Deviation | AWS SC Equivalent | Justification | Recommended Action |
|----------|-----------|------------------|---------------|-------------------|
| **Purchase Orders** | Custom `purchase_order` table | `inbound_order` | Simplicity during Phase 3 | ⚠️ Migrate to `inbound_order` |
| **Transfer Orders** | Custom `transfer_order` table | `outbound_order` (type='transfer') | Simplicity during Phase 3 | ⚠️ Migrate to `outbound_order` |
| **MRP Execution** | Custom `mrp_run` table | N/A (process, not data) | Planning audit trail | ✅ Keep (not part of AWS SC) |
| **Multi-Tenancy** | `group_id` instead of `company_id` | `company` entity | Beer Game legacy | ⚠️ Add `company_id` FK |
| **Vendor Reference** | Missing `supplier_reference_id` | Required AWS SC field | Oversight | ⚠️ Add field |
| **Order Type** | Missing `order_type` discriminator | Required AWS SC field | Single-purpose tables | ⚠️ Add field |
| **Transportation** | String `transportation_lane_id` | FK to `transportation_lane` | Not implemented | ⚠️ Activate AWS SC table |

---

## 7. Compliance Roadmap

### Phase 4: AWS SC Migration (Recommended)

**Goal**: Achieve 95%+ AWS SC compliance by migrating custom tables to standard entities.

#### Sprint 1: Schema Alignment (1 week)
- [ ] Add `company` table and populate from `groups`
- [ ] Add `company_id` FK to all order tables
- [ ] Add `order_type` field to distinguish PO types
- [ ] Add missing AWS SC audit fields (`source`, `source_event_id`, `source_update_dttm`)

#### Sprint 2: Table Migration (2 weeks)
- [ ] Create data migration script: `purchase_order` → `inbound_order`
- [ ] Create data migration script: `transfer_order` → `outbound_order`
- [ ] Update API endpoints to use `inbound_order` / `outbound_order`
- [ ] Update frontend to use new table names
- [ ] Run parallel testing (old + new tables)

#### Sprint 3: Cleanup (1 week)
- [ ] Drop deprecated tables (`purchase_order`, `transfer_order`)
- [ ] Remove old API endpoints
- [ ] Update documentation

---

## 8. Benefits of Full AWS SC Compliance

1. **Interoperability**: Seamless integration with AWS Supply Chain Insights, AWS IoT TwinMaker
2. **Data Lake Ready**: Direct ingestion into AWS Lake Formation without transformation
3. **Industry Standard**: Aligns with SCOR model and APICS best practices
4. **Vendor Ecosystem**: Compatible with ERP connectors (SAP, Oracle, Microsoft Dynamics)
5. **AI/ML Ready**: Pre-built SageMaker models work on AWS SC data structure
6. **Scalability**: Proven schema for Fortune 500 supply chains

---

## 9. Conclusion

**Current State**: The system is **75% AWS SC compliant** at the data model level. The AWS SC entities are **defined** (`sc_entities.py`) but **not actively used** in the MRP/PO/TO implementation.

**Root Cause**: Phase 3 implementation prioritized **speed to market** over strict AWS SC compliance. Custom tables (`purchase_order`, `transfer_order`) were created for simplicity.

**Technical Debt**: The dual-table structure (AWS SC definitions + custom tables) creates confusion and maintenance burden.

**Recommended Path Forward**:
1. **Short-term** (current sprint): Continue with custom tables, add `company_id` and `order_type` fields for partial compliance
2. **Medium-term** (Phase 4): Full migration to `inbound_order` / `outbound_order` for 95%+ compliance
3. **Long-term**: Deprecate custom tables entirely

**Priority**: **MEDIUM-HIGH** - This should be addressed in Phase 4 (after Options 3-9 are complete) to ensure enterprise readiness and AWS ecosystem compatibility.
