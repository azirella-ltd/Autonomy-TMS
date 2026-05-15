"""TMS shim for the canonical hive_feedback module.

Canonical home: ``azirella_data_model.powell.hive_feedback``
(MIGRATION_REGISTER §1.13, lifted 2026-05-15). Byte-identical between
SCP and TMS pre-lift.
"""
from azirella_data_model.powell.hive_feedback import (  # noqa: F401
    HiveFeedbackFeatures,
    compute_feedback_features,
)


__all__ = ["HiveFeedbackFeatures", "compute_feedback_features"]
