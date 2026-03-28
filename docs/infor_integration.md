# Infor M3 / CloudSuite Integration

Integration with Infor M3, LN, and CloudSuite via the ION API Gateway.

## Overview

| Aspect | Detail |
|--------|--------|
| **ERP** | Infor M3, LN, CloudSuite Industrial/Distribution |
| **Protocol** | REST/JSON via ION API Gateway |
| **Authentication** | OAuth 2.0 (Client Credentials or Resource Owner Password grant) |
| **Data Model** | InforOAGIS (OAGIS standard), ~196 nouns — public XSD schemas |
| **Schema Source** | https://schema.infor.com/InforOAGIS/Nouns/ |
| **SDK** | https://github.com/infor-cloud/ion-api-sdk (Java, C#, Go) |
| **Free Sandbox** | None — partner agreement required |
| **Demo Data** | Synthetic (Midwest Industrial Supply — pumps, valves, actuators) |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     INFOR M3 / CLOUDSUITE                       │
│              ION API Gateway (REST + OAuth 2.0)                 │
│              M3 MI Programs: {MI}/{Transaction}                 │
└─────────────────────────────────────────────────────────────────┘
                             ↓ (extraction)
                    ┌────────────────────┐
                    │  InforConnector     │
                    │  (async client)     │
                    │  OAuth2 + M3 MI API │
                    └────────────────────┘
           ↙              ↓              ↘
    (CSV Fallback)  (ION API Gateway) (Demo Data)
         ↓               ↓               ↓
    CSV/JSON files   30+ entities   generate_infor_demo_data.py
         ↓               ↓               ↓
         └── FieldMapping ────┘
              (3-tier lookup)
                  ↓ (staged)
        ┌─────────────────────┐
        │  infor_staging      │  ← Raw M3 data (intermediate layer)
        │  (PostgreSQL)       │
        │ - extraction_runs   │
        │ - rows (JSONB)      │
        │ - table_schemas     │
        └─────────────────────┘
                  ↓ (reverse ETL)
        ┌─────────────────────┐
        │ InforConfigBuilder  │
        │ - Master build      │ (sites, products, partners, BOMs)
        │ - Inventory build   │ (levels, policies)
        │ - Transaction build │ (POs, SOs, MOs, shipments)
        │ - Enrichments       │ (pricing, groups)
        └─────────────────────┘
                  ↓ (AWS SC data model)
        ┌─────────────────────┐
        │   PUBLIC SCHEMA     │  ← Final SupplyChainConfig
        │  (PostgreSQL)       │
        │ - site              │
        │ - product           │
        │ - product_bom       │
        │ - trading_partner   │
        │ - inv_level/policy  │
        │ - inbound_order     │
        │ - outbound_order    │
        │ - production_order  │
        │ - ... (20+ more)    │
        └─────────────────────┘
