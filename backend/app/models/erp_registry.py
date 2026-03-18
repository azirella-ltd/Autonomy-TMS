"""
ERP Vendor & Variant Registry — Supported ERP systems and their data extraction profiles.

Two-level hierarchy:
  ERP Vendor (e.g., SAP, Oracle, Microsoft)
    └── ERP Variant (e.g., S/4HANA, ECC, APO, Cloud SCM, D365)

Each variant defines:
  - Which SAP/ERP tables are available
  - Default extraction method (RFC, CSV, OData, API)
  - Data category mappings
  - Version compatibility notes

Set at tenant creation time as a systemadmin configuration.
"""

from enum import Enum as PyEnum
from typing import Any, Dict, List


class ERPVendor(str, PyEnum):
    """Supported ERP vendors."""
    SAP = "SAP"
    ORACLE = "Oracle"
    MICROSOFT = "Microsoft"
    INFOR = "Infor"
    EPICOR = "Epicor"
    IFS = "IFS"
    OTHER = "Other"


class ERPVariant(str, PyEnum):
    """Supported ERP system variants."""
    # SAP
    SAP_S4HANA = "S4HANA"
    SAP_S4HANA_CLOUD = "S4HANA_Cloud"
    SAP_ECC = "ECC"
    SAP_APO = "APO"
    SAP_IBP = "IBP"
    SAP_BW = "BW"
    SAP_ARIBA = "Ariba"

    # Oracle
    ORACLE_CLOUD_SCM = "Oracle_Cloud_SCM"
    ORACLE_EBS = "Oracle_EBS"
    ORACLE_JDE = "Oracle_JDE"
    ORACLE_DEMANTRA = "Oracle_Demantra"

    # Microsoft
    MS_D365_SCM = "D365_SCM"
    MS_D365_FO = "D365_FO"
    MS_NAV = "NAV"

    # Infor
    INFOR_LN = "Infor_LN"
    INFOR_M3 = "Infor_M3"
    INFOR_CLOUDSUITE = "Infor_CloudSuite"

    # Generic
    CSV_GENERIC = "CSV_Generic"


# ---------------------------------------------------------------------------
# ERP Vendor → Variant mapping
# ---------------------------------------------------------------------------

ERP_VENDOR_VARIANTS: Dict[str, List[str]] = {
    ERPVendor.SAP: [
        ERPVariant.SAP_S4HANA,
        ERPVariant.SAP_S4HANA_CLOUD,
        ERPVariant.SAP_ECC,
        ERPVariant.SAP_APO,
        ERPVariant.SAP_IBP,
        ERPVariant.SAP_BW,
        ERPVariant.SAP_ARIBA,
    ],
    ERPVendor.ORACLE: [
        ERPVariant.ORACLE_CLOUD_SCM,
        ERPVariant.ORACLE_EBS,
        ERPVariant.ORACLE_JDE,
        ERPVariant.ORACLE_DEMANTRA,
    ],
    ERPVendor.MICROSOFT: [
        ERPVariant.MS_D365_SCM,
        ERPVariant.MS_D365_FO,
        ERPVariant.MS_NAV,
    ],
    ERPVendor.INFOR: [
        ERPVariant.INFOR_LN,
        ERPVariant.INFOR_M3,
        ERPVariant.INFOR_CLOUDSUITE,
    ],
    ERPVendor.OTHER: [
        ERPVariant.CSV_GENERIC,
    ],
}


# ---------------------------------------------------------------------------
# ERP Variant profiles — extraction capabilities and defaults
# ---------------------------------------------------------------------------

