# Product Migration Quick Reference Guide

**For Developers Working on The Beer Game**

---

## ⚠️ IMPORTANT: Item → Product Migration In Progress

The Beer Game is migrating from the custom `items` table to the AWS Supply Chain compliant `product` table with **String primary keys**.

**Status**: Phases 1-4 complete, service layer migration in progress

---

## Quick Reference

### ✅ Use This (New):
```python
from app.models.sc_entities import Product
from app.schemas.supply_chain_config import Product, ProductCreate, ProductUpdate

# Get product by string ID
product = crud.product.get(db, id="CASE")

# Query products
products = db.query(Product).filter(Product.config_id == 1).all()

# Foreign key to product
product_id = Column(String(100), ForeignKey("product.id"))
```

### ❌ Don't Use This (Old):
```python
from app.models.supply_chain_config import Item  # DEPRECATED
from app.schemas import Item, ItemCreate, ItemUpdate  # REMOVED

# Old integer-based queries
item = crud.item.get(db, id=1)  # Integer IDs no longer used
```

---

## Product ID Format

### String Primary Keys (Not Integers!)

**Format**: Uppercase alphanumeric, no spaces or hyphens
**Examples**:
- ✅ `"CASE"` - Good
- ✅ `"SIXPACK"` - Good (hyphen removed from "Six-Pack")
- ✅ `"BOTTLE"` - Good
- ✅ `"INGREDIENTS"` - Good
- ❌ `1` - Wrong (Integer)
- ❌ `"six-pack"` - Wrong (lowercase, hyphen)
- ❌ `"Case 1"` - Wrong (space)

### ID Normalization Function:
```python
def normalize_product_id(name: str) -> str:
    """Convert product name to ID"""
    return name.upper().replace("-", "").replace(" ", "")

# Examples:
normalize_product_id("Case") → "CASE"
normalize_product_id("Six-Pack") → "SIXPACK"
normalize_product_id("Lager Case") → "LAGERCASE"
```

---

## Database Schema Changes

### Product Table

```sql
CREATE TABLE product (
    id VARCHAR(100) PRIMARY KEY,  -- String PK!
    description VARCHAR(500),
    company_id VARCHAR(100) REFERENCES company(id),
    config_id INTEGER REFERENCES supply_chain_configs(id),
    product_type VARCHAR(50),  -- finished_good, component, raw_material
    base_uom VARCHAR(10),      -- EA (each), default
    unit_cost DECIMAL(10,2),
    unit_price DECIMAL(10,2),
    is_active VARCHAR(10)       -- 'true' or 'false' as string
);
```

### Foreign Key Updates

**Before**:
```python
product_id = Column(Integer, ForeignKey("items.id"))
```

**After**:
```python
product_id = Column(String(100), ForeignKey("product.id"))
```

**All tables with product FKs**:
- market_demands
- mps_plan_items
- mps_key_material_requirements
- monte_carlo_time_series
- mrp_requirements (component_id, parent_id)
- purchase_order_line_items
- transfer_order_line_items
- production_orders
- production_order_components
- inv_projections (all projection tables)
- aggregated_orders
- vendor_products

---

## Model Layer Usage

### Importing Product Model

```python
# AWS SC Product model
from app.models.sc_entities import Product, ProductBom

# Compatibility shim (temporary - use sparingly)
from app.models.compatibility import Item, ItemNodeConfig
```

### Querying Products

```python
from app.models.sc_entities import Product

# Get by string ID
product = db.query(Product).filter(Product.id == "CASE").first()

# Get all products for config
products = db.query(Product).filter(Product.config_id == 1).all()

# Check if product exists
exists = db.query(Product).filter(Product.id == "NEWPRODUCT").first() is not None
```

### Creating Products

```python
from app.models.sc_entities import Product

product = Product(
    id="TESTPROD",
    description="Test Product",
    company_id="DEFAULT",
    config_id=1,
    product_type="finished_good",
    base_uom="EA",
    unit_cost=10.0,
    unit_price=12.0,
    is_active="true"
)
db.add(product)
db.commit()
```

