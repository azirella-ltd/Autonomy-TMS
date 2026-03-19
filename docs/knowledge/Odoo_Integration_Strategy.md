# Odoo ERP Integration Strategy — Autonomy Platform

**Date**: 2026-03-18 | **Status**: Research / Pre-Implementation

---

## Why Odoo

Odoo is the **fastest-growing ERP** globally ($650M revenue, +50% YoY growth). It dominates the mid-market segment — exactly Autonomy's target customer base. While SAP targets enterprises ($500K+/yr), Odoo serves SMBs and mid-market manufacturers at a fraction of the cost.

**Strategic fit:**
- **Same target market** as Autonomy: mid-market manufacturers frustrated with enterprise ERP costs
- **Open source** (Community Edition) + commercial (Enterprise) = easy integration, no licensing barriers
- **PostgreSQL native** — same DB as Autonomy, simplifies deployment and data access
- **Docker-native** — official Docker image, same deployment model as Autonomy
- **Built-in demo data** — no SAP CAL needed, spin up in minutes with full manufacturing data
- **70/30 revenue share** on Odoo Apps Store — Autonomy can sell as an Odoo app
- **12M+ users worldwide** — massive addressable market

---

## Odoo Partner Program

### App Store (ISV Path) — Recommended

| Aspect | Details |
|--------|---------|
| **Revenue share** | 70% to vendor, 30% to Odoo |
| **Listing cost** | Free to list |
| **Requirements** | Module manifest with price, description, screenshots, bug-free |
| **Supported currencies** | EUR, USD |
| **Payment** | Monthly automatic or manual invoice |
| **Restrictions** | No obfuscated code, no silent data collection, lowest price on web |
| **URL** | https://apps.odoo.com/apps/upload |

### Implementation Partner (Not Recommended for Autonomy)

The standard partner program (Learning → Ready → Silver → Gold) is for implementation consultancies, not ISVs. It requires selling Odoo Enterprise licenses (10-300 new users/year) and maintaining certified resources. Not the right fit.

---

## Odoo Data Model → AWS SC Data Model Mapping

Odoo uses dot-notation model names (e.g., `product.product`) which map to PostgreSQL tables with underscores (e.g., `product_product`). ~600 tables total.

### Core Supply Chain Models

| Odoo Model | Table Name | AWS SC Entity | SAP Equivalent |
|-----------|-----------|--------------|----------------|
| `product.template` | product_template | Product | MARA |
| `product.product` | product_product | Product (variant) | MARC |
| `product.category` | product_category | ProductHierarchy | T179 |
| `uom.uom` | uom_uom | (unit of measure) | MARM |
| `stock.warehouse` | stock_warehouse | Site | T001W |
| `stock.location` | stock_location | Site (storage) | T001L/LGORT |
| `res.company` | res_company | Company | T001 |
| `res.partner` | res_partner | TradingPartner | KNA1/LFA1 |
| `sale.order` | sale_order | OutboundOrder | VBAK |
| `sale.order.line` | sale_order_line | OutboundOrderLine | VBAP |
| `purchase.order` | purchase_order | InboundOrder | EKKO |
| `purchase.order.line` | purchase_order_line | InboundOrderLine | EKPO |
| `mrp.production` | mrp_production | ProductionProcess | AFKO |
| `mrp.bom` | mrp_bom | ProductBOM | STKO |
| `mrp.bom.line` | mrp_bom_line | ProductBOM (component) | STPO |
| `mrp.routing.workcenter` | mrp_routing_workcenter | ProcessOperation | PLPO |
| `mrp.workcenter` | mrp_workcenter | CapacityResource | CRHD |
| `stock.picking` | stock_picking | Shipment | LIKP |
| `stock.move` | stock_move | ShipmentLot | LIPS |
| `stock.quant` | stock_quant | InvLevel | MARD |
| `stock.warehouse.orderpoint` | stock_warehouse_orderpoint | InvPolicy | — |
| `stock.rule` | stock_rule | SourcingRules | EORD |
| `stock.route` | stock_route | TransportationLane | — |
| `quality.check` | quality_check | QualityOrder | QALS |
| `quality.alert` | quality_alert | QualityOrder (alert) | QMEL |
| `maintenance.request` | maintenance_request | MaintenanceOrder | — |
| `maintenance.equipment` | maintenance_equipment | (asset) | EQUI |
| `account.move` | account_move | Invoice | — |

### Key Differences from SAP

| Aspect | SAP | Odoo |
|--------|-----|------|
| **Product master** | MARA (header) + MARC (plant) + MARD (storage) | product.template (header) + product.product (variant) |
| **BOM** | STKO (header) + STPO (items) | mrp.bom + mrp.bom.line |
| **Customer/Vendor** | KNA1 (customer) + LFA1 (vendor) — separate | res.partner (unified — type field distinguishes) |
| **Inventory** | MARD (storage location) + MBEW (valuation) | stock.quant (location-level qty + value) |
| **Production** | AFKO (header) + AFPO (items) + AFVC (operations) | mrp.production (unified with work orders) |
| **Warehouse** | T001W (plant) + T001L (storage location) | stock.warehouse + stock.location (hierarchical) |
| **Routes** | EORD (source list) + transportation lanes | stock.route + stock.rule (pull/push rules) |
| **Company** | T001 (company code) | res.company (multi-company native) |

---

## Demo Data — Built-In (No Translation Needed)

