# Claude Skills Strategy: Replacing PicoClaw/OpenClaw + TRMs

**Date**: February 2026
**Status**: Approved for implementation

## Executive Summary

Replace two external agent runtimes (PicoClaw, OpenClaw) and 11 TRM neural networks with Claude's managed ecosystem: Skills for execution decisions, RAG decision memory for continuous learning, Cowork for executive interfaces, and MCP for tool integration. This eliminates ~37,000 lines of training pipeline code, removes security-questionable dependencies, and produces better AI quality at lower total cost of ownership.

---

## 1. Why: The Problem with PicoClaw/OpenClaw

### Security Debt
- **OpenClaw**: 7+ published CVEs including CVE-2026-25253 (CVSS 8.8, critical RCE). January 2026 audit found 512 total vulnerabilities, 8 critical. ClawHavoc campaign discovered 1,184 malicious skills on ClawHub marketplace. WhatsApp integration uses Baileys (unofficial, ToS risk). Founder left for OpenAI; project moved to foundation governance.
- **PicoClaw**: Pre-v1.0, no CVEs published (indicating lack of scrutiny), no SECURITY.md, no signed binaries. Codebase is 95% AI-generated.

### Engineering Overhead
Maintaining PicoClaw/OpenClaw costs **$3,600-7,200/month** in engineering time:
- CVE tracking & patching: 8-16h/mo
- Fleet Docker management (223 containers): 4-8h/mo
- OpenClaw version upgrades: 4-8h/mo
- Signal ingestion debugging: 4-8h/mo
- vLLM model upgrades: 2-4h/mo
- Security monitoring: 2-4h/mo

### What They Actually Do
- **PicoClaw**: Shell scripts calling `curl` and parsing JSON with `jq`. Deterministic CDC monitoring (zero LLM calls). A single centralized cron job provides the same value.
- **OpenClaw**: Chat interface via messaging apps + signal capture + escalation formatting. Valuable capabilities, but Claude's Slack/Teams MCP connectors + Skills provide the same with better LLM quality (Opus 4.6 vs Qwen 3 8B).

---

## 2. Why: The Problem with TRMs

### Decision Volumes Are Low
| TRM | Actual Volume/Day | Nature |
|-----|-------------------|--------|
| ATPExecutor | ~7/site (default) | Calculation |
| POCreation | Daily MRP batch | Formula + selection |
| InventoryBuffer | ~1,000/cycle | 6 prioritized rules |
| OrderTracking | Hourly scan | Threshold comparison |
| Rebalancing | Daily batch | Pair identification |
| MOExecution | 20-50 | Sequencing judgment |
| TOExecution | 10-30 | Consolidation timing |
| QualityDisposition | 5-20 | Strongly judgment |
| ForecastAdjustment | 0-50 | Signal-to-noise |
| MaintenanceScheduling | 1-5 | Risk assessment |
| Subcontracting | 2-10 | Trade-offs |
| **Total** | **~200-500** | |

### Training Pipeline Is Disproportionate
~37,000 lines of code to produce 7M-parameter models making 200-500 decisions/day:
- 11 TRM implementation files (~6,700 lines)
- `trm_trainer.py`, `trm_curriculum.py`, `trm_site_trainer.py` (~5,200 lines)
- `hive_curriculum.py` (1,126 lines), `hive_feedback.py` (6,957 lines)
- `coordinated_sim_runner.py` (12,314 lines), `decision_cycle.py` (7,583 lines)
- `cdc_retraining_service.py`, `cdt_calibration_service.py` (~1,700 lines)
- Plus GPU infrastructure, PyTorch runtime dependency, 5-phase curriculum

### Heuristics Already Exist
Every TRM has a deterministic engine fallback with well-defined heuristics. The TRM is an adjustment layer on top. Claude Skills encode these same heuristics as natural language instructions.

---

## 3. Architecture: Claude Skills + RAG Decision Memory

### Decision Flow
```
Customer Order / Planning Event
       |
       v
Deterministic Engine (unchanged, always runs first)
       |
       v
RAG Decision Memory: "Find 5 similar past decisions"
       |
       v
Claude Skill (Haiku or Sonnet):
  - Skill instructions (heuristic rules, cached 90% off)
  - Retrieved similar decisions with outcomes (few-shot)
  - Engine output (current state)
  - Decision schema (structured output)
       |
       v
Decision persisted to powell_*_decisions (unchanged)
       |
       v
Embedding stored in decision_embeddings (enriches future retrieval)
```

### Three Decision Tiers
| Tier | TRMs | Model | Cost/Call |
|------|-------|-------|-----------|
| Deterministic (ATP consumption, OrderTracking) | Keep engines only | None | $0 |
| Haiku Skills (PO, Buffer, TO, Rebalancing) | ~1,500/day | Haiku 4.5 | $0.0012 (with caching) |
| Sonnet Skills (Quality, Forecast, MO, Maintenance, Subcontracting) | ~300/day | Sonnet 4.6 | $0.0054 |

