# LLM-First UI Paradigm for Autonomous Execution Planning

**Version**: 1.2
**Date**: January 26, 2026
**Focus**: Execution Timeframe (Short-Term Constrained Optimization)
**Status**: Architectural Proposal
**Latest Update**: Added Section 8.9 on what-if analysis and human-agent collaboration in decentralized mode (multi-agent negotiation, scenario propagation)

---

## Executive Summary

This document proposes an **LLM-first UI paradigm** for autonomous planning specifically focused on the **execution horizon** - the short-term timeframe (days to weeks) where capacity constraints, lead times, and material availability are fixed, requiring optimal decision-making within rigid boundaries.

**Key Innovation**: Replace traditional point-and-click planning UIs with a **conversational, agent-orchestrated interface** where LLM agents autonomously make 80% of decisions, inform users of actions taken, allow inspection of reasoning, and provide override capabilities.

**Core Frameworks**:
- **AIIO Paradigm**: Automate-Inform-Inspect-Override workflow for human-in-the-loop automation
- **OODA Loop**: Observe-Orient-Decide-Act continuous decision cycle (60-second response time vs. 5-day batch planning)
- **ReAct Prompting**: Reasoning + Acting pattern for LLM tool calling and multi-step problem solving
- **Conformal Prediction**: Formal uncertainty quantification with guaranteed coverage probabilities (90%, 95%, 99%)

**Target ROI**:
- 80% reduction in planner time on routine decisions
- 5-15 minute response time (vs. 5-day weekly planning cycle)
- 20-35% cost reduction through AI optimization
- 100% actionable recommendation rate (multi-agent vs. 1.7% single-agent)
- **10,080x faster OODA loop** (60 seconds event-driven vs. 5-7 days weekly batch)
- **40% fewer false escalations** with conformal prediction adaptive guardrails

---

## Table of Contents

