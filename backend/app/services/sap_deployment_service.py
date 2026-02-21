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
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)


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
    """Configuration for SAP system connection."""
    id: Optional[int] = None
    group_id: int = 0
    name: str = ""
    system_type: SAPSystemType = SAPSystemType.S4HANA
    connection_method: ConnectionMethod = ConnectionMethod.CSV

    # RFC connection settings
    ashost: Optional[str] = None
    sysnr: Optional[str] = None
    client: Optional[str] = None
    user: Optional[str] = None
    # Password stored separately in secrets

    # CSV settings
    csv_directory: Optional[str] = None
    csv_pattern: Optional[str] = None

    # OData settings
    odata_url: Optional[str] = None

    # Metadata
    is_active: bool = True
    is_validated: bool = False
    last_validated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "group_id": self.group_id,
            "name": self.name,
            "system_type": self.system_type.value,
            "connection_method": self.connection_method.value,
            "ashost": self.ashost,
            "sysnr": self.sysnr,
            "client": self.client,
            "user": self.user,
            "csv_directory": self.csv_directory,
            "csv_pattern": self.csv_pattern,
            "odata_url": self.odata_url,
            "is_active": self.is_active,
            "is_validated": self.is_validated,
            "last_validated_at": self.last_validated_at.isoformat() if self.last_validated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


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
    """Overall deployment status for a group."""
    group_id: int
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
            "group_id": self.group_id,
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

    def __init__(self, db: AsyncSession, group_id: int):
        self.db = db
        self.group_id = group_id
        self._connections: Dict[int, SAPConnectionConfig] = {}
        self._table_configs: Dict[int, SAPTableConfig] = {}
        self._field_mappings: Dict[int, List[FieldMapping]] = {}

    # -------------------------------------------------------------------------
    # Connection Management
    # -------------------------------------------------------------------------

    async def create_connection(
        self,
        name: str,
        system_type: SAPSystemType,
        connection_method: ConnectionMethod,
        **kwargs
    ) -> SAPConnectionConfig:
        """Create a new SAP connection configuration."""
        config = SAPConnectionConfig(
            group_id=self.group_id,
            name=name,
            system_type=system_type,
            connection_method=connection_method,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            **kwargs
        )

        # TODO: Persist to database
        # For now, store in memory
        config.id = len(self._connections) + 1
        self._connections[config.id] = config

        logger.info(f"Created SAP connection: {name} ({system_type.value})")
        return config

    async def test_connection(self, connection_id: int) -> Tuple[bool, str]:
        """Test an SAP connection."""
        config = self._connections.get(connection_id)
        if not config:
            return False, "Connection not found"

        try:
            if config.connection_method == ConnectionMethod.CSV:
                # For CSV, just verify the directory exists
                import os
                if config.csv_directory and os.path.isdir(config.csv_directory):
                    config.is_validated = True
                    config.last_validated_at = datetime.utcnow()
                    return True, "CSV directory accessible"
                else:
                    return False, f"CSV directory not found: {config.csv_directory}"

            elif config.connection_method == ConnectionMethod.RFC:
                # TODO: Use S4HANAConnector to test RFC connection
                # For now, simulate
                config.is_validated = True
                config.last_validated_at = datetime.utcnow()
                return True, "RFC connection successful"

            else:
                return False, f"Connection method not yet supported: {config.connection_method}"

        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False, str(e)

    async def get_connections(self) -> List[SAPConnectionConfig]:
        """Get all connections for this group."""
        return [c for c in self._connections.values() if c.group_id == self.group_id]

    # -------------------------------------------------------------------------
    # Table Discovery and Configuration
    # -------------------------------------------------------------------------

    async def discover_tables(self, connection_id: int) -> List[SAPTableConfig]:
        """Discover available tables from an SAP connection."""
        config = self._connections.get(connection_id)
        if not config:
            raise ValueError("Connection not found")

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
        connection = self._connections.get(table_config.connection_id)
        if not connection:
            raise ValueError("Connection not found")

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
        """Get overall deployment status for this group."""
        status = DeploymentStatus(
            group_id=self.group_id,
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
        config = self._connections.get(connection_id)
        if not config:
            errors.append("Connection not configured")
            return False, errors, warnings

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
def create_deployment_service(db: AsyncSession, group_id: int) -> SAPDeploymentService:
    """Create a deployment service for a group."""
    return SAPDeploymentService(db, group_id)
