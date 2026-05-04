"""TMS heuristic handlers — direct-call API.

Three read-side skills + four write-side skills (refused). Each handler
takes ``(tenant_id, plane_config, inp)`` keyword args and returns a dict
already stamped with the four-place warning regime.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from azirella_heuristics_common import (
    HeuristicWriteRefused,
    stamp_heuristic_response,
)

from .eta import BUILT_IN_DEFAULTS, estimate_eta

logger = logging.getLogger(__name__)


HEURISTIC_PRODUCER_SIGNATURE = "autonomy-tms-heuristics:v0.1.0"
_PLANE = "tms"


# ---------------------------------------------------------------------------
# transport.lane.estimate_eta
# ---------------------------------------------------------------------------


def estimate_lane_eta(
    *,
    tenant_id: int,
    plane_config: Dict[str, Any],
    inp: Dict[str, Any],
) -> Dict[str, Any]:
    """Heuristic ETA — haversine × speed × dispatch buffer."""
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

    skill_signature = f"{HEURISTIC_PRODUCER_SIGNATURE}:lane.estimate_eta"
    band = result.as_band(producer_signature=skill_signature)
    payload = {
        "from_site_id": str(inp["from_site_id"]),
        "to_site_id": str(inp["to_site_id"]),
        **result.as_dict(),
        "eta_band": band.as_dict(),
    }
    return stamp_heuristic_response(
        payload,
        plane=_PLANE,
        skill_id="transport.lane.estimate_eta",
        producer_signature=skill_signature,
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
    """Heuristic consolidation — always recommend ship-as-is."""
    config_id = inp.get("config_id")
    shipment_ids = inp.get("shipment_ids") or []
    if config_id is None:
        raise ValueError("missing required input: config_id")
    if not shipment_ids:
        raise ValueError("missing required input: shipment_ids (non-empty list)")

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
        plane=_PLANE,
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
    """Heuristic carrier recommendation — tenant default or ``"unknown"``."""
    config_id = inp.get("config_id")
    load_id = inp.get("load_id")
    if config_id is None or load_id is None:
        raise ValueError("missing required input: config_id and load_id")
    top_n = int(inp.get("top_n", 3))

    default_carrier_id = plane_config.get("default_carrier_id")

    if default_carrier_id:
        recommendations = [{
            "carrier_id": str(default_carrier_id),
            "score": 0.5,
            "reasoning": (
                "Tenant default carrier from heuristic config; no real "
                "procurement waterfall executed."
            ),
        }]
    else:
        recommendations = [{
            "carrier_id": "unknown",
            "score": 0.0,
            "reasoning": (
                "No default carrier configured for tenant; heuristic tier "
                "cannot select a real carrier."
            ),
        }]

    payload = {
        "load_id": str(load_id),
        "config_id": int(config_id),
        "top_n": top_n,
        "recommendations": recommendations,
    }
    return stamp_heuristic_response(
        payload,
        plane=_PLANE,
        skill_id="transport.carrier.recommend",
        producer_signature=(
            f"{HEURISTIC_PRODUCER_SIGNATURE}:carrier.recommend"
        ),
    )


# ---------------------------------------------------------------------------
# Write-side refusal
# ---------------------------------------------------------------------------


def refuse_write(skill_id: str) -> None:
    raise HeuristicWriteRefused(skill_id=skill_id, plane=_PLANE)


# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------


HEURISTIC_HANDLERS: Dict[str, Any] = {
    "transport.lane.estimate_eta": estimate_lane_eta,
    "transport.load.evaluate_consolidation": evaluate_consolidation,
    "transport.carrier.recommend": recommend_carrier,
}


HEURISTIC_WRITE_SKILLS = frozenset({
    "transport.load.dispatch",
    "transport.shipment.tender",
    "transport.dock.schedule",
    "transport.equipment.reposition",
})


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
    "estimate_lane_eta",
    "evaluate_consolidation",
    "recommend_carrier",
    "refuse_write",
]