---

## CRUD Operations

### Using Product CRUD

```python
from app import crud
from app.schemas.supply_chain_config import ProductCreate, ProductUpdate

# Get product
product = crud.product.get(db, id="CASE")

# Get products for config
products = crud.product.get_by_config(db, config_id=1)

# Create product
product_in = ProductCreate(
    id="NEWPROD",
    description="New Product",
    company_id="DEFAULT",
    config_id=1,
    product_type="finished_good"
)
product = crud.product.create(db, obj_in=product_in)

# Update product
product_in = ProductUpdate(description="Updated description")
product = crud.product.update(db, db_obj=product, obj_in=product_in)

# Delete product
crud.product.remove(db, id="OLDPROD")
```

---

## API Endpoints

### Product Endpoints (Use These)

```
GET    /api/v1/supply-chain-configs/{config_id}/products
POST   /api/v1/supply-chain-configs/{config_id}/products
GET    /api/v1/supply-chain-configs/{config_id}/products/{product_id}
PUT    /api/v1/supply-chain-configs/{config_id}/products/{product_id}
DELETE /api/v1/supply-chain-configs/{config_id}/products/{product_id}
```

**Note**: `product_id` in URL is a **String**, not an Integer!

### Legacy Item Endpoints (Deprecated)

```
❌ /api/v1/supply-chain-configs/{config_id}/items (COMMENTED OUT)
❌ /api/v1/supply-chain-configs/{config_id}/item-node-configs (COMMENTED OUT)
```

These endpoints are disabled. Use `/products` and `/inv-policies` instead.

---

## Pydantic Schemas

### Product Schemas

```python
from app.schemas.supply_chain_config import (
    Product,
    ProductCreate,
    ProductUpdate
)

# ProductBase
class ProductBase(BaseModel):
    id: str  # String PK
    description: Optional[str]
    product_type: Optional[str] = "finished_good"
    base_uom: str = "EA"
    unit_cost: Optional[float]
    unit_price: Optional[float]
    is_active: str = "true"

# ProductCreate
class ProductCreate(ProductBase):
    config_id: Optional[int]
    company_id: str = "DEFAULT"

# ProductUpdate (partial)
class ProductUpdate(BaseModel):
    description: Optional[str]
    unit_cost: Optional[float]
    unit_price: Optional[float]
    is_active: Optional[str]

# Product (full with ORM)
class Product(ProductBase):
    company_id: str
    config_id: Optional[int]
```

---

## Service Layer Patterns

### Pattern 1: Query Product by ID

```python
# ✅ Correct
from app.models.sc_entities import Product

product = db.query(Product).filter(Product.id == "CASE").first()
if not product:
    raise ValueError(f"Product CASE not found")

# ❌ Wrong (old Item model)
item = db.query(Item).filter(Item.id == 1).first()
```

### Pattern 2: Iterate Products

```python
# ✅ Correct
from app.models.sc_entities import Product

products = db.query(Product).filter(Product.config_id == config_id).all()
for product in products:
    print(f"Product: {product.id} - {product.description}")

# ❌ Wrong
items = db.query(Item).filter(Item.config_id == config_id).all()
```

### Pattern 3: FK Relationships

```python
# ✅ Correct (String FK)
class MPSPlanItem(Base):
    product_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("product.id"),
        nullable=False
    )
    product = relationship("Product")

# ❌ Wrong (Integer FK)
class MPSPlanItem(Base):
    item_id = Column(Integer, ForeignKey("items.id"))
    item = relationship("Item")
```

---

## Common Pitfalls

### 1. Using Integer IDs Instead of Strings

**Wrong**:
```python
product_id = 1  # Integer
product = db.query(Product).filter(Product.id == product_id).first()
```

**Right**:
```python
product_id = "CASE"  # String
product = db.query(Product).filter(Product.id == product_id).first()
```

### 2. Importing from Wrong Module

**Wrong**:
```python
from app.models.supply_chain_config import Item  # Old location, removed
```

**Right**:
```python
from app.models.sc_entities import Product  # AWS SC location
```

