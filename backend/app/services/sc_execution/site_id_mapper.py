"""
Site ID Mapper - Simulation to SC Site Mapping

Maps between site names (strings like "retailer_001") and site IDs (integers)
for Transfer Order creation.

This service ensures simulation conforms to SC data model by using
Integer ForeignKeys to site table.
"""

from typing import Dict, Optional
from sqlalchemy.orm import Session
from app.models.supply_chain_config import Site
from app.models.sc_entities import Product


class SiteIdMapper:
    """
    Maps between simulation site names and SC site IDs.

    The simulation uses human-readable names like "retailer_001", but
    Transfer Orders must use Integer ForeignKeys to site table.

    This mapper provides bidirectional translation:
    - site name → site ID (for TO creation)
    - site ID → site name (for API responses)
    """

    def __init__(self, db: Session, config_id: int):
        """
        Initialize mapper for a supply chain configuration.

        Args:
            db: Database session
            config_id: Supply chain configuration ID
        """
        self.db = db
        self.config_id = config_id
        self._name_to_id: Dict[str, int] = {}
        self._id_to_name: Dict[int, str] = {}
        self._load_mapping()

    def _load_mapping(self):
        """Load site name ↔ ID mapping from database."""
        sites = self.db.query(Site).filter(
            Site.config_id == self.config_id
        ).all()

        for site in sites:
            self._name_to_id[site.name] = site.id
            self._id_to_name[site.id] = site.name

    def get_site_id(self, site_name: str) -> Optional[int]:
        """
        Get site ID from name.

        Args:
            site_name: Site name (e.g., "retailer_001")

        Returns:
            Site ID (Integer) or None if not found

        Example:
            >>> mapper.get_site_id("retailer_001")
            123
        """
        return self._name_to_id.get(site_name)

    def get_site_name(self, site_id: int) -> Optional[str]:
        """
        Get site name from ID.

        Args:
            site_id: Site ID (Integer)

        Returns:
            Site name (String) or None if not found

        Example:
            >>> mapper.get_site_name(123)
            "retailer_001"
        """
        return self._id_to_name.get(site_id)

    def get_all_sites(self) -> Dict[str, int]:
        """
        Get all site name → ID mappings.

        Returns:
            Dictionary of site_name → site_id
        """
        return self._name_to_id.copy()

    def get_site_by_type(self, site_type: str) -> Dict[str, int]:
        """
        Get sites filtered by type.

        Args:
            site_type: Site type (e.g., "RETAILER", "WHOLESALER")

        Returns:
            Dictionary of site_name → site_id for matching type
        """
        sites = self.db.query(Site).filter(
            Site.config_id == self.config_id,
            Site.type == site_type
        ).all()

        return {site.name: site.id for site in sites}


class ProductIdMapper:
    """
    Maps between simulation product names and SC product IDs.

    Similar to SiteIdMapper but for products.
    """

    def __init__(self, db: Session, config_id: int):
        """
        Initialize mapper for a supply chain configuration.

        Args:
            db: Database session
            config_id: Supply chain configuration ID
        """
        self.db = db
        self.config_id = config_id
        self._name_to_id: Dict[str, int] = {}
        self._id_to_name: Dict[int, str] = {}
        self._load_mapping()

    def _load_mapping(self):
        """Load product id ↔ description mapping from database.

        Product.id is a VARCHAR PK (e.g. 'TBG-CASES-1') — there is no
        separate 'name' field.  We index by both id and description.
        """
        products = self.db.query(Product).filter(
            Product.config_id == self.config_id
        ).all()

        for product in products:
            # Index by id (canonical identifier)
            self._name_to_id[product.id] = product.id
            # Also index by description (human-readable label) if set
            if product.description:
                self._name_to_id[product.description] = product.id
            self._id_to_name[product.id] = product.id

    def get_product_id(self, product_name: str) -> Optional[str]:
        """
        Get product ID from name or description.

        Args:
            product_name: Product id or description (e.g., "TBG-CASES-1")

        Returns:
            Product ID (string PK) or None if not found
        """
        return self._name_to_id.get(product_name)

    def get_product_name(self, product_id: str) -> Optional[str]:
        """
        Get product id (used as display name) from product id.

        Args:
            product_id: Product string PK

        Returns:
            Product ID string or None if not found
        """
        return self._id_to_name.get(product_id)

    def get_all_products(self) -> Dict[str, int]:
        """
        Get all product name → ID mappings.

        Returns:
            Dictionary of product_name → product_id
        """
        return self._name_to_id.copy()


class SimulationIdMapper:
    """
    Combined mapper for both sites and products.

    Convenience wrapper for simulation services that need both mappers.
    """

    def __init__(self, db: Session, config_id: int):
        """
        Initialize combined mapper.

        Args:
            db: Database session
            config_id: Supply chain configuration ID
        """
        self.site_mapper = SiteIdMapper(db, config_id)
        self.product_mapper = ProductIdMapper(db, config_id)

    def get_site_id(self, site_name: str) -> Optional[int]:
        """Get site ID from name."""
        return self.site_mapper.get_site_id(site_name)

    def get_site_name(self, site_id: int) -> Optional[str]:
        """Get site name from ID."""
        return self.site_mapper.get_site_name(site_id)

    def get_product_id(self, product_name: str) -> Optional[str]:
        """Get product string PK from name/id/description."""
        return self.product_mapper.get_product_id(product_name)

    def get_product_name(self, product_id: str) -> Optional[str]:
        """Get product display name (same as id) from string PK."""
        return self.product_mapper.get_product_name(product_id)


# Example usage:
# >>> mapper = SimulationIdMapper(db, config_id=1)
# >>> source_id = mapper.get_site_id("retailer_001")  # → 123
# >>> dest_id = mapper.get_site_id("MARKET")  # → 456
# >>> product_id = mapper.get_product_id("Cases")  # → 789
# >>>
# >>> to = TransferOrder(
# >>>     source_site_id=source_id,  # Integer
# >>>     destination_site_id=dest_id,  # Integer
# >>>     ...
# >>> )
