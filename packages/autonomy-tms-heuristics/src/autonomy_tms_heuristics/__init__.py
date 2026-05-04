"""autonomy-tms-heuristics — TMS-team-owned heuristic policies (AD-12).

Same content (haversine ETA, ship-as-is consolidation, tenant-default
carrier) is consumed in two places:

1. **HEURISTIC-tier runtime dispatch** by ``azirella-router``, when a
   tenant's TMS plane resolves to HEURISTIC. The router discovers this
   package via Python entry point (``azirella_router.heuristics`` →
   ``tms``) and calls :func:`get_handler_bundle` to fetch the dispatch
   surface.

2. **Training-baseline policies** for TMS RL training pipelines. The
   training script imports :data:`HEURISTIC_HANDLERS` directly and
   wraps it in a baseline policy adapter for ``RolloutHarness``.

This package depends only on:
- ``azirella-data-model`` (for ``ConformalBand``, geofence haversine math)
- ``azirella-heuristics-common`` (for the four-place warning regime + exceptions)

It does NOT depend on the TMS backend app — it ships separately so
SCP / DP backends can pip-install it for in-process HEURISTIC dispatch
without pulling in the TMS app.
"""
from .handlers import (
    HEURISTIC_HANDLERS,
    HEURISTIC_PRODUCER_SIGNATURE,
    HEURISTIC_WRITE_SKILLS,
    estimate_lane_eta,
    evaluate_consolidation,
    recommend_carrier,
    refuse_write,
)
from .eta import BUILT_IN_DEFAULTS, ETAResult, estimate_eta

__version__ = "0.1.0"

__all__ = [
    "BUILT_IN_DEFAULTS",
    "ETAResult",
    "HEURISTIC_HANDLERS",
    "HEURISTIC_PRODUCER_SIGNATURE",
    "HEURISTIC_WRITE_SKILLS",
    "estimate_eta",
    "estimate_lane_eta",
    "evaluate_consolidation",
    "get_handler_bundle",
    "recommend_carrier",
    "refuse_write",
]


def get_handler_bundle():
    """Entry-point factory for ``azirella-router``'s plugin discovery.

    Wraps :data:`HEURISTIC_HANDLERS`, :data:`HEURISTIC_WRITE_SKILLS`, and
    :func:`refuse_write` into a :class:`HeuristicPlaneBundle` the router
    can consume. Lazy-imports ``azirella_router`` so this package can be
    imported without it (e.g. by training scripts using the handlers
    directly).
    """
    from azirella_router import HeuristicPlaneBundle
    return HeuristicPlaneBundle(
        plane="tms",
        handlers=HEURISTIC_HANDLERS,
        write_skills=HEURISTIC_WRITE_SKILLS,
        refuse_write=refuse_write,
        producer_signature=HEURISTIC_PRODUCER_SIGNATURE,
    )
