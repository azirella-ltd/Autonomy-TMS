"""
TRM (Tiny Recursive Model) package.

Contains the base TRM architecture and per-TRM model variants for
each Powell Framework execution service.
"""

from .tiny_recursive_model import (
    TinyRecursiveModel,
    SupplyChainEncoder,
    RecursiveRefinementBlock,
    create_trm_model,
)
from .atp_trm_model import ATPTRMModel, ATP_STATE_DIM, ATP_NUM_ACTIONS
from .rebalancing_trm_model import RebalancingTRMModel, REB_STATE_DIM
from .po_creation_trm_model import POCreationTRMModel, PO_STATE_DIM, PO_NUM_ACTIONS
from .order_tracking_trm_model import (
    OrderTrackingTRMModel,
    OT_STATE_DIM,
    OT_NUM_EXCEPTION_TYPES,
    OT_NUM_SEVERITIES,
    OT_NUM_ACTIONS,
)

# Registry mapping TRM type name to (model_class, state_dim) for training scripts
MODEL_REGISTRY = {
    "atp_executor": (ATPTRMModel, ATP_STATE_DIM),
    "rebalancing": (RebalancingTRMModel, REB_STATE_DIM),
    "po_creation": (POCreationTRMModel, PO_STATE_DIM),
    "order_tracking": (OrderTrackingTRMModel, OT_STATE_DIM),
}

def load_trm_checkpoint(trm_type: str, checkpoint_path: str, device: str = "cpu"):
    """
    Load a per-TRM model from a checkpoint file.

    Returns a wrapper with a .predict(numpy_input) method that returns
    a dict of numpy arrays, compatible with Powell TRM services.

    Args:
        trm_type: One of 'atp_executor', 'rebalancing', 'po_creation', 'order_tracking'
        checkpoint_path: Path to .pt checkpoint file
        device: 'cpu' or 'cuda'

    Returns:
        TRMModelWrapper with .predict() method
    """
    import torch
    import numpy as np

    if trm_type not in MODEL_REGISTRY:
        raise ValueError(f"Unknown TRM type: {trm_type}. Choose from: {list(MODEL_REGISTRY.keys())}")

    model_cls, state_dim = MODEL_REGISTRY[trm_type]
    model = model_cls(state_dim=state_dim)

    ckpt = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    model.to(device)

    class TRMModelWrapper:
        """Wraps nn.Module for numpy-in/dict-out inference."""

        def __init__(self, model, device):
            self._model = model
            self._device = device

        def predict(self, features: np.ndarray) -> dict:
            """Run inference. Input: numpy [batch, state_dim]. Output: dict of numpy arrays."""
            with torch.no_grad():
                x = torch.tensor(features, dtype=torch.float32).to(self._device)
                out = self._model(x)
                return {k: v.cpu().numpy() for k, v in out.items()}

    return TRMModelWrapper(model, device)


__all__ = [
    # Base TRM
    "TinyRecursiveModel",
    "SupplyChainEncoder",
    "RecursiveRefinementBlock",
    "create_trm_model",
    # Per-TRM models
    "ATPTRMModel",
    "RebalancingTRMModel",
    "POCreationTRMModel",
    "OrderTrackingTRMModel",
    # Registry and loading
    "MODEL_REGISTRY",
    "load_trm_checkpoint",
]
