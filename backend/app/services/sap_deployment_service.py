"""
SAP Deployment Configuration Service

Manages SAP system connections, table selections, field mappings,
and deployment configuration for initial and ongoing SAP integration.

Provides:
1. SAP connection configuration (S/4HANA, APO, CSV)
2. Table selection and prioritization
3. Field mapping configuration
4. Deployment validation and testing
5. Z-table/Z-field discovery and handling
"""

import logging
import base64
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

from app.models.sap_connection import SAPConnection

logger = logging.getLogger(__name__)


def _encrypt_password(plaintext: str) -> str:
    """Encode password for storage. Uses base64 as a placeholder;
    replace with Fernet encryption when cryptography key management is set up."""
    return base64.b64encode(plaintext.encode("utf-8")).decode("utf-8")


def _decrypt_password(encoded: str) -> str:
    """Decode stored password."""
    return base64.b64decode(encoded.encode("utf-8")).decode("utf-8")


class SAPSystemType(str, Enum):
    """Type of SAP system."""
    S4HANA = "s4hana"
    APO = "apo"
    ECC = "ecc"
    BW = "bw"


class ConnectionMethod(str, Enum):
    """Method for connecting to SAP."""
    RFC = "rfc"  # Direct RFC connection
    CSV = "csv"  # CSV file-based extraction
    ODATA = "odata"  # OData API
    IDOC = "idoc"  # IDoc interface
    HANA_DB = "hana_db"  # Direct SQL to HANA database


class DeploymentPhase(str, Enum):
    """Phase in the deployment process."""
    DISCOVERY = "discovery"
    CONFIGURATION = "configuration"
    VALIDATION = "validation"
    TESTING = "testing"
    PRODUCTION = "production"


class MappingStatus(str, Enum):
    """Status of a field mapping."""
    UNMAPPED = "unmapped"
    AUTO_MAPPED = "auto_mapped"
    MANUALLY_MAPPED = "manually_mapped"
    IGNORED = "ignored"
    REQUIRES_TRANSFORM = "requires_transform"


@dataclass
class SAPConnectionConfig:
    """Configuration for SAP system connection.

    Maps to/from the SAPConnection DB model. Used as a lightweight
    data-transfer object between service and API layers.
    """
    id: Optional[int] = None
    tenant_id: int = 0
    name: str = ""
    description: Optional[str] = None
    system_type: SAPSystemType = SAPSystemType.S4HANA
    connection_method: ConnectionMethod = ConnectionMethod.CSV

    # SAP System Identity
    sid: Optional[str] = None

    # Network / Host
    hostname: Optional[str] = None
    port: Optional[int] = None
    use_ssl: bool = True
    ssl_verify: bool = False

    # RFC connection settings
    ashost: Optional[str] = None
    sysnr: Optional[str] = None
    client: Optional[str] = None
    user: Optional[str] = None
    language: Optional[str] = "EN"

    # CSV settings
    csv_directory: Optional[str] = None
    csv_pattern: Optional[str] = None

    # OData settings
    odata_url: Optional[str] = None
    odata_base_path: Optional[str] = None

    # HANA DB direct settings
    hana_schema: Optional[str] = "SAPHANADB"
    hana_port: Optional[int] = None

    # SAP Router / Cloud Connector
    sap_router_string: Optional[str] = None
    cloud_connector_location_id: Optional[str] = None

    # Metadata
    is_active: bool = True
    is_validated: bool = False
    last_validated_at: Optional[datetime] = None
    validation_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "system_type": self.system_type.value,
            "connection_method": self.connection_method.value,
            "sid": self.sid,
            "hostname": self.hostname,
            "port": self.port,
            "use_ssl": self.use_ssl,
            "ssl_verify": self.ssl_verify,
            "ashost": self.ashost,
            "sysnr": self.sysnr,
            "client": self.client,
            "user": self.user,
            "language": self.language,
            "csv_directory": self.csv_directory,
            "csv_pattern": self.csv_pattern,
            "odata_url": self.odata_url,
            "odata_base_path": self.odata_base_path,
            "hana_schema": self.hana_schema,
            "hana_port": self.hana_port,
            "sap_router_string": self.sap_router_string,
            "cloud_connector_location_id": self.cloud_connector_location_id,
            "is_active": self.is_active,
            "is_validated": self.is_validated,
            "last_validated_at": self.last_validated_at.isoformat() if self.last_validated_at else None,
            "validation_message": self.validation_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_db(cls, row) -> "SAPConnectionConfig":
        """Create SAPConnectionConfig from a SAPConnection DB model instance."""
        return cls(
            id=row.id,
            tenant_id=row.tenant_id,
            name=row.name,
            description=row.description,
            system_type=SAPSystemType(row.system_type),
            connection_method=ConnectionMethod(row.connection_method),
            sid=row.sid,
            hostname=row.hostname,
            port=row.port,
            use_ssl=row.use_ssl,
            ssl_verify=row.ssl_verify,
            ashost=row.ashost,
            sysnr=row.sysnr,
            client=row.client,
            user=row.sap_user,
            language=row.language,
            csv_directory=row.csv_directory,
            csv_pattern=row.csv_pattern,
            odata_base_path=row.odata_base_path,
            hana_schema=getattr(row, "hana_schema", "SAPHANADB"),
            hana_port=getattr(row, "hana_port", None),
            sap_router_string=row.sap_router_string,
            cloud_connector_location_id=row.cloud_connector_location_id,
            is_active=row.is_active,
            is_validated=row.is_validated,
            last_validated_at=row.last_validated_at,
            validation_message=row.validation_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


@dataclass
class SAPTableConfig:
    """Configuration for a SAP table to extract."""
    id: Optional[int] = None
    connection_id: int = 0
    table_name: str = ""
    description: str = ""

    # Table type
    is_standard: bool = True  # Standard SAP table vs Z-table
    is_enabled: bool = True
    priority: int = 1  # 1=high, 2=medium, 3=low

    # Extraction settings
    extraction_mode: str = "full"  # full, delta, incremental
    key_fields: List[str] = field(default_factory=list)
    timestamp_field: Optional[str] = None

    # Mapping target
    aws_sc_entity: Optional[str] = None  # Target AWS SC entity

    # Metadata
    row_count: Optional[int] = None
    last_extracted_at: Optional[datetime] = None


@dataclass
class FieldMapping:
    """Mapping between SAP field and AWS SC field."""
    id: Optional[int] = None
    table_config_id: int = 0

    # Source (SAP)
    sap_field_name: str = ""
    sap_field_type: str = ""
    sap_field_length: Optional[int] = None
    sap_field_description: str = ""
    is_z_field: bool = False

    # Target (AWS SC)
    aws_sc_entity: str = ""
    aws_sc_field: str = ""
    aws_sc_field_type: str = ""

    # Mapping details
    status: MappingStatus = MappingStatus.UNMAPPED
    confidence: float = 0.0  # 0-1 confidence score for auto-mapping
    transform_rule: Optional[str] = None  # Transformation expression
    default_value: Optional[str] = None

    # AI assistance
    ai_suggestion: Optional[str] = None
    ai_rationale: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "table_config_id": self.table_config_id,
            "sap_field_name": self.sap_field_name,
            "sap_field_type": self.sap_field_type,
            "sap_field_length": self.sap_field_length,
            "sap_field_description": self.sap_field_description,
            "is_z_field": self.is_z_field,
            "aws_sc_entity": self.aws_sc_entity,
            "aws_sc_field": self.aws_sc_field,
            "aws_sc_field_type": self.aws_sc_field_type,
            "status": self.status.value,
            "confidence": self.confidence,
            "transform_rule": self.transform_rule,
            "default_value": self.default_value,
            "ai_suggestion": self.ai_suggestion,
            "ai_rationale": self.ai_rationale,
        }


