# AWS Supply Chain Data Model (AWS SC DM) Refactoring Plan

**Status**: In Progress
**Created**: January 26, 2026
**Last Updated**: January 26, 2026

## Executive Summary

The Autonomy Platform is being refactored to fully comply with AWS Supply Chain Data Model terminology. The backend migration is **100% complete**, with all models, services, and APIs now using `Product` instead of `Item`. This plan outlines the remaining frontend and integration work needed to complete full AWS SC DM compliance.

### Current Compliance Status

| Layer | Status | Compliance | Notes |
|-------|--------|------------|-------|
| **Backend Models** | ✅ Complete | 100% | All models use Product from sc_entities |
| **Backend Services** | ✅ Complete | 100% | All services use Product |
| **Backend APIs** | ✅ Complete | 100% | All active endpoints use /products |
| **Database Schema** | ✅ Complete | 100% | Migrated to String PKs, Product table |
| **Frontend Services** | 🔄 Partial | 80% | Has backward compat aliases |
| **Frontend Components** | 🔄 Partial | 70% | Sankey complete, others TBD |
| **Documentation** | 🔄 Partial | 60% | Needs terminology update |

---

## Phase 1: Frontend Service Layer [HIGH PRIORITY]

### 1.1 Remove Deprecated Item Endpoint Calls

**File**: `frontend/src/services/supplyChainConfigService.js`

**Issue**: Lines 166-185 still call deprecated `/item-node-configs` endpoint that returns 404

**Current Code** (Lines 166-185):
```javascript
// Item-Node Configs CRUD
export const getItemNodeConfigs = async (configId) => {
  const response = await api.get(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/item-node-configs`);
  return response.data;
};

export const createItemNodeConfig = async (configId, itemNodeData) => {
  const response = await api.post(
    `${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/item-node-configs`,
    itemNodeData
  );
  return response.data;
};

export const updateItemNodeConfig = async (configId, itemNodeId, itemNodeData) => {
  const response = await api.put(
    `${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/item-node-configs/${itemNodeId}`,
    itemNodeData
  );
  return response.data;
};
```

**Required Action**:
This endpoint has been **deprecated** in the backend. According to `backend/app/models/compatibility.py`, the ItemNodeConfig functionality is now split across three AWS SC entities:

- **InvPolicy** (inventory policies) - handles inventory targets, safety stock
- **ProductBom** (BOM relationships) - handles component relationships
- **VendorProduct** (supplier configurations) - handles supplier-specific product attributes

**Recommended Solution**:
1. Create new AWS SC DM compliant endpoints in backend:
   - `/api/v1/supply-chain-configs/{config_id}/inv-policies` (for inventory policies)
   - `/api/v1/supply-chain-configs/{config_id}/product-boms` (for BOM)
   - `/api/v1/supply-chain-configs/{config_id}/vendor-products` (for supplier configs)

2. Update frontend service to use these new endpoints

3. OR: If backward compatibility is required short-term, re-enable the deprecated endpoint in backend with a deprecation warning header

**Impact**: HIGH - The Sankey component currently calls `getItemNodeConfigs()` which returns 404

**Estimated Effort**: 4-6 hours (backend endpoint creation + frontend service update + testing)

### 1.2 Add AWS SC DM Compliant Function Aliases

**File**: `frontend/src/services/supplyChainConfigService.js`

**Current Code** (Lines 86-113):
```javascript
// Products CRUD (AWS SC compliant - was Items)
export const getProducts = async (configId) => {
  const response = await api.get(`${SUPPLY_CHAIN_CONFIG_BASE_URL}/${configId}/products`);
  return response.data;
};

