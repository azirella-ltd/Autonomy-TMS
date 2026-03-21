# ODOO-FORK.md — Complete Conversion Analysis

**Date**: 2026-03-21
**Author**: Architecture Team
**Status**: Investigation / Decision Brief
**Scope**: Full fork of Autonomy Platform into native Odoo modules, replacing the AWS SC data model with Odoo's native data model, adopting OWL frontend framework, and complying with Odoo design language and module conventions.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [What "Native Odoo" Means](#2-what-native-odoo-means)
3. [Current Platform Scope](#3-current-platform-scope)
4. [Data Model Conversion: AWS SC → Odoo Native](#4-data-model-conversion-aws-sc--odoo-native)
5. [Backend Conversion: FastAPI → Odoo Modules](#5-backend-conversion-fastapi--odoo-modules)
6. [Frontend Conversion: React/MUI → OWL/Odoo UI](#6-frontend-conversion-reactmui--owlodoo-ui)
7. [AI/ML Architecture Under Odoo](#7-aiml-architecture-under-odoo)
8. [Security & SOC II Compliance](#8-security--soc-ii-compliance)
9. [What Gets Lost](#9-what-gets-lost)
10. [What Gets Gained](#10-what-gets-gained)
11. [Module-by-Module Conversion Map](#11-module-by-module-conversion-map)
12. [Deployment Architecture](#12-deployment-architecture)
13. [Deploying on Odoo Cloud (Odoo.sh)](#13-deploying-on-odoo-cloud-odoosh)
14. [Effort Estimation](#14-effort-estimation)
15. [Risk Assessment](#15-risk-assessment)
16. [Alternative: Hybrid Architecture](#16-alternative-hybrid-architecture)
17. [Recommendation](#17-recommendation)

---

## 1. Executive Summary

This document evaluates the effort, risk, and trade-offs of forking the Autonomy Platform into a **fully native Odoo solution** — meaning Odoo's data model replaces the AWS SC data model, Odoo's OWL framework replaces React, Odoo's ORM replaces SQLAlchemy, and the application adopts Odoo's visual design language, module conventions, and extension patterns.

**Bottom line**: The conversion is technically feasible but represents a near-complete rewrite. The current Autonomy codebase (~522K lines across 1,070 files) shares almost zero reusable code with an Odoo module architecture. The AI/ML layer (PyTorch TRMs, GNNs, Monte Carlo simulation) cannot run inside Odoo workers and must remain as external microservices regardless — meaning the "native Odoo" framing applies only to the data layer and UI, while the intelligence layer stays decoupled.

**Key numbers**:

| Metric | Current Platform | Odoo Fork Estimate |
|--------|-----------------|-------------------|
| Backend code | 348K lines (Python/FastAPI) | ~120K lines (Odoo modules) + ~80K lines (AI microservices) |
| Frontend code | 174K lines (React/MUI) | ~90K lines (OWL/XML) |
| Database tables | 322 (AWS SC + Powell) | ~180 (Odoo native + extensions) |
| Data model | AWS SC (35 entities) | Odoo native (27 models) + extensions |
| Reusable from current codebase | — | ~15% (AI/ML algorithms, math, some service logic) |
| Estimated calendar time | — | 18–24 months (8-person team) |

---

## 2. What "Native Odoo" Means

A native Odoo module must comply with these architectural constraints:

### 2.1 Module Structure

```
autonomy_planning/
  __init__.py
  __manifest__.py          # Dependencies, version, data files, assets
  models/                  # Python classes inheriting odoo.models.Model
    __init__.py
    demand_forecast.py     # Fields auto-create PostgreSQL columns
    supply_plan.py
    inventory_policy.py
  views/                   # XML view definitions (form, list, kanban, Gantt)
    demand_forecast_views.xml
    supply_plan_views.xml
    menus.xml
  controllers/             # HTTP route handlers (optional, for custom pages)
  security/
    ir.model.access.csv    # Model-level ACL (CRUD per group)
    security.xml           # Record rules (row-level domain filters)
  data/                    # Default/demo data loaded on install
  static/
    src/
      js/                  # OWL components
      xml/                 # QWeb templates
      scss/                # Styles (Odoo Bootstrap theme)
  wizard/                  # Transient models for multi-step flows
  report/                  # QWeb PDF/HTML reports
```

### 2.2 Odoo ORM (Replaces SQLAlchemy)

```python
from odoo import models, fields, api

class DemandForecast(models.Model):
    _name = 'autonomy.demand.forecast'
    _description = 'Demand Forecast'
    _inherit = ['mail.thread']  # Adds chatter (audit trail)

    product_id = fields.Many2one('product.product', required=True)
    warehouse_id = fields.Many2one('stock.warehouse', required=True)
    forecast_date = fields.Date(required=True)
    quantity_p10 = fields.Float('P10 Quantity')
    quantity_p50 = fields.Float('P50 Quantity')
    quantity_p90 = fields.Float('P90 Quantity')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('approved', 'Approved'),
    ], default='draft', tracking=True)

    @api.depends('quantity_p50', 'product_id.standard_price')
    def _compute_forecast_value(self):
        for rec in self:
            rec.forecast_value = rec.quantity_p50 * rec.product_id.standard_price
```

**Key differences from SQLAlchemy**:
- No raw SQL (ORM-only for security)
- No async/await (fully synchronous)
- Computed fields are Python methods, not DB-level
- Relationships via `Many2one`, `One2many`, `Many2many` (no explicit FK declarations)
- Record rules replace PostgreSQL RLS
- No `session.commit()` — auto-commit per RPC call (or `cr.savepoint()` for manual control)

### 2.3 Odoo Frontend (Replaces React)

**OWL 2.x** — Odoo's in-house component framework:

```javascript
/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

class DemandForecastDashboard extends Component {
    setup() {
        this.state = useState({ forecasts: [], loading: true });
        this.orm = this.env.services.orm;
    }
    async willStart() {
        this.state.forecasts = await this.orm.searchRead(
            'autonomy.demand.forecast',
            [['state', '=', 'confirmed']],
            ['product_id', 'quantity_p50', 'forecast_date']
        );
        this.state.loading = false;
    }
}
DemandForecastDashboard.template = "autonomy_planning.DemandForecastDashboard";
registry.category("actions").add("autonomy_demand_dashboard", DemandForecastDashboard);
```

```xml
<!-- views/demand_forecast_dashboard.xml -->
<templates>
  <t t-name="autonomy_planning.DemandForecastDashboard">
    <div class="o_action">
      <t t-if="state.loading">
        <div class="o_loading">Loading forecasts...</div>
      </t>
      <t t-else="">
        <table class="table table-sm">
          <t t-foreach="state.forecasts" t-as="fc" t-key="fc.id">
            <tr>
              <td t-esc="fc.product_id[1]"/>
              <td t-esc="fc.quantity_p50"/>
            </tr>
          </t>
        </table>
      </t>
    </div>
  </t>
</templates>
```

**What this means**: No JSX, no Material-UI, no Recharts, no D3. All UI must be OWL components with XML templates, using Odoo's Bootstrap-based design system.

### 2.4 Odoo Design Language

Odoo enforces a consistent visual identity:
- **Bootstrap 5** base with Odoo's custom theme (not MUI)
- **Standard views**: Form, List/Tree, Kanban, Calendar, Gantt, Pivot, Graph, Map, Cohort
- **Action menus**: Top-level app → sub-menus → views (not React Router)
- **Chatter**: Built-in audit trail on every model (`mail.thread` mixin)
- **Breadcrumb navigation**: Automatic from action stack
- **No custom page layouts**: Must use Odoo's action/view system
- **Color palette**: Odoo purple (#714B67), standard Bootstrap variants
- **Font**: Odoo's custom Inter-based system font

---

## 3. Current Platform Scope

### 3.1 Code Volume

| Component | Files | Lines of Code |
|-----------|-------|---------------|
| Backend Python (FastAPI) | 714 | 348,442 |
| Frontend React (JSX) | 356 | 173,906 |
| Database migrations (Alembic) | 177 | 21,783 |
| Docker/Infrastructure | 12 | ~2,000 |
| Documentation | 419 | ~50,000 |
| **Total** | **~1,678** | **~596,131** |

### 3.2 Feature Surface Area

| Domain | Current Implementation |
|--------|----------------------|
| **AWS SC Entities** | 35 entity types, 100% compliance |
| **Planning** | MPS, MRP, S&OP, demand, supply, inventory (8 policy types), capacity |
| **Execution** | 11 TRM worklists (ATP, PO, MO, TO, Quality, Maintenance, Rebalancing, Buffer, Forecast Adj, Order Tracking, Subcontracting) |
| **AI Agents** | 11 TRM types, Site tGNN, Network tGNN, S&OP GraphSAGE, LLM multi-agent |
| **Simulation** | SimPy digital twin, Beer Game, Monte Carlo (1000+ scenarios) |
| **Causal AI** | Counterfactual, propensity matching, Bayesian posteriors |
| **Conformal Prediction** | 8 inventory policies, CDT on all decisions, CRPS evaluation |
| **ERP Integration** | SAP (54 tables), D365 (42 entities), Odoo (27 models) |
| **UI Pages** | 96+ pages (planning, admin, execution, simulation, analytics) |
| **Real-Time** | WebSocket (scenario, decision stream, collaborative planning) |
| **Database** | 322 tables, pgvector, pgaudit, RLS |

---

## 4. Data Model Conversion: AWS SC → Odoo Native

This is the most consequential architectural change. The AWS SC data model is the foundation of the entire platform — every service, every query, every AI feature references it.

### 4.1 Entity Mapping: AWS SC → Odoo Native

| AWS SC Entity | Odoo Native Model | Conversion Notes |
|---------------|-------------------|------------------|
| `site` | `stock.warehouse` + `stock.location` | Odoo uses hierarchical locations within warehouses. No `master_type` field — must infer from usage patterns or add extension field |
| `product` | `product.product` (variant) + `product.template` | Odoo splits header/variant. `unit_cost` → `standard_price`. No `safety_stock` field on product |
| `product_bom` | `mrp.bom` + `mrp.bom.line` | Good alignment. Odoo adds `type` (normal/phantom/subcontracting) |
| `transportation_lane` | `stock.route` + `stock.rule` | Fundamentally different. Odoo uses pull/push rules, not explicit lane entities. No `supply_lead_time` on lanes |
| `forecast` | **No native equivalent** | Odoo has no forecast entity. Must create `autonomy.forecast` extension model |
| `supply_plan` | `stock.picking` + `purchase.order` + `mrp.production` | Odoo splits by transaction type. No unified supply plan concept |
| `inv_policy` | `stock.warehouse.orderpoint` | Odoo: min/max reorder point only. No service level, no conformal, no DOC-based policies |
| `inv_level` | `stock.quant` | Location-level quantity. No `on_order_qty`, no `in_transit_qty` — must compute |
| `sourcing_rules` | `stock.rule` + vendor pricelists | Odoo uses route-based rules, not explicit sourcing priority tables |
| `vendor_product` | `product.supplierinfo` | Good alignment for vendor-product attributes |
| `vendor_lead_time` | `product.supplierinfo.delay` | Single field, not a separate entity |
| `production_process` | `mrp.routing.workcenter` | Odoo uses routing lines on BOMs |
| `trading_partner` | `res.partner` | Odoo's unified partner model (customer + vendor + contact in one table) |
| `customer_cost` | **No native equivalent** | Must create extension |
| `outbound_order_line` | `sale.order.line` | Good alignment |
| `inbound_order_line` | `purchase.order.line` | Good alignment |
| `shipment` | `stock.picking` | Odoo's unified transfer model |
| `fulfillment_order` | `sale.order` → `stock.picking` | Generated from SO confirmation |

### 4.2 Models with No Odoo Equivalent (Must Create as Extensions)

These AWS SC / Autonomy-specific models have **no Odoo counterpart** and must be created as custom models:

| Model Category | Count | Examples |
|----------------|-------|---------|
| **Planning** | 8 | `forecast`, `supply_plan` (unified), `supply_planning_parameters`, `supply_demand_pegging`, `aatp_consumption_record`, `planning_decision`, `planning_commit`, `planning_hierarchy_config` |
| **Powell Framework** | 27 | All `powell_*` tables (allocations, 11 decision tables, policy parameters, belief state, CDC triggers, calibration log, etc.) |
| **AI/ML** | 12 | `site_agent_configs`, `decision_embeddings`, `hive_signal_bus_states`, `gnn_directive_reviews`, `trm_checkpoints`, etc. |
| **Simulation** | 5 | `scenarios`, `scenario_users`, `scenario_user_periods`, `agent_configs`, `agent_scenario_configs` |
| **Causal AI** | 3 | `override_effectiveness_posteriors`, `override_causal_match_pairs`, `escalation_log` |
| **Platform** | 15 | `user_directives`, `config_provisioning_status`, `email_signals`, `email_connections`, `kb_documents`, `kb_chunks`, `sop_worklist_items`, etc. |
| **Total** | **~70** | Custom Odoo models with no native mapping |

**Impact**: ~70 of the platform's ~322 tables have no Odoo equivalent. These must be created as extension models under the `autonomy.*` namespace, following Odoo's ORM conventions but providing no benefit from Odoo's built-in functionality.

### 4.3 Data Model Implications

**What changes fundamentally**:

1. **No explicit DAG topology**: Odoo has no `transportation_lane` entity or DAG concept. Supply chain topology is implicit in route rules + warehouse locations. The entire DAG engine (`supply_chain_config_service.py`, Sankey visualizations, topology validation) must be reimagined using Odoo's route/rule system or maintained as a parallel model.

2. **No unified supply plan**: Odoo generates POs, MOs, and internal transfers as separate entities. The concept of a unified `supply_plan` with approval workflow doesn't exist. Each document type has its own lifecycle.

3. **Inventory policies limited to min/max**: Odoo's `stock.warehouse.orderpoint` supports only minimum/maximum quantity reorder rules. The 8 policy types (abs_level, doc_dem, doc_fcst, sl, sl_fitted, conformal, sl_conformal_fitted, econ_optimal) must be reimplemented as extensions that override the standard replenishment logic.

4. **No forecast entity**: Demand planning must be built from scratch. Odoo's MPS uses a basic spreadsheet-like grid for manual demand entry — no statistical forecasting, no P10/P50/P90 percentiles, no forecast versioning.

5. **Partner model unification**: Odoo's `res.partner` merges customers, vendors, contacts, and companies. The AWS SC distinction between `TradingPartner` types and the separate `customer_id` semantics must be handled via `partner.category_id` tags or custom fields.

6. **Multi-company replaces tenant**: Odoo's multi-company model (`res.company`) replaces the Autonomy `tenant` concept. Record rules filter by `company_id` instead of `tenant_id`. This is architecturally sound but requires careful migration of all tenant-scoped queries.

---

## 5. Backend Conversion: FastAPI → Odoo Modules

### 5.1 Architecture Comparison

| Aspect | Current (FastAPI) | Target (Odoo) |
|--------|-------------------|---------------|
| Web framework | FastAPI (async, ASGI) | Werkzeug (sync, WSGI) |
| ORM | SQLAlchemy 2.0 (async) | Odoo ORM (sync, custom) |
| API style | REST + WebSocket | JSON-RPC (Odoo native) |
| Auth | JWT + CSRF + MFA | Session-based + API keys |
| Background jobs | APScheduler (in-process) | ir.cron (DB-driven, single-thread) |
| Process model | Single async process | Pre-forked workers (6 users/worker) |
| Worker memory limit | None (container-level) | 768 MB hard kill |
| Database access | Raw SQL + ORM | ORM only (raw SQL bypasses security) |
| Schema migrations | Alembic | Odoo auto-migration (on module upgrade) |

### 5.2 Service-by-Service Conversion Feasibility

| Service | Lines | Odoo Conversion | Notes |
|---------|-------|-----------------|-------|
| **Planning Services** | | | |
| `demand_processor.py` | 890 | ✅ Rewrite as Odoo model methods | Queries change from SQLAlchemy to ORM |
| `inventory_target_calculator.py` | 1,200 | ⚠️ Extend `stock.warehouse.orderpoint` | 8 policy types must override Odoo's min/max |
| `net_requirements_calculator.py` | 1,400 | ⚠️ Extend Odoo MRP scheduler | Odoo's `_procure_orderpoint_confirm()` is the entry point; must inject custom logic |
| `stochastic_sampler.py` | 600 | 🔴 External service | Monte Carlo cannot run in Odoo workers (memory) |
| **Powell Framework** | | | |
| All 11 TRM services | 12,000 | 🔴 External microservice | PyTorch inference cannot run in Odoo workers |
| `site_agent.py` | 2,500 | 🔴 External microservice | Orchestrates TRM hive, needs GPU |
| `decision_cycle.py` | 7,583 | 🔴 External microservice | 6-phase cycle too complex for ir.cron |
| `escalation_arbiter.py` | 1,200 | 🔴 External microservice | Cross-tier routing logic |
| **GNN/GraphSAGE** | | | |
| All GNN services | 8,000 | 🔴 External microservice | PyTorch Geometric, GPU training |
| `site_tgnn_inference_service.py` | 800 | 🔴 External microservice | Hourly inference cycle |
| **Simulation** | | | |
| `engine.py` (Beer Game) | 1,800 | ⚠️ Rewrite as Odoo model | SimPy dependency problematic in Odoo |
| `training_distributions.py` | 2,000 | 🔴 External service | scipy, Monte Carlo |
| `coordinated_sim_runner.py` | 12,314 | 🔴 External service | Multi-episode simulation |
| **Conformal Prediction** | | | |
| All conformal services | 4,000 | 🔴 External service | scipy, statsmodels, heavy computation |
| **Causal AI** | | | |
| `outcome_collector.py` | 1,500 | 🔴 External service | Complex cross-table joins + computation |
| `override_effectiveness_service.py` | 800 | 🔴 External service | Bayesian Beta posteriors |
| `causal_matching_service.py` | 600 | 🔴 External service | Propensity score matching |
| **Integration** | | | |
| SAP/D365 staging | 3,000 | ✅ Rewrite as Odoo modules | JSONB staging → Odoo models |
| ERP field mapping | 2,000 | ✅ Rewrite as Odoo modules | 3-tier mapping → Odoo model methods |
| **Platform** | | | |
| `auth_service.py` | 600 | ✅ Use Odoo auth | Odoo handles auth natively |
| `tenant_service.py` | 400 | ✅ Map to `res.company` | Multi-company = multi-tenant |
| WebSocket services | 1,200 | 🔴 External service | Odoo has no WebSocket support |
| `directive_service.py` | 800 | ⚠️ Hybrid | LLM parsing → external; storage → Odoo |
| `query_router.py` | 500 | ⚠️ Rewrite for Odoo actions | Route to Odoo menu items instead of React routes |
| Knowledge Base / RAG | 1,500 | 🔴 External service | pgvector, embeddings |

**Summary**:
- ✅ **Can be Odoo-native**: ~20% of backend (CRUD, auth, ERP staging, basic planning queries)
- ⚠️ **Partial rewrite**: ~15% (planning logic that extends Odoo's MRP/replenishment)
- 🔴 **Must remain external**: ~65% (all AI/ML, simulation, Monte Carlo, conformal, causal, WebSocket, RAG)

### 5.3 Background Job Migration

| Current (APScheduler) | Odoo Equivalent | Risk |
|----------------------|-----------------|------|
| Outcome collection (:30, :32, :33) | ir.cron | ir.cron is single-threaded; failure in one record rolls back batch |
| CDT calibration (:35) | External service | Too compute-heavy for ir.cron |
| Site tGNN inference (:25) | External service | PyTorch, GPU |
| Escalation arbiter (every 2h) | ir.cron (trigger only) | Actual computation external |
| CFA optimization (weekly) | External service | Differential Evolution, hours of compute |
| Site tGNN training (every 12h) | External service | PyTorch training |
| Conformal recalibration | External service | scipy, statsmodels |

---

## 6. Frontend Conversion: React/MUI → OWL/Odoo UI

### 6.1 Scale of Rewrite

| Category | React Pages | OWL Equivalent Effort |
|----------|-------------|----------------------|
| **Planning** (MPS, MRP, S&OP, demand, supply, inventory, capacity) | 43 | 43 Odoo views (form + list + pivot + graph per model) |
| **Execution Worklists** (11 TRM types) | 11 | 11 Odoo list/kanban views with custom actions |
| **Admin** (TRM, GNN, Skills, SAP, users, provisioning) | 25 | 25 Odoo views + settings pages |
| **Simulation** (Beer Game) | 8 | 8 custom OWL components (no Odoo view equivalent) |
| **Analytics/Dashboards** | 12 | 12 custom OWL dashboard components |
| **Auth** | 5 | 0 (Odoo handles auth UI) |
| **Total** | **96+** | **~90 views/components** |

### 6.2 Component Library Losses

Every one of these must be reimplemented or abandoned:

| React Library | Usage | Odoo Replacement |
|--------------|-------|------------------|
| **Material-UI 5** | All form controls, dialogs, tabs, navigation | Odoo Bootstrap theme (different design language) |
| **Recharts** | 40+ chart types (line, bar, area, scatter, radar) | Odoo's Chart.js integration (limited) or custom OWL |
| **D3-Sankey** | Supply chain topology visualization | Custom OWL + D3 (can embed D3 in OWL) |
| **React Router** | Client-side routing | Odoo action stack (server-driven navigation) |
| **Axios** | API client | `this.env.services.orm` + `this.env.services.rpc` |
| **React DnD** | Drag-and-drop (Gantt, planning boards) | Odoo's built-in drag support (limited) |
| **date-fns** | Date manipulation | Odoo's `luxon` integration |

### 6.3 Visualization Challenges

Autonomy's most distinctive UI elements have no Odoo equivalent:

1. **D3-Sankey supply chain topology**: Must be reimplemented as a custom OWL widget embedding D3. Odoo has no network/graph visualization.

2. **Decision Stream inbox**: Real-time WebSocket-driven decision feed. Odoo's `mail.thread` / Discuss provides activity feeds but not the urgency-sorted, multi-source decision routing that Decision Stream implements.

3. **Probabilistic scorecards**: P10/P50/P90 distribution visualizations. Odoo's pivot/graph views show single-point values, not distributions.

4. **TRM Hive visualization**: Custom SVG rendering of urgency vectors, signal bus, decision cycle phases. No Odoo equivalent — must be custom OWL.

5. **Provisioning Stepper**: 14-step pipeline visualization with dependency tracking. Could use Odoo's status bar widget partially, but the dependency DAG visualization is custom.

6. **Scenario Board** (Beer Game): Real-time multi-user game board with WebSocket updates. Fundamentally incompatible with Odoo's request/response model — must remain as a separate web app or use a custom OWL component with external WebSocket connection.

### 6.4 Odoo View Types Available

| Odoo View | Usable For | Limitations |
|-----------|-----------|-------------|
| **Form** | Data entry, detail pages | Single-record, no custom layouts |
| **List/Tree** | Worklists, tables | Column types limited to Odoo field widgets |
| **Kanban** | Card-based views, decision boards | Limited to predefined card templates |
| **Pivot** | Multi-dimensional analysis | No probabilistic values, no custom aggregations |
| **Graph** | Basic charts (bar, line, pie) | Chart.js only, limited customization |
| **Gantt** (Enterprise) | Production scheduling, timelines | Good for MO/WO planning |
| **Map** (Enterprise) | Geographic views | Not needed for Autonomy |
| **Calendar** | Time-based scheduling | Limited applicability |
| **Dashboard** | KPI tiles | No custom visualizations |
| **Cohort** (Enterprise) | Retention analysis | Not applicable |

---

## 7. AI/ML Architecture Under Odoo

### 7.1 The Fundamental Constraint

Odoo workers enforce a **768 MB hard memory limit** (process killed instantly). A single TRM model (7M parameters, ~28 MB in memory) is small, but:

- PyTorch runtime: ~200 MB base
- PyTorch Geometric: ~150 MB
- scipy + numpy + pandas: ~100 MB
- Model weights (11 TRMs loaded): ~310 MB
- Inference buffers: ~100 MB
- **Total**: ~860 MB — **exceeds hard limit**

**Conclusion**: AI/ML inference and training **cannot run inside Odoo workers**. Period.

### 7.2 Required Sidecar Architecture

```
┌─────────────────────────────────────────────┐
│                   Odoo                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │ Planning  │ │ Execution│ │  Admin   │    │
│  │ Modules   │ │ Worklist │ │ Modules  │    │
│  │ (OWL UI)  │ │ (OWL UI) │ │ (OWL UI) │    │
│  └─────┬─────┘ └─────┬────┘ └────┬─────┘    │
│        │              │           │          │
│  ┌─────┴──────────────┴───────────┴─────┐    │
│  │       Odoo ORM + PostgreSQL          │    │
│  │   (Odoo native models + autonomy.*)  │    │
│  └─────────────────┬────────────────────┘    │
└────────────────────┼─────────────────────────┘
                     │ JSON-RPC / REST
                     ▼
┌─────────────────────────────────────────────┐
│         Autonomy Intelligence Layer          │
│  (Separate FastAPI / Docker container)       │
│                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │ TRM Hive │ │ GNN/tGNN │ │ Monte    │    │
│  │ (11 TRMs)│ │ GraphSAGE│ │ Carlo    │    │
│  └──────────┘ └──────────┘ └──────────┘    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │ Conformal│ │ Causal AI│ │ Claude   │    │
│  │ Predict  │ │ Outcomes │ │ Skills   │    │
│  └──────────┘ └──────────┘ └──────────┘    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │ SimPy    │ │ RAG/     │ │ WebSocket│    │
│  │ Digital  │ │ pgvector │ │ Server   │    │
│  │ Twin     │ │          │ │          │    │
│  └──────────┘ └──────────┘ └──────────┘    │
└─────────────────────────────────────────────┘
```

### 7.3 Implications

The AI/ML layer — which is the **core value proposition** of Autonomy — must remain as a separate service. This means:

1. **Two codebases**: Odoo modules (data + UI) + Intelligence microservice (AI/ML)
2. **Two deployment targets**: Odoo server + Docker container with GPU
3. **Two data access patterns**: Odoo ORM (for UI) + direct PostgreSQL (for ML training)
4. **API bridge**: Every AI decision must flow through an RPC bridge between Odoo and the intelligence layer
5. **Latency**: TRM decisions (<10ms in current architecture) gain network hop overhead (~5-15ms per RPC call)

---

## 8. Security & SOC II Compliance

### 8.1 Security Model Comparison

| Requirement | Current (PostgreSQL RLS) | Odoo Native | Gap |
|-------------|-------------------------|-------------|-----|
| **Tenant isolation** | DB-level RLS policies on `tenant_id` | ORM-level `ir.rule` on `company_id` | Odoo security is application-layer only. Raw SQL (needed for ML training) bypasses all rules. **SOC II risk.** |
| **Audit logging** | pgaudit (DDL, ROLE, WRITE) | `mail.thread` chatter + `ir.logging` | Odoo's audit is ORM-level only. Direct DB changes are invisible. |
| **Encryption at rest** | KMS / dm-crypt + pgcrypto | Odoo.sh handles at infrastructure level; self-hosted requires manual setup | Comparable if self-hosted correctly |
| **Encryption in transit** | SSL/TLS enforced on all connections | Odoo.sh handles; self-hosted via reverse proxy | Comparable |
| **RBAC** | PostgreSQL roles + application-layer | Odoo groups + ACL + record rules | Odoo's is more feature-rich (group inheritance, implied groups) but ORM-only |
| **MFA** | TOTP (PyOTP) | Odoo Enterprise TOTP (built-in since v15) | Parity in Enterprise |
| **Connection pooling safety** | `SET LOCAL` for tenant context in PgBouncer | Not applicable (Odoo manages its own connections) | Different model |

### 8.2 Critical SOC II Concern

**Odoo's security is ORM-enforced, not database-enforced.** Any code that uses `self.env.cr.execute(raw_sql)` bypasses all record rules. The intelligence layer, which needs direct DB access for ML training data extraction, would operate outside Odoo's security perimeter.

**Mitigation options**:
1. Create a dedicated PostgreSQL role for the intelligence layer with explicit GRANT/REVOKE
2. Implement DB-level RLS **in addition to** Odoo's record rules (non-standard, may conflict)
3. Route all data access through Odoo RPC (adds latency, limits query complexity)

None of these are elegant. The current architecture (PostgreSQL RLS at DB level) is inherently more secure for the multi-tenant AI/ML use case.

---

## 9. What Gets Lost

### 9.1 Technical Capabilities Lost or Degraded

| Capability | Current | After Odoo Fork | Impact |
|-----------|---------|------------------|--------|
| **Async execution** | Full async (FastAPI/SQLAlchemy) | Synchronous (Werkzeug) | Higher latency, lower throughput |
| **WebSocket real-time** | Native WebSocket | Must run separate server | Beer Game, Decision Stream degraded |
| **Database-level security** | PostgreSQL RLS | ORM-level record rules | SOC II compliance risk |
| **Custom SQL optimization** | Full control | ORM-only or bypass security | Performance ceiling |
| **pgvector / RAG** | Native integration | External service | Additional infrastructure |
| **Schema migrations** | Alembic (controlled, reversible) | Odoo auto-migration (opaque) | Less control over schema evolution |
| **API design** | REST with OpenAPI docs | JSON-RPC (no OpenAPI, no Swagger) | Worse developer experience for external integrators |
| **Horizontal scaling** | Stateless containers | Worker-based (stateful sessions) | Harder to scale under load |

### 9.2 Business Capabilities Lost

| Capability | Reason |
|-----------|--------|
| **AWS SC data model compliance** | Replaced by Odoo data model. Lose AWS Marketplace / ISV Accelerate eligibility. |
| **SAP customer migration** | No longer a drop-in AI overlay for SAP customers. Odoo-only. |
| **D365 customer migration** | Same — Odoo-only positioning. |
| **ERP-agnostic positioning** | Platform becomes Odoo-specific. |
| **Multi-ERP training** | Cannot train TRMs on unified AWS SC feature space across ERP vendors. |
| **AWS SC compliance documentation** | 35-entity compliance matrix becomes irrelevant. |

### 9.3 Competitive Positioning Lost

The current platform positions as **ERP-agnostic decision intelligence** — sits above any ERP (SAP, D365, Odoo) and provides AI planning. An Odoo fork positions as an **Odoo add-on** — a fundamentally different market position:

| Aspect | Current Position | Odoo Fork Position |
|--------|-----------------|-------------------|
| **Market** | Mid-market manufacturers (any ERP) | Odoo-only manufacturers |
| **TAM** | $12B+ APS market | Odoo ecosystem (~$1B) |
| **Competition** | Kinaxis, SAP IBP, o9, OMP | frePPLe, Odoo MPS, MRP Consultants |
| **Pricing power** | Enterprise SaaS ($50K-500K ARR) | Odoo app store ($10-50/user/month) |
| **Buyer** | VP Supply Chain / CIO | Odoo partner / IT manager |

---

## 10. What Gets Gained

### 10.1 Technical Advantages

| Advantage | Impact |
|-----------|--------|
| **Odoo App Store distribution** | 12M+ Odoo users, 70/30 revenue share, instant discovery |
| **Built-in ERP features** | Accounting, HR, CRM, project management — no need to build |
| **Odoo's MRP as foundation** | BOM explosion, routing, work orders — extend rather than build |
| **Multi-company native** | Tenant isolation via `res.company` is first-class |
| **Chatter audit trail** | Every model gets built-in change tracking (mail.thread) |
| **Odoo Studio** (Enterprise) | No-code customization for simple field additions |
| **Partner ecosystem** | Odoo partners can implement / support the solution |
| **Simpler deployment** (for basic features) | Odoo's standard deployment is well-documented |
| **Odoo.sh** (for non-AI features) | Managed hosting for the Odoo layer |

### 10.2 Market Advantages

| Advantage | Impact |
|-----------|--------|
| **Odoo's growth trajectory** | Fastest-growing ERP ($650M revenue, +50% YoY) |
| **SMB/mid-market penetration** | Odoo dominates the market segment Autonomy targets |
| **Lower customer acquisition cost** | App Store discovery vs enterprise sales cycles |
| **Partner channel** | 4,000+ Odoo partners globally can resell |
| **Regional strength** | Odoo strong in Europe, Middle East, Africa, South Asia — complements Autonomy's NA focus |

### 10.3 Operational Advantages

| Advantage | Impact |
|-----------|--------|
| **Single vendor relationship** | Customer's ERP and planning on same platform |
| **Unified authentication** | No separate login or SSO configuration |
| **Data consistency** | No ETL/staging layer — direct access to operational data |
| **Upgrade compatibility** | Odoo's module system handles cross-module compatibility |

---

## 11. Module-by-Module Conversion Map

### 11.1 Proposed Odoo Module Structure

```
autonomy_base/                    # Core models, settings, security
autonomy_planning/                # Demand planning, S&OP, forecasting
autonomy_supply/                  # Supply planning, net requirements
autonomy_inventory/               # Inventory optimization (8 policies)
autonomy_mps/                     # Master Production Scheduling
autonomy_execution/               # TRM worklists (11 types)
autonomy_agents/                  # Agent configuration, training UI
autonomy_intelligence_bridge/     # RPC bridge to AI microservice
autonomy_simulation/              # Beer Game / Digital Twin UI
autonomy_decision_stream/         # Decision inbox, routing
autonomy_authorization/           # AAP (Agentic Authorization Protocol)
autonomy_conformal/               # Conformal prediction UI / config
autonomy_provisioning/            # 14-step provisioning stepper
autonomy_directives/              # Azirella directive capture
autonomy_email_signals/           # Email signal ingestion
autonomy_knowledge_base/          # RAG document management
autonomy_skills/                  # Claude Skills configuration
```

### 11.2 Conversion Effort Per Module

| Module | New Odoo Code | Reusable Code | External Service | Effort (person-months) |
|--------|--------------|---------------|-----------------|----------------------|
| `autonomy_base` | Models, security, menus | 0% | None | 2 |
| `autonomy_planning` | Views, wizards, reports | 20% (math logic) | Stochastic sampler | 4 |
| `autonomy_supply` | Extend MRP scheduler | 30% (net req calc) | Monte Carlo | 3 |
| `autonomy_inventory` | Extend orderpoint | 40% (policy math) | Conformal service | 3 |
| `autonomy_mps` | Extend Odoo MPS | 20% | None | 2 |
| `autonomy_execution` | 11 worklist views | 10% (UI only) | All TRM services | 4 |
| `autonomy_agents` | Training config UI | 5% | All AI services | 2 |
| `autonomy_intelligence_bridge` | RPC bridge + adapters | 0% | IS the bridge | 3 |
| `autonomy_simulation` | OWL game board | 5% (engine logic) | WebSocket server | 3 |
| `autonomy_decision_stream` | Kanban/list views | 10% (routing logic) | WebSocket server | 2 |
| `autonomy_authorization` | Board views, actions | 10% | LLM service | 2 |
| `autonomy_conformal` | Config views | 5% | All computation | 1 |
| `autonomy_provisioning` | Stepper wizard | 10% | Pipeline orchestrator | 2 |
| `autonomy_directives` | Form + chatter | 15% (parsing logic) | LLM service | 1 |
| `autonomy_email_signals` | List views, config | 20% (PII scrubber) | IMAP connector | 1 |
| `autonomy_knowledge_base` | Document management | 5% | pgvector / RAG | 1 |
| `autonomy_skills` | Config dashboard | 5% | Claude API client | 1 |
| **Intelligence Microservice** | Refactored from current | 60% | N/A (IS the service) | 8 |
| **Total** | | | | **45 person-months** |

---

## 12. Deployment Architecture

### 12.1 Self-Hosted (Required for Full AI Features)

```yaml
# docker-compose.odoo-fork.yml (conceptual)

services:
  # --- Odoo Layer ---
  odoo:
    image: odoo:19
    volumes:
      - ./addons:/mnt/extra-addons    # autonomy_* modules
      - odoo-data:/var/lib/odoo
    environment:
      - DB_HOST=db
      - DB_USER=odoo
      - DB_PASSWORD=secret
    depends_on:
      - db
      - intelligence

  # --- Database ---
  db:
    image: postgres:15
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=odoo
      - POSTGRES_USER=odoo
    # Extensions: pgvector, pgaudit (loaded via init script)

  # --- Intelligence Layer (Autonomy AI) ---
  intelligence:
    build: ./intelligence
    runtime: nvidia          # GPU support
    volumes:
      - checkpoints:/app/checkpoints
    environment:
      - DB_HOST=db
      - CLAUDE_API_KEY=${CLAUDE_API_KEY}
      - LLM_API_BASE=${LLM_API_BASE}
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]

  # --- WebSocket Server (Real-Time) ---
  websocket:
    build: ./websocket
    ports:
      - "8072:8072"

  # --- Reverse Proxy ---
  nginx:
    image: nginx:alpine
    ports:
      - "8088:80"
      - "8443:443"
    # Route: /web/* → odoo, /intelligence/* → intelligence, /ws/* → websocket
```

### 12.2 Odoo.sh + External AI (Compromise)

```
┌───────────────────────────┐
│       Odoo.sh (SaaS)      │  ← Odoo modules (data + UI)
│  autonomy_* custom modules│
│  Standard MRP/MPS/Quality │
└────────────┬──────────────┘
             │ HTTPS / JSON-RPC
             ▼
┌───────────────────────────┐
│   Cloud VM (GPU instance) │  ← Intelligence Layer
│   FastAPI + PyTorch       │
│   TRMs, GNNs, Monte Carlo│
│   WebSocket server        │
└───────────────────────────┘
```

**Limitations**: Odoo.sh max 8 workers, can't install pgvector, can't run GPU. All AI features require the external VM. Latency between Odoo.sh and external VM adds 10-50ms per decision.

---

## 13. Deploying on Odoo Cloud (Odoo.sh)

This section covers how a forked Autonomy-as-Odoo-modules solution would be deployed on Odoo's managed cloud platform (Odoo.sh), including the constraints, workarounds, and the required external infrastructure for the AI/ML intelligence layer.

### 13.1 Odoo.sh Overview

Odoo.sh is Odoo's official PaaS (Platform-as-a-Service), tightly integrated with GitHub for CI/CD. It provides managed Odoo instances with staging environments, automated backups, and monitoring.

**Pricing tiers** (as of 2026):

| Tier | Price | Workers | Storage | RAM | Use Case |
|------|-------|---------|---------|-----|----------|
| **Shared** | From $180/mo + $24/user/mo (Enterprise) | 1-8 | Up to 512 GB | Shared | Small deployments (<50 users) |
| **Dedicated** | Custom pricing | Up to 256 | Up to 4,096 GB | Dedicated | Large deployments, compliance |

**What Odoo.sh provides**:
- GitHub-integrated CI/CD (push to branch → auto-deploy to staging)
- Three environment types: Production, Staging, Development
- Automated daily backups with point-in-time recovery
- Built-in monitoring (CPU, RAM, disk, worker utilization)
- Let's Encrypt SSL certificates (auto-provisioned)
- Custom domain support
- PostgreSQL managed instance (no direct shell access)
- Odoo Enterprise license included in subscription

### 13.2 Deploying Autonomy Modules on Odoo.sh

**Step 1: Repository Structure**

Odoo.sh expects a specific Git repository structure:

```
autonomy-odoo/
├── .odoo.sh/                    # Odoo.sh configuration
│   └── requirements.txt         # Python pip dependencies
├── autonomy_base/               # Core module
│   ├── __manifest__.py
│   ├── models/
│   ├── views/
│   └── security/
├── autonomy_planning/           # Planning module
├── autonomy_supply/             # Supply planning module
├── autonomy_inventory/          # Inventory optimization
├── autonomy_mps/                # MPS extensions
├── autonomy_execution/          # TRM worklists
├── autonomy_agents/             # Agent configuration
├── autonomy_intelligence_bridge/ # Bridge to external AI
├── autonomy_simulation/         # Beer Game / Digital Twin
├── autonomy_decision_stream/    # Decision inbox
├── autonomy_authorization/      # AAP
├── autonomy_conformal/          # Conformal prediction UI
├── autonomy_provisioning/       # Provisioning stepper
├── autonomy_directives/         # Azirella
├── autonomy_email_signals/      # Email signal ingestion
├── autonomy_knowledge_base/     # RAG document management
└── autonomy_skills/             # Claude Skills config
```

**Step 2: Dependencies**

Odoo.sh allows Python pip packages via `.odoo.sh/requirements.txt`, but with restrictions:
- No compiled C extensions that require system libraries not present on Odoo.sh
- No packages that exceed worker memory limits
- **Cannot install**: PyTorch, PyTorch Geometric, scipy (large), pgvector
- **Can install**: requests, python-dateutil, pydantic, cryptography, pyotp

```
# .odoo.sh/requirements.txt (Odoo-safe only)
pydantic>=2.0
python-dateutil>=2.8
cryptography>=41.0
pyotp>=2.9
httpx>=0.25      # For calling intelligence service API
```

**Step 3: Module Installation**

```
# In Odoo.sh Settings → Apps
# Install modules in dependency order:
1. autonomy_base
2. autonomy_planning
3. autonomy_supply
4. autonomy_inventory
5. autonomy_mps
6. autonomy_execution
7. autonomy_intelligence_bridge  # Must point to external AI service
8. ... (remaining modules)
```

### 13.3 The Intelligence Layer: External Cloud Deployment

Since Odoo.sh **cannot run PyTorch, GPU workloads, pgvector, WebSocket servers, or heavy computation**, the intelligence layer must be deployed on a separate cloud instance.

**Recommended deployment: AWS / GCP / Azure VM alongside Odoo.sh**

```
┌─────────────────────────────────────┐
│         Odoo.sh (Managed)           │
│                                     │
│  autonomy_* Odoo modules            │
│  Odoo Enterprise (MRP, Quality...)  │
│  PostgreSQL (managed, no extensions)│
│                                     │
│  autonomy_intelligence_bridge       │
│  └─→ HTTPS calls to ──────────────────┐
└─────────────────────────────────────┘  │
                                         ▼
┌─────────────────────────────────────────────┐
│    Cloud VM (e.g., AWS g5.xlarge)           │
│                                             │
│    Docker Compose:                          │
│    ┌────────────────────────────────┐       │
│    │  intelligence-api (FastAPI)    │       │
│    │  - 11 TRM agents              │       │
│    │  - Site tGNN, Network tGNN    │       │
│    │  - S&OP GraphSAGE             │       │
│    │  - Monte Carlo simulator      │       │
│    │  - Conformal prediction       │       │
│    │  - Causal AI pipeline         │       │
│    │  - Claude Skills orchestrator │       │
│    │  - Decision reasoning engine  │       │
│    └────────────────────────────────┘       │
│    ┌────────────────────────────────┐       │
│    │  postgres:15 + pgvector       │       │
│    │  (AI-specific tables only)    │       │
│    └────────────────────────────────┘       │
│    ┌────────────────────────────────┐       │
│    │  websocket-server (FastAPI)   │       │
│    │  - Decision Stream live feed  │       │
│    │  - Beer Game real-time        │       │
│    │  - Collaborative planning     │       │
│    └────────────────────────────────┘       │
│    ┌────────────────────────────────┐       │
│    │  vllm (optional, Qwen 3 8B)  │       │
│    │  - Self-hosted LLM inference  │       │
│    └────────────────────────────────┘       │
│                                             │
│    NVIDIA GPU: T4 (inference) or A10G      │
│    RAM: 32 GB minimum                       │
│    Storage: 100 GB SSD                      │
│    Cost: ~$500-1,200/mo (AWS g5.xlarge)    │
└─────────────────────────────────────────────┘
```

### 13.4 Data Synchronization Architecture

The split deployment creates a **dual-database challenge**: Odoo.sh manages its own PostgreSQL (no direct access, no extensions), while the intelligence layer needs its own database (with pgvector, custom tables).

**Synchronization flow**:

```
Odoo.sh PostgreSQL                    Intelligence PostgreSQL
┌──────────────────┐                  ┌──────────────────┐
│ Odoo native:     │                  │ AI-specific:     │
│ - product.product│  ─── sync ───→   │ - powell_*       │
│ - stock.warehouse│  (scheduled)     │ - decision_embed │
│ - mrp.production │                  │ - hive_states    │
│ - stock.quant    │                  │ - gnn_*          │
│ - sale.order     │                  │ - trm_checkpoints│
│ - purchase.order │                  │ - conformal_*    │
│ - autonomy.*     │  ←── results ── │ - causal_*       │
│   (extension)    │  (on decision)  │ - scenarios      │
└──────────────────┘                  └──────────────────┘
```

**Sync implementation** (via `autonomy_intelligence_bridge`):

```python
# autonomy_intelligence_bridge/models/sync_service.py

class IntelligenceSyncService(models.Model):
    _name = 'autonomy.intelligence.sync'
    _description = 'Sync Odoo data to Intelligence Layer'

    @api.model
    def sync_master_data(self):
        """Scheduled action: push master data changes to intelligence API."""
        api_url = self.env['ir.config_parameter'].sudo().get_param(
            'autonomy.intelligence_api_url'
        )
        # Collect changed products since last sync
        last_sync = self._get_last_sync_timestamp()
        products = self.env['product.product'].search([
            ('write_date', '>', last_sync)
        ])
        payload = [{
            'odoo_id': p.id,
            'name': p.name,
            'default_code': p.default_code,
            'standard_price': p.standard_price,
            'uom': p.uom_id.name,
        } for p in products]

        httpx.post(f'{api_url}/sync/products', json=payload, timeout=30)

    @api.model
    def pull_decisions(self):
        """Scheduled action: pull AI decisions and create Odoo activities."""
        api_url = self.env['ir.config_parameter'].sudo().get_param(
            'autonomy.intelligence_api_url'
        )
        decisions = httpx.get(
            f'{api_url}/decisions/pending', timeout=30
        ).json()

        for dec in decisions:
            # Create Odoo activity on relevant record
            if dec['type'] == 'po_creation':
                partner = self.env['res.partner'].search([
                    ('ref', '=', dec['vendor_ref'])
                ], limit=1)
                if partner:
                    partner.activity_schedule(
                        'mail.mail_activity_data_todo',
                        summary=f"AI Recommendation: {dec['summary']}",
                        note=dec['reasoning'],
                    )
```

### 13.5 Odoo.sh Configuration

**System Parameters** (Settings → Technical → Parameters → System Parameters):

| Key | Value | Purpose |
|-----|-------|---------|
| `autonomy.intelligence_api_url` | `https://ai.example.com/api/v1` | Intelligence layer endpoint |
| `autonomy.intelligence_api_key` | `sk-...` | Authentication for AI service |
| `autonomy.websocket_url` | `wss://ai.example.com/ws` | WebSocket endpoint for real-time features |
| `autonomy.sync_interval_minutes` | `15` | Master data sync frequency |
| `autonomy.decision_poll_minutes` | `5` | Decision polling frequency |
| `autonomy.claude_api_key` | `sk-ant-...` | Claude API key (for Skills) |

**Scheduled Actions** (ir.cron entries created by module install):

| Cron Job | Interval | Function |
|----------|----------|----------|
| Sync Master Data | Every 15 min | `autonomy.intelligence.sync.sync_master_data()` |
| Pull AI Decisions | Every 5 min | `autonomy.intelligence.sync.pull_decisions()` |
| Sync Inventory Levels | Every 1 hour | `autonomy.intelligence.sync.sync_inventory()` |
| Sync Order Changes | Every 15 min | `autonomy.intelligence.sync.sync_orders()` |
| Sync Forecast Data | Every 6 hours | `autonomy.intelligence.sync.sync_forecasts()` |

### 13.6 Network & Security Configuration

**Firewall rules** (between Odoo.sh and Intelligence VM):

```
# Intelligence VM security group
Inbound:
  - TCP 443 from Odoo.sh IP ranges (HTTPS API)
  - TCP 8072 from Odoo.sh IP ranges (WebSocket)
  - TCP 443 from customer browser IPs (for direct WebSocket)

Outbound:
  - TCP 5432 to Intelligence PostgreSQL (if separate)
  - TCP 443 to Claude API (api.anthropic.com)
  - TCP 443 to vLLM (if remote)
```

**Authentication between services**:
- Odoo.sh → Intelligence: API key in header (`Authorization: Bearer sk-...`)
- Intelligence → Odoo.sh: Odoo API key (`/json/2` endpoint with `apikey` parameter)
- Browser → WebSocket: JWT token from Odoo session (validated by WebSocket server)

### 13.7 Odoo.sh Limitations Impact

| Limitation | Impact on Autonomy | Workaround |
|-----------|-------------------|------------|
| **No GPU** | Cannot train or run TRM/GNN models | External VM (mandatory) |
| **No pgvector** | Cannot store decision embeddings | External PostgreSQL |
| **No custom system packages** | Cannot install PyTorch, scipy | External VM |
| **768 MB worker memory** | Cannot load ML models | External inference |
| **No WebSocket server** | Cannot provide real-time updates | External WebSocket + browser direct connect |
| **No background workers** | Cannot run continuous inference | ir.cron polling (5-15 min intervals) |
| **No Docker** | Cannot run vLLM or sidecar services | External VM |
| **8 workers max (shared)** | ~48 concurrent users | Dedicated tier for larger deployments |
| **No shell access (shared)** | Cannot debug/tune PostgreSQL | Dedicated tier or external DB |
| **No db extensions** | No pgaudit for SOC II | External audit logging service |

### 13.8 Cost Model: Odoo.sh + External AI

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| **Odoo.sh Shared** | $180 base | Platform fee |
| **Odoo Enterprise licenses** | $24/user × N users | Required for MPS, Quality, Gantt |
| **Intelligence VM (AWS g5.xlarge)** | $800-1,200 | 1 GPU, 16 GB GPU RAM, 32 GB RAM |
| **Intelligence PostgreSQL (RDS)** | $200-400 | db.r6g.large with pgvector |
| **Network transfer** | $50-100 | Data sync between Odoo.sh and VM |
| **Claude API** | $50-200 | Skills exception handling (~5% of decisions) |
| **Domain + SSL** | $20 | Custom domain for intelligence API |
| **Monitoring (Datadog/CloudWatch)** | $50-100 | Both Odoo.sh and VM |

**Total for 20 users**: ~$1,800-2,600/month ($108-156/user/month)
**Total for 50 users**: ~$2,600-3,800/month ($52-76/user/month)
**Total for 100 users**: ~$3,800-5,400/month ($38-54/user/month)

**Comparison**: Current Autonomy (self-hosted Docker Compose) costs ~$800-1,500/month for infrastructure regardless of user count. The Odoo.sh path adds $1,000-2,000/month in platform and licensing fees.

### 13.9 Deployment Checklist

```
□ Phase 1: Odoo.sh Setup
  □ Create Odoo.sh project (GitHub integration)
  □ Configure production branch (main)
  □ Set up staging branch (develop)
  □ Configure custom domain
  □ Install Odoo Enterprise modules (MRP, Quality, Planning)

□ Phase 2: Intelligence VM Setup
  □ Provision GPU VM (AWS g5.xlarge or equivalent)
  □ Install Docker + NVIDIA Container Toolkit
  □ Deploy intelligence-api container (FastAPI + PyTorch)
  □ Deploy PostgreSQL 15 with pgvector extension
  □ Deploy WebSocket server container
  □ Deploy vLLM container (optional, for self-hosted LLM)
  □ Configure SSL certificates (Let's Encrypt)
  □ Set up firewall rules (whitelist Odoo.sh IPs)

□ Phase 3: Module Deployment
  □ Push autonomy_* modules to GitHub repo
  □ Verify Odoo.sh auto-build succeeds (staging)
  □ Install modules in dependency order (staging)
  □ Configure System Parameters (intelligence API URL, keys)
  □ Verify sync jobs execute correctly
  □ Run integration tests (Odoo → Intelligence → Odoo round-trip)
  □ Promote staging → production

□ Phase 4: Data Migration
  □ Export current Autonomy data (AWS SC model)
  □ Transform to Odoo native format (product, warehouse, BOM, etc.)
  □ Import via Odoo's base_import or custom migration script
  □ Populate autonomy.* extension models
  □ Sync initial data to intelligence layer
  □ Run provisioning pipeline (14-step warm-start)
  □ Verify TRM calibration and decision seeding

□ Phase 5: Validation
  □ Verify all 11 TRM worklists display decisions
  □ Verify Decision Stream polling works
  □ Verify Beer Game WebSocket connectivity (browser → external WS)
  □ Verify conformal prediction calibration
  □ Load test: 50 concurrent users on Odoo.sh shared tier
  □ SOC II gap assessment (ORM security vs RLS)
  □ Disaster recovery test (Odoo.sh backup + VM snapshot restore)
```

---

## 14. Effort Estimation

### 14.1 Work Breakdown

| Phase | Duration | Team | Deliverable |
|-------|----------|------|-------------|
| **Phase 0: Architecture** | 4 weeks | 2 architects | Module design, data model mapping, API contracts |
| **Phase 1: Core Models** | 8 weeks | 3 developers | `autonomy_base`, `autonomy_planning`, `autonomy_supply`, `autonomy_inventory` |
| **Phase 2: Intelligence Bridge** | 6 weeks | 2 developers | Refactor AI services into standalone microservice, RPC bridge |
| **Phase 3: MPS/MRP Extensions** | 6 weeks | 2 developers | `autonomy_mps`, extend Odoo scheduler |
| **Phase 4: Execution Worklists** | 8 weeks | 3 developers | 11 TRM worklist views, decision stream |
| **Phase 5: Admin & Config** | 6 weeks | 2 developers | Agent config, provisioning, directives, email signals |
| **Phase 6: Simulation** | 4 weeks | 2 developers | Beer Game OWL UI, WebSocket integration |
| **Phase 7: Advanced Features** | 8 weeks | 3 developers | AAP, knowledge base, skills, conformal UI |
| **Phase 8: Testing & Polish** | 8 weeks | 4 developers | Integration testing, Odoo upgrade compatibility, App Store submission |
| **Total** | **~58 weeks** | **8 avg** | **~45 person-months** |

### 14.2 Ongoing Maintenance Burden

| Item | Current Platform | Odoo Fork |
|------|-----------------|-----------|
| Odoo version upgrades | N/A | 2-4 weeks per annual release (test all modules) |
| Odoo security patches | N/A | Immediate application required |
| Module compatibility | N/A | Test against Odoo Enterprise + OCA modules |
| Dual codebase maintenance | 1 codebase | 2 codebases (Odoo modules + Intelligence service) |
| AI/ML development | Unified | Split across two repos, two deployment targets |
| CI/CD | Docker-based | Odoo module testing + Docker for intelligence |

---

## 15. Risk Assessment

### 15.1 High Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **OWL frontend immaturity** | High | High | OWL ecosystem is tiny (Odoo developers only). No MUI equivalent, limited charting. Custom components require deep OWL expertise. |
| **Odoo ORM performance ceiling** | High | High | Complex planning queries (multi-level BOM explosion, time-phased netting) may hit ORM limits. Raw SQL bypasses security. |
| **SOC II compliance gap** | High | Critical | ORM-only security is insufficient for multi-tenant AI training. DB-level controls needed but non-standard for Odoo. |
| **Intelligence layer latency** | Medium | High | Every AI decision adds network hop. TRM <10ms target becomes <25ms. Acceptable? |
| **Dual codebase divergence** | High | Medium | Odoo modules and intelligence service can drift. Schema changes must be coordinated. |
| **Odoo upgrade breakage** | Medium | High | Odoo's annual releases regularly break third-party modules. Requires dedicated QA per release. |

### 15.2 Medium Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Odoo.sh limitations** | Medium | Medium | Cloud customers expect SaaS. Odoo.sh can't run GPU workloads. Must offer self-hosted or hybrid. |
| **App Store approval** | Low | High | Odoo reviews apps for quality. Complex modules with external service dependencies may face scrutiny. |
| **Team skill gap** | High | Medium | Current team knows FastAPI/React. Odoo ORM/OWL is a different skill set. Training needed. |
| **Market cannibalization** | Medium | Medium | Odoo-only positioning may confuse existing SAP/D365 pipeline. |

### 15.3 Low Risks

| Risk | Probability | Impact |
|------|-------------|--------|
| **Database migration** | Low | Medium | Both use PostgreSQL. Data migration is SQL-level. |
| **AI algorithm portability** | Low | Low | PyTorch code is Python — runs anywhere with GPU. |
| **Odoo community support** | Low | Low | Large community, OCA modules fill gaps. |

---

## 16. Alternative: Hybrid Architecture

Instead of a full fork, consider a **thin Odoo shell** that keeps the intelligence layer intact:

### 16.1 Hybrid Approach

```
┌─────────────────────────────────────────────┐
│            Odoo (Thin Shell)                 │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │  autonomy_bridge module              │   │
│  │  - Odoo menu items → iframe/embed    │   │
│  │  - Odoo models sync ↔ Autonomy DB   │   │
│  │  - ir.cron triggers → Autonomy API   │   │
│  │  - SSO passthrough                   │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  Standard Odoo: MRP, Inventory, Sales, etc. │
└──────────────────┬──────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────┐
│      Autonomy Platform (Current Stack)       │
│      FastAPI + React + PyTorch + PostgreSQL  │
│      (Unchanged, full feature set)           │
└─────────────────────────────────────────────┘
```

### 16.2 Hybrid Advantages

| Advantage | Details |
|-----------|---------|
| **Preserve all features** | No capability loss |
| **Minimal conversion effort** | ~3 months for bridge module |
| **Single codebase** | Intelligence + UI stay unified |
| **SOC II unchanged** | PostgreSQL RLS stays in place |
| **ERP-agnostic preserved** | Can still serve SAP/D365 customers |
| **Odoo App Store eligible** | Bridge module is a valid Odoo app |
| **Incremental migration** | Move features to native Odoo over time as needed |

### 16.3 Hybrid Disadvantages

| Disadvantage | Details |
|--------------|---------|
| **Not "native" Odoo** | Iframe/embed feels bolted-on to Odoo purists |
| **Two UI languages** | Odoo (Bootstrap) + Autonomy (MUI) side by side |
| **Two auth systems** | SSO passthrough adds complexity |
| **Partner skepticism** | Odoo partners may prefer fully native solutions |

---

## 17. Recommendation

### 17.1 Decision Matrix

| Factor | Weight | Full Fork | Hybrid | Current (Integration) |
|--------|--------|-----------|--------|-----------------------|
| **Odoo market access** | 25% | 9/10 | 7/10 | 4/10 |
| **Feature preservation** | 25% | 4/10 | 9/10 | 10/10 |
| **Time to market** | 20% | 2/10 | 8/10 | 10/10 |
| **Engineering risk** | 15% | 3/10 | 7/10 | 9/10 |
| **SOC II compliance** | 10% | 4/10 | 9/10 | 10/10 |
| **Long-term maintainability** | 5% | 5/10 | 6/10 | 8/10 |
| **Weighted Score** | | **4.85** | **7.85** | **8.20** |

### 17.2 Verdict

**A full Odoo fork is not recommended at this time.** The conversion effort (~45 person-months, 18-24 months) destroys more value than it creates:

1. **65% of the backend cannot run inside Odoo** — the intelligence layer must be a separate service regardless, making "native Odoo" a misnomer for the platform's core value.

2. **The AWS SC data model is an asset, not a liability.** It enables ERP-agnostic positioning (SAP + D365 + Odoo customers all feed into the same AI training pipeline). Replacing it with Odoo's data model locks out 80%+ of the addressable market.

3. **The frontend rewrite yields negative ROI.** Rewriting 96+ React pages in OWL abandons the MUI/Recharts/D3 ecosystem for a smaller, less capable framework — while the distinctive visualizations (Sankey, probabilistic scorecards, TRM hive) must still be custom-built.

4. **SOC II compliance becomes harder, not easier.** Odoo's ORM-level security is weaker than PostgreSQL RLS for multi-tenant AI workloads.

### 17.3 Recommended Path

**Pursue the Hybrid approach (Option B)** — build a thin `autonomy_bridge` Odoo module that:

1. Adds Autonomy menu items in Odoo's navigation
2. Embeds Autonomy's React UI via iframe/web component for planning and AI features
3. Syncs Odoo MRP/inventory/sales data to Autonomy's AWS SC model (the existing Odoo connector already does this)
4. Triggers AI workflows from Odoo events via ir.cron → Autonomy API
5. Displays AI recommendations as Odoo activities (`mail.activity`) on relevant MOs, POs, SOs

This preserves 100% of Autonomy's capabilities, maintains ERP-agnostic positioning, keeps SOC II compliance intact, and is achievable in **~3 months** with **2 developers** — versus 18-24 months and 8 developers for a full fork.

The bridge module is a legitimate Odoo App Store submission and gives Odoo customers a seamless experience without sacrificing the platform's core architecture.

---

## Appendix A: Odoo Technical Constraints Summary

| Constraint | Value | Source |
|-----------|-------|--------|
| Worker memory hard limit | 768 MB | Odoo server configuration |
| Worker memory soft limit | 640 MB | Odoo server configuration |
| Users per worker | ~6 | Odoo deployment guide |
| Max workers (Odoo.sh shared) | 8 | Odoo.sh pricing page |
| GPU support | None | Odoo.sh / standard Odoo |
| Async execution | None | Werkzeug WSGI (synchronous) |
| WebSocket support | None (bus.bus longpolling only) | Odoo architecture |
| pgvector support | None | Odoo ORM |
| Native job queue | ir.cron (single-threaded, fragile) | Odoo documentation |
| JSON-RPC deprecation | Odoo 22 (fall 2028) | Odoo 19 release notes |
| OWL framework ecosystem | Odoo developers only | OWL GitHub |
| Enterprise features required | MPS, Quality, PLM, IoT, Gantt | Odoo editions comparison |

## Appendix B: Odoo Data Model Quick Reference

| Odoo Model | Table | AWS SC Equivalent | Notes |
|-----------|-------|-------------------|-------|
| `res.company` | res_company | tenant | Multi-company = multi-tenant |
| `res.partner` | res_partner | trading_partner | Unified customer+vendor+contact |
| `stock.warehouse` | stock_warehouse | site | With `stock.location` hierarchy |
| `stock.location` | stock_location | (sub-site) | Hierarchical within warehouse |
| `product.template` | product_template | (header) | Product header |
| `product.product` | product_product | product | Product variant |
| `mrp.bom` | mrp_bom | product_bom (header) | BOM header |
| `mrp.bom.line` | mrp_bom_line | product_bom (detail) | BOM components |
| `stock.warehouse.orderpoint` | stock_warehouse_orderpoint | inv_policy | Min/max only |
| `stock.quant` | stock_quant | inv_level | Location-level qty |
| `purchase.order` | purchase_order | supply_plan (buy) | PO header |
| `purchase.order.line` | purchase_order_line | inbound_order_line | PO detail |
| `sale.order` | sale_order | (demand source) | SO header |
| `sale.order.line` | sale_order_line | outbound_order_line | SO detail |
| `mrp.production` | mrp_production | supply_plan (make) | Manufacturing order |
| `stock.picking` | stock_picking | shipment / supply_plan (transfer) | Inventory transfer |
| `stock.move` | stock_move | (movement detail) | Individual item movement |
| `stock.route` | stock_route | (routing) | Pull/push rules |
| `stock.rule` | stock_rule | sourcing_rules | Procurement rules |
| `product.supplierinfo` | product_supplierinfo | vendor_product | Vendor-product link |
| `mrp.workcenter` | mrp_workcenter | production_process | Work center |
| `quality.check` | quality_check | (quality) | Enterprise only |
| `maintenance.equipment` | maintenance_equipment | (asset) | Enterprise only |
| — | — | forecast | **No equivalent** |
| — | — | supply_plan (unified) | **No equivalent** |
| — | — | supply_demand_pegging | **No equivalent** |
| — | — | powell_* (27 tables) | **No equivalent** |

## Appendix C: References

- Odoo 19 Architecture: https://www.odoo.com/documentation/19.0/developer/tutorials/server_framework_101/01_architecture.html
- OWL Framework: https://github.com/odoo/owl
- Odoo.sh Pricing: https://www.odoo.sh/pricing
- Odoo MPS Documentation: https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/workflows/use_mps.html
- frePPLe "5 Things Odoo MRP Doesn't Do": https://frepple.com/blog/five_things_odoo_mrp_doesnt_do/
- Odoo 19 External API: https://www.odoo.com/documentation/19.0/developer/reference/external_api.html
- Odoo Enterprise vs Community: https://www.odoo.com/page/editions