@dataclass
class DeploymentStatus:
    """Overall deployment status for a customer."""
    tenant_id: int
    phase: DeploymentPhase

    # Connection status
    connection_configured: bool = False
    connection_tested: bool = False

    # Table status
    tables_discovered: int = 0
    tables_configured: int = 0
    tables_enabled: int = 0

    # Field mapping status
    total_fields: int = 0
    mapped_fields: int = 0
    unmapped_fields: int = 0
    z_fields_count: int = 0
    z_fields_mapped: int = 0

    # Validation status
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)

    # Testing status
    test_extraction_success: bool = False
    test_records_loaded: int = 0

    # Overall readiness
    ready_for_production: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "phase": self.phase.value,
            "connection_configured": self.connection_configured,
            "connection_tested": self.connection_tested,
            "tables_discovered": self.tables_discovered,
            "tables_configured": self.tables_configured,
            "tables_enabled": self.tables_enabled,
            "total_fields": self.total_fields,
            "mapped_fields": self.mapped_fields,
            "unmapped_fields": self.unmapped_fields,
            "z_fields_count": self.z_fields_count,
            "z_fields_mapped": self.z_fields_mapped,
            "validation_errors": self.validation_errors,
            "validation_warnings": self.validation_warnings,
            "test_extraction_success": self.test_extraction_success,
            "test_records_loaded": self.test_records_loaded,
            "ready_for_production": self.ready_for_production,
        }


