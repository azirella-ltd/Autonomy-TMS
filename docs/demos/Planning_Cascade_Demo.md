# Planning Cascade Demo Script

**Autonomy Platform - Distributor Prototype**

*Demo Duration: 15-20 minutes*

---

## Executive Summary

This demo showcases Autonomy's **Planning Cascade** for distributors - a complete supply chain planning system that combines AI agents with human oversight. The system supports two operating modes:

| Mode | Customer Provides | Autonomy Provides |
|------|------------------|-------------------|
| **INPUT** | S&OP parameters, MRP output | Agent validation, risk governance, execution |
| **FULL** | Nothing (or starting parameters) | End-to-end optimization with simulation |

**Key Value Propositions:**
1. AI agents that explain their reasoning
2. Human-in-the-loop override capability
3. Feed-forward contracts (traceable decisions)
4. Feed-back signals (continuous improvement)

---

## Demo Setup

### Option A: Terminal Demo (No Server Required)
```bash
cd backend
pip install rich  # if not installed
python scripts/demo_planning_cascade.py
```

### Option B: Full UI Demo
```bash
# Start the full stack
make up

# Seed Dot Foods demo data (recommended)
docker compose exec backend python scripts/seed_dot_foods_demo.py

# Or start services individually:
# Terminal 1: Backend
cd backend && uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm start
```

**URLs:**
- Cascade Dashboard: http://localhost:8088/planning/cascade-dashboard
- Powell Dashboards: http://localhost:8088/executive-dashboard
- API Docs: http://localhost:8000/docs#/planning-cascade

**Demo Login (Recommended):**
- Email: demo@distdemo.com
- Password: Autonomy@2025
- Access: All Powell dashboards (no login/logout needed!)

See also: [Powell Framework Demo](Powell_Framework_Demo.md) for role-based dashboard demo.

---

## Demo Flow

### Act 1: The Business Problem (2 min)

**Talking Points:**

> "Today I'm going to show you how Autonomy helps distributors like Dot Foods manage their supply chain planning."

> "Distributors face a classic challenge: they need to balance service levels against inventory costs. Order too much, and you tie up capital. Order too little, and you miss sales."

> "Traditional planning systems give you recommendations, but they're black boxes. You don't know WHY the system suggested what it did, and you can't easily adjust it."

> "Autonomy solves this with transparent AI agents and human-in-the-loop governance."

---

### Act 2: The Planning Cascade Architecture (3 min)

**Show:** Cascade Dashboard or Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     PLANNING CASCADE                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐                                           │
│  │ S&OP Policy      │ ← Customer provides (INPUT) or           │
│  │ Envelope (θ_SOP) │   Autonomy optimizes (FULL)              │
│  └────────┬─────────┘                                           │
│           │ feed-forward                                        │
│           ▼                                                     │
│  ┌──────────────────┐                                           │
│  │ MRS / Supply     │ 5 candidate methods with                  │
│  │ Baseline Pack    │ tradeoff frontier                         │
│  └────────┬─────────┘                                           │
│           │ feed-forward                                        │
│           ▼                                                     │
│  ┌──────────────────┐                                           │
│  │ Supply Agent     │ Agent selects, validates,                 │
│  │ → Supply Commit  │ flags risks, explains reasoning           │
│  └────────┬─────────┘                                           │
│           │ feed-forward                                        │
│           ▼                                                     │
│  ┌──────────────────┐                                           │
│  │ Allocation Agent │ Distributes supply across                 │
│  │ → Alloc Commit   │ customer segments                         │
│  └────────┬─────────┘                                           │
│           │                                                     │
│           ▼                                                     │
│  ┌──────────────────┐                                           │
│  │ Execution        │ Feed-back signals                         │
│  │                  │ → re-tune upstream                        │
│  └──────────────────┘                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Talking Points:**

> "The Planning Cascade has five layers. Each layer produces a versioned, hash-linked artifact that feeds into the next layer."

> "This is important because it gives you full traceability. You can always answer: 'Why did we make this decision?' by tracing back through the chain."

> "At the bottom, execution outcomes flow back UP as feed-back signals, enabling continuous improvement."

---

### Act 3: S&OP Policy Envelope (3 min)

**Navigate to:** S&OP Policy Screen or show in terminal

**Show the dual-mode interface:**

| INPUT Mode | FULL Mode |
|------------|-----------|
| User enters their existing S&OP parameters | Autonomy simulation generates optimal parameters |
| "Here are my service targets" | "Based on 1000 scenarios, here are the recommended targets" |
| Simple input form | What-if scenario comparison |

**Demo Data - Dot Foods:**

| Segment | OTIF Floor | Fill Rate Target |
|---------|------------|------------------|
| Strategic | 99% | 99% |
| Standard | 95% | 98% |
| Transactional | 90% | 95% |

| Category | Safety Stock (WOS) | DOS Ceiling | Expedite Cap |
|----------|-------------------|-------------|--------------|
| Frozen Proteins | 2.0 weeks | 21 days | $15,000 |
| Refrigerated Dairy | 1.5 weeks | 14 days | $10,000 |
| Dry Pantry | 3.0 weeks | 45 days | $5,000 |

