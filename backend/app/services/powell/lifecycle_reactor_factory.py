"""Production wire-up for §3.45 LaneVolumeLifecycleReactor.

Closes the §3.40 loop by providing:

  - :class:`A2ALifecycleAdjustmentProvider` — concrete implementation
    of the reactor's :class:`LifecycleAdjustmentProvider` Protocol.
    Wraps :class:`azirella_a2a_client.Client` and calls DP's
    ``forecast.adjustment.list_lifecycle`` skill (§3.44).
  - :func:`make_lifecycle_reactor` — factory that resolves DP's A2A
    endpoint via the §3.32a plane registry, wires the provider, and
    returns a configured :class:`LaneVolumeLifecycleReactor`. Returns
    ``None`` when DP's plane producer isn't reachable — the caller's
    forecast still runs without a lifecycle overlay (the no-fallbacks
    rule applies: don't make up overlays when the producer is down).

Usage::

    from app.services.powell.lifecycle_reactor_factory import (
        make_lifecycle_reactor,
    )
    from app.services.powell.tactical_forecast_service import (
        TacticalForecastService,
    )

    reactor = make_lifecycle_reactor(db, tenant_id=42)
    svc = TacticalForecastService(db)
    svc.publish_forecast(
        tenant_id=42, config_id=1, inputs=lane_inputs,
        lifecycle_reactor=reactor,  # None is fine — service handles it
    )

This module is the *only* place in TMS that knows about the DP A2A
skill's wire shape. The reactor itself stays Protocol-typed and is
testable with fake providers (see ``test_lane_volume_lifecycle_reactor.py``).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.powell.lane_volume_lifecycle_reactor import (
        LaneVolumeLifecycleReactor,
    )


logger = logging.getLogger(__name__)


# Skill id matches the registered skill in
# Autonomy-DP/backend/app/a2a/phase3_skills.py — the §3.44 contract.
_DP_LIST_LIFECYCLE_SKILL_ID = "forecast.adjustment.list_lifecycle"


class A2ALifecycleAdjustmentProvider:
    """Production :class:`LifecycleAdjustmentProvider` backed by an
    A2A call to DP's ``forecast.adjustment.list_lifecycle`` skill.

    Construction takes an :class:`azirella_a2a_client.Client` already
    pointed at DP's endpoint — the factory below handles plane-registry
    resolution. Tests can construct directly with a stubbed client.

    Why a class wrapper rather than inlining the call: the reactor's
    Protocol is *sync* (compute_overlays is sync) but the A2A client
    is *async*. We bridge that here with ``asyncio.run`` per call,
    which is fine for the per-publish read pattern (one call per
    publish_forecast invocation, not per-input). Production callers
    on FastAPI's existing event loop should construct the provider
    once and reuse — `asyncio.run` raises if a loop is already running,
    so threaded callers (e.g. APScheduler background jobs) are safe.
    """

    def __init__(
        self,
        client: Any,  # azirella_a2a_client.Client; Any to keep import optional
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    def list_lifecycle_adjustments(
        self,
        *,
        tenant_id: int,
        since: Optional[datetime] = None,
        reason_codes: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Sync wrapper around the async A2A call.

        Returns an empty list (rather than raising) on any A2A failure
        — the reactor's contract is "no-op when the producer is down,"
        not "fail the whole publish_forecast." The error is logged
        WARNING so ops can monitor.
        """
        payload: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "limit": int(limit),
        }
        if since is not None:
            payload["since"] = since.isoformat()
        if reason_codes is not None:
            payload["reason_codes"] = list(reason_codes)

        try:
            task = asyncio.run(
                asyncio.wait_for(
                    self._client.send_task(
                        skill_id=_DP_LIST_LIFECYCLE_SKILL_ID,
                        input=payload,
                        tenant_id=tenant_id,
                    ),
                    timeout=self._timeout_seconds,
                )
            )
        except Exception as exc:
            logger.warning(
                "A2ALifecycleAdjustmentProvider: DP A2A call failed for "
                "tenant=%s — returning empty result. exc=%s",
                tenant_id, exc,
            )
            return []

        # Task carries the skill's return payload. The §3.44 skill
        # returns ``{"adjustments": [...], "count": int, ...}``.
        result = _extract_skill_result(task)
        if not isinstance(result, dict):
            logger.warning(
                "A2ALifecycleAdjustmentProvider: unexpected result shape "
                "(not a dict) for tenant=%s — got %r",
                tenant_id, type(result).__name__,
            )
            return []
        adjustments = result.get("adjustments")
        if not isinstance(adjustments, list):
            return []
        return adjustments


