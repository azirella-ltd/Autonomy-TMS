"""
Seed Override Effectiveness Demo Data

Generates realistic override data in powell_site_agent_decisions with
counterfactual comparisons and Bayesian posteriors, so the Override
Effectiveness dashboard has data to display.

Usage:
    python -m scripts.seed_override_effectiveness [--days 90] [--overrides-per-day 5]
"""

import sys
import os
import random
import argparse
import math
from datetime import datetime, timedelta

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db.session import SessionLocal
from app.models.powell_decision import SiteAgentDecision
from app.models.override_effectiveness import (
    OverrideEffectivenessPosterior,
    CausalMatchPair,
)
from app.services.override_effectiveness_service import (
    OverrideEffectivenessService,
    TIER_MAP,
)

# Decision types to simulate (covers all 3 tiers)
DECISION_TYPES = [
    # Tier 1
    "atp_exception", "forecast_adjustment", "quality_disposition",
    # Tier 2
    "mo_execution", "to_execution", "po_timing", "order_tracking",
    # Tier 3
    "inventory_adjustment", "safety_stock", "maintenance_scheduling",
    "subcontracting",
]

SITES = ["PLANT-01", "DC-EAST", "DC-WEST", "WAREHOUSE-01", "FACTORY-02"]

# Override reason codes
REASON_CODES = [
    "MARKET_INTELLIGENCE", "CUSTOMER_COMMITMENT", "CAPACITY_CONSTRAINT",
    "SUPPLIER_ISSUE", "QUALITY_CONCERN", "COST_OPTIMIZATION",
    "SERVICE_LEVEL", "DEMAND_CHANGE", "EXPEDITE_REQUIRED",
    "RISK_MITIGATION",
]


def generate_state(decision_type):
    """Generate a realistic input_state for a decision type."""
    base = {
        "inventory_level": random.randint(50, 500),
        "backlog": random.randint(0, 100),
        "demand": random.randint(20, 200),
        "pipeline": random.randint(10, 150),
        "safety_stock": random.randint(30, 150),
        "lead_time": random.uniform(1, 14),
        "capacity_utilization": random.uniform(0.5, 0.98),
        "service_level": random.uniform(0.85, 0.99),
        "fill_rate": random.uniform(0.8, 1.0),
        "days_of_supply": random.uniform(5, 30),
    }

    if decision_type in ("atp_exception", "order_tracking"):
        base["order_qty"] = random.randint(10, 100)
        base["priority"] = random.randint(1, 5)
    elif decision_type in ("po_timing", "po_creation"):
        base["reorder_point"] = random.randint(50, 200)
        base["order_quantity"] = random.randint(100, 500)
    elif decision_type in ("mo_execution",):
        base["production_rate"] = random.uniform(50, 200)
        base["utilization"] = random.uniform(0.6, 0.95)

    return base


def generate_override_delta(decision_type):
    """
    Generate a realistic override delta.

    Distribution: ~55% beneficial, ~25% neutral, ~20% detrimental.
    Tier 1 types tend to have clearer signals (bigger deltas).
    """
    tier = TIER_MAP.get(decision_type, 3)

    # Choose outcome category
    r = random.random()
    if r < 0.55:  # Beneficial
        if tier == 1:
            return random.uniform(0.05, 0.4)
        elif tier == 2:
            return random.uniform(0.05, 0.25)
        else:
            return random.uniform(0.05, 0.15)
    elif r < 0.80:  # Neutral
        return random.uniform(-0.05, 0.05)
    else:  # Detrimental
        if tier == 1:
            return random.uniform(-0.3, -0.05)
        elif tier == 2:
            return random.uniform(-0.2, -0.05)
        else:
            return random.uniform(-0.15, -0.05)


def classify_delta(delta):
    if delta >= 0.05:
        return "BENEFICIAL"
    elif delta <= -0.05:
        return "DETRIMENTAL"
    return "NEUTRAL"


