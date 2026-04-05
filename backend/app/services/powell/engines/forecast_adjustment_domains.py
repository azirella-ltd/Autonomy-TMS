"""
Forecast Adjustment Domain Engines — Expanded Capabilities.

Each domain provides deterministic heuristics for a specific type of
forecast adjustment. The ForecastAdjustmentTRM delegates to these
engines based on the adjustment type.

Domains:
  1. Promotion effect estimation (learned elasticity)
  2. NPI transfer learning (similar-product matching)
  3. EOL coordination (phase-out + successor ramp)
  4. Demand sensing (POS exception detection)
  5. Cannibalization / substitution
  6. Consensus FVA gating
  7. External signal (existing — in forecast_adjustment_engine.py)

All domains return standardized AdjustmentResult dataclass.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text as sql_text

logger = logging.getLogger(__name__)


@dataclass
class AdjustmentResult:
    """Standardized result from any domain engine."""
    should_adjust: bool = False
    adjustment_pct: float = 0.0          # Signed: positive = up, negative = down
    confidence: float = 0.5
    domain: str = ""                      # promotion, npi, eol, sensing, cannibalization, consensus
    reason: str = ""
    requires_human_review: bool = True
    cannibalization_impact: Optional[Dict[str, float]] = None  # {product_id: pct}
    forward_buy_pct: Optional[float] = None  # Post-promo demand depression
    fva_expected: float = 0.0
    escalate_to_llm: bool = False
    escalation_reason: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════
# Domain 1: Promotion Effect Estimation
# ═══════════════════════════════════════════════════════════════════════

FORWARD_BUY_FRACTION = {
    "staples": 0.30,       # Customers stock up on non-perishables
    "perishables": 0.10,   # Limited forward buy for perishables
    "durables": 0.50,      # Strong forward buy for durable goods
    "default": 0.20,
}


class PromotionDomain:
    """Learned promotion elasticity from historical promo events."""

    @staticmethod
    async def evaluate(
        db,
        product_id: str,
        site_id: str,
        config_id: int,
        promo_id: Optional[int] = None,
        promo_type: Optional[str] = None,
        expected_uplift_pct: Optional[float] = None,
        expected_cannibalization_pct: Optional[float] = None,
        product_category: Optional[str] = None,
        product_type: str = "default",  # staples, perishables, durables
    ) -> AdjustmentResult:
        """Estimate promotion uplift using learned elasticity from history."""
        # Load historical promo performance for this category + type
        learned_uplift = None
        learned_cannib = None
        promo_count = 0

        try:
            result = await db.execute(
                sql_text("""
                    SELECT AVG(actual_uplift_pct) as avg_uplift,
                           AVG(actual_cannibalization_pct) as avg_cannib,
                           COUNT(*) as promo_count
                    FROM promotions
                    WHERE config_id = :config_id
                      AND status = 'completed'
                      AND actual_uplift_pct IS NOT NULL
                      AND promotion_type = COALESCE(:promo_type, promotion_type)
                """),
                {"config_id": config_id, "promo_type": promo_type},
            )
            row = result.fetchone()
            if row and row.promo_count >= 5:
                learned_uplift = row.avg_uplift
                learned_cannib = row.avg_cannib
                promo_count = row.promo_count
        except Exception as e:
            logger.debug("Could not load promo history: %s", e)

        # Blend learned (70%) + expected (30%) if enough history
        if learned_uplift is not None and promo_count >= 5:
            uplift = learned_uplift * 0.7 + (expected_uplift_pct or 0.15) * 0.3
            cannib = (learned_cannib or 0) * 0.7 + (expected_cannibalization_pct or 0) * 0.3
            confidence = min(0.80, 0.50 + promo_count * 0.03)
        else:
            # Use expected with 30% dampening (manual estimates are optimistic)
            uplift = (expected_uplift_pct or 0.15) * 0.7
            cannib = (expected_cannibalization_pct or 0) * 0.7
            confidence = 0.50

        # Forward buy estimation
        fb_fraction = FORWARD_BUY_FRACTION.get(product_type, 0.20)
        forward_buy = -(uplift * fb_fraction)  # Negative = post-promo depression

        # Cannibalization impact on siblings (if any)
        cannib_impact = None
        if cannib > 0 and product_category:
            cannib_impact = await _estimate_sibling_cannibalization(
                db, config_id, product_id, product_category, cannib
            )

        # Escalate if novel promo type with no history
        escalate = promo_count < 3 and (expected_uplift_pct or 0) > 0.25

        return AdjustmentResult(
            should_adjust=True,
            adjustment_pct=uplift / 100.0 if uplift > 1 else uplift,  # Normalize to fraction
            confidence=confidence,
            domain="promotion",
            reason=(
                f"Promotion uplift: {uplift:.1f}% "
                f"({'learned from ' + str(promo_count) + ' promos' if learned_uplift else 'estimated, dampened 30%'})"
            ),
            requires_human_review=uplift > 25 or escalate,
            cannibalization_impact=cannib_impact,
            forward_buy_pct=forward_buy,
            fva_expected=0.03 if promo_count >= 5 else 0.0,
            escalate_to_llm=escalate,
            escalation_reason="Novel promo type with < 3 historical events" if escalate else None,
        )


async def _estimate_sibling_cannibalization(
    db, config_id: int, product_id: str,
    category: str, cannib_pct: float,
) -> Dict[str, float]:
    """Estimate cannibalization impact on sibling products in the category."""
    try:
        result = await db.execute(
            sql_text("""
                SELECT p.id as product_id
                FROM product p
                JOIN product_hierarchy_node phn ON p.product_hierarchy_id = phn.id
                WHERE p.config_id = :config_id
                  AND phn.description = :category
                  AND p.id != :product_id
                LIMIT 20
            """),
            {"config_id": config_id, "category": category, "product_id": product_id},
        )
        siblings = [r.product_id for r in result.fetchall()]
        if not siblings:
            return {}

        # Distribute cannibalization equally among siblings
        per_sibling = (cannib_pct / 100.0) / len(siblings)
        return {s: -per_sibling for s in siblings}
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════════════
# Domain 2: NPI Transfer Learning
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_NPI_RAMP = [0.10, 0.25, 0.50, 0.75, 1.00]  # 5 periods
FAST_RAMP = [0.25, 0.50, 0.75, 1.00]                # 4 periods (FMCG)
SLOW_RAMP = [0.05, 0.10, 0.20, 0.35, 0.50, 0.70, 0.85, 1.00]  # 8 periods (industrial)


class NPIDomain:
    """NPI forecast using similar-product transfer learning."""

    @staticmethod
    async def evaluate(
        db,
        product_id: str,
        site_id: str,
        config_id: int,
        weeks_since_launch: int = 0,
        expected_market_share: Optional[float] = None,
        product_category: Optional[str] = None,
        product_price: Optional[float] = None,
        category_velocity: str = "medium",  # fast, medium, slow
    ) -> AdjustmentResult:
        """Estimate NPI demand using similar-product transfer."""
        # Find k-nearest similar mature products
        similar_products = await _find_similar_products(
            db, config_id, product_id, product_category, product_price
        )

        if not similar_products:
            # Cold start — escalate to LLM
            ramp = DEFAULT_NPI_RAMP
            ramp_value = ramp[min(weeks_since_launch // 4, len(ramp) - 1)]
            return AdjustmentResult(
                should_adjust=True,
                adjustment_pct=0.0,  # Can't estimate without reference
                confidence=0.30,
                domain="npi",
                reason="NPI cold-start: no similar products found. Using default ramp curve.",
                requires_human_review=True,
                escalate_to_llm=True,
                escalation_reason="No similar products for NPI transfer learning",
            )

        # Compute weighted average demand from similar products
        total_weight = 0
        weighted_demand = 0
        for sim_product_id, similarity_score, avg_demand in similar_products:
            weighted_demand += avg_demand * similarity_score
            total_weight += similarity_score

        reference_demand = weighted_demand / total_weight if total_weight > 0 else 0

        # Apply market share scaling
        if expected_market_share:
            scaled_demand = reference_demand * expected_market_share
        else:
            # Estimate from price positioning
            share = _estimate_share_from_price(product_price, similar_products)
            scaled_demand = reference_demand * share

        # Apply ramp curve
        if category_velocity == "fast":
            ramp = FAST_RAMP
        elif category_velocity == "slow":
            ramp = SLOW_RAMP
        else:
            ramp = DEFAULT_NPI_RAMP

        period_idx = min(weeks_since_launch // 4, len(ramp) - 1)
        ramp_factor = ramp[period_idx]
        npi_forecast = scaled_demand * ramp_factor

        # Estimate cannibalization on siblings
        cannib_impact = {}
        if product_category:
            cannib_pct = 0.15  # Default 15% NPI cannibalization
            for sim_id, sim_score, _ in similar_products[:3]:
                cannib_impact[sim_id] = -(cannib_pct * sim_score * 0.3)

        confidence = min(0.60, 0.30 + len(similar_products) * 0.06)

        return AdjustmentResult(
            should_adjust=True,
            adjustment_pct=ramp_factor,  # Fraction of steady-state
            confidence=confidence,
            domain="npi",
            reason=(
                f"NPI transfer from {len(similar_products)} similar products. "
                f"Week {weeks_since_launch}: {ramp_factor:.0%} of steady-state. "
                f"Reference demand: {reference_demand:.0f}/period."
            ),
            requires_human_review=True,
            cannibalization_impact=cannib_impact if cannib_impact else None,
            fva_expected=0.0,  # No FVA history for new products
        )


async def _find_similar_products(
    db, config_id: int, product_id: str,
    category: Optional[str], price: Optional[float],
    k: int = 5,
) -> List[Tuple[str, float, float]]:
    """Find k most similar mature products. Returns [(product_id, similarity, avg_demand)]."""
    try:
        # Simple attribute-based similarity: same category + price proximity
        # forecast table columns: forecast_p50 / forecast_quantity (not
        # 'quantity'), and no plan_version column.
        result = await db.execute(
            sql_text("""
                SELECT p.id, p.unit_cost,
                       COALESCE(AVG(COALESCE(f.forecast_p50, f.forecast_quantity)), 0) as avg_demand
                FROM product p
                LEFT JOIN forecast f ON f.product_id = p.id
                    AND f.config_id = :config_id
                WHERE p.config_id = :config_id
                  AND p.id != :product_id
                GROUP BY p.id, p.unit_cost
                HAVING COUNT(f.id) >= 4
                   AND COALESCE(AVG(COALESCE(f.forecast_p50, f.forecast_quantity)), 0) > 0
                LIMIT 20
            """),
            {"config_id": config_id, "product_id": product_id},
        )
        candidates = result.fetchall()
        if not candidates:
            return []

        # Score by price similarity (simple — could be expanded with more attributes)
        scored = []
        for row in candidates:
            price_sim = 1.0
            if price and row.unit_cost and row.unit_cost > 0:
                price_ratio = price / row.unit_cost
                price_sim = max(0, 1.0 - abs(1.0 - price_ratio))
            scored.append((row.id, price_sim, float(row.avg_demand)))

        # Sort by similarity descending, take top k
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]
    except Exception as e:
        logger.debug("Similar product search failed: %s", e)
        return []


def _estimate_share_from_price(
    price: Optional[float],
    similar_products: List[Tuple[str, float, float]],
) -> float:
    """Estimate market share from price positioning within category."""
    if not price or not similar_products:
        return 0.20  # Default 20%

    avg_price = sum(1.0 for _, _, _ in similar_products) / len(similar_products)  # placeholder
    # Premium = lower share, value = higher share
    if price > avg_price * 1.2:
        return 0.12  # Premium positioning
    elif price < avg_price * 0.8:
        return 0.35  # Value positioning
    else:
        return 0.25  # Mainstream


# ═══════════════════════════════════════════════════════════════════════
# Domain 3: EOL Coordination
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_PHASEOUT_CURVE = [0.90, 0.75, 0.50, 0.25, 0.10, 0.0]  # 6 periods


class EOLDomain:
    """End-of-life phase-out and successor ramp coordination."""

    @staticmethod
    async def evaluate(
        db,
        product_id: str,
        site_id: str,
        config_id: int,
        periods_until_eol: int = 6,
        successor_product_id: Optional[str] = None,
        current_baseline: float = 0.0,
    ) -> AdjustmentResult:
        """Apply EOL phase-out curve and coordinate successor ramp."""
        curve = DEFAULT_PHASEOUT_CURVE
        idx = max(0, len(curve) - periods_until_eol)
        if idx >= len(curve):
            phase_out_factor = 0.0
        else:
            phase_out_factor = curve[idx]

        adjustment_pct = phase_out_factor - 1.0  # Negative (reduction)

        # Successor coordination
        cannib_impact = None
        if successor_product_id and phase_out_factor < 0.50:
            # Successor should ramp inversely
            successor_ramp = 1.0 - phase_out_factor
            cannib_impact = {successor_product_id: successor_ramp}

        # Last-buy calculation context
        remaining_demand_factor = sum(
            curve[max(0, len(curve) - p):] for p in range(1, periods_until_eol + 1)
            if max(0, len(curve) - p) < len(curve)
        )

        return AdjustmentResult(
            should_adjust=True,
            adjustment_pct=adjustment_pct,
            confidence=0.70,
            domain="eol",
            reason=(
                f"EOL phase-out: {periods_until_eol} periods remaining. "
                f"Demand factor: {phase_out_factor:.0%} of baseline."
                + (f" Successor {successor_product_id} ramping to {1-phase_out_factor:.0%}."
                   if successor_product_id else "")
            ),
            requires_human_review=periods_until_eol <= 2,
            cannibalization_impact=cannib_impact,
        )


# ═══════════════════════════════════════════════════════════════════════
# Domain 4: Demand Sensing
# ═══════════════════════════════════════════════════════════════════════

SENSING_DECAY = [0.60, 0.30, 0.15, 0.05]  # α decay by horizon (periods +1 to +4)


class DemandSensingDomain:
    """Short-horizon demand corrections from leading indicators."""

    @staticmethod
    async def evaluate(
        db,
        product_id: str,
        site_id: str,
        config_id: int,
        actual_recent: float = 0.0,      # Actual demand last 7-14 days
        forecast_recent: float = 0.0,     # Forecast for same period
        exception_threshold: float = 0.15,  # 15% deviation triggers exception
        horizon_periods: int = 4,
    ) -> AdjustmentResult:
        """Detect demand exceptions and compute short-horizon correction."""
        if forecast_recent <= 0:
            return AdjustmentResult(domain="sensing", reason="No forecast to compare against")

        ratio = actual_recent / forecast_recent
        deviation = ratio - 1.0  # Positive = above forecast, negative = below

        if abs(deviation) < exception_threshold:
            return AdjustmentResult(
                domain="sensing",
                reason=f"No exception: deviation {deviation:.1%} within threshold {exception_threshold:.0%}",
            )

        # Exception detected — compute correction with horizon decay
        corrections = []
        for period in range(min(horizon_periods, len(SENSING_DECAY))):
            alpha = SENSING_DECAY[period]
            correction = deviation * alpha
            corrections.append(correction)

        # Primary adjustment is for period +1
        primary_correction = corrections[0] if corrections else 0

        confidence = min(0.75, 0.50 + abs(deviation) * 0.5)
        direction = "positive" if deviation > 0 else "negative"

        return AdjustmentResult(
            should_adjust=True,
            adjustment_pct=primary_correction,
            confidence=confidence,
            domain="sensing",
            reason=(
                f"Demand sensing: {direction} exception of {deviation:+.1%}. "
                f"Correction: {primary_correction:+.1%} (period +1), "
                f"decaying to {corrections[-1]:+.1%} (period +{len(corrections)})."
            ),
            requires_human_review=abs(deviation) > 0.50,
            escalate_to_llm=abs(deviation) > 0.50,
            escalation_reason=(
                f"Large demand exception ({deviation:+.0%}) with no identified cause"
                if abs(deviation) > 0.50 else None
            ),
        )


# ═══════════════════════════════════════════════════════════════════════
# Domain 5: Cannibalization / Substitution
# ═══════════════════════════════════════════════════════════════════════

class CannibalizationDomain:
    """Category share monitoring and substitution estimation."""

    @staticmethod
    async def evaluate(
        db,
        product_id: str,
        site_id: str,
        config_id: int,
        current_share: float = 0.0,      # This product's % of family demand (current)
        prior_share: float = 0.0,         # Same metric, prior period
        family_demand_change: float = 0.0,  # Family-level demand change %
        inventory_level: float = 0.0,     # Current inventory
        substitutes: Optional[List[str]] = None,
    ) -> AdjustmentResult:
        """Detect assortment migration and stockout-driven substitution."""
        share_change = current_share - prior_share

        # Assortment migration: share shifting within stable family
        if abs(share_change) > 0.05 and abs(family_demand_change) < 0.05:
            # Zero-sum: family stable, this product's share changed
            direction = "losing share" if share_change < 0 else "gaining share"
            return AdjustmentResult(
                should_adjust=True,
                adjustment_pct=share_change,  # Apply share change as % adjustment
                confidence=0.55,
                domain="cannibalization",
                reason=(
                    f"Assortment migration: {direction} ({share_change:+.1%}pp). "
                    f"Family demand stable ({family_demand_change:+.1%})."
                ),
                requires_human_review=abs(share_change) > 0.10,
            )

        # Stockout-driven substitution
        if inventory_level <= 0 and substitutes:
            # This product is OOS → demand shifts to substitutes
            lost_demand_fraction = 0.40  # 40% of demand lost (customers leave)
            substitution_fraction = 0.40  # 40% substitutes, 20% deferred
            per_substitute = substitution_fraction / len(substitutes)

            cannib_impact = {s: per_substitute for s in substitutes}

            return AdjustmentResult(
                should_adjust=True,
                adjustment_pct=-lost_demand_fraction,  # This product loses demand
                confidence=0.50,
                domain="cannibalization",
                reason=(
                    f"Stockout substitution: {lost_demand_fraction:.0%} demand lost, "
                    f"{substitution_fraction:.0%} redirected to {len(substitutes)} substitutes."
                ),
                cannibalization_impact=cannib_impact,
                requires_human_review=True,
            )

        return AdjustmentResult(
            domain="cannibalization",
            reason="No significant category share shift or substitution detected",
        )


# ═══════════════════════════════════════════════════════════════════════
# Domain 6: Consensus FVA Gating
# ═══════════════════════════════════════════════════════════════════════

class ConsensusDomain:
    """FVA-gated consensus forecast overrides."""

    @staticmethod
    async def evaluate(
        db,
        product_id: str,
        config_id: int,
        override_pct: float = 0.0,
        override_user_id: Optional[int] = None,
        product_category: Optional[str] = None,
    ) -> AdjustmentResult:
        """Accept or reject human override based on FVA track record."""
        if abs(override_pct) < 0.01:
            return AdjustmentResult(domain="consensus", reason="No override to evaluate")

        # Look up user's FVA in this category
        user_fva = 0.0
        override_count = 0
        try:
            if override_user_id:
                result = await db.execute(
                    sql_text("""
                        SELECT AVG(
                            CASE WHEN forecast_error_after IS NOT NULL AND forecast_error_before IS NOT NULL
                                 THEN forecast_error_before - forecast_error_after
                                 ELSE NULL END
                        ) as avg_fva,
                        COUNT(*) as override_count
                        FROM powell_forecast_adjustment_decisions
                        WHERE config_id = :config_id
                          AND was_applied = true
                          AND signal_source = 'sales_input'
                    """),
                    {"config_id": config_id},
                )
                row = result.fetchone()
                if row and row.override_count >= 5:
                    user_fva = row.avg_fva or 0
                    override_count = row.override_count
        except Exception:
            pass

        # Decision based on FVA
        if user_fva > 0 and override_count >= 5:
            # User adds value — accept with weight based on FVA magnitude
            weight = 1.0 if user_fva > 0.05 else 0.7
            return AdjustmentResult(
                should_adjust=True,
                adjustment_pct=override_pct * weight,
                confidence=min(0.75, 0.50 + user_fva),
                domain="consensus",
                reason=(
                    f"Consensus override accepted (FVA: {user_fva:+.2f} from "
                    f"{override_count} past overrides). Weight: {weight:.0%}."
                ),
                requires_human_review=abs(override_pct) > 0.25,
                fva_expected=user_fva,
            )
        elif user_fva <= 0 and override_count >= 5:
            # User destroys value
            if abs(override_pct) < 0.15:
                # Small override — accept with heavy dampening
                return AdjustmentResult(
                    should_adjust=True,
                    adjustment_pct=override_pct * 0.5,
                    confidence=0.40,
                    domain="consensus",
                    reason=(
                        f"Consensus override dampened 50% (user FVA: {user_fva:+.2f}, "
                        f"negative track record from {override_count} overrides)."
                    ),
                    requires_human_review=True,
                    fva_expected=user_fva,
                )
            else:
                # Large override from poor-FVA user — reject, escalate
                return AdjustmentResult(
                    should_adjust=False,
                    adjustment_pct=0,
                    confidence=0.60,
                    domain="consensus",
                    reason=(
                        f"Consensus override REJECTED: user FVA is {user_fva:+.2f} "
                        f"from {override_count} overrides. Override of {override_pct:+.0%} "
                        f"exceeds 15% threshold for negative-FVA users."
                    ),
                    requires_human_review=True,
                    escalate_to_llm=True,
                    escalation_reason=(
                        f"Large override ({override_pct:+.0%}) from user with negative FVA"
                    ),
                    fva_expected=user_fva,
                )
        else:
            # Insufficient history — accept with dampening, track
            return AdjustmentResult(
                should_adjust=True,
                adjustment_pct=override_pct * 0.7,
                confidence=0.45,
                domain="consensus",
                reason=(
                    f"Consensus override accepted with 30% dampening "
                    f"(insufficient FVA history: {override_count} overrides, need 5+)."
                ),
                requires_human_review=abs(override_pct) > 0.15,
                fva_expected=0.0,
            )
