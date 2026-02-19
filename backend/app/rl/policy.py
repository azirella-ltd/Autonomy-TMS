from typing import Optional, Any
import numpy as np

TORCH_IMPORT_ERROR = None
try:  # pragma: no cover - optional dependency
    import torch
    import torch.nn as nn
except Exception as exc:  # pragma: no cover - depends on torch availability
    TORCH_IMPORT_ERROR = exc
    torch = None  # type: ignore
    nn = None  # type: ignore

from .config import ACTION_LEVELS
from .data_generator import action_idx_to_order_units

if torch is not None:

    class SimpleTemporalHead(nn.Module):
        """
        A tiny decoder that turns a node embedding into action logits.
        Plug your temporal GNN in to produce [B, T, N, H], then map to [B, T, N, A].
        """

        def __init__(self, hidden_dim: int, num_actions: int = len(ACTION_LEVELS)):
            super().__init__()
            self.proj = nn.Linear(hidden_dim, num_actions)

        def forward(self, x):
            # x: [B, T, N, H]
            return self.proj(x)  # [B, T, N, A]

else:

    class SimpleTemporalHead:  # type: ignore[empty-body]
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "SimpleTemporalHead requires torch; training should be skipped when torch is unavailable."
            )

def select_action(
    logits: Any,
    epsilon: float = 0.0,
    temperature: float = 1.0,
) -> Any:
    """
    Select actions from logits with optional exploration.
    
    Args:
        logits: [B, N, A] for current step
        epsilon: probability of taking a random action (for exploration)
        temperature: softmax temperature (higher = more random)
        
    Returns:
        indices: [B, N] action indices
    """
    if torch is None:
        raise RuntimeError(
            "select_action requires torch; ensure torch is installed before calling."
        )

    if epsilon > 0 and np.random.rand() < epsilon:
        B, N, A = logits.shape
        return torch.randint(low=0, high=A, size=(B, N), device=logits.device)
    if temperature != 1.0:
        logits = logits / temperature
    return torch.argmax(logits, dim=-1)  # greedy

def indices_to_units(indices: np.ndarray) -> np.ndarray:
    """
    Convert action indices to actual order units for each node.
    
    Args:
        indices: [B, N] array of action indices
        
    Returns:
        order_units: [B, N] array of order quantities
    """
    vec = np.vectorize(lambda i: action_idx_to_order_units(int(i)))
    return vec(indices)
