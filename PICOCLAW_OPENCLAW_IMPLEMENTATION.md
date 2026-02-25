# PicoClaw & OpenClaw Implementation Plan

**Created**: 2026-02-19
**Status**: PROPOSED
**Dependencies**: Self-hosted LLM (vLLM + Qwen 3), Autonomy REST API (existing)

> **Usage Guide**: For practical setup, deployment, and day-to-day usage instructions, see [docs/PICOCLAW_OPENCLAW_GUIDE.md](docs/PICOCLAW_OPENCLAW_GUIDE.md). This document covers the detailed implementation roadmap, enterprise-scale analysis, and security risk matrix.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Enterprise-Scale Analysis](#enterprise-scale-analysis)
3. [Architecture Overview](#architecture-overview)
4. [Phase 1: OpenClaw Chat Interface](#phase-1-openclaw-chat-interface-lowest-risk-highest-value)
5. [Phase 2: PicoClaw Edge CDC Monitors](#phase-2-picoclaw-edge-cdc-monitors)
6. [Phase 3: Multi-Agent Authorization Protocol](#phase-3-multi-agent-authorization-protocol)
7. [Phase 4: PicoClaw Simulation Swarm](#phase-4-picoclaw-simulation-swarm)
8. [Phase 5: Channel Context Capture](#phase-5-channel-context-capture-signal-ingestion-from-external-sources)
9. [Self-Hosted LLM Infrastructure](#self-hosted-llm-infrastructure)
10. [Security & Risk Mitigation](#security--risk-mitigation)
11. [Cost Analysis](#cost-analysis)
12. [Success Metrics](#success-metrics)

---

## Executive Summary

This document defines the implementation plan for integrating PicoClaw and OpenClaw agent runtimes with the Autonomy platform. These frameworks act as **thin orchestration layers** wrapping existing Autonomy REST APIs — they do not replace the core Powell computation (TRM, GNN, MRP engines) but provide three new capabilities:

1. **Chat-based planning interface** (OpenClaw) — planners interact via WhatsApp/Slack/Teams instead of only the React frontend
2. **Edge CDC monitoring** (PicoClaw) — distributed, ultra-lightweight deterministic site monitoring on $10 hardware
3. **Human escalation for authorization** (OpenClaw) — format agent-unresolvable decisions for human review; agent-to-agent uses existing `ConditionMonitorService`
4. **Channel context capture** (OpenClaw + PicoClaw) — structured signal ingestion from email, Slack, voice, market data, and other channels into the ForecastAdjustmentTRM evaluation pipeline (see [Phase 5](#phase-5-channel-context-capture-signal-ingestion-from-external-sources))

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

## Phase 5: Channel Context Capture (Signal Ingestion from External Sources)

**Timeline**: 2-3 weeks (after Phase 3)
**Prerequisites**: OpenClaw chat working (Phase 1), PicoClaw CDC running (Phase 2)
**Effort**: Medium — new OpenClaw skills + new Autonomy API endpoint for signal ingestion

### 5.1 The Signal Capture Problem

The `ForecastAdjustmentTRM` already defines 10 signal sources (email, voice, market_intelligence, news, customer_feedback, sales_input, weather, economic_indicator, social_media, competitor_action) and a complete evaluation pipeline (source reliability weighting, time decay, confidence thresholds, magnitude estimation). **But there is no automated ingestion path** — signals currently enter only through the REST API or the forecast adjustment UI.

OpenClaw and PicoClaw close this gap by serving as **structured context capture gateways** that normalize multi-channel input into `ForecastAdjustmentState` signals for TRM evaluation.

### 5.2 Channel-to-Signal Architecture

```
EXTERNAL CHANNELS                    CAPTURE LAYER                     AUTONOMY BACKEND
─────────────────                    ─────────────                     ────────────────
                                     ┌──────────────┐
  Email (IMAP/webhook) ──────────────┤              │
  Slack (@mention, thread) ──────────┤              │
  Teams (channel message) ───────────┤   OpenClaw   │    POST /api/v1/signals/ingest
  WhatsApp (planner chat) ───────────┤   Gateway    ├──────────────────────────────►
  Telegram (field report) ───────────┤   + Skills   │    {source, signal_type,
  Voice (transcribed call) ──────────┤              │     direction, magnitude,
                                     └──────────────┘     product_id, site_id,
                                                          signal_text, confidence}
  Market data feeds (API) ───────────┐                         │
  News/RSS webhooks ─────────────────┤   PicoClaw              │
  Weather API (scheduled) ───────────┤   Heartbeat      ┌─────▼──────┐
  Economic indicators ──────────────►│   + Digest   ────►│ Signal     │
  IoT sensor alerts ─────────────────┤                   │ Ingestion  │
                                     └───────────────    │ Service    │
                                                         └─────┬──────┘
                                                               │
                                                    ┌──────────▼──────────┐
                                                    │ ForecastAdjustment  │
                                                    │ TRM Evaluation      │
                                                    │ (source reliability,│
                                                    │  time decay,        │
                                                    │  confidence gate)   │
                                                    └──────────┬──────────┘
                                                               │
                                              ┌────────────────┼────────────────┐
                                              │                │                │
                                         confidence       confidence       confidence
                                         ≥ 0.8            0.3-0.8          < 0.3
                                              │                │                │
                                         AUTO-APPLY       HUMAN REVIEW      REJECT
                                         + HiveSignal     via OpenClaw      (logged)
                                         FORECAST_ADJ     escalation
```

### 5.3 OpenClaw Signal Capture Skills

**Skill: signal-capture** (primary ingestion skill)

```markdown
# skills/signal-capture/SKILL.md

## Description
Capture supply chain signals from planner messages and route to
ForecastAdjustmentTRM for evaluation. Extracts structured signal
data from natural language input across any channel.

## Triggers
- "ACME just announced a 30% expansion"
- "Heard from sales that Q2 demand is going to spike"
- "Supplier Alpha delayed shipment by 2 weeks"
- "Weather forecast: hurricane approaching Gulf Coast"
- "Customer called — they want to double their order"
- Any message containing: forecast, demand, supply, delay, shortage,
  surplus, promotion, disruption, competitor, price change

## Implementation
1. CLASSIFY the message using LLM:
   - Extract: source (infer from channel + sender role)
   - Extract: signal_type (DEMAND_INCREASE, DISRUPTION, etc.)
   - Extract: direction (up, down, no_change)
   - Extract: magnitude_hint (% if mentioned, null otherwise)
   - Extract: product_id (if specific product mentioned)
   - Extract: site_id (if specific site mentioned)
   - Extract: time_horizon (if timeframe mentioned)
   - Assign: signal_confidence based on specificity and sender

2. VALIDATE extracted fields:
   - product_id must exist in Autonomy product catalog
     (GET /api/v1/products?search={product_name})
   - site_id must exist in supply chain config
     (GET /api/v1/supply-chain-configs/{id}/sites?search={site_name})
   - If ambiguous, ask sender for clarification

3. SUBMIT to Autonomy Signal Ingestion API:
   POST /api/v1/signals/ingest
   {
     "source": "{channel_type}",          // email, slack, voice, etc.
     "signal_type": "{classified_type}",
     "direction": "{up|down|no_change}",
     "magnitude_hint": {pct_or_null},
     "product_id": "{resolved_id}",
     "site_id": "{resolved_id}",
     "signal_text": "{original_message}",
     "signal_confidence": {0.0-1.0},
     "sender_id": "{channel_sender_id}",
     "sender_role": "{planner|sales|customer|external}",
     "channel": "{slack|teams|whatsapp|telegram|email}",
     "thread_id": "{channel_thread_id}",
     "timestamp": "{message_timestamp}"
   }

4. REPORT back to sender:
   "Signal captured: {signal_type} for {product} at {site}.
    Source reliability: {weight}. Confidence: {score}.
    Status: {auto-applied | pending human review | rejected (too weak)}"

5. If auto-applied, report the adjustment:
   "Forecast adjusted: {product} at {site} {direction} by {pct}%.
    New forecast: {value}. Reason: {signal_text}"
```

**Skill: voice-signal** (voice-specific transcription + capture)

```markdown
# skills/voice-signal/SKILL.md

## Description
Process voice notes and phone call transcripts as forecast signals.
OpenClaw automatically transcribes voice notes sent via WhatsApp,
Telegram, and other channels. This skill captures the transcription
as a structured signal.

## Triggers
- Any voice note or audio file attachment
- "I just got off the phone with..."
- "In today's call, they mentioned..."

## Implementation
1. Voice note transcription is handled by OpenClaw's built-in
   speech-to-text pipeline (Whisper via voice-call plugin)
2. Treat transcription as signal_text
3. Set source = "voice", signal_confidence *= 0.4 (voice reliability weight)
4. Route to signal-capture skill for classification and submission
```

**Skill: email-signal** (email-specific parsing)

```markdown
# skills/email-signal/SKILL.md

## Description
Parse inbound emails for supply chain signals. Extracts signal
context from email subject, body, and attachments.

## Triggers
- Emails received via OpenClaw email channel (IMAP polling or webhook)
- Emails forwarded to the planning channel with "FYI" or "signal"

## Implementation
1. Extract: sender domain (customer vs supplier vs internal)
2. Extract: email subject for signal type classification
3. Extract: body text for magnitude, product, site references
4. If attachment (PDF, Excel): extract key figures via document parsing
5. Set source = "email", signal_confidence *= 0.5 (email reliability weight)
6. Route to signal-capture skill for classification and submission
```

### 5.4 PicoClaw Market Data Capture

PicoClaw instances can monitor structured data feeds on a scheduled basis and convert them to signals:

```bash
#!/bin/bash
# MARKET_SIGNAL.sh — Scheduled market data capture (deterministic, NO LLM)
# Runs every 4 hours via PicoClaw cron

SITE_KEY="${PICOCLAW_SITE_KEY}"
API_BASE="${PICOCLAW_API_BASE}"
AUTH_TOKEN="${PICOCLAW_AUTH_TOKEN}"

# Step 1: Pull weather data for site region
WEATHER=$(curl -sf "https://api.weather.gov/alerts/active?area=${SITE_REGION}")
SEVERE_COUNT=$(echo "$WEATHER" | jq '[.features[] | select(.properties.severity == "Severe" or .properties.severity == "Extreme")] | length')

if [ "$SEVERE_COUNT" -gt 0 ]; then
  curl -sf -X POST -H "Authorization: Bearer ${AUTH_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{
      \"source\": \"weather\",
      \"signal_type\": \"DISRUPTION\",
      \"direction\": \"down\",
      \"magnitude_hint\": null,
      \"site_id\": \"${SITE_KEY}\",
      \"signal_text\": \"${SEVERE_COUNT} severe weather alerts active in region\",
      \"signal_confidence\": 0.7
    }" \
    "${API_BASE}/api/v1/signals/ingest"
fi

# Step 2: Check commodity price index (if relevant)
# Step 3: Check economic indicators (PMI, etc.)
# ... (similar pattern: fetch → threshold check → submit signal)
```

### 5.5 Signal Ingestion API Endpoint (New)

```python
# backend/app/api/endpoints/signal_ingestion.py

@router.post("/signals/ingest")
async def ingest_signal(
    signal: SignalIngestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ingest an external signal for ForecastAdjustmentTRM evaluation.

    Called by OpenClaw (chat-captured signals) and PicoClaw
    (market data feeds). Validates the signal, creates a
    ForecastAdjustmentState, evaluates via the TRM, and returns
    the recommendation.

    Security: Requires authenticated user or service account.
    Rate limited: 100 signals/hour per source to prevent flooding.
    """
    # 1. Validate product_id and site_id exist
    # 2. Create ForecastAdjustmentState from signal
    # 3. Evaluate via ForecastAdjustmentTRM
    # 4. If auto_applicable: apply adjustment, emit HiveSignal
    # 5. If requires_human_review: create worklist item
    # 6. Return recommendation to caller
    ...
```

### 5.6 Signal-to-HiveSignal Bridge

When a captured signal results in an auto-applied forecast adjustment, the system bridges to the Hive Signal Bus:

```
OpenClaw captures: "ACME doubled their Q2 order"
  → signal-capture skill classifies: DEMAND_INCREASE, +100%, customer_feedback
  → POST /api/v1/signals/ingest
  → ForecastAdjustmentTRM evaluates: confidence 0.72 × source 0.7 = 0.50
  → REQUIRES_HUMAN_REVIEW (below 0.8 threshold)
  → OpenClaw presents to planner: "Approve forecast increase of 35% for SKU-X?"
  → Planner approves via chat: "Yes, ACME confirmed this in their PO"
  → Forecast adjusted, override captured (is_expert_decision=true)
  → HiveSignalBus emits: FORECAST_ADJUSTED (direction=up, magnitude=35%)
  → POCreationTRM reads signal → adjusts reorder quantities
  → InventoryBufferTRM reads signal → evaluates buffer adequacy
```

### 5.7 Channel-to-Signal Source Mapping

| Channel | Default Signal Source | Reliability Weight | Notes |
|---|---|---|---|
| Slack (#demand-planning) | sales_input | 0.7 | Internal planning team |
| Slack (#customer-alerts) | customer_feedback | 0.7 | Customer-facing team |
| Teams (planner chat) | sales_input | 0.7 | Internal |
| WhatsApp (field reports) | sales_input | 0.6 | Less structured, lower reliability |
| Telegram (supplier updates) | customer_feedback | 0.6 | Informal channel |
| Email (customer PO update) | customer_feedback | 0.5 | Email signal decay applies |
| Email (market report) | market_intelligence | 0.8 | Professional analysis |
| Voice note (sales call) | voice | 0.4 | Lowest reliability — informal, noisy |
| Weather API (PicoClaw) | weather | 0.7 | Structured data, high reliability |
| Economic API (PicoClaw) | economic_indicator | 0.8 | Professional data feed |
| News RSS (PicoClaw) | news | 0.6 | Requires context interpretation |

### 5.8 Multi-Signal Correlation

When multiple signals arrive from different channels about the same topic, the Signal Ingestion Service correlates them to boost confidence:

```
Signal 1 (Slack, 10:00): "Sales says ACME wants 30% more in Q2"
  → source: sales_input, confidence: 0.49

Signal 2 (Email, 10:30): ACME sends updated forecast spreadsheet
  → source: customer_feedback, confidence: 0.56

Signal 3 (Voice, 11:00): VP Sales calls: "Just confirmed ACME expansion"
  → source: voice, confidence: 0.32

CORRELATION ENGINE detects: 3 signals, same product, same direction, <2h window
  → Correlated confidence: 1 - (1-0.49)(1-0.56)(1-0.32) = 0.85
  → Now exceeds 0.8 threshold → AUTO-APPLY
  → No human review needed — multi-source corroboration sufficient
```

### 5.9 Validation Criteria

- [ ] OpenClaw signal-capture skill correctly classifies 90%+ of test signals (50-message test set)
- [ ] Captured signals appear in `powell_forecast_adjustment_decisions` within 5s
- [ ] Voice notes transcribed and classified within 10s
- [ ] PicoClaw weather/market scripts submit signals deterministically (no LLM)
- [ ] Multi-signal correlation correctly boosts confidence when 2+ signals agree
- [ ] Rate limiting prevents more than 100 signals/hour per source
- [ ] All captured signals include full provenance (channel, sender, thread_id, timestamp)

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

### Known Vulnerabilities (as of February 2026)

Both PicoClaw and OpenClaw are early-stage open-source projects with active security histories. This section documents known issues, their relevance to the Autonomy deployment model, and required mitigations.

#### OpenClaw CVEs

| CVE | CVSS | Description | Patched In | Autonomy Impact |
|---|---|---|---|---|
| **CVE-2026-25253** | 8.8 (Critical) | 1-click RCE via auth token exfiltration through crafted `gatewayUrl` query parameter | v2026.1.29 | HIGH — exposes gateway control if user clicks malicious link |
| **CVE-2026-26325** | High | Auth bypass via `rawCommand`/`command[]` mismatch in `system.run` handler | v2026.2.14 | HIGH — bypasses tool execution allowlist |
| **CVE-2026-25474** | High | Telegram webhook request forgery when `webhookSecret` not configured | v2026.2.1 | MEDIUM — affects Telegram channel only |
| **CVE-2026-26324** | 7.6 (High) | SSRF guard bypass via IPv4-mapped IPv6 addresses, reaching loopback/metadata | Patched | MEDIUM — mitigated by container network isolation |
| **CVE-2026-27003** | Moderate | Telegram bot token exposure via error logs and stack traces | Patched | MEDIUM — token leakage enables bot impersonation |
| **CVE-2026-27004** | Moderate | Session isolation bypass in `sessions_list`/`sessions_history`/`sessions_send` | v2026.2.15 | LOW — Autonomy uses single-agent mode, not multi-tenant |
| **GHSA-r5fq-947m-xm57** | 8.8 (High) | Path traversal in `apply_patch` tool via LLM guardrail bypass | Patched | HIGH — demonstrates LLM-mediated guards can be bypassed |

**MANDATORY**: Minimum OpenClaw version for Autonomy deployment: **v2026.2.15** or later.

Additionally, Endor Labs discovered 6 SAST-identified vulnerabilities (SSRF in gateway, Urbit auth, image tool; missing webhook verification for Telnyx/Twilio; path traversal in browser upload) — all patched. A January 2026 audit identified 512 total vulnerabilities, 8 classified as critical.

#### PicoClaw Security Status

| Issue | Severity | Description | Status |
|---|---|---|---|
| No CVEs published | N/A | No formal vulnerability tracking exists | **HIGH RISK** — absence of CVEs indicates lack of scrutiny, not absence of vulnerabilities |
| No SECURITY.md | HIGH | No vulnerability disclosure policy | No structured way to report security issues |
| No signed binaries | MEDIUM | GitHub Releases without cryptographic signatures | Users cannot verify binary integrity |
| 95% AI-generated codebase | HIGH | "Vibe coded" — LLMs fail to secure against common attacks (XSS, injection) in 86-88% of cases | Independent audit required before production |
| Slack allowlist bypass (#179) | MEDIUM | Any user in Slack workspace could interact regardless of allowlist | Patched, but indicates access control immaturity |
| Blocklist-based sandbox | MEDIUM | `restrict_to_workspace` uses deny-list approach | Novel bypasses possible (OpenClaw's GHSA-r5fq proved similar guards breakable) |

**Assessment**: PicoClaw has no formal security audit, no vulnerability disclosure process, and its maintainers explicitly warn against production deployment. However, the Autonomy deployment model (deterministic heartbeat scripts, read-only API calls, no LLM in the decision path) **limits the blast radius significantly**.

### Supply Chain Attack Surface

#### ClawHavoc Campaign (OpenClaw/ClawHub)

In January 2026, security researchers discovered **1,184 malicious skills** on ClawHub (the OpenClaw marketplace), uploaded by just 12 accounts. Malware payloads included Atomic macOS Stealer (AMOS), reverse shells, SSH key theft, and crypto wallet exfiltration. The #1 most popular skill on ClawHub was malware.

**Mitigation for Autonomy**:
- **NEVER install skills from public ClawHub**. All OpenClaw skills must be authored in-house from the templates in this document (Section 1.2).
- Skills are defined as SKILL.md files in the workspace — plain Markdown, not executable code. The attack surface is the LLM's interpretation of these files, not arbitrary code execution.
- Autonomy API enforces RBAC regardless of caller — even a compromised skill can only perform actions the authenticated service account is authorized for.

#### WhatsApp via Baileys Library

OpenClaw uses the Baileys library for WhatsApp integration, which reverse-engineers the WhatsApp Web protocol. Risks:

- **Terms of Service violation**: Meta prohibits unauthorized automation tools. Accounts can be permanently banned without warning.
- **Supply chain poisoning**: A malicious fork ("lotusbail", 56K+ downloads) stole WhatsApp auth tokens, session keys, and all messages via a persistent backdoor.
- **Protocol instability**: WhatsApp protocol changes can break Baileys without notice.

**Mitigation for Autonomy**:
- **For production**: Use only the official WhatsApp Business API (requires Meta Business verification). Baileys is acceptable only for pilot/development environments.
- Pin the exact Baileys npm version and verify checksums.
- Monitor for account bans and have fallback to Slack/Teams channels.

#### Credential Targeting (Infostealer Campaign)

In February 2026, a Vidar infostealer variant was discovered specifically targeting OpenClaw configuration files (`openclaw.json`, `device.json`), exfiltrating gateway auth tokens and RSA key pairs. Security researchers characterized this as "the transition from stealing browser credentials to harvesting the souls of personal AI agents."

### Comprehensive Risk Matrix

| Risk | Severity | Likelihood | Autonomy Mitigation |
|---|---|---|---|
| **OpenClaw RCE via known CVEs** | CRITICAL | LOW (if patched) | **Minimum version v2026.2.15. No exceptions.** Automated version check in deployment script. |
| **Prompt injection via channel messages** | HIGH | HIGH | All channel inputs treated as untrusted. OpenClaw LLM classifies signals but **cannot execute actions directly** — must go through Autonomy API which enforces RBAC. Signal ingestion rate-limited to 100/hour/source. Input sanitization layer strips control characters and injection patterns before LLM processing. |
| **Supply chain attack (ClawHub skills)** | CRITICAL | MEDIUM | **Zero ClawHub skills installed.** All skills authored in-house as SKILL.md files. `npm audit` run on every OpenClaw update. Dependency lockfile checked into version control. |
| **WhatsApp account ban (Baileys ToS)** | HIGH | MEDIUM | Production deployments use official WhatsApp Business API only. Baileys restricted to pilot/dev. Multi-channel fallback (Slack, Teams, Telegram) ensures no single-channel dependency. |
| **Credential theft (infostealer)** | HIGH | MEDIUM | Store all credentials (API keys, bot tokens, gateway auth) in **environment variables or secrets manager** (HashiCorp Vault, AWS Secrets Manager), not plaintext config files. Rotate gateway tokens quarterly. PicoClaw service accounts use short-lived JWT with per-site scoping. |
| **PicoClaw sandbox escape** | MEDIUM | LOW | PicoClaw runs in **read-only Docker containers** with `--read-only --no-new-privileges --cap-drop ALL`. No host filesystem access. Workspace mounted as tmpfs. Network restricted to Autonomy API endpoint only via Docker network policy. |
| **OpenClaw broad permissions** | HIGH | MEDIUM | Skills restricted to read-only API calls in copilot mode. Write operations (forecast adjustment, override capture) require human confirmation via gateway. OpenClaw process runs as non-root user in container with minimal capabilities. |
| **Session isolation bypass** | MEDIUM | LOW | Autonomy uses single-agent single-tenant mode (one OpenClaw per planning team). Multi-tenant shared-agent mode is **prohibited** in Autonomy deployments. |
| **Telegram bot token exposure** | MEDIUM | MEDIUM | Configure `webhookSecret` (mandatory, not optional). Enable log redaction. Bot tokens stored in environment variables, not config files. |
| **SSRF from gateway** | HIGH | LOW | OpenClaw gateway bound to **loopback only** (127.0.0.1). External access via authenticated reverse proxy (Nginx) with TLS. Container network isolated — gateway cannot reach cloud metadata endpoints. |
| **LLM hallucination / false signals** | MEDIUM | HIGH | All signal ingestion goes through ForecastAdjustmentTRM's source reliability weighting and confidence thresholding. Signals below 0.3 confidence auto-rejected. Signals 0.3-0.8 require human review. Only signals above 0.8 auto-apply — and even then, bounded to ±50% adjustment cap. |
| **Data sovereignty** | HIGH | LOW | Self-hosted Qwen 3 via vLLM — all LLM processing stays on-premises. No data leaves the Docker network. LLM container has no internet access (egress blocked). |
| **PicoClaw pre-v1.0 maturity** | MEDIUM | HIGH | PicoClaw used **only** for deterministic heartbeat scripts and structured data feed polling. No LLM in the decision path at enterprise scale. No execution authority — read-only API access. |
| **Signal flooding / DoS** | MEDIUM | LOW | Rate limiting: 100 signals/hour per source, 500/hour globally. Duplicate detection via signal deduplication (same source + same product + same direction within 1h = deduplicate). PicoClaw heartbeat interval (30 min) inherently limits throughput. |
| **Agent impersonation** | LOW | LOW | Each OpenClaw session authenticated via JWT from Autonomy auth service. PicoClaw instances use service account tokens with per-site scoping (token for DC-East cannot query DC-West). Token rotation on 90-day cycle. |
| **Runaway agent costs** | LOW | LOW | Self-hosted vLLM eliminates per-token costs. PicoClaw heartbeat interval limits LLM call frequency. OpenClaw rate limiting via gateway configuration. |
| **Project governance (founder departure)** | MEDIUM | MEDIUM | OpenClaw founder joined OpenAI in Feb 2026. Project moved to open-source foundation. **Monitor foundation's security response cadence** — if patch velocity drops below 7-day SLA for critical CVEs, evaluate fork or alternative. PicoClaw's Sipeed backing provides hardware company stability but limited software security expertise. |

### Required Security Controls for Deployment

**Pre-deployment checklist** (all items mandatory before any PicoClaw/OpenClaw instance touches production data):

```
INFRASTRUCTURE
  □ OpenClaw version ≥ v2026.2.15 (all known CVEs patched)
  □ OpenClaw gateway bound to loopback (127.0.0.1) only
  □ Authenticated reverse proxy (Nginx + TLS) for external access
  □ Gateway auth token set (no unauthenticated access)
  □ OpenClaw container: non-root user, --no-new-privileges, --cap-drop ALL
  □ PicoClaw container: --read-only, tmpfs workspace, network-restricted
  □ No internet egress from LLM container (air-gapped from external APIs)
  □ Run SecureClaw audit tool: `openclaw security audit --deep`

CREDENTIALS
  □ All API keys in environment variables or secrets manager (not config files)
  □ Bot tokens (Telegram, Slack) in environment variables (not config files)
  □ Gateway auth token rotated from default
  □ PicoClaw service accounts: per-site JWT with minimal permissions
  □ No plaintext credentials in workspace IDENTITY.md, SOUL.md, or TOOLS.md

CHANNEL SECURITY
  □ Telegram: webhookSecret configured (not empty)
  □ Slack: Bot token scoped to specific channels only
  □ WhatsApp: Official Business API for production (Baileys for dev/pilot only)
  □ Email: SPF/DKIM/DMARC validation enabled, allowlist enforcement
  □ DM pairing mode enabled (default) — users must approve connection

SIGNAL INGESTION
  □ Rate limiting enabled: 100 signals/hour/source, 500/hour global
  □ Signal deduplication active (same source + product + direction within 1h)
  □ Input sanitization: strip control characters, detect injection patterns
  □ ForecastAdjustmentTRM confidence gate active (0.3 minimum, 0.8 auto-apply)
  □ Adjustment cap: ±50% maximum (±15% for low-confidence signals)

MONITORING
  □ OpenClaw gateway access logs forwarded to SIEM
  □ PicoClaw heartbeat logs retained for 30 days
  □ Failed authentication attempts alerting configured
  □ Signal ingestion anomaly detection (volume spike = potential attack)
  □ Weekly review of captured signals for prompt injection patterns

SKILLS
  □ Zero ClawHub marketplace skills installed
  □ All skills authored in-house from Section 1.2 templates
  □ npm audit clean (no known vulnerabilities in dependencies)
  □ Dependency lockfile checked into version control
  □ Skills reviewed for prompt injection vectors before deployment
```

### Security Architecture Diagram

```
INTERNET                          DMZ                             INTERNAL NETWORK
─────────                         ───                             ────────────────
                           ┌─────────────┐
  Slack/Teams/Telegram ────┤   Nginx     │
  (TLS, webhook verify)    │   Reverse   │
                           │   Proxy     │
  Email (SPF/DKIM/DMARC) ──┤   + WAF    │
                           └──────┬──────┘
                                  │ Authenticated
                                  │ (JWT + TLS)
                           ┌──────▼──────┐
                           │  OpenClaw   │  ← loopback only (127.0.0.1:18789)
                           │  Container  │  ← non-root, --cap-drop ALL
                           │  (Gateway)  │  ← no internet egress
                           └──────┬──────┘
                                  │ REST API (JWT auth)
                                  │
                    ┌─────────────▼──────────────┐
                    │    Autonomy Backend        │
                    │    (FastAPI + RBAC)        │  ← enforces permissions
                    │                            │     regardless of caller
                    │  ┌──────────────────────┐  │
                    │  │ Signal Ingestion     │  │  ← rate limited
                    │  │ Service              │  │  ← input sanitized
                    │  │  → ForecastAdjTRM    │  │  ← confidence gated
                    │  └──────────────────────┘  │
                    │                            │
                    │  ┌──────────────────────┐  │
                    │  │ vLLM (Qwen 3)       │  │  ← no internet egress
                    │  │ Air-gapped container │  │  ← data stays on-prem
                    │  └──────────────────────┘  │
                    └─────────────▲──────────────┘
                                  │ REST API (service JWT)
                    ┌─────────────┴──────────────┐
                    │  PicoClaw Fleet            │
                    │  (223 containers)           │  ← --read-only
                    │  Deterministic heartbeats   │  ← tmpfs workspace
                    │  No LLM at enterprise scale │  ← network restricted
                    └────────────────────────────┘
```

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

### Phase 5 (Channel Context Capture)

| Metric | Target | Measurement |
|---|---|---|
| **Signal classification accuracy** | 90%+ of signals correctly classified (type, direction) | Manual audit of 50-message test set |
| **Signal ingestion latency** | <5s from channel message to `powell_forecast_adjustment_decisions` record | Timestamp diff: channel → API |
| **Voice transcription + classification** | <10s end-to-end | Timestamp diff: voice note → signal record |
| **Multi-signal correlation** | Correctly boosts confidence when 2+ signals agree within 2h | Correlation engine audit |
| **False signal rate** | <10% of ingested signals are noise/irrelevant | Manual review of signals over 1 week |
| **Prompt injection resistance** | 0 successful prompt injections in signal capture pipeline | Red team test with 20 crafted injection attempts |
| **Rate limiting** | Enforced at 100 signals/hour/source, 500/hour global | Load test with signal flooding |
| **Source provenance** | 100% of signals include channel, sender, thread_id, timestamp | Field completeness audit |

---

## References

- **PicoClaw**: [GitHub](https://github.com/sipeed/picoclaw) | [Docs](https://picoclaw.ai/docs) | [CNX Software Review](https://www.cnx-software.com/2026/02/10/picoclaw-ultra-lightweight-personal-ai-assistant-run-on-just-10mb-of-ram/)
- **OpenClaw**: [GitHub](https://github.com/openclaw/openclaw) | [DigitalOcean Guide](https://www.digitalocean.com/resources/articles/what-is-openclaw) | [Agent Workforce Guide](https://o-mega.ai/articles/openclaw-creating-the-ai-agent-workforce-ultimate-guide-2026)
- **Qwen 3**: [Tool Calling Docs](https://qwen.readthedocs.io/en/latest/framework/function_call.html) | [Qwen-Agent Framework](https://github.com/QwenLM/Qwen-Agent)
- **vLLM**: [Structured Outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/) | [Docker Serving](https://docs.vllm.ai/en/stable/cli/serve/)
- **Security Advisories**:
  - [CrowdStrike — What Security Teams Need to Know About OpenClaw](https://www.crowdstrike.com/en-us/blog/what-security-teams-need-to-know-about-openclaw-ai-super-agent/)
  - [Microsoft — Running OpenClaw Safely](https://www.microsoft.com/en-us/security/blog/2026/02/19/running-openclaw-safely-identity-isolation-runtime-risk/)
  - [Cisco — Personal AI Agents Like OpenClaw Are a Security Nightmare](https://blogs.cisco.com/ai/personal-ai-agents-like-openclaw-are-a-security-nightmare)
  - [Endor Labs — Path Traversal in OpenClaw via LLM Guardrail Bypass](https://www.endorlabs.com/learn/ai-sast-finding-path-traversal-in-openclaw-via-llm-guardrail-bypass)
  - [Adversa AI — OpenClaw Security 101](https://adversa.ai/blog/openclaw-security-101-vulnerabilities-hardening-2026/)
  - [Snyk — 280+ Leaky Skills in ClawHub](https://snyk.io/blog/openclaw-skills-credential-leaks-research/)
  - [SecureClaw Audit Tool](https://github.com/polyakov/secureclaw)
- **Supply Chain Incidents**:
  - [The Hacker News — 341 Malicious ClawHub Skills](https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html)
  - [BleepingComputer — Infostealer Targeting OpenClaw Secrets](https://www.bleepingcomputer.com/news/security/infostealer-malware-found-stealing-openclaw-secrets-for-first-time/)
  - [The Register — Poisoned WhatsApp API Package (Baileys fork)](https://www.theregister.com/2025/12/22/whatsapp_npm_package_message_steal/)
- **CVE Database**: [NVD — CVE-2026-25253](https://nvd.nist.gov/vuln/detail/CVE-2026-25253) | [GitLab Advisory — CVE-2026-25474](https://advisories.gitlab.com/pkg/npm/openclaw/CVE-2026-25474/) | [GitLab Advisory — CVE-2026-26324](https://advisories.gitlab.com/pkg/npm/openclaw/CVE-2026-26324/) | [GitLab Advisory — CVE-2026-26325](https://advisories.gitlab.com/pkg/npm/openclaw/CVE-2026-26325/)
- **Autonomy Internal**: [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) | [AI_AGENTS.md](AI_AGENTS.md) | [POWELL_APPROACH.md](POWELL_APPROACH.md) | [AGENTIC_AUTHORIZATION_PROTOCOL.md](docs/AGENTIC_AUTHORIZATION_PROTOCOL.md) | [TRM_HIVE_ARCHITECTURE.md](TRM_HIVE_ARCHITECTURE.md)
