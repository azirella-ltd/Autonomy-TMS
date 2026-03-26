---
name: code-review
description: Review code changes against Autonomy project conventions and quality standards
---

# Code Review Skill

Review changed code for compliance with Autonomy project rules.

## Checklist

### Critical Rules (must fail review if violated)
1. **No hardcoded values** — no fallback defaults, no `getattr(obj, "field", default)`, no demo data
2. **AWS SC Data Model compliance** — field names match `sc_entities.py`, extensions documented
3. **Tenant isolation** — all queries filtered by `tenant_id` or `config_id`, no cross-tenant leaks
4. **No silent fallbacks** — missing data shows nothing or raises error, never substitutes fake values
5. **Column names match DB schema** — check model definition before using any column name
6. **All API endpoints require authentication** — every GET/POST/PUT/DELETE must have `current_user = Depends(...)`. Unauthenticated endpoints are a SOC II violation.

### Defensive Patterns (must flag if missing)
7. **Safe dict access** — never `.get("FIELD", "").strip()` on CSV/JSONB data. Use `(d.get("FIELD") or "").strip()` because `.get()` returns None when key exists with None value.
8. **FK-aware deletion** — any script that deletes config data must handle ALL foreign key dependencies dynamically, not with a hardcoded table list. Use the `information_schema.table_constraints` approach or CASCADE.
9. **Alembic migration required** — every new table MUST have an Alembic migration. `create_all()` at startup is NOT sufficient for SOC II compliance. Check `backend/migrations/versions/` for coverage.
10. **Pydantic input vs output schemas** — input schemas (UserCreate, UserUpdate) can have strict validation. Response/output schemas (User, UserInDBBase) must be permissive enough to serialize existing DB data without crashing.
11. **main.py scope** — main.py defines `get_current_user` (returns Dict), NOT `get_current_active_user` (from core.security, returns User model). Endpoints defined inline in main.py must use the Dict version.

### Terminology (must use correct terms)
- Game → Scenario, Player → ScenarioUser, Round → Period, Group → Tenant
- SafetyStockTRM → InventoryBufferTRM, node → site, item → product, lane → transportation_lane
- customer_id = trading partner (NOT tenant), tenant_id = organization boundary

### Code Quality
- No unnecessary error handling for impossible scenarios
- No premature abstractions — three similar lines better than one helper used once
- No backwards-compatibility shims — delete unused code completely
- No added comments/docstrings for code not changed
- Frontend: icons from lucide-react only, classNames via `cn()`, API calls via `services/*.js`

### SOC II Compliance
- Tenant-scoped data: RLS policies, `tenant_id` filtering
- No shared superuser access from application code
- Schema changes via Alembic migrations only
- Model checkpoints stored with tenant_id isolation

## Output Format
List issues as: `[CRITICAL/WARNING/INFO] file:line — description`
