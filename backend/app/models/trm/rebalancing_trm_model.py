"""
Inventory Rebalancing TRM Model.

Narrow model for cross-location inventory transfer decisions.
State: 30 floats (source site 12 + dest site 12 + lane 3 + network 3)
Actions: binary (transfer/hold) + continuous transfer quantity
"""

import torch
import torch.nn as nn
import numpy as np


REBALANCING_STATE_DIM = 30
REB_STATE_DIM = REBALANCING_STATE_DIM  # Alias for backward compatibility


class RebalancingTRMModel(nn.Module):
    """
    TRM model for inventory rebalancing decisions.

    Input: 30 floats from RebalancingState.get_pair_features():
        [0-11] source site state (on_hand, in_transit, committed, backlog,
               demand_forecast, demand_uncertainty, safety_stock, target_dos,
               criticality_score, supply_risk_score, days_of_supply, stockout_risk)
        [12-23] destination site state (same fields)
        [24] transfer_time, [25] cost_per_unit, [26] lane_available
        [27] network_imbalance_score, [28] total_network_inventory,
        [29] total_network_demand

    Output:
        transfer_logit: (batch, 1) logit for transfer decision (sigmoid -> prob)
        transfer_qty: (batch, 1) predicted transfer quantity
        confidence: (batch, 1) decision confidence (0-1)
        value: (batch, 1) state value for RL
    """

    def __init__(self, state_dim: int = REBALANCING_STATE_DIM, hidden_dim: int = 128,
                 num_refinement_steps: int = 3):
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

        # Transfer decision head (binary)
        self.transfer_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, 1),
        )

        # Transfer quantity head (continuous, non-negative)
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
            x: (batch, 30) state features

        Returns:
            dict with transfer_logit, transfer_qty, confidence, value
        """
        h = self.encoder(x)

        for _ in range(self.num_refinement_steps):
            h = h + self.refine(h)

        return {
            "transfer_logit": self.transfer_head(h),
            "transfer_qty": self.qty_head(h),
            "confidence": self.confidence_head(h),
            "value": self.value_head(h),
        }
