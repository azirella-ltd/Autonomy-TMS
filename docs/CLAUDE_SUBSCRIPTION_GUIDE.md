# Claude Subscription & Configuration Guide

**Date**: February 2026

## What You Need

The Autonomy platform uses Claude in two ways that require separate subscriptions:

1. **Claude API** (per-token pricing) — For programmatic decision-making (Skills), signal classification, escalation formatting
2. **Claude Subscriptions** (per-user pricing) — For human users accessing Cowork, chat, and plugins

---

## 1. Claude API Setup

### Get an API Key
1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Create an account or sign in
3. Navigate to API Keys
4. Create a new key with a descriptive name (e.g., "autonomy-production")

### Configure Environment Variables
```bash
# Required for Claude Skills
CLAUDE_API_KEY=sk-ant-api03-...     # From console.anthropic.com

# Model selection (defaults shown)
CLAUDE_MODEL_HAIKU=claude-haiku-4-5-20251001    # Fast, cheap ($1/$5 per M tokens)
CLAUDE_MODEL_SONNET=claude-sonnet-4-6            # Balanced ($3/$15 per M tokens)
CLAUDE_MODEL_OPUS=claude-opus-4-6                # Best quality ($5/$25 per M tokens)

# Feature flag
USE_CLAUDE_SKILLS=false    # Set to true to enable Claude Skills (off by default)

# Existing fallback (keep configured)
LLM_API_BASE=http://localhost:8001/v1    # vLLM/Qwen fallback
LLM_API_KEY=not-needed
LLM_MODEL_NAME=qwen3-8b
```

### API Pricing (February 2026)

| Model | Input (per M tokens) | Output (per M tokens) | Prompt Cache Read | Best For |
|-------|---------------------|----------------------|-------------------|----------|
| Haiku 4.5 | $1.00 | $5.00 | $0.10 | High-volume calculation decisions (PO, Buffer, TO, Rebalancing) |
| Sonnet 4.6 | $3.00 | $15.00 | $0.30 | Judgment decisions (Quality, Forecast, MO, Maintenance, Subcontracting) |
| Opus 4.6 | $5.00 | $25.00 | $0.50 | Executive analysis, complex multi-step reasoning |

### Smart Routing (Recommended)
The skill orchestrator routes each decision type to the appropriate model:

| Decision Type | Model | Typical Cost/Call | Rationale |
|--------------|-------|-------------------|-----------|
| ATP Executor | Haiku | $0.0012 | Tier-based arithmetic, low judgment |
| PO Creation | Haiku | $0.0012 | Order-up-to formula |
| Inventory Buffer | Haiku | $0.0012 | 6 prioritized rules |
| Order Tracking | Haiku | $0.0012 | Threshold comparison |
| Inventory Rebalancing | Haiku | $0.0012 | Pair identification |
| MO Execution | Sonnet | $0.0054 | Multi-objective sequencing |
| TO Execution | Sonnet | $0.0054 | Consolidation judgment |
| Quality Disposition | Sonnet | $0.0054 | Context-dependent judgment |
| Forecast Adjustment | Sonnet | $0.0054 | Signal-to-noise separation |
| Maintenance Scheduling | Sonnet | $0.0054 | Risk assessment |
| Subcontracting | Sonnet | $0.0054 | Make-vs-buy trade-offs |

### Monthly Cost Estimates

| Scale | Decision Calls/Day | Smart-Routed API Cost |
|-------|-------------------|----------------------|
| Pilot (8 sites) | 50-200 | $5-20/mo |
| Department (50 sites) | 200-800 | $20-75/mo |
| Enterprise (223 sites) | 1,000-2,000 | $95-190/mo |
| Enterprise + chat (5K total) | 5,000 | ~$467/mo |

### Cloud Deployment Options (Data Residency)

