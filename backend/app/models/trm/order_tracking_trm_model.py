"""
Order Tracking TRM Model.

Narrow model for order exception detection and recommended actions.
State: 15 floats (order type 3 + status 2 + timing 2 + quantities 3 + rates 3 + context 2)
Actions: 9-class exception type + 4-class severity + 9-class recommended action
"""

import torch
import torch.nn as nn
import numpy as np


OT_STATE_DIM = 15
OT_NUM_EXCEPTION_TYPES = 9  # late, early, shortage, overage, quality, missing_confirm, stuck, price, no_exception
OT_NUM_SEVERITIES = 4  # info, warning, high, critical
OT_NUM_ACTIONS = 9  # no_action, expedite, delay, partial, alternate, cancel, inspect, negotiate, escalate

OT_EXCEPTION_NAMES = [
    "late_delivery", "early_delivery", "quantity_shortage", "quantity_overage",
    "quality_issue", "missing_confirmation", "stuck_in_transit", "price_variance",
    "no_exception",
]
OT_SEVERITY_NAMES = ["info", "warning", "high", "critical"]
OT_ACTION_NAMES = [
    "no_action", "expedite", "delay_acceptance", "partial_receipt",
    "find_alternate", "cancel_reorder", "quality_inspection",
    "price_negotiation", "escalate",
]


class OrderTrackingTRMModel(nn.Module):
    """
    TRM model for order exception detection decisions.

    Input: 15 floats from OrderState.to_features():
        [0] is_purchase_order, [1] is_transfer_order, [2] is_customer_order,
        [3] is_in_transit, [4] is_partially_received,
        [5] days_until_expected, [6] days_since_created,
        [7] ordered_qty, [8] received_qty, [9] remaining_qty,
        [10] fill_rate, [11] price_variance_pct,
        [12] partner_on_time_rate, [13] partner_fill_rate, [14] typical_transit_days

    Output:
        exception_logits: (batch, 9) logits for exception type
        severity_logits: (batch, 4) logits for severity
        action_logits: (batch, 9) logits for recommended action
        confidence: (batch, 1) decision confidence (0-1)
        value: (batch, 1) state value for RL
    """

    def __init__(self, state_dim: int = OT_STATE_DIM, hidden_dim: int = 128,
                 num_exception_types: int = OT_NUM_EXCEPTION_TYPES,
                 num_severities: int = OT_NUM_SEVERITIES,
                 num_actions: int = OT_NUM_ACTIONS,
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

        # Exception type head (9-class)
        self.exception_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, num_exception_types),
        )

        # Severity head (4-class)
        self.severity_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 4),
            nn.ReLU(),
            nn.Linear(hidden_dim // 4, num_severities),
        )

        # Recommended action head (9-class)
        self.action_head = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
            nn.Linear(hidden_dim // 2, num_actions),
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
            x: (batch, 15) state features

        Returns:
            dict with exception_logits, severity_logits, action_logits, confidence, value
        """
        h = self.encoder(x)

        for _ in range(self.num_refinement_steps):
            h = h + self.refine(h)

        return {
            "exception_logits": self.exception_head(h),
            "severity_logits": self.severity_head(h),
            "action_logits": self.action_head(h),
            "confidence": self.confidence_head(h),
            "value": self.value_head(h),
        }
