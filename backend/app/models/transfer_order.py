"""TMS transfer_order shim — re-exports canonical from Core.

The canonical `TransferOrder` + `TransferOrderLineItem` live in
`azirella_data_model.work_order.transfer_order` (promoted 2026-05-14).
Both SCP and TMS carried near-identical copies before promotion; the
Core version is the union of both (SCP's conformal ETA band +
plan_version + ERP source markers are substrate).

Why Core: every plane that moves inventory between sites (SCP today,
TMS for carrier selection / load build, future logistics portal)
needs the same canonical record. Rule 1 + Rule 2.
"""
from azirella_data_model.work_order.transfer_order import (  # noqa: F401
    TransferOrder,
    TransferOrderLineItem,
)


__all__ = [
    "TransferOrder",
    "TransferOrderLineItem",
]
