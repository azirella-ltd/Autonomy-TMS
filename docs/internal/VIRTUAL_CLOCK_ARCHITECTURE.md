# Virtual Clock Architecture

**Status**: Phase 1 complete (Apr 2026) — infrastructure + SAP Demo frozen.
**Rollout**: Incremental migration of `date.today()` callsites.

## Problem

Static demo environments need **reproducibility over time**. A demo built today should work identically a year from now. But:

1. **ERP data ages** — A pre-extracted snapshot (e.g., SAP CAL FAA frozen at Nov 2025) has a fixed reference date. Forward PIRs, planned orders, and forecasts extend ~5 months from that reference date. Five months after the snapshot, all forward data is in the past.

2. **External data moves forward** — The Context Engine ingests weather, economic, and market signals daily. Even if we shifted ERP data forward to align with today, external data would continue to advance, breaking any reproducibility.

3. **Production has the opposite need** — Real tenants must use the real current date for everything.

## Solution: Per-Tenant Virtual Clock

Two orthogonal concepts, both scoped to the tenant:

### 1. Time Mode
- `time_mode = 'live'` → `today()` returns the real current date (production default)
- `time_mode = 'frozen'` → `today()` returns `virtual_today` (a fixed historical date)

### 2. External Data Mode
- `external_data_mode = 'live'` → Context Engine calls external APIs (weather, FRED, GDELT, etc.)
- `external_data_mode = 'snapshot'` → Context Engine replays pre-captured signals from storage

### Example Tenant Configurations

| Tenant | time_mode | virtual_today | external_data_mode | Purpose |
|--------|-----------|---------------|-------------------|---------|
| Production customer A | live | NULL | live | Real operations |
| Production customer B | live | NULL | live | Real operations |
| Food Dist Demo | live | NULL | live | Rolling demo (data stays fresh via regeneration) |
| **SAP Demo** | **frozen** | **2025-11-20** | **snapshot** | Reproducible demo using SAP CAL FAA frozen data |
| Learning tenant | live | NULL | live | Beer Game / training |

## Schema

```sql
ALTER TABLE tenants ADD COLUMN time_mode VARCHAR(16) NOT NULL DEFAULT 'live';
ALTER TABLE tenants ADD COLUMN virtual_today DATE;
ALTER TABLE tenants ADD COLUMN external_data_mode VARCHAR(16) NOT NULL DEFAULT 'live';
ALTER TABLE tenants ADD COLUMN external_snapshot_id VARCHAR(100);

CREATE INDEX ix_tenants_time_mode ON tenants(time_mode);
ALTER TABLE tenants ADD CONSTRAINT ck_tenants_frozen_has_virtual_today
    CHECK (time_mode != 'frozen' OR virtual_today IS NOT NULL);
```

## API

The clock helper lives in `app/core/clock.py`:

```python
from app.core.clock import tenant_today, tenant_today_sync, config_today, config_today_sync

# Async (FastAPI endpoints, async services)
today = await tenant_today(tenant_id, db)
today = await config_today(config_id, db)  # resolves tenant from config

# Sync (background jobs, training scripts)
today = tenant_today_sync(tenant_id, sync_db)
today = config_today_sync(config_id, sync_db)
```

### Caching

Clock state is cached per-process (in-memory dict) to avoid a DB hit on every call. Call `invalidate_cache(tenant_id)` after updating a tenant's `time_mode` or `virtual_today`.

## Rules: What Uses Virtual Today vs Real Time

### MUST use virtual today (supply-chain time)
- Planning horizons ("next N weeks from today")
- Inventory aging / expiry calculations
- Decision urgency decay (relative to decision creation date)
- Forecast generation windows
- CDC delta detection ("what changed since last tick?")
- Decision Stream chart time windows
- SLA / order age calculations
- Forecast exception detection periods
- Safety stock buffer calculations
- Net requirements calculation start dates

### MUST NOT use virtual today (system/security time)
- Audit log timestamps (SOC II requirement)
- JWT / session expiry
- Rate limiting / throttling
- Cron scheduler triggers (real wall clock)
- Monitoring / health checks
- `created_at` / `updated_at` columns (system metadata)
- Password reset token expiry
- API request correlation IDs

### Rule of thumb
*If the calculation is about **supply chain time**, use virtual today. If it's about **system time or security**, use real time.*

## External Signal Snapshot Strategy (Phase 2 — Not Yet Implemented)

For frozen demo tenants, external signals must be replayed from a snapshot:

1. **Capture**: Every day, the Context Engine writes the day's external signals to `external_signal_snapshot` table (keyed by `signal_date`). Production tenants write live data, which automatically builds the snapshot.

2. **Replay**: Frozen demo tenants read external signals from `external_signal_snapshot WHERE signal_date = tenant.virtual_today`.

3. **Snapshot bundles**: A snapshot identifier (`external_snapshot_id`) groups a set of captured signals, so a demo tenant can be pointed at a pre-curated "Nov 2025" bundle without pulling from live production tenants.

## CDC Replay for Demo Tenants (Phase 3 — Not Yet Implemented)

- Production tenants: poll ERP MCP in real-time, feed events into agents
- Demo tenants: pre-captured CDC events stored with offsets relative to `virtual_today`, replayed in order as the demo unfolds

## Current Rollout Status

**Phase 1 (complete)** — Apr 2026:
- [x] Migration: tenant columns added
- [x] `Tenant` model updated
- [x] `app/core/clock.py` helper created
- [x] SAP Demo tenant (id=20) set to frozen at 2025-11-20
- [x] Forecast exception detection uses tenant clock (2 callsites)
- [x] Decision Stream time-series endpoint uses tenant clock

**Phase 2 (in progress)** — Incremental migration:
- [ ] Planning cascade services
- [ ] Inventory aging / expiry calculations
- [ ] Supply plan generation
- [ ] SLA calculations
- [ ] ~80 remaining `date.today()` callsites in business logic

**Phase 3 (future)**:
- [ ] External signal snapshot table + daily capture
- [ ] Context Engine playback mode
- [ ] CDC event replay for demo tenants
- [ ] Demo tenant creation tooling (clone + freeze)

## Why This Matters

Beyond fixing the SAP Demo aging problem, this architecture enables:

1. **Reproducible demos** — Every customer sees identical outcomes
2. **Regression testing** — Freeze a tenant at a specific date to test agent behavior
3. **Historical replay** — "Show me what Autonomy would have decided in Nov 2025"
4. **Accelerated demos** — Future enhancement: `tick_rate > 1` to fast-forward a week in 10 minutes
5. **Multi-demo catalog** — SAP Demo (Nov 2025), Odoo Demo (live), Food Dist Demo (live) — each with its own universe

## Migration Pattern

For existing callsites, the mechanical transformation is:

```python
# Before
from datetime import date
today = date.today()

# After (async, has tenant_id)
from app.core.clock import tenant_today
today = await tenant_today(tenant_id, db)

# After (sync, has config_id)
from app.core.clock import config_today_sync
today = config_today_sync(config_id, sync_db)
```

If the callsite has neither `tenant_id` nor `config_id` in scope, resolve the tenant from a parent object or pass it through the call chain.

Callsites that legitimately need real time (audit, JWT, cron) should keep using `date.today()` / `datetime.now()` unchanged.
