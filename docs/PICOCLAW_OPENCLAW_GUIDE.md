# PicoClaw & OpenClaw Usage Guide

**Last Updated**: 2026-02-25
**Status**: PROPOSED — not yet deployed to production

This guide covers the practical setup, configuration, and day-to-day use of PicoClaw and OpenClaw with the Autonomy platform. For the detailed implementation roadmap (5-phase plan, enterprise-scale analysis, full security risk matrix), see [PICOCLAW_OPENCLAW_IMPLEMENTATION.md](../PICOCLAW_OPENCLAW_IMPLEMENTATION.md).

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Quick Start: OpenClaw](#quick-start-openclaw)
5. [Quick Start: PicoClaw](#quick-start-picoclaw)
6. [Self-Hosted LLM (vLLM)](#self-hosted-llm-vllm)
7. [OpenClaw Skills Reference](#openclaw-skills-reference)
8. [PicoClaw Operating Modes](#picoclaw-operating-modes)
9. [Signal Ingestion Pipeline](#signal-ingestion-pipeline)
10. [Admin UI Pages](#admin-ui-pages)
11. [Make Targets](#make-targets)
12. [Security Checklist](#security-checklist)
13. [Troubleshooting](#troubleshooting)
14. [References](#references)

---

## Overview

PicoClaw and OpenClaw are **external agent runtimes** that wrap the Autonomy REST API as thin orchestration layers. They do not replace the core computation (TRM, GNN, MRP engines) — they provide three new capabilities:

| Framework | What It Is | What It Does | Resource Footprint |
|-----------|-----------|-------------|-------------------|
| **PicoClaw** | Ultra-lightweight Go binary | Edge CDC monitoring and alert routing across supply chain sites | <10MB RAM, runs on $10 hardware |
| **OpenClaw** | Feature-rich agent platform | Chat-based planning interface via WhatsApp, Slack, Teams | ~200MB RAM, Docker container |

**What problems they solve:**

1. **Chat-based planning** (OpenClaw) — Planners interact via WhatsApp/Slack/Teams instead of only the React frontend. Query supply plans, check ATP, override decisions, and ask "why?" — all from a messaging app.

2. **Edge CDC monitoring** (PicoClaw) — Distributed, lightweight site monitoring. Each supply chain site gets a PicoClaw instance that checks CDC status and routes alerts via Telegram/Slack/Discord. At enterprise scale (50+ sites), heartbeats are deterministic — no LLM needed.

3. **Channel context capture** (both) — Structured signal ingestion from email, Slack, voice notes, weather APIs, and market data feeds into the ForecastAdjustmentTRM evaluation pipeline.

4. **Human escalation** (OpenClaw) — When AI agents cannot resolve an authorization request autonomously, OpenClaw formats ranked options with a Balanced Scorecard and sends them to a planner via chat for review.

**Key design principle**: Both frameworks consume the same Autonomy REST API that the React frontend uses. No backend computation changes are required. At enterprise scale, **LLM touches <1% of decisions** — the existing deterministic engines and TRM heads handle everything else.

---

## Architecture

```
TIER 3: HUMAN INTERFACE — OpenClaw
  ├─ Planner chat (WhatsApp/Slack/Teams)
  ├─ Human escalation (ranked options + scorecard)
  └─ KPI digests and ask-why
  LLM calls: ~800-2,300/day
       │ REST API
       ▼
TIER 2: LEARNED — Autonomy Backend (FastAPI + Powell)
  ├─ TRM/GNN inference (<10ms)
  ├─ Agent-to-agent authorization (ConditionMonitor, <500ms, NO LLM)
  └─ Self-hosted LLM (vLLM + Qwen 3) — serves Tier 3 only
  TRM/GNN inferences: ~10K-40K/day
       │ REST API
       ▼
TIER 1: DETERMINISTIC — Autonomy Engines
  ├─ AATP, MRP, Safety Stock (250K-700K ops/day)
  └─ CDC Monitor (arithmetic threshold comparison)
       │ REST API (heartbeat)
       ▼
EDGE: PicoClaw Swarm
  ├─ One instance per supply chain site
  ├─ Deterministic heartbeat: GET CDC status → if/else → alert
  └─ LLM only on human question (~5-20 calls/site/day)
```

All communication between layers uses the Autonomy REST API. PicoClaw and OpenClaw never talk to each other directly — they both talk to the backend.

---

## Prerequisites

Before deploying PicoClaw or OpenClaw:

1. **Autonomy backend running**: `make up` (the standard stack must be running)
2. **Self-hosted LLM** (recommended): `make up-llm` — starts vLLM with Qwen 3 8B. Alternatively, configure an external LLM endpoint (OpenAI, etc.)
3. **Service account token**: Both frameworks authenticate via JWT service accounts created through the Edge Agents API

**Required environment variables** (add to `.env`):

```bash
# Self-hosted LLM
AUTONOMY_LLM_PROVIDER=vllm
AUTONOMY_LLM_MODEL=qwen3-8b
AUTONOMY_LLM_BASE_URL=http://llm:8000/v1
AUTONOMY_LLM_API_KEY=not-needed

# OpenClaw
OPENCLAW_SERVICE_TOKEN=<generated-from-api>
SLACK_BOT_TOKEN=<your-slack-bot-token>        # optional
TEAMS_WEBHOOK_URL=<your-teams-webhook>         # optional

# PicoClaw
PICOCLAW_SERVICE_TOKEN=<generated-from-api>
```

### Creating a Service Account

```bash
# Via the API (requires admin auth):
curl -X POST http://localhost:8000/api/v1/edge-agents/picoclaw/service-accounts \
  -H "Authorization: Bearer <admin-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"name": "openclaw-gateway", "scope": "global"}'

# The response includes the JWT token — save it as OPENCLAW_SERVICE_TOKEN
```

Or use the Admin UI: **Administration > Edge Agents > PicoClaw > Service Accounts**.

---

## Quick Start: OpenClaw

OpenClaw provides a chat-based interface for supply planners via WhatsApp, Slack, Teams, Discord, or Signal.

### Step 1: Deploy

```bash
# Start OpenClaw (requires the main stack to be running first)
make openclaw-up
```

This runs `docker compose -f docker-compose.yml -f deploy/openclaw/docker-compose.openclaw.yml up -d openclaw`.

The container mounts the workspace from `deploy/openclaw/workspace/` (skills, SOUL.md) and config from `deploy/openclaw/openclaw.json`.

### Step 2: Configure Channels

Edit `deploy/openclaw/openclaw.json` to enable messaging channels:

```json
{
  "agent": {
    "model": "qwen3-8b",
    "providers": {
      "custom": {
        "api_key": "not-needed",
        "api_base": "http://vllm:8000/v1"
      }
    }
  },
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

Or configure via the Admin UI: **Administration > Edge Agents > OpenClaw > Channels**.

### Step 3: Verify

```bash
# Check container is running
docker ps | grep openclaw

# View logs
make openclaw-logs

# Send a test message via your configured channel
# e.g., in Slack: "KPI summary" — should return a dashboard digest
```

### Step 4: Stop

```bash
make openclaw-down
```

---

## Quick Start: PicoClaw

PicoClaw deploys one lightweight instance per supply chain site for CDC monitoring and alert routing.

### Step 1: Generate Per-Site Workspaces

```bash
# Generate workspaces from your supply chain config
make picoclaw-workspaces
# Uses PICOCLAW_CONFIG_ID=1 by default; override with:
# make picoclaw-workspaces PICOCLAW_CONFIG_ID=3
```

This reads your supply chain configuration from the database and generates a workspace directory per site under `deploy/picoclaw/workspaces/`, each with:
- `config.json` — Site key, mode (deterministic/LLM), alert channel
- `IDENTITY.md` — Site identity and role
- `SOUL.md` — Agent persona for human queries
- `HEARTBEAT.sh` — Deterministic CDC check script
- `skills/` — Human query skill

### Step 2: Generate Fleet Docker Compose

```bash
make picoclaw-fleet
```

This reads the generated workspaces and creates `deploy/picoclaw/docker-compose.picoclaw.yml` with one container per site.

### Step 3: Deploy the Fleet

```bash
make picoclaw-up
```

### Step 4: Verify

```bash
# Check fleet status
make picoclaw-status

# View fleet logs
make picoclaw-logs

# In the Admin UI: Administration > Edge Agents > PicoClaw
# Should show registered instances with heartbeat timestamps
```

### Step 5: Stop

```bash
make picoclaw-down
```

---

## Self-Hosted LLM (vLLM)

Both PicoClaw and OpenClaw need an LLM backend. For data sovereignty (keeping business data on-premises), self-host Qwen 3 via vLLM.

### Deploy

```bash
# Start the full stack with vLLM
make up-llm
```

This adds the vLLM service via `docker-compose.llm.yml`. The first start downloads the model (~5GB).

### Model Selection

| Stage | Model | VRAM Required | When to Use |
|-------|-------|---------------|-------------|
| **Pilot** | Qwen 3 8B | 8GB (RTX 3070/4060) | Getting started, <50 sites |
| **Production** | Qwen 3 14B | 16GB (RTX 4080) | 50-200 sites |
| **Enterprise** | Qwen 3 32B | 24GB (RTX 4090) | 200+ sites with disruption headroom |

### GPU Sharing

| Setup | GPU 0 | GPU 1 |
|-------|-------|-------|
| **Single GPU** | vLLM (60% VRAM) + TRM/GNN inference (40%) | N/A |
| **Dual GPU** | vLLM (dedicated) | TRM/GNN training + inference |

### Verify

```bash
# Check LLM endpoint
make llm-check

# Or directly:
curl http://localhost:8001/v1/models
```

---

## OpenClaw Skills Reference

OpenClaw uses modular skills (defined as `SKILL.md` files) to interact with the Autonomy API. All skills are authored in-house — **never install skills from public ClawHub** (see [Security](#security-checklist)).

Skills are located in `deploy/openclaw/workspace/skills/`:

| Skill | Triggers | What It Does |
|-------|----------|-------------|
| **supply-plan-query** | "Show supply plan for X at Y", "What's the plan?" | Queries supply plan for a product-site combination and formats a human-readable summary |
| **atp-check** | "Can we promise 100 of X by Friday?", "ATP check" | Checks Available-to-Promise via the AATP engine and returns promised qty, date, and confidence |
| **ask-why** | "Why did you recommend X?", "Explain decision 42" | Calls the Ask Why API and returns context-aware explanation with authority, guardrails, attribution, and counterfactuals |
| **override-decision** | "Override decision 42 because...", "Reject recommendation" | Captures planner's override with reasoning; feeds into RLHF training loop |
| **kpi-dashboard** | "Dashboard", "KPI summary", "How are we doing?" | Aggregates KPIs (service level, inventory, exceptions, touchless rate) into a digest message |
| **escalate-authorization** | Triggered automatically on agent timeout/low confidence | Formats unresolved authorization requests as ranked options with Balanced Scorecard for human review |
| **signal-capture** | "ACME wants 30% more in Q2", "Supplier delayed 2 weeks" | Classifies natural language messages as forecast signals and submits to the Signal Ingestion API |
| **voice-signal** | Voice notes, audio attachments | Processes transcribed voice notes as forecast signals (confidence weighted at 0.4) |
| **email-signal** | Forwarded emails, email webhooks | Parses inbound emails for supply chain signals (confidence weighted at 0.5) |

---

## PicoClaw Operating Modes

PicoClaw supports two operating modes, auto-selected based on network size:

### Deterministic Mode (Default, 50+ sites)

Heartbeats execute as shell scripts — **zero LLM calls**:

1. `HEARTBEAT.sh` calls `GET /api/v1/site-agent/cdc/status/{site_key}`
2. Parses response JSON with `jq` (severity, inventory ratio, service level)
3. Routes by severity:
   - `CRITICAL` → Immediate gateway alert (Slack/Telegram/Discord)
   - `WARNING` → Buffer for next digest
   - `NORMAL` → Log timestamp
4. `DIGEST.sh` (every 4h) compiles buffered warnings into a summary message

LLM is invoked **only** when a human asks a question via the chat gateway (e.g., "Why is DC-East critical?"). Volume: ~5-20 LLM calls/site/day.

### LLM-Interpreted Mode (Pilot, <50 sites)

For small deployments, PicoClaw uses LLM-interpreted `HEARTBEAT.md`:

1. LLM reads the heartbeat prompt every 30 minutes
2. Calls the Autonomy API for inventory levels and CDC status
3. Analyzes trends and checks thresholds
4. Generates a natural language summary with recommended actions

Cost at pilot scale: 8 sites x 48 heartbeats/day = 384 LLM calls/day — easily within capacity.

### Market Data Capture (Both Modes)

PicoClaw also captures structured signals from external data feeds via deterministic scripts — no LLM needed:

- Weather API alerts → `DISRUPTION` signals
- Commodity price changes → `SUPPLY_DISRUPTION` or `DEMAND_INCREASE` signals
- Economic indicators (PMI) → `DEMAND_INCREASE`/`DEMAND_DECREASE` signals

These scripts run on a 4-hour cron and submit signals to `POST /api/v1/signals/ingest`.

---

## Signal Ingestion Pipeline

Signals flow from external channels through PicoClaw/OpenClaw into the ForecastAdjustmentTRM:

```
CHANNELS                          CAPTURE                    BACKEND
────────                          ───────                    ───────

  Slack, Teams, WhatsApp ──┐
  Email, Voice notes ──────┤─→ OpenClaw (LLM classifies) ──┐
  Telegram, field reports ─┘                                 │
                                                             ▼
  Weather, commodities ────┐                          Signal Ingestion
  News, economic data ─────┤─→ PicoClaw (deterministic) ──→ Service
  IoT sensor alerts ───────┘                                 │
                                                             ▼
                                                   ForecastAdjustmentTRM
                                                    (source reliability,
                                                     confidence gating)
                                                             │
                                              ┌──────────────┼──────────────┐
                                         conf ≥ 0.8    conf 0.3-0.8    conf < 0.3
                                              │              │              │
                                         AUTO-APPLY    HUMAN REVIEW      REJECT
                                                     (via OpenClaw)     (logged)
```

**Source reliability weights** (configurable):

| Source | Default Weight | Notes |
|--------|---------------|-------|
| Slack (planner) | 0.7 | Professional context |
| Email (customer PO) | 0.5 | Semi-structured |
| Voice note | 0.4 | Informal, noisy |
| Weather API | 0.7 | Structured data |
| Economic indicator | 0.8 | Professional data feed |
| News RSS | 0.6 | Requires interpretation |

**Multi-signal correlation**: When 2+ signals arrive about the same product/direction within 2 hours, the Signal Ingestion Service correlates them and boosts confidence using `1 - product(1 - conf_i)`.

**Admin UI**: **Administration > Edge Agents > Signal Dashboard** — view, approve, reject signals; manage source reliability; view correlations.

---

## Admin UI Pages

Access via **Administration > Edge Agents** in the navigation menu (requires Group Admin or System Admin role).

### PicoClaw Management

**Path**: Administration > Edge Agents > PicoClaw
**File**: `frontend/src/pages/admin/PicoClawManagement.jsx`

- **Fleet Summary** — Overview of all registered PicoClaw instances with health status
- **Instances** — Per-site details: last heartbeat, CDC severity, alert count
- **Alerts** — Active and historical CDC alerts with acknowledgment workflow
- **Configuration** — Heartbeat mode (deterministic/LLM), intervals, alert channels
- **Service Accounts** — Create and manage JWT service accounts for PicoClaw authentication

### OpenClaw Management

**Path**: Administration > Edge Agents > OpenClaw
**File**: `frontend/src/pages/admin/OpenClawManagement.jsx`

- **Gateway Overview** — OpenClaw status, version, LLM provider configuration
- **Skills** — Toggle individual skills on/off, view skill descriptions
- **Channels** — Configure messaging channels (Slack, Teams, WhatsApp, Telegram, Email)
- **Sessions** — Monitor active chat sessions and activity history
- **LLM Config** — Provider, model, API base URL, API key

### Signal Ingestion Dashboard

**Path**: Administration > Edge Agents > Signals
**File**: `frontend/src/pages/admin/SignalIngestionDashboard.jsx`

- **Signals** — List of captured signals with approve/reject workflow
- **Correlations** — Multi-signal correlation groups
- **Source Reliability** — Per-source reliability weights and history
- **Pipeline Status** — Signal processing metrics and error rates

### Edge Agent Security

**Path**: Administration > Edge Agents > Security
**File**: `frontend/src/pages/admin/EdgeAgentSecurity.jsx`

- **Pre-Deployment Checklist** — Mandatory security checks before going live
- **Risk Assessment** — Current security posture and open items
- **Activity Log** — Audit trail of all edge agent operations

---

## Make Targets

### LLM

| Target | Description |
|--------|------------|
| `make up-llm` | Start full stack with vLLM (Qwen 3 8B) — requires NVIDIA GPU with >= 8GB VRAM |
| `make llm-check` | Test LLM endpoint connectivity |

### OpenClaw

| Target | Description |
|--------|------------|
| `make openclaw-setup` | Validate OpenClaw workspace configuration (SOUL.md, skills, openclaw.json) |
| `make openclaw-up` | Start OpenClaw container (runs `openclaw-setup` first) |
| `make openclaw-down` | Stop OpenClaw container |
| `make openclaw-logs` | Tail OpenClaw container logs |

### PicoClaw

| Target | Description |
|--------|------------|
| `make picoclaw-workspaces` | Generate per-site workspaces from supply chain config (uses `PICOCLAW_CONFIG_ID`, default: 1) |
| `make picoclaw-fleet` | Generate fleet `docker-compose.picoclaw.yml` from generated workspaces |
| `make picoclaw-up` | Start PicoClaw CDC fleet |
| `make picoclaw-down` | Stop PicoClaw fleet |
| `make picoclaw-logs` | Tail PicoClaw fleet logs |
| `make picoclaw-status` | Show fleet container status |

---

## Security Checklist

Both PicoClaw and OpenClaw are early-stage open-source projects with known vulnerabilities. **All items below are mandatory before any instance touches production data.**

For the comprehensive risk matrix (14 risks with severity, likelihood, and mitigations), see [PICOCLAW_OPENCLAW_IMPLEMENTATION.md — Security](../PICOCLAW_OPENCLAW_IMPLEMENTATION.md#security--risk-mitigation).

### Infrastructure

- [ ] OpenClaw version >= **v2026.2.15** (patches critical RCE CVE-2026-25253)
- [ ] OpenClaw gateway bound to loopback only (127.0.0.1)
- [ ] Authenticated reverse proxy (Nginx + TLS) for external access
- [ ] OpenClaw container: non-root user, `--no-new-privileges`, `--cap-drop ALL`
- [ ] PicoClaw container: `--read-only`, tmpfs workspace, network restricted to Autonomy API only
- [ ] LLM container: no internet egress (air-gapped)

### Credentials

- [ ] All API keys and bot tokens in environment variables or secrets manager — never in config files
- [ ] Gateway auth token rotated from default
- [ ] PicoClaw service accounts: per-site JWT with minimal permissions
- [ ] No plaintext credentials in IDENTITY.md, SOUL.md, or TOOLS.md

### Channels

- [ ] Telegram: `webhookSecret` configured (not empty)
- [ ] Slack: bot token scoped to specific channels only
- [ ] WhatsApp: official Business API for production (Baileys for pilot only — ToS risk)
- [ ] Email: SPF/DKIM/DMARC validation enabled

### Signal Ingestion

- [ ] Rate limiting: 100 signals/hour/source, 500/hour globally
- [ ] Signal deduplication active (same source + product + direction within 1h)
- [ ] ForecastAdjustmentTRM confidence gate active (0.3 minimum, 0.8 auto-apply)
- [ ] Adjustment cap: ±50% maximum

### Skills

- [ ] **Zero ClawHub marketplace skills installed** — all skills authored in-house
- [ ] `npm audit` clean on every OpenClaw update
- [ ] Dependency lockfile checked into version control

### Monitoring

- [ ] OpenClaw gateway access logs forwarded to SIEM
- [ ] PicoClaw heartbeat logs retained for 30 days
- [ ] Failed authentication attempts alerting configured
- [ ] Weekly review of captured signals for prompt injection patterns

---

## Troubleshooting

### OpenClaw won't start

```bash
# Check if the main stack is running (OpenClaw depends on backend)
docker ps | grep backend

# Check for config errors
make openclaw-setup

# View startup logs
docker logs autonomy-openclaw
```

**Common causes**: Missing `OPENCLAW_SERVICE_TOKEN`, backend not running, LLM endpoint unreachable.

### PicoClaw fleet won't start

```bash
# Verify fleet compose was generated
ls deploy/picoclaw/docker-compose.picoclaw.yml

# If missing, regenerate:
make picoclaw-workspaces && make picoclaw-fleet

# Check status
make picoclaw-status
```

**Common causes**: Workspaces not generated, fleet compose missing, `PICOCLAW_SERVICE_TOKEN` not set.

### LLM not responding

```bash
# Check vLLM container
docker logs autonomy-vllm

# Test endpoint directly
curl http://localhost:8001/v1/models

# First start downloads the model (~5GB) — can take several minutes
make llm-check
```

**Common causes**: Model still downloading, insufficient GPU memory, CUDA driver mismatch.

### Heartbeats not firing

1. Check the PicoClaw container logs: `make picoclaw-logs`
2. Verify the service account token is valid: `curl -H "Authorization: Bearer $PICOCLAW_SERVICE_TOKEN" http://localhost:8000/api/v1/edge-agents/picoclaw/instances`
3. Verify the CDC status endpoint works: `curl http://localhost:8000/api/v1/site-agent/cdc/status/{site_key}`

### Signals not appearing in dashboard

1. Check OpenClaw logs for signal submission errors: `make openclaw-logs`
2. Verify signal ingestion API: `curl -X POST http://localhost:8000/api/v1/signals/ingest -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"source": "test", "signal_type": "DEMAND_INCREASE", "direction": "up", "signal_text": "test signal", "signal_confidence": 0.5}'`
3. Check rate limiting — signals may be deduplicated if submitted too rapidly

---

## References

### Internal Documentation

| Document | What It Covers |
|----------|---------------|
| [PICOCLAW_OPENCLAW_IMPLEMENTATION.md](../PICOCLAW_OPENCLAW_IMPLEMENTATION.md) | Detailed 5-phase implementation roadmap, enterprise-scale analysis, full security risk matrix, cost analysis |
| [INTEGRATION_GUIDE.md](../INTEGRATION_GUIDE.md#external-agent-runtimes-picoclaw--openclaw) | Integration overview, dual-mode operation, security considerations |
| [AI_AGENTS.md](../AI_AGENTS.md#external-agent-runtimes-picoclaw--openclaw) | Comparison with built-in agents, hybrid architecture, channel context capture |
| [POWELL_APPROACH.md](../POWELL_APPROACH.md) | Powell Framework for AI agent decision-making |
| [AGENTIC_AUTHORIZATION_PROTOCOL.md](AGENTIC_AUTHORIZATION_PROTOCOL.md) | Cross-functional authorization protocol for agent-to-agent and human escalation |

### External Resources

| Resource | Link |
|----------|------|
| PicoClaw GitHub | https://github.com/sipeed/picoclaw |
| PicoClaw Docs | https://picoclaw.ai/docs |
| OpenClaw GitHub | https://github.com/openclaw/openclaw |
| Qwen 3 Tool Calling | https://qwen.readthedocs.io/en/latest/framework/function_call.html |
| vLLM Docs | https://docs.vllm.ai/en/latest/ |

### Security Advisories

| Advisory | Link |
|----------|------|
| CrowdStrike — OpenClaw Security | https://www.crowdstrike.com/en-us/blog/what-security-teams-need-to-know-about-openclaw-ai-super-agent/ |
| Microsoft — Running OpenClaw Safely | https://www.microsoft.com/en-us/security/blog/2026/02/19/running-openclaw-safely-identity-isolation-runtime-risk/ |
| Adversa AI — OpenClaw Security 101 | https://adversa.ai/blog/openclaw-security-101-vulnerabilities-hardening-2026/ |
| SecureClaw Audit Tool | https://github.com/polyakov/secureclaw |

### Key Files

| Path | Purpose |
|------|---------|
| `deploy/openclaw/docker-compose.openclaw.yml` | OpenClaw Docker Compose service |
| `deploy/openclaw/workspace/skills/` | 9 OpenClaw skill definitions |
| `deploy/openclaw/openclaw.json` | OpenClaw configuration (LLM, channels) |
| `deploy/picoclaw/generate_workspaces.py` | Per-site workspace generator |
| `deploy/picoclaw/generate_fleet_compose.py` | Fleet Docker Compose generator |
| `deploy/picoclaw/templates/SOUL.md` | PicoClaw agent persona template |
| `backend/app/api/endpoints/edge_agents.py` | REST API endpoints (927 lines) |
| `backend/app/services/edge_agent_service.py` | Business logic (621 lines) |
| `backend/app/services/signal_ingestion_service.py` | Signal pipeline (753 lines) |
| `backend/app/models/edge_agents.py` | 13 database models (581 lines) |
| `frontend/src/pages/admin/PicoClawManagement.jsx` | PicoClaw admin UI |
| `frontend/src/pages/admin/OpenClawManagement.jsx` | OpenClaw admin UI |
| `frontend/src/pages/admin/SignalIngestionDashboard.jsx` | Signal dashboard UI |
| `frontend/src/pages/admin/EdgeAgentSecurity.jsx` | Security checklist UI |
| `frontend/src/services/edgeAgentApi.js` | Frontend API client |
