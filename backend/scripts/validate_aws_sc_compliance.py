#!/usr/bin/env python3
"""
AWS SC 100% Compliance Validation Script

Validates that all AWS SC certification features are properly implemented:
✅ Priority 1: Hierarchical overrides (6/5/3 levels)
✅ Priority 2: All 4 policy types
✅ Priority 3: Vendor management entities and FKs
✅ Priority 4: Sourcing schedules
✅ Priority 5: Advanced manufacturing features

Returns exit code 0 if all validations pass, 1 if any fail.
"""

import asyncio
import sys
from sqlalchemy import text, inspect as sql_inspect
from app.db.session import engine


class ComplianceValidator:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.total_checks = 0

    def check(self, name: str, condition: bool, details: str = ""):
        """Record validation check result"""
        self.total_checks += 1
        if condition:
            self.passed.append((name, details))
            print(f"  ✅ {name}")
            if details:
                print(f"     {details}")
        else:
            self.failed.append((name, details))
            print(f"  ❌ {name}")
            if details:
                print(f"     {details}")

    def print_summary(self):
        """Print validation summary"""
        print("\n" + "="*70)
        print("COMPLIANCE VALIDATION SUMMARY")
        print("="*70)
        print(f"\n✅ Passed: {len(self.passed)}/{self.total_checks}")
        print(f"❌ Failed: {len(self.failed)}/{self.total_checks}")

        if self.failed:
            print("\n⚠️  Failed Checks:")
            for name, details in self.failed:
                print(f"  • {name}")
                if details:
                    print(f"    {details}")

        compliance_pct = (len(self.passed) / self.total_checks * 100) if self.total_checks > 0 else 0
        print(f"\n🎯 Overall Compliance: {compliance_pct:.1f}%")

        if compliance_pct == 100:
            print("\n🎉 AWS SC 100% CERTIFIED! 🎉\n")
            return 0
        else:
            print(f"\n⚠️  Compliance incomplete: {100-compliance_pct:.1f}% remaining\n")
            return 1


