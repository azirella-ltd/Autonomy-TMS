"""
Theta* Inferencer — Derives optimal policy parameters from TRM decisions.

For each scenario, back-infers the 5 policy parameters (safety stock
multiplier, service level target, reorder point days, order up to days,
sourcing split) per site from the TRM decisions that occurred during
the scenario simulation.

These inferred theta* values become the training targets for the S&OP
GraphSAGE (Layer 4).
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ThetaStarInferencer:
    """Infers S&OP policy parameters from TRM decision logs.

    Each policy parameter has a corresponding TRM whose decisions reveal
    the optimal value for that parameter:

    - safety_stock_multiplier: Inventory Buffer TRM's action.multiplier average
    - service_level_target:    ATP TRM's achieved fill_rate average
    - reorder_point_days:      PO TRM's average days_of_supply at trigger
    - order_up_to_days:        PO TRM's action.target_days_of_supply average
    - sourcing_split:          Not yet captured in current TRMs (default 0.7)
    """

    def infer(self, samples: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
        """Infer theta* per site from Level 1 samples.

        Args:
            samples: List of Layer 1 TRM decision samples from one scenario

        Returns:
            Dict keyed by site_id -> policy params
        """
        # Group by site
        by_site: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for s in samples:
            site = s.get("_site_id") or s.get("site_id", "unknown")
            by_site[site].append(s)

        result: Dict[str, Dict[str, float]] = {}
        for site_id, site_samples in by_site.items():
            result[site_id] = self._infer_per_site(site_samples)

        return result

    def _infer_per_site(self, samples: List[Dict[str, Any]]) -> Dict[str, float]:
        """Infer the 5 policy parameters for one site."""
        # Default values if not enough data to infer
        theta = {
            "safety_stock_multiplier": 1.0,
            "service_level_target": 0.95,
            "reorder_point_days": 7.0,
            "order_up_to_days": 21.0,
            "sourcing_split": 0.7,
        }

        # ── safety_stock_multiplier: from inventory_buffer TRM ──
        buf_samples = [s for s in samples if s.get("_trm_type") == "inventory_buffer" or s.get("trm_type") == "inventory_buffer"]
        if buf_samples:
            multipliers = [
                s.get("action", {}).get("multiplier", 1.0)
                for s in buf_samples
            ]
            if multipliers:
                theta["safety_stock_multiplier"] = sum(multipliers) / len(multipliers)

        # ── service_level_target: from atp_allocation TRM (achieved fill rate) ──
        atp_samples = [s for s in samples if s.get("_trm_type") == "atp_allocation" or s.get("trm_type") == "atp_allocation"]
        if atp_samples:
            fill_rates = [
                s.get("action", {}).get("fill_rate", 0.95)
                for s in atp_samples
            ]
            if fill_rates:
                # Use the 90th percentile as "target" since we want aspiration, not average
                fill_rates.sort()
                idx = int(len(fill_rates) * 0.9)
                theta["service_level_target"] = max(0.80, min(0.99, fill_rates[idx]))

        # ── reorder_point_days: from po_creation TRM (days_of_supply at trigger) ──
        po_samples = [s for s in samples if s.get("_trm_type") == "po_creation" or s.get("trm_type") == "po_creation"]
        if po_samples:
            dos_values = [
                s.get("state_features", {}).get("days_of_supply", 7.0)
                for s in po_samples
                if s.get("action", {}).get("order_quantity", 0) > 0  # only triggered orders
            ]
            if dos_values:
                theta["reorder_point_days"] = max(3.0, min(21.0, sum(dos_values) / len(dos_values)))

        # ── order_up_to_days: from po_creation TRM (target days of supply) ──
        if po_samples:
            target_dos = [
                s.get("action", {}).get("target_days_of_supply", 21.0)
                for s in po_samples
                if s.get("action", {}).get("order_quantity", 0) > 0
            ]
            if target_dos:
                theta["order_up_to_days"] = max(7.0, min(60.0, sum(target_dos) / len(target_dos)))

        # ── sourcing_split: default until we capture vendor choices in PO TRM ──
        # Future: compute from the fraction of PO decisions that went to primary vs backup vendor

        return theta
