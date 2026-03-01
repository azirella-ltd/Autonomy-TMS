# Executive Strategy Briefing

**Date**: February 2026
**Status**: Implemented

## Overview

The Executive Strategy Briefing is an LLM-powered synthesis feature that automatically gathers metrics from 6+ internal platform services, retrieves strategic context from the Knowledge Base via RAG, and produces natural language executive briefings with scored recommendations and interactive follow-up Q&A.

Inspired by Pieter van Schalkwyk's "Sunday Morning Strategy" approach — the idea that a CEO should receive a comprehensive, AI-synthesized strategy briefing without opening a dashboard.

**Key principle**: The briefing IS the LLM narrative. Data cards supplement but don't replace it. The LLM synthesizes across data sources, surfaces what matters, and scores recommendations — tasks dashboards cannot do.

---

## How It Works

### Architecture

```
6 Platform Services                Knowledge Base (RAG)
    ↓ (data collection)               ↓ (semantic search)
BriefingDataCollector             KnowledgeBaseService
    ↓ JSON data pack (~5K tokens)      ↓ strategy context (~4K tokens)
    └──────────────┬───────────────────┘
                   ↓
            Claude Sonnet 4.6
            (BRIEFING_PROMPT.md system prompt)
                   ↓
            Structured JSON response
            (narrative + scored recommendations)
                   ↓
            executive_briefings table
                   ↓
            Frontend renders briefing
            with follow-up chat
```

### Data Sources

The `BriefingDataCollector` gathers a JSON "data pack" from these sources. Each source is independently fault-tolerant — if one fails, the briefing still generates with the available data.

| Source | What It Provides | Service |
|--------|-----------------|---------|
| **Executive Dashboard** | Agent KPIs, ROI metrics, touchless rate, trends, S&OP worklist | `AgentPerformanceService` |
| **Balanced Scorecard** | 4-tier Gartner hierarchy (ASSESS/DIAGNOSE/CORRECT/AGENT PERFORMANCE) | `HierarchicalMetricsService` |
| **Condition Alerts** | Active CRITICAL/WARNING alerts from last 7 days (ATP shortfall, inventory, capacity, orders, forecast) | `ConditionAlert` model |
| **CDC Triggers** | Model drift events and recommended retraining actions | `powell_cdc_trigger_log` table |
| **Override Effectiveness** | Human override quality by agent type, agent vs planner scores | `performance_metrics` table |
| **External Signals** | Multi-channel signals (email, Slack, market data) by type and status | `signal_ingestion` table |

Data is truncated to keep the data pack under ~5K tokens: top 20 alerts, 10 CDC triggers, 6 months of trends, 5 worklist items.

### LLM Synthesis

The system prompt (`BRIEFING_PROMPT.md`) instructs Claude Sonnet to produce a structured JSON response with:

1. **Title** — Date or theme-driven headline
2. **Executive Summary** — 2-3 sentence lead
3. **6 Narrative Sections** — Each 3-6 sentences with specific metric citations:
   - Situation Overview (what changed)
   - Scorecard Narrative (BSC tier 1/2 trends)
   - Agent Performance Digest (AI trust trajectory)
   - Risk Report (CDC triggers, alerts, mitigation)
   - External Signals (market intelligence)
   - Trend Analysis (week-over-week direction)
4. **Scored Recommendations** — 3-7 ranked recommendations
5. **Data Quality Notes** — Transparency about gaps

### 5-Criteria Scoring Framework

Each recommendation is scored on 5 criteria (1-5 scale) with weighted composite:

| Criteria | Weight | Scale |
|----------|--------|-------|
| Financial Impact | 0.30 | 1-5 (revenue/cost magnitude) |
| Urgency | 0.25 | 1-5 (5 = act today) |
| Confidence | 0.20 | 1-5 (data quality backing the recommendation) |
| Strategic Alignment | 0.15 | 1-5 (alignment with company strategy from KB) |
| Feasibility | 0.10 | 1-5 (5 = easy to implement) |

Composite score = weighted average. Recommendations are ranked highest-first. Visual color coding: green (>= 3.5), amber (2.5-3.5), red (< 2.5).

### Knowledge Base Integration

If strategic documents have been uploaded to the Knowledge Base (Administration > Knowledge Base), the system performs a semantic search for "company strategy supply chain priorities objectives risks competitive" (top 5 results, up to 4K tokens). This context is appended to the system prompt, enabling the LLM to align recommendations with stated company priorities and score `strategic_alignment` more accurately.

Upload strategy documents, competitive intelligence, and decision frameworks to the KB for richer, more contextual briefings.

---

## Using the UI

Navigate to **Insights & Analytics > Strategy Briefing** (requires `view_executive_dashboard` capability).

### Tab 1: Latest Briefing

This is the primary view. It shows the most recent completed briefing.

**Generating a briefing**:
1. Click **Generate Now** (top right) — triggers an ad-hoc generation
2. A spinner appears ("Generating executive briefing...") — typically 15-75 seconds depending on data volume and LLM response time
3. The page polls every 2 seconds for completion (120s timeout)
4. Once complete, the briefing renders in place

