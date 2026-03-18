# Odoo User Authorization Guide

## Quick Reference: Minimum Permissions for Autonomy Integration

### Integration User

| Setting | Value |
|---------|-------|
| **User Name** | `Autonomy Integration` |
| **Login (Email)** | `autonomy@yourcompany.com` |
| **Authentication** | API Key (recommended) or password |
| **User Type** | Internal User |
| **Companies** | Restricted to target company only |

### Required Access Groups

| Module | Group | Technical Name | Purpose |
|--------|-------|---------------|---------|
| **Inventory** | User | `stock.group_stock_user` | Warehouses, locations, quants, transfers |
| **Manufacturing** | User | `mrp.group_mrp_user` | BOMs, work centers, production orders |
| **Purchase** | User | `purchase.group_purchase_user` | Purchase orders, vendor pricelists |
| **Sales** | User | `sale.group_sale_salesman` | Sale orders, customers |
| **Technical** | Technical Settings | `base.group_no_one` (enabled) | Required for `ir.model` API introspection |

### Connection Details

| Parameter | Docker Demo | Production |
|-----------|------------|------------|
| **URL** | `http://localhost:8069` | `https://odoo.yourcompany.com` |
| **Database** | `odoo18demo` | Customer-specific |
| **Protocol** | JSON-RPC | JSON-RPC (HTTPS) |
| **Endpoint** | `/jsonrpc` | `/jsonrpc` |
| **Auth** | Password or API Key | API Key (recommended) |
| **Timeout** | 120s | 120s |

---

## Step-by-Step Setup Checklist

### For the Odoo Administrator

- [ ] Create dedicated integration user (Section 2 below)
- [ ] Assign minimum access groups (see table above)
- [ ] Generate API key for the user
- [ ] Verify required modules are installed (Inventory, Manufacturing, Purchase, Sales)
- [ ] If multi-company: restrict user to target company only
- [ ] Test: verify JSON-RPC authentication returns a valid uid
- [ ] Document the database name

### For the Autonomy Platform Administrator

- [ ] Create ERP connection in Autonomy (Admin > ERP Data Management)
- [ ] Enter: Odoo URL, database name, username, API key
- [ ] Test connection
- [ ] Run initial master data extraction
- [ ] Verify model counts match expected data
- [ ] Schedule CDC (change data capture) sync

---

## Detailed Permission Reference

### Model-Level Access Control

Odoo uses `ir.model.access` records to control read/write/create/delete per model per group. The integration user needs **read only** (`perm_read = True`) on all supply chain models.

To verify access for a specific model:
```sql
-- Run in Odoo's PostgreSQL database
SELECT m.model, a.perm_read, g.name as group_name
FROM ir_model_access a
JOIN ir_model m ON m.id = a.model_id
LEFT JOIN res_groups g ON g.id = a.group_id
WHERE m.model = 'product.product'
ORDER BY g.name;
```

### Complete Model Access Matrix

| Model | Group Required | Perm Read | Notes |
|-------|---------------|-----------|-------|
| `res.company` | Base (all users) | Yes | Company info |
| `res.partner` | Base (all users) | Yes | Vendors + customers |
| `res.country` | Base (all users) | Yes | Country reference |
| `uom.uom` | Base (all users) | Yes | Units of measure |
| `product.product` | `stock.group_stock_user` | Yes | Product variants |
| `product.template` | `stock.group_stock_user` | Yes | Product templates |
| `product.category` | `stock.group_stock_user` | Yes | Product categories |
| `product.supplierinfo` | `purchase.group_purchase_user` | Yes | Vendor pricing + lead times |
| `stock.warehouse` | `stock.group_stock_user` | Yes | Warehouses |
| `stock.location` | `stock.group_stock_user` | Yes | Stock locations |
| `stock.quant` | `stock.group_stock_user` | Yes | On-hand inventory |
| `stock.warehouse.orderpoint` | `stock.group_stock_user` | Yes | Reorder rules |
| `stock.picking` | `stock.group_stock_user` | Yes | Stock transfers |
| `stock.move` | `stock.group_stock_user` | Yes | Stock movements |
| `stock.picking.type` | `stock.group_stock_user` | Yes | Operation types |
| `mrp.bom` | `mrp.group_mrp_user` | Yes | Bills of materials |
| `mrp.bom.line` | `mrp.group_mrp_user` | Yes | BOM components |
| `mrp.workcenter` | `mrp.group_mrp_user` | Yes | Work centers |
| `mrp.routing.workcenter` | `mrp.group_mrp_user` | Yes | Routing operations |
| `mrp.production` | `mrp.group_mrp_user` | Yes | Manufacturing orders |
| `mrp.workorder` | `mrp.group_mrp_user` | Yes | Work orders |
| `purchase.order` | `purchase.group_purchase_user` | Yes | Purchase orders |
| `purchase.order.line` | `purchase.group_purchase_user` | Yes | PO lines |
| `sale.order` | `sale.group_sale_salesman` | Yes | Sale orders |
| `sale.order.line` | `sale.group_sale_salesman` | Yes | SO lines |
| `ir.module.module` | `base.group_no_one` | Yes | Installed modules (discovery) |