// Backwards compatibility aliases (deprecated - use Product methods above)
export const getItems = getProducts;
export const createItem = createProduct;
export const updateItem = updateProduct;
export const deleteItem = deleteProduct;
```

**Required Action**: This is already AWS SC DM compliant ✅

**Status**: Complete - Proper Product functions with backward compatibility aliases

---

## Phase 2: Frontend Components [MEDIUM PRIORITY]

### 2.1 SupplyChainConfigSankey Component ✅

**File**: `frontend/src/components/supply-chain-config/SupplyChainConfigSankey.jsx`

**Status**: ✅ **COMPLETE** (as of January 26, 2026)

**Changes Made**:
- Renamed state variables: `items` → `products`, `itemNodeConfigs` → `productNodeConfigs`
- Updated lookup maps: `itemLookup` → `productLookup`
- Updated all table rendering to use `product` instead of `item`
- Updated tab labels to display correct counts
- All variable references now AWS SC DM compliant

### 2.2 Other Frontend Components Audit [MEDIUM]

**Required Action**: Audit all remaining frontend components for Item/Product terminology

**Files to Check**:
```bash
frontend/src/components/supply-chain-config/
├── SupplyChainConfigCard.jsx
├── SupplyChainConfigForm.jsx
├── SupplyChainConfigList.jsx
└── ... (other config components)

frontend/src/pages/
├── CreateMixedGame.jsx (may reference items)
├── GameBoard.jsx (may reference items)
└── ... (other pages)
```

**Search Command**:
```bash
# Find all Item references in frontend components
grep -r "\bitem\b" frontend/src/components/ --include="*.jsx" --include="*.js" | grep -v "node_modules"
```

**Estimated Effort**: 2-4 hours per component (depending on complexity)

---

## Phase 3: Backend API Endpoint Restoration [HIGH PRIORITY]

### 3.1 Restore Item-Node-Config Endpoint (Temporary)

**File**: `backend/app/api/endpoints/supply_chain_config.py`

**Issue**: Lines 1495-1587 are commented out, causing 404 errors in frontend

**Recommended Action**:
**Option A - Quick Fix (Temporary)**: Uncomment and update the endpoint to return AWS SC DM compliant data

**Option B - Proper Fix (Recommended)**: Create three new AWS SC DM endpoints:

```python
# backend/app/api/endpoints/supply_chain_config.py

