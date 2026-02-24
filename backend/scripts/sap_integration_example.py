#!/usr/bin/env python3
"""
Example SAP Integration Script for Supply Chain Simulation.

Demonstrates:
1. Extracting supply chain data from S/4HANA and APO
2. Mapping to AWS Supply Chain Data Model
3. Running supply chain optimization
4. Writing results back to SAP

Usage:
    # Using direct RFC connection:
    python sap_integration_example.py --mode rfc --config config.yaml

    # Using CSV files:
    python sap_integration_example.py --mode csv --csv-dir /path/to/csv
"""

import argparse
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.integrations.sap import (
    S4HANAConnector,
    S4HANAConnectionConfig,
    APOConnector,
    APOConnectionConfig,
    AWSSupplyChainMapper,
    CSVDataLoader,
    PlanWriter,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def extract_data_rfc(s4hana_config, apo_config):
    """Extract data using RFC connections."""
    logger.info("=== Extracting Data via RFC ===")

    # Connect to S/4HANA
    with S4HANAConnector(s4hana_config) as s4:
        logger.info("Extracting S/4HANA data...")

        # Extract master data
        plants = s4.extract_plants()
        materials = s4.extract_materials(plant="1000")
        inventory = s4.extract_inventory(plant="1000")

        # Extract transactional data
        date_from = date.today() - timedelta(days=90)
        date_to = date.today()

        po_headers, po_items = s4.extract_purchase_orders(
            plant="1000",
            date_from=date_from,
            date_to=date_to
        )

        so_headers, so_items = s4.extract_sales_orders(
            sales_org="1000",
            date_from=date_from,
            date_to=date_to
        )

        delivery_headers, delivery_items = s4.extract_deliveries(
            plant="1000",
            date_from=date_from,
            date_to=date_to
        )

    # Connect to APO (if configured)
    apo_data = {}
    if apo_config:
        with APOConnector(apo_config) as apo:
            logger.info("Extracting APO data...")

            apo_data["locations"] = apo.extract_locations()
            apo_data["materials"] = apo.extract_materials()
            apo_data["stock"] = apo.extract_stock()
            apo_data["orders"] = apo.extract_orders(
                date_from=date_from,
                date_to=date_to
            )
            apo_data["snp_plan"] = apo.extract_snp_plan(
                plan_version="000",
                date_from=date_from,
                date_to=date_to
            )

    return {
        "s4hana": {
            "plants": plants,
            "materials": materials,
            "inventory": inventory,
            "po_headers": po_headers,
            "po_items": po_items,
            "so_headers": so_headers,
            "so_items": so_items,
            "delivery_headers": delivery_headers,
            "delivery_items": delivery_items,
        },
        "apo": apo_data
    }


def extract_data_csv(csv_dir):
    """Extract data from CSV files."""
    logger.info("=== Extracting Data from CSV ===")

    loader = CSVDataLoader(csv_dir)

    # List available tables
    available_tables = loader.list_available_tables()
    logger.info(f"Available tables: {available_tables}")

    # Load S/4HANA data
    plants = loader.load_plants()
    materials = loader.load_materials(with_plant_data=True)
    inventory = loader.load_inventory()
    po_headers, po_items = loader.load_purchase_orders()
    so_headers, so_items = loader.load_sales_orders()
    delivery_headers, delivery_items = loader.load_deliveries()

    # Load APO data (if available)
    apo_locations = loader.load_apo_locations()
    apo_materials = loader.load_apo_materials()
    apo_stock = loader.load_apo_stock()
    apo_orders = loader.load_apo_orders()
    apo_snp = loader.load_apo_snp_plan(plan_version="000")

    return {
        "s4hana": {
            "plants": plants,
            "materials": materials,
            "inventory": inventory,
            "po_headers": po_headers,
            "po_items": po_items,
            "so_headers": so_headers,
            "so_items": so_items,
            "delivery_headers": delivery_headers,
            "delivery_items": delivery_items,
        },
        "apo": {
            "locations": apo_locations,
            "materials": apo_materials,
            "stock": apo_stock,
            "orders": apo_orders,
            "snp_plan": apo_snp,
        }
    }


def map_to_aws_model(extracted_data):
    """Map extracted SAP data to AWS Supply Chain Data Model."""
    logger.info("=== Mapping to AWS Supply Chain Data Model ===")

    mapper = AWSSupplyChainMapper()
    aws_data = {}

    s4_data = extracted_data["s4hana"]
    apo_data = extracted_data.get("apo", {})

    # Map sites
    if not s4_data["plants"].empty:
        aws_data["sites_s4"] = mapper.map_s4hana_plants_to_sites(s4_data["plants"])

    if apo_data.get("locations") is not None and not apo_data["locations"].empty:
        aws_data["sites_apo"] = mapper.map_apo_locations_to_sites(apo_data["locations"])

    # Map products
    if not s4_data["materials"].empty:
        aws_data["products_s4"] = mapper.map_s4hana_materials_to_products(
            s4_data["materials"]
        )

    if apo_data.get("materials") is not None and not apo_data["materials"].empty:
        aws_data["products_apo"] = mapper.map_apo_materials_to_products(
            apo_data["materials"]
        )

    # Map inventory
    if not s4_data["inventory"].empty:
        aws_data["inventory_levels"] = mapper.map_s4hana_inventory_to_inventory_levels(
            s4_data["inventory"]
        )

    # Map purchase orders
    if not s4_data["po_headers"].empty and not s4_data["po_items"].empty:
        aws_data["purchase_orders"] = mapper.map_s4hana_po_to_purchase_orders(
            s4_data["po_headers"],
            s4_data["po_items"]
        )

    # Map sales orders
    if not s4_data["so_headers"].empty and not s4_data["so_items"].empty:
        aws_data["sales_orders"] = mapper.map_s4hana_so_to_sales_orders(
            s4_data["so_headers"],
            s4_data["so_items"]
        )

    # Map deliveries to shipments
    if not s4_data["delivery_headers"].empty and not s4_data["delivery_items"].empty:
        aws_data["shipments"] = mapper.map_s4hana_deliveries_to_shipments(
            s4_data["delivery_headers"],
            s4_data["delivery_items"]
        )

    # Map APO data
    if apo_data.get("orders") is not None and not apo_data["orders"].empty:
        aws_data["supply_plans"] = mapper.map_apo_orders_to_supply_plans(
            apo_data["orders"]
        )

    if apo_data.get("snp_plan") is not None and not apo_data["snp_plan"].empty:
        aws_data["demand_plans"] = mapper.map_apo_snp_to_demand_plans(
            apo_data["snp_plan"]
        )

    logger.info(f"Mapped {len(aws_data)} AWS entities")
    for entity, df in aws_data.items():
        logger.info(f"  {entity}: {len(df)} records")

    return aws_data


def run_simulation_optimization(aws_data):
    """
    Run simulation optimization on AWS Supply Chain data.

    This is a placeholder - integrate with actual simulation engine.
    """
    logger.info("=== Running Simulation Optimization ===")

    # TODO: Integrate with simulation engine
    # For now, return mock optimization results

    import pandas as pd

    # Mock: Generate purchase requisitions
    if "inventory_levels" in aws_data:
        inv = aws_data["inventory_levels"]

        # Simple reorder logic: if available < safety stock, create PR
        prs = []
        for _, row in inv.iterrows():
            if row["available_quantity"] < row["safety_stock_quantity"]:
                shortage = row["safety_stock_quantity"] - row["available_quantity"]
                prs.append({
                    "MATERIAL": row["product_id"],
                    "PLANT": row["site_id"],
                    "QUANTITY": shortage * 2,  # Order 2x shortage
                    "DELIV_DATE": date.today() + timedelta(days=14),
                    "PREQ_PRICE": 10.0,
                    "CURRENCY": "USD",
                    "PUR_GROUP": "001",
                })

        pr_df = pd.DataFrame(prs)
    else:
        pr_df = pd.DataFrame()

    # Mock: Generate planned orders
    plord_df = pd.DataFrame()  # Would be based on production planning

    # Mock: Generate stock transfers
    sto_df = pd.DataFrame()  # Would be based on network optimization

    # Mock: Generate SNP plan
    snp_df = pd.DataFrame()  # Would be based on demand forecasting

    logger.info(f"Generated {len(pr_df)} purchase requisitions")

    return {
        "purchase_requisitions": pr_df,
        "planned_orders": plord_df,
        "stock_transfers": sto_df,
        "snp_plan": snp_df,
    }


def write_results_to_sap(optimization_results, output_dir, connection=None):
    """Write optimization results back to SAP."""
    logger.info("=== Writing Results to SAP ===")

    # Initialize plan writer
    writer = PlanWriter(
        connection=connection,
        output_directory=output_dir,
        use_csv_mode=(connection is None)
    )

    # Plan metadata
    plan_metadata = {
        "plan_version": "BG_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
        "planning_horizon_start": date.today(),
        "planning_horizon_end": date.today() + timedelta(days=90),
        "created_by": "SIMULATION",
        "description": "Simulation Optimization Plan",
    }

    # Write complete plan
    results = writer.write_simulation_optimization_plan(
        optimization_results,
        plan_metadata
    )

    # Log results
    logger.info("Write Results:")
    for component, result in results.items():
        logger.info(f"  {component}:")
        logger.info(f"    Success: {result.success}")
        logger.info(f"    Written: {result.records_written}")
        logger.info(f"    Failed: {result.records_failed}")
        if result.output_file:
            logger.info(f"    File: {result.output_file}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="SAP Integration for Supply Chain Simulation"
    )
    parser.add_argument(
        "--mode",
        choices=["rfc", "csv"],
        default="csv",
        help="Connection mode: rfc (direct) or csv (file-based)"
    )
    parser.add_argument(
        "--csv-dir",
        type=str,
        default="./sap_csv_data",
        help="Directory containing CSV files (for CSV mode)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./sap_output",
        help="Directory for output files"
    )

    # S/4HANA connection parameters (for RFC mode)
    parser.add_argument("--s4-host", type=str, help="S/4HANA host")
    parser.add_argument("--s4-sysnr", type=str, help="S/4HANA system number")
    parser.add_argument("--s4-client", type=str, help="S/4HANA client")
    parser.add_argument("--s4-user", type=str, help="S/4HANA username")
    parser.add_argument("--s4-passwd", type=str, help="S/4HANA password")

    # APO connection parameters (for RFC mode)
    parser.add_argument("--apo-host", type=str, help="APO host")
    parser.add_argument("--apo-sysnr", type=str, help="APO system number")
    parser.add_argument("--apo-client", type=str, help="APO client")
    parser.add_argument("--apo-user", type=str, help="APO username")
    parser.add_argument("--apo-passwd", type=str, help="APO password")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Supply Chain SAP Integration")
    logger.info("=" * 60)

    try:
        # Step 1: Extract data
        if args.mode == "rfc":
            # RFC connection mode
            s4_config = S4HANAConnectionConfig(
                ashost=args.s4_host,
                sysnr=args.s4_sysnr,
                client=args.s4_client,
                user=args.s4_user,
                passwd=args.s4_passwd,
            )

            apo_config = None
            if args.apo_host:
                apo_config = APOConnectionConfig(
                    ashost=args.apo_host,
                    sysnr=args.apo_sysnr,
                    client=args.apo_client,
                    user=args.apo_user,
                    passwd=args.apo_passwd,
                    use_csv_mode=False
                )

            extracted_data = extract_data_rfc(s4_config, apo_config)
        else:
            # CSV mode
            extracted_data = extract_data_csv(args.csv_dir)

        # Step 2: Map to AWS Supply Chain Data Model
        aws_data = map_to_aws_model(extracted_data)

        # Step 3: Run simulation optimization
        optimization_results = run_simulation_optimization(aws_data)

        # Step 4: Write results back to SAP
        write_results = write_results_to_sap(
            optimization_results,
            args.output_dir,
            connection=None  # Use CSV mode for writing
        )

        logger.info("=" * 60)
        logger.info("Integration Complete!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Integration failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
