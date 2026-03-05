"""
Quality Disposition TRM Model.

Narrow model for quality hold/release/rework/scrap/use-as-is decisions.
State: 14 floats (quality metrics 5 + cost/risk 5 + context 4)
Actions: 5-class discrete (accept, reject, rework, scrap, use_as_is)
"""

import torch
import torch.nn as nn


QD_STATE_DIM = 14
QD_NUM_ACTIONS = 5
QD_ACTION_NAMES = ["accept", "reject", "rework", "scrap", "use_as_is"]


class QualityDispositionTRMModel(nn.Module):
    """
    TRM model for quality disposition decisions.

    Input: 14 floats:
        [0] defect_rate (0–1)      [1] severity_score (0–1)
        [2] units_affected (normalised)  [3] rework_cost (normalised)
        [4] scrap_cost (normalised) [5] hold_duration (normalised days)
        [6] order_urgency (0–1)    [7] inspection_cost (normalised)
        [8] rework_capacity (0–1)  [9] supplier_reliability (0–1)
        [10] warranty_risk (0–1)   [11] customer_impact (0–1)
        [12] production_disruption (0–1)  [13] disposition_cost (normalised)

    Output:
        action_logits: (batch, 5)
        quantity: (batch, 1)   — units to disposition in recommended action
        confidence: (batch, 1)
        value: (batch, 1)
    """

    def __init__(self, state_dim: int = QD_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = QD_NUM_ACTIONS, num_refinement_steps: int = 3):
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