# Standard SAP tables for supply chain
STANDARD_SAP_TABLES = {
    "s4hana": {
        "MARA": {
            "description": "Material Master - General Data",
            "priority": 1,
            "aws_sc_entity": "product",
            "key_fields": ["MATNR"],
        },
        "MARC": {
            "description": "Material Master - Plant Data",
            "priority": 1,
            "aws_sc_entity": "product",
            "key_fields": ["MATNR", "WERKS"],
        },
        "MARD": {
            "description": "Inventory by Storage Location",
            "priority": 1,
            "aws_sc_entity": "inv_level",
            "key_fields": ["MATNR", "WERKS", "LGORT"],
        },
        "T001W": {
            "description": "Plants/Branches",
            "priority": 1,
            "aws_sc_entity": "site",
            "key_fields": ["WERKS"],
        },
        "LFA1": {
            "description": "Vendor Master",
            "priority": 2,
            "aws_sc_entity": "trading_partner",
            "key_fields": ["LIFNR"],
        },
        "KNA1": {
            "description": "Customer Master",
            "priority": 2,
            "aws_sc_entity": "trading_partner",
            "key_fields": ["KUNNR"],
        },
        "EKKO": {
            "description": "Purchase Order Header",
            "priority": 2,
            "aws_sc_entity": "inbound_order",
            "key_fields": ["EBELN"],
        },
        "EKPO": {
            "description": "Purchase Order Item",
            "priority": 2,
            "aws_sc_entity": "inbound_order_line",
            "key_fields": ["EBELN", "EBELP"],
        },
        "VBAK": {
            "description": "Sales Order Header",
            "priority": 2,
            "aws_sc_entity": "outbound_order",
            "key_fields": ["VBELN"],
        },
        "VBAP": {
            "description": "Sales Order Item",
            "priority": 2,
            "aws_sc_entity": "outbound_order_line",
            "key_fields": ["VBELN", "POSNR"],
        },
        "LIKP": {
            "description": "Delivery Header",
            "priority": 2,
            "aws_sc_entity": "shipment",
            "key_fields": ["VBELN"],
        },
        "LIPS": {
            "description": "Delivery Item",
            "priority": 2,
            "aws_sc_entity": "shipment_line",
            "key_fields": ["VBELN", "POSNR"],
        },
        "AFKO": {
            "description": "Production Order Header",
            "priority": 2,
            "aws_sc_entity": "production_order",
            "key_fields": ["AUFNR"],
        },
        "AFPO": {
            "description": "Production Order Item",
            "priority": 2,
            "aws_sc_entity": "production_order_line",
            "key_fields": ["AUFNR", "POSNR"],
        },
        "STPO": {
            "description": "Bill of Materials Item",
            "priority": 1,
            "aws_sc_entity": "product_bom",
            "key_fields": ["STLNR", "STLKN"],
        },
        "EKET": {
            "description": "PO Schedule Lines (ATP)",
            "priority": 2,
            "aws_sc_entity": "supply_plan",
            "key_fields": ["EBELN", "EBELP", "ETENR"],
        },
        "RESB": {
            "description": "Reservations",
            "priority": 3,
            "aws_sc_entity": "allocation",
            "key_fields": ["RSNUM", "RSPOS"],
        },
        # Transfer Orders
        "LTAK": {
            "description": "Transfer Order Header",
            "priority": 2,
            "aws_sc_entity": "transfer_order",
            "key_fields": ["LGNUM", "TESSION"],
        },
        "LTAP": {
            "description": "Transfer Order Item",
            "priority": 2,
            "aws_sc_entity": "transfer_order_line",
            "key_fields": ["LGNUM", "TESSION", "TAESSION"],
        },
        # Quality Orders
        "QMEL": {
            "description": "Quality Notification Header",
            "priority": 2,
            "aws_sc_entity": "quality_order",
            "key_fields": ["QMNUM"],
        },
        "QMIH": {
            "description": "Quality Notification Items",
            "priority": 2,
            "aws_sc_entity": "quality_order_line",
            "key_fields": ["QMNUM", "FEESSION"],
        },
        # Maintenance Orders (PM module uses AUFK with order type PM)
        "AUFK_PM": {
            "description": "Maintenance Order Header (PM Orders from AUFK)",
            "priority": 2,
            "aws_sc_entity": "maintenance_order",
            "key_fields": ["AUFNR"],
        },
        "IHPA": {
            "description": "Plant Maintenance Object Partners",
            "priority": 3,
            "aws_sc_entity": "maintenance_order",
            "key_fields": ["OBJNR", "PESSION"],
        },
        "MHIS": {
            "description": "Maintenance History",
            "priority": 3,
            "aws_sc_entity": "maintenance_order",
            "key_fields": ["OBJNR", "POINT"],
        },
        # Subcontracting (EKKO/EKPO with doc type L + MKAL for subcontracting cockpit)
        "MKAL": {
            "description": "Subcontracting Cockpit - Production Versions",
            "priority": 2,
            "aws_sc_entity": "subcontracting_order",
            "key_fields": ["MATNR", "WERKS", "VEESSION"],
        },
        # --- Config-Critical Tables (for building SupplyChainConfig from SAP) ---
        "EINA": {
            "description": "Purchasing Info Record Header",
            "priority": 1,
            "aws_sc_entity": "vendor_product",
            "key_fields": ["INFNR", "MATNR", "LIFNR"],
        },
        "EINE": {
            "description": "Purchasing Info Record Item",
            "priority": 1,
            "aws_sc_entity": "vendor_lead_time",
            "key_fields": ["INFNR", "EKORG"],
        },
        "EORD": {
            "description": "Source List",
            "priority": 1,
            "aws_sc_entity": "sourcing_rules",
            "key_fields": ["MATNR", "WERKS", "LIFNR"],
        },
        "T001": {
            "description": "Company Codes",
            "priority": 1,
            "aws_sc_entity": "company",
            "key_fields": ["BUKRS"],
        },
        "ADRC": {
            "description": "Addresses (Central Address Management)",
            "priority": 2,
            "aws_sc_entity": "geography",
            "key_fields": ["ADDRNUMBER"],
        },
        "KNVV": {
            "description": "Customer Sales Data",
            "priority": 2,
            "aws_sc_entity": "market",
            "key_fields": ["KUNNR", "VKORG", "VTWEG", "SPART"],
        },
        "MVKE": {
            "description": "Sales Data for Material",
            "priority": 2,
            "aws_sc_entity": "product",
            "key_fields": ["MATNR", "VKORG", "VTWEG"],
        },
        "PLKO": {
            "description": "Routing Header",
            "priority": 2,
            "aws_sc_entity": "production_process",
            "key_fields": ["PLNTY", "PLNNR", "PLNAL"],
        },
        "PLPO": {
            "description": "Routing Operation",
            "priority": 2,
            "aws_sc_entity": "production_process",
            "key_fields": ["PLNTY", "PLNNR", "PLNKN"],
        },
        "STKO": {
            "description": "BOM Header",
            "priority": 1,
            "aws_sc_entity": "product_bom",
            "key_fields": ["STLNR", "STLAL"],
        },
        # --- Enrichment Tables ---
        "CRHD": {
            "description": "Work Center Header",
            "priority": 3,
            "aws_sc_entity": "resource_capacity",
            "key_fields": ["OBJID", "ARBPL", "WERKS"],
        },
        "KAKO": {
            "description": "Capacity Header",
            "priority": 3,
            "aws_sc_entity": "resource_capacity",
            "key_fields": ["OBJID"],
        },
        "MARM": {
            "description": "Material Unit of Measure Conversions",
            "priority": 2,
            "aws_sc_entity": "product",
            "key_fields": ["MATNR", "MEINH"],
        },
        # --- MRP Planning Tables ---
        "MDKP": {
            "description": "MRP Document Header",
            "priority": 1,
            "aws_sc_entity": "supply_plan",
            "key_fields": ["MATNR", "WERKS", "DTART"],
        },
        "MDTB": {
            "description": "MRP Table Lines (MRP Elements)",
            "priority": 1,
            "aws_sc_entity": "supply_plan",
            "key_fields": ["MATNR", "WERKS", "DELKZ"],
        },
        "PLAF": {
            "description": "Planned Orders",
            "priority": 1,
            "aws_sc_entity": "supply_plan",
            "key_fields": ["PLNUM"],
        },
        "EBAN": {
            "description": "Purchase Requisitions",
            "priority": 1,
            "aws_sc_entity": "purchase_requisition",
            "key_fields": ["BANFN", "BNFPO"],
        },
        # --- Forecast Tables ---
        "PBIM": {
            "description": "Independent Requirements Header (Planned Independent Requirements)",
            "priority": 1,
            "aws_sc_entity": "forecast",
            "key_fields": ["MATNR", "WERKS", "BEDAE"],
        },
        "MPOP": {
            "description": "Forecast Parameters/Profiles",
            "priority": 1,
            "aws_sc_entity": "forecast",
            "key_fields": ["MATNR", "WERKS", "PESSION"],
        },
        # --- Supporting Tables ---
        "T001L": {
            "description": "Storage Locations",
            "priority": 2,
            "aws_sc_entity": "site",
            "key_fields": ["WERKS", "LGORT"],
        },
        "MAKT": {
            "description": "Material Descriptions (Multi-Language)",
            "priority": 2,
            "aws_sc_entity": "product",
            "key_fields": ["MATNR", "SPRAS"],
        },
        "T024E": {
            "description": "Purchasing Organizations",
            "priority": 2,
            "aws_sc_entity": "company",
            "key_fields": ["EKORG"],
        },
        # --- User / Authorization Tables (SC-filtered user import) ---
        "USR02": {
            "description": "User Logon Data (username, type, validity dates)",
            "priority": 2,
            "aws_sc_entity": "sap_user",
            "key_fields": ["MANDT", "BNAME"],
        },
        "USR21": {
            "description": "User Name / Address Assignment",
            "priority": 2,
            "aws_sc_entity": "sap_user",
            "key_fields": ["MANDT", "BNAME"],
        },
        "ADRP": {
            "description": "Person Address Data (email, first/last name)",
            "priority": 2,
            "aws_sc_entity": "sap_user",
            "key_fields": ["PERSNUMBER"],
        },
        "AGR_USERS": {
            "description": "Role-to-User Assignments",
            "priority": 2,
            "aws_sc_entity": "sap_role",
            "key_fields": ["MANDT", "UNAME", "AGR_NAME"],
        },
        "AGR_DEFINE": {
            "description": "Role Definitions (name, description)",
            "priority": 2,
            "aws_sc_entity": "sap_role",
            "key_fields": ["MANDT", "AGR_NAME"],
        },
        "AGR_1251": {
            "description": "Authorization Values in Roles (objects, field values)",
            "priority": 2,
            "aws_sc_entity": "sap_authorization",
            "key_fields": ["MANDT", "AGR_NAME", "OBJECT", "FIELD"],
        },
        "AGR_TCODES": {
            "description": "Transaction Codes Assigned to Roles",
            "priority": 2,
            "aws_sc_entity": "sap_authorization",
            "key_fields": ["MANDT", "AGR_NAME", "TCODE"],
        },
    },
    "apo": {
        "/SAPAPO/LOC": {
            "description": "APO Locations",
            "priority": 1,
            "aws_sc_entity": "site",
            "key_fields": ["LOCNO"],
        },
        "/SAPAPO/MAT": {
            "description": "APO Materials",
            "priority": 1,
            "aws_sc_entity": "product",
            "key_fields": ["MATNR", "LOCNO"],
        },
        "/SAPAPO/STOCK": {
            "description": "APO Stock",
            "priority": 1,
            "aws_sc_entity": "inv_level",
            "key_fields": ["MATNR", "LOCNO"],
        },
        "/SAPAPO/ATPREL": {
            "description": "APO ATP Relevant Data",
            "priority": 2,
            "aws_sc_entity": "atp_check",
            "key_fields": ["MATNR", "LOCNO"],
        },
        "/SAPAPO/SNPFC": {
            "description": "APO SNP Forecast",
            "priority": 2,
            "aws_sc_entity": "forecast",
            "key_fields": ["MATNR", "LOCNO", "PERIODID"],
        },
        # --- Config-Critical APO Tables (network topology) ---
        "/SAPAPO/MATLOC": {
            "description": "APO Material-Location Assignments",
            "priority": 1,
            "aws_sc_entity": "product",
            "key_fields": ["MATNR", "LOCNO"],
        },
        "/SAPAPO/TRLANE": {
            "description": "APO Transportation Lanes",
            "priority": 1,
            "aws_sc_entity": "transportation_lane",
            "key_fields": ["LOCFR", "LOCTO", "MATID"],
        },
        "/SAPAPO/PDS": {
            "description": "APO Product Data Structure (BOM/Routing)",
            "priority": 2,
            "aws_sc_entity": "product_bom",
            "key_fields": ["PDSID", "MATNR", "LOCNO"],
        },
        "/SAPAPO/SNPBV": {
            "description": "APO SNP Basic Values (Historical Demand/Supply)",
            "priority": 2,
            "aws_sc_entity": "forecast",
            "key_fields": ["MATNR", "LOCNO", "PERIODID"],
        },
    },
}

