# Phase 7 Sprint 3 - LLM Integration for A2A Collaboration

**Date**: 2026-01-14
**Sprint**: Phase 7 Sprint 3 - Intelligent Agent Suggestions
**Duration**: 2-3 days
**Dependencies**: Phase 7 Sprint 2 Complete ✅

---

## Executive Summary

Phase 7 Sprint 3 enhances the A2A collaboration system with intelligent, LLM-powered agent suggestions. We'll replace the current heuristic-based suggestion generation with sophisticated LLM reasoning that considers game context, historical patterns, and strategic objectives.

**Goal**: Transform agent suggestions from simple inventory calculations into thoughtful, context-aware recommendations with explanations and confidence scoring.

---

## Objectives

### Primary Goals
1. **LLM-Powered Suggestions**: Replace heuristic `_generate_heuristic_suggestion()` with LLM-based analysis
2. **Context-Rich Prompts**: Build comprehensive context from game state, history, and trends
3. **Structured Output**: Parse LLM responses into structured `AgentSuggestion` objects
4. **Confidence Scoring**: Derive meaningful confidence levels from LLM reasoning
5. **What-If Analysis**: Implement async LLM-based scenario analysis

### Secondary Goals
6. **Multi-Model Support**: Support OpenAI GPT-4, Claude, and custom models
7. **Prompt Templates**: Create reusable prompt templates for different agent roles
8. **Caching**: Cache suggestions to reduce API costs
9. **Fallback Strategy**: Gracefully degrade to heuristics on LLM failure

---

## User Stories

### Story 1: Intelligent Agent Suggestions
**As a** player
**I want** agent suggestions that explain their reasoning
**So that** I can understand why a particular order quantity is recommended

**Acceptance Criteria:**
- ✅ Suggestions include detailed rationale (not just "Based on inventory...")
- ✅ Confidence level reflects LLM certainty about the recommendation
- ✅ Context includes historical trends, demand patterns, and risk factors
- ✅ Suggestions consider strategic objectives (minimize cost, reduce backlog, etc.)

### Story 2: What-If Analysis
**As a** player
**I want** to ask "what if" questions about different ordering strategies
**So that** I can explore alternatives before committing

