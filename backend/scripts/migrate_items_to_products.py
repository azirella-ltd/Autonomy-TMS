#!/usr/bin/env python3
"""
Data Migration Script: Items → AWS SC Product Table

This script migrates The Beer Game from the items table to the AWS Supply Chain
compliant product table, including:
1. Converting Item records to Product records with string IDs
2. Extracting BOMs from Node.attributes JSON to ProductBom table
3. Marking raw materials as key materials for MPS planning
4. Creating temporary mapping table for FK updates

Usage:
    python scripts/migrate_items_to_products.py [--dry-run] [--verbose]

Requirements:
    - Database must be running
    - Backup recommended before execution
    - Run from backend directory
"""

import sys
from pathlib import Path
import argparse
import logging
from typing import Dict, List, Tuple, Optional

# Add backend to Python path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from app.models.supply_chain_config import Item, Node
from app.models.sc_entities import Product, ProductBom
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """
    Convert item name to AWS SC product ID.

    Rules:
    - Uppercase
    - Remove hyphens
    - Remove spaces
    - Preserve alphanumeric characters

    Examples:
        "Case" → "CASE"
        "Six-Pack" → "SIXPACK"
        "Lager Case" → "LAGERCASE"
    """
    if not name:
        return ""

    # Convert to uppercase and remove special characters
    normalized = name.upper().replace("-", "").replace(" ", "")

    # Keep only alphanumeric characters
    normalized = ''.join(c for c in normalized if c.isalnum())

    return normalized


def determine_key_material(product_id: str) -> str:
    """
    Determine if component is a key material for MPS planning.

    Key materials are:
    - Raw materials (BOTTLE, INGREDIENTS, CAN, BOX)
    - Long lead time items
    - Bottleneck resources
    - Strategic materials

    Returns:
        'true' if key material, 'false' otherwise
    """
    # Raw materials that should be planned at MPS level
    key_materials = {
        "BOTTLE",
        "INGREDIENTS",
        "CAN",
        "BOX",
        "RAWMATERIAL",
        "COMPONENT"
    }

    return 'true' if product_id.upper() in key_materials else 'false'


def generate_product_id(item: Item, existing_ids: set, db: Session) -> str:
    """
    Generate unique product ID from item name.

    If collision occurs, append numeric suffix (e.g., CASE-002).
    """
    base_id = normalize_name(item.name)

    if not base_id:
        # Fallback: use item ID
        base_id = f"ITEM{item.id}"

    product_id = base_id
    counter = 2

    # Handle collisions
    while product_id in existing_ids:
        product_id = f"{base_id}{counter:03d}"
        counter += 1
        if counter > 999:
            raise ValueError(f"Too many collisions for base ID: {base_id}")

    existing_ids.add(product_id)
    return product_id


