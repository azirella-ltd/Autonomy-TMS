"""SCP shim — canonical Infor field mapping in Core.

``INFOR_FIELD_MAPPINGS`` + ``INFOR_FIELD_PATTERNS`` + status-map dicts
(PO/SO/MO) + ``map_po_status`` / ``map_so_status`` / ``map_mo_status`` /
``map_warehouse_type`` / ``get_field_mapping`` now live in
``azirella_integrations.erp.infor.field_mapping`` (lifted 2026-05-15
per MIGRATION_REGISTER §1.1.6). SCP canonical (~5% diff).
"""
from azirella_integrations.erp.infor.field_mapping import (  # noqa: F401
    INFOR_FIELD_MAPPINGS,
    INFOR_FIELD_PATTERNS,
    INFOR_PO_STATUS_MAP,
    INFOR_SO_STATUS_MAP,
    map_po_status,
    map_so_status,
    map_mo_status,
    map_warehouse_type,
    get_field_mapping,
)


__all__ = [
    "INFOR_FIELD_MAPPINGS",
    "INFOR_FIELD_PATTERNS",
    "INFOR_PO_STATUS_MAP",
    "INFOR_SO_STATUS_MAP",
    "map_po_status",
    "map_so_status",
    "map_mo_status",
    "map_warehouse_type",
    "get_field_mapping",
]
