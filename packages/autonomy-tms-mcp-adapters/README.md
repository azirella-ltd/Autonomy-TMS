# autonomy-tms-mcp-adapters

**TMS-team-owned vendor MCP adapters** for the THIRD_PARTY tier of [AD-12](https://github.com/azirella-ltd/Autonomy-Core/blob/main/docs/architecture/ARCHITECTURE_DECISIONS.md).

When a tenant has TMS at `producer_tier=THIRD_PARTY` and `plane_config.mcp_adapter_vendor` set (e.g. `sap_tm`), `azirella-router` discovers the matching vendor sub-package via Python entry point and calls its handlers in-process to translate the canonical TMS skill call to the vendor's API.

## Status — v0.1.0

**Skeleton only.** No vendor adapters yet. The Microsoft 2026-05-11 demo runs entirely on AZIRELLA + HEURISTIC tiers; THIRD_PARTY isn't on the demo path. First vendor adapter (likely SAP TM) lands post-demo.

## Adding a vendor adapter

Per-vendor sub-package layout:

```
src/autonomy_tms_mcp_adapters/
└── sap_tm/
    ├── __init__.py        ← exposes get_adapter_bundle()
    ├── handlers.py        ← skill_id → handler dict
    └── translator.py      ← Azirella-canonical ↔ SAP TM API translation
```

Register the entry point in `pyproject.toml`:

```toml
[project.entry-points."azirella_router.mcp_adapters"]
tms_sap_tm = "autonomy_tms_mcp_adapters.sap_tm:get_adapter_bundle"
```

The factory returns an `MCPAdapterBundle`:

```python
def get_adapter_bundle():
    from azirella_router import MCPAdapterBundle
    from .handlers import HANDLERS
    return MCPAdapterBundle(
        plane="tms",
        vendor="sap_tm",
        handlers=HANDLERS,
        producer_signature="autonomy-tms-mcp-adapters:sap_tm:v0.1.0",
    )
```

## Skills covered

Same canonical TMS skill IDs as `autonomy-tms-heuristics`:

| Skill | Notes |
|---|---|
| `transport.lane.estimate_eta` | Translate to vendor's lane-ETA endpoint |
| `transport.load.evaluate_consolidation` | Translate to vendor's consolidation analysis |
| `transport.carrier.recommend` | Translate to vendor's procurement waterfall |
| `transport.load.dispatch` (write) | Translate to vendor's dispatch endpoint |
| `transport.shipment.tender` (write) | Translate to vendor's tender endpoint |
| `transport.dock.schedule` (write) | Translate to vendor's dock scheduler |
| `transport.equipment.reposition` (write) | Translate to vendor's equipment repositioning |

Vendor adapters MAY support fewer skills than this; the router raises `RouterCallFailed` if a tenant resolves to a vendor that doesn't expose the requested skill.

## See also

- [autonomy-tms-heuristics](../autonomy-tms-heuristics/) — HEURISTIC-tier handlers (same skill IDs, conservative defaults).
- [azirella-router](https://github.com/azirella-ltd/Autonomy-Core/tree/main/packages/azirella-router) — the consumer-side dispatcher.
- [AD-12](https://github.com/azirella-ltd/Autonomy-Core/blob/main/docs/architecture/ARCHITECTURE_DECISIONS.md)
