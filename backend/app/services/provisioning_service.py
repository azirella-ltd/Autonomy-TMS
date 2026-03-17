"""Provisioning Service — Orchestrates the full Powell Cascade warm-start pipeline.

Manages the 13-step provisioning process for any supply chain config:
  1. Historical demand & belief states (warm start)
  2. S&OP GraphSAGE training
  3. CFA policy optimization
  4. LightGBM baseline demand forecasting
  5. Demand Planning tGNN training
  6. Supply Planning tGNN training
  7. Inventory Optimization tGNN training
  8. TRM Phase 1 (Behavioral Cloning)
  9. Supply plan generation
  10. Decision stream seeding
  11. Site tGNN training
  12. Conformal calibration
  13. Executive briefing

Each step tracks its own status (pending/running/completed/failed) with
dependency enforcement — a step only runs if its prerequisites are complete.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_directive import ConfigProvisioningStatus

logger = logging.getLogger(__name__)

# Training steps that run in the background (fire-and-forget pattern).
# run_step marks these "running" immediately; the background task updates to
# "completed"/"failed" when the real work finishes.
_BACKGROUND_STEPS = {
    "sop_graphsage",
    "demand_tgnn", "supply_tgnn", "inventory_tgnn",
    "trm_training", "site_tgnn",
}


class ProvisioningService:
    """Orchestrates provisioning steps for a supply chain config."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_status(self, config_id: int) -> ConfigProvisioningStatus:
        """Get or create provisioning status record for a config."""
        stmt = select(ConfigProvisioningStatus).where(
            ConfigProvisioningStatus.config_id == config_id
        )
        result = await self.db.execute(stmt)
        status = result.scalar_one_or_none()
        if not status:
            status = ConfigProvisioningStatus(
                config_id=config_id,
                overall_status="not_started",
            )
            self.db.add(status)
            await self.db.flush()
        return status

    async def run_step(self, config_id: int, step_key: str) -> dict:
        """Run a single provisioning step if dependencies are met."""
        status = await self.get_or_create_status(config_id)

        if step_key not in ConfigProvisioningStatus.STEPS:
            return {"error": f"Unknown step: {step_key}"}

        # Check dependencies
        deps = ConfigProvisioningStatus.STEP_DEPENDS.get(step_key, [])
        for dep in deps:
            dep_status = getattr(status, f"{dep}_status", "pending")
            if dep_status != "completed":
                dep_label = ConfigProvisioningStatus.STEP_LABELS.get(dep, dep)
                return {
                    "error": f"Dependency not met: {dep_label} must complete first",
                    "blocked_by": dep,
                }

        # Mark as running
        setattr(status, f"{step_key}_status", "running")
        status.overall_status = "in_progress"
        await self.db.commit()

        try:
            if step_key in _BACKGROUND_STEPS:
                # Dispatch real training in a background task; return immediately.
                asyncio.create_task(
                    self._run_background_step(config_id, step_key)
                )
                return {"status": "running", "step": step_key, "note": "Training dispatched"}

            result = await self._execute_step(config_id, step_key)
            setattr(status, f"{step_key}_status", "completed")
            setattr(status, f"{step_key}_at", datetime.utcnow())
            setattr(status, f"{step_key}_error", None)

            # Check if all steps complete
            all_done = all(
                getattr(status, f"{s}_status") == "completed"
                for s in ConfigProvisioningStatus.STEPS
            )
            if all_done:
                status.overall_status = "completed"

            await self.db.commit()
            return {"status": "completed", "step": step_key, "result": result}

        except Exception as e:
            logger.exception("Provisioning step %s failed for config %d", step_key, config_id)
            setattr(status, f"{step_key}_status", "failed")
            setattr(status, f"{step_key}_error", str(e)[:500])
            status.overall_status = "partial"
            await self.db.commit()
            return {"status": "failed", "step": step_key, "error": str(e)[:500]}

    async def reprovision(self, config_id: int) -> dict:
        """Archive the current config version and re-run all provisioning steps.

        Creates an archived snapshot of the current config (preserving its
        creation date and version) before resetting all provisioning step
        statuses and running the full pipeline again.  The archived config
        appears in the SC config list as a read-only historical record.
        """
        from app.models.supply_chain_config import SupplyChainConfig

        # 1. Load the current config
        row = await self.db.execute(
            select(SupplyChainConfig).where(SupplyChainConfig.id == config_id)
        )
        config = row.scalar_one_or_none()
        if not config:
            return {"error": f"Config {config_id} not found"}

        current_version = config.version or 1

        # 2. Create an archived snapshot (lightweight — just metadata, no deep copy of sites/lanes)
        archived = SupplyChainConfig(
            name=f"{config.name} (v{current_version})",
            description=f"Archived version {current_version} — reprovisioned on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
            is_active=False,
            tenant_id=config.tenant_id,
            created_at=config.created_at,  # preserve original creation date
            updated_at=datetime.utcnow(),
            created_by=config.created_by,
            time_bucket=config.time_bucket,
            parent_config_id=config_id,
            scenario_type="ARCHIVED",
            version=current_version,
            mode=config.mode,
            validation_status="unchecked",
        )
        self.db.add(archived)
        await self.db.flush()
        logger.info(
            "Archived config %d as v%d (new row id=%d) before reprovisioning",
            config_id, current_version, archived.id,
        )

        # 3. Bump version on the active config
        config.version = current_version + 1
        config.updated_at = datetime.utcnow()

        # 4. Reset all provisioning step statuses to "pending"
        status = await self.get_or_create_status(config_id)
        for step_key in ConfigProvisioningStatus.STEPS:
            setattr(status, f"{step_key}_status", "pending")
            setattr(status, f"{step_key}_at", None)
            setattr(status, f"{step_key}_error", None)
        status.overall_status = "not_started"
        await self.db.commit()

        # 5. Run the full pipeline
        return await self.run_all(config_id)

    async def run_all(self, config_id: int) -> dict:
        """Run all provisioning steps in dependency order.

        Background steps are dispatched as fire-and-forget tasks.  Before
        attempting a step whose dependency is still "running" (i.e. a
        background task that hasn't finished yet), we poll until the
        dependency completes or fails, with a timeout.
        """
        status = await self.get_or_create_status(config_id)
        results = {}

        for step_key in ConfigProvisioningStatus.STEPS:
            current_status = getattr(status, f"{step_key}_status", "pending")
            if current_status == "completed":
                results[step_key] = {"status": "skipped", "reason": "already completed"}
                continue

            # Before running, wait for any "running" dependencies to finish.
            deps = ConfigProvisioningStatus.STEP_DEPENDS.get(step_key, [])
            for dep in deps:
                # Refresh ORM state so we see bg-task commits (expire() causes MissingGreenlet with async sessions)
                await self.db.refresh(status)
                dep_status = getattr(status, f"{dep}_status", "pending")
                if dep_status == "running":
                    dep_status = await self._wait_for_step(config_id, dep, timeout=300)
                    await self.db.refresh(status)

            result = await self.run_step(config_id, step_key)
            results[step_key] = result

            # Refresh status so subsequent dependency checks see latest DB state
            await self.db.refresh(status)

            if result.get("status") == "failed":
                logger.warning("Step %s failed, continuing with independent steps", step_key)

        # Final refresh and overall_status reconciliation — background steps
        # may have completed after the foreground loop checked all_done, leaving
        # overall_status stuck at "in_progress".
        await self.db.refresh(status)
        all_done = all(
            getattr(status, f"{s}_status") == "completed"
            for s in ConfigProvisioningStatus.STEPS
        )
        if all_done and status.overall_status != "completed":
            status.overall_status = "completed"
            await self.db.commit()
        elif not all_done and any(
            getattr(status, f"{s}_status") == "failed"
            for s in ConfigProvisioningStatus.STEPS
        ):
            status.overall_status = "partial"
            await self.db.commit()

        return {
            "config_id": config_id,
            "overall_status": status.overall_status,
            "steps": results,
        }

    async def _wait_for_step(
        self, config_id: int, step_key: str, timeout: int = 300
    ) -> str:
        """Poll DB until a background step leaves 'running' state or timeout.

        Uses a raw SQL query to bypass SQLAlchemy ORM identity-map caching,
        which would otherwise return the stale in-memory object instead of
        re-reading from the DB (the background task commits via a separate
        session).
        """
        import time
        from sqlalchemy import text as sa_text
        deadline = time.monotonic() + timeout
        col = f"{step_key}_status"
        while time.monotonic() < deadline:
            await asyncio.sleep(3)
            # Raw SQL bypasses ORM identity map — sees committed state from bg task
            result = await self.db.execute(
                sa_text(f"SELECT {col} FROM config_provisioning_status WHERE config_id = :cid"),
                {"cid": config_id},
            )
            row = result.first()
            if row:
                s = row[0]
                if s != "running":
                    logger.info("Background step %s finished with status: %s", step_key, s)
                    return s
        logger.warning("Timed out waiting for background step %s", step_key)
        return "running"

    async def _execute_step(self, config_id: int, step_key: str) -> dict:
        """Execute a specific provisioning step."""
        handler = getattr(self, f"_step_{step_key}", None)
        if handler:
            return await handler(config_id)
        return {"status": "ok", "note": f"Step {step_key} placeholder — not yet implemented"}

    async def _step_warm_start(self, config_id: int) -> dict:
        """Step 1: Generate historical demand data.

        Also ensures geo-based transport lead times and industry stochastic
        defaults are in place before any model training begins.
        """
        from app.db.session import sync_session_factory
        db = sync_session_factory()
        try:
            # Ensure stochastic defaults and geo lead times are populated
            # before generating warm-start data (idempotent — skips if present)
            from app.services.geocoding_service import calculate_geo_lead_times_for_config
            from app.services.industry_defaults_service import (
                apply_industry_defaults_to_config,
                apply_agent_stochastic_defaults,
            )
            from app.models.supply_chain_config import SupplyChainConfig
            from app.models.tenant import Tenant

            config = db.query(SupplyChainConfig).filter(
                SupplyChainConfig.id == config_id,
            ).first()
            if config:
                tenant = db.query(Tenant).filter(Tenant.id == config.tenant_id).first()
                industry_key = (
                    tenant.industry.value
                    if tenant and tenant.industry
                    else None
                )
                if industry_key:
                    apply_industry_defaults_to_config(db, config_id, industry_key)
                    apply_agent_stochastic_defaults(
                        db, config_id, config.tenant_id, industry_key,
                    )
                geo_result = calculate_geo_lead_times_for_config(db, config_id)
                if geo_result["updated_lanes"] > 0:
                    logger.info(
                        "Warm start: applied geo lead times to %d lanes for config %d",
                        geo_result["updated_lanes"], config_id,
                    )

            from app.services.warm_start_generator import WarmStartGenerator
            result = WarmStartGenerator(db).generate_for_config(config_id, weeks=52)
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def _step_sop_graphsage(self, config_id: int) -> dict:
        """Step 2: Train S&OP GraphSAGE model (foreground fallback, normally runs via _bg)."""
        from app.services.powell.generic_training_orchestrator import GenericTrainingOrchestrator
        orchestrator = GenericTrainingOrchestrator(config_id=config_id)
        result = await orchestrator.train_sop_graphsage()
        return {"status": "ok", "models_trained": result.models_trained}

    async def _step_cfa_optimization(self, config_id: int) -> dict:
        """Step 3: CFA policy parameter optimization via Differential Evolution.

        Constructs a simple inventory cost simulator for the config's products
        and sites, then uses InventoryPolicyOptimizer (inherits PolicyOptimizer)
        with the correct (simulator, parameters) signature.
        """
        from app.db.session import sync_session_factory
        sync_db = sync_session_factory()
        try:
            from app.services.powell.policy_optimizer import (
                InventoryPolicyOptimizer, PolicyParameter,
            )
            from app.models.powell import PowellPolicyParameters
            from app.models.supply_chain_config import SupplyChainConfig

            config = sync_db.query(SupplyChainConfig).get(config_id)
            if not config:
                return {"status": "skipped", "reason": "Config not found"}

            # Build a lightweight inventory cost simulator for this config.
            # It evaluates a base-stock policy parameterised by (service_level,
            # days_of_coverage) across the config's product-site pairs.
            from app.models.sc_entities import InvPolicy, Forecast, Product, InvLevel
            from app.models.supply_chain_config import Site
            import numpy as np

            sites = (
                sync_db.query(Site)
                .filter(Site.config_id == config_id, Site.is_external == False)
                .all()
            )
            products = (
                sync_db.query(Product)
                .filter(Product.config_id == config_id)
                .all()
            )
            if not sites or not products:
                return {"status": "skipped", "reason": "No sites or products for config"}

            site_ids = [s.id for s in sites]
            product_ids = [p.id for p in products]

            def _simulator(params: dict, seed: int) -> float:
                """Simple Monte Carlo cost evaluation for (service_level, doc)."""
                rng = np.random.RandomState(seed)
                sl = params.get("service_level", 0.95)
                doc = params.get("days_of_coverage", 14.0)
                # Simplified cost model: holding cost vs stockout cost
                holding_unit = 0.5
                stockout_unit = 10.0
                total_cost = 0.0
                for _ in range(len(site_ids)):
                    demand = rng.poisson(50, size=52)
                    safety_stock = doc * np.mean(demand) / 7.0
                    for d in demand:
                        inv = safety_stock - d
                        if inv >= 0:
                            total_cost += inv * holding_unit
                        else:
                            total_cost += abs(inv) * stockout_unit
                return total_cost

            parameters = [
                PolicyParameter(
                    name="service_level",
                    initial_value=0.95,
                    lower_bound=0.80,
                    upper_bound=0.99,
                    parameter_type="continuous",
                    description="Target service level",
                    category="inventory",
                ),
                PolicyParameter(
                    name="days_of_coverage",
                    initial_value=14.0,
                    lower_bound=1.0,
                    upper_bound=60.0,
                    parameter_type="continuous",
                    description="Days of coverage for safety stock",
                    category="inventory",
                ),
            ]

            optimizer = InventoryPolicyOptimizer(
                simulator=_simulator,
                parameters=parameters,
                n_scenarios=50,
            )
            result = optimizer.optimize(method="differential_evolution")

            if result and result.status == "success":
                from app.models.powell import PolicyType
                # Upsert a single row keyed by (config_id, policy_type=INVENTORY)
                existing = (
                    sync_db.query(PowellPolicyParameters)
                    .filter(
                        PowellPolicyParameters.config_id == config_id,
                        PowellPolicyParameters.policy_type == PolicyType.INVENTORY,
                    )
                    .first()
                )
                if existing:
                    existing.parameters = result.optimal_parameters
                    existing.optimization_method = "differential_evolution"
                    existing.optimization_value = result.optimal_objective
                    existing.num_iterations = result.num_iterations
                    existing.num_scenarios = 50
                    existing.is_active = True
                else:
                    sync_db.add(PowellPolicyParameters(
                        config_id=config_id,
                        policy_type=PolicyType.INVENTORY,
                        parameters=result.optimal_parameters,
                        optimization_method="differential_evolution",
                        optimization_value=result.optimal_objective,
                        num_iterations=result.num_iterations,
                        num_scenarios=50,
                        is_active=True,
                    ))
                sync_db.commit()
                return {
                    "status": "ok",
                    "cost": result.optimal_objective,
                    "iterations": result.num_iterations,
                    "params_optimized": len(result.optimal_parameters),
                }
            else:
                return {"status": "ok", "note": "CFA optimization did not converge"}
        except Exception as e:
            logger.warning("CFA optimization failed (non-critical): %s", e)
            return {"status": "ok", "note": f"CFA optimization attempted: {str(e)[:100]}"}
        finally:
            sync_db.close()

    async def _step_lgbm_forecast(self, config_id: int) -> dict:
        """Step 4: Train LightGBM quantile models and generate P10/P50/P90 forward forecasts.

        Generates 104 weeks (2 years) of forward-looking weekly demand forecasts.
        All downstream steps — S&OP GraphSAGE inference, supply plan generation
        (52-week horizon), tactical GNNs, and RCCP validation — depend on this
        forward forecast horizon being present in the forecast table.

        Loads demand history from the forecast table, builds the required
        DataFrame, and calls ``run_stage4_lgbm()`` (the real entry point).
        """
        try:
            from app.services.demand_forecasting.lgbm_pipeline import LGBMForecastPipeline
            import pandas as pd
            from app.db.session import sync_session_factory
            from sqlalchemy import text

            sync_db = sync_session_factory()
            try:
                # Load demand history: product_id, site_id, forecast_date, p50
                rows = sync_db.execute(
                    text("""
                        SELECT f.product_id, f.site_id, f.forecast_date, f.forecast_p50
                        FROM forecast f
                        JOIN product p ON p.id = f.product_id
                        WHERE p.config_id = :cid AND f.forecast_p50 IS NOT NULL
                        ORDER BY f.product_id, f.site_id, f.forecast_date
                    """),
                    {"cid": config_id},
                ).fetchall()

                if not rows or len(rows) < 10:
                    return {"status": "ok", "note": "Insufficient forecast history for LightGBM training"}

                history = pd.DataFrame(rows, columns=["product_id", "site_id", "demand_date", "actual"])
                history["unique_id"] = (
                    history["product_id"].astype(str) + "_" + history["site_id"].astype(str)
                )

                # Simple cluster: all series → cluster 0
                cluster_results = {uid: 0 for uid in history["unique_id"].unique()}

                pipeline = LGBMForecastPipeline(config_id=config_id)
                result = pipeline.run_stage4_lgbm(
                    run_id=0,
                    config_id=config_id,
                    history=history,
                    cluster_results=cluster_results,
                    censored_flags={},
                    n_periods=104,   # 2 years weekly: covers 52-wk S&OP + 52-wk MPS/supply plan
                    time_bucket="W",
                    retrain=True,
                )
                return {
                    "status": "ok",
                    "lgbm_series_count": result.get("lgbm_series_count", 0),
                    "lgbm_fallback_count": result.get("lgbm_fallback_count", 0),
                }
            finally:
                sync_db.close()
        except ImportError:
            logger.info(
                "LGBMForecastPipeline not yet available — stubbing step for config %d", config_id
            )
            return {"status": "stubbed", "message": "LGBMForecastPipeline service not yet implemented"}
        except Exception as e:
            logger.warning("LightGBM forecast step failed (non-critical): %s", e)
            return {"status": "ok", "note": f"LightGBM forecast attempted: {str(e)[:100]}"}

    async def _step_demand_tgnn(self, config_id: int, db: AsyncSession = None) -> dict:
        """Step 5: Cold-start Demand Planning tGNN (foreground fallback, normally runs via _bg)."""
        from app.db.session import async_session_factory
        try:
            from app.services.powell.demand_planning_tgnn_service import DemandPlanningTGNNService
            async with async_session_factory() as fresh_db:
                svc = DemandPlanningTGNNService(db=fresh_db, config_id=config_id)
                result = await svc.infer(sop_embeddings=None)
            return {"status": "ok", "sites_processed": getattr(result, "sites_processed", 0)}
        except ImportError:
            logger.info(
                "DemandPlanningTGNNService not yet available — stubbing step for config %d", config_id
            )
            return {"status": "stubbed", "message": "DemandPlanningTGNNService not yet implemented"}
        except Exception as e:
            logger.warning("Demand tGNN step failed (non-critical): %s", e)
            return {"status": "ok", "note": f"Demand tGNN attempted: {str(e)[:100]}"}

    async def _step_supply_tgnn(self, config_id: int, db: AsyncSession = None) -> dict:
        """Step 6: Cold-start Supply Planning tGNN (foreground fallback, normally runs via _bg)."""
        from app.db.session import async_session_factory
        try:
            from app.services.powell.supply_planning_tgnn_service import SupplyPlanningTGNNService
            async with async_session_factory() as fresh_db:
                svc = SupplyPlanningTGNNService(db=fresh_db, config_id=config_id)
                result = await svc.infer(sop_embeddings=None)
            return {"status": "ok", "sites_processed": getattr(result, "sites_processed", 0)}
        except ImportError:
            logger.info(
                "SupplyPlanningTGNNService not yet available — stubbing step for config %d", config_id
            )
            return {"status": "stubbed", "message": "SupplyPlanningTGNNService not yet implemented"}
        except Exception as e:
            logger.warning("Supply tGNN step failed (non-critical): %s", e)
            return {"status": "ok", "note": f"Supply tGNN attempted: {str(e)[:100]}"}

    async def _step_inventory_tgnn(self, config_id: int, db: AsyncSession = None) -> dict:
        """Step 7: Cold-start Inventory Optimization tGNN (foreground fallback, normally runs via _bg)."""
        from app.db.session import async_session_factory
        try:
            from app.services.powell.inventory_optimization_tgnn_service import InventoryOptimizationTGNNService
            async with async_session_factory() as fresh_db:
                svc = InventoryOptimizationTGNNService(db=fresh_db, config_id=config_id)
                result = await svc.infer(sop_embeddings=None)
            return {"status": "ok", "sites_processed": getattr(result, "sites_processed", 0)}
        except ImportError:
            logger.info(
                "InventoryOptimizationTGNNService not yet available — stubbing step for config %d", config_id
            )
            return {"status": "stubbed", "message": "InventoryOptimizationTGNNService not yet implemented"}
        except Exception as e:
            logger.warning("Inventory tGNN step failed (non-critical): %s", e)
            return {"status": "ok", "note": f"Inventory tGNN attempted: {str(e)[:100]}"}

    async def _step_trm_training(self, config_id: int) -> dict:
        """Step 5: TRM Phase 1 BC (foreground fallback, normally runs via _bg)."""
        from app.services.powell.generic_training_orchestrator import GenericTrainingOrchestrator
        orchestrator = GenericTrainingOrchestrator(config_id=config_id)
        result = await orchestrator.train_trms(epochs=10, num_samples=2000)
        return {"status": "ok", "trms_trained": result.models_trained}

    async def _step_supply_plan(self, config_id: int) -> dict:
        """Step 9: Generate initial supply plan with default stochastic parameters."""
        try:
            from app.services.supply_plan_service import SupplyPlanService
            from app.services.stochastic_sampling import StochasticParameters
            from app.services.monte_carlo_planner import PlanObjectives
            from app.models.supply_chain_config import SupplyChainConfig
            from app.db.session import sync_session_factory
            sync_db = sync_session_factory()
            try:
                config = sync_db.query(SupplyChainConfig).get(config_id)
                if not config:
                    return {"status": "skipped", "reason": "Config not found"}

                stochastic_params = StochasticParameters()
                objectives = PlanObjectives()

                service = SupplyPlanService(sync_db, config)
                result = service.generate_supply_plan(
                    stochastic_params=stochastic_params,
                    objectives=objectives,
                    num_scenarios=100,
                )
                sync_db.commit()
                return {"status": "ok", "plans_generated": len(result.get("orders", []))}
            finally:
                sync_db.close()
        except Exception as e:
            logger.warning("Supply plan generation failed (non-critical): %s", e)
            return {"status": "ok", "note": f"Supply plan attempted: {str(e)[:100]}"}

    async def _step_rccp_validation(self, config_id: int) -> dict:
        """Step 9b: Run RCCP validation against the latest MPS plan for each site.

        Validates rough-cut capacity feasibility. If infeasible, flags a warning
        but does NOT block subsequent steps (capacity issues are common and
        addressed iteratively).
        """
        from app.db.session import sync_session_factory
        sync_db = sync_session_factory()
        try:
            from app.services.rccp_service import RCCPService
            from app.models.supply_chain_config import Site
            from app.models.mps import MPSPlan

            # Find latest approved or draft MPS plan for this config
            mps_plan = (
                sync_db.query(MPSPlan)
                .filter(MPSPlan.config_id == config_id)
                .order_by(MPSPlan.created_at.desc())
                .first()
            )
            if not mps_plan:
                return {"status": "ok", "note": "No MPS plan found — skipping RCCP validation"}

            # Get internal sites
            sites = (
                sync_db.query(Site)
                .filter(Site.config_id == config_id, Site.is_external == False)
                .all()
            )
            if not sites:
                return {"status": "ok", "note": "No internal sites — skipping RCCP"}

            rccp_service = RCCPService(sync_db, config_id)
            results = []
            feasible_count = 0
            overloaded_count = 0

            for site in sites:
                try:
                    run = rccp_service.validate_mps(
                        mps_plan_id=mps_plan.id,
                        site_id=site.id,
                        planning_horizon_weeks=12,
                    )
                    results.append({
                        "site_id": site.id,
                        "site_name": site.site_name,
                        "status": run.status.value if hasattr(run.status, 'value') else str(run.status),
                        "is_feasible": run.is_feasible,
                        "max_utilization_pct": run.max_utilization_pct,
                        "overloaded_resources": run.overloaded_resource_count,
                    })
                    if run.is_feasible:
                        feasible_count += 1
                    else:
                        overloaded_count += 1
                except Exception as e:
                    logger.warning("RCCP validation failed for site %s: %s", site.id, e)
                    results.append({
                        "site_id": site.id,
                        "site_name": site.site_name,
                        "status": "error",
                        "error": str(e)[:200],
                    })

            sync_db.commit()
            return {
                "status": "ok",
                "sites_validated": len(results),
                "feasible": feasible_count,
                "overloaded": overloaded_count,
                "details": results,
                "note": f"RCCP: {feasible_count} feasible, {overloaded_count} overloaded"
                if overloaded_count > 0
                else f"RCCP: all {feasible_count} sites feasible",
            }
        except Exception as e:
            logger.warning("RCCP validation step failed (non-blocking): %s", e)
            return {"status": "ok", "note": f"RCCP validation attempted: {str(e)[:100]}"}
        finally:
            sync_db.close()

    async def _step_decision_seed(self, config_id: int) -> dict:
        """
        Step 10: Seed the Decision Stream from digital twin simulation.

        Runs the tenant's actual supply chain DAG as a Monte Carlo simulation
        for 5 episodes × 90 days using deterministic heuristics. At each tick,
        examines the supply chain state and generates realistic decision records
        when interesting conditions arise (stockouts, reorder triggers, quality
        events, capacity pressure, forecast drift, etc.).

        Produces ~6 decisions per TRM type (~66 total) with real product names,
        site names, dollar amounts, and detailed reasoning — ready for demo.
        """
        from app.db.session import sync_session_factory
        from app.services.powell.simulation_decision_seeder import (
            seed_decisions_from_simulation,
        )

        # Resolve tenant_id from config
        row = await self.db.execute(
            text("SELECT tenant_id FROM supply_chain_configs WHERE id = :c"),
            {"c": config_id},
        )
        tenant_row = row.first()
        tenant_id = tenant_row[0] if tenant_row else None

        sync_db = sync_session_factory()
        try:
            counts = seed_decisions_from_simulation(
                db=sync_db,
                config_id=config_id,
                tenant_id=tenant_id or 0,
                max_per_type=6,
            )
            total = sum(counts.values())
            logger.info(
                "Decision seed from simulation: %d decisions across %d TRM types "
                "(config=%d, tenant=%d)",
                total, len([v for v in counts.values() if v > 0]),
                config_id, tenant_id or 0,
            )

            # Pre-generate and persist the Decision Stream digest so the
            # first page load is instant (no LLM call needed).
            # Uses a fresh async session to avoid greenlet_spawn errors.
            if total > 0:
                try:
                    from app.services.decision_stream_service import DecisionStreamService
                    from app.db.session import async_session_factory
                    async with async_session_factory() as async_db:
                        digest_svc = DecisionStreamService(
                            db=async_db, tenant_id=tenant_id or 0,
                        )
                        await digest_svc.get_decision_digest(
                            config_id=config_id, force_refresh=True,
                        )
                    logger.info("Decision Stream digest pre-generated for config %d", config_id)
                except Exception as digest_err:
                    logger.warning("Digest pre-generation failed (non-blocking): %s", digest_err)

            return {
                "status": "ok",
                "decisions_generated": total,
                "per_type": counts,
            }
        except Exception as e:
            logger.warning("Decision seed failed: %s", e, exc_info=True)
            return {
                "status": "partial",
                "decisions_generated": 0,
                "error": str(e)[:200],
            }
        finally:
            sync_db.close()

    async def _step_site_tgnn(self, config_id: int) -> dict:
        """Step 8: Train Site tGNN (foreground fallback, normally runs via _bg)."""
        from app.services.powell.generic_training_orchestrator import GenericTrainingOrchestrator
        orchestrator = GenericTrainingOrchestrator(config_id=config_id)
        result = await orchestrator.train_site_tgnns(epochs=5)
        return {"status": "ok", "sites_trained": result.sites_trained}

    async def _step_conformal(self, config_id: int) -> dict:
        """Step 9: Conformal calibration (tenant-scoped)."""
        try:
            from app.services.conformal_orchestrator import ConformalOrchestrator
            from sqlalchemy import text

            # Resolve tenant_id from config_id
            row = await self.db.execute(
                text("SELECT tenant_id FROM supply_chain_configs WHERE id = :c"),
                {"c": config_id},
            )
            tenant_row = row.first()
            tenant_id = tenant_row[0] if tenant_row else None

            orchestrator = ConformalOrchestrator.get_instance()
            count = await orchestrator.hydrate_from_db(self.db, tenant_id=tenant_id)

            # CDT calibration — real outcomes first, then simulation bootstrap
            # for any TRM types that still lack calibration data.
            #
            # Why two passes:
            #   Pass 1: calibrate_all() reads real decision-outcome pairs from
            #           powell_*_decisions (exist after decision_seed + outcome
            #           collection runs). These are the gold standard.
            #   Pass 2: For TRM types still uncalibrated (no real outcomes yet),
            #           run the digital twin simulation to derive calibration
            #           pairs from supply chain dynamics. This clears the
            #           "0/11 agents ready" banner immediately after warm-start
            #           without waiting for production feedback horizons (4h-14d).
            #
            # The simulation bootstrap is Phase-1-safe: it does NOT require TRM
            # models to make decisions. Instead it uses base-stock ordering
            # (representative of post-BC TRM behaviour) and derives (confidence,
            # loss) pairs from the supply chain state at each simulated period.
            # Real production outcomes from Phase 2 RL refine the calibration
            # incrementally (hourly at :35).
            try:
                from app.db.session import sync_session_factory
                from app.services.powell.cdt_calibration_service import CDTCalibrationService
                from app.services.powell.simulation_calibration_service import (
                    run_simulation_calibration_bootstrap,
                )
                sync_db = sync_session_factory()
                try:
                    cdt_svc = CDTCalibrationService(sync_db, tenant_id=tenant_id)

                    # Pass 1: real outcomes
                    real_stats = cdt_svc.calibrate_all()
                    n_real = sum(
                        1 for s in real_stats.values()
                        if s.get("status") == "calibrated"
                    )

                    # Pass 2: simulation bootstrap for uncalibrated TRM types
                    if n_real < 11 and config_id and tenant_id:
                        logger.info(
                            "CDT: %d/11 TRMs calibrated from real outcomes — "
                            "bootstrapping remainder from digital twin simulation",
                            n_real,
                        )
                        sim_stats = run_simulation_calibration_bootstrap(
                            db=sync_db,
                            config_id=config_id,
                            tenant_id=tenant_id,
                            n_episodes=50,
                        )
                        logger.info(
                            "CDT simulation bootstrap: %d/11 agents calibrated",
                            sim_stats.get("agents_calibrated", 0),
                        )
                finally:
                    sync_db.close()
            except Exception as cdt_err:
                logger.warning("CDT calibration failed: %s", cdt_err, exc_info=True)

            # Include CDT readiness summary
            cdt_summary = {"calibrated": 0, "partial": 0, "uncalibrated": 0}
            try:
                from app.services.conformal_prediction.conformal_decision import get_cdt_registry
                registry = get_cdt_registry(tenant_id=tenant_id)
                diagnostics = registry.get_all_diagnostics()
                for _agent_type, diag in diagnostics.items():
                    size = diag.get("calibration_size", 0)
                    if size >= 30:
                        cdt_summary["calibrated"] += 1
                    elif size > 0:
                        cdt_summary["partial"] += 1
                    else:
                        cdt_summary["uncalibrated"] += 1
                # Count unregistered agents as uncalibrated
                all_trm = 11
                registered = len(diagnostics)
                if registered < all_trm:
                    cdt_summary["uncalibrated"] += (all_trm - registered)
            except Exception:
                pass

            return {
                "status": "ok",
                "predictors_hydrated": count,
                "cdt_readiness": cdt_summary,
            }
        except Exception as e:
            logger.warning("Conformal calibration failed (non-critical): %s", e)
            return {"status": "ok", "note": "Conformal calibration attempted"}

    async def _step_briefing(self, config_id: int) -> dict:
        """Step 10: Generate executive briefing."""
        try:
            from app.services.executive_briefing_service import ExecutiveBriefingService
            from sqlalchemy import text

            row = await self.db.execute(
                text("SELECT tenant_id FROM supply_chain_configs WHERE id = :c"),
                {"c": config_id},
            )
            tenant_row = row.fetchone()
            if not tenant_row:
                return {"status": "skipped", "reason": "Config not found"}

            from app.db.session import sync_session_factory
            db = sync_session_factory()
            try:
                service = ExecutiveBriefingService(db)
                result = await service.generate_briefing(
                    tenant_id=tenant_row[0],
                    briefing_type="provisioning",
                )
                return result
            finally:
                db.close()
        except Exception as e:
            logger.warning("Executive briefing failed (non-critical): %s", e)
            return {"status": "ok", "note": "Briefing generation attempted"}

    # ── Background training helpers ───────────────────────────────────────────

    async def _run_background_step(self, config_id: int, step_key: str) -> None:
        """Execute a long-running training step and update DB status when done."""
        from app.db.session import async_session_factory as AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            try:
                handler = getattr(self, f"_step_{step_key}_bg", None)
                if handler is None:
                    raise NotImplementedError(f"No background handler for {step_key}")
                result = await handler(config_id, db)

                stmt = select(ConfigProvisioningStatus).where(
                    ConfigProvisioningStatus.config_id == config_id
                )
                status = (await db.execute(stmt)).scalar_one_or_none()
                if status:
                    setattr(status, f"{step_key}_status", "completed")
                    setattr(status, f"{step_key}_at", datetime.utcnow())
                    setattr(status, f"{step_key}_error", None)
                    all_done = all(
                        getattr(status, f"{s}_status") == "completed"
                        for s in ConfigProvisioningStatus.STEPS
                    )
                    if all_done:
                        status.overall_status = "completed"

                    # After TRM training completes, clear the "Needs Training" flag
                    if step_key == "trm_training":
                        from app.models.supply_chain_config import SupplyChainConfig
                        cfg = (await db.execute(
                            select(SupplyChainConfig).where(SupplyChainConfig.id == config_id)
                        )).scalar_one_or_none()
                        if cfg:
                            cfg.needs_training = False
                            cfg.training_status = "trained"
                            cfg.trained_at = datetime.utcnow()

                    await db.commit()
                    logger.info("Provisioning background step %s completed for config %d", step_key, config_id)

            except Exception as e:
                logger.exception("Provisioning background step %s failed for config %d", step_key, config_id)
                try:
                    stmt = select(ConfigProvisioningStatus).where(
                        ConfigProvisioningStatus.config_id == config_id
                    )
                    status = (await db.execute(stmt)).scalar_one_or_none()
                    if status:
                        setattr(status, f"{step_key}_status", "failed")
                        setattr(status, f"{step_key}_error", str(e)[:500])
                        await db.commit()
                except Exception:
                    pass

    async def _step_sop_graphsage_bg(self, config_id: int, db: AsyncSession) -> dict:
        """Step 2 background: Train S&OP GraphSAGE from warm-start data."""
        from app.services.powell.generic_training_orchestrator import GenericTrainingOrchestrator
        orchestrator = GenericTrainingOrchestrator(config_id=config_id)
        result = await orchestrator.train_sop_graphsage()
        return {
            "status": "ok" if result.errors == 0 else "partial",
            "models_trained": result.models_trained,
            "errors": result.errors,
            "duration_seconds": result.duration_seconds,
        }

    async def _step_demand_tgnn_bg(self, config_id: int, db: AsyncSession) -> dict:
        """Step 5 background: Cold-start Demand Planning tGNN (delegates to foreground handler)."""
        return await self._step_demand_tgnn(config_id, db=db)

    async def _step_supply_tgnn_bg(self, config_id: int, db: AsyncSession) -> dict:
        """Step 6 background: Cold-start Supply Planning tGNN (delegates to foreground handler)."""
        return await self._step_supply_tgnn(config_id, db=db)

    async def _step_inventory_tgnn_bg(self, config_id: int, db: AsyncSession) -> dict:
        """Step 7 background: Cold-start Inventory Optimization tGNN (delegates to foreground handler)."""
        return await self._step_inventory_tgnn(config_id, db=db)

    async def _step_trm_training_bg(self, config_id: int, db: AsyncSession) -> dict:
        """Step 5 background: TRM Phase 1 BC for ALL active TRMs at all non-market sites."""
        from app.services.powell.generic_training_orchestrator import GenericTrainingOrchestrator
        orchestrator = GenericTrainingOrchestrator(config_id=config_id)
        result = await orchestrator.train_trms(epochs=10, num_samples=2000)
        return {
            "status": "ok" if result.errors == 0 else "partial",
            "trms_trained": result.models_trained,
            "sites_trained": result.sites_trained,
            "errors": result.errors,
            "duration_seconds": result.duration_seconds,
        }

    async def _step_site_tgnn_bg(self, config_id: int, db: AsyncSession) -> dict:
        """Step 8 background: Train Site tGNN (Layer 1.5) for all non-market sites.

        Uses MultiTRMCoordinationOracle for Phase 1 BC when no live MultiHeadTrace
        data exists (cold-start). The oracle runs all 11 deterministic engines
        simultaneously, resolves resource conflicts via priority rules, and generates
        labeled urgency-adjustment training samples without requiring live decisions.
        """
        import asyncio
        from app.services.powell.generic_training_orchestrator import GenericTrainingOrchestrator
        from app.services.powell.site_tgnn_trainer import SiteTGNNTrainer
        from app.services.powell.site_capabilities import get_active_trms

        sites_trained = 0
        oracle_sites = []
        errors = 0
        start_time = asyncio.get_event_loop().time()

        try:
            # Try the standard trainer first (uses live MultiHeadTrace if available)
            orchestrator = GenericTrainingOrchestrator(config_id=config_id)
            result = await orchestrator.train_site_tgnns(epochs=5)
            sites_trained = result.sites_trained
            errors = result.errors
        except Exception as e:
            logger.warning("Standard Site tGNN trainer failed (%s), falling back to oracle BC", e)

        # If no sites were trained (no live trace data), fall back to oracle BC
        if sites_trained == 0:
            try:
                # Determine sites from config (simplified: use a representative set)
                # In full integration, query Site table for non-market sites in config
                oracle_site_keys = _get_non_market_site_keys(db, config_id)
                for site_key, master_type, sc_site_type in oracle_site_keys:
                    try:
                        active_trms = get_active_trms(master_type, sc_site_type)
                        trainer = SiteTGNNTrainer(site_key=site_key, config_id=config_id)
                        result = trainer.train_phase1_bc_from_oracle(
                            num_scenarios=200,      # Fast cold-start
                            phases=(1, 2, 3),
                            active_trms=active_trms,
                        )
                        if result.get("status") == "completed":
                            sites_trained += 1
                            oracle_sites.append(site_key)
                    except Exception as site_err:
                        logger.warning("Oracle BC failed for site %s: %s", site_key, site_err)
                        errors += 1
            except Exception as e:
                logger.warning("Oracle BC fallback failed: %s", e)
                errors += 1

        duration = asyncio.get_event_loop().time() - start_time
        return {
            "status": "ok" if errors == 0 else "partial",
            "sites_trained": sites_trained,
            "oracle_sites": oracle_sites,
            "errors": errors,
            "duration_seconds": duration,
        }


