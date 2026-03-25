"""
Decision Stream API Endpoints

LLM-First UI endpoints for the Decision Stream "inbox":
  - GET  /digest  — Digest of pending decisions + alerts
  - POST /action  — Accept/override/reject a decision
  - POST /chat    — Conversational interaction with decision context
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.deps import get_current_user
from app.schemas.decision_stream import (
    DecisionDigestResponse,
    DecisionActionRequest,
    DecisionActionResponse,
    DecisionStreamChatRequest,
    DecisionStreamChatResponse,
)
from app.services.decision_stream_service import DecisionStreamService, invalidate_digest_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/decision-stream", tags=["Decision Stream"])


def _require_tenant_user(user):
    """Raise 403 if the user has no tenant (e.g. SYSTEM_ADMIN).

    The Decision Stream is a tenant-scoped feature. SYSTEM_ADMIN's scope is
    restricted to tenant and tenant admin management — it has no access to
    agent decisions, provisioning, or any other tenant-scoped feature.
    """
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Decision Stream requires a tenant-scoped user. "
                   "System administrators manage tenants and tenant admins only.",
        )
    return tenant_id


async def _get_service(db: AsyncSession, user) -> DecisionStreamService:
    """Create a tenant-scoped, user-scoped DecisionStreamService."""
    tenant_id = _require_tenant_user(user)
    tenant_name = ""
    if hasattr(user, "tenant") and user.tenant:
        tenant_name = getattr(user.tenant, "name", "")

    return DecisionStreamService(db=db, tenant_id=tenant_id, tenant_name=tenant_name, user=user)


@router.get("/digest", response_model=DecisionDigestResponse)
async def get_decision_digest(
    config_id: Optional[int] = Query(None, description="Supply chain config ID to scope"),
    level: Optional[str] = Query(None, description="Filter by decision level: governance, strategic, tactical, execution"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get the decision digest: pending decisions, alerts, and LLM synthesis.

    Level filtering:
    - Each role has a default level view (e.g., S&OP Director → strategic)
    - Pass ?level=execution to drill down to a specific level
    - Escalated decisions from the level below always pass through
    """
    service = await _get_service(db, current_user)
    decision_level = getattr(current_user, "decision_level", None)

    result = await service.get_decision_digest(
        decision_level=decision_level,
        config_id=config_id,
        level_override=level,
    )
    return result