**Acceptance Criteria:**
- ✅ What-if analysis runs asynchronously (doesn't block)
- ✅ Results include projected metrics (inventory, backlog, cost)
- ✅ LLM provides interpretation and recommendations
- ✅ Analysis completes within 5-10 seconds

### Story 3: Multi-Agent Coordination
**As a** player
**I want** suggestions from multiple agents with different perspectives
**So that** I can see consensus or disagreement across the supply chain

**Acceptance Criteria:**
- ✅ Can request suggestions from retailer, wholesaler, distributor, factory
- ✅ Each agent has role-specific context and objectives
- ✅ Suggestions show agreement/disagreement patterns
- ✅ UI highlights high-confidence consensus recommendations

---

## Technical Architecture

### Current State (Sprint 2)

```python
# backend/app/services/chat_service.py
async def request_suggestion(
    self,
    game_id: int,
    agent_name: str,
    request_data: Optional[AgentSuggestionRequest] = None,
) -> AgentSuggestion:
    # Get game state
    context = {
        "current_inventory": player_round.current_inventory if player_round else 0,
        "current_backlog": player_round.current_backlog if player_round else 0,
        "recent_demand": [],  # TODO
        "forecast_demand": 0,  # TODO
    }

    # Simple heuristic
    order_quantity = self._generate_heuristic_suggestion(context)
    confidence = 0.7  # Placeholder

    return AgentSuggestion(...)
```

### Target State (Sprint 3)

```python
# backend/app/services/chat_service.py
async def request_suggestion(
    self,
    game_id: int,
    agent_name: str,
    request_data: Optional[AgentSuggestionRequest] = None,
) -> AgentSuggestion:
    # 1. Build rich context
    context = await self._build_suggestion_context(game_id, agent_name)

    # 2. Call LLM for analysis
    llm_response = await self.llm_service.generate_suggestion(
        agent_name=agent_name,
        context=context,
        request_data=request_data,
    )

    # 3. Parse structured response
    suggestion = self._parse_llm_suggestion(llm_response)

    # 4. Store and return
    return await self._save_suggestion(game_id, agent_name, suggestion)
```

---

## Implementation Plan

### Day 1: LLM Service Foundation

#### Task 1.1: Create LLM Service (2-3 hours)
**File**: `backend/app/services/llm_suggestion_service.py`

```python
"""
LLM-powered suggestion generation service.
Phase 7 Sprint 3
"""

from typing import Dict, Any, Optional
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic
import logging

logger = logging.getLogger(__name__)


class LLMSuggestionService:
    """Service for generating LLM-powered agent suggestions."""

    def __init__(self, provider: str = "openai", model: str = "gpt-4"):
        self.provider = provider
        self.model = model

        if provider == "openai":
            self.client = AsyncOpenAI()
        elif provider == "anthropic":
            self.client = AsyncAnthropic()
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def generate_suggestion(
        self,
        agent_name: str,
        context: Dict[str, Any],
        request_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate order recommendation using LLM.

        Args:
            agent_name: Agent role (retailer, wholesaler, etc.)
            context: Game state context
            request_data: Optional additional request parameters

        Returns:
            Dict with order_quantity, confidence, rationale, reasoning_steps
        """
        # Build prompt
        prompt = self._build_suggestion_prompt(agent_name, context, request_data)

        # Call LLM
        if self.provider == "openai":
            response = await self._call_openai(prompt)
        elif self.provider == "anthropic":
            response = await self._call_anthropic(prompt)

        # Parse response
        suggestion = self._parse_response(response)

        logger.info(
            f"LLM suggestion for {agent_name}: {suggestion['order_quantity']} units "
            f"({suggestion['confidence']:.0%} confidence)"
        )

        return suggestion

    def _build_suggestion_prompt(
        self,
        agent_name: str,
        context: Dict[str, Any],
        request_data: Optional[Dict[str, Any]],
    ) -> str:
        """Build prompt for suggestion generation."""

        # Role-specific objectives
        objectives = self._get_agent_objectives(agent_name)

        prompt = f"""You are an AI advisor for the {agent_name} in a supply chain simulation (The Beer Game).

Your role: {objectives['description']}
Primary objectives:
{chr(10).join(f"- {obj}" for obj in objectives['goals'])}

Current Game State:
- Round: {context.get('current_round', 0)}
- Current Inventory: {context.get('current_inventory', 0)} units
- Current Backlog: {context.get('current_backlog', 0)} units
- Incoming Shipment: {context.get('incoming_shipment', 0)} units (arriving in {context.get('lead_time', 2)} rounds)
- Pending Orders: {context.get('pipeline_orders', [])}

Recent Demand (last 5 rounds):
{self._format_demand_history(context.get('recent_demand', []))}

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
- Upstream lead time: {context.get('lead_time', 2)} rounds

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
"""

        # Add request-specific context
        if request_data and request_data.get('priority'):
            prompt += f"\n\nUser Priority: {request_data['priority']}"

        return prompt

    def _get_agent_objectives(self, agent_name: str) -> Dict[str, Any]:
        """Get role-specific objectives."""

        objectives_map = {
            "retailer": {
                "description": "You face customer demand directly and must balance customer service with inventory costs.",
                "goals": [
                    "Maintain high service level (minimize backlog)",
                    "Keep inventory lean to reduce holding costs",
                    "Anticipate demand trends early",
                ]
            },
            "wholesaler": {
                "description": "You buffer demand variability between retailers and distributors.",
                "goals": [
                    "Smooth order patterns to reduce bullwhip effect",
                    "Maintain safety stock for demand spikes",
                    "Coordinate with both upstream and downstream",
                ]
            },
            "distributor": {
                "description": "You manage the middle tier of the supply chain, coordinating between manufacturers and wholesalers.",
                "goals": [
                    "Balance responsiveness with efficiency",
                    "Anticipate wholesaler order patterns",
                    "Maintain buffer inventory for variability",
                ]
            },
            "factory": {
                "description": "You produce goods with fixed lead time and capacity constraints.",
                "goals": [
                    "Stabilize production schedules",
                    "Minimize production cost variability",
                    "Meet distributor demand reliably",
                ]
            },
        }

        return objectives_map.get(
            agent_name.lower(),
            {
                "description": "Generic supply chain agent",
                "goals": ["Minimize total cost", "Maintain service level"],
            }
        )

    def _format_demand_history(self, demand_history: list) -> str:
        """Format demand history for prompt."""
        if not demand_history:
            return "  No history available"

        lines = []
        for i, demand in enumerate(demand_history[-5:], 1):
            lines.append(f"  Round -{len(demand_history) - i + 1}: {demand} units")

        return "\n".join(lines)

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a supply chain optimization expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000,
        )

        return response.choices[0].message.content

    async def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic Claude API."""
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        return response.content[0].text

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into structured format."""
        import json
        import re

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            json_str = json_match.group(0) if json_match else response

        try:
            parsed = json.loads(json_str)

            # Validate required fields
            assert isinstance(parsed.get('order_quantity'), int)
            assert isinstance(parsed.get('confidence'), (int, float))
            assert 0.0 <= parsed['confidence'] <= 1.0
            assert isinstance(parsed.get('rationale'), str)

            return parsed

        except (json.JSONDecodeError, AssertionError, KeyError) as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.error(f"Response: {response}")

            # Fallback: extract order quantity from text
            order_match = re.search(r'order[:\s]+(\d+)', response, re.IGNORECASE)
            order_qty = int(order_match.group(1)) if order_match else 40

            return {
                "order_quantity": order_qty,
                "confidence": 0.5,
                "rationale": "LLM response parsing failed - using fallback",
                "reasoning_steps": [],
                "risk_factors": [],
                "alternative_strategies": [],
            }


# Singleton instance
_llm_service = None

def get_llm_service(provider: str = "openai", model: str = "gpt-4") -> LLMSuggestionService:
    """Get or create LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMSuggestionService(provider=provider, model=model)
    return _llm_service
```

#### Task 1.2: Enhance Context Building (1-2 hours)
**File**: `backend/app/services/chat_service.py`

Add method to build comprehensive context:

```python
async def _build_suggestion_context(
    self,
    game_id: int,
    agent_name: str,
) -> Dict[str, Any]:
    """
    Build comprehensive context for LLM suggestion.

    Includes:
    - Current inventory, backlog, pipeline
    - Recent demand history (last 5-10 rounds)
    - Forecast demand
    - Historical performance metrics
    - Bullwhip detection
    """
    from app.models.supply_chain import PlayerRound
    from sqlalchemy import desc, func

    # Get game
    game_result = await self.db.execute(select(Game).filter(Game.id == game_id))
    game = game_result.scalars().first()

    # Get player
    player_result = await self.db.execute(
        select(Player).filter(
            Player.game_id == game_id,
            Player.role == agent_name.upper()
        )
    )
    player = player_result.scalars().first()

    if not player:
        raise ValueError(f"No player found for agent {agent_name} in game {game_id}")

    # Get recent player rounds (last 10)
    rounds_result = await self.db.execute(
        select(PlayerRound)
        .filter(PlayerRound.player_id == player.id)
        .order_by(desc(PlayerRound.round))
        .limit(10)
    )
    recent_rounds = list(rounds_result.scalars().all())

    # Current state (most recent round)
    current_round = recent_rounds[0] if recent_rounds else None

    # Calculate metrics
    recent_demand = [r.demand for r in reversed(recent_rounds)] if recent_rounds else []
    avg_inventory = sum(r.current_inventory for r in recent_rounds) / len(recent_rounds) if recent_rounds else 0
    avg_backlog = sum(r.current_backlog for r in recent_rounds) / len(recent_rounds) if recent_rounds else 0
    total_cost = sum(r.total_cost for r in recent_rounds) if recent_rounds else 0

    # Service level (% of demand met without backlog)
    fulfilled_rounds = sum(1 for r in recent_rounds if r.current_backlog == 0)
    service_level = fulfilled_rounds / len(recent_rounds) if recent_rounds else 0.0

    # Demand volatility
    if len(recent_demand) > 1:
        import statistics
        demand_volatility = statistics.stdev(recent_demand) / (statistics.mean(recent_demand) + 1)
        if demand_volatility > 0.5:
            volatility_label = "high"
        elif demand_volatility > 0.2:
            volatility_label = "moderate"
        else:
            volatility_label = "low"
    else:
        volatility_label = "unknown"

    # Bullwhip detection (compare order variance to demand variance)
    recent_orders = [r.order_placed for r in reversed(recent_rounds) if r.order_placed] if recent_rounds else []
    bullwhip_detected = False
    if len(recent_orders) > 2 and len(recent_demand) > 2:
        import statistics
        order_var = statistics.variance(recent_orders)
        demand_var = statistics.variance(recent_demand)
        bullwhip_detected = order_var > (demand_var * 2)  # Orders more volatile than demand

    # Forecast demand (simple moving average for now)
    forecast_demand = sum(recent_demand[-3:]) / 3 if len(recent_demand) >= 3 else (recent_demand[-1] if recent_demand else 0)
    forecast_confidence = 0.7  # TODO: Use actual GNN forecast

    # Pipeline orders (orders placed but not yet received)
    pipeline_orders = []
    if current_round:
        # Get pending orders from recent rounds
        for r in recent_rounds[:player.lead_time]:
            if r.order_placed:
                pipeline_orders.append({
                    "round": r.round,
                    "quantity": r.order_placed,
                    "eta_rounds": player.lead_time - (game.current_round - r.round)
                })

    context = {
        "current_round": game.current_round,
        "current_inventory": current_round.current_inventory if current_round else 0,
        "current_backlog": current_round.current_backlog if current_round else 0,
        "incoming_shipment": current_round.incoming_shipment if current_round else 0,
        "lead_time": player.lead_time,
        "pipeline_orders": pipeline_orders,
        "recent_demand": recent_demand,
        "forecast_demand": forecast_demand,
        "forecast_confidence": forecast_confidence,
        "avg_inventory": avg_inventory,
        "avg_backlog": avg_backlog,
        "service_level": service_level,
        "total_cost": total_cost,
        "bullwhip_detected": bullwhip_detected,
        "demand_volatility": volatility_label,
    }

    return context
```

#### Task 1.3: Integrate LLM Service (1 hour)
**File**: `backend/app/services/chat_service.py`

Update `request_suggestion` to use LLM:

```python
async def request_suggestion(
    self,
    game_id: int,
    agent_name: str,
    request_data: Optional[AgentSuggestionRequest] = None,
) -> AgentSuggestion:
    """Request an agent suggestion (LLM-powered)."""

    game_result = await self.db.execute(select(Game).filter(Game.id == game_id))
    game = game_result.scalars().first()
    if not game:
        raise ValueError(f"Game {game_id} not found")

    # Build comprehensive context
    try:
        context = await self._build_suggestion_context(game_id, agent_name)
    except Exception as e:
        logger.error(f"Failed to build context: {e}")
        # Fallback to minimal context
        context = {
            "current_round": game.current_round,
            "current_inventory": 0,
            "current_backlog": 0,
        }

    # Call LLM for suggestion
    try:
        from app.services.llm_suggestion_service import get_llm_service
        llm_service = get_llm_service()

        llm_response = await llm_service.generate_suggestion(
            agent_name=agent_name,
            context=context,
            request_data=request_data.dict() if request_data else None,
        )

        order_quantity = llm_response['order_quantity']
        confidence = llm_response['confidence']
        rationale = llm_response['rationale']

        # Store full reasoning in context
        context['llm_reasoning'] = {
            "reasoning_steps": llm_response.get('reasoning_steps', []),
            "risk_factors": llm_response.get('risk_factors', []),
            "alternatives": llm_response.get('alternative_strategies', []),
        }

    except Exception as e:
        logger.error(f"LLM suggestion failed: {e}, falling back to heuristic")
        # Fallback to heuristic
        order_quantity = self._generate_heuristic_suggestion(context)
        confidence = 0.6
        rationale = f"Heuristic recommendation (LLM unavailable): Based on current inventory ({context.get('current_inventory', 0)}) and backlog ({context.get('current_backlog', 0)})."

    # Create suggestion
    suggestion = AgentSuggestion(
        game_id=game_id,
        round=game.current_round,
        agent_name=agent_name,
        order_quantity=order_quantity,
        confidence=confidence,
        rationale=rationale,
        context=context,
    )

    self.db.add(suggestion)
    await self.db.commit()
    await self.db.refresh(suggestion)

    logger.info(
        f"Created LLM suggestion {suggestion.id} from {agent_name} in game {game_id}: "
        f"{order_quantity} units ({confidence:.0%} confidence)"
    )

    return suggestion
```

---

### Day 2: What-If Analysis & Testing

#### Task 2.1: What-If Analysis Engine (2-3 hours)
**File**: `backend/app/services/what_if_service.py`

```python
"""
What-If Analysis Service
Phase 7 Sprint 3
"""

import asyncio
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.chat import WhatIfAnalysis
from app.models.game import Game
from app.services.llm_suggestion_service import get_llm_service
import logging

logger = logging.getLogger(__name__)


class WhatIfAnalysisService:
    """Service for running what-if scenario analysis."""

    def __init__(self, db: Session):
        self.db = db

    async def process_analysis(self, analysis_id: int):
        """
        Process a what-if analysis asynchronously.

        This method:
        1. Loads the analysis request
        2. Runs simulation with scenario parameters
        3. Calls LLM for interpretation
        4. Updates analysis with results
        """
        # Get analysis
        result = await self.db.execute(
            select(WhatIfAnalysis).filter(WhatIfAnalysis.id == analysis_id)
        )
        analysis = result.scalars().first()

        if not analysis:
            logger.error(f"Analysis {analysis_id} not found")
            return

        try:
            # Run simulation
            sim_result = await self._simulate_scenario(
                game_id=analysis.game_id,
                round=analysis.round,
                scenario=analysis.scenario,
            )

            # Get LLM interpretation
            llm_analysis = await self._analyze_with_llm(
                question=analysis.question,
                scenario=analysis.scenario,
                result=sim_result,
            )

            # Update analysis
            analysis.result = sim_result
            analysis.agent_analysis = llm_analysis
            analysis.completed = True
            analysis.completed_at = datetime.utcnow()

            await self.db.commit()
            await self.db.refresh(analysis)

            logger.info(f"Completed what-if analysis {analysis_id}")

            # Broadcast completion via WebSocket
            from app.api.endpoints.websocket import manager
            await manager.broadcast_to_game(
                analysis.game_id,
                {
                    "type": "chat:analysis_complete",
                    "data": {
                        "id": analysis.id,
                        "completed": True,
                        "result": sim_result,
                        "agent_analysis": llm_analysis,
                        "completed_at": analysis.completed_at.isoformat(),
                    }
                }
            )

        except Exception as e:
            logger.error(f"Failed to process analysis {analysis_id}: {e}")
            analysis.completed = True
            analysis.agent_analysis = f"Analysis failed: {str(e)}"
            await self.db.commit()

    async def _simulate_scenario(
        self,
        game_id: int,
        round: int,
        scenario: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Simulate scenario and calculate projected metrics.

        For now, this uses a simplified projection.
        In future, integrate with SimPy simulation engine.
        """
        # Get game state
        from app.models.player import Player
        from app.models.supply_chain import PlayerRound

        game_result = await self.db.execute(select(Game).filter(Game.id == game_id))
        game = game_result.scalars().first()

        # Get current player state
        player_result = await self.db.execute(
            select(Player).filter(Player.game_id == game_id).limit(1)
        )
        player = player_result.scalars().first()

        if not player:
            raise ValueError(f"No player found for game {game_id}")

        # Get latest round
        round_result = await self.db.execute(
            select(PlayerRound)
            .filter(PlayerRound.player_id == player.id)
            .order_by(PlayerRound.round.desc())
            .limit(1)
        )
        current_round = round_result.scalars().first()

        if not current_round:
            raise ValueError(f"No rounds found for player {player.id}")

        # Extract scenario parameters
        order_quantity = scenario.get('order_quantity', 0)
        current_order = scenario.get('current_order', 0)

        # Simple projection (replace with full simulation later)
        inventory = current_round.current_inventory
        backlog = current_round.current_backlog

        # Assume demand stays constant
        projected_demand = current_round.demand

        # Calculate next round state
        incoming = order_quantity  # Simplified: ignore lead time
        fulfilled = min(inventory + incoming, backlog + projected_demand)
        new_inventory = max(0, inventory + incoming - fulfilled)
        new_backlog = max(0, backlog + projected_demand - fulfilled)

        # Calculate costs
        inventory_cost = new_inventory * 0.50
        backlog_cost = new_backlog * 1.00
        total_cost = inventory_cost + backlog_cost

        # Cost difference
        baseline_cost = current_round.total_cost if current_round else 0
        cost_difference = total_cost - baseline_cost

        # Service level
        service_level = fulfilled / (backlog + projected_demand) if (backlog + projected_demand) > 0 else 1.0

        result = {
            "projected_inventory": new_inventory,
            "projected_backlog": new_backlog,
            "projected_cost": total_cost,
            "cost_difference": cost_difference,
            "service_level": service_level,
            "order_quantity": order_quantity,
            "current_order": current_order,
            "demand_assumption": projected_demand,
        }

        return result

    async def _analyze_with_llm(
        self,
        question: str,
        scenario: Dict[str, Any],
        result: Dict[str, Any],
    ) -> str:
        """Get LLM interpretation of simulation results."""

        llm_service = get_llm_service()

        prompt = f"""You are a supply chain advisor analyzing a "what-if" scenario.

User Question: {question}

Scenario Parameters:
- Order Quantity: {scenario.get('order_quantity', 'N/A')} units
- Baseline Order: {scenario.get('current_order', 'N/A')} units

Projected Results:
- Projected Inventory: {result['projected_inventory']} units
- Projected Backlog: {result['projected_backlog']} units
- Projected Cost: ${result['projected_cost']:.2f}
- Cost Difference: ${result['cost_difference']:+.2f} (vs. baseline)
- Service Level: {result['service_level']:.1%}

Provide a 2-3 sentence analysis explaining:
1. What the results mean
2. Whether this strategy is recommended
3. What risks or benefits to consider

Be concise, actionable, and clear.
"""

        if llm_service.provider == "openai":
            response = await llm_service._call_openai(prompt)
        else:
            response = await llm_service._call_anthropic(prompt)

        return response.strip()


def get_what_if_service(db: Session) -> WhatIfAnalysisService:
    """Get what-if analysis service."""
    return WhatIfAnalysisService(db)
```

#### Task 2.2: Update Chat Endpoint (30 minutes)
**File**: `backend/app/api/endpoints/chat.py`

Update what-if endpoint to trigger async processing:

```python
@router.post(
    "/games/{game_id}/chat/what-if",
    response_model=WhatIfAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_what_if_analysis(
    game_id: int,
    analysis_data: WhatIfAnalysisRequest,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Run what-if analysis (async)."""
    try:
        analysis = await chat_service.create_what_if_analysis(
            game_id=game_id,
            analysis_data=analysis_data,
        )

        # Trigger async processing
        from app.services.what_if_service import get_what_if_service
        what_if_service = get_what_if_service(chat_service.db)

        # Run in background
        import asyncio
        asyncio.create_task(what_if_service.process_analysis(analysis.id))

        return WhatIfAnalysisResponse.from_orm(analysis)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating what-if analysis in game {game_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create analysis: {str(e)}",
        )
```

#### Task 2.3: Testing (2-3 hours)

**Test Script**: `backend/scripts/test_llm_suggestions.py`

```python
"""
Test LLM-powered suggestions.
Phase 7 Sprint 3
"""

import asyncio
import sys
sys.path.append('/app')

from app.services.llm_suggestion_service import get_llm_service
from app.db.session import get_db


async def test_suggestion_generation():
    """Test basic suggestion generation."""

    llm_service = get_llm_service(provider="openai", model="gpt-4o-mini")

    # Mock context
    context = {
        "current_round": 5,
        "current_inventory": 12,
        "current_backlog": 5,
        "incoming_shipment": 20,
        "lead_time": 2,
        "pipeline_orders": [
            {"round": 4, "quantity": 20, "eta_rounds": 1},
        ],
        "recent_demand": [30, 35, 38, 42, 40],
        "forecast_demand": 44,
        "forecast_confidence": 0.75,
        "avg_inventory": 15.0,
        "avg_backlog": 3.5,
        "service_level": 0.85,
        "total_cost": 125.50,
        "bullwhip_detected": False,
        "demand_volatility": "moderate",
    }

    print("Testing LLM suggestion generation...")
    print(f"Context: inventory={context['current_inventory']}, backlog={context['current_backlog']}")

    result = await llm_service.generate_suggestion(
        agent_name="wholesaler",
        context=context,
        request_data=None,
    )

    print(f"\n=== LLM Suggestion ===")
    print(f"Order Quantity: {result['order_quantity']} units")
    print(f"Confidence: {result['confidence']:.1%}")
    print(f"Rationale: {result['rationale']}")
    print(f"\nReasoning Steps:")
    for i, step in enumerate(result.get('reasoning_steps', []), 1):
        print(f"  {i}. {step}")

    if result.get('risk_factors'):
        print(f"\nRisk Factors:")
        for risk in result['risk_factors']:
            print(f"  - {risk}")

    if result.get('alternative_strategies'):
        print(f"\nAlternative Strategies:")
        for alt in result['alternative_strategies']:
            print(f"  - {alt['strategy']}: {alt['order_quantity']} units")
            print(f"    Pros: {alt['pros']}")
            print(f"    Cons: {alt['cons']}")


if __name__ == "__main__":
    asyncio.run(test_suggestion_generation())
```

---

### Day 3: Polish & Documentation

#### Task 3.1: Configuration (1 hour)
**File**: `backend/app/core/config.py`

Add LLM configuration:

```python
# LLM Configuration
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")  # openai, anthropic
LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")  # gpt-4, gpt-4o-mini, claude-3-sonnet
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1000"))
LLM_CACHE_TTL: int = int(os.getenv("LLM_CACHE_TTL", "300"))  # 5 minutes
```

#### Task 3.2: Caching (1-2 hours)
Implement Redis caching for suggestions to reduce API costs:

```python
# backend/app/services/llm_suggestion_service.py

import hashlib
import json
from redis import asyncio as aioredis

class LLMSuggestionService:
    def __init__(self, ...):
        # ...
        self.redis = aioredis.from_url(settings.REDIS_URL)
        self.cache_ttl = settings.LLM_CACHE_TTL

    async def generate_suggestion(self, agent_name, context, request_data):
        # Generate cache key
        cache_key = self._get_cache_key(agent_name, context)

        # Check cache
        cached = await self.redis.get(cache_key)
        if cached:
            logger.info(f"Cache hit for {agent_name} suggestion")
            return json.loads(cached)

        # Generate suggestion
        suggestion = await self._generate_suggestion_uncached(...)

        # Cache result
        await self.redis.setex(
            cache_key,
            self.cache_ttl,
            json.dumps(suggestion),
        )

        return suggestion

    def _get_cache_key(self, agent_name, context):
        """Generate cache key from context."""
        # Use only relevant fields for caching
        cache_context = {
            "inventory": context.get("current_inventory"),
            "backlog": context.get("current_backlog"),
            "recent_demand": context.get("recent_demand", [])[-3:],
        }

        context_str = json.dumps(cache_context, sort_keys=True)
        hash_str = hashlib.md5(context_str.encode()).hexdigest()

        return f"llm_suggestion:{agent_name}:{hash_str}"
```

#### Task 3.3: Documentation (2-3 hours)

Update [CHAT_API_DOCUMENTATION.md](backend/CHAT_API_DOCUMENTATION.md) with LLM details:
- Add section on LLM-powered suggestions
- Document confidence scoring interpretation
- Add examples of reasoning steps
- Document what-if analysis workflow

Create **LLM_INTEGRATION_GUIDE.md**:
- How to configure different LLM providers
- Cost optimization strategies
- Prompt engineering guidelines
- Troubleshooting LLM failures

---

## Testing Strategy

### Unit Tests
- ✅ LLM service prompt generation
- ✅ Response parsing with various formats
- ✅ Fallback to heuristic on failure
- ✅ Context building with missing data
- ✅ What-if simulation calculations

### Integration Tests
- ✅ Full suggestion generation flow
- ✅ What-if analysis async processing
- ✅ WebSocket event broadcasting
- ✅ Cache hit/miss scenarios

### Manual Testing
- ✅ Request suggestions from each agent role
- ✅ Compare LLM vs. heuristic suggestions
- ✅ Run what-if analysis scenarios
- ✅ Test with different game states

---

## Success Metrics

### Functional
- ✅ LLM suggestions complete in <3 seconds
- ✅ What-if analysis completes in <10 seconds
- ✅ Confidence scores correlate with actual performance
- ✅ 90%+ of suggestions are actionable (not errors)

### Quality
- ✅ Rationale explains reasoning clearly
- ✅ Order quantities are reasonable (not extreme)
- ✅ Risk factors are relevant
- ✅ Alternative strategies provide value

### Cost
- ✅ Average API cost per suggestion <$0.01
- ✅ Caching reduces duplicate calls by 50%+
- ✅ Fallback to heuristic prevents API spending spikes

---

## Risks & Mitigation

### Risk 1: LLM API Failures
**Impact**: High
**Likelihood**: Medium
**Mitigation**: Robust fallback to heuristic suggestions, retry logic, error handling

### Risk 2: Slow LLM Response Times
**Impact**: Medium
**Likelihood**: Medium
**Mitigation**: Use faster models (gpt-4o-mini), implement timeout, show loading state

### Risk 3: High API Costs
**Impact**: Medium
**Likelihood**: High
**Mitigation**: Caching, rate limiting, use cheaper models for non-critical requests

### Risk 4: Poor Quality Suggestions
**Impact**: High
**Likelihood**: Low
**Mitigation**: Prompt engineering, validation, human review of initial suggestions

---

## Environment Variables

Add to `.env`:

```bash
# LLM Configuration
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI specific
OPENAI_PROJECT=proj_...
OPENAI_ORGANIZATION=org-...

# Performance
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=1000
LLM_CACHE_TTL=300
LLM_TIMEOUT=10

# Redis for caching
REDIS_URL=redis://localhost:6379/0
```

---

## Deliverables

### Code
- ✅ `llm_suggestion_service.py` - LLM service (400+ lines)
- ✅ `what_if_service.py` - What-if analysis engine (300+ lines)
- ✅ Enhanced `chat_service.py` - Context building (200+ lines)
- ✅ Updated `chat.py` - Async what-if processing

### Tests
- ✅ `test_llm_suggestions.py` - LLM service tests
- ✅ `test_what_if_service.py` - What-if engine tests
- ✅ Integration tests for full flow

### Documentation
- ✅ Updated `CHAT_API_DOCUMENTATION.md`
- ✅ New `LLM_INTEGRATION_GUIDE.md`
- ✅ Sprint 3 completion summary

---

## Next Sprint Preview

### Phase 7 Sprint 4: Advanced A2A Features (Optional)
- Multi-agent consensus building
- Agent debate/negotiation
- Historical suggestion performance tracking
- Agent learning from outcomes
- Voice input for questions
- Mobile push notifications

---

**Status**: 📋 Ready to Start
**Estimated Effort**: 2-3 days (16-24 hours)
**Priority**: High
**Dependencies**: Phase 7 Sprint 2 Complete ✅

---

*Let's make the agents truly intelligent!* 🤖🧠✨