# AWS SC entity field definitions for mapping targets
AWS_SC_ENTITY_FIELDS = {
    "product": [
        {"name": "product_id", "type": "string", "required": True},
        {"name": "company_id", "type": "string", "required": True},
        {"name": "product_name", "type": "string", "required": False},
        {"name": "description", "type": "string", "required": False},
        {"name": "product_group", "type": "string", "required": False},
        {"name": "base_uom", "type": "string", "required": False},
        {"name": "status", "type": "string", "required": False},
    ],
    "site": [
        {"name": "site_id", "type": "string", "required": True},
        {"name": "company_id", "type": "string", "required": True},
        {"name": "site_name", "type": "string", "required": False},
        {"name": "site_type", "type": "string", "required": False},
        {"name": "address", "type": "string", "required": False},
        {"name": "country", "type": "string", "required": False},
    ],
    "inv_level": [
        {"name": "site_id", "type": "string", "required": True},
        {"name": "product_id", "type": "string", "required": True},
        {"name": "quantity", "type": "decimal", "required": True},
        {"name": "uom", "type": "string", "required": False},
        {"name": "snapshot_date", "type": "date", "required": True},
    ],
    "trading_partner": [
        {"name": "partner_id", "type": "string", "required": True},
        {"name": "company_id", "type": "string", "required": True},
        {"name": "partner_type", "type": "string", "required": True},
        {"name": "partner_name", "type": "string", "required": False},
    ],
    "inbound_order": [
        {"name": "order_id", "type": "string", "required": True},
        {"name": "company_id", "type": "string", "required": True},
        {"name": "order_type", "type": "string", "required": True},
        {"name": "supplier_id", "type": "string", "required": True},
        {"name": "site_id", "type": "string", "required": True},
        {"name": "order_date", "type": "date", "required": True},
    ],
    "outbound_order": [
        {"name": "order_id", "type": "string", "required": True},
        {"name": "company_id", "type": "string", "required": True},
        {"name": "customer_id", "type": "string", "required": True},
        {"name": "ship_from_site_id", "type": "string", "required": True},
        {"name": "order_date", "type": "date", "required": True},
    ],
    "forecast": [
        {"name": "site_id", "type": "string", "required": True},
        {"name": "product_id", "type": "string", "required": True},
        {"name": "forecast_date", "type": "date", "required": True},
        {"name": "forecast_quantity", "type": "decimal", "required": True},
        {"name": "forecast_p10", "type": "decimal", "required": False},
        {"name": "forecast_p50", "type": "decimal", "required": False},
        {"name": "forecast_p90", "type": "decimal", "required": False},
    ],
    "transfer_order": [
        {"name": "order_id", "type": "string", "required": True},
        {"name": "company_id", "type": "string", "required": True},
        {"name": "source_site_id", "type": "string", "required": True},
        {"name": "destination_site_id", "type": "string", "required": True},
        {"name": "product_id", "type": "string", "required": True},
        {"name": "quantity", "type": "decimal", "required": True},
        {"name": "status", "type": "string", "required": False},
        {"name": "ship_date", "type": "date", "required": False},
        {"name": "arrival_date", "type": "date", "required": False},
        {"name": "transportation_mode", "type": "string", "required": False},
    ],
    "quality_order": [
        {"name": "order_id", "type": "string", "required": True},
        {"name": "company_id", "type": "string", "required": True},
        {"name": "site_id", "type": "string", "required": True},
        {"name": "product_id", "type": "string", "required": True},
        {"name": "inspection_type", "type": "string", "required": True},
        {"name": "lot_number", "type": "string", "required": False},
        {"name": "lot_size", "type": "decimal", "required": False},
        {"name": "sample_size", "type": "decimal", "required": False},
        {"name": "defect_count", "type": "integer", "required": False},
        {"name": "disposition", "type": "string", "required": False},
        {"name": "status", "type": "string", "required": False},
        {"name": "inspection_date", "type": "date", "required": False},
    ],
    "maintenance_order": [
        {"name": "order_id", "type": "string", "required": True},
        {"name": "company_id", "type": "string", "required": True},
        {"name": "site_id", "type": "string", "required": True},
        {"name": "asset_id", "type": "string", "required": True},
        {"name": "maintenance_type", "type": "string", "required": True},
        {"name": "priority", "type": "string", "required": False},
        {"name": "status", "type": "string", "required": False},
        {"name": "planned_start", "type": "date", "required": False},
        {"name": "planned_end", "type": "date", "required": False},
        {"name": "actual_start", "type": "date", "required": False},
        {"name": "actual_end", "type": "date", "required": False},
        {"name": "estimated_duration_hours", "type": "decimal", "required": False},
        {"name": "cost", "type": "decimal", "required": False},
    ],
    "subcontracting_order": [
        {"name": "order_id", "type": "string", "required": True},
        {"name": "company_id", "type": "string", "required": True},
        {"name": "site_id", "type": "string", "required": True},
        {"name": "subcontractor_id", "type": "string", "required": True},
        {"name": "product_id", "type": "string", "required": True},
        {"name": "quantity", "type": "decimal", "required": True},
        {"name": "status", "type": "string", "required": False},
        {"name": "order_date", "type": "date", "required": False},
        {"name": "due_date", "type": "date", "required": False},
        {"name": "material_sent_date", "type": "date", "required": False},
        {"name": "goods_received_date", "type": "date", "required": False},
        {"name": "unit_cost", "type": "decimal", "required": False},
    ],
    # --- Config Builder entity types ---
    "vendor_product": [
        {"name": "vendor_id", "type": "string", "required": True},
        {"name": "product_id", "type": "string", "required": True},
        {"name": "company_id", "type": "string", "required": True},
        {"name": "info_record", "type": "string", "required": False},
        {"name": "net_price", "type": "decimal", "required": False},
        {"name": "currency", "type": "string", "required": False},
        {"name": "min_order_qty", "type": "decimal", "required": False},
        {"name": "standard_order_qty", "type": "decimal", "required": False},
        {"name": "price_unit", "type": "decimal", "required": False},
    ],
    "vendor_lead_time": [
        {"name": "vendor_id", "type": "string", "required": True},
        {"name": "product_id", "type": "string", "required": True},
        {"name": "site_id", "type": "string", "required": True},
        {"name": "lead_time_days", "type": "integer", "required": True},
        {"name": "purchasing_org", "type": "string", "required": False},
        {"name": "planned_delivery_time", "type": "integer", "required": False},
    ],
    "sourcing_rules": [
        {"name": "product_id", "type": "string", "required": True},
        {"name": "site_id", "type": "string", "required": True},
        {"name": "source_type", "type": "string", "required": True},
        {"name": "source_id", "type": "string", "required": True},
        {"name": "priority", "type": "integer", "required": False},
        {"name": "allocation_pct", "type": "decimal", "required": False},
        {"name": "valid_from", "type": "date", "required": False},
        {"name": "valid_to", "type": "date", "required": False},
        {"name": "fixed_vendor", "type": "boolean", "required": False},
    ],
    "production_process": [
        {"name": "process_id", "type": "string", "required": True},
        {"name": "site_id", "type": "string", "required": True},
        {"name": "product_id", "type": "string", "required": True},
        {"name": "operation_number", "type": "string", "required": False},
        {"name": "work_center_id", "type": "string", "required": False},
        {"name": "setup_time", "type": "decimal", "required": False},
        {"name": "machine_time", "type": "decimal", "required": False},
        {"name": "labor_time", "type": "decimal", "required": False},
        {"name": "time_unit", "type": "string", "required": False},
    ],
    "company": [
        {"name": "company_id", "type": "string", "required": True},
        {"name": "company_name", "type": "string", "required": True},
        {"name": "country", "type": "string", "required": False},
        {"name": "currency", "type": "string", "required": False},
    ],
    "geography": [
        {"name": "address_id", "type": "string", "required": True},
        {"name": "country", "type": "string", "required": False},
        {"name": "region", "type": "string", "required": False},
        {"name": "city", "type": "string", "required": False},
        {"name": "postal_code", "type": "string", "required": False},
        {"name": "latitude", "type": "decimal", "required": False},
        {"name": "longitude", "type": "decimal", "required": False},
    ],
    "transportation_lane": [
        {"name": "source_site_id", "type": "string", "required": True},
        {"name": "destination_site_id", "type": "string", "required": True},
        {"name": "product_id", "type": "string", "required": False},
        {"name": "lead_time_days", "type": "integer", "required": False},
        {"name": "capacity", "type": "decimal", "required": False},
        {"name": "transport_mode", "type": "string", "required": False},
        {"name": "cost_per_unit", "type": "decimal", "required": False},
    ],
    "resource_capacity": [
        {"name": "resource_id", "type": "string", "required": True},
        {"name": "site_id", "type": "string", "required": True},
        {"name": "resource_name", "type": "string", "required": False},
        {"name": "capacity_hours", "type": "decimal", "required": False},
        {"name": "capacity_unit", "type": "string", "required": False},
    ],
    # --- Planning Entity Types ---
    "supply_plan": [
        {"name": "plan_id", "type": "string", "required": True},
        {"name": "company_id", "type": "string", "required": True},
        {"name": "product_id", "type": "string", "required": True},
        {"name": "site_id", "type": "string", "required": True},
        {"name": "plan_date", "type": "date", "required": True},
        {"name": "plan_type", "type": "string", "required": True},
        {"name": "planned_order_quantity", "type": "decimal", "required": False},
        {"name": "planned_order_date", "type": "date", "required": False},
        {"name": "planned_receipt_date", "type": "date", "required": False},
        {"name": "demand_quantity", "type": "decimal", "required": False},
        {"name": "supply_quantity", "type": "decimal", "required": False},
        {"name": "opening_inventory", "type": "decimal", "required": False},
        {"name": "closing_inventory", "type": "decimal", "required": False},
        {"name": "safety_stock", "type": "decimal", "required": False},
        {"name": "supplier_id", "type": "string", "required": False},
        {"name": "from_site_id", "type": "string", "required": False},
        {"name": "mrp_type", "type": "string", "required": False},
        {"name": "mrp_controller", "type": "string", "required": False},
        {"name": "lot_size_procedure", "type": "string", "required": False},
        {"name": "order_status", "type": "string", "required": False},
        {"name": "plan_version", "type": "string", "required": False},
    ],
    "inv_policy": [
        {"name": "product_id", "type": "string", "required": True},
        {"name": "site_id", "type": "string", "required": True},
        {"name": "company_id", "type": "string", "required": True},
        {"name": "ss_policy", "type": "string", "required": True},
        {"name": "ss_quantity", "type": "decimal", "required": False},
        {"name": "ss_days", "type": "integer", "required": False},
        {"name": "service_level", "type": "decimal", "required": False},
        {"name": "reorder_point", "type": "decimal", "required": False},
        {"name": "min_order_quantity", "type": "decimal", "required": False},
        {"name": "max_order_quantity", "type": "decimal", "required": False},
        {"name": "fixed_order_quantity", "type": "decimal", "required": False},
        {"name": "order_up_to_level", "type": "decimal", "required": False},
        {"name": "review_period", "type": "integer", "required": False},
        {"name": "mrp_type", "type": "string", "required": False},
        {"name": "mrp_controller", "type": "string", "required": False},
        {"name": "lot_size_procedure", "type": "string", "required": False},
        {"name": "planned_delivery_time", "type": "integer", "required": False},
        {"name": "gr_processing_time", "type": "integer", "required": False},
        {"name": "scheduling_margin_key", "type": "string", "required": False},
    ],
    "purchase_requisition": [
        {"name": "requisition_id", "type": "string", "required": True},
        {"name": "line_number", "type": "string", "required": True},
        {"name": "company_id", "type": "string", "required": True},
        {"name": "product_id", "type": "string", "required": True},
        {"name": "site_id", "type": "string", "required": True},
        {"name": "quantity", "type": "decimal", "required": True},
        {"name": "delivery_date", "type": "date", "required": False},
        {"name": "release_date", "type": "date", "required": False},
        {"name": "requisition_type", "type": "string", "required": False},
        {"name": "purchasing_group", "type": "string", "required": False},
        {"name": "purchasing_org", "type": "string", "required": False},
        {"name": "supplier_id", "type": "string", "required": False},
        {"name": "price", "type": "decimal", "required": False},
        {"name": "status", "type": "string", "required": False},
        {"name": "source_plan_id", "type": "string", "required": False},
    ],
    # --- SAP User / Role / Authorization entities (SC-filtered import) ---
    "sap_user": [
        {"name": "sap_username", "type": "string", "required": True},
        {"name": "email", "type": "string", "required": False},
        {"name": "first_name", "type": "string", "required": False},
        {"name": "last_name", "type": "string", "required": False},
        {"name": "user_type", "type": "string", "required": False},
        {"name": "valid_from", "type": "date", "required": False},
        {"name": "valid_to", "type": "date", "required": False},
        {"name": "account_class", "type": "string", "required": False},
    ],
    "sap_role": [
        {"name": "role_name", "type": "string", "required": True},
        {"name": "role_description", "type": "string", "required": False},
        {"name": "assigned_user", "type": "string", "required": False},
        {"name": "valid_from", "type": "date", "required": False},
        {"name": "valid_to", "type": "date", "required": False},
    ],
    "sap_authorization": [
        {"name": "role_name", "type": "string", "required": True},
        {"name": "auth_object", "type": "string", "required": False},
        {"name": "field_name", "type": "string", "required": False},
        {"name": "value_low", "type": "string", "required": False},
        {"name": "value_high", "type": "string", "required": False},
        {"name": "tcode", "type": "string", "required": False},
    ],
}


