"""TMS quality_order shim — re-exports canonical from Core.

The canonical `QualityOrder` + `QualityOrderLineItem` live in
`azirella_data_model.work_order.quality_order` (promoted 2026-05-14
per §3.X of MIGRATION_REGISTER). Both SCP and TMS carried
near-identical copies before promotion.

Why Core: any plane that inspects product and decides a disposition
(SCP today, TMS for inbound/returns, future WMS / returns portal)
needs the same canonical record. Rule 1 + Rule 2.
"""
from azirella_data_model.work_order.quality_order import (  # noqa: F401
    QualityOrder,
    QualityOrderLineItem,
)


__all__ = [
    "QualityOrder",
    "QualityOrderLineItem",
]
