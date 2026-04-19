"""
Planning Cascade Jobs — Automated planning execution on schedule.

Under AIIO, the planning cascade runs automatically:
  - S&OP (strategic): Weekly — GraphSAGE network optimization
  - MPS/Supply Plan (tactical): Daily — Plan of Record refresh from latest forecasts
  - Execution (operational): Hourly — TRM decision cycle at each site

Each tier reads the output of the tier above:
  S&OP policy parameters θ → MPS/Supply plan quantities → TRM execution decisions

The cascade also triggers:
  - Forecast exception detection after each MPS refresh
  - ERP baseline comparison update after plan changes
  - Decision Stream digest invalidation
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def register_planning_cascade_jobs(scheduler_service):
    """Register planning cascade jobs with the APScheduler service."""

    # S&OP: Weekly (Monday 6am) — strategic network planning
    scheduler_service.add_job(
        func=_run_sop_cycle,
        trigger="cron",
        day_of_week="mon",
        hour=6,
        minute=0,
        id="planning_cascade_sop",
        name="S&OP Weekly Planning Cycle",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Registered S&OP weekly planning job (Monday 6am)")

    # MPS/Supply Plan: Daily (5am) — tactical plan refresh
    scheduler_service.add_job(
        func=_run_mps_refresh,
        trigger="cron",
        hour=5,
        minute=0,
        id="planning_cascade_mps",
        name="MPS Daily Plan Refresh",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    logger.info("Registered MPS daily refresh job (5am)")

    # Execution: Every 4 hours — TRM decision cycle
    scheduler_service.add_job(
        func=_run_execution_cycle,
        trigger="interval",
        hours=4,
        id="planning_cascade_execution",
        name="Execution TRM Decision Cycle",
        replace_existing=True,
        misfire_grace_time=900,
    )
    logger.info("Registered execution cycle job (every 4 hours)")

    # Forecast exception check: Daily (6am, after MPS)
    scheduler_service.add_job(
        func=_run_forecast_exception_check,
        trigger="cron",
        hour=6,
        minute=0,
        id="planning_cascade_exceptions",
        name="Forecast Exception Detection",
        replace_existing=True,
        misfire_grace_time=1800,
    )
    logger.info("Registered forecast exception check job (6am)")


def _get_active_configs():
    """Get all active supply chain configs across all tenants."""
    from app.db.session import sync_session_factory
    from app.models.supply_chain_config import SupplyChainConfig

    db = sync_session_factory()
    try:
        configs = db.query(SupplyChainConfig).filter(
            SupplyChainConfig.is_active == True,
            SupplyChainConfig.mode == "production",
        ).all()
        return [(c.id, c.tenant_id, c.name) for c in configs]
    finally:
        db.close()


def _run_sop_cycle():
    """Weekly S&OP cycle: run GraphSAGE inference for network optimization."""
    configs = _get_active_configs()
    logger.info("S&OP cycle: processing %d active configs", len(configs))

    for config_id, tenant_id, name in configs:
        try:
            from app.db.session import sync_session_factory
            db = sync_session_factory()
            try:
                # GraphSAGE S&OP inference would run here
                # For now, log the execution
                logger.info("S&OP cycle: config %d (%s) — GraphSAGE inference", config_id, name)
            finally:
                db.close()
        except Exception as e:
            logger.warning("S&OP cycle failed for config %d: %s", config_id, e)


def _run_mps_refresh():
    """Daily MPS refresh: regenerate Plan of Record from latest forecasts."""
    from app.db.session import sync_session_factory
    from sqlalchemy import text

    configs = _get_active_configs()
    logger.info("MPS refresh: processing %d active configs", len(configs))

    for config_id, tenant_id, name in configs:
        try:
            db = sync_session_factory()
            try:
                # Refresh Plan of Record from latest forecast P50
                db.execute(text("""
                    DELETE FROM supply_plan
                    WHERE config_id = :cfg AND plan_version = 'live' AND source = 'plan_of_record'
                """), {"cfg": config_id})

                result = db.execute(text("""
                    INSERT INTO supply_plan
                        (config_id, product_id, site_id, plan_date, plan_type,
                         forecast_quantity, demand_quantity, planned_order_quantity,
                         planned_order_date, plan_version, source, planner_name, created_dttm)
                    SELECT
                        f.config_id, f.product_id, CAST(f.site_id AS INTEGER),
                        date_trunc('week', f.forecast_date)::date, 'demand_plan',
                        SUM(f.forecast_p50), SUM(f.forecast_p50), SUM(f.forecast_p50),
                        date_trunc('week', f.forecast_date)::date,
                        'live', 'plan_of_record', 'demand_agent', NOW()
                    FROM forecast f
                    WHERE f.config_id = :cfg AND f.forecast_p50 IS NOT NULL
                    AND f.forecast_date >= CURRENT_DATE - INTERVAL '7 days'
                    AND COALESCE(f.source, '') NOT IN ('disaggregated_ship_to', 'erp_baseline', 'naive_aggregate')
                    GROUP BY f.config_id, f.product_id, f.site_id, date_trunc('week', f.forecast_date)
                """), {"cfg": config_id})

                db.commit()
                logger.info(
                    "MPS refresh: config %d (%s) — %d Plan of Record rows refreshed",
                    config_id, name, result.rowcount,
                )

                # Invalidate Decision Stream cache
                try:
                    from app.services.decision_stream_service import invalidate_digest_cache
                    invalidate_digest_cache(tenant_id=tenant_id)
                except Exception:
                    pass

            finally:
                db.close()
        except Exception as e:
            logger.warning("MPS refresh failed for config %d: %s", config_id, e)


def _run_execution_cycle():
    """TRM execution cycle: run decision cycle at each site."""
    configs = _get_active_configs()
    logger.info("Execution cycle: processing %d active configs", len(configs))

    for config_id, tenant_id, name in configs:
        try:
            # The decision cycle would run SiteAgent.run_decision_cycle()
            # for each internal site in the config.
            # For now, log the execution.
            logger.info("Execution cycle: config %d (%s) — TRM decisions", config_id, name)
        except Exception as e:
            logger.warning("Execution cycle failed for config %d: %s", config_id, e)


def _run_forecast_exception_check():
    """Forecast exception detection + re-evaluation of existing exceptions."""
    from app.db.session import sync_session_factory

    configs = _get_active_configs()
    logger.info("Exception check: processing %d active configs", len(configs))

    for config_id, tenant_id, name in configs:
        try:
            db = sync_session_factory()
            try:
                from app.services.forecast_exception_detector import ForecastExceptionDetector
                from app.core.clock import tenant_today_sync
                from datetime import timedelta

                detector = ForecastExceptionDetector(db)
                # Use tenant's virtual today (frozen for demos)
                period_end = tenant_today_sync(tenant_id, db)
                period_start = period_end - timedelta(days=30)

                detected = detector.run_detection(
                    config_id=config_id,
                    period_start=period_start,
                    period_end=period_end,
                )
                reeval = detector.reevaluate_open_exceptions(config_id=config_id)
                db.commit()

                logger.info(
                    "Exception check: config %d — detected=%s, resolved=%d",
                    config_id, detected.get("exceptions_created", 0), reeval.get("resolved", 0),
                )
            finally:
                db.close()
        except Exception as e:
            logger.warning("Exception check failed for config %d: %s", config_id, e)
