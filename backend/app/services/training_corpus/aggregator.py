"""
Training Corpus Aggregator — Rolls up Level 1 samples to higher layers.

Pure data transformation. No new oracle calls or simulations.

  Level 1 (TRM decisions)
       ↓ aggregate by (scenario, site, window)
  Level 1.5 (Site tGNN samples)
       ↓ aggregate by (scenario, period)
  Level 2 (Tactical tGNN samples)
       ↓ aggregate by (scenario) with inferred theta*
  Level 4 (S&OP GraphSAGE samples)
"""

import logging
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training_corpus import TrainingCorpusSample

logger = logging.getLogger(__name__)


class TrainingCorpusAggregator:
    """Aggregates Level 1 (TRM) samples into Level 1.5, 2, and 4."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def aggregate_all_levels(
        self,
        tenant_id: int,
        config_id: int,
    ) -> Dict[str, int]:
        """Run all three aggregation levels. Returns counts per layer."""
        layer1_samples = await self._load_layer1_samples(config_id)
        logger.info("Aggregator: loaded %d Level 1 samples for config %d", len(layer1_samples), config_id)

        layer2_count = await self._aggregate_site_level(tenant_id, config_id, layer1_samples)
        layer3_count = await self._aggregate_tactical_level(tenant_id, config_id, layer1_samples)
        layer4_count = await self._aggregate_strategic_level(tenant_id, config_id, layer1_samples)

        await self.db.flush()

        logger.info(
            "Aggregator complete: Layer 2=%d, Layer 2=%d, Layer 4=%d",
            layer2_count, layer3_count, layer4_count,
        )
        return {
            "layer2_count": layer2_count,
            "layer3_count": layer3_count,
            "layer4_count": layer4_count,
        }

    async def _load_layer1_samples(self, config_id: int) -> List[Dict[str, Any]]:
        """Load all Layer 1 samples for a config."""
        result = await self.db.execute(
            sql_text("""
                SELECT sample_data, scenario_id, trm_type, product_id, site_id, reward
                FROM training_corpus
                WHERE config_id = :cid AND layer = 1.0
            """),
            {"cid": config_id},
        )
        rows = result.fetchall()
        samples = []
        for row in rows:
            sample = dict(row.sample_data) if row.sample_data else {}
            sample["_scenario_id"] = row.scenario_id
            sample["_trm_type"] = row.trm_type
            sample["_site_id"] = row.site_id
            sample["_product_id"] = row.product_id
            sample["_reward"] = row.reward
            samples.append(sample)
        return samples

    # ── Level 1.5: Site tGNN aggregation ──

    async def _aggregate_site_level(
        self,
        tenant_id: int,
        config_id: int,
        layer1_samples: List[Dict[str, Any]],
    ) -> int:
        """Aggregate TRM decisions by (scenario, site, time_window).

        Target: per-TRM features for the Site tGNN.
        """
        # Bucket: (scenario_id, site_id, window) -> list of samples
        buckets: Dict[Tuple[str, str, str], List[Dict]] = defaultdict(list)
        for sample in layer1_samples:
            sid = sample.get("_scenario_id", "unknown")
            site = sample.get("_site_id", "unknown")
            period = sample.get("period", 0)
            window = f"W{period // 1:02d}"  # weekly bucket
            buckets[(sid, site, window)].append(sample)

        count = 0
        for (scenario_id, site_id, window), samples_in_bucket in buckets.items():
            # Compute per-TRM features
            per_trm: Dict[str, Dict[str, float]] = defaultdict(
                lambda: {
                    "decision_count": 0,
                    "avg_confidence": 0.0,
                    "avg_urgency": 0.0,
                    "avg_reward": 0.0,
                    "total_reward": 0.0,
                }
            )
            total_rewards = 0.0
            for s in samples_in_bucket:
                trm_type = s.get("_trm_type", "unknown")
                features = per_trm[trm_type]
                features["decision_count"] += 1
                reward = s.get("_reward") or s.get("aggregate_reward", 0.5)
                features["total_reward"] += reward
                total_rewards += reward

            # Normalize averages
            for trm_type, features in per_trm.items():
                if features["decision_count"] > 0:
                    features["avg_reward"] = features["total_reward"] / features["decision_count"]

            site_aggregate_reward = total_rewards / max(len(samples_in_bucket), 1)

            sample_data = {
                "scenario_id": scenario_id,
                "site_id": site_id,
                "window": window,
                "per_trm_features": dict(per_trm),
                "site_aggregate_reward": site_aggregate_reward,
                "cross_trm_coordination_loss": 0.0,  # placeholder; computed from signal conflicts
                "decision_count": len(samples_in_bucket),
            }

            self.db.add(TrainingCorpusSample(
                tenant_id=tenant_id,
                config_id=config_id,
                layer=2.0,
                scenario_id=scenario_id,
                origin="simulation",
                site_id=site_id,
                time_window=window,
                sample_data=sample_data,
                reward=site_aggregate_reward,
                weight=1.0,
            ))
            count += 1

        return count

    # ── Level 2: Tactical tGNN aggregation ──

    async def _aggregate_tactical_level(
        self,
        tenant_id: int,
        config_id: int,
        layer1_samples: List[Dict[str, Any]],
    ) -> int:
        """Aggregate TRM decisions by (scenario, period).

        Targets: supply_outcomes, inventory_outcomes, capacity_outcomes
        for the three tactical tGNNs.
        """
        # Bucket: (scenario_id, period) -> list of samples
        buckets: Dict[Tuple[str, int], List[Dict]] = defaultdict(list)
        for sample in layer1_samples:
            sid = sample.get("_scenario_id", "unknown")
            period = sample.get("period", 0)
            buckets[(sid, period)].append(sample)

        count = 0
        for (scenario_id, period), samples_in_bucket in buckets.items():
            # Supply outcomes: from PO creation decisions
            po_samples = [s for s in samples_in_bucket if s.get("_trm_type") == "po_creation"]
            supply_by_site: Dict[str, Dict[str, float]] = defaultdict(dict)
            for s in po_samples:
                site = s.get("_site_id", "unknown")
                action = s.get("action", {})
                supply_by_site[site]["order_recommendation"] = supply_by_site[site].get("order_recommendation", 0) + action.get("order_quantity", 0)
                supply_by_site[site]["allocation_priority"] = 0.7
                supply_by_site[site]["exception_prob"] = 0.1 if s.get("_reward", 0.5) < 0.3 else 0.0

            # Inventory outcomes: from Inventory Buffer decisions
            buf_samples = [s for s in samples_in_bucket if s.get("_trm_type") == "inventory_buffer"]
            inventory_by_site: Dict[str, Dict[str, float]] = defaultdict(dict)
            for s in buf_samples:
                site = s.get("_site_id", "unknown")
                action = s.get("action", {})
                state = s.get("state_features", {})
                inventory_by_site[site]["buffer_adjustment"] = action.get("multiplier", 1.0) - 1.0
                inventory_by_site[site]["stockout_probability"] = min(1.0, state.get("stockout_count", 0) / 10.0)
                inventory_by_site[site]["rebalancing_urgency"] = 0.5 if state.get("stockout_count", 0) > 0 else 0.1

            # Capacity outcomes: derived from PO order volume vs capacity (placeholder)
            capacity_by_site: Dict[str, Dict[str, float]] = defaultdict(dict)
            for site in supply_by_site.keys():
                capacity_by_site[site]["planned_utilization"] = 0.7
                capacity_by_site[site]["feasibility_score"] = 0.85
                capacity_by_site[site]["bottleneck_risk"] = 0.15

            period_reward = sum(s.get("_reward", 0.5) or 0.5 for s in samples_in_bucket) / max(len(samples_in_bucket), 1)

            sample_data = {
                "scenario_id": scenario_id,
                "period": period,
                "supply_outcomes": dict(supply_by_site),
                "inventory_outcomes": dict(inventory_by_site),
                "capacity_outcomes": dict(capacity_by_site),
                "period_total_reward": period_reward,
                "decision_count": len(samples_in_bucket),
            }

            self.db.add(TrainingCorpusSample(
                tenant_id=tenant_id,
                config_id=config_id,
                layer=3.0,
                scenario_id=scenario_id,
                origin="simulation",
                period=str(period),
                sample_data=sample_data,
                reward=period_reward,
                weight=1.0,
            ))
            count += 1

        return count

    # ── Level 4: S&OP GraphSAGE aggregation ──

    async def _aggregate_strategic_level(
        self,
        tenant_id: int,
        config_id: int,
        layer1_samples: List[Dict[str, Any]],
    ) -> int:
        """Aggregate TRM decisions by (scenario) with inferred theta*.

        Target: optimal policy parameters (safety stock multiplier,
        service level target, reorder point days, order up to days,
        sourcing split) per site, inferred from TRM decisions.
        """
        from .theta_inference import ThetaStarInferencer
        inferencer = ThetaStarInferencer()

        # Bucket: scenario_id -> list of samples
        buckets: Dict[str, List[Dict]] = defaultdict(list)
        for sample in layer1_samples:
            sid = sample.get("_scenario_id", "unknown")
            buckets[sid].append(sample)

        count = 0
        for scenario_id, samples_in_bucket in buckets.items():
            theta_star = inferencer.infer(samples_in_bucket)

            scenario_reward = sum(s.get("_reward", 0.5) or 0.5 for s in samples_in_bucket) / max(len(samples_in_bucket), 1)

            sample_data = {
                "scenario_id": scenario_id,
                "theta_star": theta_star,
                "objective_value": 1.0 - scenario_reward,  # lower is better
                "decision_count": len(samples_in_bucket),
            }

            self.db.add(TrainingCorpusSample(
                tenant_id=tenant_id,
                config_id=config_id,
                layer=4.0,
                scenario_id=scenario_id,
                origin="simulation",
                sample_data=sample_data,
                reward=scenario_reward,
                weight=1.0,
            ))
            count += 1

        return count