@router.post("/refresh")
async def refresh_digest(
    config_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Invalidate the digest cache and return a fresh digest.

    Use the refresh button in the UI to force a fresh LLM synthesis.
    """
    service = await _get_service(db, current_user)
    invalidate_digest_cache(tenant_id=service.tenant_id, config_id=config_id)
    decision_level = getattr(current_user, "decision_level", None)
    result = await service.get_decision_digest(
        decision_level=decision_level,
        config_id=config_id,
        force_refresh=True,
    )
    return result


@router.post("/analyze-override-reason")
async def analyze_override_reason(
    request: dict,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Generate context-specific follow-up questions for override reasoning.

    Given a reason_code and decision context, returns follow-up questions
    that capture the structured experiential knowledge needed for RL training.
    The questions reference the decision's scope (product, site, time frame).
    """
    reason_code = request.get("reason_code", "")
    decision_type = request.get("decision_type", "")
    product_name = request.get("product_name", "")
    site_name = request.get("site_name", "")
    override_mode = request.get("override_mode", "modify")  # modify or cancel

    # Context string for question framing
    scope = []
    if product_name:
        scope.append(product_name)
    if site_name:
        scope.append(f"@ {site_name}")
    scope_str = " ".join(scope) if scope else "this decision"

    # Generate follow-up questions based on reason code + decision type
    # Each question captures a dimension of experiential knowledge
    followups = []

    # Always ask about temporal scope — is this a one-time or recurring pattern?
    followups.append({
        "field": "temporal_scope",
        "question": f"Is this override for {scope_str} a one-time adjustment or a recurring pattern?",
        "type": "select",
        "options": [
            "One-time (this period only)",
            "Short-term (next 2-4 weeks)",
            "Seasonal (recurring each year)",
            "Permanent (until further notice)",
        ],
        "required": True,
    })

    # Reason-specific questions
    REASON_FOLLOWUPS = {
        "MARKET_INTELLIGENCE": [
            {
                "field": "market_signal",
                "question": f"What market signal is driving this change for {scope_str}?",
                "type": "select",
                "options": [
                    "New competitor entry",
                    "Competitor exit / supply gap",
                    "Price change (commodity/input)",
                    "Customer behavior shift",
                    "Regulatory change",
                    "Promotional activity",
                    "Macroeconomic indicator",
                    "Other external signal",
                ],
                "required": True,
            },
            {
                "field": "signal_source",
                "question": "Where did you learn this? (e.g., customer call, trade publication, field report)",
                "type": "text",
                "required": True,
            },
        ],
        "CUSTOMER_COMMITMENT": [
            {
                "field": "customer_identity",
                "question": f"Which customer or customer segment does this affect for {scope_str}?",
                "type": "text",
                "required": True,
            },
            {
                "field": "commitment_type",
                "question": "What type of commitment?",
                "type": "select",
                "options": [
                    "Contractual SLA",
                    "Verbal agreement",
                    "Strategic account priority",
                    "Emergency request",
                    "New business opportunity",
                ],
                "required": True,
            },
        ],
        "CAPACITY_CONSTRAINT": [
            {
                "field": "constraint_resource",
                "question": f"What resource is constrained at {site_name or 'this site'}?",
                "type": "select",
                "options": [
                    "Production line / work center",
                    "Raw material availability",
                    "Labor / shifts",
                    "Storage / warehouse space",
                    "Transportation / logistics",
                    "Quality / testing capacity",
                    "Supplier capacity",
                ],
                "required": True,
            },
            {
                "field": "constraint_resolution",
                "question": "When do you expect this constraint to be resolved?",
                "type": "select",
                "options": [
                    "Within 1 week",
                    "2-4 weeks",
                    "1-3 months",
                    "Unknown / indefinite",
                ],
                "required": True,
            },
        ],
        "SUPPLIER_ISSUE": [
            {
                "field": "supplier_problem",
                "question": "What is the supplier issue?",
                "type": "select",
                "options": [
                    "Late delivery (current order)",
                    "Quality problem",
                    "Capacity reduction",
                    "Price increase",
                    "Financial distress / risk",
                    "Force majeure / disruption",
                    "Communication breakdown",
                ],
                "required": True,
            },
            {
                "field": "alternate_source",
                "question": "Is an alternate source available?",
                "type": "select",
                "options": [
                    "Yes — already qualified",
                    "Yes — needs qualification",
                    "Partially — can cover some volume",
                    "No — sole source",
                ],
                "required": True,
            },
        ],
        "QUALITY_CONCERN": [
            {
                "field": "quality_type",
                "question": f"What quality concern for {scope_str}?",
                "type": "select",
                "options": [
                    "Incoming material quality",
                    "In-process defect rate",
                    "Customer complaint / return",
                    "Regulatory / compliance risk",
                    "Shelf life / expiration",
                    "Specification change",
                ],
                "required": True,
            },
        ],
        "COST_OPTIMIZATION": [
            {
                "field": "cost_driver",
                "question": f"What cost factor is driving this override for {scope_str}?",
                "type": "select",
                "options": [
                    "Holding cost reduction",
                    "Transportation cost saving",
                    "Volume discount opportunity",
                    "Expedite cost avoidance",
                    "Obsolescence risk reduction",
                    "Budget constraint",
                ],
                "required": True,
            },
            {
                "field": "estimated_impact",
                "question": "Estimated dollar impact of this override?",
                "type": "select",
                "options": [
                    "< $1,000",
                    "$1,000 - $10,000",
                    "$10,000 - $50,000",
                    "$50,000 - $100,000",
                    "> $100,000",
                    "Don't know",
                ],
                "required": False,
            },
        ],
        "DEMAND_CHANGE": [
            {
                "field": "demand_direction",
                "question": f"How is demand changing for {scope_str}?",
                "type": "select",
                "options": [
                    "Increase — confirmed orders",
                    "Increase — expected (leading indicators)",
                    "Decrease — cancellations",
                    "Decrease — expected slowdown",
                    "Shift — timing change (earlier/later)",
                    "Mix change — different products",
                ],
                "required": True,
            },
            {
                "field": "demand_magnitude",
                "question": "Approximate magnitude of the change?",
                "type": "select",
                "options": [
                    "< 10%",
                    "10-25%",
                    "25-50%",
                    "> 50%",
                ],
                "required": True,
            },
        ],
        "SERVICE_LEVEL": [
            {
                "field": "service_priority",
                "question": f"Why does {scope_str} need a service level exception?",
                "type": "select",
                "options": [
                    "Strategic account at risk",
                    "Contractual SLA breach imminent",
                    "New product launch commitment",
                    "Competitive win/loss situation",
                    "Seasonal peak — temporary",
                ],
                "required": True,
            },
        ],
        "EXPEDITE_REQUIRED": [
            {
                "field": "expedite_reason",
                "question": f"What triggered the expedite need for {scope_str}?",
                "type": "select",
                "options": [
                    "Stockout imminent",
                    "Customer escalation",
                    "Supply disruption recovery",
                    "Demand spike (unexpected)",
                    "Quality reject — need replacement",
                    "Planning error correction",
                ],
                "required": True,
            },
        ],
        "RISK_MITIGATION": [
            {
                "field": "risk_type",
                "question": f"What risk are you mitigating for {scope_str}?",
                "type": "select",
                "options": [
                    "Supply continuity",
                    "Demand uncertainty",
                    "Price volatility",
                    "Quality / compliance",
                    "Geopolitical / trade",
                    "Weather / natural disaster",
                    "Currency / financial",
                ],
                "required": True,
            },
        ],
        "INVENTORY_BUFFER": [
            {
                "field": "buffer_reason",
                "question": f"Why adjust the inventory buffer for {scope_str}?",
                "type": "select",
                "options": [
                    "Lead time variability increased",
                    "Demand variability increased",
                    "Supplier reliability degraded",
                    "Seasonal build required",
                    "Excess inventory — reduce buffer",
                    "Service level target changed",
                ],
                "required": True,
            },
        ],
    }

    # Add reason-specific questions
    reason_specific = REASON_FOLLOWUPS.get(reason_code, [])
    followups.extend(reason_specific)

    # Always ask about confidence — how sure is the planner?
    followups.append({
        "field": "override_confidence",
        "question": "How confident are you that this override will improve the outcome?",
        "type": "select",
        "options": [
            "Very confident — I've seen this pattern before",
            "Fairly confident — strong signals",
            "Moderate — judgment call",
            "Low — but agent recommendation seems wrong",
        ],
        "required": True,
    })

    # For cancel mode, ask what should happen instead
    if override_mode == "cancel":
        followups.append({
            "field": "alternative_action",
            "question": f"What should happen instead for {scope_str}?",
            "type": "text",
            "required": True,
        })

    return {
        "reason_code": reason_code,
        "decision_type": decision_type,
        "scope": scope_str,
        "followup_questions": followups,
    }


@router.post("/action", response_model=DecisionActionResponse)
async def act_on_decision(
    request: DecisionActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Accept, override, or reject a pending decision."""
    service = await _get_service(db, current_user)

    result = await service.act_on_decision(
        decision_id=request.decision_id,
        decision_type=request.decision_type,
        action=request.action.value,
        override_reason_code=request.override_reason_code,
        override_reason_text=request.override_reason_text,
        override_values=request.override_values,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Action failed"))

    return result


@router.get("/ask-why")
async def ask_why(
    decision_id: int = Query(..., description="Decision ID"),
    decision_type: str = Query(..., description="Decision type (atp, po_creation, etc.)"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return pre-computed reasoning for a decision. No LLM call — instant response."""
    from app.services.decision_stream_service import DECISION_TYPE_TABLE_MAP
    from sqlalchemy import text

    table = DECISION_TYPE_TABLE_MAP.get(decision_type)
    if not table:
        raise HTTPException(status_code=400, detail=f"Unknown decision type: {decision_type}")

    # Direct DB lookup for the pre-computed reasoning
    result = await db.execute(
        text(f"SELECT decision_reasoning FROM {table} WHERE id = :id"),
        {"id": decision_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found")

    reasoning = row[0] if row[0] else "No reasoning was captured for this decision."
    return {"decision_id": decision_id, "decision_type": decision_type, "reasoning": reasoning}


@router.get("/time-series")
async def get_decision_time_series(
    decision_type: str = Query(..., description="Decision type"),
    product_id: Optional[str] = Query(None, description="Product ID"),
    site_id: Optional[str] = Query(None, description="Site ID"),
    config_id: Optional[int] = Query(None, description="Config ID"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return time series data for a decision's product/site context.

    Returns forecast, inventory, or lead time data depending on decision type,
    formatted for Recharts rendering.
    """
    from sqlalchemy import text
    from datetime import datetime, timedelta

    # Resolve config
    cfg_id = config_id or getattr(current_user, 'default_config_id', None)
    if not cfg_id:
        return {"series": [], "lines": [], "error": True}

    # Determine which data to fetch based on decision type
    DEMAND_TYPES = {"forecast_adjustment", "atp", "po_creation"}
    INVENTORY_TYPES = {"inventory_buffer", "rebalancing"}

    series = []
    lines = []
    bands = []
    title = ""
    chart_type = "line"
    annotation = None

    # Product IDs in forecast/inv_level use config-prefixed format (e.g. CFG22_BV001)
    # Decision cards may pass unprefixed IDs — try both formats
    pid_variants = [product_id] if product_id else []
    if product_id and not product_id.startswith(f"CFG{cfg_id}_"):
        pid_variants.append(f"CFG{cfg_id}_{product_id}")

    try:
        if decision_type in DEMAND_TYPES and product_id:
            # Fetch forecast time series (P10/P50/P90) — try both ID formats
            result = await db.execute(
                text("""
                    SELECT forecast_date, p10_quantity, p50_quantity, p90_quantity
                    FROM forecast
                    WHERE product_id = ANY(:pids) AND config_id = :cfg
                    ORDER BY forecast_date
                    LIMIT 52
                """),
                {"pids": pid_variants, "cfg": cfg_id},
            )
            rows = result.fetchall()
            for row in rows:
                series.append({
                    "date": row[0].strftime("%Y-%m-%d") if row[0] else "",
                    "p10": float(row[1] or 0),
                    "p50": float(row[2] or 0),
                    "p90": float(row[3] or 0),
                })
            chart_type = "area"
            bands = [
                {"key": "p90", "color": "#ffc658", "label": "P90 (High)"},
                {"key": "p10", "color": "#82ca9d", "label": "P10 (Low)"},
            ]
            lines = [{"key": "p50", "color": "#8884d8", "label": "P50 (Most Likely)", "bold": True}]
            title = f"Demand Forecast — {product_id}"
            annotation = f"Decision type: {decision_type.replace('_', ' ')}"

        elif decision_type in INVENTORY_TYPES and product_id:
            # Fetch inventory levels over time — try both ID formats
            result = await db.execute(
                text("""
                    SELECT inventory_date, on_hand_qty, in_transit_qty
                    FROM inv_level
                    WHERE product_id = ANY(:pids) AND config_id = :cfg
                    ORDER BY inventory_date
                    LIMIT 52
                """),
                {"pids": pid_variants, "cfg": cfg_id},
            )
            rows = result.fetchall()
            for row in rows:
                series.append({
                    "date": row[0].strftime("%Y-%m-%d") if row[0] else "",
                    "on_hand": float(row[1] or 0),
                    "in_transit": float(row[2] or 0),
                })
            lines = [
                {"key": "on_hand", "color": "#8884d8", "label": "On Hand", "bold": True},
                {"key": "in_transit", "color": "#82ca9d", "label": "In Transit", "bold": False},
            ]
            title = f"Inventory Levels — {product_id}"

        else:
            # Generic: try forecast as fallback
            if product_id:
                result = await db.execute(
                    text("""
                        SELECT forecast_date, p50_quantity
                        FROM forecast
                        WHERE product_id = :pid AND config_id = :cfg
                        ORDER BY forecast_date
                        LIMIT 52
                    """),
                    {"pid": product_id, "cfg": cfg_id},
                )
                rows = result.fetchall()
                for row in rows:
                    series.append({
                        "date": row[0].strftime("%Y-%m-%d") if row[0] else "",
                        "forecast": float(row[1] or 0),
                    })
                lines = [{"key": "forecast", "color": "#8884d8", "label": "Forecast (P50)", "bold": True}]
                title = f"Forecast — {product_id}"

        # Fallback: if no data from primary source, show decision history
        if not series and product_id:
            # Query the decision table for this product's decision history
            TABLE_MAP = {
                "forecast_adjustment": ("powell_forecast_adjustment_decisions", "created_at", "confidence"),
                "atp": ("powell_atp_decisions", "created_at", "confidence"),
                "po_creation": ("powell_po_decisions", "created_at", "confidence"),
                "rebalancing": ("powell_rebalance_decisions", "created_at", "confidence"),
                "inventory_buffer": ("powell_buffer_decisions", "created_at", "confidence"),
                "mo_execution": ("powell_mo_decisions", "created_at", "confidence"),
                "to_execution": ("powell_to_decisions", "created_at", "confidence"),
            }
            tbl_info = TABLE_MAP.get(decision_type)
            if tbl_info:
                tbl_name, date_col, val_col = tbl_info
                result = await db.execute(
                    text(f"""
                        SELECT {date_col}, {val_col}, urgency_at_time,
                               decision_reasoning
                        FROM {tbl_name}
                        WHERE product_id = :pid AND config_id = :cfg
                        ORDER BY {date_col}
                        LIMIT 30
                    """),
                    {"pid": product_id, "cfg": cfg_id},
                )
                rows = result.fetchall()
                for row in rows:
                    series.append({
                        "date": row[0].strftime("%Y-%m-%d %H:%M") if row[0] else "",
                        "confidence": round(float(row[1] or 0) * 100, 1),
                        "urgency": round(float(row[2] or 0) * 100, 1),
                    })
                lines = [
                    {"key": "confidence", "color": "#8884d8", "label": "Confidence %", "bold": True},
                    {"key": "urgency", "color": "#ff7300", "label": "Urgency %", "bold": False},
                ]
                # Get product name from description
                prod_result = await db.execute(
                    text("SELECT description FROM product WHERE id = :pid"),
                    {"pid": product_id},
                )
                prod_name = prod_result.scalar_one_or_none() or product_id
                title = f"Agent Decision History — {prod_name}"
                annotation = f"{len(series)} decisions for this product"

    except Exception as e:
        logger.warning(f"Time series query failed: {e}")
        return {"series": [], "lines": [], "error": True}

    return {
        "series": series,
        "lines": lines,
        "bands": bands if bands else None,
        "chart_type": chart_type,
        "title": title,
        "annotation": annotation,
        "error": len(series) == 0,
    }


@router.post("/chat", response_model=DecisionStreamChatResponse)
async def chat(
    request: DecisionStreamChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Conversational interaction with decision-context injection."""
    service = await _get_service(db, current_user)
    decision_level = getattr(current_user, "decision_level", None)

    result = await service.chat(
        message=request.message,
        conversation_id=request.conversation_id,
        config_id=request.config_id,
        decision_level=decision_level,
    )
    return result