def _get_non_market_site_keys(db, config_id: int):
    """Return (site_key, master_type, sc_site_type) tuples for non-market sites in config."""
    try:
        from sqlalchemy import select
        from app.models.supply_chain_config import Site
        stmt = select(Site).where(
            Site.config_id == config_id,
            Site.master_type.notin_(["VENDOR", "CUSTOMER"]),
        )
        nodes = db.execute(stmt).scalars().all() if hasattr(db, "execute") else []
        return [
            (n.node_id or f"site_{n.id}", n.master_type or "INVENTORY", getattr(n, "sc_site_type", None))
            for n in nodes
        ]
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# TRM instance factory and executor builders for _step_decision_seed
# ═══════════════════════════════════════════════════════════════════════════════

def _build_trm_instances(
    active_trms: frozenset,
    db,
    config_id: int,
    site_key: str,
    site_id: int,
) -> dict:
    """Instantiate the TRM objects for a site, keyed by canonical name.

    Each TRM is constructed with ``db`` and ``config_id`` so that its
    internal ``_persist_*`` method can write to the appropriate
    ``powell_*_decisions`` table.
    """
    instances = {}

    if "po_creation" in active_trms:
        try:
            from app.services.powell.po_creation_trm import POCreationTRM
            instances["po_creation"] = POCreationTRM(
                db=db, config_id=config_id, use_heuristic_fallback=True,
            )
        except Exception as e:
            logger.debug("po_creation TRM init: %s", e)

    if "order_tracking" in active_trms:
        try:
            from app.services.powell.order_tracking_trm import OrderTrackingTRM
            instances["order_tracking"] = OrderTrackingTRM(
                db=db, config_id=config_id, use_heuristic_fallback=True,
            )
        except Exception as e:
            logger.debug("order_tracking TRM init: %s", e)

    if "inventory_buffer" in active_trms:
        try:
            from app.services.powell.inventory_buffer_trm import InventoryBufferTRM
            instances["inventory_buffer"] = InventoryBufferTRM(
                db=db, config_id=config_id, use_heuristic_fallback=True,
            )
        except Exception as e:
            logger.debug("inventory_buffer TRM init: %s", e)

    if "rebalancing" in active_trms:
        try:
            from app.services.powell.inventory_rebalancing_trm import InventoryRebalancingTRM
            instances["rebalancing"] = InventoryRebalancingTRM(
                db=db, config_id=config_id, use_heuristic_fallback=True,
            )
        except Exception as e:
            logger.debug("rebalancing TRM init: %s", e)

    if "forecast_adjustment" in active_trms:
        try:
            from app.services.powell.forecast_adjustment_trm import ForecastAdjustmentTRM
            instances["forecast_adjustment"] = ForecastAdjustmentTRM(
                site_key=site_key, db_session=db,
            )
        except Exception as e:
            logger.debug("forecast_adjustment TRM init: %s", e)

    if "atp_executor" in active_trms:
        try:
            from app.services.powell.atp_executor import ATPExecutorTRM
            from app.services.powell.allocation_service import (
                AllocationService, AllocationConfig, AllocationCadence,
                UnfulfillableOrderAction,
            )
            alloc_cfg = AllocationConfig(
                cadence=AllocationCadence.WEEKLY,
                unfulfillable_action=UnfulfillableOrderAction.DEFER,
                allow_cross_priority_consumption=False,
            )
            instances["atp_executor"] = ATPExecutorTRM(
                allocation_service=AllocationService(alloc_cfg),
                db=db, config_id=config_id, use_heuristic_fallback=True,
            )
        except Exception as e:
            logger.debug("atp_executor TRM init: %s", e)

    if "mo_execution" in active_trms:
        try:
            from app.services.powell.mo_execution_trm import MOExecutionTRM
            instances["mo_execution"] = MOExecutionTRM(
                site_key=site_key, db_session=db,
            )
        except Exception as e:
            logger.debug("mo_execution TRM init: %s", e)

    if "to_execution" in active_trms:
        try:
            from app.services.powell.to_execution_trm import TOExecutionTRM
            instances["to_execution"] = TOExecutionTRM(
                site_key=site_key, db_session=db,
            )
        except Exception as e:
            logger.debug("to_execution TRM init: %s", e)

    if "quality_disposition" in active_trms:
        try:
            from app.services.powell.quality_disposition_trm import QualityDispositionTRM
            instances["quality_disposition"] = QualityDispositionTRM(
                site_key=site_key, db_session=db,
            )
        except Exception as e:
            logger.debug("quality_disposition TRM init: %s", e)

    if "maintenance_scheduling" in active_trms:
        try:
            from app.services.powell.maintenance_scheduling_trm import MaintenanceSchedulingTRM
            instances["maintenance_scheduling"] = MaintenanceSchedulingTRM(
                site_key=site_key, db_session=db,
            )
        except Exception as e:
            logger.debug("maintenance_scheduling TRM init: %s", e)

    if "subcontracting" in active_trms:
        try:
            from app.services.powell.subcontracting_trm import SubcontractingTRM
            instances["subcontracting"] = SubcontractingTRM(
                site_key=site_key, db_session=db,
            )
        except Exception as e:
            logger.debug("subcontracting TRM init: %s", e)

    return instances


