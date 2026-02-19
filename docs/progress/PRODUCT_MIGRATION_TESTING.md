# Product Migration: Testing & Validation Checklist

**Migration Status**: Backend Complete (Phases 1-8) ✅
**Created**: January 22, 2026
**Purpose**: Comprehensive testing checklist for Item → Product migration validation

---

## 🎯 Testing Objectives

1. Verify all Product CRUD operations work with String IDs
2. Ensure BOM explosion uses ProductBom table correctly
3. Validate MPS key material planning functionality
4. Confirm Beer Game playability with Product model
5. Test backwards compatibility layer
6. Verify no data loss or corruption

---

## ✅ Phase 1: Backend API Testing

### Product CRUD Operations

**Endpoint**: `GET /api/v1/supply-chain-configs/{config_id}/products`

```bash
# Test: List all products
curl -X GET http://localhost:8088/api/v1/supply-chain-configs/1/products \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"

# Expected: Array of products with String IDs (CASE, SIXPACK, BOTTLE, etc.)
```

**Endpoint**: `POST /api/v1/supply-chain-configs/{config_id}/products`

```bash
# Test: Create new product with String ID
curl -X POST http://localhost:8088/api/v1/supply-chain-configs/1/products \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "TESTPROD",
    "description": "Test Product",
    "company_id": "DEFAULT",
    "product_type": "finished_good",
    "base_uom": "EA",
    "unit_cost": 10.0,
    "unit_price": 12.0
  }'

# Expected: 201 Created with product object
```

**Endpoint**: `GET /api/v1/supply-chain-configs/{config_id}/products/{product_id}`

```bash
# Test: Get product by String ID
curl -X GET http://localhost:8088/api/v1/supply-chain-configs/1/products/CASE \
  -H "Authorization: Bearer $TOKEN"

# Expected: Product object with id="CASE"
```

**Endpoint**: `PUT /api/v1/supply-chain-configs/{config_id}/products/{product_id}`

```bash
# Test: Update product
curl -X PUT http://localhost:8088/api/v1/supply-chain-configs/1/products/TESTPROD \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Updated Test Product",
    "unit_cost": 15.0
  }'

# Expected: 200 OK with updated product
```

**Endpoint**: `DELETE /api/v1/supply-chain-configs/{config_id}/products/{product_id}`

```bash
# Test: Delete product
curl -X DELETE http://localhost:8088/api/v1/supply-chain-configs/1/products/TESTPROD \
  -H "Authorization: Bearer $TOKEN"

# Expected: 204 No Content
```

### Validation Checks

- [ ] String IDs accepted (e.g., "CASE", "SIXPACK", "BOTTLE")
- [ ] Integer IDs rejected with 400 error
- [ ] Duplicate ID detection works
- [ ] Special characters in IDs handled correctly
- [ ] Long IDs (>100 chars) rejected
- [ ] Empty ID rejected
- [ ] Case sensitivity preserved (CASE != case)

---

## ✅ Phase 2: Database Integrity Testing

### Product Table Verification

```sql
-- Test: Verify Product table has String primary keys
SELECT id, description, product_type, company_id
FROM product
LIMIT 10;

-- Expected: id column shows strings like "CASE", "SIXPACK"
-- NOT integers like 1, 2, 3

-- Test: Verify ProductBom relationships
SELECT
    pb.product_id,
    pb.component_product_id,
    pb.component_quantity,
    pb.is_key_material,
    p1.description as parent_desc,
    p2.description as component_desc
FROM product_bom pb
JOIN product p1 ON pb.product_id = p1.id
JOIN product p2 ON pb.component_product_id = p2.id
LIMIT 10;

-- Expected: Valid product_id and component_product_id as strings
-- is_key_material shows 'true' for raw materials, 'false' for intermediates

-- Test: Count products by type
SELECT product_type, COUNT(*)
FROM product
GROUP BY product_type;

-- Expected: Distribution of finished_good, component, raw_material
```

### Foreign Key Integrity