**Reading a briefing**:
- **Executive Summary** — Highlighted card at the top with the 2-3 sentence lead. Read this first.
- **Narrative Sections** — 6 collapsible cards below, each with an icon and color. Click to expand/collapse:
  - Situation Overview (blue globe icon)
  - Scorecard Narrative (green chart icon)
  - Agent Performance Digest (purple bot icon)
  - Risk Report (red alert icon)
  - External Signals (amber radio icon)
  - Trend Analysis (cyan trending icon)
- **Recommendations** — Ranked cards showing:
  - Composite score badge (color-coded)
  - Title and description
  - Category tag (operations, finance, ai_agents, risk, strategy)
  - 5 horizontal score bars for each criterion
  - Data citations (the specific metrics backing the recommendation)
- **Data Quality Notes** — Amber warning box if any data sources were unavailable or stale
- **Generation Metadata** — Model used, token count, generation time (bottom of page)

**Follow-up Q&A** (the conversational LLM interface):
- Below the briefing, a chat panel labeled "Ask a follow-up question" appears
- Type a question like "Why did service level drop last week?" or "What's driving the inventory build?"
- The LLM receives the full data pack, narrative, and previous Q&A as context
- Responses are in natural language (not JSON), citing specific metrics
- Conversation history persists — each new question sees all prior Q&A
- Follow-ups use Claude Sonnet with the same data pack context

**If generation fails**:
- A red error banner shows the failure reason
- Common causes: LLM timeout, network issue, no data available
- Click "Generate Now" to retry

### Tab 2: History

A paginated list of all past briefings ordered by date. Each entry shows:
- Title, type badge (daily/weekly/monthly/adhoc), status badge
- Executive summary preview (truncated)
- Follow-up count
- Creation date

Click any entry to load it into the Latest Briefing tab for full viewing.

### Tab 3: Settings

**Scheduled Generation**:
- Toggle to enable/disable automated briefings
- Frequency: daily, weekly, or monthly (1st of month)
- Day of week (for weekly): Monday through Sunday
- Time (UTC): hour (00-23) and minute (00/15/30/45)
- Click **Save Schedule** to persist

Example: Enable weekly briefings on Monday at 06:00 UTC — the CEO receives a fresh briefing every Monday morning.

**Strategic Context**:
- Link to the Knowledge Base where you can upload strategy documents
- These documents feed into the LLM's strategic alignment scoring

**Last Generation Details**:
- Shows model, token count, generation time, and estimated cost for the most recent briefing

---

## Scheduled Briefings

An APScheduler job runs hourly at :05. It checks all `briefing_schedules` where `enabled=True` and generates briefings for tenants whose schedule matches the current time:

- **Daily**: Generates every day at the configured hour/minute
- **Weekly**: Generates on the configured day of week at the configured time
- **Monthly**: Generates on the 1st of each month at the configured time

The job uses an isolated DB session per tenant to prevent cross-tenant failures.

---

## API Reference

