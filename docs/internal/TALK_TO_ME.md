# Talk to Me — Natural Language Directive Capture & Query Routing

## Overview

"Talk to Me" is a persistent AI prompt bar in the TopNavbar that accepts natural language input from any authenticated user. The system handles two modes:

1. **Directives**: Actionable instructions ("increase service levels by 5% in the SW region") are parsed, gap-checked, and routed to the appropriate Powell Cascade layer.
2. **Questions**: Informational queries ("show me overdue POs" or "what's our inventory at the Dallas DC?") are answered inline and optionally navigate the user to the relevant page with pre-applied filters.

This is the primary human-to-AI input channel for the Autonomy platform — where the "agentic operating model" meets human judgment.

## Architecture

### Two-Phase Flow

```
User types directive in TopNavbar
        |
        v
Phase 1: POST /directives/analyze
        |  LLM parses → structured fields + missing_fields list
        |
        v
  ┌─────────────────────────────┐
  │  is_complete?               │
  │  (missing_fields empty)     │
  ├─────────┬───────────────────┤
  │  YES    │  NO               │
  │         │                   │
  │  Submit │  Show clarification│
  │  now    │  panel with        │
  │         │  questions         │
  │         │         |          │
  │         │  User answers all  │
  │         │         |          │
  └─────┬───┴─────────┘         │
        v                       │
Phase 2: POST /directives/submit│
        |  Original text + clarifications dict
        |  → LLM re-parse with enriched context
        |  → Persist UserDirective
        |  → Route to Powell layer
        |  → Auto-apply if confidence ≥ 0.7
        v
  Decision Stream alert + effectiveness tracking
```

### Required Fields (Gap Detection)

Every actionable directive requires ALL of these dimensions. If any are missing, the clarification panel shows the appropriate input:

| Field | Input Type | Always Required? | Notes |
|-------|-----------|-----------------|-------|
| **Reason/justification** | Text | YES | WHY — "customer feedback", "Q3 targets", "supplier delays" |
| **Direction** | Select | YES | increase / decrease / maintain / reallocate |
| **Metric** | Select | YES | revenue / cost / service_level / inventory / capacity / quality / lead_time |
| **Magnitude** | Number | YES | By what percentage (e.g., 10%) |
| **Duration** | Select | YES | 2 weeks / 1 month / 1 quarter / 6 months / 1 year |
| **Geography** | Select | Lenient for strategic | Which sites/regions — VP/Executive can target "all sites" |
| **Products** | Select | Lenient for strategic | Which product families — VP/Executive can target "all products" |

The reason field is **always** required. A directive without justification ("increase revenue") cannot be tracked for effectiveness. Good reasons cite evidence: "customer feedback indicates growing demand in SW region", "market intelligence suggests competitor price cut in Q2".

### Powell Layer Routing

The user's `powell_role` determines which layer receives the directive:

| User Role | Target Layer | What Happens |
|-----------|-------------|-------------|
| VP / Executive | Layer 4: S&OP GraphSAGE | Network-wide policy parameter adjustment (θ) |
| S&OP Director | Layer 2: Execution tGNN | Multi-site daily directives and allocation priorities |
| MPS / Allocation Manager | Layer 1.5: Site tGNN | Single-site cross-TRM urgency modulation |
| Analysts (ATP, PO, etc.) | Layer 1: Individual TRM | Specific execution decision at a single site |

Tenant Admins default to the strategic layer.

### Directive Lifecycle

```
PARSED → APPLIED → MEASURED
```

1. **PARSED**: LLM extraction complete, structured fields populated
2. **APPLIED**: Routed to target layer, actions created (if confidence ≥ 0.7)
3. **MEASURED**: Time horizon expired, effectiveness delta computed

Effectiveness tracking uses Bayesian posteriors per `(user_id, directive_type)` to learn which users and directive types actually improve outcomes.

## Implementation

### Backend

| File | Purpose |
|------|---------|
| `backend/app/services/directive_service.py` | LLM parsing, gap detection, routing, effectiveness collection |
| `backend/app/api/endpoints/user_directives.py` | REST API — analyze, submit, list, get |
| `backend/app/models/user_directive.py` | `UserDirective` model + `ConfigProvisioningStatus` model |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/src/components/TopNavbar.jsx` | "Talk to me" input bar + clarification panel |

### API Endpoints

```
POST /api/v1/directives/analyze    — Parse + gap detect (no persist)
POST /api/v1/directives/submit     — Persist + route (with clarifications)
GET  /api/v1/directives/           — List recent directives for tenant
GET  /api/v1/directives/{id}       — Get single directive by ID
```

### Database

**Table: `user_directives`**

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | Auto-increment |
| user_id | FK → users | Who submitted |
| config_id | FK → supply_chain_configs | Which SC config |
| tenant_id | FK → tenants | Tenant boundary |
| raw_text | Text | Original natural language |
| directive_type | String(50) | e.g., STRATEGIC_REVENUE_TARGET |
| reason_code | String(100) | Same or more specific |
| parsed_intent | String(30) | directive / observation / question |
| parsed_scope | JSON | {region, product_family, site_keys, product_ids, time_horizon_weeks} |
| parsed_direction | String(20) | increase / decrease / maintain / reallocate |
| parsed_metric | String(50) | revenue / cost / service_level / etc. |
| parsed_magnitude_pct | Float | e.g., 10.0 for "10%" |
| parser_confidence | Float | 0-1 LLM confidence |
| target_layer | String(20) | strategic / tactical / operational / execution |
| target_trm_types | JSON | ["forecast_adjustment", "inventory_buffer"] |
| target_site_keys | JSON | ["FOODDIST_DC"] |
| status | String(20) | PARSED → APPLIED → MEASURED |
| routed_actions | JSON | Array of routing actions with layer/trm_type |
| effectiveness_delta | Float | Post-measurement outcome delta |
| effectiveness_scope | String(20) | network / region / site |

**Indexes**: user_id, config_id, (tenant_id, status), created_at

## Provisioning Stepper

The 14-step Powell Cascade warm-start pipeline bootstraps all AI layers before they can receive directives. A directive routed to an unprovisioned layer has nowhere to go — provisioning ensures readiness.

See **[PROVISIONING_STEPPER.md](PROVISIONING_STEPPER.md)** for full step definitions, dependency graph, and conformal calibration details.

## Query Routing (Question Mode)

When the LLM classifies a prompt as a **question** (not a directive), the system answers inline and identifies the most relevant page to navigate to, with pre-applied filters.

### Dual-Strategy Architecture

```
User asks a question in TopNavbar
        |
        v
