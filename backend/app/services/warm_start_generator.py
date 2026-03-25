"""Monte Carlo warm start generator for supply chain configs.

Generates consistent historical demand data from existing Forecast P10/P50/P90
distributions, enabling conformal calibration and ROI metrics to hydrate on
any SC config — not just Food Dist.

Uses triangular sampling (not SimPy) so it works for any topology.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.sc_entities import Forecast, OutboundOrderLine
from app.models.powell import PowellBeliefState, PowellCalibrationLog, EntityType, ConformalMethod
from app.models.decision_tracking import PerformanceMetric
from app.models.supply_chain_config import SupplyChainConfig

logger = logging.getLogger(__name__)

WARM_START_ORDER_PREFIX = "WS"


class WarmStartGenerator:
    """Monte Carlo warm start — idempotent historical data generator.

    Samples actual demand from existing Forecast triangular distributions
    (P10, P50, P90), writes OutboundOrderLine records, seeds performance
    metrics and Powell belief states for conformal calibration.
    """

    HISTORY_WEEKS = 52
    SEED = 42

    def __init__(self, db: Session):
        self.db = db
        self.rng = np.random.default_rng(self.SEED)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_for_config(self, config_id: int, weeks: int = 52) -> dict:
        """Main entry point. Idempotent (cleans up previous warm start first).

        Args:
            config_id: SupplyChainConfig.id
            weeks: How many weeks of history to generate

        Returns:
            {"status": "ok", "records": N} or {"status": "skipped", "reason": "..."}
        """
        config = self.db.query(SupplyChainConfig).filter(SupplyChainConfig.id == config_id).first()
        if not config:
            return {"status": "skipped", "reason": f"config {config_id} not found"}

        tenant_id = config.tenant_id

        # Step 1: Clean up any previous warm start data
        self._cleanup_existing(config_id)

        # Step 1b: Detect NPI products (in config but missing forecasts) and create
        # initial forecasts based on category averages from existing products
        npi_count = self._create_npi_forecasts(config_id, weeks)
        if npi_count:
            logger.info("WarmStart config=%d: created %d NPI forecast rows for products without forecasts", config_id, npi_count)

        # Step 2: Load existing forecast records (P10/P50/P90)
        forecast_rows = self._load_forecasts(config_id, weeks)
        if not forecast_rows:
            return {"status": "skipped", "reason": "no forecasts found for config"}

        logger.info("WarmStart config=%d: found %d forecast rows, generating actuals", config_id, len(forecast_rows))

        # Step 3: Sample actuals via triangular distribution
        actuals = self._generate_actuals(forecast_rows, weeks)

        # Step 4: Write OutboundOrderLine records (skipped if product_id FK mismatch)
        ool_count = self._write_outbound_order_lines(actuals, config_id)
        logger.info("WarmStart config=%d: %d OOL records written", config_id, ool_count)

        # Step 5: Update Forecast.forecast_error / forecast_bias
        self._update_forecast_errors(forecast_rows, actuals)

        # Step 6: Seed PerformanceMetric history (12 months)
        self._seed_performance_metrics(config_id, tenant_id)

        # Step 7: Seed PowellBeliefState + PowellCalibrationLog
        self._seed_belief_states(config_id, tenant_id, actuals)

        self.db.flush()

        # Step 8: Generate initial executive briefing + ensure schedule exists
        self._generate_initial_briefing(config_id, tenant_id)

        logger.info("WarmStart config=%d: committed %d actuals", config_id, len(actuals))
        return {"status": "ok", "records": len(actuals), "config_id": config_id}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_npi_forecasts(self, config_id: int, weeks: int) -> int:
        """Detect NPI products (exist in config but have no forecast) and create
        initial forecasts based on category averages from existing products.

        This is what the forecast adjustment TRM would do: detect the gap and
        generate a conservative initial forecast derived from similar products.
        NPI forecasts use a ramp-up profile: 30% of category average in week 1,
        ramping to 80% by week 12, to reflect typical NPI adoption curves.

        Returns count of forecast rows created.
        """
        from app.models.sc_entities import Product
        from sqlalchemy import text as sa_text

        # Find all products in this config
        all_products = (
            self.db.query(Product)
            .filter(Product.config_id == config_id)
            .all()
        )
        if not all_products:
            return 0

        # Find products that already have forecasts
        result = self.db.execute(
            sa_text("SELECT DISTINCT product_id FROM forecast WHERE config_id = :c"),
            {"c": config_id},
        )
        has_forecast = {r[0] for r in result.fetchall()}

        # NPI = products without any forecast rows
        npi_products = [p for p in all_products if p.id not in has_forecast]
        if not npi_products:
            return 0

        logger.info(
            "WarmStart config=%d: %d NPI products detected without forecasts: %s",
            config_id, len(npi_products),
            [p.id for p in npi_products],
        )

        # Compute category averages from existing forecasts
        # Group existing products by category
        cat_avgs = {}
        for p in all_products:
            if p.id in has_forecast:
                cat = getattr(p, "category", None) or "DEFAULT"
                cat_avgs.setdefault(cat, []).append(p.id)

        # Get typical weekly P50 per category — median of per-product-site P50 values
        # Uses PERCENTILE_CONT(0.5) to avoid P90 outlier inflation
        cat_forecast_avgs = {}
        for cat, pids in cat_avgs.items():
            result = self.db.execute(
                sa_text("""
                    SELECT
                        PERCENTILE_CONT(0.1) WITHIN GROUP (ORDER BY forecast_p50) as p10,
                        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY forecast_p50) as p50,
                        PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY forecast_p50) as p90
                    FROM forecast
                    WHERE config_id = :c AND product_id = ANY(:pids)
                    AND forecast_p50 > 0
                """),
                {"c": config_id, "pids": pids},
            )
            row = result.fetchone()
            if row and row[1]:
                cat_forecast_avgs[cat] = {
                    "p10": float(row[0] or 0),
                    "p50": float(row[1] or 0),
                    "p90": float(row[2] or 0),
                }

        # Global fallback if no category match
        global_avg = None
        if cat_forecast_avgs:
            all_p50 = [v["p50"] for v in cat_forecast_avgs.values()]
            global_avg = {
                "p10": sum(v["p10"] for v in cat_forecast_avgs.values()) / len(cat_forecast_avgs),
                "p50": sum(all_p50) / len(all_p50),
                "p90": sum(v["p90"] for v in cat_forecast_avgs.values()) / len(cat_forecast_avgs),
            }

        if not global_avg:
            logger.warning("WarmStart config=%d: no category averages available for NPI forecasts", config_id)
            return 0

        # Create forecast rows for each NPI product
        count = 0
        today = date.today()
        # Generate future forecasts (NPI has no history — only forward-looking)
        for p in npi_products:
            cat = getattr(p, "category", None) or "DEFAULT"
            base = cat_forecast_avgs.get(cat, global_avg)

            for week_offset in range(weeks):
                forecast_date = today + timedelta(weeks=week_offset)

                # NPI ramp-up: 30% at launch → 80% by week 12 → 100% by week 24
                if week_offset < 12:
                    ramp = 0.30 + (0.50 * week_offset / 12)  # 30% → 80%
                elif week_offset < 24:
                    ramp = 0.80 + (0.20 * (week_offset - 12) / 12)  # 80% → 100%
                else:
                    ramp = 1.0

                # Add uncertainty: wider P10/P90 for NPI (more uncertain)
                npi_uncertainty = max(1.0, 2.0 - (week_offset / 24))  # 2x uncertainty at launch → 1x by week 24

                p50 = round(base["p50"] * ramp, 2)
                p10 = round(base["p10"] * ramp / npi_uncertainty, 2)
                p90 = round(base["p90"] * ramp * npi_uncertainty, 2)

                self.db.execute(
                    sa_text("""
                        INSERT INTO forecast (config_id, product_id, forecast_date,
                            forecast_p10, forecast_p50, forecast_p90,
                            forecast_quantity, forecast_type, forecast_method,
                            is_active)
                        VALUES (:c, :pid, :dt, :p10, :p50, :p90,
                            :p50, 'npi_ramp', 'category_analog', true)
                    """),
                    {"c": config_id, "pid": p.id, "dt": forecast_date,
                     "p10": p10, "p50": p50, "p90": p90},
                )
                count += 1

        self.db.flush()
        return count

    def _load_forecasts(self, config_id: int, weeks: int) -> List[Forecast]:
        """Load Forecast rows for this config covering the past `weeks` weeks."""
        cutoff = date.today() - timedelta(weeks=weeks + 4)  # small buffer
        rows = (
            self.db.query(Forecast)
            .filter(
                Forecast.config_id == config_id,
                Forecast.forecast_p50.isnot(None),
                Forecast.forecast_p50 > 0,
                Forecast.forecast_date >= cutoff,
            )
            .all()
        )
        return rows

    def _generate_actuals(self, forecast_rows: List[Forecast], weeks: int) -> List[dict]:
        """Sample actual demand from triangular(P10, P50, P90) + multiplicative noise."""
        actuals = []
        cutoff = date.today() - timedelta(weeks=weeks)

        for row in forecast_rows:
            if row.forecast_date > date.today():
                continue  # skip future forecasts
            if row.forecast_date < cutoff:
                continue

            p50 = float(row.forecast_p50)
            p10 = float(row.forecast_p10) if row.forecast_p10 is not None else p50 * 0.7
            p90 = float(row.forecast_p90) if row.forecast_p90 is not None else p50 * 1.3

            # Triangular sample: mode=p50, left=p10, right=p90
            # Add 3% multiplicative noise for realism
            triangular = float(self.rng.triangular(left=max(0, p10), mode=p50, right=max(p50 + 0.01, p90)))
            noise = float(self.rng.normal(1.0, 0.03))
            actual_qty = max(0.0, round(triangular * noise, 4))

            actuals.append({
                "product_id": str(row.product_id),
                "site_id": row.site_id,
                "date": row.forecast_date,
                "actual_qty": actual_qty,
                "forecast_p50": p50,
                "forecast_p10": p10,
                "forecast_p90": p90,
                "error": actual_qty - p50,
            })
        return actuals

    def _write_outbound_order_lines(self, actuals: List[dict], config_id: int) -> int:
        """INSERT demand history records via raw SQL to match actual DB schema.

        The outbound_order_line table has a legacy INTEGER FK product_id to
        items.id (Beer Game table). AWS SC configs use string product IDs from
        the product table, which are incompatible. In that case we skip OOL
        creation — the forecast pipeline falls back to Forecast.forecast_p50
        as actuals, and conformal calibration uses PowellCalibrationLog.

        Returns number of rows inserted (0 if skipped due to FK mismatch).
        """
        if not actuals:
            return 0

        # Check if this config's products exist in the items table (Beer Game)
        # vs the product table (AWS SC). If products are strings, skip OOL.
        sample_product_id = actuals[0]["product_id"]
        is_string_product = not str(sample_product_id).isdigit()
        if is_string_product:
            logger.info(
                "WarmStart config=%d: skipping OOL creation — product_id '%s' is a "
                "string (AWS SC product table), incompatible with outbound_order_line "
                "INTEGER FK to items.id. Conformal calibration uses PowellCalibrationLog.",
                config_id, sample_product_id,
            )
            return 0

        # Beer Game configs with integer product IDs — use extended or minimal schema
        col_rows = self.db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='outbound_order_line'"
            )
        ).fetchall()
        available = {row[0] for row in col_rows}
        has_extended = "shipped_quantity" in available

        count = 0
        for a in actuals:
            order_id = f"{WARM_START_ORDER_PREFIX}-{config_id}-{a['product_id']}-{a['date'].isoformat()}"
            try:
                if has_extended:
                    self.db.execute(
                        text("""
                            INSERT INTO outbound_order_line
                                (order_id, line_number, product_id, site_id, ordered_quantity,
                                 requested_delivery_date, order_date, config_id,
                                 shipped_quantity, backlog_quantity, status, priority_code)
                            VALUES (:oid, 1, :pid, :sid, :qty, :rdate, :odate, :cid,
                                    :qty, 0.0, 'FULFILLED', 'STANDARD')
                        """),
                        {"oid": order_id, "pid": int(a["product_id"]),
                         "sid": a["site_id"], "qty": a["actual_qty"],
                         "rdate": a["date"], "odate": a["date"], "cid": config_id},
                    )
                else:
                    self.db.execute(
                        text("""
                            INSERT INTO outbound_order_line
                                (order_id, line_number, product_id, site_id, ordered_quantity,
                                 requested_delivery_date, order_date, config_id)
                            VALUES (:oid, 1, :pid, :sid, :qty, :rdate, :odate, :cid)
                        """),
                        {"oid": order_id, "pid": int(a["product_id"]),
                         "sid": a["site_id"], "qty": a["actual_qty"],
                         "rdate": a["date"], "odate": a["date"], "cid": config_id},
                    )
                count += 1
            except Exception as exc:
                logger.warning("WarmStart: skipping OOL insert for %s: %s", order_id, exc)
                self.db.rollback()
                break
        return count

    def _update_forecast_errors(self, forecast_rows: List[Forecast], actuals: List[dict]) -> None:
        """Backfill Forecast.forecast_error / forecast_bias from generated actuals."""
        actual_map: Dict[tuple, dict] = {
            (a["product_id"], a["site_id"], a["date"]): a
            for a in actuals
        }
        for row in forecast_rows:
            key = (str(row.product_id), row.site_id, row.forecast_date)
            if key in actual_map:
                a = actual_map[key]
                row.forecast_error = a["error"]
                row.forecast_bias = (a["error"] / a["forecast_p50"]) if a["forecast_p50"] else None

    def _seed_performance_metrics(self, config_id: int, tenant_id: int) -> None:
        """Create 12 monthly PerformanceMetric rows showing automation improvement."""
        # Only seed if tenant has no existing metrics
        existing = (
            self.db.query(PerformanceMetric)
            .filter(PerformanceMetric.tenant_id == tenant_id)
            .count()
        )
        if existing > 0:
            return

        now = datetime.utcnow()
        n_months = 12
        for i in range(n_months):
            t = i / (n_months - 1)  # 0.0 → 1.0
            month_start = now - timedelta(days=30 * (n_months - 1 - i))
            month_end = month_start + timedelta(days=30)

            automation = 30.0 + t * (75.0 - 30.0)       # 30 → 75
            agent_score = 45.0 + t * (72.0 - 45.0)      # 45 → 72
            planner_score = 35.0 + t * (48.0 - 35.0)    # 35 → 48
            override_rate = 45.0 - t * (45.0 - 22.0)    # 45 → 22

            self.db.add(PerformanceMetric(
                tenant_id=tenant_id,
                period_start=month_start,
                period_end=month_end,
                period_type="monthly",
                category=None,
                automation_percentage=round(automation, 1),
                agent_score=round(agent_score, 1),
                planner_score=round(planner_score, 1),
                override_rate=round(override_rate, 1),
                total_decisions=100 + i * 8,
                agent_decisions=int((automation / 100) * (100 + i * 8)),
                planner_decisions=int((1 - automation / 100) * (100 + i * 8)),
                active_agents=3,
                active_planners=2,
                total_skus=25,
            ))

    def _seed_belief_states(self, config_id: int, tenant_id: int, actuals: List[dict]) -> None:
        """Create PowellBeliefState + PowellCalibrationLog from generated actuals.

        Uses raw SQL to match the actual DB schema, which differs from the ORM model:
        - DB uses config_id (not tenant_id) for belief state association
        - entity_type is varchar (not enum)
        """
        import json
        from collections import defaultdict

        # Group actuals by (product_id, site_id)
        groups: Dict[tuple, List[dict]] = defaultdict(list)
        for a in actuals:
            groups[(a["product_id"], a["site_id"])].append(a)

        for (product_id, site_id), items in groups.items():
            items_sorted = sorted(items, key=lambda x: x["date"])
            errors = [it["error"] for it in items_sorted]
            p50s = [it["forecast_p50"] for it in items_sorted]

            std_err = float(np.std(errors)) if len(errors) > 1 else float(np.mean(p50s) * 0.15 if p50s else 1.0)
            mean_p50 = float(np.mean(p50s)) if p50s else 1.0
            entity_id = f"{product_id}:{site_id}"
            recent_residuals = errors[-30:]
            coverage_history = [1] * len(recent_residuals)

            # Check if belief state already exists for this tenant+entity
            existing = self.db.execute(
                text("""
                    SELECT id FROM powell_belief_state
                    WHERE tenant_id = :t AND entity_type = 'DEMAND' AND entity_id = :e
                    LIMIT 1
                """),
                {"t": tenant_id, "e": entity_id},
            ).fetchone()

            if existing is None:
                result = self.db.execute(
                    text("""
                        INSERT INTO powell_belief_state
                            (entity_type, entity_id, tenant_id,
                             point_estimate, conformal_lower, conformal_upper,
                             conformal_coverage, conformal_method,
                             recent_residuals, coverage_history,
                             created_at, updated_at)
                        VALUES ('DEMAND', :eid, :tid,
                                :p50, :lower, :upper,
                                0.80, 'adaptive',
                                :residuals, :coverage,
                                NOW(), NOW())
                        RETURNING id
                    """),
                    {
                        "eid": entity_id,
                        "tid": tenant_id,
                        "p50": mean_p50,
                        "lower": max(0.0, mean_p50 - 1.96 * std_err),
                        "upper": mean_p50 + 1.96 * std_err,
                        "residuals": json.dumps(recent_residuals),
                        "coverage": json.dumps(coverage_history),
                    },
                )
                belief_state_id = result.fetchone()[0]
            else:
                belief_state_id = existing[0]

            # Write calibration log (last 30 actuals)
            for it in items_sorted[-30:]:
                in_interval = abs(it["error"]) < 1.96 * std_err
                self.db.execute(
                    text("""
                        INSERT INTO powell_calibration_log
                            (belief_state_id, predicted_value, predicted_lower,
                             predicted_upper, actual_value, in_interval, residual,
                             observed_at)
                        VALUES (:bs_id, :pred, :lower, :upper,
                                :actual, :in_int, :resid, :obs_at)
                    """),
                    {
                        "bs_id": belief_state_id,
                        "pred": it["forecast_p50"],
                        "lower": max(0.0, it["forecast_p50"] - 1.96 * std_err),
                        "upper": it["forecast_p50"] + 1.96 * std_err,
                        "actual": it["actual_qty"],
                        "in_int": in_interval,
                        "resid": it["error"],
                        "obs_at": datetime.combine(it["date"], datetime.min.time()),
                    },
                )

    def _ensure_briefing_schedule(self, tenant_id: int) -> None:
        """Create a default weekly BriefingSchedule if one doesn't exist."""
        from app.models.executive_briefing import BriefingSchedule

        existing = (
            self.db.query(BriefingSchedule)
            .filter(BriefingSchedule.tenant_id == tenant_id)
            .first()
        )
        if not existing:
            self.db.add(BriefingSchedule(
                tenant_id=tenant_id,
                enabled=True,
                briefing_type="weekly",
                cron_day_of_week="mon",
                cron_hour=6,
                cron_minute=0,
            ))
            self.db.flush()
            logger.info("WarmStart: created default weekly briefing schedule for tenant %d", tenant_id)

    def _generate_initial_briefing(self, config_id: int, tenant_id: int) -> None:
        """Generate an initial executive briefing and ensure schedule exists.

        Commits warm start data first so BriefingDataCollector can see it.
        Failures are non-fatal (logged but don't abort warm start).
        """
        try:
            self._ensure_briefing_schedule(tenant_id)
            self.db.commit()

            from app.services.executive_briefing_service import ExecutiveBriefingService
            service = ExecutiveBriefingService(self.db)
            asyncio.run(service.generate_briefing(
                tenant_id=tenant_id,
                briefing_type="weekly",
                requested_by=None,
            ))
            logger.info(
                "WarmStart config=%d: initial executive briefing generated for tenant %d",
                config_id, tenant_id,
            )
        except Exception as e:
            logger.warning(
                "WarmStart config=%d: briefing generation failed (non-fatal): %s",
                config_id, e,
            )

    def _cleanup_existing(self, config_id: int) -> None:
        """Remove previous warm start data for this config."""
        # Remove warm start OutboundOrderLines (tagged by order_id prefix)
        self.db.execute(
            text(
                f"DELETE FROM outbound_order_line "
                f"WHERE config_id = :c AND order_id LIKE '{WARM_START_ORDER_PREFIX}-%'"
            ),
            {"c": config_id},
        )

        # Reset forecast_error/bias
        self.db.execute(
            text("UPDATE forecast SET forecast_error = NULL, forecast_bias = NULL WHERE config_id = :c"),
            {"c": config_id},
        )

        self.db.flush()

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    def get_status(self, config_id: int) -> dict:
        """Return counts for warm start data for this config."""
        config = self.db.query(SupplyChainConfig).filter(SupplyChainConfig.id == config_id).first()
        tenant_id = config.tenant_id if config else None

        ool_count = self.db.execute(
            text(f"SELECT COUNT(*) FROM outbound_order_line WHERE config_id = :c AND order_id LIKE '{WARM_START_ORDER_PREFIX}-%'"),
            {"c": config_id},
        ).scalar() or 0

        bs_count = 0
        cal_count = 0
        pm_count = 0
        if tenant_id:
            bs_count = self.db.execute(
                text("SELECT COUNT(*) FROM powell_belief_state WHERE tenant_id = :t AND entity_type = 'DEMAND'"),
                {"t": tenant_id},
            ).scalar() or 0
            cal_count = self.db.execute(
                text("""
                    SELECT COUNT(*) FROM powell_calibration_log cl
                    JOIN powell_belief_state bs ON bs.id = cl.belief_state_id
                    WHERE bs.tenant_id = :t
                """),
                {"t": tenant_id},
            ).scalar() or 0
            pm_count = (
                self.db.query(PerformanceMetric)
                .filter(PerformanceMetric.tenant_id == tenant_id)
                .count()
            )

        return {
            "config_id": config_id,
            "outbound_order_lines": int(ool_count),
            "belief_states": int(bs_count),
            "calibration_log": int(cal_count),
            "performance_metrics": int(pm_count),
        }
