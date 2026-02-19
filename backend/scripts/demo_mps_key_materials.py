#!/usr/bin/env python3
"""
Demo script for MPS Key Material BOM Explosion

This script demonstrates the complete MPS key material feature:
1. Creates sample BOM data with key materials flagged
2. Creates an MPS plan with finished goods
3. Explodes key materials (rough-cut planning)
4. Displays the results

Usage:
    python scripts/demo_mps_key_materials.py
"""

import sys
from pathlib import Path

# Add backend to Python path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from app.models.mps import MPSPlan, MPSPlanItem, MPSStatus, MPSKeyMaterialRequirement
from app.models.sc_entities import ProductBom, Product
from app.models.supply_chain_config import Item, Node
from datetime import datetime, timedelta


def create_sample_bom_data(db: Session):
    """Create sample BOM structure with key materials"""
    print("\n" + "="*80)
    print("STEP 1: Creating Sample BOM Data")
    print("="*80)

    # Check if products already exist
    existing = db.query(Product).filter(Product.id == 'FG-001').first()
    if existing:
        print("[info] Sample products already exist, skipping creation")
        return

    # Create sample products
    products = [
        Product(id='FG-001', description='Finished Good - Beer Case', product_type='finished_good', base_uom='EA', is_active='true'),
        Product(id='FG-002', description='Finished Good - Six Pack', product_type='component', base_uom='EA', is_active='true'),
        Product(id='COMP-001', description='Aluminum Can', product_type='raw_material', base_uom='EA', is_active='true'),
        Product(id='COMP-002', description='Cardboard Box', product_type='raw_material', base_uom='EA', is_active='true'),
        Product(id='COMP-003', description='Beer (Liquid)', product_type='raw_material', base_uom='L', is_active='true'),
    ]

    for product in products:
        db.add(product)

    db.commit()
    print(f"[success] Created {len(products)} sample products")

    # Create BOM structure
    boms = [
        # Level 1: Beer Case contains 4 Six Packs and 1 Cardboard Box
        ProductBom(product_id='FG-001', component_product_id='FG-002', component_quantity=4, scrap_percentage=2.0, is_key_material='false'),
        ProductBom(product_id='FG-001', component_product_id='COMP-002', component_quantity=1, scrap_percentage=5.0, is_key_material='true'),
        # Level 2: Six Pack contains 6 Cans and Beer
        ProductBom(product_id='FG-002', component_product_id='COMP-001', component_quantity=6, scrap_percentage=1.0, is_key_material='true'),
        ProductBom(product_id='FG-002', component_product_id='COMP-003', component_quantity=2.0, scrap_percentage=0.5, is_key_material='true'),
    ]

    for bom in boms:
        db.add(bom)

    db.commit()
    print(f"[success] Created {len(boms)} BOM entries")

    # Display BOM structure
    print("\n[info] BOM Structure:")
    bom_records = db.query(ProductBom).all()
    for bom in bom_records:
        parent = db.query(Product).filter(Product.id == bom.product_id).first()
        component = db.query(Product).filter(Product.id == bom.component_product_id).first()
        key_flag = "✓ KEY" if bom.is_key_material == 'true' else ""
        print(f"  {parent.description} → {component.description} (qty: {bom.component_quantity}, scrap: {bom.scrap_percentage}%) {key_flag}")


