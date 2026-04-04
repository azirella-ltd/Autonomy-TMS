"""
Forecast Baseline TRM — Statistical Demand Forecast Orchestration.

The 12th TRM. Orchestrates the baseline statistical forecast pipeline:
model selection, retraining decisions, cross-product feature management,
external signal integration, and conformal calibration.

TRM Scope:
- Given: Historical demand, product characteristics, external signals,
         cross-product features, conformal prediction intervals
- Decide: Which model for each product×site? Retrain now? Include signal?
          What confidence to assign? Correct for censored demand?

This TRM does NOT produce the forecast itself — it makes decisions ABOUT
the forecast pipeline. The actual forecasting is done by LightGBM/TFT/
Holt-Winters under the TRM's orchestration.

Phase: SENSE (Phase 1) — runs first to establish demand baseline
       before any other TRM acts.

Signals emitted:
- DEMAND_SURGE: when baseline forecast shows significant period-over-period increase
- DEMAND_DROP: when baseline forecast shows significant decline
- FORECAST_ADJUSTED: when model switch or retrain changes the forecast

Decision table: powell_forecast_baseline_decisions
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, date
import numpy as np
import hashlib
import json
import logging

from .hive_signal import HiveSignal, HiveSignalBus, HiveSignalType

try:
    from ..conformal_prediction.conformal_decision import get_cdt_registry
    _CDT_AVAILABLE = True
except ImportError:
    _CDT_AVAILABLE = False

logger = logging.getLogger(__name__)


# ── Demand classification (affects model selection) ──
# Based on Syntetos-Boylan classification framework
class DemandProfile:
    """Demand profile classification for model selection."""
    SMOOTH = "smooth"           # Low CV (<0.5), regular intervals → LightGBM, ETS
    ERRATIC = "erratic"         # High CV (>0.5), regular intervals → LightGBM with volatility features
    INTERMITTENT = "intermittent"  # Low CV, irregular (ADI>1.32) → Croston, SBA
    LUMPY = "lumpy"             # High CV, irregular intervals → Croston, or aggregate to family
    NEW = "new"                 # <26 observations → Holt-Winters, naive, or NPI transfer
    DECLINING = "declining"     # Consistent downtrend → lifecycle-aware model


# ── Model recommendation ──
MODEL_BY_PROFILE = {
    DemandProfile.SMOOTH: "lgbm",
    DemandProfile.ERRATIC: "lgbm_volatility",
    DemandProfile.INTERMITTENT: "croston",
    DemandProfile.LUMPY: "croston",
    DemandProfile.NEW: "holt_winters",
    DemandProfile.DECLINING: "lgbm_lifecycle",
}


# ── Drift detection thresholds ──
DRIFT_CUSUM_THRESHOLD = 5.0      # CUSUM statistic to trigger retrain
DRIFT_MAPE_DEGRADATION = 0.15    # 15% MAPE increase from baseline → retrain
MIN_OBSERVATIONS_LGBM = 26       # Minimum weeks for LightGBM
MIN_OBSERVATIONS_CROSTON = 12    # Minimum non-zero periods for Croston


@dataclass
class ForecastBaselineState:
    """State representation for forecast baseline TRM decisions."""
    product_id: str
    site_id: str

    # Demand profile
    demand_cv: float = 0.0                # Coefficient of variation
    demand_adi: float = 0.0               # Average Demand Interval (1.0 = every period)
    observation_count: int = 0            # Periods with history
    non_zero_count: int = 0               # Periods with non-zero demand
    trend_slope: float = 0.0              # Linear trend slope (positive = growing)
    seasonality_strength: float = 0.0     # 0-1, strength of seasonal pattern
    lifecycle_stage: str = "maturity"     # concept/launch/growth/maturity/decline/eol

    # Current model performance
    current_model: str = "lgbm"
    current_mape: float = 0.0             # Recent MAPE (last 8 weeks)
    baseline_mape: float = 0.0            # MAPE at last retrain
    cusum_statistic: float = 0.0          # CUSUM drift detector value

    # Current forecast
    current_p50: float = 0.0
    current_p10: float = 0.0
    current_p90: float = 0.0
    conformal_coverage: float = 0.80      # Actual coverage of conformal intervals

    # Cross-product context
    category_demand_trend: float = 0.0    # Category-level period-over-period change
    sibling_count: int = 0                # Products in same family
    sibling_share_change: float = 0.0     # This product's share of family demand vs prior period

    # External signals available
    external_signals_active: List[str] = field(default_factory=list)
    signal_fva_scores: Dict[str, float] = field(default_factory=dict)  # signal → FVA contribution

    # Censored demand indicators
    stockout_periods_pct: float = 0.0     # % of periods with zero inventory
    censored_demand_estimated: bool = False

    def classify_demand(self) -> str:
        """Classify demand profile using Syntetos-Boylan framework."""
        if self.observation_count < MIN_OBSERVATIONS_LGBM:
            return DemandProfile.NEW
        if self.trend_slope < -0.05 and self.lifecycle_stage in ("decline", "eol"):
            return DemandProfile.DECLINING

        cv_threshold = 0.5
        adi_threshold = 1.32

        if self.demand_cv < cv_threshold:
            if self.demand_adi <= adi_threshold:
                return DemandProfile.SMOOTH
            else:
                return DemandProfile.INTERMITTENT
        else:
            if self.demand_adi <= adi_threshold:
                return DemandProfile.ERRATIC
            else:
                return DemandProfile.LUMPY


@dataclass
class ForecastBaselineRecommendation:
    """TRM recommendation for baseline forecast pipeline."""
    product_id: str
    site_id: str

    # Model decision
    demand_profile: str                   # DemandProfile classification
    recommended_model: str                # "lgbm", "lgbm_volatility", "croston", "holt_winters", "tft", "naive"
    model_changed: bool = False           # True if recommending a switch from current

    # Retrain decision
    retrain_recommended: bool = False
    retrain_reason: Optional[str] = None  # "drift", "degradation", "new_data", "schedule"

    # Feature decisions
    cross_product_features_enabled: bool = True
    external_signals_enabled: List[str] = field(default_factory=list)
    censored_demand_correction: bool = False

    # Forecast output
    forecast_p50: float = 0.0
    forecast_p10: float = 0.0
    forecast_p90: float = 0.0
    forecast_periods: int = 12            # Number of periods forecasted
    forecast_method_used: str = ""

    # Quality metrics
    confidence: float = 0.0
    mape: float = 0.0
    conformal_interval_width: float = 0.0  # (P90 - P10) / P50 — wider = less certain
    fva_vs_naive: float = 0.0             # FVA: MAPE improvement over naive repeat

    # Demand signals detected
    demand_trend_signal: Optional[str] = None  # "surge", "drop", "stable"
    demand_trend_magnitude: float = 0.0

    # Metadata
    reason: str = ""
    context_explanation: Optional[Dict] = None
    risk_bound: Optional[float] = None
    risk_assessment: Optional[Dict] = None


@dataclass
class ForecastBaselineTRMConfig:
    """Configuration for the Forecast Baseline TRM."""
    # Model selection
    prefer_model: Optional[str] = None    # Force a specific model (None = auto)
    min_lgbm_observations: int = 26
    min_croston_observations: int = 12

    # Drift detection
    cusum_threshold: float = DRIFT_CUSUM_THRESHOLD
    mape_degradation_threshold: float = DRIFT_MAPE_DEGRADATION
    retrain_cooldown_hours: int = 168     # 7 days between retrains

    # Cross-product features
    enable_category_features: bool = True
    enable_substitution_features: bool = True
    enable_product_embeddings: bool = False  # Requires pre-computed embeddings

    # External signals
    enable_external_signals: bool = True
    signal_fva_threshold: float = 0.0     # Minimum FVA to include signal (0 = include all)

    # Censored demand
    enable_censored_correction: bool = True
    stockout_threshold: float = 0.10      # >10% stockout periods → apply correction

    # Conformal calibration
    conformal_target_coverage: float = 0.80

    # TRM model
    use_trm_model: bool = True
    confidence_threshold: float = 0.7


class ForecastBaselineTRM:
    """
    Forecast Baseline TRM — 12th TRM in the Powell Framework.

    Orchestrates the statistical demand forecast pipeline. Makes decisions
    about model selection, retraining, feature engineering, and quality
    assessment. Does NOT produce forecasts directly — orchestrates the
    LightGBM/TFT/Holt-Winters pipeline.

    Phase: SENSE (Phase 1) — establishes demand baseline before other TRMs act.
    Site types: All (Manufacturer, DC, Retailer) — every site has demand.
    """

    def __init__(self, site_key: str, config=None, model=None, db_session=None):
        self.site_key = site_key
        self.config = config or ForecastBaselineTRMConfig()
        self.model = model  # Optional trained PyTorch model for decision-making
        self.db = db_session
        self.ctx_explainer = None  # Set by SiteAgent
        self.signal_bus: Optional[HiveSignalBus] = None
        self._cdt_wrapper = None
        self._last_retrain: Optional[datetime] = None
        if _CDT_AVAILABLE:
            try:
                self._cdt_wrapper = get_cdt_registry().get_or_create("forecast_baseline")
            except Exception:
                pass

    # ── Signal Integration ──

    def _read_signals_before_decision(self) -> Dict[str, Any]:
        """Read hive signals relevant to baseline forecasting."""
        if self.signal_bus is None:
            return {}
        try:
            signals = self.signal_bus.read(
                consumer_trm="forecast_baseline",
                types={
                    HiveSignalType.DEMAND_SURGE,
                    HiveSignalType.DEMAND_DROP,
                    HiveSignalType.ALLOCATION_REFRESH,
                },
            )
            context = {}
            for s in signals:
                if s.signal_type == HiveSignalType.DEMAND_SURGE:
                    context["upstream_surge"] = True
                    context["surge_product"] = s.product_id
                elif s.signal_type == HiveSignalType.DEMAND_DROP:
                    context["upstream_drop"] = True
                elif s.signal_type == HiveSignalType.ALLOCATION_REFRESH:
                    context["network_change"] = True
            return context
        except Exception as e:
            logger.debug("Signal read failed: %s", e)
            return {}

    def _emit_signals_after_decision(
        self, state: ForecastBaselineState, rec: ForecastBaselineRecommendation
    ) -> None:
        """Emit demand signals after baseline forecast evaluation."""
        if self.signal_bus is None:
            return
        try:
            # Emit trend signals
            if rec.demand_trend_signal == "surge" and rec.demand_trend_magnitude > 0.05:
                self.signal_bus.emit(HiveSignal(
                    source_trm="forecast_baseline",
                    signal_type=HiveSignalType.DEMAND_SURGE,
                    urgency=min(1.0, rec.demand_trend_magnitude * 3),
                    direction="shortage",
                    magnitude=rec.demand_trend_magnitude,
                    product_id=state.product_id,
                    payload={
                        "trend_pct": rec.demand_trend_magnitude,
                        "model": rec.recommended_model,
                        "confidence": rec.confidence,
                    },
                ))
            elif rec.demand_trend_signal == "drop" and rec.demand_trend_magnitude > 0.05:
                self.signal_bus.emit(HiveSignal(
                    source_trm="forecast_baseline",
                    signal_type=HiveSignalType.DEMAND_DROP,
                    urgency=min(1.0, rec.demand_trend_magnitude * 2),
                    direction="surplus",
                    magnitude=rec.demand_trend_magnitude,
                    product_id=state.product_id,
                    payload={
                        "trend_pct": -rec.demand_trend_magnitude,
                        "model": rec.recommended_model,
                    },
                ))

            # Emit model change signal
            if rec.model_changed or rec.retrain_recommended:
                self.signal_bus.emit(HiveSignal(
                    source_trm="forecast_baseline",
                    signal_type=HiveSignalType.FORECAST_ADJUSTED,
                    urgency=0.5,
                    direction="neutral",
                    magnitude=0.1,
                    product_id=state.product_id,
                    payload={
                        "event": "model_change" if rec.model_changed else "retrain",
                        "new_model": rec.recommended_model,
                        "reason": rec.retrain_reason,
                    },
                ))

            # Update urgency vector
            urgency = min(1.0, rec.conformal_interval_width)  # Wide interval = uncertain = urgent
            self.signal_bus.urgency.update("forecast_baseline", urgency, "neutral")

        except Exception as e:
            logger.debug("Signal emit failed: %s", e)

    # ── Main Decision Method ──

    def evaluate(self, state: ForecastBaselineState) -> ForecastBaselineRecommendation:
        """Evaluate forecast baseline decisions for a product×site.

        Decides: model selection, retrain trigger, feature inclusion,
        censored demand correction, confidence assessment.
        """
        signal_context = self._read_signals_before_decision()

        # 1. Classify demand profile
        demand_profile = state.classify_demand()
        recommended_model = self.config.prefer_model or MODEL_BY_PROFILE.get(
            demand_profile, "lgbm"
        )
        model_changed = recommended_model != state.current_model

        # 2. Drift detection → retrain decision
        retrain_recommended, retrain_reason = self._check_drift(state)

        # 3. Feature decisions
        cross_product = self.config.enable_category_features
        external_signals = self._select_external_signals(state)
        censored = (
            self.config.enable_censored_correction
            and state.stockout_periods_pct > self.config.stockout_threshold
        )

        # 4. Demand trend detection
        trend_signal, trend_magnitude = self._detect_demand_trend(state, signal_context)

        # 5. Confidence from conformal interval width
        interval_width = 0.0
        if state.current_p50 > 0:
            interval_width = (state.current_p90 - state.current_p10) / state.current_p50
        confidence = max(0.1, min(0.99, 1.0 - interval_width))

        # 6. FVA vs naive
        fva_vs_naive = 0.0
        if state.baseline_mape > 0 and state.current_mape > 0:
            # Naive MAPE is typically ~20-30% for smooth demand
            naive_mape_estimate = max(state.baseline_mape * 1.5, 0.25)
            fva_vs_naive = naive_mape_estimate - state.current_mape

        rec = ForecastBaselineRecommendation(
            product_id=state.product_id,
            site_id=state.site_id,
            demand_profile=demand_profile,
            recommended_model=recommended_model,
            model_changed=model_changed,
            retrain_recommended=retrain_recommended,
            retrain_reason=retrain_reason,
            cross_product_features_enabled=cross_product,
            external_signals_enabled=external_signals,
            censored_demand_correction=censored,
            forecast_p50=state.current_p50,
            forecast_p10=state.current_p10,
            forecast_p90=state.current_p90,
            forecast_method_used=state.current_model,
            confidence=confidence,
            mape=state.current_mape,
            conformal_interval_width=interval_width,
            fva_vs_naive=fva_vs_naive,
            demand_trend_signal=trend_signal,
            demand_trend_magnitude=trend_magnitude,
        )

        # Context-aware reasoning
        rec.reason = self._build_reasoning(state, rec)

        if self.ctx_explainer is not None:
            try:
                summary = f"Baseline forecast: {demand_profile}, model={recommended_model}"
                ctx = self.ctx_explainer.generate_inline_explanation(
                    decision_summary=summary,
                    confidence=confidence,
                    trm_confidence=confidence if self.model else None,
                    decision_category='demand_forecast',
                    delta_percent=trend_magnitude * 100 if trend_signal else 0,
                )
                rec.context_explanation = ctx.to_dict()
            except Exception:
                pass

        # CDT risk bound
        if self._cdt_wrapper and self._cdt_wrapper.is_calibrated:
            try:
                risk = self._cdt_wrapper.compute_risk_bound(state.current_p50)
                rec.risk_bound = risk.risk_bound
                rec.risk_assessment = risk.to_dict()
            except Exception:
                pass

        self._emit_signals_after_decision(state, rec)
        self._persist_decision(state, rec)
        return rec

    # ── Decision Logic ──

    def _check_drift(self, state: ForecastBaselineState) -> Tuple[bool, Optional[str]]:
        """Check if the forecast model has drifted and needs retraining."""
        # Cooldown check
        if self._last_retrain:
            hours_since = (datetime.utcnow() - self._last_retrain).total_seconds() / 3600
            if hours_since < self.config.retrain_cooldown_hours:
                return False, None

        # CUSUM detector
        if state.cusum_statistic > self.config.cusum_threshold:
            return True, "drift_cusum"

        # MAPE degradation
        if state.baseline_mape > 0:
            degradation = (state.current_mape - state.baseline_mape) / state.baseline_mape
            if degradation > self.config.mape_degradation_threshold:
                return True, "mape_degradation"

        # Conformal coverage drift
        if state.conformal_coverage < self.config.conformal_target_coverage - 0.10:
            return True, "conformal_coverage_drift"

        return False, None

    def _select_external_signals(self, state: ForecastBaselineState) -> List[str]:
        """Select which external signals to include based on FVA."""
        if not self.config.enable_external_signals:
            return []

        selected = []
        for signal in state.external_signals_active:
            fva = state.signal_fva_scores.get(signal, 0.0)
            if fva >= self.config.signal_fva_threshold:
                selected.append(signal)

        return selected

    def _detect_demand_trend(
        self, state: ForecastBaselineState, signal_context: Dict
    ) -> Tuple[Optional[str], float]:
        """Detect significant demand trend for signal emission."""
        # Period-over-period change based on trend slope
        if state.trend_slope > 0.10:
            return "surge", state.trend_slope
        elif state.trend_slope < -0.10:
            return "drop", abs(state.trend_slope)

        # Category-level trend (assortment effect)
        if state.category_demand_trend > 0.15 and state.sibling_share_change < -0.05:
            # Category growing but this product losing share → demand migration
            return "drop", abs(state.sibling_share_change)

        # Upstream signals override
        if signal_context.get("upstream_surge"):
            return "surge", 0.15  # Default moderate surge from upstream signal

        return None, 0.0

    def _build_reasoning(
        self, state: ForecastBaselineState, rec: ForecastBaselineRecommendation
    ) -> str:
        """Build structured reasoning string for the decision."""
        parts = []

        # Profile
        parts.append(f"Demand profile: {rec.demand_profile}")
        parts.append(f"Observations: {state.observation_count}, CV: {state.demand_cv:.2f}")

        # Model
        if rec.model_changed:
            parts.append(
                f"Model switch: {state.current_model} → {rec.recommended_model} "
                f"(profile changed to {rec.demand_profile})"
            )
        else:
            parts.append(f"Model: {rec.recommended_model} (unchanged)")

        # Retrain
        if rec.retrain_recommended:
            parts.append(f"Retrain needed: {rec.retrain_reason}")

        # Accuracy
        parts.append(f"MAPE: {state.current_mape:.1%}, FVA vs naive: {rec.fva_vs_naive:+.1%}")

        # Confidence
        parts.append(
            f"Confidence: {rec.confidence:.2f} "
            f"(interval width: {rec.conformal_interval_width:.2f})"
        )

        # Cross-product
        if state.sibling_share_change != 0:
            direction = "gaining" if state.sibling_share_change > 0 else "losing"
            parts.append(
                f"Category share: {direction} ({state.sibling_share_change:+.1%})"
            )

        # Censored demand
        if rec.censored_demand_correction:
            parts.append(
                f"Censored demand correction applied "
                f"({state.stockout_periods_pct:.0%} stockout periods)"
            )

        # Trend
        if rec.demand_trend_signal:
            parts.append(
                f"Trend: {rec.demand_trend_signal} ({rec.demand_trend_magnitude:.1%})"
            )

        return ". ".join(parts)

    # ── Persistence ──

    def _persist_decision(
        self, state: ForecastBaselineState, rec: ForecastBaselineRecommendation
    ) -> None:
        """Write decision to powell_forecast_baseline_decisions."""
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellForecastBaselineDecision
            from app.services.powell.decision_reasoning import capture_hive_context

            hive_ctx = capture_hive_context(
                self.signal_bus, "forecast_baseline",
                cycle_id=getattr(self, "_cycle_id", None),
                cycle_phase=getattr(self, "_cycle_phase", None),
            )

            d = PowellForecastBaselineDecision(
                config_id=0,  # Set by SiteAgent
                product_id=state.product_id,
                site_id=state.site_id,
                demand_profile=rec.demand_profile,
                recommended_model=rec.recommended_model,
                model_changed=rec.model_changed,
                retrain_recommended=rec.retrain_recommended,
                retrain_reason=rec.retrain_reason,
                current_mape=state.current_mape,
                forecast_p50=rec.forecast_p50,
                forecast_p10=rec.forecast_p10,
                forecast_p90=rec.forecast_p90,
                conformal_interval_width=rec.conformal_interval_width,
                fva_vs_naive=rec.fva_vs_naive,
                cross_product_enabled=rec.cross_product_features_enabled,
                external_signals=rec.external_signals_enabled,
                censored_demand_corrected=rec.censored_demand_correction,
                demand_trend=rec.demand_trend_signal,
                demand_trend_magnitude=rec.demand_trend_magnitude,
                confidence=rec.confidence,
                decision_reasoning=rec.reason,
                **hive_ctx,
            )
            self.db.add(d)
            self.db.flush()
        except Exception as e:
            logger.warning("Failed to persist forecast baseline decision: %s", e)

    # ── Batch Evaluation ──

    def evaluate_batch(
        self, states: List[ForecastBaselineState]
    ) -> List[ForecastBaselineRecommendation]:
        """Evaluate baseline decisions for multiple product×site pairs."""
        return [self.evaluate(s) for s in states]
