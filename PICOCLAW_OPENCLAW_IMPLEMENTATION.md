# PicoClaw & OpenClaw Implementation Plan

**Created**: 2026-02-19
**Status**: PROPOSED
**Dependencies**: Self-hosted LLM (vLLM + Qwen 3), Autonomy REST API (existing)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Enterprise-Scale Analysis](#enterprise-scale-analysis)
3. [Architecture Overview](#architecture-overview)
4. [Phase 1: OpenClaw Chat Interface](#phase-1-openclaw-chat-interface-lowest-risk-highest-value)
5. [Phase 2: PicoClaw Edge CDC Monitors](#phase-2-picoclaw-edge-cdc-monitors)
6. [Phase 3: Multi-Agent Authorization Protocol](#phase-3-multi-agent-authorization-protocol)
7. [Phase 4: PicoClaw Simulation Swarm](#phase-4-picoclaw-simulation-swarm)
8. [Self-Hosted LLM Infrastructure](#self-hosted-llm-infrastructure)
9. [Security & Risk Mitigation](#security--risk-mitigation)
10. [Cost Analysis](#cost-analysis)
11. [Success Metrics](#success-metrics)

---

## Executive Summary

This document defines the implementation plan for integrating PicoClaw and OpenClaw agent runtimes with the Autonomy platform. These frameworks act as **thin orchestration layers** wrapping existing Autonomy REST APIs — they do not replace the core Powell computation (TRM, GNN, MRP engines) but provide three new capabilities:

1. **Chat-based planning interface** (OpenClaw) — planners interact via WhatsApp/Slack/Teams instead of only the React frontend
2. **Edge CDC monitoring** (PicoClaw) — distributed, ultra-lightweight deterministic site monitoring on $10 hardware
3. **Human escalation for authorization** (OpenClaw) — format agent-unresolvable decisions for human review; agent-to-agent uses existing `ConditionMonitorService`

All three capabilities consume the **same Autonomy REST API** that already exists. No backend computation changes are required.

**CRITICAL**: At enterprise scale (223 sites, 300K SKUs), PicoClaw and OpenClaw must operate as **deterministic gateways with LLM escalation**, not as LLM-first agents. See [Enterprise-Scale Analysis](#enterprise-scale-analysis) for volume projections and the tiered intelligence model that keeps LLM costs tractable.

---

## Enterprise-Scale Analysis

**Reference Network**: 10 local DCs, 3 regional DCs, 10 manufacturing sites, 100 suppliers, 100 customers, 300,000 sold items.

### Network Dimensions

| Entity | Count | Master Type | Role |
|---|---|---|---|
| Local DCs | 10 | INVENTORY | Storage/fulfillment |
| Regional DCs | 3 | INVENTORY | Aggregation/cross-dock |
| Manufacturing sites | 10 | MANUFACTURER | Production with BOM |
| Suppliers | 100 | MARKET_SUPPLY | Raw material / component source |
| Customers | 100 | MARKET_DEMAND | End demand |
| **Total sites** | **223** | | All requiring monitoring |
| Sold items (SKUs) | 300,000 | | Finished goods catalog |
| **Product-site pairs** | **~3.9M** | | 300K SKUs × 13 stocking locations |

### Daily Volume Projections

| Operation | Volume/Day | Latency Requirement | Correct Tier |
|---|---|---|---|
| **ATP checks** | 50K-200K | <100ms | Tier 1: AATP Engine (deterministic) |
| **CDC threshold checks** | 10,704 (223 × 48) | Seconds | Tier 1: Arithmetic comparison |
| **Condition scans** | ~3.9M product-site pairs | Minutes (batch) | Tier 1: SQL aggregate queries |
| **MRP explosion** | 300K SKUs × 13 sites | Hours (nightly batch) | Tier 1: MRPEngine |
| **TRM exception handling** | 5K-20K | <10ms | Tier 2: TRM heads |
| **Agent-to-agent authorization** | 500-2,000 | <500ms | Tier 2: ConditionMonitor supply requests |
| **PO timing adjustments** | 5K-20K | <10ms | Tier 2: TRM PO timing head |
| **Planner chat interactions** | 500-1,500 | <5s | Tier 3: LLM (Qwen 3) |
| **Human escalations** | 50-200 | <10s | Tier 3: LLM (Qwen 3) |
| **KPI digests / reports** | 200-500 | <30s | Tier 3: LLM (Qwen 3) |
| **Novel exceptions** | 50-100 | <30s | Tier 3: LLM (Qwen 3) |

### What Breaks If Everything Uses LLM

If PicoClaw CDC monitoring and OpenClaw authorization both route through the LLM (as originally proposed for small networks):

| Workload | LLM Calls/Day | Problem |
|---|---|---|
| CDC monitoring (223 sites × 48/day × 1-3 LLM calls) | 10K-32K | **Consumes 12-37% of single-GPU LLM capacity** for pure arithmetic |
| Authorization protocol (500-2K requests × 2-4 LLM calls) | 1K-8K | **60s latency** per authorization vs 500ms deterministic |
| ATP checks via LLM | N/A | **Physically impossible**: 200K × 2s = 111 hours/day |
| **Total LLM calls** | **11.5K-40K/day** | Peak bursts during disruptions could 3-5x |

A single Qwen 3 8B instance handles ~86K calls/day theoretical max (1/sec). Normal operation barely fits. Supply disruption spikes would collapse the system.

### Tiered Intelligence Model (Enterprise-Scale)

**The fundamental rule: LLM touches <1% of decisions.** The existing deterministic engines and TRM heads handle everything else.

```
TIER 3: LLM (Strategic + Human Interaction)     ~800-2,300 calls/day
  ├─ Planner chat (WhatsApp/Slack via OpenClaw)    500-1,500
  ├─ Human escalation formatting                    50-200
  ├─ KPI digest generation                          200-500
  └─ Novel exception reasoning                      50-100
  Infrastructure: 1× Qwen 3 8B (8GB VRAM) — comfortable headroom

TIER 2: TRM/GNN (Learned Adjustments)           ~10K-40K inferences/day
  ├─ ATP exception handling (shortages only)        5K-20K
  ├─ PO timing adjustments                         5K-20K
  ├─ Safety stock multiplier adjustments            223/day
  ├─ Agent-to-agent supply requests                 500-2,000
  └─ CDC-triggered parameter recalibration          10-50
  Infrastructure: Existing GPU (PyTorch, <10ms per inference)

TIER 1: Deterministic Engines (Core)             ~250K-700K operations/day
  ├─ AATP consumption (priority-based)              50K-200K
  ├─ MRP netting + BOM explosion                    300K SKUs (nightly)
  ├─ Safety stock calculation (4 policy types)      3.9M pairs (nightly)
  ├─ CDC threshold comparison (arithmetic)          10,704
  ├─ Condition detection (SQL queries)              Hourly batch
  └─ Order tracking exception flags                 10K-50K
  Infrastructure: Existing CPU backend
```

### Revised PicoClaw Role at Enterprise Scale

PicoClaw instances must operate as **deterministic gateways** — they call the Autonomy API, apply simple if/else logic locally, and route alerts through their gateway. LLM calls are reserved for human-initiated interactions.

```
PicoClaw (per site, deterministic mode):

  HEARTBEAT (every 30 min — NO LLM):
    1. GET /api/v1/site-agent/cdc/status/{site_key}
    2. Parse response JSON (simple field access, no LLM)
    3. IF severity >= CRITICAL → send gateway alert
    4. IF severity >= WARNING → buffer for next digest
    5. ELSE → log timestamp, done

  DIGEST (every 4 hours — NO LLM):
    1. Compile buffered warnings from MEMORY.md
    2. Format as structured text (template-based)
    3. Send to channel via gateway

  HUMAN QUESTION (on-demand — LLM):
    1. Planner asks via Telegram: "Why is DC-East in shortage?"
    2. NOW call LLM to reason over context
    3. ~5-20 LLM calls/site/day (vs 48+ in naive approach)
```

**LLM call reduction**: 10K-32K/day → **1.1K-4.5K/day** (7-10× reduction).

### Revised OpenClaw Role at Enterprise Scale

OpenClaw serves **human planners only** — not as the inter-agent communication layer. Agent-to-agent authorization uses the existing `ConditionMonitorService` supply request pattern (pure Python, <500ms, no LLM).

```
Agent-to-Agent (Tier 2 — NO LLM):
  SiteAgent A → ConditionMonitor.create_supply_request()  ← DB write
  SiteAgent B → get_pending_supply_requests()              ← DB query
  SiteAgent B → respond_to_supply_request()                ← DB write
  Volume: 500-2,000/day at <500ms each

Human Escalation (Tier 3 — OpenClaw + LLM):
  Agent resolution confidence < threshold → OpenClaw formats escalation
  Planner sees ranked options with Balanced Scorecard via chat
  Planner responds: "Approve option 2 because..."
  Override captured for RLHF
  Volume: 50-200/day (10-15% escalation rate)
```

### Revised LLM Infrastructure Sizing

| Scale | Sites | SKUs | LLM Calls/Day | Required LLM Infrastructure |
|---|---|---|---|---|
| **Pilot** | 4-8 | 100-500 | 200-800 | Qwen 3 8B, shared GPU |
| **Department** | 20-50 | 5K-20K | 800-3,000 | Qwen 3 8B, shared GPU |
| **Division** | 50-100 | 50K-100K | 1,500-5,000 | Qwen 3 14B, dedicated GPU |
| **Enterprise** | 200+ | 300K+ | 2,000-7,000 | Qwen 3 14B, dedicated GPU |
| **Enterprise + disruption spike** | 200+ | 300K+ | 5,000-20,000 | Qwen 3 32B or 2× Qwen 3 14B |

**Key insight**: Even at enterprise scale with 223 sites and 300K SKUs, the tiered architecture keeps LLM calls under 7K/day normal, 20K/day peak — well within a single dedicated GPU's capacity. The tiered model is what makes this tractable, not bigger hardware.

---

## Architecture Overview

### Enterprise-Scale (223 Sites, 300K SKUs)

```
┌─────────────────────────────────────────────────────────────────┐
│  TIER 3: HUMAN + LLM (<1% of decisions, ~2K-7K LLM calls/day)  │
│                                                                  │
│  OpenClaw (Human Interface ONLY — not agent-to-agent)            │
│  ├─ 5-15 Supply Planner sessions (WhatsApp/Slack/Teams)          │
│  ├─ Human escalation formatting (50-200/day)                     │
│  ├─ KPI digests / ask-why / override capture                     │
│  └─ Novel exception reasoning                                    │
│                                                                  │
├────────────────────┬─────────────────────────────────────────────┤
│                    │ REST API                                    │
│                    ▼                                             │
│  TIER 2: LEARNED (TRM/GNN, ~10K-40K inferences/day, <10ms)      │
│                                                                  │
│  Autonomy Backend (FastAPI + Powell)                              │
│  ├─ TRM: ATP exception, PO timing, safety stock adjustment       │
│  ├─ GNN: Network-wide priority allocations                       │
│  ├─ Agent-to-Agent: ConditionMonitor supply requests (<500ms)    │
│  ├─ Decision Integration (audit + RLHF)                          │
│  └─ Self-Hosted LLM (vLLM + Qwen 3) — serves Tier 3 only        │
│                                                                  │
├────────────────────┬─────────────────────────────────────────────┤
│                    │ REST API                                    │
│                    ▼                                             │
│  TIER 1: DETERMINISTIC (250K-700K ops/day, <10ms each)           │
│                                                                  │
│  Autonomy Engines                                                │
│  ├─ AATP Engine: 50K-200K ATP checks/day                         │
│  ├─ MRP Engine: 300K SKU nightly explosion                       │
│  ├─ Safety Stock Calculator: 3.9M product-site pairs             │
│  ├─ CDC Monitor: Arithmetic threshold comparison                  │
│  └─ Condition Monitor: SQL-based persistent condition detection   │
│                                                                  │
├────────────────────┬─────────────────────────────────────────────┤
│                    │ REST API (heartbeat)                        │
│                    ▼                                             │
│  EDGE LAYER: PicoClaw Swarm (deterministic gateway, NO LLM)     │
│                                                                  │
│  223 PicoClaw instances (10 LDC + 3 RDC + 10 MFG + 100 SUP      │
│                          + 100 CUST)                             │
│  ├─ Heartbeat: GET CDC status → if/else → gateway alert          │
│  ├─ Digest: Compile warnings → template format → send            │
│  ├─ LLM call ONLY on human question via chat gateway              │
│  └─ Each: <10MB RAM, 30-min cycle, ~5-20 LLM calls/day max      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Small-Network Mode (Pilot, 4-8 Sites)

For pilot deployments and Beer Game simulations, the original LLM-first architecture is viable:

```
OpenClaw (Chat + Agent-to-Agent via sessions_send)
    │ REST API
    ▼
Autonomy Backend + Self-Hosted LLM
    │ REST API
    ▼
PicoClaw Swarm (LLM-based heartbeats OK at 4-8 sites)
```

The system auto-detects scale: below 50 sites, PicoClaw can use LLM for richer heartbeat analysis. Above 50 sites, it switches to deterministic mode.

---

## Phase 1: OpenClaw Chat Interface (Lowest Risk, Highest Value)

**Timeline**: 2-3 weeks
**Prerequisites**: Self-hosted LLM running (see [Self-Hosted LLM Infrastructure](#self-hosted-llm-infrastructure))
**Effort**: Low — no Autonomy backend changes required

### 1.1 Install & Configure OpenClaw

```bash
# Install OpenClaw
curl -fsSL https://openclaw.ai/install.sh | bash

# Initialize workspace
openclaw init

# Configure LLM provider (point to local vLLM)
cat > ~/.openclaw/openclaw.json << 'EOF'
{
  "agent": {
    "model": "qwen3-8b",
    "providers": {
      "custom": {
        "api_key": "not-needed",
        "api_base": "http://localhost:8100/v1"
      }
    }
  }
}
EOF
```

### 1.2 Create Autonomy AgentSkills

Create skill packages in `~/.openclaw/workspace/skills/`:

**Skill: supply-plan-query**
```
~/.openclaw/workspace/skills/supply-plan-query/
└── SKILL.md
```

```markdown
# supply-plan-query

## Description
Query the current supply plan for a product-site combination.

## Triggers
- "Show me the supply plan for {product} at {site}"
- "What's the plan for {product}?"
- "Supply plan status"

## Implementation
1. Authenticate: POST /api/v1/auth/login (cached JWT)
2. Query: GET /api/v1/supply-plan?product={product}&site={site}
3. Format response with: demand, on-hand, safety stock, planned orders, OTIF forecast
4. If no results, suggest checking config_id or product name spelling
```

**Skill: atp-check**
```markdown
# atp-check

## Description
Check Available-to-Promise for an order.

## Triggers
- "Can we promise {qty} of {product} at {site} by {date}?"
- "ATP check for order {order_id}"
- "What can we ship?"

## Implementation
1. POST /api/v1/site-agent/atp/check
   Body: { "order_id": "{order_id}", "product_id": "{product}", "site_key": "{site}", "requested_qty": {qty}, "priority": {priority} }
2. Return: promised_qty, promise_date, source (deterministic vs trm_adjusted), confidence
3. If shortage, explain: "Only {available} of {requested} available. TRM suggests: {explanation}"
```

**Skill: override-decision**
```markdown
# override-decision

## Description
Override an agent recommendation with human reasoning. Feeds into RLHF training loop.

## Triggers
- "Override {decision_id}. Reason: {reason}"
- "Reject recommendation for {order_id} because {reason}"
- "I disagree with {decision}. {reason}"

## Implementation
1. Parse decision_id and reason from message
2. POST /api/v1/site-agent/decisions/{decision_id}/override
   Body: { "accepted": false, "reason": "{reason}", "human_feedback": "{full_message}" }
3. Confirm: "Override recorded for {decision_id}. Your reasoning will be used to improve future decisions."
```

**Skill: ask-why**
```markdown
# ask-why

## Description
Get agent reasoning for a specific decision.

## Triggers
- "Why did you recommend {action}?"
- "Explain decision {decision_id}"
- "Ask why for {order_id}"

## Implementation
1. GET /api/v1/planning-cascade/trm-decision/{decision_id}/ask-why?level=NORMAL
2. Response contains `ContextAwareExplanation` with:
   - `authority`: agent classification (UNILATERAL/REQUIRES_AUTH/ADVISORY), authority level, approval chain
   - `guardrails`: CDC threshold status (WITHIN/APPROACHING/EXCEEDED) per metric
   - `attribution`: top-5 feature importances from gradient saliency
   - `counterfactuals`: nearest threshold boundaries that would change the outcome
   - `summary` + `explanation` at requested verbosity level
3. Format natural language explanation from template:
   - "The deterministic engine found {shortage} units shortage for {product} at {site}."
   - "The TRM model (confidence: {confidence}) suggested {action} — {authority_statement}."
   - "Top driver: {top_feature} ({importance}%). {guardrail_summary}."
   - "Impact: {fill_rate}% fill rate, estimated cost ${cost}."
4. Fallback: GET /api/v1/site-agent/decisions/{decision_id} for legacy format
```

**Skill: kpi-dashboard**
```markdown
# kpi-dashboard

## Description
Generate a KPI summary digest.

## Triggers
- "Dashboard"
- "KPI summary"
- "How are we doing?"

## Implementation
1. GET /api/v1/site-agent/status (all active agents)
2. GET /api/v1/inventory/levels?summary=true
3. GET /api/v1/supply-plan/latest/scorecard
4. Format digest:
   - Service Level: {otif}%
   - Inventory: ${total_value} ({dos} days of supply)
   - Open Exceptions: {count} ({critical} critical)
   - Agent Touchless Rate: {rate}%
   - Pending Human Decisions: {count}
```

### 1.3 Configure Agent Persona

```markdown
# ~/.openclaw/workspace/SOUL.md

You are an AI Supply Planner for {company_name}, powered by the Autonomy platform.

## Behavior
- Be concise and data-driven. Cite specific numbers from API responses.
- When presenting recommendations, always include confidence scores.
- When a planner overrides a recommendation, acknowledge it and confirm the override was recorded.
- Proactively surface exceptions from the worklist when conversation is idle.
- Never fabricate data. If the API returns an error, say so and suggest next steps.

## Communication Style
- Professional but approachable
- Use supply chain terminology (OTIF, DOS, safety stock, ATP)
- Format numbers: quantities as integers, percentages to 1 decimal, currency with $ and commas

## Authority
- READ: All planning data, KPIs, agent decisions, inventory levels
- SUGGEST: Recommendations with reasoning
- CANNOT: Approve plans, modify inventory, change agent configuration
- ESCALATE: Plans above $50K impact, multi-site shortfalls, S&OP triggers
```

### 1.4 Connect Messaging Channels

```json
// ~/.openclaw/openclaw.json (channels section)
{
  "channels": {
    "slack": {
      "enabled": true,
      "bot_token": "${SLACK_BOT_TOKEN}",
      "allow_from": ["planning-team", "supply-chain-ops"]
    },
    "teams": {
      "enabled": true,
      "webhook_url": "${TEAMS_WEBHOOK_URL}"
    }
  }
}
```

### 1.5 Validation Criteria

- [ ] Planner can query supply plan via Slack and receive formatted response
- [ ] ATP check returns accurate results matching direct API call
- [ ] Override capture persists to `powell_decision` table with human_feedback
- [ ] Ask Why returns comprehensible explanation with evidence citations
- [ ] KPI dashboard digest matches React frontend dashboard values
- [ ] Response latency <5s for read operations, <10s for ATP checks

---

## Phase 2: PicoClaw Edge CDC Monitors

**Timeline**: 1-2 weeks (after Phase 1)
**Prerequisites**: Autonomy REST API running, alert channel configured
**Effort**: Low — configuration only, no code changes

**IMPORTANT — Enterprise-Scale Design**: At 223+ sites, PicoClaw heartbeats execute as **deterministic scripts** — no LLM invocation. The heartbeat calls the Autonomy API, compares numeric thresholds locally (Go binary arithmetic), and routes alerts via the gateway. LLM is invoked ONLY when a human asks a question through the chat gateway. See [Enterprise-Scale Analysis](#enterprise-scale-analysis) for volume justification.

### 2.1 Dual-Mode Architecture

PicoClaw operates in two modes depending on network scale:

| Mode | Sites | Heartbeat Execution | LLM Usage | Config |
|---|---|---|---|---|
| **Deterministic** (default) | 50+ sites | Shell script via `HEARTBEAT.sh` | Human questions only (5-20 calls/site/day) | `"heartbeat_mode": "deterministic"` |
| **LLM-Interpreted** (pilot) | <50 sites | LLM interprets `HEARTBEAT.md` | Every heartbeat (~48/day/site) | `"heartbeat_mode": "llm"` |

The system auto-selects mode based on site count in the supply chain config. Override via `config.json`.

### 2.2 PicoClaw Workspace Template

Create a template workspace that gets cloned per site:

```
picoclaw-site-template/
├── config.json          # Mode selection + gateway config
├── IDENTITY.md          # Site identity (populated per-site)
├── TOOLS.md             # Autonomy API tool definitions (for LLM-mode and human queries)
├── HEARTBEAT.sh         # Deterministic CDC script (enterprise mode)
├── HEARTBEAT.md         # LLM-interpreted CDC prompt (pilot mode, <50 sites)
├── SOUL.md              # Chat persona (for human questions only)
└── skills/
    └── site-query/
        └── SKILL.md     # Human query skill (on-demand LLM)
```

### 2.3 Deterministic Heartbeat (Enterprise Mode)

At enterprise scale, the heartbeat is a shell script — no LLM involved:

```bash
#!/bin/bash
# HEARTBEAT.sh — Deterministic CDC monitor (NO LLM)
# Runs every 30 minutes via PicoClaw cron

SITE_KEY="${PICOCLAW_SITE_KEY}"
API_BASE="${PICOCLAW_API_BASE}"
AUTH_TOKEN="${PICOCLAW_AUTH_TOKEN}"
GATEWAY_CHANNEL="${PICOCLAW_ALERT_CHANNEL}"

# Step 1: Query CDC status from Autonomy API
CDC_RESPONSE=$(curl -sf -H "Authorization: Bearer ${AUTH_TOKEN}" \
  "${API_BASE}/api/v1/site-agent/cdc/status/${SITE_KEY}")

if [ $? -ne 0 ]; then
  picoclaw gateway send "${GATEWAY_CHANNEL}" \
    "⚠️ CDC check failed for ${SITE_KEY} — API unreachable"
  exit 1
fi

# Step 2: Extract metrics (jq — no LLM needed)
SEVERITY=$(echo "$CDC_RESPONSE" | jq -r '.severity // "NORMAL"')
INV_RATIO=$(echo "$CDC_RESPONSE" | jq -r '.inventory_ratio // 1.0')
SERVICE_LEVEL=$(echo "$CDC_RESPONSE" | jq -r '.service_level // 1.0')
TRIGGERED_CONDITIONS=$(echo "$CDC_RESPONSE" | jq -r '.triggered_conditions // []')

# Step 3: Route by severity (deterministic if/else)
case "$SEVERITY" in
  "CRITICAL")
    picoclaw gateway send "${GATEWAY_CHANNEL}" \
      "🔴 CRITICAL — ${SITE_KEY}: Inv ratio=${INV_RATIO}, SL=${SERVICE_LEVEL}. Conditions: ${TRIGGERED_CONDITIONS}"
    # Also POST back to Autonomy for tracking
    curl -sf -X POST -H "Authorization: Bearer ${AUTH_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"site_key\":\"${SITE_KEY}\",\"severity\":\"CRITICAL\",\"source\":\"picoclaw\"}" \
      "${API_BASE}/api/v1/site-agent/cdc/alert"
    ;;
  "WARNING")
    # Buffer warning — append to local digest file
    echo "$(date -Iseconds) WARNING ${SITE_KEY} inv=${INV_RATIO} sl=${SERVICE_LEVEL}" \
      >> /root/.picoclaw/workspace/digest_buffer.log
    ;;
  *)
    # Normal — log timestamp only
    echo "$(date -Iseconds) OK" >> /root/.picoclaw/workspace/heartbeat.log
    # Keep last 48 entries (24 hours at 30-min intervals)
    tail -48 /root/.picoclaw/workspace/heartbeat.log > /tmp/hb.tmp \
      && mv /tmp/hb.tmp /root/.picoclaw/workspace/heartbeat.log
    ;;
esac
```

**Key property**: Zero LLM calls. The Autonomy backend's `CDCMonitor` already computes severity, inventory ratio, and triggered conditions. PicoClaw just reads the response and routes.

### 2.4 Digest Script (Template-Based, No LLM)

```bash
#!/bin/bash
# DIGEST.sh — Compile buffered warnings into digest (NO LLM)
# Runs every 4 hours via PicoClaw cron

DIGEST_FILE="/root/.picoclaw/workspace/digest_buffer.log"
GATEWAY_CHANNEL="${PICOCLAW_ALERT_CHANNEL}"
SITE_KEY="${PICOCLAW_SITE_KEY}"

if [ ! -s "$DIGEST_FILE" ]; then
  exit 0  # No warnings to report
fi

WARNING_COUNT=$(wc -l < "$DIGEST_FILE")
DIGEST_BODY=$(cat "$DIGEST_FILE")

picoclaw gateway send "${GATEWAY_CHANNEL}" \
  "📋 ${SITE_KEY} Digest — ${WARNING_COUNT} warnings in last 4h:
${DIGEST_BODY}"

# Clear buffer after sending
> "$DIGEST_FILE"
```

### 2.5 LLM-Interpreted Heartbeat (Pilot Mode, <50 Sites)

For pilot deployments with <50 sites, PicoClaw can use LLM-interpreted `HEARTBEAT.md` for richer analysis:

```markdown
# HEARTBEAT.md (pilot mode only — LLM interprets this every 30 min)

## Step 1: Gather Metrics
Query Autonomy API for current site state:
- GET /api/v1/inventory/levels?site_key={site_key}
- GET /api/v1/site-agent/cdc/status/{site_key}

## Step 2: Analyze
From the API responses:
- inventory_ratio = on_hand_qty / target_qty
- service_level = orders_fulfilled / orders_received (last 24h)
- demand_deviation = abs(actual_demand - forecast) / forecast

Identify trends: Is inventory declining? Is demand spiking?

## Step 3: Check Thresholds
If ANY of these conditions are true, trigger alert:
- inventory_ratio < 0.70 → CRITICAL
- inventory_ratio > 1.50 → WARNING
- service_level < 0.90 → CRITICAL
- demand_deviation > 0.15 → WARNING

## Step 4: Report
Format a natural language summary with context and recommended action.
```

**Cost at pilot scale**: 8 sites × 48 heartbeats/day × 1 LLM call = 384 LLM calls/day — easily within capacity.

### 2.6 Human Query Skill (On-Demand LLM)

When a planner asks a question via the chat gateway (e.g., Telegram: "Why is DC-East low?"), PicoClaw invokes the LLM:

```markdown
# skills/site-query/SKILL.md

## Description
Answer human questions about this site's current state. This is the ONLY time
the LLM is invoked in enterprise (deterministic) mode.

## Triggers
- "Why is {site} low/high/critical?"
- "What happened at {site}?"
- "Status of {site}"

## Implementation
1. GET /api/v1/site-agent/cdc/status/{site_key} (current state)
2. GET /api/v1/site-agent/cdc/history/{site_key}?last=48h (recent history)
3. GET /api/v1/conditions?site_key={site_key}&status=active (active conditions)
4. Pass all context to LLM for natural language explanation
5. Reply via gateway with explanation + recommended actions
```

**Enterprise-scale volume**: ~5-20 human queries/site/day × 223 sites = **1.1K-4.5K LLM calls/day** (vs 10K-32K in LLM-first approach).

### 2.7 Per-Site Configuration

```json
// config.json (per site)
{
  "site_key": "site_42",
  "site_name": "DC-East",
  "site_type": "Distribution Center",
  "region": "East",
  "heartbeat_mode": "deterministic",
  "heartbeat_interval_minutes": 30,
  "digest_interval_hours": 4,
  "alert_channel": "#dc-east-alerts",
  "escalation_contact": "@supply-planner-east",
  "api_base": "http://autonomy-backend:8000",
  "llm_api_base": "http://autonomy-llm:8000/v1",
  "llm_model": "qwen3-8b"
}
```

```markdown
# IDENTITY.md (example for DC-East)

Name: CDC Monitor — DC-East
Site Key: site_42
Site Type: Distribution Center
Region: East
Products Monitored: All FG at this location
Alert Channel: #dc-east-alerts (Slack)
Escalation: @supply-planner-east
```

### 2.8 Deployment Options

**Option A: Docker Containers** (recommended for initial deployment)
```yaml
# docker-compose.picoclaw.yml
services:
  picoclaw-dc-east:
    image: picoclaw/picoclaw:latest
    container_name: picoclaw-dc-east
    command: gateway
    volumes:
      - ./picoclaw-workspaces/dc-east:/root/.picoclaw/workspace
    environment:
      - PICOCLAW_SITE_KEY=site_42
      - PICOCLAW_API_BASE=http://backend:8000
      - PICOCLAW_AUTH_TOKEN=${PICOCLAW_SERVICE_TOKEN}
      - PICOCLAW_ALERT_CHANNEL=#dc-east-alerts
      - PICOCLAW_LLM_API_BASE=http://llm:8000/v1
      - PICOCLAW_LLM_MODEL=qwen3-8b
    networks:
      - autonomy-network
    restart: unless-stopped
    mem_limit: 20m

  picoclaw-wh-north:
    image: picoclaw/picoclaw:latest
    container_name: picoclaw-wh-north
    command: gateway
    volumes:
      - ./picoclaw-workspaces/wh-north:/root/.picoclaw/workspace
    environment:
      - PICOCLAW_SITE_KEY=site_18
      - PICOCLAW_API_BASE=http://backend:8000
      - PICOCLAW_AUTH_TOKEN=${PICOCLAW_SERVICE_TOKEN}
      - PICOCLAW_ALERT_CHANNEL=#wh-north-alerts
      - PICOCLAW_LLM_API_BASE=http://llm:8000/v1
      - PICOCLAW_LLM_MODEL=qwen3-8b
    networks:
      - autonomy-network
    restart: unless-stopped
    mem_limit: 20m
```

**Option B: Auto-Generated Fleet** (enterprise deployment)
```bash
#!/bin/bash
# generate_picoclaw_fleet.sh
# Generates docker-compose.picoclaw.yml for all sites from Autonomy API

SITES=$(curl -sf -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  "${API_BASE}/api/v1/supply-chain-configs/${CONFIG_ID}/sites" | jq -r '.[].site_key')

echo "services:" > docker-compose.picoclaw.yml

for SITE_KEY in $SITES; do
  SITE_NAME=$(curl -sf -H "Authorization: Bearer ${ADMIN_TOKEN}" \
    "${API_BASE}/api/v1/sites/${SITE_KEY}" | jq -r '.site_name')

  cat >> docker-compose.picoclaw.yml << EOF
  picoclaw-${SITE_KEY}:
    image: picoclaw/picoclaw:latest
    container_name: picoclaw-${SITE_KEY}
    command: gateway
    volumes:
      - ./picoclaw-workspaces/${SITE_KEY}:/root/.picoclaw/workspace
    environment:
      - PICOCLAW_SITE_KEY=${SITE_KEY}
      - PICOCLAW_API_BASE=http://backend:8000
      - PICOCLAW_AUTH_TOKEN=\${PICOCLAW_SERVICE_TOKEN}
      - PICOCLAW_ALERT_CHANNEL=#${SITE_KEY}-alerts
      - PICOCLAW_LLM_API_BASE=http://llm:8000/v1
      - PICOCLAW_LLM_MODEL=qwen3-8b
    networks:
      - autonomy-network
    restart: unless-stopped
    mem_limit: 20m
EOF
done

echo "networks:" >> docker-compose.picoclaw.yml
echo "  autonomy-network:" >> docker-compose.picoclaw.yml
echo "    external: true" >> docker-compose.picoclaw.yml

echo "Generated fleet for $(echo "$SITES" | wc -w) sites"
```

**Option C: Physical Edge Devices** (for production sites with local sensors)
- Hardware: Sipeed LicheeRV Nano (~$15) or Raspberry Pi Zero 2 W (~$15)
- Install PicoClaw binary, configure workspace, connect to Autonomy API over VPN
- Suitable when sites have local sensor data to incorporate

### 2.9 Validation Criteria

- [ ] PicoClaw deterministic heartbeat fires every 30 minutes and queries Autonomy API
- [ ] **Zero LLM calls** during heartbeat cycle (verify via vLLM request logs)
- [ ] CDC trigger events from PicoClaw match CDC triggers from built-in CDCMonitor
- [ ] Alerts route correctly to Slack/Telegram channel
- [ ] CRITICAL alerts arrive within 2 minutes of threshold breach
- [ ] Digest compiles warnings every 4 hours with correct counts
- [ ] Human questions via gateway correctly invoke LLM and return explanations
- [ ] Memory footprint stays under 20MB per instance
- [ ] 223-instance fleet starts within 5 minutes and consumes <5GB total RAM
- [ ] PicoClaw instances recover automatically after Autonomy backend restart

---

## Phase 3: Multi-Agent Authorization Protocol

**Timeline**: 4-6 weeks (after Phase 1)
**Prerequisites**: Phase 1 complete, ConditionMonitorService operational
**Effort**: Medium — requires authority boundary configuration + Autonomy API extensions

**IMPORTANT — Enterprise-Scale Design**: At 223+ sites with 500-2,000 authorization requests/day, agent-to-agent communication uses the existing `ConditionMonitorService` supply request pattern (pure Python, DB-backed, <500ms). OpenClaw is used ONLY for the ~50-200 daily human escalations. This separation keeps authorization latency at <500ms vs ~60s through LLM and eliminates 1K-8K LLM calls/day.

### 3.1 Two-Channel Authorization Architecture

```
Agent-to-Agent (Tier 2 — 500-2,000/day, <500ms, NO LLM)
┌───────────────────────────────────────────────────────────────┐
│  SiteAgent A                    ConditionMonitorService        │
│  ├─ Evaluate what-if locally    ├─ create_supply_request()    │
│  ├─ Check authority boundaries  ├─ get_pending_requests()     │
│  └─ If requires-authorization:  └─ respond_to_supply_request()│
│     POST /api/v1/authorization/request                        │
│                                                                │
│  SiteAgent B                                                   │
│  ├─ Poll pending requests                                     │
│  ├─ Evaluate contention + resource availability               │
│  └─ Respond: authorized / rejected / counter-propose          │
│                                                                │
│  All decisions logged to powell_decision table for RLHF       │
└───────────────────────────────────────────────────────────────┘

Human Escalation (Tier 3 — 50-200/day, <5min, LLM via OpenClaw)
┌───────────────────────────────────────────────────────────────┐
│  When agent confidence < threshold OR timeout:                 │
│  1. Format ranked options with Balanced Scorecard              │
│  2. Send to planner via OpenClaw (Slack/Teams/WhatsApp)       │
│  3. Planner responds: "Approve option 2 because..."           │
│  4. Override captured → powell_decision + RLHF training       │
└───────────────────────────────────────────────────────────────┘
```

### 3.2 Authority Boundary Definitions

Authority boundaries are defined per agent type in the Autonomy backend configuration (Python dataclass), NOT in LLM-interpreted `SOUL.md`. This ensures deterministic enforcement at <1ms.

```python
# backend/app/services/powell/authority_boundaries.py

from dataclasses import dataclass, field
from typing import List, Dict
from enum import Enum

class AuthorizationLevel(Enum):
    UNILATERAL = "unilateral"
    REQUIRES_AUTHORIZATION = "requires_authorization"
    FORBIDDEN = "forbidden"

@dataclass
class AuthorityBoundary:
    """Authority boundary definition for a functional agent."""
    agent_type: str
    unilateral: List[str] = field(default_factory=list)
    requires_authorization: Dict[str, str] = field(default_factory=dict)  # action → target_agent
    forbidden: List[str] = field(default_factory=list)

# SO/ATP Agent boundaries
SO_ATP_AUTHORITY = AuthorityBoundary(
    agent_type="so_atp_agent",
    unilateral=[
        "consume_own_priority_tier",
        "flag_exception_within_24h",
        "accept_reject_order_under_10k",
        "query_planning_data",
    ],
    requires_authorization={
        "consume_cross_priority": "allocation_agent",
        "expedite_shipment_over_5k": "logistics_agent",
        "promise_beyond_available": "supply_agent",
        "override_trm_recommendation": "supply_agent",
    },
    forbidden=[
        "modify_safety_stock_parameters",
        "change_allocation_priorities",
        "approve_po_over_50k",
        "modify_sop_policy_envelope",
    ],
)

# Supply Agent boundaries
SUPPLY_AUTHORITY = AuthorityBoundary(
    agent_type="supply_agent",
    unilateral=[
        "select_supbp_candidate",
        "adjust_po_timing_within_3_days",
        "create_po_under_25k",
        "query_inventory_demand_capacity",
    ],
    requires_authorization={
        "create_po_over_25k": "finance_agent",
        "change_sourcing_to_secondary": "procurement_agent",
        "expedite_manufacturing_order": "plant_agent",
        "increase_safety_stock_over_1_5x": "sop_agent",
    },
    forbidden=[
        "modify_demand_forecasts",
        "change_bom_structures",
        "override_capacity_constraints",
        "approve_allocation_changes",
    ],
)
```

### 3.3 Agent-to-Agent Communication (ConditionMonitorService)

The existing `ConditionMonitorService` already provides the supply request pattern. Authorization requests extend this:

```python
# backend/app/services/powell/authorization_service.py

from app.services.condition_monitor_service import ConditionMonitorService

class AuthorizationService:
    """
    Agent-to-agent authorization using ConditionMonitorService.
    No LLM involved — pure Python, DB-backed, <500ms.
    """

    def __init__(self, condition_monitor: ConditionMonitorService):
        self.condition_monitor = condition_monitor

    async def request_authorization(
        self,
        requesting_agent: str,
        target_agent: str,
        action: str,
        context: dict,
        scorecard: dict,
    ) -> str:
        """
        Create authorization request via ConditionMonitor supply request pattern.
        Returns request_id.
        """
        # Validate action is in requires_authorization for this agent type
        boundary = get_authority_boundary(requesting_agent)
        if action in boundary.forbidden:
            raise AuthorizationError(f"Action '{action}' is forbidden for {requesting_agent}")
        if action in boundary.unilateral:
            return "auto_authorized"  # No request needed

        expected_target = boundary.requires_authorization.get(action)
        if expected_target and expected_target != target_agent:
            raise AuthorizationError(
                f"Action '{action}' requires authorization from {expected_target}, not {target_agent}"
            )

        # Create supply request (DB write, <10ms)
        request = await self.condition_monitor.create_supply_request(
            requesting_site=context.get("site_key"),
            condition_type="authorization_request",
            severity="HIGH" if scorecard.get("net_benefit", 0) > 10000 else "MEDIUM",
            details={
                "type": "AuthorizationRequest",
                "from": requesting_agent,
                "to": target_agent,
                "action": action,
                "context": context,
                "scorecard": scorecard,
            },
        )
        return request.id

    async def respond_to_authorization(
        self,
        request_id: str,
        decision: str,  # "authorized" | "rejected" | "counter_propose"
        conditions: list = None,
        reasoning: str = "",
        resolved_by: str = "agent",
    ):
        """
        Respond to authorization request. Logs to powell_decision for RLHF.
        """
        await self.condition_monitor.respond_to_supply_request(
            request_id=request_id,
            response={
                "decision": decision,
                "conditions": conditions or [],
                "reasoning": reasoning,
                "resolved_by": resolved_by,
            },
        )
        # Log for RLHF training
        await self._log_authorization_decision(
            request_id, decision, conditions, reasoning, resolved_by
        )

    async def get_pending_authorizations(self, agent_type: str) -> list:
        """Get pending authorization requests for this agent type."""
        return await self.condition_monitor.get_pending_supply_requests(
            condition_type="authorization_request",
            target_agent=agent_type,
        )
```

### 3.4 Human Escalation via OpenClaw (Tier 3)

When agent-to-agent resolution fails (timeout, low confidence, or policy requires human approval), OpenClaw formats the escalation for human review:

```markdown
# OpenClaw skill: escalate-authorization

## Description
Format an authorization request for human review when agents cannot resolve autonomously.

## Triggers
- Agent timeout (>5 min without response)
- Agent confidence < threshold
- Action net_benefit near zero (ambiguous trade-off)
- Policy requires human approval (e.g., PO > $50K)

## Implementation
1. GET /api/v1/authorization/request/{request_id} (full context + scorecard)
2. Format ranked options with Balanced Scorecard impact:
   - Option 1: Approve as-is (expected benefit: $X, risk: Y%)
   - Option 2: Counter-propose with reduced qty (benefit: $X2, risk: Y2%)
   - Option 3: Reject (status quo: benefit $0, risk: Y3%)
3. Send to planner via gateway (Slack/Teams/WhatsApp)
4. Wait for response
5. POST /api/v1/authorization/request/{request_id}/resolve
   Body: { "decision": "<planner_choice>", "reasoning": "<planner_reasoning>",
           "resolved_by": "human_planner" }
6. Confirm: "Override recorded. Your reasoning will improve future agent decisions."
```

**Escalation rate target**: 10-15% of authorization requests (50-200/day at enterprise scale).

### 3.5 OpenClaw SOUL.md for Human Interface

OpenClaw's `SOUL.md` defines how the agent communicates with human planners — NOT how it communicates with other agents:

```markdown
# SOUL.md — Supply Planner Chat Agent

## Role
You help supply planners review and resolve authorization requests that agents
could not resolve autonomously. You are a human interface layer, NOT a
decision-maker.

## When presenting escalations:
- Show ranked options with full Balanced Scorecard impact
- Cite specific numbers: order IDs, quantities, dollar impacts
- Show confidence scores for each option
- Explain WHY agents could not resolve (timeout, contention, ambiguous trade-off)

## When capturing overrides:
- Always confirm the planner's choice and reasoning
- Log both the decision and the reasoning to the backend
- Remind the planner that their reasoning trains future agent decisions

## Authority (OpenClaw agent itself):
- READ: All planning data, authorization requests, agent decisions
- FORMAT: Escalation summaries for human review
- CAPTURE: Human decisions and reasoning
- CANNOT: Approve plans, modify inventory, resolve authorizations itself
```

### 3.6 Required Autonomy API Extensions

New endpoints needed to support the authorization protocol:

```python
# POST /api/v1/scenario-evaluation/what-if
# Run what-if analysis for a proposed action (used by SiteAgent before requesting)
{
  "action_type": "consume_cross_priority",
  "parameters": { "from_priority": 3, "to_priority": 2, "qty": 80 },
  "evaluate_metrics": ["financial", "customer", "operational"]
}
# Returns: Balanced Scorecard impact

# POST /api/v1/authorization/request
# Create authorization request (called by AuthorizationService)
{
  "requesting_agent": "so_atp_agent",
  "target_agent": "allocation_agent",
  "action": "consume_from_priority_3",
  "context": { "order_id": "ORD-7891", "product_id": "WIDGET-A", ... },
  "scorecard": { "financial": {...}, "customer": {...}, "operational": {...} },
  "status": "pending"
}

# GET /api/v1/authorization/request/{id}
# Get full authorization request (used by OpenClaw for escalation formatting)

# PUT /api/v1/authorization/request/{id}/resolve
# Log resolution for RLHF training
{
  "decision": "authorized",
  "conditions": ["restore_within_72h_if_p3_order_arrives"],
  "reasoning": "P3 has 300 units remaining. 80 = 27% draw. No contention in next 48h.",
  "resolved_by": "allocation_agent"  # or "human_planner"
}

# GET /api/v1/authorization/requests?status=pending&target_agent={agent_type}
# List pending authorization requests for an agent type
```

### 3.7 Validation Criteria

- [ ] Agent-to-agent authorization resolves in <500ms via ConditionMonitorService
- [ ] **Zero LLM calls** for agent-to-agent authorization (verify via vLLM logs)
- [ ] Authority boundaries enforced deterministically (forbidden actions rejected, unilateral auto-approved)
- [ ] Authorization decisions logged to `powell_decision` table for RLHF
- [ ] Human escalation triggers when agent timeout (>5 min) or low-confidence
- [ ] OpenClaw formats escalation with ranked options and Balanced Scorecard
- [ ] Human override reasoning captured and feeds into RLHF training pipeline
- [ ] 80%+ of authorizations resolved by agents without human escalation
- [ ] Resolution latency: <500ms agent-to-agent, <5min with human escalation
- [ ] 100+ authorization transcripts per month available for training data

---

## Phase 4: PicoClaw Simulation Swarm

**Timeline**: 2-3 weeks (optional, after Phase 2)
**Prerequisites**: Phase 2 complete, sufficient hardware for parallel instances
**Effort**: Medium — requires orchestration script

### 4.1 Concept

Use PicoClaw's extreme lightweight nature to spawn hundreds of instances for parallel Monte Carlo scenario evaluation. Each instance simulates one demand path.

**Memory Comparison**:
- 100 PicoClaw instances: ~1GB total (<10MB each)
- 100 Python processes: ~20GB total (~200MB each)
- **20x memory reduction** for simulation layer

### 4.2 Orchestration

```bash
#!/bin/bash
# spawn_simulation_swarm.sh

NUM_PATHS=100
RESULTS_DIR="./simulation_results"

for i in $(seq 1 $NUM_PATHS); do
  # Clone template workspace with unique demand scenario
  cp -r picoclaw-simulation-template "picoclaw-sim-$i"

  # Inject scenario parameters
  echo "Scenario Path: $i" >> "picoclaw-sim-$i/IDENTITY.md"
  echo "Demand Seed: $i" >> "picoclaw-sim-$i/IDENTITY.md"

  # Launch in background
  picoclaw agent -w "picoclaw-sim-$i" \
    -m "Run supply chain simulation for 52 periods with demand seed $i. \
        Record total_cost, service_level, bullwhip_ratio to results.json" &
done

wait  # Wait for all instances to complete

# Aggregate results
python aggregate_simulation_results.py --dir "$RESULTS_DIR"
```

### 4.3 Validation Criteria

- [ ] 100 PicoClaw instances complete 52-period simulation within 30 minutes
- [ ] Total memory consumption stays under 2GB for 100 instances
- [ ] Aggregated P10/P50/P90 distributions match conventional Monte Carlo results (within 5%)
- [ ] Results reproducible with same random seeds

---

## Self-Hosted LLM Infrastructure

### Docker Compose Configuration

Create `docker-compose.llm.yml`:

```yaml
services:
  llm:
    image: vllm/vllm-openai:latest
    container_name: autonomy-llm
    runtime: nvidia
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - NVIDIA_VISIBLE_DEVICES=0
    command: >
      --model Qwen/Qwen3-8B
      --served-model-name qwen3-8b
      --max-model-len 8192
      --enable-auto-tool-choice
      --tool-call-parser hermes
      --gpu-memory-utilization 0.85
    ports:
      - "8100:8000"
    volumes:
      - llm-cache:/root/.cache/huggingface
    networks:
      - autonomy-network
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 120s

volumes:
  llm-cache:
    driver: local
```

### Environment Variables

Add to `.env`:
```bash
# Self-hosted LLM configuration
AUTONOMY_LLM_PROVIDER=vllm
AUTONOMY_LLM_MODEL=qwen3-8b
AUTONOMY_LLM_BASE_URL=http://llm:8000/v1
AUTONOMY_LLM_API_KEY=not-needed

# PicoClaw LLM configuration
PICOCLAW_LLM_API_BASE=http://llm:8000/v1
PICOCLAW_LLM_MODEL=qwen3-8b

# OpenClaw LLM configuration
OPENCLAW_LLM_PROVIDER=custom
OPENCLAW_LLM_API_BASE=http://llm:8000/v1
OPENCLAW_LLM_MODEL=qwen3-8b
```

### GPU Sharing Strategy

| Setup | GPU 0 | GPU 1 |
|---|---|---|
| **Single GPU** | vLLM (60% VRAM) + TRM/GNN inference (40%) | N/A |
| **Dual GPU** | vLLM (dedicated) | TRM/GNN training + inference |
| **Production** | vLLM Qwen 3 32B (dedicated 24GB) | TRM/GNN + S&OP GraphSAGE |

### Model Upgrade Path

| Stage | Model | VRAM | When |
|---|---|---|---|
| **MVP** | Qwen 3 8B | 8GB | Phase 1 start |
| **Validated** | Qwen 3 14B | 16GB | After tool calling validated |
| **Production** | Qwen 3 32B | 24GB | Full authorization protocol |
| **Enterprise** | DeepSeek V3.2 | 200GB+ (4x A100) | Multi-agent negotiation at scale |

---

## Security & Risk Mitigation

| Risk | Severity | Mitigation |
|---|---|---|
| **OpenClaw broad permissions** | HIGH | Restrict skills to read-only API calls in copilot mode; write operations require human confirmation via gateway. Reference: [CrowdStrike advisory](https://www.crowdstrike.com/en-us/blog/what-security-teams-need-to-know-about-openclaw-ai-super-agent/) |
| **PicoClaw pre-v1.0 maturity** | MEDIUM | Use only for read-only monitoring/alerting. No execution decisions. Sandbox mode enabled by default. |
| **LLM hallucination** | MEDIUM | All agent actions go through Autonomy API with validation. Agents cannot bypass API-level permission checks. Structured JSON output via vLLM constrained generation reduces parsing errors. |
| **Data sovereignty** | HIGH | Self-hosted Qwen 3 via vLLM — no data leaves the network. LLM container runs on same Docker network as backend. |
| **Prompt injection via chat** | MEDIUM | OpenClaw's DM pairing mode (default) requires user approval. Skill definitions constrain available actions. Autonomy API enforces RBAC regardless of caller. |
| **Agent impersonation** | LOW | Each OpenClaw session authenticated via JWT. PicoClaw instances use service account tokens with per-site scoping. |
| **Runaway agent costs** | LOW | PicoClaw heartbeat interval (30 min) limits LLM call frequency. OpenClaw rate limiting via gateway configuration. vLLM is self-hosted (no per-token cost). |

---

## Cost Analysis

### Infrastructure Cost (Self-Hosted, Tiered Model)

| Component | Hardware | Monthly Cost | Notes |
|---|---|---|---|
| **vLLM (Qwen 3 8B)** — Pilot/Department | 1x RTX 4060 (8GB) | ~$15/mo electricity | Shared with existing GPU server |
| **vLLM (Qwen 3 14B)** — Enterprise | 1x RTX 4080 (16GB) | ~$25/mo electricity | Dedicated GPU |
| **vLLM (Qwen 3 32B)** — Enterprise + disruption headroom | 1x RTX 4090 (24GB) | ~$30/mo electricity | Dedicated GPU |
| **PicoClaw fleet (223 containers)** | Docker containers | ~$0 (marginal) | <20MB RAM each, ~4.5GB total |
| **PicoClaw (edge devices)** | Sipeed LicheeRV Nano | ~$15 one-time per site | Physical device per site |
| **OpenClaw (5-15 planner sessions)** | Docker container | ~$0 (marginal) | ~200MB RAM |

### Cost Comparison by Scale

**Pilot (4-8 sites, <500 SKUs)**:

| Workload | External (OpenAI GPT-4o) | Self-Hosted (Qwen 3 8B) |
|---|---|---|
| OpenClaw chat (2-3 planners, 100 msgs/day) | ~$10/day ($300/mo) | $0 |
| PicoClaw CDC (LLM-mode OK at pilot) | ~$3/day ($90/mo) | $0 |
| Authorization (sessions_send OK at pilot) | ~$5/day ($150/mo) | $0 |
| **Total** | **~$540/mo** | **~$15/mo electricity** |

**Enterprise (223 sites, 300K SKUs, tiered model)**:

| Workload | LLM Calls/Day | External (GPT-4o) | Self-Hosted (Qwen 3 14B) |
|---|---|---|---|
| OpenClaw chat (5-15 planners) | 500-1,500 | ~$30/day ($900/mo) | $0 |
| PicoClaw human queries | 1,100-4,500 | ~$18/day ($540/mo) | $0 |
| Human escalation formatting | 50-200 | ~$5/day ($150/mo) | $0 |
| KPI digests + novel exceptions | 250-600 | ~$8/day ($240/mo) | $0 |
| PicoClaw deterministic heartbeats | 10,704 | **$0 (no LLM)** | **$0 (no LLM)** |
| Agent-to-agent authorization | 500-2,000 | **$0 (ConditionMonitor)** | **$0 (ConditionMonitor)** |
| **Total** | **~2K-7K** | **~$1,830/mo** | **~$25/mo electricity** |

**Key insight**: The tiered model eliminates ~75% of LLM calls that the naive approach would have made (deterministic heartbeats + ConditionMonitor authorization). At enterprise scale, self-hosted GPU pays for itself within 2 weeks vs external API costs.

### Cost of Naive (LLM-First) Approach at Enterprise Scale

For comparison, if everything routed through LLM as originally proposed for small networks:

| Workload | LLM Calls/Day | External (GPT-4o) | Problem |
|---|---|---|---|
| PicoClaw LLM heartbeats | 10,704 | ~$50/day ($1,500/mo) | Pure arithmetic through LLM |
| Authorization via sessions_send | 1,000-8,000 | ~$40/day ($1,200/mo) | 60s latency per auth |
| Chat + escalation + digests | 800-2,300 | ~$20/day ($600/mo) | Same as tiered |
| **Total** | **12K-21K** | **~$3,300/mo** | Peak spikes could 3-5x |

**Savings from tiered model**: ~$1,500/mo in external API costs eliminated, plus 10x faster authorization resolution.

---

## Success Metrics

### Phase 1 (OpenClaw Chat)

| Metric | Target | Measurement |
|---|---|---|
| **Planner adoption** | 3+ planners using daily within 2 weeks | Chat session count |
| **Response accuracy** | 95%+ match between chat answers and UI dashboard | Manual audit of 50 queries |
| **Override capture rate** | 90%+ of overrides include reasoning | `powell_decision` records with `human_feedback IS NOT NULL` |
| **Response latency** | <5s read, <10s ATP check | p95 measured at OpenClaw gateway |

### Phase 2 (PicoClaw CDC)

| Metric | Target | Measurement |
|---|---|---|
| **Detection parity** | 100% of built-in CDC triggers also detected by PicoClaw | Compare trigger logs over 1 week |
| **Alert latency** | <2 min from threshold breach to Slack/Telegram alert | Timestamp comparison |
| **False positive rate** | <5% of alerts are false positives | Manual review of alerts |
| **Uptime** | 99.5%+ per PicoClaw instance | Docker container health checks |

### Phase 3 (Authorization Protocol)

| Metric | Target | Measurement |
|---|---|---|
| **Authorization resolution rate** | 80%+ resolved by agents without human escalation | `powell_decision` records with `resolved_by=agent` |
| **Agent-to-agent latency** | <500ms via ConditionMonitorService | Timestamp diff on supply request records |
| **Human escalation latency** | <5min via OpenClaw chat | Timestamp diff on escalated records |
| **Zero LLM for agent-to-agent** | 0 LLM calls for inter-agent authorization | vLLM request logs vs authorization logs |
| **Decision quality** | Agent-resolved authorizations perform within 10% of human-resolved | Outcome comparison after 30 days |
| **RLHF training data** | 100+ authorization decisions per month (agent + human) | `powell_decision` records with reasoning |

---

## References

- **PicoClaw**: [GitHub](https://github.com/sipeed/picoclaw) | [Docs](https://picoclaw.ai/docs) | [CNX Software Review](https://www.cnx-software.com/2026/02/10/picoclaw-ultra-lightweight-personal-ai-assistant-run-on-just-10mb-of-ram/)
- **OpenClaw**: [GitHub](https://github.com/openclaw/openclaw) | [DigitalOcean Guide](https://www.digitalocean.com/resources/articles/what-is-openclaw) | [Agent Workforce Guide](https://o-mega.ai/articles/openclaw-creating-the-ai-agent-workforce-ultimate-guide-2026)
- **Qwen 3**: [Tool Calling Docs](https://qwen.readthedocs.io/en/latest/framework/function_call.html) | [Qwen-Agent Framework](https://github.com/QwenLM/Qwen-Agent)
- **vLLM**: [Structured Outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/) | [Docker Serving](https://docs.vllm.ai/en/stable/cli/serve/)
- **Security**: [CrowdStrike OpenClaw Advisory](https://www.crowdstrike.com/en-us/blog/what-security-teams-need-to-know-about-openclaw-ai-super-agent/)
- **Autonomy Internal**: [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) | [AI_AGENTS.md](AI_AGENTS.md) | [POWELL_APPROACH.md](POWELL_APPROACH.md) | [AGENTIC_AUTHORIZATION_PROTOCOL.md](docs/AGENTIC_AUTHORIZATION_PROTOCOL.md)
