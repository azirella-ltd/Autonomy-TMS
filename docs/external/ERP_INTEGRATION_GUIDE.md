# ERP Integration Guide

## Overview

Autonomy integrates with enterprise ERP systems to extract supply chain master data, transaction data, and planning parameters. All data flows through a **standardized 3-phase pipeline** regardless of the source ERP, landing first in an ERP-specific PostgreSQL staging schema before being mapped to the canonical AWS Supply Chain data model.

**Supported ERPs**: SAP S/4HANA / ECC, Microsoft Dynamics 365 F&O, Odoo Community / Enterprise

**Planned**: Oracle NetSuite, Epicor Kinetic, Infor CloudSuite M3

---

## Architecture: The ERP Staging Pattern

**CRITICAL**: All ERP integrations follow the same architecture. The SAP integration is the template — D365 and Odoo replicate this pattern exactly.

```
┌─────────────┐     ┌──────────────────────┐     ┌─────────────────────┐
│   ERP System │────►│  ERP Staging Schema   │────►│  AWS SC Data Model  │
│              │     │  (PostgreSQL)         │     │  (public schema)    │
│  SAP S/4HANA │     │  sap_staging.*        │     │                     │
│  D365 F&O    │     │  d365_staging.*       │     │  site, product,     │
│  Odoo        │     │  odoo_staging.*       │     │  product_bom,       │
│              │     │                       │     │  trading_partner,   │
│  RFC/OData/  │     │  extraction_runs      │     │  inv_level,         │
│  JSON-RPC/   │     │  rows (JSONB)         │     │  inv_policy,        │
│  DMF/CSV     │     │  table_schemas        │     │  forecast,          │
│              │     │                       │     │  inbound_order, ... │
└─────────────┘     └──────────────────────┘     └─────────────────────┘
    Phase 0              Phase 1                     Phase 2
   Connection         ERP Staging                 AWS SC Mapping
```

### Three-Phase Data Flow

| Phase | Name | What Happens | Where Data Lands |
|-------|------|-------------|------------------|
| **Phase 0** | Connection | Authenticate, discover available tables/entities | `erp_connections` table |
| **Phase 1** | ERP Staging | Extract raw ERP data via API or CSV; store as JSONB rows with business keys | `{erp}_staging.rows` |
| **Phase 2** | AWS SC Mapping | Map staged rows to AWS SC entities; build SupplyChainConfig | `public.site`, `public.product`, etc. |

### Why ERP Staging?

1. **Audit trail**: Raw ERP data is preserved exactly as extracted — no transformation loss
2. **Delta detection**: Compare current extraction with previous via `row_hash` to detect changes
3. **Schema drift**: `table_schemas` tracks column sets per ERP table per tenant — alerts on changes
4. **Replay**: If the AWS SC mapping logic changes, re-run Phase 2 from staging without re-extracting
5. **Debugging**: When AWS SC data looks wrong, inspect the raw staging data to find the root cause
6. **Multi-ERP**: A tenant can have both SAP and D365 connections — each in its own staging schema

### PostgreSQL Schemas

Each ERP gets its own PostgreSQL schema with three identical tables:

| Schema | Tables | Rows Stored As |
|--------|--------|---------------|
| `sap_staging` | `extraction_runs`, `rows`, `table_schemas` | SAP table name + JSONB row |
| `d365_staging` | `extraction_runs`, `rows`, `table_schemas` | D365 entity name + JSONB row |
| `odoo_staging` | `extraction_runs`, `rows`, `table_schemas` | Odoo model name + JSONB row |

The `rows` table uses JSONB for the actual data — this allows any ERP table/entity structure to be stored without schema changes. Business keys are extracted for delta detection and deduplication.

### Data Categories

Each ERP table/entity is classified by refresh cadence:

| Category | Refresh | Examples |
|----------|---------|---------|
| **Master** | Weekly | Products, sites, BOMs, vendors, customers, work centers |
| **Transaction** | Daily | POs, SOs, production orders, shipments, requisitions |
| **CDC** | Hourly | Goods receipts, confirmations, inventory movements, status changes |

---

## ERP Connection Model

All ERPs share the `erp_connections` table (public schema):

| Field | Description |
|-------|-------------|
| `erp_type` | `sap`, `d365`, `odoo`, `netsuite`, `epicor` |
| `connection_method` | `rest_api`, `odata`, `json_rpc`, `csv`, `rfc`, `db_direct`, `dmf` |
| `base_url` | ERP server URL |
| `auth_type` | `password`, `api_key`, `oauth2_client_credentials`, `certificate` |
| `auth_credentials_encrypted` | Encrypted JSON blob with credentials |
| `connection_params` | ERP-specific JSON (SAP: SID/client; D365: tenant_id/data_area; Odoo: database) |

