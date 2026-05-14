"""TMS maintenance_order shim — re-exports canonical from Core.

The canonical `MaintenanceOrder` + `MaintenanceOrderSpare` live in
`azirella_data_model.work_order.maintenance_order` (promoted
2026-05-14). Both SCP and TMS carried near-identical copies before
promotion.

Why Core: any plane that schedules asset maintenance and consumes
spare parts (SCP today, TMS for equipment maintenance, future EAM
product) needs the same canonical record. Rule 1 + Rule 2.
"""
from azirella_data_model.work_order.maintenance_order import (  # noqa: F401
    MaintenanceOrder,
    MaintenanceOrderSpare,
)


__all__ = [
    "MaintenanceOrder",
    "MaintenanceOrderSpare",
]