```sql
-- Test: All foreign keys reference valid products
SELECT COUNT(*) as orphaned_market_demands
FROM market_demands md
LEFT JOIN product p ON md.product_id = p.id
WHERE p.id IS NULL;

-- Expected: 0 (no orphans)

SELECT COUNT(*) as orphaned_vendor_products
FROM vendor_products vp
LEFT JOIN product p ON vp.product_id = p.id
WHERE p.id IS NULL;

-- Expected: 0 (no orphans)

-- Test: All ProductBom references valid products
SELECT COUNT(*) as invalid_boms
FROM product_bom pb
LEFT JOIN product p1 ON pb.product_id = p1.id
LEFT JOIN product p2 ON pb.component_product_id = p2.id
WHERE p1.id IS NULL OR p2.id IS NULL;

-- Expected: 0 (all valid)
```

### Migration Completeness

```sql
-- Test: Verify old items table doesn't exist or is empty
SHOW TABLES LIKE 'items';
-- Expected: Empty result or error (table doesn't exist)

-- Test: Count products matches expected
SELECT COUNT(*) as total_products FROM product;
-- Expected: 26 (from migration)

-- Test: Key materials flagged correctly
SELECT COUNT(*) as key_materials
FROM product_bom
WHERE is_key_material = 'true';
-- Expected: 5+ key materials
```

---

## ✅ Phase 3: Service Layer Testing

### Mixed Game Service

**Test**: Create Beer Game with Product model

```python
# backend/scripts/test_beer_game_with_products.py
from app.db.base_class import SessionLocal
from app.services.mixed_game_service import MixedGameService
from app.models import Game, Player, User

db = SessionLocal()

# Test: Create game
game = MixedGameService.create_game(
    db=db,
    config_id=1,  # Default TBG config
    name="Product Migration Test Game",
    max_rounds=10
)

print(f"✅ Game created: ID={game.id}")

# Test: Verify products loaded
config = db.query(SupplyChainConfig).get(1)
products = db.query(Product).filter(Product.config_id == config.id).all()
print(f"✅ Products loaded: {len(products)} products")
for product in products[:5]:
    print(f"   - {product.id}: {product.description}")

# Test: Start game round
MixedGameService.play_round(db=db, game_id=game.id)
print(f"✅ Round 1 completed")

db.close()
```

**Expected Output**:
```
✅ Game created: ID=123
✅ Products loaded: 26 products
   - CASE: Case of beer
   - SIXPACK: Six-pack
   - BOTTLE: Bottle
   - INGREDIENTS: Beer ingredients
   - CAN: Aluminum can
✅ Round 1 completed
```

### BOM Explosion Testing

**Test**: ProductBom explosion for MPS key materials

```python
# Test BOM explosion
from app.services.sc_planning.net_requirements_calculator import NetRequirementsCalculator

calculator = NetRequirementsCalculator(db, config_id=1)

# Test: Explode CASE product
bom_entries = db.query(ProductBom).filter(
    ProductBom.product_id == "CASE"
).all()

print(f"✅ BOM for CASE:")
for entry in bom_entries:
    print(f"   - {entry.component_quantity}x {entry.component_product_id}")
    print(f"     Key Material: {entry.is_key_material}")

# Expected:
# ✅ BOM for CASE:
#    - 4.0x SIXPACK
#      Key Material: false
```

### Supplier/Vendor Testing

**Test**: VendorProduct with String product IDs

```sql
-- Test: Vendor products reference valid products
SELECT
    vp.id,
    vp.tpartner_id,
    vp.product_id,
    p.description,
    vp.vendor_unit_cost
FROM vendor_products vp
JOIN product p ON vp.product_id = p.id
LIMIT 10;

-- Expected: Valid product_id strings in results
```

---

## ✅ Phase 4: Frontend Integration Testing

### API Client Tests (JavaScript)

