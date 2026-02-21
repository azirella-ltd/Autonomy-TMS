"""
Deployment Pipeline Service

Orchestrates the full 7-step demo system build:
  1. Seed Config        → Create/verify SupplyChainConfig
  2. Deterministic Sim  → DAGSimulator (3 strategies × 52 periods)
  3. Stochastic Sim     → DAGSimPySimulator (128 × 52 Monte Carlo)
  4. Convert Data       → SimulationDataConverter → NPZ + TRM records
  5. Train Models       → S&OP GraphSAGE + tGNN + TRMs (BC)
  6. Generate Day 1     → SAPCSVExporter.export_day1()
  7. Generate Day 2     → SAPCSVExporter.export_day2()

Each step reports progress to DeploymentPipelineRun.
Pipeline is resumable from any failed step.
"""

from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deployment_pipeline import DeploymentPipelineRun

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
TRAINING_ROOT = BACKEND_ROOT / "training_jobs"
CHECKPOINT_ROOT = BACKEND_ROOT / "checkpoints" / "supply_chain_configs"
EXPORT_ROOT = BACKEND_ROOT / "exports"


STEP_NAMES = {
    1: "Seed Config",
    2: "Deterministic Simulation",
    3: "Stochastic Monte Carlo",
    4: "Convert Training Data",
    5: "Train Models",
    6: "Generate Day 1 CSVs",
    7: "Generate Day 2 CSVs",
}


