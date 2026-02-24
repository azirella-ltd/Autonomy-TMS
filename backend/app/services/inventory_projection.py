"""Utility helpers for presenting simulation inventory state."""

from __future__ import annotations

from typing import Any

from app.services.engine import Node


def project_start_of_next_round_inventory(node: Node) -> int:
    """Estimate the stock level scenario_users should see before the next round begins."""

    try:
        base_inventory = int(getattr(node, "inventory", 0))
    except (TypeError, ValueError):
        base_inventory = 0

    try:
        lead_time = int(getattr(node, "shipment_lead_time", 0))
    except (TypeError, ValueError):
        lead_time = 0

    if lead_time <= 0:
        return base_inventory

    pipeline: Any = getattr(node, "pipeline_shipments", None)
    if not pipeline:
        return base_inventory

    try:
        next_arrival = int(pipeline[0])
    except (TypeError, ValueError, IndexError):
        next_arrival = 0

    return base_inventory + max(0, next_arrival)
