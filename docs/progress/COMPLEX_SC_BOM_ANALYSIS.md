# Complex SC Configuration: BOM Analysis & Issues

**Date**: January 22, 2026
**Status**: ❌ **INCOMPLETE** - BOM not traversable from FG to bought materials
**Config**: Complex_SC (ID: 5)

---

## Executive Summary

The Complex SC configuration has **broken BOM data** that prevents DAG traversal from finished goods to purchased materials. The BOM references point to 30 component items that **do not exist** as Product records.

### Critical Issues

1. ❌ **30 component items missing**: BOM references Items 43-72, but these were never migrated to Products
2. ❌ **30 BOM relationships missing**: No ProductBom entries for FG → Component relationships
3. ❌ **Non-existent items**: The component items (43-72) were never created in the original `items` table
4. ✅ **10 finished goods exist**: FG01-FG10 have Product records

**Impact**: Cannot perform:
- MPS key material planning
- BOM explosion for component requirements
- DAG traversal from finished goods to raw materials
- Supply planning with multi-level BOMs

---

## Detailed Analysis

### Product Status

```
Total Products in Complex SC: 10
All marked as: finished_good
```

| Product ID | Description | Type | Status |
|------------|-------------|------|--------|
| FG01 | Finished good for the multi-region supply chain | finished_good | ✅ Exists |
| FG02 | Finished good for the multi-region supply chain | finished_good | ✅ Exists |
| FG03 | Finished good for the multi-region supply chain | finished_good | ✅ Exists |
| FG04 | Finished good for the multi-region supply chain | finished_good | ✅ Exists |
| FG05 | Finished good for the multi-region supply chain | finished_good | ✅ Exists |
| FG06 | Finished good for the multi-region supply chain | finished_good | ✅ Exists |
| FG07 | Finished good for the multi-region supply chain | finished_good | ✅ Exists |
| FG08 | Finished good for the multi-region supply chain | finished_good | ✅ Exists |
| FG09 | Finished good for the multi-region supply chain | finished_good | ✅ Exists |
| FG10 | Finished good for the multi-region supply chain | finished_good | ✅ Exists |

### BOM Structure (in Node Attributes)

**Plant B1 (Node ID: 41)**:
```json
{
  "11": {"43": 1, "44": 1, "45": 1},  // FG01 requires 3 components
  "12": {"46": 1, "47": 1, "48": 1},  // FG02 requires 3 components
  "13": {"49": 1, "50": 1, "51": 1},  // FG03 requires 3 components
  "14": {"52": 1, "53": 1, "54": 1},  // FG04 requires 3 components
  "15": {"55": 1, "56": 1, "57": 1}   // FG05 requires 3 components
}
```

**Plant B2 (Node ID: 42)**:
```json
{
  "16": {"58": 1, "59": 1, "60": 1},  // FG06 requires 3 components
  "17": {"61": 1, "62": 1, "63": 1},  // FG07 requires 3 components
  "18": {"64": 1, "65": 1, "66": 1},  // FG08 requires 3 components
  "19": {"67": 1, "68": 1, "69": 1},  // FG09 requires 3 components
  "20": {"70": 1, "71": 1, "72": 1}   // FG10 requires 3 components
}
```

### Item-to-Product Mapping Status

| Item ID Range | Product ID | Migration Status |
|---------------|------------|------------------|
| 11-20 (FGs) | FG01-FG10 | ✅ Mapped |
| 43-72 (Components) | ❌ None | ❌ **NOT MAPPED** |

### Missing Components

**30 component items referenced but not created**:
```
Items 43-72: [43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72]
```

These items:
- ❌ Do not exist in the old `items` table
- ❌ Were never migrated to `product` table
- ❌ Have no ProductBom entries
- ❌ Cannot be traversed in supply planning

---

## Root Cause

The Complex SC configuration was created with **BOM references to items that were never actually created**. This appears to be a data setup issue where:

1. The seed script or UI created Nodes with BOM attributes
2. The BOM attributes reference Item IDs 43-72
3. But these Item records were **never inserted** into the `items` table
4. The Item → Product migration script only migrated **existing items** (IDs 1-20)
5. Result: Broken foreign key references in BOM data

---

## ProductBom Table Status

**Query Result**:
```sql
SELECT COUNT(*) FROM product_bom WHERE product_id IN ('FG01', 'FG02', ..., 'FG10');
-- Result: 0
```

**Expected ProductBom entries**: 30 (10 FGs × 3 components each)
**Actual ProductBom entries**: 0
**Difference**: -30 ❌

---

## Impact on Supply Planning

### What Works ✅
- Products exist and can be queried
- Finished goods have valid Product records
- Single-level planning (no BOM explosion)

### What's Broken ❌
- **BOM Explosion**: Cannot explode FG01-FG10 to component requirements
- **MPS Key Material Planning**: Cannot identify key materials (no components exist)
- **DAG Traversal**: Cannot traverse from FG → Components → Raw Materials
- **Net Requirements Calculation**: Cannot calculate component needs from FG demand
- **Multi-level Planning**: Stuck at finished goods level

### Example Failure Scenario

