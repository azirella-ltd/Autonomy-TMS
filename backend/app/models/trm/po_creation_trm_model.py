"""
PO Creation TRM Model.

Narrow model for purchase order timing and quantity decisions.
State: 17 floats (inventory position 8 + supplier info 5 + context 4)
Actions: 4-class discrete (order, defer, expedite, cancel) + continuous order qty
"""

import torch
import torch.nn as nn
import numpy as np


PO_STATE_DIM = 17
PO_NUM_ACTIONS = 4  # order, defer, expedite, cancel
PO_ACTION_NAMES = ["order", "defer", "expedite", "cancel"]


class POCreationTRMModel(nn.Module):
    """
    TRM model for PO creation decisions.

    Input: 17 floats from POCreationState.get_supplier_features():
        [0] on_hand, [1] in_transit, [2] on_order, [3] committed,
        [4] backlog, [5] safety_stock, [6] reorder_point, [7] days_of_supply
        [8] lead_time_days, [9] unit_cost, [10] min_order_qty,
        [11] on_time_rate, [12] is_available
        [13] forecast_next_30_days, [14] forecast_uncertainty,
        [15] supply_risk_score, [16] demand_volatility_score

    Output:
        action_logits: (batch, 4) logits for action type
        order_qty: (batch, 1) predicted order quantity
        confidence: (batch, 1) decision confidence (0-1)
        value: (batch, 1) state value for RL
    """

    def __init__(self, state_dim: int = PO_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = PO_NUM_ACTIONS, num_refinement_steps: int = 3):
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

        # Order quantity head (continuous, non-negative)
        self.qty_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
            nn.ReLU(),  # Non-negative quantity
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
            x: (batch, 17) state features

        Returns:
            dict with action_logits, order_qty, confidence, value
        """
        h = self.encoder(x)

        for _ in range(self.num_refinement_steps):
            h = h + self.refine(h)

        return {
            "action_logits": self.action_head(h),
            "order_qty": self.qty_head(h),
            "confidence": self.confidence_head(h),
            "value": self.value_head(h),
        }
