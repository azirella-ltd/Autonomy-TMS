"""SCP shim — canonical B1 field mapping in Core.

``B1_FIELD_MAPPINGS`` + ``B1_FIELD_PATTERNS`` + ``B1_CARD_TYPE_MAP`` +
``map_card_type`` + ``get_field_mapping`` now live in
``azirella_integrations.erp.b1.field_mapping`` (lifted 2026-05-15 per
MIGRATION_REGISTER §1.1.5). SCP-superset canonical (~10% diff;
SCP has more pattern rules).
"""
from azirella_integrations.erp.b1.field_mapping import (  # noqa: F401
    B1_FIELD_MAPPINGS,
    B1_FIELD_PATTERNS,
    B1_CARD_TYPE_MAP,
    map_card_type,
    get_field_mapping,
)


__all__ = [
    "B1_FIELD_MAPPINGS",
    "B1_FIELD_PATTERNS",
    "B1_CARD_TYPE_MAP",
    "map_card_type",
    "get_field_mapping",
]