**Talking Points:**

> "In INPUT mode, customers enter their existing S&OP parameters - the targets they've already agreed to."

> "In FULL mode, Autonomy runs Monte Carlo simulation to find the optimal parameters. But here's the key: it's the SAME screen. Customers can start in INPUT mode and upgrade later."

> "These parameters become the 'policy envelope' - the guardrails that govern all downstream decisions."

---

### Act 4: MRS Candidate Generation (3 min)

**Navigate to:** MRS Candidate Screen

**Show the tradeoff frontier (FULL mode):**

```
OTIF ▲
 98% │              ● Service Maximized ($142K)
     │
 96% │     ● Parametric CFA ($115K)
     │
 95% │        ● Periodic Review ($118K)
     │
 94% │  ● Reorder Point ($125K)
     │
 92% │● Min Cost EOQ ($105K)
     └──────────────────────────────────────► Cost
        $100K    $120K    $140K
```

**Five Candidate Methods:**

| Method | Description | Best For |
|--------|-------------|----------|
| Reorder Point | Classic (r, Q) policy | Stable demand |
| Periodic Review | Fixed review intervals | Regular ordering |
| Min Cost EOQ | Minimize total cost | Cost-focused |
| Service Maximized | Maximize fill rate | Service-focused |
| Parametric CFA | Learned θ parameters | Balanced optimization |

**Talking Points:**

> "In FULL mode, we generate five different supply plans using different optimization methods."

> "This tradeoff frontier shows you the cost vs. service tradeoff. You can see that 'Min Cost EOQ' is cheapest but has lower service, while 'Service Maximized' has highest service but costs more."

> "In INPUT mode, customers upload their existing MRP output. The agent still validates it against the policy envelope."

---

### Act 5: Supply Agent - The AI Decision Maker (4 min)

**Navigate to:** Supply Agent Worklist → Click "Details" on a commit

**HIGHLIGHT: Agent Reasoning Panel**

```
┌─────────────────────────────────────────────────────────────────┐
│ 🤖 AGENT REASONING                                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Decision Summary:                                                │
│ Selected PARAMETRIC_CFA method based on optimal cost-service    │
│ tradeoff. This method uses learned θ parameters from CFA        │
│ optimization.                                                    │
│                                                                  │
│ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│ │ Selected    │  │ Projected   │  │ Confidence  │              │
│ │ Method      │  │ OTIF        │  │ Score       │              │
│ │             │  │             │  │             │              │
│ │ PARAMETRIC  │  │   96.0%     │  │    87%      │              │
│ │ CFA         │  │ vs 90% floor│  │             │              │
│ └─────────────┘  └─────────────┘  └─────────────┘              │
│                                                                  │
│ Key Factors: [Cost optimization] [Service level] [Lead time]    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Talking Points:**

> "This is where Autonomy is different. The agent doesn't just give you a recommendation - it EXPLAINS why."

> "You can see it selected the Parametric CFA method, which balances cost and service. It shows the projected OTIF of 96%, well above the 90% floor."

> "The confidence score tells you how reliable the recommendation is based on data quality and model fit."

**Show Integrity Checks & Risk Flags:**

| Type | Example | Action |
|------|---------|--------|
| **Integrity Violation** (Blocking) | Negative inventory, lead time infeasible | Cannot submit |
| **Risk Flag** (Advisory) | OTIF below floor, DOS ceiling breach | Review suggested |

> "The agent also runs automated checks. Integrity violations BLOCK submission - these are hard constraints that can't be violated."

> "Risk flags are advisory - they flag things for human review but don't block the workflow."

---

### Act 6: Human Adjustment - The Override Capability (3 min)

**Navigate to:** Supply Agent Worklist → Click "Review" on a commit

**HIGHLIGHT: Human Adjustment Interface**

```
┌─────────────────────────────────────────────────────────────────┐
│ 👤 HUMAN ADJUSTMENTS                                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ You can adjust specific orders below. Your changes will be      │
│ tracked as overrides.                                           │
│                                                                  │
│ ┌──────────────────────────────────────────────────────────────┐│
│ │ SKU     │ Agent Qty │ Your Adj │ Change  │ Rationale        ││
│ ├──────────────────────────────────────────────────────────────┤│
│ │ FP003   │ 500       │ [600   ] │ +20%    │ Below ROP        ││
│ │ DP002   │ 300       │ [250   ] │ -17%    │ DOS ceiling      ││
│ │ BV001   │ 400       │ [400   ] │ —       │ Periodic review  ││
│ └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│ Review Notes & Adjustment Rationale:                            │
│ ┌──────────────────────────────────────────────────────────────┐│
│ │ Increasing FP003 due to expected holiday demand spike.       ││
│ │ Reducing DP002 to stay within DOS ceiling.                   ││
│ └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│                  [Cancel]  [Override]  [Accept]                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Talking Points:**

> "Here's the human-in-the-loop capability. You can see the agent's recommendation, but you can ADJUST specific orders."

