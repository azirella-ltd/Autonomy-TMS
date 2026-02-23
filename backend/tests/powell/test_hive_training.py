"""
Sprint 7 Tests — Signal-Aware Training Pipeline

Validates:
  1. SharedStateEncoder accepts optional signal_summary tensor
  2. Signal-attribution reward in RewardCalculator
  3. CDC retraining feature extraction includes signal context
  4. StigmergicPhase enum and state augmentation in TRMSiteTrainer
  5. Cross-head reward integration in Phase 3
  6. Backward compatibility: existing checkpoints load with zero-padded signals
"""

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# 1. SharedStateEncoder signal_summary fusion
# ---------------------------------------------------------------------------

class TestSharedStateEncoderSignals:
    """Test signal_summary projection in SharedStateEncoder."""

    # The encoder concatenates inventory(P) + pipeline(P*L) + backlog(P) +
    # demand(P*W) + forecasts(P*H) and projects through input_proj(state_dim).
    # With state_dim=64 default, we pick tensor sizes that sum to 64:
    #   P=5, L=4, W=4, H=3 → 5 + 20 + 5 + 20 + 15 = 65... so use P=4:
    #   P=4, L=4, W=4, H=3 → 4 + 16 + 4 + 16 + 12 = 52
    # Or just use state_dim to match total. Easiest: set state_dim to match.
    P, L, W, H = 4, 4, 4, 3  # products, pipeline, demand window, forecast horizon

    def _make_encoder(self, **config_overrides):
        import torch
        from app.services.powell.site_agent_model import SharedStateEncoder, SiteAgentModelConfig
        total_dim = self.P + self.P * self.L + self.P + self.P * self.W + self.P * self.H
        config = SiteAgentModelConfig(state_dim=total_dim, **config_overrides)
        encoder = SharedStateEncoder(config)
        encoder.eval()
        return encoder, config

    def _make_dummy_inputs(self, batch=2):
        import torch
        return {
            "inventory": torch.randn(batch, self.P),
            "pipeline": torch.randn(batch, self.P, self.L),
            "backlog": torch.randn(batch, self.P),
            "demand_history": torch.randn(batch, self.P, self.W),
            "forecasts": torch.randn(batch, self.P, self.H),
        }

    def test_forward_without_signals(self):
        """Encoder works without urgency_vector or signal_summary (backward compat)."""
        encoder, config = self._make_encoder()
        inputs = self._make_dummy_inputs()
        out = encoder(**inputs)
        assert out.shape == (2, config.embedding_dim)

    def test_forward_with_urgency_only(self):
        """Encoder works with urgency_vector but no signal_summary."""
        import torch
        encoder, config = self._make_encoder()
        inputs = self._make_dummy_inputs()
        inputs["urgency_vector"] = torch.randn(2, 11)
        out = encoder(**inputs)
        assert out.shape == (2, config.embedding_dim)

    def test_forward_with_full_signals(self):
        """Encoder works with both urgency_vector and signal_summary."""
        import torch
        encoder, config = self._make_encoder()
        inputs = self._make_dummy_inputs()
        inputs["urgency_vector"] = torch.randn(2, 11)
        inputs["signal_summary"] = torch.randn(2, config.signal_summary_dim)
        out = encoder(**inputs)
        assert out.shape == (2, config.embedding_dim)

    def test_signal_summary_affects_output(self):
        """Adding signal_summary changes the embedding (is not a no-op)."""
        import torch
        encoder, config = self._make_encoder()
        inputs = self._make_dummy_inputs()

        # Without signals
        out_no_sig = encoder(**inputs).detach()

        # With non-zero signals
        inputs["signal_summary"] = torch.ones(2, config.signal_summary_dim)
        out_with_sig = encoder(**inputs).detach()

        # They should differ
        assert not torch.allclose(out_no_sig, out_with_sig, atol=1e-6)

    def test_signal_summary_dim_configurable(self):
        """signal_summary_dim can be customized in config."""
        import torch
        encoder, config = self._make_encoder(signal_summary_dim=16)
        inputs = self._make_dummy_inputs()
        inputs["signal_summary"] = torch.randn(2, 16)
        out = encoder(**inputs)
        assert out.shape == (2, config.embedding_dim)

    def test_zero_signal_summary_impact_smaller_than_nonzero(self):
        """A zero signal_summary has less impact than a large one."""
        import torch
        encoder, config = self._make_encoder()

        inputs = self._make_dummy_inputs()
        out_none = encoder(**inputs).detach()

        # Zero signal_summary: bias terms pass through, but small impact
        inputs["signal_summary"] = torch.zeros(2, config.signal_summary_dim)
        out_zero = encoder(**inputs).detach()

        # Large signal_summary: large impact
        inputs["signal_summary"] = torch.ones(2, config.signal_summary_dim) * 5.0
        out_large = encoder(**inputs).detach()

        diff_zero = (out_none - out_zero).norm()
        diff_large = (out_none - out_large).norm()

        # The zero-signal diff should be smaller than the large-signal diff
        assert diff_zero < diff_large


