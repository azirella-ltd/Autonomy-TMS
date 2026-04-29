# Cross-plane data exchange — MCP only

**Hard rule.** Any direct read of another plane's database (today: SCP) must go through that plane's **MCP server**. Direct cross-plane DB reads, shared Docker networks for cross-plane DB hosts, and shared connection pools are deprecated — they couple deployment topology in ways the [SCP/TMS separation decision](../../../Autonomy-Core/docs/MIGRATION_REGISTER.md) explicitly rejects.

## Scope

This rule applies to every plane the TMS backend talks to:
- **SCP** — read SCP-resident data (supply plan, ATP, demand forecast, master data) via SCP's MCP server.
- **Future DP plane** — read demand envelope via DP's MCP server (once DP is physically extracted; today the DP plane is logical-only — see [MIGRATION_REGISTER §3.6](../../../Autonomy-Core/docs/MIGRATION_REGISTER.md)).
- **Future WMS / Sales / Revenue planes** — same rule when they exist.

Within-plane DB access (TMS reading TMS) is unaffected — that's just normal application code.

## Why

The cross-plane contract is a versioned MCP tool surface, not a SQL dialect. Going through MCP gives us:

1. **Topology-independent code.** TMS source doesn't know or care whether SCP runs on the same host, a different host, or in a different cloud region. MCP is HTTP-tier; works identically across all three.
2. **No cross-host DB credentials.** The `tms_reader@autonomy-scp-db` pattern only ever worked when both stacks were colocated on a single Docker host (`msi-stealth`). MCP needs only the SCP MCP endpoint URL + a service token — both are normal HTTP-API config, easy to rotate.
3. **Schema isolation.** SCP can refactor its tables without breaking TMS. The MCP tool surface is the contract; SCP-side serialisation handles schema migrations.
4. **Audit + governance.** Every cross-plane read goes through the MCP server's existing logging, auth, and rate limits. Direct DB reads bypass those.
5. **Failure isolation.** When SCP's MCP is down, TMS gets a clean error response and can degrade gracefully. When SCP's DB is up but its app is down, MCP fails clean; direct DB reads silently succeed and might serve TMS uncommitted or pre-migration data.
6. **Symmetric architecture.** SCP→TMS reads use TMS's MCP (see TMS-exposed tools below). It would be inconsistent to keep TMS→SCP on direct DB while SCP→TMS goes via MCP.

## Existing infrastructure

### TMS exposes for cross-plane consumers

`backend/app/mcp_server/server.py` runs as a sidecar (HTTP on 8002, proxied via Nginx at `/mcp`). Tool modules in `backend/app/mcp_server/tools/`:

| Module | Purpose | Notable tools |
|---|---|---|
| `ad11.py` | SCP × TMS intersection reads (AD-11 contract) | `get_carrier_capacity`, `get_dock_availability`, `get_active_exceptions` |
| `forecast.py` | TMS-side lane / shipment forecasts | `get_forecast` |
| `decision_stream.py` | TMS decision stream events | `get_decision_stream` |
| `network.py` | Network-level state | `get_network_status` |
| `kpi.py` | KPI metrics | `get_kpi_metrics` |
| `atp.py` | ATP / capacity promise context | (multiple) |
| `governance.py` | Governance pipeline state | `get_governance_status` |
| `override.py` | User-override audit | (multiple) |
| `reasoning.py` | Decision reasoning chains | (multiple) |

If SCP needs additional TMS-resident data, **add a tool here** rather than expecting SCP to read `autonomy-tms-db` directly.

### SCP exposes for TMS consumption

Mirror surface lives in `Autonomy-SCP/backend/app/mcp_server/tools/`:

| Module | Purpose | Notable tools |
|---|---|---|
| `intersection_reads.py` | SCP-side reads TMS calls per AD-11 | `get_atp_constraints`, `get_demand_forecast`, `get_supply_plan` |
| Plus: `forecast.py`, `network.py`, `kpi.py`, `decision_stream.py`, `governance.py`, `override.py`, `reasoning.py`, `atp.py` |

When TMS needs SCP-resident data **not** already covered, the right move is to **request a new SCP MCP tool** — not to add a direct DB read.

## Migration backlog

Existing TMS direct-DB-read sites that violate this rule (allowed transitionally, tracked):

- [`backend/app/services/tms/scp_etl.py`](../../backend/app/services/tms/scp_etl.py) — `FoodDistExtractor` class with 10 queries against SCP tables (`supply_chain_configs`, `site`, `trading_partners`, `transportation_lane`, `product`, `shipment`, `outbound_order_line`, `inbound_order_line`).
- [`backend/scripts/extract_scp_food_dist.py`](../../backend/scripts/extract_scp_food_dist.py) — CLI driver for the above.
- [`backend/app/core/config.py:222`](../../backend/app/core/config.py#L222) — `SCP_DB_URL: Optional[str]` setting (the entire credential is a transitional escape hatch).

Migration target: SCP exposes `scp_export_config_snapshot(config_name) -> ConfigSnapshot` MCP tool; TMS replaces the direct queries with the call and keeps staging-table persistence. After migration, `tms_reader` Postgres role + `SCP_DB_URL` retire.

Tracked in [Autonomy-Core MIGRATION_REGISTER §3.7](../../../Autonomy-Core/docs/MIGRATION_REGISTER.md).

## How to apply (every TMS PR)

- **New code that needs SCP-resident data** → use SCP's MCP. If the right tool doesn't exist, request it from the SCP team (or write it on the SCP side first); don't extend `scp_etl.py`.
- **New code in any plane that needs TMS-resident data** → add a tool to TMS's `app/mcp_server/tools/` rather than allowing a direct read into `autonomy-tms-db`.
- **Editing `scp_etl.py` or `extract_scp_food_dist.py`** → migrate that piece to MCP rather than extending it. The whole file is on the migration target list.
- **Adding new fields to `SCP_DB_URL`-using settings** → do not. New cross-plane config goes through the MCP client, not the legacy SCP DB credential.
- **Co-locating TMS with SCP for dev** → fine, opt in with `SCP_COLOCATED=1` (Makefile gate). Don't make it the default.

## What this rule does NOT cover

- **MCP writebacks** are a separate design question. Today the rule is about reads. Cross-plane writes need explicit per-tool design (audit, idempotency, rollback) — don't add them implicitly.
- **Within-plane DB access** is unaffected. TMS reading its own DB is normal application code.
- **Real-time streaming** (e.g. SCP supply-plan updates pushed to TMS) is out of scope of this rule. Current ETL is snapshot semantics; if streaming is needed later, that's a separate cross-plane contract.

---

**Authority:** [Autonomy-Core/CLAUDE.md](../../../Autonomy-Core/CLAUDE.md) §"Cross-product engineering rules" — cross-app data exchange via MCP.

**Tracked migration:** [Autonomy-Core/docs/MIGRATION_REGISTER.md §3.7](../../../Autonomy-Core/docs/MIGRATION_REGISTER.md).

**Companion architectural memory:** project memory `project_scp_tms_separation.md` (separation as default deployment topology).
