"""Point-in-time state reconstruction from historical tables.

Given a decision timestamp T, these helpers return the state of the supply
chain as it was at T - 1, i.e., the state the ERP was looking at when it
made the decision we are about to label.

Used by per-TRM extractors to attach a consistent `state_features` payload
to every historical sample.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class InvState:
    on_hand: float
    in_transit: float
    allocated: float
    safety_stock: float
    as_of: Optional[date]


@dataclass
class PolicyState:
    ss_quantity: float
    reorder_point: float
    order_up_to_level: float
    service_level: Optional[float]


@dataclass
class DemandStats:
    mean_weekly: float
    std_weekly: float
    cv: float
    observations: int


class StateReconstructor:
    """Point-in-time queries for historical state reconstruction."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def inventory_at(
        self, config_id: int, product_id: str, site_id, at: date,
    ) -> InvState:
        """Most recent inv_level snapshot on or before `at` for this (p,s)."""
        r = await self.db.execute(
            sql_text("""
                SELECT on_hand_qty, in_transit_qty, allocated_qty, safety_stock_qty,
                       inventory_date
                FROM inv_level
                WHERE config_id = :cid
                  AND product_id = :pid
                  AND site_id = :sid
                  AND inventory_date <= :at
                ORDER BY inventory_date DESC NULLS LAST
                LIMIT 1
            """),
            {"cid": config_id, "pid": product_id, "sid": site_id, "at": at},
        )
        row = r.fetchone()
        if row is None:
            return InvState(0.0, 0.0, 0.0, 0.0, None)
        return InvState(
            on_hand=float(row.on_hand_qty or 0),
            in_transit=float(row.in_transit_qty or 0),
            allocated=float(row.allocated_qty or 0),
            safety_stock=float(row.safety_stock_qty or 0),
            as_of=row.inventory_date,
        )

    async def policy_at(
        self, config_id: int, product_id: str, site_id, at: date,
    ) -> PolicyState:
        """inv_policy row in effect at `at`."""
        r = await self.db.execute(
            sql_text("""
                SELECT ss_quantity, reorder_point, order_up_to_level, service_level
                FROM inv_policy
                WHERE config_id = :cid
                  AND product_id = :pid
                  AND site_id = :sid
                  AND (eff_start_date IS NULL OR eff_start_date <= :at)
                  AND (eff_end_date   IS NULL OR eff_end_date   >  :at)
                ORDER BY eff_start_date DESC NULLS LAST
                LIMIT 1
            """),
            {"cid": config_id, "pid": product_id, "sid": site_id, "at": at},
        )
        row = r.fetchone()
        if row is None:
            return PolicyState(0.0, 0.0, 0.0, None)
        return PolicyState(
            ss_quantity=float(row.ss_quantity or 0),
            reorder_point=float(row.reorder_point or 0),
            order_up_to_level=float(row.order_up_to_level or 0),
            service_level=float(row.service_level) if row.service_level is not None else None,
        )

    async def demand_stats_at(
        self,
        config_id: int,
        product_id: str,
        site_id,
        at: date,
        lookback_weeks: int = 26,
    ) -> DemandStats:
        """Aggregated demand statistics over the N weeks prior to `at`."""
        from_date = at - timedelta(weeks=lookback_weeks)
        r = await self.db.execute(
            sql_text("""
                SELECT
                    COALESCE(AVG(weekly_qty), 0) AS mean_w,
                    COALESCE(STDDEV_POP(weekly_qty), 0) AS std_w,
                    COUNT(*) AS n
                FROM (
                    SELECT DATE_TRUNC('week', order_date) AS wk,
                           SUM(COALESCE(shipped_quantity, ordered_quantity, 0)) AS weekly_qty
                    FROM outbound_order_line
                    WHERE config_id = :cid
                      AND product_id = :pid
                      AND site_id = :sid
                      AND order_date >= :from_date
                      AND order_date <  :at
                    GROUP BY 1
                ) s
            """),
            {"cid": config_id, "pid": product_id, "sid": site_id,
             "from_date": from_date, "at": at},
        )
        row = r.fetchone()
        mean_w = float(row.mean_w or 0)
        std_w = float(row.std_w or 0)
        cv = (std_w / mean_w) if mean_w > 0 else 0.0
        return DemandStats(
            mean_weekly=mean_w,
            std_weekly=std_w,
            cv=cv,
            observations=int(row.n or 0),
        )

    async def forecast_p50_at(
        self, config_id: int, product_id: str, site_id, at: date,
    ) -> Optional[float]:
        """Most recent forecast_p50 available on or before `at`."""
        r = await self.db.execute(
            sql_text("""
                SELECT COALESCE(forecast_p50, forecast_quantity) AS p50
                FROM forecast
                WHERE config_id = :cid
                  AND product_id = :pid
                  AND site_id = :sid
                  AND forecast_date <= :at
                ORDER BY forecast_date DESC
                LIMIT 1
            """),
            {"cid": config_id, "pid": product_id, "sid": site_id, "at": at},
        )
        row = r.fetchone()
        return float(row.p50) if row and row.p50 is not None else None
