"""Production wire-up for §3.45 LaneVolumeLifecycleReactor.

Closes the §3.40 loop by providing:

  - :class:`RouterLifecycleAdjustmentProvider` — concrete implementation
    of the reactor's :class:`LifecycleAdjustmentProvider` Protocol. Calls
    DP's ``forecast.adjustment.list_lifecycle`` skill (§3.44) via
    :class:`azirella_router.RouterClient`, which resolves the tenant's
    DP ``producer_tier`` per call and dispatches in-process for
    HEURISTIC / THIRD_PARTY tiers or A2A HTTP for AZIRELLA tier.

  - :func:`make_lifecycle_reactor` — factory that constructs the provider
    and a configured :class:`LaneVolumeLifecycleReactor`.

Usage::

    from app.services.powell.lifecycle_reactor_factory import (
        make_lifecycle_reactor,
    )

    reactor = make_lifecycle_reactor(db, tenant_id=42)
    svc.publish_forecast(
        tenant_id=42, config_id=1, inputs=lane_inputs,
        lifecycle_reactor=reactor,  # None is fine — service handles it
    )

AD-12 v3 cutover (CONSUMER_ADOPTION_LOG 2026-05-04, §3.48): replaced
direct ``azirella_a2a_client.Client`` construction with
``RouterClient.call_skill``. The router resolves ``producer_tier``
per-call, so HEURISTIC-tier DP tenants don't need a DP container
deployed — the call lands in-process via
``autonomy-dp-heuristics``. At AZIRELLA tier the call still goes A2A
through the same client substrate.

This module is the *only* place in TMS that knows about the DP cross-
plane call's wire shape. The reactor itself stays Protocol-typed and is
testable with fake providers (see ``test_lane_volume_lifecycle_reactor.py``).
"""
from __future__ import annotations

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


class RouterLifecycleAdjustmentProvider:
    """Production :class:`LifecycleAdjustmentProvider` backed by
    :class:`azirella_router.RouterClient`.

    Calls DP's ``forecast.adjustment.list_lifecycle`` skill. The router
    resolves ``producer_tier`` per call so the same provider serves both
    AZIRELLA-tier DP (A2A HTTP to a DP container) and HEURISTIC-tier DP
    (in-process via ``autonomy-dp-heuristics`` if installed).

    The reactor's Protocol is sync; ``RouterClient.call_skill`` is sync
    (it internally bridges asyncio for the AZIRELLA path). No asyncio
    plumbing is needed at this layer.
    """

    def __init__(
        self,
        *,
        db: "Session",
        config_id: Optional[int] = None,
    ) -> None:
        self._db = db
        self._config_id = config_id

    def list_lifecycle_adjustments(
        self,
        *,
        tenant_id: int,
        since: Optional[datetime] = None,
        reason_codes: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Sync call through the router.

        Returns an empty list (rather than raising) on any failure —
        the reactor's contract is "no-op when the producer is down,"
        not "fail the whole publish_forecast." Errors log WARNING so
        ops can monitor.
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
            from azirella_router import RouterClient
        except ImportError as exc:
            logger.warning(
                "RouterLifecycleAdjustmentProvider: azirella-router not "
                "installed — returning empty result. exc=%s", exc,
            )
            return []

        try:
            response = RouterClient.call_skill(
                db=self._db,
                tenant_id=tenant_id,
                skill_id=_DP_LIST_LIFECYCLE_SKILL_ID,
                inp=payload,
                config_id=self._config_id,
            )
        except Exception as exc:
            logger.warning(
                "RouterLifecycleAdjustmentProvider: router call failed for "
                "tenant=%s — returning empty result. exc=%s",
                tenant_id, exc,
            )
            return []

        result = _extract_skill_result(response)
        if not isinstance(result, dict):
            logger.warning(
                "RouterLifecycleAdjustmentProvider: unexpected result shape "
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
) -> "Optional[LaneVolumeLifecycleReactor]":
    """Construct a :class:`LaneVolumeLifecycleReactor` wired through
    :class:`azirella_router.RouterClient`.

    Returns ``None`` when ``azirella_router`` or the reactor module
    cannot be imported. Per-call DP resolution failures (no producer
    registered, A2A endpoint unreachable, etc.) are handled inside
    :class:`RouterLifecycleAdjustmentProvider` — they yield empty
    overlays rather than a ``None`` reactor. Callers thread the result
    into ``publish_forecast``'s ``lifecycle_reactor=`` parameter;
    ``None`` is a safe no-op there.

    :param db: SQLAlchemy session against the platform DB. Held by the
        provider for per-call ``plane_registration`` lookups.
    :param tenant_id: Tenant scope. (Currently used for symmetry with
        the prior factory signature; the provider reads ``tenant_id``
        from the per-call kwarg, not from construction.)
    :param config_id: Optional config scope passed to the router on
        each dispatch.
    :param coverage_threshold: Override the reactor's default (0.10).
    """
    # ``tenant_id`` is accepted for API symmetry with the prior factory
    # signature. It's not used at construction time because the router
    # resolves per call; see RouterLifecycleAdjustmentProvider docstring.
    del tenant_id

    try:
        import azirella_router  # noqa: F401  -- presence check
    except ImportError as exc:
        logger.warning(
            "make_lifecycle_reactor: azirella_router unavailable; "
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

    provider = RouterLifecycleAdjustmentProvider(db=db, config_id=config_id)
    if coverage_threshold is None:
        return LaneVolumeLifecycleReactor(provider=provider)
    return LaneVolumeLifecycleReactor(
        provider=provider, coverage_threshold=coverage_threshold,
    )


def _extract_skill_result(task: Any) -> Any:
    """Walk an A2A Task envelope or unwrap a dict response.

    :class:`RouterClient.call_skill` returns:

    - HEURISTIC tier: the handler's stamped dict directly (no envelope).
    - AZIRELLA tier: ``task.result`` if present on the Task, else the
      raw Task object (depends on the A2A spec version).

    Both shapes are handled here. A dict that lacks an explicit
    ``result``/``data`` key is treated as the result itself (the
    HEURISTIC path).
    """
    # Modern Task shape: task.artifacts[0].parts[0].data
    artifacts = getattr(task, "artifacts", None)
    if artifacts:
        for art in artifacts:
            parts = getattr(art, "parts", None) or []
            for part in parts:
                data = getattr(part, "data", None)
                if data is not None:
                    return data
    # Older Task shape: task.message.parts[0].data
    message = getattr(task, "message", None)
    if message is not None:
        parts = getattr(message, "parts", None) or []
        for part in parts:
            data = getattr(part, "data", None)
            if data is not None:
                return data
    if isinstance(task, dict):
        # Dict envelope variants — {"result": {...}} or {"data": {...}}
        # take precedence; otherwise the dict itself IS the result
        # (HEURISTIC handlers stamp markers + data into one dict).
        if "result" in task:
            return task["result"]
        if "data" in task:
            return task["data"]
        return task
    return None


__all__ = [
    "RouterLifecycleAdjustmentProvider",
    "make_lifecycle_reactor",
]
