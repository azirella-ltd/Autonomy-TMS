"""
Joint Inventory-Capacity Optimization Service.

Implements the 2-pass refinement between Inventory tGNN and Capacity tGNN:
1. Inventory tGNN outputs buffer levels
2. Capacity tGNN checks if those buffers are achievable given capacity constraints
3. Capacity tGNN outputs capacity constraints
4. Inventory tGNN adjusts buffers accordingly

The joint optimization trades off inventory holding costs vs capacity overtime costs:
    min(holding_cost * inventory_buffer + overtime_cost * capacity_buffer)

This runs AFTER both tGNNs have completed their individual inference passes
(i.e., after the lateral cycle in TacticalHiveCoordinator). It is a post-hoc
refinement step, not part of training.

Extension: Joint Inventory-Capacity Optimization (April 2026)
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np

from app.services.powell.inventory_optimization_tgnn_service import (
    InventoryOptimizationTGNNOutput,
)
from app.services.powell.capacity_rccp_tgnn_service import (
    CapacityRCCPTGNNOutput,
)

logger = logging.getLogger(__name__)


async def joint_inventory_capacity_optimization(
    config_id: int,
    inventory_output: InventoryOptimizationTGNNOutput,
    capacity_output: CapacityRCCPTGNNOutput,
    holding_cost_per_unit: float = 1.0,
    overtime_cost_per_hour: float = 2.0,
) -> Dict[str, Dict[str, float]]:
    """Trade off inventory buffers vs capacity buffers.

    For each product-site combo:
    - If capacity utilization > 85% AND safety stock is low -> raise safety stock
      (because capacity cannot flex to meet demand spikes, so buffer with inventory)
    - If capacity utilization < 60% AND safety stock is high -> reduce safety stock
      (use capacity flex instead of holding excess inventory)
    - Optimize using: min(holding_cost * inventory_buffer + overtime_cost * capacity_buffer)

    Args:
        config_id: SC config being optimized.
        inventory_output: Output from Inventory Optimization tGNN.
        capacity_output: Output from Capacity/RCCP tGNN.
        holding_cost_per_unit: Per-unit holding cost ($/unit/period).
        overtime_cost_per_hour: Per-hour overtime cost premium ($/hour).

    Returns:
        Dict[site_key, Dict] with adjusted signals:
            - adjusted_buffer_signal: refined buffer adjustment (replaces raw)
            - adjusted_capacity_buffer: refined capacity buffer pct
            - inventory_capacity_tradeoff: which lever is cheaper (inventory|capacity)
            - total_cost_estimate: estimated cost of the combined buffer strategy
            - adjustment_reasoning: plain-English explanation of the trade-off
    """
    # Collect all site keys from both outputs
    all_sites = set(inventory_output.site_keys) | set(capacity_output.site_keys)
    adjustments: Dict[str, Dict[str, float]] = {}

    for site_key in all_sites:
        # Inventory signals
        buffer_signal = inventory_output.buffer_adjustment_signal.get(site_key, 0.0)
        stockout_prob = inventory_output.stockout_probability.get(site_key, 0.0)
        inv_health = inventory_output.inventory_health.get(site_key, 0.5)
        days_of_stock = inventory_output.days_of_stock.get(site_key, 14.0)

        # Capacity signals
        planned_util = capacity_output.planned_utilization.get(site_key, 0.70)
        cap_buffer = capacity_output.capacity_buffer_pct.get(site_key, 0.15)
        feasibility = capacity_output.feasibility_score.get(site_key, 0.8)
        bottleneck_risk = capacity_output.bottleneck_risk.get(site_key, 0.2)
        avail_hours = capacity_output.available_capacity_hours.get(site_key, 160.0)
        load_hours = capacity_output.planned_load_hours.get(site_key, 112.0)

        # --- Joint optimization logic ---

        adjusted_buffer = buffer_signal
        adjusted_cap_buffer = cap_buffer
        tradeoff_lever = "balanced"
        reasoning_parts = []

        # Case 1: High utilization + low safety stock -> increase inventory buffer
        if planned_util > 0.85 and (stockout_prob > 0.3 or days_of_stock < 7):
            # Capacity is tight — cannot rely on capacity flex for demand spikes
            # Increase inventory buffer to compensate
            urgency = min((planned_util - 0.85) * 5.0, 1.0)  # [0, 1]
            buffer_boost = urgency * 0.3  # up to +0.3 buffer signal
            adjusted_buffer = float(np.clip(buffer_signal + buffer_boost, -1.0, 1.0))
            tradeoff_lever = "inventory"
            reasoning_parts.append(
                f"Capacity utilization is high ({planned_util:.0%}), "
                f"increasing inventory buffer by {buffer_boost:+.2f} to absorb demand variability."
            )

        # Case 2: Low utilization + high safety stock -> reduce inventory, use capacity flex
        elif planned_util < 0.60 and days_of_stock > 21 and inv_health > 0.7:
            # Capacity has headroom — reduce expensive inventory, flex capacity instead
            excess_factor = min((0.60 - planned_util) * 3.0, 1.0)  # [0, 1]
            buffer_reduction = excess_factor * 0.25  # up to -0.25
            adjusted_buffer = float(np.clip(buffer_signal - buffer_reduction, -1.0, 1.0))
            # Widen capacity buffer to absorb potential demand
            cap_boost = excess_factor * 0.1
            adjusted_cap_buffer = float(np.clip(cap_buffer + cap_boost, 0.0, 0.5))
            tradeoff_lever = "capacity"
            reasoning_parts.append(
                f"Low utilization ({planned_util:.0%}) with excess inventory "
                f"({days_of_stock:.0f} days) — reducing inventory buffer by "
                f"{buffer_reduction:.2f}, using capacity flex instead."
            )

        # Case 3: Bottleneck risk is high -> protect with inventory
        elif bottleneck_risk > 0.7 and feasibility < 0.6:
            buffer_boost = bottleneck_risk * 0.2
            adjusted_buffer = float(np.clip(buffer_signal + buffer_boost, -1.0, 1.0))
            tradeoff_lever = "inventory"
            reasoning_parts.append(
                f"High bottleneck risk ({bottleneck_risk:.0%}) with low feasibility "
                f"({feasibility:.0%}) — increasing inventory buffer as protection."
            )

        # Case 4: Balanced — no strong signal either way
        else:
            reasoning_parts.append(
                f"Balanced state: utilization {planned_util:.0%}, "
                f"buffer signal {buffer_signal:+.2f}, "
                f"feasibility {feasibility:.0%}. No adjustment needed."
            )

        # Cost estimate for the combined strategy
        # Inventory cost: proportional to days of stock * holding cost
        inv_cost = max(days_of_stock, 0) * holding_cost_per_unit
        # Capacity cost: overtime hours * overtime premium
        overtime_hours = max(load_hours - avail_hours * (1.0 - adjusted_cap_buffer), 0)
        cap_cost = overtime_hours * overtime_cost_per_hour
        total_cost = inv_cost + cap_cost

        adjustments[site_key] = {
            "adjusted_buffer_signal": round(adjusted_buffer, 4),
            "adjusted_capacity_buffer": round(adjusted_cap_buffer, 4),
            "original_buffer_signal": round(buffer_signal, 4),
            "original_capacity_buffer": round(cap_buffer, 4),
            "inventory_capacity_tradeoff": tradeoff_lever,
            "total_cost_estimate": round(total_cost, 2),
            "inventory_cost_component": round(inv_cost, 2),
            "capacity_cost_component": round(cap_cost, 2),
            "adjustment_reasoning": " ".join(reasoning_parts),
        }

    logger.info(
        "Joint inventory-capacity optimization complete for config %d: %d sites adjusted",
        config_id, len(adjustments),
    )

    return adjustments
