"""
Inventory Cache Service
Sprint 7: Performance Optimization - Option 3

Implements caching layer for frequently accessed inventory data:
- Current inventory levels
- Inventory targets (safety stock)
- Days of supply calculations
- Product-site combinations

Uses LRU cache with configurable TTL to reduce database queries.

Expected Performance Improvement: 60-80% reduction in database queries for inventory data
"""

from typing import Dict, Optional, Tuple, List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select
import logging

from app.models.sc_entities import InvLevel, Product, InvPolicy, Forecast
from app.models.supply_chain_config import Site
from app.utils.performance import LRUCache, cache_result

logger = logging.getLogger(__name__)


# ============================================================================
# Global Cache Instances
# ============================================================================

# Inventory level cache (product_id, site_id) -> InvLevel
# TTL: 5 minutes (inventory changes frequently)
inventory_level_cache = LRUCache(max_size=10000, ttl=300)

# Inventory policy cache (product_id, site_id) -> InvPolicy
# TTL: 1 hour (policies change infrequently)
inventory_policy_cache = LRUCache(max_size=5000, ttl=3600)

# Days of supply cache (product_id, site_id) -> float
# TTL: 10 minutes
days_of_supply_cache = LRUCache(max_size=10000, ttl=600)

# Forecast cache (product_id, site_id, date) -> Forecast
# TTL: 30 minutes
forecast_cache = LRUCache(max_size=20000, ttl=1800)


