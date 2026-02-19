#!/usr/bin/env python3
"""
Seed script demonstrating AWS SC vendor management with FK references

Creates:
- Trading partners (vendors)
- Vendor-specific product pricing and lead times
- Sourcing rules with vendor FK references

This demonstrates Priority 3 implementation:
- TradingPartner entity
- VendorProduct entity with unit costs and lead times
- SourcingRules.tpartner_id FK references
"""

import asyncio
from datetime import datetime
from sqlalchemy import select
from decimal import Decimal

from app.db.session import SessionLocal
from app.models.supply_chain_config import SupplyChainConfig, Node, Item
from app.models.aws_sc_planning import SourcingRules, VendorProduct


async def seed_vendor_management():
    """Seed vendor management example data"""

    async with SessionLocal() as db:
        # Use existing "Default TBG" config (always exists from bootstrap)
        result = await db.execute(
            select(SupplyChainConfig).filter(
                SupplyChainConfig.name == "Default TBG"
            )
        )
        config = result.scalar_one_or_none()

        if not config:
            # Fallback to any config
            result = await db.execute(
                select(SupplyChainConfig).limit(1)
            )
            config = result.scalar_one_or_none()

        if not config:
            print("❌ No supply chain configs found. Please run db bootstrap first.")
            return

        print(f"✓ Using config: {config.name} (ID: {config.id})")

        # Get existing items from config
        result = await db.execute(
            select(Item).filter(Item.config_id == config.id).limit(3)
        )
        items = list(result.scalars().all())

        if not items:
            print("❌ No items found in config. Please ensure config is seeded.")
            return

        print(f"✓ Found {len(items)} items in config")

        # Get existing nodes from config
        result = await db.execute(
            select(Node).filter(Node.config_id == config.id).limit(3)
        )
        nodes = list(result.scalars().all())

        if not nodes:
            print("❌ No nodes found in config. Please ensure config is seeded.")
            return

        print(f"✓ Found {len(nodes)} nodes in config")

        # Create trading partners (vendors)
        vendors = await create_trading_partners(db)

        # Create vendor-specific product pricing and lead times
        await create_vendor_products(db, config.id, vendors, items)

        # Create sourcing rules with vendor FK references
        await create_sourcing_rules_with_vendors(db, config.id, vendors, items, nodes)

        print("\n✅ Vendor management seed complete!")
        print(f"   - {len(vendors)} trading partners created")
        print(f"   - Vendor products with pricing and lead times created")
        print(f"   - Sourcing rules with tpartner_id FK references created")


async def create_trading_partners(db):
    """Create trading partner (vendor) examples"""

    vendors = []

    vendor_configs = [
        {
            "description": "Global Manufacturing Co.",
            "country": "China",
            "tpartner_type": "supplier",
            "city": "Shenzhen",
            "state_prov": "Guangdong",
            "email": "orders@globalmanufacturing.com"
        },
        {
            "description": "Local Supplier Inc.",
            "country": "USA",
            "tpartner_type": "supplier",
            "city": "Portland",
            "state_prov": "Oregon",
            "email": "sales@localsupplier.com"
        },
        {
            "description": "Premium Components Ltd.",
            "country": "Germany",
            "tpartner_type": "supplier",
            "city": "Munich",
            "state_prov": "Bavaria",
            "email": "info@premiumcomponents.de"
        }
    ]

    # Note: TradingPartner table already exists from 20260107_aws_standard_entities.py
    # Use the existing model from aws_sc_planning.py
    from app.models.aws_sc_planning import TradingPartner
    from sqlalchemy import text

    for vendor_config in vendor_configs:
        # Check if vendor already exists
        result = await db.execute(
            text("SELECT id FROM trading_partner WHERE description = :desc LIMIT 1").bindparams(
                desc=vendor_config["description"]
            )
        )
        existing_row = result.fetchone()

        if not existing_row:
            # Insert using raw SQL (TradingPartner model exists but is complex)
            result = await db.execute(
                text("""
                    INSERT INTO trading_partner
                    (description, country, tpartner_type, city, state_prov, email, is_active, eff_start_date, eff_end_date)
                    VALUES (:desc, :country, :tpartner_type, :city, :state_prov, :email, 1, '2024-01-01', '9999-12-31')
                """).bindparams(
                    desc=vendor_config["description"],
                    country=vendor_config["country"],
                    tpartner_type=vendor_config["tpartner_type"],
                    city=vendor_config["city"],
                    state_prov=vendor_config["state_prov"],
                    email=vendor_config["email"]
                )
            )
            await db.commit()

            # Get the inserted ID
            result = await db.execute(
                text("SELECT id FROM trading_partner WHERE description = :desc ORDER BY id DESC LIMIT 1").bindparams(
                    desc=vendor_config["description"]
                )
            )
            vendor_id = result.scalar()
            vendors.append({"id": vendor_id, **vendor_config})
            print(f"  ✓ Created vendor: {vendor_config['description']} (ID: {vendor_id})")
        else:
            vendor_id = existing_row[0]
            vendors.append({"id": vendor_id, **vendor_config})
            print(f"  ✓ Using existing vendor: {vendor_config['description']} (ID: {vendor_id})")

    return vendors