def create_mps_plan(db: Session):
    """Create an MPS plan with finished goods"""
    print("\n" + "="*80)
    print("STEP 2: Creating MPS Plan")
    print("="*80)

    # Get first node and item
    node = db.query(Node).first()
    item = db.query(Item).first()

    if not node or not item:
        print("[error] No nodes or items found in database")
        return None

    # Create MPS plan
    plan = MPSPlan(
        supply_chain_config_id=node.config_id,
        name="Demo MPS Plan - Key Materials",
        description="Demonstration of MPS key material BOM explosion",
        start_date=datetime.now(),
        end_date=datetime.now() + timedelta(weeks=12),
        status=MPSStatus.DRAFT,
        planning_horizon_weeks=12,
        bucket_size_days=7,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    print(f"[success] Created MPS plan '{plan.name}' (id={plan.id})")

    # Create MPS plan items for finished goods
    weekly_quantities = [100, 120, 150, 140, 130, 160, 170, 150, 140, 130, 120, 110]

    mps_item = MPSPlanItem(
        plan_id=plan.id,
        product_id=item.id,
        site_id=node.id,
        weekly_quantities=weekly_quantities,
    )
    db.add(mps_item)
    db.commit()
    db.refresh(mps_item)

    print(f"[success] Created MPS plan item for product '{item.name}' (id={mps_item.id})")
    print(f"[info] Weekly quantities: {weekly_quantities}")
    print(f"[info] Total quantity: {sum(weekly_quantities)} units")

    return plan


def explode_key_materials(db: Session, plan: MPSPlan):
    """Explode key materials for the MPS plan"""
    print("\n" + "="*80)
    print("STEP 3: Exploding Key Materials (Rough-Cut BOM)")
    print("="*80)

    # This would normally be called via the API endpoint
    # For demo purposes, we'll call the explosion function directly
    from app.api.endpoints.mps import explode_key_materials_for_mps

    # Get plan items
    plan_items = db.query(MPSPlanItem).filter(MPSPlanItem.plan_id == plan.id).all()

    if not plan_items:
        print("[error] No plan items found")
        return

    # Clear existing key material requirements
    db.query(MPSKeyMaterialRequirement).filter(
        MPSKeyMaterialRequirement.plan_id == plan.id
    ).delete()
    db.commit()

    # Explode key materials for each plan item
    all_key_materials = []
    for mps_item in plan_items:
        print(f"[info] Exploding BOM for MPS item {mps_item.id}...")
        key_materials = explode_key_materials_for_mps(
            db=db,
            plan=plan,
            mps_item=mps_item,
            current_level=1,
            max_levels=10
        )
        all_key_materials.extend(key_materials)

    # Save to database
    for key_mat in all_key_materials:
        db.add(key_mat)
    db.commit()

    print(f"[success] Exploded {len(all_key_materials)} key material requirements")

    return all_key_materials


def display_results(db: Session, plan: MPSPlan):
    """Display key material requirements"""
    print("\n" + "="*80)
    print("STEP 4: Key Material Requirements Summary")
    print("="*80)

    key_materials = db.query(MPSKeyMaterialRequirement).filter(
        MPSKeyMaterialRequirement.plan_id == plan.id
    ).all()

    if not key_materials:
        print("[warning] No key material requirements found")
        return

    print(f"\n[info] Found {len(key_materials)} key material requirements:\n")

    for i, key_mat in enumerate(key_materials, 1):
        # Get product and site names
        parent_product = db.query(Product).filter(Product.id == str(key_mat.parent_product_id)).first()
        key_material_product = db.query(Product).filter(Product.id == str(key_mat.key_material_product_id)).first()
        key_material_site = db.query(Node).filter(Node.id == key_mat.key_material_site_id).first()

        print(f"{i}. Key Material: {key_material_product.description if key_material_product else f'Product {key_mat.key_material_product_id}'}")
        print(f"   Parent: {parent_product.description if parent_product else f'Product {key_mat.parent_product_id}'}")
        print(f"   Site: {key_material_site.name if key_material_site else f'Site {key_mat.key_material_site_id}'}")
        print(f"   BOM Level: {key_mat.bom_level}")
        print(f"   Component Qty: {key_mat.component_quantity} (scrap: {key_mat.scrap_percentage}%)")
        print(f"   Total Gross Requirement: {key_mat.total_gross_requirement:.2f} units")
        print(f"   Flags: Bottleneck={key_mat.is_bottleneck}, Long Lead Time={key_mat.is_long_lead_time}, Strategic={key_mat.is_strategic}")
        print(f"   Procurement Lead Time: {key_mat.procurement_lead_time_days} days" if key_mat.procurement_lead_time_days else "   Procurement Lead Time: Not specified")
        print(f"   Weekly Requirements: {[f'{x:.1f}' for x in key_mat.weekly_gross_requirements[:6]]}...")
        print()


def main():
    """Main demonstration flow"""
    print("\n" + "="*80)
    print("MPS KEY MATERIAL BOM EXPLOSION DEMONSTRATION")
    print("="*80)
    print("\nThis demo shows the industry-standard rough-cut planning approach:")
    print("• MPS: Plans finished goods + key materials (strategic/rough-cut)")
    print("• MRP: Plans all components (tactical/detailed)")
    print("\nKey materials are critical components that require MPS-level planning:")
    print("• Long lead time items (>4 weeks)")
    print("• Bottleneck/constrained resources")
    print("• High-value components")
    print("• Strategic materials with limited suppliers")

    # Create synchronous database session
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg2://autonomy_user:change-me-user@db:5432/autonomy')
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        # Step 1: Create sample BOM data
        create_sample_bom_data(db)

        # Step 2: Create MPS plan
        plan = create_mps_plan(db)
        if not plan:
            return

        # Step 3: Explode key materials
        explode_key_materials(db, plan)

        # Step 4: Display results
        display_results(db, plan)

        print("\n" + "="*80)
        print("DEMONSTRATION COMPLETE")
        print("="*80)
        print("\n[info] Next steps:")
        print("  1. Use API endpoint POST /api/v1/mps/{plan_id}/explode-key-materials")
        print("  2. Use API endpoint GET /api/v1/mps/{plan_id}/key-materials")
        print("  3. Flag additional materials using scripts/flag_key_materials.py")
        print("  4. Integrate with MRP for detailed component planning")

    except Exception as e:
        print(f"\n[error] {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