Odoo ships with **built-in demo data** for every module. Spin up with Docker:

```yaml
# docker-compose.odoo-demo.yml
version: '3'
services:
  odoo:
    image: odoo:18.0
    depends_on:
      - db
    ports:
      - "8069:8069"
    environment:
      - HOST=db
      - USER=odoo
      - PASSWORD=odoo
    command: -- --database=odoo_demo --init=sale,purchase,mrp,stock,quality,maintenance --demo=all

  db:
    image: postgres:15
    environment:
      - POSTGRES_USER=odoo
      - POSTGRES_PASSWORD=odoo
      - POSTGRES_DB=postgres
```

This creates a database with:
- Products with variants, BOMs, routings
- Warehouses, locations, stock rules
- Sample sales orders, purchase orders
- Manufacturing orders with operations
- Quality checks, maintenance requests
- Demo customers and vendors

**Access**: http://localhost:8069 → Login: admin / admin

### Extracting Demo Data via API

```python
import xmlrpc.client

url = "http://localhost:8069"
db = "odoo_demo"
username = "admin"
password = "admin"

# Authenticate
common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
uid = common.authenticate(db, username, password, {})
models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

# Read products
products = models.execute_kw(db, uid, password,
    'product.product', 'search_read',
    [[]],  # domain (all records)
    {'fields': ['name', 'default_code', 'type', 'categ_id', 'standard_price', 'list_price'],
     'limit': 100})

# Read BOMs
boms = models.execute_kw(db, uid, password,
    'mrp.bom', 'search_read',
    [[]],
    {'fields': ['product_tmpl_id', 'product_qty', 'type', 'bom_line_ids']})

# Read warehouses
warehouses = models.execute_kw(db, uid, password,
    'stock.warehouse', 'search_read',
    [[]],
    {'fields': ['name', 'code', 'company_id', 'lot_stock_id']})

# Read inventory (stock.quant)
inventory = models.execute_kw(db, uid, password,
    'stock.quant', 'search_read',
    [[]],
    {'fields': ['product_id', 'location_id', 'quantity', 'reserved_quantity']})
```

> **Note**: Odoo 19+ introduces a new **External JSON-2 API** replacing XML-RPC/JSON-RPC (deprecated, removal in Odoo 22 / fall 2028). Plan for the new API.

---

## API Access Methods

| Method | Protocol | Odoo Version | Status | Use Case |
|--------|----------|-------------|--------|----------|
| **XML-RPC** | `/xmlrpc/2/object` | All versions | Deprecated (removal Odoo 22) | Legacy integration |
| **JSON-RPC** | `/jsonrpc` | All versions | Deprecated (removal Odoo 22) | Web/mobile apps |
| **JSON-2 API** | `/api/...` | 19+ | Current | Modern integration |
| **REST API** | Standard HTTP | 17+ | Current | Standard REST |
| **Direct PostgreSQL** | Port 5432 | All (self-hosted) | Always available | Bulk extraction (fastest) |

**Recommended for Autonomy**: Direct PostgreSQL access for self-hosted Odoo (same as HANA DB Direct for SAP), JSON-2 API for Odoo.sh/cloud.

---

## Implementation Plan

### Phase 1: Odoo Connector Service

Create `backend/app/services/odoo_deployment_service.py` (parallel to `sap_deployment_service.py`):

- Connection types: **JSON-2 API** (cloud), **Direct PostgreSQL** (self-hosted), **CSV import**
- Authentication: username/password or API key
- Model discovery: `ir.model` + `ir.model.fields` introspection
- Field mapping: Odoo model fields → AWS SC entity fields

### Phase 2: Data Extraction

Same 3-phase pipeline as SAP:
1. **Master Data**: product.product, stock.warehouse, res.partner, mrp.bom, mrp.workcenter
2. **Transactional**: sale.order, purchase.order, mrp.production, stock.picking
3. **CDC**: stock.quant changes, mrp.production state changes

### Phase 3: Odoo App Store Listing

Package Autonomy's AI planning as an Odoo module:
- **Odoo App**: `autonomy_sc_planning` — installs menu items, dashboards, API connector
- **Backend**: Autonomy platform (SaaS) receives data from Odoo via API
- **Pricing**: $99-499/month via Odoo Apps Store (70% to Autonomy)

---

## Competitive Advantage

No other supply chain AI platform supports **both SAP and Odoo** with the same AWS SC Data Model underneath. This means:

1. **SAP customer** deploys Autonomy → data mapped to AWS SC model
2. **Odoo customer** deploys Autonomy → data mapped to same AWS SC model
3. **AI agents trained on SAP data** can transfer-learn to Odoo data (same feature space)
4. **Customers migrating SAP → Odoo** (common in mid-market) keep their Autonomy investment

---

## Sources

- [Odoo Supply Chain Documentation v18](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp.html)
- [Odoo External API v18](https://www.odoo.com/documentation/18.0/developer/reference/external_api.html)
- [Odoo External JSON-2 API v19](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)
- [Odoo Docker Hub](https://hub.docker.com/_/odoo/)
- [Odoo Apps Store Vendor Guidelines](https://apps.odoo.com/apps/vendor-guidelines)
- [Odoo Partner Program](https://www.odoo.com/become-a-partner)
- [Odoo Apps Store FAQ](https://apps.odoo.com/apps/faq)
- [Odoo Supply Chain Review (2026)](https://www.erpresearch.com/erp/odoo/supply-chain-management)