```

## Files

| File | Purpose | Lines |
|------|---------|-------|
| `backend/app/integrations/infor/__init__.py` | Module documentation | — |
| `backend/app/integrations/infor/connector.py` | ION API Gateway REST client (OAuth2 + M3 MI) | ~320 |
| `backend/app/integrations/infor/field_mapping.py` | M3 field → AWS SC entity.field mapping | ~260 |
| `backend/app/integrations/infor/config_builder.py` | Staged data → SupplyChainConfig transformer | ~640 |
| `backend/app/models/infor_staging.py` | Entity registry + staging model metadata | ~260 |
| `backend/scripts/generate_infor_demo_data.py` | Synthetic demo data generator | ~660 |

## ION API Gateway

### Authentication

Infor uses OAuth 2.0 exclusively. Credentials are distributed as `.ionapi` files:

```json
{
  "ti": "TENANT_ID",
  "ci": "CLIENT_ID",
  "cs": "CLIENT_SECRET",
  "iu": "https://mingle-ionapi.inforcloudsuite.com",
  "pu": "https://mingle-sso.inforcloudsuite.com:443/TENANT/as/",
  "ot": "token.oauth2"
}
```

The connector loads this file, constructs the token URL, and obtains a bearer token:

```python
connector = InforConnector(InforConnectionConfig(
    ionapi_file="/path/to/credentials.ionapi",
    m3_company="100",
    m3_division="AAA",
))
await connector.authenticate()
```

Tokens are cached and auto-refreshed (default expiry: ~2 hours).

### M3 MI Programs

Primary data extraction uses M3 MI (Machine Interface) programs:

```
GET {base_url}/M3/m3api-rest/v2/execute/{MI_Program}/{Transaction}?{params}
```

Each MI program maps to a business domain:

| MI Program | Domain | Key Transactions |
|-----------|--------|-----------------|
| MMS200MI | Item Master | LstByNumber, GetItmBasic |
| MMS005MI | Warehouses | LstWarehouses, GetWarehouse |
| CRS620MI | Suppliers | LstByNumber, GetBasicData |
| CRS610MI | Customers | LstByNumber, GetBasicData |
| PDS001MI | BOMs | LstMaterials, Get |
| PPS200MI | Purchase Orders | LstByNumber, GetHead, LstLine |
| OIS100MI | Sales Orders | LstByNumber, GetHead, LstLine |
| PMS100MI | Production Orders | LstByNumber, Get, LstMaterial |
| MWS410MI | Deliveries | LstByNumber, GetHead, LstLine |
| MMS235MI | Inventory Balance | LstInvBal, GetInvBal |
| FCS350MI | Forecasts | LstForecast, GetForecast |
| PPS170MI | Planned Orders | LstPlanned, GetPlanned |
| QMS300MI | Quality | LstInspection, GetInspection |
| MOS100MI | Maintenance | LstByNumber, Get |

### M3 Field Names

M3 uses abbreviated field codes (max 6 chars). Key mappings:

| M3 Field | Meaning | AWS SC Field |
|----------|---------|-------------|
| ITNO | Item Number | product.id |
| ITDS | Item Description | product.description |
| WHLO | Warehouse | site.id |
| SUNO | Supplier Number | trading_partner.id (vendor) |
| CUNO | Customer Number | trading_partner.id (customer) |
| PUNO | Purchase Order Number | inbound_order.id |
| ORNO | Order Number (sales) | outbound_order.id |
| MFNO | Manufacturing Order Number | production_order.id |
| ORQA | Order Quantity | various quantity fields |
| DWDT | Delivery Date | various date fields |
| PUSL | PO Status | inbound_order.status |
| ORSL | SO Status | outbound_order.status |
| WHST | MO Status | production_order.status |

### ION BOD Messages

For asynchronous integration, Infor uses BOD (Business Object Document) messages following the OAGIS standard:

- **Verb + Noun** pattern: `SyncItemMaster`, `ProcessPurchaseOrder`, `GetSalesOrder`
- **Verbs**: Process, Sync, Get, Show, Acknowledge, Confirm, Delete
- **XSD schemas**: https://schema.infor.com/InforOAGIS/Nouns/ (~196 nouns)

The connector currently uses M3 MI (synchronous REST) for extraction. BOD support can be added for real-time event-driven sync.

## Entity Mapping

### Master Data (Weekly Refresh)

| Infor Entity | MI Program | AWS SC Entity | ID Pattern |
|-------------|-----------|--------------|------------|
| Warehouse | MMS005MI | Site | `{WHLO}` |
| Supplier | CRS620MI | TradingPartner (vendor) | `INF_V_{SUNO}` |
| Customer | CRS610MI | TradingPartner (customer) | `INF_C_{CUNO}` |
| ItemMaster | MMS200MI | Product | `CFG{config_id}_{ITNO}` |
| BillOfMaterial | PDS001MI | ProductBOM | — |
| ItemWarehouse | MMS002MI | InvPolicy | — |
| PriceList | OIS017MI | Product.unit_price (enrichment) | — |
| WorkCenter | PDS010MI | ProductionProcess | — |
| PurchaseAgreement | PPS100MI | SourcingRules | `INF-AGR-{AGNB}` |

### Transaction Data (Daily Refresh)

| Infor Entity | MI Program | AWS SC Entity | ID Pattern |
|-------------|-----------|--------------|------------|
| PurchaseOrder | PPS200MI | InboundOrder | `INF-PO-{PUNO}` |
| PurchaseOrderLine | PPS200MI | InboundOrderLine | — |
| SalesOrder | OIS100MI | OutboundOrder | `INF-SO-{ORNO}` |
| SalesOrderLine | OIS100MI | OutboundOrderLine | — |
| ProductionOrder | PMS100MI | ProductionOrder | `INF-MO-{MFNO}` |
| Delivery | MWS410MI | Shipment | `INF-SHP-{CONN}` |
| GoodsReceipt | PPS300MI | InboundOrder status update | — |
| TransferOrder | MMS100MI | InboundOrder (TRANSFER) | `INF-TO-{RIDN}` |
| Forecast | FCS350MI | Forecast | — |
| PlannedOrder | PPS170MI | SupplyPlan | — |

### CDC Data (Hourly Refresh)

| Infor Entity | MI Program | AWS SC Entity |
|-------------|-----------|--------------|
| InventoryBalance | MMS235MI | InvLevel |
| InventoryTransaction | MMS080MI | InvLevel (delta) |
| QualityInspection | QMS300MI | QualityOrder |
| MaintenanceOrder | MOS100MI | MaintenanceOrder |
| LotMaster | MMS235MI | Product.external_identifiers |

## Status Mapping

### Purchase Order (PUSL)

| M3 Status | Description | AWS SC Status |
|-----------|------------|--------------|
| 05 | Entered | DRAFT |
| 10 | Printed | DRAFT |
| 15 | Activated | APPROVED |
| 20 | Confirmed | APPROVED |
| 35 | Partially received | PARTIALLY_RECEIVED |
| 45 | Received | RECEIVED |
| 75 | Closed | RECEIVED |
| 85 | Cancelled | CANCELLED |

### Sales Order (ORSL)

| M3 Status | Description | AWS SC Status |
|-----------|------------|--------------|
| 05 | Registered | DRAFT |
| 15 | Order ready | CONFIRMED |
| 33 | Allocated | CONFIRMED |
| 44 | Partially delivered | PARTIALLY_FULFILLED |
| 66 | Invoiced | FULFILLED |
| 77 | Closed | FULFILLED |
| 85 | Cancelled | CANCELLED |

### Production Order (WHST)

| M3 Status | Description | AWS SC Status |
|-----------|------------|--------------|
| 10–30 | Planned/Tentative/Firm | PLANNED |
| 40–60 | Released/Active/Partial | RELEASED |
| 70–80 | Completed/Closed | CLOSED |
| 90 | Cancelled | CANCELLED |

## Demo Data

### Midwest Industrial Supply (Synthetic)

A fictional industrial equipment manufacturer producing pumps, valves, actuators, and control systems — a typical Infor M3 manufacturing vertical.

**Generate:**
```bash
python backend/scripts/generate_infor_demo_data.py /tmp/infor_export
```

**Output:**

| Entity | Records | Description |
|--------|---------|-------------|
| Warehouse | 6 | 2 plants, 2 DCs, raw material store, spare parts |
| Supplier | 8 | Foundries, steel, seals, bearings, motors (US/DE/JP) |
| Customer | 10 | Process industry (Chevron, DuPont, BASF, ADM, etc.) |
| ItemMaster | 57 | 21 FG, 33 RM, 3 labor |
| BillOfMaterial | 76 | 9 product structures (pumps, valves, actuators, control panels) |
| ItemWarehouse | 249 | Planning params per item×warehouse |
| PurchaseOrder | 60 | Headers (+ 196 lines) |
| SalesOrder | 80 | Headers (+ 199 lines) |
| ProductionOrder | 30 | Manufacturing orders |
| Delivery | 40 | Outbound shipments |
| GoodsReceipt | 30 | Inbound receipts |
| TransferOrder | 15 | Inter-warehouse transfers |
| Forecast | 756 | 12-week horizon × 21 FG × 3 sites |
| InventoryBalance | 192 | Current on-hand per item×warehouse |
| **TOTAL** | **2,040** | |

**Product line:**
- Centrifugal pumps (2", 4", 6") — CP-100/200/300
- Positive displacement pumps — PD-100/200
- Submersible pump — SP-100
- Gate/Ball/Butterfly valves (2"–6") — GV/BV/BF series
- Control valves (pneumatic) — CV series
- Pneumatic/Electric actuators — PA/EA series
- Flow/Pressure control panels — FCP/PCP series

**Load into Autonomy (programmatic):**
```python
from app.integrations.infor.config_builder import InforConfigBuilder

