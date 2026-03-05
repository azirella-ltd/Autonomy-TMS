"""
Demand Processor - Step 1 of SC Planning Process

Processes forecasts and actual orders to compute net demand.

Logic:
1. Load forecasts for planning horizon
2. Load actual customer orders
3. Consume forecast with actuals (deduct actual orders from forecast)
4. Add reservations/allocations
5. Output: Net demand by (product, site, date)

Reference: https://docs.[removed]
"""

from datetime import date, timedelta
from typing import Dict, Tuple, Optional
from collections import defaultdict
import logging
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.sc_entities import (
    Forecast,
    OutboundOrderLine,
    Reservation
)
from .planning_types import DemandEstimate, DemandEstimateDict

logger = logging.getLogger(__name__)


class DemandProcessor:
    """
    Step 1: Demand Processing

    Combines forecasts, actual orders, and reservations to calculate net demand.
    """

    def __init__(self, config_id: int, tenant_id: int):
        self.config_id = config_id
        self.tenant_id = tenant_id

    async def process_demand(
        self,
        start_date: date,
        planning_horizon: int
    ) -> Dict[Tuple[str, str, date], float]:
        """
        Process forecasts and actual orders to compute net demand

        Args:
            start_date: Planning start date
            planning_horizon: Number of days to plan ahead

        Returns:
            Dict mapping (product_id, site_id, date) → net_demand_quantity
        """
        net_demand = {}
        end_date = start_date + timedelta(days=planning_horizon)

        print(f"  Loading forecasts from {start_date} to {end_date}...")
        forecasts = await self.load_forecasts(start_date, planning_horizon)
        print(f"  ✓ Loaded {len(forecasts)} forecast entries")

        print(f"  Loading actual orders...")
        actual_orders = await self.load_actual_orders(start_date, planning_horizon)
        print(f"  ✓ Loaded {len(actual_orders)} actual order entries")

        print(f"  Loading reservations...")
        reservations = await self.load_reservations(start_date, planning_horizon)
        print(f"  ✓ Loaded {len(reservations)} reservation entries")

        print(f"  Computing net demand...")

        # Consume forecast with actuals
        all_keys = set(forecasts.keys()) | set(actual_orders.keys()) | set(reservations.keys())

        for key in all_keys:
            product_id, site_id, demand_date = key

            forecast_qty = forecasts.get(key, 0)
            actual_qty = actual_orders.get(key, 0)
            reserved_qty = reservations.get(key, 0)

            # Net demand calculation:
            # If actuals exceed forecast, use actuals
            # If forecast exceeds actuals, use remaining forecast + actuals
            # Add reservations on top
            if actual_qty > forecast_qty:
                # Actuals exceeded forecast - use actuals
                net_demand[key] = actual_qty + reserved_qty
            else:
                # Forecast covers actuals - use forecast
                net_demand[key] = forecast_qty + reserved_qty

        print(f"  ✓ Computed net demand for {len(net_demand)} entries")

        return net_demand

    async def load_forecasts(
        self, start_date: date, horizon: int
    ) -> Dict[Tuple[str, str, date], float]:
        """
        Load forecasts from forecast table

        Args:
            start_date: Planning start date
            horizon: Number of days ahead

        Returns:
            Dict mapping (product_id, site_id, date) → forecast_quantity
        """
        async with SessionLocal() as db:
            end_date = start_date + timedelta(days=horizon)

            result = await db.execute(
                select(Forecast).filter(
                    Forecast.customer_id == self.tenant_id,
                    Forecast.config_id == self.config_id,
                    Forecast.forecast_date >= start_date,
                    Forecast.forecast_date < end_date,
                    Forecast.is_active == 'true'
                )
            )
            forecasts = result.scalars().all()

            forecast_dict = {}
            for fcst in forecasts:
                # Use user override if available, else forecast quantity
                qty = fcst.user_override_quantity or fcst.forecast_quantity or fcst.forecast_p50 or 0
                key = (fcst.product_id, fcst.site_id, fcst.forecast_date)
                forecast_dict[key] = qty

            return forecast_dict

    async def load_actual_orders(
        self, start_date: date, horizon: int
    ) -> Dict[Tuple[str, str, date], float]:
        """
        Load actual customer orders from outbound_order_line

        Args:
            start_date: Planning start date
            horizon: Number of days ahead

        Returns:
            Dict mapping (product_id, site_id, date) → ordered_quantity
        """
        async with SessionLocal() as db:
            end_date = start_date + timedelta(days=horizon)

            result = await db.execute(
                select(OutboundOrderLine).filter(
                    OutboundOrderLine.customer_id == self.tenant_id,
                    OutboundOrderLine.config_id == self.config_id,
                    OutboundOrderLine.requested_delivery_date >= start_date,
                    OutboundOrderLine.requested_delivery_date < end_date
                )
            )
            orders = result.scalars().all()

            order_dict = defaultdict(float)
            for order in orders:
                key = (order.product_id, order.site_id, order.requested_delivery_date)
                order_dict[key] += order.ordered_quantity

            return dict(order_dict)

    async def load_reservations(
        self, start_date: date, horizon: int
    ) -> Dict[Tuple[str, str, date], float]:
        """
        Load inventory reservations

        Args:
            start_date: Planning start date
            horizon: Number of days ahead

        Returns:
            Dict mapping (product_id, site_id, date) → reserved_quantity
        """
        async with SessionLocal() as db:
            end_date = start_date + timedelta(days=horizon)

            result = await db.execute(
                select(Reservation).filter(
                    Reservation.customer_id == self.tenant_id,
                    Reservation.config_id == self.config_id,
                    Reservation.reservation_date >= start_date,
                    Reservation.reservation_date < end_date
                )
            )
            reservations = result.scalars().all()

            reservation_dict = defaultdict(float)
            for res in reservations:
                key = (res.product_id, res.site_id, res.reservation_date)
                reservation_dict[key] += res.reserved_quantity

            return dict(reservation_dict)

    async def aggregate_demand_by_period(
        self,
        net_demand: Dict[Tuple[str, str, date], float],
        period_days: int = 7
    ) -> Dict[Tuple[str, str, int], float]:
        """
        Aggregate daily demand into time buckets (e.g., weekly)

        Args:
            net_demand: Daily net demand
            period_days: Days per period (default: 7 for weekly)

        Returns:
            Dict mapping (product_id, site_id, period_number) → total_demand
        """
        period_demand = defaultdict(float)

        for (product_id, site_id, demand_date), qty in net_demand.items():
            # Calculate period number (0-indexed)
            days_from_start = (demand_date - min(d for _, _, d in net_demand.keys())).days
            period_number = days_from_start // period_days

            key = (product_id, site_id, period_number)
            period_demand[key] += qty

        return dict(period_demand)

    async def load_forecasts_with_intervals(
        self, start_date: date, horizon: int
    ) -> DemandEstimateDict:
        """
        Load forecasts with conformal prediction intervals.

        Priority:
        1. Conformal suite predictor (calibrated, distribution-free guarantee)
        2. DB-stored P10/P90 percentiles (80% coverage)
        3. Interval-free DemandEstimate (point only)
        """
        # Lazy import to avoid circular dependency
        from ..conformal_prediction.suite import get_conformal_suite

        suite = get_conformal_suite()

        async with SessionLocal() as db:
            end_date = start_date + timedelta(days=horizon)

            result = await db.execute(
                select(Forecast).filter(
                    Forecast.customer_id == self.tenant_id,
                    Forecast.config_id == self.config_id,
                    Forecast.forecast_date >= start_date,
                    Forecast.forecast_date < end_date,
                    Forecast.is_active == 'true'
                )
            )
            forecasts = result.scalars().all()

            forecast_dict: DemandEstimateDict = {}
            for fcst in forecasts:
                qty = fcst.user_override_quantity or fcst.forecast_quantity or fcst.forecast_p50 or 0
                key = (fcst.product_id, fcst.site_id, fcst.forecast_date)

                # Priority 1: Conformal suite predictor
                try:
                    site_id_int = int(fcst.site_id) if isinstance(fcst.site_id, str) else fcst.site_id
                    if suite.has_demand_predictor(fcst.product_id, site_id_int):
                        interval = suite.predict_demand(
                            fcst.product_id, site_id_int, float(qty)
                        )
                        forecast_dict[key] = DemandEstimate(
                            point=qty,
                            lower=max(0, interval.lower),
                            upper=interval.upper,
                            coverage=interval.coverage_target,
                            method=interval.method,
                            source="forecast",
                        )
                        continue
                except Exception as e:
                    logger.debug(f"Conformal predictor failed for {fcst.product_id}/{fcst.site_id}: {e}")

                # Priority 2: DB-stored percentiles
                if fcst.forecast_p10 is not None and fcst.forecast_p90 is not None:
                    forecast_dict[key] = DemandEstimate(
                        point=qty,
                        lower=float(fcst.forecast_p10),
                        upper=float(fcst.forecast_p90),
                        coverage=0.80,  # P10-P90 = 80% coverage by definition
                        method="stored_percentiles",
                        source="forecast",
                    )
                    continue

                # Priority 3: Point estimate only
                forecast_dict[key] = DemandEstimate(point=qty, source="forecast")

            return forecast_dict

    async def process_demand_with_intervals(
        self,
        start_date: date,
        planning_horizon: int
    ) -> DemandEstimateDict:
        """
        Process demand with conformal prediction intervals.

        Same logic as process_demand() but returns DemandEstimate objects
        that carry optional conformal intervals when a calibrated predictor
        exists for the product-site.

        Falls back to interval-free DemandEstimate when no predictor is available.
        """
        end_date = start_date + timedelta(days=planning_horizon)

        logger.info(f"Loading forecasts with intervals from {start_date} to {end_date}...")
        forecasts = await self.load_forecasts_with_intervals(start_date, planning_horizon)
        logger.info(f"Loaded {len(forecasts)} forecast entries "
                     f"({sum(1 for f in forecasts.values() if f.has_interval)} with intervals)")

        actual_orders = await self.load_actual_orders(start_date, planning_horizon)
        reservations = await self.load_reservations(start_date, planning_horizon)

        net_demand: DemandEstimateDict = {}

        # Combine all keys
        all_keys = set(forecasts.keys()) | set(actual_orders.keys()) | set(reservations.keys())

        for key in all_keys:
            forecast_est = forecasts.get(key)
            actual_qty = actual_orders.get(key, 0)
            reserved_qty = reservations.get(key, 0)

            forecast_point = forecast_est.point if forecast_est else 0

            if actual_qty > forecast_point:
                # Actuals exceeded forecast — use actuals (no interval, ground truth)
                net_demand[key] = DemandEstimate(
                    point=actual_qty + reserved_qty,
                    source="actual",
                )
            elif forecast_est and forecast_est.has_interval:
                # Forecast covers actuals — propagate intervals + reservation
                net_demand[key] = DemandEstimate(
                    point=forecast_point + reserved_qty,
                    lower=forecast_est.lower + reserved_qty,
                    upper=forecast_est.upper + reserved_qty,
                    coverage=forecast_est.coverage,
                    method=forecast_est.method,
                    source="net",
                )
            else:
                # No interval — point estimate only
                net_demand[key] = DemandEstimate(
                    point=forecast_point + reserved_qty,
                    source="net",
                )

        logger.info(f"Computed net demand with intervals for {len(net_demand)} entries "
                     f"({sum(1 for d in net_demand.values() if d.has_interval)} with intervals)")

        return net_demand
