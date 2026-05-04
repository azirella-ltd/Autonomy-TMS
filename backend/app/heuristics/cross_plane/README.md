# TMS cross-plane heuristics

**Status:** Phase 1 of [AD-12 migration](https://github.com/azirella-ltd/Autonomy-Core/blob/main/docs/architecture/ARCHITECTURE_DECISIONS.md#ad-12-target-side-license-driven-plane-routing--each-app-owns-its-three-modes) — content moved from `azirella-tms-stub` (Autonomy-Core package) into TMS-the-product. Phase 2 (the per-request tier dispatcher) is a separate PR.

## What this module does

When TMS runs in **HEURISTIC tier** for a tenant — i.e. the customer has not licensed full TMS planning — calls into TMS's cross-plane skills (`transport.lane.estimate_eta`, `transport.load.evaluate_consolidation`, `transport.carrier.recommend`) return conservative-defaults answers from this module instead of from real planning agents.

The HEURISTIC-tier responder is **co-located with the real TMS code** (this repo, this team) so that as the real TMS planning evolves, the heuristic floor evolves in lockstep — no drift across separate packages.

## Public API

```python
from app.heuristics.cross_plane import (
    HEURISTIC_HANDLERS,             # {skill_id: handler} registry
    HEURISTIC_WRITE_SKILLS,         # frozenset of write-side skill IDs
    HEURISTIC_PRODUCER_SIGNATURE,   # "autonomy-tms-heuristics:v0.1.0"
    HeuristicWriteRefused,          # exception for write-skill calls
    estimate_lane_eta,              # direct callable
    evaluate_consolidation,         # direct callable
    recommend_carrier,              # direct callable
    refuse_write,                   # raises HeuristicWriteRefused
    stamp_heuristic_response,       # 4-place warning helper
)
```

Handlers take `(tenant_id, plane_config, inp)` keyword args and return a dict already stamped with the four canonical heuristic markers (`producer_tier="HEURISTIC"`, `producer_signature`, `heuristic_warning`, `heuristic_plane`).

## Skills covered

| Skill | Heuristic |
|---|---|
| `transport.lane.estimate_eta` | Haversine × parametric speed (DOT-HOS / ATRI / FHWA defaults) + dispatch buffer; returns wide ConformalBand |
| `transport.load.evaluate_consolidation` | Always `recommend_consolidation=False` |
| `transport.carrier.recommend` | Tenant default-carrier from config, or `"unknown"` |

Write-side skills (`transport.load.dispatch`, `transport.shipment.tender`, `transport.dock.schedule`, `transport.equipment.reposition`) are NOT in `HEURISTIC_HANDLERS`. Phase 2's dispatcher refuses them with `HeuristicWriteRefused` when called against a HEURISTIC-tier tenant.

## What's NOT here yet (Phase 2)

The **dispatcher** that:

1. Reads the calling tenant's `producer_tier` from `plane_registration`.
2. If `AZIRELLA`, routes to the real TMS planning code.
3. If `THIRD_PARTY`, routes to the MCP adapter (deferred — `NotImplementedError` for the demo).
4. If `HEURISTIC` (or `STUB` in the legacy enum), looks up the skill in `HEURISTIC_HANDLERS` and calls it with the tenant's plane_config.

The dispatcher lives in the TMS A2A request handler — a single small `async def handle_a2a_request(...)` that branches by tier.

## What's NOT here ever (out of scope)

- The legacy `azirella-tms-stub` package's FastAPI mount + sidecar startup. Under AD-12 we don't run a sidecar — the heuristic answers come from the TMS backend itself running in HEURISTIC mode. The Phase 1 port keeps the heuristic *content* and drops the *transport* layer.

## Default values

Speed model defaults from [HEURISTIC_DEFAULTS_REGISTRY.md](https://github.com/azirella-ltd/Autonomy-Core/blob/main/docs/HEURISTIC_DEFAULTS_REGISTRY.md):

- `transit_speed_mph_p10` = 600 mi/day (DOT-HOS + ATRI best-case OTR)
- `transit_speed_mph_p50` = 500 mi/day (median solo OTR throughput)
- `transit_speed_mph_p90` = 350 mi/day (LTL / multi-stop / congested)
- `road_distance_multiplier` = 1.3 (FHWA conservative midpoint)
- `dispatch_buffer_days` = 1.0 (origin + delivery dwell)

All overridable per-tenant via `plane_config` (passed in by Phase 2's dispatcher).

## Decommission of `azirella-tms-stub`

The stub package is not removed by this PR. Phase 5 of the [AD-12 migration plan](https://github.com/azirella-ltd/Autonomy-Core/blob/main/docs/architecture/AD12_MIGRATION_PLAN.md) decommissions it after every consumer has migrated through Phases 2 and 3. This PR is the content move; the stub stays deployed in parallel until Phase 5.

## See also

- [AD-12 in ARCHITECTURE_DECISIONS.md](https://github.com/azirella-ltd/Autonomy-Core/blob/main/docs/architecture/ARCHITECTURE_DECISIONS.md#ad-12-target-side-license-driven-plane-routing--each-app-owns-its-three-modes)
- [AD-12 migration plan](https://github.com/azirella-ltd/Autonomy-Core/blob/main/docs/architecture/AD12_MIGRATION_PLAN.md)
- [HEURISTIC_DEFAULTS_REGISTRY.md](https://github.com/azirella-ltd/Autonomy-Core/blob/main/docs/HEURISTIC_DEFAULTS_REGISTRY.md)
- Legacy: [azirella-tms-stub README](https://github.com/azirella-ltd/Autonomy-Core/blob/main/packages/azirella-tms-stub/README.md)