class DeploymentPipelineService:
    """
    Orchestrates the demo system deployment pipeline.
    """

    def __init__(self, db: AsyncSession, pipeline_id: int):
        self.db = db
        self.pipeline_id = pipeline_id
        self._pipeline: Optional[DeploymentPipelineRun] = None

    async def run(self) -> DeploymentPipelineRun:
        """Execute the full pipeline (or resume from last failed step)."""
        pipeline = await self._load_pipeline()
        if not pipeline:
            raise ValueError(f"Pipeline {self.pipeline_id} not found")

        pipeline.status = "running"
        pipeline.started_at = pipeline.started_at or datetime.utcnow()
        await self.db.flush()

        params = pipeline.parameters or {}
        results = pipeline.results or {}
        start_step = pipeline.current_step + 1 if pipeline.current_step > 0 else 1

        # Check if we should resume from a failed step
        for step_num in range(start_step, pipeline.total_steps + 1):
            step_status = (pipeline.step_statuses or {}).get(str(step_num), {})
            if step_status.get("status") == "completed":
                continue

            try:
                await self._update_step(pipeline, step_num, "running")

                step_start = time.time()

                if step_num == 1:
                    step_result = await self._step_seed_config(pipeline, params)
                elif step_num == 2:
                    step_result = await self._step_deterministic_sim(pipeline, params)
                elif step_num == 3:
                    step_result = await self._step_stochastic_sim(pipeline, params)
                elif step_num == 4:
                    step_result = await self._step_convert_data(pipeline, params)
                elif step_num == 5:
                    step_result = await self._step_train_models(pipeline, params)
                elif step_num == 6:
                    step_result = await self._step_day1_export(pipeline, params)
                elif step_num == 7:
                    step_result = await self._step_day2_export(pipeline, params)
                else:
                    step_result = {}

                elapsed = time.time() - step_start
                results[f"step_{step_num}"] = step_result

                await self._update_step(
                    pipeline, step_num, "completed",
                    elapsed=elapsed, details=step_result
                )
                pipeline.results = results
                await self.db.flush()

            except Exception as e:
                elapsed = time.time() - step_start
                error_msg = f"Step {step_num} ({STEP_NAMES.get(step_num, '?')}): {str(e)}"
                logger.error(f"Pipeline {self.pipeline_id} failed: {error_msg}")
                logger.error(traceback.format_exc())

                await self._update_step(
                    pipeline, step_num, "failed",
                    elapsed=elapsed, error=str(e)
                )
                pipeline.status = "failed"
                pipeline.error_message = error_msg
                pipeline.error_step = step_num
                pipeline.results = results
                await self.db.flush()
                return pipeline

        # All steps complete
        pipeline.status = "completed"
        pipeline.completed_at = datetime.utcnow()
        pipeline.results = results
        await self.db.flush()

        logger.info(f"Pipeline {self.pipeline_id} completed successfully")
        return pipeline

    # ── Step Implementations ──

    async def _step_seed_config(
        self, pipeline: DeploymentPipelineRun, params: Dict
    ) -> Dict[str, Any]:
        """Step 1: Verify or create the supply chain config."""
        from app.models.supply_chain_config import SupplyChainConfig

        config_name = pipeline.config_template

        result = await self.db.execute(
            select(SupplyChainConfig).where(SupplyChainConfig.name == config_name)
        )
        config = result.scalar_one_or_none()

        if config:
            pipeline.config_id = config.id
            return {
                "config_id": config.id,
                "config_name": config_name,
                "action": "existing",
            }

        # Try to generate Food Distribution config
        if "food" in config_name.lower():
            try:
                from scripts.food_dist_config_generator import generate_food_dist_config
                new_config = await generate_food_dist_config(self.db)
                pipeline.config_id = new_config.id
                await self.db.flush()
                return {
                    "config_id": new_config.id,
                    "config_name": config_name,
                    "action": "created",
                }
            except Exception as e:
                logger.warning(f"Food dist generator failed: {e}")

        raise ValueError(
            f"Config '{config_name}' not found and cannot be auto-generated"
        )

    async def _step_deterministic_sim(
        self, pipeline: DeploymentPipelineRun, params: Dict
    ) -> Dict[str, Any]:
        """Step 2: Run deterministic DAG simulation."""
        from app.services.dag_simulator import (
            DAGSimulator, load_topology, OrderingStrategy
        )

        config_id = pipeline.config_id
        topology = await load_topology(config_id, self.db)

        num_periods = params.get("periods", 52)
        seed = params.get("seed", 42)
        demand_cv = params.get("demand_noise_cv", 0.15)

        strategies = [
            OrderingStrategy.BASE_STOCK,
            OrderingStrategy.CONSERVATIVE,
            OrderingStrategy.PID,
        ]

        det_results = []
        for strategy in strategies:
            sim = DAGSimulator(topology, strategy=strategy)
            result = sim.simulate(
                num_periods=num_periods,
                seed=seed,
                demand_noise_cv=demand_cv,
            )
            det_results.append(result)

        # Store results for later steps
        self._det_results = det_results
        self._topology = topology

        return {
            "strategies": [s.value for s in strategies],
            "periods": num_periods,
            "total_decisions": sum(len(r.decisions) for r in det_results),
            "fill_rates": [r.kpis.fill_rate for r in det_results],
        }

    async def _step_stochastic_sim(
        self, pipeline: DeploymentPipelineRun, params: Dict
    ) -> Dict[str, Any]:
        """Step 3: Run stochastic SimPy Monte Carlo."""
        from app.services.dag_simpy_simulator import (
            DAGSimPySimulator, StochasticConfig
        )
        from app.services.dag_simulator import OrderingStrategy

        if not hasattr(self, '_topology'):
            from app.services.dag_simulator import load_topology
            self._topology = await load_topology(pipeline.config_id, self.db)

        mc_runs = params.get("monte_carlo_runs", 128)
        num_periods = params.get("periods", 52)
        seed = params.get("seed", 42)
        demand_cv = params.get("demand_noise_cv", 0.15)

        stochastic_config = StochasticConfig(
            demand_cv=demand_cv,
            lead_time_cv=0.15,
            supplier_reliability=0.95,
        )
        simpy_sim = DAGSimPySimulator(
            self._topology,
            strategy=OrderingStrategy.BASE_STOCK,
            stochastic_config=stochastic_config,
        )
        mc_result = simpy_sim.run_monte_carlo(
            num_runs=mc_runs,
            num_periods=num_periods,
            seed=seed,
        )

        self._mc_result = mc_result

        return {
            "monte_carlo_runs": mc_runs,
            "periods": num_periods,
            "avg_fill_rate": mc_result.kpi_stats['fill_rate']['mean'],
            "total_decisions": sum(
                len(r.decisions) for r in mc_result.all_results
            ),
        }

    async def _step_convert_data(
        self, pipeline: DeploymentPipelineRun, params: Dict
    ) -> Dict[str, Any]:
        """Step 4: Convert simulation data to training formats."""
        from app.services.simulation_data_converter import SimulationDataConverter
        import re

        window = params.get("window", 52)
        horizon = params.get("horizon", 1)
        slug = re.sub(
            r"[^0-9a-zA-Z]+", "-",
            pipeline.config_template.strip().lower()
        ).strip("-") or "config"

        converter = SimulationDataConverter(window=window, horizon=horizon)

        det_results = getattr(self, '_det_results', [])
        mc_results = getattr(self, '_mc_result', None)
        all_results = det_results + (mc_results.all_results if mc_results else [])

        conversion = converter.convert_multiple(all_results)

        # Save files
        output_dir = TRAINING_ROOT / slug
        output_dir.mkdir(parents=True, exist_ok=True)

        gnn_path = converter.save_npz(
            conversion, output_dir / f"{slug}_gnn_dataset.npz"
        )
        trm_paths = converter.save_trm_records(
            conversion, output_dir / "trm_data"
        )

        # Insert decisions to DB
        await converter.insert_decisions_to_db(
            conversion, self.db, pipeline.config_id
        )
        await self.db.flush()

        self._conversion = conversion

        return {
            "gnn_shape": {
                "X": list(conversion.X.shape),
                "A": list(conversion.A.shape),
                "Y": list(conversion.Y.shape),
            },
            "num_samples": conversion.num_samples,
            "trm_types": {
                k: len(v) for k, v in conversion.trm_records.items()
            },
            "gnn_path": str(gnn_path),
        }

    async def _step_train_models(
        self, pipeline: DeploymentPipelineRun, params: Dict
    ) -> Dict[str, Any]:
        """Step 5: Train S&OP GraphSAGE, Execution tGNN, and TRMs."""
        import re
        slug = re.sub(
            r"[^0-9a-zA-Z]+", "-",
            pipeline.config_template.strip().lower()
        ).strip("-") or "config"

        config_id = pipeline.config_id
        epochs = params.get("epochs", 50)
        results = {"sop": None, "tgnn": None, "trm": {}}

        conversion = getattr(self, '_conversion', None)
        if conversion is None:
            return {"error": "No training data - run step 4 first"}

        # Train S&OP GraphSAGE
        try:
            from app.services.powell.powell_training_service import (
                PowellTrainingService, TrainingData
            )

            training_svc = PowellTrainingService(
                db=self.db, config_id=config_id
            )
            training_data = TrainingData(
                X=conversion.X,
                A=conversion.A,
                Y=conversion.Y,
                num_nodes=conversion.num_sites,
                node_features=conversion.X.shape[-1],
                config_id=config_id,
            )
            sop_result = await training_svc.train_sop_graphsage(training_data)
            results["sop"] = {
                "status": "completed",
                "loss": sop_result.get("final_loss"),
            }
        except Exception as e:
            results["sop"] = {"status": "failed", "error": str(e)}
            logger.warning(f"S&OP training failed: {e}")

        # Train Execution tGNN
        try:
            tgnn_result = await training_svc.train_execution_tgnn(training_data)
            results["tgnn"] = {
                "status": "completed",
                "loss": tgnn_result.get("final_loss"),
            }
        except Exception as e:
            results["tgnn"] = {"status": "failed", "error": str(e)}
            logger.warning(f"tGNN training failed: {e}")

        # Train TRMs via behavioral cloning
        import numpy as np
        import torch
        import torch.nn as nn

        for trm_type, records in conversion.trm_records.items():
            if len(records) < 50:
                results["trm"][trm_type] = {
                    "status": "skipped",
                    "reason": f"Only {len(records)} records",
                }
                continue

            try:
                output_dir = TRAINING_ROOT / slug / "trm_data"
                trm_data_path = output_dir / f"{trm_type}.npz"
                if not trm_data_path.exists():
                    results["trm"][trm_type] = {
                        "status": "skipped",
                        "reason": "No NPZ file",
                    }
                    continue

                data = np.load(str(trm_data_path))
                states = data["states"]
                expert_actions = data["expert_actions"]

                state_dim = states.shape[1]
                model = nn.Sequential(
                    nn.Linear(state_dim, 128),
                    nn.ReLU(),
                    nn.Linear(128, 64),
                    nn.ReLU(),
                    nn.Linear(64, 1),
                )

                optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
                loss_fn = nn.MSELoss()
                states_t = torch.FloatTensor(states)
                targets_t = torch.FloatTensor(expert_actions).unsqueeze(1)

                dataset = torch.utils.data.TensorDataset(states_t, targets_t)
                loader = torch.utils.data.DataLoader(
                    dataset,
                    batch_size=min(64, len(records)),
                    shuffle=True,
                )

                bc_epochs = min(epochs, 100)
                final_loss = 0.0
                for epoch in range(bc_epochs):
                    total_loss = 0.0
                    for batch_s, batch_t in loader:
                        pred = model(batch_s)
                        loss = loss_fn(pred, batch_t)
                        optimizer.zero_grad()
                        loss.backward()
                        optimizer.step()
                        total_loss += loss.item()
                    final_loss = total_loss / len(loader)

                # Save checkpoint
                ckpt_dir = CHECKPOINT_ROOT / slug
                ckpt_dir.mkdir(parents=True, exist_ok=True)
                ckpt_path = ckpt_dir / f"trm_{trm_type}_{config_id}.pt"
                torch.save({
                    "model_state_dict": model.state_dict(),
                    "trm_type": trm_type,
                    "config_id": config_id,
                    "state_dim": state_dim,
                    "num_records": len(records),
                }, str(ckpt_path))

                results["trm"][trm_type] = {
                    "status": "completed",
                    "records": len(records),
                    "final_loss": final_loss,
                    "checkpoint": str(ckpt_path),
                }

            except Exception as e:
                results["trm"][trm_type] = {
                    "status": "failed",
                    "error": str(e),
                }

        return results

    async def _step_day1_export(
        self, pipeline: DeploymentPipelineRun, params: Dict
    ) -> Dict[str, Any]:
        """Step 6: Generate Day 1 SAP CSVs."""
        from app.services.sap_csv_exporter import SAPCSVExporter

        output_dir = EXPORT_ROOT / str(pipeline.config_id)
        exporter = SAPCSVExporter(self.db, pipeline.config_id)
        zip_path = await exporter.export_day1(output_dir)

        return {
            "zip_path": str(zip_path),
            "type": "day1",
        }

    async def _step_day2_export(
        self, pipeline: DeploymentPipelineRun, params: Dict
    ) -> Dict[str, Any]:
        """Step 7: Generate Day 2 delta CSVs."""
        from app.services.sap_csv_exporter import (
            SAPCSVExporter, Day2ScenarioProfile
        )

        output_dir = EXPORT_ROOT / str(pipeline.config_id)
        profile_name = params.get("day2_profile", "mixed")

        profile = Day2ScenarioProfile(name=profile_name)
        exporter = SAPCSVExporter(self.db, pipeline.config_id)
        zip_path = await exporter.export_day2(output_dir, profile=profile)

        return {
            "zip_path": str(zip_path),
            "type": "day2",
            "profile": profile_name,
        }

    # ── Helpers ──

    async def _load_pipeline(self) -> Optional[DeploymentPipelineRun]:
        """Load pipeline from DB."""
        if self._pipeline:
            return self._pipeline

        result = await self.db.execute(
            select(DeploymentPipelineRun)
            .where(DeploymentPipelineRun.id == self.pipeline_id)
        )
        self._pipeline = result.scalar_one_or_none()
        return self._pipeline

    async def _update_step(
        self,
        pipeline: DeploymentPipelineRun,
        step_num: int,
        status: str,
        elapsed: float = 0,
        details: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        """Update step status in pipeline."""
        step_statuses = pipeline.step_statuses or {}
        step_statuses[str(step_num)] = {
            "status": status,
            "name": STEP_NAMES.get(step_num, f"Step {step_num}"),
            "elapsed": round(elapsed, 1),
            "details": details or {},
            "error": error,
            "updated_at": datetime.utcnow().isoformat(),
        }
        pipeline.step_statuses = step_statuses
        pipeline.current_step = step_num
        await self.db.flush()
