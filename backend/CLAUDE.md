# Backend — Claude Code Context

Scoped instructions for working in the backend. Supplements the root CLAUDE.md.

## Stack
- FastAPI (Python 3.10+), SQLAlchemy 2.0 (async + sync sessions), PostgreSQL 15+
- PyTorch 2.2.0 for TRM/GNN models
- Docker container: `backend` mounts `./backend:/app`, entry point `main.py`

## Critical Rules
1. **AWS SC Data Model compliance** — all entities use AWS SC field names (see `models/sc_entities.py`)
2. **No hardcoded values** — no fallbacks, no `getattr(obj, "field", default)` patterns
3. **No cross-tenant data leaks** — always filter by `tenant_id`, RLS enforced at DB level
4. **Column names must match DB schema** — check the model before using any column name
5. **All economic parameters explicit** — holding_cost, stockout_cost must be set per tenant

## Architecture

### Entry Point
`main.py` is ~62K lines. Contains route registration, startup hooks, scheduler setup.
SC config routes are registered IN main.py (not in an endpoints file — the router file is dead code).

### Key Directories
- `app/api/endpoints/` — FastAPI route handlers
- `app/models/` — SQLAlchemy models (AWS SC entities, Powell framework, user/tenant)
- `app/services/` — Business logic (planning, agents, Powell, decision stream)
- `app/services/powell/` — 11 TRM execution services + hive coordination
- `app/services/skills/` — Claude Skills exception handlers (11 SKILL.md files)
- `app/services/aws_sc_planning/` — 3-step planning flow (demand → inventory → requirements)

### Sessions
- `async_session_factory` — for async endpoints (FastAPI dependency injection)
- `sync_session_factory` — for background tasks, schedulers, scripts
- `SessionLocal` in `app.db.session` is actually async despite the name

### Powell Framework Tables
All 11 TRM types have `powell_*_decisions` tables with common columns:
`product_id`, `site_id`, `config_id`, `confidence`, `urgency_at_time`, `decision_reasoning`,
`signal_context`, `cycle_phase`, `cycle_id`, `status` (INFORMED/ACTIONED/OVERRIDDEN/INSPECTED)

### Decision Stream Service
`decision_stream_service.py` — collects decisions from all 11 powell tables + GNN directives.
Key methods: `get_decision_digest()`, `_collect_pending_decisions()`, `_synthesize_digest()`, `chat()`
Returns `(decisions, product_names, site_names)` — always resolve IDs to display names.

### Migrations
Alembic migrations in `backend/migrations/versions/` (NOT `backend/alembic/versions/`).
All schema changes via migration scripts — never ad-hoc SQL.

## Common Patterns

### Adding a new API endpoint
1. Create handler in `app/api/endpoints/your_endpoint.py`
2. Register router in `main.py`: `api.include_router(router, prefix="/your-path", tags=["your-tag"])`

### Querying with tenant isolation
```python
result = await db.execute(
    select(Model).where(Model.config_id.in_(config_filter))
)
```
Never query without tenant/config scoping.

## Build & Deploy
```bash
docker compose build backend     # Build the image
docker compose up -d backend     # Deploy (waits for DB healthy)
# Backend runs on port 8000, proxied at :8088/api/*
```

## Testing
```bash
cd backend
uvicorn main:app --reload        # Local dev server
python scripts/manual_round_driver.py --max-rounds 6  # Debug simulation
```
