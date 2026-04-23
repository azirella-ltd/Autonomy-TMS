"""
Metrics Collection Module
Phase 6 Sprint 3: Monitoring & Observability

Provides:
- Prometheus-compatible metrics
- Request counters and histograms
- Business metrics tracking
- Custom metric decorators
"""

import time
from typing import Dict, List, Optional, Callable
from functools import wraps
from collections import defaultdict
from threading import Lock
from datetime import datetime

# Thread-safe storage for metrics
_metrics_lock = Lock()
_counters: Dict[str, int] = defaultdict(int)
_histograms: Dict[str, List[float]] = defaultdict(list)
_gauges: Dict[str, float] = {}
_last_reset = datetime.utcnow()


class Counter:
    """
    Counter metric for tracking cumulative values

    Usage:
        counter = Counter('http_requests_total', 'Total HTTP requests')
        counter.inc()  # Increment by 1
        counter.inc(5)  # Increment by 5
    """

    def __init__(self, name: str, description: str, labels: Optional[Dict[str, str]] = None):
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._value = 0

    def inc(self, amount: int = 1):
        """Increment counter"""
        with _metrics_lock:
            _counters[self._get_key()] += amount

    def get(self) -> int:
        """Get current value"""
        return _counters.get(self._get_key(), 0)

    def _get_key(self) -> str:
        """Get key with labels"""
        if self.labels:
            label_str = ','.join(f'{k}="{v}"' for k, v in sorted(self.labels.items()))
            return f'{self.name}{{{label_str}}}'
        return self.name


class Histogram:
    """
    Histogram metric for tracking distributions

    Usage:
        histogram = Histogram('request_duration_seconds', 'Request duration')
        histogram.observe(0.123)  # Record a value
    """

    def __init__(self, name: str, description: str, labels: Optional[Dict[str, str]] = None):
        self.name = name
        self.description = description
        self.labels = labels or {}

    def observe(self, value: float):
        """Record an observation"""
        with _metrics_lock:
            _histograms[self._get_key()].append(value)

    def get_stats(self) -> Dict[str, float]:
        """Get histogram statistics"""
        values = _histograms.get(self._get_key(), [])
        if not values:
            return {'count': 0, 'sum': 0, 'min': 0, 'max': 0, 'mean': 0}

        return {
            'count': len(values),
            'sum': sum(values),
            'min': min(values),
            'max': max(values),
            'mean': sum(values) / len(values),
            'p50': self._percentile(values, 50),
            'p95': self._percentile(values, 95),
            'p99': self._percentile(values, 99)
        }

    @staticmethod
    def _percentile(values: List[float], percentile: float) -> float:
        """Calculate percentile"""
        if not values:
            return 0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * (percentile / 100.0))
        return sorted_values[min(index, len(sorted_values) - 1)]

    def _get_key(self) -> str:
        """Get key with labels"""
        if self.labels:
            label_str = ','.join(f'{k}="{v}"' for k, v in sorted(self.labels.items()))
            return f'{self.name}{{{label_str}}}'
        return self.name


class Gauge:
    """
    Gauge metric for tracking values that can go up and down

    Usage:
        gauge = Gauge('active_connections', 'Active database connections')
        gauge.set(10)
        gauge.inc()  # Increment
        gauge.dec()  # Decrement
    """

    def __init__(self, name: str, description: str, labels: Optional[Dict[str, str]] = None):
        self.name = name
        self.description = description
        self.labels = labels or {}

    def set(self, value: float):
        """Set gauge value"""
        with _metrics_lock:
            _gauges[self._get_key()] = value

    def inc(self, amount: float = 1.0):
        """Increment gauge"""
        with _metrics_lock:
            current = _gauges.get(self._get_key(), 0)
            _gauges[self._get_key()] = current + amount

    def dec(self, amount: float = 1.0):
        """Decrement gauge"""
        with _metrics_lock:
            current = _gauges.get(self._get_key(), 0)
            _gauges[self._get_key()] = current - amount

    def get(self) -> float:
        """Get current value"""
        return _gauges.get(self._get_key(), 0)

    def _get_key(self) -> str:
        """Get key with labels"""
        if self.labels:
            label_str = ','.join(f'{k}="{v}"' for k, v in sorted(self.labels.items()))
            return f'{self.name}{{{label_str}}}'
        return self.name


# Global metrics instances
http_requests_total = Counter('http_requests_total', 'Total HTTP requests received')
http_request_duration_seconds = Histogram('http_request_duration_seconds', 'HTTP request duration in seconds')
http_requests_in_progress = Gauge('http_requests_in_progress', 'HTTP requests currently in progress')

scenario_creations_total = Counter('scenario_creations_total', 'Total scenarios created')
scenario_completions_total = Counter('scenario_completions_total', 'Total scenarios completed')
simulations_run_total = Counter('simulations_run_total', 'Total simulations run')
monte_carlo_runs_total = Counter('monte_carlo_runs_total', 'Total Monte Carlo simulation runs')

active_games = Gauge('active_games', 'Number of active scenarios')
active_users = Gauge('active_users', 'Number of active users')


