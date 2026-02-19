# AWS Supply Chain - Full Compliance Implementation Plan

**Goal**: Achieve 100% AWS SC Certification Compliance
**Current Status**: 65% Complete
**Target**: 100% Complete
**Estimated Effort**: 8-12 days

---

## Phase 3: Full AWS SC Compliance Implementation

### Priority 1: Hierarchical Override Logic (3-5 days) 🔥

#### 1.1 Schema Extensions
**Files to modify**:
- `backend/app/models/supply_chain_config.py` (Node, Item)
- `backend/app/models/aws_sc_planning.py` (InvPolicy, SourcingRules, VendorLeadTime)
- New migration: `20260110_hierarchical_fields.py`

**Changes**:
```sql
-- Add to nodes table
ALTER TABLE nodes ADD COLUMN geo_id VARCHAR(100);
ALTER TABLE nodes ADD COLUMN segment_id VARCHAR(100);
ALTER TABLE nodes ADD COLUMN company_id VARCHAR(100);

-- Add to items table
ALTER TABLE items ADD COLUMN product_group_id VARCHAR(100);

-- Add to inv_policy table
ALTER TABLE inv_policy ADD COLUMN product_group_id VARCHAR(100);
ALTER TABLE inv_policy ADD COLUMN dest_geo_id VARCHAR(100);
ALTER TABLE inv_policy ADD COLUMN segment_id VARCHAR(100);
ALTER TABLE inv_policy ADD COLUMN company_id VARCHAR(100);

-- Add to sourcing_rules table
ALTER TABLE sourcing_rules ADD COLUMN product_group_id VARCHAR(100);
ALTER TABLE sourcing_rules ADD COLUMN company_id VARCHAR(100);

-- Add to vendor_lead_time table (if exists)
ALTER TABLE vendor_lead_time ADD COLUMN product_group_id VARCHAR(100);
ALTER TABLE vendor_lead_time ADD COLUMN geo_id VARCHAR(100);
ALTER TABLE vendor_lead_time ADD COLUMN segment_id VARCHAR(100);
ALTER TABLE vendor_lead_time ADD COLUMN company_id VARCHAR(100);
```

#### 1.2 Implement 6-Level InvPolicy Lookup
**File**: `backend/app/services/aws_sc_planning/inventory_target_calculator.py`

**Logic**:
1. Try: product_id + site_id (exact match) ✅ Already done
2. Try: product_id + dest_geo_id
3. Try: product_group_id + site_id
4. Try: product_group_id + dest_geo_id
5. Try: site_id only
6. Try: dest_geo_id only
7. Try: segment_id only
8. Try: company_id only (default)

#### 1.3 Implement 5-Level VendorLeadTime Lookup
**File**: `backend/app/services/aws_sc_planning/inventory_target_calculator.py`

**Logic**:
1. Try: product_id + site_id
2. Try: product_id + geo_id
3. Try: product_group_id + site_id
4. Try: product_group_id + geo_id
5. Try: company_id (default)

#### 1.4 Implement 3-Level SourcingRules Lookup
**File**: `backend/app/services/aws_sc_planning/net_requirements_calculator.py`

**Logic**:
1. Try: product_id + site_id ✅ Already done
2. Try: product_group_id + site_id
3. Try: company_id + site_id (default)

**Estimated Effort**: 3-5 days

---

### Priority 2: AWS SC Standard Inventory Policy Types (2-3 days) 🔥

#### 2.1 Schema Changes
**Migration**: `20260110_inv_policy_aws_fields.py`

```sql
ALTER TABLE inv_policy ADD COLUMN ss_policy VARCHAR(20);
ALTER TABLE inv_policy ADD COLUMN ss_quantity DECIMAL(10,2);
ALTER TABLE inv_policy ADD COLUMN ss_days INT;
ALTER TABLE inv_policy ADD COLUMN policy_value DECIMAL(10,2);

-- Add check constraint
ALTER TABLE inv_policy ADD CONSTRAINT chk_ss_policy
  CHECK (ss_policy IN ('abs_level', 'doc_dem', 'doc_fcst', 'sl'));
```

#### 2.2 Implement All 4 Policy Types
**File**: `backend/app/services/aws_sc_planning/inventory_target_calculator.py`

**Implementations**:

1. **abs_level** (Absolute Level):
```python
if policy.ss_policy == 'abs_level':
    return policy.ss_quantity or 0
```