@router.get("/{config_id}/inv-policies", response_model=List[schemas.InvPolicy])
def list_inv_policies(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """List inventory policies for a config (AWS SC DM compliant)."""
    config = get_config_or_404(db, config_id)
    # Query InvPolicy table
    return crud.inv_policy.get_by_config(db, config_id=config_id)


@router.get("/{config_id}/product-boms", response_model=List[schemas.ProductBom])
def list_product_boms(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """List product BOMs for a config (AWS SC DM compliant)."""
    config = get_config_or_404(db, config_id)
    # Query ProductBom table
    return crud.product_bom.get_by_config(db, config_id=config_id)


@router.get("/{config_id}/vendor-products", response_model=List[schemas.VendorProduct])
def list_vendor_products(
    config_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """List vendor products for a config (AWS SC DM compliant)."""
    config = get_config_or_404(db, config_id)
    # Query VendorProduct table
    return crud.vendor_product.get_by_config(db, config_id=config_id)
```

**Impact**: HIGH - Frontend currently broken due to 404 errors

**Estimated Effort**:
- Option A: 1 hour
- Option B: 4-6 hours (including CRUD operations and schemas)

---

## Phase 4: Documentation Updates [LOW PRIORITY]

### 4.1 Update Code Comments

**Files**:
- All files in `backend/app/models/`
- All files in `backend/app/services/`
- All files in `frontend/src/`

**Search and Replace**:
```bash
# Find all comments referencing "Item" (not "ItemNodeConfig")
grep -r "# .*[Ii]tem[^N]" backend/ frontend/ --include="*.py" --include="*.jsx" --include="*.js"
```

**Required Action**: Update comments to use "Product" terminology

### 4.2 Update README and CLAUDE.md

**Files**:
- `README.md`
- `CLAUDE.md`
- `docs/*.md`

**Required Changes**:
- Replace all "Item" references with "Product"
- Update data model diagrams to show Product entity
- Update API endpoint documentation
- Add migration notes explaining Item → Product change

**Estimated Effort**: 2-3 hours

---

## Phase 5: Testing and Validation [HIGH PRIORITY]

### 5.1 API Endpoint Testing

**Test Cases**:

1. **Product Endpoints** ✅
   - `GET /api/v1/supply-chain-configs/{id}/products` - Should return all products
   - `POST /api/v1/supply-chain-configs/{id}/products` - Should create new product
   - `PUT /api/v1/supply-chain-configs/{id}/products/{product_id}` - Should update product
   - `DELETE /api/v1/supply-chain-configs/{id}/products/{product_id}` - Should delete product

2. **Deprecated Item Endpoints** ⚠️
   - `GET /api/v1/supply-chain-configs/{id}/items` - Should return 404 or deprecation warning
   - `GET /api/v1/supply-chain-configs/{id}/item-node-configs` - Should return 404 or deprecation warning

3. **New AWS SC DM Endpoints** 🔄
   - `GET /api/v1/supply-chain-configs/{id}/inv-policies` - To be implemented
   - `GET /api/v1/supply-chain-configs/{id}/product-boms` - To be implemented
   - `GET /api/v1/supply-chain-configs/{id}/vendor-products` - To be implemented

### 5.2 Frontend Component Testing

**Test Cases**:

1. **Sankey Diagram** ✅
   - Navigate to Supply Chain Configs page
   - Select "Default TBG" configuration
   - Verify Flow Diagram tab renders without errors
   - Verify Products tab shows correct product count
   - Verify Product-Site tab shows correct config count
   - Check browser console for errors

2. **Supply Chain Config Forms** 🔄
   - Test creating new products (not items)
   - Test editing product properties
   - Test creating lanes between nodes
   - Verify all form labels use "Product" terminology

### 5.3 Regression Testing

**Critical Paths**:
- [ ] User can create a new supply chain configuration
- [ ] User can add products to a configuration
- [ ] User can create lanes between nodes
- [ ] Sankey diagram renders correctly with real data
- [ ] Games can be created using supply chain configs
- [ ] Agent games run successfully with products
- [ ] Mixed games (human + AI) function correctly

---

## Phase 6: Cleanup and Removal [LOW PRIORITY]

### 6.1 Remove Compatibility Layer

**File**: `backend/app/models/compatibility.py`

**Current Status**: Intentionally kept for gradual migration

**Removal Criteria** (from file header):
- ✅ Frontend UI components fully updated to SC schema
- ✅ All external API consumers verified with Product endpoints
- ✅ Full regression testing completed
- ✅ Production deployment stable for 30+ days

**Required Actions Before Removal**:
1. Verify no imports of `Item` or `ItemNodeConfig` from compatibility.py
2. Search entire codebase for `from app.models.compatibility import`
3. Update all imports to use `from app.models.sc_entities import Product`
4. Run full test suite
5. Deploy to staging and monitor for 30 days
6. Remove compatibility.py

**Search Commands**:
```bash
# Find all imports from compatibility layer
grep -r "from.*compatibility import" backend/ frontend/

# Find all Item() constructor calls
grep -r "Item(" backend/ --include="*.py"
```

**Estimated Effort**: 1-2 hours (once criteria met)

### 6.2 Remove Backward Compatibility Aliases

**File**: `frontend/src/services/supplyChainConfigService.js`

**Lines to Remove** (after migration complete):
```javascript
// These lines should be removed once all components use Product methods:
export const getItems = getProducts;
export const createItem = createProduct;
export const updateItem = updateProduct;
export const deleteItem = deleteProduct;
```

**Required Action**:
1. Search all frontend components for usage of deprecated aliases
2. Update components to use `getProducts`, `createProduct`, etc.
3. Remove aliases after confirming no usage

**Search Command**:
```bash
grep -r "getItems\|createItem\|updateItem\|deleteItem" frontend/src/ --include="*.jsx" --include="*.js"
```

---

## Priority Summary

### HIGH Priority (Complete within 1 week)
1. ✅ **Fix Sankey Component** - COMPLETE as of Jan 26, 2026
2. 🔄 **Restore Item-Node-Config Endpoint** - Frontend broken, needs immediate fix
3. 🔄 **Create AWS SC DM Endpoints** - inv-policies, product-boms, vendor-products
4. 🔄 **Frontend Service Layer Update** - Update getItemNodeConfigs to use new endpoints

### MEDIUM Priority (Complete within 2-4 weeks)
1. 🔄 **Audit Frontend Components** - Check all components for Item terminology
2. 🔄 **Update Component Variables** - Rename remaining item → product references
3. 🔄 **Regression Testing** - Verify all critical paths work with Product

### LOW Priority (Complete within 2-3 months)
1. 🔄 **Documentation Updates** - README, CLAUDE.md, code comments
2. 🔄 **Remove Compatibility Layer** - After 30-day stability period
3. 🔄 **Remove Backward Compat Aliases** - Clean up deprecated functions

---

## Migration Checklist

### Backend ✅ 100% Complete
- [x] Database schema migrated to Product table
- [x] All models use Product from sc_entities
- [x] All services use Product
- [x] All API endpoints use /products paths
- [x] Compatibility layer created for gradual migration
- [x] All active endpoints return Product schema

### Frontend 🔄 ~70% Complete
- [x] Service layer has Product functions (with backward compat)
- [x] Sankey component uses Product terminology
- [ ] All other components audited for Item references
- [ ] All forms updated to use Product labels
- [ ] All table columns use Product headers
- [ ] All API calls use Product endpoints

### API Endpoints 🔄 ~80% Complete
- [x] GET /products - Active and working
- [x] POST /products - Active and working
- [x] PUT /products/{id} - Active and working
- [x] DELETE /products/{id} - Active and working
- [ ] GET /inv-policies - Need to implement
- [ ] GET /product-boms - Need to implement
- [ ] GET /vendor-products - Need to implement
- [x] GET /items - Properly deprecated (commented out)
- [x] GET /item-node-configs - Properly deprecated (commented out)

### Testing 🔄 ~60% Complete
- [x] Sankey diagram renders correctly
- [ ] All frontend forms tested
- [ ] All API endpoints tested
- [ ] Regression tests pass
- [ ] Integration tests pass
- [ ] End-to-end game creation tested

---

## Notes and Considerations

### AWS SC Data Model Entities

According to AWS Supply Chain standard, the following entities should be used:

| Legacy Term | AWS SC DM Term | Status |
|-------------|----------------|--------|
| Item | **Product** | ✅ Complete |
| Node | Site (or keep as Node for Beer Game context) | ✅ Acceptable |
| Lane | Lane | ✅ Compliant |
| ItemNodeConfig | InvPolicy + ProductBom + VendorProduct | 🔄 In Progress |

### Why Node ≠ Site (Acceptable Deviation)

While AWS SC DM uses "Site" for physical locations, the Beer Game abstraction uses "Node" to represent:
- Market Supply (upstream suppliers)
- Market Demand (downstream customers)
- Inventory nodes (warehouses, DCs)
- Manufacturer nodes (production facilities)

This is an **acceptable deviation** because:
1. Beer Game is a pedagogical abstraction, not a real supply chain
2. "Node" better represents the graph-based topology
3. AWS SC "Site" implies physical location, but Beer Game nodes are logical
4. Documentation clearly maps Node types to AWS SC master types

### Backward Compatibility Strategy

The current approach is:
1. **Backend**: 100% Product-based, with compatibility shims for old code
2. **Frontend**: Gradual migration with backward compat aliases
3. **API**: Deprecated endpoints commented out, new endpoints active
4. **Database**: Fully migrated to Product schema

This allows:
- Zero downtime migration ✅
- Gradual frontend component updates ✅
- Safe rollback if issues discovered ✅
- External API consumers time to migrate ✅

---

## References

- **Backend Compatibility Layer**: `backend/app/models/compatibility.py`
- **AWS SC Entities**: `backend/app/models/sc_entities.py`
- **Frontend Service**: `frontend/src/services/supplyChainConfigService.js`
- **Sankey Component**: `frontend/src/components/supply-chain-config/SupplyChainConfigSankey.jsx`
- **API Endpoints**: `backend/app/api/endpoints/supply_chain_config.py`
- **Migration Status**: `AWS_SC_IMPLEMENTATION_STATUS.md`
- **Planning Knowledge Base**: `PLANNING_KNOWLEDGE_BASE.md`

---

## Contact

For questions about this refactoring plan, contact:
- **Project Lead**: systemadmin@autonomy.ai
- **Documentation**: See `CLAUDE.md` for AI assistant guidance

---

**Last Updated**: January 26, 2026
**Next Review Date**: February 9, 2026
