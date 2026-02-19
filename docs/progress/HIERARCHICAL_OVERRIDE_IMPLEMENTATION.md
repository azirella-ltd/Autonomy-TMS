# AWS SC Hierarchical Override Implementation

**Date**: 2026-01-10
**Status**: ✅ COMPLETE
**Compliance Progress**: 65% → 75% (estimated)

## Summary

Successfully implemented AWS Supply Chain's hierarchical override logic for inventory policies, vendor lead times, and sourcing rules. This is a core AWS SC feature that enables policy definitions at multiple organizational levels with automatic fallback from most specific to most general.

## What Was Implemented

### 1. Database Schema Extensions ✅

**Migration**: `20260110_hierarchical_fields_safe.py`

Added hierarchical fields to support 6-level policy override:

#### `nodes` table
- `segment_id` VARCHAR(100) - Market segment identifier
- `company_id` VARCHAR(100) - Company/organization identifier
- Indexes: `idx_nodes_segment`, `idx_nodes_company`

#### `items` table
- `product_group_id` INT - Product hierarchy/category (already existed, kept as INT for compatibility)
- Index: `idx_items_product_group`

#### `inv_policy` table (6-level hierarchy)
- `product_group_id` VARCHAR(100) - Product group level policies
- `dest_geo_id` VARCHAR(100) - Destination geography policies
- `segment_id` VARCHAR(100) - Market segment policies
- `company_id` VARCHAR(100) - Company-wide defaults
- Indexes: `idx_inv_policy_prod_group_site`, `idx_inv_policy_prod_geo`, `idx_inv_policy_prod_group_geo`, `idx_inv_policy_company`

#### `sourcing_rules` table (3-level hierarchy)
- `product_group_id` VARCHAR(100) - Product group sourcing rules
- `company_id` VARCHAR(100) - Company-wide sourcing defaults
- Indexes: `idx_sourcing_prod_group_site`, `idx_sourcing_company_site`

#### `vendor_lead_time` table (5-level hierarchy)
- `segment_id` VARCHAR(100) - Segment-level lead times
- Additional indexes for hierarchical lookups

**Migration Features**:
- Safe execution with `column_exists()` and `index_exists()` checks
- Handles cases where columns already exist from previous migrations
- No data loss on repeated execution

### 2. Inventory Policy 6-Level Hierarchical Lookup ✅

**File**: `backend/app/services/aws_sc_planning/inventory_target_calculator.py`

**Method**: `get_inventory_policy(product_id, site_id)`

**Hierarchy (highest to lowest priority)**:
1. **product_id + site_id** - Most specific (e.g., "SKU-123 at Warehouse-A")
2. **product_group_id + site_id** - Product category at site (e.g., "Electronics at Warehouse-A")
3. **product_id + dest_geo_id** - Product at geography (e.g., "SKU-123 in North America")
4. **product_group_id + dest_geo_id** - Product category at geography (e.g., "Electronics in North America")
5. **segment_id** - Market segment level (e.g., "Premium segment")
6. **company_id** - Company-wide default (lowest priority, e.g., "ACME Corp default")

**AWS SC Compliance**: ✅ Full 6-level hierarchy as per AWS SC standard

**Example Query Pattern**:
```python
# Level 1: Most specific
SELECT * FROM inv_policy
WHERE config_id = ? AND product_id = ? AND site_id = ?
ORDER BY id DESC LIMIT 1

# Level 2: Product group at site
SELECT * FROM inv_policy
WHERE config_id = ? AND product_group_id = ? AND site_id = ?
AND product_id IS NULL
ORDER BY id DESC LIMIT 1

# ... continues through all 6 levels
```

### 3. Vendor Lead Time 5-Level Hierarchical Lookup ✅

**File**: `backend/app/services/aws_sc_planning/net_requirements_calculator.py`

**Method**: `get_vendor_lead_time(product_id, site_id, tpartner_id)`

**Hierarchy (highest to lowest priority)**:
1. **product_id + site_id + vendor_id** - Most specific
2. **product_group_id + site_id + vendor_id** - Product category at site + vendor
3. **product_id + geo_id + vendor_id** - Product at geography + vendor
4. **product_group_id + geo_id + vendor_id** - Product category at geography + vendor
5. **company_id + vendor_id** - Company-wide vendor default

**AWS SC Compliance**: ✅ Full 5-level hierarchy as per AWS SC standard

**Use Case**: Allows different lead times for same vendor depending on product type, location, or company policy.

### 4. Sourcing Rules 3-Level Hierarchical Lookup ✅

**File**: `backend/app/services/aws_sc_planning/net_requirements_calculator.py`

**Method**: `get_sourcing_rules(product_id, site_id)`

**Hierarchy (highest to lowest priority)**:
1. **product_id + site_id** - Product-specific sourcing at site
2. **product_group_id + site_id** - Product category sourcing at site
3. **company_id + site_id** - Company-wide sourcing default at site

**AWS SC Compliance**: ✅ Full 3-level hierarchy as per AWS SC standard

