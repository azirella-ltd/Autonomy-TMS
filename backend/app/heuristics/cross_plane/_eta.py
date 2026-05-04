"""ETA math for TMS HEURISTIC-tier responses.

Ported from the legacy ``azirella-tms-stub`` package as part of the
AD-12 migration (Phase 1, 2026-05-04). When TMS runs in HEURISTIC
tier for a tenant — i.e. the customer hasn't licensed full TMS
planning — calls into ``transport.lane.estimate_eta`` return ETAs
derived from haversine distance and a parametric speed model rather
than from the real planning agents.

This module has no real lane-history data, no live carrier feeds,
no geofence telemetry. It exists to satisfy cross-plane contracts
(SCP's ATP promise math, DP's arrival-window forecasts) when full
TMS isn't deployed for the tenant.

Speed defaults are pulled from public US-trucking averages:

- **DOT regulations** cap solo OTR drivers at 11 hours driving in a
  14-hour on-duty window with a 30-minute break after 8 hours
  driving (49 CFR §395.3). Practical solo OTR throughput is
  ~500–600 miles/day on long lanes (American Transportation
  Research Institute, *An Analysis of the Operational Costs of
  Trucking*, recent editions; FMCSA driver-day surveys).
- **Effective truck speed** in steady cruise is ~55–60 mph; net of
  HOS, dock dwell, fueling, traffic, and en-route inspections,
  effective progress drops to roughly the per-day numbers above.
- **Road-vs-great-circle distance** for typical North-American
  highway routes runs ~1.2–1.4× great-circle (FHWA freight-flow
  studies). The stub uses 1.3× as a conservative midpoint.
- **Mode mix** spreads the band: short-haul / single-day deliveries
  cluster near 600 mi/day; LTL with multiple stops drops to
  ~250–350 mi/day; intermodal rail moves containers at 350–450
  mi/day on long lanes; ocean freight is days of dwell + ~500
  nautical miles/day at sea.

The default p10 / p50 / p90 speeds (600 / 500 / 350 mi/day) are
deliberately wide to widen the conformal band — stubs MUST err
toward conservative confidence so consumers don't trust them like
real data.

Plus a fixed dispatch buffer to cover origin-side dwell + the
scheduling lead time from order entry to truck-rolling. ATRI's
*Operational Costs of Trucking* and ProductionMetrics dock-dwell
surveys put detention at 1.5–4 hours per shipment median; the stub
uses half-day dispatch + half-day delivery dwell as a conservative
combined buffer.

Tenant overrides (per ``StubTenantConfig.plane_config``):

- ``transit_speed_mph_p10`` (default 600): best-case effective speed.
- ``transit_speed_mph_p50`` (default 500): median effective speed.
- ``transit_speed_mph_p90`` (default 350): worst-case effective speed.
- ``road_distance_multiplier`` (default 1.3): great-circle → road km.
- ``dispatch_buffer_days`` (default 1.0): origin + delivery dwell.
- ``minimum_transit_days_p50`` (default 1.0): floor for p50; same-day
  delivery is rare on the OTR network the stub models.
- ``default_transit_days_p50`` (default 3.0): used when neither lat/lng
  nor a configured site-coordinate map can resolve a pair of sites.
- ``site_coordinates`` (default ``{}``): map of ``site_id`` (string) →
  ``{"lat": float, "lon": float}``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from azirella_data_model.conformal import ConformalBand
from azirella_data_model.planes import ProducerTier
from azirella_data_model.visibility.geofence_emitter import haversine_meters


# Conservative built-in defaults (see module docstring).
BUILT_IN_DEFAULTS: Dict[str, Any] = {
    "transit_speed_mph_p10": 600.0,    # best case (hot lane, OTR cruise)
    "transit_speed_mph_p50": 500.0,    # median solo OTR throughput
    "transit_speed_mph_p90": 350.0,    # LTL / multi-stop / congested
    "road_distance_multiplier": 1.3,   # great-circle → road
    "dispatch_buffer_days": 1.0,       # origin + delivery dwell
    "minimum_transit_days_p50": 1.0,   # same-day OTR is rare
    "default_transit_days_p50": 3.0,   # fallback when no coords
    "default_transit_days_p10": 2.0,
    "default_transit_days_p90": 5.0,
    "site_coordinates": {},
}


@dataclass(frozen=True)
class ETAResult:
    """Stub ETA decision.

    :param departure_at: when the shipment leaves the origin.
    :param p10_at: optimistic arrival (10th percentile of arrival
        time = early). Mapped from ``p10_days`` (small days = early).
    :param p50_at: median arrival.
    :param p90_at: pessimistic arrival.
    :param p10_days: transit days at the 10th percentile (small).
    :param p50_days: median transit days.
    :param p90_days: transit days at the 90th percentile (large).
    :param road_distance_miles: estimated road distance (haversine ×
        road multiplier). ``None`` when neither coordinates nor
        config could resolve the lane and the stub used the flat
        ``default_transit_days_*`` config.
    :param resolution_path: how the stub resolved the lane —
        ``"caller_coordinates"`` / ``"config_coordinates"`` /
        ``"flat_default"``. Useful for audit / debugging.
    """

    departure_at: datetime
    p10_at: datetime
    p50_at: datetime
    p90_at: datetime
    p10_days: float
    p50_days: float
    p90_days: float
    road_distance_miles: Optional[float]
    resolution_path: str

    def as_band(self, *, producer_signature: str) -> ConformalBand:
        """Wrap transit-day estimates as a :class:`ConformalBand`.

        Bands are in DAYS. Stamps ``producer_tier=STUB`` so consumer
        TRMs widen confidence automatically per §3.32a / §3.31.
        """
        return ConformalBand(
            p10=float(self.p10_days),
            p50=float(self.p50_days),
            p90=float(self.p90_days),
            coverage_target=0.95,  # wide — stubs are low-confidence
            producer_signature=producer_signature,
            producer_tier=ProducerTier.STUB,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "departure_at": self.departure_at.isoformat(),
            "p10_at": self.p10_at.isoformat(),
            "p50_at": self.p50_at.isoformat(),
            "p90_at": self.p90_at.isoformat(),
            "p10_days": self.p10_days,
            "p50_days": self.p50_days,
            "p90_days": self.p90_days,
            "road_distance_miles": self.road_distance_miles,
            "resolution_path": self.resolution_path,
        }


def estimate_eta(
    *,
    from_site_id: str,
    to_site_id: str,
    departure_at: datetime,
    plane_config: Dict[str, Any],
    from_coords: Optional[Dict[str, float]] = None,
    to_coords: Optional[Dict[str, float]] = None,
) -> ETAResult:
    """Compute a stub ETA from haversine + speed × buffer math.

    Resolution order for site coordinates:

    1. ``from_coords`` / ``to_coords`` passed by the caller
       (``{"lat": float, "lon": float}``).
    2. ``plane_config["site_coordinates"][site_id]`` for each side.
    3. Flat-default: use ``default_transit_days_p10/p50/p90`` from
       config without computing distance.

    Either both endpoints' coordinates resolve from the same source
    (caller or config) or we fall through to flat-default. Mixing
    a caller-provided origin with a config-resolved destination is
    accepted — both sides need a lat/lon, the source doesn't have
    to be uniform.
    """
    cfg = {**BUILT_IN_DEFAULTS, **(plane_config or {})}

    coords_from = from_coords or _coords_from_config(
        cfg, from_site_id,
    )
    coords_to = to_coords or _coords_from_config(
        cfg, to_site_id,
    )

    if coords_from is None or coords_to is None:
        # Fall back to flat-default — no distance computed.
        p10 = float(cfg["default_transit_days_p10"])
        p50 = max(
            float(cfg["minimum_transit_days_p50"]),
            float(cfg["default_transit_days_p50"]),
        )
        p90 = float(cfg["default_transit_days_p90"])
        return _build_result(
            departure_at=departure_at,
            p10_days=p10,
            p50_days=p50,
            p90_days=p90,
            road_distance_miles=None,
            resolution_path="flat_default",
        )

    # Distance — meters → miles, scaled by road-distance multiplier.
    great_circle_meters = haversine_meters(
        coords_from["lat"], coords_from["lon"],
        coords_to["lat"], coords_to["lon"],
    )
    great_circle_miles = great_circle_meters / 1609.344
    road_miles = great_circle_miles * float(cfg["road_distance_multiplier"])

    buffer_days = float(cfg["dispatch_buffer_days"])
    min_p50 = float(cfg["minimum_transit_days_p50"])

    p10_days = (road_miles / float(cfg["transit_speed_mph_p10"])) + buffer_days
    p50_days = max(
        min_p50,
        (road_miles / float(cfg["transit_speed_mph_p50"])) + buffer_days,
    )
    p90_days = (road_miles / float(cfg["transit_speed_mph_p90"])) + buffer_days

    # Sanity check: ConformalBand requires p10 <= p50 <= p90.
    # Numeric edge cases (very short lanes after the min-p50 floor)
    # can push p10 below the floored p50; clamp to preserve order.
    p10_days = min(p10_days, p50_days)
    p90_days = max(p90_days, p50_days)

    resolution_path = (
        "caller_coordinates"
        if (from_coords is not None and to_coords is not None)
        else "config_coordinates"
        if (from_coords is None and to_coords is None)
        else "mixed_coordinates"
    )

    return _build_result(
        departure_at=departure_at,
        p10_days=p10_days,
        p50_days=p50_days,
        p90_days=p90_days,
        road_distance_miles=road_miles,
        resolution_path=resolution_path,
    )


def _coords_from_config(
    cfg: Dict[str, Any], site_id: str,
) -> Optional[Dict[str, float]]:
    site_map = cfg.get("site_coordinates", {}) or {}
    if not isinstance(site_map, dict):
        return None
    entry = site_map.get(str(site_id))
    if not isinstance(entry, dict):
        return None
    if "lat" not in entry or "lon" not in entry:
        return None
    return {"lat": float(entry["lat"]), "lon": float(entry["lon"])}


def _build_result(
    *,
    departure_at: datetime,
    p10_days: float,
    p50_days: float,
    p90_days: float,
    road_distance_miles: Optional[float],
    resolution_path: str,
) -> ETAResult:
    if departure_at.tzinfo is None:
        departure_at = departure_at.replace(tzinfo=timezone.utc)
    return ETAResult(
        departure_at=departure_at,
        p10_at=departure_at + timedelta(days=p10_days),
        p50_at=departure_at + timedelta(days=p50_days),
        p90_at=departure_at + timedelta(days=p90_days),
        p10_days=p10_days,
        p50_days=p50_days,
        p90_days=p90_days,
        road_distance_miles=road_distance_miles,
        resolution_path=resolution_path,
    )


__all__ = ["BUILT_IN_DEFAULTS", "ETAResult", "estimate_eta"]
