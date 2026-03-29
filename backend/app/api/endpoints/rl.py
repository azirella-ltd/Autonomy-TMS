"""
API endpoints for RL (Reinforcement Learning) agent management.

Provides endpoints for training, loading, and managing RL agents using Stable-Baselines3.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from pathlib import Path
import logging
import subprocess
import json
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rl", tags=["rl"])


# Request/Response Models
class RLTrainingRequest(BaseModel):
    """Request to start RL training."""
    algorithm: str = Field("PPO", description="RL algorithm: PPO, SAC, A2C")
    supply_chain_config: Optional[str] = Field(None, description="Supply chain config name for checkpoint naming")
    total_timesteps: int = Field(1_000_000, description="Total training timesteps", ge=10000, le=10_000_000)
    device: str = Field("cpu", description="Training device: cuda or cpu")
    n_envs: int = Field(4, description="Number of parallel environments", ge=1, le=16)
    learning_rate: float = Field(3e-4, description="Learning rate", gt=0, le=1)
    batch_size: int = Field(64, description="Batch size", ge=1, le=512)
    n_steps: int = Field(2048, description="Steps per update (PPO only)", ge=128, le=8192)
    gamma: float = Field(0.99, description="Discount factor", gt=0, le=1)
    ent_coef: float = Field(0.01, description="Entropy coefficient", ge=0, le=1)
    max_periods: int = Field(52, description="Max rounds per episode", ge=10, le=200)
    max_order: int = Field(50, description="Max order quantity", ge=10, le=200)
    holding_cost: float = Field(0.5, description="Holding cost per unit", ge=0, le=10)
    backlog_cost: float = Field(1.0, description="Backlog cost per unit", ge=0, le=10)
    checkpoint_dir: str = Field("./checkpoints/rl", description="Checkpoint directory")
    log_dir: str = Field("./logs/rl", description="TensorBoard log directory")
    eval_freq: int = Field(10000, description="Evaluation frequency", ge=1000)
    eval_episodes: int = Field(10, description="Number of evaluation episodes", ge=1, le=100)


class RLTrainingStatus(BaseModel):
    """RL training status."""
    status: str  # "idle", "training", "completed", "failed"
    algorithm: Optional[str] = None
    config: Optional[str] = None  # Supply chain config name
    timesteps: Optional[int] = None
    total_timesteps: Optional[int] = None
    mean_reward: Optional[float] = None
    mean_cost: Optional[float] = None
    episode_length: Optional[float] = None
    message: Optional[str] = None
    metrics: Optional[dict] = None  # Additional metrics dict


class RLModelInfo(BaseModel):
    """RL model information."""
    model_loaded: bool
    model_path: Optional[str] = None
    algorithm: Optional[str] = None
    device: str
    total_timesteps: Optional[int] = None
    use_fallback: bool


class RLLoadModelRequest(BaseModel):
    """Request to load RL model."""
    model_path: str = Field(..., description="Path to RL checkpoint (.zip)")
    device: str = Field("cpu", description="Device for inference: cpu or cuda")


class RLTestRequest(BaseModel):
    """Request to test RL model."""
    inventory: float = Field(..., ge=0)
    backlog: float = Field(..., ge=0)
    incoming_shipment_0: float = Field(..., ge=0)
    incoming_shipment_1: float = Field(..., ge=0)
    incoming_order: float = Field(..., ge=0)
    last_order: float = Field(..., ge=0)
    round_number: int = Field(..., ge=0)
    total_cost: float = Field(..., ge=0)


class RLTestResponse(BaseModel):
    """Response from RL test."""
    order_quantity: int
    model_used: bool
    fallback_used: bool
    explanation: str


class RLEvaluationRequest(BaseModel):
    """Request to evaluate RL model."""
    model_path: str = Field(..., description="Path to model checkpoint")
    n_episodes: int = Field(20, description="Number of evaluation episodes", ge=1, le=100)
    device: str = Field("cpu", description="Device: cpu or cuda")


class RLEvaluationResponse(BaseModel):
    """Response from RL evaluation."""
    mean_cost: float
    std_cost: float
    mean_reward: float
    std_reward: float
    mean_length: float
    episodes: int


# Training status tracking (in-memory for simplicity)
training_status = RLTrainingStatus(status="idle")


@router.post("/train", response_model=RLTrainingStatus)
async def start_training(request: RLTrainingRequest, background_tasks: BackgroundTasks):
    """
    Start RL training in the background.

    The training runs asynchronously, and you can check status with /rl/training-status.
    """
    global training_status

    if training_status.status == "training":
        raise HTTPException(status_code=400, detail="Training already in progress")

    # Validate device and fallback to CPU if CUDA not available
    if request.device == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                logger.warning("CUDA requested but not available, falling back to CPU")
                request.device = "cpu"  # Graceful fallback
                training_status.message = "CUDA not available, using CPU instead"
        except ImportError:
            logger.warning("PyTorch not installed, falling back to CPU")
            request.device = "cpu"  # Graceful fallback
            training_status.message = "PyTorch not installed, using CPU instead"

    # Validate algorithm
    if request.algorithm not in ["PPO", "SAC", "A2C"]:
        raise HTTPException(status_code=400, detail=f"Invalid algorithm: {request.algorithm}")

    # Update status
    training_status.status = "training"
    training_status.algorithm = request.algorithm
    training_status.config = request.supply_chain_config
    training_status.timesteps = 0
    training_status.total_timesteps = request.total_timesteps
    training_status.mean_reward = None
    training_status.mean_cost = None
    training_status.episode_length = None
    training_status.message = "Starting training..."
    training_status.metrics = None

    # Start training in background
    background_tasks.add_task(
        run_training_task,
        request
    )

    return training_status


def run_training_task(request: RLTrainingRequest):
    """Background task to run RL training."""
    global training_status

    try:
        # Build command
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "training" / "train_rl.py"

        cmd = [
            "python",
            str(script_path),
            "--algorithm", request.algorithm,
            "--timesteps", str(request.total_timesteps),
            "--device", request.device,
            "--n-envs", str(request.n_envs),
            "--learning-rate", str(request.learning_rate),
            "--batch-size", str(request.batch_size),
            "--n-steps", str(request.n_steps),
            "--gamma", str(request.gamma),
            "--ent-coef", str(request.ent_coef),
            "--max-rounds", str(request.max_periods),
            "--max-order", str(request.max_order),
            "--holding-cost", str(request.holding_cost),
            "--backlog-cost", str(request.backlog_cost),
            "--checkpoint-dir", request.checkpoint_dir,
            "--log-dir", request.log_dir,
            "--eval-freq", str(request.eval_freq),
            "--eval-episodes", str(request.eval_episodes),
        ]

        # Add config name for checkpoint naming (optional)
        if request.supply_chain_config:
            cmd.extend(["--config-name", request.supply_chain_config])

        logger.info(f"Starting RL training: {' '.join(cmd)}")

        # Run training
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Monitor output
        for line in process.stdout:
            logger.info(f"RL Training: {line.strip()}")

            # Parse training progress from output
            if "total_timesteps" in line:
                try:
                    # Extract timesteps from SB3 output
                    parts = line.split("|")
                    for part in parts:
                        if "total_timesteps" in part:
                            timesteps = int(part.split("|")[1].strip())
                            training_status.timesteps = timesteps
                except:
                    pass

            if "mean_reward" in line or "ep_rew_mean" in line:
                try:
                    # Extract mean reward from SB3 output
                    parts = line.split("|")
                    for i, part in enumerate(parts):
                        if "mean_reward" in part or "ep_rew_mean" in part:
                            if i + 1 < len(parts):
                                reward = float(parts[i + 1].strip())
                                training_status.mean_reward = reward
                                # Cost is negative reward in simulation
                                training_status.mean_cost = abs(reward)
                except:
                    pass

            if "mean_ep_length" in line or "ep_len_mean" in line:
                try:
                    # Extract episode length from SB3 output
                    parts = line.split("|")
                    for i, part in enumerate(parts):
                        if "mean_ep_length" in part or "ep_len_mean" in part:
                            if i + 1 < len(parts):
                                training_status.episode_length = float(parts[i + 1].strip())
                except:
                    pass

        process.wait()

        if process.returncode == 0:
            training_status.status = "completed"
            training_status.message = "Training completed successfully"
            logger.info("RL training completed successfully")
        else:
            stderr = process.stderr.read()
            training_status.status = "failed"
            training_status.message = f"Training failed: {stderr[:200]}"
            logger.error(f"RL training failed: {stderr}")

    except Exception as e:
        training_status.status = "failed"
        training_status.message = f"Training failed: {str(e)}"
        logger.error(f"RL training error: {e}", exc_info=True)


@router.get("/training-status", response_model=RLTrainingStatus)
async def get_training_status():
    """Get current training status."""
    return training_status


@router.post("/load-model", response_model=RLModelInfo)
async def load_model(request: RLLoadModelRequest):
    """Load a trained RL model for inference."""
    model_path = Path(request.model_path)

    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model not found: {request.model_path}")

    try:
        from app.agents.rl_agent import RLAgent

        # Load model
        agent = RLAgent(model_path=str(model_path))

        # Check if model loaded successfully
        if agent.is_trained:
            algorithm = agent.config.algorithm if agent.config else "Unknown"
            total_timesteps = agent.config.total_timesteps if agent.config else None

            return RLModelInfo(
                model_loaded=True,
                model_path=str(model_path),
                algorithm=algorithm,
                device=request.device,
                total_timesteps=total_timesteps,
                use_fallback=False
            )
        else:
            return RLModelInfo(
                model_loaded=False,
                model_path=None,
                algorithm=None,
                device=request.device,
                total_timesteps=None,
                use_fallback=True
            )

    except Exception as e:
        logger.error(f"Failed to load RL model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}")


@router.get("/model-info", response_model=RLModelInfo)
async def get_model_info():
    """Get information about the currently loaded RL model."""
    # For now, return default info
    # In production, you'd maintain a global RL agent instance
    return RLModelInfo(
        model_loaded=False,
        model_path=None,
        algorithm=None,
        device="cpu",
        total_timesteps=None,
        use_fallback=True
    )


@router.get("/checkpoints")
async def list_checkpoints(
    checkpoint_dir: str = "./checkpoints/rl",
    algorithm: Optional[str] = None
):
    """
    List available RL checkpoints.

    Args:
        checkpoint_dir: Directory containing checkpoints
        algorithm: Optional algorithm to filter by (PPO, SAC, A2C)
    """
    checkpoint_path = Path(checkpoint_dir)

    if not checkpoint_path.exists():
        return {"checkpoints": []}

    checkpoints = []
    pattern = f"{algorithm}_*.zip" if algorithm else "*.zip"

    for file in checkpoint_path.glob(pattern):
        stat = file.stat()
        from datetime import datetime

        # Parse checkpoint filename to extract metadata
        # New format: {algorithm}_{config}_{timesteps}.zip or {algorithm}_{config}_final.zip
        # Old format: {algorithm}_{timesteps}.zip or {algorithm}_final.zip
        checkpoint_info = {
            "name": file.name,
            "path": str(file),
            "size": stat.st_size,  # Size in bytes for table display
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "algorithm": None,
            "config": None,
            "timesteps": None,
        }

        # Try to extract metadata from filename
        if "_" in file.stem:
            parts = file.stem.split("_")
            # First part is always algorithm
            checkpoint_info["algorithm"] = parts[0].upper()

            if len(parts) == 2:
                # Old format: {algorithm}_{timesteps} or {algorithm}_final
                if parts[1].isdigit():
                    checkpoint_info["timesteps"] = int(parts[1])
                # If not a digit, could be "final" or unknown
            elif len(parts) >= 3:
                # New format: {algorithm}_{config}_{timesteps} or {algorithm}_{config}_final
                # Config is the middle part(s), last is timesteps/final
                last_part = parts[-1]
                if last_part.isdigit():
                    checkpoint_info["timesteps"] = int(last_part)
                    # Config is everything between algorithm and timesteps
                    checkpoint_info["config"] = "_".join(parts[1:-1])
                else:
                    # Last part might be "final", config is middle parts
                    checkpoint_info["config"] = "_".join(parts[1:-1]) if len(parts) > 2 else parts[1]

        checkpoints.append(checkpoint_info)

    # Sort by modification time (newest first)
    checkpoints.sort(key=lambda x: x["modified"], reverse=True)

    return {"checkpoints": checkpoints}


@router.post("/test", response_model=RLTestResponse)
async def test_model(request: RLTestRequest):
    """Test the RL model with sample input."""
    try:
        from app.agents.rl_agent import RLAgent
        import numpy as np

        # Create agent (will use fallback if no model loaded)
        agent = RLAgent()

        # Prepare observation
        obs = np.array([
            request.inventory,
            request.backlog,
            request.incoming_shipment_0,
            request.incoming_shipment_1,
            request.incoming_order,
            request.last_order,
            request.round_number / 52.0,  # Normalize
            request.total_cost / 10000.0  # Normalize
        ], dtype=np.float32)

        # Get prediction
        if agent.is_trained:
            action, _ = agent.model.predict(obs, deterministic=True)
            order_quantity = int(action)
            model_used = True
            fallback_used = False
            explanation = f"RL model ({agent.config.algorithm}) predicted order quantity"
        else:
            # Use base-stock fallback
            from app.agents.rl_agent import compute_base_stock_order

            class MockNode:
                def __init__(self):
                    self.inventory = request.inventory
                    self.backlog = request.backlog
                    self.pipeline_shipments = [request.incoming_shipment_0, request.incoming_shipment_1]
                    self.incoming_order = request.incoming_order

            mock_node = MockNode()
            order_quantity = compute_base_stock_order(mock_node, {})
            model_used = False
            fallback_used = True
            explanation = "Used base-stock fallback (no model loaded)"

        return RLTestResponse(
            order_quantity=order_quantity,
            model_used=model_used,
            fallback_used=fallback_used,
            explanation=explanation
        )

    except Exception as e:
        logger.error(f"RL test failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")


@router.post("/evaluate", response_model=RLEvaluationResponse)
async def evaluate_model(request: RLEvaluationRequest):
    """Evaluate a trained RL model."""
    model_path = Path(request.model_path)

    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model not found: {request.model_path}")

    try:
        from app.agents.rl_agent import RLAgent

        # Load model
        agent = RLAgent(model_path=str(model_path))

        if not agent.is_trained:
            raise HTTPException(status_code=400, detail="Model not properly loaded")

        # Run evaluation
        metrics = agent.evaluate(n_episodes=request.n_episodes, render=False)

        return RLEvaluationResponse(
            mean_cost=metrics["mean_cost"],
            std_cost=metrics["std_cost"],
            mean_reward=metrics["mean_reward"],
            std_reward=metrics["std_reward"],
            mean_length=metrics["mean_length"],
            episodes=request.n_episodes
        )

    except Exception as e:
        logger.error(f"RL evaluation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")


@router.delete("/checkpoint")
async def delete_checkpoint(checkpoint_path: str):
    """Delete an RL checkpoint."""
    path = Path(checkpoint_path)

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Checkpoint not found: {checkpoint_path}")

    try:
        path.unlink()
        logger.info(f"Deleted RL checkpoint: {checkpoint_path}")
        return {"message": f"Checkpoint deleted: {checkpoint_path}"}

    except Exception as e:
        logger.error(f"Failed to delete checkpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete checkpoint: {str(e)}")


@router.post("/stop-training")
async def stop_training():
    """Stop ongoing training (if possible)."""
    global training_status

    if training_status.status != "training":
        raise HTTPException(status_code=400, detail="No training in progress")

    # Note: This is a simplified implementation
    # In production, you'd need to track and kill the subprocess
    training_status.status = "failed"
    training_status.message = "Training stopped by user"

    return {"message": "Training stop requested"}
