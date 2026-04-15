"""Shipment route cache — stores OSRM-derived route polylines.

Lazy-populated by GET /shipments/{id}/route on first request.
Separate from the shipment row to keep the hot table narrow and to
allow cache invalidation without touching the shipment record.
"""

from sqlalchemy import Column, Integer, Float, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from .base import Base


class ShipmentRouteCache(Base):
    """Canonical `Base` already supplies the `id` PK column.
    `shipment_id` is a unique FK so each shipment has at most one cache row.
    """
    __tablename__ = "shipment_route_cache"

    shipment_id = Column(
        Integer,
        ForeignKey("tms_shipment.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    geometry_geojson = Column(Text, nullable=False)
    distance_meters = Column(Float, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    source = Column(String(50), nullable=False, default="osrm")
    computed_at = Column(DateTime, nullable=False, server_default=func.now())