async def validate_compliance():
    """Run all compliance validation checks"""

    validator = ComplianceValidator()

    print("\n" + "="*70)
    print("AWS SUPPLY CHAIN COMPLIANCE VALIDATION")
    print("="*70 + "\n")

    async with engine.connect() as conn:
        # ================================================================
        # Priority 1: Hierarchical Override Fields
        # ================================================================
        print("🎯 PRIORITY 1: Hierarchical Override Fields")
        print("-"*70)

        # Check nodes hierarchical fields
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='beer_game' AND table_name='nodes' "
            "AND column_name IN ('geo_id', 'segment_id', 'company_id')"
        ))
        node_fields = {row[0] for row in result}
        validator.check(
            "Nodes: geo_id, segment_id, company_id",
            len(node_fields) == 3,
            f"Found: {', '.join(node_fields)}"
        )

        # Check items product_group_id
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='beer_game' AND table_name='items' "
            "AND column_name='product_group_id'"
        ))
        validator.check(
            "Items: product_group_id",
            result.rowcount > 0
        )

        # Check inv_policy hierarchical fields
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='beer_game' AND table_name='inv_policy' "
            "AND column_name IN ('product_group_id', 'dest_geo_id', 'segment_id', 'company_id')"
        ))
        inv_policy_fields = {row[0] for row in result}
        validator.check(
            "InvPolicy: 6-level hierarchy fields",
            len(inv_policy_fields) == 4,
            f"Found: {', '.join(inv_policy_fields)}"
        )

        # ================================================================
        # Priority 2: Policy Types
        # ================================================================
        print("\n🎯 PRIORITY 2: AWS SC Policy Types")
        print("-"*70)

        # Check policy type fields
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='beer_game' AND table_name='inv_policy' "
            "AND column_name IN ('ss_policy', 'ss_days', 'ss_quantity', 'policy_value')"
        ))
        policy_fields = {row[0] for row in result}
        validator.check(
            "InvPolicy: Policy type fields (ss_policy, ss_days, ss_quantity, policy_value)",
            len(policy_fields) == 4,
            f"Found: {', '.join(policy_fields)}"
        )

        # Check for policies with each type
        for policy_type in ['abs_level', 'doc_dem', 'doc_fcst', 'sl']:
            result = await conn.execute(text(
                f"SELECT COUNT(*) FROM inv_policy WHERE ss_policy = '{policy_type}'"
            ))
            count = result.scalar()
            validator.check(
                f"Policy type '{policy_type}' examples exist",
                count > 0,
                f"Found {count} policies"
            )

        # ================================================================
        # Priority 3: Vendor Management
        # ================================================================
        print("\n🎯 PRIORITY 3: Vendor Management")
        print("-"*70)

        # Check vendor_product table
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='beer_game' AND table_name='vendor_product'"
        ))
        validator.check(
            "VendorProduct table exists",
            result.scalar() > 0
        )

        # Check vendor_product FKs
        result = await conn.execute(text(
            "SELECT constraint_name FROM information_schema.key_column_usage "
            "WHERE table_schema='beer_game' AND table_name='vendor_product' "
            "AND referenced_table_name IS NOT NULL"
        ))
        fks = {row[0] for row in result}
        validator.check(
            "VendorProduct: FK constraints",
            len(fks) >= 2,
            f"Found {len(fks)} FKs (tpartner_id, product_id)"
        )

        # Check sourcing_rules FKs
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='beer_game' AND table_name='sourcing_rules' "
            "AND column_name IN ('tpartner_id', 'transportation_lane_id', 'production_process_id')"
        ))
        sr_fk_fields = {row[0] for row in result}
        validator.check(
            "SourcingRules: FK fields added",
            len(sr_fk_fields) == 3,
            f"Found: {', '.join(sr_fk_fields)}"
        )

        # Check vendor_product data
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM vendor_product"
        ))
        vp_count = result.scalar()
        validator.check(
            "VendorProduct: Sample data exists",
            vp_count > 0,
            f"Found {vp_count} vendor products"
        )

        # ================================================================
        # Priority 4: Sourcing Schedules
        # ================================================================
        print("\n🎯 PRIORITY 4: Sourcing Schedules")
        print("-"*70)

        # Check sourcing_schedule table
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='beer_game' AND table_name='sourcing_schedule'"
        ))
        validator.check(
            "SourcingSchedule table exists",
            result.scalar() > 0
        )

        # Check sourcing_schedule_details table
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='beer_game' AND table_name='sourcing_schedule_details'"
        ))
        validator.check(
            "SourcingScheduleDetails table exists",
            result.scalar() > 0
        )

        # Check schedule detail fields
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='beer_game' AND table_name='sourcing_schedule_details' "
            "AND column_name IN ('day_of_week', 'week_of_month', 'schedule_date')"
        ))
        sched_fields = {row[0] for row in result}
        validator.check(
            "Schedule: Timing fields (day_of_week, week_of_month, schedule_date)",
            len(sched_fields) == 3,
            f"Found: {', '.join(sched_fields)}"
        )

        # Check order_up_to_level field
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='beer_game' AND table_name='inv_policy' "
            "AND column_name='order_up_to_level'"
        ))
        validator.check(
            "InvPolicy: order_up_to_level field",
            result.rowcount > 0
        )

        # ================================================================
        # Priority 5: Advanced Features
        # ================================================================
        print("\n🎯 PRIORITY 5: Advanced Manufacturing Features")
        print("-"*70)

        # Check production_process advanced fields
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='beer_game' AND table_name='production_process' "
            "AND column_name IN ('frozen_horizon_days', 'setup_time', 'changeover_time', "
            "'changeover_cost', 'min_batch_size', 'max_batch_size')"
        ))
        adv_fields = {row[0] for row in result}
        validator.check(
            "ProductionProcess: Advanced fields (6 total)",
            len(adv_fields) == 6,
            f"Found: {', '.join(adv_fields)}"
        )

        # Check BOM alternate support
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='beer_game' AND table_name='product_bom' "
            "AND column_name IN ('alternate_group', 'priority')"
        ))
        bom_fields = {row[0] for row in result}
        validator.check(
            "ProductBom: Alternate support (alternate_group, priority)",
            len(bom_fields) == 2,
            f"Found: {', '.join(bom_fields)}"
        )

        # ================================================================
        # Overall System Checks
        # ================================================================
        print("\n🎯 OVERALL SYSTEM VALIDATION")
        print("-"*70)

        # Check all migrations applied
        result = await conn.execute(text(
            "SELECT version_num FROM alembic_version"
        ))
        current_version = result.scalar()
        validator.check(
            "Database migrations current",
            current_version == '20260110_advanced_feat',
            f"Current version: {current_version}"
        )

        # Check for data integrity (FK constraints)
        result = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.table_constraints "
            "WHERE table_schema='beer_game' AND constraint_type='FOREIGN KEY' "
            "AND table_name IN ('vendor_product', 'sourcing_rules', 'sourcing_schedule', "
            "'sourcing_schedule_details', 'inv_policy')"
        ))
        fk_count = result.scalar()
        validator.check(
            "Foreign key constraints in place",
            fk_count >= 5,
            f"Found {fk_count} FK constraints"
        )

        # Check indexes for performance
        result = await conn.execute(text(
            "SELECT COUNT(DISTINCT index_name) FROM information_schema.statistics "
            "WHERE table_schema='beer_game' "
            "AND table_name IN ('vendor_product', 'sourcing_schedule', 'sourcing_schedule_details')"
        ))
        index_count = result.scalar()
        validator.check(
            "Performance indexes created",
            index_count >= 5,
            f"Found {index_count} indexes"
        )

    # Print summary and return result
    return validator.print_summary()


if __name__ == "__main__":
    exit_code = asyncio.run(validate_compliance())
    sys.exit(exit_code)
