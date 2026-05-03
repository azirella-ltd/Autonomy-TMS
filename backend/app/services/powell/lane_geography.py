"""Shared lane-geography resolver — §3.42 Phase 3.

Extracted from ``MovementPlannerService`` so that
``IntegratedBalancerService._capacity_filter_matches`` (and any other
service that needs to match `lane_filter` JSONB shapes) can reuse the
same resolution logic.

Walks ``TransportationLane → Site → Geography`` to extract per-lane
metadata (``origin_geo_id``, ``origin_state``, ``origin_zip3``, dest
counterparts, plus ``mode`` from TMS-side ``LaneProfile``). Each
resolver instance caches per-lane (so N items on the same lane share
one DB roundtrip).

The cache is per-instance (not module-global) because tests + services
need isolated caches across runs.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session


class LaneGeographyResolver:
    """Per-instance cached resolver of lane → geographic metadata.

    Use one instance per service-call so the cache scopes to the call.
    Pass to ``_capacity_filter_matches`` etc. as a callable that maps
    ``lane_id → metadata dict | None``.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self._cache: dict = {}

    def resolve(self, lane_id: int) -> Optional[dict]:
        """Resolve a lane's geography. Returns ``{origin_geo_id,
        dest_geo_id, origin_state, dest_state, origin_zip3, dest_zip3,
        mode}`` (any subset, depending on what's in the DB) or ``None``
        when the lookup chain breaks.
        """
        cache_key = ("lane_geography", lane_id)
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            return cached if cached != "MISS" else None

        try:
            from azirella_data_model.master.config import TransportationLane
        except ImportError:
            self._cache[cache_key] = "MISS"
            return None

        lane = self.db.query(TransportationLane).filter_by(id=lane_id).first()
        if lane is None:
            self._cache[cache_key] = "MISS"
            return None

        meta: dict = {}

        # Mode via TMS-side LaneProfile (more accurate than transportation_lane).
        try:
            from app.models.transportation_config import LaneProfile
            profile = (
                self.db.query(LaneProfile)
                .filter_by(lane_id=lane_id).first()
            )
            if profile is not None and profile.primary_mode:
                meta["mode"] = profile.primary_mode
        except Exception:
            pass

        # Origin / destination via Site → Geography.
        for endpoint, prefix in (
            (getattr(lane, "from_site_id", None), "origin"),
            (getattr(lane, "to_site_id", None), "dest"),
        ):
            if endpoint is None:
                continue
            try:
                from azirella_data_model.master.entities import Geography
                from azirella_data_model.master.config import Site

                site = self.db.query(Site).filter_by(id=endpoint).first()
                if site is None:
                    continue
                geo_id = getattr(site, "geography_id", None)
                if geo_id is not None:
                    meta[f"{prefix}_geo_id"] = geo_id
                    geo = (
                        self.db.query(Geography).filter_by(id=geo_id).first()
                    )
                    if geo is not None:
                        for attr in ("state", "region", "country"):
                            val = getattr(geo, attr, None)
                            if val:
                                meta[f"{prefix}_state"] = val
                                break
                        postal = (
                            getattr(geo, "postal_code", None)
                            or getattr(site, "postal_code", None)
                        )
                        if postal:
                            meta[f"{prefix}_zip3"] = str(postal)[:3]
            except Exception:
                continue

        result = meta if meta else "MISS"
        self._cache[cache_key] = result
        return meta if meta else None


__all__ = ["LaneGeographyResolver"]