> "You type in your adjusted quantity, and the system tracks the change. You're required to provide a rationale for your adjustments."

> "You have two options: Accept if you agree with the agent's decision, or Override if you want to make any changes - whether small adjustments or a complete replacement."

**KEY VALUE PROP:**

> "This is governance. The agent owns the decision, humans can accept or override with reasoning captured. Everything is tracked for audit and learning."

---

### Act 7: Allocation Agent & Segment Prioritization (2 min)

**Navigate to:** Allocation Agent Worklist

**Show allocation by segment:**

| Segment | Requested | Allocated | Fill Rate | OTIF Floor | Status |
|---------|-----------|-----------|-----------|------------|--------|
| Strategic | 45,000 | 44,800 | 99.6% | 99% | ✓ |
| Standard | 75,000 | 73,500 | 98.0% | 95% | ✓ |
| Transactional | 30,000 | 27,000 | 90.0% | 90% | ⚠ |

**Talking Points:**

> "The Allocation Agent takes the supply we committed to buy and distributes it across customer segments."

> "It follows the OTIF floors we set in the policy envelope. Strategic customers get priority, then standard, then transactional."

> "You can see transactional is right at the floor - that's intentional. We're not over-serving lower-tier customers at the expense of higher-tier ones."

---

### Act 8: Feed-Back Signals - Continuous Improvement (2 min)

**Show feed-back signals table:**

| Signal Type | Metric | Value | Threshold | Fed Back To |
|-------------|--------|-------|-----------|-------------|
| ACTUAL_OTIF | Strategic OTIF | 98.5% | 99% | Supply Agent |
| EXPEDITE_FREQUENCY | Frozen expedites/week | 3.2 | 2.0 | S&OP |
| EO_WRITEOFF | E&O write-off % | 0.8% | 1.0% | S&OP |
| ALLOCATION_SHORTFALL | Transactional shortfall | 4.2% | 5.0% | Supply Agent |

**Talking Points:**

> "After execution, actual outcomes flow back as feed-back signals."

> "If Strategic OTIF was 98.5% but the floor was 99%, that signals to the Supply Agent to order more next time."

> "If expedite frequency is high, that signals to S&OP to increase safety stock targets."

> "This creates a continuous improvement loop - the system learns from actual outcomes."

---

## Key Takeaways

### For the Audience

1. **Transparency**: AI agents explain their reasoning - no more black boxes
2. **Governance**: Humans accept or override agent recommendations with full audit trail
3. **Traceability**: Hash-linked feed-forward contracts trace every decision
4. **Learning**: Feed-back signals enable continuous improvement
5. **Flexibility**: Same UI works for INPUT mode (customer provides) or FULL mode (Autonomy optimizes)

### Competitive Differentiation

| Traditional Systems | Autonomy |
|--------------------|----------|
| Black box recommendations | Agent reasoning visible |
| Accept or reject only | Granular human adjustment |
| Static parameters | Feed-back driven re-tuning |
| All-or-nothing purchase | Modular: INPUT → FULL upgrade path |

---

## Q&A Talking Points

**Q: How is this different from traditional MRP/DRP systems?**
> "Traditional systems give you one answer with no explanation. Autonomy gives you multiple candidates, shows you the tradeoffs, and explains why it recommends what it does. Plus, you can adjust individual line items while maintaining governance."

**Q: What if we already have S&OP parameters from SAP/Kinaxis?**
> "That's exactly what INPUT mode is for. You bring your existing parameters, and Autonomy's agents validate, flag risks, and govern execution. You can upgrade to FULL mode later when you're ready for optimization."

**Q: How does the feed-back loop work in practice?**
> "Each week, we compare actual OTIF, expedite spend, and inventory levels against targets. Deviations become signals that inform parameter adjustments. Over time, the system learns your specific patterns and gets better."

**Q: Can we trust the AI recommendations?**
> "You don't have to trust blindly. Every recommendation comes with reasoning, confidence scores, and risk flags. And you can always override. We track human vs. agent performance to prove the value over time."

---

## Demo Cleanup

```bash
# If using Docker
make down

# If running locally
# Ctrl+C in each terminal
```

---

## Appendix: Technical Details

### API Endpoints
- `POST /api/v1/planning-cascade/run` - Run full cascade
- `GET /api/v1/planning-cascade/status/{config_id}` - Get cascade status
- `POST /api/v1/planning-cascade/supply-commit/{id}/review` - Review supply commit
- `GET /api/v1/planning-cascade/worklist/supply/{config_id}` - Supply worklist

### Database Tables
- `planning_policy_envelope` - S&OP parameters
- `supply_baseline_pack` - MRS candidates
- `supply_commit` - Supply agent decisions
- `allocation_commit` - Allocation agent decisions
- `feed_back_signal` - Execution outcomes

### Files
- Backend Services: `backend/app/services/planning_cascade/`
- Frontend Components: `frontend/src/pages/planning/`
- Database Models: `backend/app/models/planning_cascade.py`
- API Endpoints: `backend/app/api/endpoints/planning_cascade.py`
