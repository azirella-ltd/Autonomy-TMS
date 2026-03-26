"""
Confidence Funnel Service

Builds nested probability interval data for supply orders, showing when
supply will actually arrive using conformal prediction intervals.

Each order gets P50/P80/P90/P95 intervals derived from the conformal
prediction bounds on the supply_plan (lead_time_lower, lead_time_upper).
"""

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ConfidenceFunnelService:
    """Builds confidence funnel visualization data for supply orders."""

    def __init__(self, db: Session):
        self.db = db

    def build_funnel_data(
        self,
        config_id: int,
        product_id: str,
        site_id: int,
        horizon_days: int = 90,
    ) -> dict:
        """
        Build confidence funnel data for all supply orders for a
        product at a site within the planning horizon.

        Returns nested confidence intervals (P50/P80/P90/P95) for each
        order, plus on-time probability relative to pegged demand dates.
        """
        horizon_end = date.today() + timedelta(days=horizon_days)

        # Resolve product and site names
        product_name, site_name = self._resolve_names(
            config_id, product_id, site_id,
        )

        # Collect all supply orders
        orders = []

        # 1. Planned orders from supply_plan
        planned = self._get_planned_orders(
            config_id, product_id, site_id, horizon_end,
        )
        orders.extend(planned)

        # 2. Open inbound orders (POs)
        inbound = self._get_inbound_orders(
            config_id, product_id, site_id, horizon_end,
        )
        orders.extend(inbound)

        # 3. Open production orders (MOs)
        production = self._get_production_orders(
            config_id, product_id, site_id, horizon_end,
        )
        orders.extend(production)

        # Sort by planned receipt date
        orders.sort(key=lambda o: o["planned_receipt"] or "9999-12-31")

        # Compute on-time probability for each order
        for order in orders:
            order["on_time_probability"] = self._compute_on_time_probability(order)

        # Build summary
        summary = self._build_summary(orders)

        return {
            "product_id": product_id,
            "product_name": product_name,
            "site_id": str(site_id),
            "site_name": site_name,
            "orders": orders,
            "summary": summary,
        }

    # ------------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------------

    def _resolve_names(
        self, config_id: int, product_id: str, site_id: int,
    ) -> tuple:
        """Resolve display names for product and site."""
        row = self.db.execute(
            text("""
                SELECT p.product_name, s.site_name
                FROM product p, site s
                WHERE p.id = :pid AND s.id = :sid
            """),
            {"pid": product_id, "sid": site_id},
        ).first()

        if row:
            return row[0] or product_id, row[1] or str(site_id)
        return product_id, str(site_id)

    def _get_planned_orders(
        self,
        config_id: int,
        product_id: str,
        site_id: int,
        horizon_end: date,
    ) -> list:
        """Get planned orders from supply_plan table."""
        rows = self.db.execute(
            text("""
                SELECT
                    sp.id,
                    sp.plan_type,
                    sp.planned_order_quantity,
                    sp.planned_order_date,
                    sp.planned_receipt_date,
                    sp.supplier_id,
                    sp.lead_time_lower,
                    sp.lead_time_upper,
                    sp.lead_time_coverage,
                    sp.from_site_id,
                    tp.tpartner_name AS supplier_name,
                    fs.site_name AS from_site_name
                FROM supply_plan sp
                LEFT JOIN trading_partner tp ON tp.id = sp.supplier_id
                LEFT JOIN site fs ON fs.id = sp.from_site_id
                WHERE sp.config_id = :config_id
                  AND sp.product_id = :product_id
                  AND sp.site_id = :site_id
                  AND sp.planned_receipt_date IS NOT NULL
                  AND sp.planned_receipt_date <= :horizon_end
                  AND sp.planned_receipt_date >= CURRENT_DATE - INTERVAL '7 days'
                  AND sp.planned_order_quantity > 0
                ORDER BY sp.planned_receipt_date
            """),
            {
                "config_id": config_id,
                "product_id": product_id,
                "site_id": site_id,
                "horizon_end": horizon_end,
            },
        ).fetchall()

        orders = []
        for r in rows:
            order_id = f"SP-{r[0]}"
            plan_type = r[1] or "planned_order"
            quantity = r[2] or 0
            planned_order_date = r[3]
            planned_receipt = r[4]
            supplier_id = r[5]
            lt_lower = r[6]
            lt_upper = r[7]
            lt_coverage = r[8]
            supplier_name = r[10]
            from_site_name = r[11]

            source = supplier_name or from_site_name or supplier_id or ""

            # Compute lead time days from order date and receipt date
            lt_days = None
            if planned_order_date and planned_receipt:
                lt_days = (planned_receipt - planned_order_date).days

            # Build intervals
            intervals = self._compute_intervals(
                planned_receipt, lt_days, lt_lower, lt_upper,
            )

            # Look up pegged demand date
            target_date = self._get_pegged_demand_date(
                config_id, plan_type, str(r[0]), product_id, site_id,
            )

            orders.append({
                "order_id": order_id,
                "order_type": plan_type,
                "quantity": quantity,
                "source": source,
                "planned_receipt": planned_receipt.isoformat() if planned_receipt else None,
                "target_date": target_date,
                "intervals": intervals,
                "on_time_probability": 0.0,
                "critical_path": False,
                "has_conformal": lt_lower is not None and lt_upper is not None,
                "lead_time_coverage": lt_coverage,
            })

        return orders

    def _get_inbound_orders(
        self,
        config_id: int,
        product_id: str,
        site_id: int,
        horizon_end: date,
    ) -> list:
        """Get open inbound orders (POs/TOs)."""
        rows = self.db.execute(
            text("""
                SELECT
                    io.id,
                    io.order_type,
                    iol.ordered_qty,
                    io.order_date,
                    io.requested_delivery_date,
                    io.promised_delivery_date,
                    io.supplier_name,
                    io.supplier_id,
                    io.status
                FROM inbound_order io
                JOIN inbound_order_line iol ON iol.order_id = io.id
                WHERE io.config_id = :config_id
                  AND iol.product_id = :product_id
                  AND io.ship_to_site_id = :site_id
                  AND io.status NOT IN ('RECEIVED', 'CANCELLED')
                  AND COALESCE(io.promised_delivery_date, io.requested_delivery_date)
                      <= :horizon_end
                  AND COALESCE(io.promised_delivery_date, io.requested_delivery_date)
                      >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY COALESCE(io.promised_delivery_date, io.requested_delivery_date)
            """),
            {
                "config_id": config_id,
                "product_id": product_id,
                "site_id": site_id,
                "horizon_end": horizon_end,
            },
        ).fetchall()

        orders = []
        for r in rows:
            order_id = r[0]
            order_type = "po_request" if r[1] == "PURCHASE" else "to_request"
            quantity = r[2] or 0
            order_date = r[3]
            requested_date = r[4]
            promised_date = r[5]
            supplier_name = r[6] or r[7] or ""

            planned_receipt = promised_date or requested_date
            lt_days = None
            if order_date and planned_receipt:
                lt_days = (planned_receipt - order_date).days

            # For firm orders, use tighter intervals (no conformal)
            intervals = self._compute_intervals_firm(planned_receipt, lt_days)

            target_date = self._get_pegged_demand_date(
                config_id, "purchase_order", order_id, product_id, site_id,
            )

            orders.append({
                "order_id": order_id,
                "order_type": order_type,
                "quantity": quantity,
                "source": supplier_name,
                "planned_receipt": planned_receipt.isoformat() if planned_receipt else None,
                "target_date": target_date,
                "intervals": intervals,
                "on_time_probability": 0.0,
                "critical_path": False,
                "has_conformal": False,
                "lead_time_coverage": None,
            })

        return orders

    def _get_production_orders(
        self,
        config_id: int,
        product_id: str,
        site_id: int,
        horizon_end: date,
    ) -> list:
        """Get open production orders (MOs)."""
        rows = self.db.execute(
            text("""
                SELECT
                    po.id,
                    po.order_number,
                    po.planned_quantity,
                    po.planned_start_date,
                    po.planned_completion_date,
                    po.status,
                    po.lead_time_planned,
                    s.site_name
                FROM production_orders po
                JOIN site s ON s.id = po.site_id
                WHERE po.config_id = :config_id
                  AND po.item_id = :product_id
                  AND po.site_id = :site_id
                  AND po.status NOT IN ('COMPLETED', 'CLOSED', 'CANCELLED')
                  AND po.planned_completion_date <= :horizon_end
                  AND po.planned_completion_date >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY po.planned_completion_date
            """),
            {
                "config_id": config_id,
                "product_id": product_id,
                "site_id": site_id,
                "horizon_end": horizon_end,
            },
        ).fetchall()

        orders = []
        for r in rows:
            order_id = r[1] or f"MO-{r[0]}"
            quantity = r[2] or 0
            planned_start = r[3]
            planned_completion = r[4]
            lt_planned = r[6]
            site_name = r[7] or ""

            planned_receipt = planned_completion.date() if planned_completion else None
            lt_days = lt_planned

            # MOs use modest uncertainty based on planned lead time
            intervals = self._compute_intervals_firm(planned_receipt, lt_days)

            target_date = self._get_pegged_demand_date(
                config_id, "manufacturing_order", order_id, product_id, site_id,
            )

            orders.append({
                "order_id": order_id,
                "order_type": "mo_request",
                "quantity": quantity,
                "source": site_name,
                "planned_receipt": planned_receipt.isoformat() if planned_receipt else None,
                "target_date": target_date,
                "intervals": intervals,
                "on_time_probability": 0.0,
                "critical_path": False,
                "has_conformal": False,
                "lead_time_coverage": None,
            })

        return orders

    # ------------------------------------------------------------------
    # Interval computation
    # ------------------------------------------------------------------

    def _compute_intervals(
        self,
        planned_receipt: Optional[date],
        lt_days: Optional[int],
        lt_lower: Optional[float],
        lt_upper: Optional[float],
    ) -> dict:
        """
        Compute nested confidence intervals from conformal bounds.

        If conformal intervals exist:
          P90 = [lt_lower, lt_upper] (the full conformal range)
          P50 = planned_receipt +/- 0 (the point estimate)
          P80 = expand by 60% of the conformal range on each side
          P95 = expand by 120% of conformal range
        """
        if not planned_receipt:
            return {"p50": [None, None], "p80": [None, None], "p90": [None, None], "p95": [None, None]}

        receipt = planned_receipt
        if isinstance(receipt, str):
            receipt = date.fromisoformat(receipt)

        if lt_lower is not None and lt_upper is not None and lt_days is not None:
            # Conformal range in days
            # lt_lower/lt_upper are the earliest/latest arrival offsets
            # Convert to date offsets from planned_receipt
            early_days = lt_days - lt_lower  # Days earlier than planned
            late_days = lt_upper - lt_days   # Days later than planned
            conf_range = early_days + late_days

            if conf_range > 0:
                # P50: tight around planned receipt (+/- 0 days effectively)
                p50_early = 0
                p50_late = 0

                # P80: 60% of conformal range on each side
                p80_early = early_days * 0.6
                p80_late = late_days * 0.6

                # P90: full conformal range
                p90_early = early_days
                p90_late = late_days

                # P95: 120% of conformal range
                p95_early = early_days * 1.2
                p95_late = late_days * 1.2

                return {
                    "p50": [
                        (receipt - timedelta(days=p50_early)).isoformat(),
                        (receipt + timedelta(days=p50_late)).isoformat(),
                    ],
                    "p80": [
                        (receipt - timedelta(days=p80_early)).isoformat(),
                        (receipt + timedelta(days=p80_late)).isoformat(),
                    ],
                    "p90": [
                        (receipt - timedelta(days=p90_early)).isoformat(),
                        (receipt + timedelta(days=p90_late)).isoformat(),
                    ],
                    "p95": [
                        (receipt - timedelta(days=p95_early)).isoformat(),
                        (receipt + timedelta(days=p95_late)).isoformat(),
                    ],
                }

        # Fallback: no conformal data, use heuristic based on lead time
        return self._compute_intervals_firm(receipt, lt_days)

    def _compute_intervals_firm(
        self,
        planned_receipt: Optional[date],
        lt_days: Optional[int],
    ) -> dict:
        """
        Compute intervals for firm orders without conformal data.
        Uses a heuristic: uncertainty proportional to lead time.
        """
        if not planned_receipt:
            return {"p50": [None, None], "p80": [None, None], "p90": [None, None], "p95": [None, None]}

        receipt = planned_receipt
        if isinstance(receipt, str):
            receipt = date.fromisoformat(receipt)

        # Heuristic: +/- 10% of lead time per confidence level spread
        lt = max(lt_days or 7, 1)
        base_spread = max(lt * 0.1, 1)

        p50_spread = 0
        p80_spread = base_spread * 1.0
        p90_spread = base_spread * 1.5
        p95_spread = base_spread * 2.0

        return {
            "p50": [
                (receipt - timedelta(days=p50_spread)).isoformat(),
                (receipt + timedelta(days=p50_spread)).isoformat(),
            ],
            "p80": [
                (receipt - timedelta(days=p80_spread)).isoformat(),
                (receipt + timedelta(days=p80_spread)).isoformat(),
            ],
            "p90": [
                (receipt - timedelta(days=p90_spread)).isoformat(),
                (receipt + timedelta(days=p90_spread)).isoformat(),
            ],
            "p95": [
                (receipt - timedelta(days=p95_spread)).isoformat(),
                (receipt + timedelta(days=p95_spread)).isoformat(),
            ],
        }

    # ------------------------------------------------------------------
    # Pegging & on-time probability
    # ------------------------------------------------------------------

    def _get_pegged_demand_date(
        self,
        config_id: int,
        supply_type: str,
        supply_id: str,
        product_id: str,
        site_id: int,
    ) -> Optional[str]:
        """Look up the demand date this supply is pegged to."""
        row = self.db.execute(
            text("""
                SELECT sdp.pegging_date
                FROM supply_demand_pegging sdp
                WHERE sdp.config_id = :config_id
                  AND sdp.supply_id = :supply_id
                  AND sdp.product_id = :product_id
                  AND sdp.site_id = :site_id
                  AND sdp.is_active = true
                ORDER BY sdp.pegging_date
                LIMIT 1
            """),
            {
                "config_id": config_id,
                "supply_id": supply_id,
                "product_id": product_id,
                "site_id": site_id,
            },
        ).first()

        if row and row[0]:
            return row[0].isoformat()
        return None

    def _compute_on_time_probability(self, order: dict) -> float:
        """
        Estimate the probability that the order arrives on or before
        the target date, based on the confidence intervals.

        Uses linear interpolation across the interval levels.
        """
        target = order.get("target_date")
        planned = order.get("planned_receipt")
        intervals = order.get("intervals", {})

        if not target or not planned:
            # No target date — assume moderate probability
            return 0.75

        target_d = date.fromisoformat(target)
        planned_d = date.fromisoformat(planned)

        # If planned receipt is well before target, high probability
        if planned_d <= target_d:
            # Check how much of the uncertainty could push past target
            p95_upper = intervals.get("p95", [None, None])[1]
            if p95_upper:
                p95_d = date.fromisoformat(p95_upper)
                if p95_d <= target_d:
                    return 0.98  # Even P95 upper bound is before target

                p90_upper = intervals.get("p90", [None, None])[1]
                p80_upper = intervals.get("p80", [None, None])[1]

                if p90_upper and date.fromisoformat(p90_upper) <= target_d:
                    return 0.92
                if p80_upper and date.fromisoformat(p80_upper) <= target_d:
                    return 0.82
                # P50 is on time but wider intervals cross target
                return 0.65
            return 0.90
        else:
            # Planned receipt is after target — lower probability
            delay_days = (planned_d - target_d).days
            p50_lower = intervals.get("p50", [None, None])[0]
            if p50_lower:
                p50_d = date.fromisoformat(p50_lower)
                if p50_d <= target_d:
                    return 0.45  # Lower bound of P50 reaches target
            # Significantly late
            return max(0.1, 0.5 - delay_days * 0.05)

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _build_summary(self, orders: list) -> dict:
        """Build summary statistics for the funnel."""
        if not orders:
            return {
                "total_orders": 0,
                "avg_on_time_probability": 0.0,
                "highest_risk_order": None,
                "critical_path_orders": [],
            }

        total = len(orders)
        avg_otp = sum(o["on_time_probability"] for o in orders) / total

        # Mark critical path: orders with on_time_probability < 0.7
        critical_threshold = 0.7
        for o in orders:
            o["critical_path"] = o["on_time_probability"] < critical_threshold

        critical_orders = [o["order_id"] for o in orders if o["critical_path"]]

        # Highest risk = lowest on_time_probability
        highest_risk = min(orders, key=lambda o: o["on_time_probability"])

        return {
            "total_orders": total,
            "avg_on_time_probability": round(avg_otp, 2),
            "highest_risk_order": highest_risk["order_id"],
            "critical_path_orders": critical_orders,
        }