```javascript
// frontend/src/services/__tests__/supplyChainConfigService.test.js
import { getProducts, createProduct, updateProduct, deleteProduct } from '../supplyChainConfigService';

describe('Product API Client', () => {
  test('getProducts returns array of products', async () => {
    const products = await getProducts(1);
    expect(Array.isArray(products)).toBe(true);
    expect(products[0]).toHaveProperty('id');
    expect(typeof products[0].id).toBe('string'); // String ID!
  });

  test('createProduct accepts String ID', async () => {
    const newProduct = {
      id: 'TESTPROD',
      description: 'Test Product',
      company_id: 'DEFAULT',
      product_type: 'finished_good',
      base_uom: 'EA'
    };
    const created = await createProduct(1, newProduct);
    expect(created.id).toBe('TESTPROD');
  });

  test('backwards compatibility aliases work', async () => {
    const { getItems } = require('../supplyChainConfigService');
    const products = await getItems(1); // Old name
    expect(Array.isArray(products)).toBe(true); // Still works
  });
});
```

### Manual UI Testing Checklist

- [ ] Supply Chain Config page loads without errors
- [ ] "Products" tab displays (not "Items")
- [ ] Product list shows String IDs (CASE, SIXPACK, etc.)
- [ ] Can click "Add Product" button
- [ ] Form validation works
- [ ] Can save product (even with old schema temporarily)
- [ ] Can edit existing product
- [ ] Can delete product
- [ ] No console errors related to products
- [ ] Sankey diagram displays products correctly

---

## ✅ Phase 5: Beer Game End-to-End Testing

### Game Creation & Playability

**Test Script**: Play full Beer Game with Product model

```bash
# 1. Create game via API
curl -X POST http://localhost:8088/api/v1/mixed-games \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": 1,
    "name": "Product Migration E2E Test",
    "max_rounds": 10,
    "players": [
      {"role": "retailer", "type": "human"},
      {"role": "wholesaler", "type": "ai", "strategy": "naive"},
      {"role": "distributor", "type": "ai", "strategy": "naive"},
      {"role": "factory", "type": "ai", "strategy": "naive"}
    ]
  }'

# 2. Start game
curl -X POST http://localhost:8088/api/v1/mixed-games/{game_id}/start \
  -H "Authorization: Bearer $TOKEN"

# 3. Play rounds
for i in {1..10}; do
  echo "Playing round $i..."
  curl -X POST http://localhost:8088/api/v1/mixed-games/{game_id}/play-round \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"orders": {"retailer": 10}}'
  sleep 1
done

# 4. Get final state
curl -X GET http://localhost:8088/api/v1/mixed-games/{game_id}/state \
  -H "Authorization: Bearer $TOKEN"
```

**Expected**:
- ✅ Game creates successfully
- ✅ All rounds complete without errors
- ✅ Inventory tracking works
- ✅ Orders flow through supply chain
- ✅ Costs calculated correctly
- ✅ Scoring displays properly

### Validation Checks

- [ ] Game creates with default TBG config
- [ ] Products loaded for all nodes
- [ ] Inventory by product tracked correctly
- [ ] Orders reference product IDs (strings)
- [ ] Shipments contain product IDs (strings)
- [ ] Backlog tracked by product
- [ ] Costs attributed to products
- [ ] Game completes all rounds
- [ ] Final scoring works
- [ ] No errors in backend logs

---

## ✅ Phase 6: Performance Testing

### Query Performance with String PKs

```sql
-- Test: Product lookup by String ID (should be fast)
EXPLAIN SELECT * FROM product WHERE id = 'CASE';
-- Expected: Uses PRIMARY KEY, type=const, rows=1

-- Test: ProductBom joins
EXPLAIN SELECT *
FROM product_bom pb
JOIN product p1 ON pb.product_id = p1.id
JOIN product p2 ON pb.component_product_id = p2.id
LIMIT 100;
-- Expected: Uses indexes, type=ref or eq_ref

-- Test: Complex query performance
SELECT
    p.id,
    p.description,
    COUNT(pb.component_product_id) as num_components,
    SUM(CASE WHEN pb.is_key_material = 'true' THEN 1 ELSE 0 END) as key_materials
FROM product p
LEFT JOIN product_bom pb ON p.id = pb.product_id
GROUP BY p.id, p.description;
-- Expected: Completes in <100ms for 26 products
```