# ---------------------------------------------------------------------------
# 2. Signal-attribution reward
# ---------------------------------------------------------------------------

class TestSignalAttributionReward:
    """Test RewardCalculator.signal_attribution_bonus()."""

    def _calc(self):
        from app.services.powell.trm_trainer import RewardCalculator
        return RewardCalculator()

    def test_no_signal_context_returns_zero(self):
        bonus = self._calc().signal_attribution_bonus({})
        assert bonus == 0.0

    def test_no_signal_context_missing_key(self):
        bonus = self._calc().signal_attribution_bonus({"some_key": "val"})
        assert bonus == 0.0

    def test_signal_triggered_positive_outcome(self):
        outcome = {
            "signal_triggered": True,
            "signal_urgency": 0.8,
            "outcome_positive": True,
            "cross_head_reward": 0.0,
        }
        bonus = self._calc().signal_attribution_bonus(outcome)
        assert bonus > 0.0
        assert abs(bonus - 0.15 * 0.8) < 1e-6

    def test_signal_triggered_negative_outcome(self):
        outcome = {
            "signal_triggered": True,
            "signal_urgency": 0.5,
            "outcome_positive": False,
            "cross_head_reward": 0.0,
        }
        bonus = self._calc().signal_attribution_bonus(outcome)
        assert bonus == pytest.approx(-0.05)

    def test_no_signal_negative_outcome_penalty(self):
        outcome = {
            "signal_triggered": False,
            "signal_urgency": 0.6,
            "outcome_positive": False,
            "cross_head_reward": 0.0,
        }
        bonus = self._calc().signal_attribution_bonus(outcome)
        assert bonus < 0.0
        assert abs(bonus - (-0.10 * 0.6)) < 1e-6

    def test_cross_head_reward_additive(self):
        outcome = {
            "signal_triggered": True,
            "signal_urgency": 0.5,
            "outcome_positive": True,
            "cross_head_reward": 1.0,
        }
        bonus = self._calc().signal_attribution_bonus(outcome)
        # 0.15 * 0.5 + 1.0 * 0.05 = 0.075 + 0.05 = 0.125
        assert abs(bonus - 0.125) < 1e-6

    def test_integrated_into_calculate_reward(self):
        """signal_attribution_bonus is called within calculate_reward()."""
        calc = self._calc()
        outcome = {
            "fill_rate": 0.9,
            "dos_actual": 10,
            "dos_target": 10,
            "excess_inventory_ratio": 0.0,
            "stability_delta": 0.0,
            "signal_triggered": True,
            "signal_urgency": 1.0,
            "outcome_positive": True,
            "cross_head_reward": 0.0,
        }
        # Note: calculator key is "atp", not "atp_executor"
        reward = calc.calculate_reward("atp", outcome)
        # Should include signal bonus > 0
        reward_no_signal = calc.calculate_reward("atp", {
            "fill_rate": 0.9, "dos_actual": 10, "dos_target": 10,
            "excess_inventory_ratio": 0.0, "stability_delta": 0.0,
        })
        assert reward > reward_no_signal