builder = InforConfigBuilder(db=session, tenant_id=28)
result = await builder.build_from_csv("/tmp/infor_export")
```

## Demo Tenant Provisioning

The full provisioning pipeline creates two tenants (Production + Learning), loads demo data, and creates users.

**One-command setup:**
```bash
make seed-infor-demo
```

**What it creates:**

| Resource | Production | Learning |
|----------|-----------|----------|
| Tenant | Autonomy Infor Demo | Autonomy Infor Demo (Learning) |
| Slug | `infor-demo` | `infor-learn` |
| Mode | PRODUCTION | LEARNING |
| Industry | industrial_equipment | industrial_equipment |
| Admin | admin@infor-demo.com | admin-learn@infor-demo.com |
| is_demo | true (daily date shift) | true |

**Demo users (Production tenant):**

| Email | Role | Decision Level | Landing Page |
|-------|------|---------------|-------------|
| admin@infor-demo.com | Tenant Admin | DEMO_ALL | Admin Dashboard |
| exec@infor-demo.com | Executive | EXECUTIVE | Executive Dashboard |
| scvp@infor-demo.com | VP Supply Chain | SC_VP | Executive Dashboard |
| sopdir@infor-demo.com | S&OP Director | SOP_DIRECTOR | S&OP Worklist |
| mps@infor-demo.com | MPS Manager | MPS_MANAGER | Insights/Actions |
| atp@infor-demo.com | ATP Analyst | ATP_ANALYST | ATP Worklist |
| rebalancing@infor-demo.com | Rebalancing | REBALANCING_ANALYST | Rebalancing Worklist |
| po@infor-demo.com | PO Analyst | PO_ANALYST | PO Worklist |
| ordertracking@infor-demo.com | Order Tracking | ORDER_TRACKING_ANALYST | Order Tracking |

**Password:** `Autonomy@2026` (all users)

**Manual provisioning steps:**
```bash
# 1. Generate demo data
make generate-infor-demo-data