async def create_vendor_products(db, config_id: int, vendors: list, items: list):
    """Create vendor-specific product pricing and lead times"""

    if not items:
        print("  ⚠️  No items found, skipping vendor_product creation")
        return

    vendor_products = []

    # Create vendor products for the first item (always exists)
    # Global Manufacturing Co. - Low cost, longer lead time
    vendor_products.append({
        "tpartner_id": vendors[0]["id"],
        "product_id": items[0].id,
        "vendor_product_id": f"GMC-{items[0].name}-001",
        "unit_cost": Decimal("10.50"),
        "currency_code": "USD",
        "lead_time_days": 45,
        "min_order_qty": Decimal("500"),
        "order_multiple": Decimal("100"),
        "is_preferred": "false"
    })

    # Local Supplier Inc. - Higher cost, shorter lead time, preferred
    vendor_products.append({
        "tpartner_id": vendors[1]["id"],
        "product_id": items[0].id,
        "vendor_product_id": f"LSI-{items[0].name}-101",
        "unit_cost": Decimal("15.00"),
        "currency_code": "USD",
        "lead_time_days": 7,
        "min_order_qty": Decimal("100"),
        "order_multiple": Decimal("50"),
        "is_preferred": "true"
    })

    # Premium Components Ltd. - Premium pricing, fastest delivery
    vendor_products.append({
        "tpartner_id": vendors[2]["id"],
        "product_id": items[0].id,
        "vendor_product_id": f"PCL-{items[0].name}-201",
        "unit_cost": Decimal("25.00"),
        "currency_code": "EUR",
        "lead_time_days": 3,
        "min_order_qty": Decimal("50"),
        "order_multiple": Decimal("10"),
        "is_preferred": "false"
    })

    # Insert vendor products
    for vp in vendor_products:
        # Check if already exists
        result = await db.execute(
            select(VendorProduct).filter(
                VendorProduct.config_id == config_id,
                VendorProduct.tpartner_id == vp["tpartner_id"],
                VendorProduct.product_id == vp["product_id"]
            )
        )
        existing = result.scalar_one_or_none()

        if not existing:
            vendor_product = VendorProduct(
                config_id=config_id,
                **vp,
                is_active="true",
                eff_start_date=datetime(2024, 1, 1),
                eff_end_date=datetime(9999, 12, 31)
            )
            db.add(vendor_product)
            print(f"  ✓ Created vendor_product: {vp['vendor_product_id']} "
                  f"(vendor={vp['tpartner_id']}, product={vp['product_id']}, "
                  f"cost={vp['unit_cost']}, LT={vp['lead_time_days']}d)")

    await db.commit()


async def create_sourcing_rules_with_vendors(db, config_id: int, vendors: list, items: list, nodes: list):
    """Create sourcing rules with vendor FK references"""

    if not items or not nodes:
        print("  ⚠️  No items or nodes found, skipping sourcing rules")
        return

    sourcing_rules = []

    # Sourcing rule from Local Supplier (preferred, priority 1)
    sourcing_rules.append({
        "config_id": config_id,
        "product_id": items[0].id,
        "site_id": nodes[0].id,  # Destination site
        "supplier_site_id": nodes[1].id if len(nodes) > 1 else nodes[0].id,  # Supplier site
        "sourcing_rule_type": "buy",
        "tpartner_id": vendors[1]["id"],  # Local Supplier Inc.
        "priority": 1,
        "allocation_percent": Decimal("70.00"),
        "unit_cost": Decimal("15.00"),
        "lead_time": 7
    })

    # Sourcing rule from Global Manufacturing (backup, priority 2)
    sourcing_rules.append({
        "config_id": config_id,
        "product_id": items[0].id,
        "site_id": nodes[0].id,  # Destination site
        "supplier_site_id": nodes[1].id if len(nodes) > 1 else nodes[0].id,  # Supplier site
        "sourcing_rule_type": "buy",
        "tpartner_id": vendors[0]["id"],  # Global Manufacturing Co.
        "priority": 2,
        "allocation_percent": Decimal("30.00"),
        "unit_cost": Decimal("10.50"),
        "lead_time": 45
    })

    # Insert sourcing rules
    for sr in sourcing_rules:
        # Check if already exists
        result = await db.execute(
            select(SourcingRules).filter(
                SourcingRules.config_id == config_id,
                SourcingRules.product_id == sr["product_id"],
                SourcingRules.site_id == sr["site_id"],
                SourcingRules.priority == sr["priority"]
            )
        )
        existing = result.scalar_one_or_none()

        if not existing:
            sourcing_rule = SourcingRules(**sr)
            db.add(sourcing_rule)
            print(f"  ✓ Created sourcing rule: product={sr['product_id']} → "
                  f"site={sr['site_id']}, vendor={sr['tpartner_id']}, "
                  f"priority={sr['priority']}")

    await db.commit()


if __name__ == "__main__":
    print("="*60)
    print("AWS SC Vendor Management Seed Script")
    print("="*60)
    print()

    asyncio.run(seed_vendor_management())

    print()
    print("="*60)
    print("Seed complete! You can now test:")
    print("  1. Vendor-specific pricing from vendor_product table")
    print("  2. Vendor-specific lead times from vendor_product table")
    print("  3. Sourcing rules with tpartner_id FK references")
    print("  4. Multi-vendor sourcing with allocation percentages")
    print("="*60)
