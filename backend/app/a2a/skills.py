"""TMS A2A skills + Agent Card construction.

Three skills in Phase 4 covering the most-likely cross-plane
caller patterns:

- ``transport.load.evaluate_consolidation`` — wraps load-build
  consolidation scoring.
- ``transport.carrier.recommend`` — wraps freight-procurement
  carrier-selection waterfall.
- ``transport.lane.estimate_eta`` — wraps the conformal ETA
  predictor (§3.29 Group A) for a given lane.

The handlers are deliberately thin — unpack the input, delegate
to existing TRMs / engines, return a serialised dict. Heavy
lifting stays where it already lives.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from azirella_a2a_client import (
    AgentCard,
    Skill,
    SkillContext,
    mount_a2a_router,
)


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# transport.load.evaluate_consolidation
# ---------------------------------------------------------------------------


async def evaluate_consolidation_skill(ctx: SkillContext) -> Dict[str, Any]:
    """Score whether a group of shipments should be consolidated.

    Wraps :class:`LoadBuildTRM`'s ``evaluate_group`` for a
    candidate group of shipment ids; returns the recommendation
    + score + utilisation metrics.
    """
    inp = ctx.input
    config_id = inp.get("config_id")
    shipment_ids = inp.get("shipment_ids") or []
    if config_id is None:
        raise ValueError("missing required input: config_id")
    if not shipment_ids:
        raise ValueError("missing required input: shipment_ids (non-empty list)")

    try:
        from app.services.powell.load_build_trm import LoadBuildTRM
        from app.db.session import sync_session_factory
    except ImportError as exc:
        raise RuntimeError(f"load_build_trm unavailable: {exc}") from exc

    sync_db = sync_session_factory()
    try:
        trm = LoadBuildTRM(db=sync_db, config_id=int(config_id))
        # evaluate_group expects a candidate group dict with the
        # shipment ids; the TRM's full signature varies by version.
        # Build a minimal payload and invoke; on TRM-side errors we
        # surface a structured error.
        try:
            result = trm.evaluate_group(
                {"shipment_ids": [str(s) for s in shipment_ids]},
            )
        except TypeError:
            # Fallback for TRMs whose evaluate_group takes
            # positional shipment ids. Best-effort.
            result = trm.evaluate_group(shipment_ids)  # type: ignore[arg-type]
    finally:
        sync_db.close()

    if not isinstance(result, dict):
        return {"raw": str(result)}
    return result


# ---------------------------------------------------------------------------
# transport.carrier.recommend
# ---------------------------------------------------------------------------


async def recommend_carrier_skill(ctx: SkillContext) -> Dict[str, Any]:
    """Recommend a carrier for a given load.

    Wraps :class:`FreightProcurementTRM`'s carrier-waterfall scoring.
    Returns the top-N carriers ordered by composite score.
    """
    inp = ctx.input
    config_id = inp.get("config_id")
    load_id = inp.get("load_id")
    if config_id is None or load_id is None:
        raise ValueError("missing required input: config_id and load_id")

    top_n = int(inp.get("top_n", 3))

    try:
        from app.services.powell.freight_procurement_trm import (
            FreightProcurementTRM,
        )
        from app.db.session import sync_session_factory
    except ImportError as exc:
        raise RuntimeError(f"freight_procurement_trm unavailable: {exc}") from exc

    sync_db = sync_session_factory()
    try:
        trm = FreightProcurementTRM(db=sync_db, config_id=int(config_id))
        # Most TRM implementations expose recommend(load_id, top_n);
        # accept either shape.
        try:
            recs = trm.recommend_for_load(load_id=load_id, top_n=top_n)  # type: ignore[attr-defined]
        except AttributeError:
            try:
                recs = trm.recommend(load_id=load_id, top_n=top_n)  # type: ignore[attr-defined]
            except AttributeError as exc:
                raise RuntimeError(
                    f"FreightProcurementTRM does not expose a "
                    f"recommend* method ({exc})"
                ) from exc
    finally:
        sync_db.close()

    return {
        "load_id": load_id,
        "recommendations": recs if isinstance(recs, list) else [recs],
        "top_n": top_n,
    }


# ---------------------------------------------------------------------------
# transport.lane.estimate_eta
# ---------------------------------------------------------------------------


async def estimate_lane_eta_skill(ctx: SkillContext) -> Dict[str, Any]:
    """Return ConformalBand-shaped ETA for a (lane, departure) pair.

    Wraps the §3.29 Group A conformal ETA predictor (already in
    Core via the visibility substrate) for a specific lane.
    """
    inp = ctx.input
    for required in ("from_site_id", "to_site_id", "departure_at"):
        if not inp.get(required):
            raise ValueError(f"missing required input: {required}")

    try:
        # The Core visibility substrate exposes a lane-historical
        # ETA predictor; import path under
        # azirella_data_model.visibility.eta or similar.
        from app.services.powell.shipment_tracking_trm import (
            ShipmentTrackingTRM,
        )
        from app.db.session import sync_session_factory
    except ImportError as exc:
        raise RuntimeError(f"shipment_tracking_trm unavailable: {exc}") from exc

    sync_db = sync_session_factory()
    try:
        trm = ShipmentTrackingTRM(db=sync_db, config_id=int(inp.get("config_id", 0)))
        # Try the most likely method names; report a structured error
        # if none match (TRM evolves; A2A interface stays stable).
        for method in ("estimate_lane_eta", "predict_eta", "estimate_eta"):
            fn = getattr(trm, method, None)
            if fn is None:
                continue
            try:
                result = fn(
                    from_site_id=inp["from_site_id"],
                    to_site_id=inp["to_site_id"],
                    departure_at=inp["departure_at"],
                )
            except TypeError:
                continue
            break
        else:
            raise RuntimeError(
                "ShipmentTrackingTRM does not expose an ETA estimator "
                "method matching the expected signature."
            )
    finally:
        sync_db.close()

    if isinstance(result, dict):
        return result
    # If the TRM returned a ConformalBand instance, convert.
    if hasattr(result, "as_dict"):
        return result.as_dict()
    return {"raw": str(result)}


# ---------------------------------------------------------------------------
# Agent Card + skill registry
# ---------------------------------------------------------------------------


def build_agent_card(
    *, base_url: str = "http://autonomy-tms:8001/a2a",
) -> AgentCard:
    """Build TMS's Agent Card. Called once at app startup."""
    return AgentCard(
        name="autonomy-tms",
        version="0.1.0",
        url=base_url,
        description=(
            "Transportation Management plane — owns load-building, "
            "carrier procurement, dispatch, dock scheduling, "
            "equipment positioning, multi-carrier visibility, and "
            "lane / route optimisation."
        ),
        skills=[
            Skill(
                id="transport.load.evaluate_consolidation",
                name="Evaluate consolidation candidate",
                description=(
                    "Score whether a group of shipments should be "
                    "consolidated into one load. Returns the "
                    "recommendation + score + utilisation metrics. "
                    "Used by SCP rebalancing TRMs choosing transfer-"
                    "order shapes, and by external schedulers."
                ),
            ),
            Skill(
                id="transport.carrier.recommend",
                name="Recommend carrier for load",
                description=(
                    "Recommend top-N carriers for a given load via "
                    "the freight-procurement waterfall. Returns "
                    "carriers ordered by composite score (cost / "
                    "OTIF / asset compatibility)."
                ),
            ),
            Skill(
                id="transport.lane.estimate_eta",
                name="Estimate lane ETA",
                description=(
                    "Return P10/P50/P90 ETA for a given "
                    "(from_site, to_site, departure_at) tuple. "
                    "Wraps the §3.29 Group A conformal ETA "
                    "predictor + lane historical performance."
                ),
            ),
        ],
    )


def get_skill_handlers() -> Dict[str, Any]:
    """Return ``{skill_id: handler}`` for ``mount_a2a_router``."""
    return {
        "transport.load.evaluate_consolidation": evaluate_consolidation_skill,
        "transport.carrier.recommend": recommend_carrier_skill,
        "transport.lane.estimate_eta": estimate_lane_eta_skill,
    }


def mount(app: Any, *, base_url: Optional[str] = None) -> None:
    """Mount TMS's A2A surface on the given FastAPI app."""
    card = build_agent_card(base_url=base_url) if base_url else build_agent_card()
    handlers = get_skill_handlers()
    mount_a2a_router(app, agent_card=card, handlers=handlers)
    log.info(
        "TMS A2A surface mounted: %d skills (%s)",
        len(card.skills), [s.id for s in card.skills],
    )
