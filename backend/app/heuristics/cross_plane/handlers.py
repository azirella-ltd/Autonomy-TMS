"""TMS cross-plane heuristic handlers — direct-call API.

Ported from ``azirella-tms-stub.skills`` as part of the AD-12
migration (Phase 1). The legacy stub package wrapped these as A2A
``SkillContext``-based handlers mounted on a FastAPI router on a
sidecar container. Under AD-12 they're called **directly** from
inside the TMS backend's request handler when the tenant's
license tier is HEURISTIC — no separate sidecar, no A2A round-trip.

Three skills covered (mirror the legacy stub package):

- ``estimate_lane_eta``           — haversine × parametric speed.
- ``evaluate_consolidation``      — always ship-as-is; the
                                    heuristic has no lane economics.
- ``recommend_carrier``           — tenant default-carrier from
                                    config, or ``"unknown"``.

Write-side skills (``transport.load.dispatch``,
``transport.shipment.tender``, ``transport.dock.schedule``,
``transport.equipment.reposition``) intentionally have no handler
here. Phase 2's dispatcher should refuse them with a typed error
when the tenant is at HEURISTIC tier — see ``refuse_write`` below.

Phase 2 (separate PR) wires these handlers into the TMS A2A
request handler so they get called when the resolver determines
the tenant is at HEURISTIC tier. This file is the content; Phase 2
is the dispatch glue.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from azirella_data_model.planes import ProducerTier

from ._eta import BUILT_IN_DEFAULTS, estimate_eta
from .warning import stamp_heuristic_response

logger = logging.getLogger(__name__)


# Producer-signature head. Per-skill suffix appended in handlers.
HEURISTIC_PRODUCER_SIGNATURE = "autonomy-tms-heuristics:v0.1.0"


class HeuristicWriteRefused(RuntimeError):
    """Raised when a write-side skill is called against a tenant at
    HEURISTIC tier. The TMS request handler MUST translate this to
    a clean error code on the wire — heuristic-tier customers get
    no TMS write paths.
    """

    def __init__(self, skill_id: str) -> None:
        super().__init__(
            f"skill {skill_id!r} not available at HEURISTIC tier — "
            "license a full TMS plane (AZIRELLA) or configure a THIRD_PARTY "
            "MCP adapter to a real TMS"
        )
        self.skill_id = skill_id


# ---------------------------------------------------------------------------
# transport.lane.estimate_eta
# ---------------------------------------------------------------------------


def estimate_lane_eta(
    *,
    tenant_id: int,
    plane_config: Dict[str, Any],
    inp: Dict[str, Any],
) -> Dict[str, Any]:
    """Heuristic ETA — haversine × speed × dispatch buffer.

    :param tenant_id: caller tenant. Used by the dispatcher's caller
        identity but not consumed by the heuristic math itself.
    :param plane_config: the tenant's heuristic-mode config (dict
        layered over ``BUILT_IN_DEFAULTS``). Phase 2's dispatcher
        builds this from ``plane_registration.heuristic_config`` or
        the per-tenant override file; for Phase 1 the test seed
        passes ``BUILT_IN_DEFAULTS`` directly.
    :param inp: skill input. Required: ``from_site_id``,
        ``to_site_id``, ``departure_at``. Optional: ``from_lat``,
        ``from_lon``, ``to_lat``, ``to_lon``.
    """
    for required in ("from_site_id", "to_site_id", "departure_at"):
        if not inp.get(required):
            raise ValueError(f"missing required input: {required}")

    departure = _parse_datetime(inp["departure_at"])
    from_coords = _coords_from_input(inp, "from_lat", "from_lon")
    to_coords = _coords_from_input(inp, "to_lat", "to_lon")

    result = estimate_eta(
        from_site_id=str(inp["from_site_id"]),
        to_site_id=str(inp["to_site_id"]),
        departure_at=departure,
        plane_config=plane_config,
        from_coords=from_coords,
        to_coords=to_coords,
    )

    band = result.as_band(
        producer_signature=f"{HEURISTIC_PRODUCER_SIGNATURE}:lane.estimate_eta",
    )
    payload = {
        "from_site_id": str(inp["from_site_id"]),
        "to_site_id": str(inp["to_site_id"]),
        **result.as_dict(),
        "eta_band": band.as_dict(),
    }
    return stamp_heuristic_response(
        payload,
        skill_id="transport.lane.estimate_eta",
        producer_signature=f"{HEURISTIC_PRODUCER_SIGNATURE}:lane.estimate_eta",
    )


# ---------------------------------------------------------------------------
# transport.load.evaluate_consolidation
# ---------------------------------------------------------------------------


def evaluate_consolidation(
    *,
    tenant_id: int,
    plane_config: Dict[str, Any],
    inp: Dict[str, Any],
) -> Dict[str, Any]:
    """Heuristic consolidation — always recommend ship-as-is.

    Consolidation has real trade-offs: hold-back time vs. service
    level, customer-mix compatibility, equipment fit, lane economics.
    None of these are observable from a heuristic — so the safe
    answer is "don't consolidate; ship each shipment as-is". The
    cost-savings field is filled with a conservative null; consumers
    that need real consolidation analysis MUST upgrade to a full
    TMS or third-party adapter.
    """
    config_id = inp.get("config_id")
    shipment_ids = inp.get("shipment_ids") or []
    if config_id is None:
        raise ValueError("missing required input: config_id")
    if not shipment_ids:
        raise ValueError(
            "missing required input: shipment_ids (non-empty list)"
        )

    payload = {
        "config_id": int(config_id),
        "shipment_ids": [str(s) for s in shipment_ids],
        "shipment_count": len(shipment_ids),
        "recommend_consolidation": False,
        "score": 0.0,
        "utilisation_estimate": None,
        "consolidation_cost_savings_estimate": None,
        "reasoning": (
            "TMS heuristic tier: no consolidation analysis available. "
            "Default decision is ship-as-is — every shipment dispatched "
            "individually. Real consolidation analysis requires lane "
            "economics, equipment fit, customer-mix compatibility, and "
            "hold-back time analysis the heuristic does not have."
        ),
    }
    return stamp_heuristic_response(
        payload,
        skill_id="transport.load.evaluate_consolidation",
        producer_signature=(
            f"{HEURISTIC_PRODUCER_SIGNATURE}:load.evaluate_consolidation"
        ),
    )


# ---------------------------------------------------------------------------
# transport.carrier.recommend
# ---------------------------------------------------------------------------


def recommend_carrier(
    *,
    tenant_id: int,
    plane_config: Dict[str, Any],
    inp: Dict[str, Any],
) -> Dict[str, Any]:
    """Heuristic carrier recommendation — tenant default or
    ``"unknown"``.

    Real carrier procurement runs a multi-criteria waterfall (cost,
    OTIF, asset compatibility, capacity availability, contract
    coverage). The heuristic returns the tenant's default-carrier
    from config as a single-recommendation list. If no default is
    configured, returns ``"unknown"`` with a low confidence score.
    """
    config_id = inp.get("config_id")
    load_id = inp.get("load_id")
    if config_id is None or load_id is None:
        raise ValueError(
            "missing required input: config_id and load_id"
        )
    top_n = int(inp.get("top_n", 3))

    default_carrier_id = plane_config.get("default_carrier_id")

    if default_carrier_id:
        recommendations = [
            {
                "carrier_id": str(default_carrier_id),
                "score": 0.5,
                "reasoning": (
                    "Tenant default carrier from heuristic config; no real "
                    "procurement waterfall executed."
                ),
            }
        ]
    else:
        recommendations = [
            {
                "carrier_id": "unknown",
                "score": 0.0,
                "reasoning": (
                    "No default carrier configured for tenant; heuristic "
                    "tier cannot select a real carrier."
                ),
            }
        ]

    payload = {
        "load_id": str(load_id),
        "config_id": int(config_id),
        "top_n": top_n,
        "recommendations": recommendations,
    }
    return stamp_heuristic_response(
        payload,
        skill_id="transport.carrier.recommend",
        producer_signature=(
            f"{HEURISTIC_PRODUCER_SIGNATURE}:carrier.recommend"
        ),
    )


# ---------------------------------------------------------------------------
# Write-side refusal helper
# ---------------------------------------------------------------------------


def refuse_write(skill_id: str) -> None:
    """Raise :class:`HeuristicWriteRefused` for any write-side skill.

    Phase 2's dispatcher calls this when the tenant is at HEURISTIC
    tier and the requested skill is one of the write-side ones.
    Heuristic tier doesn't support writes — by design.
    """
    raise HeuristicWriteRefused(skill_id=skill_id)


# ---------------------------------------------------------------------------
# Skill registry — the names Phase 2's dispatcher will look up by
# ---------------------------------------------------------------------------


HEURISTIC_HANDLERS: Dict[str, Any] = {
    "transport.lane.estimate_eta": estimate_lane_eta,
    "transport.load.evaluate_consolidation": evaluate_consolidation,
    "transport.carrier.recommend": recommend_carrier,
}
"""Handler registry. Phase 2's tier dispatcher looks up the
incoming ``skill_id`` and calls the matching handler with the
tenant's heuristic plane_config and the request input."""


HEURISTIC_WRITE_SKILLS = frozenset({
    "transport.load.dispatch",
    "transport.shipment.tender",
    "transport.dock.schedule",
    "transport.equipment.reposition",
})
"""Write-side skill IDs that Phase 2's dispatcher refuses with
``HeuristicWriteRefused`` when called against a HEURISTIC-tier
tenant."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_datetime(raw: Any) -> datetime:
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    raise ValueError(
        f"departure_at must be ISO-8601 string or datetime; got "
        f"{type(raw).__name__}"
    )


def _coords_from_input(
    inp: Dict[str, Any], lat_key: str, lon_key: str,
) -> Optional[Dict[str, float]]:
    lat = inp.get(lat_key)
    lon = inp.get(lon_key)
    if lat is None or lon is None:
        return None
    return {"lat": float(lat), "lon": float(lon)}


__all__ = [
    "HEURISTIC_HANDLERS",
    "HEURISTIC_PRODUCER_SIGNATURE",
    "HEURISTIC_WRITE_SKILLS",
    "HeuristicWriteRefused",
    "estimate_lane_eta",
    "evaluate_consolidation",
    "recommend_carrier",
    "refuse_write",
]
