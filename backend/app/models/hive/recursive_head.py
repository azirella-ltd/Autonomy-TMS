"""
Recursive TRM Heads — Per-head iterative refinement with adaptive halting.

Each TRM head applies R refinement steps (default R=3) using shared-weight
transformer blocks, progressively improving its decision via a latent
scratchpad state.

Architecture reference: TRM_HIVE_ARCHITECTURE.md Section 14.4

Forward pass per head:
    head_input [B, input_dim]
    → Initialize y₀, z₀
    → For r in range(R):
        z_r = PostNorm(head_block(head_input, y_{r-1}, z_{r-1}))
        y_r = PostNorm(answer_block(y_{r-1}, z_r))
        if adaptive_halt and confidence(y_r) > threshold: break
    → Output y_R with action_probs, value, confidence

Key design choices:
- Shared weights across R steps (not R different networks)
- Post-norm for recursion stability (pre-norm causes divergence)
- Bottleneck projection (hidden_dim//2) in refinement block for parameter efficiency
- Refinement gate: learned mixing between current and previous thought
- ~25K params per head (275K total for 11 heads)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class RecursiveHeadConfig:
    """Configuration for a recursive TRM head."""
    input_dim: int = 128         # Head input dimension (state_emb or state_emb + cross_context)
    hidden_dim: int = 64         # Internal hidden dimension / scratchpad size
    num_refinement_steps: int = 3  # R — number of recursive passes
    halt_threshold: float = 0.95   # Confidence threshold for adaptive halting
    adaptive_halt: bool = False    # Enable early stopping on high confidence
    dropout: float = 0.1


class RefinementBlock(nn.Module):
    """Single refinement iteration — shared weights across all R steps.

    Combines head_input with previous answer and scratchpad to produce
    an updated scratchpad state. Uses post-norm for recursion stability.
    """

    def __init__(self, input_dim: int, answer_dim: int, hidden_dim: int, dropout: float = 0.1):
        super().__init__()
        # Bottleneck: compress combined input before gated refinement
        bottleneck = hidden_dim // 2
        self.proj = nn.Linear(input_dim + answer_dim + hidden_dim, bottleneck)
        self.gate = nn.Linear(bottleneck, hidden_dim)
        self.refine = nn.Linear(bottleneck, hidden_dim)
        self.layer_norm = nn.LayerNorm(hidden_dim)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        head_input: torch.Tensor,     # [B, input_dim]
        prev_answer: torch.Tensor,    # [B, answer_dim]
        prev_scratchpad: torch.Tensor, # [B, hidden_dim]
    ) -> torch.Tensor:
        """Update scratchpad from head_input, previous answer and scratchpad.

        Returns: updated scratchpad [B, hidden_dim]
        """
        combined = torch.cat([head_input, prev_answer, prev_scratchpad], dim=-1)
        h = F.gelu(self.proj(combined))

        # Gated refinement: learn how much to keep from previous vs new
        gate_val = torch.sigmoid(self.gate(h))
        new_content = self.refine(h)
        new_content = self.dropout(new_content)

        # Post-norm: apply after residual for recursion stability
        scratchpad = gate_val * new_content + (1 - gate_val) * prev_scratchpad
        return self.layer_norm(scratchpad)


class AnswerBlock(nn.Module):
    """Refine the answer using updated scratchpad. Shared across R steps."""

    def __init__(self, hidden_dim: int, answer_dim: int, dropout: float = 0.1):
        super().__init__()
        self.proj = nn.Linear(hidden_dim + answer_dim, hidden_dim)
        self.output = nn.Linear(hidden_dim, answer_dim)
        self.layer_norm = nn.LayerNorm(answer_dim)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        prev_answer: torch.Tensor,   # [B, answer_dim]
        scratchpad: torch.Tensor,     # [B, hidden_dim]
    ) -> torch.Tensor:
        """Refine answer using scratchpad context.

        Returns: updated answer [B, answer_dim]
        """
        combined = torch.cat([scratchpad, prev_answer], dim=-1)
        h = F.gelu(self.proj(combined))
        h = self.dropout(h)
        delta = self.output(h)
        # Post-norm residual
        return self.layer_norm(prev_answer + delta)


class RecursiveTRMHead(nn.Module):
    """Base class for recursive TRM heads.

    Subclasses specify ``answer_dim`` and implement ``_decode_answer()``
    to map the raw answer vector into task-specific outputs
    (action_probs, values, multipliers, etc.).

    The base class handles:
    - Initial answer/scratchpad projection
    - R-step recursive refinement loop
    - Confidence prediction for adaptive halting
    - Halting statistics tracking
    """

    # Subclasses override this
    answer_dim: int = 8

    def __init__(self, config: Optional[RecursiveHeadConfig] = None):
        super().__init__()
        config = config or RecursiveHeadConfig()
        self.config = config

        # Initial projections
        self.initial_answer_proj = nn.Linear(config.input_dim, self.answer_dim)
        self.initial_scratchpad_proj = nn.Linear(config.input_dim, config.hidden_dim)

        # Shared refinement blocks (weight-shared across R steps)
        self.refinement_block = RefinementBlock(
            config.input_dim, self.answer_dim, config.hidden_dim, config.dropout
        )
        self.answer_block = AnswerBlock(
            config.hidden_dim, self.answer_dim, config.dropout
        )

        # Confidence predictor (from scratchpad, for adaptive halting)
        self.confidence_head = nn.Linear(config.hidden_dim, 1)

        # Track halting statistics (non-parameter)
        self.register_buffer("_total_steps", torch.tensor(0, dtype=torch.long))
        self.register_buffer("_total_calls", torch.tensor(0, dtype=torch.long))

    def _decode_answer(self, answer: torch.Tensor) -> Dict[str, torch.Tensor]:
        """Convert raw answer vector to task-specific outputs.

        Subclasses must override this method.

        Args:
            answer: [B, answer_dim] raw refined answer vector

        Returns:
            Dict with task-specific tensors (action_probs, value, etc.)
        """
        return {"raw_answer": answer}

    def forward(
        self,
        head_input: torch.Tensor,  # [B, input_dim]
        R: Optional[int] = None,   # Override refinement steps (for CGAR curriculum)
    ) -> Dict[str, torch.Tensor]:
        """Run recursive refinement and produce task-specific outputs.

        Args:
            head_input: Input features [B, input_dim].
            R: Number of refinement steps. Defaults to config.num_refinement_steps.

        Returns:
            Dict with task outputs + 'confidence' [B, 1] + 'num_steps' int.
        """
        R = R or self.config.num_refinement_steps

        # Initialize
        initial_answer = self.initial_answer_proj(head_input)  # [B, answer_dim]
        answer = initial_answer
        scratchpad = self.initial_scratchpad_proj(head_input)  # [B, hidden_dim]

        steps_taken = R
        for step in range(R):
            scratchpad = self.refinement_block(head_input, answer, scratchpad)
            answer = self.answer_block(answer, scratchpad)

            # Adaptive halting
            if self.config.adaptive_halt and step < R - 1:
                conf = torch.sigmoid(self.confidence_head(scratchpad))
                if (conf > self.config.halt_threshold).all():
                    steps_taken = step + 1
                    break

        # Residual skip from initial answer — gradient highway through
        # the recursive refinement loop (standard practice for deep
        # recursive architectures to prevent gradient vanishing)
        answer = answer + 0.01 * initial_answer

        # Final confidence
        confidence = torch.sigmoid(self.confidence_head(scratchpad))

        # Track statistics
        if self.training:
            self._total_steps += steps_taken
            self._total_calls += 1

        # Decode to task-specific outputs
        outputs = self._decode_answer(answer)
        outputs["confidence"] = confidence
        outputs["num_steps"] = steps_taken
        return outputs

    @property
    def avg_steps(self) -> float:
        """Average refinement steps taken (for monitoring adaptive halting)."""
        if self._total_calls == 0:
            return 0.0
        return (self._total_steps / self._total_calls).item()


# ---------------------------------------------------------------------------
# Concrete Head Subclasses — one per TRM type
# ---------------------------------------------------------------------------

class RecursiveATPHead(RecursiveTRMHead):
    """ATP exception decisions: action (4-way) + fill_rate."""
    answer_dim = 6  # 4 action logits + 1 fill_rate + 1 value

    def _decode_answer(self, answer: torch.Tensor) -> Dict[str, torch.Tensor]:
        return {
            "action_probs": F.softmax(answer[:, :4], dim=-1),
            "fill_rate": torch.sigmoid(answer[:, 4:5]),
            "value": answer[:, 5:6],
        }


class RecursiveRebalancingHead(RecursiveTRMHead):
    """Inventory rebalancing: transfer_qty_mult + direction + value."""
    answer_dim = 4  # qty_mult + direction (2-way) + value

    def _decode_answer(self, answer: torch.Tensor) -> Dict[str, torch.Tensor]:
        return {
            "qty_multiplier": torch.sigmoid(answer[:, 0:1]) * 2,  # [0, 2]
            "direction_probs": F.softmax(answer[:, 1:3], dim=-1),
            "value": answer[:, 3:4],
        }


class RecursivePOHead(RecursiveTRMHead):
    """PO creation: timing (3-way) + expedite + days_offset + value."""
    answer_dim = 6  # 3 timing + 1 expedite + 1 days + 1 value

    def _decode_answer(self, answer: torch.Tensor) -> Dict[str, torch.Tensor]:
        return {
            "timing_probs": F.softmax(answer[:, :3], dim=-1),
            "expedite_prob": torch.sigmoid(answer[:, 3:4]),
            "days_offset": torch.tanh(answer[:, 4:5]) * 7,
            "value": answer[:, 5:6],
        }


class RecursiveOrderTrackingHead(RecursiveTRMHead):
    """Order tracking: exception action (5-way) + severity + value."""
    answer_dim = 7  # 5 action + 1 severity + 1 value

    def _decode_answer(self, answer: torch.Tensor) -> Dict[str, torch.Tensor]:
        return {
            "action_probs": F.softmax(answer[:, :5], dim=-1),
            "severity": torch.sigmoid(answer[:, 5:6]),
            "value": answer[:, 6:7],
        }


class RecursiveMOHead(RecursiveTRMHead):
    """MO execution: action (5-way: release/sequence/split/expedite/defer) + value."""
    answer_dim = 6  # 5 action + 1 value

    def _decode_answer(self, answer: torch.Tensor) -> Dict[str, torch.Tensor]:
        return {
            "action_probs": F.softmax(answer[:, :5], dim=-1),
            "value": answer[:, 5:6],
        }


class RecursiveTOHead(RecursiveTRMHead):
    """TO execution: action (4-way: release/consolidate/expedite/defer) + value."""
    answer_dim = 5  # 4 action + 1 value

    def _decode_answer(self, answer: torch.Tensor) -> Dict[str, torch.Tensor]:
        return {
            "action_probs": F.softmax(answer[:, :4], dim=-1),
            "value": answer[:, 4:5],
        }


class RecursiveQualityHead(RecursiveTRMHead):
    """Quality disposition: action (5-way: accept/reject/rework/scrap/use-as-is) + value."""
    answer_dim = 6  # 5 action + 1 value

    def _decode_answer(self, answer: torch.Tensor) -> Dict[str, torch.Tensor]:
        return {
            "action_probs": F.softmax(answer[:, :5], dim=-1),
            "value": answer[:, 5:6],
        }


class RecursiveMaintenanceHead(RecursiveTRMHead):
    """Maintenance scheduling: action (4-way: schedule/defer/expedite/outsource) + value."""
    answer_dim = 5  # 4 action + 1 value

    def _decode_answer(self, answer: torch.Tensor) -> Dict[str, torch.Tensor]:
        return {
            "action_probs": F.softmax(answer[:, :4], dim=-1),
            "value": answer[:, 4:5],
        }


class RecursiveSubcontractingHead(RecursiveTRMHead):
    """Subcontracting: action (3-way: internal/external/split) + split_ratio + value."""
    answer_dim = 5  # 3 action + 1 split_ratio + 1 value

    def _decode_answer(self, answer: torch.Tensor) -> Dict[str, torch.Tensor]:
        return {
            "action_probs": F.softmax(answer[:, :3], dim=-1),
            "split_ratio": torch.sigmoid(answer[:, 3:4]),
            "value": answer[:, 4:5],
        }


class RecursiveForecastAdjHead(RecursiveTRMHead):
    """Forecast adjustment: direction (3-way: up/down/none) + magnitude + value."""
    answer_dim = 5  # 3 direction + 1 magnitude + 1 value

    def _decode_answer(self, answer: torch.Tensor) -> Dict[str, torch.Tensor]:
        return {
            "direction_probs": F.softmax(answer[:, :3], dim=-1),
            "magnitude": torch.sigmoid(answer[:, 3:4]),  # [0, 1] fraction
            "value": answer[:, 4:5],
        }


class RecursiveSafetyStockHead(RecursiveTRMHead):
    """Safety stock adjustment: ss_multiplier + rop_multiplier + value."""
    answer_dim = 3  # ss_mult + rop_mult + value

    def _decode_answer(self, answer: torch.Tensor) -> Dict[str, torch.Tensor]:
        # Map to [0.8, 1.2] range
        return {
            "ss_multiplier": torch.tanh(answer[:, 0:1]) * 0.2 + 1.0,
            "rop_multiplier": torch.tanh(answer[:, 1:2]) * 0.2 + 1.0,
            "value": answer[:, 2:3],
        }


# Registry for lookup by TRM type name
RECURSIVE_HEAD_REGISTRY: Dict[str, type] = {
    "atp_executor": RecursiveATPHead,
    "rebalancing": RecursiveRebalancingHead,
    "po_creation": RecursivePOHead,
    "order_tracking": RecursiveOrderTrackingHead,
    "mo_execution": RecursiveMOHead,
    "to_execution": RecursiveTOHead,
    "quality_disposition": RecursiveQualityHead,
    "maintenance_scheduling": RecursiveMaintenanceHead,
    "subcontracting": RecursiveSubcontractingHead,
    "forecast_adjustment": RecursiveForecastAdjHead,
    "safety_stock": RecursiveSafetyStockHead,
}