# 2. Seed tenants + users + load data
make seed-infor-demo

# 3. Trigger full provisioning (16-step pipeline) via UI
#    Login as admin@infor-demo.com → Admin → Provisioning → Run Full
```

**Script:** `backend/scripts/seed_infor_demo.py`

## Comparison: Infor vs SAP B1

| Aspect | SAP B1 | Infor M3 |
|--------|--------|----------|
| API | OData v4 REST (Service Layer) | REST via ION API Gateway + M3 MI |
| Auth | Session cookie (30 min) | OAuth 2.0 Bearer (2 hour) |
| Data Model | OData $metadata (JSON) | OAGIS XSD schemas (~196 nouns) |
| Public Schema | Via Service Layer | schema.infor.com (free) |
| Free Sandbox | Cloudiax FAA | None (partner required) |
| Demo Data | In FAA + generate_b1_demo_data.py | generate_infor_demo_data.py (synthetic) |
| Entity Count | 38 Service Layer entities | 30+ MI programs |
| ID Prefix | `B1-PO-`, `B1V_`, `B1C_` | `INF-PO-`, `INF_V_`, `INF_C_` |
| Integration Complexity | Low (direct REST) | Medium (ION middleware + OAuth) |

## Next Steps

1. **Partner sandbox access** — Apply to Infor Partner Network for live M3 environment
2. **BOD real-time sync** — Add ION Connect BOD listener for event-driven data sync
3. **M3 pagination** — Implement maxrecs/NFTR continuation for large datasets (>10K records)
4. **LN support** — LN uses similar ION Gateway but different API programs
5. **CloudSuite Industry** — Map industry-specific extensions (Food & Beverage, Distribution)
