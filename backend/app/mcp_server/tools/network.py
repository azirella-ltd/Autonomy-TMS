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
        config_id: int,
    ) -> dict:
        """Get the supply chain network topology and health status.

        Returns the DAG structure (sites + transportation lanes) with:
        - Site details: name, type (Manufacturer/DC/Retailer), master_type, capabilities
        - Transportation lanes: connections between sites with lead times
        - Active alerts: CDC triggers, condition monitor breaches
        - Bottleneck indicators: sites with capacity constraints

        Args:
            config_id: Supply chain config ID (must belong to authenticated tenant)

        Returns:
            Network topology with health indicators.
        """
        from sqlalchemy import text as sql_text
        from .db import get_db, require_config

        async with get_db() as (db, user):
            # Tenant-isolation gate. ``require_config`` raises
            # PermissionError if config_id is not owned by the
            # authenticated tenant; the FastMCP transport surfaces
            # that as a structured tool error so callers see a clear
            # 4xx-style failure rather than a typed-empty rollback.
            config_id = await require_config(db, user, config_id)

            # Sites — column names match canonical Core Site (azirella_data_model
            # .master.config.Site): name, type, master_type. Earlier draft of
            # this query used `description` and `site_type` which do not exist
            # in the canonical schema; fixed 2026-04-30 typed-empty audit.
            sites_result = await db.execute(
                sql_text("""
                    SELECT id, name, type, master_type,
                           latitude, longitude, geo_id
                    FROM site
                    WHERE config_id = :config_id
                    ORDER BY master_type, name
                """),
                {"config_id": config_id},
            )
            sites = [
                {
                    "id": r.id,
                    "name": r.name,
                    "type": r.type,
                    "master_type": r.master_type,
                    "latitude": r.latitude,
                    "longitude": r.longitude,
                    "geo_id": r.geo_id,
                }
                for r in sites_result.fetchall()
            ]

            # Transportation lanes — canonical TransportationLane carries
            # `lead_time_days` (no `transit_time`/`transit_time_uom`) and
            # has no mode column. Mode is derived per-shipment in TMS, not
            # stored on the lane. Earlier draft selected non-existent
            # columns; fixed 2026-04-30 typed-empty audit.
            lanes_result = await db.execute(
                sql_text("""
                    SELECT id, from_site_id, to_site_id, lead_time_days,
                           demand_lead_time, supply_lead_time
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
                    "mode": None,  # not modelled at lane level
                    "lead_time_days": r.lead_time_days,
                    "demand_lead_time": r.demand_lead_time,
                    "supply_lead_time": r.supply_lead_time,
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