### RAG Decision Memory
Instead of training neural network weights from data, retrieve exemplar decisions as few-shot context:
- Embed past decisions using nomic-embed-text (768 dims, existing infrastructure)
- Store in pgvector (existing infrastructure)
- Retrieve top-5 similar decisions by cosine similarity
- Cache hits (similarity >0.95, good outcome) skip LLM entirely

### Cost Over Time
| Month | Cache Hit % | Monthly Cost | Trend |
|-------|-------------|-------------|-------|
| 1 (cold start) | 0% | ~$97 | Building corpus |
| 3 | 15% | ~$66 | Learning patterns |
| 6 | 30% | ~$44 | Rich corpus |
| 12 (mature) | 40% | ~$34 | System gets cheaper as it gets smarter |

---

## 4. Cost Comparison

### Total Cost of Ownership (Enterprise, 223 sites)
| | Current Stack | Claude Ecosystem |
|-|--------------|-----------------|
| LLM inference | $0 (self-hosted) | $467/mo (API, smart-routed) |
| Decision skills | $0 (TRM on GPU) | $130/mo (decreasing) |
| Subscriptions | $0 | $1,050/mo (Team + Max) |
| Infrastructure | $25/mo | $0 |
| GPU amortized | $126/mo | $0 |
| **Engineering overhead** | **$3,600-7,200/mo** | **$1,200/mo** |
| **Total** | **$3,751-7,351/mo** | **$2,847/mo** |

Engineering time is the dominant cost. The Claude ecosystem is 23-61% cheaper overall while providing dramatically better AI quality.

---

## 5. IP Protection Strategy

### Skills Are Not Open Source
The agentskills.io format is an open standard (like JSON). Your skill content is your IP. Using the format does not require publishing.

### Recommended Architecture (Hybrid)
- **Tier 2 skills (calculation-heavy)**: Decision logic in your API, skill is a thin caller. Customer never sees thresholds.
- **Tier 3 skills (judgment-heavy)**: Reasoning heuristics in the skill, but parameterized from your API at runtime. Thresholds come from your backend (protected, customer-specific, calibrated from overrides).

### The Real Moat
Your competitive advantage is NOT the heuristics (textbook inventory management) or the skill format (open standard). It's:
1. The integrated system (35 AWS SC entities, Powell framework, deterministic engines)
2. Calibrated parameters (customer-specific, learned from override data)
3. The feedback loop (override -> outcome -> skill refinement, compounds monthly)
4. Customer-specific decision corpus (tenant-scoped, enriches over time)

---

## 6. What Claude Provides Beyond LLM Chat

### For Executives (VP Supply Chain, S&OP Director)
- **Cowork**: Drop BSC exports and exception reports into a folder, get polished executive summaries
- **Plugins**: Autonomy Plugin packages supply chain skills for any Claude interface
- **Extended Thinking**: Transparent reasoning chains for high-stakes decisions

### For Planners
- **Slack/Teams MCP connectors**: Chat-based planning where they already work
- **Skills**: `/s&op-brief`, `/risk-report`, `/agent-performance` slash commands
- **AskUserQuestion**: Structured escalation with ranked options

### For the Platform
- **Agent SDK**: Autonomous agents for weekly S&OP analysis, exception triage, override analysis
- **Agent Teams**: Lead agent coordinating demand/supply/capacity specialists in parallel
- **MCP Server**: Expose deterministic engines as Claude tools for multi-step reasoning
- **Private Plugin Marketplace**: Distribute Autonomy plugin to customer orgs

---

## 7. Migration Path

### Phase 1: Documentation + Cleanup
- Create strategy/planning/subscription docs
- Delete PicoClaw/OpenClaw code, deploy directories, Docker references
- Delete redundant .md files

### Phase 2: Skills Framework
- 11 SKILL.md files with heuristic rules from TRM fallback logic
- Skill orchestrator replacing TRM model calls
- Feature-flagged integration in site_agent.py

### Phase 3: RAG Decision Memory
- Decision embeddings table (pgvector, extends existing KB infrastructure)
- Decision memory service (embed, search, backfill)
- Integration with skill orchestrator (few-shot context)

### Phase 4: Deprecation (future)
- Remove TRM training pipeline (~37,000 lines) once skills validated
- Remove TRM model files once skill path proven in production
- Refactor signal ingestion for Claude-based processing
- Build Claude MCP server wrapping REST API

### What Stays Unchanged
- Deterministic engines (10 files in engines/)
- Powell decision tables (11 tables, audit trail)
- GNN infrastructure (GraphSAGE + tGNN)
- Override effectiveness tracking
- Hive signal coordination
- Outcome collector (feeds decision memory instead of TRM retraining)
