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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

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
  "intent": "directive" | "observation" | "question" | "unknown",
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
- INTENT CLASSIFICATION (critical):
  - "directive" = the user wants to CHANGE something (e.g., "increase service levels by 5%", "reduce inventory in SW region")
  - "question" = the user wants to KNOW something (e.g., "where are we most exposed to stockouts?", "what's our forecast accuracy?")
  - "observation" = the user is sharing information (e.g., "I heard competitor X is launching a new product")
  - "unknown" = you genuinely cannot determine intent. Set confidence to 0.0.
  If it is clearly a question (contains "?", starts with who/what/where/when/why/how, asks for information), set intent to "question".
  If it is clearly a directive (imperative verb, requests a change, sets a target), set intent to "directive".
  If it could be either, set intent to "unknown" and confidence to 0.0 — the system will ask the user to clarify.
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
        """Route a parsed directive to the appropriate Powell layer.

        Strategic → create/update PowellPolicyParameters
        Tactical  → create GNNDirectiveReview for human review
        Operational/Execution → adjust urgency via HiveSignalBus
        """
        directive.status = "APPLIED"
        directive.applied_at = datetime.utcnow()

        actions = []
        layer = directive.target_layer

        # --- Infer TRM targets from metric ---
        trm_types = directive.target_trm_types or []
        if not trm_types and directive.parsed_direction:
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

        # --- Layer 4: Strategic → PowellPolicyParameters ---
        if layer == "strategic":
            action_result = await self._apply_strategic(directive)
            actions.append(action_result)

        # --- Layer 2: Tactical → GNNDirectiveReview ---
        if layer in ("strategic", "tactical"):
            action_result = await self._apply_tactical(directive)
            actions.append(action_result)

        # --- Layer 1.5/1: Operational/Execution → urgency adjustment ---
        if trm_types:
            urgency_results = await self._apply_urgency_adjustments(
                directive, trm_types,
            )
            actions.extend(urgency_results)

        directive.routed_actions = actions
        logger.info(
            "Directive %d applied: layer=%s, %d actions, confidence=%.2f",
            directive.id, layer, len(actions), directive.parser_confidence,
        )

    async def _apply_strategic(self, directive: UserDirective) -> Dict[str, Any]:
        """Create PowellPolicyParameters record from a strategic directive."""
        from app.models.powell import PowellPolicyParameters, PolicyType

        # Map directive metric to policy type
        metric_to_policy = {
            "revenue": PolicyType.INVENTORY,
            "service_level": PolicyType.INVENTORY,
            "inventory": PolicyType.INVENTORY,
            "cost": PolicyType.LOT_SIZING,
            "capacity": PolicyType.EXCEPTION,
            "quality": PolicyType.EXCEPTION,
            "lead_time": PolicyType.SOURCING,
        }
        policy_type = metric_to_policy.get(
            directive.parsed_metric or "", PolicyType.INVENTORY,
        )

        # Build parameter adjustment
        magnitude = directive.parsed_magnitude_pct or 5.0
        direction_mult = 1.0 if directive.parsed_direction == "increase" else -1.0
        adjustment_factor = 1.0 + (direction_mult * magnitude / 100.0)

        params = PowellPolicyParameters(
            config_id=directive.config_id,
            policy_type=policy_type,
            entity_type="directive",
            entity_id=f"directive_{directive.id}",
            parameters={
                "adjustment_factor": round(adjustment_factor, 4),
                "direction": directive.parsed_direction,
                "metric": directive.parsed_metric,
                "magnitude_pct": magnitude,
                "source_directive_id": directive.id,
            },
            optimization_method="user_directive",
            optimization_objective=directive.parsed_metric,
            decision_reasoning=(
                f"User directive: {directive.raw_text} "
                f"(reason: {directive.reason_code}, "
                f"confidence: {directive.parser_confidence:.2f})"
            ),
            is_active=True,
        )
        self.db.add(params)
        await self.db.flush()

        logger.info(
            "Strategic directive %d → PowellPolicyParameters %d "
            "(type=%s, factor=%.4f)",
            directive.id, params.id, policy_type.value, adjustment_factor,
        )
        return {
            "layer": "sop_graphsage",
            "action": f"Policy parameter created: {directive.parsed_direction} "
                      f"{directive.parsed_metric} by {magnitude}%",
            "policy_parameters_id": params.id,
            "adjustment_factor": adjustment_factor,
            "status": "created",
        }

    async def _apply_tactical(self, directive: UserDirective) -> Dict[str, Any]:
        """Create GNNDirectiveReview record for human review."""
        from app.models.gnn_directive_review import GNNDirectiveReview

        # Determine scope
        scope = "execution_directive"
        model_type = "execution_tgnn"
        if directive.target_layer == "strategic":
            scope = "sop_policy"
            model_type = "sop_graphsage"

        # Build proposed values from directive
        proposed = {
            "direction": directive.parsed_direction,
            "metric": directive.parsed_metric,
            "magnitude_pct": directive.parsed_magnitude_pct,
            "source_directive_id": directive.id,
            "raw_text": directive.raw_text,
        }
        if directive.target_trm_types:
            proposed["target_trm_types"] = directive.target_trm_types
        if directive.target_site_keys:
            proposed["target_site_keys"] = directive.target_site_keys

        # Determine site key — use first target site or "NETWORK"
        site_key = "NETWORK"
        if directive.target_site_keys:
            site_key = directive.target_site_keys[0]
        elif directive.parsed_scope and directive.parsed_scope.get("site_keys"):
            site_key = directive.parsed_scope["site_keys"][0]

        review = GNNDirectiveReview(
            config_id=directive.config_id,
            site_key=site_key,
            directive_scope=scope,
            proposed_values=proposed,
            proposed_reasoning=(
                f"User directive from {directive.user.name if directive.user else 'unknown'}: "
                f"{directive.raw_text}"
            ),
            model_type=model_type,
            model_confidence=directive.parser_confidence,
            status="PROPOSED",
            expires_at=directive.expires_at,
        )
        self.db.add(review)
        await self.db.flush()

        logger.info(
            "Tactical directive %d → GNNDirectiveReview %d "
            "(scope=%s, site=%s)",
            directive.id, review.id, scope, site_key,
        )
        return {
            "layer": model_type,
            "action": f"Directive review created: {directive.parsed_direction} "
                      f"{directive.parsed_metric}",
            "gnn_directive_review_id": review.id,
            "scope": scope,
            "site_key": site_key,
            "status": "proposed",
        }

    async def _apply_urgency_adjustments(
        self,
        directive: UserDirective,
        trm_types: List[str],
    ) -> List[Dict[str, Any]]:
        """Adjust TRM urgency via HiveSignalBus for operational/execution directives.

        This modifies the urgency vector in registered SiteAgents, which affects
        the next decision cycle. The adjustment is proportional to the directive's
        magnitude and direction.
        """
        results = []
        magnitude = directive.parsed_magnitude_pct or 5.0

        # Map direction to urgency delta:
        # "increase" metric → raise urgency (agent should act more aggressively)
        # "decrease" metric → lower urgency (agent should back off)
        direction = directive.parsed_direction or "increase"
        if direction in ("increase", "reallocate"):
            base_delta = 0.15
        elif direction == "decrease":
            base_delta = -0.15
        else:
            base_delta = 0.0

        # Scale delta by magnitude (5% → base, 20% → 4x base, capped at ±0.3)
        scale = min(magnitude / 5.0, 4.0) if magnitude > 0 else 1.0
        delta = max(-0.3, min(0.3, base_delta * scale))

        if abs(delta) < 0.01:
            return results

        # Try to get registered SiteAgents
        site_agents = self._get_site_agents()
        if not site_agents:
            # No live agents — record intent for next decision cycle
            for trm in trm_types:
                results.append({
                    "layer": f"trm_{trm}",
                    "trm_type": trm,
                    "action": f"Urgency adjustment queued: delta={delta:+.3f}",
                    "sites": directive.target_site_keys,
                    "delta": delta,
                    "status": "queued_no_active_agents",
                })
            return results

        # Apply urgency adjustment to matching sites
        target_sites = directive.target_site_keys
        adjusted_count = 0

        for site_key, agent in site_agents.items():
            # Filter by target sites if specified
            if target_sites and site_key not in target_sites:
                continue

            signal_bus = getattr(agent, "signal_bus", None)
            if not signal_bus:
                continue

            for trm in trm_types:
                try:
                    signal_bus.urgency.adjust(trm, delta)
                    adjusted_count += 1
                except Exception as e:
                    logger.warning(
                        "Failed to adjust urgency for %s/%s: %s",
                        site_key, trm, e,
                    )

        for trm in trm_types:
            results.append({
                "layer": f"trm_{trm}",
                "trm_type": trm,
                "action": f"Urgency adjusted: delta={delta:+.3f} "
                          f"on {adjusted_count} site(s)",
                "sites": target_sites,
                "delta": delta,
                "adjusted_count": adjusted_count,
                "status": "applied",
            })

        logger.info(
            "Execution directive %d → urgency delta=%+.3f for %s on %d sites",
            directive.id, delta, trm_types, adjusted_count,
        )
        return results

    @staticmethod
    def _get_site_agents() -> Dict[str, Any]:
        """Get registered SiteAgent instances from the module-level registry.

        The DirectiveBroadcastService stores its instance in
        ``_active_broadcast_service`` at module scope when created by the
        scheduler or startup code.  Returns empty dict when no agents are
        registered (e.g., during startup or testing).
        """
        try:
            from app.services.powell import directive_broadcast_service as dbs_mod
            svc = getattr(dbs_mod, "_active_broadcast_service", None)
            if svc and hasattr(svc, "_site_agents"):
                return svc._site_agents
        except ImportError:
            pass
        return {}

    async def _parse_with_llm(
        self,
        raw_text: str,
        user: User,
        layer: str,
        tenant_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Parse natural language directive using LLM."""
        # Handle explicit intent prefixes from the UI clarification flow
        forced_intent = None
        if raw_text.startswith("[Directive] "):
            forced_intent = "directive"
            raw_text = raw_text[len("[Directive] "):]
        elif raw_text.startswith("[Question] "):
            forced_intent = "question"
            raw_text = raw_text[len("[Question] "):]

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
            result = await client.complete(
                system_prompt=system_prompt,
                user_message=raw_text,
                model_tier="haiku",
                temperature=0.1,
                max_tokens=1024,
            )
            content = result.get("content", "")
            parsed = client.parse_json_response(content)

            # Override intent if user explicitly clarified
            if forced_intent:
                parsed["intent"] = forced_intent
                if forced_intent == "question":
                    parsed["confidence"] = max(parsed.get("confidence", 0.5), 0.5)

            # Ensure missing_fields is present even if LLM omits it
            if "missing_fields" not in parsed or parsed["missing_fields"] is None:
                parsed["missing_fields"] = _detect_missing_from_parsed(
                    parsed, layer, tenant_context,
                )
            return parsed
        except Exception as e:
            logger.warning("LLM parsing failed, using heuristic: %s", e)
            result = self._heuristic_parse(raw_text, layer, tenant_context)
            if forced_intent:
                result["intent"] = forced_intent
            return result

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
        """Parse user input and route appropriately.

        Three possible intents:
        - "directive" → structured parse + missing field detection (submit flow)
        - "question"  → query relevant data, generate LLM answer (chat flow)
        - "unknown"   → ask the user to clarify
        """
        layer = _ROLE_TO_LAYER.get(user.powell_role, "operational")
        if user.user_type and user.user_type.value == "TENANT_ADMIN":
            layer = "strategic"

        tenant_context = await self._get_tenant_context(config_id)
        parsed = await self._parse_with_llm(raw_text, user, layer, tenant_context)

        intent = parsed.get("intent", "directive")

        # --- Question flow: query data and answer via LLM ---
        if intent == "question":
            answer = await self._answer_question(
                raw_text, user, config_id, layer, tenant_context, parsed,
            )
            return {
                "intent": "question",
                "answer": answer,
                "confidence": parsed.get("confidence", 0.5),
                "target_layer": layer,
                "layer_description": _LAYER_DESCRIPTIONS.get(layer, ""),
            }

        # --- Ambiguous: LLM couldn't tell if directive or question ---
        if intent == "unknown" or parsed.get("confidence", 0) < 0.2:
            return {
                "intent": "unknown",
                "clarification_needed": True,
                "question": (
                    "I'm not sure if this is a directive (something you want me to act on) "
                    "or a question (something you want me to look up). Could you clarify?"
                ),
                "original_text": raw_text,
                "target_layer": layer,
                "layer_description": _LAYER_DESCRIPTIONS.get(layer, ""),
            }

        # --- Directive flow: structured parse + gap detection ---
        if "missing_fields" not in parsed:
            parsed["missing_fields"] = _detect_missing_from_parsed(
                parsed, layer, tenant_context,
            )

        parsed["target_layer"] = layer
        parsed["layer_description"] = _LAYER_DESCRIPTIONS.get(layer, "")
        return parsed

    async def _answer_question(
        self,
        raw_text: str,
        user: User,
        config_id: int,
        layer: str,
        tenant_context: Dict[str, Any],
        parsed: Dict[str, Any],
    ) -> str:
        """Answer a supply chain question by querying relevant data and using the LLM.

        Gathers context from the database based on the question's scope
        (inventory levels, forecasts, decision history, etc.) and passes
        it to the LLM along with the original question.
        """
        from sqlalchemy import text

        # Gather data context based on what the question seems to be about
        data_context_parts: List[str] = []
        metric = parsed.get("metric")
        scope = parsed.get("scope", {})
        site_keys = scope.get("site_keys") or tenant_context.get("site_names", [])[:10]

        # Inventory / stockout data
        if metric in ("inventory", "service_level", None):
            try:
                inv_q = text("""
                    SELECT s.name AS site_name, p.product_name,
                           il.on_hand_qty, il.in_transit_qty,
                           ip.ss_quantity, ip.reorder_point
                    FROM inv_level il
                    JOIN site s ON s.id = il.site_id
                    JOIN product p ON p.id = il.product_id
                    LEFT JOIN inv_policy ip ON ip.product_id = il.product_id
                        AND ip.site_id = il.site_id AND ip.is_active = true
                    WHERE s.config_id = :cid
                    ORDER BY (il.on_hand_qty - COALESCE(ip.ss_quantity, 0)) ASC
                    LIMIT 20
                """)
                rows = await self.db.execute(inv_q, {"cid": config_id})
                inv_data = rows.fetchall()
                if inv_data:
                    lines = ["Inventory levels (sorted by risk, lowest first):"]
                    for r in inv_data:
                        ss = r[4] or 0
                        gap = (r[2] or 0) - ss
                        lines.append(
                            f"  {r[0]} / {r[1]}: on_hand={r[2]}, "
                            f"in_transit={r[3]}, safety_stock={ss}, "
                            f"gap_to_ss={gap:.0f}"
                        )
                    data_context_parts.append("\n".join(lines))
            except Exception as e:
                logger.debug("Inventory context query failed: %s", e)

        # Forecast data
        if metric in ("revenue", "service_level", None):
            try:
                fcst_q = text("""
                    SELECT s.name, p.product_name,
                           f.forecast_value_p50, f.forecast_value_p10,
                           f.forecast_value_p90, f.forecast_date
                    FROM forecast f
                    JOIN site s ON s.id = f.site_id
                    JOIN product p ON p.id = f.product_id
                    WHERE f.config_id = :cid
                      AND f.forecast_date >= CURRENT_DATE
                      AND f.forecast_date <= CURRENT_DATE + INTERVAL '21 days'
                    ORDER BY f.forecast_date, s.name
                    LIMIT 30
                """)
                rows = await self.db.execute(fcst_q, {"cid": config_id})
                fcst_data = rows.fetchall()
                if fcst_data:
                    lines = ["Forecast (next 3 weeks):"]
                    for r in fcst_data:
                        lines.append(
                            f"  {r[5]} {r[0]} / {r[1]}: "
                            f"P10={r[3]}, P50={r[2]}, P90={r[4]}"
                        )
                    data_context_parts.append("\n".join(lines))
            except Exception as e:
                logger.debug("Forecast context query failed: %s", e)

        # Recent decisions / exceptions
        try:
            exc_q = text("""
                SELECT site_key, exception_type, severity, recommended_action,
                       created_at
                FROM powell_order_exceptions
                WHERE config_id = :cid
                  AND created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
                ORDER BY created_at DESC
                LIMIT 15
            """)
            rows = await self.db.execute(exc_q, {"cid": config_id})
            exc_data = rows.fetchall()
            if exc_data:
                lines = ["Recent order exceptions (last 7 days):"]
                for r in exc_data:
                    lines.append(
                        f"  {r[4]} {r[0]}: {r[1]} (severity={r[2]}, "
                        f"rec={r[3]})"
                    )
                data_context_parts.append("\n".join(lines))
        except Exception as e:
            logger.debug("Exception context query failed: %s", e)

        data_context = "\n\n".join(data_context_parts) if data_context_parts else "No detailed data available for this scope."

        # Build answer prompt
        answer_system = (
            "You are a supply chain analyst for the Autonomy platform. "
            "Answer the user's question based on the data provided below. "
            "Be specific — cite site names, product names, and numbers from the data. "
            "If the data is insufficient to fully answer, say what you can determine "
            "and what additional data would be needed.\n\n"
            f"User role: {user.powell_role.value if user.powell_role else 'TENANT_ADMIN'}\n"
            f"Powell layer: {layer}\n"
            f"Available sites: {json.dumps(tenant_context.get('site_names', []))}\n"
            f"Available product families: {json.dumps(tenant_context.get('product_families', []))}\n\n"
            f"--- DATA CONTEXT ---\n{data_context}\n--- END DATA ---"
        )

        try:
            from app.services.skills.claude_client import ClaudeClient
            client = ClaudeClient()
            result = await client.complete(
                system_prompt=answer_system,
                user_message=raw_text,
                model_tier="haiku",
                temperature=0.3,
                max_tokens=1500,
            )
            return result.get("content", "I was unable to generate an answer. Please try rephrasing your question.")
        except Exception as e:
            logger.warning("Question answering LLM call failed: %s", e)
            return (
                "I'm unable to answer right now due to a service issue. "
                "Please try again in a moment."
            )

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

        For each APPLIED directive past its expires_at, compute effectiveness_delta
        by comparing the targeted BSC metric in the directive's scope before vs
        after the directive was applied.

        Metric sources:
        - revenue / service_level → PerformanceMetric table
        - inventory / cost → InvLevel / supply_plan aggregates
        - capacity → resource_capacity_constraint utilization

        Falls back to TRM decision outcome data when BSC metrics are unavailable.
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

        stats = {"found": len(directives), "measured": 0, "with_delta": 0}

        for directive in directives:
            delta = await self._compute_directive_delta(directive)
            directive.status = "MEASURED"
            directive.measured_at = now
            directive.effectiveness_delta = delta
            stats["measured"] += 1
            if delta is not None:
                stats["with_delta"] += 1

        if directives:
            await self.db.commit()

        logger.info(
            "Directive outcome collection: %d found, %d measured, %d with delta",
            stats["found"], stats["measured"], stats["with_delta"],
        )
        return stats

    async def _compute_directive_delta(
        self, directive: UserDirective,
    ) -> Optional[float]:
        """Compute effectiveness delta for a single directive.

        Compares the targeted metric in the pre-directive window vs the
        post-directive window. Returns a signed delta (positive = improvement
        in the directed direction).
        """
        from sqlalchemy import text

        if not directive.applied_at or not directive.parsed_metric:
            return None

        config_id = directive.config_id
        applied = directive.applied_at
        metric = directive.parsed_metric
        direction = directive.parsed_direction or "increase"

        # Window: compare [applied - window, applied] vs [applied, expires_at]
        pre_start = applied - timedelta(days=30)

        # Try TRM decision outcomes first — most reliable source
        trm_types = directive.target_trm_types or []
        if trm_types:
            delta = await self._delta_from_trm_decisions(
                config_id, trm_types, pre_start, applied,
                directive.expires_at or now_utc(),
            )
            if delta is not None:
                # Flip sign if direction is "decrease" (lower cost = positive)
                if direction == "decrease":
                    delta = -delta
                return round(delta, 4)

        # Fallback: query PerformanceMetric for the metric
        try:
            pre_q = text("""
                SELECT AVG(metric_value) FROM performance_metrics
                WHERE config_id = :cid
                  AND metric_name = :metric
                  AND recorded_at BETWEEN :t0 AND :t1
            """)
            post_q = text("""
                SELECT AVG(metric_value) FROM performance_metrics
                WHERE config_id = :cid
                  AND metric_name = :metric
                  AND recorded_at BETWEEN :t1 AND :t2
            """)
            pre_result = await self.db.execute(pre_q, {
                "cid": config_id, "metric": metric,
                "t0": pre_start, "t1": applied,
            })
            post_result = await self.db.execute(post_q, {
                "cid": config_id, "metric": metric,
                "t1": applied, "t2": directive.expires_at or now_utc(),
            })
            pre_val = pre_result.scalar()
            post_val = post_result.scalar()

            if pre_val is not None and post_val is not None and pre_val != 0:
                raw_delta = (post_val - pre_val) / abs(pre_val)
                if direction == "decrease":
                    raw_delta = -raw_delta
                return round(raw_delta, 4)
        except Exception as e:
            logger.debug("PerformanceMetric query failed: %s", e)

        return None

    async def _delta_from_trm_decisions(
        self,
        config_id: int,
        trm_types: List[str],
        pre_start: datetime,
        applied_at: datetime,
        post_end: datetime,
    ) -> Optional[float]:
        """Compute delta from TRM decision outcomes in powell_*_decisions tables."""
        from sqlalchemy import text

        # Map TRM type to its decision table and outcome column
        # Column names match actual schema in powell_decisions.py
        table_map = {
            "atp_executor": ("powell_atp_decisions", "actual_fulfilled_qty"),
            "po_creation": ("powell_po_decisions", "actual_cost"),
            "inventory_rebalancing": ("powell_rebalance_decisions", "service_impact"),
            "inventory_buffer": ("powell_buffer_decisions", "actual_service_level"),
            "forecast_adjustment": ("powell_forecast_adjustment_decisions", "forecast_error_after"),
            "order_tracking": ("powell_order_exceptions", "resolution_time_hours"),
            "mo_execution": ("powell_mo_decisions", "actual_yield_pct"),
            "to_execution": ("powell_to_decisions", "actual_transit_days"),
            "quality_disposition": ("powell_quality_decisions", "actual_rework_cost"),
            "maintenance_scheduling": ("powell_maintenance_decisions", "actual_downtime_hours"),
            "subcontracting": ("powell_subcontracting_decisions", "actual_cost"),
        }

        deltas = []
        for trm in trm_types:
            entry = table_map.get(trm)
            if not entry:
                continue
            table, col = entry

            try:
                # Check if the outcome column exists
                pre_q = text(f"""
                    SELECT AVG({col}) FROM {table}
                    WHERE config_id = :cid
                      AND created_at BETWEEN :t0 AND :t1
                      AND {col} IS NOT NULL
                """)
                post_q = text(f"""
                    SELECT AVG({col}) FROM {table}
                    WHERE config_id = :cid
                      AND created_at BETWEEN :t1 AND :t2
                      AND {col} IS NOT NULL
                """)
                pre_r = await self.db.execute(pre_q, {
                    "cid": config_id, "t0": pre_start, "t1": applied_at,
                })
                post_r = await self.db.execute(post_q, {
                    "cid": config_id, "t1": applied_at, "t2": post_end,
                })
                pre_val = pre_r.scalar()
                post_val = post_r.scalar()

                if pre_val is not None and post_val is not None:
                    deltas.append(post_val - pre_val)
            except Exception as e:
                logger.debug("TRM delta query failed for %s: %s", trm, e)
                continue

        if deltas:
            return sum(deltas) / len(deltas)
        return None