def create_mapping_table(db: Session) -> None:
    """Create temporary mapping table for item_id → product_id."""
    logger.info("Creating temporary mapping table...")

    db.execute(text("""
        CREATE TABLE IF NOT EXISTS item_product_mapping (
            item_id INTEGER PRIMARY KEY,
            product_id VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    db.commit()
    logger.info("Mapping table created.")


def ensure_default_company(db: Session, dry_run: bool = False) -> None:
    """Ensure DEFAULT company exists in company table."""
    from app.models.sc_entities import Company

    if dry_run:
        return

    # Check if DEFAULT company exists
    existing_company = db.query(Company).filter(Company.id == "DEFAULT").first()
    if not existing_company:
        logger.info("Creating DEFAULT company...")
        company = Company(
            id="DEFAULT",
            description="Default Beer Game Company"
        )
        db.add(company)
        db.commit()
        logger.info("✓ DEFAULT company created")
    else:
        logger.info("DEFAULT company already exists")


def migrate_items_to_products(db: Session, dry_run: bool = False) -> Dict[int, str]:
    """
    Migrate Item records to Product table.

    Returns:
        Dictionary mapping item_id → product_id
    """
    logger.info("=" * 80)
    logger.info("STEP 1: Migrating Items to Products")
    logger.info("=" * 80)

    # Query all items
    items = db.query(Item).all()
    logger.info(f"Found {len(items)} items to migrate")

    if len(items) == 0:
        logger.warning("No items found to migrate!")
        return {}

    # Track existing product IDs to avoid collisions
    existing_ids = set()
    existing_products = db.query(Product).all()
    for p in existing_products:
        existing_ids.add(p.id)

    mapping: Dict[int, str] = {}
    products_created = 0

    for item in items:
        # Generate product ID
        product_id = generate_product_id(item, existing_ids, db)
        mapping[item.id] = product_id

        # Determine product type based on name/description
        product_type = "finished_good"
        if "bottle" in item.name.lower() or "ingredient" in item.name.lower():
            product_type = "raw_material"
        elif "pack" in item.name.lower():
            product_type = "component"

        # Calculate unit cost from range
        unit_cost_range = item.unit_cost_range or {"min": 0, "max": 100}
        unit_cost = (unit_cost_range.get("min", 0) + unit_cost_range.get("max", 100)) / 2
        unit_price = unit_cost * 1.2  # 20% markup

        logger.info(f"  {item.name} (ID={item.id}) → {product_id} (type={product_type}, cost=${unit_cost:.2f})")

        if not dry_run:
            # Check if product already exists
            existing_product = db.query(Product).filter(Product.id == product_id).first()
            if existing_product:
                logger.warning(f"    Product {product_id} already exists, skipping creation")
                continue

            # Create Product record
            product = Product(
                id=product_id,
                description=item.description or item.name,
                company_id="DEFAULT",  # Default company
                config_id=item.config_id,  # Track original config
                product_type=product_type,
                base_uom="EA",  # Each (default unit)
                unit_cost=unit_cost,
                unit_price=unit_price,
                is_active="true"
            )
            db.add(product)
            products_created += 1

            # Record mapping
            db.execute(text("""
                INSERT INTO item_product_mapping (item_id, product_id)
                VALUES (:item_id, :product_id)
                ON CONFLICT (item_id) DO NOTHING
            """), {"item_id": item.id, "product_id": product_id})

    if not dry_run:
        db.commit()
        logger.info(f"✓ Created {products_created} product records")
    else:
        logger.info(f"[DRY RUN] Would create {len(items)} product records")

    return mapping


def extract_boms_to_product_bom(db: Session, mapping: Dict[int, str], dry_run: bool = False) -> int:
    """
    Extract BOMs from Node.attributes JSON to ProductBom table.

    Returns:
        Number of BOM entries created
    """
    logger.info("=" * 80)
    logger.info("STEP 2: Extracting BOMs from Node Attributes")
    logger.info("=" * 80)

    # Query nodes with BOMs
    nodes = db.query(Node).filter(
        Node.attributes.isnot(None)
    ).all()

    bom_entries_created = 0

    for node in nodes:
        attributes = node.attributes or {}
        bom_json = attributes.get("bill_of_materials", {})

        if not bom_json:
            continue

        logger.info(f"Processing BOMs for node: {node.name} (ID={node.id})")

        for parent_item_id_str, components_dict in bom_json.items():
            try:
                parent_item_id = int(parent_item_id_str)
            except ValueError:
                logger.warning(f"  Invalid parent item ID: {parent_item_id_str}")
                continue

            if parent_item_id not in mapping:
                logger.warning(f"  Parent item {parent_item_id} not found in mapping")
                continue

            parent_product_id = mapping[parent_item_id]

            for component_item_id_str, quantity in components_dict.items():
                try:
                    component_item_id = int(component_item_id_str)
                except ValueError:
                    logger.warning(f"  Invalid component item ID: {component_item_id_str}")
                    continue

                if component_item_id not in mapping:
                    logger.warning(f"  Component item {component_item_id} not found in mapping")
                    continue

                component_product_id = mapping[component_item_id]

                # Determine if key material
                is_key = determine_key_material(component_product_id)

                logger.info(f"  {parent_product_id} ← {component_product_id} (qty={quantity}, key={is_key})")

                if not dry_run:
                    # Check if BOM entry already exists
                    existing_bom = db.query(ProductBom).filter(
                        ProductBom.product_id == parent_product_id,
                        ProductBom.component_product_id == component_product_id
                    ).first()

                    if existing_bom:
                        logger.warning(f"    BOM entry already exists, skipping")
                        continue

                    # Create BOM entry
                    bom = ProductBom(
                        product_id=parent_product_id,
                        component_product_id=component_product_id,
                        component_quantity=float(quantity),
                        scrap_percentage=2.0,  # Default 2% scrap
                        is_key_material=is_key
                    )
                    db.add(bom)
                    bom_entries_created += 1

    if not dry_run:
        db.commit()
        logger.info(f"✓ Created {bom_entries_created} BOM entries")
    else:
        logger.info(f"[DRY RUN] Would create BOM entries")

    return bom_entries_created


def display_migration_summary(db: Session, mapping: Dict[int, str]) -> None:
    """Display summary of migrated data."""
    logger.info("=" * 80)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 80)

    # Count products
    product_count = db.query(Product).filter(Product.config_id.isnot(None)).count()
    logger.info(f"Products created: {product_count}")

    # Count BOM entries
    bom_count = db.query(ProductBom).count()
    logger.info(f"BOM entries created: {bom_count}")

    # Count key materials
    key_material_count = db.query(ProductBom).filter(ProductBom.is_key_material == 'true').count()
    logger.info(f"Key materials flagged: {key_material_count}")

    # Display product list
    logger.info("\nMigrated Products:")
    products = db.query(Product).filter(Product.config_id.isnot(None)).order_by(Product.id).all()
    for product in products:
        logger.info(f"  {product.id}: {product.description} (type={product.product_type})")

    # Display BOM hierarchy
    logger.info("\nBOM Hierarchy:")
    bom_entries = db.query(ProductBom).all()
    for bom in bom_entries:
        key_flag = "✓ KEY" if bom.is_key_material == 'true' else ""
        logger.info(f"  {bom.product_id} ← {bom.component_product_id} "
                   f"(qty={bom.component_quantity}, scrap={bom.scrap_percentage}%) {key_flag}")


def main():
    """Main migration flow."""
    parser = argparse.ArgumentParser(description="Migrate Items to AWS SC Product Table")
    parser.add_argument('--dry-run', action='store_true', help='Preview migration without making changes')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.info("=" * 80)
    logger.info("ITEMS → PRODUCT TABLE MIGRATION")
    logger.info("=" * 80)

    if args.dry_run:
        logger.warning("⚠️  DRY RUN MODE - No changes will be made")
    else:
        logger.warning("⚠️  LIVE MODE - Database will be modified")
        logger.warning("⚠️  Ensure you have a backup before proceeding!")
        response = input("\nContinue? [y/N]: ")
        if response.lower() != 'y':
            logger.info("Migration cancelled")
            return

    # Create database session
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg2://autonomy_user:change-me-user@db:5432/autonomy')
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Step 0: Ensure DEFAULT company exists
        ensure_default_company(db, dry_run=args.dry_run)

        # Step 1: Create mapping table
        if not args.dry_run:
            create_mapping_table(db)

        # Step 2: Migrate items to products
        mapping = migrate_items_to_products(db, dry_run=args.dry_run)

        if not mapping:
            logger.error("No items migrated. Aborting.")
            return

        # Step 3: Extract BOMs to ProductBom table
        bom_count = extract_boms_to_product_bom(db, mapping, dry_run=args.dry_run)

        # Step 4: Display summary
        if not args.dry_run:
            display_migration_summary(db, mapping)

        logger.info("=" * 80)
        logger.info("MIGRATION COMPLETE")
        logger.info("=" * 80)

        if not args.dry_run:
            logger.info("\nNext Steps:")
            logger.info("  1. Verify product records: SELECT * FROM product WHERE config_id IS NOT NULL;")
            logger.info("  2. Verify BOM entries: SELECT * FROM product_bom;")
            logger.info("  3. Test MPS key material explosion")
            logger.info("  4. Proceed with Phase 2: Model Layer Migration")
        else:
            logger.info("\nRun without --dry-run to apply changes")

    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        import traceback
        traceback.print_exc()
        if not args.dry_run:
            db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
