# Odoo ERP Integration Guide

## Overview

Autonomy integrates with Odoo Community and Enterprise editions to extract supply chain master data, transaction data, and planning parameters. Data is mapped to the AWS Supply Chain data model and used for AI-driven planning and execution.

**Supported versions**: Odoo 16.0, 17.0, 18.0 (Community and Enterprise)

**Connection methods**: JSON-RPC API (recommended), XML-RPC API (legacy), CSV file import

---

## 1. Prerequisites

### 1.1 Odoo Instance

| Requirement | Detail |
|-------------|--------|
| **Odoo Server** | Self-hosted (Docker) or Odoo.com cloud subscription |
| **Admin Access** | Odoo user with "Administration / Settings" group |
| **Installed Modules** | Inventory, Manufacturing (MRP), Purchase, Sales |
| **API Access** | JSON-RPC enabled (default — no configuration needed) |
| **PostgreSQL** | Odoo's database (for direct CSV export if needed) |

### 1.2 For Development / Demo

Stand up a free Odoo 18 instance with manufacturing demo data in under 5 minutes:

```bash
mkdir odoo18-demo && cd odoo18-demo

cat > docker-compose.yml << 'EOF'
services:
  odoo:
    image: odoo:18.0
    depends_on: [db]
    ports: ["8069:8069"]
    environment:
      HOST: db
      USER: odoo
      PASSWORD: odoo
  db:
    image: postgres:17
    environment:
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: odoo
      POSTGRES_DB: postgres
volumes:
  odoo-data:
  db-data:
EOF

docker compose up -d
```

Then open http://localhost:8069 and create a database:
- **Database Name**: `odoo18demo`
- **Email**: `admin@example.com`
- **Password**: `admin`
- **Demo data**: **CHECK THIS BOX**

After database creation, install modules: **Apps** → search and activate:
1. **Inventory** (`stock`)
2. **Manufacturing** (`mrp`)
3. **Purchase** (`purchase`)
4. **Sales** (`sale_management`)

**Demo data contents** (after module installation):

| Entity | Count | Notes |
|--------|-------|-------|
| Products | ~48 | Office furniture + manufacturing components |
| BOMs | 7 | Multi-level (4 deep): Table→Top→Panel→Layers |
| Work Centers | 3 | Assembly 1, Assembly 2, Drill 1 |
| Manufacturing Orders | 3-4 | Table, Table Top, Drawer |
| Warehouses | 1 | Default (WH) with standard locations |
| Inventory (quants) | ~12 | With lot/serial tracking |
| Reordering Rules | ~5 | Min/max stock rules |
| Partners (vendors+customers) | ~20+ | Companies and contacts |
| Purchase Orders | ~10 | Various states |
| Sale Orders | ~20 | Various states |
| Vendor Pricelists | ~2+ | With lead time (delay) |

---

## 2. User & Permission Configuration

### 2.1 Create a Dedicated Integration User

Do NOT use the admin account for integration. Create a dedicated user:

1. Navigate to **Settings** → **Users & Companies** → **Users**
2. Click **New**
3. Configure:
   - **Name**: `Autonomy Integration`
   - **Email**: `autonomy@yourcompany.com`
   - **Password**: (set a strong password)

### 2.2 Required Access Rights

Assign the following access groups to the integration user:

| Module | Access Group | Level | Purpose |
|--------|-------------|-------|---------|
| **Inventory** | Inventory / User | User | Read warehouses, locations, quants, pickings |
| **Manufacturing** | Manufacturing / User | User | Read BOMs, work centers, production orders |
| **Purchase** | Purchase / User | User | Read purchase orders, vendor pricelists |
| **Sales** | Sales / User | User | Read sale orders, customer data |
| **Contacts** | (implicit) | Read | Read res.partner records |
| **Extra Rights** | Technical Settings | Enabled | Required for API access to ir.model |

**To set access rights**:
1. Open the user record
2. Scroll to **Access Rights** tab
3. Set each module's access level as listed above
4. Save

### 2.3 API Key Authentication (Odoo 14+, recommended)

Instead of sending the user's password with every API call, use an API key:

1. Log in as the integration user
2. Navigate to **Preferences** (click user avatar → My Profile)
3. Go to the **Account Security** tab
4. Under **API Keys**, click **New API Key**
5. Enter a description: `Autonomy SC Extraction`
6. Click **Generate Key**
7. **Copy the key immediately** — it is only shown once

The API key replaces the password in all JSON-RPC/XML-RPC calls.

### 2.4 Access Rights Reference (Technical)

