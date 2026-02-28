"""
Inventory Buffer TRM Model.

Narrow model for inventory buffer (safety stock) adjustment decisions.
State: 14 floats (current SS, demand stats, lead time stats, service level,
       stockout freq, excess cost, holding cost, forecast error, ATP signal,
       demand trend, seasonality)
Actions: 5 discrete (maintain, increase_small, increase_large,
         decrease_small, decrease_large)
"""

import torch
import torch.nn as nn


INVENTORY_BUFFER_STATE_DIM = 14
IB_STATE_DIM = INVENTORY_BUFFER_STATE_DIM
IB_NUM_ACTIONS = 5


class InventoryBufferTRMModel(nn.Module):
    """
    TRM model for inventory buffer (safety stock) adjustment decisions.

    Input: 14 floats from InventoryBufferState:
        [0] current_ss_norm         - Current safety stock level (normalized)
        [1] demand_mean_norm        - Mean demand (normalized)
        [2] demand_cv               - Demand coefficient of variation
        [3] lead_time_mean_norm     - Mean lead time (normalized)
        [4] lead_time_cv            - Lead time coefficient of variation
        [5] service_level_target    - Target service level (e.g., 0.95)
        [6] actual_service_level    - Achieved service level
        [7] stockout_frequency      - Frequency of stockouts (0-1)
        [8] excess_inventory_cost   - Excess inventory cost (normalized)
        [9] holding_cost_norm       - Holding cost (normalized)
        [10] forecast_error_pct     - Forecast error percentage
        [11] atp_shortage_signal    - ATP shortage signal from hive (0-1)
        [12] demand_trend           - Demand trend (negative=declining)
        [13] seasonality_index      - Seasonality index (1.0=neutral)

    Output:
        action_logits: (batch, 5) logits for 5 adjustment actions
        confidence: (batch, 1) decision confidence (0-1)
        value: (batch, 1) state value for RL
    """

    def __init__(self, state_dim: int = INVENTORY_BUFFER_STATE_DIM,
                 hidden_dim: int = 128, num_refinement_steps: int = 3):
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

        # Recursive refinement block (shared weights, applied N times)
        self.refine = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )

        # Action head (5 discrete actions)
        self.action_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, IB_NUM_ACTIONS),
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
            x: (batch, 14) state features

        Returns:
            dict with action_logits, confidence, value
        """
        h = self.encoder(x)

        for _ in range(self.num_refinement_steps):
            h = h + self.refine(h)

        return {
            "action_logits": self.action_head(h),
            "confidence": self.confidence_head(h),
            "value": self.value_head(h),
        }
