"""
External Identifier Registry — Standardized external IDs for cross-system enrichment.

Product and TradingPartner entities carry an `external_identifiers` JSONB field
storing typed identifiers from external systems (SAP, GS1, D&B, etc.).

JSON structure: {"identifier_type": "value", ...}
Example: {"sap_material_number": "MAT-12345", "gtin": "00012345678905"}
"""

# ── Product identifier types ────────────────────────────────────────────────

PRODUCT_ID_TYPES = {
    "sap_material_number": "SAP Material Number (MATNR)",
    "gtin": "Global Trade Item Number (GTIN-14)",
    "upc": "Universal Product Code (UPC-A / UPC-E)",
    "ean": "European Article Number (EAN-13)",
    "isbn": "International Standard Book Number",
    "sku": "Internal Stock Keeping Unit",
    "customer_part_number": "Customer part number",
    "hs_code": "Harmonized System tariff code",
    "unspsc": "United Nations Standard Products and Services Code",
}

# ── Trading partner identifier types ────────────────────────────────────────

PARTNER_ID_TYPES = {
    "duns": "D-U-N-S Number (Dun & Bradstreet 9-digit)",
    "lei": "Legal Entity Identifier (ISO 17442)",
    "sap_vendor_number": "SAP Vendor Number (LIFNR)",
    "sap_customer_number": "SAP Customer Number (KUNNR)",
    "vat_id": "VAT Registration Number",
    "tax_id": "Tax Identification Number",
    "gln": "Global Location Number (GS1 GLN-13)",
    "open_supplier_hub_id": "Open Supplier Hub Organization ID",
}

ALL_ID_TYPES = {**PRODUCT_ID_TYPES, **PARTNER_ID_TYPES}


def upsert_external_id(entity, id_type: str, value: str) -> dict:
    """Merge an external identifier into an entity's external_identifiers JSON.

    Args:
        entity: SQLAlchemy model instance with ``external_identifiers`` column.
        id_type: Key from PRODUCT_ID_TYPES or PARTNER_ID_TYPES.
        value: The identifier value (e.g., "MAT-12345").

    Returns:
        The updated identifiers dict.
    """
    current = dict(entity.external_identifiers or {})
    current[id_type] = value
    entity.external_identifiers = current
    return current


def get_external_id(entity, id_type: str) -> str | None:
    """Read a single external identifier from an entity."""
    ids = entity.external_identifiers or {}
    return ids.get(id_type)