Odoo's access control is based on `ir.model.access` records. The integration user needs `read` (`perm_read = True`) on these models:

| Model | Group Required | Notes |
|-------|---------------|-------|
| `product.product` | Sales / User or Inventory / User | Products |
| `product.template` | Sales / User or Inventory / User | Product templates |
| `product.category` | Sales / User | Product categories |
| `mrp.bom` | Manufacturing / User | Bill of materials |
| `mrp.bom.line` | Manufacturing / User | BOM components |
| `mrp.workcenter` | Manufacturing / User | Work centers |
| `mrp.production` | Manufacturing / User | Manufacturing orders |
| `stock.warehouse` | Inventory / User | Warehouses |
| `stock.location` | Inventory / User | Stock locations |
| `stock.quant` | Inventory / User | On-hand inventory |
| `stock.warehouse.orderpoint` | Inventory / User | Reordering rules |
| `stock.picking` | Inventory / User | Stock transfers |
| `stock.move` | Inventory / User | Stock movements |
| `purchase.order` | Purchase / User | Purchase orders |
| `purchase.order.line` | Purchase / User | PO lines |
| `sale.order` | Sales / User | Sale orders |
| `sale.order.line` | Sales / User | SO lines |
| `res.partner` | (base access) | Vendors and customers |
| `res.company` | (base access) | Company information |
| `product.supplierinfo` | Purchase / User | Vendor pricelists & lead times |
| `uom.uom` | (base access) | Units of measure |

### 2.5 Multi-Company Access

If the Odoo instance has multiple companies:

1. The integration user must be assigned to the target company
2. Navigate to **Settings** → **Users** → select user → **Multi Companies** tab
3. Set **Allowed Companies** to include the target company
4. Set **Current Company** to the target company

API calls will respect the user's company scope.

---

## 3. Connection Configuration

### 3.1 JSON-RPC API (Recommended)

**Endpoint**: `http://<odoo-server>:8069/jsonrpc`

**Authentication**: Username + password (or API key)

```python
# Authenticate
POST http://localhost:8069/jsonrpc
{
    "jsonrpc": "2.0",
    "method": "call",
    "params": {
        "service": "common",
        "method": "authenticate",
        "args": ["odoo18demo", "admin@example.com", "admin", {}]
    }
}
# Returns: uid (integer)

# Query products
POST http://localhost:8069/jsonrpc
{
    "jsonrpc": "2.0",
    "method": "call",
    "params": {
        "service": "object",
        "method": "execute_kw",
        "args": [
            "odoo18demo", 2, "admin",
            "product.product", "search_read",
            [[["type", "=", "product"]]],
            {"fields": ["name", "default_code", "standard_price"]}
        ]
    }
}
```

**Autonomy extraction script**: `backend/scripts/extract_odoo_demo.py` (planned)

### 3.2 XML-RPC API (Legacy)

**Endpoints**:
- `http://<server>:8069/xmlrpc/2/common` — authentication
- `http://<server>:8069/xmlrpc/2/object` — data operations

Same authentication and query patterns as JSON-RPC but using XML-RPC protocol. Supported for backward compatibility with Odoo 12-15. **Note**: XML-RPC and JSON-RPC will be deprecated in Odoo 22 (Fall 2028) in favor of the JSON-2 API.

### 3.3 CSV File Import

For offline / air-gapped environments:

1. Export data from Odoo UI: **List view** → select records → **Actions** → **Export**
2. Or use direct SQL: `docker compose exec db psql -U odoo -d odoo18demo -c "COPY (...) TO STDOUT WITH CSV HEADER"`
3. Place CSVs in a directory
4. Run the Autonomy config builder

---

## 4. Data Models Extracted

### 4.1 Master Data (Phase 1 — 12 models)

| Odoo Model | AWS SC Target | Fields Extracted | Notes |
|------------|---------------|------------------|-------|
| `res.company` | `company` | id, name, country_id, currency_id | Organisation |
| `stock.warehouse` | `site` | id, name, code, partner_id | Warehouses → sites |
| `stock.location` | `site` (location) | id, name, usage, warehouse_id | Internal locations |
| `product.product` | `product` | id, name, default_code, type, standard_price, weight | Storable products only |
| `product.category` | `product_hierarchy` | id, name, parent_id | Category tree |
| `res.partner` | `trading_partner` | id, name, supplier_rank, customer_rank | Companies only |
| `product.supplierinfo` | `vendor_product` / `vendor_lead_time` | partner_id, price, delay | Vendor pricing & lead times |
| `mrp.bom` | `product_bom` (header) | product_tmpl_id, product_qty, type | BOM headers |
| `mrp.bom.line` | `product_bom` (component) | product_id, product_qty | BOM components |
| `mrp.workcenter` | `production_process` | name, capacity, costs_hour | Work centers |
| `stock.quant` | `inv_level` | product_id, location_id, quantity | On-hand inventory |
| `stock.warehouse.orderpoint` | `inv_policy` | product_min_qty, product_max_qty | Reorder rules |

