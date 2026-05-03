"""LaneVolumeLifecycleReactor — §3.45 (TMS lane-volume lifecycle reactor).

Translates DP's per-product lifecycle adjustments into per-lane signal
overlays that the L1 ``LaneVolumeForecastTRM`` consumes.

The substrate this depends on:

  - **§3.43** — Core's ``ProductLane`` table, which records what
    fraction of each lane's volume is contributed by each product over
    a temporal window. Without this, we can't translate "product X has
    a 50% NPI lift" into "lane L (which is 30% product X) gets a 15%
    NPI lift."

  - **§3.44** — DP's ``forecast.adjustment.list_lifecycle`` A2A skill,
    which exposes recent lifecycle-tagged forecast adjustments
    keyed by ``(product_id, period_start, period_end, reason_code,
    adjustment_value)``.

The math:

  lane_overlay(L, period) =
      Σ_p [ volume_share(p, L, period) × per_product_lift(p, period) ]

where ``per_product_lift`` is DP's ``adjustment_value`` (signed delta
fraction of baseline). The sum is over products with non-zero lifecycle
adjustments in the period; products without lifecycle adjustments
contribute zero.

The reactor emits one ``LaneOverlay`` per affected ``(lane, period)``
tuple. The TRM caller reads ``overlays[(lane_id, period_start)]`` and
translates it onto ``LaneVolumeForecastState.signal_type`` /
``signal_magnitude`` / ``signal_confidence`` before invoking the
forecaster.

Why this lives in TMS, not Core: the *math* of weighting per-product
adjustments by lane share is policy specific to "transport plane
forecasts loads on lanes." It's not substrate. The two tables it
reads (``ProductLane``, DP's adjustments via A2A skill) are substrate
and live in their respective producer planes; this module is the
TMS-side glue that consumes them.

Per CLAUDE.md no-fallbacks rule: when the substrate is missing
(``ProductLane`` empty for a lane × period, or DP A2A unavailable),
the reactor returns no overlay — does not fall back to a uniform
shift. Lifecycle reactivity at the lane grain requires real
volume-share data; without it, the L1 forecaster runs without a
lifecycle overlay and the planner sees the unadjusted baseline.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LaneOverlay:
    """Per-lane × period lifecycle signal overlay.

    Attributes
    ----------
    lane_id, period_start, period_end : the window this overlay applies to.
    signal_type : str
        ``"NPI"`` if any contributing product is in NPI introduction or
        ramp; ``"EOL"`` if any is in phaseout / runout; ``"MIXED"`` if
        both. Maps onto ``LaneVolumeForecastState.signal_type`` directly.
    signal_magnitude : float
        Volume-share-weighted aggregate adjustment fraction. Positive =
        lift; negative = decline.
    signal_confidence : float
        Confidence the L1 forecaster should weight this overlay with.
        Derived from the underlying adjustment confidences and the
        coverage of contributing products (0..1).
    contributing_products : list[str]
        Product IDs whose lifecycle adjustments aggregated into this
        overlay. Surfaceable in audit / explain UIs.
    coverage_share : float
        Sum of ``volume_share`` across contributing products. 1.0 when
        every product on the lane has a lifecycle adjustment; lower
        when only a subset does. Used by the TRM caller to decide
        whether the overlay is meaningful enough to apply (very low
        coverage → ignore).
    reason_codes : list[str]
        Distinct lifecycle reason codes that contributed
        (``lifecycle_npi_introduction`` etc.).
    """

    lane_id: int
    period_start: date
    period_end: date
    signal_type: str
    signal_magnitude: float
    signal_confidence: float
    contributing_products: List[str] = field(default_factory=list)
    coverage_share: float = 0.0
    reason_codes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DP A2A bridge
# ---------------------------------------------------------------------------


class LifecycleAdjustmentProvider(Protocol):
    """Read-side abstraction over DP's
    ``forecast.adjustment.list_lifecycle`` A2A skill (§3.44).

    The provider returns one dict per matching ForecastAdjustment row,
    keyed by ``product_id``, with at least:

      - ``period_start``: ISO date string or ``date``
      - ``period_end``: ISO date string or ``date``
      - ``reason_code``: str
      - ``adjustment_value``: float (signed fraction of baseline)
      - ``new_value``, ``original_value``: float (absolute) — optional
    """

    def list_lifecycle_adjustments(
        self,
        *,
        tenant_id: int,
        since: Optional[datetime] = None,
        reason_codes: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        ...


# ---------------------------------------------------------------------------
# Reactor
# ---------------------------------------------------------------------------


COVERAGE_THRESHOLD_DEFAULT = 0.10
"""Below this fraction, the overlay is ignored — too little of the
lane's volume is lifecycle-tagged for the lifecycle signal to
meaningfully shift the lane forecast. Tunable per tenant."""


class LaneVolumeLifecycleReactor:
    """Compute lane-volume lifecycle overlays from DP adjustments + Core
    ``ProductLane`` shares.

    Single entry point: :meth:`compute_overlays`. Stateless —
    instantiate per call or keep one around; both are fine.

    Construction takes a :class:`LifecycleAdjustmentProvider` (the
    DP-A2A wrapper). Tests can pass a fake provider. Production wires
    in the live A2A client.
    """

    def __init__(
        self,
        provider: LifecycleAdjustmentProvider,
        *,
        coverage_threshold: float = COVERAGE_THRESHOLD_DEFAULT,
    ) -> None:
        self.provider = provider
        if not 0.0 <= coverage_threshold <= 1.0:
            raise ValueError("coverage_threshold must be in [0, 1]")
        self.coverage_threshold = coverage_threshold

    def compute_overlays(
        self,
        db: Session,
        *,
        tenant_id: int,
        since: Optional[datetime] = None,
    ) -> Dict[Tuple[int, date], LaneOverlay]:
        """Compute lane × period overlays for the tenant.

        Steps:
          1. Pull recent lifecycle adjustments from DP via the provider.
          2. For each (product, period) tuple, look up that product's
             share of each lane's volume in ``ProductLane`` (window
             overlap with the adjustment period).
          3. Aggregate per (lane, period): signal_magnitude is the
             volume-share-weighted sum of adjustment_values; signal_type
             collapses to NPI / EOL / MIXED based on contributing reason
             codes; coverage_share is the sum of contributing shares.
          4. Drop overlays where coverage_share < ``coverage_threshold``.
        """
        if since is None:
            # Default to 30 days ago (UTC).
            since = datetime.now(timezone.utc) - timedelta(days=30)

        adjustments = self.provider.list_lifecycle_adjustments(
            tenant_id=tenant_id,
            since=since,
        )
        if not adjustments:
            return {}

        # Bucket adjustments by (product_id, period_start, period_end).
        # A product may have multiple adjustments in a single period
        # (e.g. introduction + ramp landing in the same week); sum them.
        by_product_period: Dict[
            Tuple[str, date, date], _ProductPeriodAdjustment
        ] = {}
        for adj in adjustments:
            product_id = adj.get("product_id")
            if not product_id:
                continue
            ps = _coerce_date(adj.get("period_start"))
            pe = _coerce_date(adj.get("period_end"))
            if ps is None or pe is None or ps >= pe:
                continue
            adjustment_value = adj.get("adjustment_value")
            if adjustment_value is None:
                continue
            reason_code = adj.get("reason_code") or ""
            key = (product_id, ps, pe)
            existing = by_product_period.get(key)
            if existing is None:
                by_product_period[key] = _ProductPeriodAdjustment(
                    product_id=product_id,
                    period_start=ps,
                    period_end=pe,
                    adjustment_value=float(adjustment_value),
                    reason_codes=[reason_code] if reason_code else [],
                )
            else:
                existing.adjustment_value += float(adjustment_value)
                if reason_code and reason_code not in existing.reason_codes:
                    existing.reason_codes.append(reason_code)

        if not by_product_period:
            return {}

        # Pull ProductLane rows for the affected (product, period) tuples.
        # We do one query per distinct period to keep the read pattern
        # in line with the hot-path index. In practice the period set is
        # small (one or two weeks).
        per_lane_period: Dict[Tuple[int, date], _LaneAggregation] = {}

        product_periods_by_period: Dict[Tuple[date, date], List[str]] = {}
        for (pid, ps, pe), _ in by_product_period.items():
            product_periods_by_period.setdefault((ps, pe), []).append(pid)

        # Lazy import to avoid dragging Core ORM into module-load when
        # callers only need the dataclasses.
        from azirella_data_model.transport_plan import ProductLane

        for (ps, pe), pids in product_periods_by_period.items():
            stmt = (
                select(
                    ProductLane.lane_id,
                    ProductLane.product_id,
                    ProductLane.period_start,
                    ProductLane.period_end,
                    ProductLane.volume_share,
                    ProductLane.confidence,
                )
                .where(
                    ProductLane.tenant_id == tenant_id,
                    ProductLane.product_id.in_(pids),
                    # Window overlap: ProductLane window touches the
                    # adjustment window.
                    ProductLane.period_start < pe,
                    ProductLane.period_end > ps,
                )
            )
            rows = db.execute(stmt).all()

            for row in rows:
                key_pp = (row.product_id, ps, pe)
                adjustment = by_product_period.get(key_pp)
                if adjustment is None:
                    # Window-overlap on a different product-period;
                    # shouldn't happen given the .in_() filter above,
                    # but be defensive.
                    continue
                lane_key = (row.lane_id, ps)
                agg = per_lane_period.get(lane_key)
                if agg is None:
                    agg = _LaneAggregation(
                        lane_id=row.lane_id,
                        period_start=ps,
                        period_end=pe,
                    )
                    per_lane_period[lane_key] = agg
                share = float(row.volume_share)
                conf = float(row.confidence) if row.confidence is not None else 1.0
                agg.weighted_magnitude_sum += share * adjustment.adjustment_value
                agg.coverage_share += share
                agg.weighted_confidence_sum += share * conf
                if adjustment.product_id not in agg.contributing_products:
                    agg.contributing_products.append(adjustment.product_id)
                for rc in adjustment.reason_codes:
                    if rc not in agg.reason_codes:
                        agg.reason_codes.append(rc)

        # Materialise into LaneOverlay dataclasses, dropping low-coverage
        # ones.
        overlays: Dict[Tuple[int, date], LaneOverlay] = {}
        for key, agg in per_lane_period.items():
            if agg.coverage_share < self.coverage_threshold:
                continue
            # Average confidence across contributing products (volume-
            # share weighted); coverage_share itself is the normaliser.
            avg_confidence = (
                agg.weighted_confidence_sum / agg.coverage_share
                if agg.coverage_share > 0
                else 0.0
            )
            overlays[key] = LaneOverlay(
                lane_id=agg.lane_id,
                period_start=agg.period_start,
                period_end=agg.period_end,
                signal_type=_collapse_signal_type(agg.reason_codes),
                signal_magnitude=agg.weighted_magnitude_sum,
                signal_confidence=min(1.0, max(0.0, avg_confidence)),
                contributing_products=list(agg.contributing_products),
                coverage_share=min(1.0, agg.coverage_share),
                reason_codes=list(agg.reason_codes),
            )
        return overlays

    def apply_to_state(
        self,
        state: Any,
        overlays: Dict[Tuple[int, date], LaneOverlay],
    ) -> Any:
        """Mutate a ``LaneVolumeForecastState`` (or compatible) in-place
        with the lifecycle overlay matching its ``(lane_id,
        period_start)`` key. Returns the state for chaining.

        When no overlay matches, the state's signal fields are left
        untouched. Existing non-lifecycle signals (e.g. PROMO_LIFT
        already set by another upstream service) are *not* overwritten —
        the lifecycle reactor refuses to clobber a pre-existing signal,
        on the principle that whichever upstream set it earlier knew
        more about its provenance than we do.
        """
        lane_id = getattr(state, "lane_id", None)
        period_start = getattr(state, "period_start", None)
        if lane_id is None or period_start is None:
            return state
        overlay = overlays.get((int(lane_id), period_start))
        if overlay is None:
            return state
        if getattr(state, "signal_type", "") and getattr(state, "signal_type") not in (
            "NPI", "EOL", "MIXED"
        ):
            # Don't clobber a non-lifecycle signal already set upstream.
            return state
        state.signal_type = overlay.signal_type
        state.signal_magnitude = overlay.signal_magnitude
        state.signal_confidence = overlay.signal_confidence
        return state


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@dataclass
class _ProductPeriodAdjustment:
    product_id: str
    period_start: date
    period_end: date
    adjustment_value: float
    reason_codes: List[str]


@dataclass
class _LaneAggregation:
    lane_id: int
    period_start: date
    period_end: date
    weighted_magnitude_sum: float = 0.0
    weighted_confidence_sum: float = 0.0
    coverage_share: float = 0.0
    contributing_products: List[str] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)


def _coerce_date(value: Any) -> Optional[date]:
    """Accept date / datetime / ISO string and return date, or None."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None
    return None


_NPI_CODES = {"lifecycle_npi_introduction", "lifecycle_npi_ramp"}
_EOL_CODES = {"lifecycle_eol_phaseout", "lifecycle_eol_runout"}


def _collapse_signal_type(reason_codes: List[str]) -> str:
    """Decide signal_type from the set of contributing reason codes.

    NPI codes only → "NPI". EOL codes only → "EOL". Both present →
    "MIXED" (same lane has products on opposite ends of their
    lifecycle, which is operationally meaningful — planner should
    review)."""
    has_npi = any(rc in _NPI_CODES for rc in reason_codes)
    has_eol = any(rc in _EOL_CODES for rc in reason_codes)
    if has_npi and has_eol:
        return "MIXED"
    if has_npi:
        return "NPI"
    if has_eol:
        return "EOL"
    return ""


__all__ = [
    "LaneOverlay",
    "LaneVolumeLifecycleReactor",
    "LifecycleAdjustmentProvider",
    "COVERAGE_THRESHOLD_DEFAULT",
]