### 3. Using Old Schema Names

**Wrong**:
```python
from app.schemas import Item, ItemCreate
```

**Right**:
```python
from app.schemas import Product, ProductCreate
```

### 4. Hardcoding Integer IDs

**Wrong**:
```python
SELECT * FROM product WHERE id = 1;  -- Will fail, id is string
```

**Right**:
```python
SELECT * FROM product WHERE id = 'CASE';  -- Correct
```

---

## Compatibility Layer (Temporary)

During migration, a compatibility layer exists to ease transition:

```python
from app.models.compatibility import Item, ItemNodeConfig

# These are SHIMS that proxy to Product
# Use sparingly and only during migration
```

**Do NOT** rely on the compatibility layer for new code. It will be removed once migration is complete.

---

## Testing Your Changes

### 1. Verify String IDs Work

```python
def test_product_string_id():
    product = Product(
        id="TESTPROD",
        description="Test",
        company_id="DEFAULT",
        is_active="true"
    )
    db.add(product)
    db.commit()

    retrieved = db.query(Product).filter(Product.id == "TESTPROD").first()
    assert retrieved is not None
    assert retrieved.id == "TESTPROD"
```

### 2. Test FK Relationships

```python
def test_product_fk_relationship():
    # Create product
    product = Product(id="PARENT", company_id="DEFAULT", is_active="true")
    db.add(product)
    db.commit()

    # Create MPS item with product FK
    mps_item = MPSPlanItem(
        plan_id=1,
        product_id="PARENT",  # String FK
        site_id=1,
        weekly_quantities=[100, 120]
    )
    db.add(mps_item)
    db.commit()

    # Verify relationship
    assert mps_item.product.id == "PARENT"
```

### 3. Check API Endpoints

```bash
# Test product list
curl -X GET "http://localhost:8088/api/v1/supply-chain-configs/1/products"

# Test product creation
curl -X POST "http://localhost:8088/api/v1/supply-chain-configs/1/products" \
  -H "Content-Type: application/json" \
  -d '{"id": "NEWPROD", "description": "New Product", "company_id": "DEFAULT"}'
```

---

## Migration Checklist for Services

When updating a service file:

- [ ] Replace `from app.models.supply_chain_config import Item` with `from app.models.sc_entities import Product`
- [ ] Change all `Item` variable names to `product`
- [ ] Update all `item_id` to `product_id` (ensure String type)
- [ ] Change `db.query(Item)` to `db.query(Product)`
- [ ] Update FK filters to use String IDs: `Product.id == "CASE"` not `== 1`
- [ ] Remove any integer ID handling logic (e.g., `int(product_id)`)
- [ ] Update schema imports: `schemas.Item` → `schemas.Product`
- [ ] Update CRUD calls: `crud.item` → `crud.product`
- [ ] Test with real string product IDs
- [ ] Remove compatibility imports once no longer needed

---

## Need Help?

**Documentation**:
- [MIGRATION_STATUS.md](MIGRATION_STATUS.md) - Full migration status
- [AWS_SC_IMPLEMENTATION_STATUS.md](AWS_SC_IMPLEMENTATION_STATUS.md) - AWS SC compliance status
- [CLAUDE.md](CLAUDE.md) - Project overview

**Key Files**:
- Models: [backend/app/models/sc_entities.py](backend/app/models/sc_entities.py)
- Schemas: [backend/app/schemas/supply_chain_config.py](backend/app/schemas/supply_chain_config.py)
- CRUD: [backend/app/crud/crud_supply_chain_config.py](backend/app/crud/crud_supply_chain_config.py)
- API: [backend/app/api/endpoints/supply_chain_config.py](backend/app/api/endpoints/supply_chain_config.py)
- Compatibility: [backend/app/models/compatibility.py](backend/app/models/compatibility.py)

**Migration Scripts**:
- [backend/scripts/migrate_items_to_products.py](backend/scripts/migrate_items_to_products.py)
- [backend/scripts/demo_mps_key_materials.py](backend/scripts/demo_mps_key_materials.py)

---

**Last Updated**: January 22, 2026
