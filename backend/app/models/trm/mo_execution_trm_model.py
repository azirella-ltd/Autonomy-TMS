"""
MO Execution TRM Model.

Narrow model for manufacturing order release, sequencing, splitting, expediting, and cancellation.
State: 20 floats (production position 8 + resource state 6 + context 6)
Actions: 5-class discrete (release, defer, split, expedite, cancel) + continuous quantity
"""

import torch
import torch.nn as nn


MO_STATE_DIM = 20
MO_NUM_ACTIONS = 5
MO_ACTION_NAMES = ["release", "defer", "split", "expedite", "cancel"]


class MOExecutionTRMModel(nn.Module):
    """
    TRM model for manufacturing order execution decisions.

    Input: 20 floats:
        [0] work_in_progress       [1] capacity_available
        [2] order_qty              [3] due_date_urgency (0–1)
        [4] backlog                [5] material_available (0–1)
        [6] operator_available (0–1)  [7] quality_rate (0–1)
        [8] tool_wear (0–1)        [9] maintenance_due (0–1)
        [10] parallel_orders       [11] priority (0–1)
        [12] yield_rate (0–1)      [13] energy_cost (normalised)
        [14] overtime_available (0–1) [15] sequence_position (normalised)
        [16] bom_coverage (0–1)    [17] defect_rate (0–1)
        [18] setup_time (normalised) [19] cycle_time (normalised)

    Output:
        action_logits: (batch, 5)
        quantity: (batch, 1)
        confidence: (batch, 1)
        value: (batch, 1)
    """

    def __init__(self, state_dim: int = MO_STATE_DIM, hidden_dim: int = 128,
                 num_actions: int = MO_NUM_ACTIONS, num_refinement_steps: int = 3):
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
