"""
Directive Service — Parse, Route, and Track Natural Language Directives

Accepts natural language from authenticated users, uses an LLM to extract
structured signals, routes to the appropriate Powell layer based on the
user's role, and tracks effectiveness via Bayesian posteriors.

Routing logic:
  VP / EXECUTIVE / SOP_DIRECTOR  → Layer 4: S&OP GraphSAGE (network-wide)
  MPS_MANAGER / ALLOCATION_MGR   → Layer 2: Execution tGNN (multi-site)
  Site-scoped roles (analysts)    → Layer 1.5: Site tGNN (single site)
  Line-level roles                → Layer 1: Specific TRM (single decision)
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, PowellRoleEnum
from app.models.user_directive import UserDirective

logger = logging.getLogger(__name__)

# Role → Powell layer mapping
_ROLE_TO_LAYER = {
    PowellRoleEnum.SC_VP: "strategic",
    PowellRoleEnum.EXECUTIVE: "strategic",
    PowellRoleEnum.SOP_DIRECTOR: "tactical",
    PowellRoleEnum.MPS_MANAGER: "operational",
    PowellRoleEnum.ALLOCATION_MANAGER: "operational",
    PowellRoleEnum.ORDER_PROMISE_MANAGER: "operational",
    PowellRoleEnum.ATP_ANALYST: "execution",
    PowellRoleEnum.REBALANCING_ANALYST: "execution",
    PowellRoleEnum.PO_ANALYST: "execution",
    PowellRoleEnum.ORDER_TRACKING_ANALYST: "execution",
    PowellRoleEnum.DEMO_ALL: "strategic",
}

# Layer descriptions for the LLM prompt
_LAYER_DESCRIPTIONS = {
    "strategic": "S&OP GraphSAGE — network-wide policy parameters, pushed down through entire cascade",
    "tactical": "Execution tGNN — multi-site daily directives and allocation priorities",
    "operational": "Site tGNN — single-site cross-TRM coordination and urgency modulation",
    "execution": "Individual TRM — specific execution decision at a single site",
}

_REASON_CODES = [
    "STRATEGIC_REVENUE_TARGET",
    "MARKET_INTELLIGENCE",
    "CUSTOMER_FEEDBACK",
    "RISK_MITIGATION",
    "CAPACITY_DIRECTION",
    "PROMOTION_PLANNING",
    "COST_REDUCTION",
    "REGULATORY",
    "OPERATIONAL_ADJUSTMENT",
    "QUALITY_CONCERN",
    "SUPPLIER_ISSUE",
    "DEMAND_SIGNAL",
]

_PARSE_SYSTEM_PROMPT = """You are a supply chain directive parser for the Autonomy platform.

Your job: extract structured signals from natural language directives given by supply chain professionals.
A complete, actionable directive requires ALL of: a reason/justification, a desired outcome (metric + direction),
a magnitude (how much), a time horizon (how long), and a scope (where — geography/sites, and what — products/families).

The directive comes from a user with role "{role}" at Powell layer "{layer}" ({layer_desc}).

Available product families in this tenant: {product_families}
Available site/region names in this tenant: {site_names}

