"""
Conformal Prediction Orchestrator

Thin wiring layer that connects:
- SupplyChainConformalSuite (in-memory predictions)
- CalibrationFeedbackService (async DB operations)
- PowellBeliefState / PowellCalibrationLog (persistence)
- APScheduler (periodic recalibration)
- Forecast model (forecast_error field)

Six gaps filled:
1. Forecast load hook - apply/trigger calibration on forecast import
2. Actuals observation hook - match to forecast, compute error, feed calibration
3. Drift monitoring - emergency recalibration when coverage drifts >5%
4. Scheduled recalibration - daily APScheduler job
5. Planning staleness check - verify freshness before using intervals
6. Suite <-> DB persistence - persist on calibrate, hydrate on startup

Multi-entity observation hooks:
- Demand: on_actual_demand_observed() - from customer order creation
- Lead Time: on_lead_time_observed() - from TO/PO receipt
- Yield: on_yield_observed() - from manufacturing execution (future)
- Price: on_price_observed() - from PO receipt vs catalog price
- Service Level: on_service_level_observed() - from order fulfillment
"""

import logging
import math
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.services.conformal_prediction.suite import (
    SupplyChainConformalSuite,
    get_conformal_suite,
)
from app.models.powell import (
    PowellBeliefState,
    PowellCalibrationLog,
    EntityType,
    ConformalMethod,
)
from app.models.sc_entities import Forecast

logger = logging.getLogger(__name__)

# Configuration
STALENESS_WARNING_HOURS = 168       # 7 days
STALENESS_ERROR_HOURS = 336         # 14 days
DRIFT_COVERAGE_THRESHOLD = 0.05    # 5% deviation triggers emergency recal
MIN_OBSERVATIONS_FOR_CALIBRATION = 10
DAILY_RECALIBRATION_HOUR = 1
DAILY_RECALIBRATION_MINUTE = 30