### Record Rules (Row-Level Security)

Odoo also has `ir.rule` records that filter which records a user can see based on domain expressions. Common rules that affect extraction:

| Rule | Model | Effect | Resolution |
|------|-------|--------|------------|
| Multi-company | Most models | User sees only records from their assigned companies | Assign user to target company |
| Warehouse access | `stock.quant` | User sees inventory only in accessible warehouses | Ensure user has access to all warehouses |
| My documents | `purchase.order`, `sale.order` | User sees only their own orders | Grant "See all" group or use admin API key |

To bypass "my documents" rules, assign additional groups:
- Purchase: `purchase.group_purchase_manager` (see all POs)
- Sales: `sale.group_sale_salesman_all_leads` (see all SOs)

---

## API Key Management

### Generate API Key

1. Log in as the integration user
2. Click user avatar → **My Profile** → **Account Security** tab
3. **API Keys** section → **New API Key**
4. Description: `Autonomy SC Extraction`
5. Copy the key immediately (shown only once)

### Use API Key

Replace the password with the API key in all JSON-RPC calls:

```python
# Normal auth: uid = authenticate(db, "user@email", "password")
# API key:     uid = authenticate(db, "user@email", "api-key-value")
# The API key works as a drop-in replacement for the password
```

### Revoke API Key

1. Log in as admin
2. Navigate to **Settings** → **Users** → select integration user
3. **Account Security** → **API Keys** → click trash icon on the key
4. Or via SQL: `DELETE FROM auth_api_key WHERE user_id = <uid>`

### Key Rotation

| Item | Rotation Period | How |
|------|-----------------|-----|
| API Key | Every 6-12 months | Generate new key, update Autonomy connection, delete old key |
| User Password | Per company policy | Settings > Users > Change Password |
| Database Master Password | At setup only | Configuration file `odoo.conf` |

---

## Docker Demo Credentials Reference

| Item | Value |
|------|-------|
| **Odoo URL** | `http://localhost:8069` |
| **Database** | `odoo18demo` |
| **Admin Email** | `admin@example.com` (set at DB creation) |
| **Admin Password** | `admin` (set at DB creation) |
| **DB Master Password** | `admin` (default, change in production) |
| **PostgreSQL User** | `odoo` |
| **PostgreSQL Password** | `odoo` |
| **Database Manager** | `http://localhost:8069/web/database/manager` |
| **JSON-RPC Endpoint** | `http://localhost:8069/jsonrpc` |

---

## Security Hardening (Production)

### Principle of Least Privilege

1. Create a dedicated integration user (never use `admin`)
2. Assign only the User-level groups listed above (not Manager/Administrator)
3. Use API key authentication (not password)
4. Restrict to a single company in multi-company setups
5. Enable audit logging (`base.group_erp_manager` can view logs)

### Network Security

1. **HTTPS only**: Configure Nginx reverse proxy with valid SSL certificate
2. **IP whitelisting**: Restrict Odoo access to Autonomy server IPs via firewall
3. **Separate database user**: If using direct SQL export, create a PostgreSQL user with `SELECT`-only on the Odoo database
4. **VPN**: For cloud-hosted Odoo, use VPN or private network for JSON-RPC access

### Odoo Configuration File (`odoo.conf`)

```ini
[options]
; Restrict database operations
list_db = False          ; Hide database list from login page
admin_passwd = <strong>  ; Change from default 'admin'
proxy_mode = True        ; Required when behind reverse proxy
db_name = odoo18demo     ; Restrict to single database
```

---

## Troubleshooting Permission Errors

### `Authentication failed`

1. Check: Is the database name correct? List databases via `/web/database/manager`
2. Check: Is the email address correct? (Odoo uses email as login, not username)
3. Check: Is the password or API key correct?
4. Check: Is the user active? (not archived)

### `Access Denied` on Model

1. Check: Does the user have the required group? (See Model Access Matrix)
2. Check: Is the module installed? (`mrp.bom` requires Manufacturing module)
3. Diagnose: `ir.model.access` records control access — check via SQL or Odoo Settings > Technical > Security > Access Rules

### Empty Results

1. Check: Is the user assigned to the correct company? (multi-company rule)
2. Check: Are there record rules filtering results? (Settings > Technical > Security > Record Rules)
3. Check: Is the domain filter too restrictive? (e.g., `type = product` excludes services)

### `Model not found`

1. Check: Is the module installed? (e.g., `mrp.production` requires Manufacturing module)
2. Check: Is Technical Settings enabled for the user? (needed for `ir.model` introspection)
3. Verify: API call to `fields_get` returns the model's fields