Legacy SAP connections remain in the `sap_connections` table for backward compatibility.

---

## Field Mapping Architecture

All ERPs use the same 3-tier field mapping strategy:

| Tier | Method | Confidence | Priority |
|------|--------|-----------|----------|
| **1 — Exact** | Table-specific field → AWS SC entity | 100% | Highest |
| **2 — Pattern** | Regex on field names | 75% | Medium |
| **3 — Fuzzy/AI** | String similarity + Claude AI | Varies | Lowest |

Implementation files:
- SAP: `backend/app/services/sap_field_mapping_service.py`
- D365: `backend/app/integrations/d365/field_mapping.py`
- Odoo: `backend/app/integrations/odoo/field_mapping.py`

---

## Entity Coverage Comparison

| AWS SC Entity | SAP Tables | D365 Entities | Odoo Models |
|---------------|-----------|--------------|-------------|
| `company` | T001 | LegalEntities | res.company |
| `site` | T001W, T001L | Sites, Warehouses, StorageLocations | stock.warehouse, stock.location |
| `product` | MARA, MAKT, MBEW, MARM, MVKE | ReleasedProductsV2, ProductUnitConversions | product.product, product.template |
| `product_hierarchy` | T179 | ProductCategories | product.category |
| `product_bom` | STKO, STPO, MAST | BillOfMaterialsHeaders/Lines | mrp.bom, mrp.bom.line |
| `production_process` | CRHD, CRCO, PLKO, PLPO, KAKO | WorkCenters, RoutingHeaders/Operations, CapacityData | mrp.workcenter, mrp.routing.workcenter |
| `trading_partner` (vendor) | LFA1, EINA, EINE, EORD | Vendors, VendorPurchasePrices, ApprovedVendorList | res.partner (supplier_rank>0), product.supplierinfo |
| `trading_partner` (customer) | KNA1, KNVV | CustomersV3, CustomerSalesAreas | res.partner (customer_rank>0) |
| `vendor_lead_time` | EINE (APLFZ) | VendorPurchasePrices (LeadTimeDays) | product.supplierinfo (delay) |
| `inv_level` | MARD | InventWarehouseOnHandEntity | stock.quant |
| `inv_policy` | MARC (EISBE, MINBE) | ItemCoverageSettings | stock.warehouse.orderpoint |
| `inbound_order` | EKKO, EKPO, EKET | PurchaseOrderHeaders/Lines/ScheduleLines | purchase.order, purchase.order.line |
| `outbound_order` | VBAK, VBAP, VBEP | SalesOrderHeaders/Lines/DeliverySchedules | sale.order, sale.order.line |
| `production_order` | AFKO, AFPO, AFVC, AFRU, RESB | ProductionOrderHeaders/Items/BOMLines/RouteOps/Confirmations | mrp.production |
| `shipment` | LIKP, LIPS | ShipmentHeaders/Lines | stock.picking, stock.move |
| `forecast` | PBIM, PBED | DemandForecastEntries | (Enterprise only) |
| `planned_order` | PLAF | PlannedOrders | (MRP module) |
| `purchase_requisition` | EBAN | PurchaseRequisitionLines | (not standard) |
| `quality` | QALS, QASE, QMEL | QualityOrders/TestResults/Notifications | (Enterprise only) |
| `equipment` | EQUI | MaintenanceAssets | (Enterprise only) |
| `batch` | MCH1, MCHA | BatchMaster | stock.lot |
| `status_history` | JEST, TJ02T | ObjectStatusHistory | (audit log) |
| `change_documents` | CDHDR, CDPOS | (ModifiedDateTime CDC) | (write_date CDC) |

**SAP**: 54 tables → `sap_staging` schema
**D365**: 42 entities → `d365_staging` schema
**Odoo**: 27 models → `odoo_staging` schema

---

## Implementation Files

### Shared Infrastructure

| File | Purpose |
|------|---------|
| `backend/app/models/erp_connection.py` | Generalized `ERPConnection` model |
| `backend/app/models/erp_registry.py` | ERP vendor/variant registry |
| `backend/app/api/endpoints/erp_integration.py` | Unified `/erp/` API endpoints |
| `frontend/src/pages/admin/ERPDataManagement.jsx` | ERP admin UI |

### SAP Integration

