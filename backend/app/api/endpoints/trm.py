"""
API endpoints for TRM (Tiny Recursive Model) management.

Provides endpoints for training, loading, and managing TRM models.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from pathlib import Path
import logging
import subprocess
import json
import os

from app.services.trm_agent import get_trm_agent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trm", tags=["trm"])


# Request/Response Models
class TRMTrainingRequest(BaseModel):
    """Request to start per-TRM training."""
    trm_type: str = Field("all", description="TRM type: atp_executor, rebalancing, po_creation, order_tracking, or 'all'")
    supply_chain_config: str = Field("default_beer_game", description="Supply chain config ID to train on")
    phase: str = Field("all", description="Training phase: 1, 2, 3, or 'all'")
    epochs: int = Field(50, description="Epochs per phase", ge=1, le=500)
    device: str = Field("cuda", description="Training device: cuda or cpu")
    batch_size: int = Field(64, description="Batch size", ge=1, le=256)
    learning_rate: float = Field(1e-4, description="Learning rate", gt=0, le=1)
    num_samples: int = Field(10000, description="Samples per phase", ge=1000)
    checkpoint_dir: str = Field("./checkpoints", description="Checkpoint directory")
    resume_checkpoint: Optional[str] = Field(None, description="Resume from checkpoint")


class TRMTrainingStatus(BaseModel):
    """TRM training status."""
    status: str  # "idle", "training", "completed", "failed"
    phase: Optional[int] = None
    epoch: Optional[int] = None
    total_epochs: Optional[int] = None
    train_loss: Optional[float] = None
    val_loss: Optional[float] = None
    message: Optional[str] = None


class TRMModelInfo(BaseModel):
    """TRM model information."""
    model_loaded: bool
    model_path: Optional[str] = None
    device: str
    parameters: Optional[Dict[str, int]] = None
    window_size: int
    use_fallback: bool


class TRMLoadModelRequest(BaseModel):
    """Request to load TRM model."""
    model_path: str = Field(..., description="Path to TRM checkpoint")
    device: str = Field("cpu", description="Device for inference: cpu or cuda")


class TRMTestRequest(BaseModel):
    """Request to test TRM model."""
    inventory: float = Field(..., ge=0)
    backlog: float = Field(..., ge=0)
    pipeline: float = Field(..., ge=0)
    demand_history: List[float] = Field(..., min_items=1, max_items=20)
    node_type: str = Field("retailer", description="Node type: retailer, wholesaler, etc.")
    node_position: int = Field(0, description="Position in supply chain", ge=0, le=9)


class TRMTestResponse(BaseModel):
    """Response from TRM test."""
    order_quantity: float
    model_used: bool
    fallback_used: bool
    explanation: str


# Training status tracking (in-memory for simplicity)
training_status = TRMTrainingStatus(status="idle")


@router.post("/train", response_model=TRMTrainingStatus)
async def start_training(request: TRMTrainingRequest, background_tasks: BackgroundTasks):
    """
    Start TRM training in the background.

    The training runs asynchronously, and you can check status with /trm/training-status.
    """
    global training_status

    if training_status.status == "training":
        raise HTTPException(status_code=400, detail="Training already in progress")

    # Validate device
    if request.device == "cuda":
        try:
            import torch
            if not torch.cuda.is_available():
                raise HTTPException(status_code=400, detail="CUDA not available")
        except ImportError:
            raise HTTPException(status_code=400, detail="PyTorch not installed")

    # Update status
    training_status.status = "training"
    training_status.phase = 1 if request.phase == "all" else int(request.phase)
    training_status.epoch = 0
    training_status.total_epochs = request.epochs
    training_status.train_loss = None
    training_status.val_loss = None
    training_status.message = "Starting training..."

    # Start training in background
    background_tasks.add_task(
        run_training_task,
        request
    )

    return training_status


def run_training_task(request: TRMTrainingRequest):
    """Background task to run TRM training."""
    global training_status

    try:
        # Build command
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "training" / "train_trm.py"

        cmd = [
            "python",
            str(script_path),
            "--trm-type", request.trm_type,
            "--config-id", request.supply_chain_config,
            "--phase", str(request.phase),
            "--epochs", str(request.epochs),
            "--device", request.device,
            "--batch-size", str(request.batch_size),
            "--learning-rate", str(request.learning_rate),
            "--num-samples", str(request.num_samples),
            "--checkpoint-dir", request.checkpoint_dir,
        ]

        if request.resume_checkpoint:
            cmd.extend(["--resume", request.resume_checkpoint])

        logger.info(f"Starting TRM training: {' '.join(cmd)}")

        # Run training
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Monitor output
        for line in process.stdout:
            logger.info(f"TRM Training: {line.strip()}")

            # Parse training progress from output
            if "Epoch" in line and "/" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "Epoch" and i + 1 < len(parts):
                        epoch_info = parts[i + 1].split("/")
                        if len(epoch_info) == 2:
                            training_status.epoch = int(epoch_info[0])
                            training_status.total_epochs = int(epoch_info[1])

            if "Train Loss:" in line:
                parts = line.split("Train Loss:")
                if len(parts) > 1:
                    try:
                        training_status.train_loss = float(parts[1].strip().split()[0])
                    except:
                        pass

            if "Val Loss:" in line:
                parts = line.split("Val Loss:")
                if len(parts) > 1:
                    try:
                        training_status.val_loss = float(parts[1].strip().split()[0])
                    except:
                        pass

        process.wait()

        if process.returncode == 0:
            training_status.status = "completed"
            training_status.message = "Training completed successfully"
            logger.info("TRM training completed successfully")
        else:
            stderr = process.stderr.read()
            training_status.status = "failed"
            training_status.message = f"Training failed: {stderr[:200]}"
            logger.error(f"TRM training failed: {stderr}")

    except Exception as e:
        training_status.status = "failed"
        training_status.message = f"Training failed: {str(e)}"
        logger.error(f"TRM training error: {e}", exc_info=True)


@router.get("/training-status", response_model=TRMTrainingStatus)
async def get_training_status():
    """Get current training status."""
    return training_status


@router.post("/load-model", response_model=TRMModelInfo)
async def load_model(request: TRMLoadModelRequest):
    """Load a trained TRM model for inference."""
    model_path = Path(request.model_path)

    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Model not found: {request.model_path}")

    try:
        # Load model
        agent = get_trm_agent(
            model_path=str(model_path),
            device=request.device,
            reload=True
        )

        info = agent.get_info()

        return TRMModelInfo(
            model_loaded=info["model_loaded"],
            model_path=str(model_path),
            device=info["device"],
            parameters=info["parameters"],
            window_size=info["window_size"],
            use_fallback=info["use_fallback"]
        )

    except Exception as e:
        logger.error(f"Failed to load TRM model: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load model: {str(e)}")


@router.get("/model-info", response_model=TRMModelInfo)
async def get_model_info():
    """Get information about the currently loaded TRM model."""
    agent = get_trm_agent()
    info = agent.get_info()

    return TRMModelInfo(
        model_loaded=info["model_loaded"],
        model_path=None,  # Not tracked in current implementation
        device=info["device"],
        parameters=info["parameters"],
        window_size=info["window_size"],
        use_fallback=info["use_fallback"]
    )


@router.get("/checkpoints")
async def list_checkpoints(
    checkpoint_dir: str = "./checkpoints",
    config_id: Optional[str] = None
):
    """
    List available TRM checkpoints.

    Args:
        checkpoint_dir: Directory containing checkpoints
        config_id: Optional supply chain config ID to filter by (e.g., 'default_beer_game')
    """
    checkpoint_path = Path(checkpoint_dir)

    if not checkpoint_path.exists():
        return {"checkpoints": []}

    checkpoints = []

    # Collect files from multiple patterns
    files_to_process = set()

    if config_id:
        # Look for config-specific checkpoints
        for file in checkpoint_path.glob(f"{config_id}_*.pt"):
            files_to_process.add(file)
        # Also include legacy trm_* checkpoints (shared across all configs)
        for file in checkpoint_path.glob("trm_*.pt"):
            files_to_process.add(file)
    else:
        # No filter - get all .pt files in the main directory (not subdirs)
        for file in checkpoint_path.glob("*.pt"):
            files_to_process.add(file)

    for file in files_to_process:
        stat = file.stat()

        # Parse checkpoint filename to extract metadata
        # Expected format: {config_id}_phase{N}_epoch{M}.pt
        # or legacy format: trm_phase{N}_epoch{M}.pt
        checkpoint_info = {
            "name": file.name,
            "path": str(file),
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified": stat.st_mtime
        }

        # Try to parse phase and epoch from filename
        filename = file.stem  # Remove .pt extension
        if "_phase" in filename and "_epoch" in filename:
            try:
                parts = filename.split("_")
                for i, part in enumerate(parts):
                    if part == "phase" and i + 1 < len(parts):
                        checkpoint_info["phase"] = int(parts[i + 1])
                    elif part == "epoch" and i + 1 < len(parts):
                        checkpoint_info["epoch"] = int(parts[i + 1])

                # Extract config_id from filename
                if parts[0] != "trm":
                    checkpoint_info["config_id"] = parts[0]
                else:
                    checkpoint_info["config_id"] = "legacy"
            except (ValueError, IndexError):
                pass

        checkpoints.append(checkpoint_info)

    # Sort by modification time (newest first)
    checkpoints.sort(key=lambda x: x["modified"], reverse=True)

    return {"checkpoints": checkpoints}


@router.post("/test", response_model=TRMTestResponse)
async def test_model(request: TRMTestRequest):
    """
    Test TRM model with specific inputs.

    Useful for debugging and validation.
    """
    agent = get_trm_agent()

    if not agent.model_loaded:
        # Test with fallback
        try:
            # Create dummy node for fallback
            class SimpleNode:
                def __init__(self):
                    self.name = "test_node"
                    self.node_type = request.node_type
                    self.inventory = request.inventory
                    self.backlog = request.backlog
                    self.pipeline_shipments = [type('obj', (object,), {'quantity': request.pipeline})()]
                    self.incoming_order = request.demand_history[-1] if request.demand_history else 0

            node = SimpleNode()
            context = {"round_number": 0}

            order_qty = agent.compute_order(node, context)

            return TRMTestResponse(
                order_quantity=order_qty,
                model_used=False,
                fallback_used=True,
                explanation="TRM model not loaded, used base stock heuristic fallback"
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")

    # Test with actual TRM model
    try:
        order_qty = agent.model.get_action(
            inventory=request.inventory,
            backlog=request.backlog,
            pipeline=request.pipeline,
            demand_history=request.demand_history[-agent.window_size:],
            node_type=agent.NODE_TYPE_MAP.get(request.node_type.lower(), 0),
            node_position=request.node_position
        )

        return TRMTestResponse(
            order_quantity=order_qty,
            model_used=True,
            fallback_used=False,
            explanation=f"TRM prediction for {request.node_type} at position {request.node_position}"
        )

    except Exception as e:
        logger.error(f"TRM test failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")


@router.delete("/model")
async def unload_model():
    """Unload the currently loaded TRM model."""
    agent = get_trm_agent()
    agent.reset()
    agent.model = None
    agent.model_loaded = False

    return {"message": "TRM model unloaded successfully"}


@router.get("/config")
async def get_default_config():
    """Get default TRM configuration."""
    return {
        "trm_types": [
            {"type": "atp_executor", "state_dim": 12, "description": "Available-to-Promise decisions"},
            {"type": "rebalancing", "state_dim": 30, "description": "Cross-location transfer decisions"},
            {"type": "po_creation", "state_dim": 17, "description": "PO timing and quantity decisions"},
            {"type": "order_tracking", "state_dim": 15, "description": "Exception detection and actions"},
        ],
        "training": {
            "default_epochs": 50,
            "default_batch_size": 64,
            "default_learning_rate": 1e-4,
            "default_num_samples": 10000
        },
        "curriculum_phases": [
            {"phase": 1, "name": "Simple scenarios", "description": "Easy decisions, clear signals"},
            {"phase": 2, "name": "Moderate complexity", "description": "Trade-offs, variability"},
            {"phase": 3, "name": "Full complexity", "description": "Disruptions, uncertainty, edge cases"},
        ]
    }
