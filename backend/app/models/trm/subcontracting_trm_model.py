"""
Subcontracting TRM Model.

Narrow model for make-vs-buy and external manufacturing routing decisions.
State: 16 floats (capacity position 4 + cost comparison 6 + routing context 6)
Actions: 4-class discrete (internal, external, split, defer) + continuous split ratio
"""

import torch
import torch.nn as nn


SUB_STATE_DIM = 16
SUB_NUM_ACTIONS = 4
SUB_ACTION_NAMES = ["internal", "external", "split", "defer"]


class SubcontractingTRMModel(nn.Module):
    """
    TRM model for subcontracting routing decisions.

    Input: 16 floats:
        [0] capacity_utilized (0–1)    [1] overtime_available (0–1)
        [2] internal_cost (normalised) [3] external_cost (normalised)
        [4] lead_time_internal (norm)  [5] lead_time_external (norm)
        [6] quality_internal (0–1)     [7] quality_external (0–1)
        [8] order_qty (normalised)     [9] due_date_urgency (0–1)
        [10] split_available (0–1)     [11] vendor_reliability (0–1)
        [12] min_order_qty (normalised) [13] setup_cost (normalised)
        [14] capacity_surge (0–1)      [15] backlog (normalised)

    Output:
        action_logits: (batch, 4)
        quantity: (batch, 1)   — split ratio or external quantity
        confidence: (batch, 1)
        value: (batch, 1)
    """

    def __init__(self, state_dim: int = SUB_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = SUB_NUM_ACTIONS, num_refinement_steps: int = 3):
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
