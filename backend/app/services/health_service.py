"""
Health Check Service
Phase 6 Sprint 3: Monitoring & Observability

Provides health check endpoints for monitoring application status:
- Overall health status
- Database connectivity
- External service availability
- Resource utilization
"""

import time
import psutil
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from sqlalchemy import text
from sqlalchemy.orm import Session

# Application start time
START_TIME = datetime.utcnow()


@dataclass
class HealthStatus:
    """Health status for a component"""
    name: str
    status: str  # 'healthy', 'degraded', 'unhealthy'
    message: Optional[str] = None
    details: Dict = field(default_factory=dict)
    response_time_ms: Optional[float] = None


@dataclass
class SystemHealth:
    """Overall system health"""
    status: str  # 'healthy', 'degraded', 'unhealthy'
    timestamp: str
    uptime_seconds: float
    version: str
    checks: List[HealthStatus]


class HealthService:
    """
    Service for checking application and dependency health

    Provides comprehensive health checks for:
    - Application status
    - Database connectivity
    - External services
    - System resources
    """

    def __init__(self, db: Session, app_version: str = "1.0.0"):
        self.db = db
        self.app_version = app_version

    def check_overall_health(self) -> SystemHealth:
        """
        Check overall system health

        Returns:
            SystemHealth object with status and component checks
        """
        checks = [
            self.check_application(),
            self.check_database(),
            self.check_disk_space(),
            self.check_memory(),
        ]

        # Determine overall status
        if all(check.status == 'healthy' for check in checks):
            overall_status = 'healthy'
        elif any(check.status == 'unhealthy' for check in checks):
            overall_status = 'unhealthy'
        else:
            overall_status = 'degraded'

        uptime = (datetime.utcnow() - START_TIME).total_seconds()

        return SystemHealth(
            status=overall_status,
            timestamp=datetime.utcnow().isoformat() + 'Z',
            uptime_seconds=uptime,
            version=self.app_version,
            checks=checks
        )

    def check_readiness(self) -> SystemHealth:
        """
        Check if application is ready to accept traffic

        Checks critical dependencies (database) but not resources.
        Used for Kubernetes readiness probes.

        Returns:
            SystemHealth object with readiness status
        """
        checks = [
            self.check_application(),
            self.check_database(),
        ]

        # Must be fully healthy to be ready
        overall_status = 'healthy' if all(check.status == 'healthy' for check in checks) else 'unhealthy'

        uptime = (datetime.utcnow() - START_TIME).total_seconds()

        return SystemHealth(
            status=overall_status,
            timestamp=datetime.utcnow().isoformat() + 'Z',
            uptime_seconds=uptime,
            version=self.app_version,
            checks=checks
        )

    def check_liveness(self) -> SystemHealth:
        """
        Check if application is alive

        Basic check to ensure application is responsive.
        Used for Kubernetes liveness probes.

        Returns:
            SystemHealth object with liveness status
        """
        checks = [
            self.check_application(),
        ]

        overall_status = 'healthy'
        uptime = (datetime.utcnow() - START_TIME).total_seconds()

        return SystemHealth(
            status=overall_status,
            timestamp=datetime.utcnow().isoformat() + 'Z',
            uptime_seconds=uptime,
            version=self.app_version,
            checks=checks
        )

    def check_application(self) -> HealthStatus:
        """Check basic application health"""
        start = time.time()

        uptime = (datetime.utcnow() - START_TIME).total_seconds()

        response_time_ms = (time.time() - start) * 1000

        return HealthStatus(
            name='application',
            status='healthy',
            message='Application is running',
            details={
                'uptime_seconds': round(uptime, 2),
                'start_time': START_TIME.isoformat() + 'Z',
                'version': self.app_version
            },
            response_time_ms=round(response_time_ms, 2)
        )

    def check_database(self) -> HealthStatus:
        """Check database connectivity and performance"""
        start = time.time()

        try:
            # Simple query to test connectivity
            result = self.db.execute(text("SELECT 1")).scalar()

            response_time_ms = (time.time() - start) * 1000

            # Check if response time is acceptable
            if response_time_ms > 1000:  # >1s is concerning
                status = 'degraded'
                message = 'Database responding slowly'
            else:
                status = 'healthy'
                message = 'Database connection OK'

            return HealthStatus(
                name='database',
                status=status,
                message=message,
                details={
                    'connected': True,
                    'response_time_ms': round(response_time_ms, 2)
                },
                response_time_ms=round(response_time_ms, 2)
            )

        except Exception as e:
            response_time_ms = (time.time() - start) * 1000

            return HealthStatus(
                name='database',
                status='unhealthy',
                message=f'Database connection failed: {str(e)}',
                details={
                    'connected': False,
                    'error': str(e)
                },
                response_time_ms=round(response_time_ms, 2)
            )

    def check_disk_space(self) -> HealthStatus:
        """Check disk space availability"""
        start = time.time()

        try:
            disk = psutil.disk_usage('/')
            percent_used = disk.percent
            free_gb = disk.free / (1024 ** 3)

            # Determine status based on disk usage
            if percent_used > 90:
                status = 'unhealthy'
                message = f'Disk space critical: {percent_used}% used'
            elif percent_used > 80:
                status = 'degraded'
                message = f'Disk space high: {percent_used}% used'
            else:
                status = 'healthy'
                message = f'Disk space OK: {percent_used}% used'

            response_time_ms = (time.time() - start) * 1000

            return HealthStatus(
                name='disk_space',
                status=status,
                message=message,
                details={
                    'percent_used': round(percent_used, 1),
                    'free_gb': round(free_gb, 2),
                    'total_gb': round(disk.total / (1024 ** 3), 2)
                },
                response_time_ms=round(response_time_ms, 2)
            )

        except Exception as e:
            response_time_ms = (time.time() - start) * 1000

            return HealthStatus(
                name='disk_space',
                status='unhealthy',
                message=f'Disk check failed: {str(e)}',
                details={'error': str(e)},
                response_time_ms=round(response_time_ms, 2)
            )

    def check_memory(self) -> HealthStatus:
        """Check memory usage"""
        start = time.time()

        try:
            memory = psutil.virtual_memory()
            percent_used = memory.percent
            available_gb = memory.available / (1024 ** 3)

            # Determine status based on memory usage
            if percent_used > 90:
                status = 'unhealthy'
                message = f'Memory critical: {percent_used}% used'
            elif percent_used > 80:
                status = 'degraded'
                message = f'Memory high: {percent_used}% used'
            else:
                status = 'healthy'
                message = f'Memory OK: {percent_used}% used'

            response_time_ms = (time.time() - start) * 1000

            return HealthStatus(
                name='memory',
                status=status,
                message=message,
                details={
                    'percent_used': round(percent_used, 1),
                    'available_gb': round(available_gb, 2),
                    'total_gb': round(memory.total / (1024 ** 3), 2)
                },
                response_time_ms=round(response_time_ms, 2)
            )

        except Exception as e:
            response_time_ms = (time.time() - start) * 1000

            return HealthStatus(
                name='memory',
                status='unhealthy',
                message=f'Memory check failed: {str(e)}',
                details={'error': str(e)},
                response_time_ms=round(response_time_ms, 2)
            )

    def check_llm_provider(self, api_key: Optional[str] = None) -> HealthStatus:
        """Check LLM provider availability (vLLM, Ollama, or any OpenAI-compatible API).

        Args:
            api_key: API key to test (optional for local providers)

        Returns:
            HealthStatus for the configured LLM provider
        """
        start = time.time()
        import os
        base_url = os.getenv("LLM_API_BASE")

        if not api_key and not base_url:
            return HealthStatus(
                name='llm_provider',
                status='healthy',
                message='LLM provider check skipped (not configured)',
                details={'configured': False},
                response_time_ms=0
            )

        try:
            from openai import OpenAI
            kwargs: dict = {}
            if base_url:
                kwargs["base_url"] = base_url
            resolved_key = api_key or os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "not-needed"
            kwargs["api_key"] = resolved_key
            client = OpenAI(**kwargs)

            # List models as a connectivity test
            models = client.models.list()

            response_time_ms = (time.time() - start) * 1000
            provider_label = base_url or "OpenAI API"

            if response_time_ms > 5000:
                status = 'degraded'
                message = f'LLM provider responding slowly ({provider_label})'
            else:
                status = 'healthy'
                message = f'LLM provider available ({provider_label})'

            return HealthStatus(
                name='llm_provider',
                status=status,
                message=message,
                details={
                    'configured': True,
                    'available': True,
                    'provider': provider_label,
                    'model_count': len(models.data) if hasattr(models, 'data') else 0
                },
                response_time_ms=round(response_time_ms, 2)
            )

        except Exception as e:
            response_time_ms = (time.time() - start) * 1000

            return HealthStatus(
                name='llm_provider',
                status='unhealthy',
                message=f'LLM provider unavailable: {str(e)}',
                details={
                    'configured': True,
                    'available': False,
                    'error': str(e)
                },
                response_time_ms=round(response_time_ms, 2)
            )

    # Backward-compat alias
    check_openai_api = check_llm_provider


