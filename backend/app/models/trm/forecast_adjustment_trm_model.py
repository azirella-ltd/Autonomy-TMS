"""
Forecast Adjustment TRM Model.

Narrow model for signal-driven forecast adjustments (email, voice, market intelligence).
State: 18 floats (signal state 3 + forecast state 5 + demand context 5 + external signals 5)
Actions: 5-class discrete (increase_high, increase_low, hold, decrease_low, decrease_high)
         + continuous adjustment magnitude
"""

import torch
import torch.nn as nn


FA_STATE_DIM = 18
FA_NUM_ACTIONS = 5
FA_ACTION_NAMES = ["increase_high", "increase_low", "hold", "decrease_low", "decrease_high"]


class ForecastAdjustmentTRMModel(nn.Module):
    """
    TRM model for forecast adjustment decisions.

    Input: 18 floats:
        [0] signal_strength (0–1)      [1] signal_direction (-1 to 1, normalised)
        [2] signal_confidence (0–1)    [3] current_forecast (normalised)
        [4] forecast_error_recent (normalised)  [5] demand_trend (-1 to 1, norm)
        [6] seasonality_index (normalised)  [7] days_to_horizon (normalised)
        [8] inventory_position (normalised)  [9] backlog_rate (0–1)
        [10] customer_order_coverage (0–1)  [11] market_indicator (normalised)
        [12] news_sentiment (-1 to 1, norm)  [13] price_signal (normalised)
        [14] competitor_signal (normalised)  [15] historical_accuracy (0–1)
        [16] adjustment_magnitude (normalised)  [17] safety_factor (0–1)

    Output:
        action_logits: (batch, 5)
        quantity: (batch, 1)   — forecast adjustment magnitude (% change)
        confidence: (batch, 1)
        value: (batch, 1)
    """

    def __init__(self, state_dim: int = FA_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = FA_NUM_ACTIONS, num_refinement_steps: int = 3):
        super().__init__()
        self.state_dim = state_dim
        self.hidden_dim = hidden_dim
        self.num_refinement_steps = num_refinement_steps

        self.encoder = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            nn.Dropout(0.1),
        )

        self.refine = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
        )

        self.action_head = nn.Linear(hidden_dim, num_actions)
        self.quantity_head = nn.Sequential(nn.Linear(hidden_dim, 1), nn.Softplus())
        self.confidence_head = nn.Sequential(nn.Linear(hidden_dim, 1), nn.Sigmoid())
        self.value_head = nn.Linear(hidden_dim, 1)

    def forward(self, x: torch.Tensor) -> dict:
        h = self.encoder(x)
        for _ in range(self.num_refinement_steps):
            h = h + self.refine(h)
        return {
            "action_logits": self.action_head(h),
            "quantity": self.quantity_head(h),
            "confidence": self.confidence_head(h),
            "value": self.value_head(h),
        }