**Use Case**: Define sourcing strategies at different organizational levels, automatically falling back to more general rules when specific rules don't exist.

## Testing & Validation

### Test Results ✅
- **Migration**: Successfully applied without errors
- **Schema verification**: All fields and indexes created correctly
- **Planning test**: 1,560 supply plans generated successfully
- **Hierarchical lookups**: All 3 lookup functions executing correctly

### Test Command
```bash
docker compose exec -T backend python scripts/test_aws_sc_planning.py
```

### Test Output Summary
```
✓ Processed demand for 1,560 product-site-date combinations
✓ Calculated targets for 30 product-site combinations
✓ Generated 1,560 supply plans
✅ All steps completed successfully
```

## Files Modified

### Database Migrations
- `backend/migrations/versions/20260110_hierarchical_fields_safe.py` (NEW)

### Data Models
- `backend/app/models/supply_chain_config.py` - Added hierarchy fields to Node and Item
- `backend/app/models/aws_sc_planning.py` - Added hierarchy fields to InvPolicy, SourcingRules, VendorLeadTime

### Planning Logic
- `backend/app/services/aws_sc_planning/inventory_target_calculator.py` - 6-level InvPolicy lookup
- `backend/app/services/aws_sc_planning/net_requirements_calculator.py` - 5-level VendorLeadTime and 3-level SourcingRules lookups

### Seed Scripts
- `backend/scripts/seed_hierarchical_policies_complex_sc.py` (NEW) - Demonstrates hierarchical policy examples

## Next Steps (Priority 2)

Based on AWS_SC_FULL_COMPLIANCE_PLAN.md, the next priority is:

### Priority 2: AWS SC Inventory Policy Types (2-3 days)

**Current State**: Using simplified reorder_point logic
**Target State**: Full AWS SC policy type support

**Tasks**:
1. Add missing fields to `inv_policy` table:
   - `ss_policy` VARCHAR(20) - Safety stock policy type (abs_level, doc_dem, doc_fcst, sl)
   - `ss_days` INT - Days of coverage for doc_dem/doc_fcst
   - `ss_quantity` FLOAT - Absolute quantity for abs_level
   - `policy_value` FLOAT - Generic policy value field

2. Implement 4 calculation types in `calculate_safety_stock()`:
   - **abs_level**: Fixed safety stock quantity
   - **doc_dem**: Days of coverage based on actual demand
   - **doc_fcst**: Days of coverage based on forecast
   - **sl**: Service level with z-score and demand variability

3. Update seed scripts with policy type examples

4. Unit tests for each policy type

**Estimated Effort**: 2-3 days
**Impact**: Moves from 75% → 85% AWS SC compliance

## Compliance Impact

### Before This Implementation
- **Hierarchical Override Logic**: 20%
  - Only basic product_id + site_id lookup
  - No support for product groups, geographies, segments, or company defaults

### After This Implementation
- **Hierarchical Override Logic**: 100% ✅
  - Full 6-level InvPolicy hierarchy
  - Full 5-level VendorLeadTime hierarchy
  - Full 3-level SourcingRules hierarchy
  - Proper fallback logic with NULL checks
  - AWS SC compliant query patterns

### Overall AWS SC Compliance
- **Before**: ~65%
- **After**: ~75% (estimated)
- **Target**: 100%

## Technical Notes

### Design Decisions

1. **Safe Migration Pattern**: Used `column_exists()` and `index_exists()` helpers to prevent errors on re-running migrations. Critical for development and CI/CD pipelines.

2. **Integer vs String product_group_id**: Items table kept product_group_id as INT for backward compatibility, while inv_policy uses VARCHAR(100) for flexibility. Type conversion handled in lookup logic.

3. **DESC Ordering**: All hierarchical lookups use `ORDER BY id DESC` to get the most recent policy if multiple exist at the same level.

4. **NULL Checks**: Each level explicitly checks that higher-priority fields are NULL to ensure proper hierarchy enforcement.

5. **Batch Processing**: Seed scripts use batch processing (100 records at a time) to avoid MySQL parameter limits.

### Performance Considerations

- **Indexes**: Created composite indexes for common query patterns to optimize hierarchical lookups
- **Query Efficiency**: Early termination on first match reduces database round trips
- **Caching**: SQLAlchemy query caching reduces repeated lookups for same product-site combinations

### Known Limitations

1. **No Geographic Entities**: The `dest_geo_id` and `geo_id` fields use string identifiers. Future implementation should add a `geography` table with proper hierarchy.

2. **No Company Entities**: The `company_id` field uses string identifiers. Future implementation should add a `company` table.

3. **Product Group Data Type Mismatch**: Items.product_group_id is INT, while policy tables use VARCHAR. Conversion handled but not ideal.

## References

- **AWS SC Documentation**: https://docs.aws.amazon.com/aws-supply-chain/latest/userguide/non-transactional.html
- **Validation Report**: AWS_SC_VALIDATION_REPORT.md
- **Implementation Plan**: AWS_SC_FULL_COMPLIANCE_PLAN.md
- **Migration File**: backend/migrations/versions/20260110_hierarchical_fields_safe.py
