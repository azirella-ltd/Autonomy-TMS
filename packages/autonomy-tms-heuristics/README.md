# autonomy-tms-heuristics

**TMS-team-owned heuristic policies, per [AD-12](https://github.com/azirella-ltd/Autonomy-Core/blob/main/docs/architecture/ARCHITECTURE_DECISIONS.md).**

The same heuristic content (haversine ETA, ship-as-is consolidation, tenant-default carrier) is consumed in two places:

1. **HEURISTIC-tier runtime dispatch** by `azirella-router`. When a tenant's TMS plane resolves to HEURISTIC tier, the consumer (SCP backend, DP backend) calls into this package in-process. The router discovers the package via Python entry point.
2. **Training-baseline policies** for TMS RL training. The training script imports `HEURISTIC_HANDLERS` directly and wraps in a baseline policy adapter for `RolloutHarness`.

This package depends only on `azirella-data-model` (for `ConformalBand` and the geofence math) and `azirella-heuristics-common` (for the four-place warning regime + exceptions). It does NOT depend on the TMS backend app — it ships separately so SCP / DP backends can pip-install it without pulling in the full TMS app.

## Public API

```python
from autonomy_tms_heuristics import (
    HEURISTIC_HANDLERS,            # {skill_id: handler}
    HEURISTIC_WRITE_SKILLS,        # frozenset of refused write skill IDs
    HEURISTIC_PRODUCER_SIGNATURE,  # "autonomy-tms-heuristics:v0.1.0"
    estimate_lane_eta,             # transport.lane.estimate_eta
    evaluate_consolidation,        # transport.load.evaluate_consolidation
    recommend_carrier,             # transport.carrier.recommend
    refuse_write,                  # raises HeuristicWriteRefused
    get_handler_bundle,            # entry-point factory for azirella-router
)
```

## Entry-point registration

`pyproject.toml`:

```toml
[project.entry-points."azirella_router.heuristics"]
tms = "autonomy_tms_heuristics:get_handler_bundle"
```

When this package is installed in the consumer's image, `azirella-router` discovers it automatically — no explicit registration call needed.

## Skills covered

| Skill | Heuristic |
|---|---|
| `transport.lane.estimate_eta` | Haversine × parametric speed (DOT-HOS / ATRI / FHWA defaults) + dispatch buffer; returns wide ConformalBand |
| `transport.load.evaluate_consolidation` | Always `recommend_consolidation=False` |
| `transport.carrier.recommend` | Tenant default-carrier from config, or `"unknown"` |

Write skills refused with `HeuristicWriteRefused`: `transport.load.dispatch`, `transport.shipment.tender`, `transport.dock.schedule`, `transport.equipment.reposition`.

## Four-place warning regime

Every read response carries:

1. `producer_tier="HEURISTIC"`
2. `producer_signature="autonomy-tms-heuristics:<skill>:v0.1.0"`
3. `heuristic_warning` — string starting with the canonical `AZIRELLA-STUB-WARNING` audit-grep phrase (preserved from the legacy stub packages)
4. `heuristic_plane="autonomy-tms-heuristics"`

## Default values

Speed model defaults from the [HEURISTIC_DEFAULTS_REGISTRY](https://github.com/azirella-ltd/Autonomy-Core/blob/main/docs/HEURISTIC_DEFAULTS_REGISTRY.md):

- `transit_speed_mph_p10` = 600 mi/day (DOT-HOS + ATRI best-case OTR)
- `transit_speed_mph_p50` = 500 mi/day (median solo OTR throughput)
- `transit_speed_mph_p90` = 350 mi/day (LTL / multi-stop / congested)
- `road_distance_multiplier` = 1.3 (FHWA conservative midpoint)
- `dispatch_buffer_days` = 1.0 (origin + delivery dwell)

Overridable per-tenant via `plane_config`.

## See also

- [azirella-router](https://github.com/azirella-ltd/Autonomy-Core/tree/main/packages/azirella-router) — the consumer-side dispatcher.
- [azirella-heuristics-common](https://github.com/azirella-ltd/Autonomy-Core/tree/main/packages/azirella-heuristics-common) — warning regime + exceptions.
- [autonomy-tms-mcp-adapters](../autonomy-tms-mcp-adapters/) — vendor MCP adapters for THIRD_PARTY tier.
- [AD-12 in ARCHITECTURE_DECISIONS.md](https://github.com/azirella-ltd/Autonomy-Core/blob/main/docs/architecture/ARCHITECTURE_DECISIONS.md)