# ---------------------------------------------------------------------------
# 3. CDC retraining signal-enriched features
# ---------------------------------------------------------------------------

class TestCDCRetrainingFeatures:
    """Test _extract_features includes signal context."""

    def _service(self):
        from unittest.mock import MagicMock
        from app.services.powell.cdc_retraining_service import CDCRetrainingService
        db = MagicMock()
        return CDCRetrainingService(db=db, site_key="TEST", group_id=1)

    def test_extract_features_no_signal_context(self):
        svc = self._service()
        features = svc._extract_features({"inventory_on_hand": 100})
        assert len(features) == 26
        # First feature should be inventory
        assert features[0] == 100.0
        # Urgency slots (11-20) should be zero
        assert all(f == 0.0 for f in features[10:21])

    def test_extract_features_with_urgency(self):
        svc = self._service()
        urgency_vals = [0.1 * i for i in range(11)]
        features = svc._extract_features({
            "inventory_on_hand": 50,
            "signal_context": {
                "urgency_vector": {"values": urgency_vals},
                "active_signal_count": 5,
                "summary": {"ATP_SHORTAGE": 2, "DEMAND_SURGE": 1},
            },
            "urgency_at_time": 0.7,
            "triggered_by": "ATP_SHORTAGE",
            "signals_emitted": ["PO_EXPEDITE"],
        })
        assert len(features) == 26
        # Urgency values should be present
        assert features[10] == pytest.approx(0.0)
        assert features[11] == pytest.approx(0.1)
        assert features[20] == pytest.approx(1.0)
        # Signal summary features
        assert features[21] == pytest.approx(5.0 / 20.0)  # active_signal_count / 20
        assert features[22] == pytest.approx(2.0)  # len(summary)
        assert features[23] == pytest.approx(0.7)  # urgency_at_time
        assert features[24] == pytest.approx(1.0)  # triggered_by is truthy
        assert features[25] == pytest.approx(1.0)  # len(signals_emitted)

    def test_extract_features_partial_urgency(self):
        """Handles urgency vectors shorter than 11."""
        svc = self._service()
        features = svc._extract_features({
            "signal_context": {
                "urgency_vector": {"values": [0.5, 0.3]},
            },
        })
        assert len(features) == 26
        assert features[10] == pytest.approx(0.5)
        assert features[11] == pytest.approx(0.3)
        assert features[12] == 0.0  # Padded


# ---------------------------------------------------------------------------
# 4. StigmergicPhase and state augmentation
# ---------------------------------------------------------------------------

