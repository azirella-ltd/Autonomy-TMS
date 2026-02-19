"""
Health Check API Endpoints
Phase 6 Sprint 3: Monitoring & Observability

Provides health check endpoints for monitoring:
- GET /health - Overall application health
- GET /health/ready - Readiness probe (Kubernetes)
- GET /health/live - Liveness probe (Kubernetes)
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.db.session import get_db
from app.core.config import settings

router = APIRouter()


@router.get("", response_model=Dict[str, Any])
async def health_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Comprehensive health check endpoint

    Returns:
    - Application status
    - Database connectivity
    - Uptime
    - Version info

    Returns HTTP 200 for healthy, 503 for unhealthy
    """
    import time
    from datetime import datetime

    # Track start time for response time
    start_time = time.time()

    checks = []
    overall_status = "healthy"

    # Check application
    checks.append({
        "name": "application",
        "status": "healthy",
        "message": "Application is running"
    })

    # Check database
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        db_response_time = (time.time() - start_time) * 1000
        checks.append({
            "name": "database",
            "status": "healthy",
            "message": "Database connection OK",
            "response_time_ms": round(db_response_time, 2)
        })
    except Exception as e:
        overall_status = "unhealthy"
        checks.append({
            "name": "database",
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}"
        })

    # Check disk space (if psutil available)
    try:
        import psutil
        disk = psutil.disk_usage('/')
        percent_used = disk.percent

        if percent_used > 90:
            disk_status = "unhealthy"
            overall_status = "unhealthy"
        elif percent_used > 80:
            disk_status = "degraded"
            if overall_status == "healthy":
                overall_status = "degraded"
        else:
            disk_status = "healthy"

        checks.append({
            "name": "disk_space",
            "status": disk_status,
            "message": f"Disk space {percent_used}% used",
            "details": {
                "percent_used": round(percent_used, 1),
                "free_gb": round(disk.free / (1024 ** 3), 2)
            }
        })
    except ImportError:
        # psutil not available, skip disk check
        pass
    except Exception as e:
        checks.append({
            "name": "disk_space",
            "status": "unknown",
            "message": f"Disk check failed: {str(e)}"
        })

    response_data = {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat() + 'Z',
        "version": getattr(settings, 'VERSION', '1.0.0'),
        "checks": checks
    }

    # Return 503 if unhealthy
    if overall_status == "unhealthy":
        return Response(
            content=str(response_data),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json"
        )

    return response_data


@router.get("/ready", response_model=Dict[str, Any])
async def readiness_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Kubernetes readiness probe

    Checks if application is ready to accept traffic.
    Only checks critical dependencies (database).

    Returns 200 if ready, 503 if not ready.
    """
    from datetime import datetime

    try:
        # Test database connection
        result = await db.execute(text("SELECT 1"))
        result.scalar()

        return {
            "status": "healthy",
            "ready": True,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "checks": [
                {"name": "database", "status": "healthy"}
            ]
        }
    except Exception as e:
        return Response(
            content=str({
                "status": "unhealthy",
                "ready": False,
                "timestamp": datetime.utcnow().isoformat() + 'Z',
                "checks": [
                    {"name": "database", "status": "unhealthy", "error": str(e)}
                ]
            }),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json"
        )


@router.get("/live", response_model=Dict[str, Any])
async def liveness_check() -> Dict[str, Any]:
    """
    Kubernetes liveness probe

    Minimal check to verify application is alive and responsive.
    Does not check dependencies.

    Returns 200 if alive.
    """
    from datetime import datetime

    return {
        "status": "healthy",
        "alive": True,
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }


@router.get("/version", response_model=Dict[str, str])
async def version_info() -> Dict[str, str]:
    """
    Get application version information

    Returns version and environment.
    """
    return {
        "version": getattr(settings, 'VERSION', '1.0.0'),
        "environment": getattr(settings, 'ENVIRONMENT', 'development')
    }