### 4.2 Transaction Data (Phase 3 — 7 models)

| Odoo Model | AWS SC Target | Notes |
|------------|---------------|-------|
| `purchase.order` / `.line` | `inbound_order` | Purchase orders |
| `sale.order` / `.line` | `outbound_order` | Sale orders |
| `mrp.production` | `production_order` | Manufacturing orders |
| `stock.picking` / `stock.move` | `shipment` | Stock transfers |

### 4.3 Change Data Capture (Phase 2)

Odoo stores `write_date` on every model. The connector filters `write_date >= <last_sync>` to extract only changed records.

---

## 5. Field Mapping

All Odoo fields are mapped to AWS Supply Chain data model entities via the 3-tier mapping service:

- **Tier 1 (Exact)**: 20 Odoo models with field-level mappings (confidence: 100%)
- **Tier 2 (Pattern)**: Regex matching for Odoo naming conventions (confidence: 75%)
- **Tier 3 (Fuzzy/AI)**: String similarity + Claude AI for custom fields (confidence: varies)

**Odoo-specific type conversions**:
- Many2one fields return `[id, "Display Name"]` tuples — the connector extracts the ID
- Many2many fields return lists of IDs
- `False` is used for null values (converted to `None`)

Implementation: `backend/app/integrations/odoo/field_mapping.py`

---

## 6. Network & Firewall Requirements

| Service | Protocol | Port | Direction | Purpose |
|---------|----------|------|-----------|---------|
| Odoo Server | HTTP/HTTPS | 8069 (or 443) | Outbound | JSON-RPC API calls |
| PostgreSQL | TCP | 5432 | (optional) | Direct SQL export |

No inbound connections are required. All communication is initiated by the Autonomy platform.

**For Docker-hosted Odoo**: Ensure port 8069 is exposed and accessible from the Autonomy backend.

---

## 7. Security Considerations

- **Credentials**: Passwords / API keys are stored encrypted in the `erp_connections` table
- **Least privilege**: Use a dedicated integration user with read-only access (Section 2.2)
- **API keys preferred**: API keys can be revoked without changing the user password
- **Database isolation**: Odoo supports multiple databases per instance — specify the correct database name
- **No write-back**: Autonomy does not modify Odoo data — all access is read-only
- **Multi-company**: Ensure the integration user has access only to the target company
- **HTTPS**: For production, always use HTTPS with a valid certificate (configure via Odoo's `proxy_mode = True` behind Nginx)

---

## 8. Odoo Enterprise vs Community

| Feature | Community | Enterprise | Impact on Extraction |
|---------|-----------|------------|---------------------|
| Manufacturing (MRP) | Basic | Advanced (routing, PLM, subcontracting) | More production data in Enterprise |
| Quality Control | Not included | Included | No quality data in Community |
| Maintenance | Not included | Included | No maintenance data in Community |
| Forecasting | Not included | MRP scheduling + demand forecast | No forecast data in Community |
| Batch/Serial Tracking | Basic | Advanced | Simpler lot tracking in Community |
| Multi-warehouse | Basic | Advanced (barcode, wave picking) | Same warehouse model |
| Subcontracting | Not included | Included | Missing subcontracting in Community |

**Recommendation**: Enterprise edition provides significantly richer supply chain data. For demo/development, Community is sufficient to test the connector.

---

## 9. Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|------------|
| `Authentication failed` | Wrong database name, email, or password | Verify database name at `/web/database/manager` |
| `Access denied` on model | Insufficient access rights | Check user's groups (Section 2.2) |
| `Model not found` | Module not installed | Install required module (Section 1.2) |
| Empty product list | Products are `service` or `consumable` type | Extraction filters to `type = product` (storable) only |
| Timeout on large queries | Too many records in one call | Use `limit` and `offset` pagination (connector handles this) |
| `Database not found` | Wrong database name or database doesn't exist | List databases: `POST /jsonrpc {"service":"db","method":"list"}` |
| SSL errors | Self-signed certificate | Set `ssl_verify = false` in connection config |
