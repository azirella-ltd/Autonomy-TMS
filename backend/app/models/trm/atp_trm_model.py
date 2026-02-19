"""
ATP Executor TRM Model.

Narrow model for Available-to-Promise decisions.
State: 12 floats (order priority, requested qty, inventory state, allocations)
Actions: 5-class discrete (fulfill, partial, defer, reserve, reject) + continuous qty
"""

import torch
import torch.nn as nn
import numpy as np


ATP_STATE_DIM = 12
ATP_NUM_ACTIONS = 5  # fulfill, partial, defer, reserve, reject
ATP_ACTION_NAMES = ["fulfill", "partial", "defer", "reserve", "reject"]


class ATPTRMModel(nn.Module):
    """
    TRM model for ATP execution decisions.

    Input: 12 floats from ATPState.to_features():
        [0] order_priority, [1] requested_qty, [2] current_inventory,
        [3] pipeline_inventory, [4] safety_stock_level, [5] demand_forecast,
        [6] demand_uncertainty, [7-11] allocation_available[1..5]

    Output:
        action_logits: (batch, 5) logits for action type
        fulfill_qty: (batch, 1) predicted fulfill quantity
        confidence: (batch, 1) decision confidence (0-1)
        value: (batch, 1) state value for RL
    """

    def __init__(self, state_dim: int = ATP_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = ATP_NUM_ACTIONS, num_refinement_steps: int = 3):
        super().__init__()
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        self.num_refinement_steps = num_refinement_steps

        # Encoder
        self.encoder = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            nn.Dropout(0.1),
        )

        # Recursive refinement block
        self.refine = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )

        # Action type head (discrete)
        self.action_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, num_actions),
        )

        # Fulfill quantity head (continuous, 0 to max)
        self.qty_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
            nn.Sigmoid(),  # Output 0-1, scale by requested_qty at inference
        )

        # Confidence head
        self.confidence_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, 1),
            nn.Sigmoid(),
        )

        # Value head (for RL)
        self.value_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(self, x: torch.Tensor):
        """
        Args:
            x: (batch, 12) state features

        Returns:
            dict with action_logits, fulfill_qty, confidence, value
        """
        h = self.encoder(x)

        for _ in range(self.num_refinement_steps):
            h = h + self.refine(h)

        return {
            "action_logits": self.action_head(h),
            "fulfill_qty": self.qty_head(h),
            "confidence": self.confidence_head(h),
            "value": self.value_head(h),
        }
