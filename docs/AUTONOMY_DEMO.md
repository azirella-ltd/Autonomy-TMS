# Autonomy Demo Guide

> Runbook for demonstrating the Autonomy supply chain platform.
> Each section is self-contained: prerequisites, setup, script, and talking points.

---

## Table of Contents

1. [Platform Access](#1-platform-access)
2. [Demo Architecture](#2-demo-architecture)
3. [Demo Path A — CSV Injection (SAP / D365 / Any ERP)](#3-demo-path-a--csv-injection)
4. [Demo Path B — Scenario Event Injection](#4-demo-path-b--scenario-event-injection)
5. [Demo Path C — Odoo Live Integration](#5-demo-path-c--odoo-live-integration)
6. [Demo Path D — Autonomy MCP Server (AI-to-AI)](#6-demo-path-d--autonomy-mcp-server)
7. [ERP-Specific Sections](#7-erp-specific-sections)
8. [Demo Scenarios (Cross-ERP)](#8-demo-scenarios)
9. [Decision Stream Walkthrough](#9-decision-stream-walkthrough)
10. [AIIO Governance Demo](#10-aiio-governance-demo)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Platform Access

| Service | URL | Credentials |
|---------|-----|-------------|
| Frontend | http://localhost:8088 | See below |
| API Docs | http://localhost:8000/docs | — |
| pgAdmin | http://localhost:5050 | admin@autonomy.com / admin |

### Login Accounts

| Role | Email | Password | Tenant |
|------|-------|----------|--------|
| System Admin | systemadmin@autonomy.com | Autonomy@2026 | (none) |
| Food Dist Admin | admin@distdemo.com | Autonomy@2026 | Food Dist (id=3) |
| SAP Demo Admin | admin@sap-demo.com | Autonomy@2026 | SAP Demo (id=20) |
| D365 Demo Admin | admin@d365-demo.com | Autonomy@2026 | D365 Demo |
| Odoo Demo Admin | admin@odoo-demo.com | Autonomy@2026 | Odoo Demo |

### Active Configs

| Tenant | Config ID | Name | Status |
|--------|-----------|------|--------|
| Food Dist | 129 | Distribution Network | Fully provisioned |
| SAP Demo | 150 | Werk 0001 | Master data extracted, needs provisioning |

---

## 2. Demo Architecture

```
                    Demo Entry Points
                    ─────────────────
    ┌──────────┐   ┌──────────────┐   ┌──────────────┐
    │ CSV File │   │ Scenario     │   │ Odoo Live    │
    │ Upload   │   │ Event API    │   │ (JSON-RPC)   │
    └────┬─────┘   └──────┬───────┘   └──────┬───────┘
         │               │                   │
         ▼               ▼                   ▼
    ┌────────────────────────────────────────────────┐
    │              Context Engine                     │
    │    CDC Analysis → Signal Classification         │
    └────────────────────┬───────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │   HiveSignalBus     │
              │   (25 signal types)  │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │   11 TRM Agents     │
              │   (Powell Framework) │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │   Decision Stream   │
              │   (WebSocket + UI)   │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │   ERP Write-back    │
              │   (MCP, adaptive     │
              │    delay, AIIO)      │
              └─────────────────────┘
```

---

## 3. Demo Path A — CSV Injection

**Best for**: SAP, D365, or any ERP where you don't have live access.
Upload a CSV representing an ERP table export → system detects changes →
TRM agents respond → Decision Stream shows results.

### 3.1 Prerequisites

- Autonomy backend running (`make up`)
- A provisioned config (Food Dist config 129 recommended)
- CSV files from `data/sap_faa_backup/Autonomy_SAP_Demo/` or custom

### 3.2 Available Sample Data

The SAP S/4HANA FAA backup provides 39 tables with real data:

| Category | Tables | Key Demo Tables |
|----------|--------|----------------|
| **Demand** | VBAK, VBAP, VBRK, VBRP | VBAK (8K sales orders) |
| **Supply** | EKKO, EKPO, EINA, EINE, EORD | EKKO (purchase orders) |
| **Production** | AFKO, AFPO, PLAF, PLKO, PLPO | AFKO (production orders) |
| **Inventory** | MARD, MBEW, RESB | MARD (stock levels) |
| **Master Data** | MARA, MARC, MAKT, MARM, T001W | MARA (materials) |
| **Logistics** | LIKP, LIPS | LIKP (deliveries) |
| **Quality** | QALS, QMEL | QMEL (quality notifications) |
| **BOM** | STKO, STPO, MAST | STKO (BOM headers) |
| **Partners** | LFA1, KNA1, ADRC | LFA1 (vendors), KNA1 (customers) |

### 3.3 API Usage

**Discover supported tables:**
```bash
curl http://localhost:8088/api/v1/erp/csv-inject/supported-tables
```

**Inject a CSV:**
```bash
# New sales orders (demand signal)
curl -X POST http://localhost:8088/api/v1/erp/csv-inject \
  -F "file=@data/sap_faa_backup/Autonomy_SAP_Demo/VBAK.csv" \
  -F "config_id=129"

# Inventory changes
curl -X POST http://localhost:8088/api/v1/erp/csv-inject \
  -F "file=@data/sap_faa_backup/Autonomy_SAP_Demo/MARD.csv" \
  -F "config_id=129"

# New purchase orders
curl -X POST http://localhost:8088/api/v1/erp/csv-inject \
  -F "file=@data/sap_faa_backup/Autonomy_SAP_Demo/EKKO.csv" \
  -F "config_id=129"
```

**Response:**
```json
{
  "status": "success",
  "correlation_id": "abc-123",
  "table_detected": "VBAK",
  "entity_type": "outbound_order",
  "tier": "transactional",
  "records_parsed": 8175,
  "cdc_summary": {
    "new": 42,
    "changed": 15,
    "deleted": 0,
    "unchanged": 8118
  },
  "signals_emitted": 57,
  "pending_decisions": 3,
  "decisions_preview": [...]
}
```

### 3.4 Demo Script

1. **Setup**: Open Decision Stream in browser (logged in as tenant admin)
2. **Narrate**: "We're going to simulate what happens when SAP processes new sales orders"
3. **Action**: Upload VBAK.csv via curl or API tool
4. **Watch**: Decision Stream shows CDC event → TRM responses appear
5. **Drilldown**: Click a decision → "Ask Why" → show reasoning chain
6. **Override**: Override one decision with a reason → show AIIO governance
7. **Highlight**: "This same pipeline works with any ERP — the CSV is just a transport"

### 3.5 Creating Custom Demo CSVs

To simulate a specific scenario, create a minimal CSV:

**New large sales order (VBAK.csv):**
```csv
VBELN,ERDAT,AUART,KUNNR,NETWR,WAERK,VKORG
9900000001,20260403,TA,CUST001,250000.00,USD,1000
```

**Inventory drop (MARD.csv):**
```csv
MATNR,WERKS,LGORT,LABST,INSME,EINME
MAT-001,1000,0001,50,0,0
```

**Supplier delay (modify EKKO dates):**
```csv
EBELN,BUKRS,LIFNR,BSART,BEDAT,EINDT
4500000001,1000,VENDOR-01,NB,20260403,20260430
```

---

## 4. Demo Path B — Scenario Event Injection

**Best for**: Controlled "what-if" demos. 24 pre-built event types with
parameter selection. No CSV needed — just pick an event and inject.

### 4.1 Event Catalog

**Demand Events (7):**

| Event | Parameters | TRMs Responding |
|-------|-----------|----------------|
| `demand_spike` | product, site, spike_pct (0.1-5.0) | Forecast Adjustment, Inventory Buffer, PO Creation |
| `drop_in_order` | product, site, drop_pct | Forecast Adjustment, Inventory Buffer |
| `forecast_revision` | product, site, revision_pct | Forecast Adjustment |
| `customer_return` | product, site, return_qty | Quality, Inventory Buffer |
| `product_phase_out` | product | Forecast Adjustment, Inventory Buffer |
| `new_product_intro` | product, site | Forecast Adjustment, PO Creation |
| `seasonal_demand_shift` | product, site, shift_factor | Forecast Adjustment |

**Supply Events (6):**

| Event | Parameters | TRMs Responding |
|-------|-----------|----------------|
| `supplier_delay` | vendor, delay_days | PO Creation, Order Tracking |
| `supplier_loss` | vendor | PO Creation, Subcontracting |
| `quality_hold` | product, site, hold_qty | Quality, Inventory Buffer |
| `component_shortage` | product, site | PO Creation, MO Release |
| `price_change` | product, vendor, new_price | PO Creation |
| `product_recall` | product | Quality, Rebalancing |

**Capacity Events (5):**

| Event | Parameters | TRMs Responding |
|-------|-----------|----------------|
| `capacity_loss` | site, reduction_pct | MO Release, Subcontracting |
| `machine_breakdown` | site, resource | Maintenance, MO Release |
| `yield_loss` | product, site, yield_drop | MO Release, Quality |
| `labor_shortage` | site, reduction_pct | MO Release |
| `engineering_change` | product | MO Release, PO Creation |

**Logistics Events (3):**

| Event | Parameters | TRMs Responding |
|-------|-----------|----------------|
| `shipment_delay` | lane, delay_days | Transfer Order, Rebalancing |
| `lane_disruption` | lane | Transfer Order, Rebalancing |
| `warehouse_capacity_constraint` | site | Rebalancing, Transfer Order |

**Macro Events (3):**

| Event | Parameters | TRMs Responding |
|-------|-----------|----------------|
| `tariff_change` | product, pct_change | PO Creation |
| `currency_fluctuation` | currency, pct_change | PO Creation |
| `regulatory_change` | product | Quality |

### 4.2 API Usage

**Browse available events:**
```bash
curl http://localhost:8088/api/v1/scenario-events/catalog
```

**Get parameter dropdowns (products, sites, vendors for a config):**
```bash
curl http://localhost:8088/api/v1/scenario-events/config/129/entities
```

**Inject an event:**
```bash
# Demand spike: 50% increase for a product at a site
curl -X POST http://localhost:8088/api/v1/scenario-events/config/129/inject \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "demand_spike",
    "parameters": {
      "product_id": "FG-ORGANIC-PASTA",
      "site_id": "DC-Northeast",
      "spike_pct": 0.5
    }
  }'

# Supplier loss
curl -X POST http://localhost:8088/api/v1/scenario-events/config/129/inject \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "supplier_loss",
    "parameters": {
      "vendor_id": "VENDOR-GRAINS-01"
    },
    "scenario_name": "What-if: grain supplier bankruptcy"
  }'
```

### 4.3 Demo Script

1. **Open** Decision Stream + scenario events catalog side by side
2. **Narrate**: "Let's see what happens when a key supplier goes down"
3. **Action**: Inject `supplier_loss` event
4. **Watch**: Decision Stream shows scenario event notification
5. **Show**: TRM agents respond — PO Creation agent finds alternate vendor,
   Subcontracting agent evaluates outsourcing, Rebalancing agent shifts inventory
6. **Compare**: Show scenario branch vs baseline in Supply Plan view
7. **Revert**: Revert the event to show it's non-destructive

---

## 5. Demo Path C — Odoo Live Integration

**Best for**: Showing real bidirectional ERP integration. Odoo is the only
ERP with permanent live access.

### 5.1 Prerequisites

**Odoo instance** (Docker, ~5 min setup):
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
EOF

docker compose up -d
```

Open http://localhost:8069, create database with demo data checked.
Install modules: Inventory, Manufacturing, Purchase, Sales.

### 5.2 Connection Setup

1. **Admin → ERP Data Management** → Add Odoo connection
2. Configure: URL=http://odoo:8069, Database=odoo18demo, API Key=(from Odoo)
3. **Test Connection** → should show green
4. **Run Initial Extraction** → bulk load master + transactional data
5. **Run Provisioning** → full 17-step pipeline

### 5.3 Live Demo Flow

```
You (in Odoo)                    Autonomy (Decision Stream)
─────────────                    ─────────────────────────
1. Create a new sales order      →  CDC detects new demand
   (200 units of Table Kit)      →  DEMAND_SURGE signal emitted
                                 →  ATP TRM checks availability
                                 →  Decision: "Allocate 150 units,
                                     backorder 50, PO recommended"

2. Create a quality hold         →  QUALITY_HOLD signal
   (reject 30 units in WH)       →  Quality TRM evaluates disposition
                                 →  Inventory Buffer TRM re-evaluates
                                 →  Decision: "Quarantine, adjust SS"

3. Watch Decision Stream         →  Adaptive delay countdown visible
                                 →  "ERP write-back in 23 min"

4. Override a decision           →  Decision status → OVERRIDDEN
   (change PO quantity)          →  Reason captured for Bayesian learning

5. Let delay expire              →  MCP write-back executes
                                 →  PO created in Odoo automatically
                                 →  Audit trail in mcp_call_log
```

### 5.4 MCP Live Operations (Advanced)

With `mcp-server-odoo` installed:
```bash
pip install mcp-server-odoo
```

Configure MCP polling in Admin → Governance → MCP Connections:
- Transport: STDIO
- Command: `["python", "-m", "mcp_server_odoo"]`
- Poll interval: 60 seconds

Autonomy will poll Odoo every 60 seconds for changes and write back
agent decisions (PO/MO/TO) governed by the AIIO adaptive delay.

---

## 6. Demo Path D — Autonomy MCP Server (AI-to-AI)

**Best for**: Showing Autonomy as a platform that other AI agents can consume.
Any MCP-compatible tool (Claude Code, Copilot, custom agents) can query
Autonomy's supply chain intelligence.

### 6.1 Start the MCP Server

```bash
# STDIO mode (for Claude Code / development)
cd backend
python -m app.mcp_server.server --stdio

# HTTP mode (for network access)
python -m app.mcp_server.server
# → Listening on http://0.0.0.0:8001
```

### 6.2 Available Tools

| Tool | Type | Purpose |
|------|------|---------|
| `get_decision_stream` | Read | Query pending agent decisions |
| `chat_with_decisions` | Read | Natural-language Q&A about decisions |
| `check_availability` | Read | Multi-stage ATP/CTP check |
| `promise_order` | Write | ATP check + pegging chain creation |
| `ask_why` | Read | Explain agent decision reasoning |
| `get_network_status` | Read | DAG topology + active alerts |
| `get_kpi_metrics` | Read | BSC metrics (fill rate, touchless rate) |
| `get_forecast` | Read | Demand forecast with P10/P50/P90 |
| `get_governance_status` | Read | Active policies + directives |
| `override_decision` | Write | Override with mandatory reason |
| `reverse_erp_writeback` | Write | Compensating ERP reversal |

### 6.3 Demo Script — Claude Code

```
You:     "What urgent decisions need attention right now?"
Claude:  → calls get_decision_stream(tenant_id=3, decision_level="execution")
         "There are 5 pending decisions. The most urgent is a PO creation
          for Organic Pasta at DC-Northeast (urgency 0.87)."

You:     "Why does it want to create that PO?"
Claude:  → calls ask_why(tenant_id=3, decision_id=1234, decision_type="po_creation")
         "The agent detected inventory below safety stock (current: 120,
          SS target: 200). Lead time from supplier GRAINS-01 is 5 days.
          Confidence: 0.82. Alternative considered: rebalancing from DC-West
          (rejected: insufficient stock at source)."

You:     "Can we fulfill 500 units of FG-PASTA at DC-Northeast by April 15?"
Claude:  → calls check_availability(tenant_id=3, config_id=129,
            product_id="FG-PASTA", site_id="DC-NE", quantity=500,
            target_date="2026-04-15")
         "CTP check: 380 units feasible by April 15. Binding constraint is
          component availability (flour). Full 500 possible by April 19."

You:     "Override that PO — use supplier GRAINS-02 instead, they're cheaper"
Claude:  → calls override_decision(tenant_id=3, decision_id=1234,
            decision_type="po_creation", action="override",
            reason="Switching to GRAINS-02 for 12% cost savings",
            override_values={"vendor_id": "GRAINS-02"})
         "Decision overridden. Reason recorded for learning."
```

---

## 7. ERP-Specific Sections

### 7.1 SAP S/4HANA

**Live MCP status**: Not available (requires permanent SAP S/4HANA FAA — pending funding).

**Demo approach**: CSV injection using FAA backup data in `data/sap_faa_backup/Autonomy_SAP_Demo/`.

**Sample data available**: 39 SAP tables, 338K total rows. Covers materials (MARA), plants (T001W), BOMs (STKO/STPO), vendors (LFA1), customers (KNA1), POs (EKKO/EKPO), SOs (VBAK/VBAP), production orders (AFKO/AFPO), deliveries (LIKP/LIPS), inventory (MARD), quality (QALS/QMEL).

**MCP servers available** (for when FAA is provisioned):
- `btp-sap-odata-to-mcp-server` — requires SAP BTP
- `hana-mcp-server` — direct HANA connection, no BTP needed
- `odata-mcp-proxy` — zero-code JSON config

**Adapter**: `backend/app/integrations/mcp/adapters/sap_s4.py` — 11 OData entity types, PO/MO/TO write-back.

### 7.2 SAP Business One

**Live access**: Cloudiax demo instance (expires 2026-04-10).
- User: c88888.28 / Autonomy@2026!
- URL: https://sap.cloudiax.com/

**Demo approach**: Limited — B1 lacks the OData APIs that the S/4HANA adapter targets. Use CSV injection with B1-format exports instead.

**MCP servers available**:
- `sap-b1-mcp-server` (npm) — Service Layer, session-based auth, full CRUD

**Adapter**: Not yet implemented. Planned: `backend/app/integrations/mcp/adapters/b1.py`

### 7.3 Microsoft Dynamics 365 F&O

**Live access**: None (requires Azure AD + D365 license).

**Demo approach**: CSV injection. Create D365-style CSVs with column names matching D365 data entities (ReleasedProductsV2, PurchaseOrderHeadersV2, etc.).

**MCP server**: Official Microsoft D365 ERP MCP (GA Feb 2026). Dynamic tool discovery — supports all ERP features + ISV customizations. Requires F&O v10.0.47+.

**Adapter**: `backend/app/integrations/mcp/adapters/d365.py` — 9 entity types, PO/MO/TO write-back.

### 7.4 Odoo

**Live access**: Free permanent access via Docker (see Path C above).

**Demo approach**: Full live integration — the only ERP where we can demo the complete loop: place order in Odoo → Autonomy detects → agent acts → writes back to Odoo.

**MCP server**: `mcp-server-odoo` (PyPI) — full CRUD on any Odoo model.

**Adapter**: `backend/app/integrations/mcp/adapters/odoo.py` — 8 models, write_date-based CDC.

### 7.5 Oracle NetSuite

**Live access**: None (requires NetSuite subscription).

**Demo approach**: CSV injection. NetSuite exports are standard CSV.

**MCP server**: Oracle AI Connector Service (GA March 2026). Official, OAuth 2.0 PKCE.

**Adapter**: Not yet implemented. Planned: `backend/app/integrations/mcp/adapters/netsuite.py`

### 7.6 Infor M3/LN

**Live access**: None.

**Demo approach**: CSV injection.

**MCP server**: None available. Would need custom wrapper around ION API Gateway.

**Adapter**: Not yet implemented.

---

## 8. Demo Scenarios (Cross-ERP)

These scenarios work with any demo path (CSV, scenario events, or Odoo live).

### 8.1 New Large Customer Order (Demand Signal)

**Story**: "A major retailer just placed a rush order for 5,000 units. Watch how the system responds."

**What happens**:
1. Demand signal detected → `DEMAND_SURGE` HiveSignal
2. ATP TRM checks availability → partial fulfillment (3,200 units)
3. PO TRM recommends purchase order for shortfall
4. Rebalancing TRM evaluates cross-DC transfer
5. Forecast Adjustment TRM updates demand baseline
6. Decision Stream shows all actions with countdown timers

**Talking points**: Multi-agent coordination, conformal prediction bounds, AIIO governance, adaptive delay.

### 8.2 Supplier Bankruptcy (Supply Disruption)

**Story**: "Your primary grain supplier just filed for bankruptcy. Every PO in flight is at risk."

**What happens**:
1. Supplier flagged → all open POs from that vendor marked at risk
2. PO TRM identifies alternate vendors with capacity
3. Subcontracting TRM evaluates outsourcing
4. Rebalancing TRM shifts safety stock between DCs
5. S&OP GraphSAGE re-optimizes network allocation

**Talking points**: Cascading decisions, agent-to-agent negotiation (AAP), network-level optimization.

### 8.3 Quality Hold at Distribution Center

**Story**: "Quality inspection failed on a batch at DC-West. 500 units quarantined."

**What happens**:
1. Quality signal → `QUALITY_HOLD` HiveSignal
2. Quality TRM disposition: quarantine, investigate, scrap/rework
3. Inventory Buffer TRM re-evaluates safety stock
4. ATP TRM recalculates availability (reduced)
5. Order Tracking TRM identifies affected customer orders

**Talking points**: Cross-TRM coordination via stigmergic signals, conformal prediction on quality risk.

### 8.4 After-Hours Emergency (Oversight Schedule Demo)

**Story**: "It's 11pm on Friday. A critical stockout is detected. How does the system handle it?"

**What happens**:
1. Urgency 0.92 → exceeds bypass threshold (0.85)
2. Adaptive delay ignores business hours → executes after 5-minute floor
3. On-call user gets `oncall_notification` in Decision Stream
4. Write-back creates emergency PO in ERP
5. Audit trail records after-hours execution + on-call notification

**Talking points**: Business-hours-aware delays, urgent bypass, on-call escalation, SOC II audit.

---

## 9. Decision Stream Walkthrough

The Decision Stream is the primary human interface for AIIO governance.

### What to Show

1. **Decision cards**: Each shows agent type, product, site, urgency, confidence, suggested action
2. **Ask Why**: Click to see full reasoning chain, alternatives, model attribution
3. **Override**: Change the decision with mandatory reason
4. **Countdown timer**: Shows adaptive delay before ERP write-back
5. **CDC events**: Real-time notifications when ERP data changes
6. **Level filtering**: Governance / Strategic / Tactical / Execution

### Key Metrics to Highlight

| Metric | What It Shows | Target |
|--------|--------------|--------|
| Touchless Rate | % of decisions auto-executed without human involvement | 70-85% |
| Override Rate | % of decisions humans changed | 1-3% |
| Override Effectiveness | Did human corrections improve outcomes? (Bayesian) | >50% |
| Fill Rate | Customer orders fulfilled on time and in full | >95% |
| Forecast MAPE | Mean Absolute Percentage Error | <15% |

---

## 10. AIIO Governance Demo

### Governance Pipeline Visualization

Navigate to **Admin → Decision Governance → Pipeline** tab.

Show the four stages:
1. **Planning Envelope**: Adjust existing orders before creating new ones (Glenday Sieve)
2. **Impact Scoring**: 5-dimension composite (financial, scope, reversibility, confidence, override rate)
3. **Mode Assignment**: AUTOMATE / INFORM / INSPECT based on impact thresholds
4. **Guardrail Override**: Executive directives that tighten or relax controls

### Simulate a Decision

Navigate to **Simulate** tab:
- Input: Agent type = Procurement, Impact = $50,000, Confidence = 0.75
- Output: Impact score, dimension breakdown, assigned mode, matching policy

### Oversight Schedule

Navigate to **Oversight Schedule** tab:
- Show weekly operating hours (Mon-Fri 08:00-17:00)
- Show timezone setting
- Show urgent bypass threshold (0.85)
- Explain: "Write-back delays only count down during these hours"

### Write-back Delay Preview

In the **Policy editor**, show the "ERP Write-back Delay" section:
- Adjust urgency/confidence weights
- Watch the **live preview** update in real-time:
  - Urgent + Confident: 5 min
  - Medium: 23 min
  - Low urgency + Uncertain: 69 min

---

## 11. Troubleshooting

| Issue | Solution |
|-------|---------|
| CSV injection returns "Could not detect SAP table" | Provide explicit `table_name` parameter, or rename file to match SAP convention (e.g., VBAK.csv) |
| No decisions appear after injection | Check if config has been provisioned (needs TRM training data) |
| Decision Stream not updating in real-time | Check WebSocket connection (browser console → WS tab) |
| Scenario event injection fails | Verify config_id belongs to your tenant |
| MCP server won't start | Install: `pip install fastmcp mcp` |
| "No MCP config for tenant" on write-back | Configure MCP connection in Admin → ERP Data Management |
| Write-back not executing | Check `mcp_pending_writeback` table — is `eligible_at` in the future? Check business hours. |