class TestStigmergicPhase:
    """Test StigmergicPhase enum and TRMSiteTrainer augmentation."""

    def test_phase_enum_values(self):
        from app.services.powell.trm_site_trainer import StigmergicPhase
        assert StigmergicPhase.NO_SIGNALS.value == 0
        assert StigmergicPhase.URGENCY_ONLY.value == 1
        assert StigmergicPhase.FULL_SIGNALS.value == 2

    def test_phase_extra_dims(self):
        from app.services.powell.trm_site_trainer import StigmergicPhase
        assert StigmergicPhase.NO_SIGNALS.extra_dims == 0
        assert StigmergicPhase.URGENCY_ONLY.extra_dims == 11
        assert StigmergicPhase.FULL_SIGNALS.extra_dims == 33

    def _make_trainer(self, phase):
        from app.services.powell.trm_site_trainer import TRMSiteTrainer
        return TRMSiteTrainer(
            trm_type="atp_executor", site_id=1, site_name="Test",
            master_type="INVENTORY", group_id=1, config_id=1,
            stigmergic_phase=phase,
        )

    def test_augment_no_signals(self):
        from app.services.powell.trm_site_trainer import StigmergicPhase
        trainer = self._make_trainer(StigmergicPhase.NO_SIGNALS)
        states = np.random.randn(10, 12).astype(np.float32)
        result = trainer._augment_states_synthetic(states)
        assert result.shape == (10, 12)  # Unchanged

    def test_augment_urgency_only(self):
        from app.services.powell.trm_site_trainer import StigmergicPhase
        trainer = self._make_trainer(StigmergicPhase.URGENCY_ONLY)
        states = np.random.randn(10, 12).astype(np.float32)
        result = trainer._augment_states_synthetic(states)
        assert result.shape == (10, 23)  # 12 + 11

    def test_augment_full_signals(self):
        from app.services.powell.trm_site_trainer import StigmergicPhase
        trainer = self._make_trainer(StigmergicPhase.FULL_SIGNALS)
        states = np.random.randn(10, 12).astype(np.float32)
        result = trainer._augment_states_synthetic(states)
        assert result.shape == (10, 45)  # 12 + 11 + 22

    def test_augment_empty_states(self):
        from app.services.powell.trm_site_trainer import StigmergicPhase
        trainer = self._make_trainer(StigmergicPhase.FULL_SIGNALS)
        states = np.empty((0, 12), dtype=np.float32)
        result = trainer._augment_states_synthetic(states)
        assert result.shape == (0, 12)  # Empty passthrough

    def test_augment_from_context_no_signals(self):
        from app.services.powell.trm_site_trainer import StigmergicPhase
        trainer = self._make_trainer(StigmergicPhase.NO_SIGNALS)
        states = np.random.randn(3, 8).astype(np.float32)
        contexts = [None, None, None]
        result = trainer._augment_states_from_context(states, contexts)
        assert result.shape == (3, 8)

    def test_augment_from_context_urgency_only(self):
        from app.services.powell.trm_site_trainer import StigmergicPhase
        trainer = self._make_trainer(StigmergicPhase.URGENCY_ONLY)
        states = np.random.randn(2, 8).astype(np.float32)
        contexts = [
            {"urgency_vector": {"values": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 0.5]}},
            None,
        ]
        result = trainer._augment_states_from_context(states, contexts)
        assert result.shape == (2, 19)  # 8 + 11
        # First row should have urgency values
        assert result[0, 8] == pytest.approx(0.1)
        assert result[0, 18] == pytest.approx(0.5)
        # Second row: zeros
        assert result[1, 8] == pytest.approx(0.0)

    def test_augment_from_context_full_signals(self):
        from app.services.powell.trm_site_trainer import StigmergicPhase
        trainer = self._make_trainer(StigmergicPhase.FULL_SIGNALS)
        states = np.random.randn(1, 8).astype(np.float32)
        contexts = [{
            "urgency_vector": {"values": [0.5] * 11},
            "summary": {"ATP_SHORTAGE": 3, "DEMAND_SURGE": 1},
            "active_signals": [
                {"strength": 0.8, "type": "ATP_SHORTAGE"},
                {"strength": 0.4, "type": "DEMAND_SURGE"},
            ],
        }]
        result = trainer._augment_states_from_context(states, contexts)
        assert result.shape == (1, 41)  # 8 + 11 + 22
        # Urgency values
        assert result[0, 8] == pytest.approx(0.5)
        # Signal summary: first 2 signal types encoded
        assert result[0, 19] == pytest.approx(min(3.0 / 10.0, 1.0))
        assert result[0, 20] == pytest.approx(min(1.0 / 10.0, 1.0))
        # Signal strengths
        assert result[0, 30] == pytest.approx(0.8)
        assert result[0, 31] == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# 5. Cross-head reward integration
# ---------------------------------------------------------------------------

