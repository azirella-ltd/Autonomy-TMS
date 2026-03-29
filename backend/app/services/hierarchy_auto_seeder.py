"""Auto-generate site and product hierarchies from supply chain config entities.

Called during the warm_start provisioning step. Idempotent — skips if hierarchy
nodes already exist for the tenant.

Hierarchy structure:
  Site:    Company → Region (by master_type) → Site
  Product: All Products → Category/Family → Product
"""
import logging
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.planning_hierarchy import SiteHierarchyNode, ProductHierarchyNode
from app.models.supply_chain_config import Site, SupplyChainConfig
from app.models.sc_entities import Product

logger = logging.getLogger(__name__)


def auto_seed_hierarchies(
    db: Session,
    config_id: int,
    tenant_id: int,
) -> dict:
    """Auto-generate site and product hierarchy trees from config entities.

    Returns dict with created=True/False, site_nodes, product_nodes counts.
    """
    site_result = _seed_site_hierarchy(db, config_id, tenant_id)
    product_result = _seed_product_hierarchy(db, config_id, tenant_id)

    created = site_result["created"] or product_result["created"]
    return {
        "created": created,
        "site_nodes": site_result["count"],
        "product_nodes": product_result["count"],
    }


def _seed_site_hierarchy(
    db: Session, config_id: int, tenant_id: int
) -> dict:
    """Create site hierarchy: Company → Region (by master_type) → Site."""
    existing = (
        db.query(SiteHierarchyNode)
        .filter(SiteHierarchyNode.tenant_id == tenant_id)
        .count()
    )
    if existing > 0:
        # Delete and recreate to handle partial/stale data from failed builds
        logger.info(
            "Site hierarchy exists for tenant %d (%d nodes) — clearing for fresh seed",
            tenant_id, existing,
        )
        db.query(SiteHierarchyNode).filter(
            SiteHierarchyNode.tenant_id == tenant_id
        ).delete()
        db.flush()

    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == config_id
    ).first()
    if not config:
        return {"created": False, "count": 0}

    sites = (
        db.query(Site)
        .filter(Site.config_id == config_id)
        .all()
    )
    if not sites:
        return {"created": False, "count": 0}

    config_name = config.name or f"Config {config_id}"
    company_code = f"COMPANY_{tenant_id}"

    # Root: Company
    company = SiteHierarchyNode(
        tenant_id=tenant_id,
        code=company_code,
        name=config_name,
        hierarchy_level="COMPANY",
        hierarchy_path=company_code,
        depth=0,
        parent_id=None,
    )
    db.add(company)
    db.flush()

    count = 1  # company node

    # Group sites by master_type for region nodes
    by_type = defaultdict(list)
    for s in sites:
        mt = s.master_type or s.dag_type or "OTHER"
        by_type[mt].append(s)

    _REGION_LABELS = {
        "VENDOR": "Suppliers",
        "CUSTOMER": "Customers",
        "INVENTORY": "Distribution Sites",
        "MANUFACTURER": "Manufacturing Sites",
    }

    _seen_codes: set = set()
    for mt, site_list in sorted(by_type.items()):
        region_code = f"REGION_{mt}_{tenant_id}"
        region_label = _REGION_LABELS.get(mt, mt.replace("_", " ").title())
        region = SiteHierarchyNode(
            tenant_id=tenant_id,
            code=region_code,
            name=region_label,
            hierarchy_level="REGION",
            hierarchy_path=f"{company_code}/{region_code}",
            depth=1,
            parent_id=company.id,
        )
        db.add(region)
        db.flush()
        count += 1

        for s in site_list:
            site_code = f"SITE_{s.name}_{tenant_id}"
            if site_code in _seen_codes:
                continue  # Skip duplicate site names
            _seen_codes.add(site_code)
            node = SiteHierarchyNode(
                tenant_id=tenant_id,
                code=site_code,
                name=s.name,
                hierarchy_level="SITE",
                hierarchy_path=f"{company_code}/{region_code}/{site_code}",
                depth=2,
                parent_id=region.id,
                site_id=s.id,
            )
            db.add(node)
            count += 1

    db.flush()
    logger.info(
        "Auto-seeded %d site hierarchy nodes for tenant %d (config %d)",
        count, tenant_id, config_id,
    )
    return {"created": True, "count": count}


def _seed_product_hierarchy(
    db: Session, config_id: int, tenant_id: int
) -> dict:
    """Create product hierarchy: All Products → Category/Family → Product."""
    existing = (
        db.query(ProductHierarchyNode)
        .filter(ProductHierarchyNode.tenant_id == tenant_id)
        .count()
    )
    if existing > 0:
        logger.info(
            "Product hierarchy exists for tenant %d (%d nodes) — clearing for fresh seed",
            tenant_id, existing,
        )
        db.query(ProductHierarchyNode).filter(
            ProductHierarchyNode.tenant_id == tenant_id
        ).delete()
        db.flush()

    products = (
        db.query(Product)
        .filter(Product.config_id == config_id)
        .all()
    )
    if not products:
        return {"created": False, "count": 0}

    root_code = f"ALL_PRODUCTS_{tenant_id}"
    root = ProductHierarchyNode(
        tenant_id=tenant_id,
        code=root_code,
        name="All Products",
        hierarchy_level="CATEGORY",
        hierarchy_path=root_code,
        depth=0,
        parent_id=None,
    )
    db.add(root)
    db.flush()

    count = 1  # root

    # Group by category or family fields from the Product model
    by_cat = defaultdict(list)
    for p in products:
        cat = p.category or p.family or p.product_group or p.product_type or "General"
        by_cat[cat].append(p)

    for cat, prod_list in sorted(by_cat.items()):
        cat_code = f"CAT_{cat}_{tenant_id}"
        cat_node = ProductHierarchyNode(
            tenant_id=tenant_id,
            code=cat_code,
            name=cat,
            hierarchy_level="FAMILY",
            hierarchy_path=f"{root_code}/{cat_code}",
            depth=1,
            parent_id=root.id,
        )
        db.add(cat_node)
        db.flush()
        count += 1

        for p in prod_list:
            desc = p.description or f"Product {p.id}"
            prod_code = f"PROD_{p.id}_{tenant_id}"
            node = ProductHierarchyNode(
                tenant_id=tenant_id,
                code=prod_code,
                name=desc,
                hierarchy_level="PRODUCT",
                hierarchy_path=f"{root_code}/{cat_code}/{prod_code}",
                depth=2,
                parent_id=cat_node.id,
                product_id=p.id,
            )
            db.add(node)
            count += 1

    db.flush()
    logger.info(
        "Auto-seeded %d product hierarchy nodes for tenant %d (config %d)",
        count, tenant_id, config_id,
    )
    return {"created": True, "count": count}
