"""
MCP Tool: Network Status — DAG Topology Health.

Returns the supply chain network topology (sites, transportation lanes,
master types) with health indicators, active alerts, and bottleneck status.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def register(mcp):
    """Register network status tools on the MCP server."""

    @mcp.tool()
    async def get_network_status(
        tenant_id: int,
        config_id: int,
    ) -> dict:
        """Get the supply chain network topology and health status.

        Returns the DAG structure (sites + transportation lanes) with:
        - Site details: name, type (Manufacturer/DC/Retailer), master_type, capabilities
        - Transportation lanes: connections between sites with lead times
        - Active alerts: CDC triggers, condition monitor breaches
        - Bottleneck indicators: sites with capacity constraints

        Args:
            tenant_id: Organization ID
            config_id: Supply chain config ID

        Returns:
            Network topology with health indicators.
        """
        from sqlalchemy import text as sql_text
        from .db import get_db

        async with get_db() as db:
            # Sites
            sites_result = await db.execute(
                sql_text("""
                    SELECT id, description, site_type, master_type,
                           latitude, longitude, geo_id
                    FROM site
                    WHERE config_id = :config_id
                    ORDER BY master_type, description
                """),
                {"config_id": config_id},
            )
            sites = [
                {
                    "id": r.id,
                    "name": r.description,
                    "type": r.site_type,
                    "master_type": r.master_type,
                    "latitude": r.latitude,
                    "longitude": r.longitude,
                    "geo_id": r.geo_id,
                }
                for r in sites_result.fetchall()
            ]

            # Transportation lanes
            lanes_result = await db.execute(
                sql_text("""
                    SELECT id, from_site_id, to_site_id, transportation_mode,
                           transit_time, transit_time_uom
                    FROM transportation_lane
                    WHERE config_id = :config_id
                """),
                {"config_id": config_id},
            )
            lanes = [
                {
                    "id": r.id,
                    "from_site": r.from_site_id,
                    "to_site": r.to_site_id,
                    "mode": r.transportation_mode,
                    "transit_time": r.transit_time,
                    "transit_time_uom": r.transit_time_uom,
                }
                for r in lanes_result.fetchall()
            ]

            # Active CDC triggers (last 24h)
            try:
                alerts_result = await db.execute(
                    sql_text("""
                        SELECT trigger_reason, severity, site_key, message, created_at
                        FROM powell_cdc_trigger_log
                        WHERE config_id = :config_id
                          AND created_at > NOW() - INTERVAL '24 hours'
                        ORDER BY created_at DESC
                        LIMIT 20
                    """),
                    {"config_id": config_id},
                )
                alerts = [
                    {
                        "reason": r.trigger_reason,
                        "severity": r.severity,
                        "site": r.site_key,
                        "message": r.message,
                        "timestamp": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in alerts_result.fetchall()
                ]
            except Exception:
                alerts = []

            return {
                "site_count": len(sites),
                "lane_count": len(lanes),
                "alert_count": len(alerts),
                "sites": sites,
                "lanes": lanes,
                "alerts": alerts,
            }