2. **doc_dem** (Days of Coverage - Demand):
```python
elif policy.ss_policy == 'doc_dem':
    avg_daily_demand = await self.calculate_avg_daily_demand(
        product_id, site_id, start_date, lookback_days=30
    )
    return (policy.ss_days or 0) * avg_daily_demand
```

3. **doc_fcst** (Days of Coverage - Forecast):
```python
elif policy.ss_policy == 'doc_fcst':
    avg_daily_forecast = self.calculate_avg_daily_forecast(
        product_id, site_id, net_demand, start_date, horizon_days=30
    )
    return (policy.ss_days or 0) * avg_daily_forecast
```

4. **sl** (Service Level - Probabilistic):
```python
elif policy.ss_policy == 'sl':
    service_level = policy.service_level or 0.95
    z_score = self.get_z_score(service_level)
    demand_std_dev = await self.calculate_demand_std_dev(
        product_id, site_id, start_date, lookback_days=90
    )
    lead_time = await self.get_replenishment_lead_time(product_id, site_id)
    safety_stock = z_score * demand_std_dev * math.sqrt(lead_time)
    return safety_stock
```

**Note**: All code already exists in commented form - just need to uncomment and wire up!

**Estimated Effort**: 2-3 days

---

### Priority 3: FK References & Vendor Management (2-3 days) 🔥

#### 3.1 Add FK Fields to SourcingRules
**Migration**: `20260110_sourcing_rules_fks.py`

```sql
ALTER TABLE sourcing_rules ADD COLUMN transportation_lane_id INT;
ALTER TABLE sourcing_rules ADD COLUMN production_process_id VARCHAR(100);
ALTER TABLE sourcing_rules ADD COLUMN tpartner_id VARCHAR(100);

ALTER TABLE sourcing_rules ADD CONSTRAINT fk_sr_transport_lane
  FOREIGN KEY (transportation_lane_id) REFERENCES lanes(id);

ALTER TABLE sourcing_rules ADD CONSTRAINT fk_sr_prod_process
  FOREIGN KEY (production_process_id) REFERENCES production_process(id);
```

#### 3.2 Create TradingPartner Entity
**File**: `backend/app/models/aws_sc_planning.py`

```python
class TradingPartner(Base):
    """Trading partner (vendor/customer)"""
    __tablename__ = "trading_partner"

    id = Column(String(100), primary_key=True)  # tpartner_id
    name = Column(String(255), nullable=False)
    tpartner_type = Column(String(50), nullable=False)  # 'Vendor', 'Customer'
    company_id = Column(String(100))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
```

#### 3.3 Create VendorProduct Entity
**File**: `backend/app/models/aws_sc_planning.py`

```python
class VendorProduct(Base):
    """Vendor-specific product information"""
    __tablename__ = "vendor_product"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tpartner_id = Column(String(100), ForeignKey("trading_partner.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    vendor_cost = Column(DECIMAL(10, 2))
    vendor_sku = Column(String(100))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
```

#### 3.4 Update Lead Time Logic
**Files**:
- `net_requirements_calculator.py` (transfer plans)
- `inventory_target_calculator.py` (replenishment lead time)

**Changes**:
- Use `transportation_lane_id` FK to lookup `lanes.transit_time`
- Use `production_process_id` FK to lookup `production_process.manufacturing_leadtime`
- Use `tpartner_id` FK to lookup `vendor_lead_time`

**Estimated Effort**: 2-3 days

---

### Priority 4: Sourcing Schedule (Optional) (1-2 days)

#### 4.1 Create Entities
**File**: `backend/app/models/aws_sc_planning.py`

```python
class SourcingSchedule(Base):
    """Sourcing schedule configuration"""
    __tablename__ = "sourcing_schedule"

    id = Column(String(100), primary_key=True)  # sourcing_schedule_id
    to_site_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    tpartner_id = Column(String(100), ForeignKey("trading_partner.id"))
    from_site_id = Column(Integer, ForeignKey("nodes.id"))
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))

class SourcingScheduleDetails(Base):
    """Sourcing schedule time details"""
    __tablename__ = "sourcing_schedule_details"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sourcing_schedule_id = Column(String(100), ForeignKey("sourcing_schedule.id"), nullable=False)
    company_id = Column(String(100))
    product_group_id = Column(String(100))
    product_id = Column(Integer, ForeignKey("items.id"))
    schedule_date = Column(Date)
    day_of_week = Column(Integer)  # 0=Sun, 1=Mon, ..., 6=Sat
    week_of_month = Column(Integer)  # 1-5
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
```

#### 4.2 Implement Periodic Ordering Logic
**File**: `backend/app/services/aws_sc_planning/net_requirements_calculator.py`

