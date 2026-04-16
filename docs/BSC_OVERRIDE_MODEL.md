# BSC 5-Axis Override Model — TMS Port

**Status**: Port guide for acer-nitro. SCP reference implementation shipped 2026-04-16 on `main` at commit `69ee81d3`.
**Sister docs**: `CONSTRAINED_SOLVER_PORT.md` + `CONSTRAINED_SOLVER_PORT_TIER_3_ADDENDUM.md` in this directory.

---

## Why this exists

The BSC objective function that drives the tactical planner is **not a single tenant-flat weight vector**. Users want weights that vary by:

1. **Time phase** relative to today — near-term emphasis on cost / margin, longer-horizon emphasis on service level (OTIF).
2. **Calendar events** — Christmas, Black Friday, Chinese New Year, Singles Day, Easter, Ramadan, back-to-school. During peak-retail periods, customer service dominates; during carrier-capacity-short periods (CNY factory closures), the balance shifts.
3. **Product hierarchy** — premium categories get higher customer-service weighting than commodity SKUs.
4. **Geo hierarchy** — different regions have different service-level expectations.
5. **Tenant-level defaults** — the root, always present.

SCP landed a unified 5-axis override model on `tenant_bsc_weights_override` and `tenant_bsc_metric_goal_override` with a single-resolver pattern. TMS needs the same model with the same schema for cross-product consistency — BSC weights are a tenant-wide concept, not SCP-specific.

## Recommended port path

### Option A (recommended): share via Autonomy-Core canonical

Move `tenant_bsc_weights`, `tenant_bsc_metric_goals`, `tenant_bsc_weights_override`, `tenant_bsc_metric_goal_override`, `calendar_event`, `calendar_event_instance` into `azirella-data-model.governance`. Both SCP and TMS import. One source of truth; a tenant running both products sees consistent BSC across them.

File a `CONSUMER_ADOPTION_LOG.md` entry for the migration. Both products bump their `azirella-data-model` pin.

### Option B: per-product copies

