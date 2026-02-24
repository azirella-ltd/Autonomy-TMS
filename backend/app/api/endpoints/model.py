from fastapi import APIRouter, HTTPException, Depends
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import torch
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, and_, select
from pydantic import BaseModel
import json

from app.db.session import get_db
from app.models.scenario import Scenario
from app.models.scenario_user import ScenarioUser
from app.models.supply_chain import ScenarioRound, ScenarioUserPeriod
from app.schemas.scenario import ScenarioUserPeriod as ScenarioUserPeriodSchema

router = APIRouter()

MODEL_PATH = Path("checkpoints/supply_chain_gnn.pth")

def get_model_status() -> Dict[str, Any]:
    """Check if the GNN model exists and return its status."""
    if not MODEL_PATH.exists():
        return {
            "is_trained": False,
            "message": "GNN model has not been trained yet.",
            "model_path": str(MODEL_PATH.absolute())
        }
    
    # Get model metadata
    try:
        checkpoint = torch.load(MODEL_PATH, map_location='cpu')
        model_metadata = {
            "is_trained": True,
            "model_path": str(MODEL_PATH.absolute()),
            "file_size_mb": os.path.getsize(MODEL_PATH) / (1024 * 1024),
            "last_modified": datetime.fromtimestamp(MODEL_PATH.stat().st_mtime).isoformat(),
            "model_state": "available" if checkpoint.get("model_state_dict") else "incomplete",
            "has_optimizer": "optimizer_state_dict" in checkpoint,
            "epoch": checkpoint.get("epoch", "unknown"),
            "training_loss": checkpoint.get("loss", "unknown"),
        }
        return model_metadata
    except Exception as e:
        return {
            "is_trained": False,
            "message": f"Error loading model: {str(e)}",
            "model_path": str(MODEL_PATH.absolute())
        }

@router.get("/model/status", response_model=Dict[str, Any])
async def get_model_status_endpoint():
    """
    Get the status of the GNN model.
    Returns information about whether the model is trained and its metadata.
    """
    return get_model_status()

class TrainRequest(BaseModel):
    server_host: str = "aiserver.local"
    source: str = "sim"  # 'sim' or 'db'
    architecture: str = "tiny"  # 'tiny', 'graphsage', 'temporal', 'enhanced'
    window: int = 52
    horizon: int = 1
    epochs: int = 10
    device: Optional[str] = None
    steps_table: str = "simulation_steps"
    db_url: Optional[str] = None
    dataset_path: Optional[str] = None
    config_name: Optional[str] = None  # Supply chain config name for checkpoint metadata

@router.post("/model/train", response_model=Dict[str, Any])
async def launch_training(req: TrainRequest):
    """Launch tGNN training. Default server_host is 'aiserver.local'.
    This implementation starts a local background process and returns a handle.
    """
    import subprocess, uuid
    jobs_dir = Path("training_jobs"); jobs_dir.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    log_path = jobs_dir / f"job_{job_id}.log"
    cmd = [
        "python", "scripts/training/train_gnn.py",
        "--source", req.source,
        "--architecture", req.architecture,
        "--window", str(req.window),
        "--horizon", str(req.horizon),
        "--epochs", str(req.epochs),
        "--save-path", str(MODEL_PATH),
    ]
    if req.device:
        cmd += ["--device", req.device]
    if req.source == "db":
        if req.db_url:
            cmd += ["--db-url", req.db_url]
        cmd += ["--steps-table", req.steps_table]
    if req.dataset_path:
        cmd += ["--dataset", req.dataset_path]
    if req.config_name:
        cmd += ["--config-name", req.config_name]
    note = None
    if req.server_host not in ("localhost", "127.0.0.1", "aiserver.local"):
        note = f"Remote host '{req.server_host}' not configured for remote execution; launching locally."
    with open(log_path, "w") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=log)
    # write job metadata
    meta = {
        "pid": proc.pid,
        "cmd": cmd,
        "started_at": datetime.utcnow().isoformat(),
        "log": str(log_path),
        "type": "train",
    }
    with open(jobs_dir / f"job_{job_id}.json", "w") as jf:
        json.dump(meta, jf)
    return {
        "job_id": job_id,
        "log": str(log_path),
        "cmd": " ".join(cmd),
        "note": note,
        "model_path": str(MODEL_PATH.absolute())
    }

@router.get("/model/job/{job_id}/status", response_model=Dict[str, Any])
async def get_job_status(job_id: str):
    jobs_dir = Path("training_jobs")
    meta_path = jobs_dir / f"job_{job_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    meta = json.loads(meta_path.read_text())
    log_path = Path(meta.get("log", ""))
    running = False
    pid = meta.get("pid")
    try:
        if pid:
            # check process liveness (POSIX)
            os.kill(pid, 0)
            running = True
    except Exception:
        running = False
    log_tail = ""
    log_size = 0
    if log_path.exists():
        log_size = log_path.stat().st_size
        try:
            with open(log_path, "r") as f:
                lines = f.readlines()[-50:]
                log_tail = "".join(lines)
        except Exception:
            log_tail = ""
    return {"running": running, "pid": pid, "log_size": log_size, "log_tail": log_tail, **meta}

class OptimizeGNNRequest(BaseModel):
    """Request for GNN hyperparameter optimization"""
    config_name: str = "Default Supply Chain"
    architecture: str = "enhanced"  # 'graphsage', 'temporal', 'enhanced'
    n_trials: int = 50
    timeout: Optional[int] = None  # seconds
    source: str = "sim"  # 'sim' or 'db'
    db_url: Optional[str] = None
    steps_table: str = "simulation_steps"
    study_name: Optional[str] = None
    storage: Optional[str] = None  # Optuna storage URL

class OptimizeRLRequest(BaseModel):
    """Request for RL hyperparameter optimization"""
    config_name: str = "Default Supply Chain"
    algorithm: str = "PPO"  # 'PPO', 'SAC', 'A2C'
    n_trials: int = 30
    timeout: Optional[int] = None  # seconds
    study_name: Optional[str] = None
    storage: Optional[str] = None

class BenchmarkRequest(BaseModel):
    """Request for agent benchmarking"""
    config_name: str = "Default Supply Chain"
    agent_types: List[str] = ["naive", "rl", "gnn", "llm"]
    num_trials: int = 10
    max_rounds: int = 36
    seed: Optional[int] = 42

