# MCP ERP Integration — Architecture and Per-ERP Capability Reference

> **Autonomy Platform — Technical Reference**
>
> Model Context Protocol (MCP) as the universal live-operations layer for
> bidirectional ERP communication. Covers architecture, per-ERP capabilities,
> authentication, known limitations, and operational guidance.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Two-Phase Integration Model](#2-two-phase-integration-model)
3. [MCP Client Infrastructure](#3-mcp-client-infrastructure)
4. [SAP S/4HANA](#4-sap-s4hana)
5. [Odoo](#5-odoo)
6. [Microsoft Dynamics 365 F&O](#6-microsoft-dynamics-365-fo)
7. [SAP Business One](#7-sap-business-one)
8. [Oracle NetSuite](#8-oracle-netsuite)
9. [Infor M3/LN](#9-infor-m3ln)
10. [Adaptive Write-back Delay](#10-adaptive-write-back-delay)
11. [Human Oversight Schedule](#11-human-oversight-schedule)
12. [Context Engine — Inbound CDC Routing](#12-context-engine--inbound-cdc-routing)
13. [Write-back Service — Outbound AIIO-Governed](#13-write-back-service--outbound-aiio-governed)
14. [SOC II Compliance](#14-soc-ii-compliance)
15. [Operational Runbook](#15-operational-runbook)
16. [Key Files](#16-key-files)

---

## 1. Architecture Overview

```
                  ┌─────────────────────────────┐
                  │     ERP MCP Servers          │
                  │  (SAP, Odoo, D365, etc.)     │
                  └──────────┬──────────────────┘
                             │ MCP Protocol
                             │ (JSON-RPC 2.0 over SSE/STDIO/HTTP)
                  ┌──────────▼──────────────────┐
                  │   MCPClientSession           │
                  │   (connection pooled per      │
                  │    tenant + ERP)              │
                  └──────────┬──────────────────┘
                   ┌─────────┴─────────┐
                   │                   │
          ┌────────▼───────┐  ┌────────▼───────┐
          │   INBOUND      │  │   OUTBOUND     │
          │   CDC Polling   │  │   Write-back   │
          └────────┬───────┘  └────────┬───────┘
                   │                   │
          ┌────────▼───────┐  ┌────────▼───────┐
          │ DeltaClassifier │  │ Governance     │
          │ (hash-based)    │  │ (AIIO + delay) │
          └────────┬───────┘  └────────┬───────┘
                   │                   │
          ┌────────▼───────┐  ┌────────▼───────┐
          │ ContextEngine   │  │ Oversight Sched│
          │ → HiveSignalBus │  │ (biz hours)    │
          │ → WebSocket     │  │ → pending table│
          │ → Audit log     │  │ → Audit log    │
          └────────────────┘  └────────────────┘
```

---

## 2. Two-Phase Integration Model

| Phase | Mechanism | Purpose | When |
|-------|-----------|---------|------|
| **Provisioning** | Bulk extraction via per-ERP connector (RFC, OData, JSON-RPC, REST) | Initial full load of master + transactional data | One-time tenant onboarding |
| **Live Operations** | MCP (this document) | Ongoing CDC reads + agent write-back | Continuous post-provisioning |

**Why two phases?** MCP servers are tool-oriented (one record or query at a time), not optimized for extracting 50K+ records across 18 entity tiers. The existing extractors handle bulk efficiently. MCP replaces the per-ERP CDC polling implementations with a single protocol.

**Rule**: When adding a new ERP integration, always build both:
1. Traditional extractor (connector + extraction_service + config_builder) for provisioning
2. MCP adapter for live operations (CDC polls + write-back)

---

## 3. MCP Client Infrastructure

### Transport Options

| Transport | How It Works | When to Use |
|-----------|-------------|-------------|
| **SSE** (Server-Sent Events) | HTTP connection to remote MCP server | Production: server hosted separately (BTP, cloud) |
| **STDIO** | Local subprocess (npx, python -m) | Development/testing: server runs as child process |
| **Streamable HTTP** | HTTP POST with streaming response | MCP 2025+ spec: stateless, scalable |
| **HTTP Fallback** | Direct JSON-RPC 2.0 POST | When MCP SDK not installed |

### Connection Pool

`MCPConnectionPool` (singleton `mcp_pool`) maintains one `MCPClientSession` per tenant+ERP. Lazy-connects on first use, auto-reconnects on failure.

### Authentication

Each ERP has different auth requirements, stored encrypted in `mcp_server_config.auth_config_encrypted`:

| ERP | Auth Method | Key Fields |
|-----|-------------|------------|
| SAP S/4HANA | OAuth 2.0 (BTP Destination) or Basic Auth (OData) | base_url, client, user, password |
| Odoo | API token + database | url, database, api_key |
| D365 | OAuth 2.0 (Azure AD) | tenant_id_azure, client_id, client_secret |
| SAP B1 | Session-based (Service Layer) | base_url, company_db, user, password |
| NetSuite | OAuth 2.0 Client Credentials (JWT) | account_id, client_id, client_secret, private_key |
| Infor | OAuth 2.0 (ION API Gateway) | base_url, client_id, client_secret |

### DB Configuration

`mcp_server_config` table (per tenant, RLS-enabled):
- `erp_type`, `transport`, `server_url` / `server_command`
- `auth_config_encrypted` (column-level encryption)
- `server_env` (JSON: env vars for STDIO subprocess)
- `tool_mappings` (JSON: canonical name → actual MCP tool name overrides)
- `poll_interval_seconds` (default 300 = 5 min)
- `enabled`, `is_validated`, `last_poll_at`

---

## 4. SAP S/4HANA

### Available MCP Servers

| Server | Source | Transport | Auth | Capabilities |
|--------|--------|-----------|------|-------------|
| **btp-sap-odata-to-mcp-server** | [GitHub](https://github.com/lemaiwo/btp-sap-odata-to-mcp-server) | SSE (BTP CloudFoundry) | OAuth 2.0 via BTP Destination | Full CRUD on all OData services. Auto-discovers APIs. |
| **odata-mcp-proxy** | SAP Community | SSE / STDIO | Configurable | Zero-code JSON config. Full CRUD. |
| **hana-mcp-server** | [GitHub](https://github.com/HatriGt/hana-mcp-server) | STDIO | Direct HANA creds (SSL) | SQL execution with guardrails. Schema discovery. |
| **CData SAP HANA MCP** | [GitHub](https://github.com/CDataSoftware/sap-hana-mcp-server-by-cdata) | STDIO | JDBC | Read-only (free). Full CRUD via CData Connect AI (paid). |

### Inbound: CDC Entities Polled

| Entity Type | OData Service | Entity Set | Change Detection | Key Field | AWS SC Entity |
|------------|--------------|-----------|-----------------|-----------|--------------|
| Materials | API_PRODUCT_SRV | A_Product | LastChangeDateTime | Product | product |
| Plants | API_PLANT_SRV | A_Plant | — (snapshot) | Plant | site |
| Purchase Orders | API_PURCHASEORDER_PROCESS_SRV | A_PurchaseOrder | LastChangeDateTime | PurchaseOrder | inbound_order |
| Sales Orders | API_SALES_ORDER_SRV | A_SalesOrder | LastChangeDateTime | SalesOrder | outbound_order |
| Production Orders | API_PRODUCTION_ORDER_2_SRV | A_ProductionOrder | LastChangeDateTime | ManufacturingOrder | manufacturing_order |
| Inventory | API_MATERIAL_STOCK_SRV | A_MatlStkInAcctMod | — (snapshot) | Material | inventory_level |
| Inbound Deliveries | API_INBOUND_DELIVERY_SRV;v=0002 | A_InbDeliveryHeader | LastChangeDateTime | DeliveryDocument | shipment |
| Outbound Deliveries | API_OUTBOUND_DELIVERY_SRV;v=0002 | A_OutbDeliveryHeader | LastChangeDateTime | DeliveryDocument | shipment |
| BOMs | API_BILL_OF_MATERIAL_SRV;v=0002 | A_BillOfMaterial | LastChangeDate | BillOfMaterial | product_bom |
| Vendors | API_BUSINESS_PARTNER | A_Supplier | LastChangeDateTime | Supplier | trading_partner |
| Customers | API_BUSINESS_PARTNER | A_Customer | LastChangeDateTime | Customer | trading_partner |

### Outbound: Write-back Operations

| TRM Decision | MCP Tool | SAP OData Entity | SAP Document |
|-------------|----------|-----------------|-------------|
| PO Creation | create_entity → A_PurchaseOrder | API_PURCHASEORDER_PROCESS_SRV | Purchase Order (NB) |
| MO Release | create_entity → A_ProductionOrder | API_PRODUCTION_ORDER_2_SRV | Production Order |
| Stock Transfer | create_entity → A_MaterialDocumentHeader | API_MATERIAL_DOCUMENT_SRV | Material Document (mvt 311) |
| SO Update (ATP) | update_entity → A_SalesOrder | API_SALES_ORDER_SRV | Sales Order confirmation |
| Subcontracting | create_entity → A_PurchaseOrder | API_PURCHASEORDER_PROCESS_SRV | Subcontracting PO (UB) |
| ATP Check | query_entities → A_MatlAvailInfo | API_MATERIAL_AVAILABILITY_INFO_BASIC_SRV | Real-time availability |

### Reversal (Compensating Actions)

| Original | Reversal | SAP Action |
|----------|---------|-----------|
| PO created | PO cancelled | Set PurchaseOrderDeletionCode = "L" |
| Production order | TECO | Set MfgOrderConfirmation = "TECO" |
| Stock transfer (311) | Reverse transfer (312) | Swap Plant/IssuingOrReceivingPlant, GoodsMovementType = "312" |
| SO ATP confirmation | Clear confirmation | ConfdDelivQtyInOrderQtyUnit = "0" |

### Known Limitations

- **BTP dependency**: `btp-sap-odata-to-mcp-server` requires SAP BTP CloudFoundry deployment. For on-premise S/4HANA without BTP, use `hana-mcp-server` or `odata-mcp-proxy`.
- **Rate limits**: SAP OData APIs typically throttle at ~100 requests/second. Use `$top` and `$filter` to minimize calls.
- **Pagination**: OData returns max 1000 records per request. The adapter handles `$top` but does not yet implement `$skiptoken` for >1000 record sets.
- **Z-fields**: Custom SAP fields (Z-tables, Z-fields) are discoverable via the SAP Schema Agent (`schema_profile` on `sap_connections`) but require custom `tool_mappings` in `mcp_server_config`.
- **IDoc/RFC write-back**: Some SAP operations (e.g., goods receipt, quality notifications) are only available via IDoc or RFC, not OData. These are not yet supported via MCP — the existing `plan_writer.py` BAPI path handles them.

### Adapter File

`backend/app/integrations/mcp/adapters/sap_s4.py`

---

## 5. Odoo

### Available MCP Servers

| Server | Source | Transport | Auth | Capabilities |
|--------|--------|-----------|------|-------------|
| **mcp-server-odoo** | [PyPI](https://pypi.org/project/mcp-server-odoo/) / [GitHub](https://github.com/ivnvxd/mcp-server-odoo) | STDIO | API token + DB creds | Full CRUD on any Odoo model. Search, filter, sort. |
| **mcp-odoo** | [GitHub](https://github.com/tuanle96/mcp-odoo) | STDIO | API token | TypeScript alternative. Similar CRUD. |
| **odoo-mcp-improved** | PyPI | STDIO | API token | Enhanced tools for Sales, Purchases, Inventory, Accounting. |
| **Odoo Apps Store modules** | Odoo 17+/18+ | STDIO | Odoo session | Official Odoo modules: mcp_server, eb_mcp_server. |

### MCP Tools Exposed (mcp-server-odoo)

| Tool | Operation | Notes |
|------|-----------|-------|
| `odoo_search_read` | Query any model with domain filters | Primary CDC tool. Supports `write_date` filtering. |
| `odoo_create` | Create record in any model | Used for PO/MO/transfer creation. |
| `odoo_write` | Update existing record | Used for SO confirmation updates. |
| `odoo_unlink` | Delete record | Used for cancellation (where Odoo supports delete). |
| `odoo_execute` | Call any Odoo method | Flexible — can trigger workflows, confirm orders, etc. |

### Inbound: CDC Models Polled

| Odoo Model | Entity Type | Key Field | Change Detection | AWS SC Entity |
|-----------|------------|-----------|-----------------|--------------|
| product.product | materials | id | write_date | product |
| stock.warehouse | plants | id | write_date | site |
| res.partner (supplier_rank > 0) | vendors | id | write_date | trading_partner |
| purchase.order | purchase_orders | id | write_date | inbound_order |
| sale.order | sales_orders | id | write_date | outbound_order |
| mrp.production | production_orders | id | write_date | manufacturing_order |
| stock.picking | deliveries | id | write_date | shipment |
| stock.quant (internal locations) | inventory | id | write_date | inventory_level |

### Outbound: Write-back Operations

| TRM Decision | Odoo Model | MCP Tool | Notes |
|-------------|-----------|----------|-------|
| PO Creation | purchase.order + purchase.order.line | odoo_create (2 calls) | Header first, then lines |
| MO Release | mrp.production | odoo_create | Single call with product/qty/dates |
| Transfer Order | stock.picking + stock.move | odoo_create | Internal transfer with move lines |
| SO Update | sale.order | odoo_write | Update confirmation fields |

### Known Limitations

- **Two-step PO creation**: Odoo requires separate creation of PO header and line items (no deep insert). The adapter handles this with sequential calls.
- **No BOM via write**: BOMs are master data — created during provisioning, not via live write-back.
- **Webhook alternative**: Odoo supports webhooks for real-time CDC (no polling needed). Not yet implemented — would replace the `write_date` polling approach.
- **Community vs Enterprise**: Some manufacturing features (mrp module) require Odoo Enterprise. The adapter assumes Enterprise is available.
- **Rate limits**: Odoo has no formal rate limits, but high-frequency polling can impact performance on smaller instances.

### Adapter File

`backend/app/integrations/mcp/adapters/odoo.py`

---

## 6. Microsoft Dynamics 365 F&O

### Available MCP Servers

| Server | Source | Transport | Auth | Capabilities |
|--------|--------|-----------|------|-------------|
| **Official D365 ERP MCP** | [Microsoft Learn](https://learn.microsoft.com/en-us/dynamics365/fin-ops-core/dev-itpro/copilot/copilot-mcp) | SSE (cloud-hosted) | OAuth 2.0 via Azure AD | Dynamic: all ERP features + ISV customizations. Three tool categories. |
| **Community D365 MCP** | [GitHub](https://github.com/srikanth-paladugula/mcp-dynamics365-server) | STDIO | OAuth 2.0 | Community implementation. Use official version instead. |

### MCP Tool Categories (Official Server)

| Category | Tools | Purpose |
|----------|-------|---------|
| **Form tools** | Interact with D365 forms | UI-level operations (navigate, read form data) |
| **API tools** | Call OData/REST endpoints | Direct API access with full filter/expand support |
| **Data tools** | CRUD (Create, Read, Update, Delete) | Structured data operations on any D365 entity |

**Dynamic server (v2025+)**: The D365 MCP server auto-discovers all available entities including ISV customizations. No static tool list — capabilities scale with the D365 instance.

### Inbound: CDC Entities Polled

| D365 Entity | Entity Type | Key Field | Change Detection | AWS SC Entity |
|------------|------------|-----------|-----------------|--------------|
| ReleasedProductsV2 | materials | ItemNumber | ModifiedDateTime | product |
| OperationalSites | sites | SiteId | ModifiedDateTime | site |
| Warehouses | warehouses | WarehouseId | ModifiedDateTime | site |
| VendorsV2 | vendors | VendorAccountNumber | ModifiedDateTime | trading_partner |
| PurchaseOrderHeadersV2 | purchase_orders | PurchaseOrderNumber | ModifiedDateTime | inbound_order |
| SalesOrderHeadersV2 | sales_orders | SalesOrderNumber | ModifiedDateTime | outbound_order |
| ProductionOrders | production_orders | ProductionOrderNumber | ModifiedDateTime | manufacturing_order |
| TransferOrderHeaders | transfer_orders | TransferOrderNumber | ModifiedDateTime | shipment |
| InventOnHandV2 | inventory | ItemNumber | — (snapshot) | inventory_level |

### Outbound: Write-back Operations

| TRM Decision | MCP Tool | D365 Entity | Key Fields |
|-------------|----------|------------|-----------|
| PO Creation | create_data | PurchaseOrderHeadersV2 | OrderVendorAccountNumber, dataAreaId |
| MO Release | create_data | ProductionOrders | ItemNumber, ScheduledQuantity, ProductionSiteId |
| Transfer Order | create_data | TransferOrderHeaders | SendingWarehouseId, ReceivingWarehouseId |
| SO Update | update_data | SalesOrderHeadersV2 | Confirmation fields |

### Known Limitations

- **Prerequisites**: Requires Finance & Operations v10.0.47 or later.
- **Azure AD registration**: MCP server requires Azure AD app registration with appropriate D365 permissions.
- **dataAreaId**: All operations require explicit `dataAreaId` (legal entity). Must be stored in MCP config.
- **Change tracking**: D365 supports native change tracking (`GET /data/EntityName?$filter=ModifiedDateTime gt ...`). More efficient than hash-based delta, but requires enabling change tracking per entity in D365 admin.
- **Throttling**: D365 OData has priority-based throttling. High-volume CDC polling during peak ERP usage may be deprioritized. Use off-peak scheduling or increase poll interval.

### Adapter File

`backend/app/integrations/mcp/adapters/d365.py`

---

## 7. SAP Business One

### Available MCP Servers

| Server | Source | Transport | Auth | Capabilities |
|--------|--------|-----------|------|-------------|
| **sap-b1-mcp-server** | [npm](https://www.npmjs.com/package/sap-b1-mcp-server) | STDIO / HTTP / SSE | Session-based (Service Layer) | Full CRUD. Auto-session renewal. Business partners, orders, inventory. |
| **CompuTec AppEngine MCP** | [CompuTec](https://learn.computec.one/docs/appengine/administrators-guide/configuration-and-administration/mcp-server-for-sap-business-one/) | SSE | B1 Authorizations | Modification commands with permission control. SAP partner solution. |
| **CData SAP B1 MCP** | [GitHub](https://github.com/CDataSoftware/sap-business-one-mcp-server-by-cdata) | STDIO | JDBC | Read-only (free). Full CRUD via CData Connect AI (paid). |

### Capabilities

| Capability | Status | Notes |
|-----------|--------|-------|
| **Read: Items** | Supported | Via Service Layer Items entity |
| **Read: Business Partners** | Supported | Vendors + customers |
| **Read: Purchase Orders** | Supported | Headers + lines |
| **Read: Sales Orders** | Supported | Headers + lines |
| **Read: Production Orders** | Supported | Manufacturing module required |
| **Read: Inventory** | Supported | Via InventoryGenEntries or stock queries |
| **Write: Purchase Orders** | Supported | Create + update |
| **Write: Production Orders** | Limited | Depends on B1 manufacturing license |
| **Write: Inventory Transfer** | Supported | StockTransfers entity |
| **CDC: Change detection** | Via UpdateDate field | Session-based polling |

### Known Limitations

- **Session management**: B1 Service Layer sessions expire after 30 minutes of inactivity. The `sap-b1-mcp-server` handles auto-renewal.
- **No BOM deep insert**: BOMs must be created component-by-component.
- **Manufacturing module**: Production orders require the SAP B1 Manufacturing module (not included in base license).
- **Smaller scale**: B1 is designed for <500 concurrent users. CDC polling interval should be conservative (5+ minutes).

### Adapter File

Not yet implemented. Planned: `backend/app/integrations/mcp/adapters/b1.py`

---

## 8. Oracle NetSuite

### Available MCP Servers

| Server | Source | Transport | Auth | Capabilities |
|--------|--------|-----------|------|-------------|
| **Oracle AI Connector Service** | [Oracle](https://www.netsuite.com/portal/products/artificial-intelligence-ai/mcp-server.shtml) | SSE | OAuth 2.0 PKCE | Official. Full CRUD. GA March 2026. |
| **dsvantien/netsuite-mcp-server** | [GitHub](https://github.com/dsvantien/netsuite-mcp-server) | STDIO | OAuth 2.0 PKCE | Listed on official MCP servers repo. |
| **ChatFin-Labs/netsuite-mcp** | [GitHub](https://github.com/ChatFin-Labs/netsuite-mcp) | STDIO / HTTP | OAuth 2.0 | Comprehensive: RESTlets, SuiteQL, financial data. |
| **CData NetSuite MCP** | CData | STDIO | JDBC | Read-only (free). |

### Key Supply Chain Entities

| NetSuite Record | REST Endpoint | AWS SC Entity | CRUD |
|----------------|--------------|--------------|------|
| inventoryitem | /record/v1/inventoryitem | product | Full |
| location | /record/v1/location | site | Full |
| vendor | /record/v1/vendor | trading_partner | Full |
| customer | /record/v1/customer | trading_partner | Full |
| purchaseOrder | /record/v1/purchaseOrder | inbound_order | Full |
| salesorder | /record/v1/salesorder | outbound_order | Full |
| workOrder | /record/v1/workorder | manufacturing_order | Full |
| transferOrder | /record/v1/transferorder | shipment | Full |
| bom | /record/v1/bom | product_bom | Full |

### Key Differentiators

- **SuiteQL**: SQL-like bulk query endpoint (`POST /query/v1/suiteql`). Ideal for CDC — single query can return all changed records across entity types.
- **SOAP deprecated**: SOAP endpoints no longer provided as of 2026.1 release. All new integrations must use REST + OAuth 2.0.
- **Rate limits**: 15 concurrent requests/account (default). Up to 55 with SuiteCloud Plus license.
- **Pagination**: Max 1,000 records per request via `limit`/`offset`.

### Known Limitations

- **No official Python SDK**: Use `requests` with custom OAuth 2.0 client (JWT assertion flow).
- **Multi-subsidiary complexity**: NetSuite OneWorld uses subsidiary hierarchy. Location-to-subsidiary mapping needed for site resolution.
- **Token TTL**: OAuth 2.0 access tokens expire after 60 minutes. Client must handle refresh.

### Adapter File

Not yet implemented. Planned: `backend/app/integrations/mcp/adapters/netsuite.py`

---

## 9. Infor M3/LN

### Available MCP Servers

**No dedicated MCP server exists for Infor.** Integration options:

| Approach | Mechanism | Effort |
|----------|-----------|--------|
| **Custom ION API wrapper** | Build MCP server around Infor ION API Gateway REST endpoints | Medium |
| **OData-to-MCP proxy** | Use generic `odata-mcp-proxy` with Infor OData endpoints (if available) | Low |
| **CData Infor MCP** | CData provides JDBC-based read-only access | Low (read-only) |

### Current Status

Infor integration uses direct REST/OData calls via `backend/app/integrations/infor/connector.py`. Live MCP operations are **not yet available** for Infor. The existing bulk extractor handles provisioning.

### Adapter File

Not yet implemented. Blocked on MCP server availability.

---

## 10. Adaptive Write-back Delay

Every agent decision gets an adaptive cooling period before ERP write-back, regardless of AIIO mode. See [AGENT_GUARDRAILS_AND_AIIO.md Section 16.4](AGENT_GUARDRAILS_AND_AIIO.md#164-adaptive-write-back-delay) for the formula and examples.

**Per-policy settings** (on `DecisionGovernancePolicy`):

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `writeback_enabled` | bool | true | Enable/disable write-back for this action type |
| `writeback_base_delay_minutes` | int | 30 | Base delay |
| `writeback_min_delay_minutes` | int | 5 | Floor (even urgent+confident waits this long) |
| `writeback_max_delay_minutes` | int | 480 | Ceiling (8 hours) |
| `writeback_urgency_weight` | float | 1.0 | How much urgency reduces delay (0=ignore, 2=double effect) |
| `writeback_confidence_weight` | float | 1.0 | How much confidence reduces delay |

**Configured in**: Governance admin → Policies tab → policy editor → "ERP Write-back Delay" section.

---

## 11. Human Oversight Schedule

Write-back delay countdown only ticks during business hours. See [AGENT_GUARDRAILS_AND_AIIO.md Section 16.5](AGENT_GUARDRAILS_AND_AIIO.md#165-business-hours-aware-delay-human-oversight).

**Three tables**:
- `tenant_operating_schedule` — weekly hours per day-of-week
- `tenant_holiday_calendar` — non-operating dates
- `tenant_oversight_config` — timezone, urgent bypass, on-call

**Configured in**: Governance admin → Oversight Schedule tab.

---

## 12. Context Engine — Inbound CDC Routing

The Context Engine (`context_engine.py`) is the single router for all inbound ERP data:

1. **Receives** raw MCP poll results from any adapter
2. **Classifies** changes via `DeltaClassifier` (hash comparison against `mcp_delta_state` table)
3. **Maps** ERP entity changes → `HiveSignalType` signals
4. **Emits** signals to all site `HiveSignalBus` instances for TRM consumption
5. **Broadcasts** CDC summary to Decision Stream via WebSocket
6. **Logs** to `audit.mcp_call_log` with correlation_id

### Signal Mapping (ERP Change → HiveSignal)

| AWS SC Entity | Change Type | HiveSignalType | Caste |
|--------------|------------|---------------|-------|
| outbound_order | new | DEMAND_SURGE | Scout |
| outbound_order | changed | ORDER_EXCEPTION | Scout |
| outbound_order | deleted | DEMAND_DROP | Scout |
| inbound_order | new/changed | PO_EXPEDITE | Forager |
| inbound_order | deleted | PO_DEFERRED | Forager |
| manufacturing_order | new | MO_RELEASED | Builder |
| manufacturing_order | changed | MO_DELAYED | Builder |
| shipment | new | TO_RELEASED | Builder |
| shipment | changed | TO_DELAYED | Builder |
| inventory_level | changed | BUFFER_DECREASED | Nurse |
| product/product_bom/site | changed | ALLOCATION_REFRESH | tGNN |

### Urgency Computation

Signals have urgency (0-1) computed from entity type + change type + volume:
- Demand-side changes: base 0.7
- Supply-side changes: base 0.5
- Master data changes: base 0.3
- Deletions (cancellations): +0.2 boost
- Volume boost: min(count/100, 0.2)

---

## 13. Write-back Service — Outbound AIIO-Governed

The `MCPWritebackService` handles the full outbound lifecycle:

1. **Receive** TRM decision (decision_id, type, data, urgency, confidence)
2. **Check AIIO mode** — OVERRIDE skips write-back entirely
3. **Compute adaptive delay** via `DecisionGovernanceService.compute_writeback_delay()`
4. **Compute eligible_at** via `OversightScheduleService` (business-hours-aware)
5. **Schedule** in `mcp_pending_writeback` table with `eligible_at`
6. **Broadcast** countdown to Decision Stream
7. **Notify on-call** if outside business hours + urgent
8. **Wait** for delay to expire (or human override)
9. **Execute** via MCP tool call when `eligible_at` passes
10. **Audit** log the result + update decision record with ERP reference

### Pending Write-back States

| Status | Meaning | Transition |
|--------|---------|-----------|
| `scheduled` | Waiting for eligible_at to pass | → executed, cancelled, failed |
| `executed` | Successfully written to ERP | → reversed (if human overrides post-execution) |
| `cancelled` | Human overrode during delay | Terminal |
| `failed` | MCP tool call failed | May retry |
| `reversed` | Post-execution compensating action issued | Terminal |

### Post-Execution Reversal

`reverse_writeback()` creates a compensating ERP document:
- Loads original payload from `mcp_pending_writeback`
- Builds reversal payload (swap from/to, set deletion flag, etc.)
- Executes via MCP
- Updates original status to `reversed`
- Updates powell decision status to `OVERRIDDEN`
- Requires mandatory reason (feeds Bayesian learning)
- Audited with `tool_name = "REVERSAL:<original_tool>"`

---

## 14. SOC II Compliance

| Requirement | Implementation |
|------------|---------------|
| **Audit trail** | `audit.mcp_call_log` — every MCP call logged with direction, tool, hash, duration, correlation_id |
| **Tenant isolation** | RLS on `mcp_server_config`, `mcp_pending_writeback`, all schedule tables |
| **Credential security** | `auth_config_encrypted` column-level encryption |
| **No PII in audit** | Arguments stored as SHA-256 hash + key-only summary, not raw values |
| **Decision tracing** | `correlation_id` chains: CDC event → HiveSignal → TRM decision → write-back → reversal |
| **Change management** | All schema changes via Alembic migrations, not direct SQL |

---

## 15. Operational Runbook

### Adding MCP for a New Tenant

1. **Admin → Governance → Oversight Schedule**: Set timezone, business hours, holidays
2. **Admin → ERP Data Management → MCP Connections** (planned): Configure server URL, auth, enable polling
3. **Run initial provisioning** first (bulk extraction) — MCP is for live ops only
4. **Enable MCP polling**: Set `enabled = true` on `mcp_server_config`
5. **Monitor**: Check `audit.mcp_call_log` for errors, `mcp_pending_writeback` for scheduled items

### Troubleshooting

| Symptom | Check |
|---------|-------|
| No CDC events | `mcp_server_config.last_poll_at` — is polling running? Check `enabled` flag. |
| Write-backs not executing | `mcp_pending_writeback` — check `eligible_at` vs current time. Business hours? |
| MCP connection failures | `audit.mcp_call_log` with `status='error'` — check auth, server URL, network |
| Write-back delayed too long | Check governance policy `writeback_max_delay_minutes`. Check holiday calendar. |
| On-call not notified | Check `tenant_oversight_config.oncall_enabled` and `oncall_user_id` |

### Scheduler Jobs

| Job | Frequency | Purpose |
|-----|-----------|---------|
| `mcp_poll_{tenant}_{erp}` | Per `poll_interval_seconds` (default 5 min) | CDC polling |
| `process_pending_writebacks` | Every 1 minute | Execute eligible write-backs |

---

## 16. Key Files

| File | Purpose |
|------|---------|
| `integrations/mcp/__init__.py` | Package docstring |
| `integrations/mcp/client.py` | MCPClientSession, MCPConnectionPool |
| `integrations/mcp/config.py` | MCPServerConfig model, query helpers |
| `integrations/mcp/audit.py` | MCPCallLog model, MCPAuditLogger |
| `integrations/mcp/context_engine.py` | ContextEngine, DeltaClassifier |
| `integrations/mcp/writeback_service.py` | MCPWritebackService, reverse_writeback, process_pending_writebacks, notify_oncall_if_needed |
| `integrations/mcp/scheduler.py` | APScheduler integration (execute_mcp_poll, register_mcp_jobs) |
| `integrations/mcp/adapters/sap_s4.py` | SAP S/4HANA OData adapter |
| `integrations/mcp/adapters/odoo.py` | Odoo adapter |
| `integrations/mcp/adapters/d365.py` | D365 F&O adapter |
| `models/operating_schedule.py` | TenantOperatingSchedule, TenantHolidayCalendar, TenantOversightConfig |
| `models/decision_governance.py` | DecisionGovernancePolicy (writeback_* fields) |
| `services/oversight_schedule_service.py` | Business-hours-aware compute_eligible_at() |
| `services/decision_governance_service.py` | compute_writeback_delay(), compute_writeback_eligible_at() |
| `migrations/versions/20260403_mcp_infrastructure.py` | MCP tables |
| `migrations/versions/20260403_adaptive_writeback_delay.py` | Writeback delay columns |
| `migrations/versions/20260403_operating_schedule.py` | Operating schedule tables |