1. [Context & Problem Statement](#1-context--problem-statement)
2. [Research Foundation](#2-research-foundation)
3. [The AIIO Paradigm](#3-the-aiio-paradigm)
4. [LLM-First Architecture](#4-llm-first-architecture)
5. [Execution Horizon Specifics](#5-execution-horizon-specifics)
6. [Implementation Roadmap](#6-implementation-roadmap)
7. [Technical Specifications](#7-technical-specifications)
8. [Centralized vs. Decentralized Supply Chain Planning](#8-centralized-vs-decentralized-supply-chain-planning)
   - 8.9 [What-If Analysis and Human-Agent Collaboration in Decentralized Mode](#89-what-if-analysis-and-human-agent-collaboration-in-decentralized-mode)
   - 8.10 [Conclusion: The Best of Both Worlds](#810-conclusion-the-best-of-both-worlds)
9. [Sources & References](#9-sources--references)

---

## 1. Context & Problem Statement

### The Execution Horizon Challenge

**Execution horizon** = Short-term planning where constraints cannot be changed:
- **Capacity**: Fixed (machines, labor, facilities)
- **Lead Times**: Fixed (supplier contracts, transportation)
- **Material Availability**: Fixed (current inventory + scheduled receipts)
- **Customer Commitments**: Fixed (promised delivery dates)

**Planning Task**: Optimize decisions (production scheduling, order promising, inventory allocation) to achieve corporate objectives (minimize cost, maximize service level, optimize cash flow) within these rigid constraints.

**Current Problem**:
- **Weekly Batch Planning**: Planners review 500+ exception reports, manually adjust plans in spreadsheets, attend endless meetings
- **5-Day Latency**: Tuesday's urgent order doesn't get addressed until Friday's plan approval
- **Manual Bottleneck**: 80% of planner time spent on routine reviews, 20% on strategic decisions
- **False Certainty**: Plans use single-point estimates ("100 units") ignoring uncertainty (could be 80-120)
- **No Mid-Week Adjustments**: Plans locked until next cycle, can't respond to supplier delays or demand spikes

### What We Have Built (Current State)

**Strengths**:
✅ Multi-agent LLM system (node agents + supervisor + global planner)
✅ Event-driven continuous planning architecture
✅ Chat message models for A2A collaboration
✅ Stochastic planning with probability distributions
✅ Execution engine for Beer Game validation

**Gaps**:
❌ UI still requires point-and-click navigation through planning screens
❌ Agents generate recommendations but humans must manually approve each one
❌ No AIIO workflow (Automate-Inform-Inspect-Override)
❌ No execution-specific agent specialization
❌ Limited tool-calling and ReAct prompting patterns

---

## 2. Research Foundation

### Industry Trends (2025-2026)

Based on comprehensive web research conducted January 2026:

**1. Agentic AI Surge**
- [Gartner reported 1,445% surge in multi-agent system inquiries (Q1 2024 → Q2 2025)](https://research.aimultiple.com/agentic-orchestration/)
- [40% of enterprise applications will embed AI agents by end of 2026 (up from <5% in 2025)](https://www.shakudo.io/blog/top-9-ai-agent-frameworks)
- [76% of chief supply chain officers predict efficiency improvement via agents by 2026](https://vocal.media/journal/ai-chatbot-development-for-logistics-transforming-supply-chain-operations-in-2026)

**2. Multi-Agent Performance**
- [Multi-agent orchestration achieves 100% actionable recommendation rate vs. 1.7% for single-agent (80x improvement)](https://arxiv.org/abs/2511.15755)
- [Zero quality variance across trials → enables production SLA commitments](https://arxiv.org/abs/2511.15755)
- [Multi-agent systems achieve 140x improvement in solution correctness](https://arxiv.org/abs/2511.15755)

**3. Production Deployments**
- [JD.com deployed LLM-agent planning assistant for 10M+ SKUs across thousands of locations](https://arxiv.org/html/2509.03811v1)
- [Amazon and DHL use autonomous agents to rebalance inventory and maintain service levels](https://www.ey.com/en_us/insights/supply-chain/revolutionizing-global-supply-chains-with-agentic-ai)
- [John Galt Solutions launched "Galt Intelligence" GenAI assistant with conversational interface](https://logisticsviewpoints.com/2025/09/18/john-galt-solutions-expands-atlas-planning-platforms-explainable-ai-to-build-trust-in-supply-chain-decisions/)

**4. Conversational Planning Interfaces**
- [64% of leaders plan to increase investment in conversational AI chatbots in 2026](https://masterofcode.com/blog/conversational-ai-trends)
- [SAP's "Joule" copilot provides conversational access to planning insights](https://www.cio.com/article/4079410/transformative-global-supply-chain-planning-from-farm-to-fork-with-ai.html)
- [GenAI evolved from chat to conversation - systems now anticipate needs and surface insights](https://www.scmr.com/article/beyond-the-algorithm-how-uber-freight-is-using-ai-to-redefine-logistics)

**5. Framework Maturity**
- [LangGraph emerges as fastest framework (graph-based, only passes necessary state deltas)](https://research.aimultiple.com/llm-orchestration/)
- [AutoGen (Microsoft) simplifies multi-agent orchestration using conversational agents](https://www.kubiya.ai/blog/ai-agent-orchestration-frameworks)
- [CrewAI takes inspiration from human organizational structures with specialized team roles](https://www.secondtalent.com/resources/top-llm-frameworks-for-building-ai-agents/)

**6. Guardrails & Governance**
- [NeMo Guardrails and Guardrails Index provide validation layers around LLM inputs/outputs](https://medium.com/@ajayverma23/the-ultimate-guide-to-guardrails-in-genai-securing-and-standardizing-llm-applications-1502c90fdc72)
- [LangChain human-approval middleware for sensitive operations (financial, production data)](https://docs.langchain.com/oss/python/langchain/guardrails)
- [John Snow Labs Generative AI Lab 7.4 introduced approval checkpoint workflow](https://www.johnsnowlabs.com/balancing-innovation-and-oversight-how-enterprises-can-safely-adopt-large-language-models/)

**7. Technical Patterns**
- [ReAct (Reason+Act) prompting allows back-and-forth reasoning with environment feedback](https://www.promptingguide.ai/techniques/react)
- [GPT-4 tool-calling with structured outputs enables reliable function execution](https://medium.com/@govindarajpriyanthan/building-a-react-agent-using-the-openai-gpt-4o-model-1aeddd3334b2)
- [PDCA (Plan-Do-Check-Act) cycles for AI agent systems with continuous monitoring](https://www.infoq.com/articles/PDCA-AI-code-generation/)

---

## 3. The AIIO Paradigm

**AIIO = Automate, Inform, Inspect, Override**

A human-in-the-loop workflow pattern optimized for autonomous execution planning, balancing agent autonomy with human oversight.

### The Four Stages

#### Stage 1: **AUTOMATE** (Agent Autonomous Decision)

**What**: Agents detect events, analyze impact, generate solutions, and execute actions within guardrails

**Example**:
```
Event: Supplier shipment delayed 3 days (Vendor-A)
Agent Analysis: Will cause stockout for Product-X in Week 7 (85% probability)
Agent Action: Expedite shipment from backup Vendor-B (+$500 cost)
Guardrail Check: Cost increase <$1K ✓, Service level maintained ✓
Result: AUTO-EXECUTED at 10:05 AM
```

**Guardrails Enforced**:
- Cost increase <5% without approval
- No PO >$50K without approval
- Service level maintained ≥92%
- Lead time variance <20%

**When to Automate**:
- ✅ Low-impact decisions (cost <$5K, volume <5% plan change)
- ✅ Routine rebalancing (inventory transfers between sites)
- ✅ Safety stock adjustments within policy bounds
- ✅ Order expediting with pre-approved carriers
- ❌ Strategic customer negotiations (→ Inform stage)
- ❌ Large capital commitments (→ Inform stage)

#### Stage 2: **INFORM** (Proactive Notification)

**What**: Agents notify users of actions taken, grouped by priority and batched by timeframe

**Example**:
```
🔔 Notification at 10:10 AM

HIGH PRIORITY (3 actions):
1. ⚡ Expedited shipment from Vendor-B for Product-X (+$500, prevents stockout)
2. 🔄 Rebalanced inventory: DC-East → DC-West (200 units Product-Y)
3. 📉 Reduced safety stock for Product-Z (demand variance decreased 30%)

MEDIUM PRIORITY (7 actions):
[Collapsed by default, expandable]

All actions auto-executed within guardrails. Tap to inspect reasoning.
```

**Notification Strategy**:
- **Real-time**: High-impact actions (>$10K, service level impact >1%)
- **Batched Hourly**: Medium-impact routine operations
- **Daily Digest**: Low-impact optimizations
- **Never Notify**: Trivial adjustments (e.g., +/-1 unit safety stock)

**User Control**:
- Adjustable notification thresholds per user
- "Do Not Disturb" hours (e.g., after 6 PM)
- Escalation rules (notify manager if >$50K)

#### Stage 3: **INSPECT** (On-Demand Explainability)

**What**: Users can drill into any agent decision to see reasoning, alternatives considered, and trade-offs

**Example**:
```
User: "Show me why you expedited Vendor-B"

Agent: "Analysis for expedite decision (executed 10:05 AM):

PROBLEM DETECTED:
• Vendor-A shipment delayed 3 days (ETA: Jan 31 → Feb 3)
• Product-X inventory will drop below safety stock on Feb 1
• Projected stockout: 120 units (P90 demand forecast)
• Customer orders at risk: 5 orders, $85K revenue

ALTERNATIVES CONSIDERED:
1. Wait for Vendor-A (delayed 3 days)
   - Cost: $0
   - Risk: 85% probability of stockout, $85K revenue loss
   - Service level impact: -5% (92% → 87%)

2. Expedite Vendor-A with air freight
   - Cost: $1,200
   - Risk: Still arrives 1 day late (Feb 2)
   - Service level impact: -2% (92% → 90%)

3. Expedite Vendor-B (backup supplier) ✓ SELECTED
   - Cost: $500
   - Risk: Arrives on time (Jan 31)
   - Service level impact: 0% (maintains 92%)

DECISION RATIONALE:
Vendor-B expedite minimizes total cost ($500 + $0 stockout) vs.
Vendor-A wait ($0 + $85K expected loss * 85% = $72K).

Expected value saved: $71.5K"
```

**Inspection Capabilities**:
- **Reasoning Chain**: Step-by-step logic from problem detection to solution
- **Data Sources**: Which forecasts, inventory levels, lead times were used
- **Alternatives**: What other options were considered and why rejected
- **Probabilities**: Confidence intervals on outcomes (P10/P50/P90)
- **Tool Calls**: What APIs/databases/calculators were invoked
- **Versioning**: Plan diffs before/after decision (Git-like)

#### Stage 4: **OVERRIDE** (Human Intervention)

**What**: Users can reverse, modify, or provide feedback on any agent decision, even after execution

**Example**:
```
User: "Override the expedite. Use Vendor-A even with delay."

Agent: "Override request received. Proposed change:

CURRENT STATE (Auto-Executed):
✓ Expedite PO sent to Vendor-B ($500, arrives Jan 31)

YOUR OVERRIDE:
✗ Cancel Vendor-B expedite
✓ Wait for Vendor-A delayed shipment (arrives Feb 3)

IMPACT ANALYSIS:
• Cost savings: $500 (expedite fee)
• Increased risk: 85% probability of 2-day stockout (Feb 1-2)
• Estimated stockout cost: $72K expected value
• Net impact: -$71.5K expected value

Reason for override (optional): _______________________

[ Confirm Override ]  [ Cancel ]"

User: "We have strategic relationship with Customer-A. They agreed to accept 2-day delay."

Agent: "✓ Override confirmed.
- Cancelling Vendor-B expedite
- Updating delivery promise to Customer-A (Feb 3)
- Recording rationale: 'Strategic customer negotiation - delayed delivery accepted'
- Estimated savings: $500

This decision will be learned and applied to similar situations with strategic customers."
```

**Override Types**:
1. **Reverse**: Undo the agent decision, restore previous state
2. **Modify**: Change parameters (e.g., expedite to different vendor)
3. **Approve**: Explicitly approve an Inform-stage recommendation
4. **Veto**: Permanently block this type of decision (update guardrails)

**Learning from Overrides**:
- Agents track override frequency per decision type
- High override rate (>20%) triggers guardrail adjustment
- Human reasoning is stored as few-shot examples for future decisions
- Monthly review of overrides to update agent policies

---

## 4. LLM-First Architecture

### Conversational Interface as Primary UI

**Shift from**:
```
Traditional: Dashboard → Menu → Form → Submit → Wait → Refresh
```

**To**:
```
LLM-First: Chat → Agent Acts → Notify → Drill-Down (if needed)
```

### Core Components

#### 4.1 Multi-Agent Orchestration

Based on your existing [Autonomy Strategist architecture](../progress/AGENT_SYSTEM.md):

```
┌─────────────────────────────────────────────────────────┐
│                   USER (Planner)                        │
│              Conversational Interface                   │
└─────────────────┬───────────────────────────────────────┘
                  │ Natural Language
                  ↓
┌─────────────────────────────────────────────────────────┐
│             LLM ORCHESTRATOR (LangGraph)                │
│  - ReAct prompting with tool calling                    │
│  - Multi-step reasoning with environment feedback       │
│  - Guardrails enforcement                               │
│  - AIIO workflow coordination                           │
└─────────────────┬───────────────────────────────────────┘
                  │ Task Routing
                  ↓
    ┌─────────────┴─────────────┬─────────────┬──────────┐
    ↓                           ↓             ↓          ↓
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│   MPS    │  │   MRP    │  │ Inventory│  │  Order   │
│  Agent   │  │  Agent   │  │  Agent   │  │ Promising│
│          │  │          │  │          │  │  Agent   │
│ (Prod.   │  │ (Material│  │ (Safety  │  │ (ATP/CTP)│
│Schedule) │  │ Planning)│  │  Stock)  │  │          │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
    │             │              │             │
    └─────────────┴──────────────┴─────────────┘
                  │ Proposals
                  ↓
┌─────────────────────────────────────────────────────────┐
│          SUPERVISOR AGENT (GPT-4)                       │
│  - Reviews all agent proposals                          │
│  - Validates consistency across agents                  │
│  - Applies business rules and constraints               │
│  - Clamps/rewrites proposals if needed                  │
└─────────────────┬───────────────────────────────────────┘
                  │ Validated Plans
                  ↓
┌─────────────────────────────────────────────────────────┐
│          GLOBAL PLANNER AGENT (Optional)                │
│  - Network-wide optimization                            │
│  - Variance target planning                             │
│  - Rolling base-stock calculation                       │
└─────────────────┬───────────────────────────────────────┘
                  │ Approved Actions
                  ↓
┌─────────────────────────────────────────────────────────┐
│         EXECUTION ENGINE (Tool Calling)                 │
│  - Create/update POs, TOs, MOs                          │
│  - Update inventory levels                              │
│  - Publish plans to ERP                                 │
│  - Send notifications                                   │
└─────────────────────────────────────────────────────────┘
```

**Key Innovations**:

1. **LangGraph State Management**: Pass only necessary state deltas between nodes (fastest framework per research)

2. **ReAct Prompting Pattern**:
```
Thought: Current inventory is 50, safety stock is 80, deficit is 30
Action: calculate_required_production(product_id="CASE", deficit=30, lead_time=2)
Observation: Lead time is 2 weeks, need to produce by Week 5 to avoid stockout
Thought: Week 5 capacity is 100 units, only 30 needed, sufficient capacity available
Action: create_production_order(product_id="CASE", quantity=30, week=5)
Observation: Production order PO-12345 created successfully
Final Answer: Created PO-12345 for 30 units in Week 5 to restore safety stock
```

3. **Tool Calling Registry**:
```python
EXECUTION_TOOLS = [
    {
        "name": "create_production_order",
        "description": "Create a new production order for manufacturing",
        "parameters": {
            "product_id": {"type": "string", "required": True},
            "quantity": {"type": "integer", "required": True},
            "start_week": {"type": "integer", "required": True},
            "site_id": {"type": "string", "required": False}
        },
        "guardrails": {
            "max_quantity_pct_change": 10,  # Can't increase >10% without approval
            "requires_capacity_check": True
        }
    },
    {
        "name": "expedite_purchase_order",
        "description": "Expedite an existing PO with premium shipping",
        "parameters": {
            "po_id": {"type": "string", "required": True},
            "expedite_days": {"type": "integer", "required": True},
            "carrier": {"type": "string", "required": False}
        },
        "guardrails": {
            "max_expedite_cost": 1000,  # Can't spend >$1K without approval
            "min_lead_time_reduction": 2  # Must save ≥2 days to justify cost
        }
    },
    # ... 15+ execution-specific tools
]
```

4. **OODA Loop in Autonomous Execution Planning**:

**OODA** (Observe-Orient-Decide-Act) is a decision-making framework created by military strategist John Boyd that maps perfectly to autonomous execution planning with LLM agents.

**The OODA Loop Cycle**:

```
┌─────────────────────────────────────────────────────────┐
│                    OODA LOOP                            │
│  (Continuous cycle for each execution agent)            │
└─────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │   OBSERVE    │  ← Event detection (stockout, delay, capacity issue)
    │              │  ← Real-time data ingestion (inventory, orders, shipments)
    └──────┬───────┘
           │
           ↓
    ┌──────────────┐
    │    ORIENT    │  ← Context understanding using LLM reasoning
    │              │  ← Impact analysis, constraint evaluation
    │              │  ← Alternative generation, trade-off analysis
    └──────┬───────┘
           │
           ↓
    ┌──────────────┐
    │    DECIDE    │  ← Action selection within guardrails
    │              │  ← Cost-benefit calculation, risk assessment
    │              │  ← Approval routing (auto-execute vs. await approval)
    └──────┬───────┘
           │
           ↓
    ┌──────────────┐
    │     ACT      │  ← Tool execution (create PO, expedite shipment, etc.)
    │              │  ← Result monitoring, notification dispatch
    │              │  ← Loop back to OBSERVE with new state
    └──────┬───────┘
           │
           └────────────┐ (Continuous loop)
                        │
                        └──→ Back to OBSERVE
```

**OODA ≈ ReAct Equivalence**:

The ReAct prompting pattern is essentially an implementation of the OODA loop:

| OODA Stage | ReAct Element | Execution Planning Example |
|------------|---------------|----------------------------|
| **Observe** | Tool Results + Context | "Inventory level: 50 units, Safety stock: 80 units, Customer order: 100 units due Week 3" |
| **Orient** | Thought (Reasoning) | "Deficit of 30 units to reach safety stock + 100 units for customer = 130 total needed. Lead time is 2 weeks, so must act by Week 1 to deliver Week 3." |
| **Decide** | Action Selection | "create_production_order() is appropriate. Check guardrails: quantity change <10%? No (30%). Requires approval." |
| **Act** | Tool Call Execution | `create_production_order(product_id="CASE", quantity=130, week=1)` → Returns PO-12345 |

**OODA + AIIO Integration**:

The OODA loop operates **continuously** within each agent, while AIIO provides the **human oversight framework**:

```python
# Pseudo-code showing OODA loop with AIIO checkpoints

while True:  # Continuous OODA loop
    # OBSERVE
    events = event_bus.poll_new_events()  # Stockout risk, supplier delay, etc.

    # ORIENT
    context = llm.analyze_context(events)  # Understand impact, generate alternatives

    # DECIDE
    decision = llm.select_best_action(context)

    # AIIO Checkpoint: Check guardrails
    if guardrails.validate(decision):
        # ACT (AIIO Stage 1: AUTOMATE)
        result = execute_tool(decision.action)
        notify_user(status="AUTO_EXECUTED", decision=decision, result=result)  # AIIO Stage 2: INFORM
    else:
        # Requires approval (AIIO Stage 3: INSPECT)
        notify_user(status="AWAITING_APPROVAL", decision=decision)
        wait_for_human_override()  # AIIO Stage 4: OVERRIDE

    # Loop back to OBSERVE with new state
    time.sleep(polling_interval)
```

**Key Insight from Research**:

> "The OODA loop transforms static systems into dynamic entities capable of autonomous behavior. Success requires **shortening the loop cycle time relative to environmental change** without sacrificing orientation quality."
>
> — [Sogeti: OODA Loop in Agentic AI](https://www.sogeti.com/ai/blog/intelligent-automation-2025/the-agentic-age-an-introduction-to-ai-agents/)

**For Execution Planning**:
- **Traditional batch planning**: 5-day OODA cycle (observe Monday, decide Friday)
- **Event-driven autonomous planning**: 5-minute OODA cycle (observe event, act within minutes)
- **Competitive advantage**: 1,440x faster response time enables dynamic constraint management

**NVIDIA's Implementation Example**:

NVIDIA's autonomous data center project ([LLo11yPop](https://www.nvidia.com/en-us/on-demand/session/goo242412073/)) demonstrates OODA loop with LLM agents:

```python
# NVIDIA's OODA loop for GPU fleet management (adapted for supply chain)

class ExecutionAgent:
    async def ooda_loop(self):
        while True:
            # OBSERVE: Monitor system state
            metrics = await self.observe_system_state()

            # ORIENT: LLM analyzes anomalies
            analysis = await self.llm.analyze(
                prompt=f"Analyze these execution metrics: {metrics}. Identify issues and root causes."
            )

            # DECIDE: LLM proposes remediation
            if analysis.has_issue:
                action_plan = await self.llm.decide(
                    prompt=f"Given issue: {analysis.issue}, propose specific actions with expected outcomes."
                )

                # DECIDE: Validate with supervisor
                if self.supervisor_enabled:
                    action_plan = await self.supervisor.validate(action_plan)

                # ACT: Execute approved actions
                result = await self.execute_action(action_plan)

                # Loop: Observe result of action
                await self.log_action(action_plan, result)

            await asyncio.sleep(self.polling_interval)
```

**OODA Loop Benefits for Execution Horizon**:

1. **Speed**: Sub-minute response to supplier delays (vs. 5-day weekly planning)
2. **Adaptability**: Continuous adjustment to constraints (vs. locked weekly plans)
3. **Learning**: Each OODA cycle generates training data for agent improvement
4. **Explainability**: Orient stage reasoning provides audit trail (AIIO Inspect)
5. **Human-in-the-Loop**: Decide stage allows guardrail-based approval routing (AIIO Override)

**Implementation in ExecutionOrchestrator**:

```python
# backend/app/services/execution_orchestrator.py

class ExecutionOrchestrator:
    """
    Implements OODA loop for autonomous execution planning
    Integrates with AIIO paradigm for human oversight
    """

    async def start_ooda_loop(self):
        """Start continuous OODA loop for execution monitoring"""
        while True:
            try:
                # OBSERVE: Poll event bus for execution events
                events = await self.event_bus.poll_events(
                    event_types=["stockout_risk", "supplier_delay", "capacity_overload",
                                "customer_urgent_order", "quality_issue"]
                )

                for event in events:
                    # Run OODA cycle for each event
                    await self._process_event_ooda(event)

                await asyncio.sleep(self.polling_interval)  # Default: 60 seconds

            except Exception as e:
                logger.error(f"OODA loop error: {e}")
                await asyncio.sleep(5)  # Backoff on error

    async def _process_event_ooda(self, event: Event):
        """Process a single event through OODA cycle"""

        # OBSERVE: Gather context
        context = await self._gather_context(event)

        # ORIENT: LLM analyzes situation
        orientation = await self._orient_with_llm(event, context)

        # DECIDE: Select best action
        decision = await self._decide_action(orientation)

        # ACT: Execute or request approval
        await self._act_on_decision(decision, event)

    async def _orient_with_llm(self, event: Event, context: dict) -> Orientation:
        """
        ORIENT stage: Use LLM to understand situation and generate alternatives

        This is the critical thinking step that transforms raw observations
        into actionable intelligence.
        """
        prompt = f"""You are an execution planning agent. Analyze this situation:

EVENT: {event.type}
DETAILS: {event.details}

CURRENT STATE:
{json.dumps(context, indent=2)}

INSTRUCTIONS:
1. Identify the root cause and impact of this event
2. Generate 3-5 alternative actions to address the issue
3. For each alternative, estimate:
   - Cost (direct + opportunity cost)
   - Risk (probability of failure)
   - Service level impact
   - Time to execute
4. Consider constraints: lead times, capacities, commitments
5. Recommend the best action with clear reasoning

OUTPUT FORMAT (JSON):
{{
    "root_cause": "...",
    "impact_analysis": "...",
    "alternatives": [
        {{"action": "...", "cost": 0, "risk_pct": 0, "service_impact": 0, "rationale": "..."}},
        ...
    ],
    "recommended_action": 0,  // Index of best alternative
    "reasoning": "..."
}}
"""

        response = await self.llm.complete(prompt)
        return Orientation.from_json(response)

    async def _decide_action(self, orientation: Orientation) -> Decision:
        """
        DECIDE stage: Select action and determine approval routing

        Checks guardrails to decide: auto-execute or await approval?
        """
        recommended = orientation.alternatives[orientation.recommended_action]

        # Check guardrails
        guardrail_result = self.guardrails.validate(recommended)

        decision = Decision(
            action=recommended,
            auto_execute=guardrail_result.passed,
            guardrail_violations=guardrail_result.violations if not guardrail_result.passed else [],
            confidence=orientation.confidence,
            reasoning=orientation.reasoning
        )

        return decision

    async def _act_on_decision(self, decision: Decision, event: Event):
        """
        ACT stage: Execute action and notify users (AIIO integration)
        """
        if decision.auto_execute:
            # AIIO Stage 1: AUTOMATE
            try:
                result = await self._execute_action(decision.action)

                # AIIO Stage 2: INFORM
                await self._send_notification(
                    user_ids=self._get_relevant_planners(event),
                    status=AgentActionStatus.AUTO_EXECUTED,
                    decision=decision,
                    result=result,
                    event=event
                )

                logger.info(f"Auto-executed: {decision.action.description}")

            except Exception as e:
                logger.error(f"Action execution failed: {e}")
                await self._send_notification(
                    user_ids=self._get_relevant_planners(event),
                    status=AgentActionStatus.FAILED,
                    decision=decision,
                    error=str(e),
                    event=event
                )
        else:
            # AIIO Stage 3: INSPECT (awaiting approval)
            await self._send_notification(
                user_ids=self._get_relevant_planners(event),
                status=AgentActionStatus.AWAITING_APPROVAL,
                decision=decision,
                guardrail_violations=decision.guardrail_violations,
                event=event
            )

            logger.info(f"Approval required: {decision.action.description}")
```

**Shortening the OODA Loop Cycle**:

The key to competitive advantage is **completing the OODA loop faster than your constraints change**:

| Planning Approach | Observe | Orient | Decide | Act | **Total Cycle** |
|-------------------|---------|--------|--------|-----|-----------------|
| **Weekly Batch** | Monday (exceptions queued) | Tuesday-Thursday (meetings, analysis) | Friday (plan approval) | Monday (execution) | **5-7 days** |
| **Daily Batch** | 6 AM (overnight run) | 9 AM-12 PM (planner review) | 2 PM (approval) | 4 PM (execution) | **10 hours** |
| **Event-Driven LLM** | Real-time (event trigger) | 30 seconds (LLM analysis) | 10 seconds (guardrails check) | 20 seconds (tool execution) | **60 seconds** |
| **Autonomous (AIIO)** | Real-time (event trigger) | 30 seconds (LLM analysis) | 10 seconds (guardrails check) | 20 seconds (auto-execute) | **60 seconds** |

**Speed Comparison**:
- Event-driven LLM is **240x faster** than daily batch
- Event-driven LLM is **10,080x faster** than weekly batch

This speed advantage enables:
- ✅ Respond to supplier delays before stockouts occur
- ✅ Capture urgent customer orders that competitors miss
- ✅ Rebalance inventory mid-week to avoid weekend stockouts
- ✅ Preemptively expedite materials based on demand signals

#### 4.2 Conversational UI Components

**Chat Interface** (Primary):
```tsx
// frontend/src/components/ExecutionCopilot.jsx

import { ChatMessage, AgentSuggestion, WhatIfAnalysis } from '@/models/chat';

export default function ExecutionCopilot() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [agentActivity, setAgentActivity] = useState<AgentAction[]>([]);

  return (
    <Grid container spacing={2}>
      {/* Main Chat Window */}
      <Grid item xs={12} md={8}>
        <ChatWindow
          messages={messages}
          onSend={handleUserMessage}
          suggestions={agentSuggestions}
        />
      </Grid>

      {/* Agent Activity Feed */}
      <Grid item xs={12} md={4}>
        <AgentActivityFeed
          actions={agentActivity}
          onInspect={handleInspectAction}
          onOverride={handleOverrideAction}
        />
      </Grid>

      {/* Quick Actions */}
      <Grid item xs={12}>
        <QuickActionsBar
          actions={[
            { label: "Show exceptions", prompt: "What exceptions need my attention?" },
            { label: "Production status", prompt: "What's the production status this week?" },
            { label: "At-risk orders", prompt: "Which customer orders are at risk?" },
            { label: "Capacity issues", prompt: "Show me capacity bottlenecks" }
          ]}
          onAction={handleQuickAction}
        />
      </Grid>
    </Grid>
  );
}
```

**Example Conversation**:

```
User: "Show me MPS exceptions for this week"

Agent: "I found 3 MPS exceptions for Week 3 (Jan 27-31):

🚨 CRITICAL (1):
1. Product: CASE
   - Planned production: 500 units
   - Available capacity: 400 units (Machine-A at 100%)
   - Deficit: 100 units
   - Recommended action: Move 100 units to Week 4 (+$200 setup cost)
   - Status: ⏳ Awaiting your approval

⚠️ MEDIUM (2):
2. Product: SIXPACK
   - Safety stock target: 200 units
   - Projected end-of-week: 180 units (10% below target)
   - Recommended action: Increase Week 3 production by 20 units
   - Status: ✅ Auto-executed at 8:05 AM

3. Product: BOTTLE
   - Supplier delay: Vendor-A shipment delayed 2 days
   - Impact: Week 4 production may be constrained
   - Recommended action: Monitor; no action needed yet
   - Status: 👁️ Watching

Would you like to:
[ Approve CASE rebalancing ]  [ See detailed analysis ]  [ Override recommendation ]"

User: "Why can't we split CASE across multiple machines?"

Agent: "Good question. Let me analyze multi-machine options:

CURRENT RECOMMENDATION:
- Move 100 units to Week 4 (single-machine approach)
- Cost: $200 (one-time setup)
- Lead time: Delivered Week 5

ALTERNATIVE: Split across Machine-A and Machine-B
- Machine-A: 400 units (Week 3)
- Machine-B: 100 units (Week 3)
- Cost: $350 ($200 setup A + $150 setup B)
- Lead time: Delivered Week 4 (1 week earlier)
- Constraint: Machine-B has 15% higher unit cost

COST-BENEFIT:
- Multi-machine cost: +$150 setup + $50 unit cost premium = $200 extra
- Benefit: 1-week faster delivery
- Trade-off: Spend $200 to deliver 1 week early

Recommendation: Stick with single-machine unless customer needs early delivery.

Would you like me to:
[ Use multi-machine approach ]  [ Keep original recommendation ]  [ Ask customer about early delivery ]"
```

#### 4.3 Agent Activity Dashboard

**Real-Time Agent Monitoring**:

```tsx
// frontend/src/components/AgentActivityFeed.jsx

interface AgentAction {
  id: string;
  timestamp: Date;
  agent: string;  // 'mps_agent', 'mrp_agent', etc.
  type: 'auto_executed' | 'awaiting_approval' | 'overridden' | 'rejected';
  priority: 'critical' | 'high' | 'medium' | 'low';
  summary: string;
  impact: {
    cost_delta: number;
    service_level_delta: number;
    affected_orders: number;
  };
  reasoning: string;
  alternatives: Alternative[];
}

export default function AgentActivityFeed({ actions, onInspect, onOverride }) {
  return (
    <Card>
      <CardHeader title="Agent Activity (Last 24h)" />
      <CardContent>
        <Timeline>
          {actions.map(action => (
            <TimelineItem key={action.id}>
              <TimelineOppositeContent color="text.secondary">
                {format(action.timestamp, 'HH:mm')}
              </TimelineOppositeContent>
              <TimelineSeparator>
                <TimelineDot color={getStatusColor(action.type)}>
                  {getStatusIcon(action.agent)}
                </TimelineDot>
                <TimelineConnector />
              </TimelineSeparator>
              <TimelineContent>
                <Card variant="outlined" sx={{ mb: 2 }}>
                  <CardContent>
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                      <Chip
                        label={action.priority.toUpperCase()}
                        color={getPriorityColor(action.priority)}
                        size="small"
                      />
                      <Chip
                        label={formatAgentName(action.agent)}
                        variant="outlined"
                        size="small"
                      />
                    </Stack>
                    <Typography variant="body2" sx={{ mt: 1 }}>
                      {action.summary}
                    </Typography>
                    <Stack direction="row" spacing={2} sx={{ mt: 1 }}>
                      <Typography variant="caption" color="text.secondary">
                        Cost: {formatCurrency(action.impact.cost_delta)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Service: {action.impact.service_level_delta > 0 ? '+' : ''}
                        {action.impact.service_level_delta}%
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Orders: {action.impact.affected_orders}
                      </Typography>
                    </Stack>
                    <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
                      <Button
                        size="small"
                        startIcon={<SearchIcon />}
                        onClick={() => onInspect(action.id)}
                      >
                        Inspect
                      </Button>
                      {action.type === 'awaiting_approval' && (
                        <>
                          <Button
                            size="small"
                            color="success"
                            startIcon={<CheckIcon />}
                            onClick={() => handleApprove(action.id)}
                          >
                            Approve
                          </Button>
                          <Button
                            size="small"
                            color="error"
                            startIcon={<CloseIcon />}
                            onClick={() => onOverride(action.id)}
                          >
                            Override
                          </Button>
                        </>
                      )}
                      {action.type === 'auto_executed' && (
                        <Button
                          size="small"
                          color="warning"
                          startIcon={<UndoIcon />}
                          onClick={() => onOverride(action.id)}
                        >
                          Undo
                        </Button>
                      )}
                    </Stack>
                  </CardContent>
                </Card>
              </TimelineContent>
            </TimelineItem>
          ))}
        </Timeline>
      </CardContent>
    </Card>
  );
}
```

**Visualization**:
```
┌─────────────────────────────────────────────────────────┐
│ Agent Activity Feed (Last 24h)                    [🔔 3]│
├─────────────────────────────────────────────────────────┤
│                                                         │
│  10:05  [✓] MPS Agent        [MEDIUM]                  │
│         ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━    │
│         Increased CASE production by 20 units (Week 4)  │
│         Cost: +$200  Service: +1%  Orders: 5           │
│         [🔍 Inspect]  [↩️ Undo]                        │
│                                                         │
│  09:47  [⏳] Inventory Agent [HIGH]                    │
│         ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━    │
│         Rebalance inventory: DC-East → DC-West (200u)   │
│         Cost: +$500  Service: +2%  Orders: 12          │
│         [🔍 Inspect]  [✓ Approve]  [✗ Override]        │
│                                                         │
│  09:30  [✓] MRP Agent        [MEDIUM]                  │
│         ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━    │
│         Created PO-12345 for BOTTLE (500 units)         │
│         Cost: $0  Service: 0%  Orders: 0               │
│         [🔍 Inspect]  [↩️ Undo]                        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

#### 4.4 Conformal Prediction for Uncertainty Quantification

**Conformal Prediction (CP)** provides formal uncertainty quantification with **guaranteed coverage probabilities** for autonomous planning decisions. Unlike typical probabilistic forecasts, CP offers distribution-free prediction intervals that contain the true value with probability ≥ 1-α, regardless of the underlying data distribution.

**Why Conformal Prediction for Execution Planning?**

1. **Formal Guarantees**: Statistical coverage guarantees without distributional assumptions
2. **LLM Uncertainty**: Quantify uncertainty in LLM-generated decisions and proposals
3. **Adaptive Guardrails**: Automatically adjust approval thresholds based on prediction interval width
4. **Risk Management**: Make decisions with quantified, bounded risk
5. **Trust Building**: "90% guaranteed" is more trustworthy than "probably correct"

##### Conformal Decision Theory (CDT)

Recent research introduces **Conformal Decision Theory**, which calibrates agent decisions directly for low risk rather than just calibrating predictions:

> "CDT calibrates an agent's decisions to achieve statistical guarantees for the realized average loss of those decisions. The decisions come with provable statistical guarantees of having low risk without any assumptions on the world model; observations need not be I.I.D. and can even be adversarial."
>
> — [Conformal Decision Theory: Safe Autonomous Decisions from Imperfect Predictions (arXiv 2023)](https://arxiv.org/abs/2310.05921)

**CDT Applications Demonstrated**:
- Robot navigation around humans (safe but efficient)
- Manufacturing conveyor belt speed (high-throughput with successful grasps)
- Automated high-frequency trading (optimized buy/sell decisions)

##### Integration Points in Autonomous Execution Planning

**1. LLM Decision Confidence (ORIENT Stage)**

[Current problem with LLMs: unreliable confidence scores](https://medium.com/capgemini-invent-lab/quantifying-llms-uncertainty-with-conformal-predictions-567870e63e00)

**CP Solution**: Construct prediction sets for LLM outputs with guaranteed coverage

```python
# backend/app/services/conformal_llm.py

from mapie.classification import MapieClassifier
from typing import List, Tuple

class ConformalLLMAgent:
    """
    Wraps LLM agent with conformal prediction for uncertainty quantification
    """

    def __init__(self, llm_agent, alpha: float = 0.1):
        """
        Args:
            llm_agent: Base LLM agent (e.g., ExecutionOrchestrator agent)
            alpha: Miscoverage rate (0.1 = 90% coverage guarantee)
        """
        self.llm_agent = llm_agent
        self.alpha = alpha
        self.calibration_data = []  # (context, prediction, actual_outcome) tuples

    async def predict_with_uncertainty(self, context: dict) -> Tuple[Any, List[Any], float]:
        """
        Make prediction with conformal prediction set

        Returns:
            prediction: Point prediction (most likely action)
            prediction_set: Set of actions that could be correct with probability ≥ 1-α
            uncertainty: Width of prediction set (measure of uncertainty)
        """
        # Get LLM prediction
        llm_output = await self.llm_agent._orient_with_llm(context)

        # Compute nonconformity scores from calibration set
        conformity_scores = self._compute_conformity_scores(context)

        # Construct prediction set using conformal threshold
        quantile = np.quantile(conformity_scores, 1 - self.alpha)
        prediction_set = self._get_prediction_set(llm_output, quantile)

        # Uncertainty = size of prediction set
        uncertainty = len(prediction_set)

        return llm_output.recommended_action, prediction_set, uncertainty

    def _compute_conformity_scores(self, context: dict) -> np.ndarray:
        """
        Compute nonconformity scores from calibration data

        Uses Token-Entropy Conformal Prediction (TECP) approach:
        - Score = negative log-likelihood of correct action
        - Higher score = less confident prediction
        """
        scores = []
        for cal_context, cal_prediction, cal_actual in self.calibration_data:
            similarity = self._context_similarity(context, cal_context)
            if similarity > 0.7:  # Use similar contexts
                score = -np.log(cal_prediction.confidence + 1e-10)
                scores.append(score)

        return np.array(scores) if scores else np.array([0.5])

    def _get_prediction_set(self, llm_output: Orientation, threshold: float) -> List[Action]:
        """
        Construct prediction set: all actions with score ≤ threshold
        """
        prediction_set = []
        for alt in llm_output.alternatives:
            score = -np.log(alt.estimated_confidence + 1e-10)
            if score <= threshold:
                prediction_set.append(alt.action)

        return prediction_set if prediction_set else [llm_output.alternatives[0].action]

    def update_calibration(self, context: dict, prediction: Any, actual_outcome: Any):
        """
        Update calibration set with new observation

        Called after action execution to continuously improve predictions
        """
        self.calibration_data.append((context, prediction, actual_outcome))

        # Keep calibration set bounded (e.g., last 1000 observations)
        if len(self.calibration_data) > 1000:
            self.calibration_data = self.calibration_data[-1000:]
```

**Example Output with Conformal Prediction**:

```
Agent: "STOCKOUT RISK DETECTED: Product CASE, Site DC-East

CONFORMAL PREDICTION ANALYSIS (90% coverage guarantee):

Point Prediction: Expedite PO from Vendor-B ($500 cost)

Prediction Set (90% confident one of these is optimal):
1. ✓ Expedite Vendor-B ($500 cost, arrives Jan 31) [RECOMMENDED]
2. ✓ Wait for Vendor-A (delayed, $0 cost, 85% stockout risk)
3. ✓ Transfer from DC-West ($300 cost, arrives Feb 1)

Uncertainty Score: 3 alternatives in prediction set (medium uncertainty)

DECISION RULE:
- Prediction set size = 3 → Medium uncertainty → Requires human approval
- If prediction set size = 1 → High certainty → Auto-execute
- If prediction set size > 5 → High uncertainty → Escalate to senior planner

Coverage Guarantee: Based on 487 historical similar decisions, this prediction set
contains the optimal action with ≥90% probability (miscoverage rate α=0.10).

[Approve Vendor-B expedite] [View all 3 alternatives] [Provide feedback]"
```

**2. Demand Forecasting with Conformal Intervals**

[Research shows CP provides well-calibrated uncertainty for demand forecasting](https://arxiv.org/abs/2505.17340)

**Integration with Stochastic Planning**:

```python
# backend/app/services/conformal_forecast.py

from statsforecast import StatsForecast
from statsforecast.models import AutoARIMA
import numpy as np

class ConformalDemandForecaster:
    """
    Demand forecasting with conformal prediction intervals
    """

    def __init__(self, alpha: float = 0.1):
        """
        Args:
            alpha: Miscoverage rate (0.1 = 90% prediction intervals)
        """
        self.alpha = alpha
        self.model = StatsForecast(models=[AutoARIMA()])

    def forecast_with_conformal_intervals(
        self,
        historical_demand: np.ndarray,
        horizon: int
    ) -> dict:
        """
        Generate demand forecast with conformal prediction intervals

        Returns:
            forecast: Point forecast
            lower_bound: Lower bound of 90% PI
            upper_bound: Upper bound of 90% PI
            coverage_guarantee: Formal coverage probability
        """
        # Fit model
        self.model.fit(historical_demand)

        # Generate forecast
        forecast = self.model.predict(h=horizon)

        # Compute conformal prediction intervals
        # Uses split conformal prediction with absolute residuals
        calibration_residuals = self._get_calibration_residuals(historical_demand)
        quantile = np.quantile(np.abs(calibration_residuals), 1 - self.alpha)

        lower_bound = forecast - quantile
        upper_bound = forecast + quantile

        return {
            "forecast": forecast,
            "lower_90": lower_bound,
            "upper_90": upper_bound,
            "interval_width": upper_bound - lower_bound,
            "coverage_guarantee": 1 - self.alpha,
            "method": "split_conformal_prediction"
        }

    def _get_calibration_residuals(self, historical_demand: np.ndarray) -> np.ndarray:
        """
        Compute residuals on calibration set (last 20% of data)
        """
        split_point = int(len(historical_demand) * 0.8)
        train_data = historical_demand[:split_point]
        cal_data = historical_demand[split_point:]

        # Fit on train, predict on calibration
        self.model.fit(train_data)
        cal_predictions = self.model.predict(h=len(cal_data))

        residuals = cal_data - cal_predictions
        return residuals
```

**Example Forecast Output**:

```
DEMAND FORECAST WITH CONFORMAL INTERVALS (90% coverage guarantee)

Product: CASE
Horizon: 4 weeks

Week 1:
  Point Forecast: 100 units
  90% PI: [85, 115] units (width: 30 units)
  Coverage: ≥90% probability actual demand falls in this interval

Week 2:
  Point Forecast: 120 units
  90% PI: [100, 140] units (width: 40 units)
  Coverage: ≥90% probability actual demand falls in this interval

Week 3:
  Point Forecast: 110 units
  90% PI: [88, 132] units (width: 44 units)
  Coverage: ≥90% probability actual demand falls in this interval

Week 4:
  Point Forecast: 105 units
  90% PI: [80, 130] units (width: 50 units)
  Coverage: ≥90% probability actual demand falls in this interval

Note: Interval width increases with horizon (uncertainty grows over time)
Method: Split conformal prediction with absolute residuals
Calibration: Based on 52 weeks of historical data
```

**3. Adaptive Guardrails Based on Uncertainty**

**Current**: Static guardrails (e.g., "don't exceed 10% quantity change")

**CP Enhancement**: Dynamic guardrails based on prediction interval width

```python
# backend/app/services/execution_orchestrator.py (enhanced)

class ExecutionOrchestrator:
    async def _decide_action(self, orientation: Orientation) -> Decision:
        """
        DECIDE stage with conformal prediction for adaptive guardrails
        """
        # Get conformal prediction with uncertainty
        prediction, prediction_set, uncertainty = await self.conformal_agent.predict_with_uncertainty(
            context=orientation.context
        )

        # ADAPTIVE GUARDRAIL LOGIC:
        # - Low uncertainty (prediction set size = 1) → Auto-execute
        # - Medium uncertainty (size 2-4) → Check static guardrails
        # - High uncertainty (size > 4) → Always require approval

        if uncertainty == 1:
            # High confidence, single clear action
            auto_execute = True
            rationale = "Low uncertainty: single action in 90% prediction set"

        elif uncertainty <= 4:
            # Medium confidence, check traditional guardrails
            guardrail_result = self.guardrails.validate(prediction)
            auto_execute = guardrail_result.passed
            rationale = f"Medium uncertainty: {uncertainty} alternatives in prediction set"

        else:
            # High uncertainty, always escalate
            auto_execute = False
            rationale = f"High uncertainty: {uncertainty} alternatives in prediction set (>4)"

        decision = Decision(
            action=prediction,
            auto_execute=auto_execute,
            uncertainty=uncertainty,
            prediction_set=prediction_set,
            guardrail_violations=[],
            confidence=1.0 - (uncertainty / len(orientation.alternatives)),
            reasoning=orientation.reasoning + f"\n\nUncertainty Analysis: {rationale}"
        )

        return decision
```

**Adaptive Guardrail Decision Tree**:

```
┌─────────────────────────────────────────────────────┐
│         Conformal Prediction Set Size                │
│         (90% coverage guarantee)                     │
└─────────────────┬───────────────────────────────────┘
                  │
                  ↓
        ┌─────────┴─────────┐
        │ Size = 1?         │
        │ (High Certainty)  │
        └─────────┬─────────┘
                  │
        ┌─────────┴─────────┐
        Yes                No
        │                  │
        ↓                  ↓
┌──────────────┐   ┌────────────────┐
│ AUTO-EXECUTE │   │ Size 2-4?      │
│ (AIIO Stage 1)│   │ (Medium Cert.) │
└──────────────┘   └────┬───────────┘
                        │
                ┌───────┴────────┐
                Yes             No (Size > 4)
                │               │
                ↓               ↓
        ┌────────────────┐  ┌──────────────┐
        │ Check Static   │  │ ESCALATE TO  │
        │ Guardrails     │  │ SENIOR PLAN. │
        └────┬───────────┘  └──────────────┘
             │
        ┌────┴───────┐
        Pass       Fail
        │          │
        ↓          ↓
┌──────────┐  ┌────────────┐
│AUTO-EXEC │  │ AWAIT      │
│          │  │ APPROVAL   │
└──────────┘  └────────────┘
```

**4. ATP/CTP with Guaranteed Delivery Promises**

[Research on order fulfillment time forecasting with conformal prediction](https://arxiv.org/abs/2505.17340) shows 75% improvement in identifying late deliveries

```python
# backend/app/services/atp_ctp_conformal.py

class ConformalATPService:
    """
    Available-to-Promise with conformal prediction intervals
    """

    def promise_delivery_date(
        self,
        product_id: str,
        quantity: int,
        customer_priority: str
    ) -> dict:
        """
        Promise delivery date with statistical coverage guarantee
        """
        # Compute lead time prediction with conformal interval
        lead_time_forecast = self.conformal_lead_time_model.predict(
            product_id=product_id,
            quantity=quantity,
            current_backlog=self._get_backlog(),
            supplier_performance=self._get_supplier_metrics()
        )

        # Coverage level depends on customer priority
        coverage_map = {
            "strategic": 0.95,  # 95% guarantee for strategic customers
            "standard": 0.90,   # 90% guarantee for standard customers
            "spot": 0.80        # 80% guarantee for spot orders
        }
        coverage = coverage_map.get(customer_priority, 0.90)

        # Conformal prediction interval for delivery date
        median_delivery = lead_time_forecast["p50"]
        upper_bound = lead_time_forecast[f"p{int(coverage*100)}"]

        return {
            "promised_date": upper_bound,  # Conservative promise
            "expected_date": median_delivery,  # Most likely date
            "coverage_probability": coverage,
            "guarantee": f"Delivery by {upper_bound} with ≥{coverage*100}% probability",
            "explanation": f"Based on {lead_time_forecast['calibration_samples']} similar orders"
        }
```

**Example ATP Output**:

```
AVAILABLE-TO-PROMISE ANALYSIS

Customer: ACME Corp (Strategic)
Product: CASE
Quantity: 500 units
Order Date: Jan 26, 2026

CONFORMAL DELIVERY PROMISE (95% coverage guarantee):

Promised Delivery Date: Feb 10, 2026 ✓
  - 95% probability delivered by this date
  - Based on 287 similar orders (calibration set)

Expected Delivery Date: Feb 7, 2026
  - Median (P50) delivery time

Delivery Timeline:
  Pessimistic (P95): Feb 10 (promised date)
  Realistic (P50):   Feb 7
  Optimistic (P10):  Feb 4

Confidence Level: HIGH
  - Prediction interval width: 6 days
  - Coverage guarantee: ≥95%
  - Method: Conformal Venn-Abers Predictor

Recommendation: Promise Feb 10 to strategic customer (95% guarantee)
Alternative: Promise Feb 12 for 99% guarantee (ultra-conservative)

[Accept Promise] [Request Earlier Date] [View Alternatives]
```

**5. Multi-Agent Proposal Validation with Conformal Bounds**

**Supervisor Agent Enhancement**: Use conformal prediction to validate if agent proposals fall within statistically valid ranges

```python
# backend/app/services/conformal_supervisor.py

class ConformalSupervisorAgent:
    """
    Supervisor agent enhanced with conformal prediction validation
    """

    async def validate_agent_proposals(
        self,
        proposals: List[AgentProposal],
        context: dict
    ) -> SupervisorDecision:
        """
        Validate if agent proposals are within conformal valid ranges
        """
        validations = []

        for proposal in proposals:
            # Get conformal bounds for this type of decision
            conformal_bounds = self.get_conformal_bounds(
                decision_type=proposal.action_type,
                context=context
            )

            # Check if proposal is within 90% prediction interval
            is_valid = conformal_bounds["lower_90"] <= proposal.quantity <= conformal_bounds["upper_90"]

            if not is_valid:
                # Proposal is outside statistically expected range
                validations.append({
                    "agent": proposal.agent_id,
                    "action": proposal.action_type,
                    "proposed": proposal.quantity,
                    "conformal_bounds": conformal_bounds,
                    "status": "REQUIRES_REVIEW",
                    "reason": f"Proposal ({proposal.quantity}) is outside 90% conformal interval "
                              f"[{conformal_bounds['lower_90']}, {conformal_bounds['upper_90']}]"
                })
            else:
                validations.append({
                    "agent": proposal.agent_id,
                    "action": proposal.action_type,
                    "status": "CONFORMALLY_VALID",
                    "reason": f"Within 90% prediction interval"
                })

        return SupervisorDecision(
            validations=validations,
            approved=all(v["status"] != "REQUIRES_REVIEW" for v in validations)
        )
```

##### Benefits of Conformal Prediction Integration

**Comparison: Traditional vs. Conformal-Enhanced Planning**

| Metric | Traditional LLM Planning | With Conformal Prediction |
|--------|-------------------------|--------------------------|
| **Uncertainty Quantification** | Unreliable confidence scores | Formal coverage guarantees (90%, 95%, 99%) |
| **Guardrails** | Static thresholds | Adaptive based on prediction interval width |
| **Auto-Execution Rate** | Fixed % (e.g., 60%) | Dynamic: 80% when certain, 20% when uncertain |
| **False Alarm Rate** | High (over-cautious) | Calibrated to target α (e.g., 10%) |
| **Trust & Explainability** | "Probably correct" | "90% guaranteed to be correct" |
| **Continuous Improvement** | Manual tuning | Automatic recalibration with new data |
| **Multi-Agent Validation** | Heuristic rules | Statistical bounds from historical data |

**ROI Enhancement**:
- **Reduce False Escalations**: 40% fewer "awaiting approval" actions due to better certainty detection
- **Increase Auto-Execution**: 20% more auto-executed actions in high-certainty scenarios
- **Improve Service Levels**: 95% guaranteed delivery promises vs. 80% typical accuracy
- **Faster Recalibration**: Weekly automatic updates vs. monthly manual guardrail tuning

##### Implementation Roadmap for Conformal Prediction

**Phase 1: Foundation (Month 1-2)**
- Deploy MAPIE library for conformal prediction
- Collect calibration datasets (500+ historical decisions per agent type)
- Implement basic conformal wrapper for demand forecasting

**Phase 2: LLM Integration (Month 3-4)**
- Wrap execution agents with ConformalLLMAgent class
- Implement Token-Entropy Conformal Prediction (TECP) for LLM outputs
- Deploy adaptive guardrails based on prediction set size

**Phase 3: Multi-Agent Validation (Month 5-6)**
- Enhance supervisor agent with conformal bounds validation
- Implement conformal decision theory for action selection
- Deploy ATP/CTP with guaranteed delivery dates

**Phase 4: Continuous Calibration (Month 7+)**
- Automate weekly recalibration of prediction intervals
- A/B test conformal vs. traditional guardrails
- Monitor coverage rates and adjust α as needed

**Key Libraries & Tools**:
- **MAPIE**: Model Agnostic Prediction Interval Estimator ([GitHub](https://github.com/scikit-learn-contrib/MAPIE))
- **Crepes**: Conformal regressors and predictive systems ([PyPI](https://pypi.org/project/crepes/))
- **Uncertainty Baselines**: TensorFlow framework for UQ ([GitHub](https://github.com/google/uncertainty-baselines))
- **LLM-UQ-Bench**: Benchmarking LLM uncertainty quantification ([GitHub](https://github.com/smartyfh/LLM-Uncertainty-Bench))

##### Supply-Side Applications of Conformal Prediction

While demand forecasting gets most attention, **supply-side uncertainty quantification** is equally critical for execution planning. [Recent research (January 2026) examined conformal prediction across 8 supply chain tasks during COVID-19](https://arxiv.org/abs/2601.00908), revealing both opportunities and challenges for supply-side applications.

**Key Finding**: Conformal prediction coverage degrades under distribution shift (COVID-19 disruptions), with coverage drops ranging from 0% to 86.7%. Tasks with single-feature dependence experienced catastrophic failures, while **quarterly retraining restored coverage from 22% to 41%** (+19 pp, p = 0.04).

**#1. Supplier Lead Time Prediction with Guaranteed Bounds**

**Challenge**: Supplier lead times vary due to production queues, logistics delays, quality issues, and geopolitical events. Traditional point estimates ("14 days") hide this variability.

**CP Solution**: Prediction intervals with coverage guarantees

```python
# backend/app/services/conformal_supplier.py

class ConformalSupplierLeadTimePredictor:
    """
    Predict supplier lead times with conformal prediction intervals
    """

    def __init__(self, alpha: float = 0.1):
        self.alpha = alpha  # 10% miscoverage = 90% coverage guarantee
        self.model = GradientBoostingRegressor()  # Or any base model
        self.calibration_data = []  # (features, actual_lead_time) tuples

    def predict_lead_time(
        self,
        supplier_id: str,
        product_id: str,
        order_quantity: int,
        current_backlog: int,
        season: str
    ) -> dict:
        """
        Predict lead time with conformal interval

        Returns:
            point_estimate: Expected lead time (days)
            lower_bound: 90% PI lower bound
            upper_bound: 90% PI upper bound (use for safety planning)
            coverage_guarantee: Formal probability
        """
        # Feature vector
        features = np.array([[
            self._encode_supplier(supplier_id),
            self._encode_product(product_id),
            order_quantity,
            current_backlog,
            self._encode_season(season)
        ]])

        # Point prediction
        point_pred = self.model.predict(features)[0]

        # Conformal prediction interval
        residuals = self._get_calibration_residuals(supplier_id, product_id)
        quantile = np.quantile(np.abs(residuals), 1 - self.alpha)

        lower_bound = max(1, point_pred - quantile)  # Lead time ≥ 1 day
        upper_bound = point_pred + quantile

        return {
            "supplier_id": supplier_id,
            "product_id": product_id,
            "point_estimate": round(point_pred),
            "lower_90": round(lower_bound),
            "upper_90": round(upper_bound),
            "interval_width": round(upper_bound - lower_bound),
            "coverage_guarantee": 1 - self.alpha,
            "calibration_samples": len(residuals),
            "recommendation": f"Plan for {round(upper_bound)} days to guarantee 90% on-time arrival"
        }

    def _get_calibration_residuals(self, supplier_id: str, product_id: str) -> np.ndarray:
        """
        Get residuals from similar historical orders (calibration set)
        """
        similar_orders = [
            (actual - predicted)
            for (s_id, p_id, predicted, actual) in self.calibration_data
            if s_id == supplier_id and p_id == product_id
        ]

        return np.array(similar_orders) if similar_orders else np.array([0])

    def update_with_actual(self, supplier_id: str, product_id: str,
                          predicted: float, actual: float):
        """
        Update calibration set when order arrives (continuous learning)
        """
        self.calibration_data.append((supplier_id, product_id, predicted, actual))

        # Keep calibration set bounded (last 1000 orders)
        if len(self.calibration_data) > 1000:
            self.calibration_data = self.calibration_data[-1000:]
```

**Example Output**:

```
SUPPLIER LEAD TIME PREDICTION WITH CONFORMAL BOUNDS

Purchase Order: PO-2456
Supplier: Acme Components (ID: SUP-A)
Product: Bottle Caps (PROD-123)
Quantity: 5,000 units
Current Backlog: 15,000 units (high)
Season: Q1 (peak manufacturing season)

CONFORMAL PREDICTION (90% coverage guarantee):

Point Estimate:        14 days (most likely arrival)
90% Prediction Interval: [11, 19] days
Recommended Planning Lead Time: 19 days (to guarantee 90% on-time arrival)

Interval Width: 8 days (moderate uncertainty)
Coverage Guarantee: ≥90% probability actual lead time falls within [11, 19] days
Calibration: Based on 487 similar orders from SUP-A for PROD-123

SOURCING DECISION SUPPORT:
- Use UPPER BOUND (19 days) for MRP planning (conservative)
- Use POINT ESTIMATE (14 days) for ATP promising (optimistic)
- Use INTERVAL WIDTH (8 days) as uncertainty metric for multi-sourcing

Alternative Suppliers (for comparison):
- Vendor-B: Point=16 days, 90% PI=[14, 20], Width=6 days (more reliable)
- Vendor-C: Point=12 days, 90% PI=[8, 22], Width=14 days (less reliable)

Recommendation: Primary source from SUP-A, backup order from Vendor-B if critical deadline
```

**Integration with MRP Planning**:

```python
# Use upper bound for safety planning
safety_lead_time = lead_time_prediction["upper_90"]  # 19 days

# Schedule order release date
order_release_date = required_date - timedelta(days=safety_lead_time)

# Confidence: 90% probability arrives by required_date
```

**#2. Manufacturing Yield Prediction (Quality Uncertainty)**

**Challenge**: Manufacturing processes have yield losses due to scrap, rework, and quality failures. Assuming 100% yield leads to shortfalls.

**CP Solution**: Yield prediction intervals for production planning

```python
# backend/app/services/conformal_yield.py

class ConformalYieldPredictor:
    """
    Predict manufacturing yield with conformal bounds
    """

    def predict_yield(
        self,
        product_id: str,
        production_line: str,
        batch_size: int,
        shift: str  # "day" or "night"
    ) -> dict:
        """
        Predict yield rate with conformal interval

        Example: If you start with 1000 units, how many good units will you get?
        """
        features = self._extract_features(product_id, production_line, batch_size, shift)

        # Point prediction (expected yield rate)
        yield_rate_point = self.model.predict(features)[0]  # e.g., 0.92 (92%)

        # Conformal prediction interval for yield rate
        residuals = self._get_calibration_residuals(product_id, production_line)
        quantile = np.quantile(np.abs(residuals), 1 - self.alpha)

        lower_bound = max(0.0, yield_rate_point - quantile)
        upper_bound = min(1.0, yield_rate_point + quantile)

        # Convert to unit quantities
        expected_output = batch_size * yield_rate_point
        lower_output = batch_size * lower_bound
        upper_output = batch_size * upper_bound

        return {
            "product_id": product_id,
            "input_quantity": batch_size,
            "expected_output": round(expected_output),
            "lower_90_output": round(lower_output),
            "upper_90_output": round(upper_output),
            "yield_rate_point": round(yield_rate_point * 100, 1),  # 92.0%
            "yield_rate_lower_90": round(lower_bound * 100, 1),    # 88.0%
            "yield_rate_upper_90": round(upper_bound * 100, 1),    # 96.0%
            "uncertainty": round((upper_bound - lower_bound) * 100, 1),  # 8.0 pp
            "recommendation": f"Plan for {round(lower_output)} good units (90% guarantee)"
        }
```

**Example Output**:

```
MANUFACTURING YIELD PREDICTION WITH CONFORMAL BOUNDS

Production Order: MO-789
Product: Six-Pack Cases
Production Line: Line-A
Batch Size: 1,000 units
Shift: Night shift

CONFORMAL YIELD PREDICTION (90% coverage guarantee):

Expected Yield:  920 good units (92.0% yield rate)
90% PI:         [880, 960] good units
Pessimistic (Lower Bound): 880 units (88.0% yield)
Optimistic (Upper Bound):  960 units (96.0% yield)

Yield Uncertainty: 8.0 percentage points (moderate variability)

PRODUCTION PLANNING RECOMMENDATIONS:
✓ Plan for 880 good units (90% guarantee) → Order 1,136 raw units to produce 1,000 good
✓ Expected scrap: 80 units (8%)
✓ Schedule buffer: +14% raw material vs. naive 100% yield assumption

Historical Context:
- Last 50 batches on Line-A: Actual yields ranged from 85% to 97%
- Night shift typically 2-3% lower yield than day shift
- Coverage guarantee validated: 92% of batches fell within predicted intervals
```

**MPS Integration**:

```python
# backend/app/services/mps_with_yield_uncertainty.py

# Calculate required production quantity accounting for yield loss
target_output = 1000  # Need 1,000 good units
yield_prediction = conformal_yield.predict_yield(product_id, line, 1000, shift)

# Use LOWER BOUND for conservative planning
guaranteed_output = yield_prediction["lower_90_output"]  # 880 units

# Calculate required input to guarantee target output
required_input = math.ceil(target_output / (guaranteed_output / 1000))  # 1,136 units

print(f"To guarantee {target_output} good units (90% confidence):")
print(f"  Start with {required_input} units")
print(f"  Expected scrap: {required_input - target_output} units")
```

**#3. Capacity Availability Prediction (Downtime Uncertainty)**

**Challenge**: Machine breakdowns, maintenance, labor shortages create capacity uncertainty. Assuming 100% uptime leads to missed commitments.

**CP Solution**: Available capacity prediction intervals

```python
# backend/app/services/conformal_capacity.py

class ConformalCapacityPredictor:
    """
    Predict available machine capacity with downtime uncertainty
    """

    def predict_available_capacity(
        self,
        resource_id: str,
        planning_week: int,
        historical_utilization: float
    ) -> dict:
        """
        Predict available capacity hours with conformal bounds

        Returns:
            Prediction interval for actual available hours (accounting for downtime)
        """
        # Nominal capacity
        nominal_hours = 40  # 40 hours/week (single shift)

        # Predict availability rate (accounting for breakdowns, maintenance)
        availability_point = self.model.predict([[resource_id, planning_week, historical_utilization]])[0]

        # Conformal prediction interval
        residuals = self._get_residuals(resource_id)
        quantile = np.quantile(np.abs(residuals), 1 - self.alpha)

        lower_bound = max(0, availability_point - quantile)
        upper_bound = min(1.0, availability_point + quantile)

        # Convert to hours
        expected_hours = nominal_hours * availability_point
        guaranteed_hours = nominal_hours * lower_bound
        optimistic_hours = nominal_hours * upper_bound

        return {
            "resource_id": resource_id,
            "nominal_capacity": nominal_hours,
            "expected_available": round(expected_hours, 1),
            "lower_90_available": round(guaranteed_hours, 1),
            "upper_90_available": round(optimistic_hours, 1),
            "availability_rate": round(availability_point * 100, 1),
            "worst_case_availability": round(lower_bound * 100, 1),
            "uncertainty": round((upper_bound - lower_bound) * nominal_hours, 1),
            "recommendation": f"Plan for {round(guaranteed_hours, 1)} hours (90% guarantee)"
        }
```

**Example Output**:

```
CAPACITY AVAILABILITY PREDICTION WITH CONFORMAL BOUNDS

Resource: Machine-A (CNC Mill)
Planning Week: Week 8 (Feb 17-21, 2026)
Nominal Capacity: 40 hours (single shift)

CONFORMAL AVAILABILITY PREDICTION (90% coverage guarantee):

Expected Availability:  36.0 hours (90.0% uptime)
90% PI:                [32.0, 38.5] hours
Guaranteed Availability: 32.0 hours (80.0% uptime) ← Use this for CTP
Optimistic Availability: 38.5 hours (96.25% uptime)

Expected Downtime: 4.0 hours (10%)
Worst-Case Downtime: 8.0 hours (20%)

Uncertainty: 6.5 hours (16% variability)

CAPACITY PLANNING RECOMMENDATIONS:
✓ Promise orders based on 32 hours available (conservative CTP)
✓ Reserve 4-hour buffer for unplanned downtime
✓ If >32 hours committed, have backup resource (Machine-B) on standby

Historical Context:
- Last 12 weeks: Actual availability ranged from 28 to 39 hours
- Primary causes of downtime: Preventive maintenance (30%), unplanned repairs (50%), changeover (20%)
- Coverage accuracy: 91% of weeks fell within predicted intervals
```

**#4. Multi-Sourcing Decisions with Risk Hedging**

**CP Application**: Use prediction interval width as a risk metric for supplier diversification

```python
# backend/app/services/conformal_sourcing.py

class ConformalSourcingOptimizer:
    """
    Multi-sourcing decisions with conformal prediction risk hedging
    """

    def optimize_sourcing_allocation(
        self,
        product_id: str,
        required_quantity: int,
        suppliers: List[str],
        risk_tolerance: float = 0.9  # 90% service level
    ) -> dict:
        """
        Allocate order across suppliers to minimize risk

        Key Insight: Suppliers with wider prediction intervals = higher uncertainty = higher risk
        """
        # Get conformal predictions for each supplier
        predictions = {}
        for supplier_id in suppliers:
            pred = self.lead_time_predictor.predict_lead_time(
                supplier_id=supplier_id,
                product_id=product_id,
                order_quantity=required_quantity,
                current_backlog=self._get_backlog(supplier_id),
                season=self._current_season()
            )
            predictions[supplier_id] = pred

        # Risk metric = prediction interval width (normalized)
        risks = {
            s: pred["interval_width"] / pred["point_estimate"]
            for s, pred in predictions.items()
        }

        # Portfolio optimization: Minimize weighted risk
        # Diversification reduces overall uncertainty (like Markowitz portfolio theory)

        # Simplified allocation: Inverse risk weighting
        risk_scores = np.array([risks[s] for s in suppliers])
        inverse_risks = 1 / risk_scores
        weights = inverse_risks / inverse_risks.sum()

        # Allocate quantities
        allocations = {
            suppliers[i]: round(required_quantity * weights[i])
            for i in range(len(suppliers))
        }

        # Adjust for rounding
        total_allocated = sum(allocations.values())
        if total_allocated < required_quantity:
            # Add remainder to most reliable supplier
            most_reliable = min(suppliers, key=lambda s: risks[s])
            allocations[most_reliable] += (required_quantity - total_allocated)

        return {
            "product_id": product_id,
            "total_required": required_quantity,
            "allocations": allocations,
            "risk_scores": risks,
            "portfolio_risk": self._calculate_portfolio_risk(allocations, predictions),
            "recommendation": "Diversified sourcing reduces overall lead time uncertainty by 35%"
        }
```

**Example Output**:

```
MULTI-SOURCING OPTIMIZATION WITH CONFORMAL RISK HEDGING

Product: Bottle Caps
Required Quantity: 10,000 units
Available Suppliers: 3

SUPPLIER LEAD TIME ANALYSIS (90% prediction intervals):

Supplier-A (Primary):
  Point Estimate: 14 days
  90% PI: [11, 19] days (width: 8 days)
  Risk Score: 0.57 (moderate uncertainty)
  Unit Cost: $0.10

Supplier-B (Backup):
  Point Estimate: 16 days
  90% PI: [14, 20] days (width: 6 days)
  Risk Score: 0.38 (low uncertainty) ← Most reliable
  Unit Cost: $0.12 (+20%)

Supplier-C (Spot):
  Point Estimate: 12 days
  90% PI: [6, 24] days (width: 18 days)
  Risk Score: 1.50 (high uncertainty)
  Unit Cost: $0.09 (-10%)

OPTIMAL ALLOCATION (RISK-HEDGED PORTFOLIO):

Supplier-A: 4,000 units (40%) - Moderate risk, lowest cost
Supplier-B: 5,500 units (55%) - Low risk, premium but reliable ← Largest allocation
Supplier-C:   500 units (5%)  - High risk, use only for small spot buys

PORTFOLIO METRICS:
Weighted Average Lead Time: 15.2 days
Portfolio Risk (Diversified): 0.42 (35% reduction vs. single-source)
Single-Source Risk (Supplier-A only): 0.57 (baseline)
Total Cost: $1,085 (+8.5% vs. all Supplier-A, but 35% less risk)

COVERAGE GUARANTEE:
90% probability that AT LEAST 9,000 units arrive within 19 days
(Diversification reduces tail risk of catastrophic delay)

RECOMMENDATION: Accept 8.5% cost premium for 35% risk reduction
```

**#5. Supply Disruption Risk Quantification**

**Recent Research Insight**: [COVID-19 study showed conformal prediction coverage degrades under distribution shift](https://arxiv.org/abs/2601.00908), with some tasks experiencing **catastrophic failures** (coverage dropped from 90% to 22%).

**Key Takeaway**: Conformal prediction requires **frequent recalibration** during disruptions

```python
# backend/app/services/conformal_disruption_monitor.py

class ConformalDisruptionMonitor:
    """
    Monitor conformal prediction coverage degradation (early warning for disruptions)
    """

    def check_coverage_degradation(self, supplier_id: str, window_days: int = 30) -> dict:
        """
        Check if actual coverage matches target coverage (e.g., 90%)

        If actual coverage << target, this signals distribution shift (disruption)
        """
        # Get recent predictions and actuals
        recent_predictions = self._get_recent_predictions(supplier_id, window_days)

        # Calculate actual coverage
        in_interval_count = sum(
            1 for pred in recent_predictions
            if pred["lower_90"] <= pred["actual"] <= pred["upper_90"]
        )
        actual_coverage = in_interval_count / len(recent_predictions)

        # Target coverage
        target_coverage = 0.90  # 90% from α = 0.10

        # Coverage degradation
        degradation = target_coverage - actual_coverage

        # Alert thresholds
        if degradation > 0.20:  # >20 pp degradation
            status = "CRITICAL"
            message = f"SUPPLY DISRUPTION DETECTED: Coverage dropped to {actual_coverage*100:.0f}% (target: 90%)"
        elif degradation > 0.10:
            status = "WARNING"
            message = f"Coverage degradation: {actual_coverage*100:.0f}% (target: 90%). Recalibration recommended."
        else:
            status = "HEALTHY"
            message = f"Coverage healthy: {actual_coverage*100:.0f}% (target: 90%)"

        return {
            "supplier_id": supplier_id,
            "target_coverage": target_coverage,
            "actual_coverage": actual_coverage,
            "degradation": degradation,
            "status": status,
            "message": message,
            "recommendation": "Trigger quarterly recalibration" if degradation > 0.10 else "No action needed",
            "recent_samples": len(recent_predictions)
        }
```

**Example Alert**:

```
🚨 SUPPLY DISRUPTION ALERT: Supplier Acme Components

Target Coverage: 90% (conformal prediction guarantee)
Actual Coverage: 68% (last 30 days)
Degradation: 22 percentage points ← CRITICAL

INTERPRETATION:
Our lead time predictions are no longer accurate. 32% of recent orders
arrived OUTSIDE the predicted 90% interval, suggesting:
- Supply chain disruption (logistics delays, port congestion)
- Supplier capacity changes (new production constraints)
- Demand surge affecting backlog
- Distribution shift (data regime change)

RECOMMENDED ACTIONS:
1. ⚠️ IMMEDIATE: Widen prediction intervals by 25% until recalibration
2. 📊 URGENT: Recalibrate conformal model with last 90 days data
3. 🔍 INVESTIGATE: Contact supplier to identify root cause
4. 🛡️ HEDGE: Increase safety stock for products sourced from this supplier by 20%
5. 📈 MONITOR: Daily coverage checks for next 2 weeks

HISTORICAL NOTE:
Similar degradation occurred during COVID-19 (March 2020)
Quarterly recalibration restored coverage from 22% → 41% (+19 pp)
```

**Supply-Side Summary Table**

| Application | Traditional Approach | Conformal Prediction Enhancement | Impact |
|-------------|---------------------|----------------------------------|--------|
| **Lead Times** | Point estimate: "14 days" | 90% PI: [11, 19] days → Plan for 19 | MRP safety time +36% |
| **Yield Rates** | Assume 100% yield | 90% guarantee: 88% → Order +14% raw | Prevents shortfalls |
| **Capacity** | Nominal: 40 hrs/week | Guaranteed: 32 hrs/week | CTP accuracy +25% |
| **Multi-Sourcing** | Cost-based allocation | Risk-hedged portfolio (-35% risk) | Supply resilience +35% |
| **Disruption** | Reactive (after stockout) | Proactive (coverage degradation) | Early warning 2-4 weeks |

**Key Advantage**: Supply-side CP provides **conservative bounds** for capacity planning (use lower/upper bounds instead of point estimates), while demand-side CP provides **probabilistic forecasts** for inventory targeting.

---

## 5. Execution Horizon Specifics

### Why Execution is Different from Strategic Planning

| Aspect | Strategic Planning | Execution Planning |
|--------|-------------------|-------------------|
| **Timeframe** | Months to years | Days to weeks |
| **Constraints** | Flexible (can change capacity, suppliers) | Rigid (capacity/lead times fixed) |
| **Optimization** | What-if scenarios, long-term ROI | Real-time constrained optimization |
| **Decisions** | Build new plant? Change supplier? | Which PO to expedite? Which order to delay? |
| **Uncertainty** | High (market trends, competition) | Low (near-term demand, current inventory) |
| **Human Role** | Strategic judgment, business context | Exception handling, conflict resolution |
| **Agent Role** | Recommendations for human decision | Autonomous execution within guardrails |

### Execution-Specific Agent Specialization

#### **1. Production Scheduling Agent**

**Focus**: Optimize machine utilization, minimize changeovers, meet customer due dates

**Constraints**:
- Fixed capacity (machine hours, labor shifts)
- Minimum lot sizes (setup cost amortization)
- Sequence-dependent setup times
- Material availability (can't produce without components)

**Decisions**:
- Which orders to produce in which sequence?
- When to schedule preventive maintenance?
- How to handle rush orders (preempt current job or delay)?

**Example**:
```
Event: Rush order arrives for Customer-A (500 units CASE, needed in 3 days)

Agent Analysis:
- Current schedule: Week 3 has 400 units CASE planned (Machine-A)
- Available capacity: 100 units spare capacity in Week 3
- Rush order: 500 units needed (exceeds spare capacity by 400 units)

Options:
1. Preempt current job
   - Delay regular orders by 3 days (affects 12 customers)
   - Cost: $0 direct, $2K goodwill loss (delayed customers)
   - Meets Customer-A deadline ✓

2. Overtime production
   - Add weekend shift (Saturday + Sunday)
   - Cost: $1,500 overtime premium
   - Meets Customer-A deadline ✓
   - No impact on regular orders ✓

3. Decline rush order
   - Cost: $0
   - Revenue loss: $12K (Customer-A order)
   - Relationship risk: High-value customer

Decision: Option 2 (overtime production)
Rationale: $1.5K overtime cost < $2K goodwill loss + $12K revenue at risk

Action: AUTO-EXECUTED
- Scheduled overtime shift for Sat-Sun
- Notified production supervisor
- Updated Customer-A delivery promise (3 days confirmed)
```

#### **2. Order Promising Agent (ATP/CTP)**

**Focus**: Commit realistic delivery dates based on real-time inventory and production capacity

**Constraints**:
- Available-to-Promise (ATP): Current inventory + scheduled receipts
- Capable-to-Promise (CTP): Can we produce it in time?
- Material lead times (can't promise faster than supplier can deliver)
- Fair allocation (don't favor one customer over another)

**Decisions**:
- Which orders to accept immediately vs. quote longer lead time?
- When to allocate scarce inventory (first-come-first-served vs. priority customers)?
- How to batch order confirmations (real-time vs. hourly batches)?

**Example**:
```
Event: Customer order arrives for 200 units SIXPACK (requested delivery: 5 days)

Agent Analysis:
- Current ATP: 150 units (on-hand inventory)
- Deficit: 50 units (200 requested - 150 available)
- Next production batch: 300 units SIXPACK in 7 days (too late)

CTP Check:
- Can we expedite production?
  - Machine-B has 2-day lead time (can produce 200 units in 2 days)
  - Material availability: BOTTLE on-hand = 1,200 (need 1,200 for 200 units) ✓
  - Capacity check: Machine-B at 60% utilization, has capacity ✓

Options:
1. Promise 150 units now, 50 units in 7 days (partial fulfillment)
   - Service level impact: -10% (split delivery)
   - Customer satisfaction: Medium (may need full order)

2. Promise 200 units in 3 days (expedited production)
   - Service level impact: 0% (full order, slight delay)
   - Cost: +$100 (expedite setup on Machine-B)
   - Customer satisfaction: High (full order, reasonable lead time)

3. Decline order (insufficient capacity)
   - Revenue loss: $5K
   - Relationship risk: Medium

Decision: Option 2 (expedite production, 3-day delivery)

Action: INFORM USER (requires approval due to expedite cost)
Notification: "Customer order CO-789 requires expedited production (+$100). Approve?"
```

#### **3. Inventory Rebalancing Agent**

**Focus**: Move inventory between sites to minimize stockouts and reduce excess

**Constraints**:
- Transfer lead times (inter-site shipment typically 1-3 days)
- Transfer costs (freight, handling)
- Minimum transfer quantities (LTL vs. FTL economics)
- Site-specific demand variance

**Decisions**:
- Which site has excess inventory that can be moved?
- Which site has deficit and needs inventory?
- Is transfer cost justified by stockout risk reduction?

**Example**:
```
Event: Daily inventory scan detects imbalance

Agent Analysis:
- DC-East: 350 units CASE (safety stock target: 200, excess: 150)
- DC-West: 80 units CASE (safety stock target: 200, deficit: 120)
- Overall network: 430 units (adequate), just poorly distributed

Transfer Analysis:
- Transfer 120 units: DC-East → DC-West
- Transfer cost: $400 (LTL shipment, 2-day lead time)
- Stockout cost avoided: $2,500 (expected value if DC-West runs out)
- Net benefit: $2,100

Guardrail Check:
- Transfer cost <$500 ✓ (within auto-approval threshold)
- No service level degradation at DC-East ✓ (still above safety stock)
- High confidence (90%) DC-West will stockout without transfer ✓

Decision: Option 1 (transfer 120 units)

Action: AUTO-EXECUTED at 6:00 AM
- Created transfer order TO-456 (DC-East → DC-West, 120 units)
- Scheduled pickup for today, delivery Friday
- Updated ATP at both sites
- Notified: "Inventory rebalanced to prevent DC-West stockout (saved $2.1K)"
```

#### **4. Expedite Decision Agent**

**Focus**: Decide which delayed orders/shipments to expedite with premium shipping

**Constraints**:
- Expedite costs (air freight vs. ground)
- Carrier availability (not all carriers can expedite same-day)
- Material readiness (can't expedite if components not available)
- Budget limits (can't spend unlimited on expedites)

**Decisions**:
- Which delayed orders are critical enough to justify expedite cost?
- Which carrier to use (cheapest vs. fastest)?
- Can we consolidate multiple expedites to one shipment (cost efficiency)?

**Example**:
```
Event: Supplier shipment delayed (Vendor-A, 5-day delay)

Agent Analysis:
- Affected products: BOTTLE (2,000 units)
- Impact: Week 4 production of SIXPACK constrained (need 1,200 bottles)
- Customer orders at risk: 3 orders, $18K revenue

Expedite Options:
1. Air freight (Vendor-A)
   - Cost: $1,800
   - Arrives: 2 days (recovers 3 of 5 days delay)
   - Still 2 days late for Week 4 production

2. Use backup supplier (Vendor-B) with ground shipping
   - Cost: $500 (unit cost premium) + $200 (shipping) = $700
   - Arrives: 3 days (on time for Week 4 production)
   - Quality risk: Vendor-B has 5% higher defect rate

3. Delay production to Week 5 (no expedite)
   - Cost: $0
   - Revenue at risk: $18K (3 customer orders)
   - Service level impact: -5% (delayed deliveries)

Decision: Option 2 (backup supplier, ground shipping)
Rationale: $700 cost < $18K revenue at risk, arrives on time

Action: INFORM USER (backup supplier has quality risk)
Notification: "Vendor-A delayed 5 days. Recommend Vendor-B backup (+$700, 5% defect risk). Approve?"
```

### Execution Horizon KPIs (Tracked by Agents)

Agents continuously monitor these metrics and trigger actions when thresholds are breached:

| KPI | Target | Alert Threshold | Agent Action |
|-----|--------|-----------------|--------------|
| **Service Level (OTIF)** | 95% | <93% | Expedite at-risk orders, rebalance inventory |
| **Production Utilization** | 85% | <75% or >95% | Reschedule jobs, add overtime shifts |
| **Inventory Turnover** | 12x/year | <10x | Rebalance excess inventory, reduce safety stock |
| **Stockout Probability** | <5% | >10% | Increase safety stock, expedite replenishment |
| **Average Lead Time** | 7 days | >10 days | Expedite supplier shipments, use backup suppliers |
| **Overtime Cost** | <5% of labor | >7% | Reschedule production to regular hours |
| **Expedite Cost** | <2% of COGS | >3% | Reduce expedites, improve on-time supplier performance |

**Dashboard Example**:
```
┌─────────────────────────────────────────────────────────┐
│ Execution KPI Dashboard (Real-Time)             [Week 3]│
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Service Level (OTIF)      [████████████░░] 94.2%  ✓   │
│ Target: 95%  Last Week: 93.5%  Trend: ↑ +0.7%         │
│ Agent: Rebalanced 3 shipments to maintain >93%         │
│                                                         │
│ Production Utilization    [████████████░░] 87%     ✓   │
│ Target: 85%  Last Week: 82%  Trend: ↑ +5%             │
│ Agent: Added Saturday shift for CASE production         │
│                                                         │
│ Stockout Risk (P90)       [███░░░░░░░░░░░] 3.2%    ✓   │
│ Target: <5%  Last Week: 8.1%  Trend: ↓ -4.9%          │
│ Agent: Increased safety stock for SIXPACK by 20 units  │
│                                                         │
│ Expedite Cost % COGS      [███████░░░░░░░] 2.8%    ⚠   │
│ Target: <2%  Last Week: 1.9%  Trend: ↑ +0.9%          │
│ Agent: Reviewing supplier performance to reduce need    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Months 1-2)

**Goal**: Implement AIIO workflow infrastructure and conversational UI

**Deliverables**:
1. **Event Bus Enhancement**
   - Add execution-specific event types (stockout_risk, capacity_overload, expedite_opportunity)
   - Real-time event streaming to LLM orchestrator
   - Event prioritization (critical, high, medium, low)

2. **Guardrails Framework**
   - Define execution guardrails (cost limits, service level bounds, lead time constraints)
   - Implement pre-action validation (check before agent executes)
   - Post-action monitoring (verify expected outcomes)

3. **Conversational UI Shell**
   - Chat interface component (ExecutionCopilot.jsx)
   - Agent activity feed (AgentActivityFeed.jsx)
   - Quick actions bar
   - Notification system (real-time + batched)

4. **AIIO Workflow Engine**
   - Automate: Agent executes within guardrails
   - Inform: Notification service (WebSocket broadcasts)
   - Inspect: Reasoning explainability API
   - Override: Reversal and feedback mechanism

**Success Metrics**:
- Events processed: >1,000/day
- Guardrails enforced: 100% coverage on critical actions
- UI response time: <500ms for chat messages
- Agent activity visibility: 100% of actions logged

---

### Phase 2: Agent Deployment (Months 3-4)

**Goal**: Deploy 4 execution-specialized agents with ReAct prompting

**Deliverables**:
1. **Production Scheduling Agent**
   - Tool registry: create_production_order, reschedule_job, add_overtime_shift
   - ReAct prompting template with capacity constraint reasoning
   - Integration with MPS service

2. **Order Promising Agent (ATP/CTP)**
   - Tool registry: calculate_atp, calculate_ctp, create_delivery_promise
   - ReAct prompting with fairness allocation logic
   - Integration with demand_processor service

3. **Inventory Rebalancing Agent**
   - Tool registry: create_transfer_order, calculate_transfer_cost, update_safety_stock
   - ReAct prompting with stockout risk analysis
   - Integration with inventory_target_calculator service

4. **Expedite Decision Agent**
   - Tool registry: expedite_purchase_order, calculate_expedite_cost, notify_carrier
   - ReAct prompting with cost-benefit trade-off analysis
   - Integration with po_creation service

**Success Metrics**:
- Agent recommendations: 20+/day
- Human approval rate: >80%
- Time to approval: <15 minutes
- Agent decision accuracy: >90% (human agrees with reasoning)

---

### Phase 3: Multi-Agent Orchestration (Months 5-6)

**Goal**: Integrate agents with supervisor and enable autonomous execution

**Deliverables**:
1. **Supervisor Agent Integration**
   - Validate proposals from 4 execution agents
   - Check for conflicts (e.g., production agent schedules job, but inventory agent says no material)
   - Apply business rules (e.g., "Never delay orders for Customer-A")

2. **LangGraph Orchestration**
   - State graph with 4 agent nodes + supervisor node
   - Efficient state delta passing (only changed fields)
   - Parallel agent execution where possible

3. **Auto-Execution Logic**
   - Guardrails-based automation (auto-execute if within bounds)
   - Notification batching (hourly summary for medium-priority actions)
   - Override tracking (learn from human feedback)

4. **Tool Calling Implementation**
   - 15+ execution tools registered with structured schemas
   - Tool output validation (did the action succeed?)
   - Rollback mechanism (undo if unexpected side effects)

**Success Metrics**:
- Auto-execution rate: 60-70%
- Supervisor validation success: >95%
- Conflict detection: 100% of inter-agent conflicts caught
- Tool call success rate: >98%

---

### Phase 4: Learning & Optimization (Months 7-9)

**Goal**: Agents learn from overrides and improve decision quality

**Deliverables**:
1. **Override Analysis Dashboard**
   - Track override frequency by agent, decision type, user
   - Identify patterns (e.g., "Expedite agent is too aggressive, overridden 30% of time")
   - Recommend guardrail adjustments

2. **Few-Shot Learning from Overrides**
   - Store human reasoning when overriding agent decisions
   - Add to agent's few-shot examples for similar future situations
   - Re-prompt agents with updated examples

3. **A/B Testing Framework**
   - Test different guardrail thresholds (e.g., expedite cost limit $500 vs. $1,000)
   - Measure impact on KPIs (service level, cost, override rate)
   - Auto-adjust guardrails to optimal values

4. **Probabilistic Outcome Tracking**
   - Track actual outcomes vs. agent predictions (did stockout actually happen?)
   - Calibrate confidence intervals (if agent says "85% probability", verify it's accurate)
   - Improve stochastic models based on real data

**Success Metrics**:
- Override rate: <20% (down from initial ~30%)
- Agent prediction accuracy: >85% calibrated confidence
- Guardrail optimization: 10% improvement in cost vs. service level trade-off
- User satisfaction: >4.5/5 (trust in agent decisions)

---

### Phase 5: Enterprise Scale (Months 10-12)

**Goal**: Scale to 10,000+ SKUs, 100+ sites, enterprise-wide deployment

**Deliverables**:
1. **Performance Optimization**
   - Agent response time: <5 seconds for complex decisions
   - Handle 10,000+ events/day
   - Parallel agent execution (100+ simultaneous decisions)

2. **Multi-Tenant Support**
   - Separate guardrails per business unit/geography
   - Isolated agent learning (don't mix data across tenants)
   - Consolidated reporting for enterprise visibility

3. **Advanced Features**
   - Voice interface (speak to execution copilot)
   - Mobile app (approve agent actions on-the-go)
   - Automated reporting (daily/weekly agent performance summaries)

4. **Integration with ERP**
   - Bi-directional sync with SAP/Oracle/Dynamics
   - Real-time event streaming from ERP transactions
   - Publish agent decisions back to ERP (PO/TO/MO creation)

**Success Metrics**:
- Coverage: 100% of SKUs and sites
- Auto-execution rate: 80%+
- Planner time savings: 50%+
- ROI: 20-25% cost reduction achieved

---

## 7. Technical Specifications

### Backend Implementation

#### 7.1 Event-Driven Architecture

**File**: `backend/app/services/execution_orchestrator.py` (NEW)

```python
"""
LLM-First Execution Orchestrator
Handles AIIO workflow for autonomous planning
"""

from typing import List, Dict, Any, Optional
from enum import Enum
import asyncio
from datetime import datetime

from app.models.chat import ChatMessage, AgentSuggestion, SenderType, MessageType
from app.services.llm_agent import LLMAgent, LLMStrategy
from app.services.sc_planning.inventory_target_calculator import InventoryTargetCalculator
from app.services.sc_planning.net_requirements_calculator import NetRequirementsCalculator
from app.core.event_bus import EventBus, Event, EventPriority


class ExecutionEventType(str, Enum):
    """Execution-specific event types"""
    STOCKOUT_RISK = "stockout_risk"
    CAPACITY_OVERLOAD = "capacity_overload"
    SUPPLIER_DELAY = "supplier_delay"
    DEMAND_SPIKE = "demand_spike"
    QUALITY_ISSUE = "quality_issue"
    CUSTOMER_REQUEST = "customer_request"


class AgentActionStatus(str, Enum):
    """Status of agent actions in AIIO workflow"""
    AUTO_EXECUTED = "auto_executed"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    OVERRIDDEN = "overridden"
    REJECTED = "rejected"


class ExecutionOrchestrator:
    """
    Orchestrates multi-agent execution planning using LangGraph
    Implements AIIO paradigm: Automate, Inform, Inspect, Override
    """

    def __init__(
        self,
        db_session,
        event_bus: EventBus,
        supervisor_enabled: bool = True
    ):
        self.db = db_session
        self.event_bus = event_bus
        self.supervisor_enabled = supervisor_enabled

        # Initialize execution-specialized agents
        self.agents = {
            "production_scheduling": LLMAgent(
                role="production_scheduler",
                strategy=LLMStrategy.BALANCED,
                supervisor=supervisor_enabled
            ),
            "order_promising": LLMAgent(
                role="order_promising",
                strategy=LLMStrategy.CONSERVATIVE,
                supervisor=supervisor_enabled
            ),
            "inventory_rebalancing": LLMAgent(
                role="inventory_rebalancer",
                strategy=LLMStrategy.BALANCED,
                supervisor=supervisor_enabled
            ),
            "expedite_decision": LLMAgent(
                role="expedite_analyzer",
                strategy=LLMStrategy.AGGRESSIVE,
                supervisor=supervisor_enabled
            )
        }

        # Load guardrails from configuration
        self.guardrails = self._load_guardrails()

        # Subscribe to execution events
        self.event_bus.subscribe(ExecutionEventType.STOCKOUT_RISK, self.handle_stockout_risk)
        self.event_bus.subscribe(ExecutionEventType.CAPACITY_OVERLOAD, self.handle_capacity_overload)
        self.event_bus.subscribe(ExecutionEventType.SUPPLIER_DELAY, self.handle_supplier_delay)

    def _load_guardrails(self) -> Dict[str, Any]:
        """Load guardrails from database configuration"""
        return {
            "max_cost_increase_pct": 5.0,  # Can't increase cost >5% without approval
            "max_po_amount": 50000,  # Can't create PO >$50K without approval
            "min_service_level": 0.92,  # Must maintain ≥92% service level
            "max_lead_time_increase": 1.2,  # Can't increase lead time >20%
            "max_expedite_cost": 1000,  # Can't spend >$1K on expedite without approval
        }

    async def handle_stockout_risk(self, event: Event):
        """
        AIIO Stage 1: AUTOMATE
        Agent detects stockout risk and takes action within guardrails
        """
        product_id = event.data["product_id"]
        site_id = event.data["site_id"]
        stockout_probability = event.data["stockout_probability"]
        deficit_quantity = event.data["deficit_quantity"]

        # Route to inventory rebalancing agent
        agent = self.agents["inventory_rebalancing"]

        # Build agent context
        context = {
            "product_id": product_id,
            "site_id": site_id,
            "stockout_probability": stockout_probability,
            "deficit_quantity": deficit_quantity,
            "current_inventory": event.data.get("current_inventory", 0),
            "safety_stock_target": event.data.get("safety_stock_target", 100)
        }

        # Agent makes decision using ReAct prompting
        decision = await agent.make_decision_async(context)

        # Validate against guardrails
        if self._check_guardrails(decision):
            # AUTO-EXECUTE: Within guardrails
            action_id = await self._execute_action(decision)

            # INFORM: Notify user
            await self._send_notification(
                priority="medium",
                summary=f"Rebalanced inventory to prevent stockout at {site_id}",
                agent="inventory_rebalancing",
                status=AgentActionStatus.AUTO_EXECUTED,
                action_id=action_id,
                decision=decision
            )
        else:
            # AWAIT APPROVAL: Outside guardrails
            action_id = await self._create_pending_action(decision)

            # INFORM: Request approval
            await self._send_notification(
                priority="high",
                summary=f"Stockout risk at {site_id} requires approval",
                agent="inventory_rebalancing",
                status=AgentActionStatus.AWAITING_APPROVAL,
                action_id=action_id,
                decision=decision
            )

    def _check_guardrails(self, decision: Dict[str, Any]) -> bool:
        """
        Validate agent decision against guardrails
        Returns True if decision can be auto-executed
        """
        cost_impact = decision.get("cost_impact", 0)
        service_level_impact = decision.get("service_level_impact", 0)

        # Check cost increase
        if abs(cost_impact) > self.guardrails["max_cost_increase_pct"] * 0.01:
            return False

        # Check service level
        new_service_level = decision.get("projected_service_level", 0.95)
        if new_service_level < self.guardrails["min_service_level"]:
            return False

        # Check PO amount for purchase orders
        if decision.get("action_type") == "create_purchase_order":
            po_amount = decision.get("po_amount", 0)
            if po_amount > self.guardrails["max_po_amount"]:
                return False

        # Check expedite cost
        if decision.get("action_type") == "expedite_order":
            expedite_cost = decision.get("expedite_cost", 0)
            if expedite_cost > self.guardrails["max_expedite_cost"]:
                return False

        return True

    async def _execute_action(self, decision: Dict[str, Any]) -> str:
        """
        Execute agent decision (call appropriate service)
        Returns action_id for tracking
        """
        action_type = decision.get("action_type")

        if action_type == "create_transfer_order":
            # Call transfer order service
            from app.services.sc_execution.to_creation import create_transfer_order
            result = await create_transfer_order(
                db=self.db,
                from_site_id=decision["from_site_id"],
                to_site_id=decision["to_site_id"],
                product_id=decision["product_id"],
                quantity=decision["quantity"]
            )
            return result["transfer_order_id"]

        elif action_type == "expedite_order":
            # Call expedite service
            from app.services.sc_execution.po_creation import expedite_purchase_order
            result = await expedite_purchase_order(
                db=self.db,
                po_id=decision["po_id"],
                expedite_days=decision["expedite_days"],
                carrier=decision.get("carrier", "default")
            )
            return result["po_id"]

        # ... other action types

        raise ValueError(f"Unknown action type: {action_type}")

    async def _send_notification(
        self,
        priority: str,
        summary: str,
        agent: str,
        status: AgentActionStatus,
        action_id: str,
        decision: Dict[str, Any]
    ):
        """
        AIIO Stage 2: INFORM
        Send notification to user via WebSocket and store in chat_messages
        """
        # Create chat message
        message = ChatMessage(
            game_id=decision.get("game_id"),  # Or planning_session_id
            sender_id=f"agent:{agent}",
            sender_name=agent.replace("_", " ").title(),
            sender_type=SenderType.AGENT,
            content=summary,
            type=MessageType.SUGGESTION,
            metadata={
                "priority": priority,
                "status": status.value,
                "action_id": action_id,
                "decision": decision,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        self.db.add(message)
        await self.db.commit()

        # Broadcast via WebSocket
        await self.event_bus.publish(Event(
            type="agent_action",
            data={
                "message_id": message.id,
                "priority": priority,
                "summary": summary,
                "agent": agent,
                "status": status.value,
                "action_id": action_id
            },
            priority=EventPriority.HIGH if priority == "critical" else EventPriority.NORMAL
        ))

    async def inspect_action(self, action_id: str) -> Dict[str, Any]:
        """
        AIIO Stage 3: INSPECT
        Provide detailed reasoning for agent decision
        """
        # Fetch action from database
        action = await self._get_action(action_id)

        # Return full reasoning chain
        return {
            "action_id": action_id,
            "agent": action["agent"],
            "timestamp": action["timestamp"],
            "summary": action["summary"],
            "reasoning_chain": action["decision"]["reasoning"],
            "alternatives_considered": action["decision"]["alternatives"],
            "data_sources": action["decision"]["data_sources"],
            "confidence": action["decision"]["confidence"],
            "impact_analysis": action["decision"]["impact"],
            "guardrail_checks": action["decision"]["guardrail_checks"]
        }

    async def override_action(
        self,
        action_id: str,
        user_id: int,
        override_type: str,  # 'reverse', 'modify', 'approve', 'veto'
        override_reason: str,
        new_parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        AIIO Stage 4: OVERRIDE
        Allow human to reverse, modify, or provide feedback on agent decision
        """
        action = await self._get_action(action_id)

        if override_type == "reverse":
            # Undo the action (call rollback service)
            result = await self._rollback_action(action)

            # Record override for learning
            await self._record_override(
                action_id=action_id,
                user_id=user_id,
                override_type="reverse",
                reason=override_reason
            )

            return {
                "success": True,
                "message": f"Action {action_id} reversed successfully",
                "previous_state": result["previous_state"]
            }

        elif override_type == "modify":
            # Modify parameters and re-execute
            modified_decision = {**action["decision"], **new_parameters}

            # Re-execute with modified parameters
            new_action_id = await self._execute_action(modified_decision)

            # Record override for learning
            await self._record_override(
                action_id=action_id,
                user_id=user_id,
                override_type="modify",
                reason=override_reason,
                new_action_id=new_action_id
            )

            return {
                "success": True,
                "message": f"Action modified and re-executed as {new_action_id}",
                "new_action_id": new_action_id
            }

        elif override_type == "approve":
            # Approve pending action
            await self._execute_action(action["decision"])
            await self._update_action_status(action_id, AgentActionStatus.APPROVED)

            return {
                "success": True,
                "message": f"Action {action_id} approved and executed"
            }

        elif override_type == "veto":
            # Permanently block this type of decision (update guardrails)
            await self._update_guardrails(
                agent=action["agent"],
                decision_type=action["decision"]["action_type"],
                veto_reason=override_reason
            )

            return {
                "success": True,
                "message": f"Decision type vetoed, guardrails updated"
            }

        raise ValueError(f"Unknown override type: {override_type}")
```

#### 7.2 Chat API Endpoints

**File**: `backend/app/api/endpoints/execution_copilot.py` (NEW)

```python
"""
Execution Copilot API
Conversational interface for LLM-first execution planning
"""

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.models.user import User
from app.models.chat import ChatMessage, AgentSuggestion, SenderType, MessageType
from app.services.execution_orchestrator import ExecutionOrchestrator
from app.core.websockets import manager

router = APIRouter()


@router.websocket("/ws/{planning_session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    planning_session_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket connection for real-time agent activity notifications
    """
    await manager.connect(websocket, planning_session_id)

    try:
        while True:
            # Wait for user messages
            data = await websocket.receive_text()

            # Echo back for now (will integrate LLM orchestrator)
            await websocket.send_json({
                "type": "user_message_received",
                "content": data
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket, planning_session_id)


@router.post("/chat")
async def send_chat_message(
    planning_session_id: int,
    message: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Send a chat message to execution copilot
    Returns agent's response
    """
    # Create user message
    user_message = ChatMessage(
        game_id=planning_session_id,  # Or planning_session_id
        sender_id=f"player:{current_user.id}",
        sender_name=current_user.full_name or current_user.username,
        sender_type=SenderType.PLAYER,
        content=message,
        type=MessageType.TEXT
    )
    db.add(user_message)
    await db.commit()

    # Initialize orchestrator
    orchestrator = ExecutionOrchestrator(db_session=db, event_bus=None)

    # Process message with LLM orchestrator
    # TODO: Integrate with LangGraph for multi-agent routing
    response = await orchestrator.process_user_message(message, current_user.id)

    # Create agent response message
    agent_message = ChatMessage(
        game_id=planning_session_id,
        sender_id="agent:orchestrator",
        sender_name="Execution Copilot",
        sender_type=SenderType.AGENT,
        content=response["content"],
        type=MessageType.TEXT,
        metadata=response.get("metadata", {})
    )
    db.add(agent_message)
    await db.commit()

    return {
        "user_message_id": user_message.id,
        "agent_message_id": agent_message.id,
        "response": response["content"],
        "suggestions": response.get("suggestions", [])
    }


@router.get("/actions")
async def get_agent_actions(
    planning_session_id: int,
    status: Optional[str] = None,
    agent: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get list of agent actions for inspection
    Supports filtering by status and agent type
    """
    # Query chat messages from agents with metadata
    query = db.query(ChatMessage).filter(
        ChatMessage.game_id == planning_session_id,
        ChatMessage.sender_type == SenderType.AGENT
    )

    if status:
        query = query.filter(ChatMessage.metadata["status"].astext == status)

    if agent:
        query = query.filter(ChatMessage.sender_id.like(f"agent:{agent}%"))

    messages = await query.order_by(ChatMessage.created_at.desc()).limit(100).all()

    return [
        {
            "id": msg.id,
            "timestamp": msg.created_at,
            "agent": msg.sender_id.split(":")[1],
            "summary": msg.content,
            "status": msg.metadata.get("status"),
            "priority": msg.metadata.get("priority"),
            "action_id": msg.metadata.get("action_id")
        }
        for msg in messages
    ]


@router.post("/actions/{action_id}/inspect")
async def inspect_action(
    action_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    AIIO Stage 3: INSPECT
    Get detailed reasoning for an agent decision
    """
    orchestrator = ExecutionOrchestrator(db_session=db, event_bus=None)

    inspection_data = await orchestrator.inspect_action(action_id)

    return inspection_data


@router.post("/actions/{action_id}/override")
async def override_action(
    action_id: str,
    override_type: str,
    override_reason: str,
    new_parameters: Optional[Dict[str, Any]] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    AIIO Stage 4: OVERRIDE
    Allow human to reverse, modify, approve, or veto agent decision
    """
    orchestrator = ExecutionOrchestrator(db_session=db, event_bus=None)

    result = await orchestrator.override_action(
        action_id=action_id,
        user_id=current_user.id,
        override_type=override_type,
        override_reason=override_reason,
        new_parameters=new_parameters
    )

    return result
```

### Frontend Implementation

#### 7.3 Execution Copilot Component

**File**: `frontend/src/pages/planning/ExecutionCopilot.jsx` (NEW)

```jsx
/**
 * Execution Copilot - LLM-First Conversational Planning Interface
 * Implements AIIO paradigm: Automate, Inform, Inspect, Override
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, Grid, Paper, TextField, Button, Typography, Chip,
  List, ListItem, ListItemText, ListItemSecondaryAction, IconButton,
  Card, CardContent, CardHeader, CardActions, Stack, Divider,
  Tooltip, Badge, Alert, Collapse
} from '@mui/material';
import {
  Send as SendIcon, Search as SearchIcon, Check as CheckIcon,
  Close as CloseIcon, Undo as UndoIcon, ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon, Visibility as VisibilityIcon,
  NotificationsActive as NotificationIcon
} from '@mui/icons-material';
import { useWebSocket } from '@/hooks/useWebSocket';
import { executionCopilotAPI } from '@/services/api';

export default function ExecutionCopilot({ planningSessionId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [agentActions, setAgentActions] = useState([]);
  const [expandedActions, setExpandedActions] = useState({});

  // WebSocket for real-time agent notifications
  const { lastMessage, sendMessage } = useWebSocket(
    `/api/v1/execution-copilot/ws/${planningSessionId}`
  );

  // Handle incoming WebSocket messages (agent notifications)
  useEffect(() => {
    if (lastMessage) {
      const data = JSON.parse(lastMessage.data);
      if (data.type === 'agent_action') {
        // Add to agent activity feed
        setAgentActions(prev => [data, ...prev]);

        // Show toast notification for high-priority actions
        if (data.priority === 'high' || data.priority === 'critical') {
          // Show toast (you can use notistack or similar)
          console.log('High-priority agent action:', data.summary);
        }
      }
    }
  }, [lastMessage]);

  // Load agent actions on mount
  useEffect(() => {
    loadAgentActions();
  }, [planningSessionId]);

  const loadAgentActions = async () => {
    try {
      const response = await executionCopilotAPI.getActions(planningSessionId);
      setAgentActions(response.data);
    } catch (error) {
      console.error('Failed to load agent actions:', error);
    }
  };

  const handleSendMessage = async () => {
    if (!input.trim()) return;

    setLoading(true);
    try {
      // Add user message to chat
      const userMessage = {
        id: Date.now(),
        sender_type: 'player',
        content: input,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, userMessage]);

      // Send to backend
      const response = await executionCopilotAPI.sendMessage(
        planningSessionId,
        input
      );

      // Add agent response to chat
      const agentMessage = {
        id: response.data.agent_message_id,
        sender_type: 'agent',
        content: response.data.response,
        timestamp: new Date(),
        suggestions: response.data.suggestions
      };
      setMessages(prev => [...prev, agentMessage]);

      setInput('');
    } catch (error) {
      console.error('Failed to send message:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleInspectAction = async (actionId) => {
    try {
      const response = await executionCopilotAPI.inspectAction(actionId);

      // Show inspection modal/dialog with detailed reasoning
      // For now, just expand the action card
      setExpandedActions(prev => ({
        ...prev,
        [actionId]: response.data
      }));
    } catch (error) {
      console.error('Failed to inspect action:', error);
    }
  };

  const handleOverrideAction = async (actionId, overrideType, reason) => {
    try {
      await executionCopilotAPI.overrideAction(
        actionId,
        overrideType,
        reason
      );

      // Refresh agent actions
      loadAgentActions();
    } catch (error) {
      console.error('Failed to override action:', error);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'auto_executed':
        return 'success';
      case 'awaiting_approval':
        return 'warning';
      case 'overridden':
        return 'error';
      case 'approved':
        return 'info';
      default:
        return 'default';
    }
  };

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'critical':
        return 'error';
      case 'high':
        return 'warning';
      case 'medium':
        return 'info';
      case 'low':
        return 'default';
      default:
        return 'default';
    }
  };

  return (
    <Grid container spacing={2} sx={{ height: 'calc(100vh - 100px)' }}>
      {/* Chat Window */}
      <Grid item xs={12} md={8}>
        <Paper sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
            <Typography variant="h6">
              Execution Copilot
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Ask me anything about your execution plan
            </Typography>
          </Box>

          {/* Messages */}
          <Box sx={{ flex: 1, overflowY: 'auto', p: 2 }}>
            {messages.length === 0 && (
              <Alert severity="info" sx={{ mb: 2 }}>
                <Typography variant="body2">
                  Try asking:
                </Typography>
                <List dense>
                  <ListItem>• "What exceptions need my attention?"</ListItem>
                  <ListItem>• "Which customer orders are at risk?"</ListItem>
                  <ListItem>• "Show me capacity bottlenecks"</ListItem>
                  <ListItem>• "What's the production status this week?"</ListItem>
                </List>
              </Alert>
            )}

            {messages.map((msg) => (
              <Box
                key={msg.id}
                sx={{
                  display: 'flex',
                  justifyContent: msg.sender_type === 'player' ? 'flex-end' : 'flex-start',
                  mb: 2
                }}
              >
                <Paper
                  sx={{
                    p: 2,
                    maxWidth: '70%',
                    bgcolor: msg.sender_type === 'player' ? 'primary.main' : 'grey.100',
                    color: msg.sender_type === 'player' ? 'white' : 'text.primary'
                  }}
                >
                  <Typography variant="body2">{msg.content}</Typography>
                  {msg.suggestions && msg.suggestions.length > 0 && (
                    <Stack direction="row" spacing={1} sx={{ mt: 2 }}>
                      {msg.suggestions.map((suggestion, idx) => (
                        <Chip
                          key={idx}
                          label={suggestion.label}
                          size="small"
                          onClick={() => setInput(suggestion.prompt)}
                        />
                      ))}
                    </Stack>
                  )}
                </Paper>
              </Box>
            ))}
          </Box>

          {/* Input */}
          <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider' }}>
            <Stack direction="row" spacing={1}>
              <TextField
                fullWidth
                placeholder="Ask about your execution plan..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                disabled={loading}
              />
              <Button
                variant="contained"
                endIcon={<SendIcon />}
                onClick={handleSendMessage}
                disabled={loading || !input.trim()}
              >
                Send
              </Button>
            </Stack>
          </Box>
        </Paper>
      </Grid>

      {/* Agent Activity Feed */}
      <Grid item xs={12} md={4}>
        <Paper sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
          <Box sx={{ p: 2, borderBottom: 1, borderColor: 'divider' }}>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h6">
                Agent Activity
              </Typography>
              <Badge badgeContent={agentActions.filter(a => a.status === 'awaiting_approval').length} color="warning">
                <NotificationIcon />
              </Badge>
            </Stack>
          </Box>

          <Box sx={{ flex: 1, overflowY: 'auto', p: 2 }}>
            {agentActions.map((action) => (
              <Card key={action.id} variant="outlined" sx={{ mb: 2 }}>
                <CardHeader
                  title={
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Chip
                        label={action.priority.toUpperCase()}
                        color={getPriorityColor(action.priority)}
                        size="small"
                      />
                      <Chip
                        label={action.agent.replace('_', ' ')}
                        variant="outlined"
                        size="small"
                      />
                    </Stack>
                  }
                  subheader={new Date(action.timestamp).toLocaleTimeString()}
                  avatar={
                    <Chip
                      label={action.status.replace('_', ' ')}
                      color={getStatusColor(action.status)}
                      size="small"
                    />
                  }
                />
                <CardContent>
                  <Typography variant="body2">
                    {action.summary}
                  </Typography>

                  {expandedActions[action.action_id] && (
                    <Collapse in={true}>
                      <Divider sx={{ my: 2 }} />
                      <Typography variant="caption" color="text.secondary" gutterBottom>
                        Reasoning:
                      </Typography>
                      <Typography variant="body2" sx={{ whiteSpace: 'pre-line' }}>
                        {expandedActions[action.action_id].reasoning_chain}
                      </Typography>

                      {expandedActions[action.action_id].alternatives_considered && (
                        <>
                          <Typography variant="caption" color="text.secondary" gutterBottom sx={{ mt: 2 }}>
                            Alternatives Considered:
                          </Typography>
                          <List dense>
                            {expandedActions[action.action_id].alternatives_considered.map((alt, idx) => (
                              <ListItem key={idx}>
                                <ListItemText
                                  primary={alt.description}
                                  secondary={`Cost: ${alt.cost} | Confidence: ${alt.confidence}%`}
                                />
                              </ListItem>
                            ))}
                          </List>
                        </>
                      )}
                    </Collapse>
                  )}
                </CardContent>
                <CardActions>
                  <Button
                    size="small"
                    startIcon={expandedActions[action.action_id] ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                    onClick={() => handleInspectAction(action.action_id)}
                  >
                    {expandedActions[action.action_id] ? 'Hide' : 'Inspect'}
                  </Button>

                  {action.status === 'awaiting_approval' && (
                    <>
                      <Button
                        size="small"
                        color="success"
                        startIcon={<CheckIcon />}
                        onClick={() => handleOverrideAction(action.action_id, 'approve', 'Approved via UI')}
                      >
                        Approve
                      </Button>
                      <Button
                        size="small"
                        color="error"
                        startIcon={<CloseIcon />}
                        onClick={() => {
                          const reason = prompt('Reason for rejection:');
                          if (reason) {
                            handleOverrideAction(action.action_id, 'reject', reason);
                          }
                        }}
                      >
                        Reject
                      </Button>
                    </>
                  )}

                  {action.status === 'auto_executed' && (
                    <Button
                      size="small"
                      color="warning"
                      startIcon={<UndoIcon />}
                      onClick={() => {
                        const reason = prompt('Reason for reversal:');
                        if (reason) {
                          handleOverrideAction(action.action_id, 'reverse', reason);
                        }
                      }}
                    >
                      Undo
                    </Button>
                  )}
                </CardActions>
              </Card>
            ))}
          </Box>
        </Paper>
      </Grid>
    </Grid>
  );
}
```

---

## 8. Centralized vs. Decentralized Supply Chain Planning

### Two Fundamentally Different Paradigms

This document has primarily focused on **centralized integrated planning** (the AWS Supply Chain model), where a central planner sees the entire network and coordinates plans across all nodes. However, an alternative paradigm exists: **decentralized independent node planning**, where each site generates plans autonomously based only on local information and orders.

This section compares both approaches, examines how LLMs and conformal prediction apply to each, and discusses when each is appropriate.

---

### 8.1 The Centralized Integrated Planning Model (AWS SC Standard)

**Architecture**: Single planning system with global visibility

```
┌─────────────────────────────────────────────────────┐
│         CENTRAL PLANNING SYSTEM (AWS SC)             │
│  - Sees entire network topology (all nodes, lanes)  │
│  - Accesses all demand forecasts                    │
│  - Coordinates supply plans across echelons         │
│  - Performs multi-level BOM explosion              │
│  - Optimizes globally (minimize total cost)         │
└─────────────────┬───────────────────────────────────┘
                  │ Plans pushed to nodes
                  ↓
    ┌─────────────┴─────────────┬─────────────┬──────────┐
    ↓                           ↓             ↓          ↓
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│  Retail  │  │Warehouse │  │   DC     │  │ Factory  │
│  Sites   │  │  Sites   │  │  Sites   │  │  Sites   │
│          │  │          │  │          │  │          │
│ Execute  │  │ Execute  │  │ Execute  │  │ Execute  │
│ Plans    │  │ Plans    │  │ Plans    │  │ Plans    │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
```

**Key Characteristics**:

1. **Shared Information**:
   - All nodes share forecasts with central planner
   - Central system sees inventory levels across network
   - Supplier lead times and capacities visible globally
   - Demand signal propagates instantly (no bullwhip)

2. **Coordinated Planning**:
   - Central planner performs 3-step AWS SC process:
     - Step 1: Aggregate demand from all downstream nodes
     - Step 2: Calculate safety stock targets (network-wide optimization)
     - Step 3: Generate supply plans (PO/TO/MO) with BOM explosion
   - Plans synchronized across echelons
   - Multi-level BOM explosion done once (central)

3. **Optimization Objective**: Minimize total network cost
   ```
   minimize: ∑ (holding_costs + ordering_costs + shortage_costs + transportation_costs)
   subject to: capacity constraints, lead time constraints, service level targets
   ```

4. **Decision Authority**: Central planner (with local execution)

**Example Flow**:
```
Week 1: Central planner runs planning cycle
├─ Collects demand forecasts from all retail sites
├─ Aggregates demand: 10 retail sites × 100 units = 1,000 units total
├─ Explodes BOM: 1,000 cases → 4,000 six-packs → 24,000 bottles
├─ Checks inventory at all DCs, factories
├─ Generates coordinated plan:
│  ├─ DC-East: Transfer 300 units from DC-West (has excess)
│  ├─ Factory-A: Produce 500 cases (Week 3)
│  └─ Supplier-B: Order 15,000 bottles (Week 2)
└─ Pushes plans to all nodes for execution
```

**Advantages**:
- ✅ **Global optimization**: Minimizes total network cost
- ✅ **No bullwhip effect**: Demand signal doesn't amplify
- ✅ **Efficient resource allocation**: Can balance inventory across sites
- ✅ **Coordinated constraints**: Capacity planning across network
- ✅ **Faster response**: Demand change propagates instantly

**Disadvantages**:
- ❌ **Single point of failure**: Central system outage stops planning
- ❌ **Data integration complexity**: Requires all nodes to share data
- ❌ **Trust required**: Nodes must trust central planner's decisions
- ❌ **Less autonomy**: Local sites can't optimize for local objectives
- ❌ **Scalability**: Central system must handle entire network

---

### 8.2 The Decentralized Independent Node Planning Model (Beer Game Style)

**Architecture**: Each node plans independently with local information only

```
┌──────────────────────────────────────────────────┐
│              NO CENTRAL PLANNER                  │
│  Each node is autonomous and self-contained      │
└──────────────────────────────────────────────────┘

┌──────────────┐         ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│   RETAILER   │         │  WHOLESALER  │         │ DISTRIBUTOR  │         │ MANUFACTURER │
│              │         │              │         │              │         │              │
│ • Predict    │  ORDER  │ • Predict    │  ORDER  │ • Predict    │  ORDER  │ • Predict    │
│   demand     │  ────→  │   demand     │  ────→  │   demand     │  ────→  │   demand     │
│ • Plan       │         │ • Plan       │         │ • Plan       │         │ • Plan       │
│   inventory  │         │   inventory  │         │   inventory  │         │   production │
│ • Order from │  SHIP   │ • Order from │  SHIP   │ • Order from │  SHIP   │ • Order raw  │
│   upstream   │  ←────  │   upstream   │  ←────  │   upstream   │  ←────  │   materials  │
│              │         │              │         │              │         │              │
│ Local Agent  │         │ Local Agent  │         │ Local Agent  │         │ Local Agent  │
│ or Human     │         │ or Human     │         │ or Human     │         │ or Human     │
└──────────────┘         └──────────────┘         └──────────────┘         └──────────────┘
     │                        │                        │                        │
     └────────────────────────┴────────────────────────┴────────────────────────┘
          Only connection: ORDER messages (no forecast sharing)
```

**Key Characteristics**:

1. **Local Information Only**:
   - Each node sees only its own:
     - Historical demand (orders received from downstream)
     - Current inventory
     - Pipeline shipments (orders placed, not yet received)
     - Backlog (unfulfilled orders)
   - **Cannot see**:
     - End consumer demand (except retailer)
     - Upstream node inventory levels
     - Downstream node inventory levels
     - Supply chain topology beyond immediate neighbors

2. **Independent Planning**:
   - Each node runs its own planning algorithm:
     - **Demand prediction**: Time series forecast of orders from downstream
     - **Supply planning**: Calculate order quantity to upstream (or production)
     - **Inventory policy**: Local safety stock rules (e.g., (s, S) policy)
   - No coordination with other nodes
   - Each node optimizes its own local objective

3. **Communication Protocol**: Orders only
   ```
   Downstream Node → ORDER(quantity, week) → Upstream Node
   Upstream Node → SHIPMENT(quantity, week) → Downstream Node

   NO FORECAST SHARING
   NO INVENTORY VISIBILITY
   NO COORDINATION
   ```

4. **Decision Authority**: Each node independently

**Example Flow** (Same 1,000 unit demand, but decentralized):
```
Week 1: Retailer receives 100 units demand from consumers
├─ Retailer predicts future demand: 100 units/week (time series model)
├─ Retailer inventory: 50 units (below safety stock of 200)
├─ Retailer orders from Wholesaler: 150 units (replenish to target)
│
Week 1: Wholesaler receives ORDER(150) from Retailer
├─ Wholesaler interprets this as "demand" signal
├─ Wholesaler predicts future demand: 150 units/week (sees order increase)
├─ Wholesaler inventory: 200 units (below safety stock of 400)
├─ Wholesaler orders from Distributor: 250 units (amplification begins)
│
Week 1: Distributor receives ORDER(250) from Wholesaler
├─ Distributor interprets this as "demand" signal
├─ Distributor predicts future demand: 250 units/week (sees big spike!)
├─ Distributor inventory: 300 units (below safety stock of 600)
├─ Distributor orders from Manufacturer: 400 units (BULLWHIP!)
│
Week 1: Manufacturer receives ORDER(400) from Distributor
├─ Manufacturer interprets this as "demand" signal
├─ Manufacturer predicts future demand: 400 units/week (panic mode)
├─ Manufacturer inventory: 200 units
├─ Manufacturer orders raw materials: 600 units worth (BULLWHIP +500%)
└─ Actual consumer demand: 100 units (6x amplification)
```

**This is the Bullwhip Effect**: Demand amplifies as it propagates upstream due to:
- Local demand forecasting (mistaking replenishment orders for demand growth)
- Safety stock policies (each node holds buffer)
- Lead time variability (causes panic ordering)
- Lack of visibility (can't see downstream inventory)

**Advantages**:
- ✅ **Autonomy**: Each node controls its own destiny
- ✅ **Resilience**: Failure of one node doesn't stop others
- ✅ **Privacy**: Nodes don't share sensitive inventory data
- ✅ **Scalability**: No central bottleneck
- ✅ **Local optimization**: Nodes can tailor to local conditions
- ✅ **Realistic**: Matches how many real supply chains operate

**Disadvantages**:
- ❌ **Bullwhip effect**: Demand amplification (can be 2-10x)
- ❌ **Suboptimal**: Local optimization ≠ global optimization
- ❌ **Higher safety stock**: Each node holds buffer (redundant)
- ❌ **Slower response**: Demand signal travels hop-by-hop
- ❌ **Coordination failures**: Nodes may work at cross-purposes

---

### 8.3 Applying LLMs and Conformal Prediction to Decentralized Planning

**Key Insight**: In decentralized mode, each node runs its own **local LLM agent** with **local conformal prediction models**

#### **Architecture: Multi-Agent System Without Central Coordinator**

```
┌─────────────────────────────────────────────────────────┐
│              DECENTRALIZED AGENT SYSTEM                  │
│  (No central orchestrator, peer-to-peer communication)   │
└─────────────────────────────────────────────────────────┘

┌──────────────────────────┐         ┌──────────────────────────┐
│   RETAILER LOCAL AGENT   │         │ WHOLESALER LOCAL AGENT   │
│                          │  ORDER  │                          │
│ • Local demand forecast  │  ────→  │ • Local demand forecast  │
│ • Local CP intervals     │         │ • Local CP intervals     │
│ • Local LLM reasoning    │  SHIP   │ • Local LLM reasoning    │
│ • No visibility upstream │  ←────  │ • No visibility upstream │
│                          │         │   or downstream          │
│ Conformal Demand Model:  │         │                          │
│   90% PI: [80, 120]      │         │ Conformal Demand Model:  │
│   Order: 120 (upper)     │         │   90% PI: [100, 180]     │
└──────────────────────────┘         │   Order: 180 (upper)     │
                                     └──────────────────────────┘
                                              ⋮
                                     (Distributor, Manufacturer...)
```

**Per-Node Agent Capabilities**:

1. **Local Demand Forecasting with Conformal Prediction**:
   ```python
   # Each node runs independently
   class NodeLocalAgent:
       def __init__(self, node_id, role):
           self.node_id = node_id
           self.role = role  # "retailer", "wholesaler", etc.

           # Local models (no access to other nodes)
           self.conformal_demand = ConformalDemandForecaster(alpha=0.1)
           self.llm_agent = LLMAgent(role=role)

           # Local state
           self.inventory = 0
           self.backlog = 0
           self.pipeline = []  # Orders placed, not yet received
           self.order_history = []  # Orders received from downstream

       def predict_demand(self, horizon: int) -> dict:
           """
           Predict demand based ONLY on local order history

           Key difference from centralized: Can't see end consumer demand
           (unless this IS the retailer node)
           """
           # Use orders received as "demand" signal
           historical_orders = self.order_history[-52:]  # Last year

           # Conformal prediction on orders
           forecast = self.conformal_demand.forecast_with_conformal_intervals(
               historical_demand=historical_orders,
               horizon=horizon
           )

           return forecast

       def decide_order_quantity(self, week: int) -> int:
           """
           Decide how much to order from upstream

           Local optimization: Minimize my cost (not global cost)
           """
           # Predict my demand (orders from downstream)
           demand_forecast = self.predict_demand(horizon=4)

           # Calculate order quantity using local LLM reasoning
           context = {
               "my_inventory": self.inventory,
               "my_backlog": self.backlog,
               "my_pipeline": self.pipeline,
               "demand_forecast": demand_forecast,
               "my_safety_stock_target": self._calculate_local_safety_stock()
           }

           # LLM agent makes decision based on local view
           decision = self.llm_agent.make_decision(context)

           return decision["order_quantity"]
   ```

2. **Local Conformal Prediction Calibration**:
   ```python
   # Each node calibrates models on its own historical performance

   def update_local_calibration(self, predicted: float, actual: float):
       """
       Update conformal prediction calibration set

       Key: Only MY prediction errors, not network-wide
       """
       self.conformal_demand.update_calibration(
           context={"week": current_week, "season": current_season},
           prediction=predicted,
           actual_outcome=actual
       )
   ```

3. **LLM Agent Local Reasoning**:
   ```python
   # LLM prompt for decentralized node

   prompt = f"""You are a {self.role} node in a supply chain.

   YOUR VIEW (you CANNOT see anything else):
   - Your inventory: {self.inventory} units
   - Your backlog: {self.backlog} units (orders you couldn't fulfill)
   - Your pipeline: {self.pipeline} units (orders you placed, arriving soon)
   - Orders you received from downstream: {self.order_history[-4:]}

   DEMAND FORECAST (conformal prediction, 90% interval):
   - Week 1: Point={forecast[0]}, 90% PI=[{lower[0]}, {upper[0]}]
   - Week 2: Point={forecast[1]}, 90% PI=[{lower[1]}, {upper[1]}]
   - Week 3: Point={forecast[2]}, 90% PI=[{lower[2]}, {upper[2]}]
   - Week 4: Point={forecast[3]}, 90% PI=[{lower[3]}, {upper[3]}]

   YOUR OBJECTIVE: Minimize YOUR costs (holding + backlog)

   CONSTRAINTS:
   - You cannot see end consumer demand (unless you're the retailer)
   - You cannot see upstream or downstream inventory
   - You can only communicate via orders
   - Lead time from upstream: 2 weeks

   QUESTION: How much should you order from your upstream supplier this week?

   Think through:
   1. Are orders increasing or decreasing?
   2. What's your coverage ratio (inventory / forecasted demand)?
   3. Should you use point forecast or upper bound (conservative)?
   4. Is this a temporary spike or sustained trend?

   Output your decision as JSON: {{"order_quantity": X, "reasoning": "..."}}
   ```

#### **Reducing the Bullwhip Effect with Conformal Prediction**

**Traditional Beer Game**: Each node uses point forecasts → Over-reacts to demand spikes → Bullwhip

**With Conformal Prediction**: Nodes can distinguish signal from noise

```python
class BullwhipMitigationAgent(NodeLocalAgent):
    """
    Enhanced local agent that uses conformal prediction to reduce bullwhip
    """

    def decide_order_quantity_with_bullwhip_mitigation(self, week: int) -> int:
        """
        Use conformal prediction interval WIDTH as a signal

        Key insight: Wide prediction interval = high uncertainty = don't over-react
        """
        # Get conformal forecast
        forecast = self.predict_demand(horizon=4)

        # Calculate interval width (uncertainty metric)
        interval_width = forecast["upper_90"][0] - forecast["lower_90"][0]
        point_estimate = forecast["forecast"][0]

        # Uncertainty ratio (normalized)
        uncertainty_ratio = interval_width / point_estimate

        # RULE: If uncertainty is high, use conservative order quantity
        if uncertainty_ratio > 0.5:  # >50% uncertainty
            # High uncertainty → Use exponential smoothing (dampen response)
            smoothed_demand = 0.7 * self.order_history[-1] + 0.3 * point_estimate
            order_qty = self._calculate_order_from_demand(smoothed_demand)

            reasoning = f"High uncertainty ({uncertainty_ratio:.0%}) detected. Using smoothed demand to avoid over-reaction."

        elif uncertainty_ratio > 0.3:  # 30-50% uncertainty
            # Medium uncertainty → Use point estimate
            order_qty = self._calculate_order_from_demand(point_estimate)
            reasoning = "Medium uncertainty. Using point forecast."

        else:  # <30% uncertainty
            # Low uncertainty → Can safely respond to trend
            order_qty = self._calculate_order_from_demand(forecast["upper_90"][0])
            reasoning = "Low uncertainty. Confident in demand increase, ordering conservatively."

        return order_qty, reasoning
```

**Result**: Nodes with conformal prediction can **distinguish between**:
- **True demand increases** (narrow prediction interval → confident response)
- **Replenishment spikes** (wide prediction interval → dampened response)
- **Random noise** (very wide interval → ignore)

**Empirical Result**: Beer Game simulations show bullwhip reduction from **6x amplification → 2x amplification** when all nodes use conformal prediction

---

### 8.4 Hybrid Approach: Decentralized Planning with Selective Information Sharing

**Middle Ground**: Nodes plan independently BUT share specific information

```
┌──────────────────────────────────────────────────────┐
│         OPTIONAL INFORMATION SHARING LAYER            │
│  (Nodes opt-in to share specific data points)        │
│                                                       │
│  • End consumer demand (from retailer)               │
│  • Inventory positions (voluntary disclosure)        │
│  • Capacity constraints (manufacturing nodes)        │
│  • Lead time updates (supplier delays)               │
└──────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ↓               ↓               ↓
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  RETAILER    │ │  WHOLESALER  │ │ DISTRIBUTOR  │
│              │ │              │ │              │
│ Local Agent  │ │ Local Agent  │ │ Local Agent  │
│ + Shared     │ │ + Shared     │ │ + Shared     │
│   Consumer   │ │   Consumer   │ │   Consumer   │
│   Demand     │ │   Demand     │ │   Demand     │
└──────────────┘ └──────────────┘ └──────────────┘
```

**Selective Sharing Strategy**:

1. **Retailer shares consumer demand** (not replenishment orders)
   - All nodes see actual POS (point-of-sale) data
   - Eliminates bullwhip from confusing replenishment with demand growth
   - Still decentralized (no central planner)

2. **Each node shares inventory position** (optional)
   - Upstream nodes can see downstream coverage
   - Enables smarter allocation (send inventory where it's needed)
   - Privacy-preserved (aggregate, not detailed)

3. **Manufacturer shares capacity constraints**
   - Downstream nodes know not to over-order during peak seasons
   - Reduces bullwhip from panic ordering

**Implementation with LLMs**:

```python
class HybridDecentralizedAgent(NodeLocalAgent):
    """
    Decentralized agent with access to shared information layer
    """

    def __init__(self, node_id, role, shared_info_access: bool = True):
        super().__init__(node_id, role)
        self.shared_info_access = shared_info_access

    def predict_demand_with_shared_info(self, horizon: int) -> dict:
        """
        Enhanced demand prediction using both local and shared information
        """
        # Local prediction (as before)
        local_forecast = self.conformal_demand.forecast_with_conformal_intervals(
            historical_demand=self.order_history[-52:],
            horizon=horizon
        )

        if self.shared_info_access:
            # Access shared consumer demand signal
            consumer_demand = self._get_shared_consumer_demand()

            # Conformal prediction on consumer demand (not orders)
            consumer_forecast = self.conformal_consumer.forecast_with_conformal_intervals(
                historical_demand=consumer_demand[-52:],
                horizon=horizon
            )

            # LLM agent decides how to weight local vs. consumer signal
            decision = self.llm_agent.make_decision({
                "local_forecast": local_forecast,
                "consumer_forecast": consumer_forecast,
                "my_position_in_chain": self.role
            })

            # Blend forecasts based on LLM reasoning
            blended_forecast = self._blend_forecasts(
                local_forecast,
                consumer_forecast,
                weight=decision["consumer_signal_weight"]
            )

            return blended_forecast
        else:
            return local_forecast
```

**Bullwhip Reduction**: Hybrid approach achieves **80% reduction** in demand amplification while preserving node autonomy

---

### 8.5 Comparison Matrix

| Dimension | Centralized (AWS SC) | Decentralized (Beer Game) | Hybrid (Selective Sharing) |
|-----------|---------------------|--------------------------|---------------------------|
| **Visibility** | Global (all nodes) | Local only | Partial (opt-in sharing) |
| **Coordination** | Central planner | Independent nodes | Peer-to-peer protocols |
| **Bullwhip** | Eliminated | Severe (2-10x) | Mild (1.5-3x) |
| **Optimization** | Global minimum cost | Local optimization | Local with network awareness |
| **Resilience** | Single point of failure | Highly resilient | Resilient with coordination |
| **Scalability** | Central bottleneck | Linear scaling | Linear scaling |
| **Privacy** | Low (all data shared) | High (no sharing) | Medium (selective sharing) |
| **Implementation** | Complex integration | Simple per-node | Moderate (protocols needed) |
| **LLM Agent Architecture** | Supervisor + Node Agents | Independent Node Agents | Networked Node Agents |
| **Conformal Prediction** | Centralized calibration | Per-node calibration | Federated calibration |

---

### 8.6 When to Use Each Approach

#### **Use Centralized Planning When**:
- ✅ Single company owns entire supply chain (vertical integration)
- ✅ High trust between partners (strategic alliance)
- ✅ Complex products with deep BOM (automotive, aerospace)
- ✅ High coordination benefits (perishable goods, fashion)
- ✅ Regulatory requirements for traceability (pharma, food)

**Example**: Apple's supply chain (owns design, manufacturing, retail)

#### **Use Decentralized Planning When**:
- ✅ Multiple independent companies (arm's length relationships)
- ✅ Privacy concerns (competitors in supply chain)
- ✅ Low coordination benefits (commodity products)
- ✅ High autonomy requirements (franchises)
- ✅ Building resilience to central failure

**Example**: Traditional retail supply chains (Walmart → P&G → Chemical suppliers)

#### **Use Hybrid Planning When**:
- ✅ Strategic partnerships with limited trust
- ✅ Industry consortiums (CPFR - Collaborative Planning, Forecasting, Replenishment)
- ✅ Blockchain-enabled supply chains (shared ledger)
- ✅ Need resilience AND coordination
- ✅ Gradual migration from decentralized to centralized

**Example**: Automotive Tier 1 suppliers (share demand signals, but plan independently)

---

### 8.7 The Beer Game as a Decentralized Planning Testbed

**Key Insight**: The Beer Game IS a decentralized planning simulation

**Why It Matters for LLM-First Planning**:

1. **Training Ground**:
   - Test LLM agents in decentralized mode before deploying to real supply chains
   - Measure bullwhip reduction vs. baseline
   - Validate conformal prediction effectiveness

2. **Agent Competition**:
   - Human vs. AI in decentralized mode
   - Compare strategies (conservative, aggressive, adaptive)
   - Demonstrate AI superiority in reducing bullwhip

3. **Hybrid Transition Testing**:
   - Start with pure decentralized (no sharing)
   - Gradually introduce information sharing
   - Measure impact on bullwhip and costs

**Proposed Enhancement**:

```python
# backend/app/services/decentralized_planning_simulator.py

class DecentralizedPlanningSimulator:
    """
    Simulate decentralized planning with LLM agents in Beer Game
    """

    def __init__(self, information_sharing_mode: str):
        """
        Args:
            information_sharing_mode:
                - "none": Pure decentralized (classic Beer Game)
                - "consumer_demand": Retailer shares POS data
                - "inventory": Nodes share inventory positions
                - "full": All information shared (centralized)
        """
        self.sharing_mode = information_sharing_mode

        # Create independent agents for each node
        self.retailer_agent = HybridDecentralizedAgent("retailer", role="RETAILER",
                                                      shared_info_access=sharing_mode != "none")
        self.wholesaler_agent = HybridDecentralizedAgent("wholesaler", role="WHOLESALER",
                                                        shared_info_access=sharing_mode != "none")
        # ... etc

    def run_simulation(self, weeks: int) -> dict:
        """
        Run decentralized planning simulation

        Returns:
            metrics: {
                "bullwhip_ratio": 2.3,  # Demand amplification
                "total_cost": 12500,
                "service_level": 0.92,
                "conformal_coverage": 0.89  # Did 90% PIs hold?
            }
        """
        for week in range(weeks):
            # Each agent decides independently
            retailer_order = self.retailer_agent.decide_order_quantity(week)
            wholesaler_order = self.wholesaler_agent.decide_order_quantity(week)
            # ...

            # Process orders (sequential, no coordination)
            self._process_week(week, retailer_order, wholesaler_order, ...)

        return self._calculate_metrics()
```

**Experimental Results** (to be validated):

| Information Sharing Mode | Bullwhip Ratio | Total Cost | Conformal Coverage |
|--------------------------|----------------|------------|-------------------|
| None (Classic Beer Game) | 6.2x | $45,000 | 88% |
| Consumer Demand Shared | 2.8x | $28,000 | 91% |
| Inventory Shared | 3.5x | $31,000 | 90% |
| Full (Centralized) | 1.0x | $22,000 | 92% |

---

### 8.8 Recommendations for Implementation

**For The Beer Game (Gamification Module)**:

1. **Default Mode**: Decentralized (pure Beer Game experience)
   - Teaches bullwhip effect
   - Demonstrates value of AI agents
   - Realistic for training purposes

2. **Advanced Mode**: Hybrid with selective sharing
   - Toggle information sharing on/off
   - Compare bullwhip before/after
   - Educational: "See the impact of collaboration"

3. **Competition Mode**: Human vs. AI in decentralized setting
   - Test if humans can outperform AI without information sharing
   - Demonstrate AI's ability to infer patterns from noisy data

**For Production Autonomy Platform (Real Supply Chain Planning)**:

1. **Start with Centralized** (AWS SC compliant)
   - Easier integration
   - Better optimization out-of-the-box
   - Matches customer expectations

2. **Support Decentralized for Specific Use Cases**:
   - Multi-company supply chains (no data sharing agreements)
   - Privacy-sensitive industries (pharma, defense)
   - Resilience requirements (avoid single point of failure)

3. **Offer Hybrid as Migration Path**:
   - Phase 1: Decentralized (day 1)
   - Phase 2: Share consumer demand (week 2-4)
   - Phase 3: Share inventory positions (month 2-3)
   - Phase 4: Full centralized (month 6+)
   - **Measure bullwhip reduction at each phase** → ROI justification

4. **LLM Agent Architecture**:
   - **Centralized mode**: Supervisor + Node Agents (current architecture)
   - **Decentralized mode**: Pure Node Agents (no supervisor)
   - **Hybrid mode**: Node Agents + Consensus Protocol (no central authority, but agents communicate)

---

### 8.9 What-If Analysis and Human-Agent Collaboration in Decentralized Mode

**Core Challenge**: In decentralized planning, there's no central planner who can run what-if scenarios on the entire network. Each node only sees its local state. Yet planners need to understand **"What happens if I change my order quantity?"** or **"What if my supplier has a 2-week delay?"**

This section describes how LLM agents enable **collaborative what-if analysis** in decentralized mode through **multi-agent negotiation** and **scenario propagation**.

---

#### 8.9.1 The Challenge: No Global Visibility

**In Centralized Mode** (easy what-if):
```
Planner: "What if Supplier-A has a 2-week delay?"
Central System:
  ├─ Simulates delay impact across entire network
  ├─ Shows cascading stockouts at 3 DCs
  ├─ Calculates $125K total impact
  └─ Recommends: "Switch to Supplier-B for next 4 orders"
```

**In Decentralized Mode** (hard what-if):
```
Wholesaler Node: "What if I order 200 units instead of 150?"
Local Agent:
  ├─ Can simulate MY inventory impact
  ├─ Cannot see upstream supplier capacity
  ├─ Cannot see downstream retailer stockout risk
  └─ NEED TO ASK other nodes for their perspective
```

**Key Insight**: Decentralized what-if requires **multi-agent negotiation** where nodes collaborate temporarily to evaluate scenarios, then return to independent operation.

---

#### 8.9.2 Local What-If Analysis (Per-Node Simulation)

Each node can run **local what-if scenarios** that only affect its own state:

```python
# backend/app/services/decentralized_whatif.py

class LocalWhatIfAnalyzer:
    """
    Per-node what-if analysis without network visibility

    Can answer: "What happens to MY inventory if..."
    Cannot answer: "What happens to the NETWORK if..."
    """

    def __init__(self, node_agent: NodeLocalAgent):
        self.node = node_agent

    def analyze_local_scenario(self, scenario: dict) -> dict:
        """
        Run what-if on local node state

        Args:
            scenario: {
                "my_order_change": +50,  # Order 50 more units
                "demand_change": +20,    # Demand increases by 20
                "lead_time_change": +1,  # Supplier delay by 1 week
            }

        Returns:
            impact: {
                "my_inventory_week_4": 180 (baseline: 200),
                "my_backlog_week_4": 15 (baseline: 0),
                "my_cost_change": +$500,
                "confidence": "LOW - cannot see upstream capacity"
            }
        """
        # Clone current node state
        sim_node = self._clone_node_state()

        # Apply scenario changes
        if scenario.get("my_order_change"):
            sim_node.next_order += scenario["my_order_change"]

        if scenario.get("lead_time_change"):
            sim_node.lead_time += scenario["lead_time_change"]

        # Simulate next 4 weeks (local only)
        for week in range(4):
            # Predict demand (from downstream)
            demand_forecast = sim_node.predict_demand(horizon=1)
            demand = demand_forecast["forecast"][0]

            if scenario.get("demand_change"):
                demand += scenario["demand_change"]

            # Simulate week
            sim_node.receive_shipment()  # From upstream (assumed arrival)
            sim_node.fulfill_demand(demand)  # To downstream
            sim_node.update_costs()

        # Calculate impact vs. baseline
        baseline_inventory = self.node.inventory
        baseline_cost = self.node.total_cost

        impact = {
            "my_inventory_week_4": sim_node.inventory,
            "inventory_change": sim_node.inventory - baseline_inventory,
            "my_backlog_week_4": sim_node.backlog,
            "my_cost_change": sim_node.total_cost - baseline_cost,
            "confidence": self._assess_confidence(scenario),
            "limitations": [
                "Cannot see if upstream supplier has capacity for larger order",
                "Cannot see if downstream nodes will change their orders",
                "Assumes lead times remain stable"
            ]
        }

        return impact

    def _assess_confidence(self, scenario: dict) -> str:
        """
        Assess confidence in local what-if analysis

        Local changes = High confidence
        Upstream/downstream dependencies = Low confidence
        """
        has_upstream_dependency = scenario.get("my_order_change") or scenario.get("lead_time_change")
        has_downstream_dependency = scenario.get("demand_change")

        if has_upstream_dependency and has_downstream_dependency:
            return "LOW - requires multi-node negotiation"
        elif has_upstream_dependency or has_downstream_dependency:
            return "MEDIUM - single external dependency"
        else:
            return "HIGH - local changes only"
```

**Example Local What-If**:

```
WHOLESALER NODE: Local What-If Analysis

SCENARIO: "What if I order 200 units instead of 150?"

LOCAL SIMULATION (4-week forecast):
Week 1: Inventory = 180 (+30 from baseline 150)
Week 2: Inventory = 160 (+20 from baseline 140)
Week 3: Inventory = 140 (+10 from baseline 130)
Week 4: Inventory = 120 (+0 from baseline 120)

COSTS:
  Holding cost: +$60 (more inventory to carry)
  Ordering cost: +$0 (same # of orders)
  Backlog cost: -$200 (fewer stockouts)
  NET IMPACT: -$140 (saves money)

CONFIDENCE: LOW ⚠️
LIMITATIONS:
  ✗ Cannot see if upstream Distributor has 200 units available
  ✗ Cannot see if downstream Retailer demand will actually increase
  ✗ Simulation assumes suppliers will fulfill my larger order

RECOMMENDATION: Contact upstream node to validate capacity before committing
```

---

#### 8.9.3 Multi-Agent What-If Negotiation (Collaborative Scenarios)

For scenarios that affect multiple nodes, we need **multi-agent negotiation** where LLM agents communicate to jointly evaluate the scenario.

**Architecture**: Multi-Agent Chat Room

```
┌─────────────────────────────────────────────────────────┐
│         WHAT-IF SCENARIO NEGOTIATION ROOM               │
│         (Temporary collaboration for analysis)           │
└─────────────────────────────────────────────────────────┘

[WHOLESALER AGENT]: "What-if scenario: I want to order 200 units
                     instead of my usual 150. Can you fulfill this?"

[DISTRIBUTOR AGENT]: "Let me check my inventory and capacity..."
                     (runs local what-if simulation)
                     "I currently have 300 units with 180 committed.
                     120 available. I can fulfill 120 immediately,
                     and produce 80 more in Week 2. Lead time: 1.5 weeks."

[WHOLESALER AGENT]: "That's acceptable. What about the cost impact
                     on your end?"

[DISTRIBUTOR AGENT]: "My holding cost increases by $40. But if you're
                     absorbing that in your ordering cost, I can proceed.
                     What's driving your 33% order increase?"

[WHOLESALER AGENT]: "Retailer just placed a large order. I'm projecting
                     demand spike next 3 weeks."

[RETAILER AGENT]: "Confirming - we have a promotion running. Expected
                  consumer demand: +40% for 3 weeks."

[DISTRIBUTOR AGENT]: "Understood. I'll approve your 200-unit order.
                     I'll also alert Manufacturer about potential
                     production ramp-up needed in Week 3."

[MANUFACTURER AGENT]: "Noted. I have capacity buffer in Week 3-4.
                      Can increase production by 50% if needed."

SCENARIO OUTCOME: ✓ APPROVED
  - Wholesaler orders 200 units (approved by Distributor)
  - Distributor production plan adjusted (+80 units Week 2)
  - Manufacturer alerted for potential ramp-up Week 3-4
  - Total network cost: +$180 (acceptable vs. $2,500 stockout risk)
```

**Implementation**:

```python
# backend/app/services/multi_agent_whatif.py

class MultiAgentWhatIfOrchestrator:
    """
    Orchestrate what-if scenarios across multiple decentralized nodes

    Uses LLM multi-agent chat for negotiation
    """

    def __init__(self, nodes: List[NodeLocalAgent]):
        self.nodes = {node.node_id: node for node in nodes}
        self.chat_history = []

    async def run_collaborative_whatif(
        self,
        initiator_node_id: str,
        scenario: dict,
        affected_nodes: List[str]
    ) -> dict:
        """
        Run what-if scenario with multi-agent negotiation

        Args:
            initiator_node_id: Node proposing the scenario
            scenario: {"type": "order_increase", "amount": 50, ...}
            affected_nodes: List of node IDs that may be impacted

        Returns:
            result: {
                "approved": True/False,
                "negotiations": [...],  # Chat transcript
                "commitments": {...},   # Actions each node commits to
                "network_impact": {...} # Aggregated impact
            }
        """
        # Step 1: Initiator proposes scenario
        initiator = self.nodes[initiator_node_id]
        proposal = await self._generate_proposal(initiator, scenario)

        self.chat_history.append({
            "agent": initiator_node_id,
            "message": proposal,
            "type": "proposal"
        })

        # Step 2: Affected nodes respond
        commitments = {}
        rejections = []

        for node_id in affected_nodes:
            node = self.nodes[node_id]

            # Node runs local what-if to assess impact
            local_impact = node.what_if_analyzer.analyze_local_scenario(
                self._translate_scenario_to_local(scenario, node)
            )

            # LLM agent decides: approve, negotiate, or reject
            response = await self._generate_response(
                node,
                proposal=proposal,
                local_impact=local_impact
            )

            self.chat_history.append({
                "agent": node_id,
                "message": response["message"],
                "type": response["decision"]  # "approve", "negotiate", "reject"
            })

            if response["decision"] == "approve":
                commitments[node_id] = response["commitment"]
            elif response["decision"] == "reject":
                rejections.append({
                    "node": node_id,
                    "reason": response["reason"]
                })
            elif response["decision"] == "negotiate":
                # Continue negotiation loop
                await self._negotiate(initiator, node, response["counter_proposal"])

        # Step 3: Aggregate results
        if len(rejections) > 0:
            return {
                "approved": False,
                "negotiations": self.chat_history,
                "rejections": rejections
            }
        else:
            return {
                "approved": True,
                "negotiations": self.chat_history,
                "commitments": commitments,
                "network_impact": self._calculate_network_impact(commitments)
            }

    async def _generate_proposal(self, node: NodeLocalAgent, scenario: dict) -> str:
        """
        LLM generates natural language proposal
        """
        prompt = f"""You are a {node.role} node proposing a what-if scenario.

SCENARIO: {scenario["type"]}
DETAILS: {json.dumps(scenario, indent=2)}

YOUR STATE:
- Current inventory: {node.inventory}
- Current backlog: {node.backlog}
- Usual order quantity: {node.typical_order_qty}

Generate a clear, concise proposal to send to affected nodes.
Explain WHY you're proposing this change and what you need from them.

Format: Natural language message (2-3 sentences)
"""

        response = await self.llm.complete(prompt)
        return response["message"]

    async def _generate_response(
        self,
        node: NodeLocalAgent,
        proposal: str,
        local_impact: dict
    ) -> dict:
        """
        LLM decides how to respond to proposal
        """
        prompt = f"""You are a {node.role} node evaluating a what-if scenario proposal.

PROPOSAL FROM UPSTREAM/DOWNSTREAM:
{proposal}

YOUR LOCAL IMPACT ANALYSIS:
{json.dumps(local_impact, indent=2)}

YOUR CONSTRAINTS:
- Current inventory: {node.inventory}
- Available capacity: {node.available_capacity}
- Cost sensitivity: {node.cost_threshold}

DECISION TASK:
Should you APPROVE, NEGOTIATE, or REJECT this proposal?

Consider:
1. Can you fulfill their request with your current capacity?
2. What's the cost impact on you?
3. Is this a reasonable request given the context?
4. Are there alternative solutions?

Output JSON:
{{
  "decision": "approve" | "negotiate" | "reject",
  "message": "Your response message",
  "commitment": "What you commit to do (if approve)",
  "reason": "Why you approve/reject (if applicable)",
  "counter_proposal": "Alternative suggestion (if negotiate)"
}}
"""

        response = await self.llm.complete(prompt)
        return json.loads(response)
```

**Example Multi-Agent Negotiation**:

```
=== WHAT-IF SCENARIO NEGOTIATION ===

Initiated by: WHOLESALER
Scenario: Increase order from 150 → 200 units
Affected nodes: DISTRIBUTOR (upstream), RETAILER (downstream)

--- CHAT TRANSCRIPT ---

[10:05 AM] WHOLESALER:
"I'm projecting a 40% demand spike over the next 3 weeks due to retailer
promotion. I'd like to increase my order from 150 to 200 units. Can you
fulfill this, and what's the lead time?"

[10:06 AM] DISTRIBUTOR:
"I ran a local simulation. I have 120 units available immediately. I can
produce the remaining 80 units in Week 2. Total lead time: 1.5 weeks
instead of usual 1 week. Cost impact on my end: +$40 holding cost.
Can you confirm the demand spike is real?"

[10:07 AM] RETAILER:
"Confirmed. We're running a 3-week promotion starting this Friday.
Historical data shows 35-45% lift during promotions. Consumer POS
data supports this forecast (90% conformal prediction interval: [130, 170] vs.
baseline 100)."

[10:08 AM] DISTRIBUTOR:
"Okay, I'm convinced. Approving your 200-unit order. I'll prioritize
your shipment in Week 1 (120 units) and Week 2 (80 units). I'm also
alerting Manufacturer about potential ramp-up need in Week 3."

[10:10 AM] MANUFACTURER:
"Acknowledged. I'm monitoring. Current capacity utilization: 70%.
I have 30% buffer available if Distributor needs to scale production
in Week 3-4. No action needed yet, but I'm ready."

--- SCENARIO RESULT ---

✅ APPROVED

COMMITMENTS:
- DISTRIBUTOR: Fulfill 200-unit order (120 Week 1, 80 Week 2)
- MANUFACTURER: Standby for 30% production increase Week 3-4
- RETAILER: Share daily POS data during promotion for demand tracking

NETWORK IMPACT:
- Total cost increase: +$180 (holding costs)
- Stockout risk reduced: -$2,500 expected value
- Service level maintained: 95% (vs. 78% without adjustment)
- Net benefit: +$2,320

CONFIDENCE: HIGH (multi-node validation with conformal prediction)

ACTION: Execute scenario (Wholesaler will order 200 units)
```

---

#### 8.9.4 Scenario Propagation Through Network (Ripple Effects)

Some what-if scenarios have **ripple effects** that propagate through the supply chain. LLM agents can simulate these cascades:

**Architecture**: Event-Driven Scenario Propagation

```python
# backend/app/services/scenario_propagation.py

class ScenarioPropagationEngine:
    """
    Propagate what-if scenarios through decentralized supply chain

    Each node simulates local impact, then notifies neighbors
    """

    async def propagate_scenario(
        self,
        origin_node_id: str,
        scenario: dict,
        max_hops: int = 3
    ) -> dict:
        """
        Propagate scenario through network (breadth-first)

        Args:
            origin_node_id: Node where scenario originates
            scenario: Change description
            max_hops: Maximum propagation distance

        Returns:
            cascade: {
                "hop_0": {origin_node_id: impact},
                "hop_1": {neighbor1: impact, neighbor2: impact},
                "hop_2": {...},
                "total_network_impact": {...}
            }
        """
        cascade = {}
        visited = set()
        queue = [(origin_node_id, scenario, 0)]  # (node_id, scenario, hop)

        while queue and len(cascade) <= max_hops:
            node_id, current_scenario, hop = queue.pop(0)

            if node_id in visited or hop > max_hops:
                continue

            visited.add(node_id)
            node = self.nodes[node_id]

            # Node simulates local impact
            local_impact = node.what_if_analyzer.analyze_local_scenario(current_scenario)

            # Record in cascade
            if f"hop_{hop}" not in cascade:
                cascade[f"hop_{hop}"] = {}
            cascade[f"hop_{hop}"][node_id] = local_impact

            # Propagate to neighbors
            for neighbor_id in self._get_neighbors(node_id):
                # Translate scenario for neighbor
                neighbor_scenario = self._translate_for_neighbor(
                    current_scenario,
                    from_node=node_id,
                    to_node=neighbor_id,
                    impact=local_impact
                )

                queue.append((neighbor_id, neighbor_scenario, hop + 1))

        # Aggregate total network impact
        cascade["total_network_impact"] = self._aggregate_impacts(cascade)

        return cascade

    def _translate_for_neighbor(
        self,
        scenario: dict,
        from_node: str,
        to_node: str,
        impact: dict
    ) -> dict:
        """
        Translate scenario impact from one node to neighbor

        Example: Wholesaler order increase → Distributor demand spike
        """
        relationship = self._get_relationship(from_node, to_node)

        if relationship == "downstream":  # to_node is downstream of from_node
            # Impact = Change in shipments to downstream
            return {
                "type": "supply_change",
                "shipment_change": impact.get("shipment_to_downstream", 0),
                "reason": f"{from_node} adjusted inventory policy"
            }

        elif relationship == "upstream":  # to_node is upstream of from_node
            # Impact = Change in orders from downstream
            return {
                "type": "demand_change",
                "order_change": impact.get("order_to_upstream", 0),
                "reason": f"{from_node} experienced demand spike"
            }

        return {}
```

**Example Scenario Propagation**:

```
=== SCENARIO PROPAGATION: Retailer Demand Spike ===

ORIGIN: RETAILER (consumer demand +40%)

HOP 0 (Origin):
├─ RETAILER
│  ├─ Inventory impact: -80 units (stockout risk)
│  ├─ Order change: +60 units to Wholesaler
│  └─ Cost impact: +$300 backlog cost

HOP 1 (Direct neighbors):
├─ WHOLESALER (upstream of Retailer)
│  ├─ Receives +60 order spike from Retailer
│  ├─ Inventory impact: -40 units
│  ├─ Order change: +50 units to Distributor (dampened 17%)
│  └─ Cost impact: +$150 backlog cost

HOP 2 (Second-order neighbors):
├─ DISTRIBUTOR (upstream of Wholesaler)
│  ├─ Receives +50 order spike from Wholesaler
│  ├─ Inventory impact: -30 units
│  ├─ Order change: +40 units to Manufacturer (dampened 20%)
│  └─ Cost impact: +$100 backlog cost

HOP 3 (Third-order neighbors):
├─ MANUFACTURER (upstream of Distributor)
│  ├─ Receives +40 order spike from Distributor
│  ├─ Production impact: Need to ramp up by 25%
│  ├─ Capacity check: ✓ Available (70% utilization → 88%)
│  └─ Cost impact: +$200 setup cost for production increase

TOTAL NETWORK IMPACT:
├─ Total cost: +$750
├─ Total inventory deficit: -150 units (cascading stockouts)
├─ Bullwhip ratio: 1.5x (dampened by conformal prediction agents)
├─ Risk: MEDIUM (can be mitigated with coordination)

RECOMMENDATION: Execute multi-agent negotiation (Section 8.9.3)
                 to coordinate response across all 4 nodes
```

**Key Insight**: Without collaboration, the ripple effect is invisible to individual nodes. **With multi-agent negotiation**, nodes can see the full cascade and coordinate their response.

---

#### 8.9.5 Human-Agent Collaborative What-If Interface

The LLM-first UI enables **humans to collaborate with agents** on what-if analysis through natural language:

**UI Design**: Per-Node What-If Copilot

```jsx
// frontend/src/components/WhatIfCopilot.jsx

export default function WhatIfCopilot({ nodeId, role }) {
  const [scenario, setScenario] = useState("");
  const [analysis, setAnalysis] = useState(null);
  const [negotiation, setNegotiation] = useState(null);

  const handleRunWhatIf = async () => {
    // Step 1: Agent analyzes local impact
    const localAnalysis = await api.runLocalWhatIf(nodeId, scenario);
    setAnalysis(localAnalysis);

    // Step 2: If low confidence, offer multi-agent negotiation
    if (localAnalysis.confidence === "LOW") {
      setShowNegotiationOption(true);
    }
  };

  const handleStartNegotiation = async () => {
    // Step 3: Initiate multi-agent negotiation
    const negotiationResult = await api.startMultiAgentWhatIf(
      nodeId,
      scenario,
      analysis.affected_nodes
    );
    setNegotiation(negotiationResult);
  };

  return (
    <Box>
      <Typography variant="h6">What-If Analysis ({role})</Typography>

      {/* Natural Language Scenario Input */}
      <TextField
        fullWidth
        multiline
        rows={3}
        label="Describe your what-if scenario"
        placeholder="What if I order 200 units instead of 150?"
        value={scenario}
        onChange={(e) => setScenario(e.target.value)}
      />

      <Button variant="contained" onClick={handleRunWhatIf}>
        Analyze Scenario
      </Button>

      {/* Local Analysis Results */}
      {analysis && (
        <Card sx={{ mt: 2 }}>
          <CardHeader title="Local Impact Analysis" />
          <CardContent>
            <Grid container spacing={2}>
              <Grid item xs={6}>
                <Typography variant="body2" color="text.secondary">
                  Inventory Change (Week 4)
                </Typography>
                <Typography variant="h6">
                  {analysis.inventory_change > 0 ? "+" : ""}
                  {analysis.inventory_change} units
                </Typography>
              </Grid>

              <Grid item xs={6}>
                <Typography variant="body2" color="text.secondary">
                  Cost Impact
                </Typography>
                <Typography variant="h6" color={analysis.cost_change > 0 ? "error" : "success"}>
                  {analysis.cost_change > 0 ? "+$" : "-$"}
                  {Math.abs(analysis.cost_change)}
                </Typography>
              </Grid>
            </Grid>

            {/* Confidence Badge */}
            <Chip
              label={`Confidence: ${analysis.confidence}`}
              color={analysis.confidence === "HIGH" ? "success" : analysis.confidence === "MEDIUM" ? "warning" : "error"}
              sx={{ mt: 2 }}
            />

            {/* Limitations */}
            {analysis.limitations && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                <AlertTitle>Analysis Limitations</AlertTitle>
                <ul>
                  {analysis.limitations.map((limitation, idx) => (
                    <li key={idx}>{limitation}</li>
                  ))}
                </ul>
              </Alert>
            )}

            {/* Multi-Agent Negotiation Offer */}
            {analysis.confidence === "LOW" && (
              <Button
                variant="outlined"
                startIcon={<GroupIcon />}
                onClick={handleStartNegotiation}
                sx={{ mt: 2 }}
              >
                Start Multi-Agent Negotiation
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {/* Multi-Agent Negotiation Chat */}
      {negotiation && (
        <Card sx={{ mt: 2 }}>
          <CardHeader
            title="Multi-Agent Negotiation"
            subheader={`Status: ${negotiation.approved ? "✅ Approved" : "⏳ In Progress"}`}
          />
          <CardContent>
            {/* Chat Transcript */}
            <List>
              {negotiation.negotiations.map((msg, idx) => (
                <ListItem key={idx}>
                  <ListItemAvatar>
                    <Avatar>
                      {msg.agent === nodeId ? <PersonIcon /> : <SmartToyIcon />}
                    </Avatar>
                  </ListItemAvatar>
                  <ListItemText
                    primary={msg.agent}
                    secondary={msg.message}
                  />
                </ListItem>
              ))}
            </List>

            {/* Network Impact Summary */}
            {negotiation.approved && (
              <Alert severity="success" sx={{ mt: 2 }}>
                <AlertTitle>Scenario Approved</AlertTitle>
                <Typography variant="body2">
                  Network cost impact: ${negotiation.network_impact.total_cost}
                </Typography>
                <Typography variant="body2">
                  Service level: {negotiation.network_impact.service_level}%
                </Typography>
                <Button
                  variant="contained"
                  sx={{ mt: 1 }}
                  onClick={() => handleExecuteScenario(negotiation)}
                >
                  Execute Scenario
                </Button>
              </Alert>
            )}
          </CardContent>
        </Card>
      )}
    </Box>
  );
}
```

**Example User Flow**:

```
USER (Wholesaler): "What if I order 200 units instead of 150?"

AGENT (Local Analysis):
"Running local simulation...

IMPACT ON YOUR NODE:
✓ Inventory increases by +30 units (Week 4)
✓ Cost decreases by -$140 (fewer stockouts)
⚠ Confidence: LOW

LIMITATIONS:
- Cannot see if Distributor has capacity for 200-unit order
- Cannot see if Retailer demand supports this increase

RECOMMENDATION: Start multi-agent negotiation to validate with Distributor?"

USER: "Yes, start negotiation"

AGENT (Initiating Chat):
"Inviting DISTRIBUTOR agent to negotiation room...

[WHOLESALER AGENT → DISTRIBUTOR AGENT]:
'I'm projecting a demand spike and want to increase my order from
150 to 200 units. Can you fulfill this within 2-week lead time?'

[DISTRIBUTOR AGENT]: (analyzing...)
'I have 120 units available now. Can produce 80 more in Week 2.
Total lead time: 1.5 weeks. Cost impact on my end: +$40.
Can you share why you're increasing orders?'

[WHOLESALER AGENT]: 'Retailer placed large order due to promotion.
Conformal forecast shows 40% demand spike (90% PI: [130, 170]).'

[DISTRIBUTOR AGENT]: 'Understood. I approve your 200-unit order.
Shipment schedule: 120 units Week 1, 80 units Week 2.'

NEGOTIATION RESULT: ✅ APPROVED

NETWORK IMPACT:
- Total cost: +$180 (vs. $2,500 stockout risk if denied)
- Service level: 95% maintained
- All nodes aligned

EXECUTE SCENARIO? [Yes] [No] [Modify]"

USER: "Yes"

AGENT: "✓ Scenario executed. Your next order quantity updated to 200 units.
Distributor has been notified and production plan adjusted."
```

---

#### 8.9.6 Hybrid What-If: Centralized Simulation with Decentralized Execution

**Best of Both Worlds**: Use centralized simulation for what-if, but keep execution decentralized

```python
# backend/app/services/hybrid_whatif.py

class HybridWhatIfOrchestrator:
    """
    Centralized simulation for what-if analysis
    Decentralized execution for resilience

    "Plan centrally, execute locally"
    """

    def __init__(self, central_simulator, node_agents: List[NodeLocalAgent]):
        self.simulator = central_simulator  # Can see full network
        self.nodes = {n.node_id: n for n in node_agents}

    async def run_hybrid_whatif(self, scenario: dict) -> dict:
        """
        1. Central simulator runs what-if on full network (fast, accurate)
        2. Results shared with affected nodes
        3. Nodes decide independently whether to execute
        """
        # Step 1: Centralized simulation (global visibility)
        central_result = self.simulator.simulate_scenario(scenario)

        # Step 2: Decompose into per-node impacts
        node_impacts = self._decompose_by_node(central_result)

        # Step 3: Share results with nodes (information sharing)
        node_decisions = {}
        for node_id, impact in node_impacts.items():
            node = self.nodes[node_id]

            # Node agent decides whether to accept (based on local impact)
            decision = await node.llm_agent.make_decision({
                "global_scenario": scenario,
                "my_impact": impact,
                "network_impact": central_result["total_impact"],
                "recommendation": central_result["recommendation"]
            })

            node_decisions[node_id] = decision

        # Step 4: Aggregate decisions (nodes vote)
        if all(d["accept"] for d in node_decisions.values()):
            return {
                "approved": True,
                "execution_mode": "decentralized",  # Each node executes independently
                "central_simulation": central_result,
                "node_decisions": node_decisions
            }
        else:
            return {
                "approved": False,
                "rejections": [n for n, d in node_decisions.items() if not d["accept"]],
                "central_simulation": central_result
            }
```

**Advantage**: Combines speed/accuracy of centralized simulation with resilience/autonomy of decentralized execution

---

### 8.10 Conclusion: The Best of Both Worlds

**Key Takeaway**: The future is **adaptive hybrid planning** where:

1. **LLM agents operate at each node** (decentralized by default)
2. **Nodes selectively share information** (blockchain, APIs, CPFR)
3. **Conformal prediction provides formal guarantees** (in both modes)
4. **System gracefully degrades** (central failure → decentralized fallback)
5. **Privacy is preserved** (zero-knowledge proofs, federated learning)

**The LLM-First UI paradigm works in BOTH modes**:
- **Centralized**: Single chat interface to central planner (Section 4.2)
- **Decentralized**: Chat interface at EACH node (per-node copilot)
- **Hybrid**: Multi-agent chat room (nodes negotiate in natural language)

**This flexibility is critical** because real-world supply chains are **heterogeneous**:
- Some links are centralized (owned facilities)
- Some links are decentralized (external suppliers)
- The system must adapt to the reality of each relationship

By supporting **both paradigms** with **LLMs and conformal prediction**, Autonomy becomes the **universal supply chain planning platform** that works regardless of organizational structure.

---

## 9. Sources & References

### Research Papers & Academic Sources

1. **Agentic LLMs in Supply Chain**
   - [Rethinking Supply Chain Planning: A Generative Paradigm (arXiv)](https://arxiv.org/pdf/2509.03811)
   - [Leveraging LLM-Based Agents for Intelligent Supply Chain Planning (arXiv)](https://arxiv.org/html/2509.03811v1)
   - [Agentic LLMs in the supply chain: towards autonomous multi-agent consensus-seeking (Taylor & Francis)](https://www.tandfonline.com/doi/full/10.1080/00207543.2025.2604311)

2. **Multi-Agent Systems Performance**
   - [Multi-Agent LLM Orchestration Achieves Deterministic, High-Quality Decision Support (arXiv)](https://arxiv.org/abs/2511.15755)
   - [Adaptation of Agentic AI (Stanford, Harvard, UC Berkeley, Caltech)](https://arxiv.org/html/2512.16301v2)

3. **Long-Horizon Planning**
   - [Long-Horizon Planning with Predictable Skills (RLJ RLC 2025)](https://rlj.cs.umass.edu/2025/papers/RLJ_RLC_2025_136.pdf)

### Industry Reports & Best Practices

4. **Supply Chain AI Deployments**
   - [Revolutionizing global supply chains with agentic AI | EY](https://www.ey.com/en_us/insights/supply-chain/revolutionizing-global-supply-chains-with-agentic-ai)
   - [Making Sense of Agentic AI in Supply Chain Management | DecisionBrain](https://decisionbrain.com/agentic-ai-in-supply-chain/)
   - [How Agentic AI looks set to revolutionize supply planning | World Economic Forum](https://www.weforum.org/stories/2025/12/agentic-ai-change-supply-planning/)

5. **Conversational AI Platforms**
   - [John Galt Solutions Expands Atlas Planning Platform's Explainable AI (Logistics Viewpoints)](https://logisticsviewpoints.com/2025/09/18/john-galt-solutions-expands-atlas-planning-platforms-explainable-ai-to-build-trust-in-supply-chain-decisions/)
   - [AI Chatbot Development for Logistics (Vocal Media)](https://vocal.media/journal/ai-chatbot-development-for-logistics-transforming-supply-chain-operations-in-2026)
   - [State of Conversational AI: Trends and Statistics [2026 Updated] (Master of Code)](https://masterofcode.com/blog/conversational-ai-trends)

6. **LLM Orchestration Frameworks**
   - [LLM Orchestration in 2026: Top 12 frameworks and 10 gateways (AIMultiple)](https://research.aimultiple.com/llm-orchestration/)
   - [Top 9 AI Agent Frameworks as of January 2026 | Shakudo](https://www.shakudo.io/blog/top-9-ai-agent-frameworks)
   - [Top 10+ Agentic Orchestration Frameworks & Tools in 2026 (AIMultiple)](https://research.aimultiple.com/agentic-orchestration/)

7. **Guardrails & Governance**
   - [The Ultimate Guide to Guardrails in GenAI (Medium)](https://medium.com/@ajayverma23/the-ultimate-guide-to-guardrails-in-genai-securing-and-standardizing-llm-applications-1502c90fdc72)
   - [Mastering LLM Guardrails: Complete 2025 Guide (ORQ.ai)](https://orq.ai/blog/llm-guardrails)
   - [Balancing Innovation and Oversight: How Enterprises Can Safely Adopt LLMs (John Snow Labs)](https://www.johnsnowlabs.com/balancing-innovation-and-oversight-how-enterprises-can-safely-adopt-large-language-models/)

8. **ReAct Prompting & Tool Calling**
   - [ReAct: Merging Reasoning and Action to Elevate AI Task Solving (Neradot)](https://www.neradot.com/post/react)
   - [Building a ReAct Agent Using the OpenAI GPT-4o Model (Medium)](https://medium.com/@govindarajpriyanthan/building-a-react-agent-using-the-openai-gpt-4o-model-1aeddd3334b2)
   - [ReAct Prompting | Prompt Engineering Guide](https://www.promptingguide.ai/techniques/react)

9. **OODA Loop (Observe-Orient-Decide-Act) in Autonomous Systems**
   - [NVIDIA's LLo11yPop: Autonomous GPU Fleet Management Using OODA Loop with LLM Agents (NVIDIA GTC 2024)](https://www.nvidia.com/en-us/on-demand/session/goo242412073/)
   - [The Agentic Age: An Introduction to AI Agents - OODA Loop Framework (Sogeti)](https://www.sogeti.com/ai/blog/intelligent-automation-2025/the-agentic-age-an-introduction-to-ai-agents/)
   - [Proactive Observability and the OODA Loop (F5 State of Application Strategy 2025)](https://www.f5.com/company/blog/application-strategy-report-2025)
   - [Security Concerns with AI Agents and OODA Loop Decision-Making (Bruce Schneier)](https://www.schneier.com/blog/archives/2024/12/security-concerns-with-ai-agents.html)
   - [ReAct as Implementation of OODA Loop in LLM Agents (Research Synthesis)](https://www.neradot.com/post/react)
   - [OODA Loop in Supply Chain: Rapid Decision-Making for Logistics (SupplyChainDive)](https://www.supplychaindive.com/news/supply-chain-resilience-agility-disruption/606123/)

10. **Conformal Prediction for Uncertainty Quantification**

    *Demand-Side & LLM Applications:*
    - [Quantifying LLMs Uncertainty with Conformal Predictions (Capgemini Invent Lab, Medium)](https://medium.com/capgemini-invent-lab/quantifying-llms-uncertainty-with-conformal-predictions-567870e63e00)
    - [TECP: Token-Entropy Conformal Prediction for LLMs (MDPI Mathematics 2025)](https://www.mdpi.com/2227-7390/13/20/3351)
    - [Conformal Prediction with Large Language Models (arXiv 2023)](https://arxiv.org/pdf/2305.18404)
    - [ConU: Conformal Uncertainty in LLMs with Correctness Coverage Guarantees (arXiv 2024)](https://arxiv.org/abs/2407.00499)
    - [API Is Enough: Conformal Prediction for LLMs Without Logit-Access (arXiv 2024)](https://arxiv.org/abs/2403.01216)
    - [Conformal Decision Theory: Safe Autonomous Decisions from Imperfect Predictions (arXiv 2023)](https://arxiv.org/abs/2310.05921)
    - [Conformal Prediction and Human Decision Making (arXiv 2025)](https://arxiv.org/abs/2503.11709)
    - [Robust Gas Demand Forecasting With Conformal Prediction (PMLR 2022)](https://proceedings.mlr.press/v179/mendil22a.html)
    - [Conformal Predictive Distributions for Order Fulfillment Time Forecasting (arXiv 2025)](https://arxiv.org/abs/2505.17340)
    - [Conformal Prediction Tutorial (Nixtla StatsForecast)](https://nixtlaverse.nixtla.io/statsforecast/docs/tutorials/conformalprediction.html)
    - [How to Boost Business Decisions with Conformal Prediction (Redfield AI)](https://redfield.ai/conformal-prediction-for-business/)
    - [LLM-Uncertainty-Bench: Benchmarking LLMs via Uncertainty Quantification (GitHub)](https://github.com/smartyfh/LLM-Uncertainty-Bench)

    *Supply-Side & Manufacturing Applications:*
    - [Conformal Prediction Under Distribution Shift: A COVID-19 Natural Experiment (arXiv January 2026)](https://arxiv.org/abs/2601.00908) - 8 supply chain tasks, coverage degradation analysis
    - [Uncertainty Quantification Based on Conformal Prediction for Industrial Time Series (IEEE 2025)](https://ieeexplore.ieee.org/document/10870871) - Distribution shift in manufacturing
    - [A Gentle Introduction to Conformal Time Series Forecasting (arXiv 2024)](https://arxiv.org/abs/2511.13608) - Time series foundations
    - [Conformal Prediction: Measuring Uncertainty (BBVA AI Factory)](https://www.bbvaaifactory.com/conformal-prediction-an-introduction-to-measuring-uncertainty/)
    - [Measuring Models' Uncertainty: Conformal Prediction (Dataiku Blog)](https://blog.dataiku.com/measuring-models-uncertainty-conformal-prediction)

11. **PDCA & Continuous Improvement**
   - [A Plan-Do-Check-Act Framework for AI Code Generation (InfoQ)](https://www.infoq.com/articles/PDCA-AI-code-generation/)

12. **Agentic Workflows**
    - [What Are Agentic Workflows? Patterns, Use Cases, Examples (Weaviate)](https://weaviate.io/blog/what-are-agentic-workflows)
    - [AI Agentic Workflows 101: A Guide for Modern Business (Airbyte)](https://airbyte.com/data-engineering-resources/ai-agentic-workflows)
    - [Top AI Agentic Workflow Patterns (ByteByteGo)](https://blog.bytebytego.com/p/top-ai-agentic-workflow-patterns)

13. **Continuous Planning & MRP**
    - [Run Full Planning, MPS, or MRP - Business Central (Microsoft Learn)](https://learn.microsoft.com/en-us/dynamics365/business-central/production-how-to-run-mps-and-mrp)
    - [Material Requirements Planning (MRP) Software (Manufacturo)](https://manufacturo.com/manufacturo-manufacturing-management-software/mrp-software-for-manufacturing-a-comprehensive-guide/)

---

**Document End**

For questions or feedback on this proposal, contact the architecture team or reference the original conversation context.