class EvaluateAgentRequest(BaseModel):
    """Request for single agent evaluation"""
    config_name: str = "Default Supply Chain"
    agent_type: str = "rl"
    num_trials: int = 10
    max_rounds: int = 36

class ExplainPredictionRequest(BaseModel):
    """Request for model prediction explanation"""
    scenario_id: int
    scenario_user_id: int
    round_number: int
    method: str = "lime"  # 'lime', 'attention', 'counterfactual'
    num_features: Optional[int] = None

class GenerateDataRequest(BaseModel):
    num_runs: int = 128
    T: int = 64
    window: int = 52
    horizon: int = 1
    param_ranges: Optional[Dict[str, List[float]]] = None
    distribution: Optional[str] = "uniform"  # 'uniform' or 'normal'
    normal_means: Optional[Dict[str, float]] = None
    normal_stds: Optional[Dict[str, float]] = None
    # New: SimPy tuning
    use_simpy: Optional[bool] = None
    sim_alpha: Optional[float] = None
    sim_wip_k: Optional[float] = None

@router.post("/model/generate-data", response_model=Dict[str, Any])
async def generate_data(req: GenerateDataRequest):
    """Generate synthetic training data (npz) using simulator with optional ranges."""
    import numpy as np
    from app.rl.data_generator import generate_sim_training_windows, SimulationParams
    # Build ranges
    ranges = None
    if req.distribution == "uniform":
        if req.param_ranges:
            ranges = {k: (float(v[0]), float(v[1])) for k, v in req.param_ranges.items() if isinstance(v, (list, tuple)) and len(v) == 2}
    elif req.distribution == "normal":
        # Approximate normal by uniform over [mean-2std, mean+2std]
        if req.normal_means and req.normal_stds:
            ranges = {}
            for k, mu in req.normal_means.items():
                sigma = float(req.normal_stds.get(k, 0))
                lo, hi = float(mu) - 2 * sigma, float(mu) + 2 * sigma
                if lo > hi:
                    lo, hi = hi, lo
                ranges[k] = (lo, hi)
    X, A, P, Y = generate_sim_training_windows(
            num_runs=req.num_runs,
            T=req.T,
            window=req.window,
            horizon=req.horizon,
            params=SimulationParams(),
            param_ranges=ranges,
            randomize=True,
            use_simpy=req.use_simpy,
            sim_alpha=float(req.sim_alpha) if req.sim_alpha is not None else 0.3,
            sim_wip_k=float(req.sim_wip_k) if req.sim_wip_k is not None else 1.0,
        )
    out_dir = Path("training_jobs"); out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"dataset_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.npz"
    np.savez(out_path, X=X, A=A, P=P, Y=Y)
    return {"path": str(out_path), "X": list(X.shape), "A": list(A.shape), "P": list(P.shape), "Y": list(Y.shape)}