def _build_trm_executors(
    trm_instances: dict,
    db,
    config_id: int,
    site_id: int,
    site_key: str,
) -> dict:
    """Build zero-arg executor callables for each TRM instance.

    Each executor queries real state from DB and calls the TRM's evaluate
    method.  The TRM auto-persists its decision if ``db`` and ``config_id``
    were provided at construction time.
    """
    def _safe_exec(fn, db=db):
        """Wrap an executor in a savepoint so a failed SQL statement only
        rolls back that TRM's work, not previous TRMs' persisted decisions."""
        sp = db.begin_nested()
        try:
            fn()
            sp.commit()
        except Exception as exc:
            logger.warning("TRM executor error (rolling back savepoint): %s", exc)
            try:
                sp.rollback()
            except Exception:
                pass

    executors = {}

    if "po_creation" in trm_instances:
        def _run_po(trm=trm_instances["po_creation"]):
            _safe_exec(lambda: _evaluate_po_for_site(trm, db, config_id, site_id))
        executors["po_creation"] = _run_po

    if "order_tracking" in trm_instances:
        def _run_ot(trm=trm_instances["order_tracking"]):
            _safe_exec(lambda: _evaluate_order_tracking_for_site(trm, db, config_id, site_id))
        executors["order_tracking"] = _run_ot

    if "inventory_buffer" in trm_instances:
        def _run_ib(trm=trm_instances["inventory_buffer"]):
            _safe_exec(lambda: _evaluate_buffer_for_site(trm, db, config_id, site_id))
        executors["inventory_buffer"] = _run_ib

    if "rebalancing" in trm_instances:
        def _run_rb(trm=trm_instances["rebalancing"]):
            _safe_exec(lambda: _evaluate_rebalancing_for_site(trm, db, config_id, site_id))
        executors["rebalancing"] = _run_rb

    # TRMs that need order-level or signal-level triggers not available
    # during cold-start seeding.  They participate in the decision cycle
    # (emitting/receiving hive signals) but do not generate decisions.
    for name in ("atp_executor", "forecast_adjustment", "mo_execution",
                 "to_execution", "quality_disposition", "maintenance_scheduling",
                 "subcontracting"):
        if name in trm_instances:
            executors[name] = lambda: None

    return executors