def main():
    parser = argparse.ArgumentParser(description="Seed override effectiveness data")
    parser.add_argument("--days", type=int, default=90, help="Days of history")
    parser.add_argument("--overrides-per-day", type=int, default=5, help="Overrides per day")
    parser.add_argument("--non-overrides-per-day", type=int, default=20, help="Non-overridden decisions per day")
    parser.add_argument("--user-ids", type=str, default="1,2,3", help="Comma-separated user IDs")
    args = parser.parse_args()

    user_ids = [int(x) for x in args.user_ids.split(",")]

    db = SessionLocal()
    try:
        now = datetime.utcnow()
        decision_count = 0
        override_count = 0

        for day_offset in range(args.days, 0, -1):
            base_time = now - timedelta(days=day_offset)

            # Generate non-overridden decisions (controls for matching)
            for i in range(args.non_overrides_per_day):
                dtype = random.choice(DECISION_TYPES)
                site = random.choice(SITES)
                ts = base_time + timedelta(hours=random.randint(0, 23), minutes=random.randint(0, 59))
                state = generate_state(dtype)
                reward = random.uniform(-0.3, 0.5)

                decision = SiteAgentDecision(
                    decision_id=f"seed-{day_offset:04d}-{i:04d}-ctrl",
                    site_key=site,
                    decision_type=dtype,
                    timestamp=ts,
                    input_state=state,
                    deterministic_result={"action": "baseline", "qty": state.get("demand", 100)},
                    trm_adjustment={"adjustment": random.uniform(-0.1, 0.1)},
                    final_result={"action": "adjusted", "qty": state.get("demand", 100) * random.uniform(0.9, 1.1)},
                    confidence=random.uniform(0.7, 0.98),
                    actual_outcome={"status": "completed"},
                    outcome_recorded_at=ts + timedelta(hours=24),
                    reward_signal=reward,
                    is_overridden=False,
                    created_at=ts,
                )
                db.add(decision)
                decision_count += 1

            # Generate overridden decisions
            for i in range(args.overrides_per_day):
                dtype = random.choice(DECISION_TYPES)
                site = random.choice(SITES)
                user_id = random.choice(user_ids)
                ts = base_time + timedelta(hours=random.randint(8, 18), minutes=random.randint(0, 59))
                state = generate_state(dtype)

                delta = generate_override_delta(dtype)
                classification = classify_delta(delta)
                agent_reward = random.uniform(-0.1, 0.3)
                human_reward = agent_reward + delta

                # Site BSC delta (systemic impact — sometimes different from local)
                site_bsc = delta * random.uniform(0.3, 1.2) + random.uniform(-0.05, 0.05)
                composite = 0.4 * delta + 0.6 * site_bsc

                decision = SiteAgentDecision(
                    decision_id=f"seed-{day_offset:04d}-{i:04d}-ovr",
                    site_key=site,
                    decision_type=dtype,
                    timestamp=ts,
                    input_state=state,
                    deterministic_result={"action": "baseline", "qty": state.get("demand", 100)},
                    trm_adjustment={"adjustment": random.uniform(-0.1, 0.1)},
                    final_result={"action": "override", "qty": state.get("demand", 100) * random.uniform(0.8, 1.3)},
                    confidence=random.uniform(0.5, 0.9),
                    actual_outcome={"status": "completed"},
                    outcome_recorded_at=ts + timedelta(hours=48),
                    reward_signal=human_reward,
                    is_overridden=True,
                    override_value={"qty": state.get("demand", 100) * random.uniform(0.8, 1.3)},
                    override_reason_text=f"[{random.choice(REASON_CODES)}] {random.choice(['Adjusted for customer priority', 'Market signal requires change', 'Capacity constraint override', 'Expedite to meet SLA'])}",
                    override_user_id=user_id,
                    override_timestamp=ts,
                    agent_counterfactual_reward=round(agent_reward, 4),
                    human_actual_reward=round(human_reward, 4),
                    override_delta=round(delta, 4),
                    override_classification=classification,
                    site_bsc_delta=round(site_bsc, 4),
                    composite_override_score=round(composite, 4),
                    created_at=ts,
                )
                db.add(decision)
                override_count += 1

                # Update Bayesian posterior
                OverrideEffectivenessService.update_posterior(
                    db, user_id, dtype, composite, site,
                )

        db.commit()
        print(f"Seeded {decision_count} non-overridden + {override_count} overridden decisions")
        print(f"  Total: {decision_count + override_count} decisions over {args.days} days")

        # Print posterior summary
        posteriors = db.query(OverrideEffectivenessPosterior).all()
        print(f"\nBayesian posteriors created: {len(posteriors)}")
        for p in posteriors[:10]:
            print(f"  User {p.user_id} / {p.trm_type}: "
                  f"E[p]={p.expected_effectiveness:.3f}, "
                  f"weight={p.training_weight:.3f}, "
                  f"n={p.observation_count}")

        # Run causal matching
        print("\nRunning causal matching...")
        from app.services.causal_matching_service import CausalMatchingService
        matcher = CausalMatchingService(db)
        match_stats = matcher.run_matching(lookback_days=args.days)
        print(f"  Matched: {match_stats['matched']}, "
              f"Skipped: {match_stats['skipped']}, "
              f"Failed: {match_stats['failed']}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