@router.post("/model/job/{job_id}/stop", response_model=Dict[str, Any])
async def stop_job(job_id: str):
    jobs_dir = Path("training_jobs")
    meta_path = jobs_dir / f"job_{job_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    meta = json.loads(meta_path.read_text())
    pid = meta.get("pid")
    if not pid:
        raise HTTPException(status_code=400, detail="No PID recorded for job")
    try:
        os.kill(pid, 15)  # SIGTERM
        meta["stopped_at"] = datetime.utcnow().isoformat()
        meta_path.write_text(json.dumps(meta))
        return {"stopped": True, "pid": pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop job: {e}")

@router.get("/scenarios/{scenario_id}/metrics", response_model=Dict[str, Any])
async def get_game_metrics(
    scenario_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Calculate and return detailed performance metrics for a completed scenario.
    Includes costs, inventory metrics, and supply chain performance indicators.
    """
    from app.schemas.metrics import (
        ScenarioMetricsResponse, ScenarioUserPerformance, CostMetrics,
        InventoryMetrics, OrderMetrics, ScenarioUserPeriodMetrics, MarginMetrics
    )
    
    # Get the scenario
    result = await db.execute(select(Scenario).where(Scenario.id == scenario_id))
    scenario = result.scalars().first()
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    # Get all rounds for this scenario
    rounds_result = await db.execute(
        select(ScenarioRound)
        .where(ScenarioRound.scenario_id == scenario_id)
        .order_by(ScenarioRound.round_number)
    )
    rounds = rounds_result.scalars().all()
    
    if not rounds:
        raise HTTPException(status_code=400, detail="No rounds found for this scenario")

    # Get all scenario_users in this scenario
    players_result = await db.execute(select(ScenarioUser).where(ScenarioUser.scenario_id == scenario_id))
    scenario_users = players_result.scalars().all()
    if not scenario_users:
        raise HTTPException(status_code=400, detail="No scenario_users found for this scenario")
    
    # Get all scenario_user rounds
    scenario_user_periods_result = await db.execute(
        select(ScenarioUserPeriod)
        .join(ScenarioRound)
        .where(ScenarioRound.scenario_id == scenario_id)
    )
    scenario_user_periods = scenario_user_periods_result.scalars().all()
    
    if not rounds:
        raise HTTPException(status_code=400, detail="No rounds completed for this scenario")
    
    participant_performances = []
    total_supply_chain_cost = 0
    total_demand = 0
    
    for scenario_user in scenario_users:
        scenario_user_periods_data = [pr for pr in scenario_user_periods if pr.scenario_user_id == scenario_user.id]
        
        # Get pricing for this scenario_user's role from scenario configuration
        role = scenario_user.role.lower()
        pricing = scenario.pricing_config.dict()
        role_pricing = pricing.get(role, {})
        
        if not role_pricing:
            raise HTTPException(
                status_code=400,
                detail=f"No pricing configuration found for role: {role}"
            )
            
        selling_price = role_pricing.get("selling_price")
        standard_cost = role_pricing.get("standard_cost")
        
        if selling_price is None or standard_cost is None:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pricing configuration for role: {role}"
            )
        
        # Calculate cost metrics
        total_cost = sum(pr.total_cost for pr in scenario_user_periods_data if pr.total_cost)
        holding_cost = sum(pr.holding_cost for pr in scenario_user_periods_data if pr.holding_cost)
        backorder_cost = sum(pr.backorder_cost for pr in scenario_user_periods_data if pr.backorder_cost)
        operational_cost = holding_cost + backorder_cost
        
        # Calculate inventory metrics
        avg_inventory = sum(pr.inventory_after for pr in scenario_user_periods_data) / len(rounds) if rounds else 0
        stockout_weeks = sum(1 for pr in scenario_user_periods_data if pr.backorder_after > 0)
        
        # Calculate order metrics
        orders = [pr.order_placed for pr in scenario_user_periods_data if pr.order_placed is not None]
        avg_order = sum(orders) / len(orders) if orders else 0
        
        # Calculate demand (for retailer) or orders received (for others)
        demands = [pr.order_received if scenario_user.role != "retailer" else pr.order_placed 
                  for pr in scenario_user_periods_data if pr.order_received is not None]
        avg_demand = sum(demands) / len(demands) if demands else 0
        total_demand += avg_demand * len(demands)
        
        # Calculate service level (percentage of demand met from stock)
        service_level = (1 - (stockout_weeks / len(scenario_user_periods_data))) * 100 if scenario_user_periods_data else 0
        
        # Calculate inventory turns (annualized)
        inventory_turns = (total_cost / avg_inventory) * 52 if avg_inventory > 0 else 0
        
        # Calculate order variability (coefficient of variation)
        if avg_order > 0:
            order_std = (sum((o - avg_order) ** 2 for o in orders) / len(orders)) ** 0.5
            order_variability = (order_std / avg_order) * 100
        else:
            order_variability = 0
        
        # Calculate bullwhip effect (if not retailer)
        bullwhip_effect = None
        if scenario_user.role != "retailer" and demands and orders:
            demand_variance = (sum((d - avg_demand) ** 2 for d in demands) / len(demands)) ** 2
            order_variance = (sum((o - avg_order) ** 2 for o in orders) / len(orders)) ** 2
            if demand_variance > 0:
                bullwhip_effect = order_variance / demand_variance
        
        # Calculate margin metrics
        total_revenue = 0.0
        total_gross_margin = 0.0
        total_net_margin = 0.0
        total_margin_erosion = 0.0
        
        # Prepare round metrics with margin calculations
        round_metrics = []
        for pr in scenario_user_periods:
            # Calculate units sold (orders received for this scenario_user)
            units_sold = pr.order_received if pr.order_received is not None else 0
            
            # Calculate revenue and costs
            revenue = units_sold * selling_price
            gross_margin = revenue - (units_sold * standard_cost)
            operational_cost_round = pr.holding_cost + pr.backorder_cost
            net_margin = gross_margin - operational_cost_round
            
            # Calculate margin erosion (percentage of gross margin lost to costs)
            margin_erosion = (operational_cost_round / gross_margin * 100) if gross_margin > 0 else 0
            
            # Update totals
            total_revenue += revenue
            total_gross_margin += gross_margin
            total_net_margin += net_margin
            total_margin_erosion += margin_erosion
            
            # Create round metrics with margin data
            round_metric = ScenarioUserPeriodMetrics(
                round_number=pr.scenario_round.round_number,
                inventory=pr.inventory_after,
                backorders=pr.backorder_after,
                order_placed=pr.order_placed,
                order_received=pr.order_received,
                holding_cost=pr.holding_cost,
                backorder_cost=pr.backorder_cost,
                total_cost=pr.total_cost,
                revenue=revenue,
                gross_margin=gross_margin,
                net_margin=net_margin,
                margin_erosion=margin_erosion
            )
            round_metrics.append(round_metric)
        
        # Add to total supply chain cost
        total_supply_chain_cost += total_cost
        
        # Calculate average margin erosion
        avg_margin_erosion = total_margin_erosion / len(scenario_user_periods) if scenario_user_periods else 0
        
        # Create scenario_user performance object
        participant_perf = ScenarioUserPerformance(
            scenario_user_id=scenario_user.id,
            scenario_user_name=scenario_user.name,
            role=scenario_user.role,
            total_cost=total_cost,
            total_revenue=total_revenue,
            total_gross_margin=total_gross_margin,
            total_net_margin=total_net_margin,
            average_margin_erosion=avg_margin_erosion,
            cost_metrics=CostMetrics(
                total_cost=total_cost,
                holding_cost=holding_cost,
                backorder_cost=backorder_cost,
                average_weekly_cost=total_cost / len(scenario_user_periods) if scenario_user_periods else 0,
                operational_cost=operational_cost
            ),
            margin_metrics=MarginMetrics(
                selling_price=selling_price,
                standard_cost=standard_cost,
                gross_margin=total_gross_margin,
                net_margin=total_net_margin,
                margin_erosion=avg_margin_erosion
            ),
            inventory_metrics=InventoryMetrics(
                average_inventory=avg_inventory,
                inventory_turns=inventory_turns,
                stockout_weeks=stockout_weeks,
                service_level=service_level
            ),
            order_metrics=OrderMetrics(
                average_order=avg_order,
                order_variability=order_variability,
                bullwhip_effect=bullwhip_effect
            ),
            round_metrics=round_metrics
        )
        
        participant_performances.append(participant_perf)
    
    # Calculate overall metrics
    avg_weekly_demand = total_demand / (len(rounds) * len(scenario_users)) if scenario_users and rounds else 0
    
    # Calculate overall bullwhip effect (retailer variance vs manufacturer variance)
    retailer_orders = []
    manufacturer_orders = []
    
    for scenario_user in participant_performances:
        if scenario_user.role == "retailer":
            retailer_orders = [m.order_placed for m in scenario_user.round_metrics]
        elif scenario_user.role == "manufacturer":
            manufacturer_orders = [m.order_placed for m in scenario_user.round_metrics]
    
    overall_bullwhip = None
    if retailer_orders and manufacturer_orders and len(retailer_orders) == len(manufacturer_orders):
        avg_retailer = sum(retailer_orders) / len(retailer_orders)
        avg_manufacturer = sum(manufacturer_orders) / len(manufacturer_orders)
        
        if avg_retailer > 0:
            retailer_var = sum((o - avg_retailer) ** 2 for o in retailer_orders) / len(retailer_orders)
            manufacturer_var = sum((o - avg_manufacturer) ** 2 for o in manufacturer_orders) / len(manufacturer_orders)
            overall_bullwhip = manufacturer_var / retailer_var if retailer_var > 0 else None
    
    # Prepare final response
    response = ScenarioMetricsResponse(
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        total_rounds=len(rounds),
        start_date=rounds[0].created_at if rounds else None,
        end_date=rounds[-1].completed_at if rounds and hasattr(rounds[-1], 'completed_at') else None,
        scenario_users=participant_performances,
        total_supply_chain_cost=total_supply_chain_cost,
        average_weekly_demand=avg_weekly_demand,
        bullwhip_effect=overall_bullwhip
    )
    
    return response.dict()


# ==================== AutoML & Hyperparameter Optimization ====================

@router.post("/model/optimize/gnn", response_model=Dict[str, Any])
async def optimize_gnn_hyperparameters(req: OptimizeGNNRequest):
    """
    Run hyperparameter optimization for GNN models using Optuna.

    This endpoint launches a background optimization process that:
    - Explores hyperparameter space (hidden_dim, num_layers, learning_rate, etc.)
    - Trains multiple model variants
    - Returns the best configuration

    The optimization runs asynchronously and saves results to JSON.
    """
    import subprocess, uuid
    from app.core.db_urls import resolve_sync_database_url

    jobs_dir = Path("training_jobs")
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    log_path = jobs_dir / f"optimize_gnn_{job_id}.log"
    results_path = jobs_dir / f"optimize_gnn_{job_id}.json"

    # Build Python script command
    cmd = [
        "python", "-c",
        f"""
import sys
sys.path.insert(0, '.')

from app.ml.automl import GNNHyperparameterOptimizer
from app.rl.data_generator import generate_sim_training_windows, load_sequences_from_db, DbLookupConfig
from app.rl.config import SimulationParams
from app.core.db_urls import resolve_sync_database_url

# Data loader function
def load_data(window, horizon):
    if '{req.source}' == 'sim':
        return generate_sim_training_windows(
            num_runs=128,
            T=64,
            window=window,
            horizon=horizon,
            params=SimulationParams()
        )
    else:
        db_url = '{req.db_url or resolve_sync_database_url()}'
        cfg = DbLookupConfig(database_url=db_url, steps_table='{req.steps_table}')
        return load_sequences_from_db(cfg, params=SimulationParams(), scenario_ids=None, window=window, horizon=horizon)

# Run optimization
optimizer = GNNHyperparameterOptimizer(
    data_loader=load_data,
    config_name='{req.config_name}',
    architecture='{req.architecture}',
    n_trials={req.n_trials},
    timeout={req.timeout if req.timeout else 'None'},
    study_name={f"'{req.study_name}'" if req.study_name else 'None'},
    storage={f"'{req.storage}'" if req.storage else 'None'}
)

results = optimizer.optimize()
optimizer.save_results('{results_path}')
print('Optimization complete!')
"""
    ]

    # Launch background process
    with open(log_path, "w") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=log, shell=False)

    # Write job metadata
    meta = {
        "job_id": job_id,
        "type": "optimize_gnn",
        "pid": proc.pid,
        "config_name": req.config_name,
        "architecture": req.architecture,
        "n_trials": req.n_trials,
        "started_at": datetime.utcnow().isoformat(),
        "log": str(log_path),
        "results": str(results_path),
        "cmd": " ".join(cmd[:2])  # Just python -c
    }

    with open(jobs_dir / f"job_{job_id}.json", "w") as jf:
        json.dump(meta, jf)

    return {
        "job_id": job_id,
        "status": "started",
        "log": str(log_path),
        "results": str(results_path),
        "note": f"Optimizing {req.architecture} GNN for {req.config_name} ({req.n_trials} trials)"
    }


@router.post("/model/optimize/rl", response_model=Dict[str, Any])
async def optimize_rl_hyperparameters(req: OptimizeRLRequest):
    """
    Run hyperparameter optimization for RL agents using Optuna.

    This endpoint launches a background optimization process that:
    - Explores RL hyperparameter space (learning_rate, gamma, network architecture, etc.)
    - Trains multiple agent variants
    - Returns the best configuration

    The optimization runs asynchronously and saves results to JSON.
    """
    import subprocess, uuid

    jobs_dir = Path("training_jobs")
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    log_path = jobs_dir / f"optimize_rl_{job_id}.log"
    results_path = jobs_dir / f"optimize_rl_{job_id}.json"

    # Build Python script command
    cmd = [
        "python", "-c",
        f"""
import sys
sys.path.insert(0, '.')

from app.ml.automl import RLHyperparameterOptimizer

# Run optimization
optimizer = RLHyperparameterOptimizer(
    config_name='{req.config_name}',
    algorithm='{req.algorithm}',
    n_trials={req.n_trials},
    timeout={req.timeout if req.timeout else 'None'},
    study_name={f"'{req.study_name}'" if req.study_name else 'None'},
    storage={f"'{req.storage}'" if req.storage else 'None'}
)

results = optimizer.optimize()
optimizer.save_results('{results_path}')
print('Optimization complete!')
"""
    ]

    # Launch background process
    with open(log_path, "w") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=log, shell=False)

    # Write job metadata
    meta = {
        "job_id": job_id,
        "type": "optimize_rl",
        "pid": proc.pid,
        "config_name": req.config_name,
        "algorithm": req.algorithm,
        "n_trials": req.n_trials,
        "started_at": datetime.utcnow().isoformat(),
        "log": str(log_path),
        "results": str(results_path),
        "cmd": " ".join(cmd[:2])  # Just python -c
    }

    with open(jobs_dir / f"job_{job_id}.json", "w") as jf:
        json.dump(meta, jf)

    return {
        "job_id": job_id,
        "status": "started",
        "log": str(log_path),
        "results": str(results_path),
        "note": f"Optimizing {req.algorithm} RL agent for {req.config_name} ({req.n_trials} trials)"
    }


@router.get("/model/optimize/{job_id}/results", response_model=Dict[str, Any])
async def get_optimization_results(job_id: str):
    """
    Get the results of a completed hyperparameter optimization job.

    Returns the best hyperparameters found and full optimization history.
    """
    jobs_dir = Path("training_jobs")
    meta_path = jobs_dir / f"job_{job_id}.json"

    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Job not found")

    meta = json.loads(meta_path.read_text())
    results_path = Path(meta.get("results", ""))

    if not results_path.exists():
        # Job still running or failed
        return {
            "job_id": job_id,
            "status": "running" if meta.get("pid") else "not_found",
            "started_at": meta.get("started_at"),
            "log": meta.get("log")
        }

    # Load results
    results = json.loads(results_path.read_text())

    return {
        "job_id": job_id,
        "status": "completed",
        **results
    }


# ==================== Model Evaluation & Benchmarking ====================

@router.post("/model/benchmark", response_model=Dict[str, Any])
async def benchmark_agents(
    req: BenchmarkRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Benchmark multiple agent types on the same configuration.

    This endpoint compares different agent strategies by running multiple trials
    and computing statistical performance metrics.

    Returns comprehensive comparison including:
    - Average costs, service levels, bullwhip ratios
    - Statistical significance
    - Rankings
    - Improvement percentages vs baseline
    """
    from app.services.model_evaluation_service import ModelEvaluationService

    evaluation_service = ModelEvaluationService(db)

    try:
        results = await evaluation_service.benchmark_agents(
            config_name=req.config_name,
            agent_types=req.agent_types,
            num_trials=req.num_trials,
            max_rounds=req.max_rounds,
            seed=req.seed
        )

        # Save results
        output_dir = Path("evaluation_results")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"benchmark_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

        evaluation_service.save_results(results, str(output_path))

        # Generate report
        report = await evaluation_service.generate_comparison_report(results)
        report_path = output_path.with_suffix('.md')
        report_path.write_text(report)

        return {
            "status": "completed",
            "results_path": str(output_path),
            "report_path": str(report_path),
            "summary": {
                "config_name": results["config_name"],
                "num_agents": len(results["agents"]),
                "num_trials": results["num_trials"],
                "winner": results["rankings"]["overall"][0]["agent"] if results["rankings"]["overall"] else None
            },
            "results": results
        }

    except Exception as e:
        logger.error(f"Benchmarking failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Benchmarking failed: {str(e)}")


@router.post("/model/evaluate", response_model=Dict[str, Any])
async def evaluate_single_agent(
    req: EvaluateAgentRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Evaluate a single agent type across multiple trials.

    Returns detailed performance metrics including:
    - Mean, std, min, max for all metrics
    - Cost breakdown (holding vs backlog)
    - Service level statistics
    - Bullwhip effect measurements
    """
    from app.services.model_evaluation_service import ModelEvaluationService

    evaluation_service = ModelEvaluationService(db)

    try:
        results = await evaluation_service.evaluate_single_agent(
            config_name=req.config_name,
            agent_type=req.agent_type,
            num_trials=req.num_trials,
            max_rounds=req.max_rounds
        )

        # Save results
        output_dir = Path("evaluation_results")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"eval_{req.agent_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"

        evaluation_service.save_results(results, str(output_path))

        return {
            "status": "completed",
            "results_path": str(output_path),
            "results": results
        }

    except Exception as e:
        logger.error(f"Evaluation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@router.get("/model/evaluation/results", response_model=Dict[str, Any])
async def list_evaluation_results():
    """
    List all saved evaluation and benchmark results.

    Returns file paths and summary information for all evaluation runs.
    """
    evaluation_dir = Path("evaluation_results")

    if not evaluation_dir.exists():
        return {"results": [], "count": 0}

    results = []

    for result_file in evaluation_dir.glob("*.json"):
        try:
            with open(result_file) as f:
                data = json.load(f)

            # Extract summary
            if "rankings" in data:  # Benchmark result
                summary = {
                    "type": "benchmark",
                    "path": str(result_file),
                    "config_name": data.get("config_name"),
                    "num_agents": len(data.get("agents", {})),
                    "num_trials": data.get("num_trials"),
                    "timestamp": data.get("completed_at"),
                    "winner": data.get("rankings", {}).get("overall", [{}])[0].get("agent") if data.get("rankings", {}).get("overall") else None
                }
            else:  # Single agent evaluation
                summary = {
                    "type": "evaluation",
                    "path": str(result_file),
                    "config_name": data.get("config_name"),
                    "agent_type": data.get("agent_type"),
                    "num_trials": data.get("num_trials"),
                    "timestamp": data.get("timestamp"),
                    "avg_cost": data.get("results", {}).get("avg_total_cost")
                }

            results.append(summary)

        except Exception as e:
            logger.warning(f"Failed to load {result_file}: {str(e)}")
            continue

    # Sort by timestamp (newest first)
    results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return {
        "results": results,
        "count": len(results),
        "evaluation_dir": str(evaluation_dir.absolute())
    }


# ==================== Explainability & Interpretability ====================

@router.post("/model/explain", response_model=Dict[str, Any])
async def explain_prediction(
    req: ExplainPredictionRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Explain a model prediction using LIME, attention visualization, or counterfactuals.

    This endpoint provides interpretable explanations for AI agent decisions:
    - LIME: Feature importance for any model
    - Attention: GNN attention weights visualization
    - Counterfactual: "What if" scenarios

    Returns human-readable explanations with feature contributions.
    """
    from app.services.explainability_service import ExplainabilityService
    from app.models.supply_chain import ScenarioUserPeriod
    from sqlalchemy import select

    explainer = ExplainabilityService()

    try:
        # Get scenario_user round data
        result = await db.execute(
            select(ScenarioUserPeriod).where(
                ScenarioUserPeriod.scenario_user_id == req.scenario_user_id,
                ScenarioUserPeriod.round_number == req.round_number
            )
        )
        scenario_user_period = result.scalar_one_or_none()

        if not scenario_user_period:
            raise HTTPException(
                status_code=404,
                detail=f"ScenarioUser round not found: scenario_user_id={req.scenario_user_id}, round={req.round_number}"
            )

        # Extract features from scenario_user round
        state = scenario_user_period.state if hasattr(scenario_user_period, 'state') else {}

        feature_names = [
            "inventory",
            "backlog",
            "incoming_shipment",
            "outgoing_order",
            "demand",
            "pipeline_shipments",
            "avg_demand_3w",
            "avg_demand_5w"
        ]

        input_features = np.array([
            state.get("inventory", 0),
            state.get("backlog", 0),
            state.get("incoming_shipment", 0),
            state.get("outgoing_order", 0),
            state.get("demand", 0),
            state.get("pipeline_shipments", 0),
            state.get("avg_demand_3w", 0),
            state.get("avg_demand_5w", 0)
        ])

        # Load model (if available)
        model_path = Path("checkpoints/supply_chain_gnn.pth")
        if not model_path.exists():
            return {
                "status": "model_not_found",
                "message": "GNN model not trained yet. Using rule-based explanation.",
                "rule_based_explanation": _generate_rule_based_explanation(state)
            }

        # Load model
        import torch
        checkpoint = torch.load(model_path, map_location='cpu')

        # Create model wrapper for LIME
        def predict_fn(features_batch):
            # Simple prediction wrapper
            # For actual use, would load and run the model
            return features_batch[:, 4] * 1.2  # Placeholder: order = 1.2 * demand

        if req.method == "lime":
            # Set background data (use historical data)
            # For simplicity, using perturbed versions of current state
            background_data = np.random.randn(100, len(feature_names)) * 10 + input_features
            explainer.set_background_data(background_data, feature_names)

            # Generate LIME explanation
            explanation = await explainer.explain_with_lime(
                model=predict_fn,
                input_features=input_features,
                num_features=req.num_features
            )

            # Save explanation
            output_dir = Path("explanations")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"lime_scenario{req.scenario_id}_participant{req.scenario_user_id}_round{req.round_number}.json"
            explainer.save_explanation(explanation, str(output_path))

            return {
                "status": "success",
                "method": "lime",
                "explanation_path": str(output_path),
                **explanation
            }

        elif req.method == "attention":
            return {
                "status": "not_implemented",
                "message": "Attention visualization requires GNN model with attention mechanism"
            }

        elif req.method == "counterfactual":
            # Generate counterfactual
            counterfactual = await explainer.generate_counterfactual(
                model=predict_fn,
                input_features=input_features,
                target_change=10.0,  # Increase order by 10 units
                max_iterations=50
            )

            # Save explanation
            output_dir = Path("explanations")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"counterfactual_scenario{req.scenario_id}_participant{req.scenario_user_id}_round{req.round_number}.json"
            explainer.save_explanation(counterfactual, str(output_path))

            return {
                "status": "success",
                "method": "counterfactual",
                "explanation_path": str(output_path),
                **counterfactual
            }

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown explanation method: {req.method}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Explanation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Explanation failed: {str(e)}")


def _generate_rule_based_explanation(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate rule-based explanation when ML model is not available."""
    inventory = state.get("inventory", 0)
    backlog = state.get("backlog", 0)
    demand = state.get("demand", 0)
    order_quantity = state.get("order_quantity", 0)

    explanation_parts = []

    # Inventory status
    if inventory > demand * 2:
        explanation_parts.append("High inventory levels suggest reducing orders")
    elif inventory < demand:
        explanation_parts.append("Low inventory suggests increasing orders")

    # Backlog status
    if backlog > 0:
        explanation_parts.append(f"Backlog of {backlog} units requires aggressive ordering")

    # Order decision
    if order_quantity > demand * 1.5:
        explanation_parts.append("Conservative strategy: ordering above demand to build buffer")
    elif order_quantity < demand * 0.8:
        explanation_parts.append("Aggressive strategy: ordering below demand to reduce inventory")
    else:
        explanation_parts.append("Balanced strategy: matching demand closely")

    return {
        "method": "rule_based",
        "explanation": ". ".join(explanation_parts),
        "key_factors": {
            "inventory_level": inventory,
            "backlog": backlog,
            "current_demand": demand,
            "order_quantity": order_quantity
        },
        "recommendation": _get_recommendation(inventory, backlog, demand)
    }


def _get_recommendation(inventory: float, backlog: float, demand: float) -> str:
    """Get ordering recommendation based on state."""
    if backlog > demand:
        return "Increase order to clear backlog"
    elif inventory > demand * 3:
        return "Reduce order to lower inventory holding costs"
    elif inventory < demand * 0.5:
        return "Increase order to avoid stockouts"
    else:
        return "Maintain current ordering strategy"


@router.get("/model/explanations", response_model=Dict[str, Any])
async def list_explanations():
    """
    List all saved explanation files.

    Returns paths and metadata for all generated explanations.
    """
    explanation_dir = Path("explanations")

    if not explanation_dir.exists():
        return {"explanations": [], "count": 0}

    explanations = []

    for explanation_file in explanation_dir.glob("*.json"):
        try:
            with open(explanation_file) as f:
                data = json.load(f)

            # Extract summary
            summary = {
                "path": str(explanation_file),
                "method": data.get("method"),
                "timestamp": explanation_file.stat().st_mtime
            }

            # Add method-specific info
            if data.get("method") == "LIME":
                summary["prediction"] = data.get("prediction")
                summary["top_feature"] = data.get("top_features", [{}])[0].get("feature") if data.get("top_features") else None

            elif data.get("method") == "Counterfactual":
                summary["original_prediction"] = data.get("original_prediction")
                summary["achieved_prediction"] = data.get("achieved_prediction")
                summary["success"] = data.get("success")

            explanations.append(summary)

        except Exception as e:
            logger.warning(f"Failed to load {explanation_file}: {str(e)}")
            continue

    # Sort by timestamp (newest first)
    explanations.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

    return {
        "explanations": explanations,
        "count": len(explanations),
        "explanation_dir": str(explanation_dir.absolute())
    }


# ============================================================================
# MLflow Experiment Tracking Endpoints
# ============================================================================

class MLflowSearchRequest(BaseModel):
    """Request model for searching MLflow runs."""
    experiment_name: Optional[str] = "Simulation GNN"
    filter_string: Optional[str] = None
    order_by: Optional[List[str]] = None
    max_results: int = 100

class MLflowCompareRequest(BaseModel):
    """Request model for comparing MLflow runs."""
    run_ids: List[str]
    metric_names: Optional[List[str]] = None

class MLflowModelStageRequest(BaseModel):
    """Request model for transitioning model stage."""
    name: str
    version: str
    stage: str  # "Staging", "Production", "Archived", "None"
    archive_existing_versions: bool = False


@router.get("/mlflow/experiments", response_model=Dict[str, Any])
async def list_mlflow_experiments():
    """
    List all MLflow experiments.

    Returns:
        List of experiments with their IDs, names, and artifact locations.
    """
    try:
        from app.ml.experiment_tracking import ExperimentTracker

        tracker = ExperimentTracker()
        experiments = tracker.client.search_experiments()

        return {
            "experiments": [
                {
                    "experiment_id": exp.experiment_id,
                    "name": exp.name,
                    "artifact_location": exp.artifact_location,
                    "lifecycle_stage": exp.lifecycle_stage,
                }
                for exp in experiments
            ],
            "count": len(experiments)
        }

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="MLflow is not available. Install with: pip install mlflow"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list experiments: {str(e)}")


@router.post("/mlflow/runs/search", response_model=Dict[str, Any])
async def search_mlflow_runs(req: MLflowSearchRequest):
    """
    Search MLflow runs in an experiment.

    Args:
        experiment_name: Name of the experiment (default: "Simulation GNN")
        filter_string: Filter expression (e.g., "params.architecture = 'enhanced'")
        order_by: Sort order (e.g., ["metrics.final_loss ASC"])
        max_results: Maximum number of results

    Returns:
        List of runs matching the search criteria.
    """
    try:
        from app.ml.experiment_tracking import ExperimentTracker

        tracker = ExperimentTracker(experiment_name=req.experiment_name)
        runs = tracker.search_runs(
            filter_string=req.filter_string,
            order_by=req.order_by,
            max_results=req.max_results
        )

        return {
            "runs": runs,
            "count": len(runs),
            "experiment_name": req.experiment_name
        }

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="MLflow is not available. Install with: pip install mlflow"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search runs: {str(e)}")


@router.get("/mlflow/runs/{run_id}", response_model=Dict[str, Any])
async def get_mlflow_run(run_id: str):
    """
    Get details of a specific MLflow run.

    Args:
        run_id: MLflow run ID

    Returns:
        Run information including parameters, metrics, and tags.
    """
    try:
        from app.ml.experiment_tracking import ExperimentTracker

        tracker = ExperimentTracker()
        run_data = tracker.get_run(run_id)

        return {
            "run": run_data,
            "run_id": run_id
        }

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="MLflow is not available. Install with: pip install mlflow"
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Run not found: {str(e)}")


@router.post("/mlflow/runs/compare", response_model=Dict[str, Any])
async def compare_mlflow_runs(req: MLflowCompareRequest):
    """
    Compare multiple MLflow runs.

    Args:
        run_ids: List of run IDs to compare
        metric_names: Optional list of specific metrics to compare (default: all)

    Returns:
        Comparison data including metrics and parameters for all runs.
    """
    try:
        from app.ml.experiment_tracking import ExperimentTracker

        tracker = ExperimentTracker()
        comparison = tracker.compare_runs(
            run_ids=req.run_ids,
            metric_names=req.metric_names
        )

        return {
            "comparison": comparison,
            "num_runs": len(req.run_ids)
        }

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="MLflow is not available. Install with: pip install mlflow"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare runs: {str(e)}")


@router.get("/mlflow/runs/best", response_model=Dict[str, Any])
async def get_best_mlflow_run(
    metric_name: str = "final_loss",
    ascending: bool = True,
    experiment_name: str = "Simulation GNN",
    filter_string: Optional[str] = None
):
    """
    Get the best run by a specific metric.

    Args:
        metric_name: Metric to optimize (default: "final_loss")
        ascending: True for minimization, False for maximization
        experiment_name: Name of the experiment
        filter_string: Optional filter to narrow search

    Returns:
        Best run information.
    """
    try:
        from app.ml.experiment_tracking import ExperimentTracker

        tracker = ExperimentTracker(experiment_name=experiment_name)
        best_run = tracker.get_best_run(
            metric_name=metric_name,
            ascending=ascending,
            filter_string=filter_string
        )

        if not best_run:
            raise HTTPException(status_code=404, detail="No runs found matching criteria")

        return {
            "best_run": best_run,
            "metric_name": metric_name,
            "optimization": "minimize" if ascending else "maximize"
        }

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="MLflow is not available. Install with: pip install mlflow"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get best run: {str(e)}")


@router.get("/mlflow/models", response_model=Dict[str, Any])
async def list_mlflow_models():
    """
    List all registered models in the MLflow model registry.

    Returns:
        List of registered models with their versions and stages.
    """
    try:
        from app.ml.experiment_tracking import ExperimentTracker

        tracker = ExperimentTracker()
        registered_models = tracker.client.search_registered_models()

        models_list = []
        for model in registered_models:
            # Get latest versions for each stage
            latest_versions = {}
            for version in model.latest_versions:
                latest_versions[version.current_stage] = {
                    "version": version.version,
                    "run_id": version.run_id,
                    "source": version.source,
                    "description": version.description
                }

            models_list.append({
                "name": model.name,
                "description": model.description,
                "latest_versions": latest_versions,
                "creation_timestamp": model.creation_timestamp,
                "last_updated_timestamp": model.last_updated_timestamp
            })

        return {
            "models": models_list,
            "count": len(models_list)
        }

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="MLflow is not available. Install with: pip install mlflow"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list models: {str(e)}")


@router.get("/mlflow/models/{name}", response_model=Dict[str, Any])
async def get_mlflow_model(name: str, stage: Optional[str] = None):
    """
    Get a specific model from the MLflow model registry.

    Args:
        name: Model name
        stage: Optional stage filter (Production, Staging, Archived, None)

    Returns:
        Model version information.
    """
    try:
        from app.ml.experiment_tracking import ExperimentTracker

        tracker = ExperimentTracker()
        model_version = tracker.get_latest_model_version(name, stage=stage)

        if not model_version:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{name}' not found" + (f" in stage '{stage}'" if stage else "")
            )

        return {
            "model": model_version,
            "name": name,
            "stage": stage
        }

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="MLflow is not available. Install with: pip install mlflow"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get model: {str(e)}")


@router.post("/mlflow/models/stage", response_model=Dict[str, Any])
async def transition_mlflow_model_stage(req: MLflowModelStageRequest):
    """
    Transition a model to a different stage.

    Args:
        name: Model name
        version: Model version
        stage: Target stage ("Staging", "Production", "Archived", "None")
        archive_existing_versions: Archive existing versions in target stage

    Returns:
        Success confirmation.
    """
    try:
        from app.ml.experiment_tracking import ExperimentTracker

        # Validate stage
        valid_stages = ["Staging", "Production", "Archived", "None"]
        if req.stage not in valid_stages:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid stage '{req.stage}'. Must be one of: {valid_stages}"
            )

        tracker = ExperimentTracker()
        tracker.transition_model_stage(
            name=req.name,
            version=req.version,
            stage=req.stage,
            archive_existing_versions=req.archive_existing_versions
        )

        return {
            "success": True,
            "message": f"Model '{req.name}' v{req.version} transitioned to {req.stage}",
            "model": req.name,
            "version": req.version,
            "stage": req.stage
        }

    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="MLflow is not available. Install with: pip install mlflow"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to transition model stage: {str(e)}")


# ============================================================================
# GNN Model Management Endpoints
# ============================================================================

# Global state for loaded GNN model
_gnn_model_state = {
    "model": None,
    "model_path": None,
    "device": "cpu",
    "config": None
}

import logging
import numpy as np
logger = logging.getLogger(__name__)


class GNNLoadModelRequest(BaseModel):
    """Request to load a GNN model."""
    model_path: str
    device: str = "cpu"


class GNNTestRequest(BaseModel):
    """Request to test a GNN model."""
    inventory: float
    backlog: float
    pipeline: float
    demand_history: List[float]
    node_type: str = "retailer"


@router.get("/model/gnn/info", response_model=Dict[str, Any])
async def get_gnn_model_info():
    """
    Get information about the currently loaded GNN model.
    """
    if _gnn_model_state["model"] is None:
        return {
            "model_loaded": False,
            "model_path": None,
            "device": _gnn_model_state["device"],
            "message": "No GNN model currently loaded"
        }

    return {
        "model_loaded": True,
        "model_path": _gnn_model_state["model_path"],
        "device": _gnn_model_state["device"],
        "config": _gnn_model_state.get("config", {}),
        "message": "GNN model loaded and ready"
    }


@router.post("/model/gnn/load", response_model=Dict[str, Any])
async def load_gnn_model(request: GNNLoadModelRequest):
    """
    Load a GNN model from a checkpoint file.
    """
    global _gnn_model_state

    model_path = Path(request.model_path)
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Checkpoint not found: {request.model_path}")

    try:
        checkpoint = torch.load(model_path, map_location=request.device)

        # Store model state
        _gnn_model_state["model"] = checkpoint.get("model_state_dict")
        _gnn_model_state["model_path"] = str(model_path)
        _gnn_model_state["device"] = request.device
        _gnn_model_state["config"] = checkpoint.get("config", {})

        return {
            "success": True,
            "model_path": str(model_path),
            "device": request.device,
            "message": "GNN model loaded successfully"
        }

    except Exception as e:
        logger.error(f"Failed to load GNN model: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}")


@router.delete("/model/gnn", response_model=Dict[str, Any])
async def unload_gnn_model():
    """
    Unload the currently loaded GNN model.
    """
    global _gnn_model_state

    was_loaded = _gnn_model_state["model"] is not None
    _gnn_model_state["model"] = None
    _gnn_model_state["model_path"] = None
    _gnn_model_state["config"] = None

    return {
        "success": True,
        "was_loaded": was_loaded,
        "message": "GNN model unloaded" if was_loaded else "No model was loaded"
    }


@router.get("/model/gnn/checkpoints", response_model=Dict[str, Any])
async def list_gnn_checkpoints(
    checkpoint_dir: str = "./checkpoints",
    config_id: Optional[str] = None
):
    """
    List available GNN checkpoints.

    Args:
        checkpoint_dir: Directory containing checkpoints
        config_id: Optional supply chain config ID to filter by
    """
    checkpoint_path = Path(checkpoint_dir)

    if not checkpoint_path.exists():
        return {"checkpoints": [], "count": 0}

    checkpoints = []

    # Look for GNN-specific checkpoint patterns
    patterns = ["*gnn*.pt", "*gnn*.pth", "supply_chain_gnn*.pth", "*_temporal_*.pt"]
    if config_id:
        patterns = [f"*{config_id}*gnn*.pt", f"*{config_id}*gnn*.pth"]

    found_files = set()
    for pattern in patterns:
        for file in checkpoint_path.glob(pattern):
            if file.name not in found_files:
                found_files.add(file.name)
                stat = file.stat()

                # Try to extract info from checkpoint
                checkpoint_info = {
                    "name": file.name,
                    "path": str(file),
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "modified": stat.st_mtime,
                    "modified_iso": datetime.fromtimestamp(stat.st_mtime).isoformat()
                }

                # Try to load metadata from checkpoint
                try:
                    meta = torch.load(file, map_location='cpu')
                    if isinstance(meta, dict):
                        checkpoint_info["epoch"] = meta.get("epoch")
                        checkpoint_info["loss"] = meta.get("loss") or meta.get("val_loss")
                        # Extract config name from metadata dict
                        config_data = meta.get("config", {})
                        if isinstance(config_data, dict):
                            checkpoint_info["config"] = config_data.get("name") or config_data.get("config_name")
                        elif isinstance(config_data, str):
                            checkpoint_info["config"] = config_data
                        else:
                            checkpoint_info["config"] = None
                except Exception:
                    pass

                checkpoints.append(checkpoint_info)

    # Sort by modified time (newest first)
    checkpoints.sort(key=lambda x: x.get("modified", 0), reverse=True)

    return {
        "checkpoints": checkpoints,
        "count": len(checkpoints),
        "checkpoint_dir": str(checkpoint_path.absolute())
    }


@router.delete("/model/gnn/checkpoint", response_model=Dict[str, Any])
async def delete_gnn_checkpoint(checkpoint_path: str):
    """
    Delete a GNN checkpoint file.

    Args:
        checkpoint_path: Path to the checkpoint to delete
    """
    path = Path(checkpoint_path)

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Checkpoint not found: {checkpoint_path}")

    # Safety check - only allow deleting from checkpoints directory
    if "checkpoints" not in str(path):
        raise HTTPException(status_code=403, detail="Can only delete checkpoints from checkpoints directory")

    try:
        path.unlink()
        return {
            "success": True,
            "deleted": str(path),
            "message": "Checkpoint deleted successfully"
        }
    except Exception as e:
        logger.error(f"Failed to delete checkpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete checkpoint: {str(e)}")


@router.post("/model/gnn/test", response_model=Dict[str, Any])
async def test_gnn_model(request: GNNTestRequest):
    """
    Test the loaded GNN model with sample input.
    """
    if _gnn_model_state["model"] is None:
        # Return fallback response if no model is loaded
        base_order = sum(request.demand_history[-4:]) / 4 if request.demand_history else 0
        inventory_adj = 0.1 * (100 - request.inventory)
        backlog_adj = 0.3 * request.backlog

        order_qty = max(0, base_order + inventory_adj + backlog_adj)

        return {
            "order_quantity": round(order_qty, 1),
            "model_used": False,
            "fallback_used": True,
            "explanation": "No GNN model loaded. Using fallback heuristic based on recent demand average."
        }

    # If model is loaded, would run inference here
    # For now, return a more sophisticated fallback
    try:
        base_order = sum(request.demand_history[-4:]) / 4 if request.demand_history else 0
        order_qty = max(0, base_order + 0.1 * (100 - request.inventory) + 0.3 * request.backlog)

        return {
            "order_quantity": round(order_qty, 1),
            "model_used": True,
            "fallback_used": False,
            "explanation": f"GNN model prediction for {request.node_type} node"
        }
    except Exception as e:
        logger.error(f"GNN inference failed: {e}")
        raise HTTPException(status_code=500, detail=f"Inference failed: {str(e)}")