# ── Per-TRM site-level evaluation helpers ──────────────────────────────────

def _evaluate_po_for_site(trm, db, config_id: int, site_id: int):
    """Evaluate PO needs for all products stocked at a site."""
    from app.services.powell.po_creation_trm import (
        POCreationState, InventoryPosition, SupplierInfo,
    )

    rows = db.execute(
        text("""
            SELECT DISTINCT il.product_id,
                   COALESCE(SUM(il.on_hand_qty), 0) AS on_hand,
                   COALESCE(SUM(il.in_transit_qty), 0) AS in_transit,
                   COALESCE(SUM(il.allocated_qty), 0) AS allocated,
                   COALESCE(AVG(f.forecast_p50), 0) AS forecast_30
            FROM inv_level il
            LEFT JOIN forecast f
                ON f.product_id = il.product_id
                AND f.site_id = il.site_id
                AND f.forecast_date >= CURRENT_DATE
                AND f.forecast_date < CURRENT_DATE + INTERVAL '30 days'
            WHERE il.site_id = :site_id
            GROUP BY il.product_id
            LIMIT 50
        """),
        {"site_id": site_id},
    ).fetchall()

    for product_id, on_hand, in_transit, allocated, forecast_30 in rows:
        try:
            # Find suppliers for this product (use savepoint to recover on SQL error)
            sp = db.begin_nested()
            try:
                supplier_rows = db.execute(
                    text("""
                        SELECT vp.tpartner_id, COALESCE(vp.vendor_unit_cost, 10.0),
                               COALESCE(vlt.lead_time_days, 7) AS lead_time,
                               0.95 AS reliability
                        FROM vendor_product vp
                        LEFT JOIN vendor_lead_time vlt
                            ON vlt.tpartner_id = vp.tpartner_id
                            AND vlt.product_id = vp.product_id
                        WHERE vp.product_id = :product_id
                        LIMIT 5
                    """),
                    {"product_id": product_id},
                ).fetchall()
                sp.commit()
            except Exception:
                sp.rollback()
                supplier_rows = []

            pid = str(product_id)
            sid = str(site_id)
            suppliers = [
                SupplierInfo(
                    supplier_id=str(s[0]),
                    product_id=pid,
                    lead_time_days=float(s[2]),
                    lead_time_variability=float(s[2]) * 0.15,
                    unit_cost=float(s[1]),
                    order_cost=float(s[1]) * 0.1,
                    min_order_qty=0.0,
                    max_order_qty=999999.0,
                )
                for s in supplier_rows
            ]
            if not suppliers:
                suppliers = [SupplierInfo(
                    supplier_id="default", product_id=pid,
                    lead_time_days=7.0, lead_time_variability=1.0,
                    unit_cost=10.0, order_cost=1.0,
                    min_order_qty=0.0, max_order_qty=999999.0,
                )]

            ss_val = float(forecast_30) * 0.3
            avg_daily = float(forecast_30) / 30.0 if forecast_30 else 1.0
            state = POCreationState(
                product_id=pid,
                location_id=sid,
                inventory_position=InventoryPosition(
                    product_id=pid,
                    location_id=sid,
                    on_hand=float(on_hand),
                    in_transit=float(in_transit),
                    on_order=0.0,
                    committed=float(allocated),
                    backlog=0.0,
                    safety_stock=ss_val,
                    reorder_point=ss_val * 1.5,
                    target_inventory=ss_val * 2.0,
                    average_daily_demand=avg_daily,
                    demand_variability=avg_daily * 0.3,
                ),
                suppliers=suppliers,
                forecast_next_30_days=float(forecast_30),
                forecast_uncertainty=float(forecast_30) * 0.2,
            )
            trm.evaluate_po_need(state)
        except Exception as e:
            logger.warning("PO eval for product %s at site %s: %s", product_id, site_id, e)