```python
# User tries to generate supply plan for FG01
supply_plan = generate_supply_plan(product_id="FG01", quantity=100)

# Planning flow:
1. ✅ Aggregate demand for FG01: 100 units
2. ✅ Calculate safety stock for FG01
3. ❌ FAILS: Explode BOM for FG01
   - Query ProductBom for FG01: Returns 0 rows
   - Cannot determine component requirements
   - Planning stops here

# Expected behavior:
1. Explode FG01 → Components 43, 44, 45 (1 each)
2. Calculate net requirements: 100 units FG01 = 100 of each component
3. Continue recursion for component BOMs (if multi-level)
4. Generate PO/TO/MO requests for all levels
```

---

## Resolution Options

### Option 1: Create Component Products (Recommended)

**Approach**: Retroactively create the 30 missing component Products and ProductBom entries.

**Steps**:
1. Create Products for Items 43-72 with synthetic data:
   ```python
   for item_id in range(43, 73):
       product = Product(
           id=f"COMP{item_id}",  # e.g., COMP43, COMP44, ...
           description=f"Component {item_id} for Complex SC",
           company_id="DEFAULT",
           config_id=5,  # Complex SC
           product_type="component",  # Or "raw_material"
           base_uom="EA",
           unit_cost=5.0,
           unit_price=7.0,
           is_active="true"
       )
   ```

2. Create item_product_mapping entries:
   ```python
   for item_id in range(43, 73):
       mapping = ItemProductMapping(
           item_id=item_id,
           product_id=f"COMP{item_id}"
       )
   ```

3. Extract BOMs from Node.attributes → ProductBom:
   ```python
   # For Plant B1:
   ProductBom(product_id="FG01", component_product_id="COMP43", component_quantity=1, is_key_material='true')
   ProductBom(product_id="FG01", component_product_id="COMP44", component_quantity=1, is_key_material='true')
   ProductBom(product_id="FG01", component_product_id="COMP45", component_quantity=1, is_key_material='true')
   # ... repeat for all 30 BOM relationships
   ```

4. Mark components as key materials:
   ```python
   # Assuming all leaf components are key materials (no further BOM)
   is_key_material = 'true'
   ```

**Pros**:
- ✅ Fixes BOM completeness
- ✅ Enables DAG traversal
- ✅ Preserves existing data
- ✅ Minimal disruption

**Cons**:
- ⚠️ Synthetic component names (COMP43, COMP44, etc.)
- ⚠️ Assumes all components are purchased (not manufactured)

### Option 2: Delete Complex SC Configuration

**Approach**: Remove the broken configuration entirely.

**Pros**:
- ✅ Clean slate
- ✅ No broken references

**Cons**:
- ❌ Loses all Complex SC work
- ❌ Loses node/lane topology
- ❌ Loses market demand data

### Option 3: Rebuild Complex SC from Scratch

**Approach**: Delete and recreate with proper data setup.

**Steps**:
1. Delete config ID 5 and all related data
2. Create new Complex SC config with proper seed script
3. Ensure all Items created before BOM references
4. Run migration to populate Products and ProductBom

**Pros**:
- ✅ Clean, correct data model
- ✅ Proper naming conventions
- ✅ Full testing from scratch

**Cons**:
- ❌ Most time-consuming
- ❌ Loses any custom configuration

---

## Recommended Action Plan

### Immediate Steps (Option 1)

1. **Create migration script** for Complex SC component products:
   - File: `backend/scripts/fix_complex_sc_bom.py`
   - Create 30 component Products (COMP43-COMP72)
   - Create 30 ProductBom entries
   - Mark all as key materials

2. **Run migration**:
   ```bash
   docker compose exec backend python scripts/fix_complex_sc_bom.py
   ```

3. **Verify**:
   ```bash
   # Check products created
   SELECT COUNT(*) FROM product WHERE config_id = 5;
   # Expected: 40 (10 FGs + 30 components)

   # Check BOMs created
   SELECT COUNT(*) FROM product_bom WHERE product_id IN ('FG01', ..., 'FG10');
   # Expected: 30 (10 FGs × 3 components each)
   ```

4. **Test DAG traversal**:
   ```python
   # Test BOM explosion for FG01
   bom = db.query(ProductBom).filter(ProductBom.product_id == "FG01").all()
   assert len(bom) == 3  # Should have 3 components
   ```

### Long-term Fix

- **Update seed scripts** to ensure Items created before BOM references
- **Add validation** to prevent orphaned BOM references
- **Document** proper Complex SC setup procedure

---

## Appendix: SQL Queries for Verification

### Check Product Count
```sql
SELECT config_id, COUNT(*) as product_count
FROM product
GROUP BY config_id;
-- Complex SC (ID 5) should have 40 products
```

### Check BOM Count
```sql
SELECT pb.product_id, p.description, COUNT(*) as component_count
FROM product_bom pb
JOIN product p ON pb.product_id = p.id
WHERE p.config_id = 5
GROUP BY pb.product_id, p.description;
-- Each FG should have 3 components
```

### Check Key Materials
```sql
SELECT pb.product_id, pb.component_product_id, pb.is_key_material
FROM product_bom pb
WHERE pb.is_key_material = 'true' AND pb.product_id IN ('FG01', 'FG02', ..., 'FG10');
-- Should return 30 rows (all components marked as key)
```

---

**Status**: ❌ **BOM INCOMPLETE - AWAITING FIX**
**Next Action**: Create and run `fix_complex_sc_bom.py` migration script
**Owner**: Development Team
**Priority**: HIGH (blocks supply planning for Complex SC)