def make_lifecycle_reactor(
    db: "Session",
    *,
    tenant_id: int,
    config_id: Optional[int] = None,
    coverage_threshold: Optional[float] = None,
    timeout_seconds: float = 30.0,
) -> "Optional[LaneVolumeLifecycleReactor]":
    """Construct a :class:`LaneVolumeLifecycleReactor` wired to DP's
    A2A endpoint via the §3.32a plane registry.

    Returns ``None`` when DP's plane producer can't be resolved
    (no registration, missing endpoint URL, or import failure).
    Callers thread the result into ``publish_forecast``'s
    ``lifecycle_reactor=`` parameter; ``None`` is a safe no-op there.

    :param db: SQLAlchemy session against the platform DB (used by
        :meth:`Client.for_plane` to look up the DP registration).
    :param tenant_id: Tenant scope for the registration lookup.
    :param config_id: Optional config scope. None matches tenant-wide
        registrations only.
    :param coverage_threshold: Override the reactor's default
        (0.10). Lower = lifecycle overlays apply at lower lane-share
        coverage.
    :param timeout_seconds: A2A call timeout.
    """
    try:
        from azirella_a2a_client import Client
    except ImportError as exc:
        logger.warning(
            "make_lifecycle_reactor: azirella_a2a_client unavailable; "
            "lifecycle reactor not constructed. exc=%s", exc,
        )
        return None

    try:
        from app.services.powell.lane_volume_lifecycle_reactor import (
            LaneVolumeLifecycleReactor,
        )
    except ImportError as exc:
        logger.warning(
            "make_lifecycle_reactor: reactor module unavailable. exc=%s", exc,
        )
        return None

    try:
        client = Client.for_plane(
            "demand", db=db, tenant_id=tenant_id, config_id=config_id,
        )
    except Exception as exc:
        # Includes A2AClientError (no producer registered, no endpoint
        # URL, etc.) and any plane_registry import failure. Returning
        # None lets the caller proceed without a reactor — the
        # forecaster will run without lifecycle overlays.
        logger.warning(
            "make_lifecycle_reactor: DP plane resolution failed for "
            "tenant=%s config=%s — lifecycle reactor not constructed. "
            "exc=%s",
            tenant_id, config_id, exc,
        )
        return None

    provider = A2ALifecycleAdjustmentProvider(
        client, timeout_seconds=timeout_seconds,
    )
    if coverage_threshold is None:
        return LaneVolumeLifecycleReactor(provider=provider)
    return LaneVolumeLifecycleReactor(
        provider=provider, coverage_threshold=coverage_threshold,
    )


def _extract_skill_result(task: Any) -> Any:
    """Extract the skill's return payload from a Task envelope.

    A2A tasks/send returns a Task with the producer's reply nested in
    an artifact / message — the exact shape varies slightly across
    versions of the spec. This helper pulls the data out defensively
    and returns ``None`` if the shape is unrecognised.
    """
    # Modern shape: task.artifacts[0].parts[0].data
    artifacts = getattr(task, "artifacts", None)
    if artifacts:
        for art in artifacts:
            parts = getattr(art, "parts", None) or []
            for part in parts:
                data = getattr(part, "data", None)
                if data is not None:
                    return data
    # Older shape: task.message.parts[0].data
    message = getattr(task, "message", None)
    if message is not None:
        parts = getattr(message, "parts", None) or []
        for part in parts:
            data = getattr(part, "data", None)
            if data is not None:
                return data
    # Dict fallback for transport-layer responses.
    if isinstance(task, dict):
        return task.get("result") or task.get("data")
    return None


__all__ = [
    "A2ALifecycleAdjustmentProvider",
    "make_lifecycle_reactor",
]