# Standalone testing
if __name__ == '__main__':
    import sys
    sys.path.insert(0, '/home/trevor/Documents/Autonomy/Autonomy/backend')

    from app.db.session import SessionLocal

    print("=" * 80)
    print("HEALTH CHECK SERVICE DEMO")
    print("=" * 80)

    # Create service
    db = SessionLocal()
    service = HealthService(db, app_version="1.0.0-dev")

    # Test overall health
    print("\n1. Overall Health Check")
    print("-" * 80)
    health = service.check_overall_health()
    print(f"Status: {health.status}")
    print(f"Uptime: {health.uptime_seconds:.2f}s")
    print(f"Version: {health.version}")
    print(f"\nComponent Checks:")
    for check in health.checks:
        print(f"  - {check.name}: {check.status} ({check.response_time_ms}ms)")
        print(f"    {check.message}")

    # Test readiness
    print("\n2. Readiness Check")
    print("-" * 80)
    readiness = service.check_readiness()
    print(f"Status: {readiness.status}")
    print(f"Ready: {readiness.status == 'healthy'}")

    # Test liveness
    print("\n3. Liveness Check")
    print("-" * 80)
    liveness = service.check_liveness()
    print(f"Status: {liveness.status}")
    print(f"Alive: {liveness.status == 'healthy'}")

    db.close()

    print("\n" + "=" * 80)
    print("✅ Health check service demo complete")
    print("=" * 80)
