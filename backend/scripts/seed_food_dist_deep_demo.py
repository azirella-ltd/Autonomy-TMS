#!/usr/bin/env python3
"""
Seed Food Dist Deep Demo — Action Layer Data

Populates all 4 Powell levels with interconnected, narrative-driven data
so every dashboard page has meaningful content when demoing the Food
Distribution network.

Narrative: "Late February 2026 — A Week in the Life of CDC_WEST"
Timeline: Monday Feb 24 – Friday Feb 28, 2026

Six interconnected storylines:
  1. March Madness demand surge (Chicken Breast, Turkey Breast)
  2. Rich Products weather delay (Cream Cheese, Greek Yogurt, Butter)
  3. Greek Yogurt quality hold (texture test failure, 2400 cases)
  4. Ice Cream spring ramp-up (Ice Cream Vanilla, Sorbet Mango)
  5. QUICKSERV Arizona surge (Chicken Breast — 3 new Phoenix stores)
  6. Dairy cost pressure (Butter, Cheddar — commodity prices +12%)

Prerequisites: Run seed_food_dist_demo.py and seed_food_dist_planning_data.py first.
Idempotent: Deletes and recreates action layer records each run.

Usage:
    docker compose exec backend python -m scripts.seed_food_dist_deep_demo
"""

import os
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import and_, delete
from sqlalchemy.orm import Session, sessionmaker
from app.db.session import sync_engine

# Import all models to ensure mapper relationships resolve correctly
import app.models  # noqa: F401

# Models
from app.models.tenant import Tenant
from app.models.user import User
from app.models.supply_chain_config import SupplyChainConfig
from app.models.executive_briefing import ExecutiveBriefing, BriefingFollowup
from app.models.decision_tracking import (
    AgentDecision, DecisionType, DecisionStatus, DecisionUrgency,
    PerformanceMetric, SOPWorklistItem,
)
from app.models.condition_alert import (
    ConditionAlert, ConditionType, ConditionSeverity, ConditionResolution,
    ScenarioEvaluation,
)
from app.models.powell_decisions import (
    PowellATPDecision, PowellPODecision, PowellRebalanceDecision,
    PowellOrderException, PowellForecastAdjustmentDecision,
    PowellBufferDecision,
)
from app.models.override_effectiveness import OverrideEffectivenessPosterior


# =============================================================================
# Constants — Product, Site, and Supplier IDs from Food Dist config
# =============================================================================

FOOD_DIST_TENANT_NAME = "Food Distributor"
FOOD_DIST_CONFIG_NAME = "Food Dist Distribution Network"

# Timeline
MON = datetime(2026, 2, 24, 6, 0, 0)
TUE = datetime(2026, 2, 25, 6, 0, 0)
WED = datetime(2026, 2, 26, 6, 0, 0)
THU = datetime(2026, 2, 27, 6, 0, 0)
FRI = datetime(2026, 2, 28, 6, 0, 0)
DEMO_START = MON
DEMO_END = FRI + timedelta(hours=18)

# Products (CFG22_ prefix, 5 categories × 5 products)
FP001 = "CFG22_FP001"  # Chicken Breast IQF
FP002 = "CFG22_FP002"  # Beef Patties 80/20
FP004 = "CFG22_FP004"  # Turkey Breast Deli
RD001 = "CFG22_RD001"  # Cheddar Block Sharp
RD003 = "CFG22_RD003"  # Cream Cheese Block
RD004 = "CFG22_RD004"  # Greek Yogurt Plain
RD005 = "CFG22_RD005"  # Butter Salted Grade AA
FD001 = "CFG22_FD001"  # Ice Cream Vanilla Premium
FD002 = "CFG22_FD002"  # Sorbet Mango
FD003 = "CFG22_FD003"  # Gelato Chocolate
FD004 = "CFG22_FD004"  # Pie Apple 10 inch
FD005 = "CFG22_FD005"  # Cake Chocolate Layer

# Site codes
DC_SITE = "CDC_WEST"

# Supplier codes
TYSON = "TYSON"
KRAFT = "KRAFT"
RICHPROD = "RICHPROD"
NESTLE = "NESTLE"
SYSCOMEAT = "SYSCOMEAT"
LANDOLAKES = "LANDOLAKES"
CONAGRA = "CONAGRA"

# Customer codes
QUICKSERV = "QUICKSERV"
METROGRO = "METROGRO"
RESTSUPPLY = "RESTSUPPLY"
CAMPUSDINE = "CAMPUSDINE"
FAMREST = "FAMREST"
SCHLDFOOD = "SCHLDFOOD"

# Product names (for human-readable fields)
PRODUCT_NAMES = {
    FP001: "Chicken Breast IQF 10lb",
    FP002: "Beef Patties 80/20 10lb",
    FP004: "Turkey Breast Deli 8lb",
    RD001: "Cheddar Block Sharp 5lb",
    RD003: "Cream Cheese Block 3lb",
    RD004: "Greek Yogurt Plain 32oz",
    RD005: "Butter Salted AA 36ct",
    FD001: "Ice Cream Vanilla Premium 3gal",
    FD002: "Sorbet Mango 3gal",
    FD003: "Gelato Chocolate 2.5gal",
    FD004: "Pie Apple 10in 6ct",
    FD005: "Cake Chocolate Layer 4ct",
}


# =============================================================================
# Lookup helpers
# =============================================================================

def lookup_tenant(db: Session) -> int:
    tenant = db.query(Tenant).filter(Tenant.name == FOOD_DIST_TENANT_NAME).first()
    if not tenant:
        print(f"ERROR: Tenant '{FOOD_DIST_TENANT_NAME}' not found. Run seed_food_dist_demo.py first.")
        sys.exit(1)
    return tenant.id


def lookup_config(db: Session, tenant_id: int) -> int:
    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.name == FOOD_DIST_CONFIG_NAME,
        SupplyChainConfig.tenant_id == tenant_id,
    ).order_by(SupplyChainConfig.id.desc()).first()
    if not config:
        # Fallback: search without tenant filter
        config = db.query(SupplyChainConfig).filter(
            SupplyChainConfig.name == FOOD_DIST_CONFIG_NAME,
        ).order_by(SupplyChainConfig.id.desc()).first()
    if not config:
        print(f"ERROR: Config '{FOOD_DIST_CONFIG_NAME}' not found. Run seed_food_dist_demo.py first.")
        sys.exit(1)
    return config.id


def lookup_users(db: Session, tenant_id: int) -> dict:
    """Lookup demo users by email, return {role_key: user_id}."""
    user_map = {}
    for key, email in [
        ("admin", "admin@distdemo.com"),
        ("exec", "exec@distdemo.com"),
        ("sop", "sopdir@distdemo.com"),
        ("mps", "mpsmanager@distdemo.com"),
        ("atp", "atp@distdemo.com"),
    ]:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user_map[key] = user.id
        else:
            print(f"  Warning: User {email} not found, using admin")
    if not user_map:
        print("ERROR: No demo users found. Run seed_food_dist_demo.py first.")
        sys.exit(1)
    # Fallback: use admin for any missing role
    admin_id = user_map.get("admin", list(user_map.values())[0])
    for key in ["admin", "exec", "sop", "mps", "atp"]:
        if key not in user_map:
            user_map[key] = admin_id
    return user_map


# =============================================================================
# Cleanup
# =============================================================================