Parse the directive and return JSON with these fields:
{{
  "directive_type": one of {reason_codes},
  "reason_code": same as directive_type (or more specific if clear),
  "intent": "directive" | "observation" | "question",
  "scope": {{
    "region": string or null (resolved to tenant's site hierarchy),
    "product_family": string or null (resolved to tenant's product hierarchy),
    "site_keys": [list of specific site names] or null,
    "product_ids": [list of specific product IDs] or null,
    "time_horizon_weeks": integer or null
  }},
  "direction": "increase" | "decrease" | "maintain" | "reallocate" | null,
  "metric": "revenue" | "cost" | "service_level" | "inventory" | "capacity" | "quality" | "lead_time" | null,
  "magnitude_pct": float or null (e.g. 5.0 for "5%"),
  "target_trm_types": [list from: forecast_adjustment, inventory_buffer, atp_executor, po_creation, inventory_rebalancing, mo_execution, to_execution, quality_disposition, maintenance_scheduling, subcontracting, order_tracking] or null,
  "confidence": float 0-1 (how clearly you understood the directive),
  "missing_fields": [list of objects describing what information is still needed]
}}

CRITICAL — missing_fields rules:
Each missing field is an object: {{"field": "<field_name>", "question": "<natural language question>", "type": "<input_type>", "options": [optional list of choices]}}

Detect these gaps and generate a clarifying question for each:
- If NO reason/justification is given → ask WHY (field: "reason", type: "text")
- If direction is null → ask what outcome they want (field: "direction", type: "select", options: ["increase", "decrease", "maintain", "reallocate"])
- If metric is null → ask which metric to target (field: "metric", type: "select", options: ["revenue", "cost", "service_level", "inventory", "capacity", "quality", "lead_time"])
- If magnitude_pct is null → ask by how much (field: "magnitude_pct", type: "number", question should suggest a range like "By what percentage? (e.g. 5-15%)")
- If scope.time_horizon_weeks is null → ask for how long (field: "time_horizon", type: "select", options: ["2 weeks", "1 month", "1 quarter", "6 months", "1 year"])
- If scope.region is null AND scope.site_keys is null → ask where (field: "geography", type: "select", options: from site_names list)
- If scope.product_family is null AND scope.product_ids is null → ask which products (field: "products", type: "select", options: from product_families list)

If the directive explicitly says "all sites" or "company-wide", geography is NOT missing.
If the directive explicitly says "all products" or doesn't restrict products for a strategic directive, products are NOT missing.
Strategic-layer directives (VP/Executive) may legitimately target the entire network — be lenient on geography/product scope for those.

The "reason" field is ALWAYS required — a directive without justification cannot be tracked for effectiveness.
If the user only states a desire ("increase revenue") without saying WHY, the reason IS missing.
Good reasons: "customer feedback indicates...", "market intelligence suggests...", "Q3 targets require...", "supplier delays mean..."

Set confidence based on completeness: 0 missing = 0.9+, 1-2 missing = 0.5-0.7, 3+ missing = 0.2-0.4.
If missing_fields is empty, set it to an empty list [].

Other rules:
- Resolve vague references ("SW", "frozen") against the provided tenant data
- If the user mentions a time period ("next quarter"), convert to weeks
- If multiple TRMs are affected, list all of them
- For strategic directives, target_trm_types can be null (affects policy parameters)
- If you cannot parse the directive at all, set intent to "question" and confidence to 0.0
- Return ONLY valid JSON, no markdown or explanation
"""


def _build_missing_fields(
    *,
    direction: Optional[str],
    metric: Optional[str],
    magnitude_pct: Optional[float],
    time_horizon_weeks: Optional[int],
    has_reason: bool,
    has_geography: bool,
    has_products: bool,
    layer: str,
    site_names: List[str],
    product_families: List[str],
) -> List[Dict[str, Any]]:
    """Build the list of missing field objects with clarifying questions."""
    missing = []

    if not has_reason:
        missing.append({
            "field": "reason",
            "question": "What is the business reason for this directive? (e.g. customer feedback, market intelligence, Q3 targets, supplier issue)",
            "type": "text",
        })

    if not direction:
        missing.append({
            "field": "direction",
            "question": "What outcome do you want?",
            "type": "select",
            "options": ["increase", "decrease", "maintain", "reallocate"],
        })

    if not metric:
        missing.append({
            "field": "metric",
            "question": "Which metric should this target?",
            "type": "select",
            "options": ["revenue", "cost", "service_level", "inventory", "capacity", "quality", "lead_time"],
        })

    if magnitude_pct is None:
        missing.append({
            "field": "magnitude_pct",
            "question": "By what percentage? (e.g. 5%, 10%, 15%)",
            "type": "number",
        })

    if time_horizon_weeks is None:
        missing.append({
            "field": "time_horizon",
            "question": "For how long should this directive apply?",
            "type": "select",
            "options": ["2 weeks", "1 month", "1 quarter", "6 months", "1 year"],
        })

    # Geography — lenient for strategic layer
    if not has_geography and layer not in ("strategic",):
        opts = site_names[:20] if site_names else []
        missing.append({
            "field": "geography",
            "question": "Which sites or regions does this apply to?",
            "type": "select",
            "options": opts + (["All sites"] if opts else []),
        })

    # Products — lenient for strategic layer
    if not has_products and layer not in ("strategic",):
        opts = product_families[:20] if product_families else []
        missing.append({
            "field": "products",
            "question": "Which product families does this apply to?",
            "type": "select",
            "options": opts + (["All products"] if opts else []),
        })

    return missing


def _detect_missing_from_parsed(
    parsed: Dict[str, Any],
    layer: str,
    tenant_context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Detect missing fields from an already-parsed directive (LLM output that omits missing_fields)."""
    scope = parsed.get("scope", {})

    # Check for reason — if directive_type is generic OPERATIONAL_ADJUSTMENT, likely no reason
    has_reason = parsed.get("reason_code") not in (None, "OPERATIONAL_ADJUSTMENT") or parsed.get("directive_type") not in (None, "OPERATIONAL_ADJUSTMENT")

    has_geography = bool(scope.get("region") or scope.get("site_keys"))
    has_products = bool(scope.get("product_family") or scope.get("product_ids"))

    return _build_missing_fields(
        direction=parsed.get("direction"),
        metric=parsed.get("metric"),
        magnitude_pct=parsed.get("magnitude_pct"),
        time_horizon_weeks=scope.get("time_horizon_weeks"),
        has_reason=has_reason,
        has_geography=has_geography,
        has_products=has_products,
        layer=layer,
        site_names=tenant_context.get("site_names", []),
        product_families=tenant_context.get("product_families", []),
    )


class DirectiveService:
    """Parse, route, and persist user directives."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_directive(
        self,
        user: User,
        config_id: int,
        raw_text: str,
        clarifications: Optional[Dict[str, str]] = None,
    ) -> UserDirective:
        """Parse a natural language directive and persist it.

        Args:
            clarifications: Optional dict of field→value answers from the
                clarification flow. These are appended to the raw text so the
                LLM can incorporate them into the structured parse.
        """
        # Determine Powell layer from user role
        layer = _ROLE_TO_LAYER.get(user.powell_role, "operational")
        if user.user_type and user.user_type.value == "TENANT_ADMIN":
            layer = "strategic"

        # Enrich text with clarification answers if provided
        enriched_text = raw_text
        if clarifications:
            parts = [raw_text, "\n\n--- Additional context provided by user ---"]
            for field, value in clarifications.items():
                parts.append(f"{field}: {value}")
            enriched_text = "\n".join(parts)

        # Gather tenant context for scope resolution
        tenant_context = await self._get_tenant_context(config_id)

        # Parse with LLM
        parsed = await self._parse_with_llm(enriched_text, user, layer, tenant_context)

        # Determine target site keys from scope
        target_site_keys = parsed.get("scope", {}).get("site_keys")
        if not target_site_keys and layer in ("operational", "execution"):
            # Restrict to user's site scope if they have one
            if user.site_scope:
                target_site_keys = user.site_scope

        # Calculate expiry from time horizon
        time_horizon = parsed.get("scope", {}).get("time_horizon_weeks")
        expires_at = None
        if time_horizon:
            expires_at = datetime.utcnow() + timedelta(weeks=time_horizon)

        # Determine effectiveness scope
        eff_scope = {
            "strategic": "network",
            "tactical": "region",
            "operational": "site",
            "execution": "site",
        }.get(layer, "site")

        directive = UserDirective(
            user_id=user.id,
            config_id=config_id,
            tenant_id=user.tenant_id,
            raw_text=raw_text,
            directive_type=parsed.get("directive_type", "OPERATIONAL_ADJUSTMENT"),
            reason_code=parsed.get("reason_code", "OPERATIONAL_ADJUSTMENT"),
            parsed_intent=parsed.get("intent", "directive"),
            parsed_scope=parsed.get("scope", {}),
            parsed_direction=parsed.get("direction"),
            parsed_metric=parsed.get("metric"),
            parsed_magnitude_pct=parsed.get("magnitude_pct"),
            parser_confidence=parsed.get("confidence", 0.5),
            target_layer=layer,
            target_trm_types=parsed.get("target_trm_types"),
            target_site_keys=target_site_keys,
            status="PARSED",
            expires_at=expires_at,
            effectiveness_scope=eff_scope,
        )
        self.db.add(directive)
        await self.db.flush()

        # Auto-apply if confidence is high enough and intent is directive
        if parsed.get("intent") == "directive" and parsed.get("confidence", 0) >= 0.7:
            await self._apply_directive(directive)

        await self.db.commit()
        return directive

    async def get_directives(
        self,
        tenant_id: int,
        config_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[UserDirective]:
        """Get recent directives for a tenant."""
        conditions = [UserDirective.tenant_id == tenant_id]
        if config_id:
            conditions.append(UserDirective.config_id == config_id)
        stmt = (
            select(UserDirective)
            .where(and_(*conditions))
            .order_by(UserDirective.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _apply_directive(self, directive: UserDirective) -> None:
        """Route a parsed directive to the appropriate Powell layer."""
        directive.status = "APPLIED"
        directive.applied_at = datetime.utcnow()

        actions = []
        layer = directive.target_layer

        if layer == "strategic":
            # Route to S&OP GraphSAGE — update policy parameters
            actions.append({
                "layer": "sop_graphsage",
                "action": f"Policy parameter adjustment: {directive.parsed_direction} "
                          f"{directive.parsed_metric} by {directive.parsed_magnitude_pct}%",
                "scope": directive.parsed_scope,
                "status": "queued_for_next_cycle",
            })

        if layer in ("strategic", "tactical"):
            # Route to Execution tGNN — update daily directives
            actions.append({
                "layer": "execution_tgnn",
                "action": f"Directive: {directive.parsed_direction} {directive.parsed_metric}",
                "scope": directive.parsed_scope,
                "status": "queued_for_next_cycle",
            })

        # Route to specific TRMs if identified
        trm_types = directive.target_trm_types or []
        if not trm_types and directive.parsed_direction:
            # Infer TRM targets from metric
            metric = directive.parsed_metric or ""
            if metric in ("revenue", "service_level"):
                trm_types = ["forecast_adjustment", "atp_executor"]
            elif metric == "inventory":
                trm_types = ["inventory_buffer", "inventory_rebalancing"]
            elif metric == "cost":
                trm_types = ["po_creation", "inventory_buffer"]
            elif metric == "capacity":
                trm_types = ["mo_execution", "maintenance_scheduling"]
            elif metric == "quality":
                trm_types = ["quality_disposition"]
            elif metric == "lead_time":
                trm_types = ["po_creation", "to_execution"]

        for trm in trm_types:
            actions.append({
                "layer": f"trm_{trm}",
                "trm_type": trm,
                "action": f"{directive.parsed_direction} {directive.parsed_magnitude_pct or ''}% "
                          f"via {trm}",
                "sites": directive.target_site_keys,
                "status": "applied",
            })

        directive.routed_actions = actions
        logger.info(
            "Directive %d applied: layer=%s, %d actions, confidence=%.2f",
            directive.id, layer, len(actions), directive.parser_confidence,
        )

    async def _parse_with_llm(
        self,
        raw_text: str,
        user: User,
        layer: str,
        tenant_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Parse natural language directive using LLM."""
        role_name = user.powell_role.value if user.powell_role else "TENANT_ADMIN"
        layer_desc = _LAYER_DESCRIPTIONS.get(layer, "")

        system_prompt = _PARSE_SYSTEM_PROMPT.format(
            role=role_name,
            layer=layer,
            layer_desc=layer_desc,
            product_families=json.dumps(tenant_context.get("product_families", [])),
            site_names=json.dumps(tenant_context.get("site_names", [])),
            reason_codes=json.dumps(_REASON_CODES),
        )

        try:
            from app.services.skills.claude_client import ClaudeClient
            client = ClaudeClient()
            response = await client.invoke(
                system=system_prompt,
                user_prompt=raw_text,
                model_tier="haiku",
            )
            parsed = json.loads(response)
            return parsed
        except Exception as e:
            logger.warning("LLM parsing failed, using heuristic: %s", e)
            return self._heuristic_parse(raw_text, layer, tenant_context)

    def _heuristic_parse(
        self, raw_text: str, layer: str, tenant_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Fallback parsing when LLM is unavailable."""
        import re
        text_lower = raw_text.lower()

        direction = None
        if any(w in text_lower for w in ["increase", "more", "boost", "focus on", "grow"]):
            direction = "increase"
        elif any(w in text_lower for w in ["decrease", "reduce", "cut", "lower"]):
            direction = "decrease"

        metric = None
        if "revenue" in text_lower or "sales" in text_lower:
            metric = "revenue"
        elif "cost" in text_lower or "expense" in text_lower:
            metric = "cost"
        elif "inventory" in text_lower or "stock" in text_lower:
            metric = "inventory"
        elif "service" in text_lower or "otif" in text_lower:
            metric = "service_level"
        elif "capacity" in text_lower or "production" in text_lower:
            metric = "capacity"

        # Extract percentage
        magnitude = None
        pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%', raw_text)
        if pct_match:
            magnitude = float(pct_match.group(1))

        # Extract time horizon
        time_weeks = None
        if "quarter" in text_lower:
            time_weeks = 13
        elif "month" in text_lower:
            time_weeks = 4
        elif "year" in text_lower:
            time_weeks = 52
        elif "week" in text_lower:
            week_match = re.search(r'(\d+)\s*week', text_lower)
            time_weeks = int(week_match.group(1)) if week_match else 1

        # Check for reason indicators
        reason_words = ["because", "due to", "since", "as a result", "given that",
                        "customer", "market", "competitor", "feedback", "regulation",
                        "target", "goal", "strategy", "risk", "supplier"]
        has_reason = any(w in text_lower for w in reason_words)

        # Check for geography
        region = None
        site_names = (tenant_context or {}).get("site_names", [])
        for site in site_names:
            if site.lower() in text_lower:
                region = site
                break
        has_geography = region is not None or "all site" in text_lower or "company" in text_lower or "network" in text_lower

        # Check for product scope
        product_family = None
        families = (tenant_context or {}).get("product_families", [])
        for fam in families:
            if fam.lower() in text_lower:
                product_family = fam
                break
        has_products = product_family is not None or "all product" in text_lower

        # Build missing fields
        missing = _build_missing_fields(
            direction=direction, metric=metric, magnitude_pct=magnitude,
            time_horizon_weeks=time_weeks, has_reason=has_reason,
            has_geography=has_geography, has_products=has_products,
            layer=layer, site_names=site_names, product_families=families,
        )

        num_missing = len(missing)
        confidence = max(0.2, 0.9 - num_missing * 0.15)

        return {
            "directive_type": "OPERATIONAL_ADJUSTMENT",
            "reason_code": "OPERATIONAL_ADJUSTMENT",
            "intent": "directive",
            "scope": {
                "region": region,
                "product_family": product_family,
                "time_horizon_weeks": time_weeks,
            },
            "direction": direction,
            "metric": metric,
            "magnitude_pct": magnitude,
            "target_trm_types": None,
            "confidence": confidence,
            "missing_fields": missing,
        }

    async def analyze_directive(
        self,
        user: User,
        config_id: int,
        raw_text: str,
    ) -> Dict[str, Any]:
        """Parse a directive and return the analysis WITHOUT persisting.

        Used by the frontend to detect missing fields and prompt for
        clarification before final submission.
        """
        layer = _ROLE_TO_LAYER.get(user.powell_role, "operational")
        if user.user_type and user.user_type.value == "TENANT_ADMIN":
            layer = "strategic"

        tenant_context = await self._get_tenant_context(config_id)
        parsed = await self._parse_with_llm(raw_text, user, layer, tenant_context)

        # Ensure missing_fields is always present
        if "missing_fields" not in parsed:
            parsed["missing_fields"] = _detect_missing_from_parsed(
                parsed, layer, tenant_context,
            )

        parsed["target_layer"] = layer
        parsed["layer_description"] = _LAYER_DESCRIPTIONS.get(layer, "")
        return parsed

    async def _get_tenant_context(self, config_id: int) -> Dict[str, Any]:
        """Load product families and site names for scope resolution."""
        from sqlalchemy import text

        sites_result = await self.db.execute(
            text("SELECT name, type, master_type FROM site WHERE config_id = :c ORDER BY name"),
            {"c": config_id},
        )
        sites = [{"name": r[0], "type": r[1], "master_type": r[2]} for r in sites_result.fetchall()]

        products_result = await self.db.execute(
            text("""
                SELECT DISTINCT description FROM product_hierarchy_node
                WHERE config_id = :c AND level_name IN ('family', 'category')
                ORDER BY description
            """),
            {"c": config_id},
        )
        families = [r[0] for r in products_result.fetchall()]

        # Fallback: get product names if no hierarchy
        if not families:
            prod_result = await self.db.execute(
                text("SELECT DISTINCT product_name FROM product WHERE config_id = :c LIMIT 50"),
                {"c": config_id},
            )
            families = [r[0] for r in prod_result.fetchall()]

        return {
            "site_names": [s["name"] for s in sites],
            "product_families": families,
        }

    async def collect_directive_outcomes(self) -> Dict[str, Any]:
        """Measure effectiveness of applied directives that have reached their time horizon.

        For each APPLIED directive past its expires_at or time_horizon, compute
        a simple effectiveness_delta by comparing the BSC metric in the directed
        scope before and after the directive was applied.
        """
        from sqlalchemy import text

        now = datetime.utcnow()
        stmt = select(UserDirective).where(
            and_(
                UserDirective.status == "APPLIED",
                UserDirective.measured_at.is_(None),
                UserDirective.expires_at.isnot(None),
                UserDirective.expires_at <= now,
            )
        ).limit(50)
        result = await self.db.execute(stmt)
        directives = list(result.scalars().all())

        stats = {"found": len(directives), "measured": 0}

        for directive in directives:
            directive.status = "MEASURED"
            directive.measured_at = now
            # Placeholder: in production, this would query the BSC for the
            # relevant metric in the directive's scope window and compute delta.
            # For now, mark as measured with null delta (to be filled by the
            # outcome collector when real BSC data is available).
            stats["measured"] += 1

        if directives:
            await self.db.commit()

        logger.info(
            "Directive outcome collection: %d found, %d measured",
            stats["found"], stats["measured"],
        )
        return stats
