"""
CSV Data Loader for SAP Integration.

Handles loading SAP data from CSV extracts when direct RFC connection
is not available or preferred.

Supports:
- S/4HANA table extracts
- APO liveCache extracts
- Flexible CSV formats
- Data validation
- Batch processing
"""

import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
import pandas as pd
import glob

logger = logging.getLogger(__name__)


class CSVDataLoader:
    """
    Load SAP data from CSV files.

    CSV Naming Conventions Supported:
    1. Standard: {TABLE_NAME}.csv (e.g., MARA.csv, EKKO.csv)
    2. Prefixed: SAP_{TABLE_NAME}.csv (e.g., SAP_MARA.csv)
    3. Dated: {TABLE_NAME}_YYYYMMDD.csv (e.g., MARA_20260116.csv)
    4. APO: APO_{TABLE_NAME}.csv or {/SAPAPO/TABLE}.csv
    """

    def __init__(self, csv_directory: str):
        """
        Initialize CSV loader.

        Args:
            csv_directory: Path to directory containing CSV files
        """
        self.csv_dir = Path(csv_directory)
        if not self.csv_dir.exists():
            raise ValueError(f"CSV directory does not exist: {csv_directory}")

        logger.info(f"CSV loader initialized: {self.csv_dir}")

    def list_available_tables(self) -> List[str]:
        """
        List all available CSV files/tables.

        Returns:
            List of table names (without .csv extension)
        """
        csv_files = list(self.csv_dir.glob("*.csv"))
        table_names = []

        for csv_file in csv_files:
            # Extract table name from various naming conventions
            name = csv_file.stem

            # Remove common prefixes
            if name.startswith("SAP_"):
                name = name[4:]
            elif name.startswith("APO_"):
                name = name[4:]

            # Remove date suffixes (YYYYMMDD pattern)
            if "_" in name:
                parts = name.split("_")
                if parts[-1].isdigit() and len(parts[-1]) == 8:
                    name = "_".join(parts[:-1])

            table_names.append(name)

        return sorted(set(table_names))

    def find_csv_file(self, table_name: str) -> Optional[Path]:
        """
        Find CSV file for given table name.

        Tries multiple naming patterns:
        1. {table_name}.csv
        2. SAP_{table_name}.csv
        3. APO_{table_name}.csv
        4. {table_name}_*.csv (with date suffix)

        Args:
            table_name: SAP table name

        Returns:
            Path to CSV file or None if not found
        """
        patterns = [
            f"{table_name}.csv",
            f"SAP_{table_name}.csv",
            f"APO_{table_name}.csv",
            f"{table_name}_*.csv",
            f"SAP_{table_name}_*.csv",
        ]

        for pattern in patterns:
            matches = list(self.csv_dir.glob(pattern))
            if matches:
                # If multiple matches (e.g., dated files), return most recent
                if len(matches) > 1:
                    matches.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                return matches[0]

        return None

    def load_table(
        self,
        table_name: str,
        expected_fields: Optional[List[str]] = None,
        encoding: str = "utf-8",
        delimiter: str = ",",
        skiprows: int = 0,
        nrows: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Load SAP table from CSV file.

        Args:
            table_name: SAP table name
            expected_fields: Expected column names (for validation)
            encoding: File encoding (utf-8, latin1, cp1252)
            delimiter: CSV delimiter (, or ; or |)
            skiprows: Number of rows to skip at start
            nrows: Maximum rows to read (None = all)

        Returns:
            DataFrame with table data
        """
        csv_file = self.find_csv_file(table_name)

        if not csv_file:
            logger.warning(f"CSV file not found for table: {table_name}")
            return pd.DataFrame(columns=expected_fields or [])

        logger.info(f"Loading {table_name} from {csv_file.name}")

        try:
            # Try to read with specified encoding
            df = self._read_csv_with_fallback(
                csv_file,
                encoding=encoding,
                delimiter=delimiter,
                skiprows=skiprows,
                nrows=nrows
            )

            # Standardize column names
            df.columns = [col.strip().upper() for col in df.columns]

            # Validate expected fields
            if expected_fields:
                missing = set(expected_fields) - set(df.columns)
                if missing:
                    logger.warning(
                        f"Missing expected fields in {table_name}: {missing}"
                    )

            logger.info(f"Loaded {len(df)} rows from {table_name}")
            return df

        except Exception as e:
            logger.error(f"Error loading {table_name}: {e}")
            return pd.DataFrame(columns=expected_fields or [])

    def _read_csv_with_fallback(
        self,
        file_path: Path,
        encoding: str,
        delimiter: str,
        skiprows: int,
        nrows: Optional[int]
    ) -> pd.DataFrame:
        """
        Read CSV with encoding/delimiter fallback.

        Tries multiple encodings and delimiters to handle various export formats.
        """
        encodings = [encoding, "utf-8", "latin1", "cp1252", "iso-8859-1"]
        delimiters = [delimiter, ",", ";", "|", "\t"]

        for enc in encodings:
            for delim in delimiters:
                try:
                    df = pd.read_csv(
                        file_path,
                        encoding=enc,
                        sep=delim,
                        dtype=str,  # Read all as strings initially
                        na_values=["", "NULL", "null", "NA"],
                        keep_default_na=True,
                        skiprows=skiprows,
                        nrows=nrows,
                        low_memory=False
                    )

                    # Check if read succeeded (has columns and rows)
                    if len(df.columns) > 1 and len(df) > 0:
                        logger.debug(f"Successfully read with encoding={enc}, delimiter={delim}")
                        return df

                except Exception:
                    continue

        # If all fail, try default pandas read
        return pd.read_csv(
            file_path,
            dtype=str,
            na_values=["", "NULL", "null"],
            low_memory=False
        )

    def load_materials(
        self,
        with_plant_data: bool = False
    ) -> pd.DataFrame:
        """
        Load material master data.

        Args:
            with_plant_data: If True, join with plant-specific data (MARC)

        Returns:
            DataFrame with material data
        """
        logger.info("Loading material master data")

        # Load MARA (general material data)
        mara = self.load_table("MARA")

        if with_plant_data:
            # Load MARC (plant-specific data)
            marc = self.load_table("MARC")

            if not mara.empty and not marc.empty:
                # Join on material number
                materials = mara.merge(marc, on="MATNR", how="left", suffixes=("", "_PLANT"))
            else:
                materials = mara
        else:
            materials = mara

        return materials

    def load_purchase_orders(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Load purchase order data (headers and items).

        Returns:
            Tuple of (headers DataFrame, items DataFrame)
        """
        logger.info("Loading purchase orders")

        headers = self.load_table("EKKO")
        items = self.load_table("EKPO")

        return headers, items

    def load_sales_orders(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Load sales order data (headers and items).

        Returns:
            Tuple of (headers DataFrame, items DataFrame)
        """
        logger.info("Loading sales orders")

        headers = self.load_table("VBAK")
        items = self.load_table("VBAP")

        return headers, items

    def load_deliveries(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Load delivery data (headers and items).

        Returns:
            Tuple of (headers DataFrame, items DataFrame)
        """
        logger.info("Loading deliveries")

        headers = self.load_table("LIKP")
        items = self.load_table("LIPS")

        return headers, items

    def load_inventory(self) -> pd.DataFrame:
        """
        Load inventory data (MARD - material storage location).

        Returns:
            DataFrame with inventory data
        """
        logger.info("Loading inventory")

        return self.load_table("MARD")

    def load_plants(self) -> pd.DataFrame:
        """
        Load plant master data.

        Returns:
            DataFrame with plant data
        """
        logger.info("Loading plants")

        return self.load_table("T001W")

    def load_apo_locations(self) -> pd.DataFrame:
        """
        Load APO location data.

        Returns:
            DataFrame with location data
        """
        logger.info("Loading APO locations")

        # Try multiple naming patterns for APO locations
        for table_name in ["/SAPAPO/LOC", "SAPAPO_LOC", "APO_LOC", "APO_LOCATIONS"]:
            df = self.load_table(table_name)
            if not df.empty:
                return df

        logger.warning("APO location data not found")
        return pd.DataFrame()

    def load_apo_materials(self) -> pd.DataFrame:
        """
        Load APO material data.

        Returns:
            DataFrame with material data
        """
        logger.info("Loading APO materials")

        for table_name in ["/SAPAPO/MAT", "SAPAPO_MAT", "APO_MAT", "APO_MATERIALS"]:
            df = self.load_table(table_name)
            if not df.empty:
                return df

        logger.warning("APO material data not found")
        return pd.DataFrame()

    def load_apo_stock(self) -> pd.DataFrame:
        """
        Load APO stock data.

        Returns:
            DataFrame with stock data
        """
        logger.info("Loading APO stock")

        for table_name in ["/SAPAPO/STOCK", "SAPAPO_STOCK", "APO_STOCK"]:
            df = self.load_table(table_name)
            if not df.empty:
                return df

        logger.warning("APO stock data not found")
        return pd.DataFrame()

    def load_apo_orders(self) -> pd.DataFrame:
        """
        Load APO order data.

        Returns:
            DataFrame with order data
        """
        logger.info("Loading APO orders")

        for table_name in ["/SAPAPO/ORD", "SAPAPO_ORD", "APO_ORD", "APO_ORDERS"]:
            df = self.load_table(table_name)
            if not df.empty:
                return df

        logger.warning("APO order data not found")
        return pd.DataFrame()

    def load_apo_snp_plan(self, plan_version: Optional[str] = None) -> pd.DataFrame:
        """
        Load APO SNP planning data.

        Args:
            plan_version: Filter by plan version (optional)

        Returns:
            DataFrame with SNP plan data
        """
        logger.info(f"Loading APO SNP plan (version={plan_version})")

        for table_name in ["/SAPAPO/SNP", "SAPAPO_SNP", "APO_SNP", "APO_SNP_PLAN"]:
            df = self.load_table(table_name)
            if not df.empty:
                # Filter by plan version if specified
                if plan_version and "PLAN_VERSION" in df.columns:
                    df = df[df["PLAN_VERSION"] == plan_version]
                return df

        logger.warning("APO SNP plan data not found")
        return pd.DataFrame()

    def get_file_info(self, table_name: str) -> Optional[Dict[str, any]]:
        """
        Get information about CSV file for table.

        Args:
            table_name: SAP table name

        Returns:
            Dictionary with file info (path, size, modified date, row count)
        """
        csv_file = self.find_csv_file(table_name)

        if not csv_file:
            return None

        stat = csv_file.stat()

        # Quick row count (read just to count)
        try:
            with open(csv_file, "r", encoding="utf-8") as f:
                row_count = sum(1 for _ in f) - 1  # Subtract header
        except Exception:
            row_count = None

        return {
            "file_path": str(csv_file),
            "file_name": csv_file.name,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified_date": datetime.fromtimestamp(stat.st_mtime),
            "row_count": row_count,
        }

    def validate_data_freshness(
        self,
        table_name: str,
        max_age_hours: int = 24
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if CSV data is fresh enough for use.

        Args:
            table_name: SAP table name
            max_age_hours: Maximum acceptable age in hours

        Returns:
            Tuple of (is_fresh: bool, message: str)
        """
        info = self.get_file_info(table_name)

        if not info:
            return False, f"File not found for {table_name}"

        age_hours = (datetime.now() - info["modified_date"]).total_seconds() / 3600

        if age_hours > max_age_hours:
            return False, f"Data is {age_hours:.1f} hours old (max: {max_age_hours})"

        return True, f"Data is fresh ({age_hours:.1f} hours old)"
