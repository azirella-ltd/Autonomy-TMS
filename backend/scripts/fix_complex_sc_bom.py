#!/usr/bin/env python3
"""
Fix Complex SC BOM Migration

This script creates the missing component products (Items 43-72) and extracts
BOM relationships from Node.attributes into the ProductBom table.

Background:
- Complex SC config has 10 finished goods (FG01-FG10)
- BOMs reference 30 component items (43-72) that were never created
- Migration script only processed Default TBG (Items 1-10)
- This script completes the migration for Complex SC

Run:
    docker compose exec backend python scripts/fix_complex_sc_bom.py
"""

from app.db.base_class import SessionLocal
from app.models.sc_entities import Product, ProductBom
from app.models.supply_chain_config import SupplyChainConfig, Node
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_complex_sc_bom():
    """Fix Complex SC BOM by creating missing components and ProductBom entries"""

    db = SessionLocal()

    try:
        logger.info("=== Complex SC BOM Fix Started ===")

        # Find Complex SC config
        config = db.query(SupplyChainConfig).filter(
            SupplyChainConfig.name.ilike('%complex%')
        ).first()

        if not config:
            logger.error("Complex SC config not found!")
            return

        logger.info(f"Found config: {config.name} (ID: {config.id})")

        # Step 1: Create component products (Items 43-72 → COMP43-COMP72)
        logger.info("\nStep 1: Creating 30 component products...")

        component_ids = list(range(43, 73))
        created_count = 0

        for item_id in component_ids:
            product_id = f"COMP{item_id}"

            # Check if already exists
            existing = db.query(Product).filter(Product.id == product_id).first()
            if existing:
                logger.info(f"  Product {product_id} already exists, skipping")
                continue

            # Create component product
            product = Product(
                id=product_id,
                description=f"Component {item_id} for Complex SC multi-region supply chain",
                company_id="DEFAULT",
                config_id=config.id,
                product_type="component",  # Mark as component (not raw_material yet)
                base_uom="EA",
                unit_cost=5.0,
                unit_price=7.0,
                is_active="true"
            )
            db.add(product)
            created_count += 1

            # Create item_product_mapping entry
            db.execute(text("""
                INSERT INTO item_product_mapping (item_id, product_id)
                VALUES (:item_id, :product_id)
                ON CONFLICT (item_id) DO NOTHING
            """), {"item_id": item_id, "product_id": product_id})

        db.commit()
        logger.info(f"  Created {created_count} component products")

        # Step 2: Extract BOMs from Node.attributes → ProductBom
        logger.info("\nStep 2: Extracting BOMs from Node attributes...")

        nodes_with_bom = db.query(Node).filter(
            Node.config_id == config.id
        ).all()

        bom_count = 0

        for node in nodes_with_bom:
            if not node.attributes or 'bill_of_materials' not in node.attributes:
                continue

            bom_data = node.attributes['bill_of_materials']
            logger.info(f"  Processing BOM from Node: {node.name}")

            for parent_item_id_str, components in bom_data.items():
                parent_item_id = int(parent_item_id_str)

                # Get parent product ID from mapping
                result = db.execute(text("""
                    SELECT product_id FROM item_product_mapping WHERE item_id = :item_id
                """), {"item_id": parent_item_id})
                parent_product_row = result.fetchone()

                if not parent_product_row:
                    logger.warning(f"    No product mapping for parent Item {parent_item_id}, skipping")
                    continue

                parent_product_id = parent_product_row[0]

                for comp_item_id_str, quantity in components.items():
                    comp_item_id = int(comp_item_id_str)

                    # Get component product ID from mapping
                    result = db.execute(text("""
                        SELECT product_id FROM item_product_mapping WHERE item_id = :item_id
                    """), {"item_id": comp_item_id})
                    comp_product_row = result.fetchone()

                    if not comp_product_row:
                        logger.warning(f"    No product mapping for component Item {comp_item_id}, skipping")
                        continue

                    comp_product_id = comp_product_row[0]

                    # Check if BOM entry already exists
                    existing_bom = db.query(ProductBom).filter(
                        ProductBom.product_id == parent_product_id,
                        ProductBom.component_product_id == comp_product_id
                    ).first()

                    if existing_bom:
                        logger.info(f"    BOM {parent_product_id} → {comp_product_id} already exists, skipping")
                        continue

                    # Create ProductBom entry
                    # Mark all leaf components as key materials (assume single-level BOM)
                    bom_entry = ProductBom(
                        product_id=parent_product_id,
                        component_product_id=comp_product_id,
                        component_quantity=float(quantity),
                        scrap_percentage=2.0,  # Default 2% scrap
                        is_key_material='true'  # All components are key materials (leaf nodes)
                    )
                    db.add(bom_entry)
                    bom_count += 1
                    logger.info(f"    Created BOM: {parent_product_id} → {quantity}x {comp_product_id} [KEY]")

        db.commit()
        logger.info(f"  Created {bom_count} ProductBom entries")

        # Step 3: Verification
        logger.info("\n=== Verification ===")

        # Count products
        product_count = db.query(Product).filter(Product.config_id == config.id).count()
        logger.info(f"Total products in Complex SC: {product_count}")
        logger.info(f"  Expected: 40 (10 FGs + 30 components)")

        # Count BOMs
        bom_result = db.execute(text("""
            SELECT COUNT(*) FROM product_bom
            WHERE product_id IN (
                SELECT id FROM product WHERE config_id = :config_id
            )
        """), {"config_id": config.id})
        total_boms = bom_result.scalar()
        logger.info(f"Total BOMs in Complex SC: {total_boms}")
        logger.info(f"  Expected: 30 (10 FGs × 3 components each)")

        # Count key materials
        key_result = db.execute(text("""
            SELECT COUNT(*) FROM product_bom
            WHERE is_key_material = 'true'
            AND product_id IN (
                SELECT id FROM product WHERE config_id = :config_id
            )
        """), {"config_id": config.id})
        key_materials = key_result.scalar()
        logger.info(f"Key materials flagged: {key_materials}")
        logger.info(f"  Expected: 30 (all components are leaf nodes)")

        # Sample BOM check
        logger.info("\nSample BOM verification (FG01):")
        fg01_boms = db.query(ProductBom).filter(
            ProductBom.product_id == "FG01"
        ).all()

        if fg01_boms:
            logger.info(f"  FG01 BOM entries: {len(fg01_boms)}")
            for bom in fg01_boms:
                logger.info(f"    - {bom.component_quantity}x {bom.component_product_id} (key={bom.is_key_material})")
        else:
            logger.warning("  FG01 has no BOM entries!")

        # Final status
        logger.info("\n=== Fix Complete ===")
        if product_count == 40 and total_boms == 30 and key_materials == 30:
            logger.info("✅ All checks passed! Complex SC BOM is now complete.")
            logger.info("✅ DAG traversal from FG to bought materials is now possible.")
        else:
            logger.warning("⚠️ Some checks did not match expected values. Review output above.")

    except Exception as e:
        logger.error(f"Error during fix: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    fix_complex_sc_bom()
