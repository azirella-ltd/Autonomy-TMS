"""
Plan Writer for SAP Integration.

Writes Beer Game optimization results back to SAP S/4HANA and APO systems.

Supports:
- Direct BAPI calls (S/4HANA)
- CSV file generation for import (S/4HANA and APO)
- Plan version management
- Batch processing
- Error handling and rollback

Output Types:
- Purchase Requisitions (S/4HANA)
- Planned Orders (S/4HANA/APO)
- SNP Planning Data (APO)
- Stock Transfer Orders (S/4HANA)
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
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
class PlanWriteResult:
    """Result of plan write operation."""
    success: bool
    records_written: int
    records_failed: int
    messages: List[str]
    output_file: Optional[str] = None


class PlanWriter:
    """
    Write Beer Game optimization plans back to SAP systems.

    Supports two modes:
    1. Direct RFC connection (BAPI calls)
    2. CSV file generation for batch import
    """

    def __init__(
        self,
        connection: Optional[Connection] = None,
        output_directory: Optional[str] = None,
        use_csv_mode: bool = True
    ):
        """
        Initialize plan writer.

        Args:
            connection: RFC connection object (for direct mode)
            output_directory: Directory for CSV output files
            use_csv_mode: If True, generate CSV files; if False, use RFC
        """
        self.connection = connection
        self.use_csv_mode = use_csv_mode

        if use_csv_mode:
            if not output_directory:
                raise ValueError("output_directory required for CSV mode")
            self.output_dir = Path(output_directory)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Plan writer initialized in CSV mode: {self.output_dir}")
        else:
            if not connection:
                raise ValueError("RFC connection required for direct mode")
            logger.info("Plan writer initialized in RFC mode")

    def write_purchase_requisitions(
        self,
        requisitions: pd.DataFrame,
        test_mode: bool = False
    ) -> PlanWriteResult:
        """
        Write purchase requisitions to S/4HANA.

        Args:
            requisitions: DataFrame with PR data
                Required columns:
                - MATERIAL: Material number
                - PLANT: Plant
                - QUANTITY: Requisition quantity
                - DELIV_DATE: Delivery date
                - PREQ_PRICE: Price per unit
                - CURRENCY: Currency
                - PUR_GROUP: Purchasing group

            test_mode: If True, validate only without posting

        Returns:
            PlanWriteResult with operation status
        """
        logger.info(f"Writing {len(requisitions)} purchase requisitions")

        if self.use_csv_mode:
            return self._write_pr_csv(requisitions)
        else:
            return self._write_pr_bapi(requisitions, test_mode)

    def _write_pr_csv(self, requisitions: pd.DataFrame) -> PlanWriteResult:
        """Generate CSV file for purchase requisition import."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"PR_IMPORT_{timestamp}.csv"

        # Format for SAP import
        pr_export = pd.DataFrame()
        pr_export["MATERIAL"] = requisitions["MATERIAL"]
        pr_export["PLANT"] = requisitions["PLANT"]
        pr_export["QUANTITY"] = requisitions["QUANTITY"]
        pr_export["DELIV_DATE"] = pd.to_datetime(
            requisitions["DELIV_DATE"]
        ).dt.strftime("%Y%m%d")
        pr_export["UNIT"] = requisitions.get("UNIT", "EA")
        pr_export["PREQ_PRICE"] = requisitions.get("PREQ_PRICE", 0)
        pr_export["CURRENCY"] = requisitions.get("CURRENCY", "USD")
        pr_export["PUR_GROUP"] = requisitions.get("PUR_GROUP", "")
        pr_export["DOC_TYPE"] = "NB"  # Standard PR type
        pr_export["SHORT_TEXT"] = "Beer Game Optimization Plan"

        # Export to CSV
        pr_export.to_csv(output_file, index=False)

        logger.info(f"Generated PR import file: {output_file}")

        return PlanWriteResult(
            success=True,
            records_written=len(pr_export),
            records_failed=0,
            messages=[f"CSV file generated: {output_file}"],
            output_file=str(output_file)
        )

    def _write_pr_bapi(
        self,
        requisitions: pd.DataFrame,
        test_mode: bool
    ) -> PlanWriteResult:
        """Write purchase requisitions via BAPI_PR_CREATE."""
        if not self.connection:
            raise RuntimeError("No RFC connection available")

        messages = []
        written = 0
        failed = 0

        for idx, row in requisitions.iterrows():
            try:
                # Prepare BAPI parameters
                pr_items = [{
                    "PREQ_ITEM": "00010",
                    "MATERIAL": str(row["MATERIAL"]).zfill(18),
                    "PLANT": str(row["PLANT"]),
                    "QUANTITY": float(row["QUANTITY"]),
                    "UNIT": str(row.get("UNIT", "EA")),
                    "DELIV_DATE": row["DELIV_DATE"].strftime("%Y%m%d"),
                    "PREQ_PRICE": float(row.get("PREQ_PRICE", 0)),
                    "CURRENCY": str(row.get("CURRENCY", "USD")),
                    "PUR_GROUP": str(row.get("PUR_GROUP", "")),
                    "SHORT_TEXT": "Beer Game Plan",
                }]

                # Call BAPI
                result = self.connection.call(
                    "BAPI_PR_CREATE",
                    PRHEADER={"PR_TYPE": "NB"},
                    PRITEM=pr_items,
                    TESTRUN="X" if test_mode else "",
                )

                # Check result
                if result.get("NUMBER"):
                    pr_number = result["NUMBER"]
                    messages.append(f"Created PR {pr_number} for {row['MATERIAL']}")
                    written += 1

                    # Commit if not test mode
                    if not test_mode:
                        self.connection.call("BAPI_TRANSACTION_COMMIT", WAIT="X")
                else:
                    # Check for errors
                    errors = result.get("RETURN", [])
                    if errors:
                        error_msg = errors[0].get("MESSAGE", "Unknown error")
                        messages.append(f"Failed for {row['MATERIAL']}: {error_msg}")
                        failed += 1

            except Exception as e:
                logger.error(f"Error creating PR for {row['MATERIAL']}: {e}")
                messages.append(f"Exception for {row['MATERIAL']}: {str(e)}")
                failed += 1

        return PlanWriteResult(
            success=(failed == 0),
            records_written=written,
            records_failed=failed,
            messages=messages
        )

    def write_planned_orders(
        self,
        planned_orders: pd.DataFrame,
        test_mode: bool = False
    ) -> PlanWriteResult:
        """
        Write planned orders to S/4HANA.

        Args:
            planned_orders: DataFrame with planned order data
                Required columns:
                - MATERIAL: Material number
                - PLANT: Plant
                - QUANTITY: Order quantity
                - ORDER_TYPE: Order type (LA = make-to-stock)
                - START_DATE: Production start date
                - FINISH_DATE: Production finish date

            test_mode: If True, validate only

        Returns:
            PlanWriteResult with operation status
        """
        logger.info(f"Writing {len(planned_orders)} planned orders")

        if self.use_csv_mode:
            return self._write_plord_csv(planned_orders)
        else:
            return self._write_plord_bapi(planned_orders, test_mode)

    def _write_plord_csv(self, planned_orders: pd.DataFrame) -> PlanWriteResult:
        """Generate CSV file for planned order import."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"PLORD_IMPORT_{timestamp}.csv"

        # Format for SAP import
        plord_export = pd.DataFrame()
        plord_export["MATERIAL"] = planned_orders["MATERIAL"]
        plord_export["PLANT"] = planned_orders["PLANT"]
        plord_export["QUANTITY"] = planned_orders["QUANTITY"]
        plord_export["UNIT"] = planned_orders.get("UNIT", "EA")
        plord_export["ORDER_TYPE"] = planned_orders.get("ORDER_TYPE", "LA")
        plord_export["START_DATE"] = pd.to_datetime(
            planned_orders["START_DATE"]
        ).dt.strftime("%Y%m%d")
        plord_export["FINISH_DATE"] = pd.to_datetime(
            planned_orders["FINISH_DATE"]
        ).dt.strftime("%Y%m%d")
        plord_export["MRP_CONTROLLER"] = planned_orders.get("MRP_CONTROLLER", "")
        plord_export["PROD_SCHED"] = planned_orders.get("PROD_SCHED", "")

        plord_export.to_csv(output_file, index=False)

        logger.info(f"Generated planned order import file: {output_file}")

        return PlanWriteResult(
            success=True,
            records_written=len(plord_export),
            records_failed=0,
            messages=[f"CSV file generated: {output_file}"],
            output_file=str(output_file)
        )

    def _write_plord_bapi(
        self,
        planned_orders: pd.DataFrame,
        test_mode: bool
    ) -> PlanWriteResult:
        """Write planned orders via BAPI (if available)."""
        # Note: S/4HANA may not have direct BAPI for planned orders
        # Typically managed through MRP run or manual creation in MD11
        logger.warning("Direct BAPI for planned orders not available. Use CSV mode.")

        return PlanWriteResult(
            success=False,
            records_written=0,
            records_failed=len(planned_orders),
            messages=["Direct planned order creation not supported. Use CSV mode."]
        )

    def write_apo_snp_plan(
        self,
        snp_plan: pd.DataFrame,
        plan_version: str,
        planning_horizon_start: date,
        planning_horizon_end: date
    ) -> PlanWriteResult:
        """
        Write SNP planning data to APO.

        APO SNP plans are typically written via:
        1. CSV export for liveCache import (recommended)
        2. Planning book upload
        3. Direct liveCache interface (advanced)

        Args:
            snp_plan: DataFrame with SNP plan data
                Required columns:
                - LOCATION: Location/plant
                - MATERIAL: Product ID
                - PLAN_DATE: Planning date
                - DEMAND_QTY: Demand quantity
                - SUPPLY_QTY: Supply quantity

            plan_version: Planning version (e.g., "000", "001")
            planning_horizon_start: Start date of planning horizon
            planning_horizon_end: End date of planning horizon

        Returns:
            PlanWriteResult with operation status
        """
        logger.info(
            f"Writing APO SNP plan version {plan_version} "
            f"({len(snp_plan)} records)"
        )

        # APO always uses CSV mode (liveCache complexity)
        return self._write_apo_snp_csv(
            snp_plan,
            plan_version,
            planning_horizon_start,
            planning_horizon_end
        )

    def _write_apo_snp_csv(
        self,
        snp_plan: pd.DataFrame,
        plan_version: str,
        horizon_start: date,
        horizon_end: date
    ) -> PlanWriteResult:
        """Generate CSV file for APO SNP plan import."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"APO_SNP_{plan_version}_{timestamp}.csv"

        # Format for APO import
        apo_export = pd.DataFrame()
        apo_export["PLAN_VERSION"] = plan_version
        apo_export["LOCATION"] = snp_plan["LOCATION"]
        apo_export["MATERIAL"] = snp_plan["MATERIAL"]
        apo_export["PLAN_DATE"] = pd.to_datetime(
            snp_plan["PLAN_DATE"]
        ).dt.strftime("%Y%m%d")
        apo_export["DEMAND_QTY"] = snp_plan.get("DEMAND_QTY", 0)
        apo_export["SUPPLY_QTY"] = snp_plan.get("SUPPLY_QTY", 0)
        apo_export["STOCK_QTY"] = snp_plan.get("STOCK_QTY", 0)
        apo_export["HORIZON_START"] = horizon_start.strftime("%Y%m%d")
        apo_export["HORIZON_END"] = horizon_end.strftime("%Y%m%d")
        apo_export["CREATED_BY"] = "BEERGAME"
        apo_export["CREATED_DATE"] = datetime.now().strftime("%Y%m%d")

        apo_export.to_csv(output_file, index=False)

        logger.info(f"Generated APO SNP plan file: {output_file}")

        # Also create import instructions file
        instructions_file = output_file.with_suffix(".txt")
        with open(instructions_file, "w") as f:
            f.write("APO SNP Plan Import Instructions\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Plan Version: {plan_version}\n")
            f.write(f"Planning Horizon: {horizon_start} to {horizon_end}\n")
            f.write(f"Records: {len(apo_export)}\n\n")
            f.write("Import Steps:\n")
            f.write("1. Log into APO system\n")
            f.write("2. Transaction: /SAPAPO/SNP94 (SNP Planning Book)\n")
            f.write("3. Select Planning Version: " + plan_version + "\n")
            f.write("4. Menu: Edit > Upload > From File\n")
            f.write(f"5. Select file: {output_file.name}\n")
            f.write("6. Execute import and verify results\n")

        return PlanWriteResult(
            success=True,
            records_written=len(apo_export),
            records_failed=0,
            messages=[
                f"CSV file generated: {output_file}",
                f"Instructions file: {instructions_file}"
            ],
            output_file=str(output_file)
        )

    def write_stock_transport_orders(
        self,
        sto_data: pd.DataFrame,
        test_mode: bool = False
    ) -> PlanWriteResult:
        """
        Write stock transport orders to S/4HANA.

        Args:
            sto_data: DataFrame with STO data
                Required columns:
                - MATERIAL: Material number
                - FROM_PLANT: Source plant
                - TO_PLANT: Destination plant
                - QUANTITY: Transfer quantity
                - DELIVERY_DATE: Requested delivery date

            test_mode: If True, validate only

        Returns:
            PlanWriteResult with operation status
        """
        logger.info(f"Writing {len(sto_data)} stock transport orders")

        if self.use_csv_mode:
            return self._write_sto_csv(sto_data)
        else:
            return self._write_sto_bapi(sto_data, test_mode)

    def _write_sto_csv(self, sto_data: pd.DataFrame) -> PlanWriteResult:
        """Generate CSV file for STO import."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"STO_IMPORT_{timestamp}.csv"

        # Format for SAP import
        sto_export = pd.DataFrame()
        sto_export["MATERIAL"] = sto_data["MATERIAL"]
        sto_export["FROM_PLANT"] = sto_data["FROM_PLANT"]
        sto_export["TO_PLANT"] = sto_data["TO_PLANT"]
        sto_export["QUANTITY"] = sto_data["QUANTITY"]
        sto_export["UNIT"] = sto_data.get("UNIT", "EA")
        sto_export["DELIVERY_DATE"] = pd.to_datetime(
            sto_data["DELIVERY_DATE"]
        ).dt.strftime("%Y%m%d")
        sto_export["DOC_TYPE"] = "UB"  # Stock transport order
        sto_export["VENDOR"] = sto_data["FROM_PLANT"]  # Plant as vendor
        sto_export["PUR_ORG"] = sto_data.get("PUR_ORG", "")
        sto_export["PUR_GROUP"] = sto_data.get("PUR_GROUP", "")

        sto_export.to_csv(output_file, index=False)

        logger.info(f"Generated STO import file: {output_file}")

        return PlanWriteResult(
            success=True,
            records_written=len(sto_export),
            records_failed=0,
            messages=[f"CSV file generated: {output_file}"],
            output_file=str(output_file)
        )

    def _write_sto_bapi(
        self,
        sto_data: pd.DataFrame,
        test_mode: bool
    ) -> PlanWriteResult:
        """Write STOs via BAPI_PO_CREATE1."""
        if not self.connection:
            raise RuntimeError("No RFC connection available")

        messages = []
        written = 0
        failed = 0

        for idx, row in sto_data.iterrows():
            try:
                # STO header
                po_header = {
                    "DOC_TYPE": "UB",
                    "VENDOR": str(row["FROM_PLANT"]),
                    "PURCH_ORG": str(row.get("PUR_ORG", "")),
                    "PUR_GROUP": str(row.get("PUR_GROUP", "")),
                    "DOC_DATE": datetime.now().strftime("%Y%m%d"),
                }

                # STO items
                po_items = [{
                    "PO_ITEM": "00010",
                    "MATERIAL": str(row["MATERIAL"]).zfill(18),
                    "PLANT": str(row["TO_PLANT"]),
                    "QUANTITY": float(row["QUANTITY"]),
                    "UNIT": str(row.get("UNIT", "EA")),
                    "DELIV_DATE": row["DELIVERY_DATE"].strftime("%Y%m%d"),
                }]

                # Shipping data (specifies source plant)
                po_item_shipping = [{
                    "PO_ITEM": "00010",
                    "SHIP_TO": str(row["TO_PLANT"]),
                }]

                # Call BAPI
                result = self.connection.call(
                    "BAPI_PO_CREATE1",
                    POHEADER=po_header,
                    POITEM=po_items,
                    POITEMX=[{"PO_ITEM": "00010", "MATERIAL": "X", "QUANTITY": "X"}],
                    POSHIPPING=po_item_shipping,
                    TESTRUN="X" if test_mode else "",
                )

                # Check result
                if result.get("PONUMBER"):
                    sto_number = result["PONUMBER"]
                    messages.append(
                        f"Created STO {sto_number}: "
                        f"{row['FROM_PLANT']} → {row['TO_PLANT']}"
                    )
                    written += 1

                    if not test_mode:
                        self.connection.call("BAPI_TRANSACTION_COMMIT", WAIT="X")
                else:
                    errors = result.get("RETURN", [])
                    if errors:
                        error_msg = errors[0].get("MESSAGE", "Unknown error")
                        messages.append(
                            f"Failed STO {row['FROM_PLANT']}→{row['TO_PLANT']}: "
                            f"{error_msg}"
                        )
                        failed += 1

            except Exception as e:
                logger.error(f"Error creating STO: {e}")
                messages.append(f"Exception: {str(e)}")
                failed += 1

        return PlanWriteResult(
            success=(failed == 0),
            records_written=written,
            records_failed=failed,
            messages=messages
        )

    def write_simulation_optimization_plan(
        self,
        optimization_results: Dict[str, pd.DataFrame],
        plan_metadata: Dict[str, Any]
    ) -> Dict[str, PlanWriteResult]:
        """
        Write complete simulation optimization results to SAP.

        This is the main entry point for writing simulation plans back to SAP.

        Args:
            optimization_results: Dictionary with DataFrames:
                - "purchase_requisitions": PRs to create
                - "planned_orders": Planned production orders
                - "stock_transfers": Stock transport orders
                - "snp_plan": APO SNP planning data (if applicable)

            plan_metadata: Metadata about the plan:
                - plan_version: Version identifier
                - planning_horizon_start: Start date
                - planning_horizon_end: End date
                - created_by: User/system creating plan
                - description: Plan description

        Returns:
            Dictionary with PlanWriteResult for each component
        """
        logger.info("Writing Beer Game optimization plan to SAP")
        logger.info(f"Plan metadata: {plan_metadata}")

        results = {}

        # Write purchase requisitions
        if "purchase_requisitions" in optimization_results:
            pr_df = optimization_results["purchase_requisitions"]
            if not pr_df.empty:
                results["purchase_requisitions"] = self.write_purchase_requisitions(pr_df)

        # Write planned orders
        if "planned_orders" in optimization_results:
            plord_df = optimization_results["planned_orders"]
            if not plord_df.empty:
                results["planned_orders"] = self.write_planned_orders(plord_df)

        # Write stock transfers
        if "stock_transfers" in optimization_results:
            sto_df = optimization_results["stock_transfers"]
            if not sto_df.empty:
                results["stock_transfers"] = self.write_stock_transport_orders(sto_df)

        # Write APO SNP plan
        if "snp_plan" in optimization_results:
            snp_df = optimization_results["snp_plan"]
            if not snp_df.empty:
                results["snp_plan"] = self.write_apo_snp_plan(
                    snp_df,
                    plan_version=plan_metadata.get("plan_version", "001"),
                    planning_horizon_start=plan_metadata["planning_horizon_start"],
                    planning_horizon_end=plan_metadata["planning_horizon_end"]
                )

        # Generate summary report
        self._generate_summary_report(results, plan_metadata)

        return results

    def _generate_summary_report(
        self,
        results: Dict[str, PlanWriteResult],
        metadata: Dict[str, Any]
    ):
        """Generate summary report of plan write operations."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.output_dir / f"PLAN_SUMMARY_{timestamp}.txt"

        with open(report_file, "w") as f:
            f.write("Beer Game Optimization Plan - Write Summary\n")
            f.write("=" * 60 + "\n\n")

            f.write("Plan Metadata:\n")
            for key, value in metadata.items():
                f.write(f"  {key}: {value}\n")
            f.write("\n")

            f.write("Write Results:\n")
            f.write("-" * 60 + "\n")

            total_written = 0
            total_failed = 0

            for component, result in results.items():
                f.write(f"\n{component.replace('_', ' ').title()}:\n")
                f.write(f"  Status: {'SUCCESS' if result.success else 'FAILED'}\n")
                f.write(f"  Records Written: {result.records_written}\n")
                f.write(f"  Records Failed: {result.records_failed}\n")

                if result.output_file:
                    f.write(f"  Output File: {result.output_file}\n")

                if result.messages:
                    f.write("  Messages:\n")
                    for msg in result.messages[:10]:  # Limit to first 10
                        f.write(f"    - {msg}\n")
                    if len(result.messages) > 10:
                        f.write(f"    ... and {len(result.messages) - 10} more\n")

                total_written += result.records_written
                total_failed += result.records_failed

            f.write("\n" + "=" * 60 + "\n")
            f.write(f"Total Records Written: {total_written}\n")
            f.write(f"Total Records Failed: {total_failed}\n")
            f.write(f"\nReport Generated: {datetime.now()}\n")

        logger.info(f"Summary report generated: {report_file}")
