"""
Agent Performance Metrics Service

Calculates and provides Agent Performance and Human Override metrics
for the Powell Framework demonstration.

Metrics Definition:
- Agent Performance Score: -100 to +100 scale measuring quality of decisions
  - Positive = decisions led to good outcomes (cost savings, service level met)
  - Negative = decisions led to poor outcomes (stockouts, excess inventory)

- Human Override Rate: 0-100% scale measuring human intervention rate
  - Lower = more decisions being made by agents without override
  - Declining over time = planners trusting AI more

This service provides both real calculations (from AgentDecision table)
and demo data generation for demonstration purposes.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
import random
import math

from app.models.decision_tracking import (
    AgentDecision, PerformanceMetric, SOPWorklistItem,
    DecisionType, DecisionStatus, DecisionUrgency
)


class AgentPerformanceService:
    """Service for Agent Performance metrics calculation and retrieval."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # DEMO DATA GENERATION
    # =========================================================================

    def generate_demo_performance_metrics(
        self,
        tenant_id: int,
        months: int = 12,
        start_date: Optional[datetime] = None
    ) -> List[PerformanceMetric]:
        """
        Generate demo performance metrics that show improving automation.

        Pattern (matching screenshots):
        - Agent Score: Starts around +10, improves to +75 over time
        - Planner Score: Starts around +6, improves to +45 (agents help planners too)
        - Override Rate: Starts around 100% (all manual), declines to ~25% (automation taking over)
        - Automation: Starts at ~30%, grows to ~80%
        """
        if start_date is None:
            start_date = datetime.utcnow() - timedelta(days=months * 30)

        metrics = []
        categories = ["Sports Drinks", "Enhanced Water", "Bottled Water", "Energy Drinks"]

        for month_offset in range(months):
            period_start = start_date + timedelta(days=month_offset * 30)
            period_end = period_start + timedelta(days=30)

            # Progress factor (0 to 1 over the time period)
            progress = month_offset / max(months - 1, 1)

            # Agent Score: +10 → +75 (with some noise)
            base_agent_score = 10 + (65 * progress)
            agent_score = base_agent_score + random.uniform(-5, 5)

            # Planner Score: +6 → +45 (improves as they learn from agents)
            base_planner_score = 6 + (39 * progress)
            planner_score = base_planner_score + random.uniform(-3, 3)

            # Override Rate: 100% → 25% (overrides decrease as automation increases)
            base_override = 100 - (75 * progress)
            override_rate = max(15, base_override + random.uniform(-5, 5))

            # Automation: 30% → 80%
            base_automation = 30 + (50 * progress)
            automation = min(90, base_automation + random.uniform(-3, 3))

            # Decision counts (increasing total as system scales)
            base_decisions = 150 + (month_offset * 10)
            total_decisions = int(base_decisions + random.uniform(-20, 20))
            agent_decisions = int(total_decisions * (automation / 100))
            planner_decisions = total_decisions - agent_decisions

            # Active resources
            # Planners decrease as automation increases (RIF events in screenshot)
            base_planners = 25 - int(progress * 7)  # 25 → 18
            active_planners = max(15, base_planners + random.randint(-1, 1))

            # Agents increase
            base_agents = 12 + int(progress * 6)  # 12 → 18
            active_agents = min(20, base_agents + random.randint(-1, 1))

            # SKUs managed
            total_skus = 15000 + int(progress * 3000)  # Growing SKU base
            skus_per_planner = total_skus / active_planners if active_planners > 0 else 0

            # Create overall metric
            metric = PerformanceMetric(
                tenant_id=tenant_id,
                period_start=period_start,
                period_end=period_end,
                period_type="monthly",
                category=None,  # Overall
                total_decisions=total_decisions,
                agent_decisions=agent_decisions,
                planner_decisions=planner_decisions,
                agent_score=round(agent_score, 1),
                planner_score=round(planner_score, 1),
                override_rate=round(override_rate, 1),
                override_count=int(total_decisions * (override_rate / 100) * 0.1),
                automation_percentage=round(automation, 1),
                active_agents=active_agents,
                active_planners=active_planners,
                total_skus=total_skus,
                skus_per_planner=round(skus_per_planner, 0),
            )
            metrics.append(metric)

            # Also create per-category metrics
            for cat in categories:
                # Each category has slightly different automation levels
                cat_multiplier = {
                    "Sports Drinks": 1.0,
                    "Enhanced Water": 1.08,
                    "Bottled Water": 1.12,
                    "Energy Drinks": 0.7,  # More volatile, lower automation
                }[cat]

                cat_automation = min(90, automation * cat_multiplier)
                cat_agent_score = agent_score * cat_multiplier
                cat_planner_score = planner_score * (1.1 if cat == "Energy Drinks" else 0.9)

                cat_decisions = int(total_decisions * 0.25)  # ~25% per category
                cat_agent_decisions = int(cat_decisions * (cat_automation / 100))

                cat_metric = PerformanceMetric(
                    tenant_id=tenant_id,
                    period_start=period_start,
                    period_end=period_end,
                    period_type="monthly",
                    category=cat,
                    total_decisions=cat_decisions,
                    agent_decisions=cat_agent_decisions,
                    planner_decisions=cat_decisions - cat_agent_decisions,
                    agent_score=round(cat_agent_score, 1),
                    planner_score=round(cat_planner_score, 1),
                    override_rate=round(override_rate * (1.1 if cat == "Energy Drinks" else 0.95), 1),
                    automation_percentage=round(cat_automation, 1),
                )
                metrics.append(metric)

        return metrics

    def generate_demo_sop_worklist(self, tenant_id: int) -> List[SOPWorklistItem]:
        """
        Generate demo S&OP worklist items matching the screenshot pattern.
        """
        worklist_items = [
            {
                "item_code": "PORTFOLIO",
                "item_name": "Q3 Margin Compression",
                "category": "Portfolio",
                "issue_type": "PORTFOLIO",
                "issue_summary": "Gross margin trending 180bps below plan",
                "impact_value": -2400000,
                "impact_description": "-$2.4M vs plan",
                "impact_type": "negative",
                "due_description": "EOD",
                "urgency": DecisionUrgency.URGENT,
                "agent_recommendation": "Implement dynamic pricing on high-velocity SKUs and negotiate supplier rebates for Q4",
                "agent_reasoning": "Analysis shows 65% of margin compression from input cost increases. Dynamic pricing on top 20% of SKUs could recover $1.8M. Supplier negotiations could address remaining gap.",
            },
            {
                "item_code": "CAPACITY",
                "item_name": "DC Capacity Crunch - Holiday Planning",
                "category": "Capacity",
                "issue_type": "CAPACITY",
                "issue_summary": "Peak season capacity at 94% projected",
                "impact_value": -890000,
                "impact_description": "-$890K penalty exposure",
                "impact_type": "negative",
                "due_description": "Friday",
                "urgency": DecisionUrgency.URGENT,
                "agent_recommendation": "Pre-position 15% of projected volume to secondary DC and activate overflow agreement",
                "agent_reasoning": "Historical peak utilization exceeded 96% in 3 of last 5 years. Pre-positioning reduces penalty risk by 78% with only 2.3% cost increase.",
            },
            {
                "item_code": "HL-NEW",
                "item_name": "HydraLite Energy Launch",
                "category": "New Product",
                "issue_type": "NPI",
                "issue_summary": "New product launch timing conflict with production line upgrade",
                "impact_value": 450000,
                "impact_description": "$450K",
                "impact_type": "trade-off",
                "due_description": "48 hours",
                "urgency": DecisionUrgency.URGENT,
                "agent_recommendation": "Delay launch by 2 weeks to complete line upgrade, avoiding quality risks",
                "agent_reasoning": "Launching during upgrade creates 23% higher defect probability. 2-week delay has minimal market impact but protects brand reputation.",
            },
            {
                "item_code": "HB-PROMO",
                "item_name": "Back-to-School Promo Pack",
                "category": "Promotion",
                "issue_type": "PROMO",
                "issue_summary": "Marketing budget increase requires production capacity reallocation",
                "impact_value": 780000,
                "impact_description": "$780K",
                "impact_type": "positive",
                "due_description": "3 days",
                "urgency": DecisionUrgency.STANDARD,
                "agent_recommendation": "Reallocate 12% of standard SKU capacity to promo packs for 6 weeks",
                "agent_reasoning": "ROI analysis shows promo generates 2.4x margin vs standard mix. Temporary standard SKU shortage can be managed via safety stock draw-down.",
            },
            {
                "item_code": "HB-2001",
                "item_name": "HydraBoost Classic",
                "category": "Inventory",
                "issue_type": "POLICY",
                "issue_summary": "Finance requesting 5% inventory reduction vs Operations safety stock policy",
                "impact_value": None,
                "impact_description": "Service level vs working capital trade-off",
                "impact_type": "trade-off",
                "due_description": "1 week",
                "urgency": DecisionUrgency.STANDARD,
                "agent_recommendation": "Implement tiered policy: reduce safety stock on A-items by 3%, maintain B/C items",
                "agent_reasoning": "A-items have more stable demand and faster replenishment. This achieves 3.8% working capital reduction with only 0.2% service level impact.",
            },
            {
                "item_code": "HL-4020",
                "item_name": "HydraLite Citrus Splash",
                "category": "Network",
                "issue_type": "NETWORK",
                "issue_summary": "Regional demand shift not reflected in supply network design",
                "impact_value": 95000,
                "impact_description": "$95K/month",
                "impact_type": "negative",
                "due_description": "2 weeks",
                "urgency": DecisionUrgency.STANDARD,
                "agent_recommendation": "Shift 8% of Southeast production to Midwest facility",
                "agent_reasoning": "Demand migration analysis shows 15% growth in Midwest vs 3% decline in Southeast. Network realignment reduces transport costs by $95K/month.",
            },
            {
                "item_code": "HB-PORT",
                "item_name": "Portfolio Mix",
                "category": "Portfolio",
                "issue_type": "PORTFOLIO",
                "issue_summary": "SKU rationalization proposal - discontinue 12 low-velocity items",
                "impact_value": None,
                "impact_description": "Simplification vs customer coverage",
                "impact_type": "trade-off",
                "due_description": "Q4 Planning",
                "urgency": DecisionUrgency.LOW,
                "agent_recommendation": "Discontinue 8 of 12 proposed SKUs, retain 4 with regional importance",
                "agent_reasoning": "8 SKUs have <$50K annual revenue with no regional concentration. 4 SKUs have low overall volume but 35%+ share in specific regions.",
            },
            {
                "item_code": "HB-CAP",
                "item_name": "Capacity Planning",
                "category": "Capacity",
                "issue_type": "CAPEX",
                "issue_summary": "Long-term capacity investment decision approved",
                "impact_value": None,
                "impact_description": "Line 4 expansion greenlit",
                "impact_type": "positive",
                "due_description": "Completed",
                "urgency": DecisionUrgency.LOW,
                "status": DecisionStatus.ACCEPTED,
            },
            {
                "item_code": "HL-DISC",
                "item_name": "HydraLite Grape",
                "category": "Portfolio",
                "issue_type": "DISCONTINUATION",
                "issue_summary": "Discontinuation request rejected - customer commitments through Q4",
                "impact_value": None,
                "impact_description": "Continue production through year-end",
                "impact_type": "trade-off",
                "due_description": "Closed",
                "urgency": DecisionUrgency.LOW,
                "status": DecisionStatus.REJECTED,
            },
        ]

        items = []
        for item_data in worklist_items:
            status = item_data.pop("status", DecisionStatus.PENDING)
            item = SOPWorklistItem(
                tenant_id=tenant_id,
                status=status,
                **item_data
            )
            items.append(item)

        return items

    # =========================================================================
    # METRIC CALCULATIONS
    # =========================================================================

    def get_executive_dashboard_data(
        self,
        tenant_id: int,
        planning_cycle: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get executive dashboard data for SC_VP.

        Returns summary metrics for the Executive Dashboard.
        """
        # For demo, generate if no data exists
        metrics = self.db.query(PerformanceMetric).filter(
            PerformanceMetric.tenant_id == tenant_id,
            PerformanceMetric.category.is_(None)
        ).order_by(PerformanceMetric.period_start.desc()).limit(12).all()

        if not metrics:
            # Return demo data structure
            return self._get_demo_executive_data()

        # Calculate from real data
        latest = metrics[0] if metrics else None
        previous = metrics[1] if len(metrics) > 1 else None

        # Get the demo data for fields not yet computed from real metrics
        # (business_outcomes, treemap, sop_worklist_preview)
        demo = self._get_demo_executive_data()

        return {
            "summary": {
                "autonomous_decisions_pct": round(latest.automation_percentage, 1) if latest else 78,
                "autonomous_decisions_change": round(
                    latest.automation_percentage - previous.automation_percentage, 1
                ) if latest and previous else 15.1,
                "active_agents": latest.active_agents if latest else 18,
                "active_agents_change": 6,
                "active_planners": latest.active_planners if latest else 18,
                "active_planners_change": 2,
                "planner_score": round(latest.planner_score, 1) if latest else 7,
                "planner_score_change": 3,
                "agent_score": round(latest.agent_score, 1) if latest else 12,
                "agent_score_change": 6,
            },
            "trends": [m.to_dict() for m in reversed(metrics)],
            "roi": {
                "inventory_reduction_pct": 47,
                "inventory_from": 72000,
                "inventory_to": 38000,
                "service_level": 105,
                "forecast_accuracy_from": 68,
                "forecast_accuracy_to": 86,
                "carrying_cost_reduction_pct": 7,
                "revenue_increase_pct": 20,
                "revenue_from": 125000000,
                "revenue_to": 150000000,
            },
            "key_insights": [
                "Agent score improved from +10 to +75 while handling 86% of all decisions",
                "Planner score rose from +6 to +45 as override rate declined from 90% to 20%",
                "Agent decisions increased from 30 to 180 per month, showing sustained automation growth",
                "Total decision capacity increased 40% while maintaining quality standards",
            ],
            # Include portfolio treemap, business KPIs, and S&OP preview
            "business_outcomes": demo.get("business_outcomes"),
            "treemap": demo.get("treemap"),
            "sop_worklist_preview": demo.get("sop_worklist_preview"),
            "historical_trends": demo.get("historical_trends"),
            "categories": demo.get("categories"),
        }

    def _get_demo_executive_data(self) -> Dict[str, Any]:
        """Return demo executive dashboard data matching screenshots."""
        return {
            "summary": {
                "autonomous_decisions_pct": 78,
                "autonomous_decisions_change": 15.1,
                "active_agents": 18,
                "active_agents_change": 6,
                "active_planners": 18,
                "active_planners_change": 2,
                "planner_score": 7,
                "planner_score_change": 3,
                "agent_score": 12,
                "agent_score_change": 6,
            },
            "trends": self._generate_demo_trends(),
            "roi": {
                "inventory_reduction_pct": 47,
                "inventory_from": 72000,
                "inventory_to": 38000,
                "service_level": 105,
                "forecast_accuracy_from": 68,
                "forecast_accuracy_to": 86,
                "carrying_cost_reduction_pct": 7,
                "revenue_increase_pct": 20,
                "revenue_from": 125000000,
                "revenue_to": 150000000,
            },
            "key_insights": [
                "Agent score improved from +10 to +75 while handling 86% of all decisions",
                "Planner score rose from +6 to +45 as override rate declined from 90% to 20%",
                "Agent decisions increased from 30 to 180 per month, showing sustained automation growth",
                "Total decision capacity increased 40% while maintaining quality standards",
            ],
            "categories": [
                {"name": "Sports Drinks", "revenue": 120000000, "units": 6000000, "manual_pct": 40, "auto_pct": 60, "planner_score": 6, "agent_score": 18, "decisions": 4000000},
                {"name": "Enhanced Water", "revenue": 75000000, "units": 3750000, "manual_pct": 35, "auto_pct": 65, "planner_score": 4, "agent_score": 16, "decisions": 2500000},
                {"name": "Bottled Water", "revenue": 75000000, "units": 3750000, "manual_pct": 28, "auto_pct": 72, "planner_score": 4, "agent_score": 12, "decisions": 2500000},
                {"name": "Energy Drinks", "revenue": 30000000, "units": 1500000, "manual_pct": 45, "auto_pct": 55, "planner_score": -5, "agent_score": 3, "decisions": 1000000},
            ],
            # Business outcome KPIs
            "business_outcomes": {
                "gross_margin": {"value": 32.5, "target": 30.0, "change": 2.1, "status": "success"},
                "capacity_utilization": {"value": 87, "target": 90, "change": -3, "status": "warning"},
                "revenue_at_risk": {"value": 2400000, "change": 5, "status": "danger"},
                "escalations": {"value": 12, "change": -3, "status": "info"},
            },
            # Treemap data: Geography x Product hierarchy with cost data
            "treemap": {
                "name": "Portfolio",
                "children": [
                    {
                        "name": "North America",
                        "revenue": 107000000,
                        "cost": 71250000,
                        "children": [
                            {"name": "Sports Drinks", "revenue": 45000000, "cost": 29610000, "margin": 34.2},
                            {"name": "Enhanced Water", "revenue": 28000000, "cost": 19180000, "margin": 31.5},
                            {"name": "Bottled Water", "revenue": 22000000, "cost": 15774000, "margin": 28.3},
                            {"name": "Energy Drinks", "revenue": 12000000, "cost": 7356000, "margin": 38.7},
                        ]
                    },
                    {
                        "name": "Europe",
                        "revenue": 101000000,
                        "cost": 70920000,
                        "children": [
                            {"name": "Sports Drinks", "revenue": 38000000, "cost": 25534000, "margin": 32.8},
                            {"name": "Enhanced Water", "revenue": 25000000, "cost": 17650000, "margin": 29.4},
                            {"name": "Bottled Water", "revenue": 30000000, "cost": 22170000, "margin": 26.1},
                            {"name": "Energy Drinks", "revenue": 8000000, "cost": 5184000, "margin": 35.2},
                        ]
                    },
                    {
                        "name": "Asia Pacific",
                        "revenue": 64000000,
                        "cost": 42680000,
                        "children": [
                            {"name": "Sports Drinks", "revenue": 25000000, "cost": 15875000, "margin": 36.5},
                            {"name": "Enhanced Water", "revenue": 15000000, "cost": 10020000, "margin": 33.2},
                            {"name": "Bottled Water", "revenue": 18000000, "cost": 12456000, "margin": 30.8},
                            {"name": "Energy Drinks", "revenue": 6000000, "cost": 3594000, "margin": 40.1},
                        ]
                    },
                    {
                        "name": "Latin America",
                        "revenue": 28000000,
                        "cost": 20700000,
                        "children": [
                            {"name": "Sports Drinks", "revenue": 12000000, "cost": 8592000, "margin": 28.4},
                            {"name": "Enhanced Water", "revenue": 7000000, "cost": 5208000, "margin": 25.6},
                            {"name": "Bottled Water", "revenue": 5000000, "cost": 3885000, "margin": 22.3},
                            {"name": "Energy Drinks", "revenue": 4000000, "cost": 2740000, "margin": 31.5},
                        ]
                    },
                ]
            },
            # Historical trends for the dashboard charts (12 months)
            "historical_trends": {
                "revenue": [
                    {"period": "Mar 2025", "value": 248000000},
                    {"period": "Apr 2025", "value": 255000000},
                    {"period": "May 2025", "value": 262000000},
                    {"period": "Jun 2025", "value": 271000000},
                    {"period": "Jul 2025", "value": 285000000},
                    {"period": "Aug 2025", "value": 300000000},
                ],
                "margin": [
                    {"period": "Mar 2025", "value": 28.5},
                    {"period": "Apr 2025", "value": 29.2},
                    {"period": "May 2025", "value": 30.1},
                    {"period": "Jun 2025", "value": 31.0},
                    {"period": "Jul 2025", "value": 31.8},
                    {"period": "Aug 2025", "value": 32.5},
                ],
                "capacity_utilization": [
                    {"period": "Mar 2025", "value": 78},
                    {"period": "Apr 2025", "value": 81},
                    {"period": "May 2025", "value": 83},
                    {"period": "Jun 2025", "value": 85},
                    {"period": "Jul 2025", "value": 86},
                    {"period": "Aug 2025", "value": 87},
                ],
                "service_level": [
                    {"period": "Mar 2025", "value": 92.1},
                    {"period": "Apr 2025", "value": 93.4},
                    {"period": "May 2025", "value": 94.2},
                    {"period": "Jun 2025", "value": 94.8},
                    {"period": "Jul 2025", "value": 95.1},
                    {"period": "Aug 2025", "value": 95.5},
                ],
            },
            # Top S&OP worklist items for preview
            "sop_worklist_preview": [
                {
                    "id": 1,
                    "title": "Q3 Margin Compression",
                    "category": "Portfolio",
                    "impact": "-$2.4M vs plan",
                    "urgency": "urgent",
                    "due": "EOD",
                },
                {
                    "id": 2,
                    "title": "DC Capacity Crunch - Holiday Planning",
                    "category": "Capacity",
                    "impact": "-$890K penalty exposure",
                    "urgency": "urgent",
                    "due": "Friday",
                },
                {
                    "id": 3,
                    "title": "HydraLite Energy Launch",
                    "category": "New Product",
                    "impact": "+$15M revenue opportunity",
                    "urgency": "high",
                    "due": "Next Week",
                },
            ],
        }

    def _generate_demo_trends(self) -> List[Dict]:
        """Generate demo trend data for 12 months."""
        trends = []
        months = ["Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"]

        for i, month in enumerate(months):
            progress = i / 11
            trends.append({
                "month": month,
                "period_start": (datetime(2024, 8, 1) + timedelta(days=i*30)).isoformat(),
                "planner_score": round(6 + (39 * progress) + random.uniform(-3, 3), 1),
                "agent_score": round(10 + (65 * progress) + random.uniform(-5, 5), 1),
                "override_rate": round(100 - (75 * progress) + random.uniform(-5, 5), 1),
                "total_decisions": 150 + (i * 10) + random.randint(-20, 20),
                "agent_decisions": int((150 + i * 10) * (0.3 + 0.5 * progress)),
                "planner_decisions": int((150 + i * 10) * (0.7 - 0.5 * progress)),
                "active_planners": 25 - int(progress * 7),
                "skus_per_planner": int(600 + (progress * 400)),
            })

        return trends

    def get_sop_worklist_summary(self, tenant_id: int) -> Dict[str, Any]:
        """Get S&OP worklist summary KPIs for the dashboard cards."""
        return {
            "gross_margin": {
                "value": 24.2,
                "target": 26.0,
                "variance_bps": -180,
                "status": "warning",
            },
            "capacity_utilization": {
                "value": 94,
                "target": 85,
                "status": "warning",
            },
            "revenue_at_risk": {
                "value": 2400000,
                "categories": ["Beverages", "Dairy", "HBC"],
                "status": "alert",
            },
            "escalations": {
                "count": 3,
                "urgent": 2,
                "standard": 2,
                "status": "alert",
            },
        }

    # Maps KPI button names to actual DB category values
    CATEGORY_GROUP_MAP = {
        'margin':     ['Portfolio', 'Inventory', 'Promotion'],
        'capacity':   ['Capacity', 'CapEx'],
        'risk':       ['Network', 'SKU Rationalization', 'CapEx'],
        'escalation': ['New Product', 'Network', 'SKU Rationalization'],
    }

    def get_sop_worklist_items(
        self,
        tenant_id: int,
        status: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get S&OP worklist items."""
        query = self.db.query(SOPWorklistItem).filter(
            SOPWorklistItem.tenant_id == tenant_id
        )

        if status:
            query = query.filter(SOPWorklistItem.status == status)

        if category:
            expanded = self.CATEGORY_GROUP_MAP.get(category.lower())
            if expanded:
                query = query.filter(SOPWorklistItem.category.in_(expanded))
            else:
                # Fall back to exact match (case-insensitive) for direct category names
                query = query.filter(SOPWorklistItem.category.ilike(category))

        items = query.order_by(
            SOPWorklistItem.urgency.asc(),  # enum order: urgent(0) > standard(1) > low(2)
            SOPWorklistItem.impact_value.desc(),
            SOPWorklistItem.created_at.desc()
        ).all()

        if not items:
            # Return demo data
            demo_items = self.generate_demo_sop_worklist(tenant_id)
            return [item.to_dict() for item in demo_items]

        return [item.to_dict() for item in items]

    def resolve_worklist_item(
        self,
        item_id: int,
        user_id: int,
        action: str,  # "accept" or "reject"
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resolve a worklist item (accept or reject)."""
        item = self.db.query(SOPWorklistItem).filter(
            SOPWorklistItem.id == item_id
        ).first()

        if not item:
            raise ValueError(f"Worklist item {item_id} not found")

        item.status = DecisionStatus.ACCEPTED if action == "accept" else DecisionStatus.REJECTED
        item.resolved_by = user_id
        item.resolution_action = action
        item.resolution_notes = notes
        item.resolved_at = datetime.utcnow()

        self.db.commit()

        return item.to_dict()

    def get_agent_reasoning(self, item_id: int) -> Dict[str, Any]:
        """Get detailed agent reasoning for 'Ask Why' functionality."""
        item = self.db.query(SOPWorklistItem).filter(
            SOPWorklistItem.id == item_id
        ).first()

        if not item:
            raise ValueError(f"Item {item_id} not found")

        # For demo, return enhanced reasoning
        return {
            "recommendation": item.agent_recommendation,
            "reasoning": item.agent_reasoning,
            "confidence": 0.87,
            "supporting_data": {
                "historical_patterns": "Based on 24 months of historical data",
                "similar_decisions": "Similar decisions in past had 78% success rate",
                "risk_factors": ["Supply variability", "Demand seasonality"],
                "alternatives_considered": [
                    {"option": "Do nothing", "risk": "High", "impact": "Negative"},
                    {"option": "Partial implementation", "risk": "Medium", "impact": "Neutral"},
                ],
            },
            "impact_analysis": {
                "financial": item.impact_description,
                "operational": "Moderate complexity",
                "timeline": item.due_description,
            },
        }
