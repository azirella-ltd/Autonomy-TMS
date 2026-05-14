"""TMS purchase_order shim — re-exports canonical from Core.

The canonical `PurchaseOrder` + `PurchaseOrderLineItem` live in
`azirella_data_model.work_order.purchase_order` (promoted 2026-05-14).
Both SCP and TMS carried near-identical copies before promotion; the
Core version is the union of both (SCP's plan_version + ERP source
markers are substrate, not SCP-only).

Why Core: every plane that procures from vendors (SCP today, TMS for
inbound load planning, future procurement portal) needs the same
canonical record. Rule 1 + Rule 2.
"""
from azirella_data_model.work_order.purchase_order import (  # noqa: F401
    PurchaseOrder,
    PurchaseOrderLineItem,
)


__all__ = [
    "PurchaseOrder",
    "PurchaseOrderLineItem",
]