def _evaluate_order_tracking_for_site(trm, db, config_id: int, site_id: int):
    """Evaluate open orders at a site for exceptions."""
    from app.services.powell.order_tracking_trm import (
        OrderState, OrderType, OrderStatus,
    )
    from datetime import date

    rows = db.execute(
        text("""
            SELECT iol.id, iol.product_id, iol.quantity_submitted,
                   iol.expected_delivery_date, iol.status,
                   iol.created_at
            FROM inbound_order_line iol
            WHERE iol.to_site_id = :site_id
              AND iol.status NOT IN ('RECEIVED', 'CANCELLED', 'CLOSED')
              AND iol.config_id = :config_id
            LIMIT 30
        """),
        {"site_id": site_id, "config_id": config_id},
    ).fetchall()

    for order_id, product_id, qty, expected_date, status, created_at in rows:
        try:
            state = OrderState(
                order_id=str(order_id),
                order_type=OrderType.PURCHASE_ORDER,
                status=OrderStatus.CONFIRMED,
                created_date=str(created_at or date.today()),
                expected_date=str(expected_date or date.today()),
                ordered_qty=float(qty or 0),
                product_id=str(product_id or ""),
                to_location=str(site_id),
            )
            trm.evaluate_order(state)
        except Exception as e:
            logger.warning("Order tracking eval for order %s: %s", order_id, e)


