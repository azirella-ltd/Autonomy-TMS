"""
Metrics API Endpoint
Phase 6 Sprint 3: Monitoring & Observability

Provides metrics endpoint for Prometheus scraping:
- GET /metrics - Prometheus-format metrics
"""

from fastapi import APIRouter, Response
from typing import Dict, Any

router = APIRouter()


@router.get(
    "",
    summary="Get application metrics",
    description="Returns metrics in Prometheus exposition format",
    response_class=Response
)
async def get_metrics() -> Response:
    """
    Get application metrics in Prometheus format

    Returns metrics including:
    - HTTP request counts and durations
    - Game and simulation metrics
    - System resource usage

    This endpoint is designed to be scraped by Prometheus.
    """
    try:
        from app.core.metrics import export_prometheus_format
        metrics_text = export_prometheus_format()
    except Exception:
        # Fallback if metrics module has issues
        metrics_text = "# Metrics temporarily unavailable\n"

    return Response(
        content=metrics_text,
        media_type="text/plain; version=0.0.4"
    )


@router.get(
    "/json",
    response_model=Dict[str, Any],
    summary="Get metrics in JSON format",
    description="Returns metrics as structured JSON for dashboard display"
)
async def get_metrics_json() -> Dict[str, Any]:
    """
    Get application metrics in JSON format

    Useful for web dashboards and API consumers.
    Returns structured data with counters, gauges, and histograms.
    """
    try:
        from app.core.metrics import get_all_metrics
        return get_all_metrics()
    except Exception as e:
        return {
            "error": "Metrics temporarily unavailable",
            "details": str(e)
        }
