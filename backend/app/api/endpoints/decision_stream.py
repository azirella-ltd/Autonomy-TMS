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
    from_site_id: Optional[str] = Query(None, description="Source site for transfers"),
    to_site_id: Optional[str] = Query(None, description="Destination site for transfers"),
    decision_date: Optional[str] = Query(None, description="Decision timestamp"),
    decision_id: Optional[str] = Query(None, description="Decision ID"),
    effective_from: Optional[str] = Query(None, description="Decision effective start date (ISO)"),
    period_days: Optional[int] = Query(None, description="Decision period duration in days"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return contextual time series for a decision — shows the issue, action, and projected outcome.

    Chart window is scoped to: 1 week before effective_from → 1 week after period ends.
    This ensures the chart shows context before the action, the full action period,
    and a week of projected outcome.

    Each TRM decision type returns different data:
    - Rebalancing: inventory at source + destination before/after transfer
    - ATP: ATP vs demand at fulfillment site
    - PO Creation: inventory vs reorder point + expected receipt
    - Forecast Adjustment: old vs new forecast vs actuals
    - Inventory Buffer: on-hand vs safety stock target
    - MO/TO/Quality/Maintenance/Subcontracting/Order Tracking: type-specific context
    """
    from sqlalchemy import text
    from datetime import datetime, timedelta, date
    from app.core.clock import config_today

    cfg_id = config_id or getattr(current_user, 'default_config_id', None)
    if not cfg_id:
        return {"series": [], "lines": [], "error": True}

    # Parse effective date for chart window
    # Use tenant's virtual today (frozen for demos, real for production)
    ref_date = await config_today(cfg_id, db)
    if effective_from:
        try:
            ref_date = date.fromisoformat(effective_from)
        except Exception:
            pass
    elif decision_date:
        try:
            ref_date = datetime.fromisoformat(decision_date.replace("Z", "+00:00")).date()
        except Exception:
            pass

    # Chart window: 1 week before effective_from → 1 week after period ends
    p_days = period_days or 7
    chart_start = ref_date - timedelta(days=7)
    chart_end = ref_date + timedelta(days=p_days + 7)

    # Normalize product ID to config-prefixed format
    pid = product_id
    if pid and not pid.startswith(f"CFG{cfg_id}_"):
        pid = f"CFG{cfg_id}_{pid}"
    pid_variants = [product_id, pid] if product_id else []

    # Resolve site names for display
    async def _site_name(sid):
        if not sid:
            return "?"
        try:
            r = await db.execute(text("SELECT name FROM site WHERE id = :id"), {"id": int(sid)})
            return r.scalar_one_or_none() or str(sid)
        except Exception:
            return str(sid)

    series = []
    lines = []
    bands = []
    title = ""
    chart_type = "line"
    annotation = None

    try:
        # ─── REBALANCING: inventory at source + destination ───────────
        if decision_type in ("rebalancing", "inventory_rebalancing"):
            src = from_site_id or site_id
            dst = to_site_id
            window_start = chart_start
            window_end = chart_end

            for site_label, sid in [("source", src), ("destination", dst)]:
                if not sid:
                    continue
                result = await db.execute(text("""
                    SELECT inventory_date, on_hand_qty, safety_stock_qty
                    FROM inv_level
                    WHERE product_id = ANY(:pids) AND site_id = :sid AND config_id = :cfg
                    AND inventory_date BETWEEN :s AND :e
                    ORDER BY inventory_date
                """), {"pids": pid_variants, "sid": int(sid), "cfg": cfg_id,
                       "s": window_start, "e": window_end})
                for row in result.fetchall():
                    d = row[0].strftime("%Y-%m-%d") if row[0] else ""
                    entry = next((s for s in series if s["date"] == d), None)
                    if not entry:
                        entry = {"date": d}
                        series.append(entry)
                    entry[f"{site_label}_on_hand"] = round(float(row[1] or 0), 1)
                    entry[f"{site_label}_safety_stock"] = round(float(row[2] or 0), 1)

            series.sort(key=lambda x: x["date"])
            src_name = await _site_name(src)
            dst_name = await _site_name(dst)
            lines = [
                {"key": "source_on_hand", "color": "#8884d8", "label": f"{src_name} On Hand", "bold": True},
                {"key": "source_safety_stock", "color": "#8884d8", "label": f"{src_name} Safety Stock", "bold": False},
                {"key": "destination_on_hand", "color": "#ff7300", "label": f"{dst_name} On Hand", "bold": True},
                {"key": "destination_safety_stock", "color": "#ff7300", "label": f"{dst_name} Safety Stock", "bold": False},
            ]
            title = f"Inventory Rebalancing: {src_name} → {dst_name}"
            annotation = f"Decision period: {ref_date} to {ref_date + timedelta(days=p_days)}"

        # ─── ATP: available-to-promise vs demand ──────────────────────
        elif decision_type == "atp":
            window_start = chart_start
            window_end = chart_end
            result = await db.execute(text("""
                SELECT inventory_date, on_hand_qty, allocated_qty, available_qty, safety_stock_qty
                FROM inv_level
                WHERE product_id = ANY(:pids) AND site_id = :sid AND config_id = :cfg
                AND inventory_date BETWEEN :s AND :e
                ORDER BY inventory_date
            """), {"pids": pid_variants, "sid": int(site_id) if site_id else 0,
                   "cfg": cfg_id, "s": window_start, "e": window_end})
            for row in result.fetchall():
                series.append({
                    "date": row[0].strftime("%Y-%m-%d"),
                    "on_hand": round(float(row[1] or 0), 1),
                    "allocated": round(float(row[2] or 0), 1),
                    "available": round(float(row[3] or 0), 1),
                    "safety_stock": round(float(row[4] or 0), 1),
                })
            lines = [
                {"key": "on_hand", "color": "#8884d8", "label": "On Hand", "bold": True},
                {"key": "available", "color": "#22c55e", "label": "Available (ATP)", "bold": True},
                {"key": "allocated", "color": "#ff7300", "label": "Allocated", "bold": False},
                {"key": "safety_stock", "color": "#ef4444", "label": "Safety Stock", "bold": False},
            ]
            title = f"ATP Position — {product_id}"

        # ─── PO CREATION: inventory vs reorder point + receipt ────────
        elif decision_type == "po_creation":
            window_start = chart_start
            window_end = chart_end
            result = await db.execute(text("""
                SELECT inventory_date, on_hand_qty, safety_stock_qty
                FROM inv_level
                WHERE product_id = ANY(:pids) AND config_id = :cfg
                AND inventory_date BETWEEN :s AND :e
                ORDER BY inventory_date
            """), {"pids": pid_variants, "cfg": cfg_id, "s": window_start, "e": window_end})
            for row in result.fetchall():
                series.append({
                    "date": row[0].strftime("%Y-%m-%d"),
                    "on_hand": round(float(row[1] or 0), 1),
                    "reorder_point": round(float(row[2] or 0) * 1.5, 1),  # ROP ≈ 1.5x SS
                    "safety_stock": round(float(row[2] or 0), 1),
                })
            lines = [
                {"key": "on_hand", "color": "#8884d8", "label": "On Hand", "bold": True},
                {"key": "reorder_point", "color": "#ff7300", "label": "Reorder Point", "bold": False},
                {"key": "safety_stock", "color": "#ef4444", "label": "Safety Stock", "bold": False},
            ]
            title = f"Inventory vs Reorder Point — {product_id}"
            annotation = "PO triggered when on-hand drops below reorder point"

        # ─── FORECAST ADJUSTMENT: old vs new forecast vs actuals ──────
        elif decision_type == "forecast_adjustment":
            # For forecast adjustments, the chart shows the DECISION DATA
            # (original vs adjusted values from powell_forecast_adjustment_decisions)
            # not the generic forecast table, because the seeded decisions carry
            # their own before/after values that may differ from the forecast table.

            # Resolve product + site names
            p_name = product_id
            try:
                nr = await db.execute(text(
                    "SELECT description FROM product WHERE id = ANY(:pids) AND config_id = :cfg LIMIT 1"
                ), {"pids": pid_variants, "cfg": cfg_id})
                pn = nr.scalar()
                if pn:
                    p_name = pn
            except Exception:
                pass
            s_name = await _site_name(site_id)

            # Query ALL adjustment decisions for this (product, site) —
            # handles both single-card and consolidated-card cases.
            adj_rows = []
            try:
                adj_result = await db.execute(text("""
                    SELECT id, adjustment_pct,
                           current_forecast_value, adjusted_forecast_value,
                           created_at
                    FROM powell_forecast_adjustment_decisions
                    WHERE config_id = :cfg
                      AND product_id = ANY(:pids)
                      AND CAST(site_id AS TEXT) = CAST(:sid AS TEXT)
                    ORDER BY id
                """), {"cfg": cfg_id, "pids": pid_variants, "sid": site_id})
                adj_rows = adj_result.fetchall()
            except Exception:
                pass

            if adj_rows:
                # Build series from the actual decision data
                for i, row in enumerate(adj_rows):
                    pct = float(row[1] or 0)
                    before = float(row[2] or 0)
                    after = float(row[3] or 0)
                    label = f"Period {i+1}"
                    series.append({
                        "date": label,
                        "original": round(before, 1),
                        "revised": round(after, 1),
                    })

                avg_pct = sum(float(r[1] or 0) for r in adj_rows) / len(adj_rows)
                chart_type = "line"
                lines = [
                    {"key": "original", "color": "#94a3b8", "label": "Original Forecast", "bold": False},
                    {"key": "revised", "color": "#3b82f6", "label": "Revised Forecast", "bold": True},
                ]
                adj_dir = "up" if avg_pct > 0 else "down"
                title = f"Forecast Adjustment — {p_name} @ {s_name}"
                annotation = (
                    f"Agent adjusted {adj_dir} {abs(avg_pct):.0f}% avg across {len(adj_rows)} periods | "
                    f"Range: {min(float(r[1] or 0) for r in adj_rows):.0f}% to {max(float(r[1] or 0) for r in adj_rows):.0f}%"
                )
            else:
                # Fallback: no decision rows found, show generic forecast
                result = await db.execute(text("""
                    SELECT forecast_date, forecast_p10, forecast_p50, forecast_p90
                    FROM forecast
                    WHERE product_id = ANY(:pids) AND config_id = :cfg
                    AND forecast_date BETWEEN :s AND :e AND forecast_p50 IS NOT NULL
                    ORDER BY forecast_date
                """), {"pids": pid_variants, "cfg": cfg_id, "s": chart_start, "e": chart_end})
                for row in result.fetchall():
                    series.append({
                        "date": row[0].strftime("%Y-%m-%d"),
                        "p50": round(float(row[2] or 0), 1),
                        "p10": round(float(row[1] or 0), 1),
                        "p90": round(float(row[3] or 0), 1),
                    })
                chart_type = "area"
                bands = [
                    {"key": "p90", "color": "#ef4444", "label": "P90 (High)"},
                    {"key": "p10", "color": "#22c55e", "label": "P10 (Low)"},
                ]
                lines = [{"key": "p50", "color": "#3b82f6", "label": "Forecast P50", "bold": True}]
                title = f"Forecast — {p_name} @ {s_name}"
                annotation = f"{chart_start} to {chart_end}"

        # ─── INVENTORY BUFFER: on-hand vs safety stock target ─────────
        elif decision_type == "inventory_buffer":
            window_start = chart_start
            window_end = chart_end
            result = await db.execute(text("""
                SELECT inventory_date, on_hand_qty, safety_stock_qty
                FROM inv_level
                WHERE product_id = ANY(:pids) AND config_id = :cfg
                AND inventory_date BETWEEN :s AND :e
                ORDER BY inventory_date
            """), {"pids": pid_variants, "cfg": cfg_id, "s": window_start, "e": window_end})
            for row in result.fetchall():
                series.append({
                    "date": row[0].strftime("%Y-%m-%d"),
                    "on_hand": round(float(row[1] or 0), 1),
                    "safety_stock": round(float(row[2] or 0), 1),
                })
            lines = [
                {"key": "on_hand", "color": "#8884d8", "label": "On Hand", "bold": True},
                {"key": "safety_stock", "color": "#ef4444", "label": "Safety Stock Target", "bold": False},
            ]
            title = f"Buffer Level — {product_id}"

        # ─── MO EXECUTION: production capacity + WIP ──────────────────
        elif decision_type == "mo_execution":
            window_start = chart_start
            window_end = chart_end
            result = await db.execute(text("""
                SELECT inventory_date, on_hand_qty, in_transit_qty
                FROM inv_level
                WHERE product_id = ANY(:pids) AND config_id = :cfg
                AND inventory_date BETWEEN :s AND :e
                ORDER BY inventory_date
            """), {"pids": pid_variants, "cfg": cfg_id, "s": window_start, "e": window_end})
            for row in result.fetchall():
                series.append({
                    "date": row[0].strftime("%Y-%m-%d"),
                    "finished_goods": round(float(row[1] or 0), 1),
                    "wip": round(float(row[2] or 0), 1),
                })
            lines = [
                {"key": "finished_goods", "color": "#8884d8", "label": "Finished Goods", "bold": True},
                {"key": "wip", "color": "#22c55e", "label": "WIP / In Transit", "bold": False},
            ]
            title = f"Production Impact — {product_id}"

        # ─── TO EXECUTION: in-transit + source/dest on-hand ───────────
        elif decision_type == "to_execution":
            src = from_site_id or site_id
            dst = to_site_id
            window_start = chart_start
            window_end = chart_end
            for label, sid in [("source", src), ("dest", dst)]:
                if not sid:
                    continue
                result = await db.execute(text("""
                    SELECT inventory_date, on_hand_qty, in_transit_qty
                    FROM inv_level
                    WHERE product_id = ANY(:pids) AND site_id = :sid AND config_id = :cfg
                    AND inventory_date BETWEEN :s AND :e
                    ORDER BY inventory_date
                """), {"pids": pid_variants, "sid": int(sid), "cfg": cfg_id,
                       "s": window_start, "e": window_end})
                for row in result.fetchall():
                    d = row[0].strftime("%Y-%m-%d")
                    entry = next((s for s in series if s["date"] == d), None)
                    if not entry:
                        entry = {"date": d}
                        series.append(entry)
                    entry[f"{label}_on_hand"] = round(float(row[1] or 0), 1)
            series.sort(key=lambda x: x["date"])
            lines = [
                {"key": "source_on_hand", "color": "#8884d8", "label": "Source On Hand", "bold": True},
                {"key": "dest_on_hand", "color": "#ff7300", "label": "Destination On Hand", "bold": True},
            ]
            title = f"Transfer Order Impact — {product_id}"

        # ─── QUALITY DISPOSITION: rejection trend + inventory impact ───
        elif decision_type == "quality_disposition":
            window_start = chart_start
            window_end = chart_end
            result = await db.execute(text("""
                SELECT order_date, inspection_quantity, accepted_quantity, rejected_quantity
                FROM quality_order
                WHERE config_id = :cfg AND product_id = ANY(:pids)
                AND order_date BETWEEN :s AND :e
                ORDER BY order_date
            """), {"pids": pid_variants, "cfg": cfg_id, "s": window_start, "e": window_end})
            for row in result.fetchall():
                insp = float(row[1] or 1)
                series.append({
                    "date": row[0].strftime("%Y-%m-%d") if row[0] else "",
                    "accepted": round(float(row[2] or 0), 1),
                    "rejected": round(float(row[3] or 0), 1),
                    "yield_pct": round(float(row[2] or 0) / max(insp, 1) * 100, 1),
                })
            lines = [
                {"key": "yield_pct", "color": "#22c55e", "label": "Yield %", "bold": True},
                {"key": "rejected", "color": "#ef4444", "label": "Rejected Qty", "bold": False},
            ]
            title = f"Quality Inspection — {product_id}"

        # ─── MAINTENANCE: downtime + capacity impact ──────────────────
        elif decision_type == "maintenance_scheduling":
            window_start = chart_start
            window_end = chart_end
            result = await db.execute(text("""
                SELECT order_date, estimated_downtime_hours, actual_downtime_hours, maintenance_type
                FROM maintenance_order
                WHERE config_id = :cfg AND order_date BETWEEN :s AND :e
                ORDER BY order_date
            """), {"cfg": cfg_id, "s": window_start, "e": window_end})
            for row in result.fetchall():
                series.append({
                    "date": row[0].strftime("%Y-%m-%d") if row[0] else "",
                    "estimated_hours": round(float(row[1] or 0), 1),
                    "actual_hours": round(float(row[2] or 0), 1),
                })
            lines = [
                {"key": "estimated_hours", "color": "#8884d8", "label": "Estimated Downtime", "bold": False},
                {"key": "actual_hours", "color": "#ef4444", "label": "Actual Downtime", "bold": True},
            ]
            title = "Maintenance Downtime History"

        # ─── SUBCONTRACTING: capacity vs demand ───────────────────────
        elif decision_type == "subcontracting":
            window_start = chart_start
            window_end = chart_end
            result = await db.execute(text("""
                SELECT inventory_date, on_hand_qty, in_transit_qty
                FROM inv_level
                WHERE product_id = ANY(:pids) AND config_id = :cfg
                AND inventory_date BETWEEN :s AND :e
                ORDER BY inventory_date
            """), {"pids": pid_variants, "cfg": cfg_id, "s": window_start, "e": window_end})
            for row in result.fetchall():
                series.append({
                    "date": row[0].strftime("%Y-%m-%d"),
                    "on_hand": round(float(row[1] or 0), 1),
                    "in_transit": round(float(row[2] or 0), 1),
                })
            lines = [
                {"key": "on_hand", "color": "#8884d8", "label": "On Hand", "bold": True},
                {"key": "in_transit", "color": "#22c55e", "label": "In Transit (Subcontract)", "bold": False},
            ]
            title = f"Subcontracting Impact — {product_id}"

        # ─── ORDER TRACKING: delivery timeline ────────────────────────
        elif decision_type == "order_tracking":
            window_start = chart_start
            window_end = chart_end
            result = await db.execute(text("""
                SELECT order_date, requested_delivery_date, actual_delivery_date
                FROM inbound_order
                WHERE config_id = :cfg AND order_date BETWEEN :s AND :e
                AND supplier_id IS NOT NULL
                ORDER BY order_date
                LIMIT 30
            """), {"cfg": cfg_id, "s": window_start, "e": window_end})
            for row in result.fetchall():
                planned_lt = (row[1] - row[0]).days if row[1] and row[0] else 0
                actual_lt = (row[2] - row[0]).days if row[2] and row[0] else None
                series.append({
                    "date": row[0].strftime("%Y-%m-%d") if row[0] else "",
                    "planned_lead_time": planned_lt,
                    "actual_lead_time": actual_lt,
                })
            lines = [
                {"key": "planned_lead_time", "color": "#8884d8", "label": "Planned Lead Time (days)", "bold": False},
                {"key": "actual_lead_time", "color": "#ff7300", "label": "Actual Lead Time (days)", "bold": True},
            ]
            title = "Order Tracking — Lead Time Performance"

        # ─── GNN DIRECTIVES: inventory at source + destination ─────────
        elif decision_type in ("execution_directive", "allocation_refresh",
                                "network_directive", "site_coordination", "sop_policy"):
            # GNN directives involving transfers: show inventory at both sites
            src = from_site_id or site_id
            dst = to_site_id
            window_start = chart_start
            window_end = chart_end

            if src or dst:
                for site_label, sid in [("source", src), ("destination", dst)]:
                    if not sid:
                        continue
                    try:
                        result = await db.execute(text("""
                            SELECT inventory_date, on_hand_qty, safety_stock_qty
                            FROM inv_level
                            WHERE product_id = ANY(:pids) AND site_id = :sid AND config_id = :cfg
                            AND inventory_date BETWEEN :s AND :e
                            ORDER BY inventory_date
                        """), {"pids": pid_variants, "sid": int(sid), "cfg": cfg_id,
                               "s": window_start, "e": window_end})
                        for row in result.fetchall():
                            d_str = row[0].strftime("%Y-%m-%d") if row[0] else ""
                            entry = next((s for s in series if s["date"] == d_str), None)
                            if not entry:
                                entry = {"date": d_str}
                                series.append(entry)
                            entry[f"{site_label}_on_hand"] = round(float(row[1] or 0), 1)
                            entry[f"{site_label}_safety_stock"] = round(float(row[2] or 0), 1)
                    except Exception:
                        pass

                series.sort(key=lambda x: x["date"])
                src_name = await _site_name(src) if src else "Source"
                dst_name = await _site_name(dst) if dst else "Destination"
                lines = [
                    {"key": "source_on_hand", "color": "#8884d8", "label": f"{src_name} On Hand", "bold": True},
                    {"key": "source_safety_stock", "color": "#8884d8", "label": f"{src_name} Safety Stock", "bold": False},
                    {"key": "destination_on_hand", "color": "#ff7300", "label": f"{dst_name} On Hand", "bold": True},
                    {"key": "destination_safety_stock", "color": "#ff7300", "label": f"{dst_name} Safety Stock", "bold": False},
                ]
                title = f"Inventory Position — {await _site_name(src) if src else '?'} / {await _site_name(dst) if dst else '?'}"
            else:
                # No site routing — fall through to forecast chart
                if pid_variants:
                    result = await db.execute(text("""
                        SELECT forecast_date, forecast_p50
                        FROM forecast
                        WHERE product_id = ANY(:pids) AND config_id = :cfg
                        AND forecast_date BETWEEN :s AND :e AND forecast_p50 IS NOT NULL
                        ORDER BY forecast_date
                    """), {"pids": pid_variants, "cfg": cfg_id, "s": window_start, "e": window_end})
                    for row in result.fetchall():
                        series.append({
                            "date": row[0].strftime("%Y-%m-%d"),
                            "p50": round(float(row[1] or 0), 1),
                        })
                    lines = [{"key": "p50", "color": "#8884d8", "label": "Forecast P50", "bold": True}]
                    title = f"Forecast Context — {product_id}"

        # ─── FALLBACK: generic forecast context ───────────────────────
        else:
            window_start = chart_start
            window_end = chart_end
            if pid_variants:
                result = await db.execute(text("""
                    SELECT forecast_date, forecast_p10, forecast_p50, forecast_p90
                    FROM forecast
                    WHERE product_id = ANY(:pids) AND config_id = :cfg
                    AND forecast_date BETWEEN :s AND :e AND forecast_p50 IS NOT NULL
                    ORDER BY forecast_date
                """), {"pids": pid_variants, "cfg": cfg_id, "s": window_start, "e": window_end})
                for row in result.fetchall():
                    series.append({
                        "date": row[0].strftime("%Y-%m-%d"),
                        "p50": round(float(row[2] or 0), 1),
                    })
                lines = [{"key": "p50", "color": "#8884d8", "label": "Forecast P50", "bold": True}]
                title = f"Forecast Context — {product_id}"

    except Exception as e:
        logger.warning(f"Time series query failed for {decision_type}: {e}")
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


@router.get("/chart/{decision_type}/{decision_id}")
async def get_decision_chart(
    decision_type: str,
    decision_id: int,
    config_id: int = Query(...),
    product_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get contextual chart data for a specific decision.

    Returns time-series data showing the ISSUE → ACTION → PROJECTED OUTCOME
    with a narrow, decision-relevant time window.

    Supports all 12 TRM decision types with type-specific charts:
    - ATP: supply vs demand buckets
    - Rebalancing: inventory at source + destination before/after
    - PO Creation: inventory vs reorder point + expected receipt
    - Forecast: old vs new forecast vs actuals with P10/P90
    - Buffer: on-hand vs safety stock target
    - MO: production schedule + capacity
    - TO: in-transit + source/dest on-hand
    - Quality: inspection results + inventory impact
    - Maintenance: downtime + capacity impact
    - Subcontracting: internal capacity vs demand
    - Order Tracking: delivery timeline + risk
    """
    from app.services.decision_chart_service import DecisionChartService

    service = DecisionChartService(db)
    return await service.get_chart_data(
        decision_type=decision_type,
        decision_id=decision_id,
        config_id=config_id,
        product_id=product_id,
        site_id=site_id,
    )
