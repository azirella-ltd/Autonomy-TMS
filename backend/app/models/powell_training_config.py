"""Powell training config models — re-exports from canonical azirella-data-model.

Stage 3 Phase 3d — TMS adopts azirella-data-model powell subpackage.
"""
from azirella_data_model.powell.powell_training_config import (  # noqa: F401
    TRMType,
    TrainingStatus,
    LearningPhase,
    PhaseStatus,
    PowellTrainingConfig,
    TRMTrainingConfig,
    TrainingRun,
    TRMSiteTrainingConfig,
    TRMBaseModel,
)


# ── TMS-local constants (not in canonical) ────────────────────────────────────

# Which TRM types are applicable per site master type.
TRM_APPLICABILITY = {
    "manufacturer": [
        TRMType.ATP_EXECUTOR, TRMType.ORDER_TRACKING, TRMType.INVENTORY_BUFFER,
        TRMType.FORECAST_ADJUSTMENT, TRMType.QUALITY_DISPOSITION, TRMType.PO_CREATION,
        TRMType.SUBCONTRACTING, TRMType.MAINTENANCE_SCHEDULING, TRMType.MO_EXECUTION,
        TRMType.TO_EXECUTION, TRMType.REBALANCING,
    ],
    "inventory": [
        TRMType.ATP_EXECUTOR, TRMType.ORDER_TRACKING, TRMType.INVENTORY_BUFFER,
        TRMType.FORECAST_ADJUSTMENT, TRMType.TO_EXECUTION, TRMType.REBALANCING,
        TRMType.PO_CREATION,
    ],
    "vendor": [],
    "customer": [],
}
# Default RL reward weights per TRM type. Used by the Powell training pipeline
# to configure the reward function for each TRM agent.

DEFAULT_TRM_REWARD_WEIGHTS = {
    TRMType.ATP_EXECUTOR: {
        "fill_rate": 0.4, "on_time_bonus": 0.2,
        "priority_weight": 0.2, "fairness_penalty": 0.2,
    },
    TRMType.REBALANCING: {
        "service_improvement": 0.5, "transfer_cost_penalty": 0.3,
        "balance_improvement": 0.2,
    },
    TRMType.PO_CREATION: {
        "stockout_penalty": 0.4, "dos_target_reward": 0.3,
        "cost_efficiency": 0.2, "timing_accuracy": 0.1,
    },
    TRMType.ORDER_TRACKING: {
        "correct_exception_detection": 0.4, "resolution_speed": 0.3,
        "escalation_appropriateness": 0.3,
    },
    TRMType.INVENTORY_BUFFER: {
        "stockout_penalty": 0.4, "dos_target_reward": 0.3,
        "excess_cost_penalty": 0.2, "stability_bonus": 0.1,
    },
    TRMType.MO_EXECUTION: {
        "on_time_completion": 0.3, "sequence_efficiency": 0.3,
        "utilization": 0.2, "changeover_penalty": 0.2,
    },
    TRMType.TO_EXECUTION: {
        "on_time_delivery": 0.4, "consolidation_bonus": 0.3,
        "cost_efficiency": 0.3,
    },
    TRMType.QUALITY_DISPOSITION: {
        "correct_disposition": 0.5, "cost_efficiency": 0.3,
        "throughput_impact": 0.2,
    },
    TRMType.MAINTENANCE_SCHEDULING: {
        "uptime_improvement": 0.4, "cost_efficiency": 0.3,
        "schedule_adherence": 0.3,
    },
    TRMType.SUBCONTRACTING: {
        "cost_efficiency": 0.4, "quality_score": 0.3,
        "lead_time_adherence": 0.3,
    },
    TRMType.FORECAST_ADJUSTMENT: {
        "forecast_accuracy": 0.5, "signal_relevance": 0.3,
        "adjustment_stability": 0.2,
    },
    TRMType.SAFETY_STOCK: {
        "stockout_penalty": 0.4, "dos_target_reward": 0.3,
        "excess_cost_penalty": 0.2, "stability_bonus": 0.1,
    },
}