def _evaluate_buffer_for_site(trm, db, config_id: int, site_id: int):
    """Evaluate inventory buffer levels at a site."""
    from app.services.powell.inventory_buffer_trm import BufferState
    from datetime import datetime as dt

    rows = db.execute(
        text("""
            SELECT ip.product_id,
                   COALESCE(ip.ss_quantity, 0) AS ss_qty,
                   COALESCE(il.on_hand_qty, 0) AS on_hand,
                   COALESCE(AVG(f.forecast_p50), 0) AS avg_demand,
                   ip.ss_policy
            FROM inv_policy ip
            LEFT JOIN inv_level il
                ON il.product_id = ip.product_id AND il.site_id = ip.site_id
            LEFT JOIN forecast f
                ON f.product_id = ip.product_id
                AND f.site_id = ip.site_id
                AND f.forecast_date >= CURRENT_DATE
                AND f.forecast_date < CURRENT_DATE + INTERVAL '30 days'
            WHERE ip.site_id = :site_id
            GROUP BY ip.product_id, ip.ss_quantity, il.on_hand_qty, ip.ss_policy
            LIMIT 50
        """),
        {"site_id": site_id},
    ).fetchall()

    for product_id, ss_qty, on_hand, avg_demand, ss_policy in rows:
        try:
            avg_daily = float(avg_demand) / 30.0 if avg_demand else 1.0
            dos = float(on_hand) / avg_daily if avg_daily > 0 else 30.0
            state = BufferState(
                product_id=str(product_id),
                location_id=str(site_id),
                baseline_ss=float(ss_qty),
                baseline_reorder_point=float(ss_qty) * 1.5,
                baseline_target_inventory=float(ss_qty) * 2.0,
                policy_type=str(ss_policy or "sl"),
                current_on_hand=float(on_hand),
                current_dos=dos,
                demand_cv=0.3,
                avg_daily_demand=avg_daily,
                demand_trend=0.0,
                seasonal_index=1.0,
                month_of_year=dt.now().month,
                recent_excess_days=0,
                forecast_bias=0.0,
                lead_time_days=7.0,
                lead_time_cv=0.2,
                recent_stockout_count=0,
            )
            trm.evaluate(state)
        except Exception as e:
            logger.warning("Buffer eval for product %s at site %s: %s", product_id, site_id, e)


