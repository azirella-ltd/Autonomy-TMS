"""TMS shim for the canonical hive_health module.

Canonical home: ``azirella_data_model.powell.hive_health``
(MIGRATION_REGISTER §1.13, lifted 2026-05-15). Byte-identical between
SCP and TMS pre-lift.
"""
from azirella_data_model.powell.hive_health import HiveHealthMetrics  # noqa: F401


__all__ = ["HiveHealthMetrics"]