class ConformalOrchestrator:
    """
    Singleton orchestrator wiring conformal prediction components
    into an automatic feedback loop.
    """

    _instance: Optional["ConformalOrchestrator"] = None

    def __init__(self):
        self.suite: SupplyChainConformalSuite = get_conformal_suite()
        self._hydrated = False

    @classmethod
    def get_instance(cls) -> "ConformalOrchestrator":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # =======================================================================
    # GAP 6: Suite <-> DB Persistence
    # =======================================================================

    async def hydrate_from_db(self, db: AsyncSession) -> int:
        """
        Startup: Load persisted calibration from PowellBeliefState
        into the in-memory SupplyChainConformalSuite.

        Returns number of predictors hydrated.
        """
        result = await db.execute(
            select(PowellBeliefState).where(
                and_(
                    PowellBeliefState.recent_residuals.isnot(None),
                    PowellBeliefState.observation_count >= MIN_OBSERVATIONS_FOR_CALIBRATION,
                )
            )
        )
        states = result.scalars().all()
        hydrated = 0

        for state in states:
            residuals = state.recent_residuals or []
            if len(residuals) < MIN_OBSERVATIONS_FOR_CALIBRATION:
                continue

            if state.point_estimate is None:
                continue

            # Reconstruct forecast/actual pairs from residuals.
            # residuals[i] = predicted - actual, so actual = predicted - residual.
            # We use point_estimate as the representative forecast value.
            forecast_val = state.point_estimate
            forecasts = [forecast_val] * len(residuals)
            actuals = [forecast_val - r for r in residuals]

            try:
                if state.entity_type == EntityType.DEMAND:
                    parts = state.entity_id.split(":")
                    if len(parts) >= 2:
                        prod_id, site_id_str = parts[0], parts[1]
                        self.suite.calibrate_demand(
                            product_id=prod_id,
                            site_id=int(site_id_str),
                            historical_forecasts=forecasts,
                            historical_actuals=actuals,
                        )
                        hydrated += 1

                elif state.entity_type == EntityType.LEAD_TIME:
                    self.suite.calibrate_lead_time(
                        supplier_id=state.entity_id,
                        predicted_lead_times=forecasts,
                        actual_lead_times=actuals,
                    )
                    hydrated += 1

                elif state.entity_type == EntityType.YIELD:
                    parts = state.entity_id.split(":")
                    prod_id = parts[0]
                    process_id = parts[1] if len(parts) > 1 else None
                    self.suite.calibrate_yield(
                        product_id=prod_id,
                        process_id=process_id,
                        expected_yields=forecasts,
                        actual_yields=actuals,
                    )
                    hydrated += 1

                elif state.entity_type == EntityType.PRICE:
                    self.suite.calibrate_price(
                        material_id=state.entity_id,
                        predicted_prices=forecasts,
                        actual_prices=actuals,
                    )
                    hydrated += 1

            except Exception as e:
                logger.warning(
                    f"Failed to hydrate predictor {state.entity_type}:{state.entity_id}: {e}"
                )

        self._hydrated = True
        logger.info(f"Hydrated {hydrated} conformal predictors from DB")
        return hydrated

    async def persist_calibration(
        self,
        db: AsyncSession,
        entity_type: EntityType,
        entity_id: str,
        tenant_id: int,
        point_estimate: float,
        lower: float,
        upper: float,
        coverage: float,
        residuals: List[float],
        coverage_history: List[int],
        method: ConformalMethod = ConformalMethod.ADAPTIVE,
        distribution_fit_metadata: Optional[Dict] = None,
    ) -> PowellBeliefState:
        """Upsert calibration to PowellBeliefState."""
        result = await db.execute(
            select(PowellBeliefState).where(
                and_(
                    PowellBeliefState.tenant_id == tenant_id,
                    PowellBeliefState.entity_type == entity_type,
                    PowellBeliefState.entity_id == entity_id,
                )
            )
        )
        state = result.scalar_one_or_none()

        if state is None:
            state = PowellBeliefState(
                tenant_id=tenant_id,
                entity_type=entity_type,
                entity_id=entity_id,
            )
            db.add(state)

        state.point_estimate = point_estimate
        state.conformal_lower = lower
        state.conformal_upper = upper
        state.conformal_coverage = coverage
        state.conformal_method = method
        state.recent_residuals = residuals[-100:]
        state.coverage_history = coverage_history[-100:]
        state.observation_count = len(residuals)
        state.last_recalibration = datetime.utcnow()

        # Fit distribution to residuals (Kravanja 2026) for diagnostic enrichment
        # and hybrid sl_conformal_fitted policy support
        if distribution_fit_metadata is not None:
            state.distribution_fit = distribution_fit_metadata
        elif len(residuals) >= 10:
            variable_hint = None
            if entity_type == EntityType.DEMAND:
                variable_hint = "demand"
            elif entity_type == EntityType.LEAD_TIME:
                variable_hint = "lead_time"
            elif entity_type == EntityType.YIELD:
                variable_hint = "yield"
            state.distribution_fit = SupplyChainConformalSuite.fit_residual_distribution(
                residuals, variable_type=variable_hint
            )

        # Compute empirical coverage
        if coverage_history:
            window = coverage_history[-100:]
            state.empirical_coverage = sum(window) / len(window)
            state.drift_detected = (
                abs(state.empirical_coverage - coverage) > DRIFT_COVERAGE_THRESHOLD
            )
            state.drift_score = state.empirical_coverage - coverage
        state.interval_width_mean = upper - lower

        await db.flush()
        return state

    # =======================================================================
    # GAP 1: Forecast Load Hook
    # =======================================================================

    async def on_forecasts_loaded(
        self,
        db: AsyncSession,
        product_site_pairs: List[Tuple[str, int]],
        tenant_id: int,
    ) -> Dict:
        """
        Hook called after forecasts are loaded (any of the 4 paths).

        For each product-site pair:
        1. Check if a calibrated predictor already exists
        2. If no, check if historical forecast_error data exists
        3. If enough error data, trigger initial calibration
        """
        applied = []
        triggered_calibration = []
        needs_data = []

        for product_id, site_id in product_site_pairs:
            if self.suite.has_demand_predictor(product_id, site_id):
                applied.append(f"{product_id}:{site_id}")
                continue

            # Check for historical error data to bootstrap calibration
            error_query = (
                select(Forecast)
                .where(
                    and_(
                        Forecast.product_id == product_id,
                        Forecast.site_id == site_id,
                        Forecast.forecast_error.isnot(None),
                    )
                )
                .order_by(Forecast.forecast_date)
            )
            result = await db.execute(error_query)
            error_forecasts = result.scalars().all()

            if len(error_forecasts) >= MIN_OBSERVATIONS_FOR_CALIBRATION:
                forecast_values = []
                actual_values = []
                for f in error_forecasts:
                    fv = f.forecast_p50 or f.forecast_quantity
                    if fv is not None and f.forecast_error is not None:
                        forecast_values.append(float(fv))
                        actual_values.append(float(fv) + float(f.forecast_error))

                if len(forecast_values) >= MIN_OBSERVATIONS_FOR_CALIBRATION:
                    self.suite.calibrate_demand(
                        product_id=product_id,
                        site_id=site_id,
                        historical_forecasts=forecast_values,
                        historical_actuals=actual_values,
                    )

                    # Persist to DB
                    residuals = [fv - av for fv, av in zip(forecast_values, actual_values)]
                    interval = self.suite.predict_demand(
                        product_id, site_id, forecast_values[-1]
                    )
                    cov_hist = [
                        1 if interval.lower <= av <= interval.upper else 0
                        for av in actual_values
                    ]
                    entity_id = f"{product_id}:{site_id}"
                    await self.persist_calibration(
                        db, EntityType.DEMAND, entity_id, tenant_id,
                        point_estimate=forecast_values[-1],
                        lower=interval.lower,
                        upper=interval.upper,
                        coverage=self.suite.demand_coverage,
                        residuals=residuals,
                        coverage_history=cov_hist,
                    )
                    triggered_calibration.append(entity_id)
                    continue

            needs_data.append(f"{product_id}:{site_id}")

        logger.info(
            f"Forecast load hook: {len(applied)} already calibrated, "
            f"{len(triggered_calibration)} newly calibrated, "
            f"{len(needs_data)} need more data"
        )

        return {
            "already_calibrated": len(applied),
            "triggered_calibration": len(triggered_calibration),
            "needs_data": len(needs_data),
            "details": {
                "applied": applied,
                "triggered": triggered_calibration,
                "pending": needs_data,
            },
        }

    # =======================================================================
    # GAP 2: Actuals Observation Hook
    # =======================================================================

    async def on_actual_demand_observed(
        self,
        db: AsyncSession,
        product_id: str,
        site_id: int,
        ordered_quantity: float,
        order_date: date,
        tenant_id: int,
    ) -> Optional[Dict]:
        """
        Hook called when an OutboundOrderLine is created.

        Steps:
        1. Find matching Forecast for this product/site/date
        2. Compute residual = actual - forecast
        3. Update Forecast.forecast_error field
        4. Log to PowellCalibrationLog
        5. Check if drift triggers emergency recalibration
        """
        forecast = await self._match_forecast(db, product_id, site_id, order_date)
        if forecast is None:
            logger.debug(
                f"No matching forecast for {product_id}@{site_id} on {order_date}"
            )
            return None

        forecast_value = forecast.forecast_p50 or forecast.forecast_quantity
        if forecast_value is None:
            return None

        forecast_value = float(forecast_value)
        actual_value = float(ordered_quantity)

        # Compute and store forecast_error
        error = actual_value - forecast_value
        forecast.forecast_error = error
        await db.flush()

        # Feed into calibration loop
        emergency_recal = await self._record_and_check_calibration(
            db, EntityType.DEMAND, f"{product_id}:{site_id}",
            tenant_id, forecast_value, actual_value,
        )

        return {
            "product_id": product_id,
            "site_id": site_id,
            "forecast_value": forecast_value,
            "actual_value": actual_value,
            "error": error,
            "emergency_recalibration": emergency_recal,
        }

    async def _match_forecast(
        self,
        db: AsyncSession,
        product_id: str,
        site_id: int,
        observation_date: date,
    ) -> Optional[Forecast]:
        """Find best matching active forecast: exact date first, then ±7 day window."""
        # Exact match
        result = await db.execute(
            select(Forecast)
            .where(
                and_(
                    Forecast.product_id == product_id,
                    Forecast.site_id == site_id,
                    Forecast.forecast_date == observation_date,
                    Forecast.is_active == "Y",
                )
            )
            .order_by(Forecast.created_dttm.desc())
            .limit(1)
        )
        exact = result.scalar_one_or_none()
        if exact:
            return exact

        # Window search: ±7 days, pick nearest
        window_start = observation_date - timedelta(days=7)
        window_end = observation_date + timedelta(days=7)
        result = await db.execute(
            select(Forecast)
            .where(
                and_(
                    Forecast.product_id == product_id,
                    Forecast.site_id == site_id,
                    Forecast.forecast_date.between(window_start, window_end),
                    Forecast.is_active == "Y",
                )
            )
            .order_by(
                func.abs(
                    func.extract("epoch", Forecast.forecast_date)
                    - func.extract("epoch", observation_date)
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _record_and_check_calibration(
        self,
        db: AsyncSession,
        entity_type: EntityType,
        entity_id: str,
        tenant_id: int,
        predicted_value: float,
        actual_value: float,
        default_coverage: float = 0.90,
    ) -> bool:
        """
        Record observation to belief state and calibration log.
        Returns True if emergency recalibration was triggered.

        Generic across all entity types (demand, lead_time, yield, price, etc.).
        """
        residual = predicted_value - actual_value

        # Get or create belief state
        result = await db.execute(
            select(PowellBeliefState).where(
                and_(
                    PowellBeliefState.tenant_id == tenant_id,
                    PowellBeliefState.entity_type == entity_type,
                    PowellBeliefState.entity_id == entity_id,
                )
            )
        )
        state = result.scalar_one_or_none()

        if state is None:
            state = PowellBeliefState(
                tenant_id=tenant_id,
                entity_type=entity_type,
                entity_id=entity_id,
                point_estimate=predicted_value,
                conformal_coverage=default_coverage,
                observation_count=0,
            )
            db.add(state)
            await db.flush()

        # Check if observation was within interval
        in_interval = False
        if state.conformal_lower is not None and state.conformal_upper is not None:
            in_interval = state.conformal_lower <= actual_value <= state.conformal_upper

        # Log to PowellCalibrationLog
        log_entry = PowellCalibrationLog(
            belief_state_id=state.id,
            predicted_value=predicted_value,
            predicted_lower=state.conformal_lower,
            predicted_upper=state.conformal_upper,
            actual_value=actual_value,
            in_interval=in_interval,
            residual=residual,
            observed_at=datetime.utcnow(),
        )
        db.add(log_entry)

        # Update state's residuals and coverage history
        recent_residuals = (state.recent_residuals or []) + [residual]
        coverage_history = (state.coverage_history or []) + [1 if in_interval else 0]
        state.recent_residuals = recent_residuals[-100:]
        state.coverage_history = coverage_history[-100:]
        state.observation_count = (state.observation_count or 0) + 1
        state.point_estimate = predicted_value

        # Compute running CRPS (Normal closed-form) for forecast quality tracking
        if len(state.recent_residuals) >= MIN_OBSERVATIONS_FOR_CALIBRATION:
            sigma = float(np.std(state.recent_residuals))
            crps = self.compute_crps_normal(predicted_value, sigma, actual_value)
            if state.distribution_fit is None:
                state.distribution_fit = {}
            # Exponential moving average of CRPS
            prev_crps = state.distribution_fit.get("crps_score")
            if prev_crps is not None:
                alpha = 0.1  # EMA smoothing factor
                state.distribution_fit["crps_score"] = alpha * crps + (1 - alpha) * prev_crps
            else:
                state.distribution_fit["crps_score"] = crps

        # Check drift when enough observations
        if len(state.coverage_history) >= MIN_OBSERVATIONS_FOR_CALIBRATION:
            window = state.coverage_history[-100:]
            emp_coverage = sum(window) / len(window)
            state.empirical_coverage = emp_coverage
            target = state.conformal_coverage or default_coverage

            if abs(emp_coverage - target) > DRIFT_COVERAGE_THRESHOLD:
                state.drift_detected = True
                state.drift_score = emp_coverage - target

                await self._emergency_recalibrate(
                    db, entity_type, entity_id, tenant_id, state,
                )
                await db.flush()
                return True
            else:
                state.drift_detected = False

        await db.flush()
        return False

    # =======================================================================
    # GAP 3: Drift Monitoring (emergency recalibration)
    # =======================================================================

    async def _emergency_recalibrate(
        self,
        db: AsyncSession,
        entity_type: EntityType,
        entity_id: str,
        tenant_id: int,
        state: PowellBeliefState,
    ) -> None:
        """Emergency recalibration triggered by coverage drift. Works for all entity types."""
        logger.warning(
            f"DRIFT DETECTED for {entity_type.value}:{entity_id} "
            f"(empirical={state.empirical_coverage:.1%}, "
            f"target={state.conformal_coverage:.1%}). "
            f"Triggering emergency recalibration."
        )

        # Get recent forecast/actual pairs from CalibrationLog
        result = await db.execute(
            select(PowellCalibrationLog)
            .where(PowellCalibrationLog.belief_state_id == state.id)
            .order_by(PowellCalibrationLog.observed_at.desc())
            .limit(100)
        )
        logs = list(result.scalars().all())

        if len(logs) < MIN_OBSERVATIONS_FOR_CALIBRATION:
            logger.warning("Insufficient log data for emergency recalibration")
            return

        forecasts = [log.predicted_value for log in reversed(logs) if log.predicted_value is not None]
        actuals = [log.actual_value for log in reversed(logs) if log.actual_value is not None]

        if len(forecasts) < MIN_OBSERVATIONS_FOR_CALIBRATION:
            return

        # Dispatch to entity-specific suite calibration
        lower, upper, coverage = None, None, state.conformal_coverage or 0.90

        try:
            if entity_type == EntityType.DEMAND:
                parts = entity_id.split(":")
                if len(parts) >= 2:
                    prod_id, site_id_str = parts[0], parts[1]
                    self.suite.calibrate_demand(
                        product_id=prod_id,
                        site_id=int(site_id_str),
                        historical_forecasts=forecasts,
                        historical_actuals=actuals,
                    )
                    interval = self.suite.predict_demand(prod_id, int(site_id_str), forecasts[-1])
                    lower, upper = interval.lower, interval.upper
                    coverage = self.suite.demand_coverage

            elif entity_type == EntityType.LEAD_TIME:
                self.suite.calibrate_lead_time(
                    supplier_id=entity_id,
                    predicted_lead_times=forecasts,
                    actual_lead_times=actuals,
                )
                lt_lower, lt_upper = self.suite.predict_lead_time(entity_id, forecasts[-1])
                lower, upper = lt_lower, lt_upper
                coverage = getattr(self.suite, 'lead_time_coverage', 0.90)

            elif entity_type == EntityType.YIELD:
                parts = entity_id.split(":")
                prod_id = parts[0]
                process_id = parts[1] if len(parts) > 1 and parts[1] != "None" else None
                self.suite.calibrate_yield(
                    product_id=prod_id,
                    process_id=process_id,
                    expected_yields=forecasts,
                    actual_yields=actuals,
                )
                y_lower, y_upper = self.suite.predict_yield(prod_id, process_id, forecasts[-1])
                lower, upper = y_lower, y_upper
                coverage = getattr(self.suite, 'yield_coverage', 0.90)

            elif entity_type == EntityType.PRICE:
                self.suite.calibrate_price(
                    material_id=entity_id,
                    predicted_prices=forecasts,
                    actual_prices=actuals,
                )
                price_interval = self.suite.predict_price(entity_id, forecasts[-1])
                lower, upper = price_interval.lower, price_interval.upper
                coverage = getattr(self.suite, 'price_coverage', 0.90)

            else:
                # Entity types without suite predictors (SERVICE_LEVEL, CAPACITY, etc.)
                # Still update belief state but skip suite recalibration
                logger.info(
                    f"No suite predictor for {entity_type.value}. "
                    f"Updating belief state only."
                )
        except Exception as e:
            logger.warning(f"Suite recalibration failed for {entity_type.value}:{entity_id}: {e}")

        # Persist updated calibration
        residuals = [f - a for f, a in zip(forecasts, actuals)]
        if lower is not None and upper is not None:
            cov_hist = [
                1 if lower <= a <= upper else 0
                for a in actuals
            ]
        else:
            # No interval from suite; use existing state interval for coverage history
            cov_hist = state.coverage_history or []

        await self.persist_calibration(
            db, entity_type, entity_id, tenant_id,
            point_estimate=forecasts[-1],
            lower=lower if lower is not None else (state.conformal_lower or 0.0),
            upper=upper if upper is not None else (state.conformal_upper or 0.0),
            coverage=coverage,
            residuals=residuals,
            coverage_history=cov_hist,
        )

        logger.info(
            f"Emergency recalibration complete for {entity_type.value}:{entity_id}. "
            f"New interval: [{lower}, {upper}]"
        )

    # =======================================================================
    # CRPS: Continuous Ranked Probability Score (Lokad gold standard)
    # =======================================================================

    @staticmethod
    def compute_crps_normal(mu: float, sigma: float, observed: float) -> float:
        """Closed-form CRPS for Normal distribution.

        CRPS(N(μ,σ²), x) = σ [z(2Φ(z)-1) + 2φ(z) - 1/√π]
        where z = (x-μ)/σ, Φ = CDF, φ = PDF.

        This is the gold standard metric for evaluating probabilistic
        forecasts (Lokad methodology). Lower CRPS = better calibration.
        """
        from scipy import stats as sp_stats

        if sigma <= 0:
            # Degenerate: CRPS reduces to MAE
            return abs(observed - mu)

        z = (observed - mu) / sigma
        phi_z = sp_stats.norm.pdf(z)
        big_phi_z = sp_stats.norm.cdf(z)

        return sigma * (z * (2 * big_phi_z - 1) + 2 * phi_z - 1.0 / math.sqrt(math.pi))

    @staticmethod
    def compute_crps_empirical(
        cdf_values: np.ndarray,
        grid_points: np.ndarray,
        observed: float,
    ) -> float:
        """CRPS for discrete/empirical CDF via numerical integration.

        CRPS = ∫(F(y) - 𝟙{y ≥ x})² dy

        Use this when the forecast is a full distribution (quantile grid,
        mixture, empirical CDF) rather than a parametric Normal.
        """
        indicator = (grid_points >= observed).astype(float)
        integrand = (cdf_values - indicator) ** 2
        _trapz = getattr(np, 'trapezoid', None) or np.trapz
        return float(_trapz(integrand, grid_points))

    async def compute_crps_for_entity(
        self,
        db: AsyncSession,
        entity_type: EntityType,
        entity_id: str,
    ) -> Optional[float]:
        """Compute CRPS score from recent calibration log entries.

        Uses the Normal closed-form with point_estimate as μ and
        residual std dev as σ. Returns None if insufficient data.
        """
        result = await db.execute(
            select(PowellBeliefState).where(
                and_(
                    PowellBeliefState.entity_type == entity_type,
                    PowellBeliefState.entity_id == entity_id,
                )
            )
        )
        state = result.scalar_one_or_none()
        if state is None or not state.recent_residuals:
            return None

        residuals = state.recent_residuals
        if len(residuals) < MIN_OBSERVATIONS_FOR_CALIBRATION:
            return None

        mu = state.point_estimate or 0.0
        sigma = float(np.std(residuals)) if len(residuals) > 1 else 0.0

        # Compute CRPS for each recent observation and average
        log_result = await db.execute(
            select(PowellCalibrationLog)
            .where(PowellCalibrationLog.belief_state_id == state.id)
            .order_by(PowellCalibrationLog.observed_at.desc())
            .limit(100)
        )
        logs = list(log_result.scalars().all())

        if not logs:
            return None

        crps_scores = []
        for log in logs:
            if log.actual_value is not None and log.predicted_value is not None:
                crps = self.compute_crps_normal(
                    mu=log.predicted_value,
                    sigma=sigma,
                    observed=log.actual_value,
                )
                crps_scores.append(crps)

        if not crps_scores:
            return None

        avg_crps = float(np.mean(crps_scores))

        # Persist CRPS to belief state
        if state.distribution_fit is None:
            state.distribution_fit = {}
        state.distribution_fit["crps_score"] = avg_crps
        state.distribution_fit["crps_n_observations"] = len(crps_scores)
        await db.flush()

        return avg_crps

    # =======================================================================
    # GAP 5: Planning Staleness Check
    # =======================================================================

    def check_staleness(
        self,
        product_id: str,
        site_id: int,
    ) -> Dict:
        """
        Before using conformal intervals in planning, verify freshness.
        Backward-compatible wrapper for demand entity type.
        """
        return self.check_staleness_by_entity(
            EntityType.DEMAND, f"{product_id}:{site_id}"
        )

    def check_staleness_by_entity(
        self,
        entity_type: EntityType,
        entity_id: str,
    ) -> Dict:
        """
        Check calibration freshness for any entity type.

        Args:
            entity_type: EntityType (DEMAND, LEAD_TIME, YIELD, PRICE, etc.)
            entity_id: Entity identifier (format depends on type)

        Returns:
            Dict with is_fresh, is_stale, is_expired, age_hours, recommendation
        """
        # Build suite key from entity_type and entity_id parts
        key_parts = [p for p in entity_id.split(":") if p and p != "None"]
        key = self.suite._get_key(entity_type.value, *key_parts)
        timestamp = self.suite._calibration_timestamps.get(key)

        if timestamp is None:
            return {
                "is_fresh": False,
                "is_stale": True,
                "is_expired": True,
                "age_hours": None,
                "last_calibration": None,
                "recommendation": f"No {entity_type.value} calibration exists. Run calibration first.",
            }

        age = datetime.utcnow() - timestamp
        age_hours = age.total_seconds() / 3600

        is_stale = age_hours > STALENESS_WARNING_HOURS
        is_expired = age_hours > STALENESS_ERROR_HOURS

        if is_expired:
            recommendation = (
                f"EXPIRED ({age_hours:.0f}h old). "
                "Recalibration required before use in planning."
            )
        elif is_stale:
            recommendation = (
                f"Stale ({age_hours:.0f}h old). "
                "Recalibration recommended. Results may be less reliable."
            )
        else:
            recommendation = "Fresh - OK to use."

        return {
            "is_fresh": not is_stale,
            "is_stale": is_stale,
            "is_expired": is_expired,
            "age_hours": age_hours,
            "last_calibration": timestamp.isoformat(),
            "recommendation": recommendation,
        }

    # =======================================================================
    # Non-Demand Observation Hooks
    # =======================================================================

    async def on_lead_time_observed(
        self,
        db: AsyncSession,
        supplier_id: str,
        expected_lead_time_days: float,
        actual_lead_time_days: float,
        tenant_id: int,
        source_order_type: str = "TO",
        source_order_id: Optional[int] = None,
    ) -> Optional[Dict]:
        """
        Hook called when a TransferOrder or PurchaseOrder is received,
        providing an actual lead time observation.

        Args:
            supplier_id: Supplier identifier (str(source_site_id) for TO, vendor_id for PO)
            expected_lead_time_days: Predicted lead time (estimated_delivery_date - order_date)
            actual_lead_time_days: Actual lead time (actual_delivery_date - order_date)
            tenant_id: Customer ID for belief state
            source_order_type: "TO" or "PO" for logging
            source_order_id: ID of the source order
        """
        if actual_lead_time_days < 0 or expected_lead_time_days <= 0:
            logger.debug(
                f"Invalid lead time observation: expected={expected_lead_time_days}, "
                f"actual={actual_lead_time_days}"
            )
            return None

        error = actual_lead_time_days - expected_lead_time_days

        emergency_recal = await self._record_and_check_calibration(
            db, EntityType.LEAD_TIME, supplier_id,
            tenant_id, expected_lead_time_days, actual_lead_time_days,
        )

        logger.debug(
            f"Lead time observed for supplier {supplier_id} "
            f"({source_order_type}#{source_order_id}): "
            f"expected={expected_lead_time_days}d, actual={actual_lead_time_days}d, "
            f"error={error:+.1f}d"
        )

        return {
            "supplier_id": supplier_id,
            "expected_lead_time_days": expected_lead_time_days,
            "actual_lead_time_days": actual_lead_time_days,
            "error_days": error,
            "source_order_type": source_order_type,
            "source_order_id": source_order_id,
            "emergency_recalibration": emergency_recal,
        }

    async def on_yield_observed(
        self,
        db: AsyncSession,
        product_id: str,
        process_id: Optional[str],
        expected_yield: float,
        actual_yield: float,
        tenant_id: int,
    ) -> Optional[Dict]:
        """
        Hook called when manufacturing output is recorded.

        Note: Not automatically wired yet (no manufacturing execution service).
        Designed to be called from future manufacturing endpoints or
        manually via Rolling Horizon S&OP observe_actuals().

        Args:
            product_id: Product being manufactured
            process_id: Manufacturing process ID (optional)
            expected_yield: Expected yield ratio (0.0-1.0)
            actual_yield: Actual yield ratio (0.0-1.0)
            tenant_id: Customer ID for belief state
        """
        if not (0.0 <= expected_yield <= 1.0) or not (0.0 <= actual_yield <= 1.0):
            logger.debug(
                f"Invalid yield observation: expected={expected_yield}, actual={actual_yield}"
            )
            return None

        entity_id = f"{product_id}:{process_id}" if process_id else product_id
        error = actual_yield - expected_yield

        emergency_recal = await self._record_and_check_calibration(
            db, EntityType.YIELD, entity_id,
            tenant_id, expected_yield, actual_yield,
        )

        logger.debug(
            f"Yield observed for {product_id} (process={process_id}): "
            f"expected={expected_yield:.3f}, actual={actual_yield:.3f}, "
            f"error={error:+.3f}"
        )

        return {
            "product_id": product_id,
            "process_id": process_id,
            "expected_yield": expected_yield,
            "actual_yield": actual_yield,
            "error": error,
            "emergency_recalibration": emergency_recal,
        }

    async def on_price_observed(
        self,
        db: AsyncSession,
        material_id: str,
        expected_price: float,
        actual_price: float,
        tenant_id: int,
        source_po_id: Optional[int] = None,
    ) -> Optional[Dict]:
        """
        Hook called when a PO is received and actual price can be compared
        to catalog/expected price.

        Args:
            material_id: Product ID of the material
            expected_price: Catalog/vendor_unit_cost price
            actual_price: Actual PO line item unit_price
            tenant_id: Customer ID for belief state
            source_po_id: PurchaseOrder ID
        """
        if actual_price < 0 or expected_price <= 0:
            logger.debug(
                f"Invalid price observation: expected={expected_price}, actual={actual_price}"
            )
            return None

        error = actual_price - expected_price

        emergency_recal = await self._record_and_check_calibration(
            db, EntityType.PRICE, material_id,
            tenant_id, expected_price, actual_price,
        )

        logger.debug(
            f"Price observed for material {material_id} (PO#{source_po_id}): "
            f"expected=${expected_price:.2f}, actual=${actual_price:.2f}, "
            f"error=${error:+.2f}"
        )

        return {
            "material_id": material_id,
            "expected_price": expected_price,
            "actual_price": actual_price,
            "error": error,
            "source_po_id": source_po_id,
            "emergency_recalibration": emergency_recal,
        }

    async def on_service_level_observed(
        self,
        db: AsyncSession,
        product_id: str,
        site_id: int,
        expected_fill_rate: float,
        actual_fill_rate: float,
        tenant_id: int,
    ) -> Optional[Dict]:
        """
        Hook called when an order is fully fulfilled, providing a
        service level (fill rate) observation.

        Note: No suite predictor for SERVICE_LEVEL exists yet. Records to
        PowellBeliefState for drift detection and future use.

        Args:
            product_id: Product ID
            site_id: Fulfillment site ID
            expected_fill_rate: Target fill rate (typically 1.0)
            actual_fill_rate: Actual fill rate (shipped/ordered)
            tenant_id: Customer ID for belief state
        """
        if not (0.0 <= expected_fill_rate <= 1.0) or not (0.0 <= actual_fill_rate <= 1.0):
            logger.debug(
                f"Invalid service level observation: "
                f"expected={expected_fill_rate}, actual={actual_fill_rate}"
            )
            return None

        entity_id = f"{product_id}:{site_id}"
        error = actual_fill_rate - expected_fill_rate

        emergency_recal = await self._record_and_check_calibration(
            db, EntityType.SERVICE_LEVEL, entity_id,
            tenant_id, expected_fill_rate, actual_fill_rate,
        )

        logger.debug(
            f"Service level observed for {product_id}@{site_id}: "
            f"expected={expected_fill_rate:.1%}, actual={actual_fill_rate:.1%}"
        )

        return {
            "product_id": product_id,
            "site_id": site_id,
            "expected_fill_rate": expected_fill_rate,
            "actual_fill_rate": actual_fill_rate,
            "error": error,
            "emergency_recalibration": emergency_recal,
        }


# ===========================================================================
# GAP 4: Scheduled Recalibration (module-level for APScheduler pickling)
# ===========================================================================

def _run_daily_conformal_recalibration() -> None:
    """
    APScheduler job: Daily recalibration of all stale belief states.
    Runs in a BackgroundScheduler thread, so we create our own event loop
    for async operations.
    """
    import asyncio

    logger.info("Starting scheduled daily conformal recalibration")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_async_daily_recalibration())
        finally:
            loop.close()
    except Exception as e:
        logger.error(f"Daily conformal recalibration failed: {e}")


async def _async_daily_recalibration() -> None:
    """Async implementation of daily recalibration."""
    from app.db.session import async_session_factory
    from app.services.calibration_feedback_service import CalibrationFeedbackService

    if async_session_factory is None:
        logger.warning("Async session factory not available, skipping recalibration")
        return

    async with async_session_factory() as db:
        # Get all customers that have belief states
        result = await db.execute(
            select(PowellBeliefState.tenant_id).distinct()
        )
        tenant_ids = result.scalars().all()

        total_recalibrated = 0
        for tenant_id in tenant_ids:
            try:
                feedback_service = CalibrationFeedbackService(db)
                recalibrated = await feedback_service.recalibrate_all_stale(
                    tenant_id=tenant_id,
                    max_age_hours=24,
                )
                total_recalibrated += len(recalibrated)
            except Exception as e:
                logger.error(f"Recalibration failed for tenant {tenant_id}: {e}")

        # Re-hydrate suite from updated DB state
        if total_recalibrated > 0:
            orchestrator = ConformalOrchestrator.get_instance()
            await orchestrator.hydrate_from_db(db)

        await db.commit()
        logger.info(
            f"Daily conformal recalibration complete: "
            f"{total_recalibrated} belief states recalibrated across "
            f"{len(tenant_ids)} tenants"
        )


def register_conformal_jobs(scheduler_service) -> None:
    """
    Register conformal prediction jobs with APScheduler.
    Called from main.py startup alongside register_retention_jobs().
    """
    from apscheduler.triggers.cron import CronTrigger

    scheduler = getattr(scheduler_service, "_scheduler", None)
    if not scheduler:
        logger.warning("Scheduler not available, conformal jobs not registered")
        return

    scheduler.add_job(
        func=_run_daily_conformal_recalibration,
        trigger=CronTrigger(
            hour=DAILY_RECALIBRATION_HOUR,
            minute=DAILY_RECALIBRATION_MINUTE,
        ),
        id="conformal_daily_recalibration",
        name="Daily Conformal Recalibration",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(
        f"Registered daily conformal recalibration job "
        f"({DAILY_RECALIBRATION_HOUR}:{DAILY_RECALIBRATION_MINUTE:02d} UTC)"
    )
