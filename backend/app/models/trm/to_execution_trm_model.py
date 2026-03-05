"""
TO Execution TRM Model.

Narrow model for transfer order release, deferral, consolidation, and expediting.
State: 16 floats (inventory position 6 + transit state 4 + routing context 6)
Actions: 4-class discrete (release, defer, consolidate, expedite) + continuous quantity
"""

import torch
import torch.nn as nn


TO_STATE_DIM = 16
TO_NUM_ACTIONS = 4
TO_ACTION_NAMES = ["release", "defer", "consolidate", "expedite"]


class TOExecutionTRMModel(nn.Module):
    """
    TRM model for transfer order execution decisions.

    Input: 16 floats:
        [0] origin_inventory       [1] dest_inventory
        [2] origin_safety_stock    [3] dest_safety_stock
        [4] in_transit_qty         [5] lead_time_days (normalised)
        [6] urgency_score (0–1)    [7] carrier_available (0–1)
        [8] consolidation_opportunity (0–1)  [9] priority (0–1)
        [10] route_reliability (0–1)  [11] mode_cost (normalised)
        [12] quantity              [13] dest_backlog
        [14] origin_excess         [15] days_to_due (normalised)

    Output:
        action_logits: (batch, 4)
        quantity: (batch, 1)
        confidence: (batch, 1)
        value: (batch, 1)
    """

    def __init__(self, state_dim: int = TO_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = TO_NUM_ACTIONS, num_refinement_steps: int = 3):
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
