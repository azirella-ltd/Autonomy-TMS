"""
Intelligent SAP Data Loader with AI Assistance and Delta Loading.

Combines:
- Schema validation with Claude AI
- Delta/incremental loading
- Z-field interpretation
- Automatic data quality fixes
- Missing field handling

Provides unified interface for both initial and daily loads.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
import pandas as pd

from .schema_validator import (
    SAPSchemaValidator,
    SchemaAnalysis,
    ValidationIssue,
    ClaudeSchemaAssistant
)
from .delta_loader import (
    SAPDeltaLoader,
    SAPDeltaExtractor,
    DeltaLoadConfig,
    DeltaLoadResult
)
from .s4hana_connector import S4HANAConnector, S4HANAConnectionConfig
from .apo_connector import APOConnector, APOConnectionConfig
from .csv_loader import CSVDataLoader
from .data_mapper import SupplyChainMapper

logger = logging.getLogger(__name__)


@dataclass
class LoadConfig:
    """Configuration for intelligent load."""
    mode: str  # "initial" or "daily"
    connection_type: str  # "rfc" or "csv"
    use_claude_ai: bool = True
    auto_fix_issues: bool = True
    enable_delta: bool = True  # Only for daily loads
    save_validation_report: bool = True
    report_directory: Optional[str] = "./reports"


@dataclass
class LoadResult:
    """Result of intelligent load operation."""
    table_name: str
    load_mode: str  # "initial" or "delta"
    records_loaded: int
    records_fixed: int
    validation_issues: int
    z_fields_found: int
    delta_result: Optional[DeltaLoadResult] = None
    validation_analysis: Optional[SchemaAnalysis] = None
    execution_time_seconds: float = 0.0
    claude_used: bool = False
    auto_fixes_applied: List[str] = None


class IntelligentSAPLoader:
    """
    Intelligent loader with AI assistance for SAP data.

    Features:
    - Automatic schema validation
    - Claude AI for Z-fields and missing data
    - Delta loading for daily updates
    - Auto-fixing of common issues
    - Comprehensive reporting
    """

    # Standard expected schemas (simplified - extend as needed)
    EXPECTED_SCHEMAS = {
        "MARA": {
            "MATNR": str,
            "MAKTX": str,
            "MTART": str,
            "MEINS": str,
            "MATKL": str,
        },
        "MARC": {
            "MATNR": str,
            "WERKS": str,
            "DISPO": str,
            "EISBE": float,
            "PLIFZ": int,
        },
        "MARD": {
            "MATNR": str,
            "WERKS": str,
            "LGORT": str,
            "LABST": float,
        },
        "EKKO": {
            "EBELN": str,
            "LIFNR": str,
            "BEDAT": datetime,
            "EKORG": str,
        },
        "EKPO": {
            "EBELN": str,
            "EBELP": str,
            "MATNR": str,
            "MENGE": float,
        },
        "VBAK": {
            "VBELN": str,
            "KUNNR": str,
            "ERDAT": datetime,
            "VKORG": str,
        },
        "VBAP": {
            "VBELN": str,
            "POSNR": str,
            "MATNR": str,
            "KWMENG": float,
        },
    }

    # Required fields for core functionality
    REQUIRED_FIELDS = {
        "MARA": {"MATNR", "MEINS"},
        "MARC": {"MATNR", "WERKS"},
        "MARD": {"MATNR", "WERKS", "LGORT"},
        "EKKO": {"EBELN"},
        "EKPO": {"EBELN", "EBELP", "MATNR"},
        "VBAK": {"VBELN"},
        "VBAP": {"VBELN", "POSNR", "MATNR"},
    }

    def __init__(
        self,
        config: LoadConfig,
        claude_api_key: Optional[str] = None,
        delta_state_dir: Optional[str] = "./delta_state"
    ):
        """Initialize intelligent loader."""
        self.config = config
        self.validator = SAPSchemaValidator(claude_api_key) if config.use_claude_ai else None
        self.delta_extractor = SAPDeltaExtractor(delta_state_dir) if config.enable_delta else None
        self.mapper = SupplyChainMapper()

        if config.report_directory:
            self.report_dir = Path(config.report_directory)
            self.report_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Intelligent loader initialized (mode={config.mode})")

    def load_table(
        self,
        table_name: str,
        data_source: Any,  # Connector or DataFrame
        skip_validation: bool = False
    ) -> Tuple[pd.DataFrame, LoadResult]:
        """
        Load SAP table with intelligent processing.

        Args:
            table_name: SAP table name
            data_source: S4HANAConnector, APOConnector, CSVDataLoader, or DataFrame
            skip_validation: Skip validation (for performance)

        Returns:
            Tuple of (loaded DataFrame, load result)
        """
        start_time = datetime.now()
        logger.info(f"Loading {table_name} (mode={self.config.mode})")

        # Step 1: Extract data
        if isinstance(data_source, pd.DataFrame):
            df_full = data_source
        else:
            df_full = self._extract_data(table_name, data_source)

        if df_full.empty:
            logger.warning(f"No data extracted for {table_name}")
            return df_full, self._create_empty_result(table_name, start_time)

        logger.info(f"Extracted {len(df_full)} records for {table_name}")

        # Step 2: Schema validation (with Claude AI)
        validation_analysis = None
        if not skip_validation and self.validator:
            validation_analysis = self._validate_schema(table_name, df_full)

            # Save validation report
            if self.config.save_validation_report:
                self._save_validation_report(validation_analysis)

        # Step 3: Auto-fix issues using Claude recommendations
        df_fixed = df_full
        applied_fixes = []

        if self.config.auto_fix_issues and validation_analysis:
            df_fixed, applied_fixes = self._apply_auto_fixes(
                df_full,
                validation_analysis
            )
            logger.info(f"Applied {len(applied_fixes)} auto-fixes")

        # Step 4: Delta loading (for daily mode)
        delta_result = None
        df_delta = df_fixed

        if self.config.mode == "daily" and self.config.enable_delta and self.delta_extractor:
            df_delta, delta_result = self._apply_delta_loading(
                table_name,
                df_fixed
            )
            logger.info(f"Delta: {len(df_delta)} records (from {len(df_fixed)} total)")

        # Step 5: Create result
        execution_time = (datetime.now() - start_time).total_seconds()

        result = LoadResult(
            table_name=table_name,
            load_mode="delta" if delta_result else "full",
            records_loaded=len(df_delta),
            records_fixed=len(applied_fixes),
            validation_issues=len(validation_analysis.issues) if validation_analysis else 0,
            z_fields_found=len(validation_analysis.z_fields) if validation_analysis else 0,
            delta_result=delta_result,
            validation_analysis=validation_analysis,
            execution_time_seconds=execution_time,
            claude_used=self.config.use_claude_ai and validation_analysis is not None,
            auto_fixes_applied=applied_fixes
        )

        logger.info(f"Load complete for {table_name}: {result.records_loaded} records")
        return df_delta, result

    def _extract_data(
        self,
        table_name: str,
        data_source: Any
    ) -> pd.DataFrame:
        """Extract data from various source types."""
        if isinstance(data_source, S4HANAConnector):
            # Use appropriate extraction method based on table
            if table_name == "MARA":
                return data_source.extract_materials()
            elif table_name == "EKKO":
                headers, _ = data_source.extract_purchase_orders()
                return headers
            # Add more table-specific extractions...
            else:
                # Generic extraction
                return data_source._execute_query(
                    table_name=table_name,
                    fields=list(self.EXPECTED_SCHEMAS.get(table_name, {}).keys()),
                    max_rows=100000
                )

        elif isinstance(data_source, APOConnector):
            if table_name == "/SAPAPO/LOC":
                return data_source.extract_locations()
            elif table_name == "/SAPAPO/MAT":
                return data_source.extract_materials()
            # Add more APO tables...
            else:
                return data_source._read_csv_table(table_name)

        elif isinstance(data_source, CSVDataLoader):
            return data_source.load_table(table_name)

        else:
            raise ValueError(f"Unsupported data source type: {type(data_source)}")

    def _validate_schema(
        self,
        table_name: str,
        df: pd.DataFrame
    ) -> SchemaAnalysis:
        """Validate schema with Claude AI assistance."""
        logger.info(f"Validating schema for {table_name}")

        expected_schema = self.EXPECTED_SCHEMAS.get(table_name, {})
        required_fields = self.REQUIRED_FIELDS.get(table_name, set())

        analysis = self.validator.validate_dataframe(
            df=df,
            table_name=table_name,
            expected_schema=expected_schema,
            required_fields=required_fields,
            allow_z_fields=True
        )

        # Log summary
        logger.info(f"Validation complete:")
        logger.info(f"  Missing fields: {len(analysis.missing_fields)}")
        logger.info(f"  Z-fields: {len(analysis.z_fields)}")
        logger.info(f"  Issues: {len(analysis.issues)}")

        if analysis.claude_suggestions:
            logger.info(f"  Claude recommendations: {len(analysis.claude_suggestions)} categories")

        return analysis

    def _apply_auto_fixes(
        self,
        df: pd.DataFrame,
        analysis: SchemaAnalysis
    ) -> Tuple[pd.DataFrame, List[str]]:
        """Apply automatic fixes based on validation analysis."""
        logger.info("Applying automatic fixes")

        df_fixed, applied_fixes = self.validator.auto_fix_dataframe(
            df=df,
            analysis=analysis,
            apply_claude_suggestions=True
        )

        return df_fixed, applied_fixes

    def _apply_delta_loading(
        self,
        table_name: str,
        df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, DeltaLoadResult]:
        """Apply delta loading to extract only changed records."""
        logger.info(f"Applying delta loading for {table_name}")

        df_delta, delta_result = self.delta_extractor.extract_delta(
            full_data=df,
            table_name=table_name
        )

        # Save delta report
        if self.config.save_validation_report:
            report_path = self.report_dir / f"{table_name}_delta_report.txt"
            report = self.delta_extractor.delta_loader.generate_delta_report(delta_result)
            with open(report_path, "w") as f:
                f.write(report)
            logger.info(f"Delta report saved: {report_path}")

        return df_delta, delta_result

    def _save_validation_report(self, analysis: SchemaAnalysis):
        """Save validation report to file."""
        if not self.config.report_directory:
            return

        report_path = self.report_dir / f"{analysis.table_name}_validation.txt"
        report = self.validator.generate_validation_report(analysis)

        with open(report_path, "w") as f:
            f.write(report)

        logger.info(f"Validation report saved: {report_path}")

    def _create_empty_result(
        self,
        table_name: str,
        start_time: datetime
    ) -> LoadResult:
        """Create empty load result."""
        return LoadResult(
            table_name=table_name,
            load_mode=self.config.mode,
            records_loaded=0,
            records_fixed=0,
            validation_issues=0,
            z_fields_found=0,
            execution_time_seconds=(datetime.now() - start_time).total_seconds(),
            claude_used=False,
            auto_fixes_applied=[]
        )

    def load_multiple_tables(
        self,
        table_names: List[str],
        data_source: Any,
        parallel: bool = False
    ) -> Dict[str, Tuple[pd.DataFrame, LoadResult]]:
        """
        Load multiple tables with intelligent processing.

        Args:
            table_names: List of table names to load
            data_source: Data source (connector or loader)
            parallel: Whether to load in parallel (not implemented yet)

        Returns:
            Dictionary mapping table name to (DataFrame, LoadResult)
        """
        logger.info(f"Loading {len(table_names)} tables")

        results = {}

        for table_name in table_names:
            try:
                df, result = self.load_table(table_name, data_source)
                results[table_name] = (df, result)
            except Exception as e:
                logger.error(f"Error loading {table_name}: {e}", exc_info=True)
                results[table_name] = (pd.DataFrame(), self._create_empty_result(
                    table_name,
                    datetime.now()
                ))

        # Generate summary report
        self._generate_summary_report(results)

        return results

    def _generate_summary_report(
        self,
        results: Dict[str, Tuple[pd.DataFrame, LoadResult]]
    ):
        """Generate summary report for multiple table loads."""
        if not self.config.save_validation_report:
            return

        report_path = self.report_dir / f"load_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        with open(report_path, "w") as f:
            f.write("=" * 70 + "\n")
            f.write("SAP Intelligent Load Summary\n")
            f.write("=" * 70 + "\n\n")

            f.write(f"Load Mode: {self.config.mode}\n")
            f.write(f"Connection Type: {self.config.connection_type}\n")
            f.write(f"Claude AI: {'Enabled' if self.config.use_claude_ai else 'Disabled'}\n")
            f.write(f"Delta Loading: {'Enabled' if self.config.enable_delta else 'Disabled'}\n")
            f.write(f"Timestamp: {datetime.now()}\n\n")

            f.write("-" * 70 + "\n")
            f.write("Table Summary:\n")
            f.write("-" * 70 + "\n\n")

            total_records = 0
            total_fixes = 0
            total_z_fields = 0
            total_issues = 0

            for table_name, (df, result) in results.items():
                f.write(f"\n{table_name}:\n")
                f.write(f"  Records Loaded: {result.records_loaded}\n")
                f.write(f"  Load Mode: {result.load_mode}\n")
                f.write(f"  Auto-Fixes Applied: {result.records_fixed}\n")
                f.write(f"  Validation Issues: {result.validation_issues}\n")
                f.write(f"  Z-Fields Found: {result.z_fields_found}\n")
                f.write(f"  Execution Time: {result.execution_time_seconds:.2f}s\n")

                if result.delta_result:
                    f.write(f"  Delta Stats:\n")
                    f.write(f"    New: {result.delta_result.new_records}\n")
                    f.write(f"    Changed: {result.delta_result.changed_records}\n")
                    f.write(f"    Deleted: {result.delta_result.deleted_records}\n")

                total_records += result.records_loaded
                total_fixes += result.records_fixed
                total_z_fields += result.z_fields_found
                total_issues += result.validation_issues

            f.write("\n" + "=" * 70 + "\n")
            f.write("Overall Summary:\n")
            f.write("=" * 70 + "\n")
            f.write(f"Total Tables Loaded: {len(results)}\n")
            f.write(f"Total Records: {total_records}\n")
            f.write(f"Total Auto-Fixes: {total_fixes}\n")
            f.write(f"Total Z-Fields: {total_z_fields}\n")
            f.write(f"Total Issues: {total_issues}\n")

        logger.info(f"Summary report saved: {report_path}")


def create_intelligent_loader(
    mode: str,  # "initial" or "daily"
    connection_type: str,  # "rfc" or "csv"
    use_claude: bool = True,
    enable_delta: bool = True,
    **kwargs
) -> IntelligentSAPLoader:
    """
    Factory function to create intelligent loader.

    Args:
        mode: "initial" or "daily"
        connection_type: "rfc" or "csv"
        use_claude: Enable Claude AI assistance
        enable_delta: Enable delta loading (daily mode only)
        **kwargs: Additional configuration parameters

    Returns:
        Configured IntelligentSAPLoader
    """
    config = LoadConfig(
        mode=mode,
        connection_type=connection_type,
        use_claude_ai=use_claude,
        auto_fix_issues=kwargs.get("auto_fix", True),
        enable_delta=enable_delta and mode == "daily",
        save_validation_report=kwargs.get("save_reports", True),
        report_directory=kwargs.get("report_dir", "./reports")
    )

    return IntelligentSAPLoader(
        config=config,
        claude_api_key=kwargs.get("claude_api_key"),
        delta_state_dir=kwargs.get("delta_state_dir", "./delta_state")
    )