def track_request_metrics(method: str, path: str, status_code: int, duration: float):
    """
    Track HTTP request metrics

    Args:
        method: HTTP method (GET, POST, etc.)
        path: Request path
        status_code: HTTP status code
        duration: Request duration in seconds
    """
    # Increment request counter
    request_counter = Counter(
        'http_requests_total',
        'Total HTTP requests',
        labels={'method': method, 'path': path, 'status': str(status_code)}
    )
    request_counter.inc()

    # Record duration
    duration_histogram = Histogram(
        'http_request_duration_seconds',
        'Request duration',
        labels={'method': method, 'path': path}
    )
    duration_histogram.observe(duration)


def counter_metric(metric_name: str, description: str = ''):
    """
    Decorator to count function calls

    Usage:
        @counter_metric('games_created', 'Number of scenarios created')
        def create_scenario(...):
            ...
    """
    counter = Counter(metric_name, description)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            counter.inc()
            return result

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            counter.inc()
            return result

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


def histogram_metric(metric_name: str, description: str = ''):
    """
    Decorator to track function duration

    Usage:
        @histogram_metric('scenario_creation_duration', 'Scenario creation duration')
        def create_scenario(...):
            ...
    """
    histogram = Histogram(metric_name, description)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start
                histogram.observe(duration)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = time.time() - start
                histogram.observe(duration)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


def get_all_metrics() -> Dict[str, any]:
    """
    Get all metrics in a structured format

    Returns:
        Dictionary containing all metrics
    """
    with _metrics_lock:
        metrics = {
            'counters': dict(_counters),
            'gauges': dict(_gauges),
            'histograms': {}
        }

        # Calculate histogram statistics
        for key, values in _histograms.items():
            if values:
                sorted_values = sorted(values)
                count = len(values)
                metrics['histograms'][key] = {
                    'count': count,
                    'sum': sum(values),
                    'min': min(values),
                    'max': max(values),
                    'mean': sum(values) / count,
                    'p50': sorted_values[int(count * 0.50)],
                    'p95': sorted_values[int(count * 0.95)],
                    'p99': sorted_values[int(count * 0.99)]
                }

        return metrics


def export_prometheus_format() -> str:
    """
    Export metrics in Prometheus text format

    Returns:
        Metrics in Prometheus exposition format
    """
    lines = []

    with _metrics_lock:
        # Export counters
        for name, value in _counters.items():
            lines.append(f'# TYPE {name.split("{")[0]} counter')
            lines.append(f'{name} {value}')

        # Export gauges
        for name, value in _gauges.items():
            lines.append(f'# TYPE {name.split("{")[0]} gauge')
            lines.append(f'{name} {value}')

        # Export histograms
        for name, values in _histograms.items():
            if values:
                base_name = name.split('{')[0]
                lines.append(f'# TYPE {base_name} histogram')

                sorted_values = sorted(values)
                count = len(values)
                total = sum(values)

                # Histogram buckets
                buckets = [0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0]
                for bucket in buckets:
                    count_le = sum(1 for v in values if v <= bucket)
                    lines.append(f'{name}_bucket{{le="{bucket}"}} {count_le}')

                lines.append(f'{name}_bucket{{le="+Inf"}} {count}')
                lines.append(f'{name}_sum {total}')
                lines.append(f'{name}_count {count}')

    return '\n'.join(lines) + '\n'


def reset_metrics():
    """Reset all metrics (useful for testing)"""
    global _last_reset
    with _metrics_lock:
        _counters.clear()
        _histograms.clear()
        _gauges.clear()
        _last_reset = datetime.utcnow()


# Example usage
if __name__ == '__main__':
    print("=" * 80)
    print("METRICS COLLECTION DEMO")
    print("=" * 80)

    # Counter example
    print("\n1. Counter Metrics")
    print("-" * 80)
    requests = Counter('http_requests', 'HTTP requests', labels={'method': 'GET', 'path': '/api/scenarios'})
    for i in range(10):
        requests.inc()
    print(f"Total requests: {requests.get()}")

    # Histogram example
    print("\n2. Histogram Metrics")
    print("-" * 80)
    duration = Histogram('request_duration', 'Request duration')
    for i in range(100):
        duration.observe(0.05 + (i / 1000))
    stats = duration.get_stats()
    print(f"Duration stats: count={stats['count']}, mean={stats['mean']:.4f}s, p95={stats['p95']:.4f}s")

    # Gauge example
    print("\n3. Gauge Metrics")
    print("-" * 80)
    connections = Gauge('active_connections', 'Active connections')
    connections.set(10)
    print(f"Active connections: {connections.get()}")
    connections.inc(5)
    print(f"After increment: {connections.get()}")
    connections.dec(3)
    print(f"After decrement: {connections.get()}")

    # Decorator examples
    print("\n4. Metric Decorators")
    print("-" * 80)

    @counter_metric('function_calls', 'Function call counter')
    @histogram_metric('function_duration', 'Function duration')
    def example_function():
        time.sleep(0.01)
        return "done"

    for i in range(5):
        example_function()

    print("Function called 5 times with timing metrics")

    # Export all metrics
    print("\n5. All Metrics")
    print("-" * 80)
    all_metrics = get_all_metrics()
    print(f"Counters: {len(all_metrics['counters'])}")
    print(f"Histograms: {len(all_metrics['histograms'])}")
    print(f"Gauges: {len(all_metrics['gauges'])}")

    # Prometheus format
    print("\n6. Prometheus Format Export")
    print("-" * 80)
    prom_export = export_prometheus_format()
    print(prom_export[:500] + "...")

    print("\n" + "=" * 80)
    print("✅ Metrics collection demo complete")
    print("=" * 80)
