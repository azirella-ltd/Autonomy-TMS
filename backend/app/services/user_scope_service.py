"""User Scope Resolution Service — resolves hierarchy-based scope to raw site/product IDs.

Extracted from DecisionStreamService._resolve_user_scope() for reuse across
all planning/execution API endpoints.

Usage:
    from app.services.user_scope_service import resolve_user_scope

    allowed_sites, allowed_products = await resolve_user_scope(db, user)
    # None = full access, set() = restricted to those values
"""

from typing import Optional, Set, Tuple
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def resolve_user_scope(
    db: AsyncSession,
    user,
) -> Tuple[Optional[Set[str]], Optional[Set[int]]]:
    """Resolve user's hierarchy scope keys to raw site names and product IDs.

    Traverses site_hierarchy_node and product_hierarchy_node to expand
    non-leaf scope keys (e.g. REGION_Americas) into leaf site names and
    product IDs.

    Args:
        db: async database session
        user: User model instance with site_scope and product_scope

    Returns:
        (allowed_site_names, allowed_product_ids)
        None means full access for that dimension.
    """
    if not user:
        return None, None

    has_full_sites = user.has_full_site_scope
    has_full_products = user.has_full_product_scope

    if has_full_sites and has_full_products:
        return None, None

    # Lazy imports to avoid circular dependencies
    from app.models.planning_hierarchy import (
        SiteHierarchyNode,
        SiteHierarchyLevel,
        ProductHierarchyNode,
        ProductHierarchyLevel,
    )
    from app.models.supply_chain_config import Site

    allowed_sites = None
    if not has_full_sites:
        site_scope = user.site_scope or []
        allowed_sites = set()
        for scope_key in site_scope:
            try:
                result = await db.execute(
                    select(SiteHierarchyNode).where(SiteHierarchyNode.code == scope_key)
                )
                scope_node = result.scalar_one_or_none()
                if not scope_node:
                    continue

                if scope_node.hierarchy_level == SiteHierarchyLevel.SITE:
                    if scope_node.site_id:
                        site_result = await db.execute(
                            select(Site.name).where(Site.id == scope_node.site_id)
                        )
                        site_name = site_result.scalar_one_or_none()
                        if site_name:
                            allowed_sites.add(site_name)
                else:
                    descendants = await db.execute(
                        select(Site.name).join(
                            SiteHierarchyNode, SiteHierarchyNode.site_id == Site.id
                        ).where(
                            SiteHierarchyNode.hierarchy_path.like(f"{scope_node.hierarchy_path}%"),
                            SiteHierarchyNode.hierarchy_level == SiteHierarchyLevel.SITE,
                            SiteHierarchyNode.site_id.isnot(None),
                        )
                    )
                    for row in descendants.fetchall():
                        allowed_sites.add(row[0])
            except Exception as e:
                logger.warning(f"Failed to resolve site scope key {scope_key}: {e}")

        if not allowed_sites:
            allowed_sites = None  # Graceful degradation

    allowed_products = None
    if not has_full_products:
        product_scope = user.product_scope or []
        allowed_products = set()
        for scope_key in product_scope:
            try:
                result = await db.execute(
                    select(ProductHierarchyNode).where(ProductHierarchyNode.code == scope_key)
                )
                scope_node = result.scalar_one_or_none()
                if not scope_node:
                    continue

                if scope_node.hierarchy_level == ProductHierarchyLevel.PRODUCT:
                    if scope_node.product_id:
                        allowed_products.add(scope_node.product_id)
                else:
                    descendants = await db.execute(
                        select(ProductHierarchyNode.product_id).where(
                            ProductHierarchyNode.hierarchy_path.like(f"{scope_node.hierarchy_path}%"),
                            ProductHierarchyNode.hierarchy_level == ProductHierarchyLevel.PRODUCT,
                            ProductHierarchyNode.product_id.isnot(None),
                        )
                    )
                    for row in descendants.fetchall():
                        if row[0]:
                            allowed_products.add(row[0])
            except Exception as e:
                logger.warning(f"Failed to resolve product scope key {scope_key}: {e}")

        if not allowed_products:
            allowed_products = None  # Graceful degradation

    return allowed_sites, allowed_products
