# Claude Skills Migration Plan

**Date**: February 2026
**Status**: In Progress

See [CLAUDE_SKILLS_STRATEGY.md](CLAUDE_SKILLS_STRATEGY.md) for full analysis and rationale.
See [CLAUDE_SUBSCRIPTION_GUIDE.md](CLAUDE_SUBSCRIPTION_GUIDE.md) for pricing and configuration.

---

## Phase 1: Documentation + Cleanup (Current)

### Completed
- [x] `docs/CLAUDE_SKILLS_STRATEGY.md` — Full analysis document
- [x] `docs/CLAUDE_SKILLS_MIGRATION_PLAN.md` — This file
- [x] `docs/CLAUDE_SUBSCRIPTION_GUIDE.md` — Subscription guide

### Cleanup: PicoClaw/OpenClaw Code Removal
- [x] Delete `deploy/picoclaw/` and `deploy/openclaw/` directories
- [x] Delete backend: `edge_agents.py` (model), `edge_agent_service.py`, `edge_agents.py` (endpoint)
- [x] Delete frontend: PicoClawManagement, OpenClawManagement, EdgeAgentSecurity, SignalIngestionDashboard, edgeAgentApi.js
- [x] Remove references from App.js, navigationConfig.js, main.py, base.py, deps.py, Makefile
- [x] Delete orphaned .md files (15 stale phase summaries and superseded docs)
- [x] Delete `PICOCLAW_OPENCLAW_IMPLEMENTATION.md`, `docs/PICOCLAW_OPENCLAW_GUIDE.md`

## Phase 2: Claude Skills Framework

### New Files
- [x] `backend/app/services/skills/__init__.py`
- [x] `backend/app/services/skills/base_skill.py` — SkillDefinition, SkillResult, SkillError
- [x] `backend/app/services/skills/claude_client.py` — Anthropic SDK wrapper + vLLM fallback
- [x] `backend/app/services/skills/skill_orchestrator.py` — Decision routing
- [x] 11 SKILL.md files with heuristic rules extracted from TRM fallback logic

### Integration
- [x] Feature flag: `USE_CLAUDE_SKILLS=false` (off by default)
- [x] `site_agent.py` modification to route through skill orchestrator when enabled

## Phase 3: RAG Decision Memory

### New Files
- [x] `backend/app/models/decision_embeddings.py` — pgvector model
- [x] `backend/app/services/decision_memory_service.py` — Embed, search, backfill
- [x] Alembic migration for `decision_embeddings` table

### Extensions
- [x] `rag_context.py` — `get_decision_context()` function
- [x] `knowledge_base.py` — Import DecisionEmbedding for KBBase registration

## Phase 4: Future Work (Not in Current Scope)

### TRM Deprecation (after skills validated in production)
- [ ] Remove TRM training pipeline (~37,000 lines)
- [ ] Remove TRM model files (11 files, ~6,700 lines)
- [ ] Remove `SiteAgentModel`, `site_agent_trainer.py`
- [ ] Remove PyTorch inference dependency

### Frontend
- [ ] Claude Skills dashboard (skill invocation metrics, decision memory stats)
- [ ] Replace TRMDashboard, PowellDashboard, HiveDashboard with skills UI

### Advanced Integration
- [ ] Claude MCP server wrapping Autonomy REST API
- [ ] Autonomy Plugin for Claude private marketplace
- [ ] Cowork integration for executive S&OP briefs
- [ ] Agent SDK autonomous planning agents
- [ ] Refactor signal_ingestion_service.py for Claude-based signal processing
