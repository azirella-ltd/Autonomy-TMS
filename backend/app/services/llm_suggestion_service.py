"""
LLM-powered suggestion generation service.
Phase 7 Sprint 3

This service generates intelligent order recommendations using LLM reasoning.
Supports OpenAI GPT-4 and Anthropic Claude with fallback to heuristic strategies.
"""

from typing import Dict, Any, Optional, List
import logging
import json
import re
from datetime import datetime

logger = logging.getLogger(__name__)


class LLMSuggestionService:
    """Service for generating LLM-powered agent suggestions."""

    def __init__(self, provider: str = "openai-compatible", model: str = None):
        """
        Initialize LLM service.

        Args:
            provider: LLM provider (default "openai-compatible" for vLLM/Ollama)
            model: Model name (defaults to LLM_MODEL_NAME or AUTONOMY_LLM_MODEL env)
        """
        import os
        self.provider = provider.lower()
        self.model = model or os.getenv("LLM_MODEL_NAME") or os.getenv("AUTONOMY_LLM_MODEL") or "qwen3-8b"
        self.client = None

        # Initialize client lazily (only when first used)
        self._client_initialized = False

        logger.info(f"LLM service initialized: {provider}/{model}")

    def _init_client(self):
        """Initialize OpenAI-compatible async client (lazy loading).

        Works with vLLM, Ollama, or any OpenAI-compatible API.
        """
        if self._client_initialized:
            return

        try:
            import os
            from openai import AsyncOpenAI
            kwargs = {}
            base_url = os.getenv("LLM_API_BASE")
            if base_url:
                kwargs["base_url"] = base_url
            api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "not-needed"
            kwargs["api_key"] = api_key
            self.client = AsyncOpenAI(**kwargs)
            logger.info(f"LLM client initialized (base_url={base_url or 'default'})")
            self._client_initialized = True

        except ImportError as e:
            logger.error(f"Failed to import openai library: {e}")
            logger.warning("LLM suggestions will fall back to heuristic mode")
            self.client = None
        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
            self.client = None

    async def generate_suggestion(
        self,
        agent_name: str,
        context: Dict[str, Any],
        request_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate order recommendation using LLM.

        Args:
            agent_name: Agent role (retailer, wholesaler, distributor, factory)
            context: Game state context (inventory, backlog, demand, etc.)
            request_data: Optional additional request parameters (priority, etc.)

        Returns:
            Dict with:
                - order_quantity: int
                - confidence: float (0.0-1.0)
                - rationale: str (1-2 sentence summary)
                - reasoning_steps: List[str] (detailed reasoning)
                - risk_factors: List[str] (potential risks)
                - alternative_strategies: List[Dict] (alternative approaches)
        """
        self._init_client()

        if not self.client:
            logger.warning("LLM client not available, using fallback")
            return self._fallback_suggestion(agent_name, context)

        try:
            # Retrieve RAG context from knowledge base
            from app.services.rag_context import get_rag_context
            rag_query = f"{agent_name} supply chain order quantity inventory management demand planning"
            kb_context = await get_rag_context(rag_query, top_k=3, max_tokens=2000)

            # Build prompt
            prompt = self._build_suggestion_prompt(agent_name, context, request_data, kb_context=kb_context)

            # Call LLM (all providers use OpenAI-compatible API)
            response = await self._call_openai(prompt)

            # Parse response
            suggestion = self._parse_response(response)

            logger.info(
                f"LLM suggestion for {agent_name}: {suggestion['order_quantity']} units "
                f"({suggestion['confidence']:.0%} confidence)"
            )

            return suggestion

        except Exception as e:
            logger.error(f"LLM suggestion generation failed: {e}", exc_info=True)
            logger.warning("Falling back to heuristic suggestion")
            return self._fallback_suggestion(agent_name, context)

    def _build_suggestion_prompt(
        self,
        agent_name: str,
        context: Dict[str, Any],
        request_data: Optional[Dict[str, Any]],
        kb_context: str = "",
    ) -> str:
        """Build prompt for suggestion generation."""

        # Get role-specific objectives
        objectives = self._get_agent_objectives(agent_name)

        # Format demand history
        demand_history_str = self._format_demand_history(context.get('recent_demand', []))

        # Build base prompt
        prompt = f"""You are an AI advisor for the {agent_name} in a supply chain simulation.

Your role: {objectives['description']}

Primary objectives:
{chr(10).join(f"- {obj}" for obj in objectives['goals'])}

Current Game State:
- Round: {context.get('current_round', 0)}
- Current Inventory: {context.get('current_inventory', 0)} units
- Current Backlog: {context.get('current_backlog', 0)} units
- Incoming Shipment: {context.get('incoming_shipment', 0)} units (arriving in {context.get('lead_time', 2)} rounds)
- Lead Time: {context.get('lead_time', 2)} rounds

Recent Demand (last 5 rounds):
{demand_history_str}

Demand Forecast:
- Next round predicted demand: {context.get('forecast_demand', 'N/A')}
- Forecast confidence: {context.get('forecast_confidence', 0):.0%}

Historical Performance:
- Average inventory: {context.get('avg_inventory', 0):.1f} units
- Average backlog: {context.get('avg_backlog', 0):.1f} units
- Service level: {context.get('service_level', 0):.1%}
- Total cost: ${context.get('total_cost', 0):.2f}

Strategic Context:
- Bullwhip effect detected: {context.get('bullwhip_detected', False)}
- Demand volatility: {context.get('demand_volatility', 'moderate')}

Based on this information, recommend an order quantity for the next round.

Respond in the following JSON format:
{{
    "order_quantity": <integer>,
    "confidence": <float between 0.0 and 1.0>,
    "rationale": "<1-2 sentence summary of recommendation>",
    "reasoning_steps": [
        "Step 1: <reasoning>",
        "Step 2: <reasoning>",
        "Step 3: <reasoning>"
    ],
    "risk_factors": [
        "<potential risk 1>",
        "<potential risk 2>"
    ],
    "alternative_strategies": [
        {{
            "strategy": "<alternative approach>",
            "order_quantity": <integer>,
            "pros": "<pros>",
            "cons": "<cons>"
        }}
    ]
}}

IMPORTANT:
- Order quantity must be a non-negative integer
- Consider lead time when calculating order quantity
- Balance inventory costs ($0.50/unit/round) vs. backlog costs ($1.00/unit/round)
- Aim for service level above 90%
- Explain your reasoning clearly
- Confidence should reflect uncertainty in demand forecasting
"""

        # Add knowledge base context
        if kb_context:
            prompt += f"\n\nRelevant Supply Chain Knowledge:\n{kb_context}\nUse the above knowledge to ground your recommendation in established theory.\n"

        # Add request-specific context
        if request_data:
            if request_data.get('priority'):
                prompt += f"\n\nUser Priority: {request_data['priority']}"
            if request_data.get('notes'):
                prompt += f"\nUser Notes: {request_data['notes']}"

        return prompt

    def _get_agent_objectives(self, agent_name: str) -> Dict[str, Any]:
        """Get role-specific objectives and description."""

        objectives_map = {
            "retailer": {
                "description": "You face customer demand directly and must balance customer service with inventory costs.",
                "goals": [
                    "Maintain high service level (minimize backlog)",
                    "Keep inventory lean to reduce holding costs",
                    "Anticipate demand trends early",
                    "Build customer loyalty through reliability",
                ]
            },
            "wholesaler": {
                "description": "You buffer demand variability between retailers and distributors.",
                "goals": [
                    "Smooth order patterns to reduce bullwhip effect",
                    "Maintain safety stock for demand spikes",
                    "Coordinate with both upstream and downstream partners",
                    "Balance responsiveness with cost efficiency",
                ]
            },
            "distributor": {
                "description": "You manage the middle tier of the supply chain, coordinating between manufacturers and wholesalers.",
                "goals": [
                    "Balance responsiveness with efficiency",
                    "Anticipate wholesaler order patterns",
                    "Maintain buffer inventory for variability",
                    "Optimize total supply chain flow",
                ]
            },
            "factory": {
                "description": "You produce goods with fixed lead time and capacity constraints.",
                "goals": [
                    "Stabilize production schedules",
                    "Minimize production cost variability",
                    "Meet distributor demand reliably",
                    "Optimize manufacturing efficiency",
                ]
            },
        }

        return objectives_map.get(
            agent_name.lower(),
            {
                "description": "Generic supply chain agent responsible for inventory management",
                "goals": [
                    "Minimize total cost (inventory + backlog)",
                    "Maintain adequate service level",
                    "Respond to demand changes efficiently",
                ],
            }
        )

    def _format_demand_history(self, demand_history: list) -> str:
        """Format demand history for prompt."""
        if not demand_history:
            return "  No history available"

        lines = []
        total_rounds = len(demand_history)

        for i, demand in enumerate(demand_history[-5:]):
            round_offset = total_rounds - len(demand_history[-5:]) + i
            lines.append(f"  Round {round_offset + 1}: {demand} units")

        return "\n".join(lines)

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a supply chain optimization expert. Use the provided knowledge base context to ground your recommendations in established supply chain theory and best practices."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=1000,
                response_format={"type": "json_object"},  # Force JSON output
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise

    async def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic Claude API."""
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
            )

            return response.content[0].text

        except Exception as e:
            logger.error(f"Anthropic API call failed: {e}")
            raise

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM response into structured format.

        Handles various response formats:
        - Pure JSON
        - JSON in markdown code blocks
        - Partial JSON with text
        """
        try:
            # Try to extract JSON from response
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find raw JSON
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    json_str = response

            # Parse JSON
            parsed = json.loads(json_str)

            # Validate required fields
            if not isinstance(parsed.get('order_quantity'), (int, float)):
                raise ValueError("order_quantity must be a number")

            order_qty = int(parsed['order_quantity'])
            if order_qty < 0:
                logger.warning(f"Negative order quantity {order_qty}, setting to 0")
                order_qty = 0

            confidence = float(parsed.get('confidence', 0.7))
            if not (0.0 <= confidence <= 1.0):
                logger.warning(f"Invalid confidence {confidence}, clamping to [0, 1]")
                confidence = max(0.0, min(1.0, confidence))

            rationale = parsed.get('rationale', '')
            if not isinstance(rationale, str) or not rationale:
                rationale = f"Order {order_qty} units based on current game state"

            # Build validated response
            validated = {
                "order_quantity": order_qty,
                "confidence": confidence,
                "rationale": rationale,
                "reasoning_steps": parsed.get('reasoning_steps', []),
                "risk_factors": parsed.get('risk_factors', []),
                "alternative_strategies": parsed.get('alternative_strategies', []),
            }

            return validated

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.error(f"Response: {response[:500]}...")

            # Fallback: try to extract order quantity from text
            order_match = re.search(r'order[:\s]+(\d+)', response, re.IGNORECASE)
            if order_match:
                order_qty = int(order_match.group(1))
                logger.info(f"Extracted order quantity {order_qty} from text")
            else:
                order_qty = 40  # Default fallback

            return {
                "order_quantity": order_qty,
                "confidence": 0.5,
                "rationale": "LLM response parsing failed - using fallback estimation",
                "reasoning_steps": ["Unable to parse structured reasoning from LLM response"],
                "risk_factors": ["High uncertainty due to parsing failure"],
                "alternative_strategies": [],
            }

    def _fallback_suggestion(
        self,
        agent_name: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate fallback suggestion using heuristic when LLM is unavailable.

        Uses a simple base-stock policy:
        order_quantity = target_stock - current_inventory + backlog
        """
        inventory = context.get('current_inventory', 0)
        backlog = context.get('current_backlog', 0)
        recent_demand = context.get('recent_demand', [])

        # Calculate target stock based on recent demand
        if recent_demand and len(recent_demand) >= 3:
            avg_demand = sum(recent_demand[-3:]) / 3
            target_stock = int(avg_demand * 2)  # 2 rounds of safety stock
        else:
            target_stock = 50  # Default

        # Base stock calculation
        order_quantity = max(0, target_stock - inventory + backlog)

        # Cap at 3x average demand to prevent extreme orders
        if recent_demand:
            avg_demand = sum(recent_demand[-5:]) / len(recent_demand[-5:])
            max_order = int(avg_demand * 3)
            if order_quantity > max_order:
                logger.warning(f"Capping order quantity {order_quantity} to {max_order}")
                order_quantity = max_order

        rationale = (
            f"Heuristic recommendation (LLM unavailable): Order {order_quantity} units "
            f"to reach target stock of {target_stock} units. Current inventory: {inventory}, "
            f"backlog: {backlog}."
        )

        return {
            "order_quantity": order_quantity,
            "confidence": 0.6,
            "rationale": rationale,
            "reasoning_steps": [
                f"Calculate target stock: {target_stock} units (2x average demand)",
                f"Current shortfall: {target_stock - inventory + backlog} units",
                f"Recommended order: {order_quantity} units",
            ],
            "risk_factors": [
                "Heuristic fallback used (LLM unavailable)",
                "May not account for complex demand patterns",
            ],
            "alternative_strategies": [],
        }

    async def generate_conversation_response(
        self,
        prompt: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Generate conversational AI response for multi-turn chat.
        Phase 7 Sprint 4 enhancement.

        Args:
            prompt: Full conversation prompt with history
            context: Game context snapshot

        Returns:
            Dict with content, confidence, reasoning, suggested_action
        """
        self._init_client()

        if not self.client:
            return self._fallback_conversation_response(context)

        try:
            # Retrieve RAG context based on conversation prompt
            from app.services.rag_context import get_rag_context
            kb_context = await get_rag_context(prompt[:200], top_k=3, max_tokens=1500)

            if self.provider == "openai":
                response = await self._call_openai_conversation(prompt, kb_context=kb_context)
            elif self.provider == "anthropic":
                response = await self._call_anthropic_conversation(prompt, kb_context=kb_context)
            else:
                return self._fallback_conversation_response(context)

            # Parse JSON response
            parsed = self._parse_conversation_response(response)
            return parsed

        except Exception as e:
            logger.error(f"Conversation generation failed: {e}", exc_info=True)
            return self._fallback_conversation_response(context)

    async def _call_openai_conversation(self, prompt: str, kb_context: str = "") -> str:
        """Call OpenAI for conversation response."""
        system_msg = "You are a helpful supply chain advisor."
        if kb_context:
            system_msg += f"\n\nUse this reference knowledge to inform your response:\n{kb_context}"
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500,
        )
        return response.choices[0].message.content

    async def _call_anthropic_conversation(self, prompt: str, kb_context: str = "") -> str:
        """Call Anthropic for conversation response."""
        full_prompt = prompt
        if kb_context:
            full_prompt = f"Reference Knowledge:\n{kb_context}\n\n{prompt}"
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=500,
            messages=[{"role": "user", "content": full_prompt}],
        )
        return response.content[0].text

    def _parse_conversation_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON conversation response from LLM."""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return {
                    "content": parsed.get("content", response),
                    "confidence": parsed.get("confidence", 0.75),
                    "reasoning": parsed.get("reasoning", []),
                    "suggested_action": parsed.get("suggested_action"),
                    "follow_up_questions": parsed.get("follow_up_questions", []),
                }
        except Exception as e:
            logger.warning(f"Failed to parse JSON response: {e}")

        # Fallback: treat entire response as content
        return {
            "content": response,
            "confidence": 0.7,
            "reasoning": [],
            "suggested_action": None,
            "follow_up_questions": [],
        }

    def _fallback_conversation_response(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate fallback conversation response without LLM."""
        inventory = context.get('current_inventory', 0)
        backlog = context.get('current_backlog', 0)

        # Generate simple conversational response
        if backlog > 0:
            content = f"You currently have {backlog} units in backlog. I recommend increasing your order to catch up with demand."
        elif inventory > 50:
            content = f"Your inventory is healthy at {inventory} units. You can maintain current ordering levels."
        else:
            content = f"Your inventory is at {inventory} units. Consider ordering more to build safety stock."

        return {
            "content": content,
            "confidence": 0.6,
            "reasoning": ["Analyzed current inventory and backlog levels", "Based response on standard inventory management rules"],
            "suggested_action": None,
            "follow_up_questions": [
                "What if demand increases?",
                "How much safety stock should I maintain?",
                "What are my options?"
            ],
        }


# Singleton instance
_llm_service_instance = None


def get_llm_service(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> LLMSuggestionService:
    """
    Get or create LLM service singleton.

    Args:
        provider: LLM provider (openai, anthropic). If None, uses default from config.
        model: Model name. If None, uses default from config.

    Returns:
        LLMSuggestionService instance
    """
    global _llm_service_instance

    # Get defaults from config if not provided
    if provider is None or model is None:
        try:
            from app.core.config import settings
            provider = provider or getattr(settings, 'LLM_PROVIDER', 'openai-compatible')
            model = model or getattr(settings, 'LLM_MODEL', 'qwen3-8b')
        except Exception:
            provider = provider or 'openai-compatible'
            model = model or 'qwen3-8b'

    # Create new instance if needed
    if _llm_service_instance is None:
        _llm_service_instance = LLMSuggestionService(provider=provider, model=model)

    return _llm_service_instance


# =============================================================================
# CROSS-AGENT OPTIMIZATION (PHASE 7 SPRINT 4 - FEATURE 5)
# =============================================================================

async def generate_global_optimization(
    game_state: Dict[str, Any],
    focus_nodes: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Generate global optimization recommendations considering multiple nodes.

    Phase 7 Sprint 4 - Feature 5: Cross-Agent Optimization

    Unlike single-node suggestions, this analyzes the entire supply chain
    and provides coordinated recommendations for multiple nodes simultaneously.

    Args:
        game_state: Complete game state with all nodes
        focus_nodes: Optional list of specific roles to focus on

    Returns:
        {
            "optimization_type": "coordination" | "rebalancing" | "stabilization",
            "recommendations": {
                "RETAILER": {"order": 45, "reasoning": "..."},
                "WHOLESALER": {"order": 52, "reasoning": "..."},
                ...
            },
            "expected_impact": {
                "cost_reduction": 25,
                "service_improvement": 0.15,
                "bullwhip_reduction": 0.30
            },
            "coordination_strategy": "...",
            "confidence": 0.75
        }
    """
    try:
        llm_service = get_llm_suggestion_service()
        llm_service._init_client()

        if not llm_service.client:
            # Fallback to heuristic
            return _fallback_global_optimization(game_state, focus_nodes)

        # Retrieve RAG context for multi-echelon optimization
        from app.services.rag_context import get_rag_context
        kb_context = await get_rag_context(
            "multi-echelon supply chain coordination bullwhip effect optimization inventory",
            top_k=3, max_tokens=2000,
        )

        # Build multi-node context
        context = _build_multi_node_context(game_state, focus_nodes)

        # Build knowledge section
        kb_section = ""
        if kb_context:
            kb_section = f"\n\nRELEVANT SUPPLY CHAIN KNOWLEDGE:\n{kb_context}\nUse this knowledge to improve your coordination recommendations.\n"

        # Build prompt for global optimization
        prompt = f"""You are a supply chain optimization advisor analyzing a multi-echelon supply chain simulation.

SUPPLY CHAIN STATE:
{json.dumps(context, indent=2)}
{kb_section}

TASK: Provide coordinated recommendations for multiple nodes to optimize overall supply chain performance.

Consider:
1. Inventory imbalances across nodes
2. Bullwhip effect amplification
3. Coordination opportunities
4. Trade-offs between individual and system-wide performance

IMPORTANT: Respond with valid JSON only (no markdown, no explanation outside JSON):
{{
    "optimization_type": "coordination" | "rebalancing" | "stabilization",
    "recommendations": {{
        "RETAILER": {{"order": <number>, "reasoning": "<brief explanation>"}},
        "WHOLESALER": {{"order": <number>, "reasoning": "<brief explanation>"}},
        "DISTRIBUTOR": {{"order": <number>, "reasoning": "<brief explanation>"}},
        "FACTORY": {{"order": <number>, "reasoning": "<brief explanation>"}}
    }},
    "expected_impact": {{
        "cost_reduction": <estimated percentage>,
        "service_improvement": <0-1 improvement>,
        "bullwhip_reduction": <0-1 reduction>
    }},
    "coordination_strategy": "<1-2 sentence strategy description>",
    "confidence": <0-1>
}}"""

        # Call LLM
        if llm_service.provider == "openai":
            response = await llm_service._call_openai_conversation(prompt)
        elif llm_service.provider == "anthropic":
            response = await llm_service._call_anthropic_conversation(prompt)
        else:
            return _fallback_global_optimization(game_state, focus_nodes)

        # Parse response
        parsed = _parse_global_optimization_response(response)
        return parsed

    except Exception as e:
        logger.error(f"Global optimization failed: {e}", exc_info=True)
        return _fallback_global_optimization(game_state, focus_nodes)


def _build_multi_node_context(
    game_state: Dict[str, Any],
    focus_nodes: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Build context containing all relevant nodes."""
    context = {
        "current_round": game_state.get("current_round", 0),
        "nodes": {}
    }

    # Extract node data
    scenario_users = game_state.get("scenario_users", [])

    for scenario_user in scenario_users:
        role = scenario_user.get("role", "UNKNOWN")

        # Filter if focus_nodes specified
        if focus_nodes and role not in focus_nodes:
            continue

        context["nodes"][role] = {
            "inventory": scenario_user.get("inventory_after", 0),
            "backlog": scenario_user.get("backlog_after", 0),
            "incoming": scenario_user.get("incoming_shipment", 0),
            "outgoing": scenario_user.get("outgoing_shipment", 0),
            "last_order": scenario_user.get("order_placed", 0),
            "total_cost": scenario_user.get("total_cost", 0),
            "service_level": scenario_user.get("service_level", 0.0)
        }

    return context


def _parse_global_optimization_response(response_text: str) -> Dict[str, Any]:
    """Parse LLM response for global optimization."""
    try:
        # Remove markdown code blocks if present
        text = response_text.strip()
        if text.startswith("```"):
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```$', '', text)

        # Parse JSON
        data = json.loads(text)

        # Validate structure
        required_keys = ["optimization_type", "recommendations", "expected_impact", "coordination_strategy", "confidence"]
        for key in required_keys:
            if key not in data:
                logger.warning(f"Missing key in optimization response: {key}")
                return _fallback_global_optimization({}, None)

        return data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse global optimization JSON: {e}")
        logger.debug(f"Response text: {response_text[:500]}")
        return _fallback_global_optimization({}, None)


def _fallback_global_optimization(
    game_state: Dict[str, Any],
    focus_nodes: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Heuristic-based global optimization fallback."""
    scenario_users = game_state.get("scenario_users", [])

    # Simple heuristic: stabilize orders across supply chain
    recommendations = {}

    # Calculate average order across nodes
    orders = [p.get("order_placed", 0) for p in scenario_users if p.get("order_placed", 0) > 0]
    avg_order = sum(orders) / len(orders) if orders else 50

    for scenario_user in scenario_users:
        role = scenario_user.get("role", "UNKNOWN")

        if focus_nodes and role not in focus_nodes:
            continue

        inventory = scenario_user.get("inventory_after", 0)
        backlog = scenario_user.get("backlog_after", 0)

        # Simple ordering logic
        if backlog > 20:
            recommended_order = int(avg_order * 1.2)
            reasoning = "Increase order to address backlog"
        elif inventory > 60:
            recommended_order = int(avg_order * 0.8)
            reasoning = "Reduce order due to excess inventory"
        else:
            recommended_order = int(avg_order)
            reasoning = "Maintain stable ordering"

        recommendations[role] = {
            "order": recommended_order,
            "reasoning": reasoning
        }

    return {
        "optimization_type": "stabilization",
        "recommendations": recommendations,
        "expected_impact": {
            "cost_reduction": 10,
            "service_improvement": 0.05,
            "bullwhip_reduction": 0.15
        },
        "coordination_strategy": "Stabilize orders across supply chain to reduce volatility",
        "confidence": 0.50,
        "note": "Generated using heuristic fallback (LLM unavailable)"
    }