def cleanup(db: Session, tenant_id: int, config_id: int):
    """Delete existing action layer records for this tenant in demo date range."""
    print("\nCleaning up existing demo action layer data...")

    # Tenant-scoped tables
    for model, name in [
        (BriefingFollowup, "briefing_followups"),
        (ExecutiveBriefing, "executive_briefings"),
        (SOPWorklistItem, "sop_worklist_items"),
        (AgentDecision, "agent_decisions"),
        (PerformanceMetric, "performance_metrics"),
    ]:
        # BriefingFollowup doesn't have tenant_id — delete via briefing
        if model == BriefingFollowup:
            briefing_ids = [
                b.id for b in db.query(ExecutiveBriefing.id).filter(
                    ExecutiveBriefing.tenant_id == tenant_id,
                    ExecutiveBriefing.created_at >= DEMO_START,
                    ExecutiveBriefing.created_at <= DEMO_END,
                ).all()
            ]
            if briefing_ids:
                count = db.query(BriefingFollowup).filter(
                    BriefingFollowup.briefing_id.in_(briefing_ids)
                ).delete(synchronize_session=False)
                print(f"  Deleted {count} {name}")
            continue

        count = db.query(model).filter(
            model.tenant_id == tenant_id,
            model.created_at >= DEMO_START,
            model.created_at <= DEMO_END,
        ).delete(synchronize_session=False)
        if count:
            print(f"  Deleted {count} {name}")

    # Condition alerts and scenario evaluations
    for model, name in [
        (ScenarioEvaluation, "scenario_evaluations"),
        (ConditionAlert, "condition_alerts"),
    ]:
        count = db.query(model).filter(
            model.tenant_id == tenant_id,
            model.created_at >= DEMO_START,
            model.created_at <= DEMO_END,
        ).delete(synchronize_session=False)
        if count:
            print(f"  Deleted {count} {name}")

    # Powell tables (config-scoped)
    for model, name in [
        (PowellATPDecision, "powell_atp_decisions"),
        (PowellPODecision, "powell_po_decisions"),
        (PowellRebalanceDecision, "powell_rebalance_decisions"),
        (PowellOrderException, "powell_order_exceptions"),
        (PowellForecastAdjustmentDecision, "powell_forecast_adjustment_decisions"),
        (PowellBufferDecision, "powell_buffer_decisions"),
    ]:
        count = db.query(model).filter(
            model.config_id == config_id,
            model.created_at >= DEMO_START,
            model.created_at <= DEMO_END,
        ).delete(synchronize_session=False)
        if count:
            print(f"  Deleted {count} {name}")

    # Override posteriors (user-scoped, delete all for this tenant's users)
    user_ids = [
        u.id for u in db.query(User.id).filter(User.tenant_id == tenant_id).all()
    ]
    if user_ids:
        count = db.query(OverrideEffectivenessPosterior).filter(
            OverrideEffectivenessPosterior.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
        if count:
            print(f"  Deleted {count} override_effectiveness_posteriors")

    db.flush()
    print("  Cleanup complete.")


# =============================================================================
# Section 1: Executive Briefing
# =============================================================================

def seed_executive_briefing(db: Session, tenant_id: int, users: dict) -> int:
    """Seed one completed weekly briefing. Returns briefing ID."""
    print("\n1. Seeding executive briefing...")

    briefing = ExecutiveBriefing(
        tenant_id=tenant_id,
        requested_by=users["exec"],
        briefing_type="weekly",
        status="completed",
        title="Weekly Strategy Briefing \u2014 Feb 24, 2026",
        data_pack={
            "metrics_snapshot": {
                "service_level_pct": 94.2,
                "fill_rate_pct": 96.1,
                "inventory_turns": 18.3,
                "otif_pct": 91.8,
                "total_skus_managed": 25,
                "active_orders": 47,
                "open_exceptions": 8,
                "agent_score": 72,
                "override_rate_pct": 18.0,
            },
            "period": "2026-W09",
            "config_name": FOOD_DIST_CONFIG_NAME,
        },
        narrative=(
            "## Weekly Performance Summary\n\n"
            "Service levels held at 94.2% this week despite multiple concurrent disruptions. "
            "Fill rate remains strong at 96.1%, though we expect pressure in the coming week "
            "from the convergence of three events: the March Madness pre-order surge, weather-related "
            "supplier delays from Rich Products in Buffalo, and a quality hold on Greek Yogurt.\n\n"
            "## Key Storylines This Week\n\n"
            "### 1. March Madness Pre-Order Surge\n"
            "QUICKSERV Foods and several restaurant chains have begun pre-ordering frozen proteins "
            "ahead of the NCAA tournament. Chicken Breast IQF (CFG22_FP001) demand is up 35% over "
            "baseline, and Turkey Breast (CFG22_FP004) is showing similar uplift. The AI agent has "
            "already flagged this as a demand spike and recommended buffer increases. We should "
            "pre-position inventory this week to avoid stockouts during peak tournament weekends.\n\n"
            "### 2. Rich Products Weather Delay\n"
            "A winter storm system over western New York is delaying shipments from Rich Products "
            "(Buffalo). Three dairy SKUs are affected: Cream Cheese (CFG22_RD003), Greek Yogurt "
            "(CFG22_RD004), and Butter (CFG22_RD005). Expected delay is 3 days. The agent has "
            "evaluated contingency scenarios including split-sourcing from Land O'Lakes.\n\n"
            "### 3. Greek Yogurt Quality Hold\n"
            "2,400 cases of Greek Yogurt Plain (CFG22_RD004) failed texture consistency testing "
            "on Monday. The lot is on quality hold pending disposition. Scenario evaluation suggests "
            "rework is the best option (75% confidence), preserving $36K in inventory value.\n\n"
            "### 4. Ice Cream Spring Ramp-Up\n"
            "Seasonal demand models indicate the spring transition is beginning 1 week early this year. "
            "Ice Cream Vanilla (CFG22_FD001) and Sorbet Mango (CFG22_FD002) need buffer increases "
            "to support the ramp. Production capacity at Kraft is approaching constraint levels.\n\n"
            "### 5. QUICKSERV Arizona Expansion\n"
            "Three new QUICKSERV locations in Phoenix are opening March 1. Initial stocking orders "
            "for Chicken Breast IQF are 25% above the per-store average. The agent has auto-executed "
            "forecast adjustments and safety stock replenishment for this customer.\n\n"
            "### 6. Dairy Commodity Cost Pressure\n"
            "Butter and cheddar spot prices are up 12% week-over-week due to reduced output from "
            "the Upper Midwest. The agent recommends evaluating forward contracts with Conagra and "
            "considering a modest demand forecast reduction (-8%) to account for potential menu "
            "price adjustments by restaurant customers."
        ),
        recommendations=[
            {
                "id": 1,
                "title": "Pre-position frozen proteins for March Madness",
                "score": 88,
                "impact": "$145K incremental revenue opportunity",
                "urgency": "high",
                "action": "Approve buffer increases for FP001 (+35%) and FP004 (+20%); expedite Tyson PO",
            },
            {
                "id": 2,
                "title": "Activate Rich Products contingency plan",
                "score": 82,
                "impact": "Prevent $89K service level impact",
                "urgency": "high",
                "action": "Split-source dairy SKUs: 60% Rich Products (delayed), 40% Land O'Lakes (expedite)",
            },
            {
                "id": 3,
                "title": "Disposition Greek Yogurt quality hold",
                "score": 75,
                "impact": "Recover $36K inventory value",
                "urgency": "high",
                "action": "Approve rework of 2,400 cases; expected 48h turnaround, 92% yield",
            },
            {
                "id": 4,
                "title": "Increase ice cream/sorbet buffers for spring",
                "score": 85,
                "impact": "$12K holding cost increase, prevents $45K stockout risk",
                "urgency": "medium",
                "action": "Increase buffer multiplier to 1.25x for FD001/FD002; coordinate with Kraft on capacity",
            },
            {
                "id": 5,
                "title": "Monitor dairy commodity exposure",
                "score": 65,
                "impact": "$23K margin pressure if sustained",
                "urgency": "low",
                "action": "Evaluate 30-day forward contracts; adjust demand forecast -8% for price-sensitive SKUs",
            },
        ],
        executive_summary=(
            "Service levels remain above target at 94.2% but face headwinds from the convergence "
            "of March Madness demand (+35% frozen proteins), a Rich Products weather delay (3 days, "
            "3 dairy SKUs), and a Greek Yogurt quality hold (2,400 cases). Agent score is 72 with "
            "18% override rate. Recommended actions: pre-position proteins, activate split-sourcing "
            "contingency, and approve yogurt rework."
        ),
        model_used="claude-sonnet-4-6",
        tokens_used=2847,
        generation_time_ms=3200,
        created_at=MON + timedelta(hours=1),
        completed_at=MON + timedelta(hours=1, minutes=3),
    )
    db.add(briefing)
    db.flush()
    print(f"  Created executive briefing (id={briefing.id})")
    return briefing.id


# =============================================================================
# Section 2: Briefing Follow-ups
# =============================================================================

def seed_briefing_followups(db: Session, briefing_id: int, users: dict):
    """Seed 3 follow-up Q&A exchanges."""
    print("\n2. Seeding briefing follow-ups...")

    followups = [
        BriefingFollowup(
            briefing_id=briefing_id,
            asked_by=users["exec"],
            question="What's our exposure if Rich Products delays extend to 5 days instead of 3?",
            answer=(
                "If the delay extends to 5 days, our exposure increases significantly:\n\n"
                "- **Cream Cheese (RD003)**: Current buffer covers 4.2 days. At 5-day delay, "
                "we'd have 0.8 days of shortfall affecting 3 customers. Estimated revenue at risk: $18K.\n"
                "- **Greek Yogurt (RD004)**: Already on quality hold, so the delay compounds the shortage. "
                "Combined exposure: $52K.\n"
                "- **Butter (RD005)**: Buffer covers 6.1 days, so we'd absorb a 5-day delay with "
                "1.1 days of buffer remaining.\n\n"
                "**Recommendation**: If delay confirmation comes by Wednesday, activate the full "
                "Land O'Lakes contingency (100% shift, not just 40%) for RD003 and RD004. "
                "Butter can remain on Rich Products."
            ),
            model_used="claude-sonnet-4-6",
            tokens_used=412,
            created_at=MON + timedelta(hours=2),
        ),
        BriefingFollowup(
            briefing_id=briefing_id,
            asked_by=users["sop"],
            question="Can we source Greek Yogurt from the backup supplier to cover the quality hold?",
            answer=(
                "Yes. Land O'Lakes (LANDOLAKES) is configured as an alternate supplier for "
                "refrigerated dairy with the following parameters:\n\n"
                "- **Lead time**: 6 days (vs Rich Products' normal 10 days)\n"
                "- **MOQ**: 500 cases\n"
                "- **Price premium**: +8% over Rich Products contract price\n"
                "- **Reliability**: 97% OTIF\n\n"
                "For the 2,400 cases on quality hold, a Land O'Lakes PO of 2,500 cases "
                "(MOQ-rounded) would cost approximately $10,625 at the premium rate. "
                "If the rework succeeds (estimated 92% yield = 2,208 cases recovered), "
                "the net gap is only ~200 cases, which current buffer covers.\n\n"
                "**Recommendation**: Proceed with rework first (48h). If rework yield is below 85%, "
                "trigger the Land O'Lakes backup PO immediately."
            ),
            model_used="claude-sonnet-4-6",
            tokens_used=387,
            created_at=MON + timedelta(hours=3),
        ),
        BriefingFollowup(
            briefing_id=briefing_id,
            asked_by=users["exec"],
            question="What's the March Madness revenue opportunity if we pre-position inventory?",
            answer=(
                "Based on last year's March Madness period (March 15\u2013April 7) and this year's "
                "early pre-order signals:\n\n"
                "**Revenue Uplift Estimate**:\n"
                "- Chicken Breast IQF: +35% demand × 4 weeks × $34.99/case × ~280 cases/week = **$54K**\n"
                "- Turkey Breast Deli: +20% demand × 4 weeks × $46.99/case × ~150 cases/week = **$28K**\n"
                "- Total frozen protein uplift: **$82K direct**\n"
                "- Cross-sell (beverages, pizza ingredients): estimated **$63K**\n"
                "- **Total opportunity: ~$145K**\n\n"
                "**Cost of pre-positioning**: $8.2K incremental holding cost (buffer increases + "
                "expedite premium on Tyson PO). ROI: 17.7x.\n\n"
                "**Risk**: If tournament demand doesn't materialize, excess inventory has "
                "365-day shelf life on frozen proteins, so downside is limited to holding cost."
            ),
            model_used="claude-sonnet-4-6",
            tokens_used=445,
            created_at=MON + timedelta(hours=4),
        ),
    ]
    db.add_all(followups)
    db.flush()
    print(f"  Created {len(followups)} briefing follow-ups")


# =============================================================================
# Section 3: S&OP Worklist Items
# =============================================================================

def seed_sop_worklist(db: Session, tenant_id: int, users: dict):
    """Seed 6 S&OP worklist items, one per storyline."""
    print("\n3. Seeding S&OP worklist items...")

    items = [
        # Story 1: March Madness
        SOPWorklistItem(
            tenant_id=tenant_id,
            item_code=FP001,
            item_name=PRODUCT_NAMES[FP001],
            category="Frozen Proteins",
            issue_type="DEMAND",
            issue_summary=(
                "March Madness pre-ordering has driven 35% demand uplift for frozen proteins. "
                "QUICKSERV and 4 restaurant chains are accelerating orders. Buffer increases and "
                "expedited Tyson PO recommended to capture $145K revenue opportunity."
            ),
            impact_value=145000.0,
            impact_description="$145K incremental revenue if pre-positioned",
            impact_type="positive",
            due_description="Friday EOD",
            urgency=DecisionUrgency.URGENT,
            agent_recommendation="Approve buffer increase to 1.35x for FP001 and 1.20x for FP004; expedite Tyson PO by 3 days",
            agent_reasoning="Historical March Madness uplift averaged 28-42% for frozen proteins. Pre-positioning ROI is 17.7x with limited downside (365-day shelf life).",
            status=DecisionStatus.ACCEPTED,
            resolved_by=users["sop"],
            resolution_action="accept",
            resolution_notes="Approved. Coordinate with Tyson on expedite confirmation.",
            resolved_at=TUE + timedelta(hours=3),
            created_at=MON + timedelta(hours=8),
            updated_at=TUE + timedelta(hours=3),
        ),
        # Story 2: Rich Products weather delay
        SOPWorklistItem(
            tenant_id=tenant_id,
            item_code=RD003,
            item_name=PRODUCT_NAMES[RD003],
            category="Refrigerated Dairy",
            issue_type="SUPPLY",
            issue_summary=(
                "Winter storm over Buffalo NY is delaying Rich Products shipments by 3 days. "
                "Three dairy SKUs affected (RD003, RD004, RD005). Current buffer covers 4.2 days "
                "for cream cheese but Greek Yogurt is already on quality hold. Split-sourcing from "
                "Land O'Lakes recommended."
            ),
            impact_value=-89000.0,
            impact_description="$89K service level risk if no contingency",
            impact_type="negative",
            due_description="Wednesday EOD",
            urgency=DecisionUrgency.URGENT,
            agent_recommendation="Split source: 60% Rich Products (accept delay), 40% Land O'Lakes (expedite 6-day lead time)",
            agent_reasoning="Scenario evaluation shows split-source minimizes cost while maintaining 93%+ service level. Full switch to Land O'Lakes has +8% price premium.",
            status=DecisionStatus.PENDING,
            created_at=MON + timedelta(hours=10),
            updated_at=MON + timedelta(hours=10),
        ),
        # Story 3: Greek Yogurt quality hold
        SOPWorklistItem(
            tenant_id=tenant_id,
            item_code=RD004,
            item_name=PRODUCT_NAMES[RD004],
            category="Refrigerated Dairy",
            issue_type="QUALITY",
            issue_summary=(
                "2,400 cases of Greek Yogurt Plain failed texture consistency testing. Lot is on "
                "quality hold. Three options evaluated: rework (recommended, 75% confidence), "
                "scrap ($36K loss), or use-as-is with 15% discount. Rework expected to yield 92% "
                "(2,208 cases) within 48 hours."
            ),
            impact_value=-36000.0,
            impact_description="$36K inventory at risk",
            impact_type="negative",
            due_description="Thursday EOD",
            urgency=DecisionUrgency.URGENT,
            agent_recommendation="Approve rework: 48h turnaround, 92% expected yield, preserves $33K of $36K value",
            agent_reasoning="Rework has highest expected value ($33.1K preserved) vs scrap ($0) or discount ($30.6K). Quality team confirms texture issue is correctable.",
            status=DecisionStatus.PENDING,
            created_at=MON + timedelta(hours=14),
            updated_at=MON + timedelta(hours=14),
        ),
        # Story 4: Ice Cream spring ramp
        SOPWorklistItem(
            tenant_id=tenant_id,
            item_code=FD001,
            item_name=PRODUCT_NAMES[FD001],
            category="Frozen Desserts",
            issue_type="INVENTORY",
            issue_summary=(
                "Seasonal demand models show spring transition starting 1 week early. Ice Cream "
                "Vanilla and Sorbet Mango need buffer increases from 1.0x to 1.25x. Kraft production "
                "capacity is approaching 88% utilization \u2014 need to coordinate ramp-up window."
            ),
            impact_value=12000.0,
            impact_description="$12K holding cost increase, prevents $45K stockout risk",
            impact_type="trade-off",
            due_description="Friday",
            urgency=DecisionUrgency.STANDARD,
            agent_recommendation="Increase buffer multiplier to 1.25x for FD001 and FD002; coordinate with Kraft on capacity reservation",
            agent_reasoning="Early spring signal confirmed by 3-week temperature forecast and social media trend analysis. Last year's late ramp caused $62K in lost sales.",
            status=DecisionStatus.ACCEPTED,
            resolved_by=users["sop"],
            resolution_action="accept",
            resolved_at=WED + timedelta(hours=2),
            created_at=TUE + timedelta(hours=9),
            updated_at=WED + timedelta(hours=2),
        ),
        # Story 5: QUICKSERV Arizona
        SOPWorklistItem(
            tenant_id=tenant_id,
            item_code=FP001,
            item_name=PRODUCT_NAMES[FP001],
            category="Frozen Proteins",
            issue_type="DEMAND",
            issue_summary=(
                "Three new QUICKSERV locations opening in Phoenix March 1. Initial stocking orders "
                "are 25% above per-store average. Agent has auto-executed forecast adjustment (+25% "
                "for Chicken Breast at Phoenix) and safety stock replenishment."
            ),
            impact_value=67000.0,
            impact_description="$67K new store revenue over first 90 days",
            impact_type="positive",
            due_description="Next week",
            urgency=DecisionUrgency.STANDARD,
            agent_recommendation="Auto-executed: forecast +25% for QUICKSERV Phoenix, buffer +15%, safety stock PO issued",
            agent_reasoning="New store opening patterns from QUICKSERV history show 25-30% above steady-state in first 90 days. Agent confidence 0.88 exceeded auto-execute threshold.",
            status=DecisionStatus.AUTO_EXECUTED,
            created_at=TUE + timedelta(hours=11),
            updated_at=TUE + timedelta(hours=11),
        ),
        # Story 6: Dairy cost pressure
        SOPWorklistItem(
            tenant_id=tenant_id,
            item_code=RD005,
            item_name=PRODUCT_NAMES[RD005],
            category="Refrigerated Dairy",
            issue_type="FINANCIAL",
            issue_summary=(
                "Butter and cheddar spot prices up 12% week-over-week. Upper Midwest dairy output "
                "reduced due to weather. Agent recommends evaluating forward contracts and modest "
                "demand forecast reduction (-8%) for price-sensitive restaurant customers."
            ),
            impact_value=-23000.0,
            impact_description="$23K margin erosion if sustained 30 days",
            impact_type="negative",
            due_description="Review next week",
            urgency=DecisionUrgency.LOW,
            agent_recommendation="Evaluate 30-day forward contracts with Conagra; adjust demand forecast -8% for butter/cheddar",
            agent_reasoning="Commodity cycles typically last 4-6 weeks. Forward contract locks in current rate. Demand adjustment accounts for restaurant menu price increases reducing order volume.",
            status=DecisionStatus.PENDING,
            created_at=WED + timedelta(hours=10),
            updated_at=WED + timedelta(hours=10),
        ),
    ]
    db.add_all(items)
    db.flush()
    print(f"  Created {len(items)} S&OP worklist items")


# =============================================================================
# Section 4: Agent Decisions (Copilot Worklist)
# =============================================================================

def seed_agent_decisions(db: Session, tenant_id: int, users: dict):
    """Seed 15 agent decisions across storylines."""
    print("\n4. Seeding agent decisions...")

    decisions = [
        # --- Demand Forecast (3) ---
        AgentDecision(
            tenant_id=tenant_id, user_id=users["mps"],
            decision_type=DecisionType.DEMAND_FORECAST,
            item_code=FP001, item_name=PRODUCT_NAMES[FP001], category="Frozen Proteins",
            issue_summary="March Madness demand uplift detected: +35% for Chicken Breast IQF across restaurant segment",
            impact_value=54000.0, impact_description="$54K revenue uplift",
            agent_recommendation="Increase demand forecast by 35% for weeks 10-14 (March Madness period)",
            agent_reasoning="QUICKSERV pre-orders +40%, 3 other restaurant chains signaling increased orders. Historical March Madness uplift averaged 28-42%.",
            agent_confidence=0.88, recommended_value=378.0, previous_value=280.0,
            status=DecisionStatus.ACCEPTED, urgency=DecisionUrgency.URGENT,
            user_action="accept", action_timestamp=TUE + timedelta(hours=2),
            agent_type="trm", planning_cycle="2026-W09",
            created_at=MON + timedelta(hours=9), updated_at=TUE + timedelta(hours=2),
        ),
        AgentDecision(
            tenant_id=tenant_id, user_id=users["mps"],
            decision_type=DecisionType.DEMAND_FORECAST,
            item_code=FP004, item_name=PRODUCT_NAMES[FP004], category="Frozen Proteins",
            issue_summary="March Madness demand uplift for Turkey Breast Deli: +20% across catering segment",
            impact_value=28000.0, impact_description="$28K revenue uplift",
            agent_recommendation="Increase demand forecast by 20% for weeks 10-14",
            agent_reasoning="Catering segment shows consistent Turkey Breast uplift during major sporting events. Lower confidence than chicken due to less pre-order signal.",
            agent_confidence=0.79, recommended_value=180.0, previous_value=150.0,
            status=DecisionStatus.ACCEPTED, urgency=DecisionUrgency.STANDARD,
            user_action="accept", action_timestamp=TUE + timedelta(hours=3),
            agent_type="trm", planning_cycle="2026-W09",
            created_at=MON + timedelta(hours=11), updated_at=TUE + timedelta(hours=3),
        ),
        AgentDecision(
            tenant_id=tenant_id, user_id=users["mps"],
            decision_type=DecisionType.DEMAND_FORECAST,
            item_code=FP001, item_name=PRODUCT_NAMES[FP001], category="Frozen Proteins",
            issue_summary="QUICKSERV Arizona new store openings: 3 locations, demand +25% above per-store average",
            impact_value=67000.0, impact_description="$67K first-90-day revenue",
            agent_recommendation="Adjust forecast +25% for QUICKSERV Phoenix demand zone, weeks 10-22",
            agent_reasoning="New store opening patterns from QUICKSERV history (12 openings in 2025) show 25-30% above steady-state demand in first 90 days.",
            agent_confidence=0.82, recommended_value=225.0, previous_value=180.0,
            status=DecisionStatus.AUTO_EXECUTED, urgency=DecisionUrgency.STANDARD,
            agent_type="trm", planning_cycle="2026-W09",
            created_at=TUE + timedelta(hours=10), updated_at=TUE + timedelta(hours=10),
        ),
        # --- Supply Plan (3) ---
        AgentDecision(
            tenant_id=tenant_id, user_id=users["mps"],
            decision_type=DecisionType.SUPPLY_PLAN,
            item_code=RD003, item_name=PRODUCT_NAMES[RD003], category="Refrigerated Dairy",
            issue_summary="Rich Products weather delay: 3-day shipment delay on Cream Cheese. Emergency PO to Land O'Lakes recommended.",
            impact_value=-18000.0, impact_description="$18K service risk without action",
            agent_recommendation="Issue emergency PO to Land O'Lakes for 800 cases of Cream Cheese (40% of Rich Products volume)",
            agent_reasoning="Split-source strategy minimizes cost: Rich Products order remains active (60%), Land O'Lakes fills gap at +8% premium. Net cost: $2.1K premium vs $18K service risk.",
            agent_confidence=0.84, recommended_value=800.0,
            status=DecisionStatus.PENDING, urgency=DecisionUrgency.URGENT,
            agent_type="trm", planning_cycle="2026-W09",
            created_at=MON + timedelta(hours=15), updated_at=MON + timedelta(hours=15),
        ),
        AgentDecision(
            tenant_id=tenant_id, user_id=users["mps"],
            decision_type=DecisionType.SUPPLY_PLAN,
            item_code=FD003, item_name=PRODUCT_NAMES[FD003], category="Frozen Desserts",
            issue_summary="Expedite Kraft frozen dessert shipment to offset production capacity constraint for ice cream ramp-up",
            impact_value=-4500.0, impact_description="$4.5K expedite premium",
            agent_recommendation="Request expedited shipping from Kraft (-2 days lead time) for FD001/FD002 next shipment",
            agent_reasoning="Kraft capacity at 88% utilization. Expediting current order ensures product arrives before buffer drops below safety level during spring ramp.",
            agent_confidence=0.76,
            status=DecisionStatus.REJECTED, urgency=DecisionUrgency.STANDARD,
            user_action="reject", override_reason="Kraft confirmed they can increase next week's shipment by 15% without expedite premium. Adjusted order quantity instead.",
            action_timestamp=WED + timedelta(hours=4),
            agent_type="trm", planning_cycle="2026-W09",
            created_at=TUE + timedelta(hours=14), updated_at=WED + timedelta(hours=4),
        ),
        AgentDecision(
            tenant_id=tenant_id, user_id=users["mps"],
            decision_type=DecisionType.SUPPLY_PLAN,
            item_code=RD005, item_name=PRODUCT_NAMES[RD005], category="Refrigerated Dairy",
            issue_summary="Dairy commodity prices +12%. Consider alternate sourcing or forward contract for butter.",
            impact_value=-23000.0, impact_description="$23K margin impact if sustained",
            agent_recommendation="Issue exploratory RFQ to Conagra for 30-day forward contract on butter at current spot rate",
            agent_reasoning="Commodity cycle analysis suggests 4-6 week duration. Forward contract at today's rate locks in 12% increase vs potential further escalation.",
            agent_confidence=0.72,
            status=DecisionStatus.PENDING, urgency=DecisionUrgency.LOW,
            agent_type="trm", planning_cycle="2026-W09",
            created_at=WED + timedelta(hours=11), updated_at=WED + timedelta(hours=11),
        ),
        # --- ATP Allocation (3) ---
        AgentDecision(
            tenant_id=tenant_id, user_id=users["atp"],
            decision_type=DecisionType.ATP_ALLOCATION,
            item_code=FP001, item_name=PRODUCT_NAMES[FP001], category="Frozen Proteins",
            issue_summary="QUICKSERV priority allocation: 450 cases Chicken Breast at P1 priority for March Madness pre-order",
            impact_value=15700.0, impact_description="$15.7K order value",
            agent_recommendation="Allocate 450 cases at P1 priority from current ATP pool; backfill from buffer for P3+ customers",
            agent_reasoning="QUICKSERV is P1 priority customer with 98% payment reliability. March Madness orders have 90%+ conversion rate. Buffer can absorb P3 demand deferral.",
            agent_confidence=0.92, recommended_value=450.0,
            status=DecisionStatus.ACCEPTED, urgency=DecisionUrgency.URGENT,
            user_action="accept", action_timestamp=MON + timedelta(hours=16),
            agent_type="trm", planning_cycle="2026-W09",
            created_at=MON + timedelta(hours=14), updated_at=MON + timedelta(hours=16),
        ),
        AgentDecision(
            tenant_id=tenant_id, user_id=users["atp"],
            decision_type=DecisionType.ATP_ALLOCATION,
            item_code=RD003, item_name=PRODUCT_NAMES[RD003], category="Refrigerated Dairy",
            issue_summary="Cream Cheese ATP rationing due to Rich Products delay: Metro Grocery order partially fulfilled",
            impact_value=-8500.0, impact_description="$8.5K partial fill impact",
            agent_recommendation="Partial fill Metro Grocery order at 60% (720 of 1200 cases); defer remainder to next week",
            agent_reasoning="Rich Products delay reduces available supply. Metro Grocery is P3 priority. Higher-priority QUICKSERV and Restaurant Supply orders must be protected.",
            agent_confidence=0.85, recommended_value=720.0, previous_value=1200.0,
            status=DecisionStatus.REJECTED, urgency=DecisionUrgency.URGENT,
            user_action="reject", override_reason="Metro Grocery contractual minimum is 900 cases. Adjusted to 900 cases partial fill to meet contract obligation.",
            user_value=900.0, action_timestamp=TUE + timedelta(hours=9),
            agent_type="trm", planning_cycle="2026-W09",
            created_at=TUE + timedelta(hours=7), updated_at=TUE + timedelta(hours=9),
        ),
        AgentDecision(
            tenant_id=tenant_id, user_id=users["atp"],
            decision_type=DecisionType.ATP_ALLOCATION,
            item_code=FD001, item_name=PRODUCT_NAMES[FD001], category="Frozen Desserts",
            issue_summary="Ice Cream Vanilla allocation: School District Foods order deferred to next week due to spring ramp priority",
            impact_value=-3200.0, impact_description="$3.2K deferred revenue",
            agent_recommendation="Defer School District Foods ice cream order (90 cases) by 5 days; prioritize restaurant channel",
            agent_reasoning="School District Foods is P4 priority, order is non-urgent (school break upcoming). Restaurant channel pre-orders for spring events take priority.",
            agent_confidence=0.78, recommended_value=0.0, previous_value=90.0,
            status=DecisionStatus.PENDING, urgency=DecisionUrgency.STANDARD,
            agent_type="trm", planning_cycle="2026-W09",
            created_at=WED + timedelta(hours=8), updated_at=WED + timedelta(hours=8),
        ),
        # --- Inventory Rebalance (2) ---
        AgentDecision(
            tenant_id=tenant_id, user_id=users["mps"],
            decision_type=DecisionType.INVENTORY_REBALANCE,
            item_code=RD004, item_name=PRODUCT_NAMES[RD004], category="Refrigerated Dairy",
            issue_summary="Transfer 600 cases Greek Yogurt from cold storage overflow to main DC to cover quality hold shortfall",
            impact_value=2500.0, impact_description="$2.5K transfer cost, prevents $12K stockout",
            agent_recommendation="Execute transfer of 600 cases from overflow cold storage; estimated 1-day transit",
            agent_reasoning="Overflow storage has 1,800 cases from prior Rich Products over-delivery. Transfer covers immediate gap while quality hold is resolved.",
            agent_confidence=0.81, recommended_value=600.0,
            status=DecisionStatus.ACCEPTED, urgency=DecisionUrgency.URGENT,
            user_action="accept", action_timestamp=TUE + timedelta(hours=5),
            agent_type="trm", planning_cycle="2026-W09",
            created_at=TUE + timedelta(hours=4), updated_at=TUE + timedelta(hours=5),
        ),
        AgentDecision(
            tenant_id=tenant_id, user_id=users["mps"],
            decision_type=DecisionType.INVENTORY_REBALANCE,
            item_code=FD001, item_name=PRODUCT_NAMES[FD001], category="Frozen Desserts",
            issue_summary="Transfer 200 cases Ice Cream Vanilla from overflow freezer to main DC for spring ramp",
            impact_value=1800.0, impact_description="$1.8K transfer cost",
            agent_recommendation="Execute freezer-to-DC transfer of 200 cases; supports buffer increase",
            agent_reasoning="Overflow freezer has 350 cases from winter overstock. Transfer augments buffer increase for spring ramp.",
            agent_confidence=0.85, recommended_value=200.0,
            status=DecisionStatus.AUTO_EXECUTED, urgency=DecisionUrgency.STANDARD,
            agent_type="trm", planning_cycle="2026-W09",
            created_at=WED + timedelta(hours=6), updated_at=WED + timedelta(hours=6),
        ),
        # --- Safety Stock (2) ---
        AgentDecision(
            tenant_id=tenant_id, user_id=users["mps"],
            decision_type=DecisionType.SAFETY_STOCK,
            item_code=FD001, item_name=PRODUCT_NAMES[FD001], category="Frozen Desserts",
            issue_summary="Buffer increase needed for Ice Cream Vanilla: spring ramp starting 1 week early",
            impact_value=12000.0, impact_description="$12K additional holding cost",
            agent_recommendation="Increase buffer multiplier from 1.0x to 1.25x (150 to 188 cases)",
            agent_reasoning="Seasonal demand model and 3-week temperature forecast confirm early spring onset. Last year's late ramp caused $62K lost sales.",
            agent_confidence=0.90, recommended_value=188.0, previous_value=150.0,
            status=DecisionStatus.ACCEPTED, urgency=DecisionUrgency.STANDARD,
            user_action="accept", action_timestamp=WED + timedelta(hours=3),
            agent_type="trm", planning_cycle="2026-W09",
            created_at=TUE + timedelta(hours=15), updated_at=WED + timedelta(hours=3),
        ),
        AgentDecision(
            tenant_id=tenant_id, user_id=users["mps"],
            decision_type=DecisionType.SAFETY_STOCK,
            item_code=FP001, item_name=PRODUCT_NAMES[FP001], category="Frozen Proteins",
            issue_summary="Buffer increase for Chicken Breast IQF to support March Madness demand surge",
            impact_value=5600.0, impact_description="$5.6K additional holding cost",
            agent_recommendation="Increase buffer multiplier from 1.0x to 1.35x (200 to 270 cases)",
            agent_reasoning="March Madness demand uplift of 35% requires proportional buffer increase. Frozen product has 365-day shelf life, minimal obsolescence risk.",
            agent_confidence=0.87, recommended_value=270.0, previous_value=200.0,
            status=DecisionStatus.PENDING, urgency=DecisionUrgency.URGENT,
            agent_type="trm", planning_cycle="2026-W09",
            created_at=MON + timedelta(hours=12), updated_at=MON + timedelta(hours=12),
        ),
        # --- Replenishment (2) ---
        AgentDecision(
            tenant_id=tenant_id, user_id=users["mps"],
            decision_type=DecisionType.REPLENISHMENT,
            item_code=FP001, item_name=PRODUCT_NAMES[FP001], category="Frozen Proteins",
            issue_summary="Expedited replenishment for Chicken Breast IQF to support QUICKSERV new store stocking",
            impact_value=3200.0, impact_description="$3.2K expedite premium",
            agent_recommendation="Expedite Tyson PO for 500 additional cases with 3-day lead time reduction",
            agent_reasoning="QUICKSERV March 1 opening requires inventory in-DC by Feb 27. Standard 7-day Tyson lead time is insufficient. Expedite to 4-day.",
            agent_confidence=0.83, recommended_value=500.0,
            status=DecisionStatus.PENDING, urgency=DecisionUrgency.URGENT,
            agent_type="trm", planning_cycle="2026-W09",
            created_at=TUE + timedelta(hours=8), updated_at=TUE + timedelta(hours=8),
        ),
        AgentDecision(
            tenant_id=tenant_id, user_id=users["mps"],
            decision_type=DecisionType.REPLENISHMENT,
            item_code=RD001, item_name=PRODUCT_NAMES[RD001], category="Refrigerated Dairy",
            issue_summary="Standard replenishment cycle for Cheddar Block: approaching reorder point",
            impact_value=0.0, impact_description="Standard cycle, no incremental cost",
            agent_recommendation="Issue standard PO to Conagra for 400 cases, standard 8-day lead time",
            agent_reasoning="Inventory position at 112% of reorder point. Standard replenishment within normal cycle. No urgency.",
            agent_confidence=0.95, recommended_value=400.0,
            status=DecisionStatus.AUTO_EXECUTED, urgency=DecisionUrgency.LOW,
            agent_type="trm", planning_cycle="2026-W09",
            created_at=THU + timedelta(hours=6), updated_at=THU + timedelta(hours=6),
        ),
    ]
    db.add_all(decisions)
    db.flush()
    print(f"  Created {len(decisions)} agent decisions")


# =============================================================================
# Section 5: Condition Alerts
# =============================================================================

def seed_condition_alerts(db: Session, tenant_id: int) -> dict:
    """Seed 8 condition alerts. Returns {key: alert_id} for FK references."""
    print("\n5. Seeding condition alerts...")

    alerts_data = [
        # Story 2: Frozen desserts ATP shortfall (from weather delay cascading to ice cream)
        ("atp_shortfall", ConditionAlert(
            tenant_id=tenant_id,
            condition_type=ConditionType.ATP_SHORTFALL,
            entity_type="product", entity_id=RD003,
            is_active=True, severity=ConditionSeverity.CRITICAL,
            first_detected_at=MON + timedelta(hours=14),
            last_checked_at=WED + timedelta(hours=6),
            duration_hours=40.0,
            current_value=720.0, threshold_value=1200.0, deviation_pct=-40.0,
            context={"cause": "Rich Products weather delay + increased demand", "affected_customers": [METROGRO, FAMREST]},
            created_at=MON + timedelta(hours=14), updated_at=WED + timedelta(hours=6),
        )),
        # Story 3: Greek Yogurt below safety stock
        ("inv_below_safety", ConditionAlert(
            tenant_id=tenant_id,
            condition_type=ConditionType.INVENTORY_BELOW_SAFETY,
            entity_type="product", entity_id=RD004,
            is_active=True, severity=ConditionSeverity.WARNING,
            first_detected_at=MON + timedelta(hours=11),
            last_checked_at=WED + timedelta(hours=6),
            duration_hours=43.0,
            current_value=1200.0, threshold_value=1800.0, deviation_pct=-33.3,
            context={"cause": "Quality hold on 2400 cases", "quality_hold_lot": "LOT-RD004-20260224"},
            created_at=MON + timedelta(hours=11), updated_at=WED + timedelta(hours=6),
        )),
        # Story 1: Wings demand spike
        ("demand_spike", ConditionAlert(
            tenant_id=tenant_id,
            condition_type=ConditionType.DEMAND_SPIKE,
            entity_type="product", entity_id=FP001,
            is_active=True, severity=ConditionSeverity.WARNING,
            first_detected_at=MON + timedelta(hours=9),
            last_checked_at=THU + timedelta(hours=6),
            duration_hours=69.0,
            current_value=378.0, threshold_value=280.0, deviation_pct=35.0,
            context={"trigger": "March Madness pre-orders", "top_customer": QUICKSERV},
            created_at=MON + timedelta(hours=9), updated_at=THU + timedelta(hours=6),
        )),
        # Story 5: Tenders forecast deviation (resolved)
        ("forecast_dev_resolved", ConditionAlert(
            tenant_id=tenant_id,
            condition_type=ConditionType.FORECAST_DEVIATION,
            entity_type="product", entity_id=FP001,
            is_active=False, severity=ConditionSeverity.INFO,
            first_detected_at=MON + timedelta(hours=8),
            last_checked_at=TUE + timedelta(hours=12),
            duration_hours=28.0,
            current_value=225.0, threshold_value=180.0, deviation_pct=25.0,
            context={"trigger": "QUICKSERV Arizona new stores", "auto_resolved": True},
            resolution=ConditionResolution.AGENT_RESOLVED,
            resolved_at=TUE + timedelta(hours=12),
            resolved_by_agent="forecast_adjustment_trm",
            resolution_notes="Forecast automatically adjusted +25% for QUICKSERV Phoenix zone.",
            created_at=MON + timedelta(hours=8), updated_at=TUE + timedelta(hours=12),
        )),
        # Story 4: Ice cream capacity constraint
        ("capacity_constraint", ConditionAlert(
            tenant_id=tenant_id,
            condition_type=ConditionType.CAPACITY_CONSTRAINT,
            entity_type="supplier", entity_id=KRAFT,
            is_active=True, severity=ConditionSeverity.WARNING,
            first_detected_at=TUE + timedelta(hours=10),
            last_checked_at=THU + timedelta(hours=6),
            duration_hours=44.0,
            current_value=88.0, threshold_value=85.0, deviation_pct=3.5,
            context={"resource": "Kraft frozen dessert production line", "products_affected": [FD001, FD002, FD003]},
            created_at=TUE + timedelta(hours=10), updated_at=THU + timedelta(hours=6),
        )),
        # Story 2: Rich Products order at risk
        ("order_at_risk", ConditionAlert(
            tenant_id=tenant_id,
            condition_type=ConditionType.ORDER_AT_RISK,
            entity_type="order", entity_id="PO-RICHPROD-2026-0224",
            is_active=True, severity=ConditionSeverity.CRITICAL,
            first_detected_at=MON + timedelta(hours=10),
            last_checked_at=WED + timedelta(hours=6),
            duration_hours=44.0,
            current_value=3.0, threshold_value=0.0, deviation_pct=100.0,
            context={"delay_days": 3, "cause": "Winter storm Buffalo NY", "supplier": RICHPROD, "products": [RD003, RD004, RD005]},
            created_at=MON + timedelta(hours=10), updated_at=WED + timedelta(hours=6),
        )),
        # Story 6: Butter price threshold
        ("price_breach", ConditionAlert(
            tenant_id=tenant_id,
            condition_type=ConditionType.FORECAST_DEVIATION,
            entity_type="product", entity_id=RD005,
            is_active=True, severity=ConditionSeverity.INFO,
            first_detected_at=WED + timedelta(hours=8),
            last_checked_at=THU + timedelta(hours=6),
            duration_hours=22.0,
            current_value=95.20, threshold_value=85.00, deviation_pct=12.0,
            context={"metric": "spot_price_per_case", "commodity": "butter", "cause": "Upper Midwest output reduction"},
            created_at=WED + timedelta(hours=8), updated_at=THU + timedelta(hours=6),
        )),
        # Story 1: Pizza ingredients overstock (resolved)
        ("overstock_resolved", ConditionAlert(
            tenant_id=tenant_id,
            condition_type=ConditionType.INVENTORY_ABOVE_MAX,
            entity_type="product", entity_id=FD004,
            is_active=False, severity=ConditionSeverity.INFO,
            first_detected_at=MON + timedelta(hours=6),
            last_checked_at=TUE + timedelta(hours=6),
            duration_hours=24.0,
            current_value=520.0, threshold_value=450.0, deviation_pct=15.6,
            context={"cause": "Early receipt from Nestle, will deplete naturally"},
            resolution=ConditionResolution.SELF_RESOLVED,
            resolved_at=TUE + timedelta(hours=6),
            resolution_notes="Inventory returned to normal range through regular demand consumption.",
            created_at=MON + timedelta(hours=6), updated_at=TUE + timedelta(hours=6),
        )),
    ]

    alert_ids = {}
    for key, alert in alerts_data:
        db.add(alert)
        db.flush()
        alert_ids[key] = alert.id

    print(f"  Created {len(alerts_data)} condition alerts")
    return alert_ids


# =============================================================================
# Section 6: Scenario Evaluations
# =============================================================================

def seed_scenario_evaluations(db: Session, tenant_id: int, alert_ids: dict):
    """Seed 3 what-if scenario evaluations."""
    print("\n6. Seeding scenario evaluations...")

    evaluations = [
        # Story 2: Rich Products contingency
        ScenarioEvaluation(
            tenant_id=tenant_id,
            triggered_by_condition_id=alert_ids.get("atp_shortfall"),
            trigger_type="condition",
            trigger_entity_type="product",
            trigger_entity_id=RD003,
            scenarios_count=3,
            scenario_definitions=[
                {"name": "Wait for Rich Products", "description": "Accept 3-day delay, rely on buffer"},
                {"name": "Split source 60/40", "description": "60% Rich Products (delayed), 40% Land O'Lakes (expedite)"},
                {"name": "Full switch to Land O'Lakes", "description": "100% shift to Land O'Lakes at +8% premium"},
            ],
            scenario_results=[
                {"name": "Wait", "service_level": 87.2, "cost": 0, "risk": "high", "overall_score": 62},
                {"name": "Split source", "service_level": 94.8, "cost": 2100, "risk": "low", "overall_score": 88},
                {"name": "Full switch", "service_level": 96.1, "cost": 5400, "risk": "very_low", "overall_score": 79},
            ],
            recommended_scenario_index=1,
            recommended_scenario_name="Split source 60/40",
            recommendation_confidence=0.82,
            recommendation_reason="Split source achieves 94.8% service level at $2.1K cost — best cost/service trade-off. Full switch has diminishing returns at 2.6x cost.",
            recommended_overall_score=88.0,
            recommended_service_level=94.8,
            recommended_total_cost=2100.0,
            probability_of_success=0.89,
            value_at_risk=18000.0,
            trade_offs=[
                {"dimension": "cost_vs_service", "description": "Split source costs $2.1K but recovers 7.6% service level vs waiting"},
                {"dimension": "supplier_risk", "description": "Introduces Land O'Lakes dependency, but only for 40% of volume"},
            ],
            ranking_overall=[1, 0, 2],
            ranking_financial=[0, 1, 2],
            ranking_customer=[2, 1, 0],
            evaluation_time_ms=1250.0,
            simulations_run=1000,
            evaluated_at=MON + timedelta(hours=16),
            created_at=MON + timedelta(hours=16),
        ),
        # Story 1: March Madness pre-positioning
        ScenarioEvaluation(
            tenant_id=tenant_id,
            triggered_by_condition_id=alert_ids.get("demand_spike"),
            trigger_type="condition",
            trigger_entity_type="product",
            trigger_entity_id=FP001,
            scenarios_count=3,
            scenario_definitions=[
                {"name": "Standard operations", "description": "No pre-positioning, react to orders as they come"},
                {"name": "Moderate pre-build", "description": "Buffer +20%, expedite 1 Tyson PO"},
                {"name": "Aggressive pre-build", "description": "Buffer +35%, expedite 2 POs, pre-ship to regional staging"},
            ],
            scenario_results=[
                {"name": "Standard", "service_level": 82.5, "cost": 0, "revenue_captured": 95000, "overall_score": 58},
                {"name": "Moderate", "service_level": 93.1, "cost": 5200, "revenue_captured": 132000, "overall_score": 86},
                {"name": "Aggressive", "service_level": 97.8, "cost": 12800, "revenue_captured": 145000, "overall_score": 82},
            ],
            recommended_scenario_index=1,
            recommended_scenario_name="Moderate pre-build",
            recommendation_confidence=0.88,
            recommendation_reason="Moderate pre-build captures 91% of revenue opportunity at 41% of aggressive cost. Marginal return on aggressive is only $13K revenue for $7.6K incremental cost.",
            recommended_overall_score=86.0,
            recommended_service_level=93.1,
            recommended_total_cost=5200.0,
            probability_of_success=0.91,
            value_at_risk=5200.0,
            trade_offs=[
                {"dimension": "cost_vs_revenue", "description": "Moderate captures 91% of upside at 41% of aggressive investment"},
                {"dimension": "obsolescence", "description": "Low risk — 365-day shelf life on frozen proteins"},
            ],
            ranking_overall=[1, 2, 0],
            ranking_financial=[1, 2, 0],
            ranking_customer=[2, 1, 0],
            evaluation_time_ms=980.0,
            simulations_run=1000,
            evaluated_at=MON + timedelta(hours=12),
            created_at=MON + timedelta(hours=12),
        ),
        # Story 3: Greek Yogurt disposition
        ScenarioEvaluation(
            tenant_id=tenant_id,
            triggered_by_condition_id=alert_ids.get("inv_below_safety"),
            trigger_type="condition",
            trigger_entity_type="product",
            trigger_entity_id=RD004,
            scenarios_count=3,
            scenario_definitions=[
                {"name": "Rework", "description": "Rework 2400 cases, 48h turnaround, 92% expected yield"},
                {"name": "Scrap", "description": "Scrap entire lot, order replacement from Land O'Lakes"},
                {"name": "Use-as-is (discount)", "description": "Sell at 15% discount to price-sensitive customers"},
            ],
            scenario_results=[
                {"name": "Rework", "value_preserved": 33120, "cost": 3800, "time_days": 2, "overall_score": 81},
                {"name": "Scrap", "value_preserved": 0, "cost": 36000, "time_days": 6, "overall_score": 32},
                {"name": "Use-as-is", "value_preserved": 30600, "cost": 0, "time_days": 0, "overall_score": 74},
            ],
            recommended_scenario_index=0,
            recommended_scenario_name="Rework",
            recommendation_confidence=0.75,
            recommendation_reason="Rework preserves $33.1K value at $3.8K cost (net $29.3K). Use-as-is is close second but risks customer perception. Scrap is worst option.",
            recommended_overall_score=81.0,
            recommended_total_cost=3800.0,
            probability_of_success=0.92,
            value_at_risk=36000.0,
            trade_offs=[
                {"dimension": "value_vs_time", "description": "Rework takes 48h but preserves 92% of value vs instant use-as-is"},
                {"dimension": "quality_vs_cost", "description": "Rework maintains brand quality standards; discount may affect perception"},
            ],
            ranking_overall=[0, 2, 1],
            ranking_financial=[0, 2, 1],
            ranking_customer=[0, 2, 1],
            evaluation_time_ms=850.0,
            simulations_run=500,
            evaluated_at=MON + timedelta(hours=15),
            created_at=MON + timedelta(hours=15),
        ),
    ]
    db.add_all(evaluations)
    db.flush()
    print(f"  Created {len(evaluations)} scenario evaluations")


# =============================================================================
# Section 7: Powell ATP Decisions
# =============================================================================

def seed_powell_atp_decisions(db: Session, config_id: int):
    """Seed 12 ATP consumption decisions."""
    print("\n7. Seeding Powell ATP decisions...")

    decisions = [
        # QUICKSERV high-priority orders (P1-P2) — all fulfilled
        PowellATPDecision(
            config_id=config_id, order_id="SO-QUICKSERV-2026-0301",
            product_id=FP001, location_id=DC_SITE,
            requested_qty=450.0, order_priority=1,
            can_fulfill=True, promised_qty=450.0,
            consumption_breakdown={"1": 450},
            decision_method="trm", confidence=0.94,
            created_at=MON + timedelta(hours=14),
        ),
        PowellATPDecision(
            config_id=config_id, order_id="SO-QUICKSERV-2026-0302",
            product_id=FP004, location_id=DC_SITE,
            requested_qty=200.0, order_priority=1,
            can_fulfill=True, promised_qty=200.0,
            consumption_breakdown={"1": 200},
            decision_method="trm", confidence=0.93,
            created_at=MON + timedelta(hours=15),
        ),
        PowellATPDecision(
            config_id=config_id, order_id="SO-RESTSUPPLY-2026-0224",
            product_id=FP001, location_id=DC_SITE,
            requested_qty=300.0, order_priority=2,
            can_fulfill=True, promised_qty=300.0,
            consumption_breakdown={"2": 280, "5": 20},
            decision_method="trm", confidence=0.91,
            created_at=MON + timedelta(hours=16),
        ),
        PowellATPDecision(
            config_id=config_id, order_id="SO-CAMPUSDINE-2026-0224",
            product_id=FD001, location_id=DC_SITE,
            requested_qty=150.0, order_priority=2,
            can_fulfill=True, promised_qty=150.0,
            consumption_breakdown={"2": 150},
            decision_method="trm", confidence=0.89,
            created_at=TUE + timedelta(hours=8),
        ),
        # Standard customer orders (P3) — 2 fulfilled, 1 partial
        PowellATPDecision(
            config_id=config_id, order_id="SO-FAMREST-2026-0225",
            product_id=FP001, location_id=DC_SITE,
            requested_qty=180.0, order_priority=3,
            can_fulfill=True, promised_qty=180.0,
            consumption_breakdown={"3": 180},
            decision_method="trm", confidence=0.87,
            created_at=TUE + timedelta(hours=10),
        ),
        PowellATPDecision(
            config_id=config_id, order_id="SO-PREMCATER-2026-0225",
            product_id=RD005, location_id=DC_SITE,
            requested_qty=120.0, order_priority=3,
            can_fulfill=True, promised_qty=120.0,
            consumption_breakdown={"3": 120},
            decision_method="trm", confidence=0.86,
            created_at=TUE + timedelta(hours=11),
        ),
        PowellATPDecision(
            config_id=config_id, order_id="SO-METROGRO-2026-0225",
            product_id=RD003, location_id=DC_SITE,
            requested_qty=1200.0, order_priority=3,
            can_fulfill=False, promised_qty=720.0,
            consumption_breakdown={"3": 600, "4": 120},
            decision_method="trm", confidence=0.78,
            was_committed=True, actual_fulfilled_qty=900.0,
            created_at=TUE + timedelta(hours=7),
        ),
        # Low-priority orders (P4-P5) — mixed fulfillment
        PowellATPDecision(
            config_id=config_id, order_id="SO-SCHLDFOOD-2026-0226",
            product_id=FD001, location_id=DC_SITE,
            requested_qty=90.0, order_priority=4,
            can_fulfill=False, promised_qty=0.0,
            consumption_breakdown={},
            decision_method="trm", confidence=0.82,
            created_at=WED + timedelta(hours=8),
        ),
        PowellATPDecision(
            config_id=config_id, order_id="SO-GREENVAL-2026-0226",
            product_id=RD004, location_id=DC_SITE,
            requested_qty=80.0, order_priority=5,
            can_fulfill=False, promised_qty=45.0,
            consumption_breakdown={"5": 45},
            decision_method="trm", confidence=0.75,
            created_at=WED + timedelta(hours=9),
        ),
        PowellATPDecision(
            config_id=config_id, order_id="SO-COASTHLTH-2026-0226",
            product_id=FP002, location_id=DC_SITE,
            requested_qty=200.0, order_priority=4,
            can_fulfill=True, promised_qty=200.0,
            consumption_breakdown={"4": 200},
            decision_method="trm", confidence=0.88,
            created_at=WED + timedelta(hours=10),
        ),
        # Post-rebalancing fulfillments
        PowellATPDecision(
            config_id=config_id, order_id="SO-GREENVAL-2026-0227",
            product_id=RD004, location_id=DC_SITE,
            requested_qty=80.0, order_priority=5,
            can_fulfill=True, promised_qty=80.0,
            consumption_breakdown={"5": 80},
            decision_method="trm", confidence=0.84,
            created_at=THU + timedelta(hours=8),
        ),
        PowellATPDecision(
            config_id=config_id, order_id="SO-SCHLDFOOD-2026-0228",
            product_id=FD001, location_id=DC_SITE,
            requested_qty=90.0, order_priority=4,
            can_fulfill=True, promised_qty=90.0,
            consumption_breakdown={"4": 90},
            decision_method="trm", confidence=0.86,
            created_at=FRI + timedelta(hours=7),
        ),
    ]
    db.add_all(decisions)
    db.flush()
    print(f"  Created {len(decisions)} Powell ATP decisions")


# =============================================================================
# Section 8: Powell PO Decisions
# =============================================================================

def seed_powell_po_decisions(db: Session, config_id: int):
    """Seed 6 PO creation decisions."""
    print("\n8. Seeding Powell PO decisions...")

    decisions = [
        # Story 2: Emergency PO to Land O'Lakes
        PowellPODecision(
            config_id=config_id,
            product_id=RD003, location_id=DC_SITE, supplier_id=LANDOLAKES,
            recommended_qty=800.0,
            trigger_reason="supply_disruption", urgency="urgent", confidence=0.78,
            inventory_position=720.0, days_of_supply=2.8, forecast_30_day=7800.0,
            expected_receipt_date=date(2026, 3, 3), expected_cost=7200.0,
            created_at=MON + timedelta(hours=17),
        ),
        # Story 6: Standard dairy reorder
        PowellPODecision(
            config_id=config_id,
            product_id=RD001, location_id=DC_SITE, supplier_id=CONAGRA,
            recommended_qty=400.0,
            trigger_reason="reorder_point", urgency="standard", confidence=0.91,
            inventory_position=2240.0, days_of_supply=8.5, forecast_30_day=7900.0,
            expected_receipt_date=date(2026, 3, 6), expected_cost=6200.0,
            created_at=THU + timedelta(hours=7),
        ),
        # Story 1: Expedited Chicken Breast for March Madness
        PowellPODecision(
            config_id=config_id,
            product_id=FP001, location_id=DC_SITE, supplier_id=TYSON,
            recommended_qty=500.0,
            trigger_reason="demand_surge", urgency="urgent", confidence=0.85,
            inventory_position=1400.0, days_of_supply=4.1, forecast_30_day=10200.0,
            expected_receipt_date=date(2026, 2, 28), expected_cost=14250.0,
            created_at=TUE + timedelta(hours=9),
        ),
        # Story 5: Tenders safety stock replenishment
        PowellPODecision(
            config_id=config_id,
            product_id=FP001, location_id=DC_SITE, supplier_id=TYSON,
            recommended_qty=350.0,
            trigger_reason="safety_stock_replenishment", urgency="standard", confidence=0.88,
            inventory_position=1800.0, days_of_supply=5.3, forecast_30_day=10200.0,
            expected_receipt_date=date(2026, 3, 4), expected_cost=9975.0,
            created_at=WED + timedelta(hours=7),
        ),
        # Story 4: Ice cream ingredients for spring ramp
        PowellPODecision(
            config_id=config_id,
            product_id=FD001, location_id=DC_SITE, supplier_id=KRAFT,
            recommended_qty=300.0,
            trigger_reason="seasonal_ramp", urgency="standard", confidence=0.92,
            inventory_position=650.0, days_of_supply=6.2, forecast_30_day=3150.0,
            expected_receipt_date=date(2026, 3, 7), expected_cost=8400.0,
            created_at=WED + timedelta(hours=10),
        ),
        # Story 3: Backup yogurt PO
        PowellPODecision(
            config_id=config_id,
            product_id=RD004, location_id=DC_SITE, supplier_id=LANDOLAKES,
            recommended_qty=500.0,
            trigger_reason="quality_hold_contingency", urgency="urgent", confidence=0.72,
            inventory_position=1200.0, days_of_supply=3.1, forecast_30_day=11600.0,
            expected_receipt_date=date(2026, 3, 2), expected_cost=2125.0,
            created_at=TUE + timedelta(hours=6),
        ),
    ]
    db.add_all(decisions)
    db.flush()
    print(f"  Created {len(decisions)} Powell PO decisions")


# =============================================================================
# Section 9: Powell Rebalance Decisions
# =============================================================================

def seed_powell_rebalance_decisions(db: Session, config_id: int):
    """Seed 4 rebalancing decisions."""
    print("\n9. Seeding Powell rebalance decisions...")

    decisions = [
        # Story 3: Yogurt replenishment CDC_WEST → RDC_NW
        PowellRebalanceDecision(
            config_id=config_id,
            product_id=RD004, from_site=DC_SITE, to_site="RDC_NW",
            recommended_qty=600.0,
            reason="stockout_prevention", urgency=0.85, confidence=0.81,
            source_dos_before=12.5, source_dos_after=8.2,
            dest_dos_before=3.1, dest_dos_after=5.8,
            expected_cost=2500.0,
            was_executed=True, actual_qty=600.0, actual_cost=2350.0, service_impact=4.2,
            created_at=TUE + timedelta(hours=5),
        ),
        # Story 4: Ice cream replenishment CDC_WEST → RDC_SW
        PowellRebalanceDecision(
            config_id=config_id,
            product_id=FD001, from_site=DC_SITE, to_site="RDC_SW",
            recommended_qty=200.0,
            reason="seasonal_ramp", urgency=0.6, confidence=0.85,
            source_dos_before=15.0, source_dos_after=9.8,
            dest_dos_before=6.2, dest_dos_after=8.5,
            expected_cost=1800.0,
            was_executed=True, actual_qty=200.0, actual_cost=1750.0, service_impact=2.3,
            created_at=WED + timedelta(hours=7),
        ),
        # Story 1: Wings pre-positioning CDC_WEST → RDC_SW (Phoenix region)
        PowellRebalanceDecision(
            config_id=config_id,
            product_id=FP001, from_site=DC_SITE, to_site="RDC_SW",
            recommended_qty=300.0,
            reason="demand_surge", urgency=0.75, confidence=0.79,
            source_dos_before=5.3, source_dos_after=4.4,
            dest_dos_before=0.0, dest_dos_after=3.8,
            expected_cost=3200.0,
            created_at=WED + timedelta(hours=14),
        ),
        # Story 2: Cross-RDC rebalancing RDC_NW → RDC_SW
        PowellRebalanceDecision(
            config_id=config_id,
            product_id=RD003, from_site="RDC_NW", to_site="RDC_SW",
            recommended_qty=400.0,
            reason="inventory_imbalance", urgency=0.9, confidence=0.74,
            source_dos_before=9.1, source_dos_after=5.8,
            dest_dos_before=2.8, dest_dos_after=4.5,
            expected_cost=3800.0,
            created_at=TUE + timedelta(hours=14),
        ),
    ]
    db.add_all(decisions)
    db.flush()
    print(f"  Created {len(decisions)} Powell rebalance decisions")


# =============================================================================
# Section 10: Powell Order Exceptions
# =============================================================================

def seed_powell_order_exceptions(db: Session, config_id: int):
    """Seed 5 order tracking exceptions."""
    print("\n10. Seeding Powell order exceptions...")

    exceptions = [
        # Story 2: Rich Products PO delayed
        PowellOrderException(
            config_id=config_id, order_id="PO-RICHPROD-2026-0224",
            order_type="purchase_order", order_status="in_transit",
            exception_type="DELAYED", severity="high",
            recommended_action="expedite",
            description="Rich Products shipment delayed 3 days due to winter storm in Buffalo NY region",
            impact_assessment="3 dairy SKUs (RD003, RD004, RD005) affected. Buffer covers RD005 but RD003/RD004 at risk.",
            estimated_impact_cost=18000.0, confidence=0.88,
            created_at=MON + timedelta(hours=10),
        ),
        # Story 1: QUICKSERV SO at risk
        PowellOrderException(
            config_id=config_id, order_id="SO-QUICKSERV-2026-0301",
            order_type="sales_order", order_status="confirmed",
            exception_type="AT_RISK", severity="medium",
            recommended_action="partial_ship",
            description="QUICKSERV March opening stocking order may be short if buffer not increased in time",
            impact_assessment="450 cases Chicken Breast requested. Current available 380 cases without buffer increase.",
            estimated_impact_cost=2450.0, confidence=0.76,
            action_taken="expedite", resolution_time_hours=24.0,
            resolved_at=TUE + timedelta(hours=10),
            created_at=MON + timedelta(hours=15),
        ),
        # Story 6: Dairy PO price variance
        PowellOrderException(
            config_id=config_id, order_id="PO-CONAGRA-2026-0226",
            order_type="purchase_order", order_status="confirmed",
            exception_type="PRICE_VARIANCE", severity="low",
            recommended_action="approve_variance",
            description="Conagra Cheddar Block invoice 12% above contract price due to commodity price increase",
            impact_assessment="$744 variance on 400-case order. Market price supports increase.",
            estimated_impact_cost=744.0, confidence=0.92,
            created_at=WED + timedelta(hours=12),
        ),
        # Story 1: Wings early arrival
        PowellOrderException(
            config_id=config_id, order_id="PO-TYSON-2026-0224",
            order_type="purchase_order", order_status="in_transit",
            exception_type="EARLY_ARRIVAL", severity="info",
            recommended_action="accept",
            description="Tyson Chicken Breast IQF shipment arriving 2 days early (Feb 26 instead of Feb 28)",
            impact_assessment="Positive: Supports March Madness buffer build. Ensure receiving dock availability.",
            estimated_impact_cost=0.0, confidence=0.95,
            action_taken="accept", resolution_time_hours=1.0,
            resolved_at=WED + timedelta(hours=7),
            created_at=WED + timedelta(hours=6),
        ),
        # Story 3: Yogurt quality hold
        PowellOrderException(
            config_id=config_id, order_id="QA-RD004-LOT20260224",
            order_type="quality_order", order_status="on_hold",
            exception_type="QUALITY_HOLD", severity="high",
            recommended_action="rework",
            description="2,400 cases Greek Yogurt Plain failed texture consistency test. Lot on quality hold.",
            impact_assessment="$36K inventory value at risk. Rework feasible with 92% expected yield within 48 hours.",
            estimated_impact_cost=36000.0, confidence=0.75,
            created_at=MON + timedelta(hours=11),
        ),
    ]
    db.add_all(exceptions)
    db.flush()
    print(f"  Created {len(exceptions)} Powell order exceptions")


# =============================================================================
# Section 11: Powell Forecast Adjustment Decisions
# =============================================================================

def seed_powell_forecast_adj_decisions(db: Session, config_id: int):
    """Seed 4 forecast adjustment decisions."""
    print("\n11. Seeding Powell forecast adjustment decisions...")

    decisions = [
        # Story 1: March Madness wings uplift
        PowellForecastAdjustmentDecision(
            config_id=config_id,
            product_id=FP001, site_id=DC_SITE,
            signal_source="customer_feedback", signal_type="demand_increase",
            signal_text="QUICKSERV procurement manager confirmed 35-40% increase in frozen protein orders for March Madness tournament period (March 15 - April 7).",
            signal_confidence=0.90,
            current_forecast_value=280.0,
            adjustment_direction="up", adjustment_magnitude=98.0,
            adjustment_pct=35.0, adjusted_forecast_value=378.0,
            time_horizon_periods=4,
            reason="March Madness demand signal from QUICKSERV and restaurant segment",
            confidence=0.88,
            was_applied=True,
            created_at=MON + timedelta(hours=9),
        ),
        # Story 5: QUICKSERV Arizona tenders
        PowellForecastAdjustmentDecision(
            config_id=config_id,
            product_id=FP001, site_id=DC_SITE,
            signal_source="sales_input", signal_type="demand_increase",
            signal_text="Sales team reports 3 new QUICKSERV Phoenix locations opening March 1. Initial stocking 25% above average per-store volume.",
            signal_confidence=0.85,
            current_forecast_value=180.0,
            adjustment_direction="up", adjustment_magnitude=45.0,
            adjustment_pct=25.0, adjusted_forecast_value=225.0,
            time_horizon_periods=12,
            reason="QUICKSERV Arizona new store openings — sustained demand increase",
            confidence=0.82,
            was_applied=True,
            created_at=TUE + timedelta(hours=10),
        ),
        # Story 6: Dairy demand softening
        PowellForecastAdjustmentDecision(
            config_id=config_id,
            product_id=RD005, site_id=DC_SITE,
            signal_source="market_intelligence", signal_type="demand_decrease",
            signal_text="Dairy commodity prices up 12%. Restaurant customers likely to adjust menus, reducing butter/cheese usage by estimated 8%.",
            signal_confidence=0.68,
            current_forecast_value=450.0,
            adjustment_direction="down", adjustment_magnitude=36.0,
            adjustment_pct=8.0, adjusted_forecast_value=414.0,
            time_horizon_periods=4,
            reason="Commodity price increase expected to reduce restaurant demand for dairy",
            confidence=0.71,
            was_applied=False,
            created_at=WED + timedelta(hours=11),
        ),
        # Story 4: Ice cream seasonal ramp
        PowellForecastAdjustmentDecision(
            config_id=config_id,
            product_id=FD001, site_id=DC_SITE,
            signal_source="seasonal", signal_type="seasonal",
            signal_text="Seasonal demand model indicates spring transition starting 1 week early based on 3-week temperature forecast and historical pattern matching.",
            signal_confidence=0.92,
            current_forecast_value=200.0,
            adjustment_direction="up", adjustment_magnitude=40.0,
            adjustment_pct=20.0, adjusted_forecast_value=240.0,
            time_horizon_periods=8,
            reason="Early spring onset detected — ice cream demand ramp starting ahead of schedule",
            confidence=0.93,
            was_applied=True,
            created_at=TUE + timedelta(hours=12),
        ),
    ]
    db.add_all(decisions)
    db.flush()
    print(f"  Created {len(decisions)} Powell forecast adjustment decisions")


# =============================================================================
# Section 12: Powell Buffer Decisions
# =============================================================================

def seed_powell_buffer_decisions(db: Session, config_id: int):
    """Seed 3 inventory buffer adjustment decisions."""
    print("\n12. Seeding Powell buffer decisions...")

    decisions = [
        # Story 1: Wings buffer for March Madness
        PowellBufferDecision(
            config_id=config_id,
            product_id=FP001, location_id=DC_SITE,
            baseline_ss=200.0, multiplier=1.35, adjusted_ss=270.0,
            reason="demand_surge",
            confidence=0.87, demand_cv=0.32, current_dos=5.3,
            seasonal_index=1.15, recent_stockout_count=0,
            was_applied=True,
            created_at=MON + timedelta(hours=13),
        ),
        # Story 4: Ice cream buffer for spring
        PowellBufferDecision(
            config_id=config_id,
            product_id=FD001, location_id=DC_SITE,
            baseline_ss=150.0, multiplier=1.25, adjusted_ss=188.0,
            reason="seasonal_transition",
            confidence=0.90, demand_cv=0.28, current_dos=6.2,
            seasonal_index=1.35, recent_stockout_count=0,
            was_applied=True,
            created_at=TUE + timedelta(hours=16),
        ),
        # Story 5: Tenders buffer for new stores
        PowellBufferDecision(
            config_id=config_id,
            product_id=FP001, location_id=DC_SITE,
            baseline_ss=200.0, multiplier=1.15, adjusted_ss=230.0,
            reason="new_demand_source",
            confidence=0.82, demand_cv=0.28, current_dos=4.8,
            seasonal_index=1.0, recent_stockout_count=0,
            was_applied=True,
            created_at=WED + timedelta(hours=8),
        ),
    ]
    db.add_all(decisions)
    db.flush()
    print(f"  Created {len(decisions)} Powell buffer decisions")


# =============================================================================
# Section 13: Performance Metrics
# =============================================================================

def seed_performance_metrics(db: Session, tenant_id: int):
    """Seed 5 weekly performance metric records."""
    print("\n13. Seeding performance metrics...")

    period_start = MON
    period_end = FRI + timedelta(hours=18)

    metrics = [
        # Overall
        PerformanceMetric(
            tenant_id=tenant_id,
            period_start=period_start, period_end=period_end,
            period_type="weekly", category=None, decision_type=None,
            total_decisions=47, agent_decisions=39, planner_decisions=8,
            agent_score=72.0, planner_score=68.0,
            override_rate=18.0, override_count=8,
            automation_percentage=82.0,
            override_effectiveness_rate=62.5, override_net_delta=4.2,
            active_agents=11, active_planners=4,
            total_skus=25, skus_per_planner=6.25,
            created_at=FRI + timedelta(hours=18),
        ),
        # Demand Forecast
        PerformanceMetric(
            tenant_id=tenant_id,
            period_start=period_start, period_end=period_end,
            period_type="weekly", category="Demand Forecast",
            decision_type="demand_forecast",
            total_decisions=12, agent_decisions=11, planner_decisions=1,
            agent_score=78.0, planner_score=72.0,
            override_rate=12.0, override_count=1,
            automation_percentage=91.7,
            active_agents=1, active_planners=1,
            total_skus=25, skus_per_planner=25.0,
            created_at=FRI + timedelta(hours=18),
        ),
        # Supply Plan
        PerformanceMetric(
            tenant_id=tenant_id,
            period_start=period_start, period_end=period_end,
            period_type="weekly", category="Supply Plan",
            decision_type="supply_plan",
            total_decisions=13, agent_decisions=10, planner_decisions=3,
            agent_score=65.0, planner_score=71.0,
            override_rate=24.0, override_count=3,
            automation_percentage=76.9,
            active_agents=3, active_planners=2,
            total_skus=18, skus_per_planner=9.0,
            created_at=FRI + timedelta(hours=18),
        ),
        # ATP Allocation
        PerformanceMetric(
            tenant_id=tenant_id,
            period_start=period_start, period_end=period_end,
            period_type="weekly", category="ATP Allocation",
            decision_type="atp_allocation",
            total_decisions=12, agent_decisions=11, planner_decisions=1,
            agent_score=81.0, planner_score=85.0,
            override_rate=8.0, override_count=1,
            automation_percentage=91.7,
            active_agents=1, active_planners=1,
            total_skus=25, skus_per_planner=25.0,
            created_at=FRI + timedelta(hours=18),
        ),
        # Inventory
        PerformanceMetric(
            tenant_id=tenant_id,
            period_start=period_start, period_end=period_end,
            period_type="weekly", category="Inventory",
            decision_type="safety_stock",
            total_decisions=10, agent_decisions=8, planner_decisions=2,
            agent_score=68.0, planner_score=74.0,
            override_rate=22.0, override_count=2,
            automation_percentage=80.0,
            active_agents=2, active_planners=1,
            total_skus=25, skus_per_planner=25.0,
            created_at=FRI + timedelta(hours=18),
        ),
    ]
    db.add_all(metrics)
    db.flush()
    print(f"  Created {len(metrics)} performance metrics")


# =============================================================================
# Section 14: Override Effectiveness Posteriors
# =============================================================================

def seed_override_posteriors(db: Session, users: dict):
    """Seed 3 Bayesian override effectiveness posteriors."""
    print("\n14. Seeding override effectiveness posteriors...")

    posteriors = [
        # S&OP Director overrides on supply plans
        OverrideEffectivenessPosterior(
            user_id=users["sop"],
            trm_type="supply_plan",
            site_key=DC_SITE,
            alpha=8.0, beta_param=3.0,
            expected_effectiveness=0.73,
            observation_count=11,
            training_weight=1.54,  # 0.3 + 1.7 * 0.73
        ),
        # MPS Manager overrides on demand forecasts
        OverrideEffectivenessPosterior(
            user_id=users["mps"],
            trm_type="demand_forecast",
            site_key=DC_SITE,
            alpha=5.0, beta_param=4.0,
            expected_effectiveness=0.56,
            observation_count=9,
            training_weight=1.25,  # 0.3 + 1.7 * 0.56
        ),
        # ATP Analyst overrides on ATP allocation
        OverrideEffectivenessPosterior(
            user_id=users["atp"],
            trm_type="atp_allocation",
            site_key=DC_SITE,
            alpha=12.0, beta_param=2.0,
            expected_effectiveness=0.86,
            observation_count=14,
            training_weight=1.76,  # 0.3 + 1.7 * 0.86
        ),
    ]
    db.add_all(posteriors)
    db.flush()
    print(f"  Created {len(posteriors)} override effectiveness posteriors")


# =============================================================================
# Main
# =============================================================================

def main():
    print("=" * 70)
    print("Seeding Food Dist Deep Demo — Action Layer Data")
    print("Narrative: Late February 2026 — A Week in the Life of CDC_WEST")
    print("=" * 70)

    SyncSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=sync_engine
    )
    db: Session = SyncSessionLocal()

    try:
        # Lookups
        tenant_id = lookup_tenant(db)
        config_id = lookup_config(db, tenant_id)
        users = lookup_users(db, tenant_id)
        print(f"\nTenant: {FOOD_DIST_TENANT_NAME} (id={tenant_id})")
        print(f"Config: {FOOD_DIST_CONFIG_NAME} (id={config_id})")
        print(f"Users: {users}")

        # Cleanup
        cleanup(db, tenant_id, config_id)
        db.commit()

        # Seed all 14 sections
        briefing_id = seed_executive_briefing(db, tenant_id, users)
        seed_briefing_followups(db, briefing_id, users)
        seed_sop_worklist(db, tenant_id, users)
        seed_agent_decisions(db, tenant_id, users)
        alert_ids = seed_condition_alerts(db, tenant_id)
        seed_scenario_evaluations(db, tenant_id, alert_ids)
        seed_powell_atp_decisions(db, config_id)
        seed_powell_po_decisions(db, config_id)
        seed_powell_rebalance_decisions(db, config_id)
        seed_powell_order_exceptions(db, config_id)
        seed_powell_forecast_adj_decisions(db, config_id)
        seed_powell_buffer_decisions(db, config_id)
        seed_performance_metrics(db, tenant_id)
        seed_override_posteriors(db, users)

        db.commit()

        # Summary
        print("\n" + "=" * 70)
        print("Deep Demo Seed Complete!")
        print("=" * 70)
        print(f"""
Records created:
  Executive Briefings:    1
  Briefing Follow-ups:    3
  S&OP Worklist Items:    6
  Agent Decisions:        15
  Condition Alerts:       8
  Scenario Evaluations:   3
  Powell ATP Decisions:   12
  Powell PO Decisions:    6
  Powell Rebalance:       4
  Powell Order Exceptions: 5
  Forecast Adjustments:   4
  Buffer Decisions:       3
  Performance Metrics:    5
  Override Posteriors:     3
  ─────────────────────────
  Total:                  78

Dashboard pages now populated:
  - Executive Dashboard → Weekly briefing with narrative + recommendations
  - Strategy Briefing → Follow-up Q&A (3 exchanges)
  - S&OP Worklist → 6 items (2 urgent, 3 standard, 1 low)
  - Agent Decisions → 15 copilot recommendations (mixed statuses)
  - Condition Alerts → 8 alerts (6 active, 2 resolved)
  - Scenario Evaluations → 3 what-if analyses
  - Powell ATP Worklist → 12 fulfillment decisions
  - Powell PO Worklist → 6 purchase order decisions
  - Rebalancing Worklist → 4 transfer recommendations
  - Order Exceptions → 5 tracked exceptions
  - Forecast Adjustments → 4 signal-driven adjustments
  - Buffer Decisions → 3 inventory buffer changes
  - Decision Performance → Weekly metrics (agent score 72, override rate 18%)
  - Override Effectiveness → 3 Bayesian posteriors
""")

    except Exception as e:
        print(f"\nERROR: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
