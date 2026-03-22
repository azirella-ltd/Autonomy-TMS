"""
SAP S/4HANA Connector for Supply Chain Data Extraction.

Supports:
- Direct RFC connection via pyrfc
- Standard S/4HANA tables (MARA, MARC, MARD, EKKO, EKPO, etc.)
- Supply Chain Data Model mapping
- Batch extraction with pagination
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, date
import pandas as pd

try:
    from pyrfc import Connection, ABAPApplicationError, ABAPRuntimeError
    PYRFC_AVAILABLE = True
except ImportError:
    PYRFC_AVAILABLE = False
    logging.warning("pyrfc not available. SAP RFC connections will fail.")

logger = logging.getLogger(__name__)


@dataclass
class S4HANAConnectionConfig:
    """S/4HANA connection configuration."""
    ashost: str  # Application server host
    sysnr: str  # System number (e.g., '00')
    client: str  # Client (e.g., '100')
    user: str  # SAP username
    passwd: str  # SAP password
    lang: str = "EN"  # Language
    trace: str = "0"  # RFC trace level


class S4HANAConnector:
    """
    Connector for SAP S/4HANA supply chain data extraction.

    Standard Tables:
    - MARA: Material Master (General)
    - MARC: Material Master (Plant)
    - MARD: Material Master (Storage Location)
    - EKKO: Purchasing Document Header
    - EKPO: Purchasing Document Item
    - EKET: Scheduling Agreement Schedule Lines
    - LIKP: Delivery Header
    - LIPS: Delivery Item
    - VBAK: Sales Document Header
    - VBAP: Sales Document Item
    - T001W: Plants/Branches
    - T001L: Storage Locations
    """

    # Standard S/4HANA table configurations
    MATERIAL_MASTER_FIELDS = [
        "MATNR",  # Material Number
        "MAKTX",  # Material Description
        "MTART",  # Material Type
        "MEINS",  # Base Unit of Measure
        "MATKL",  # Material Group
        "BISMT",  # Old Material Number
        "BRGEW",  # Gross Weight
        "NTGEW",  # Net Weight
        "GEWEI",  # Weight Unit
        "VOLUM",  # Volume
        "VOLEH",  # Volume Unit
        "LVORM",  # Deletion Flag
    ]

    PLANT_MATERIAL_FIELDS = [
        "MATNR",  # Material Number
        "WERKS",  # Plant
        "DISPO",  # MRP Controller
        "DISGR",  # MRP Group
        "DISMM",  # MRP Type
        "DISLS",  # Lot Sizing Procedure (EX/FX/HB/WB/TB/GR/SP/SM/OP)
        "BSTMI",  # Minimum Lot Size
        "BSTMA",  # Maximum Lot Size
        "BSTFE",  # Fixed Lot Size
        "BSTRF",  # Rounding Value
        "RDPRF",  # Rounding Profile
        "BESKZ",  # Procurement Type (E=in-house, F=external)
        "SOBSL",  # Special Procurement Type
        "LGPRO",  # Production Scheduler
        "EISBE",  # Safety Stock
        "MINBE",  # Reorder Point
        "MABST",  # Maximum Stock Level (order-up-to)
        "LOSGR",  # Fixed Lot Size (from MRP1 view)
        "PLIFZ",  # Planned Delivery Time
        "WEBAZ",  # Goods Receipt Processing Time
        "DZEIT",  # In-House Production Time
        "SHZET",  # Safety Time (safety lead time in days)
        "AUSSS",  # Assembly Scrap %
        "VRMOD",  # Consumption Mode (1=backward, 2=bwd+fwd, 3=fwd, 4=fwd+bwd, 5=period)
        "VINT1",  # Backward Consumption Period (work days)
        "VINT2",  # Forward Consumption Period (work days)
        "FXHOR",  # Planning Time Fence (work days)
        "STRGR",  # Planning Strategy Group (10/11/30/40)
        "FHORI",  # Scheduling Margin Key / Forecast Horizon
        "MTVFP",  # Availability Check Group
    ]

    PURCHASE_ORDER_HEADER_FIELDS = [
        "EBELN",  # Purchasing Document Number
        "BUKRS",  # Company Code
        "BSTYP",  # Purchasing Document Category
        "BSART",  # Purchasing Document Type
        "LIFNR",  # Vendor
        "EKORG",  # Purchasing Organization
        "EKGRP",  # Purchasing Group
        "BEDAT",  # Document Date
        "AEDAT",  # Changed On
    ]

    PURCHASE_ORDER_ITEM_FIELDS = [
        "EBELN",  # Purchasing Document Number
        "EBELP",  # Item Number
        "MATNR",  # Material Number
        "WERKS",  # Plant
        "LGORT",  # Storage Location
        "MENGE",  # Quantity
        "MEINS",  # Unit of Measure
        "NETPR",  # Net Price
        "PEINH",  # Price Unit
        "MWSKZ",  # Tax Code
        "ELIKZ",  # Delivery Completed
        "AEDAT",  # Changed On
    ]

    DELIVERY_HEADER_FIELDS = [
        "VBELN",  # Delivery Number
        "VSTEL",  # Shipping Point
        "VKORG",  # Sales Organization
        "LFART",  # Delivery Type
        "KUNNR",  # Ship-to Party
        "WADAT_IST",  # Actual GI Date
        "LFDAT",  # Delivery Date
    ]

    DELIVERY_ITEM_FIELDS = [
        "VBELN",  # Delivery Number
        "POSNR",  # Item Number
        "MATNR",  # Material Number
        "WERKS",  # Plant
        "LGORT",  # Storage Location
        "LFIMG",  # Actual Quantity Delivered
        "VRKME",  # Sales Unit
        "PSTYV",  # Item Category
    ]

    SALES_ORDER_HEADER_FIELDS = [
        "VBELN",  # Sales Document Number
        "VKORG",  # Sales Organization
        "VTWEG",  # Distribution Channel
        "SPART",  # Division
        "AUART",  # Sales Document Type
        "KUNNR",  # Sold-to Party
        "BSTNK",  # Customer Purchase Order Number
        "ERDAT",  # Created On
        "ERZET",  # Created At
    ]

    SALES_ORDER_ITEM_FIELDS = [
        "VBELN",  # Sales Document Number
        "POSNR",  # Item Number
        "MATNR",  # Material Number
        "WERKS",  # Plant
        "KWMENG",  # Order Quantity
        "VRKME",  # Sales Unit
        "NETPR",  # Net Price
        "WAERK",  # Currency
        "PSTYV",  # Item Category
    ]

    # ==========================================================================
    # ATP/CTP Integration Fields (Phase 1 - SAP ATP Integration)
    # ==========================================================================

    # Production Order Header (AFKO) - for CTP capacity and WIP
    PRODUCTION_ORDER_HEADER_FIELDS = [
        "AUFNR",  # Production Order Number
        "AUART",  # Order Type
        "MATNR",  # Material Number
        "WERKS",  # Plant
        "PSMNG",  # Order Quantity (Planned)
        "GAMNG",  # Total Order Quantity (incl. scrap)
        "WEMNG",  # Delivered Quantity (Goods Receipt)
        "GSTRP",  # Basic Start Date
        "GLTRP",  # Basic Finish Date
        "FTRMI",  # Scheduled Start Date
        "FTRMS",  # Scheduled Finish Date
        "STAT",   # System Status (REL=Released, CNF=Confirmed, TECO=Completed)
        "AUFPL",  # Routing Number
    ]

    # Production Order Item (AFPO) - for CTP component requirements
    PRODUCTION_ORDER_ITEM_FIELDS = [
        "AUFNR",  # Production Order Number
        "POSNR",  # Item Number
        "MATNR",  # Material Number
        "MEINS",  # Base Unit of Measure
        "PSMNG",  # Planned Quantity
        "WEMNG",  # Goods Receipt Quantity
        "WERKS",  # Plant
        "LGORT",  # Storage Location
        "LTRMI",  # Scheduled Finish Date
    ]

    # PO Schedule Lines (EKET) - for scheduled receipts in ATP
    PO_SCHEDULE_LINE_FIELDS = [
        "EBELN",  # Purchasing Document Number
        "EBELP",  # Item Number
        "ETENR",  # Schedule Line Number
        "EINDT",  # Delivery Date
        "MENGE",  # Scheduled Quantity
        "WEMNG",  # Goods Receipt Quantity (already received)
        "BANFN",  # Purchase Requisition Number
        "BNFPO",  # Requisition Item
    ]

    # Material Reservations (RESB) - for allocated/committed quantities
    RESERVATION_FIELDS = [
        "RSNUM",  # Reservation Number
        "RSPOS",  # Reservation Item
        "MATNR",  # Material Number
        "WERKS",  # Plant
        "LGORT",  # Storage Location
        "BDMNG",  # Requirement Quantity
        "ENMNG",  # Withdrawn Quantity
        "BDTER",  # Requirement Date
        "AUFNR",  # Production Order (if reserved for production)
        "KZEAR",  # Final Issue Indicator
        "XWAOK",  # Movement Allowed
    ]

    # Extended MARC fields for ATP calculation
    MARC_ATP_FIELDS = [
        "MATNR",  # Material Number
        "WERKS",  # Plant
        "EISBE",  # Safety Stock
        "MINBE",  # Reorder Point
        "PLIFZ",  # Planned Delivery Time (days)
        "WEBAZ",  # GR Processing Time (days)
        "DISPO",  # MRP Controller
        "DISMM",  # MRP Type
        "MTVFP",  # Availability Check Group (controls ATP checking)
        "BSTMI",  # Minimum Lot Size
        "BSTMA",  # Maximum Lot Size
        "BSTRF",  # Rounding Value
        "BESKZ",  # Procurement Type (E=in-house, F=external)
        "DZEIT",  # In-House Production Time (days)
        "LGPBE",  # Storage Bin
        "LGFSB",  # Default Storage Location for Ext. Procurement
    ]

    # ==========================================================================
    # Config Builder Fields (for building SupplyChainConfig from SAP data)
    # ==========================================================================

    # Purchasing Info Record Header (EINA) - vendor-product relationships
    PURCHASING_INFO_HEADER_FIELDS = [
        "INFNR",  # Purchasing Info Record Number
        "MATNR",  # Material Number
        "LIFNR",  # Vendor Number
        "LOEKZ",  # Deletion Indicator
    ]

    # Purchasing Info Record Item (EINE) - pricing, MOQ, lead times per org
    PURCHASING_INFO_ITEM_FIELDS = [
        "INFNR",  # Purchasing Info Record Number
        "EKORG",  # Purchasing Organization
        "ESOKZ",  # Purchasing Info Record Category
        "NETPR",  # Net Price
        "WAERS",  # Currency
        "PEINH",  # Price Unit
        "NORBM",  # Standard Order Quantity
        "MINBM",  # Minimum Order Quantity
        "APLFZ",  # Planned Delivery Time (days)
        "UEBTO",  # Over-delivery Tolerance (%)
        "UNTTO",  # Under-delivery Tolerance (%)
    ]

    # Source List (EORD) - approved vendor-plant assignments with priority
    SOURCE_LIST_FIELDS = [
        "MATNR",  # Material Number
        "WERKS",  # Plant
        "ZEESSION",  # Validity Period Counter (sequence)
        "VDATU",  # Valid From Date
        "BDATU",  # Valid To Date
        "LIFNR",  # Vendor Number
        "FLIFN",  # Fixed Vendor Indicator
        "NOTKZ",  # Source List Usage (1=normal, 2=blocked)
        "EKORG",  # Purchasing Organization
        "AUESSION",  # Agreement Number (outline agreement)
        "BESKZ",  # Procurement Type (F=external, E=in-house, U=subcontracting)
        "SOBSL",  # Special Procurement Type
    ]

    # Company Codes (T001)
    COMPANY_CODE_FIELDS = [
        "BUKRS",  # Company Code
        "BUTXT",  # Company Name
        "LAND1",  # Country Key
        "WAERS",  # Company Code Currency
        "ADRNR",  # Address Number (FK to ADRC)
    ]

    # Central Address Management (ADRC)
    ADDRESS_FIELDS = [
        "ADDRNUMBER",  # Address Number
        "NAME1",  # Name 1
        "CITY1",  # City
        "REGION",  # Region/State
        "COUNTRY",  # Country Key
        "POST_CODE1",  # Postal Code
        "STREET",  # Street
    ]

    # Customer Sales Data (KNVV) - customer grouping for market segmentation
    CUSTOMER_SALES_DATA_FIELDS = [
        "KUNNR",  # Customer Number
        "VKORG",  # Sales Organization
        "VTWEG",  # Distribution Channel
        "SPART",  # Division
        "KDGRP",  # Customer Group
        "BZIRK",  # Sales District
        "KVGR1",  # Customer Group 1
        "KVGR2",  # Customer Group 2
        "WAERS",  # Currency
    ]

    # Sales Data for Material (MVKE) - product hierarchy enrichment
    MATERIAL_SALES_DATA_FIELDS = [
        "MATNR",  # Material Number
        "VKORG",  # Sales Organization
        "VTWEG",  # Distribution Channel
        "PRODH",  # Product Hierarchy
        "MTPOS",  # Item Category Group
        "KONDM",  # Material Pricing Group
        "VERSG",  # Material Statistics Group
    ]

    # Routing Header (PLKO) - manufacturing process definitions
    ROUTING_HEADER_FIELDS = [
        "PLNTY",  # Task List Type (N=routing, R=reference, S=rate routing)
        "PLNNR",  # Group Counter (routing number)
        "PLNAL",  # Group/Alternative Counter
        "WERKS",  # Plant
        "VERWE",  # Usage (1=production, 2=process, 9=maintenance)
        "STATU",  # Status (1=created, 2=released, 3=locked)
        "LOSVN",  # Lot Size From
        "LOSBS",  # Lot Size To
        "DAESSION",  # Valid From Date
    ]

    # Routing Operation (PLPO) - setup/machine/labor times
    ROUTING_OPERATION_FIELDS = [
        "PLNTY",  # Task List Type
        "PLNNR",  # Routing Number
        "PLNKN",  # Operation/Activity Number
        "VORNR",  # Operation Number (display)
        "ARBID",  # Work Center (Object ID)
        "ARBPL",  # Work Center Name
        "WERKS",  # Plant
        "STEUS",  # Control Key
        "BMSCH",  # Base Quantity
        "VGW01",  # Setup Time
        "VGW02",  # Machine Time
        "VGW03",  # Labor Time
        "VGE01",  # Unit for Setup
        "VGE02",  # Unit for Machine
        "VGE03",  # Unit for Labor
    ]

    # BOM Header (STKO) - contextualizes existing STPO items
    BOM_HEADER_FIELDS = [
        "STLNR",  # Bill of Material Number
        "STLAL",  # Alternative BOM
        "STKOZ",  # BOM Category (M=material, S=sales, etc.)
        "BMENG",  # Base Quantity
        "BMEIN",  # Base Unit of Measure
        "DAESSION",  # Valid From Date
        "ANESSION",  # Valid To Date
        "STLST",  # BOM Status
    ]

    # Work Center Header (CRHD) - resource definitions
    WORK_CENTER_HEADER_FIELDS = [
        "OBJID",  # Object ID
        "ARBPL",  # Work Center
        "WERKS",  # Plant
        "OBJTY",  # Object Type (A=work center, D=PRT)
        "VERWE",  # Usage
    ]

    # Capacity Header (KAKO) - available capacity
    CAPACITY_HEADER_FIELDS = [
        "OBJID",  # Object ID
        "KAPESSION",  # Capacity Category (001=machine, 002=labor)
        "KESSION",  # Capacity Description
        "ESSION",  # Capacity Planning Indicator
        "ANESSION",  # Start Time
        "ENESSION",  # End Time
        "MOESSION",  # Monday Flag
        "DIESSION",  # Tuesday Flag
        "MIESSION",  # Wednesday Flag
        "DOESSION",  # Thursday Flag
        "FRESSION",  # Friday Flag
    ]

    # Material UOM Conversions (MARM) - unit conversion factors
    MATERIAL_UOM_FIELDS = [
        "MATNR",  # Material Number
        "MEINH",  # Alternative Unit of Measure
        "UMREZ",  # Numerator (alt → base)
        "UMREN",  # Denominator (alt → base)
        "BRGEW",  # Gross Weight
        "NTGEW",  # Net Weight
        "GEWEI",  # Weight Unit
        "VOLUM",  # Volume
        "VOLEH",  # Volume Unit
        "EAN11",  # EAN/UPC
    ]

    def __init__(self, config: S4HANAConnectionConfig):
        """Initialize S/4HANA connector."""
        if not PYRFC_AVAILABLE:
            raise ImportError(
                "pyrfc is required for S/4HANA connection. "
                "Install with: pip install pyrfc"
            )

        self.config = config
        self.connection: Optional[Connection] = None
        self._connected = False

    def connect(self) -> bool:
        """
        Establish RFC connection to S/4HANA.

        Returns:
            bool: True if connection successful
        """
        try:
            self.connection = Connection(
                ashost=self.config.ashost,
                sysnr=self.config.sysnr,
                client=self.config.client,
                user=self.config.user,
                passwd=self.config.passwd,
                lang=self.config.lang,
                trace=self.config.trace,
            )
            self._connected = True
            logger.info(f"Connected to S/4HANA: {self.config.ashost}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to S/4HANA: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """Close RFC connection."""
        if self.connection:
            self.connection.close()
            self._connected = False
            logger.info("Disconnected from S/4HANA")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    def _execute_query(
        self,
        table_name: str,
        fields: List[str],
        where_clause: Optional[List[Dict[str, str]]] = None,
        max_rows: int = 10000,
        skip_rows: int = 0
    ) -> pd.DataFrame:
        """
        Execute RFC_READ_TABLE to query SAP table.

        Args:
            table_name: SAP table name
            fields: List of field names to retrieve
            where_clause: WHERE conditions (list of dicts with FIELD, SIGN, OPTION, LOW, HIGH)
            max_rows: Maximum rows to retrieve
            skip_rows: Number of rows to skip (pagination)

        Returns:
            DataFrame with query results
        """
        if not self._connected:
            raise RuntimeError("Not connected to S/4HANA. Call connect() first.")

        try:
            # Prepare field list
            field_list = [{"FIELDNAME": field} for field in fields]

            # Prepare WHERE clause
            options = []
            if where_clause:
                for condition in where_clause:
                    options.append({
                        "TEXT": f"{condition['FIELD']} {condition['OPTION']} {condition['LOW']}"
                    })

            # Execute RFC_READ_TABLE
            result = self.connection.call(
                "RFC_READ_TABLE",
                QUERY_TABLE=table_name,
                DELIMITER="|",
                FIELDS=field_list,
                OPTIONS=options,
                ROWCOUNT=max_rows,
                ROWSKIPS=skip_rows,
            )

            # Parse results
            if not result.get("DATA"):
                logger.warning(f"No data returned from table {table_name}")
                return pd.DataFrame(columns=fields)

            # Convert to DataFrame
            rows = []
            for row_data in result["DATA"]:
                row_str = row_data["WA"]
                values = [v.strip() for v in row_str.split("|")]
                rows.append(values)

            df = pd.DataFrame(rows, columns=fields)

            # Clean up data types
            df = self._convert_datatypes(df, table_name)

            logger.info(f"Retrieved {len(df)} rows from {table_name}")
            return df

        except ABAPApplicationError as e:
            logger.error(f"ABAP Application Error: {e}")
            return pd.DataFrame(columns=fields)
        except ABAPRuntimeError as e:
            logger.error(f"ABAP Runtime Error: {e}")
            return pd.DataFrame(columns=fields)
        except Exception as e:
            logger.error(f"Error querying {table_name}: {e}")
            return pd.DataFrame(columns=fields)

    def _convert_datatypes(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Convert SAP datatypes to appropriate pandas types."""
        # Common date fields
        date_fields = ["AEDAT", "ERDAT", "BEDAT", "LFDAT", "WADAT_IST"]
        for field in date_fields:
            if field in df.columns:
                df[field] = pd.to_datetime(df[field], format="%Y%m%d", errors="coerce")

        # Numeric fields
        numeric_patterns = ["MENGE", "KWMENG", "LFIMG", "NETPR", "BSTMI", "EISBE", "PLIFZ"]
        for field in df.columns:
            if any(pattern in field for pattern in numeric_patterns):
                df[field] = pd.to_numeric(df[field], errors="coerce")

        return df

    def extract_materials(
        self,
        plant: Optional[str] = None,
        material_type: Optional[str] = None,
        max_rows: int = 10000
    ) -> pd.DataFrame:
        """
        Extract material master data.

        Args:
            plant: Plant filter (optional)
            material_type: Material type filter (optional)
            max_rows: Maximum rows to retrieve

        Returns:
            DataFrame with material master data
        """
        logger.info(f"Extracting materials from S/4HANA (plant={plant})")

        # Get general material data
        where_clause = []
        if material_type:
            where_clause.append({
                "FIELD": "MTART",
                "OPTION": "EQ",
                "LOW": material_type
            })

        mara = self._execute_query(
            table_name="MARA",
            fields=self.MATERIAL_MASTER_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows
        )

        # Get plant-specific data
        if plant:
            marc_where = [{"FIELD": "WERKS", "OPTION": "EQ", "LOW": plant}]
        else:
            marc_where = None

        marc = self._execute_query(
            table_name="MARC",
            fields=self.PLANT_MATERIAL_FIELDS,
            where_clause=marc_where,
            max_rows=max_rows
        )

        # Merge material data
        if not mara.empty and not marc.empty:
            materials = mara.merge(marc, on="MATNR", how="left")
        elif not mara.empty:
            materials = mara
        else:
            materials = marc

        logger.info(f"Extracted {len(materials)} materials")
        return materials

    def extract_purchase_orders(
        self,
        plant: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        max_rows: int = 10000
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Extract purchase order data.

        Args:
            plant: Plant filter (optional)
            date_from: Start date filter (optional)
            date_to: End date filter (optional)
            max_rows: Maximum rows to retrieve

        Returns:
            Tuple of (header DataFrame, item DataFrame)
        """
        logger.info(f"Extracting purchase orders from S/4HANA (plant={plant})")

        # Extract headers
        where_clause = []
        if date_from:
            where_clause.append({
                "FIELD": "BEDAT",
                "OPTION": "GE",
                "LOW": date_from.strftime("%Y%m%d")
            })
        if date_to:
            where_clause.append({
                "FIELD": "BEDAT",
                "OPTION": "LE",
                "LOW": date_to.strftime("%Y%m%d")
            })

        headers = self._execute_query(
            table_name="EKKO",
            fields=self.PURCHASE_ORDER_HEADER_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows
        )

        # Extract items
        item_where = []
        if plant:
            item_where.append({
                "FIELD": "WERKS",
                "OPTION": "EQ",
                "LOW": plant
            })

        items = self._execute_query(
            table_name="EKPO",
            fields=self.PURCHASE_ORDER_ITEM_FIELDS,
            where_clause=item_where if item_where else None,
            max_rows=max_rows
        )

        # Filter items to match headers
        if not headers.empty and not items.empty:
            po_numbers = headers["EBELN"].unique()
            items = items[items["EBELN"].isin(po_numbers)]

        logger.info(f"Extracted {len(headers)} PO headers, {len(items)} items")
        return headers, items

    def extract_sales_orders(
        self,
        sales_org: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        max_rows: int = 10000
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Extract sales order data.

        Args:
            sales_org: Sales organization filter (optional)
            date_from: Start date filter (optional)
            date_to: End date filter (optional)
            max_rows: Maximum rows to retrieve

        Returns:
            Tuple of (header DataFrame, item DataFrame)
        """
        logger.info(f"Extracting sales orders from S/4HANA (org={sales_org})")

        # Extract headers
        where_clause = []
        if sales_org:
            where_clause.append({
                "FIELD": "VKORG",
                "OPTION": "EQ",
                "LOW": sales_org
            })
        if date_from:
            where_clause.append({
                "FIELD": "ERDAT",
                "OPTION": "GE",
                "LOW": date_from.strftime("%Y%m%d")
            })
        if date_to:
            where_clause.append({
                "FIELD": "ERDAT",
                "OPTION": "LE",
                "LOW": date_to.strftime("%Y%m%d")
            })

        headers = self._execute_query(
            table_name="VBAK",
            fields=self.SALES_ORDER_HEADER_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows
        )

        # Extract items
        items = self._execute_query(
            table_name="VBAP",
            fields=self.SALES_ORDER_ITEM_FIELDS,
            where_clause=None,
            max_rows=max_rows
        )

        # Filter items to match headers
        if not headers.empty and not items.empty:
            so_numbers = headers["VBELN"].unique()
            items = items[items["VBELN"].isin(so_numbers)]

        logger.info(f"Extracted {len(headers)} SO headers, {len(items)} items")
        return headers, items

    def extract_deliveries(
        self,
        plant: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        max_rows: int = 10000
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Extract delivery data.

        Args:
            plant: Plant filter (optional)
            date_from: Start date filter (optional)
            date_to: End date filter (optional)
            max_rows: Maximum rows to retrieve

        Returns:
            Tuple of (header DataFrame, item DataFrame)
        """
        logger.info(f"Extracting deliveries from S/4HANA (plant={plant})")

        # Extract headers
        where_clause = []
        if date_from:
            where_clause.append({
                "FIELD": "LFDAT",
                "OPTION": "GE",
                "LOW": date_from.strftime("%Y%m%d")
            })
        if date_to:
            where_clause.append({
                "FIELD": "LFDAT",
                "OPTION": "LE",
                "LOW": date_to.strftime("%Y%m%d")
            })

        headers = self._execute_query(
            table_name="LIKP",
            fields=self.DELIVERY_HEADER_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows
        )

        # Extract items
        item_where = []
        if plant:
            item_where.append({
                "FIELD": "WERKS",
                "OPTION": "EQ",
                "LOW": plant
            })

        items = self._execute_query(
            table_name="LIPS",
            fields=self.DELIVERY_ITEM_FIELDS,
            where_clause=item_where if item_where else None,
            max_rows=max_rows
        )

        # Filter items to match headers
        if not headers.empty and not items.empty:
            delivery_numbers = headers["VBELN"].unique()
            items = items[items["VBELN"].isin(delivery_numbers)]

        logger.info(f"Extracted {len(headers)} delivery headers, {len(items)} items")
        return headers, items

    def extract_inventory(
        self,
        plant: Optional[str] = None,
        storage_location: Optional[str] = None,
        max_rows: int = 10000
    ) -> pd.DataFrame:
        """
        Extract inventory/stock data from MARD (Material Master Storage Location).

        Args:
            plant: Plant filter (optional)
            storage_location: Storage location filter (optional)
            max_rows: Maximum rows to retrieve

        Returns:
            DataFrame with inventory data
        """
        logger.info(f"Extracting inventory from S/4HANA (plant={plant})")

        where_clause = []
        if plant:
            where_clause.append({
                "FIELD": "WERKS",
                "OPTION": "EQ",
                "LOW": plant
            })
        if storage_location:
            where_clause.append({
                "FIELD": "LGORT",
                "OPTION": "EQ",
                "LOW": storage_location
            })

        fields = [
            "MATNR",  # Material
            "WERKS",  # Plant
            "LGORT",  # Storage Location
            "LABST",  # Unrestricted Stock
            "UMLME",  # Stock in Transfer
            "INSME",  # Quality Inspection Stock
            "SPEME",  # Blocked Stock
            "EINME",  # Restricted Stock
        ]

        inventory = self._execute_query(
            table_name="MARD",
            fields=fields,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows
        )

        logger.info(f"Extracted inventory for {len(inventory)} material-location combinations")
        return inventory

    def extract_plants(self, max_rows: int = 1000) -> pd.DataFrame:
        """
        Extract plant master data.

        Returns:
            DataFrame with plant data
        """
        logger.info("Extracting plants from S/4HANA")

        fields = [
            "WERKS",  # Plant
            "NAME1",  # Name
            "KUNNR",  # Customer Number
            "LIFNR",  # Vendor Number
            "VKORG",  # Sales Organization
            "VTWEG",  # Distribution Channel
        ]

        plants = self._execute_query(
            table_name="T001W",
            fields=fields,
            max_rows=max_rows
        )

        logger.info(f"Extracted {len(plants)} plants")
        return plants

    # ==========================================================================
    # Config Builder Extraction Methods
    # ==========================================================================

    def extract_purchasing_info_records(
        self,
        vendor: Optional[str] = None,
        max_rows: int = 10000
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Extract purchasing info records (EINA header + EINE item).

        Returns vendor-product relationships with pricing, MOQs, and lead times.
        """
        logger.info(f"Extracting purchasing info records (vendor={vendor})")

        where_clause = []
        if vendor:
            where_clause.append({"FIELD": "LIFNR", "OPTION": "EQ", "LOW": vendor})

        headers = self._execute_query(
            table_name="EINA",
            fields=self.PURCHASING_INFO_HEADER_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows,
        )

        items = self._execute_query(
            table_name="EINE",
            fields=self.PURCHASING_INFO_ITEM_FIELDS,
            where_clause=None,
            max_rows=max_rows,
        )

        if not headers.empty and not items.empty:
            info_nrs = headers["INFNR"].unique()
            items = items[items["INFNR"].isin(info_nrs)]

        logger.info(f"Extracted {len(headers)} info record headers, {len(items)} items")
        return headers, items

    def extract_source_list(
        self,
        plant: Optional[str] = None,
        max_rows: int = 10000
    ) -> pd.DataFrame:
        """Extract source list (EORD) — approved vendor-plant-material assignments."""
        logger.info(f"Extracting source list (plant={plant})")

        where_clause = []
        if plant:
            where_clause.append({"FIELD": "WERKS", "OPTION": "EQ", "LOW": plant})

        source_list = self._execute_query(
            table_name="EORD",
            fields=self.SOURCE_LIST_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows,
        )

        logger.info(f"Extracted {len(source_list)} source list entries")
        return source_list

    def extract_company_codes(self, max_rows: int = 500) -> pd.DataFrame:
        """Extract company codes (T001)."""
        logger.info("Extracting company codes")

        companies = self._execute_query(
            table_name="T001",
            fields=self.COMPANY_CODE_FIELDS,
            max_rows=max_rows,
        )

        logger.info(f"Extracted {len(companies)} company codes")
        return companies

    def extract_addresses(
        self,
        address_numbers: Optional[List[str]] = None,
        max_rows: int = 10000
    ) -> pd.DataFrame:
        """Extract central addresses (ADRC) for sites and partners."""
        logger.info("Extracting addresses")

        where_clause = []
        if address_numbers:
            for addr in address_numbers[:50]:
                where_clause.append({"FIELD": "ADDRNUMBER", "OPTION": "EQ", "LOW": addr})

        addresses = self._execute_query(
            table_name="ADRC",
            fields=self.ADDRESS_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows,
        )

        logger.info(f"Extracted {len(addresses)} addresses")
        return addresses

    def extract_customer_sales_data(
        self,
        sales_org: Optional[str] = None,
        max_rows: int = 10000
    ) -> pd.DataFrame:
        """Extract customer sales data (KNVV) for market segmentation."""
        logger.info(f"Extracting customer sales data (sales_org={sales_org})")

        where_clause = []
        if sales_org:
            where_clause.append({"FIELD": "VKORG", "OPTION": "EQ", "LOW": sales_org})

        customers = self._execute_query(
            table_name="KNVV",
            fields=self.CUSTOMER_SALES_DATA_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows,
        )

        logger.info(f"Extracted {len(customers)} customer sales records")
        return customers

    def extract_material_sales_data(
        self,
        sales_org: Optional[str] = None,
        max_rows: int = 10000
    ) -> pd.DataFrame:
        """Extract material sales data (MVKE) for product hierarchy enrichment."""
        logger.info(f"Extracting material sales data (sales_org={sales_org})")

        where_clause = []
        if sales_org:
            where_clause.append({"FIELD": "VKORG", "OPTION": "EQ", "LOW": sales_org})

        material_sales = self._execute_query(
            table_name="MVKE",
            fields=self.MATERIAL_SALES_DATA_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows,
        )

        logger.info(f"Extracted {len(material_sales)} material sales records")
        return material_sales

    def extract_routings(
        self,
        plant: Optional[str] = None,
        max_rows: int = 10000
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Extract routing headers (PLKO) and operations (PLPO).

        Returns manufacturing process definitions with setup/machine/labor times.
        """
        logger.info(f"Extracting routings (plant={plant})")

        where_clause = []
        if plant:
            where_clause.append({"FIELD": "WERKS", "OPTION": "EQ", "LOW": plant})

        headers = self._execute_query(
            table_name="PLKO",
            fields=self.ROUTING_HEADER_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows,
        )

        op_where = []
        if plant:
            op_where.append({"FIELD": "WERKS", "OPTION": "EQ", "LOW": plant})

        operations = self._execute_query(
            table_name="PLPO",
            fields=self.ROUTING_OPERATION_FIELDS,
            where_clause=op_where if op_where else None,
            max_rows=max_rows,
        )

        if not headers.empty and not operations.empty:
            routing_ids = headers["PLNNR"].unique()
            operations = operations[operations["PLNNR"].isin(routing_ids)]

        logger.info(f"Extracted {len(headers)} routing headers, {len(operations)} operations")
        return headers, operations

    def extract_bom_headers(
        self,
        max_rows: int = 10000
    ) -> pd.DataFrame:
        """Extract BOM headers (STKO) to contextualize STPO items."""
        logger.info("Extracting BOM headers")

        bom_headers = self._execute_query(
            table_name="STKO",
            fields=self.BOM_HEADER_FIELDS,
            max_rows=max_rows,
        )

        logger.info(f"Extracted {len(bom_headers)} BOM headers")
        return bom_headers

    def extract_work_centers(
        self,
        plant: Optional[str] = None,
        max_rows: int = 5000
    ) -> pd.DataFrame:
        """Extract work center definitions (CRHD)."""
        logger.info(f"Extracting work centers (plant={plant})")

        where_clause = []
        if plant:
            where_clause.append({"FIELD": "WERKS", "OPTION": "EQ", "LOW": plant})

        work_centers = self._execute_query(
            table_name="CRHD",
            fields=self.WORK_CENTER_HEADER_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows,
        )

        logger.info(f"Extracted {len(work_centers)} work centers")
        return work_centers

    def extract_capacity_headers(
        self,
        max_rows: int = 5000
    ) -> pd.DataFrame:
        """Extract capacity headers (KAKO) for resource capacity planning."""
        logger.info("Extracting capacity headers")

        capacity = self._execute_query(
            table_name="KAKO",
            fields=self.CAPACITY_HEADER_FIELDS,
            max_rows=max_rows,
        )

        logger.info(f"Extracted {len(capacity)} capacity records")
        return capacity

    def extract_material_uom(
        self,
        max_rows: int = 10000
    ) -> pd.DataFrame:
        """Extract material UOM conversions (MARM)."""
        logger.info("Extracting material UOM conversions")

        uom = self._execute_query(
            table_name="MARM",
            fields=self.MATERIAL_UOM_FIELDS,
            max_rows=max_rows,
        )

        logger.info(f"Extracted {len(uom)} UOM conversion records")
        return uom

    def execute_bapi(self, bapi_name: str, **params) -> Dict[str, Any]:
        """
        Execute a BAPI function module.

        Args:
            bapi_name: Name of BAPI function
            **params: BAPI parameters

        Returns:
            BAPI result dictionary
        """
        if not self._connected:
            raise RuntimeError("Not connected to S/4HANA. Call connect() first.")

        try:
            result = self.connection.call(bapi_name, **params)
            logger.info(f"Executed BAPI: {bapi_name}")
            return result

        except Exception as e:
            logger.error(f"Error executing BAPI {bapi_name}: {e}")
            raise

    # ==========================================================================
    # ATP/CTP Integration Methods (Phase 1 - SAP ATP Integration)
    # ==========================================================================

    def extract_production_orders(
        self,
        plant: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        status: Optional[str] = None,
        max_rows: int = 10000
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Extract production orders (AFKO/AFPO) for CTP calculation.

        Production orders represent manufacturing commitments that affect:
        - CTP: Committed capacity reduces available-to-promise
        - ATP: Scheduled receipts from production increase supply

        Args:
            plant: Plant filter (optional)
            date_from: Filter orders with finish date >= date_from
            date_to: Filter orders with finish date <= date_to
            status: Status filter (REL=Released, CNF=Confirmed, TECO=Completed)
            max_rows: Maximum rows to retrieve

        Returns:
            Tuple of (header DataFrame from AFKO, item DataFrame from AFPO)
        """
        logger.info(f"Extracting production orders from S/4HANA (plant={plant}, status={status})")

        # Build header WHERE clause
        header_where = []
        if plant:
            header_where.append({
                "FIELD": "WERKS",
                "OPTION": "EQ",
                "LOW": plant
            })
        if date_from:
            header_where.append({
                "FIELD": "GLTRP",
                "OPTION": "GE",
                "LOW": date_from.strftime("%Y%m%d")
            })
        if date_to:
            header_where.append({
                "FIELD": "GLTRP",
                "OPTION": "LE",
                "LOW": date_to.strftime("%Y%m%d")
            })

        # Extract production order headers
        headers = self._execute_query(
            table_name="AFKO",
            fields=self.PRODUCTION_ORDER_HEADER_FIELDS,
            where_clause=header_where if header_where else None,
            max_rows=max_rows
        )

        # Filter by status if specified (status is in STAT field as text codes)
        if status and not headers.empty:
            headers = headers[headers["STAT"].str.contains(status, na=False)]

        # Extract production order items
        item_where = []
        if plant:
            item_where.append({
                "FIELD": "WERKS",
                "OPTION": "EQ",
                "LOW": plant
            })

        items = self._execute_query(
            table_name="AFPO",
            fields=self.PRODUCTION_ORDER_ITEM_FIELDS,
            where_clause=item_where if item_where else None,
            max_rows=max_rows
        )

        # Filter items to match headers
        if not headers.empty and not items.empty:
            order_numbers = headers["AUFNR"].unique()
            items = items[items["AUFNR"].isin(order_numbers)]

        logger.info(f"Extracted {len(headers)} production order headers, {len(items)} items")
        return headers, items

    def extract_schedule_lines(
        self,
        plant: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        max_rows: int = 10000
    ) -> pd.DataFrame:
        """
        Extract PO schedule lines (EKET) for scheduled receipts in ATP.

        Schedule lines represent confirmed delivery dates and quantities for
        purchase orders. The open quantity (MENGE - WEMNG) is a scheduled receipt.

        Args:
            plant: Plant filter (requires join with EKPO)
            date_from: Filter schedule lines with delivery date >= date_from
            date_to: Filter schedule lines with delivery date <= date_to
            max_rows: Maximum rows to retrieve

        Returns:
            DataFrame with schedule line data including open quantities
        """
        logger.info(f"Extracting PO schedule lines from S/4HANA (date_from={date_from})")

        # Build WHERE clause for date range
        where_clause = []
        if date_from:
            where_clause.append({
                "FIELD": "EINDT",
                "OPTION": "GE",
                "LOW": date_from.strftime("%Y%m%d")
            })
        if date_to:
            where_clause.append({
                "FIELD": "EINDT",
                "OPTION": "LE",
                "LOW": date_to.strftime("%Y%m%d")
            })

        # Extract schedule lines
        schedule_lines = self._execute_query(
            table_name="EKET",
            fields=self.PO_SCHEDULE_LINE_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows
        )

        # If plant filter specified, need to join with EKPO to filter
        if plant and not schedule_lines.empty:
            # Get PO items for the plant
            item_where = [{"FIELD": "WERKS", "OPTION": "EQ", "LOW": plant}]
            po_items = self._execute_query(
                table_name="EKPO",
                fields=["EBELN", "EBELP", "MATNR", "WERKS"],
                where_clause=item_where,
                max_rows=max_rows
            )

            if not po_items.empty:
                # Merge to get material and plant info
                schedule_lines = schedule_lines.merge(
                    po_items,
                    on=["EBELN", "EBELP"],
                    how="inner"
                )

        # Calculate open quantity (scheduled - received)
        if not schedule_lines.empty:
            schedule_lines["MENGE"] = pd.to_numeric(schedule_lines["MENGE"], errors="coerce").fillna(0)
            schedule_lines["WEMNG"] = pd.to_numeric(schedule_lines["WEMNG"], errors="coerce").fillna(0)
            schedule_lines["OPEN_QTY"] = schedule_lines["MENGE"] - schedule_lines["WEMNG"]
            # Filter to only open schedule lines
            schedule_lines = schedule_lines[schedule_lines["OPEN_QTY"] > 0]

        logger.info(f"Extracted {len(schedule_lines)} open PO schedule lines")
        return schedule_lines

    def extract_reservations(
        self,
        plant: Optional[str] = None,
        material: Optional[str] = None,
        date_from: Optional[date] = None,
        max_rows: int = 10000
    ) -> pd.DataFrame:
        """
        Extract material reservations (RESB) for allocated/committed quantities.

        Reservations represent material that is committed for production orders
        or other purposes. This reduces ATP.

        Args:
            plant: Plant filter
            material: Material number filter
            date_from: Filter reservations with requirement date >= date_from
            max_rows: Maximum rows to retrieve

        Returns:
            DataFrame with reservation data including open quantities
        """
        logger.info(f"Extracting reservations from S/4HANA (plant={plant}, material={material})")

        where_clause = []
        if plant:
            where_clause.append({
                "FIELD": "WERKS",
                "OPTION": "EQ",
                "LOW": plant
            })
        if material:
            where_clause.append({
                "FIELD": "MATNR",
                "OPTION": "EQ",
                "LOW": material.zfill(18)  # SAP materials are 18 chars
            })
        if date_from:
            where_clause.append({
                "FIELD": "BDTER",
                "OPTION": "GE",
                "LOW": date_from.strftime("%Y%m%d")
            })

        reservations = self._execute_query(
            table_name="RESB",
            fields=self.RESERVATION_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows
        )

        # Calculate open reservation quantity (required - withdrawn)
        if not reservations.empty:
            reservations["BDMNG"] = pd.to_numeric(reservations["BDMNG"], errors="coerce").fillna(0)
            reservations["ENMNG"] = pd.to_numeric(reservations["ENMNG"], errors="coerce").fillna(0)
            reservations["OPEN_QTY"] = reservations["BDMNG"] - reservations["ENMNG"]
            # Filter to only open reservations
            reservations = reservations[reservations["OPEN_QTY"] > 0]

        logger.info(f"Extracted {len(reservations)} open reservations")
        return reservations

    def extract_material_atp_data(
        self,
        plant: Optional[str] = None,
        materials: Optional[List[str]] = None,
        max_rows: int = 10000
    ) -> pd.DataFrame:
        """
        Extract extended MARC data for ATP calculation.

        This retrieves material-plant specific data needed for ATP:
        - Safety stock (EISBE)
        - Planned delivery time (PLIFZ)
        - In-house production time (DZEIT)
        - MRP settings (DISPO, DISMM, MTVFP)

        Args:
            plant: Plant filter
            materials: List of material numbers to filter
            max_rows: Maximum rows to retrieve

        Returns:
            DataFrame with ATP-relevant material master data
        """
        logger.info(f"Extracting material ATP data from S/4HANA (plant={plant})")

        where_clause = []
        if plant:
            where_clause.append({
                "FIELD": "WERKS",
                "OPTION": "EQ",
                "LOW": plant
            })
        if materials:
            # Multiple materials - use IN clause via multiple conditions
            for material in materials[:10]:  # Limit to 10 materials per query
                where_clause.append({
                    "FIELD": "MATNR",
                    "OPTION": "EQ",
                    "LOW": material.zfill(18)
                })

        marc_data = self._execute_query(
            table_name="MARC",
            fields=self.MARC_ATP_FIELDS,
            where_clause=where_clause if where_clause else None,
            max_rows=max_rows
        )

        # Convert numeric fields
        if not marc_data.empty:
            numeric_fields = ["EISBE", "MINBE", "PLIFZ", "WEBAZ", "BSTMI", "BSTMA", "BSTRF", "DZEIT"]
            for field in numeric_fields:
                if field in marc_data.columns:
                    marc_data[field] = pd.to_numeric(marc_data[field], errors="coerce").fillna(0)

        logger.info(f"Extracted ATP data for {len(marc_data)} material-plant combinations")
        return marc_data

    # ==========================================================================
    # ATP BAPIs (Phase 1 - SAP ATP Integration)
    # ==========================================================================

    def call_bapi_material_availability(
        self,
        plant: str,
        material: str,
        check_date: date,
        quantity: float = 1.0,
        unit: str = "EA",
        check_rule: str = "A"
    ) -> Dict[str, Any]:
        """
        Call BAPI_MATERIAL_AVAILABILITY for real-time ATP check.

        This BAPI performs the standard SAP availability check and returns
        the available quantity for a material at a specific date.

        Args:
            plant: Plant code (e.g., "1000")
            material: Material number
            check_date: Date to check availability
            quantity: Quantity to check (default 1.0)
            unit: Unit of measure (default "EA")
            check_rule: Availability check rule (default "A" for ATP)
                - "A": ATP check
                - "B": ATP + planned receipts
                - "Z": Custom check rule

        Returns:
            Dict with:
            - AV_QTY_PLT: Available quantity at plant level
            - DIALOGFLAG: 'X' if sufficient, '' if insufficient
            - RETURN: List of messages
        """
        logger.info(f"Calling BAPI_MATERIAL_AVAILABILITY for {material} at {plant}")

        try:
            result = self.execute_bapi(
                "BAPI_MATERIAL_AVAILABILITY",
                PLANT=plant,
                MATERIAL=material.zfill(18),
                UNIT=unit,
                CHECK_RULE=check_rule,
                STGE_LOC="",  # All storage locations
                BATCH="",  # All batches
                CUSTOMER="",
                DESIRED_QTY=quantity,
                DESIRED_DATE=check_date.strftime("%Y%m%d"),
            )

            # Log result
            av_qty = result.get("AV_QTY_PLT", 0)
            dialog_flag = result.get("DIALOGFLAG", "")
            logger.info(f"ATP result: {av_qty} available, sufficient={dialog_flag=='X'}")

            return result

        except Exception as e:
            logger.error(f"BAPI_MATERIAL_AVAILABILITY failed: {e}")
            # Return empty result on failure
            return {
                "AV_QTY_PLT": 0,
                "DIALOGFLAG": "",
                "RETURN": [{"TYPE": "E", "MESSAGE": str(e)}]
            }

    def call_bapi_availability_check(
        self,
        sales_order: str,
        sales_item: str,
        check_scope: str = "A"
    ) -> Dict[str, Any]:
        """
        Call SD availability check BAPI for sales order ATP.

        This BAPI performs availability check for a specific sales order item
        and returns confirmed schedule lines.

        Args:
            sales_order: Sales document number
            sales_item: Sales item number
            check_scope: Check scope
                - "A": ATP check only
                - "B": Complete planning check

        Returns:
            Dict with:
            - SCHEDULE_LINES: Confirmed schedule lines with dates/quantities
            - AVAILABILITY_INFO: ATP details per date
            - RETURN: Messages
        """
        logger.info(f"Calling SD availability check for SO {sales_order}/{sales_item}")

        try:
            result = self.execute_bapi(
                "BAPI_SALESORDER_GETAVAILABILITY",
                SALESDOCUMENT=sales_order,
                SALESDOCUMENTITEM=sales_item.zfill(6),
            )

            return result

        except Exception as e:
            logger.error(f"SD availability check failed: {e}")
            return {
                "SCHEDULE_LINES": [],
                "AVAILABILITY_INFO": [],
                "RETURN": [{"TYPE": "E", "MESSAGE": str(e)}]
            }

    def call_bapi_atp_multi_level(
        self,
        plant: str,
        material: str,
        check_date: date,
        quantity: float,
        check_components: bool = True
    ) -> Dict[str, Any]:
        """
        Call multi-level ATP check including component availability.

        This is used for CTP (Capable-to-Promise) when the material requires
        production and we need to check component availability.

        Args:
            plant: Plant code
            material: Material number
            check_date: Date to check
            quantity: Quantity to check
            check_components: Whether to check component availability

        Returns:
            Dict with:
            - WMDVSX: ATP result table with per-period availability
            - RETURN: Messages
        """
        logger.info(f"Calling multi-level ATP for {material} at {plant}")

        try:
            # Build ATP input structure
            atp_input = [{
                "MATERIAL": material.zfill(18),
                "PLANT": plant,
                "REQQTY": quantity,
                "UNIT": "EA",
                "REQDATE": check_date.strftime("%Y%m%d"),
                "CHECKSCOPE": "X" if check_components else "",
            }]

            result = self.execute_bapi(
                "BAPI_MATERIAL_BOM_AVAILABILITY",
                ATPINPUT=atp_input,
            )

            return result

        except Exception as e:
            logger.error(f"Multi-level ATP check failed: {e}")
            return {
                "WMDVSX": [],
                "RETURN": [{"TYPE": "E", "MESSAGE": str(e)}]
            }

    def call_bapi_salesorder_change(
        self,
        sales_order: str,
        schedule_lines: List[Dict[str, Any]],
        test_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Call BAPI to update sales order schedule lines (write-back).

        Used to confirm order promises by updating the confirmed quantity
        and delivery date on sales order schedule lines.

        Args:
            sales_order: Sales document number
            schedule_lines: List of schedule line updates with:
                - ITM_NUMBER: Item number
                - SCHED_LINE: Schedule line number
                - REQ_DATE: Requested delivery date
                - REQ_QTY: Confirmed quantity
            test_mode: If True, simulate only (no commit)

        Returns:
            Dict with:
            - SALESDOCUMENT: Updated sales document number
            - RETURN: Messages
        """
        logger.info(f"Calling BAPI_SALESORDER_CHANGE for SO {sales_order}")

        try:
            # Build schedule line input
            schedule_in = []
            schedule_inx = []  # Change flags

            for line in schedule_lines:
                schedule_in.append({
                    "ITM_NUMBER": line.get("ITM_NUMBER", "000010"),
                    "SCHED_LINE": line.get("SCHED_LINE", "0001"),
                    "REQ_DATE": line.get("REQ_DATE", ""),
                    "REQ_QTY": line.get("REQ_QTY", 0),
                })
                schedule_inx.append({
                    "ITM_NUMBER": line.get("ITM_NUMBER", "000010"),
                    "SCHED_LINE": line.get("SCHED_LINE", "0001"),
                    "UPDATEFLAG": "U",
                    "REQ_DATE": "X" if line.get("REQ_DATE") else "",
                    "REQ_QTY": "X" if line.get("REQ_QTY") else "",
                })

            result = self.execute_bapi(
                "BAPI_SALESORDER_CHANGE",
                SALESDOCUMENT=sales_order,
                ORDER_HEADER_IN={},
                ORDER_HEADER_INX={"UPDATEFLAG": "U"},
                SCHEDULE_LINES=schedule_in,
                SCHEDULE_LINESX=schedule_inx,
                SIMULATION=test_mode,
            )

            # Commit if not in test mode and successful
            if not test_mode:
                return_messages = result.get("RETURN", [])
                has_error = any(msg.get("TYPE") == "E" for msg in return_messages)
                if not has_error:
                    self.execute_bapi("BAPI_TRANSACTION_COMMIT", WAIT="X")
                    logger.info(f"Committed sales order changes for {sales_order}")
                else:
                    self.execute_bapi("BAPI_TRANSACTION_ROLLBACK")
                    logger.warning(f"Rolled back sales order changes for {sales_order}")

            return result

        except Exception as e:
            logger.error(f"BAPI_SALESORDER_CHANGE failed: {e}")
            return {
                "SALESDOCUMENT": sales_order,
                "RETURN": [{"TYPE": "E", "MESSAGE": str(e)}]
            }
