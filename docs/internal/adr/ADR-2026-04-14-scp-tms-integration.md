# ADR: SCP↔TMS Integration Should Be ERP-Style, Not Docker-Network-Joined

**Date:** 2026-04-14
**Status:** Accepted (short-term hack in place; proper fix pending)
**Authors:** Trevor + Claude

## Context

Building the Food Dist TMS overlay generator required TMS to consume SCP's
Food Dist shipment history. Initial implementation (2026-04-14) did this by:

1. Adding TMS backend to SCP's external Docker network
2. Creating a `tms_reader` role on SCP's Postgres
3. Exposing `SCP_DB_URL` env var pointing at SCP's DB service hostname
4. Reading raw SQL via a dedicated ETL extractor into TMS staging tables

During implementation the approach surfaced:
- Hostname `db` collision between SCP and TMS when backend joins both networks
  (silently wrote TMS staging tables into SCP's DB on first run)
- Port-binding conflicts (SCP owned `:8000`, TMS needed remap to `:8010`)
- Need for schema-creation shims, in-container `sed` patches on installed
  `azirella_data_model` package, YAML `!override` tags
- Raw SQL reads bypass SCP's contracts — any SCP schema change silently
  breaks TMS
- `SCP_DB_URL` is per-environment plumbing rather than tenant-scoped config

Per [CLAUDE.md](../../../CLAUDE.md) and [TMS Independence](../../../.claude/projects/-home-trevor-Autonomy-TMS/memory/feedback_tms_independence.md):
TMS and SCP are sibling products with independent tech stacks from the DB
up. Sharing is meant to be via MCP or package-level npm/Python deps, not
DB-level coupling.

## Decision

SCP should plug into TMS the same way other external systems do (SAP,
Dynamics 365, Odoo, Blue Yonder, Infor M3) — as an ERP-class integration
under `backend/app/integrations/scp/` consumed by the existing
`tms_extraction_service.py` dispatcher and persisted via the
`ERPConnection` model.

```
backend/app/integrations/scp/
  __init__.py
  connection.py       # LAN URL, bearer token, health check
  extractor.py        # HTTPS GET against SCP's REST API
  data_mapper.py      # SCP JSON → tms_src_scp_* staging
  SCP.md              # integration contract doc
```

This means:
- Drop `SCP_DB_URL` from `Settings` and `docker-compose.override.yml`
- Drop the `autonomy-scp_autonomy-network` external-network join
- Drop the `tms_reader` Postgres role on SCP (no direct DB access)
- TMS reaches SCP via HTTPS at e.g. `msi-stealth.local:8000`
- Credentials live in `erp_connections` rows per tenant, same as SAP
- Existing `extraction_runs` audit trail applies

## Short-term carve-out (in place 2026-04-14)

The current Docker-network + raw-SQL ETL is accepted as a **temporary
training-data unblocker only**. TRM behavioral-cloning needs data flowing
this week; rebuilding the integration properly before collecting training
data would delay ML work.

Files that embody the hack (to be retired by the ERP integration):
- `docker-compose.override.yml` — network join + env vars
- `backend/app/services/tms/scp_etl.py` — raw-SQL extractor
- `backend/scripts/extract_scp_food_dist.py` — entry point
- `backend/app/core/config.py::Settings.SCP_DB_URL`

## Prerequisite for proper fix

SCP does not currently expose paginated historical export endpoints.
Scan of SCP OpenAPI on 2026-04-14 showed structural endpoints (sites,
lanes, partners, products) but no `/shipments?start=&end=&cursor=`,
`/outbound-order-lines`, `/inbound-order-lines` bulk history endpoints.

**The SCP-side work is non-trivial and belongs in a separate workstream
led from the SCP repo.** Until SCP exposes these, TMS cannot build the
proper integration — so the hack persists.

## Consequences

**Positive:**
- Training data flows immediately (TRM BC work unblocked)
- Pattern for SCP integration documented before it becomes tribal knowledge
- Hack is isolated to a small number of files, easy to rip out later

**Negative:**
- Second path exists (direct DB + sibling API) — easy to accidentally
  extend the DB hack instead of migrating to the API
- SCP schema drift can silently break TMS until the migration happens
- msi-stealth is the only host where this hack works (acer-nitro can't
  join a Docker network on a different host)

## Tracking

- Memory: [project_backend_mapper_drift.md](../../../.claude/projects/-home-trevor-Autonomy-TMS/memory/project_backend_mapper_drift.md)
- Memory: [project_food_dist_tms_etl.md](../../../.claude/projects/-home-trevor-Autonomy-TMS/memory/project_food_dist_tms_etl.md)
- Reseed hook: [SCP_FOOD_DIST_RESEED_HOOK.md](../SCP_FOOD_DIST_RESEED_HOOK.md)
- Follow-up: open issue in SCP repo for historical-export endpoints