POST /directives/analyze  (intent: "question")
        |
        v
  ┌─────────────────────────────────┐
  │  Option A: LLM Routing (primary)│
  │  Route context injected into    │
  │  prompt — LLM returns answer +  │
  │  target_page + filters          │
  ├─────────────────────────────────┤
  │  Option B: TF-IDF Embedding     │
  │  (fallback when LLM doesn't     │
  │  suggest a page)                │
  │  Cosine similarity on route     │
  │  descriptions + keywords        │
  └─────────────────────────────────┘
        |
        v
  TopNavbar shows answer panel
  + "Go to [page]" button if target_page found
        |
        v
  navigate(target_page, { state: { filters } })
  → Target page hydrates filters on mount
```

### Route Registry

The route registry (`backend/app/services/query_router.py`) contains ~60 route entries covering:

- Decision Stream, Executive Briefing
- Planning Cascade (MPS, MRP, S&OP)
- Demand/Supply/Inventory Planning
- All 11 TRM Worklists (ATP, PO, Rebalancing, MO, TO, Quality, Maintenance, Subcontracting, Forecast Adj, Buffer, Order Tracking)
- Orders, Capacity, Analytics
- Admin pages (AI/Agents, SAP, Email Signals)

Each route entry includes:
- **path**: Frontend route (e.g., `/planning/atp-worklist`)
- **label**: Human-readable name
- **description**: Semantic description for LLM/embedding matching
- **keywords**: Search terms
- **capability**: Required user capability (routes are filtered by user access)
- **filters**: Available filter parameters for that page
- **category**: Grouping for organized LLM context

### Filter Hydration

Target pages read `location.state.filters` on mount and apply them:

| Page Type | Supported Filters |
|-----------|-------------------|
| TRM Worklists (11 pages) | `status` (INFORMED/ACTIONED/INSPECTED/OVERRIDDEN) |
| Demand Plan View | `product`, `site`, `start_date`, `end_date` |
| Inventory Optimization | `tab` (policies/optimizations) |
| Decision Stream | Converted to initial chat message |

### Example Interactions

| User Query | Answer | Navigation |
|-----------|--------|------------|
| "Show me overdue POs" | "Here are your overdue purchase orders..." | → PO Worklist (status: INFORMED) |
| "What's inventory at Dallas DC?" | "Current inventory levels at Dallas DC..." | → Inventory Optimization |
| "Any ATP decisions pending?" | "You have 12 pending ATP fulfillment decisions..." | → ATP Worklist |
| "How's demand trending for beverages?" | "Beverage demand forecast shows..." | → Demand Plan View (product: beverages) |

### Implementation

| File | Purpose |
|------|---------|
| `backend/app/services/query_router.py` | Route registry, TF-IDF embedding fallback, capability filtering |
| `backend/app/services/directive_service.py` | LLM routing in `_answer_question()`, embedding fallback integration |
| `frontend/src/components/TopNavbar.jsx` | "Go to page" button in answer panel |
| `frontend/src/pages/planning/*WorklistPage.jsx` | `initialStatusFilter` from location state |
| `frontend/src/pages/planning/DemandPlanView.jsx` | Filter hydration from location state |
| `frontend/src/pages/planning/InventoryOptimization.jsx` | Tab hydration from location state |

## Design Principles

1. **Reason always required** — A desire without justification ("increase revenue") is not actionable. The system insists on the "why" so effectiveness can be tracked.

2. **Strategic leniency** — VP/Executive directives legitimately target the entire network. Geography and product scope are not marked missing for strategic-layer directives.

3. **Clarification, not rejection** — If the directive is incomplete, the system asks clarifying questions rather than failing. This follows the "Ask Why" UX pattern from the Agentic Authorization Protocol.

4. **Confidence-gated auto-apply** — Only directives with ≥0.7 confidence are auto-routed. Below that threshold, the directive is persisted but not applied until a human reviews.

5. **Heuristic fallback** — When the LLM is unavailable (vLLM down, air-gapped), a regex-based heuristic parser provides basic extraction. It won't be as accurate but maintains availability.
