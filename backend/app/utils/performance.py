"""
Performance Utilities
Sprint 7: Performance Optimization

Provides profiling, caching, and performance monitoring utilities.
"""

import time
import functools
import logging
from typing import Any, Callable, Optional
from collections import OrderedDict
import asyncio
import hashlib
import json

logger = logging.getLogger(__name__)


class PerformanceProfiler:
    """
    Simple performance profiler for tracking execution times
    """

    def __init__(self):
        self.timings = {}

    def profile(self, name: str):
        """
        Decorator to profile function execution time

        Usage:
            profiler = PerformanceProfiler()

            @profiler.profile("my_function")
            def my_function():
                # function code
        """
        def decorator(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    elapsed = time.time() - start_time
                    self._record_timing(name, elapsed)

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    elapsed = time.time() - start_time
                    self._record_timing(name, elapsed)

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        return decorator

    def _record_timing(self, name: str, elapsed: float):
        """Record timing for a profiled function"""
        if name not in self.timings:
            self.timings[name] = {
                'count': 0,
                'total': 0.0,
                'min': float('inf'),
                'max': 0.0,
                'avg': 0.0
            }

        stats = self.timings[name]
        stats['count'] += 1
        stats['total'] += elapsed
        stats['min'] = min(stats['min'], elapsed)
        stats['max'] = max(stats['max'], elapsed)
        stats['avg'] = stats['total'] / stats['count']

        # Log slow operations (> 1 second)
        if elapsed > 1.0:
            logger.warning(f"Slow operation: {name} took {elapsed:.3f}s")

    def get_stats(self) -> dict:
        """Get profiling statistics"""
        return self.timings

    def print_stats(self):
        """Print profiling statistics"""
        print("\n=== Performance Profile ===")
        for name, stats in sorted(self.timings.items(), key=lambda x: x[1]['avg'], reverse=True):
            print(f"{name}:")
            print(f"  Count: {stats['count']}")
            print(f"  Avg: {stats['avg']:.4f}s")
            print(f"  Min: {stats['min']:.4f}s")
            print(f"  Max: {stats['max']:.4f}s")
            print(f"  Total: {stats['total']:.4f}s")


class LRUCache:
    """
    Simple LRU (Least Recently Used) cache implementation

    Thread-safe in-memory cache with size limits and TTL support.
    """

    def __init__(self, max_size: int = 1000, ttl: Optional[int] = 3600):
        """
        Initialize LRU cache

        Args:
            max_size: Maximum number of items to cache
            ttl: Time to live in seconds (None for no expiration)
        """
        self.cache = OrderedDict()
        self.max_size = max_size
        self.ttl = ttl
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if key not in self.cache:
            self.misses += 1
            return None

        value, timestamp = self.cache[key]

        # Check TTL
        if self.ttl and (time.time() - timestamp) > self.ttl:
            del self.cache[key]
            self.misses += 1
            return None

        # Move to end (most recently used)
        self.cache.move_to_end(key)
        self.hits += 1
        return value

    def set(self, key: str, value: Any):
        """Set value in cache"""
        # Remove if exists
        if key in self.cache:
            del self.cache[key]

        # Add to end
        self.cache[key] = (value, time.time())

        # Evict oldest if over size limit
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def clear(self):
        """Clear cache"""
        self.cache.clear()
        self.hits = 0
        self.misses = 0

    def get_stats(self) -> dict:
        """Get cache statistics"""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        return {
            'size': len(self.cache),
            'max_size': self.max_size,
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': f"{hit_rate:.2f}%"
        }


def cache_result(cache: LRUCache, key_prefix: str = ""):
    """
    Decorator to cache function results

    Usage:
        cache = LRUCache(max_size=100)

        @cache_result(cache, key_prefix="analytics")
        async def compute_analytics(param1, param2):
            # expensive computation
            return result
    """
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_key = _generate_cache_key(key_prefix, func.__name__, args, kwargs)

            # Check cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Compute and cache
            result = await func(*args, **kwargs)
            cache.set(cache_key, result)
            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = _generate_cache_key(key_prefix, func.__name__, args, kwargs)

            # Check cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            # Compute and cache
            result = func(*args, **kwargs)
            cache.set(cache_key, result)
            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def _generate_cache_key(prefix: str, func_name: str, args: tuple, kwargs: dict) -> str:
    """Generate cache key from function arguments"""
    # Serialize arguments to JSON for hashing
    try:
        args_str = json.dumps([str(arg) for arg in args], sort_keys=True)
        kwargs_str = json.dumps({k: str(v) for k, v in kwargs.items()}, sort_keys=True)
        combined = f"{prefix}:{func_name}:{args_str}:{kwargs_str}"

        # Hash to keep key size manageable
        key_hash = hashlib.md5(combined.encode()).hexdigest()
        return f"{prefix}:{func_name}:{key_hash}"
    except Exception as e:
        logger.warning(f"Failed to generate cache key: {e}")
        # Fallback to simpler key
        return f"{prefix}:{func_name}:{len(args)}:{len(kwargs)}"


def batch_processor(batch_size: int = 100):
    """
    Decorator to process items in batches for better performance

    Usage:
        @batch_processor(batch_size=50)
        async def process_items(items):
            # Process batch of items
            return results
    """
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(items, *args, **kwargs):
            results = []
            for i in range(0, len(items), batch_size):
                batch = items[i:i + batch_size]
                batch_results = await func(batch, *args, **kwargs)
                results.extend(batch_results)
            return results

        @functools.wraps(func)
        def sync_wrapper(items, *args, **kwargs):
            results = []
            for i in range(0, len(items), batch_size):
                batch = items[i:i + batch_size]
                batch_results = func(batch, *args, **kwargs)
                results.extend(batch_results)
            return results

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


# Global instances
profiler = PerformanceProfiler()
analytics_cache = LRUCache(max_size=500, ttl=3600)  # 1 hour TTL
query_cache = LRUCache(max_size=1000, ttl=300)  # 5 minute TTL


def get_profiler() -> PerformanceProfiler:
    """Get global profiler instance"""
    return profiler


def get_analytics_cache() -> LRUCache:
    """Get analytics cache instance"""
    return analytics_cache


def get_query_cache() -> LRUCache:
    """Get query cache instance"""
    return query_cache
