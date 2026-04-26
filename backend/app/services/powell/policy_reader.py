"""
Lazy + cached active-policy reader for L1 TRMs.

TRMs are short-lived per-decision-cycle objects. Reading the active
PolicyParameters row on every `_build_state()` call would issue an
extra SELECT per shipment / load / appointment evaluated. Instead,
each TRM keeps a `_PolicyCache` instance that fetches once on first
access and stamps its read-time onto the cached object so a stale
cache can be detected.

Refresh window defaults to 5 minutes, which is far shorter than the
12h conformal-calibration cadence and the daily L4 rebriefing window
— policy changes within a TRM's decision cycle are vanishingly rare.

## Why not call `get_active_policy` directly

Three reasons:
  * One-row-per-cycle vs N-rows-per-cycle. A single TRM call may
    process 100s of shipments; we want one SELECT, not 100.
  * Robustness to missing policy. Provisioning seeds a default at
    tenant-create time; if it didn't (e.g. a pre-2026-04-24 tenant
    that hasn't had the migration backfill rerun), this reader
    surfaces the gap once with a logged warning rather than 100 times.
  * Future ACI hooks can flip cache invalidation when policy is
    superseded by `apply_policy_patch`.

## Failure mode (no-fallbacks)

If no active policy exists, we return `None` (not a synthetic default).
Callers that genuinely need a value pull from their existing class-
level `DEFAULT_*` constants. This preserves the no-fallbacks invariant
(`feedback_soc2_no_fallback.md`) — silent defaults mask provisioning
gaps that should fire alerts.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.policy_parameters import PolicyParameters
from app.services.policy_service import PolicyNotFound, get_active_policy

logger = logging.getLogger(__name__)


_DEFAULT_REFRESH_SECONDS = 300  # 5 minutes


class PolicyCache:
    """Per-(tenant, config) lazy cache. One per TRM instance."""

    def __init__(
        self,
        tenant_id: int,
        config_id: Optional[int] = None,
        refresh_seconds: int = _DEFAULT_REFRESH_SECONDS,
    ):
        self.tenant_id = tenant_id
        self.config_id = config_id
        self._refresh = refresh_seconds
        self._cached: Optional[PolicyParameters] = None
        self._fetched_at: Optional[datetime] = None
        self._missing_warning_logged = False

    def get(self, db: Session) -> Optional[PolicyParameters]:
        """Return the active policy (cached) or None if none exists.

        Logs a one-time WARNING when the policy is missing — never
        silently substitutes a default.
        """
        now = datetime.utcnow()
        if (
            self._cached is not None
            and self._fetched_at is not None
            and (now - self._fetched_at).total_seconds() < self._refresh
        ):
            return self._cached

        try:
            policy = get_active_policy(
                db, tenant_id=self.tenant_id, config_id=self.config_id
            )
        except PolicyNotFound:
            if not self._missing_warning_logged:
                logger.warning(
                    "PolicyCache: no active PolicyParameters for tenant=%s "
                    "config=%s — TRMs will fall back to class-level DEFAULT_* "
                    "constants. Provisioning may have skipped policy creation.",
                    self.tenant_id, self.config_id,
                )
                self._missing_warning_logged = True
            return None

        self._cached = policy
        self._fetched_at = now
        return policy

    def invalidate(self) -> None:
        """Drop the cached row. Useful from tests + after explicit
        `apply_policy_patch` calls in the same process."""
        self._cached = None
        self._fetched_at = None


def lowest_tier_priority(policy: PolicyParameters) -> Optional[int]:
    """Return the integer priority of the lowest service-level tier.

    "Lowest tier" = highest priority integer in the canonical tier
    list (PLATINUM=1 ... ECONOMY=5). Used as the default
    `customer_tier` value for shipments where a tier mapping isn't
    yet wired — conservative: every unknown shipment is treated as
    bottom-tier.
    """
    tiers = policy.service_level_tiers or []
    if not tiers:
        return None
    try:
        return max(int(t["priority"]) for t in tiers if "priority" in t)
    except (TypeError, ValueError):
        return None
