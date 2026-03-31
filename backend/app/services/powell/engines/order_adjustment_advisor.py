"""
Order Adjustment Advisor — Adjust Before Create

Principle: Before ANY TRM creates a new order (PO, MO, TO, QO), it must first
check whether an existing open order can be adjusted to satisfy the need.

Order status eligibility:
  - planned / open → adjustable (expedite, increase, reroute, consolidate)
  - confirmed / released → not adjusted (too close to execution)
  - in_progress → immutable

Adjustment hierarchy (cheapest first):
  1. EXPEDITE  — Pull forward an existing planned order to today
  2. INCREASE  — Increase quantity on an existing planned order
  3. REROUTE   — Change source/destination on a planned transfer
  4. CONSOLIDATE — Merge with another planned order for the same product
  5. CREATE    — Only if no planned order can be adjusted

Glenday Sieve integration:
  - GREEN (runners, ~50% volume): Almost always have open orders to adjust.
    Prefer expedite/increase over create. Standing orders should exist.
  - YELLOW (repeaters, ~30%): Usually have orders in the pipeline.
    Prefer adjust, but create is acceptable.
  - RED (strangers, ~15%): May not have pipeline orders. Create is normal,
    but still check for adjustable orders first.
  - BLUE (specials, ~5%): Rarely have pipeline. Create is expected.
    Still check — a blue item might share a supplier/route with a green.

Quality inspection follows the same principle:
  - Before creating a new inspection order, check if an existing QO for the
    same lot/supplier can be extended or the inspection scope increased.

Usage:
  advisor = OrderAdjustmentAdvisor(db, config_id, product_id, site_id)
  result = await advisor.recommend(
      need_type="po",           # po, mo, to, qo
      needed_qty=500,
      needed_by=date(2026, 4, 7),
      runner_category="green",  # from GlendaySieve
  )
  if result.action != "create":
      # Adjust the existing order
      ...
  else:
      # Create new order
      ...
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_, or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class AdjustmentAction(str, Enum):
    """What to do with an existing order."""
    EXPEDITE = "expedite"          # Pull forward to earlier date
    INCREASE = "increase"          # Increase quantity
    EXPEDITE_AND_INCREASE = "expedite_and_increase"
    REROUTE = "reroute"            # Change source/destination
    CONSOLIDATE = "consolidate"    # Merge with another order
    EXTEND_SCOPE = "extend_scope"  # Quality: add inspection criteria
    CREATE = "create"              # No adjustable order found — create new


@dataclass
class AdjustableOrder:
    """An existing open order that could be adjusted."""
    order_id: str
    order_type: str               # po, mo, to, qo
    product_id: str
    site_id: str
    current_qty: float
    planned_date: Optional[date]
    supplier_id: Optional[str] = None
    from_site_id: Optional[str] = None
    to_site_id: Optional[str] = None
    status: str = "open"
    # How much slack exists
    qty_headroom: float = 0.0     # Max qty increase without new approval
    date_headroom_days: int = 0   # How many days it can be pulled forward


@dataclass
class AdjustmentRecommendation:
    """Recommendation: adjust existing order or create new."""
    action: AdjustmentAction
    existing_order: Optional[AdjustableOrder] = None
    adjust_qty_delta: float = 0.0        # How much to increase
    adjust_date: Optional[date] = None   # New target date (if expediting)
    new_order_qty: float = 0.0           # If action=CREATE, how much
    reasoning: str = ""
    cost_estimate: float = 0.0           # Estimated cost of adjustment
    runner_category: str = "blue"


# Maximum days to look ahead for adjustable orders
_LOOKAHEAD_DAYS = 30

# Glenday-based adjustment preference weights
# Higher = more strongly prefer adjusting over creating
_GLENDAY_ADJUST_PREFERENCE = {
    "green": 0.95,   # Almost always adjust — runners have standing orders
    "yellow": 0.80,  # Usually adjust
    "red": 0.50,     # Equal preference
    "blue": 0.20,    # Usually create
}


class OrderAdjustmentAdvisor:
    """Checks existing open orders before recommending creation.

    Called by all TRMs (PO, MO, TO, Quality) at the start of their
    evaluation to determine whether a new order is needed or whether
    an existing order can be adjusted.
    """

    def __init__(
        self,
        db: Session,
        config_id: int,
        product_id: str,
        site_id: str,
    ):
        self.db = db
        self.config_id = config_id
        self.product_id = product_id
        self.site_id = site_id

    def recommend(
        self,
        need_type: str,
        needed_qty: float,
        needed_by: date,
        runner_category: str = "blue",
        supplier_id: Optional[str] = None,
        from_site_id: Optional[str] = None,
        to_site_id: Optional[str] = None,
    ) -> AdjustmentRecommendation:
        """Check for adjustable existing orders before recommending create.

        Args:
            need_type: "po", "mo", "to", "qo"
            needed_qty: How much is needed
            needed_by: When it's needed
            runner_category: Glenday category for this product
            supplier_id: For PO — preferred supplier
            from_site_id: For TO — source site
            to_site_id: For TO — destination site

        Returns:
            AdjustmentRecommendation with action and details.
        """
        adjust_pref = _GLENDAY_ADJUST_PREFERENCE.get(runner_category, 0.5)

        # Find existing open orders that could be adjusted
        candidates = self._find_adjustable_orders(
            need_type, needed_by, supplier_id, from_site_id, to_site_id,
        )

        if not candidates:
            return AdjustmentRecommendation(
                action=AdjustmentAction.CREATE,
                new_order_qty=needed_qty,
                reasoning=f"No open {need_type.upper()} orders found to adjust",
                runner_category=runner_category,
            )

        # Score each candidate
        best_score = -1.0
        best_rec = None

        for order in candidates:
            score, rec = self._score_adjustment(
                order, needed_qty, needed_by, adjust_pref, need_type,
            )
            if score > best_score:
                best_score = score
                best_rec = rec

        # If best adjustment score beats the "create new" threshold
        # (adjusted by Glenday preference), recommend adjusting
        create_threshold = 1.0 - adjust_pref  # Green: 0.05, Blue: 0.80
        if best_rec and best_score >= create_threshold:
            best_rec.runner_category = runner_category
            return best_rec

        return AdjustmentRecommendation(
            action=AdjustmentAction.CREATE,
            new_order_qty=needed_qty,
            reasoning=(
                f"Existing orders scored {best_score:.2f} vs threshold {create_threshold:.2f} "
                f"(runner: {runner_category})"
            ),
            runner_category=runner_category,
        )

    def _find_adjustable_orders(
        self,
        need_type: str,
        needed_by: date,
        supplier_id: Optional[str],
        from_site_id: Optional[str],
        to_site_id: Optional[str],
    ) -> List[AdjustableOrder]:
        """Query existing open orders that could satisfy this need."""
        candidates = []
        lookahead = needed_by + timedelta(days=_LOOKAHEAD_DAYS)

        try:
            if need_type == "po":
                candidates = self._find_open_pos(needed_by, lookahead, supplier_id)
            elif need_type == "mo":
                candidates = self._find_open_mos(needed_by, lookahead)
            elif need_type == "to":
                candidates = self._find_open_tos(needed_by, lookahead, from_site_id, to_site_id)
            elif need_type == "qo":
                candidates = self._find_open_qos(needed_by, lookahead)
        except Exception as e:
            logger.warning("Failed to find adjustable %s orders: %s", need_type, e)

        return candidates

    def _find_open_pos(
        self, needed_by: date, lookahead: date, supplier_id: Optional[str],
    ) -> List[AdjustableOrder]:
        """Find open purchase orders for this product."""
        from app.models.sc_entities import PurchaseOrder, PurchaseOrderLineItem

        try:
            query = (
                self.db.query(PurchaseOrder)
                .filter(
                    PurchaseOrder.config_id == self.config_id,
                    PurchaseOrder.order_status.in_(["planned", "open"]),
                )
            )
            if supplier_id:
                query = query.filter(PurchaseOrder.vendor_id == supplier_id)

            rows = query.limit(20).all()
            results = []
            for po in rows:
                # Check if this PO has a line for our product
                lines = (
                    self.db.query(PurchaseOrderLineItem)
                    .filter(
                        PurchaseOrderLineItem.po_id == po.id,
                        PurchaseOrderLineItem.product_id == self.product_id,
                    )
                    .all()
                )
                for line in lines:
                    planned = getattr(line, "expected_delivery_date", None) or getattr(po, "order_date", None)
                    results.append(AdjustableOrder(
                        order_id=str(po.id),
                        order_type="po",
                        product_id=self.product_id,
                        site_id=self.site_id,
                        current_qty=float(getattr(line, "quantity", 0) or 0),
                        planned_date=planned.date() if hasattr(planned, "date") else planned,
                        supplier_id=str(po.vendor_id) if po.vendor_id else None,
                        qty_headroom=float(getattr(line, "quantity", 0) or 0) * 0.5,  # Can increase by 50%
                        date_headroom_days=14,  # Can pull forward up to 2 weeks
                    ))
            return results
        except Exception as e:
            logger.debug("PO search failed: %s", e)
            return []

    def _find_open_mos(self, needed_by: date, lookahead: date) -> List[AdjustableOrder]:
        """Find open manufacturing orders for this product at this site."""
        from app.models.sc_entities import ProductionOrder

        try:
            rows = (
                self.db.query(ProductionOrder)
                .filter(
                    ProductionOrder.config_id == self.config_id,
                    ProductionOrder.product_id == self.product_id,
                    ProductionOrder.order_status.in_(["planned", "open"]),
                )
                .limit(20)
                .all()
            )
            results = []
            for mo in rows:
                planned = getattr(mo, "planned_end_date", None) or getattr(mo, "order_date", None)
                results.append(AdjustableOrder(
                    order_id=str(mo.id),
                    order_type="mo",
                    product_id=self.product_id,
                    site_id=self.site_id,
                    current_qty=float(getattr(mo, "total_qty", 0) or 0),
                    planned_date=planned.date() if hasattr(planned, "date") else planned,
                    qty_headroom=float(getattr(mo, "total_qty", 0) or 0) * 0.3,  # 30% increase
                    date_headroom_days=7,  # Can pull forward 1 week
                ))
            return results
        except Exception as e:
            logger.debug("MO search failed: %s", e)
            return []

    def _find_open_tos(
        self, needed_by: date, lookahead: date,
        from_site_id: Optional[str], to_site_id: Optional[str],
    ) -> List[AdjustableOrder]:
        """Find open transfer orders for this product."""
        from app.models.sc_entities import TransferOrder

        try:
            query = (
                self.db.query(TransferOrder)
                .filter(
                    TransferOrder.config_id == self.config_id,
                    TransferOrder.order_status.in_(["planned", "open"]),
                )
            )
            rows = query.limit(20).all()
            results = []
            for to in rows:
                # Check product match via line items or direct field
                to_pid = getattr(to, "product_id", None)
                if to_pid and str(to_pid) != self.product_id:
                    continue
                planned = getattr(to, "ship_by_date", None) or getattr(to, "order_date", None)
                results.append(AdjustableOrder(
                    order_id=str(to.id),
                    order_type="to",
                    product_id=self.product_id,
                    site_id=self.site_id,
                    current_qty=float(getattr(to, "quantity", 0) or 0),
                    planned_date=planned.date() if hasattr(planned, "date") else planned,
                    from_site_id=str(getattr(to, "from_site_id", "")) if getattr(to, "from_site_id", None) else None,
                    to_site_id=str(getattr(to, "to_site_id", "")) if getattr(to, "to_site_id", None) else None,
                    qty_headroom=float(getattr(to, "quantity", 0) or 0) * 0.5,
                    date_headroom_days=5,
                ))
            return results
        except Exception as e:
            logger.debug("TO search failed: %s", e)
            return []

    def _find_open_qos(self, needed_by: date, lookahead: date) -> List[AdjustableOrder]:
        """Find open quality orders for this product."""
        from app.models.sc_entities import QualityOrder

        try:
            rows = (
                self.db.query(QualityOrder)
                .filter(
                    QualityOrder.config_id == self.config_id,
                    QualityOrder.order_status.in_(["planned", "open"]),
                )
                .limit(20)
                .all()
            )
            results = []
            for qo in rows:
                qo_pid = getattr(qo, "product_id", None)
                if qo_pid and str(qo_pid) != self.product_id:
                    continue
                planned = getattr(qo, "order_date", None)
                results.append(AdjustableOrder(
                    order_id=str(qo.id),
                    order_type="qo",
                    product_id=self.product_id,
                    site_id=self.site_id,
                    current_qty=float(getattr(qo, "total_qty", 0) or 0),
                    planned_date=planned.date() if hasattr(planned, "date") else planned,
                    qty_headroom=0,  # QO: extend scope, not qty
                    date_headroom_days=3,
                ))
            return results
        except Exception as e:
            logger.debug("QO search failed: %s", e)
            return []

    def _score_adjustment(
        self,
        order: AdjustableOrder,
        needed_qty: float,
        needed_by: date,
        adjust_pref: float,
        need_type: str,
    ) -> Tuple[float, Optional[AdjustmentRecommendation]]:
        """Score how well an existing order can satisfy this need.

        Returns (score, recommendation). Score 0-1, higher = better fit.
        """
        if not order.planned_date:
            return 0.0, None

        days_early = (order.planned_date - needed_by).days  # positive = order is later
        qty_gap = needed_qty - order.current_qty            # positive = need more

        # Can this order be pulled forward enough?
        can_expedite = days_early > 0 and days_early <= order.date_headroom_days
        needs_expedite = days_early > 0

        # Can this order's quantity be increased enough?
        can_increase = qty_gap > 0 and qty_gap <= order.qty_headroom
        needs_increase = qty_gap > 0

        # Order already covers timing and quantity — just needs expedite
        if not needs_expedite and not needs_increase:
            return 0.9 * adjust_pref, AdjustmentRecommendation(
                action=AdjustmentAction.EXPEDITE if days_early < 0 else AdjustmentAction.INCREASE,
                existing_order=order,
                reasoning=f"Existing {need_type.upper()} {order.order_id} already covers need",
            )

        # Can expedite to meet date
        if needs_expedite and can_expedite and not needs_increase:
            return 0.85 * adjust_pref, AdjustmentRecommendation(
                action=AdjustmentAction.EXPEDITE,
                existing_order=order,
                adjust_date=needed_by,
                reasoning=(
                    f"Expedite {need_type.upper()} {order.order_id} from "
                    f"{order.planned_date} to {needed_by} ({days_early} days earlier)"
                ),
            )

        # Can increase qty
        if needs_increase and can_increase and not needs_expedite:
            return 0.80 * adjust_pref, AdjustmentRecommendation(
                action=AdjustmentAction.INCREASE,
                existing_order=order,
                adjust_qty_delta=qty_gap,
                reasoning=(
                    f"Increase {need_type.upper()} {order.order_id} by {qty_gap:.0f} "
                    f"(from {order.current_qty:.0f} to {order.current_qty + qty_gap:.0f})"
                ),
            )

        # Both expedite and increase needed
        if needs_expedite and can_expedite and needs_increase and can_increase:
            return 0.75 * adjust_pref, AdjustmentRecommendation(
                action=AdjustmentAction.EXPEDITE_AND_INCREASE,
                existing_order=order,
                adjust_date=needed_by,
                adjust_qty_delta=qty_gap,
                reasoning=(
                    f"Expedite {need_type.upper()} {order.order_id} to {needed_by} "
                    f"and increase by {qty_gap:.0f}"
                ),
            )

        # For quality orders: extend inspection scope
        if need_type == "qo":
            return 0.70 * adjust_pref, AdjustmentRecommendation(
                action=AdjustmentAction.EXTEND_SCOPE,
                existing_order=order,
                reasoning=f"Extend scope of QO {order.order_id} to cover additional criteria",
            )

        # Can't fully adjust — partial credit
        partial_score = 0.3 * adjust_pref
        return partial_score, None
