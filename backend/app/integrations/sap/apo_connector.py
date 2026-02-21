"""
SAP APO (Advanced Planner and Optimizer) Connector.

Primary Mode: CSV file-based extraction
Fallback Mode: RFC connection (if available)

APO Tables:
- /SAPAPO/LOC: Locations
- /SAPAPO/MAT: Materials
- /SAPAPO/MATLOC: Material-Location relationships
- /SAPAPO/ORD: Orders
- /SAPAPO/ORDTS: Order Time Series
- /SAPAPO/STOCK: Stock/Inventory
- /SAPAPO/PDS: Product Data Structure
- /SAPAPO/SNP: SNP Planning
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
import pandas as pd

try:
    from pyrfc import Connection, ABAPApplicationError, ABAPRuntimeError
    PYRFC_AVAILABLE = True
except ImportError:
    PYRFC_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class APOConnectionConfig:
    """APO connection configuration."""
    # RFC connection (if available)
    ashost: Optional[str] = None
    sysnr: Optional[str] = None
    client: Optional[str] = None
    user: Optional[str] = None
    passwd: Optional[str] = None
    lang: str = "EN"

    # CSV file mode
    csv_directory: Optional[str] = None
    use_csv_mode: bool = True  # Default to CSV mode


class APOConnector:
    """
    Connector for SAP APO supply chain planning data.

    Supports two modes:
    1. CSV file extraction (primary/recommended)
    2. RFC connection (fallback if pyrfc available)

    APO is primarily accessed via CSV exports due to:
    - Complex liveCache architecture
    - Performance considerations
    - Data volume in planning tables
    """

    # Standard APO table field mappings
    LOCATION_FIELDS = [
        "LOCNO",  # Location Number
        "LOCDESC",  # Location Description
        "LOCTYPE",  # Location Type (plant, DC, customer, etc.)
        "COUNTRY",  # Country
        "REGION",  # Region
        "CITY",  # City
        "CURRENCY",  # Currency
    ]

    MATERIAL_FIELDS = [
        "MATNR",  # Material Number
        "MATDESC",  # Material Description
        "MATTYPE",  # Material Type
        "BASEUNIT",  # Base Unit of Measure
        "PRODGRP",  # Product Group
        "LIFCYCLE",  # Lifecycle Status
    ]

    MATERIAL_LOCATION_FIELDS = [
        "MATNR",  # Material Number
        "LOCNO",  # Location Number
        "SAFETY_STOCK",  # Safety Stock
        "REORDER_POINT",  # Reorder Point
        "MAX_STOCK",  # Maximum Stock Level
        "LEAD_TIME",  # Replenishment Lead Time
        "LOT_SIZE",  # Lot Size
        "PROCUREMENT_TYPE",  # Procurement Type
    ]

    ORDER_FIELDS = [
        "ORDERNO",  # Order Number
        "ORDERTYPE",  # Order Type (PO, SO, TO, etc.)
        "MATNR",  # Material Number
        "FROM_LOC",  # Source Location
        "TO_LOC",  # Destination Location
        "QUANTITY",  # Order Quantity
        "OPEN_QTY",  # Open Quantity
        "ORDERDATE",  # Order Date
        "DELIVERY_DATE",  # Delivery Date
        "STATUS",  # Order Status
    ]

    STOCK_FIELDS = [
        "MATNR",  # Material Number
        "LOCNO",  # Location Number
        "STOCK_DATE",  # Stock Date
        "AVAILABLE_QTY",  # Available Stock
        "IN_TRANSIT_QTY",  # In-Transit Stock
        "BLOCKED_QTY",  # Blocked Stock
        "QUALITY_QTY",  # Quality Inspection Stock
    ]

    SNP_PLAN_FIELDS = [
        "PLAN_VERSION",  # Planning Version
        "MATNR",  # Material Number
        "LOCNO",  # Location Number
        "PLAN_DATE",  # Planning Date
        "DEMAND_QTY",  # Demand Quantity
        "SUPPLY_QTY",  # Supply Quantity
        "STOCK_QTY",  # Stock Quantity
        "SHORTAGE_QTY",  # Shortage Quantity
    ]

    # Config Builder APO fields

    # Transportation Lanes (/SAPAPO/TRLANE) - network edges
    TRANSPORTATION_LANE_FIELDS = [
        "LOCFR",  # Source Location
        "LOCTO",  # Destination Location
        "MATID",  # Material ID
        "TRLANE_ID",  # Lane ID
        "TRANSTIME",  # Transportation Time (days)
        "TRANSCOST",  # Transportation Cost
        "CAPACITY",  # Lane Capacity
        "TRANSMODE",  # Transportation Mode
        "VALID_FROM",  # Valid From Date
        "VALID_TO",  # Valid To Date
    ]

    # Product Data Structure (/SAPAPO/PDS) - alternative BOMs/routings
    PDS_FIELDS = [
        "PDSID",  # PDS ID
        "MATNR",  # Material Number
        "LOCNO",  # Location
        "PDSTYPE",  # PDS Type
        "PRIORITY",  # Priority
        "VALID_FROM",  # Valid From Date
        "VALID_TO",  # Valid To Date
        "COMP_MATNR",  # Component Material Number
        "COMP_QTY",  # Component Quantity
        "SETUP_TIME",  # Setup Time
        "PROC_TIME",  # Processing Time
    ]

    # SNP Basic Values (/SAPAPO/SNPBV) - historical demand/supply plan
    SNPBV_FIELDS = [
        "MATNR",  # Material Number
        "LOCNO",  # Location Number
        "PERIODID",  # Period ID
        "PERIODSTART",  # Period Start Date
        "DEMAND_QTY",  # Demand Quantity
        "SUPPLY_QTY",  # Supply Quantity
        "FORECAST_QTY",  # Forecast Quantity
        "STOCK_QTY",  # Stock Quantity
        "VERSION",  # Plan Version
    ]

    def __init__(self, config: APOConnectionConfig):
        """Initialize APO connector."""
        self.config = config
        self.connection: Optional[Connection] = None
        self._connected = False

        # Validate configuration
        if config.use_csv_mode:
            if not config.csv_directory:
                raise ValueError("csv_directory must be provided for CSV mode")
            self.csv_dir = Path(config.csv_directory)
            if not self.csv_dir.exists():
                raise ValueError(f"CSV directory does not exist: {config.csv_directory}")
            logger.info(f"APO connector initialized in CSV mode: {self.csv_dir}")
        else:
            if not PYRFC_AVAILABLE:
                raise ImportError("pyrfc required for RFC mode. Falling back to CSV mode.")
            if not all([config.ashost, config.sysnr, config.client, config.user, config.passwd]):
                raise ValueError("Complete RFC connection parameters required for RFC mode")
            logger.info("APO connector initialized in RFC mode")

    def connect(self) -> bool:
        """
        Establish connection (if RFC mode).

        Returns:
            bool: True if connection successful or CSV mode active
        """
        if self.config.use_csv_mode:
            logger.info("Using CSV mode - no connection needed")
            self._connected = True
            return True

        try:
            self.connection = Connection(
                ashost=self.config.ashost,
                sysnr=self.config.sysnr,
                client=self.config.client,
                user=self.config.user,
                passwd=self.config.passwd,
                lang=self.config.lang,
            )
            self._connected = True
            logger.info(f"Connected to APO: {self.config.ashost}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to APO: {e}")
            logger.info("Falling back to CSV mode if available")
            if self.config.csv_directory:
                self.config.use_csv_mode = True
                self._connected = True
                return True
            return False

    def disconnect(self):
        """Close RFC connection."""
        if self.connection:
            self.connection.close()
            self._connected = False
            logger.info("Disconnected from APO")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    def _read_csv_table(
        self,
        table_name: str,
        expected_fields: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Read APO data from CSV file.

        CSV file naming convention: {table_name}.csv
        Example: /SAPAPO/LOC.csv, APO_LOCATIONS.csv, etc.

        Args:
            table_name: APO table name
            expected_fields: Expected field names (for validation)

        Returns:
            DataFrame with CSV data
        """
        # Try multiple filename patterns
        filename_patterns = [
            f"{table_name}.csv",
            f"{table_name.replace('/', '_')}.csv",
            f"APO_{table_name.split('/')[-1]}.csv",
        ]

        csv_file = None
        for pattern in filename_patterns:
            potential_file = self.csv_dir / pattern
            if potential_file.exists():
                csv_file = potential_file
                break

        if not csv_file:
            logger.warning(
                f"CSV file not found for {table_name}. Tried: {filename_patterns}"
            )
            return pd.DataFrame(columns=expected_fields or [])

        try:
            # Read CSV with flexible encoding
            df = pd.read_csv(
                csv_file,
                encoding="utf-8",
                sep=",",
                dtype=str,  # Read all as string initially
                na_values=["", "NULL", "null"],
            )

            # Standardize column names (uppercase)
            df.columns = [col.upper().strip() for col in df.columns]

            # Validate expected fields
            if expected_fields:
                missing_fields = set(expected_fields) - set(df.columns)
                if missing_fields:
                    logger.warning(
                        f"Missing expected fields in {table_name}: {missing_fields}"
                    )

            logger.info(f"Read {len(df)} rows from {csv_file.name}")
            return df

        except Exception as e:
            logger.error(f"Error reading CSV {csv_file}: {e}")
            return pd.DataFrame(columns=expected_fields or [])

    def _execute_query_rfc(
        self,
        table_name: str,
        fields: List[str],
        where_clause: Optional[List[Dict[str, str]]] = None,
        max_rows: int = 10000
    ) -> pd.DataFrame:
        """
        Execute RFC_READ_TABLE for APO (fallback method).

        Note: APO tables may not be directly accessible via RFC_READ_TABLE
        due to liveCache architecture. Use CSV mode for reliability.
        """
        if not self._connected or not self.connection:
            raise RuntimeError("Not connected to APO via RFC")

        try:
            field_list = [{"FIELDNAME": field} for field in fields]

            options = []
            if where_clause:
                for condition in where_clause:
                    options.append({
                        "TEXT": f"{condition['FIELD']} {condition['OPTION']} {condition['LOW']}"
                    })

            result = self.connection.call(
                "RFC_READ_TABLE",
                QUERY_TABLE=table_name,
                DELIMITER="|",
                FIELDS=field_list,
                OPTIONS=options,
                ROWCOUNT=max_rows,
            )

            if not result.get("DATA"):
                logger.warning(f"No data returned from APO table {table_name}")
                return pd.DataFrame(columns=fields)

            rows = []
            for row_data in result["DATA"]:
                row_str = row_data["WA"]
                values = [v.strip() for v in row_str.split("|")]
                rows.append(values)

            df = pd.DataFrame(rows, columns=fields)
            logger.info(f"Retrieved {len(df)} rows from APO {table_name}")
            return df

        except Exception as e:
            logger.error(f"Error querying APO table {table_name}: {e}")
            return pd.DataFrame(columns=fields)

    def extract_locations(self, location_type: Optional[str] = None) -> pd.DataFrame:
        """
        Extract location master data from APO.

        Args:
            location_type: Filter by location type (optional)

        Returns:
            DataFrame with location data
        """
        logger.info("Extracting locations from APO")

        if self.config.use_csv_mode:
            locations = self._read_csv_table(
                "/SAPAPO/LOC",
                expected_fields=self.LOCATION_FIELDS
            )
        else:
            where_clause = []
            if location_type:
                where_clause.append({
                    "FIELD": "LOCTYPE",
                    "OPTION": "EQ",
                    "LOW": location_type
                })
            locations = self._execute_query_rfc(
                "/SAPAPO/LOC",
                self.LOCATION_FIELDS,
                where_clause if where_clause else None
            )

        # Apply filters if needed
        if location_type and "LOCTYPE" in locations.columns:
            locations = locations[locations["LOCTYPE"] == location_type]

        logger.info(f"Extracted {len(locations)} locations")
        return locations

    def extract_materials(self, material_type: Optional[str] = None) -> pd.DataFrame:
        """
        Extract material master data from APO.

        Args:
            material_type: Filter by material type (optional)

        Returns:
            DataFrame with material data
        """
        logger.info("Extracting materials from APO")

        if self.config.use_csv_mode:
            materials = self._read_csv_table(
                "/SAPAPO/MAT",
                expected_fields=self.MATERIAL_FIELDS
            )
        else:
            where_clause = []
            if material_type:
                where_clause.append({
                    "FIELD": "MATTYPE",
                    "OPTION": "EQ",
                    "LOW": material_type
                })
            materials = self._execute_query_rfc(
                "/SAPAPO/MAT",
                self.MATERIAL_FIELDS,
                where_clause if where_clause else None
            )

        if material_type and "MATTYPE" in materials.columns:
            materials = materials[materials["MATTYPE"] == material_type]

        logger.info(f"Extracted {len(materials)} materials")
        return materials

    def extract_material_locations(
        self,
        location: Optional[str] = None,
        material: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Extract material-location relationships from APO.

        Args:
            location: Filter by location (optional)
            material: Filter by material (optional)

        Returns:
            DataFrame with material-location data
        """
        logger.info("Extracting material-location data from APO")

        if self.config.use_csv_mode:
            mat_locs = self._read_csv_table(
                "/SAPAPO/MATLOC",
                expected_fields=self.MATERIAL_LOCATION_FIELDS
            )
        else:
            where_clause = []
            if location:
                where_clause.append({
                    "FIELD": "LOCNO",
                    "OPTION": "EQ",
                    "LOW": location
                })
            if material:
                where_clause.append({
                    "FIELD": "MATNR",
                    "OPTION": "EQ",
                    "LOW": material
                })
            mat_locs = self._execute_query_rfc(
                "/SAPAPO/MATLOC",
                self.MATERIAL_LOCATION_FIELDS,
                where_clause if where_clause else None
            )

        # Apply filters
        if location and "LOCNO" in mat_locs.columns:
            mat_locs = mat_locs[mat_locs["LOCNO"] == location]
        if material and "MATNR" in mat_locs.columns:
            mat_locs = mat_locs[mat_locs["MATNR"] == material]

        # Convert numeric fields
        numeric_fields = ["SAFETY_STOCK", "REORDER_POINT", "MAX_STOCK", "LEAD_TIME", "LOT_SIZE"]
        for field in numeric_fields:
            if field in mat_locs.columns:
                mat_locs[field] = pd.to_numeric(mat_locs[field], errors="coerce")

        logger.info(f"Extracted {len(mat_locs)} material-location records")
        return mat_locs

    def extract_orders(
        self,
        order_type: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> pd.DataFrame:
        """
        Extract order data from APO.

        Args:
            order_type: Filter by order type (PO, SO, TO, etc.)
            date_from: Start date filter
            date_to: End date filter

        Returns:
            DataFrame with order data
        """
        logger.info(f"Extracting orders from APO (type={order_type})")

        if self.config.use_csv_mode:
            orders = self._read_csv_table(
                "/SAPAPO/ORD",
                expected_fields=self.ORDER_FIELDS
            )
        else:
            where_clause = []
            if order_type:
                where_clause.append({
                    "FIELD": "ORDERTYPE",
                    "OPTION": "EQ",
                    "LOW": order_type
                })
            orders = self._execute_query_rfc(
                "/SAPAPO/ORD",
                self.ORDER_FIELDS,
                where_clause if where_clause else None
            )

        # Convert date fields
        date_fields = ["ORDERDATE", "DELIVERY_DATE"]
        for field in date_fields:
            if field in orders.columns:
                orders[field] = pd.to_datetime(orders[field], errors="coerce")

        # Apply date filters
        if date_from and "ORDERDATE" in orders.columns:
            orders = orders[orders["ORDERDATE"] >= pd.Timestamp(date_from)]
        if date_to and "ORDERDATE" in orders.columns:
            orders = orders[orders["ORDERDATE"] <= pd.Timestamp(date_to)]

        # Apply type filter
        if order_type and "ORDERTYPE" in orders.columns:
            orders = orders[orders["ORDERTYPE"] == order_type]

        # Convert numeric fields
        numeric_fields = ["QUANTITY", "OPEN_QTY"]
        for field in numeric_fields:
            if field in orders.columns:
                orders[field] = pd.to_numeric(orders[field], errors="coerce")

        logger.info(f"Extracted {len(orders)} orders")
        return orders

    def extract_stock(
        self,
        location: Optional[str] = None,
        material: Optional[str] = None,
        stock_date: Optional[date] = None
    ) -> pd.DataFrame:
        """
        Extract stock/inventory data from APO.

        Args:
            location: Filter by location
            material: Filter by material
            stock_date: Filter by stock date

        Returns:
            DataFrame with stock data
        """
        logger.info(f"Extracting stock from APO (loc={location})")

        if self.config.use_csv_mode:
            stock = self._read_csv_table(
                "/SAPAPO/STOCK",
                expected_fields=self.STOCK_FIELDS
            )
        else:
            where_clause = []
            if location:
                where_clause.append({
                    "FIELD": "LOCNO",
                    "OPTION": "EQ",
                    "LOW": location
                })
            if material:
                where_clause.append({
                    "FIELD": "MATNR",
                    "OPTION": "EQ",
                    "LOW": material
                })
            stock = self._execute_query_rfc(
                "/SAPAPO/STOCK",
                self.STOCK_FIELDS,
                where_clause if where_clause else None
            )

        # Convert date field
        if "STOCK_DATE" in stock.columns:
            stock["STOCK_DATE"] = pd.to_datetime(stock["STOCK_DATE"], errors="coerce")

        # Apply filters
        if location and "LOCNO" in stock.columns:
            stock = stock[stock["LOCNO"] == location]
        if material and "MATNR" in stock.columns:
            stock = stock[stock["MATNR"] == material]
        if stock_date and "STOCK_DATE" in stock.columns:
            stock = stock[stock["STOCK_DATE"] == pd.Timestamp(stock_date)]

        # Convert numeric fields
        qty_fields = ["AVAILABLE_QTY", "IN_TRANSIT_QTY", "BLOCKED_QTY", "QUALITY_QTY"]
        for field in qty_fields:
            if field in stock.columns:
                stock[field] = pd.to_numeric(stock[field], errors="coerce")

        logger.info(f"Extracted stock for {len(stock)} material-location combinations")
        return stock

    def extract_snp_plan(
        self,
        plan_version: str,
        location: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None
    ) -> pd.DataFrame:
        """
        Extract SNP planning data from APO.

        Args:
            plan_version: Planning version
            location: Filter by location
            date_from: Start date
            date_to: End date

        Returns:
            DataFrame with SNP plan data
        """
        logger.info(f"Extracting SNP plan {plan_version} from APO")

        if self.config.use_csv_mode:
            snp = self._read_csv_table(
                "/SAPAPO/SNP",
                expected_fields=self.SNP_PLAN_FIELDS
            )
        else:
            where_clause = [{
                "FIELD": "PLAN_VERSION",
                "OPTION": "EQ",
                "LOW": plan_version
            }]
            if location:
                where_clause.append({
                    "FIELD": "LOCNO",
                    "OPTION": "EQ",
                    "LOW": location
                })
            snp = self._execute_query_rfc(
                "/SAPAPO/SNP",
                self.SNP_PLAN_FIELDS,
                where_clause
            )

        # Convert date field
        if "PLAN_DATE" in snp.columns:
            snp["PLAN_DATE"] = pd.to_datetime(snp["PLAN_DATE"], errors="coerce")

        # Apply filters
        if "PLAN_VERSION" in snp.columns:
            snp = snp[snp["PLAN_VERSION"] == plan_version]
        if location and "LOCNO" in snp.columns:
            snp = snp[snp["LOCNO"] == location]
        if date_from and "PLAN_DATE" in snp.columns:
            snp = snp[snp["PLAN_DATE"] >= pd.Timestamp(date_from)]
        if date_to and "PLAN_DATE" in snp.columns:
            snp = snp[snp["PLAN_DATE"] <= pd.Timestamp(date_to)]

        # Convert numeric fields
        qty_fields = ["DEMAND_QTY", "SUPPLY_QTY", "STOCK_QTY", "SHORTAGE_QTY"]
        for field in qty_fields:
            if field in snp.columns:
                snp[field] = pd.to_numeric(snp[field], errors="coerce")

        logger.info(f"Extracted {len(snp)} SNP plan records")
        return snp

    # ==========================================================================
    # Config Builder Extraction Methods
    # ==========================================================================

    def extract_transportation_lanes(
        self,
        source_location: Optional[str] = None,
        dest_location: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Extract transportation lanes (/SAPAPO/TRLANE) — network edges.

        These are the most critical APO data for building a SupplyChainConfig
        as they define the physical material flow connections between sites.
        """
        logger.info("Extracting transportation lanes from APO")

        if self.config.use_csv_mode:
            lanes = self._read_csv_table(
                "/SAPAPO/TRLANE",
                expected_fields=self.TRANSPORTATION_LANE_FIELDS,
            )
        else:
            where_clause = []
            if source_location:
                where_clause.append({"FIELD": "LOCFR", "OPTION": "EQ", "LOW": source_location})
            if dest_location:
                where_clause.append({"FIELD": "LOCTO", "OPTION": "EQ", "LOW": dest_location})
            lanes = self._execute_query_rfc(
                "/SAPAPO/TRLANE",
                self.TRANSPORTATION_LANE_FIELDS,
                where_clause if where_clause else None,
            )

        # Apply filters
        if source_location and "LOCFR" in lanes.columns:
            lanes = lanes[lanes["LOCFR"] == source_location]
        if dest_location and "LOCTO" in lanes.columns:
            lanes = lanes[lanes["LOCTO"] == dest_location]

        # Convert numeric fields
        for field in ["TRANSTIME", "TRANSCOST", "CAPACITY"]:
            if field in lanes.columns:
                lanes[field] = pd.to_numeric(lanes[field], errors="coerce")

        logger.info(f"Extracted {len(lanes)} transportation lanes")
        return lanes

    def extract_product_data_structures(
        self,
        location: Optional[str] = None,
        material: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Extract APO Product Data Structures (/SAPAPO/PDS).

        PDS contains alternative BOM/routing definitions in APO, complementing
        S/4HANA STPO/PLKO data.
        """
        logger.info("Extracting product data structures from APO")

        if self.config.use_csv_mode:
            pds = self._read_csv_table(
                "/SAPAPO/PDS",
                expected_fields=self.PDS_FIELDS,
            )
        else:
            where_clause = []
            if location:
                where_clause.append({"FIELD": "LOCNO", "OPTION": "EQ", "LOW": location})
            if material:
                where_clause.append({"FIELD": "MATNR", "OPTION": "EQ", "LOW": material})
            pds = self._execute_query_rfc(
                "/SAPAPO/PDS",
                self.PDS_FIELDS,
                where_clause if where_clause else None,
            )

        if location and "LOCNO" in pds.columns:
            pds = pds[pds["LOCNO"] == location]
        if material and "MATNR" in pds.columns:
            pds = pds[pds["MATNR"] == material]

        for field in ["COMP_QTY", "SETUP_TIME", "PROC_TIME"]:
            if field in pds.columns:
                pds[field] = pd.to_numeric(pds[field], errors="coerce")

        logger.info(f"Extracted {len(pds)} PDS records")
        return pds

    def extract_snp_basic_values(
        self,
        location: Optional[str] = None,
        material: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        Extract SNP Basic Values (/SAPAPO/SNPBV) — historical demand/supply plan.

        Used as fallback forecast source when /SAPAPO/SNPFC is unavailable.
        """
        logger.info("Extracting SNP basic values from APO")

        if self.config.use_csv_mode:
            snpbv = self._read_csv_table(
                "/SAPAPO/SNPBV",
                expected_fields=self.SNPBV_FIELDS,
            )
        else:
            where_clause = []
            if location:
                where_clause.append({"FIELD": "LOCNO", "OPTION": "EQ", "LOW": location})
            if material:
                where_clause.append({"FIELD": "MATNR", "OPTION": "EQ", "LOW": material})
            snpbv = self._execute_query_rfc(
                "/SAPAPO/SNPBV",
                self.SNPBV_FIELDS,
                where_clause if where_clause else None,
            )

        if "PERIODSTART" in snpbv.columns:
            snpbv["PERIODSTART"] = pd.to_datetime(snpbv["PERIODSTART"], errors="coerce")

        if location and "LOCNO" in snpbv.columns:
            snpbv = snpbv[snpbv["LOCNO"] == location]
        if material and "MATNR" in snpbv.columns:
            snpbv = snpbv[snpbv["MATNR"] == material]
        if date_from and "PERIODSTART" in snpbv.columns:
            snpbv = snpbv[snpbv["PERIODSTART"] >= pd.Timestamp(date_from)]
        if date_to and "PERIODSTART" in snpbv.columns:
            snpbv = snpbv[snpbv["PERIODSTART"] <= pd.Timestamp(date_to)]

        for field in ["DEMAND_QTY", "SUPPLY_QTY", "FORECAST_QTY", "STOCK_QTY"]:
            if field in snpbv.columns:
                snpbv[field] = pd.to_numeric(snpbv[field], errors="coerce")

        logger.info(f"Extracted {len(snpbv)} SNP basic value records")
        return snpbv

    def get_available_csv_files(self) -> List[str]:
        """
        List available CSV files in the configured directory.

        Returns:
            List of CSV filenames
        """
        if not self.config.use_csv_mode:
            return []

        csv_files = list(self.csv_dir.glob("*.csv"))
        return [f.name for f in csv_files]
