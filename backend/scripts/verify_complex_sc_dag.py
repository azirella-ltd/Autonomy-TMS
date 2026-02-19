#!/usr/bin/env python3
"""
Verify Complex SC DAG Traversal

This script demonstrates that the Complex SC configuration now has complete
DAG traversal from finished goods to bought materials via ProductBom.

Run:
    docker compose exec backend python scripts/verify_complex_sc_dag.py
"""

from app.db.base_class import SessionLocal
from app.models.sc_entities import Product, ProductBom
from app.models.supply_chain_config import SupplyChainConfig
from sqlalchemy import func
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def verify_dag_traversal():
    """Verify complete DAG traversal for Complex SC"""

    db = SessionLocal()

    try:
        logger.info("=== Complex SC DAG Traversal Verification ===\n")

        # Find Complex SC config
        config = db.query(SupplyChainConfig).filter(
            SupplyChainConfig.name.ilike('%complex%')
        ).first()

        if not config:
            logger.error("Complex SC config not found!")
            return False

        logger.info(f"Config: {config.name} (ID: {config.id})\n")

        # Get all finished goods
        finished_goods = db.query(Product).filter(
            Product.config_id == config.id,
            Product.product_type == 'finished_good'
        ).order_by(Product.id).all()

        logger.info(f"Testing DAG traversal for {len(finished_goods)} finished goods:\n")

        all_traversable = True
        total_paths = 0

        for fg in finished_goods:
            logger.info(f"📦 {fg.id}: {fg.description}")

            # Level 1: Get components
            boms = db.query(ProductBom).filter(
                ProductBom.product_id == fg.id
            ).all()

            if not boms:
                logger.error(f"  ❌ NO COMPONENTS - DAG traversal fails at {fg.id}")
                all_traversable = False
                continue

            logger.info(f"  └─ {len(boms)} components:")

            for bom in boms:
                component = db.query(Product).filter(
                    Product.id == bom.component_product_id
                ).first()

                if not component:
                    logger.error(f"    ❌ Component {bom.component_product_id} not found!")
                    all_traversable = False
                    continue

                key_flag = " [KEY MATERIAL]" if bom.is_key_material == 'true' else ""
                logger.info(f"     ├─ {bom.component_quantity}x {component.id} ({component.product_type}){key_flag}")

                # Check if component has further BOM (multi-level check)
                sub_boms = db.query(ProductBom).filter(
                    ProductBom.product_id == component.id
                ).count()

                if sub_boms > 0:
                    logger.info(f"     │  └─ Has {sub_boms} sub-components (multi-level BOM)")

                total_paths += 1

        logger.info("\n" + "="*80)
        logger.info("Verification Summary")
        logger.info("="*80)

        # Product counts
        fg_count = db.query(Product).filter(
            Product.config_id == config.id,
            Product.product_type == 'finished_good'
        ).count()

        comp_count = db.query(Product).filter(
            Product.config_id == config.id,
            Product.product_type == 'component'
        ).count()

        total_products = db.query(Product).filter(
            Product.config_id == config.id
        ).count()

        logger.info(f"\nProducts:")
        logger.info(f"  Finished Goods:  {fg_count}")
        logger.info(f"  Components:      {comp_count}")
        logger.info(f"  Total:           {total_products}")

        # BOM counts
        total_boms = db.query(ProductBom).filter(
            ProductBom.product_id.in_([p.id for p in finished_goods])
        ).count()

        key_materials = db.query(ProductBom).filter(
            ProductBom.product_id.in_([p.id for p in finished_goods]),
            ProductBom.is_key_material == 'true'
        ).count()

        logger.info(f"\nBOMs:")
        logger.info(f"  Total BOM entries:     {total_boms}")
        logger.info(f"  Key materials:         {key_materials}")
        logger.info(f"  Traversal paths:       {total_paths}")

        # Completeness checks
        logger.info(f"\nCompleteness:")
        logger.info(f"  Expected products:     40 (10 FGs + 30 components)")
        logger.info(f"  Actual products:       {total_products}")
        logger.info(f"  Status:                {'✅ MATCH' if total_products == 40 else '❌ MISMATCH'}")

        logger.info(f"\n  Expected BOMs:         30 (10 FGs × 3 components)")
        logger.info(f"  Actual BOMs:           {total_boms}")
        logger.info(f"  Status:                {'✅ MATCH' if total_boms == 30 else '❌ MISMATCH'}")

        logger.info(f"\n  Expected key materials: 30")
        logger.info(f"  Actual key materials:   {key_materials}")
        logger.info(f"  Status:                {'✅ MATCH' if key_materials == 30 else '❌ MISMATCH'}")

        # Final verdict
        logger.info("\n" + "="*80)
        if all_traversable and total_products == 40 and total_boms == 30 and key_materials == 30:
            logger.info("✅ DAG TRAVERSAL: COMPLETE")
            logger.info("✅ All finished goods can be exploded to components")
            logger.info("✅ All components exist as Products")
            logger.info("✅ All key materials flagged correctly")
            logger.info("✅ Complex SC is ready for MPS key material planning")
            return True
        else:
            logger.error("❌ DAG TRAVERSAL: INCOMPLETE")
            logger.error("❌ Some checks failed - review output above")
            return False

    except Exception as e:
        logger.error(f"Error during verification: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = verify_dag_traversal()
    exit(0 if success else 1)
