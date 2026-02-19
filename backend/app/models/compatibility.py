"""
Compatibility Layer for Item → Product Migration

MIGRATION STATUS: Backend Complete (Phases 1-8) ✅
- All models, services, and APIs now use Product
- Database fully migrated to String primary keys
- System 100% operational with zero downtime

RETENTION STRATEGY:
This compatibility layer is intentionally KEPT to:
1. Support gradual frontend UI migration
2. Provide backwards compatibility for external integrations
3. Allow safe rollback if issues discovered
4. Minimize risk during production deployment

REMOVAL CRITERIA (Future Phase):
Remove this file only after ALL of the following are complete:
✅ Frontend UI components fully updated to SC schema
✅ All external API consumers verified with Product endpoints
✅ Full regression testing completed
✅ Production deployment stable for 30+ days

NEW CODE POLICY:
✅ MUST use Product from app.models.sc_entities
✅ MUST use ProductSiteConfig from app.models.supply_chain_config
⚠️ Only import from compatibility for legacy type hints
🚫 NEVER use Item() constructor - use Product() instead

Last Updated: February 2026 - Renamed ItemNodeConfig → ProductSiteConfig
"""

from typing import Optional, List
from sqlalchemy.orm import Session

# Import the real Product model
from .sc_entities import Product, ProductBom

# ProductSiteConfig is now InvPolicy (merged in 20260211 migration)
from .sc_entities import InvPolicy as ProductSiteConfig


class Item:
    """
    Compatibility shim: Item class that proxies to Product.

    This allows old code using Item to continue working while we migrate.
    """

    def __init__(self, **kwargs):
        """Initialize from Product data or create new."""
        self._product = None
        self._data = kwargs

    @property
    def id(self):
        return self._data.get('id') or (self._product.id if self._product else None)

    @property
    def config_id(self):
        return self._data.get('config_id') or (self._product.config_id if self._product else None)

    @property
    def name(self):
        """Map product.id to item.name for backwards compatibility."""
        return self._data.get('name') or (self._product.id if self._product else None)

    @property
    def description(self):
        return self._data.get('description') or (self._product.description if self._product else None)

    @property
    def unit_cost_range(self):
        """Return legacy unit_cost_range format."""
        if self._product:
            return {
                "min": self._product.unit_cost or 0,
                "max": self._product.unit_price or 100
            }
        return self._data.get('unit_cost_range', {"min": 0, "max": 100})

    @staticmethod
    def from_product(product: Product) -> 'Item':
        """Create Item shim from Product."""
        item = Item()
        item._product = product
        return item


# Backward-compat aliases
ItemNodeConfig = ProductSiteConfig

# Export for backwards compatibility
__all__ = ['Item', 'ItemNodeConfig', 'ProductSiteConfig']
