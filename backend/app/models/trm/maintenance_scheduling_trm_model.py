"""
Maintenance Scheduling TRM Model.

Narrow model for preventive maintenance scheduling, deferral, expediting, and outsourcing.
State: 14 floats (asset health 4 + resource availability 4 + cost/urgency 6)
Actions: 4-class discrete (schedule, defer, expedite, outsource)
"""

import torch
import torch.nn as nn


MS_STATE_DIM = 14
MS_NUM_ACTIONS = 4
MS_ACTION_NAMES = ["schedule", "defer", "expedite", "outsource"]


class MaintenanceSchedulingTRMModel(nn.Module):
    """
    TRM model for maintenance scheduling decisions.

    Input: 14 floats:
        [0] asset_health (0–1)     [1] failure_probability (0–1)
        [2] days_to_planned (normalised)  [3] production_impact (0–1)
        [4] maintenance_duration (normalised)  [5] crew_available (0–1)
        [6] parts_available (0–1)  [7] order_urgency (0–1)
        [8] overtime_cost (normalised)  [9] outsource_available (0–1)
        [10] last_maintenance_days (normalised)  [11] criticality (0–1)
        [12] schedule_backlog (normalised)  [13] maintenance_cost (normalised)

    Output:
        action_logits: (batch, 4)
        quantity: (batch, 1)   — maintenance window duration recommendation
        confidence: (batch, 1)
        value: (batch, 1)
    """

    def __init__(self, state_dim: int = MS_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = MS_NUM_ACTIONS, num_refinement_steps: int = 3):
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