### Load Testing

```bash
# Test: Concurrent product creation
for i in {1..10}; do
  curl -X POST http://localhost:8088/api/v1/supply-chain-configs/1/products \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"id\": \"LOAD_TEST_$i\", \"description\": \"Load test product $i\", \"company_id\": \"DEFAULT\"}" &
done
wait

# Expected: All 10 products created successfully
```

---

## ✅ Phase 7: Regression Testing

### Backwards Compatibility

- [ ] Old code using Item compatibility layer still works
- [ ] Mixed codebase (Product + Item references) operates correctly
- [ ] No breaking changes to existing games
- [ ] Historical game data still accessible
- [ ] Reports and analytics work with both old and new data

### Data Integrity

- [ ] All 26 products present in database
- [ ] No duplicate product IDs
- [ ] All products have valid company_id
- [ ] All BOMs reference valid products
- [ ] No orphaned foreign keys
- [ ] Referential integrity maintained

---

## ✅ Phase 8: Documentation Validation

### Code Documentation

- [ ] MIGRATION_STATUS.md accurate and up-to-date
- [ ] PRODUCT_MIGRATION_GUIDE.md has correct examples
- [ ] MIGRATION_SUMMARY.md reflects final state
- [ ] TODO.md shows all phases complete
- [ ] Inline code comments updated
- [ ] API documentation (Swagger) reflects Product endpoints

### Developer Onboarding

- [ ] New developer can understand migration from docs
- [ ] Quick reference guide is actually quick
- [ ] Examples work when copy-pasted
- [ ] Migration rationale clearly explained

---

## 🚨 Failure Scenarios & Rollback

### If Critical Issues Found

**Rollback Plan**:
```bash
# 1. Stop backend
docker compose stop backend

# 2. Restore database backup (if available)
pg_restore backup_pre_migration.sql

# 3. Revert code changes
git revert <migration-commit-range>

# 4. Restart backend
docker compose up -d backend

# 5. Verify rollback successful
curl http://localhost:8088/api/health
```

### Common Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| 400 errors on product creation | Integer ID sent instead of String | Update client to send String IDs |
| FK constraint violations | Product not found | Verify product exists before creating relationships |
| SQLAlchemy relationship errors | Mismatched FK types | Ensure all FKs are String(100) |
| Performance degradation | Missing indexes | Add indexes on product_id columns |
| Compatibility layer errors | Incorrect usage | Use Product directly instead |

---

## ✅ Final Sign-Off Checklist

### Before Marking Migration Complete

- [ ] All 8 phases documented as complete
- [ ] Backend health check passes
- [ ] All Product CRUD operations work
- [ ] ProductBom table populated correctly
- [ ] Key materials flagged appropriately
- [ ] MPS key material explosion tested
- [ ] Beer Game playable end-to-end
- [ ] No critical errors in logs (last 24 hours)
- [ ] Database backup created
- [ ] Documentation complete and accurate
- [ ] Team briefed on changes
- [ ] Monitoring alerts configured

### Production Deployment Checklist

- [ ] Staging environment tested successfully
- [ ] Migration script tested on staging data
- [ ] Rollback procedure documented and tested
- [ ] Database backup created
- [ ] Maintenance window scheduled
- [ ] Stakeholders notified
- [ ] Monitoring enabled
- [ ] On-call engineer assigned
- [ ] Migration executed
- [ ] Smoke tests passed
- [ ] Performance metrics normal
- [ ] No critical errors
- [ ] Documentation updated
- [ ] Team notified of completion

---

## 📊 Testing Status

**Last Updated**: January 22, 2026
**Migration Phase**: All 8 Phases Complete ✅
**Backend Status**: Healthy and Operational ✅
**Testing Status**: Comprehensive checklist provided ⏳

**Next Action**: Execute testing checklist systematically

---

*For questions or issues during testing, refer to [PRODUCT_MIGRATION_GUIDE.md](PRODUCT_MIGRATION_GUIDE.md) and [MIGRATION_STATUS.md](MIGRATION_STATUS.md).*
