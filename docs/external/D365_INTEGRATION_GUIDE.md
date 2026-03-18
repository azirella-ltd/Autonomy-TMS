# Microsoft Dynamics 365 F&O Integration Guide

## Overview

Autonomy integrates with Microsoft Dynamics 365 Finance & Operations (F&O) to extract supply chain master data, transaction data, and planning parameters. Data is mapped to the AWS Supply Chain data model and used for AI-driven planning and execution.

**Supported versions**: Dynamics 365 Finance, Dynamics 365 Supply Chain Management (cloud-hosted, version 10.0+)

**Connection methods**: OData v4 API (recommended), Data Management Framework (DMF) bulk export, CSV file import

---

## 1. Prerequisites

### 1.1 Microsoft Accounts & Licenses

| Requirement | Detail |
|-------------|--------|
| **Azure AD Tenant** | A Microsoft Entra ID (formerly Azure AD) organizational tenant. Personal `@outlook.com` or `@gmail.com` accounts do NOT work |
| **D365 F&O Environment** | Production, Sandbox, or Trial environment |
| **Azure Subscription** | Required for Azure AD app registration (free tier sufficient) |
| **Global Admin or App Admin** | Required to register the Azure AD application and grant API permissions |
| **D365 System Administrator** | Required to register the Azure AD app inside D365 F&O |

### 1.2 For Trial / Demo Environments

A 30-day free trial is available at: https://www.microsoft.com/en-us/dynamics-365/free-trial

The trial includes **Contoso demo data** (USMF legal entity) with:
- 2,500+ released products with multi-level BOMs
- 5-8 operational sites, 15+ warehouses
- 200+ vendors and customers
- Inventory on-hand, safety stock settings, demand forecasts
- Production orders, purchase orders, sales orders

**If you don't have an organizational account**: Sign up for a Microsoft 365 Business trial first (free) at https://www.microsoft.com/en-us/microsoft-365/business — this creates a `.onmicrosoft.com` tenant you can use for the D365 trial.

---

## 2. Azure AD Application Registration

### 2.1 Create the App Registration

1. Go to **Azure Portal** → https://portal.azure.com
2. Navigate to **Microsoft Entra ID** → **App registrations** → **New registration**
3. Configure:
   - **Name**: `Autonomy-D365-Integration`
   - **Supported account types**: "Accounts in this organizational directory only" (single tenant)
   - **Redirect URI**: Leave blank (not needed for client credentials)
4. Click **Register**
5. Note the **Application (client) ID** and **Directory (tenant) ID** from the Overview page

### 2.2 Create a Client Secret

1. In the app registration, go to **Certificates & secrets** → **New client secret**
2. Set description: `Autonomy SC extraction`
3. Set expiry: 12 months (or 24 months)
4. Click **Add**
5. **Copy the secret value immediately** — it is only displayed once

### 2.3 Add API Permissions

1. Go to **API permissions** → **Add a permission**
2. Select **APIs my organization uses** → search for **Dynamics ERP** (or `Microsoft.ERP`)
3. Select **Application permissions**:
   - `Connector.FullAccess` (for DMF operations)
   - `CustomService.FullAccess` (for custom service calls)
4. Alternatively, under **Delegated permissions**:
   - `Odata.FullAccess` (for OData queries)
5. Click **Grant admin consent for [tenant name]** (requires Global Admin)

### 2.4 Register in D365 F&O

1. Log into your D365 F&O environment
2. Navigate to **System administration** → **Setup** → **Microsoft Entra applications**
3. Click **New**
4. Enter:
   - **Client ID**: The Application (client) ID from step 2.1
   - **Name**: `Autonomy Integration`
   - **User ID**: Select or create a D365 service account user (see Section 3)
5. Save

---

## 3. D365 User & Security Roles

### 3.1 Service Account User

Create a dedicated service account in D365 for the integration:

1. Navigate to **System administration** → **Users** → **Users**
2. Click **New**
3. Configure:
   - **User ID**: `AUTONOMY_SVC`
   - **User name**: `Autonomy Integration Service`
   - **Email**: (use a shared mailbox or service account email)
   - **Company**: `USMF` (or your target legal entity)
4. Save

### 3.2 Required Security Roles

Assign the following security roles to the service account:

| Security Role | Purpose | Required For |
|---------------|---------|-------------|
| **Entity store reader** | Read access to all data entities | OData extraction |
| **Product information management clerk** | Product and BOM read access | Products, BOMs |
| **Procurement agent** | Purchase order read access | POs, Vendors |
| **Sales order clerk** | Sales order read access | SOs, Customers |
| **Warehouse manager** | Inventory and warehouse read access | Inventory, Warehouses |
| **Production floor manager** | Production order read access | Production orders |
| **Master planning clerk** | Planning and forecast read access | Forecasts, Coverage |

**For simplicity in trial/demo environments**, you can assign:
- **System administrator** (grants full read/write access — use only in non-production)

### 3.3 Security Role Assignment

1. Navigate to **System administration** → **Users** → select `AUTONOMY_SVC`
2. Click **Assign roles**
3. Select the roles listed above
4. Click **Assign to user**

### 3.4 Data Entity Visibility

D365 data entities have an `IsPublic` flag. Only public entities are accessible via OData. All standard supply chain entities (ReleasedProductsV2, Warehouses, Vendors, etc.) are public by default.

Custom entities or entities where `IsPublic = No` require:
1. Setting `IsPublic = Yes` in the entity configuration
2. Or using the Data Management Framework (DMF) instead of OData

---

## 4. Connection Methods

### 4.1 OData v4 API (Recommended)

