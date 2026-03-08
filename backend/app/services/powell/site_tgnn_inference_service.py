"""
Site tGNN Inference Service (Layer 1.5) — Hourly Intra-Site Cross-TRM Coordination.

Runs inference on the Site tGNN model to produce per-TRM urgency adjustments
that modulate the UrgencyVector before the 6-phase decision cycle executes.

Key behaviors:
- Cold start: Returns neutral output (zero adjustments) when no model is trained
- Hidden state persists across hourly ticks for temporal continuity
- Feature disabled: Zero overhead when enable_site_tgnn=False (not instantiated)
- Thread-safe: All tensor ops are inference-only (torch.no_grad)

Architecture reference: TRM_HIVE_ARCHITECTURE.md Section 16.3.5
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from app.models.gnn.site_tgnn import (
    SiteTGNN,
    TRM_NAMES,
    TRM_NAME_TO_IDX,
    NUM_TRM_TYPES,
)
from app.services.powell.hive_signal import (
    HiveSignalBus,
    HiveSignalType,
    UrgencyVector,
    SCOUT_SIGNALS,
    FORAGER_SIGNALS,
    NURSE_SIGNALS,
    GUARD_SIGNALS,
    BUILDER_SIGNALS,
)
from app.services.powell.hive_feedback import HiveFeedbackFeatures
from app.services.powell.site_capabilities import ALL_TRM_NAMES as _ALL_TRMS


# ============================================================================
# SiteTGNNOutput — per-TRM adjustment outputs
# ============================================================================

@dataclass
class SiteTGNNOutput:
    """Output from Site tGNN inference.

    urgency_adjustments: TRM name -> [-0.3, +0.3] delta applied to UrgencyVector
    confidence_modifiers: TRM name -> [-0.2, +0.2] delta to TRM confidence threshold
    coordination_signals: TRM name -> [0, 1] attention weight for cross-TRM signals
    """

    urgency_adjustments: Dict[str, float] = field(default_factory=dict)
    confidence_modifiers: Dict[str, float] = field(default_factory=dict)
    coordination_signals: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def neutral(cls) -> SiteTGNNOutput:
        """Return neutral output (zero adjustments). Used for cold start."""
        return cls(
            urgency_adjustments={t: 0.0 for t in TRM_NAMES},
            confidence_modifiers={t: 0.0 for t in TRM_NAMES},
            coordination_signals={t: 0.5 for t in TRM_NAMES},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "urgency_adjustments": {k: round(v, 4) for k, v in self.urgency_adjustments.items()},
            "confidence_modifiers": {k: round(v, 4) for k, v in self.confidence_modifiers.items()},
            "coordination_signals": {k: round(v, 4) for k, v in self.coordination_signals.items()},
        }


# ============================================================================
# TRM-to-caste mapping for signal density feature
# ============================================================================

_TRM_CASTE_SIGNALS: Dict[str, frozenset] = {
    "atp_executor": SCOUT_SIGNALS,
    "order_tracking": SCOUT_SIGNALS,
    "po_creation": FORAGER_SIGNALS,
    "rebalancing": FORAGER_SIGNALS,
    "subcontracting": FORAGER_SIGNALS,
    "inventory_buffer": NURSE_SIGNALS,
    "forecast_adj": NURSE_SIGNALS,
    "quality": GUARD_SIGNALS,
    "maintenance": GUARD_SIGNALS,
    "mo_execution": BUILDER_SIGNALS,
    "to_execution": BUILDER_SIGNALS,
}


# ============================================================================
# SiteTGNNInferenceService
# ============================================================================

# Short name -> canonical name alias mapping (Site tGNN uses short names)
_SHORT_TO_CANONICAL: Dict[str, str] = {
    "forecast_adj": "forecast_adjustment",
    "quality": "quality_disposition",
    "maintenance": "maintenance_scheduling",
}

def _canonical_alias(short_name: str) -> str:
    """Return canonical TRM name for a short alias, or the name itself."""
    return _SHORT_TO_CANONICAL.get(short_name, short_name)


class SiteTGNNInferenceService:
    """Hourly intra-site inference for cross-TRM coordination (Layer 1.5).

    Loads a Site tGNN checkpoint and runs inference to produce per-TRM
    urgency adjustments. Hidden state persists across calls for temporal
    continuity (GRU memory).

    Usage:
        service = SiteTGNNInferenceService(site_key="FOODDIST_DC", config_id=22)
        output = service.infer(signal_bus, urgency_vector, recent_decisions, feedback)
        for trm_name, adj in output.urgency_adjustments.items():
            urgency_vector.adjust(TRM_INDICES[trm_name], adj)
    """

    INPUT_DIM = 18  # Per-TRM feature vector dimension

    def __init__(
        self,
        site_key: str,
        config_id: int,
        active_trms: Optional[frozenset] = None,
    ):
        self.site_key = site_key
        self.config_id = config_id
        self.model: Optional[SiteTGNN] = None
        self.hidden_state: Optional[Any] = None  # torch.Tensor or None
        self._device = "cpu"  # Site tGNN always runs on CPU (<5ms)

        # Active TRM mask — inactive nodes get zeroed features + output
        self.active_trms = active_trms or _ALL_TRMS
        # Build index mask: which TRM_NAMES indices are active
        self._active_mask: List[bool] = [
            name in self.active_trms
            or _canonical_alias(name) in self.active_trms
            for name in TRM_NAMES
        ]

        self._load_checkpoint()

    def _load_checkpoint(self) -> None:
        """Load trained Site tGNN checkpoint if available."""
        if not HAS_TORCH:
            logger.debug("PyTorch not available, Site tGNN disabled")
            return

        checkpoint_dir = os.path.join("checkpoints", "site_tgnn", self.site_key)
        checkpoint_path = os.path.join(checkpoint_dir, "site_tgnn_latest.pt")

        if not os.path.exists(checkpoint_path):
            logger.info(
                f"No Site tGNN checkpoint at {checkpoint_path} — "
                f"cold start (neutral output)"
            )
            return

        try:
            checkpoint = torch.load(checkpoint_path, map_location=self._device, weights_only=False)
            self.model = SiteTGNN(input_dim=checkpoint.get("input_dim", self.INPUT_DIM))
            self.model.load_state_dict(checkpoint["model_state_dict"])
            self.model.eval()
            logger.info(
                f"Loaded Site tGNN for {self.site_key} "
                f"({self.model.count_parameters()} params)"
            )
        except Exception as e:
            logger.warning(f"Failed to load Site tGNN checkpoint: {e}")
            self.model = None

    def infer(
        self,
        hive_signal_bus: Optional[HiveSignalBus],
        urgency_vector: Optional[UrgencyVector],
        recent_decisions: Optional[Dict[str, List]] = None,
        hive_feedback: Optional[HiveFeedbackFeatures] = None,
    ) -> SiteTGNNOutput:
        """Run Site tGNN inference. Returns per-TRM adjustments.

        Args:
            hive_signal_bus: Current HiveSignalBus state
            urgency_vector: Current UrgencyVector
            recent_decisions: Dict mapping TRM name -> list of recent decision dicts
            hive_feedback: Current HiveFeedbackFeatures snapshot

        Returns:
            SiteTGNNOutput with urgency_adjustments, confidence_modifiers,
            coordination_signals per TRM. Neutral output if no model loaded.
        """
        if self.model is None or not HAS_TORCH:
            return SiteTGNNOutput.neutral()

        features = self._build_node_features(
            hive_signal_bus, urgency_vector,
            recent_decisions or {}, hive_feedback,
        )

        # Convert to tensor: [1, 11, input_dim]
        x = torch.tensor(features, dtype=torch.float32, device=self._device).unsqueeze(0)

        with torch.no_grad():
            raw_output, self.hidden_state = self.model(x, self.hidden_state)

        # raw_output: [1, 11, 3]
        output_np = raw_output[0].cpu().numpy()

        # Mask inactive TRMs: zero adjustments for nodes this site doesn't use
        return SiteTGNNOutput(
            urgency_adjustments={
                TRM_NAMES[i]: float(output_np[i, 0]) if self._active_mask[i] else 0.0
                for i in range(NUM_TRM_TYPES)
            },
            confidence_modifiers={
                TRM_NAMES[i]: float(output_np[i, 1]) if self._active_mask[i] else 0.0
                for i in range(NUM_TRM_TYPES)
            },
            coordination_signals={
                TRM_NAMES[i]: float(output_np[i, 2]) if self._active_mask[i] else 0.5
                for i in range(NUM_TRM_TYPES)
            },
        )

    def reset_hidden_state(self) -> None:
        """Reset GRU hidden state (e.g., at config reload or model update)."""
        self.hidden_state = None

    def reload_checkpoint(self) -> None:
        """Reload model from disk (e.g., after retraining)."""
        self.hidden_state = None
        self._load_checkpoint()

    # ──────────────────────────────────────────────────────────────────────
    # Feature engineering
    # ──────────────────────────────────────────────────────────────────────

    def _build_node_features(
        self,
        signal_bus: Optional[HiveSignalBus],
        urgency_vector: Optional[UrgencyVector],
        recent_decisions: Dict[str, List],
        feedback: Optional[HiveFeedbackFeatures],
    ) -> np.ndarray:
        """Build 11 x 18 feature matrix for Site tGNN input.

        Per-TRM features (18 dims):
          0: urgency                 — Current UrgencyVector slot value
          1: recent_decision_count   — Decisions in last hour
          2: avg_confidence          — Mean TRM confidence last hour
          3: override_rate           — Human override rate (rolling 24h)
          4: reward_ema              — EMA of decision rewards
          5: cdc_trigger_count       — CDC triggers in last 24h
          6: signal_density          — Signals read from bus in last hour
          7: signal_emission_rate    — Signals emitted in last hour
          8: fill_rate_contribution  — TRM contribution to site fill rate
          9: capacity_utilization    — Resource utilization for TRM
         10: backlog_pressure        — Outstanding backlogs
         11: phase_position          — TRM phase index (0-5), normalized
         12-17: hive_feedback_slice  — 6 dims from HiveFeedbackFeatures
        """
        features = np.zeros((NUM_TRM_TYPES, self.INPUT_DIM), dtype=np.float32)

        # Get urgency values
        urgency_values = [0.0] * NUM_TRM_TYPES
        if urgency_vector:
            urgency_values = urgency_vector.values_array()

        # Get feedback tensor
        feedback_arr = np.zeros(8, dtype=np.float32)
        if feedback:
            feedback_arr = feedback.to_tensor()

        for i, trm_name in enumerate(TRM_NAMES):
            # Skip inactive TRMs — leave features as zeros (masked node)
            if not self._active_mask[i]:
                continue

            # 0: urgency
            features[i, 0] = urgency_values[i] if i < len(urgency_values) else 0.0

            # 1-5: decision statistics from recent_decisions
            decisions = recent_decisions.get(trm_name, [])
            features[i, 1] = min(len(decisions) / 10.0, 1.0)  # Normalized count

            if decisions:
                confidences = [d.get("confidence", 0.5) for d in decisions if isinstance(d, dict)]
                features[i, 2] = np.mean(confidences) if confidences else 0.5
                overrides = [d for d in decisions if isinstance(d, dict) and d.get("was_overridden")]
                features[i, 3] = len(overrides) / max(len(decisions), 1)
                rewards = [d.get("reward", 0.0) for d in decisions if isinstance(d, dict)]
                features[i, 4] = np.mean(rewards) if rewards else 0.0
            else:
                features[i, 2] = 0.5
                features[i, 3] = 0.0
                features[i, 4] = 0.0

            # 5: cdc_trigger_count (from decision metadata)
            cdc_triggers = [d for d in decisions if isinstance(d, dict) and d.get("cdc_triggered")]
            features[i, 5] = min(len(cdc_triggers) / 5.0, 1.0)

            # 6-7: signal density from bus
            if signal_bus:
                caste_signals = _TRM_CASTE_SIGNALS.get(trm_name, frozenset())
                relevant = signal_bus.read(signal_types=caste_signals) if caste_signals else []
                features[i, 6] = min(len(relevant) / 10.0, 1.0)
                # Emission rate from decisions that emitted signals
                emitters = [d for d in decisions if isinstance(d, dict) and d.get("signal_emitted")]
                features[i, 7] = min(len(emitters) / 5.0, 1.0)

            # 8-10: operational features (from decision aggregates)
            features[i, 8] = self._extract_fill_rate(trm_name, decisions)
            features[i, 9] = self._extract_capacity(trm_name, decisions)
            features[i, 10] = self._extract_backlog(trm_name, decisions)

            # 11: phase position (normalized 0-1)
            from app.services.powell.decision_cycle import TRM_PHASE_MAP
            phase = TRM_PHASE_MAP.get(trm_name)
            phase_idx = phase.value if phase is not None else 0
            features[i, 11] = phase_idx / 6.0

            # 12-17: hive feedback slice (6 dims from 8-dim feedback)
            # Map: avg_urgency, urgency_spread, signal_rate, conflict_rate,
            #       cross_head_reward, exception_rate
            features[i, 12] = feedback_arr[0]  # avg_urgency
            features[i, 13] = feedback_arr[1]  # urgency_spread
            features[i, 14] = feedback_arr[2]  # signal_rate
            features[i, 15] = feedback_arr[3]  # conflict_rate
            features[i, 16] = feedback_arr[4]  # cross_head_reward
            features[i, 17] = feedback_arr[7]  # exception_rate

        return features

    def _extract_fill_rate(self, trm_name: str, decisions: List) -> float:
        """Extract fill rate contribution from decision data."""
        if not decisions:
            return 0.5
        fill_rates = [
            d.get("fill_rate", 0.5) for d in decisions
            if isinstance(d, dict) and "fill_rate" in d
        ]
        return np.mean(fill_rates) if fill_rates else 0.5

    def _extract_capacity(self, trm_name: str, decisions: List) -> float:
        """Extract capacity utilization from decision data."""
        if not decisions:
            return 0.5
        caps = [
            d.get("capacity_utilization", 0.5) for d in decisions
            if isinstance(d, dict) and "capacity_utilization" in d
        ]
        return np.mean(caps) if caps else 0.5

    def _extract_backlog(self, trm_name: str, decisions: List) -> float:
        """Extract backlog pressure from decision data."""
        if not decisions:
            return 0.0
        backlogs = [
            d.get("backlog_pressure", 0.0) for d in decisions
            if isinstance(d, dict) and "backlog_pressure" in d
        ]
        return min(np.mean(backlogs), 1.0) if backlogs else 0.0