ERP_VARIANT_PROFILES: Dict[str, Dict[str, Any]] = {
    ERPVariant.SAP_S4HANA: {
        "vendor": ERPVendor.SAP,
        "label": "SAP S/4HANA (On-Premise)",
        "extraction_methods": ["rfc", "odata", "hana_db", "csv"],
        "default_method": "rfc",
        "supports_cdc": True,
        "supports_rfc": True,
        "table_prefix": "",  # Standard SAP tables
        "notes": "Full table access via RFC or HANA SQL. IDES/FAA demo data available.",
        "version_range": "1709–2025",
    },
    ERPVariant.SAP_S4HANA_CLOUD: {
        "vendor": ERPVendor.SAP,
        "label": "SAP S/4HANA Cloud (Public Edition)",
        "extraction_methods": ["odata", "csv"],
        "default_method": "odata",
        "supports_cdc": True,
        "supports_rfc": False,  # No RFC in public cloud
        "table_prefix": "",
        "notes": "OData APIs only. No direct table access. Custom CDS views for extraction.",
        "version_range": "2208+",
    },
    ERPVariant.SAP_ECC: {
        "vendor": ERPVendor.SAP,
        "label": "SAP ECC (ERP Central Component)",
        "extraction_methods": ["rfc", "csv"],
        "default_method": "rfc",
        "supports_cdc": True,
        "supports_rfc": True,
        "table_prefix": "",
        "notes": "Same tables as S/4HANA but older field naming. BSEG instead of ACDOCA.",
        "version_range": "EHP5–EHP8",
    },
    ERPVariant.SAP_APO: {
        "vendor": ERPVendor.SAP,
        "label": "SAP APO (Advanced Planning & Optimization)",
        "extraction_methods": ["rfc", "csv"],
        "default_method": "rfc",
        "supports_cdc": False,
        "supports_rfc": True,
        "table_prefix": "/SAPAPO/",
        "notes": "APO-specific tables (/SAPAPO/SNPFC, /SAPAPO/MATLOC). Being replaced by IBP.",
        "version_range": "7.0–7.2",
    },
    ERPVariant.SAP_IBP: {
        "vendor": ERPVendor.SAP,
        "label": "SAP IBP (Integrated Business Planning)",
        "extraction_methods": ["odata", "csv"],
        "default_method": "odata",
        "supports_cdc": False,
        "supports_rfc": False,
        "table_prefix": "",
        "notes": "Cloud-native. Key planning data via OData/CSV export.",
        "version_range": "2205+",
    },
    ERPVariant.SAP_BW: {
        "vendor": ERPVendor.SAP,
        "label": "SAP BW/4HANA",
        "extraction_methods": ["odata", "csv"],
        "default_method": "csv",
        "supports_cdc": False,
        "supports_rfc": True,
        "table_prefix": "",
        "notes": "Data warehouse. Historical aggregates, not transactional.",
    },
    ERPVariant.SAP_ARIBA: {
        "vendor": ERPVendor.SAP,
        "label": "SAP Ariba",
        "extraction_methods": ["csv"],
        "default_method": "csv",
        "supports_cdc": False,
        "supports_rfc": False,
        "table_prefix": "",
        "notes": "Procurement network. Supplier data and sourcing events.",
    },
    ERPVariant.ORACLE_CLOUD_SCM: {
        "vendor": ERPVendor.ORACLE,
        "label": "Oracle Cloud SCM",
        "extraction_methods": ["csv", "odata"],
        "default_method": "csv",
        "supports_cdc": False,
        "supports_rfc": False,
        "table_prefix": "",
        "notes": "REST APIs and BI Publisher reports for extraction.",
    },
    ERPVariant.ORACLE_EBS: {
        "vendor": ERPVendor.ORACLE,
        "label": "Oracle E-Business Suite",
        "extraction_methods": ["csv"],
        "default_method": "csv",
        "supports_cdc": False,
        "supports_rfc": False,
        "table_prefix": "",
        "notes": "Direct SQL access or concurrent program output.",
    },
    ERPVariant.ORACLE_JDE: {
        "vendor": ERPVendor.ORACLE,
        "label": "Oracle JD Edwards",
        "extraction_methods": ["csv"],
        "default_method": "csv",
        "supports_cdc": False,
        "supports_rfc": False,
        "table_prefix": "F",  # JDE table prefix
        "notes": "F-prefixed tables (F4101, F4102, F4311, etc.).",
    },
    ERPVariant.MS_D365_SCM: {
        "vendor": ERPVendor.MICROSOFT,
        "label": "Microsoft Dynamics 365 Supply Chain Management",
        "extraction_methods": ["odata", "csv"],
        "default_method": "odata",
        "supports_cdc": True,
        "supports_rfc": False,
        "table_prefix": "",
        "notes": "OData APIs. Data entities for extraction.",
    },
    ERPVariant.MS_D365_FO: {
        "vendor": ERPVendor.MICROSOFT,
        "label": "Microsoft Dynamics 365 Finance & Operations",
        "extraction_methods": ["odata", "csv"],
        "default_method": "odata",
        "supports_cdc": True,
        "supports_rfc": False,
        "table_prefix": "",
        "notes": "Shared data model with D365 SCM.",
    },
    ERPVariant.INFOR_LN: {
        "vendor": ERPVendor.INFOR,
        "label": "Infor LN (Baan)",
        "extraction_methods": ["csv"],
        "default_method": "csv",
        "supports_cdc": False,
        "supports_rfc": False,
        "table_prefix": "",
        "notes": "Manufacturing-focused ERP. CSV/BOD extraction.",
    },
    ERPVariant.INFOR_M3: {
        "vendor": ERPVendor.INFOR,
        "label": "Infor M3",
        "extraction_methods": ["csv"],
        "default_method": "csv",
        "supports_cdc": False,
        "supports_rfc": False,
        "table_prefix": "",
        "notes": "Distribution and manufacturing. API or CSV.",
    },
    ERPVariant.CSV_GENERIC: {
        "vendor": ERPVendor.OTHER,
        "label": "Generic CSV Import",
        "extraction_methods": ["csv"],
        "default_method": "csv",
        "supports_cdc": False,
        "supports_rfc": False,
        "table_prefix": "",
        "notes": "Manual CSV upload. Field mapping required.",
    },
}


def get_variants_for_vendor(vendor: str) -> List[str]:
    """Return available ERP variants for a vendor."""
    return ERP_VENDOR_VARIANTS.get(vendor, [])


def get_variant_profile(variant: str) -> Dict[str, Any]:
    """Return the full profile for an ERP variant."""
    return ERP_VARIANT_PROFILES.get(variant, ERP_VARIANT_PROFILES[ERPVariant.CSV_GENERIC])


def get_default_import_path(tenant_name: str, erp_variant: str) -> str:
    """Generate the default import path for a tenant+ERP combination."""
    return f"imports/{_safe(tenant_name)}/{_safe(erp_variant)}"


def get_default_export_path(tenant_name: str, erp_variant: str) -> str:
    """Generate the default export path for a tenant+ERP combination."""
    return f"exports/{_safe(tenant_name)}/{_safe(erp_variant)}"


def _safe(name: str) -> str:
    """Filesystem-safe name."""
    import re
    return re.sub(r'[^\w\-.]', '_', name).strip('_')