**Endpoint**: `https://<environment>.operations.dynamics.com/data/`

**Authentication**: OAuth 2.0 Client Credentials flow

```
POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&client_id={application_id}
&client_secret={client_secret}
&scope=https://{environment}.operations.dynamics.com/.default
```

**Key parameters**:
- `$filter=dataAreaId eq 'usmf'` — scope to legal entity
- `$select=field1,field2` — select specific fields
- `$top=5000` — page size (max 10,000)
- `cross-company=true` — query across all legal entities

**Rate limits**: No hard limits but throttling on high-volume requests. Use `$top` and `@odata.nextLink` pagination.

**Autonomy extraction script**: `backend/scripts/extract_d365_contoso.py`

### 4.2 Data Management Framework (DMF)

For bulk export without programming:

1. In D365: **Workspaces** → **Data management** → **Export**
2. Create a new export project
3. Add entities (e.g., "Released products V2", "Bill of materials headers")
4. Set **Target data format** to CSV
5. Add `$filter: dataAreaId eq 'usmf'` to each entity
6. Click **Export**
7. Download the ZIP package containing one CSV per entity

**Autonomy config builder**: `backend/scripts/rebuild_d365_contoso_config.py`

### 4.3 CSV File Import

If OData and DMF are not available (e.g., air-gapped environments), data can be exported manually:

1. Use **Open in Excel** on any D365 list page
2. Save as CSV
3. Place CSVs in a directory
4. Run: `python scripts/rebuild_d365_contoso_config.py --config-id <ID> --csv-dir /path/to/csvs`

---

## 5. Data Entities Extracted

### 5.1 Master Data (Phase 1)

| D365 Entity | AWS SC Target | Records (USMF) | Notes |
|-------------|---------------|-----------------|-------|
| Sites / OperationalSites | `site` | ~5-8 | Manufacturing and distribution sites |
| Warehouses | `site` (child) | ~15-25 | Warehouses within sites |
| ReleasedProductsV2 | `product` | ~2,500 | Finished goods, raw materials |
| VendorsV2 | `trading_partner` (vendor) | ~100-200 | Supplier master |
| CustomersV3 | `trading_partner` (customer) | ~100-200 | Customer master |
| BillOfMaterialsHeaders | `product_bom` (header) | ~200-400 | Active BOMs |
| BillOfMaterialsLines | `product_bom` (component) | ~1,000+ | BOM components with scrap rates |
| VendorLeadTimes | `vendor_lead_time` | varies | Lead time by vendor+product+site |
| InventWarehouseOnHandEntity | `inv_level` | thousands | On-hand inventory |
| ItemCoverageSettings | `inv_policy` | ~100+ | Safety stock, min/max levels |
| TransportationRoutes | `transportation_lane` | varies | Inter-site routes |

### 5.2 Transaction Data (Phase 3)

| D365 Entity | AWS SC Target | Notes |
|-------------|---------------|-------|
| PurchaseOrderHeadersV2/LinesV2 | `inbound_order` | Open and historical POs |
| SalesOrderHeadersV2/LinesV2 | `outbound_order` | Open and historical SOs |
| ProductionOrderHeaders | `production_order` | Manufacturing orders |
| DemandForecastEntries | `forecast` | Demand forecast quantities |

### 5.3 Change Data Capture (Phase 2)

D365 entities with change tracking enabled expose `ModifiedDateTime`. The Autonomy connector filters on `ModifiedDateTime gt <timestamp>` to extract only changed records since the last sync.

---

## 6. Field Mapping

All D365 fields are mapped to AWS Supply Chain data model entities via the 3-tier mapping service:

- **Tier 1 (Exact)**: 21 D365 entities with field-level mappings (confidence: 100%)
- **Tier 2 (Pattern)**: Regex matching for D365 PascalCase conventions (confidence: 75%)
- **Tier 3 (Fuzzy/AI)**: String similarity + Claude AI for custom fields (confidence: varies)

Implementation: `backend/app/integrations/d365/field_mapping.py`

---

## 7. Network & Firewall Requirements

| Service | Protocol | Port | Direction | Purpose |
|---------|----------|------|-----------|---------|
| Azure AD | HTTPS | 443 | Outbound | OAuth token acquisition |
| D365 F&O | HTTPS | 443 | Outbound | OData API calls |
| login.microsoftonline.com | HTTPS | 443 | Outbound | Authentication |

No inbound connections are required. All communication is initiated by the Autonomy platform.

---

## 8. Security Considerations

- **Credentials**: Client secrets are stored encrypted in the `erp_connections` table
- **Least privilege**: Use read-only security roles (Section 3.2) — Autonomy does not write back to D365
- **Token lifetime**: OAuth tokens expire after 1 hour; the connector refreshes automatically
- **Data scoping**: All queries include `dataAreaId` filter to scope to a single legal entity
- **Tenant isolation**: Each Autonomy tenant has its own ERP connection — no cross-tenant data access

---

## 9. Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|------------|
| `401 Unauthorized` | Token expired or invalid | Re-authenticate; check client secret expiry |
| `403 Forbidden` | Insufficient permissions | Verify security roles (Section 3.2) and API permissions (Section 2.3) |
| `404 Not Found` on entity | Entity not public or renamed | Check `IsPublic` flag; verify entity name in `$metadata` |
| Empty results with valid entity | `dataAreaId` filter mismatch | Verify legal entity code (case-sensitive: `usmf` not `USMF`) |
| `429 Too Many Requests` | Rate throttling | Reduce `$top` page size; add delays between requests |
| DMF export stuck at "Running" | Large dataset or system load | Cancel and retry with smaller entity selection |
