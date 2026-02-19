#!/usr/bin/env python3
"""
Test script for monitoring components
Tests structured logging, health checks, and metrics collection
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_structured_logging():
    """Test structured logging imports and basic functionality"""
    print("=" * 80)
    print("Testing Structured Logging")
    print("=" * 80)

    try:
        from app.core.structured_logging import (
            JSONFormatter,
            CorrelationIdMiddleware,
            LogContext,
            timed,
            PerformanceTimer,
            setup_logging,
            get_logger,
            get_correlation_id,
            set_log_context,
            clear_log_context
        )
        print("✓ All structured logging imports successful")

        # Test logger creation
        logger = get_logger(__name__)
        print(f"✓ Logger created: {logger.name}")

        # Test correlation ID
        from contextvars import ContextVar
        from app.core.structured_logging import correlation_id_ctx
        correlation_id_ctx.set("test-123")
        cid = get_correlation_id()
        print(f"✓ Correlation ID: {cid}")

        print("\n✅ Structured logging tests passed\n")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_health_service():
    """Test health service"""
    print("=" * 80)
    print("Testing Health Service")
    print("=" * 80)

    try:
        from app.services.health_service import HealthService, HealthStatus, SystemHealth
        print("✓ Health service imports successful")

        # Test dataclasses
        status = HealthStatus(
            name="test",
            status="healthy",
            message="Test component",
            response_time_ms=10.5
        )
        print(f"✓ HealthStatus created: {status.name} - {status.status}")

        print("\n✅ Health service tests passed\n")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_metrics():
    """Test metrics collection"""
    print("=" * 80)
    print("Testing Metrics Collection")
    print("=" * 80)

    try:
        from app.core.metrics import (
            Counter,
            Histogram,
            Gauge,
            http_requests_total,
            game_creations_total,
            active_games,
            track_request_metrics,
            counter_metric,
            histogram_metric,
            get_all_metrics,
            export_prometheus_format,
            reset_metrics
        )
        print("✓ All metrics imports successful")

        # Test counter
        test_counter = Counter("test_counter", "Test counter")
        test_counter.inc()
        test_counter.inc(5)
        value = test_counter.get()
        print(f"✓ Counter test: {value} (expected 6)")

        # Test histogram
        test_histogram = Histogram("test_histogram", "Test histogram")
        test_histogram.observe(0.1)
        test_histogram.observe(0.2)
        stats = test_histogram.get_stats()
        print(f"✓ Histogram test: count={stats['count']}, mean={stats['mean']:.2f}")

        # Test gauge
        test_gauge = Gauge("test_gauge", "Test gauge")
        test_gauge.set(42)
        test_gauge.inc()
        gauge_value = test_gauge.get()
        print(f"✓ Gauge test: {gauge_value} (expected 43)")

        # Test Prometheus export
        prom_export = export_prometheus_format()
        print(f"✓ Prometheus export: {len(prom_export)} characters")

        # Reset for clean state
        reset_metrics()
        print("✓ Metrics reset")

        print("\n✅ Metrics collection tests passed\n")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_endpoints():
    """Test API endpoint imports"""
    print("=" * 80)
    print("Testing API Endpoints")
    print("=" * 80)

    try:
        from app.api.endpoints.health import router as health_router
        print(f"✓ Health router imported: {len(health_router.routes)} routes")

        from app.api.endpoints.metrics import router as metrics_router
        print(f"✓ Metrics router imported: {len(metrics_router.routes)} routes")

        print("\n✅ API endpoint tests passed\n")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("MONITORING COMPONENTS TEST SUITE")
    print("=" * 80 + "\n")

    results = []

    # Run tests
    results.append(("Structured Logging", test_structured_logging()))
    results.append(("Health Service", test_health_service()))
    results.append(("Metrics Collection", test_metrics()))
    results.append(("API Endpoints", test_api_endpoints()))

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    print("\n" + "=" * 80)
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 80 + "\n")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
