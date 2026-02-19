#!/usr/bin/env python3
"""
Intelligent SAP Data Load with Claude AI Assistance.

Features:
- Automatic schema validation
- Claude AI for Z-fields and missing data
- Delta loading for daily updates
- Auto-fixing of data quality issues
- Comprehensive reporting

Usage:
    # Initial load (full extract with validation)
    python intelligent_sap_load.py --mode initial --source csv --csv-dir /data/sap/csv

    # Daily load (delta only with net change)
    python intelligent_sap_load.py --mode daily --source csv --csv-dir /data/sap/csv

    # With Claude AI (requires ANTHROPIC_API_KEY)
    python intelligent_sap_load.py --mode initial --source csv --csv-dir /data/sap/csv --claude

    # RFC connection
    python intelligent_sap_load.py --mode daily --source rfc \\
        --s4-host sap.company.com --s4-user USER --s4-passwd PASS
"""

import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.integrations.sap import (
    create_intelligent_loader,
    S4HANAConnector,
    S4HANAConnectionConfig,
    CSVDataLoader,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Intelligent SAP Data Load with AI Assistance"
    )

    # Load configuration
    parser.add_argument(
        "--mode",
        choices=["initial", "daily"],
        required=True,
        help="Load mode: initial (full) or daily (delta)"
    )
    parser.add_argument(
        "--source",
        choices=["rfc", "csv"],
        required=True,
        help="Data source: rfc (direct) or csv (files)"
    )

    # CSV source options
    parser.add_argument("--csv-dir", type=str, help="CSV directory path")

    # RFC source options
    parser.add_argument("--s4-host", type=str, help="S/4HANA hostname")
    parser.add_argument("--s4-sysnr", type=str, help="S/4HANA system number")
    parser.add_argument("--s4-client", type=str, help="S/4HANA client")
    parser.add_argument("--s4-user", type=str, help="S/4HANA username")
    parser.add_argument("--s4-passwd", type=str, help="S/4HANA password")

    # Claude AI options
    parser.add_argument(
        "--claude",
        action="store_true",
        help="Enable Claude AI assistance (requires ANTHROPIC_API_KEY)"
    )
    parser.add_argument(
        "--claude-api-key",
        type=str,
        help="Anthropic API key (or set ANTHROPIC_API_KEY env var)"
    )

    # Delta loading options
    parser.add_argument(
        "--no-delta",
        action="store_true",
        help="Disable delta loading (force full load)"
    )
    parser.add_argument(
        "--reset-delta",
        action="store_true",
        help="Reset delta state (force full load next time)"
    )

    # Output options
    parser.add_argument(
        "--report-dir",
        type=str,
        default="./reports",
        help="Directory for validation reports"
    )
    parser.add_argument(
        "--delta-state-dir",
        type=str,
        default="./delta_state",
        help="Directory for delta state files"
    )

    # Table selection
    parser.add_argument(
        "--tables",
        type=str,
        nargs="+",
        help="Specific tables to load (default: all standard tables)"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.source == "csv" and not args.csv_dir:
        parser.error("--csv-dir required when using CSV source")
    if args.source == "rfc" and not all([args.s4_host, args.s4_user, args.s4_passwd]):
        parser.error("RFC connection requires --s4-host, --s4-user, --s4-passwd")

    logger.info("=" * 70)
    logger.info("Intelligent SAP Data Load")
    logger.info("=" * 70)
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Source: {args.source}")
    logger.info(f"Claude AI: {'Enabled' if args.claude else 'Disabled'}")
    logger.info(f"Delta Loading: {'Disabled' if args.no_delta else 'Enabled'}")
    logger.info("=" * 70)

    try:
        # Step 1: Create intelligent loader
        claude_key = args.claude_api_key or os.getenv("ANTHROPIC_API_KEY")

        loader = create_intelligent_loader(
            mode=args.mode,
            connection_type=args.source,
            use_claude=args.claude,
            enable_delta=not args.no_delta,
            claude_api_key=claude_key,
            report_dir=args.report_dir,
            delta_state_dir=args.delta_state_dir,
            auto_fix=True,
            save_reports=True
        )

        # Step 2: Reset delta state if requested
        if args.reset_delta and loader.delta_extractor:
            logger.info("Resetting delta state...")
            loader.delta_extractor.reset_delta_state()

        # Step 3: Create data source
        if args.source == "csv":
            logger.info(f"Loading from CSV directory: {args.csv_dir}")
            data_source = CSVDataLoader(args.csv_dir)

            # List available tables
            available_tables = data_source.list_available_tables()
            logger.info(f"Available tables: {available_tables}")

        else:  # RFC
            logger.info(f"Connecting to S/4HANA: {args.s4_host}")
            config = S4HANAConnectionConfig(
                ashost=args.s4_host,
                sysnr=args.s4_sysnr or "00",
                client=args.s4_client or "100",
                user=args.s4_user,
                passwd=args.s4_passwd
            )
            data_source = S4HANAConnector(config)
            data_source.connect()

        # Step 4: Determine tables to load
        if args.tables:
            tables_to_load = args.tables
        else:
            # Standard S/4HANA tables
            tables_to_load = [
                "MARA",  # Materials
                "MARC",  # Material plant data
                "MARD",  # Inventory
                "EKKO",  # PO headers
                "EKPO",  # PO items
                "VBAK",  # SO headers
                "VBAP",  # SO items
                "LIKP",  # Delivery headers
                "LIPS",  # Delivery items
            ]

        logger.info(f"Tables to load: {tables_to_load}")

        # Step 5: Load tables with intelligent processing
        logger.info("\n" + "=" * 70)
        logger.info("Starting Table Loads")
        logger.info("=" * 70 + "\n")

        results = loader.load_multiple_tables(
            table_names=tables_to_load,
            data_source=data_source
        )

        # Step 6: Display results
        logger.info("\n" + "=" * 70)
        logger.info("Load Results Summary")
        logger.info("=" * 70 + "\n")

        for table_name, (df, result) in results.items():
            logger.info(f"{table_name}:")
            logger.info(f"  Records: {result.records_loaded}")
            logger.info(f"  Mode: {result.load_mode}")
            logger.info(f"  Auto-fixes: {result.records_fixed}")
            logger.info(f"  Z-fields: {result.z_fields_found}")
            logger.info(f"  Issues: {result.validation_issues}")
            logger.info(f"  Time: {result.execution_time_seconds:.2f}s")

            if result.delta_result:
                dr = result.delta_result
                logger.info(f"  Delta - New: {dr.new_records}, Changed: {dr.changed_records}")

            if result.claude_used and result.validation_analysis:
                if result.validation_analysis.claude_suggestions:
                    logger.info("  Claude AI: Recommendations provided")

            logger.info("")

        # Step 7: Display Z-field insights (if Claude was used)
        if args.claude:
            logger.info("=" * 70)
            logger.info("Z-Field Insights (Claude AI)")
            logger.info("=" * 70 + "\n")

            for table_name, (df, result) in results.items():
                if result.z_fields_found > 0 and result.validation_analysis:
                    z_recs = result.validation_analysis.claude_suggestions.get("z_fields", {})
                    if z_recs:
                        logger.info(f"{table_name} Z-Fields:")
                        for field, rec in list(z_recs.items())[:5]:  # Show first 5
                            logger.info(f"  {field}:")
                            logger.info(f"    Purpose: {rec.get('purpose', 'N/A')}")
                            logger.info(f"    Confidence: {rec.get('confidence', 'N/A')}")
                        logger.info("")

        # Step 8: Display auto-fix summary
        all_fixes = []
        for table_name, (df, result) in results.items():
            if result.auto_fixes_applied:
                all_fixes.extend([f"{table_name}: {fix}" for fix in result.auto_fixes_applied])

        if all_fixes:
            logger.info("=" * 70)
            logger.info("Auto-Fixes Applied")
            logger.info("=" * 70)
            for fix in all_fixes:
                logger.info(f"  - {fix}")
            logger.info("")

        # Step 9: Overall statistics
        total_records = sum(r[1].records_loaded for r in results.values())
        total_fixes = sum(r[1].records_fixed for r in results.values())
        total_z_fields = sum(r[1].z_fields_found for r in results.values())
        total_issues = sum(r[1].validation_issues for r in results.values())
        total_time = sum(r[1].execution_time_seconds for r in results.values())

        logger.info("=" * 70)
        logger.info("Overall Summary")
        logger.info("=" * 70)
        logger.info(f"Tables Loaded: {len(results)}")
        logger.info(f"Total Records: {total_records:,}")
        logger.info(f"Total Auto-Fixes: {total_fixes}")
        logger.info(f"Total Z-Fields: {total_z_fields}")
        logger.info(f"Total Issues: {total_issues}")
        logger.info(f"Total Time: {total_time:.2f}s")
        logger.info(f"Avg Time/Table: {total_time/len(results):.2f}s")

        if args.mode == "daily" and not args.no_delta:
            total_new = sum(
                r[1].delta_result.new_records
                for r in results.values()
                if r[1].delta_result
            )
            total_changed = sum(
                r[1].delta_result.changed_records
                for r in results.values()
                if r[1].delta_result
            )
            logger.info(f"\nDelta Summary:")
            logger.info(f"  New Records: {total_new}")
            logger.info(f"  Changed Records: {total_changed}")

        logger.info("\n" + "=" * 70)
        logger.info("Load Complete!")
        logger.info(f"Reports saved to: {args.report_dir}")
        logger.info("=" * 70)

        # Cleanup
        if args.source == "rfc":
            data_source.disconnect()

        return 0

    except KeyboardInterrupt:
        logger.info("\nLoad interrupted by user")
        return 1

    except Exception as e:
        logger.error(f"Load failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