| File | Purpose |
|------|---------|
| `backend/app/models/sap_staging.py` | `sap_staging` schema models + SAP_TABLE_REGISTRY (54 tables) |
| `backend/app/models/sap_connection.py` | Legacy SAP connection model |
| `backend/app/services/sap_deployment_service.py` | Connection management |
| `backend/app/services/sap_field_mapping_service.py` | 3-tier field mapping (400+ field mappings) |
| `backend/app/services/sap_ingestion_monitoring_service.py` | Job monitoring, quality metrics |
| `backend/app/services/sap_data_staging_service.py` | Staging pipeline (extract → map → validate → upsert) |
| `backend/app/services/sap_config_builder.py` | Reverse ETL: staging → SupplyChainConfig |
| `backend/app/integrations/sap/` | Connectors (RFC, OData, HANA, CSV) |
| `backend/scripts/rebuild_sap_config_disaggregated.py` | Config rebuild from SAP CSVs |

### D365 Integration

| File | Purpose |
|------|---------|
| `backend/app/models/d365_staging.py` | `d365_staging` schema models + D365_ENTITY_REGISTRY (42 entities) |
| `backend/app/integrations/d365/connector.py` | OData v4 client + Azure AD OAuth |
| `backend/app/integrations/d365/field_mapping.py` | 3-tier field mapping (21 entity mappings) |
| `backend/app/integrations/d365/extraction_service.py` | 3-phase extraction + D365ConfigBuilder |
| `backend/scripts/extract_d365_contoso.py` | OData extraction from live D365 |
| `backend/scripts/rebuild_d365_contoso_config.py` | Config rebuild from D365 CSVs |
| `backend/scripts/translate_sap_to_d365_csvs.py` | SAP IDES → D365 format translation |

### Odoo Integration

| File | Purpose |
|------|---------|
| `backend/app/models/odoo_staging.py` | `odoo_staging` schema models + ODOO_MODEL_REGISTRY (27 models) |
| `backend/app/integrations/odoo/connector.py` | JSON-RPC/XML-RPC client |
| `backend/app/integrations/odoo/field_mapping.py` | 3-tier field mapping (20 model mappings) |
| `backend/app/integrations/odoo/extraction_service.py` | 3-phase extraction |
| `backend/app/integrations/odoo/config_builder.py` | Reverse ETL: staging → SupplyChainConfig |

---

## Adding a New ERP

To add support for a new ERP (e.g., Oracle NetSuite):

1. **Create staging schema**: `backend/app/models/netsuite_staging.py` with `NETSUITE_MODEL_REGISTRY` (follow `sap_staging.py` pattern)
2. **Create migration**: `CREATE SCHEMA netsuite_staging` with extraction_runs, rows, table_schemas
3. **Create connector**: `backend/app/integrations/netsuite/connector.py` (API client)
4. **Create field mapping**: `backend/app/integrations/netsuite/field_mapping.py` (3-tier mapping)
5. **Create extraction service**: `backend/app/integrations/netsuite/extraction_service.py` (3-phase pipeline)
6. **Create config builder**: Reverse ETL from staging → SupplyChainConfig
7. **Register in `erp_integration.py`**: Add to `/supported-erps`, field mapping routes
8. **Document**: Add ERP-specific section to this guide and create user authorization guide

---

## Appendix A: SAP-Specific Details

See [SAP_INTEGRATION_GUIDE.md](SAP_INTEGRATION_GUIDE.md) for:
- RFC, OData, HANA DB, CSV connection methods
- SAP FAA (IDES) demo environment setup
- Z-table/Z-field handling with AI-powered fuzzy matching

See [SAP User Authorization Guide](../internal/SAP_USER_AUTHORIZATION_GUIDE.md) for:
- RFC user (Communication type C) with S_RFC, S_TABU_NAM
- OData user (Service type S) with S_SERVICE, IWSV
- HANA DB user with SELECT grants
- CSV export user with SE16N access

## Appendix B: D365-Specific Details

See [D365_INTEGRATION_GUIDE.md](D365_INTEGRATION_GUIDE.md) for:
- Azure AD app registration and OAuth 2.0 setup
- OData v4 and DMF export methods
- Contoso USMF demo data contents
- SAP → D365 data translation for demos

See [D365 User Authorization Guide](../internal/D365_USER_AUTHORIZATION_GUIDE.md) for:
- Service account security roles (Entity store reader, Product info, Procurement, etc.)
- Azure AD API permissions (Dynamics ERP > Odata.FullAccess)
- Secret rotation schedule

## Appendix C: Odoo-Specific Details

See [ODOO_INTEGRATION_GUIDE.md](ODOO_INTEGRATION_GUIDE.md) for:
- Docker self-hosted setup with demo data
- JSON-RPC API usage
- Community vs Enterprise module differences

See [Odoo User Authorization Guide](../internal/ODOO_USER_AUTHORIZATION_GUIDE.md) for:
- Access groups (Inventory/Manufacturing/Purchase/Sales User)
- API key management
- Model-level access control (25 models)
- Multi-company configuration