class InventoryCacheService:
    """
    Caching layer for inventory operations

    Provides cached access to frequently queried inventory data with
    automatic cache invalidation and fallback to database.
    """

    def __init__(self, db: Session):
        self.db = db

    # ========================================================================
    # Inventory Level Operations
    # ========================================================================

    async def get_inventory_level(
        self,
        product_id: str,
        site_id: str,
        use_cache: bool = True
    ) -> Optional[InvLevel]:
        """
        Get current inventory level with caching

        Args:
            product_id: Product ID
            site_id: Site ID
            use_cache: Whether to use cache (default: True)

        Returns:
            InvLevel object or None if not found
        """
        cache_key = f"inv_level:{product_id}:{site_id}"

        # Check cache first
        if use_cache:
            cached = inventory_level_cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for inventory level: {cache_key}")
                return cached

        # Cache miss - query database
        logger.debug(f"Cache miss for inventory level: {cache_key}")
        stmt = select(InvLevel).where(
            InvLevel.product_id == product_id,
            InvLevel.site_id == site_id
        )
        result = await self.db.execute(stmt)
        inv_level = result.scalar_one_or_none()

        # Store in cache
        if inv_level is not None and use_cache:
            inventory_level_cache.set(cache_key, inv_level)

        return inv_level

    async def get_inventory_levels_bulk(
        self,
        product_site_pairs: List[Tuple[str, str]],
        use_cache: bool = True
    ) -> Dict[Tuple[str, str], Optional[InvLevel]]:
        """
        Get multiple inventory levels efficiently

        Uses cache for hits, batches misses into single DB query.

        Args:
            product_site_pairs: List of (product_id, site_id) tuples
            use_cache: Whether to use cache

        Returns:
            Dict mapping (product_id, site_id) -> InvLevel
        """
        results = {}
        cache_misses = []

        # Check cache for each pair
        if use_cache:
            for product_id, site_id in product_site_pairs:
                cache_key = f"inv_level:{product_id}:{site_id}"
                cached = inventory_level_cache.get(cache_key)

                if cached is not None:
                    results[(product_id, site_id)] = cached
                else:
                    cache_misses.append((product_id, site_id))
        else:
            cache_misses = product_site_pairs

        # Batch query for cache misses
        if cache_misses:
            logger.debug(f"Bulk query for {len(cache_misses)} inventory levels")

            # Build OR conditions for efficient query
            conditions = []
            for product_id, site_id in cache_misses:
                conditions.append(
                    (InvLevel.product_id == product_id) & (InvLevel.site_id == site_id)
                )

            if conditions:
                from sqlalchemy import or_
                stmt = select(InvLevel).where(or_(*conditions))
                result = await self.db.execute(stmt)
                inv_levels = result.scalars().all()

                # Store results
                for inv in inv_levels:
                    key = (inv.product_id, inv.site_id)
                    results[key] = inv

                    # Cache it
                    if use_cache:
                        cache_key = f"inv_level:{inv.product_id}:{inv.site_id}"
                        inventory_level_cache.set(cache_key, inv)

                # Add None for not found
                for product_id, site_id in cache_misses:
                    if (product_id, site_id) not in results:
                        results[(product_id, site_id)] = None

        return results

    def invalidate_inventory_level(self, product_id: str, site_id: str):
        """Invalidate cached inventory level"""
        cache_key = f"inv_level:{product_id}:{site_id}"
        inventory_level_cache.delete(cache_key)
        logger.debug(f"Invalidated cache: {cache_key}")

    # ========================================================================
    # Inventory Policy Operations
    # ========================================================================

    async def get_inventory_policy(
        self,
        product_id: str,
        site_id: str,
        use_cache: bool = True
    ) -> Optional[InvPolicy]:
        """
        Get inventory policy with caching

        Args:
            product_id: Product ID
            site_id: Site ID
            use_cache: Whether to use cache

        Returns:
            InvPolicy object or None
        """
        cache_key = f"inv_policy:{product_id}:{site_id}"

        # Check cache
        if use_cache:
            cached = inventory_policy_cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for policy: {cache_key}")
                return cached

        # Query database
        logger.debug(f"Cache miss for policy: {cache_key}")
        stmt = select(InvPolicy).where(
            InvPolicy.product_id == product_id,
            InvPolicy.site_id == site_id
        )
        result = await self.db.execute(stmt)
        policy = result.scalar_one_or_none()

        # Cache it
        if policy is not None and use_cache:
            inventory_policy_cache.set(cache_key, policy)

        return policy

    def invalidate_inventory_policy(self, product_id: str, site_id: str):
        """Invalidate cached inventory policy"""
        cache_key = f"inv_policy:{product_id}:{site_id}"
        inventory_policy_cache.delete(cache_key)

    # ========================================================================
    # Days of Supply Calculation
    # ========================================================================

    async def calculate_days_of_supply(
        self,
        product_id: str,
        site_id: str,
        on_hand_qty: float,
        use_cache: bool = True
    ) -> Optional[float]:
        """
        Calculate days of supply with caching

        DOS = on_hand_qty / daily_demand_rate

        Args:
            product_id: Product ID
            site_id: Site ID
            on_hand_qty: Current inventory quantity
            use_cache: Whether to use cache for demand rate

        Returns:
            Days of supply or None if cannot calculate
        """
        cache_key = f"dos:{product_id}:{site_id}:{on_hand_qty}"

        # Check cache
        if use_cache:
            cached = days_of_supply_cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for DOS: {cache_key}")
                return cached

        # Calculate from forecast
        # Get average daily demand from recent forecasts
        try:
            # Get last 30 days of forecasts
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=30)

            stmt = select(Forecast).where(
                Forecast.product_id == product_id,
                Forecast.site_id == site_id,
                Forecast.forecast_date >= start_date,
                Forecast.forecast_date <= end_date
            )
            result = await self.db.execute(stmt)
            forecasts = result.scalars().all()

            if not forecasts:
                return None

            # Average daily demand
            total_demand = sum(f.quantity for f in forecasts)
            avg_daily_demand = total_demand / len(forecasts)

            if avg_daily_demand <= 0:
                return None

            # Calculate DOS
            dos = on_hand_qty / avg_daily_demand

            # Cache it
            if use_cache:
                days_of_supply_cache.set(cache_key, dos)

            return dos

        except Exception as e:
            logger.error(f"Error calculating DOS: {e}")
            return None

    # ========================================================================
    # Forecast Operations
    # ========================================================================

    async def get_forecast(
        self,
        product_id: str,
        site_id: str,
        forecast_date: datetime,
        use_cache: bool = True
    ) -> Optional[Forecast]:
        """
        Get forecast with caching

        Args:
            product_id: Product ID
            site_id: Site ID
            forecast_date: Forecast date
            use_cache: Whether to use cache

        Returns:
            Forecast object or None
        """
        date_str = forecast_date.strftime("%Y-%m-%d")
        cache_key = f"forecast:{product_id}:{site_id}:{date_str}"

        # Check cache
        if use_cache:
            cached = forecast_cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for forecast: {cache_key}")
                return cached

        # Query database
        stmt = select(Forecast).where(
            Forecast.product_id == product_id,
            Forecast.site_id == site_id,
            Forecast.forecast_date == forecast_date
        )
        result = await self.db.execute(stmt)
        forecast = result.scalar_one_or_none()

        # Cache it
        if forecast is not None and use_cache:
            forecast_cache.set(cache_key, forecast)

        return forecast

    # ========================================================================
    # Cache Management
    # ========================================================================

    def clear_all_caches(self):
        """Clear all inventory caches"""
        inventory_level_cache.clear()
        inventory_policy_cache.clear()
        days_of_supply_cache.clear()
        forecast_cache.clear()
        logger.info("All inventory caches cleared")

    def get_cache_stats(self) -> Dict[str, Dict]:
        """
        Get cache statistics

        Returns:
            Dict with stats for each cache
        """
        return {
            "inventory_level": inventory_level_cache.get_stats(),
            "inventory_policy": inventory_policy_cache.get_stats(),
            "days_of_supply": days_of_supply_cache.get_stats(),
            "forecast": forecast_cache.get_stats(),
        }

    def log_cache_stats(self):
        """Log cache statistics"""
        stats = self.get_cache_stats()

        logger.info("Cache Statistics:")
        for cache_name, cache_stats in stats.items():
            hit_rate = (cache_stats["hits"] / max(cache_stats["hits"] + cache_stats["misses"], 1)) * 100
            logger.info(f"  {cache_name}:")
            logger.info(f"    Size: {cache_stats['size']}/{cache_stats['max_size']}")
            logger.info(f"    Hits: {cache_stats['hits']}")
            logger.info(f"    Misses: {cache_stats['misses']}")
            logger.info(f"    Hit Rate: {hit_rate:.1f}%")