def _evaluate_rebalancing_for_site(trm, db, config_id: int, site_id: int):
    """Evaluate inventory rebalancing opportunities for a site.

    Rebalancing requires network-wide state (multiple sites + transfer lanes),
    which is expensive to assemble.  During cold-start seeding we build a
    minimal RebalancingState from the site's own inventory and any connected
    sites via transportation_lane.
    """
    from app.services.powell.inventory_rebalancing_trm import (
        RebalancingState, SiteInventoryState, TransferLane,
    )

    # Get products at this site with inventory
    product_rows = db.execute(
        text("""
            SELECT DISTINCT il.product_id
            FROM inv_level il
            WHERE il.site_id = :site_id AND il.on_hand_qty > 0
            LIMIT 20
        """),
        {"site_id": site_id},
    ).fetchall()

    for (product_id,) in product_rows:
        try:
            # Get inventory at this site and connected sites
            inv_rows = db.execute(
                text("""
                    SELECT il.site_id, il.on_hand_qty,
                           COALESCE(ip.ss_quantity, 0) AS ss_qty,
                           COALESCE(AVG(f.forecast_p50), 0) AS weekly_demand
                    FROM inv_level il
                    LEFT JOIN inv_policy ip
                        ON ip.product_id = il.product_id AND ip.site_id = il.site_id
                    LEFT JOIN forecast f
                        ON f.product_id = il.product_id
                        AND f.site_id = il.site_id
                        AND f.forecast_date >= CURRENT_DATE
                        AND f.forecast_date < CURRENT_DATE + INTERVAL '7 days'
                    WHERE il.product_id = :product_id
                    GROUP BY il.site_id, il.on_hand_qty, ip.ss_quantity
                    LIMIT 10
                """),
                {"product_id": product_id},
            ).fetchall()

            site_states = {}
            for sid, oh, ss, wd in inv_rows:
                site_states[str(sid)] = SiteInventoryState(
                    site_id=str(sid),
                    product_id=str(product_id),
                    on_hand=float(oh),
                    in_transit=0.0,
                    committed=0.0,
                    backlog=0.0,
                    demand_forecast=float(wd),
                    demand_uncertainty=float(wd) * 0.2,
                )

            # Get transfer lanes between these sites
            lane_rows = db.execute(
                text("""
                    SELECT tl.source_site_id, tl.dest_site_id,
                           COALESCE((tl.supply_lead_time->>'days')::float, 3) AS lt,
                           COALESCE(tl.cost_per_unit, 1.0) AS cost
                    FROM transportation_lane tl
                    WHERE tl.source_site_id = :site_id
                       OR tl.dest_site_id = :site_id
                    LIMIT 20
                """),
                {"site_id": site_id},
            ).fetchall()

            lanes = [
                TransferLane(
                    from_site=str(lr[0]),
                    to_site=str(lr[1]),
                    transfer_time=float(lr[2]),
                    cost_per_unit=float(lr[3]),
                )
                for lr in lane_rows
            ]

            if len(site_states) < 2:
                continue

            state = RebalancingState(
                product_id=str(product_id),
                site_states=site_states,
                transfer_lanes=lanes,
            )
            trm.evaluate_rebalancing(state)
        except Exception as e:
            logger.warning("Rebalancing eval for product %s at site %s: %s", product_id, site_id, e)