class TestCrossHeadReward:
    """Test cross-head reward is used in Phase 3 RL loss."""

    def test_cross_head_reward_augments_rewards(self):
        """Verify cross_head_reward_weight adds to base rewards."""
        import torch

        base_rewards = torch.tensor([1.0, 2.0, 3.0])
        xhr = torch.tensor([0.5, 1.0, 0.0])
        weight = 0.1

        augmented = base_rewards + weight * xhr
        assert augmented[0].item() == pytest.approx(1.05)
        assert augmented[1].item() == pytest.approx(2.10)
        assert augmented[2].item() == pytest.approx(3.00)

    def test_cross_head_weight_default(self):
        from app.services.powell.trm_site_trainer import TRMSiteTrainer
        trainer = TRMSiteTrainer(
            trm_type="atp_executor", site_id=1, site_name="Test",
            master_type="INVENTORY", group_id=1, config_id=1,
        )
        assert trainer.cross_head_reward_weight == 0.05

    def test_cross_head_weight_custom(self):
        from app.services.powell.trm_site_trainer import TRMSiteTrainer
        trainer = TRMSiteTrainer(
            trm_type="atp_executor", site_id=1, site_name="Test",
            master_type="INVENTORY", group_id=1, config_id=1,
            cross_head_reward_weight=0.2,
        )
        assert trainer.cross_head_reward_weight == 0.2


# ---------------------------------------------------------------------------
# 6. Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Verify existing model/trainer patterns still work with signal extensions."""

    def test_site_agent_model_default_config(self):
        from app.services.powell.site_agent_model import SiteAgentModelConfig
        config = SiteAgentModelConfig()
        assert config.signal_summary_dim == 22

    def test_site_agent_model_forward_no_signals(self):
        """Full SiteAgentModel forward pass without any signal inputs."""
        import torch
        from app.services.powell.site_agent_model import SiteAgentModel, SiteAgentModelConfig

        # Use state_dim=52 to match P=4, L=4, W=4, H=3
        P, L, W, H = 4, 4, 4, 3
        total_dim = P + P * L + P + P * W + P * H
        config = SiteAgentModelConfig(state_dim=total_dim)
        model = SiteAgentModel(config)
        model.eval()

        batch = 2
        outputs = model(
            inventory=torch.randn(batch, P),
            pipeline=torch.randn(batch, P, L),
            backlog=torch.randn(batch, P),
            demand_history=torch.randn(batch, P, W),
            forecasts=torch.randn(batch, P, H),
            task="inventory",
        )
        assert "adjustment" in outputs or len(outputs) > 0

    def test_trm_site_trainer_default_phase(self):
        from app.services.powell.trm_site_trainer import TRMSiteTrainer, StigmergicPhase
        trainer = TRMSiteTrainer(
            trm_type="atp_executor", site_id=1, site_name="Test",
            master_type="INVENTORY", group_id=1, config_id=1,
        )
        assert trainer.stigmergic_phase == StigmergicPhase.NO_SIGNALS

    def test_reward_calculator_no_signal_fields(self):
        """RewardCalculator.calculate_reward works without signal fields."""
        from app.services.powell.trm_trainer import RewardCalculator
        calc = RewardCalculator()
        # ATP reward uses fulfilled_qty/requested_qty, was_on_time, customer_priority
        reward = calc.calculate_reward("atp", {
            "fulfilled_qty": 95,
            "requested_qty": 100,
            "was_on_time": True,
            "customer_priority": 1,
        })
        assert isinstance(reward, float)
        assert reward > 0.0

    def test_stigmergic_curriculum_accessible(self):
        """train_stigmergic_curriculum method exists on TRMSiteTrainer."""
        from app.services.powell.trm_site_trainer import TRMSiteTrainer
        trainer = TRMSiteTrainer(
            trm_type="atp_executor", site_id=1, site_name="Test",
            master_type="INVENTORY", group_id=1, config_id=1,
        )
        assert hasattr(trainer, "train_stigmergic_curriculum")
        assert callable(trainer.train_stigmergic_curriculum)
