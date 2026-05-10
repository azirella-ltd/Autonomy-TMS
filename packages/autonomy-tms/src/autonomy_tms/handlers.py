"""TMS AZIRELLA-tier handler bundle (AD-13 / §3.56 PR-D)."""
from __future__ import annotations

# Triggers the sys.path insertion in autonomy_tms.__init__.
import autonomy_tms  # noqa: F401


def get_handler_bundle():
    """Entry-point factory for ``azirella-router`` AZIRELLA-tier dispatch.

    Empty for the demo customer set — TMS runs at HEURISTIC tier
    today and the existing `autonomy-tms-heuristics` package handles
    dispatch via the `azirella_router.heuristics` entry point.
    """
    try:
        from azirella_router import AzirellaPlaneBundle  # type: ignore[attr-defined]

        return AzirellaPlaneBundle(plane="tms", handlers={}, write_skills=set())
    except ImportError:
        return _EmptyBundle(plane="tms")


class _EmptyBundle:
    def __init__(self, plane: str):
        self.plane = plane
        self.handlers: dict = {}
        self.write_skills: set = set()
