"""
Script to update AWS SC planning models with customer_id foreign keys

This script updates the SQLAlchemy models in aws_sc_planning.py to include
customer_id foreign key columns and composite indexes. This matches the database
schema changes from the 20260111_aws_sc_multi_tenancy migration.

Usage:
    python scripts/update_aws_sc_models_with_group_id.py
"""

import re
from pathlib import Path


def update_models():
    """Update aws_sc_planning.py models with customer_id"""

    model_file = Path(__file__).parent.parent / "app" / "models" / "aws_sc_planning.py"

    print(f"Reading {model_file}...")
    content = model_file.read_text()

    # Tables that need customer_id added (all tables with config_id)
    tables_to_update = [
        ('Forecast', 'forecast'),
        ('SupplyPlan', 'supply_plan'),
        ('ProductBom', 'product_bom'),
        ('ProductionProcess', 'production_process'),
        ('SourcingRules', 'sourcing_rules'),
        ('InvPolicy', 'inv_policy'),
        ('Reservation', 'reservation'),
        ('OutboundOrderLine', 'outbound_order_line'),
        ('VendorLeadTime', 'vendor_lead_time'),
        ('SupplyPlanningParameters', 'supply_planning_parameters'),
        ('VendorProduct', 'vendor_product'),
        ('SourcingSchedule', 'sourcing_schedule'),
        ('SourcingScheduleDetails', 'sourcing_schedule_details'),
    ]

    for class_name, table_name in tables_to_update:
        print(f"\nUpdating {class_name}...")

        # Pattern: find line with config_id and add customer_id before it
        # Match: config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))
        pattern = rf'(\s+)(config_id = Column\(Integer, ForeignKey\("supply_chain_configs\.id"\)\))'
        replacement = r'\1group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))\n\1\2'

        old_content = content
        content = re.sub(pattern, replacement, content, count=1)

        if content == old_content:
            print(f"  ⚠️  Already has customer_id or pattern not found for {class_name}")
        else:
            print(f"  ✓ Added customer_id to {class_name}")

        # Update __table_args__ to include composite index
        # Find the __table_args__ section for this class
        # Pattern: Index('idx_TABLENAME_config', 'config_id'),
        # Replace with: Index('idx_TABLENAME_group_config', 'customer_id', 'config_id'),\n        Index('idx_TABLENAME_config', 'config_id'),

        config_idx_pattern = rf"(Index\('idx_{table_name}_config', 'config_id'\))"
        config_idx_replacement = rf"Index('idx_{table_name}_group_config', 'customer_id', 'config_id'),\n        \1"

        old_content = content
        content = re.sub(config_idx_pattern, config_idx_replacement, content, count=1)

        if content == old_content:
            print(f"  ⚠️  Index might already exist or pattern not found for {class_name}")
        else:
            print(f"  ✓ Updated indexes for {class_name}")

    # Special handling for InvLevel - needs both customer_id and config_id added
    print(f"\nUpdating InvLevel...")

    # Find InvLevel class and add both columns
    inv_level_pattern = r'(class InvLevel\(Base\):.*?snapshot_date = Column\(DateTime.*?\n)'
    inv_level_match = re.search(inv_level_pattern, content, re.DOTALL)

    if inv_level_match:
        inv_level_section = inv_level_match.group(0)

        # Add customer_id and config_id before snapshot_date
        if 'customer_id' not in inv_level_section and 'config_id' not in inv_level_section:
            new_inv_level = inv_level_section.replace(
                'snapshot_date = Column(DateTime',
                'customer_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))\n    '
                'config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))\n    '
                'snapshot_date = Column(DateTime'
            )
            content = content.replace(inv_level_section, new_inv_level)
            print("  ✓ Added customer_id and config_id to InvLevel")
        else:
            print("  ⚠️  InvLevel already has customer_id or config_id")

    # Special handling for TradingPartner - needs both customer_id and config_id added
    print(f"\nUpdating TradingPartner...")

    # Find TradingPartner class and add both columns before created_at
    trading_partner_pattern = r'(class TradingPartner\(Base\):.*?created_at = Column\(DateTime)'
    trading_partner_match = re.search(trading_partner_pattern, content, re.DOTALL)

    if trading_partner_match:
        trading_partner_section = trading_partner_match.group(0)

        # Add customer_id and config_id before created_at
        if 'customer_id' not in trading_partner_section and 'config_id' not in trading_partner_section:
            # Find email line (last line before created_at)
            new_trading_partner = re.sub(
                r'(email = Column\(String\(255\)\)\n    website = Column\(String\(255\)\)\n)',
                r'\1    customer_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"))\n'
                r'    config_id = Column(Integer, ForeignKey("supply_chain_configs.id"))\n',
                trading_partner_section
            )
            content = content.replace(trading_partner_section, new_trading_partner)
            print("  ✓ Added customer_id and config_id to TradingPartner")

            # Add composite index to TradingPartner __table_args__
            tp_idx_pattern = r"(Index\('ix_trading_partner_is_active', 'is_active'\),)"
            tp_idx_replacement = r"\1\n        Index('idx_trading_partner_group_config', 'customer_id', 'config_id'),"
            content = re.sub(tp_idx_pattern, tp_idx_replacement, content, count=1)
            print("  ✓ Added composite index to TradingPartner")
        else:
            print("  ⚠️  TradingPartner already has customer_id or config_id")

    # Write updated content
    print(f"\nWriting updated models to {model_file}...")
    model_file.write_text(content)
    print("✅ Models updated successfully!")


if __name__ == "__main__":
    update_models()