All endpoints are under `/api/v1/executive-briefing/` and require authentication.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/generate` | Start async briefing generation. Returns `{briefing_id, status: "pending"}` immediately. Background task runs LLM synthesis. |
| GET | `/latest` | Most recent completed briefing for the authenticated user's tenant. |
| GET | `/history?limit=20&offset=0&briefing_type=weekly` | Paginated briefing list. Optional type filter. |
| GET | `/{briefing_id}` | Specific briefing with full narrative, recommendations, and follow-ups. |
| POST | `/{briefing_id}/ask` | Ask a follow-up question. Body: `{"question": "Why did OTIF drop?"}`. Returns natural language answer. |
| GET | `/schedule/config` | Get schedule configuration for the tenant. |
| PUT | `/schedule/config` | Update schedule. Body: `{"enabled": true, "briefing_type": "weekly", "cron_day_of_week": "mon", "cron_hour": 6, "cron_minute": 0}` |

**Async generation flow**:
1. `POST /generate` creates a `pending` record and schedules a background task
2. Background task collects data, calls LLM, updates record to `completed` or `failed`
3. Frontend polls `GET /{briefing_id}` every 2 seconds until status is terminal

---

## Cost Model

| Activity | Frequency | Tokens | Cost |
|----------|-----------|--------|------|
| Weekly briefing (Sonnet) | 4/month | ~8K (5K in + 3K out) | ~$0.25/month |
| Follow-up questions (Sonnet) | ~20/month | ~2K each | ~$0.40/month |
| KB context retrieval | Per briefing | Embedding search only | Negligible |
| **Total per tenant** | | | **< $1/month** |

Prompt caching (via `ClaudeClient`) reduces system prompt cost by ~90% on repeat calls with the same BRIEFING_PROMPT.md.

---

## Database Tables

Three tables in the `executive_briefings` migration (`20260227_exec_brief`):

### `executive_briefings`
Primary briefing records.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | Auto-increment |
| tenant_id | Integer FK → tenants | Tenant isolation |
| requested_by | Integer FK → users | User who triggered generation (nullable for scheduled) |
| briefing_type | String(20) | daily, weekly, monthly, adhoc |
| status | String(20) | pending, generating, completed, failed |
| title | String(500) | LLM-generated title |
| data_pack | JSON | Raw collected data from all sources |
| narrative | Text | LLM narrative (JSON string with 6 sections) |
| recommendations | JSON | Scored recommendations array |
| executive_summary | Text | 2-3 sentence lead |
| model_used | String(100) | e.g., "claude-sonnet-4-6" |
| tokens_used | Integer | Total input + output tokens |
| generation_time_ms | Integer | Wall-clock LLM call time |
| kb_context_used | Text | RAG context that was fed to the LLM (truncated to 2K) |
| error_message | Text | Error details if status=failed |
| created_at | DateTime | Record creation time |
| completed_at | DateTime | When generation finished |

Indexes: `(tenant_id, created_at)`, `(status)`, `(briefing_type)`

### `briefing_followups`
Q&A pairs linked to a briefing.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | Auto-increment |
| briefing_id | Integer FK → executive_briefings | Parent briefing (CASCADE delete) |
| asked_by | Integer FK → users | User who asked |
| question | Text | The follow-up question |
| answer | Text | LLM-generated answer |
| model_used | String(100) | Model used for the answer |
| tokens_used | Integer | Tokens for this Q&A turn |
| created_at | DateTime | When asked |

Index: `(briefing_id)`

### `briefing_schedules`
Per-tenant schedule configuration.

| Column | Type | Description |
|--------|------|-------------|
| id | Integer PK | Auto-increment |
| tenant_id | Integer FK → tenants | Unique per tenant |
| enabled | Boolean | Whether scheduled generation is active |
| briefing_type | String(20) | daily, weekly, monthly |
| cron_day_of_week | String(10) | mon, tue, ... sun |
| cron_hour | Integer | 0-23 (UTC) |
| cron_minute | Integer | 0-59 |
| created_at | DateTime | Record creation |
| updated_at | DateTime | Last modification |

---

## Implementation Files

| File | Purpose |
|------|---------|
| `backend/app/models/executive_briefing.py` | SQLAlchemy models (3 tables) |
| `backend/migrations/versions/20260227_executive_briefings.py` | Alembic migration |
| `backend/app/services/executive_briefing_service.py` | Core service: data collection + LLM synthesis |
| `backend/app/services/skills/executive_briefing/BRIEFING_PROMPT.md` | System prompt with scoring framework |
| `backend/app/services/executive_briefing_jobs.py` | APScheduler hourly job |
| `backend/app/api/endpoints/executive_briefing.py` | FastAPI endpoints (7 routes) |
| `backend/main.py` (lines 529, 5973) | Router + scheduler registration |
| `frontend/src/services/executiveBriefingApi.js` | API client (6 methods) |
| `frontend/src/components/briefing/BriefingRenderer.jsx` | Narrative sections + recommendation cards |
| `frontend/src/components/briefing/FollowupChat.jsx` | Interactive Q&A chat panel |
| `frontend/src/pages/ExecutiveBriefingPage.jsx` | Main page (3 tabs) |
| `frontend/src/config/navigationConfig.js` (line 115) | Navigation entry |
| `frontend/src/App.js` (line 321) | Route definition |

---

## LLM Fallback Chain

The feature uses `ClaudeClient` which supports dual backends:

1. **Claude API** (primary): Uses `CLAUDE_API_KEY` with Claude Sonnet 4.6 for briefing generation and follow-ups
2. **vLLM / OpenAI-compatible** (fallback): Uses `LLM_API_BASE` + `LLM_MODEL_NAME` (e.g., Qwen 3 8B via vLLM) for air-gapped deployments

Environment variables:
```env
CLAUDE_API_KEY=sk-ant-...          # Claude API key
CLAUDE_MODEL_SONNET=claude-sonnet-4-6  # Model for briefings
LLM_API_BASE=http://llm:8001/v1   # vLLM fallback endpoint
LLM_MODEL_NAME=qwen3-8b           # Fallback model name
```

---

## Verification

1. **Migration**: `docker compose exec backend alembic upgrade head` — verify 3 tables created
2. **Generate**: `curl -X POST http://localhost:8000/api/v1/executive-briefing/generate -H "Authorization: Bearer $TOKEN"` — returns `{briefing_id, status: "pending"}`
3. **Poll**: `curl http://localhost:8000/api/v1/executive-briefing/{id}` — status transitions to `completed` with narrative
4. **Follow-up**: `curl -X POST .../executive-briefing/{id}/ask -d '{"question":"Why did service level drop?"}'` — returns natural language answer
5. **Frontend**: Navigate to `/strategy-briefing` — page loads, "Generate Now" works, narrative renders, follow-up chat functional
6. **Fallback**: Set `CLAUDE_API_KEY=""` and configure `LLM_API_BASE` — verify briefing generates via vLLM
7. **Schedule**: Configure via Settings tab, verify job runs at configured time in Docker logs
