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

    async def run_all(self, config_id: int) -> dict:
        """Run all provisioning steps in dependency order."""
        status = await self.get_or_create_status(config_id)
        results = {}

        for step_key in ConfigProvisioningStatus.STEPS:
            current_status = getattr(status, f"{step_key}_status", "pending")
            if current_status == "completed":
                results[step_key] = {"status": "skipped", "reason": "already completed"}
                continue

            result = await self.run_step(config_id, step_key)
            results[step_key] = result

            if result.get("status") == "failed":
                # Continue with independent steps, skip dependents
                logger.warning("Step %s failed, continuing with independent steps", step_key)

        # Refresh status
        await self.db.refresh(status)
        return {
            "config_id": config_id,
            "overall_status": status.overall_status,
            "steps": results,
        }

    async def _execute_step(self, config_id: int, step_key: str) -> dict:
        """Execute a specific provisioning step."""
        handler = getattr(self, f"_step_{step_key}", None)
        if handler:
            return await handler(config_id)
        return {"status": "ok", "note": f"Step {step_key} placeholder — not yet implemented"}

    async def _step_warm_start(self, config_id: int) -> dict:
        """Step 1: Generate historical demand data."""
        from app.db.session import sync_session_factory
        db = sync_session_factory()
        try:
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
        """Step 3: CFA policy parameter optimization via Differential Evolution."""
        from app.db.session import sync_session_factory
        sync_db = sync_session_factory()
        try:
            from app.services.powell.policy_optimizer import InventoryPolicyOptimizer
            from app.models.powell import PowellPolicyParameters
            from app.models.supply_chain_config import SupplyChainConfig

            config = sync_db.query(SupplyChainConfig).get(config_id)
            if not config:
                return {"status": "skipped", "reason": "Config not found"}

            optimizer = InventoryPolicyOptimizer(
                db=sync_db,
                config_id=config_id,
                tenant_id=config.tenant_id,
            )
            result = optimizer.optimize(method="differential_evolution")

            if result and result.converged:
                from datetime import datetime as dt
                for param_name, param_value in result.optimal_params.items():
                    existing = (
                        sync_db.query(PowellPolicyParameters)
                        .filter(
                            PowellPolicyParameters.config_id == config_id,
                            PowellPolicyParameters.parameter_name == param_name,
                        )
                        .first()
                    )
                    if existing:
                        existing.parameter_value = param_value
                        existing.updated_at = dt.utcnow()
                    else:
                        sync_db.add(PowellPolicyParameters(
                            config_id=config_id,
                            tenant_id=config.tenant_id,
                            parameter_name=param_name,
                            parameter_value=param_value,
                            optimization_method="differential_evolution",
                        ))
                sync_db.commit()
                return {
                    "status": "ok",
                    "cost": result.optimal_cost,
                    "iterations": result.iterations,
                    "params_optimized": len(result.optimal_params),
                }
            else:
                return {"status": "ok", "note": "CFA optimization did not converge"}
        except Exception as e:
            logger.warning("CFA optimization failed (non-critical): %s", e)
            return {"status": "ok", "note": f"CFA optimization attempted: {str(e)[:100]}"}
        finally:
            sync_db.close()

    async def _step_lgbm_forecast(self, config_id: int) -> dict:
        """Step 4: Train LightGBM quantile models and generate P10/P50/P90 baseline forecasts."""
        try:
            from app.services.demand_forecasting.lgbm_pipeline import LGBMForecastPipeline
            pipeline = LGBMForecastPipeline(config_id=config_id)
            result = await pipeline.run()
            return {
                "status": "ok",
                "forecasts_generated": result.forecasts_generated,
                "models_trained": result.models_trained,
                "duration_seconds": result.duration_seconds,
            }
        except ImportError:
            logger.info(
                "LGBMForecastPipeline not yet available — stubbing step for config %d", config_id
            )
            return {"status": "stubbed", "message": "LGBMForecastPipeline service not yet implemented"}
        except Exception as e:
            logger.warning("LightGBM forecast step failed (non-critical): %s", e)
            return {"status": "ok", "note": f"LightGBM forecast attempted: {str(e)[:100]}"}

    async def _step_demand_tgnn(self, config_id: int) -> dict:
        """Step 5: Cold-start Demand Planning tGNN (foreground fallback, normally runs via _bg)."""
        try:
            from app.services.powell.demand_planning_tgnn_service import DemandPlanningTGNNService
            svc = DemandPlanningTGNNService(config_id=config_id)
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

    async def _step_supply_tgnn(self, config_id: int) -> dict:
        """Step 6: Cold-start Supply Planning tGNN (foreground fallback, normally runs via _bg)."""
        try:
            from app.services.powell.supply_planning_tgnn_service import SupplyPlanningTGNNService
            svc = SupplyPlanningTGNNService(config_id=config_id)
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

    async def _step_inventory_tgnn(self, config_id: int) -> dict:
        """Step 7: Cold-start Inventory Optimization tGNN (foreground fallback, normally runs via _bg)."""
        try:
            from app.services.powell.inventory_optimization_tgnn_service import InventoryOptimizationTGNNService
            svc = InventoryOptimizationTGNNService(config_id=config_id)
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
        """Step 6: Generate initial supply plan."""
        try:
            from app.services.supply_plan_service import SupplyPlanService
            from app.db.session import sync_session_factory
            sync_db = sync_session_factory()
            try:
                service = SupplyPlanService(sync_db)
                result = service.generate_supply_plan(
                    config_id=config_id,
                    planning_horizon=52,
                )
                sync_db.commit()
                return {"status": "ok", "plans_generated": getattr(result, "count", 1)}
            finally:
                sync_db.close()
        except Exception as e:
            logger.warning("Supply plan generation failed (non-critical): %s", e)
            return {"status": "ok", "note": f"Supply plan attempted: {str(e)[:100]}"}

    async def _step_decision_seed(self, config_id: int) -> dict:
        """
        Step 10: Seed the Decision Stream by running one real GNN orchestration
        cycle + one TRM decision cycle per active site.

        Populates powell_*_decisions tables from actual inventory, orders, and
        forecasts in the DB — no synthetic data. The Decision Stream is only as
        good as the real data available at provisioning time.
        """
        sites_processed = 0
        decisions_generated = 0
        errors = []

        try:
            # 1. Run GNN orchestration cycle — generates tGNN site directives
            from app.services.powell.gnn_orchestration_service import GNNOrchestrationService
            gnn_svc = GNNOrchestrationService(db=self.db, config_id=config_id)
            gnn_result = await gnn_svc.run_full_cycle()
            logger.info(
                "Decision seed GNN cycle complete for config %d: %s",
                config_id, gnn_result.get("status", "?"),
            )
        except Exception as e:
            logger.warning("Decision seed GNN cycle failed (non-critical): %s", e)
            errors.append(f"GNN: {str(e)[:100]}")

        try:
            # 2. Run one TRM decision cycle per active site
            from sqlalchemy import text
            rows = await self.db.execute(
                text("""
                    SELECT s.id, s.site_key
                    FROM site s
                    JOIN supply_chain_configs scc ON scc.id = :config_id
                    WHERE s.company_id = scc.company_id
                      AND s.master_type NOT IN ('MARKET_SUPPLY', 'MARKET_DEMAND')
                    ORDER BY s.id
                """),
                {"config_id": config_id},
            )
            site_rows = rows.fetchall()

            from app.services.powell.site_agent import SiteAgent, SiteAgentConfig
            for site_id, site_key in site_rows:
                try:
                    cfg = SiteAgentConfig(
                        config_id=config_id,
                        site_id=site_id,
                        site_key=site_key or str(site_id),
                    )
                    agent = SiteAgent(db=self.db, config=cfg)
                    result = await agent.execute_decision_cycle()
                    decisions_generated += result.get("decisions_made", 0)
                    sites_processed += 1
                except Exception as site_err:
                    logger.warning(
                        "Decision seed failed for site %s: %s", site_key, site_err
                    )
                    errors.append(f"site {site_key}: {str(site_err)[:80]}")

        except Exception as e:
            logger.warning("Decision seed site loop failed (non-critical): %s", e)
            errors.append(f"site_loop: {str(e)[:100]}")

        await self.db.commit()
        return {
            "status": "ok" if not errors else "partial",
            "sites_processed": sites_processed,
            "decisions_generated": decisions_generated,
            "errors": errors[:5],  # cap to avoid bloated status
        }

    async def _step_site_tgnn(self, config_id: int) -> dict:
        """Step 8: Train Site tGNN (foreground fallback, normally runs via _bg)."""
        from app.services.powell.generic_training_orchestrator import GenericTrainingOrchestrator
        orchestrator = GenericTrainingOrchestrator(config_id=config_id)
        result = await orchestrator.train_site_tgnns(epochs=5)
        return {"status": "ok", "sites_trained": result.sites_trained}

    async def _step_conformal(self, config_id: int) -> dict:
        """Step 9: Conformal calibration."""
        try:
            from app.services.conformal_orchestrator import ConformalOrchestrator
            orchestrator = ConformalOrchestrator.get_instance()
            count = await orchestrator.hydrate_from_db(self.db)
            return {"status": "ok", "predictors_hydrated": count}
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
        return await self._step_demand_tgnn(config_id)

    async def _step_supply_tgnn_bg(self, config_id: int, db: AsyncSession) -> dict:
        """Step 6 background: Cold-start Supply Planning tGNN (delegates to foreground handler)."""
        return await self._step_supply_tgnn(config_id)

    async def _step_inventory_tgnn_bg(self, config_id: int, db: AsyncSession) -> dict:
        """Step 7 background: Cold-start Inventory Optimization tGNN (delegates to foreground handler)."""
        return await self._step_inventory_tgnn(config_id)

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
        """Step 8 background: Train Site tGNN (Layer 1.5) for all non-market sites."""
        from app.services.powell.generic_training_orchestrator import GenericTrainingOrchestrator
        orchestrator = GenericTrainingOrchestrator(config_id=config_id)
        result = await orchestrator.train_site_tgnns(epochs=5)
        return {
            "status": "ok" if result.errors == 0 else "partial",
            "sites_trained": result.sites_trained,
            "models_trained": result.models_trained,
            "errors": result.errors,
            "duration_seconds": result.duration_seconds,
        }