# ============================================================================
# Decorator for Cached Inventory Operations
# ============================================================================

def cached_inventory_operation(ttl: int = 300):
    """
    Decorator for caching inventory operation results

    Args:
        ttl: Time to live in seconds (default: 5 minutes)

    Usage:
        @cached_inventory_operation(ttl=600)
        async def get_excess_inventory(product_id, site_id):
            # ... expensive calculation
            return result
    """
    def decorator(func):
        cache = LRUCache(max_size=1000, ttl=ttl)

        async def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

            # Check cache
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached

            # Execute function
            result = await func(*args, **kwargs)

            # Cache result
            cache.set(cache_key, result)

            return result

        return wrapper
    return decorator


# ============================================================================
# Helper Functions
# ============================================================================

def warm_up_cache(db: Session, product_ids: List[str], site_ids: List[str]):
    """
    Warm up cache with commonly accessed data

    Args:
        db: Database session
        product_ids: List of product IDs to pre-load
        site_ids: List of site IDs to pre-load
    """
    import asyncio

    async def _warm_up():
        service = InventoryCacheService(db)

        # Pre-load inventory levels
        pairs = [(p, s) for p in product_ids for s in site_ids]
        await service.get_inventory_levels_bulk(pairs, use_cache=True)

        logger.info(f"Cache warmed up with {len(pairs)} inventory levels")

    asyncio.run(_warm_up())