| Provider | Configuration | Notes |
|----------|--------------|-------|
| Anthropic Direct | `CLAUDE_API_KEY=sk-ant-...` | Default, US-hosted |
| AWS Bedrock | `CLAUDE_CODE_USE_BEDROCK=1` + AWS credentials | AWS regions |
| Google Vertex AI | `CLAUDE_CODE_USE_VERTEX=1` + GCP credentials | GCP regions |
| Azure AI Foundry | `CLAUDE_CODE_USE_FOUNDRY=1` + Azure credentials | Azure regions |

For customers requiring data residency: use Bedrock/Vertex/Foundry to keep inference within their existing cloud contract.

---

## 2. Claude Subscriptions (Human Users)

### Plan Recommendations

| Role | Plan | Price | Why |
|------|------|-------|-----|
| **Developers** (building/testing skills) | Pro | $20/user/mo | Cowork access for plugin dev, adequate limits |
| **Supply planners** (daily operations) | Team | $30/user/mo | Shared workspace, higher limits, admin controls |
| **Executives** (VP, S&OP Director) | Max | $100-200/user/mo | Highest priority, background tasks, near-zero latency |
| **Organization-wide** | Enterprise | ~$60/seat/mo (min 70) | SSO/SCIM, audit logs, 500K context window |

### Typical Customer Deployment

| Users | Plan | Monthly |
|-------|------|---------|
| 3 developers | Pro | $60 |
| 15 supply planners | Team | $450 |
| 3 executives | Max ($200) | $600 |
| **Total** | | **$1,110/mo** |

Or with Enterprise plan (organization-wide): 70 seats minimum = **$4,200/mo**

### What Each Plan Gets

**Pro ($20/mo)**:
- Claude chat + Cowork
- Claude Code access
- Standard usage limits
- Plugin installation

**Team ($30/user/mo)**:
- Everything in Pro
- Shared workspace with admin controls
- Higher usage limits
- Team plugin management

**Max ($100-200/user/mo)**:
- Everything in Pro
- 5x or 20x usage limits
- Priority access, background tasks
- Best for power users (executives using Cowork for S&OP briefs)

**Enterprise (~$60/seat/mo)**:
- Everything in Team
- SSO/SCIM integration
- Audit logs and compliance API
- 500K context window
- Private plugin marketplace
- Per-user provisioning

---

## 3. Self-Hosted Fallback (Air-Gapped Customers)

For customers who cannot use cloud LLM inference, retain the self-hosted vLLM + Qwen 3 configuration:

```bash
# Air-gapped mode: Claude Skills fall back to vLLM
CLAUDE_API_KEY=              # Empty = use vLLM fallback
LLM_API_BASE=http://vllm:8000/v1
LLM_MODEL_NAME=qwen3-8b

# GPU requirements
# Pilot: RTX 4060 (8GB) — Qwen 3 8B AWQ
# Enterprise: RTX 4080 (16GB) — Qwen 3 14B
# Enterprise+: RTX 4090 (24GB) — Qwen 3 32B
```

The skill orchestrator automatically detects missing `CLAUDE_API_KEY` and routes through the OpenAI-compatible vLLM endpoint instead. Decision quality will be lower (Qwen 3 8B vs Claude Opus/Sonnet) but functionality is preserved.

---

## 4. Development Environment

### Recommended Setup
```bash
# Local development — use vLLM for backend, Claude for skill testing
LLM_API_BASE=http://localhost:8001/v1    # Local vLLM
CLAUDE_API_KEY=sk-ant-...                 # For testing Claude Skills
CLAUDE_MODEL_HAIKU=claude-haiku-4-5-20251001  # Cheap iteration
USE_CLAUDE_SKILLS=false                   # Off by default, enable per-test
```

### Dev Cost: ~$40-60/mo per developer
- Pro subscription: $20/mo (Cowork access)
- API calls during dev: ~$20-40/mo (100-500 calls/day on Haiku)
- vLLM local: $0 marginal

### CI Pipeline
- Unit tests: Mocked LLM responses ($0)
- Integration tests: vLLM container ($0)
- Quality benchmarks (nightly): Claude Batch API at 50% discount (~$14/mo)