Each product has its own tables. Risks drift when a customer tunes BSC weights in SCP and doesn't realise TMS has its own separate weights. Only pick this if there's a concrete reason the schema needs to diverge (there isn't today).

**Recommendation: A. The schema has no TMS-specific fields; sharing via canonical is strictly better.**

## SCP reference implementation — files to port

From SCP `main` branch:

| File | Purpose |
|---|---|
| `backend/migrations/versions/20260416_k_bsc_overrides_and_calendar.py` | Schema for all six tables + seed of 10 common calendar events with 2026 instances |
| `backend/app/services/tactical/bsc_resolver.py` | Per-solve resolver. `BscResolver(db, tenant_id, as_of)` with `weights_for(product_id, site_id, plan_date)` and `metric_goal_for(metric_code, ...)` |
| `backend/app/services/tactical/bsc_attainment.py` | [-1, 1] attainment math; used by the resolver's consumer, not modified here |
| `backend/app/api/endpoints/bsc_overrides.py` | CRUD + resolver-preview endpoints |
| `backend/app/services/tactical/rl_training_harness.py` | `BscRewardFunction.compute(trajectory, db=db)` that honours per-cell resolved weights |

## What changes vs SCP on the TMS side

The schema is product-agnostic; the hierarchy walkers are not. SCP walks `product_hierarchy_node` + `site` → `geography`. TMS likely walks its own hierarchy tables. Two minor changes:

### Hierarchy walkers

In `BscResolver._product_path()` — SCP walks `product_hierarchy_node` by code. TMS equivalent: walk whatever the TMS product catalogue uses (may or may not share `product_hierarchy_node`). If TMS does not have hierarchical products, leave `_product_path()` returning empty — the resolver still works, just without product-axis specificity.

In `BscResolver._geo_path()` — SCP walks `site.geo_id` → `geography.parent_geo_id`. TMS uses different site primitives; adapt to TMS's actual site table. Same graceful-degradation pattern: empty path means geo axis is unused.

### Calendar events — TMS-specific additions

SCP seeded 10 retail-heavy events. TMS should add transport-specific ones:

- `PEAK_PRODUCE_SEASON` — late May through September, US produce trucking demand surge
- `HURRICANE_SEASON` — June-November (Atlantic), capacity + lead-time disruption risk
- `CHASSIS_SHORTAGE_Q4` — historical pattern of intermodal chassis constraints Oct-Dec
- `FUEL_SURCHARGE_RESET` — quarterly, when contract renegotiations happen
- `DRIVER_HOS_RULE_CHANGE` — one-off events for FMCSA policy updates

These populate the same `calendar_event` / `calendar_event_instance` tables if Option A is chosen; otherwise TMS's own copy.

### TMS-specific metric codes

SCP's default metric goals (from migration `20260416_h`):

| Perspective | Default metric code | TMS equivalent |
|---|---|---|
| FINANCIAL | `plan_cost_ratio` | `cost_per_mile_ratio` or `cost_per_shipment_ratio` |
| CUSTOMER | `fill_rate_actual` | `on_time_delivery_ratio` |
| INTERNAL | `capacity_utilisation` | `trailer_utilisation` / `lane_committed_utilisation` |
| LEARNING | `plan_override_rate` | same (product-agnostic) |

When porting the seed data, TMS replaces the metric codes. Same table structure, different substance.

## User examples translated to TMS

**"Near-term cost emphasis, mid-term on-time emphasis"** — time-phased:

```sql
-- Weeks 0-6: minimise spot rates, small detention exposures
INSERT INTO tenant_bsc_weights_override
  (tenant_id, horizon_start_week, horizon_end_week,
   w_financial, w_customer, w_internal, w_learning, effective_from)
VALUES (<tms_tenant_id>, 0, 6, 0.55, 0.25, 0.15, 0.05, '2026-04-16');

-- Weeks 13-26: OTD commitments to tier-1 customers dominate
INSERT INTO tenant_bsc_weights_override
  (tenant_id, horizon_start_week, horizon_end_week,
   w_financial, w_customer, w_internal, w_learning, effective_from)
VALUES (<tms_tenant_id>, 13, 26, 0.25, 0.60, 0.10, 0.05, '2026-04-16');
```

**"CNY factory-closure weeks — shift from cost to equipment-availability"** — calendar-event:

```sql
INSERT INTO tenant_bsc_weights_override
  (tenant_id, calendar_event_code,
   w_financial, w_customer, w_internal, w_learning, effective_from)
VALUES (<tms_tenant_id>, 'CHINESE_NEW_YEAR',
        0.20, 0.40, 0.35, 0.05, '2026-04-16');
-- Internal (equipment utilisation / repositioning) weighted higher because
-- the scarce resource during CNY is ocean capacity + chassis.
```

**"Produce season in California — raise customer weight for refrigerated SKUs in Western US"** — compound product × geo × calendar:

```sql
INSERT INTO tenant_bsc_weights_override
  (tenant_id, product_hierarchy_node_id, geo_hierarchy_node_id,
   calendar_event_code,
   w_financial, w_customer, w_internal, w_learning, effective_from)
VALUES (<tms_tenant>,
        <REFRIGERATED_node_id>,
        'US-WEST',
        'PEAK_PRODUCE_SEASON',
        0.10, 0.75, 0.10, 0.05, '2026-04-16');
-- Specificity = 3; beats any less-specific override
```

## Where this lands in the TMS solver

Follows exactly the SCP pattern. The solver's `SolveInputs.bsc_goals` list gets populated per-cell by the resolver instead of once per tenant. In TMS, cells are `(lane, period)` rather than `(product, site, period)` — the resolver call signature needs `product_id=None` or a lane-derived stand-in, and `site_id` should be the destination site or origin site (pick one convention and stick to it).

Suggested mapping for a TMS cell:
- `product_id = None` (TMS plans at lane granularity, not product) — OR the commodity class if product hierarchy is being used
- `site_id = destination_site_id` (where the shipment is going — arguably the more customer-facing end)
- `plan_date = period_start_date`

Then the resolver's geo-hierarchy walk picks up the destination site's geography, and compound overrides involving "destination = US-WEST" resolve correctly.

## Port effort estimate

- Schema migration (copy as-is, rename if you want TMS-specific table names, or share via Core): half a day
- Resolver port with TMS-specific hierarchy walkers: 1-2 days
- API endpoint port: half a day (SCP's FastAPI-style translates directly)
- Admin UI port: 1-2 days frontend work (same React component shape)
- TMS-specific metric code seeding + transport-domain calendar events: half a day
- Wiring into TMS solver (equivalent of `ConstrainedPlanGenerator`): 1 day

Total: **4-6 days** if shared via Core (Option A). Add 2 days if duplicated in TMS's own schema.

## Do not

- Do not merge BSC weights across SCP and TMS at the weight-value level. Each tenant in each product has its own weights, even if sharing the schema. The "unified view" is schema-level, not data-level.
- Do not invent a TMS-specific override model. The 5-axis pattern is product-agnostic and has been validated by a working implementation.
- Do not let the resolver pick randomly among ties. Ordering is specificity DESC, then effective_from DESC. A new override on the same specificity should supersede the older one, not compete.

## SCP references for context

- `docs/internal/architecture/TIER_3_GNN_FIRST_PLANNING.md` — where BSC weights fit into the RL reward function for the twin-trained GraphSAGE policy.
- `docs/internal/architecture/CONSTRAINED_SOLVER_DESIGN.md` — LP/MILP that today consumes the flat tenant weights; per-cell resolution is the upgrade pending in `ConstrainedPlanGenerator`.
- `backend/app/services/tactical/bsc_attainment.py` — the [-1, 1] attainment math.

## Status summary

- SCP: shipped. Endpoints live. Resolver validated end-to-end.
- TMS: TBD on acer-nitro. This guide + SCP reference implementation is the blueprint.
- Cross-product coordination: Option A (shared via Core) is the recommended path but requires a coordinated release touching both products' `requirements.txt` pins.