**Logic**:
- Check if sourcing_schedule exists for product-site
- If yes: Only generate orders on scheduled dates
- If no: Continuous review (current behavior)

**Estimated Effort**: 1-2 days

---

### Priority 5: Advanced Features (2-3 days)

#### 5.1 Frozen Horizon for Production
**File**: `backend/app/models/aws_sc_planning.py`

```python
class ProductionProcess(Base):
    # Add fields
    frozen_horizon_days = Column(Integer)
    setup_time = Column(Integer)
```

**Logic**:
- Lock production orders within frozen horizon
- Move all requirements to first period after frozen horizon

#### 5.2 Alternate BOM Component Logic
**File**: `backend/app/services/aws_sc_planning/net_requirements_calculator.py`

**Logic**:
- Group components by `alternate_group`
- Within each group, sort by `priority`
- Select first available component (check inventory)
- If not available, try next priority

#### 5.3 Geography & Company Entities
**File**: `backend/app/models/aws_sc_planning.py`

```python
class Company(Base):
    """Company/organization entity"""
    __tablename__ = "company"

    id = Column(String(100), primary_key=True)
    name = Column(String(255), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))

class Geography(Base):
    """Geographic region hierarchy"""
    __tablename__ = "geography"

    id = Column(String(100), primary_key=True)  # geo_id/region_id
    name = Column(String(255), nullable=False)
    parent_geo_id = Column(String(100), ForeignKey("geography.id"))
    geo_type = Column(String(50))  # 'Region', 'Country', 'State', etc.
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
```

**Estimated Effort**: 2-3 days

---

## Implementation Order

### Week 1: Core Compliance (Days 1-5)
1. **Day 1-2**: Hierarchical schema extensions + migrations
2. **Day 3**: Implement 6-level InvPolicy lookup
3. **Day 4**: Implement AWS SC inventory policy types
4. **Day 5**: Testing & validation

### Week 2: Advanced Features (Days 6-10)
6. **Day 6-7**: FK references (transportation_lane_id, production_process_id, tpartner_id)
7. **Day 8**: TradingPartner + VendorProduct entities
8. **Day 9**: Sourcing Schedule (optional)
9. **Day 10**: Frozen horizon + alternate BOM logic

### Week 3: Polish & Certification (Days 11-12)
10. **Day 11**: End-to-end testing with all features
11. **Day 12**: Documentation update + certification validation

---

## Testing Strategy

### Unit Tests
- Test each hierarchical lookup level independently
- Test all 4 inventory policy types with known inputs
- Test alternate BOM component selection

### Integration Tests
- Run full planning cycle with hierarchical policies
- Test multi-level BOM explosion with alternates
- Test periodic ordering with sourcing schedules

### Validation Tests
- Compare outputs against AWS SC documentation examples
- Verify all entity relationships
- Check constraint enforcement

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| **Data Model Coverage** | 62% | 100% |
| **Field Completeness** | 45% | 95%+ |
| **Hierarchical Override** | 20% | 100% |
| **Inventory Policy Types** | 0% | 100% |
| **BOM Explosion** | 80% | 100% |
| **Overall Compliance** | 65% | 100% |

---

## Migration Strategy

### Backward Compatibility
- All new fields nullable or with defaults
- Existing planning logic remains functional
- Gradual rollout per configuration

### Data Migration
- Populate hierarchy fields from existing data where possible
- Create default Company and Geography records
- Map existing policies to AWS SC types

### Rollback Plan
- Each migration has proper `downgrade()` function
- Keep existing simplified logic as fallback
- Feature flags for new functionality

---

## Documentation Updates Required

1. **Update AWS_SC_IMPLEMENTATION_STATUS.md**
   - Mark all entities as complete
   - Update Phase 2 & 3 status to 100%

2. **Update AWS_SC_VALIDATION_REPORT.md**
   - Re-run validation against AWS docs
   - Update compliance scores to 100%

3. **Create AWS_SC_CERTIFICATION.md**
   - Document full compliance
   - Include test results
   - Provide migration guide

4. **Update README.md**
   - Add AWS SC certification badge
   - Document new planning features
   - Add configuration examples

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing games | Feature flags + backward compatibility |
| Performance degradation | Hierarchical lookups cached, indexed queries |
| Complex schema changes | Incremental migrations, thorough testing |
| Data integrity issues | Foreign key constraints, validation |

---

**Ready to Begin**: Yes ✅
**Priority**: High 🔥
**Expected Completion**: 10-12 days
