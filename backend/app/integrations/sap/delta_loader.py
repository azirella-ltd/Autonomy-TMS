"""
Delta/Net Change Loader for SAP Integration.

Implements incremental loading to minimize data transfer and processing:
- Tracks last extraction timestamp
- Identifies changed/new records only
- Handles deletions (if supported)
- Maintains change history
- Optimizes daily batch loads

Supports both S/4HANA and APO systems.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
import json
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class DeltaLoadConfig:
    """Configuration for delta loading."""
    table_name: str
    key_fields: List[str]  # Fields that uniquely identify a record
    change_date_field: Optional[str] = None  # Field containing last change date
    change_time_field: Optional[str] = None  # Field containing last change time
    track_deletes: bool = False
    lookback_days: int = 1  # How many days to look back for changes


@dataclass
class DeltaLoadResult:
    """Result of delta load operation."""
    table_name: str
    total_records: int
    new_records: int
    changed_records: int
    deleted_records: int
    unchanged_records: int
    load_timestamp: datetime
    previous_timestamp: Optional[datetime]
    execution_time_seconds: float


class DeltaLoadTracker:
    """
    Tracks delta load state across executions.

    Persists to JSON file for resumability.
    """

    def __init__(self, state_file: str = "delta_load_state.json"):
        """Initialize tracker with state file."""
        self.state_file = Path(state_file)
        self.state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        """Load state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading state file: {e}")
                return {}
        return {}

    def _save_state(self):
        """Save state to file."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving state file: {e}")

    def get_last_load_timestamp(self, table_name: str) -> Optional[datetime]:
        """Get timestamp of last successful load for table."""
        table_state = self.state.get(table_name, {})
        last_ts = table_state.get("last_load_timestamp")

        if last_ts:
            return datetime.fromisoformat(last_ts)
        return None

    def get_last_record_keys(self, table_name: str) -> Set[str]:
        """Get set of record keys from last load."""
        table_state = self.state.get(table_name, {})
        return set(table_state.get("record_keys", []))

    def update_load_state(
        self,
        table_name: str,
        load_timestamp: datetime,
        record_keys: Set[str],
        result: DeltaLoadResult
    ):
        """Update state after successful load."""
        self.state[table_name] = {
            "last_load_timestamp": load_timestamp.isoformat(),
            "record_keys": list(record_keys),
            "last_result": {
                "total_records": result.total_records,
                "new_records": result.new_records,
                "changed_records": result.changed_records,
                "deleted_records": result.deleted_records,
                "execution_time": result.execution_time_seconds
            }
        }
        self._save_state()

    def get_table_history(self, table_name: str) -> Dict[str, Any]:
        """Get load history for table."""
        return self.state.get(table_name, {})


class SAPDeltaLoader:
    """
    Performs incremental/delta loads from SAP systems.

    Intelligently extracts only changed records to minimize load times.
    """

    def __init__(
        self,
        tracker_state_file: str = "delta_load_state.json",
        hash_cache_file: Optional[str] = None
    ):
        """Initialize delta loader."""
        self.tracker = DeltaLoadTracker(tracker_state_file)
        self.hash_cache_file = Path(hash_cache_file) if hash_cache_file else None
        self._hash_cache: Dict[str, str] = self._load_hash_cache()

    def _load_hash_cache(self) -> Dict[str, str]:
        """Load record hash cache for change detection."""
        if self.hash_cache_file and self.hash_cache_file.exists():
            try:
                with open(self.hash_cache_file, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_hash_cache(self):
        """Save record hash cache."""
        if self.hash_cache_file:
            try:
                self.hash_cache_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.hash_cache_file, "w") as f:
                    json.dump(self._hash_cache, f)
            except Exception as e:
                logger.error(f"Error saving hash cache: {e}")

    def _compute_record_hash(self, record: pd.Series) -> str:
        """Compute hash of record for change detection."""
        # Convert record to string and hash
        record_str = record.to_json(default_handler=str)
        return hashlib.md5(record_str.encode()).hexdigest()

    def load_delta(
        self,
        current_data: pd.DataFrame,
        config: DeltaLoadConfig
    ) -> Tuple[pd.DataFrame, DeltaLoadResult]:
        """
        Extract delta (changed records only) from current data.

        Args:
            current_data: Full dataset from current extraction
            config: Delta load configuration

        Returns:
            Tuple of (delta DataFrame, load result)
        """
        start_time = datetime.now()
        logger.info(f"Computing delta for {config.table_name}")

        # Get previous load state
        last_timestamp = self.tracker.get_last_load_timestamp(config.table_name)
        previous_keys = self.tracker.get_last_record_keys(config.table_name)

        logger.info(f"Last load: {last_timestamp}")
        logger.info(f"Previous record count: {len(previous_keys)}")

        # Generate keys for current records
        if not config.key_fields:
            raise ValueError(f"key_fields required for delta load: {config.table_name}")

        current_data["_record_key"] = current_data[config.key_fields].apply(
            lambda row: "|".join(row.astype(str)), axis=1
        )

        current_keys = set(current_data["_record_key"])

        # Identify changes
        new_keys = current_keys - previous_keys
        deleted_keys = previous_keys - current_keys if config.track_deletes else set()
        potential_changes = current_keys & previous_keys

        logger.info(f"New records: {len(new_keys)}")
        logger.info(f"Potential changes: {len(potential_changes)}")
        logger.info(f"Deleted records: {len(deleted_keys)}")

        # Filter by change date if available
        if config.change_date_field and last_timestamp:
            cutoff_date = (last_timestamp - timedelta(days=config.lookback_days)).date()

            if config.change_date_field in current_data.columns:
                # Convert to date
                current_data["_change_date"] = pd.to_datetime(
                    current_data[config.change_date_field],
                    errors="coerce"
                ).dt.date

                # Filter to changed records only
                changed_by_date = current_data[
                    current_data["_change_date"] >= cutoff_date
                ]

                logger.info(
                    f"Records changed after {cutoff_date}: {len(changed_by_date)}"
                )

                # Combine with new records
                delta_df = pd.concat([
                    current_data[current_data["_record_key"].isin(new_keys)],
                    changed_by_date
                ]).drop_duplicates(subset=["_record_key"])

            else:
                logger.warning(
                    f"Change date field {config.change_date_field} not found. "
                    f"Using all potential changes."
                )
                delta_df = current_data[
                    current_data["_record_key"].isin(new_keys | potential_changes)
                ]
        else:
            # No date filtering - use hash-based change detection
            changed_keys = self._detect_changes_by_hash(
                current_data,
                potential_changes,
                config.table_name
            )

            delta_df = current_data[
                current_data["_record_key"].isin(new_keys | changed_keys)
            ]

        # Remove helper columns
        delta_df = delta_df.drop(columns=["_record_key"], errors="ignore")
        if "_change_date" in delta_df.columns:
            delta_df = delta_df.drop(columns=["_change_date"])

        # Create result
        load_timestamp = datetime.now()
        execution_time = (load_timestamp - start_time).total_seconds()

        result = DeltaLoadResult(
            table_name=config.table_name,
            total_records=len(current_data),
            new_records=len(new_keys),
            changed_records=len(delta_df) - len(new_keys),
            deleted_records=len(deleted_keys),
            unchanged_records=len(current_keys) - len(delta_df),
            load_timestamp=load_timestamp,
            previous_timestamp=last_timestamp,
            execution_time_seconds=execution_time
        )

        # Update tracker state
        self.tracker.update_load_state(
            table_name=config.table_name,
            load_timestamp=load_timestamp,
            record_keys=current_keys,
            result=result
        )

        logger.info(f"Delta load complete: {len(delta_df)} records in delta")
        logger.info(f"Execution time: {execution_time:.2f}s")

        return delta_df, result

    def _detect_changes_by_hash(
        self,
        current_data: pd.DataFrame,
        potential_change_keys: Set[str],
        table_name: str
    ) -> Set[str]:
        """Detect changed records by comparing content hashes."""
        logger.info("Detecting changes using hash comparison")

        changed_keys = set()

        for key in potential_change_keys:
            record = current_data[current_data["_record_key"] == key].iloc[0]
            current_hash = self._compute_record_hash(record)

            # Check against cached hash
            cache_key = f"{table_name}:{key}"
            previous_hash = self._hash_cache.get(cache_key)

            if previous_hash != current_hash:
                changed_keys.add(key)

            # Update cache
            self._hash_cache[cache_key] = current_hash

        # Save updated cache
        self._save_hash_cache()

        logger.info(f"Detected {len(changed_keys)} changed records")
        return changed_keys

    def get_deleted_records(
        self,
        config: DeltaLoadConfig
    ) -> List[str]:
        """
        Get list of record keys that were deleted since last load.

        Returns:
            List of deleted record keys
        """
        previous_keys = self.tracker.get_last_record_keys(config.table_name)

        if not previous_keys:
            return []

        # This would need current extraction to compare
        # Return empty for now - implement in full context
        return []

    def generate_delta_report(self, result: DeltaLoadResult) -> str:
        """Generate human-readable delta load report."""
        report = []
        report.append("=" * 60)
        report.append(f"Delta Load Report: {result.table_name}")
        report.append("=" * 60)
        report.append("")

        report.append("Load Summary:")
        report.append(f"  Load Timestamp: {result.load_timestamp}")
        report.append(f"  Previous Load: {result.previous_timestamp or 'N/A (Initial Load)'}")
        report.append(f"  Execution Time: {result.execution_time_seconds:.2f}s")
        report.append("")

        report.append("Record Counts:")
        report.append(f"  Total Records (Current): {result.total_records}")
        report.append(f"  New Records: {result.new_records}")
        report.append(f"  Changed Records: {result.changed_records}")
        report.append(f"  Deleted Records: {result.deleted_records}")
        report.append(f"  Unchanged Records: {result.unchanged_records}")
        report.append("")

        delta_count = result.new_records + result.changed_records
        if result.total_records > 0:
            delta_pct = (delta_count / result.total_records) * 100
            report.append(f"Delta Efficiency:")
            report.append(f"  Delta Records: {delta_count} ({delta_pct:.1f}% of total)")
            report.append(f"  Reduction: {result.unchanged_records} records skipped")

        report.append("\n" + "=" * 60)
        return "\n".join(report)


class SAPDeltaExtractor:
    """
    High-level delta extraction for SAP systems.

    Combines connectors with delta logic for efficient incremental loads.
    """

    # Standard delta configurations for SAP tables
    STANDARD_CONFIGS = {
        "MARA": DeltaLoadConfig(
            table_name="MARA",
            key_fields=["MATNR"],
            change_date_field="AEDAT",
            lookback_days=2
        ),
        "MARC": DeltaLoadConfig(
            table_name="MARC",
            key_fields=["MATNR", "WERKS"],
            change_date_field="AEDAT",
            lookback_days=2
        ),
        "MARD": DeltaLoadConfig(
            table_name="MARD",
            key_fields=["MATNR", "WERKS", "LGORT"],
            lookback_days=1
        ),
        "EKKO": DeltaLoadConfig(
            table_name="EKKO",
            key_fields=["EBELN"],
            change_date_field="AEDAT",
            lookback_days=7
        ),
        "EKPO": DeltaLoadConfig(
            table_name="EKPO",
            key_fields=["EBELN", "EBELP"],
            change_date_field="AEDAT",
            lookback_days=7
        ),
        "VBAK": DeltaLoadConfig(
            table_name="VBAK",
            key_fields=["VBELN"],
            change_date_field="ERDAT",
            lookback_days=30
        ),
        "VBAP": DeltaLoadConfig(
            table_name="VBAP",
            key_fields=["VBELN", "POSNR"],
            lookback_days=30
        ),
        "LIKP": DeltaLoadConfig(
            table_name="LIKP",
            key_fields=["VBELN"],
            change_date_field="AEDAT",
            lookback_days=14
        ),
        "LIPS": DeltaLoadConfig(
            table_name="LIPS",
            key_fields=["VBELN", "POSNR"],
            lookback_days=14
        ),
    }

    def __init__(self, state_directory: str = "./delta_state"):
        """Initialize delta extractor."""
        self.state_dir = Path(state_directory)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.delta_loader = SAPDeltaLoader(
            tracker_state_file=str(self.state_dir / "delta_load_state.json"),
            hash_cache_file=str(self.state_dir / "hash_cache.json")
        )

    def extract_delta(
        self,
        full_data: pd.DataFrame,
        table_name: str,
        custom_config: Optional[DeltaLoadConfig] = None
    ) -> Tuple[pd.DataFrame, DeltaLoadResult]:
        """
        Extract delta from full dataset.

        Args:
            full_data: Complete current dataset
            table_name: SAP table name
            custom_config: Custom delta config (uses standard if not provided)

        Returns:
            Tuple of (delta DataFrame, load result)
        """
        # Get configuration
        if custom_config:
            config = custom_config
        elif table_name in self.STANDARD_CONFIGS:
            config = self.STANDARD_CONFIGS[table_name]
        else:
            logger.warning(
                f"No standard config for {table_name}. Using basic config."
            )
            # Try to infer key fields
            key_fields = self._infer_key_fields(full_data, table_name)
            config = DeltaLoadConfig(
                table_name=table_name,
                key_fields=key_fields,
                lookback_days=1
            )

        # Perform delta load
        return self.delta_loader.load_delta(full_data, config)

    def _infer_key_fields(
        self,
        df: pd.DataFrame,
        table_name: str
    ) -> List[str]:
        """Infer key fields from DataFrame structure."""
        # Common key field patterns
        key_patterns = [
            "MATNR",  # Material
            "EBELN",  # Purchase Order
            "VBELN",  # Sales Order / Delivery
            "LIFNR",  # Vendor
            "KUNNR",  # Customer
            "WERKS",  # Plant
            "EBELP",  # PO Item
            "POSNR",  # SO/Delivery Item
        ]

        inferred_keys = []
        for col in df.columns:
            if col in key_patterns:
                inferred_keys.append(col)

        if not inferred_keys:
            # Use first column as fallback
            inferred_keys = [df.columns[0]]
            logger.warning(
                f"Could not infer keys for {table_name}. "
                f"Using first column: {inferred_keys[0]}"
            )

        logger.info(f"Inferred key fields for {table_name}: {inferred_keys}")
        return inferred_keys

    def get_load_history(self, table_name: str) -> Dict[str, Any]:
        """Get load history for specific table."""
        return self.delta_loader.tracker.get_table_history(table_name)

    def get_all_load_history(self) -> Dict[str, Dict[str, Any]]:
        """Get load history for all tables."""
        return self.delta_loader.tracker.state

    def reset_delta_state(self, table_name: Optional[str] = None):
        """
        Reset delta state (force full load next time).

        Args:
            table_name: Table to reset (None = reset all)
        """
        if table_name:
            if table_name in self.delta_loader.tracker.state:
                del self.delta_loader.tracker.state[table_name]
                self.delta_loader.tracker._save_state()
                logger.info(f"Reset delta state for {table_name}")
        else:
            self.delta_loader.tracker.state = {}
            self.delta_loader.tracker._save_state()
            logger.info("Reset all delta state")