class SAPDeploymentService:
    """
    Service for managing SAP deployment configuration.

    Provides a guided workflow for:
    1. Configuring SAP system connections
    2. Discovering and selecting tables
    3. Mapping fields to AWS SC entities
    4. Validating and testing the configuration
    5. Deploying to production
    """

    def __init__(self, db: AsyncSession, tenant_id: int):
        self.db = db
        self.tenant_id = tenant_id
        # Legacy in-memory caches for table configs / field mappings (not yet persisted)
        self._table_configs: Dict[int, SAPTableConfig] = {}
        self._field_mappings: Dict[int, List[FieldMapping]] = {}

    # -------------------------------------------------------------------------
    # Connection Management (persisted to sap_connections table)
    # -------------------------------------------------------------------------

    async def create_connection(
        self,
        name: str,
        system_type: SAPSystemType,
        connection_method: ConnectionMethod,
        password: Optional[str] = None,
        **kwargs
    ) -> SAPConnectionConfig:
        """Create a new SAP connection configuration and persist to DB."""
        # Map dataclass field names to DB column names
        row = SAPConnection(
            tenant_id=self.tenant_id,
            name=name,
            system_type=system_type.value,
            connection_method=connection_method.value,
            description=kwargs.get("description"),
            sid=kwargs.get("sid"),
            hostname=kwargs.get("hostname"),
            port=kwargs.get("port"),
            use_ssl=kwargs.get("use_ssl", True),
            ssl_verify=kwargs.get("ssl_verify", False),
            ashost=kwargs.get("ashost"),
            sysnr=kwargs.get("sysnr"),
            client=kwargs.get("client"),
            sap_user=kwargs.get("user"),
            language=kwargs.get("language", "EN"),
            odata_base_path=kwargs.get("odata_base_path"),
            csv_directory=kwargs.get("csv_directory"),
            csv_pattern=kwargs.get("csv_pattern"),
            hana_schema=kwargs.get("hana_schema", "SAPHANADB"),
            hana_port=kwargs.get("hana_port"),
            sap_router_string=kwargs.get("sap_router_string"),
            cloud_connector_location_id=kwargs.get("cloud_connector_location_id"),
        )

        if password:
            row.sap_password_encrypted = _encrypt_password(password)

        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)

        logger.info(f"Created SAP connection: {name} ({system_type.value}) [id={row.id}]")
        return SAPConnectionConfig.from_db(row)

    async def test_connection(self, connection_id: int) -> Tuple[bool, str]:
        """Test an SAP connection."""
        result = await self.db.execute(
            select(SAPConnection).where(
                SAPConnection.id == connection_id,
                SAPConnection.tenant_id == self.tenant_id,
            )
        )
        row = result.scalar_one_or_none()
        if not row:
            return False, "Connection not found"

        try:
            method = ConnectionMethod(row.connection_method)

            if method == ConnectionMethod.CSV:
                import os
                if row.csv_directory and os.path.isdir(row.csv_directory):
                    row.is_validated = True
                    row.last_validated_at = datetime.utcnow()
                    row.validation_message = "CSV directory accessible"
                    await self.db.commit()
                    return True, "CSV directory accessible"
                else:
                    row.is_validated = False
                    row.validation_message = f"CSV directory not found: {row.csv_directory}"
                    await self.db.commit()
                    return False, row.validation_message

            elif method in (ConnectionMethod.RFC, ConnectionMethod.ODATA, ConnectionMethod.HANA_DB):
                # Use unified extractors for real connection testing
                from app.integrations.sap.extractors import create_extractor
                password = _decrypt_password(row.sap_password_encrypted) if row.sap_password_encrypted else ""
                connection = SAPConnectionConfig.from_db(row)

                try:
                    extractor = create_extractor(connection, password)
                    success, msg = await extractor.test_connection()
                    row.is_validated = success
                    row.last_validated_at = datetime.utcnow()
                    row.validation_message = msg
                    await self.db.commit()
                    return success, msg
                except ImportError as e:
                    row.is_validated = False
                    row.validation_message = str(e)
                    await self.db.commit()
                    return False, str(e)

            else:
                return False, f"Connection method not yet supported: {method.value}"

        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            row.is_validated = False
            row.validation_message = str(e)
            await self.db.commit()
            return False, str(e)

    async def get_connections(self) -> List[SAPConnectionConfig]:
        """Get all connections for this tenant."""
        result = await self.db.execute(
            select(SAPConnection)
            .where(SAPConnection.tenant_id == self.tenant_id)
            .order_by(SAPConnection.id)
        )
        rows = result.scalars().all()
        return [SAPConnectionConfig.from_db(r) for r in rows]

    async def _get_connection_row(self, connection_id: int) -> Optional[SAPConnection]:
        """Internal helper to fetch a connection row by id within the tenant."""
        result = await self.db.execute(
            select(SAPConnection).where(
                SAPConnection.id == connection_id,
                SAPConnection.tenant_id == self.tenant_id,
            )
        )
        return result.scalar_one_or_none()

    # -------------------------------------------------------------------------
    # Table Discovery and Configuration
    # -------------------------------------------------------------------------

    async def discover_tables(self, connection_id: int) -> List[SAPTableConfig]:
        """Discover available tables from an SAP connection."""
        config_row = await self._get_connection_row(connection_id)
        if not config_row:
            raise ValueError("Connection not found")
        config = SAPConnectionConfig.from_db(config_row)

        tables = []

        # Get standard tables for this system type
        standard_tables = STANDARD_SAP_TABLES.get(config.system_type.value, {})

        for table_name, table_info in standard_tables.items():
            table_config = SAPTableConfig(
                connection_id=connection_id,
                table_name=table_name,
                description=table_info["description"],
                is_standard=True,
                priority=table_info["priority"],
                key_fields=table_info["key_fields"],
                aws_sc_entity=table_info.get("aws_sc_entity"),
            )
            tables.append(table_config)

        # TODO: For RFC connections, discover Z-tables dynamically
        # Would use DD02L, DD02T to find custom tables starting with Z

        logger.info(f"Discovered {len(tables)} tables for connection {connection_id}")
        return tables

    async def configure_table(
        self,
        connection_id: int,
        table_name: str,
        **kwargs
    ) -> SAPTableConfig:
        """Configure a table for extraction."""
        table_id = len(self._table_configs) + 1

        table_config = SAPTableConfig(
            id=table_id,
            connection_id=connection_id,
            table_name=table_name,
            **kwargs
        )

        self._table_configs[table_id] = table_config
        return table_config

    async def discover_z_tables(self, connection_id: int) -> List[Dict[str, Any]]:
        """Discover Z-tables (custom SAP tables) from connection."""
        # In a real implementation, this would query DD02L for tables starting with Z
        # For now, return a template structure
        return [
            {
                "table_name": "ZSCM_CUSTOM",
                "description": "Custom SCM Extension Table",
                "field_count": 0,
                "is_z_table": True,
                "suggested_mapping": None,
            }
        ]

    # -------------------------------------------------------------------------
    # Field Mapping
    # -------------------------------------------------------------------------

    async def discover_fields(self, table_config_id: int) -> List[FieldMapping]:
        """Discover fields from a configured table."""
        table_config = self._table_configs.get(table_config_id)
        if not table_config:
            raise ValueError("Table config not found")

        # Get connection to determine system type
        connection_row = await self._get_connection_row(table_config.connection_id)
        if not connection_row:
            raise ValueError("Connection not found")
        connection = SAPConnectionConfig.from_db(connection_row)

        # TODO: For RFC, query DD03L for actual field definitions
        # For now, return sample fields based on known table structures

        fields = []

        # Add auto-mapped fields based on known patterns
        if table_config.aws_sc_entity:
            target_fields = AWS_SC_ENTITY_FIELDS.get(table_config.aws_sc_entity, [])

            for target in target_fields:
                field_mapping = FieldMapping(
                    table_config_id=table_config_id,
                    sap_field_name=self._guess_sap_field_name(target["name"]),
                    sap_field_type=self._map_type_to_sap(target["type"]),
                    aws_sc_entity=table_config.aws_sc_entity,
                    aws_sc_field=target["name"],
                    aws_sc_field_type=target["type"],
                    status=MappingStatus.AUTO_MAPPED,
                    confidence=0.8,
                )
                fields.append(field_mapping)

        self._field_mappings[table_config_id] = fields
        return fields

    def _guess_sap_field_name(self, aws_field: str) -> str:
        """Guess SAP field name from AWS SC field name."""
        mapping = {
            "product_id": "MATNR",
            "site_id": "WERKS",
            "company_id": "BUKRS",
            "quantity": "LABST",
            "partner_id": "LIFNR",
            "order_id": "EBELN",
            "customer_id": "KUNNR",
        }
        return mapping.get(aws_field, aws_field.upper())

    def _map_type_to_sap(self, aws_type: str) -> str:
        """Map AWS SC type to SAP type."""
        mapping = {
            "string": "CHAR",
            "decimal": "DEC",
            "integer": "INT4",
            "date": "DATS",
            "datetime": "TIMS",
        }
        return mapping.get(aws_type, "CHAR")

    async def update_field_mapping(
        self,
        mapping_id: int,
        table_config_id: int,
        **updates
    ) -> FieldMapping:
        """Update a field mapping."""
        mappings = self._field_mappings.get(table_config_id, [])

        for mapping in mappings:
            if mapping.id == mapping_id:
                for key, value in updates.items():
                    if hasattr(mapping, key):
                        setattr(mapping, key, value)

                # Update status
                if updates.get("aws_sc_field"):
                    mapping.status = MappingStatus.MANUALLY_MAPPED

                return mapping

        raise ValueError("Mapping not found")

    async def get_unmapped_z_fields(self, connection_id: int) -> List[FieldMapping]:
        """Get all unmapped Z-fields for a connection."""
        unmapped = []

        for table_id, mappings in self._field_mappings.items():
            table_config = self._table_configs.get(table_id)
            if table_config and table_config.connection_id == connection_id:
                for mapping in mappings:
                    if mapping.is_z_field and mapping.status == MappingStatus.UNMAPPED:
                        unmapped.append(mapping)

        return unmapped

    # -------------------------------------------------------------------------
    # Deployment Status
    # -------------------------------------------------------------------------

    async def get_deployment_status(self) -> DeploymentStatus:
        """Get overall deployment status for this customer."""
        status = DeploymentStatus(
            tenant_id=self.tenant_id,
            phase=DeploymentPhase.DISCOVERY,
        )

        # Check connection status
        connections = await self.get_connections()
        if connections:
            status.connection_configured = True
            status.connection_tested = any(c.is_validated for c in connections)

        # Check table status
        for table_config in self._table_configs.values():
            status.tables_configured += 1
            if table_config.is_enabled:
                status.tables_enabled += 1

        # Check field mapping status
        for table_id, mappings in self._field_mappings.items():
            for mapping in mappings:
                status.total_fields += 1

                if mapping.is_z_field:
                    status.z_fields_count += 1

                if mapping.status in (MappingStatus.AUTO_MAPPED, MappingStatus.MANUALLY_MAPPED):
                    status.mapped_fields += 1
                    if mapping.is_z_field:
                        status.z_fields_mapped += 1
                elif mapping.status == MappingStatus.UNMAPPED:
                    status.unmapped_fields += 1

        # Determine current phase
        if not status.connection_configured:
            status.phase = DeploymentPhase.DISCOVERY
        elif not status.connection_tested:
            status.phase = DeploymentPhase.CONFIGURATION
        elif status.unmapped_fields > 0:
            status.phase = DeploymentPhase.CONFIGURATION
        elif not status.test_extraction_success:
            status.phase = DeploymentPhase.VALIDATION
        else:
            status.phase = DeploymentPhase.TESTING

        # Check readiness
        status.ready_for_production = (
            status.connection_tested and
            status.unmapped_fields == 0 and
            len(status.validation_errors) == 0 and
            status.test_extraction_success
        )

        return status

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    async def validate_configuration(self, connection_id: int) -> Tuple[bool, List[str], List[str]]:
        """Validate the entire configuration."""
        errors = []
        warnings = []

        # Validate connection
        config_row = await self._get_connection_row(connection_id)
        if not config_row:
            errors.append("Connection not configured")
            return False, errors, warnings
        config = SAPConnectionConfig.from_db(config_row)

        if not config.is_validated:
            errors.append("Connection not tested")

        # Validate tables
        connection_tables = [t for t in self._table_configs.values() if t.connection_id == connection_id]
        if not connection_tables:
            errors.append("No tables configured for extraction")

        enabled_tables = [t for t in connection_tables if t.is_enabled]
        if not enabled_tables:
            warnings.append("No tables enabled for extraction")

        # Validate required entities
        required_entities = {"product", "site", "inv_level"}
        configured_entities = {t.aws_sc_entity for t in enabled_tables if t.aws_sc_entity}
        missing_entities = required_entities - configured_entities

        if missing_entities:
            errors.append(f"Missing required entities: {', '.join(missing_entities)}")

        # Validate field mappings
        for table in enabled_tables:
            mappings = self._field_mappings.get(table.id, [])
            unmapped = [m for m in mappings if m.status == MappingStatus.UNMAPPED and not m.is_z_field]

            if unmapped:
                warnings.append(f"Table {table.table_name} has {len(unmapped)} unmapped required fields")

        is_valid = len(errors) == 0
        return is_valid, errors, warnings


# Convenience function
def create_deployment_service(db: AsyncSession, tenant_id: int) -> SAPDeploymentService:
    """Create a deployment service for a customer."""
    return SAPDeploymentService(db, tenant_id)
