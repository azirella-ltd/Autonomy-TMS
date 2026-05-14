"""TMS metrics_hierarchy shim — re-exports canonical from Core.

The canonical Gartner SCOR metric catalog lives in
`azirella_data_model.metrics.hierarchy` (promoted 2026-05-13 per §1.1.1
of Core MIGRATION_REGISTER). Both SCP and TMS carried byte-identical
copies before promotion.

Why Core/metrics: every plane's metrics dashboard reads from the same
catalog; the catalog is plane-agnostic data, not TMS policy.
"""
from azirella_data_model.metrics.hierarchy import (  # noqa: F401
    DashboardMetricConfig,
    DEFAULT_DASHBOARD_METRICS,
    GARTNER_METRICS,
    GartnerLevel,
    MetricConfig,
    MetricDefinition,
    POWELL_LAYER_METRICS,
    TRM_METRIC_MAPPING,
    get_metric_config,
)


__all__ = [
    "DashboardMetricConfig",
    "DEFAULT_DASHBOARD_METRICS",
    "GARTNER_METRICS",
    "GartnerLevel",
    "MetricConfig",
    "MetricDefinition",
    "POWELL_LAYER_METRICS",
    "TRM_METRIC_MAPPING",
    "get_metric_config",
]
