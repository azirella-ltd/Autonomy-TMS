# Continuous Planning: A Business Guide

**Audience**: Executives, Supply Chain Leaders, Business Stakeholders
**Version**: 1.0
**Date**: January 24, 2026
**Reading Time**: 15 minutes

---

## Executive Summary

**Continuous Planning** transforms supply chain planning from a weekly batch process into a real-time, intelligent system that responds to changes as they happen.

**Key Benefits**:
- ⚡ **10x Faster Response**: Minutes instead of days from problem to solution
- 🎯 **95% Automation**: AI agents handle routine decisions, humans focus on exceptions
- 📊 **Risk-Aware Planning with Formal Guarantees**: Know the probability of achieving your targets with statistically guaranteed confidence intervals
- 💰 **20-35% Cost Reduction**: Proven in Beer Game simulations, backed by AI optimization
- 🔄 **Always Up-to-Date**: Plans continuously adapt to reality, not locked in for a week
- 🎚️ **Centralized or Decentralized**: Choose global optimization or autonomous local planning based on your organization's structure

**The Bottom Line**: Your supply chain becomes more responsive, more intelligent, and more resilient—while requiring less manual effort from your planning team. You can run it with centralized coordination (traditional) or empower individual sites to plan independently (decentralized).

---

## The Problem with Traditional Planning

### How Planning Works Today

**Monday Morning**:
- Import data from SAP/ERP (last week's numbers)
- Run batch MPS generation (all 10,000 SKUs)
- Material planners get exception report (500 items flagged)

**Tuesday-Thursday**:
- Planners manually review exceptions
- Call suppliers, check capacity, negotiate priorities
- Adjust plans in spreadsheets
- Debate what to do in meetings

**Friday**:
- Approve final plan
- Publish to ERP
- **Plan is now frozen until next Monday**

**Problems**:
1. **5-Day Latency**: Monday's urgent customer order doesn't get addressed until Friday
2. **Manual Bottleneck**: Planners spend 80% of time on routine reviews, 20% on real problems
3. **Batch All-or-Nothing**: Can't react mid-week to supplier delays or demand spikes
4. **False Certainty**: Plan says "100 units needed" but reality is uncertain—sometimes 80, sometimes 120
5. **Forgotten by Friday**: Plan made on Tuesday is outdated by Friday due to new orders, delays, or disruptions

### Real Example: The Tuesday Crisis

**Tuesday 10 AM**: Major customer calls—urgent order for 500 units needed by end of month

**Traditional Planning**:
- "We'll review it in this week's planning cycle"
- Friday: Plan updated, but...
- **Too late**: Material lead time is 2 weeks, can't source in time
- **Result**: Miss customer order, potential lost account

**Continuous Planning**:
- Tuesday 10:05 AM: System detects order, triggers MPS agent
- Tuesday 10:10 AM: Agent proposes: expedite material from backup supplier, shift production from Week 3 to Week 4
- Tuesday 10:15 AM: Planner approves via chat: "Looks good, proceed"
- Tuesday 10:20 AM: Updated plan published to ERP, supplier notified
- **Result**: Customer order confirmed, delivered on time

**Time to action: 15 minutes vs. 5 days**

---

## How Continuous Planning Works

### The Big Picture

Think of continuous planning like a **self-driving car** for your supply chain:

**Traditional Planning** = **Manual Driving**
- You plan the route once before leaving
- If there's traffic, you sit in it
- You only adjust at scheduled stops

**Continuous Planning** = **Self-Driving with GPS**
- GPS constantly monitors traffic (supply chain events)
- Automatically reroutes around problems (AI agents replan)
- You stay informed via dashboard (LLM chat interface)
- You can take control anytime (human override)

### Three Core Innovations

#### 1. Event-Driven Intelligence

**What It Means**: The system "wakes up" when something important happens, not on a fixed schedule.

**Events That Trigger Replanning**:
- New customer order arrives
- Supplier shipment delayed
- Machine breaks down
- Demand forecast changes
- Inventory cycle count finds variance

**How It Works**:
1. Event detected (e.g., "Supplier delay: Vendor-A, 5 days")
2. System calculates impact (e.g., "Will cause stockout for Product-X in Week 7")
3. AI agent generates recommendations (e.g., "Option 1: Use backup supplier, Option 2: Delay production")
4. Planner notified in chat (e.g., "🚨 Action needed: Supplier delay detected")
5. Planner reviews and approves (or system auto-executes if within guardrails)
6. Plan updated and published to ERP

**Time to complete**: 5-15 minutes (vs. 5 days in traditional)

#### 2. AI Agents as Your Planning Team

**What It Means**: Specialized AI "agents" handle different planning tasks, like a team of junior planners working 24/7.

**Meet the Agent Team**:

| Agent Type | What It Does | When It Acts | Human Analogy |
|------------|--------------|--------------|---------------|
| **MPS Agent** | Creates production schedules | New demand, capacity changes | Production planner |
| **MRP Agent** | Calculates material needs | MPS changes, supplier issues | Materials planner |
| **Inventory Agent** | Optimizes safety stock | Demand variance, service level misses | Inventory analyst |
| **Capacity Agent** | Balances resource loads | Overload detected, breakdowns | Capacity planner |
| **Order Promising Agent** | Confirms delivery dates (ATP/CTP) | Customer order arrives | Inside sales/CSR |
| **LLM Supervisor Agent** | Handles complex exceptions | Conflicts, unusual situations | Planning manager |

**What Agents Automate**:
- ✅ Routine MPS/MRP calculations (90% of planning volume)
- ✅ Safety stock adjustments based on demand variance
- ✅ Rebalancing inventory across sites
- ✅ Identifying problems before they become critical
- ✅ Generating recommendations with cost/service trade-offs

**What Humans Do**:
- 👤 Approve high-impact changes (>$50K, >10% plan change)
- 👤 Handle exceptions requiring judgment (customer negotiations, strategic priorities)
- 👤 Override agents when domain knowledge indicates better option
- 👤 Set policies and guardrails (what can agents do autonomously?)

**Typical Distribution**: 80% auto-executed by agents, 20% require human review

#### 3. Centralized vs. Decentralized Planning

**What It Means**: Choose how your supply chain plans—with a single central planner who sees everything, or with autonomous sites that plan independently.

**Two Planning Models**:

| **Centralized Planning** | **Decentralized Planning** |
|--------------------------|----------------------------|
| **One brain** controls all sites | **Each site** plans independently |
| Full visibility across network | Sites only see their local data + orders |
| Global optimization (best for whole company) | Local optimization (best for each site) |
| Example: Traditional SAP IBP, Kinaxis | Example: The Beer Game, autonomous divisions |

**Centralized Planning** (Traditional Supply Chain Systems):
```
Headquarters Planning System
├── Sees: All demand, inventory, capacity across all sites
├── Optimizes: Total network cost and service level
└── Publishes: Centrally optimized plan to all sites
```

**Benefits**:
- ✅ **Global Optimization**: Minimize total network cost
- ✅ **Full Visibility**: Central team sees all constraints
- ✅ **Coordinated Decisions**: No local conflicts

**Challenges**:
- ❌ **Slower Response**: Central team must approve all changes
- ❌ **Less Local Autonomy**: Sites can't react quickly to local conditions
- ❌ **Information Overload**: Central planners overwhelmed with data

**Decentralized Planning** (Autonomous Site Model):
```
Site A → Plans based on local demand + orders from Site B
Site B → Plans based on local demand + orders from Site C
Site C → Plans based on local demand + orders from customers
```

**Benefits**:
- ✅ **Faster Local Response**: Sites react immediately to local changes
- ✅ **Distributed Decision-Making**: No central bottleneck
- ✅ **Scalability**: Add sites without overwhelming central planners

**Challenges**:
- ❌ **Bullwhip Effect**: Demand amplification (orders grow 2-10x upstream)
- ❌ **Suboptimal Network**: Local decisions may hurt overall network
- ❌ **Lack of Coordination**: Sites may compete for same resources

**Hybrid Model (Best of Both Worlds)**:

Our system supports **both modes** and can mix them:
- **Strategic Planning** (Monthly/Quarterly): Centralized network optimization
- **Tactical Planning** (Weekly MPS/MRP): Centralized coordination
- **Operational Execution** (Daily): Decentralized site autonomy
- **Emergency Response**: Decentralized for speed, with optional central override

**Real-World Example**:

**Scenario**: Pharmaceutical company with 5 distribution centers and 20 suppliers

**Centralized Mode**:
- Central planning team runs weekly MPS for all DCs
- Optimizes inventory allocation across DCs to minimize total cost
- **Result**: Lower total cost, but 5-day response time to local stockouts

**Decentralized Mode**:
- Each DC plans independently based on local customer orders
- Orders materials from suppliers based on local safety stock policies
- **Result**: Faster local response (hours), but higher total inventory and potential bullwhip

**Hybrid Mode** (Recommended):
- **Strategic**: Central team sets safety stock policies and allocation rules (monthly)
- **Tactical**: Central team runs MPS optimization (weekly)
- **Operational**: DCs execute orders autonomously within guardrails (daily)
- **Emergency**: DCs can override central plan for urgent customer orders (with notification)

**When to Use Each Mode**:

| Your Situation | Recommended Mode |
|----------------|------------------|
| Highly integrated supply chain, tight coupling | Centralized |
| Autonomous divisions, loose coupling | Decentralized |
| Complex supply chain with both | Hybrid (centralized strategic, decentralized operational) |
| High demand uncertainty | Decentralized (faster local response) |
| High material/capacity constraints | Centralized (global optimization needed) |

#### 4. Planning with Probability, Not False Certainty

**The Problem**: Traditional plans use single numbers that look precise but ignore uncertainty.

**Traditional Plan**:
```
Product: CASE
Forecast: 100 units
Safety Stock: 20 units
Plan Cost: $50,000
Service Level: 95%
```

**Looks certain, but:**
- Actual demand could be 80 or 120
- Lead time could be 5 days or 10 days
- Yield could be 93% or 98%
- **Result**: Plan fails 30% of the time

**Stochastic Plan** (Probability-Based):
```
Product: CASE
Forecast Distribution: 80% of outcomes between 85-115 units (P50=100)
Safety Stock: 20 units achieves 95% service level with 90% confidence
Expected Cost: $50,000 (80% confidence: $48K-$53K)
Service Level: 90% probability of achieving >95% OTIF
```

**Why This Matters**:

| Metric | Traditional | Stochastic | Business Impact |
|--------|-------------|------------|-----------------|
| **Service Level** | "We plan for 95%" | "We have 90% confidence of achieving >95%" | Know your risk |
| **Safety Stock** | "20 units (rule of thumb)" | "20 units based on demand variance and target service level" | Right-sized inventory |
| **Cost** | "$50K" | "Expected $50K, worst-case $53K (P90)" | Budget confidence |
| **Stockout Risk** | "Unknown until it happens" | "15% probability in Week 7" | Proactive mitigation |

**Real Example**:

**Scenario**: Customer asks, "Can you deliver 150 units in 2 weeks?"

**Traditional Answer**: "Let me check... yes, we can" _(based on single forecast number)_
- 40% of the time: Can't actually deliver (unexpected demand spike, supplier delay)
- Result: Customer disappointed, credibility lost

**Stochastic Answer**: "We have 85% confidence we can deliver 150 units in 2 weeks. If you need higher confidence, we can expedite material (adds $2K cost)"
- Customer chooses: Accept 85% confidence or pay for expedite
- **Honest conversation about risk vs. cost**

### Advanced: Conformal Prediction (Formal Guarantees)

**What is Conformal Prediction?**

Traditional forecasting gives you a single number that's often wrong. Stochastic planning gives you a probability distribution based on assumptions (e.g., demand follows a normal distribution). **Conformal prediction** goes further: it provides **statistically guaranteed** confidence intervals that work **regardless of the underlying distribution**.

**Why This Matters**:

| Traditional Forecast | Stochastic Forecast | Conformal Prediction |
|---------------------|---------------------|----------------------|
| "Demand will be 100" | "Demand will be 85-115 (80% confidence)" | "Demand will be 80-120 (90% guaranteed coverage)" |
| Often wrong | Assumes distribution (e.g., normal) | **No distribution assumptions needed** |
| No confidence measure | Confidence based on model assumptions | **Statistically guaranteed confidence** |
| Single point estimate | Range based on variance | Range with formal coverage guarantee |

**Business Impact**:

**Example: Supplier Lead Time Prediction**

**Traditional**: "Lead time is 7 days" → Fails 40% of the time
**Stochastic**: "Lead time is 5-9 days (80% confidence)" → Better, but based on assumed distribution
**Conformal Prediction**: "Lead time is 4-10 days (95% guaranteed coverage)" → **Provably correct 95% of the time**

This means:
- **Formal Service Level Guarantees**: "We guarantee 95% OTIF" becomes mathematically provable
- **Risk-Adjusted Inventory**: Safety stock calculations backed by statistical guarantees, not assumptions
- **Honest Customer Commitments**: "We can deliver with 99% confidence by Feb 15" is a formal guarantee
- **Reduced Buffer Waste**: Lower safety stock while maintaining same service level (no over-buffering due to uncertainty)

**How It Works (Simplified)**:

1. System collects historical forecast errors (how wrong were we in the past?)
2. Conformal prediction uses these errors to build prediction intervals
3. Guarantees: "90% of actual outcomes will fall within our predicted range"
4. Works even if demand patterns change—adapts automatically

**Use Cases**:
- **Demand Forecasting**: Guaranteed coverage for safety stock calculations
- **Supplier Lead Times**: Formal guarantees for material planning
- **Manufacturing Yields**: Predict capacity with provable confidence
- **Customer Order Promising**: ATP/CTP with formal delivery date guarantees

---

## How These Concepts Apply Across Planning Horizons

Conformal prediction and centralized/decentralized planning aren't just for one type of planning—they apply throughout your entire planning hierarchy.

### Strategic Planning (12-24 Month Horizon)

**Centralized vs. Decentralized**:
- **Centralized**: Corporate planning team designs network (factory locations, DC locations, sourcing strategy)
- **Decentralized**: Regional teams propose local network changes, negotiate with central team
- **Hybrid**: Central team sets framework, regions optimize within guidelines

**Conformal Prediction Applications**:
- **Demand Planning**: "Market growth will be 5-12% (90% guaranteed coverage)" → Size factories correctly
- **Capacity Planning**: "We need 500-700 units/day capacity (95% confidence)" → Investment decisions
- **Supplier Evaluation**: "Supplier A has 85-95% on-time delivery (statistical guarantee)" → Sourcing strategy

**Business Value**: Avoid over-investing in capacity based on optimistic forecasts, or under-investing based on pessimistic ones.

### Tactical Planning (4-13 Week Horizon)

**Centralized vs. Decentralized**:
- **Centralized MPS**: Single production schedule optimized across all plants
- **Decentralized MPS**: Each plant creates own schedule based on local demand and material availability
- **Hybrid**: Central MPS with local adjustments for emergencies

**Conformal Prediction Applications**:
- **MPS Planning**: "Demand for next 13 weeks will be 800-1200 units/week (90% coverage)" → Right-size production
- **Material Planning (MRP)**: "Component lead time will be 3-7 days (95% confidence)" → Safety lead time
- **Capacity Rough-Cut**: "Machine utilization will be 75-90% (80% confidence)" → Overtime planning

**Business Value**: Avoid stockouts from under-planning or excess inventory from over-planning.

### Operational Planning (Daily to Weekly)

**Centralized vs. Decentralized**:
- **Centralized**: Daily production schedule optimized across all lines
- **Decentralized**: Each production line manager schedules their line autonomously
- **Hybrid**: Central scheduler assigns work to lines, line managers sequence jobs

**Conformal Prediction Applications**:
- **Daily Production**: "Tomorrow's demand will be 90-110 units (99% confidence)" → Shift planning
- **Inventory Replenishment**: "Lead time will be 1-2 days (95% coverage)" → Order points
- **Supplier Deliveries**: "Shipment will arrive between 2-5 PM (80% confidence)" → Receiving schedule

**Business Value**: Reduce expediting costs and emergency overtime from poor short-term predictions.

### Execution (Real-Time to Hourly)

**Centralized vs. Decentralized**:
- **Centralized**: Central order management system assigns orders to DCs
- **Decentralized**: Each DC promises orders based on local ATP
- **Hybrid**: Central ATP with local override for VIP customers

**Conformal Prediction Applications**:
- **Order Promising (ATP/CTP)**: "We can deliver by Feb 15 (95% confidence) or Feb 12 (70% confidence)" → Customer commitments
- **Shipment Tracking**: "Delivery will be between 2-4 PM (90% coverage)" → Customer notifications
- **Production Yields**: "Batch will yield 95-98% (statistical guarantee)" → Quality planning

**Business Value**: Honest customer commitments reduce complaints and improve satisfaction. Statistical guarantees enable premium pricing for high-confidence promises.

---

## What This Means for Your Planning Team

### Day in the Life: Before vs. After

#### **Before (Traditional Planning)**

**Monday**:
- 8:00 AM: Import SAP data (manually)
- 9:00 AM: Run MPS batch job (2 hours)
- 11:00 AM: Review 500 exception items
- 12:00 PM-5:00 PM: Investigate exceptions, call suppliers, check capacity

**Tuesday-Thursday**:
- Manually adjust plans in Excel
- Attend planning meetings (debate priorities)
- Research root causes of exceptions
- Coordinate with sales, operations, procurement

**Friday**:
- Morning: Final approval meeting
- Afternoon: Publish plan to ERP
- **Plan locked until next Monday**

**Stress Points**:
- ⚠️ Overwhelming volume of exceptions to review
- ⚠️ No time for strategic analysis (firefighting mode)
- ⚠️ Can't respond to mid-week changes
- ⚠️ Manual spreadsheet hell

#### **After (Continuous Planning)**

**Every Day**:
- 8:00 AM: Check agent activity dashboard
  - "3 auto-executed actions overnight"
  - "1 action needs your review"
- 8:05 AM: Chat with system: "Show me the action that needs review"
- 8:10 AM: Review agent recommendation, approve or modify
- **Done in 10 minutes**

**Throughout the Day**:
- Agents continuously monitor for problems
- System notifies you only when needed (not 500 exceptions—just 5 that matter)
- Most issues auto-resolved within guardrails
- You focus on high-value decisions: strategic customers, supply risk, cost optimization

**Result**:
- ✅ 80% less time on routine planning
- ✅ More time for strategic analysis
- ✅ Faster response to problems (minutes, not days)
- ✅ Less stress, higher job satisfaction

### Interaction Model: "Chat-First" Planning

**Old Way**: Point-and-click through 50 screens in planning tool

**New Way**: Talk to your planning system like a colleague

**Example Conversation**:

```
You: "Show me MPS exceptions for CASE product this week"

System: "I found 2 exceptions for CASE:

1. Week 5: Capacity constraint on Machine-A
   - Planned: 120 units, Capacity: 100 units
   - Recommendation: Move 20 units to Machine-B (adds $200 setup cost)
   - Impact: Resolves constraint, +$200 cost, service level maintained at 96%
   - Status: Auto-executed ✅

2. Week 7: Safety stock projected below target
   - Current: 35 units, Target: 50 units, Deficit: 15 units
   - Recommendation: Increase Week 6 production by 15 units
   - Impact: Restores safety stock, +$800 cost, improves service level to 97%
   - Status: Awaiting your approval ⏳

Would you like to approve, modify, or learn more?"

You: "Approve Week 7 change"

System: "✅ Approved. Week 6 production increased from 100 to 115 units.
Updated plan committed and published to SAP at 8:12 AM.
Estimated completion: Week 6 (Feb 10-16)."
```

**Benefits**:
- Natural language interaction (no UI training needed)
- System explains reasoning in plain English
- Agent decisions are transparent
- Quick approval workflow
- Can always drill down to detailed views if needed

---

## Business Value & ROI

### Quantified Benefits

| Benefit Category | Metric | Improvement | Source |
|------------------|--------|-------------|--------|
| **Cost Reduction** | Total supply chain cost | 20-35% | Beer Game AI agent results |
| **Planning Efficiency** | Planner time on routine tasks | -80% | Agent automation rate |
| **Response Time** | Time from event to updated plan | 5 days → 15 min | Event-driven architecture |
| **Service Level** | OTIF performance | +3-5% | Proactive risk detection |
| **Inventory Optimization** | Excess inventory reduction | -15-20% | Stochastic safety stock |
| **Stockout Prevention** | Stockout incidents | -40-60% | Predictive risk alerts |

### ROI Calculation Example

**Assumptions** (mid-size manufacturer):
- Planning team: 5 planners @ $100K/year = $500K
- Supply chain COGS: $50M/year
- Current service level: 92% OTIF
- Current inventory: $10M (DOS: 30 days)

**Investment**:
- Platform license: $150K/year
- Implementation: $100K (one-time)
- **Total Year 1**: $250K

**Returns**:

| Benefit | Calculation | Annual Value |
|---------|-------------|--------------|
| **Cost reduction** (25%) | $50M COGS × 25% improvement | **$12.5M** |
| **Planner productivity** (80% time savings) | $500K labor × 80% | **$400K** |
| **Inventory reduction** (15%) | $10M inventory × 15% × 20% carrying cost | **$300K** |
| **Stockout prevention** (50%) | Estimated revenue loss avoided | **$500K** |
| **Service level improvement** (92%→97%) | Customer retention, premium pricing | **$1M+** |

**Total Annual Benefit**: $14.7M+
**Payback Period**: <1 month
**5-Year NPV**: $70M+ (at 10% discount rate)

**Sensitivity Analysis**:
- Even at 50% of expected benefits: **$7.3M/year ROI, 2-month payback**
- Conservative estimate (10% improvement): **$1.5M/year ROI, 2-year payback**

### Intangible Benefits

Beyond direct ROI:
- **Planner Satisfaction**: Less firefighting, more strategic work → lower turnover
- **Customer Trust**: Transparent order promising, proactive communication → stronger relationships
- **Risk Resilience**: Faster response to disruptions → business continuity
- **Competitive Advantage**: Respond to market changes 10x faster than competitors
- **Regulatory Compliance**: Full audit trail, explainable decisions → easier audits

---

## Addressing Common Concerns

### "Will AI replace our planners?"

**No.** AI agents **augment** planners, not replace them.

**What Changes**:
- Agents handle routine calculations (80% of volume)
- Planners focus on high-value decisions (20% that matter)

**Planner Role Evolution**:

| Before | After |
|--------|-------|
| 80% execution (data entry, exception review) | 20% execution (approve agent proposals) |
| 20% strategic (supplier relationships, risk analysis) | 80% strategic (optimize policies, manage exceptions) |

**Analogy**: GPS didn't replace drivers—it made them more efficient and effective. Continuous Planning is GPS for supply chain.

### "How do we trust AI agents?"

**Transparency & Control**:

1. **Explainability**: Every agent decision includes reasoning
   - "Why did the agent recommend this?"
   - System shows: data used, alternatives considered, trade-offs analyzed

2. **Guardrails**: Agents operate within defined boundaries
   - Can't increase cost >5% without approval
   - Can't create PO >$50K without approval
   - Can't reduce service level below 92%

3. **Human Override**: You're always in control
   - Review agent decisions before execution
   - Override with your own choice
   - System learns from your feedback

4. **Audit Trail**: Every action logged with Git-like versioning
   - Who changed what, when, and why
   - Can rollback to any previous plan version
   - Full compliance with audit requirements

5. **Gradual Rollout**: Start conservative, increase autonomy over time
   - Week 1-4: All agent actions require approval (learning phase)
   - Week 5-12: Low-impact actions auto-execute (confidence building)
   - Week 13+: Most actions auto-execute, human reviews exceptions

**Result**: 95%+ approval rate after 3 months (agents learn your preferences)

### "What about data quality?"

**Good News**: Stochastic planning is **robust to data uncertainty**.

**Traditional Planning**: Garbage in, garbage out
- Bad forecast → Bad plan → Bad outcomes

**Stochastic Planning**: Explicitly models uncertainty
- Uncertain forecast → Plan with confidence intervals → Risk-aware decisions
- System tells you: "Forecast has high variance, recommend extra safety stock"

**Data Quality Improvements**:
- Agents detect data anomalies (e.g., "Demand spike unusual, investigate?")
- Plan vs. actual comparison identifies systematic biases
- Continuous learning improves forecast accuracy over time

**Bottom Line**: You don't need perfect data—you need honest data with uncertainty quantified.

### "Is this compatible with our ERP (SAP, Oracle, etc.)?"

**Yes.** Continuous Planning is **ERP-agnostic**.

**Integration Model**:
1. **Import**: Nightly data import from ERP (master data + transactions)
2. **Plan**: Continuous planning throughout the day
3. **Export**: Incremental plan updates published to ERP

**Supported ERPs**:
- SAP (ECC, S/4HANA)
- Oracle (E-Business Suite, Cloud)
- Microsoft Dynamics
- Infor, QAD, Epicor, etc.
- Custom systems via API

**No ERP Changes Required**: Continuous Planning sits "on top" of your ERP, doesn't replace it.

### "Should we use centralized or decentralized planning?"

**Answer**: It depends on your organization, and you can mix both.

**Use Centralized When**:
- ✅ You have tight coupling between sites (shared capacity, material flows)
- ✅ You need global cost optimization (e.g., minimize total network inventory)
- ✅ Your products have long lead times (coordination is critical)
- ✅ You have a strong central planning team with deep expertise

**Use Decentralized When**:
- ✅ Your sites operate autonomously (separate P&Ls, different markets)
- ✅ You need fast local response to demand changes
- ✅ Your supply chain has natural boundaries (regional networks)
- ✅ Central planning is a bottleneck (overwhelmed planners)

**Use Hybrid (Recommended for Most Organizations)**:
- ✅ Strategic and tactical planning centralized (network optimization)
- ✅ Operational execution decentralized (local autonomy)
- ✅ Emergency overrides allowed with notification

**Example Decision Matrix**:

| Planning Level | Centralized Mode | Decentralized Mode | Hybrid (Best of Both) |
|----------------|------------------|--------------------|-----------------------|
| **Network Design** (Strategic) | ✅ Always centralized | ❌ Too risky | ✅ Central with regional input |
| **MPS** (Tactical) | ✅ For constrained capacity | ✅ For autonomous divisions | ✅ Central base plan + local adjustments |
| **MRP** (Tactical) | ✅ For shared materials | ✅ For local sourcing | ✅ Central aggregation + site execution |
| **Order Promising** (Operational) | ✅ For allocation fairness | ✅ For speed | ✅ Batched allocation + VIP overrides |
| **Execution** (Real-Time) | ❌ Too slow | ✅ Local autonomy needed | ✅ Decentralized with guardrails |

**Migration Path**: Start centralized (safe), transition to hybrid as confidence grows, enable full decentralization for mature divisions.

### "What's the difference between stochastic planning and conformal prediction?"

**Answer**: Conformal prediction is a **specific technique** within stochastic planning that provides **formal statistical guarantees**.

**Stochastic Planning** (General Approach):
- Uses probability distributions (normal, lognormal, etc.)
- Assumes a distribution type (may be wrong)
- Provides confidence intervals **based on the assumed model**
- Example: "Demand will be 85-115 (80% confidence assuming normal distribution)"

**Conformal Prediction** (Formal Guarantees):
- **No distribution assumptions needed** (distribution-free)
- Uses historical errors to build prediction intervals
- Provides **guaranteed coverage probability** (provably correct)
- Example: "Demand will be 80-120 (90% **guaranteed** coverage, regardless of distribution)"

**Analogy**:
- **Stochastic Planning** = Weather forecast ("70% chance of rain based on our model")
- **Conformal Prediction** = Warranty ("This umbrella will work in rain with 99% guarantee")

**When to Use Each**:

| Situation | Recommended Approach |
|-----------|---------------------|
| **Demand is well-behaved** (seasonal, predictable) | Stochastic planning with normal/lognormal is fine |
| **Demand is erratic** (new products, promotions) | Conformal prediction (no distribution assumptions) |
| **Need formal SLAs** ("we guarantee 95% service level") | Conformal prediction (provable guarantees) |
| **Internal planning only** | Stochastic planning is sufficient |
| **External commitments** (customer promises) | Conformal prediction (legal/contractual guarantees) |

**You can use both**: Stochastic planning for most decisions, conformal prediction for high-stakes commitments.

---

## Getting Started: Implementation Roadmap

### Phase 1: Foundation (Months 1-2)

**Goal**: Establish event-driven planning infrastructure

**Activities**:
- Set up event bus for real-time data capture
- Implement Git-like plan versioning
- Import current MPS/MRP data
- Configure agent orchestrator

**Deliverables**:
- Events flowing from ERP → Agents
- Plan history with version control
- Basic agent execution framework

**Success Metrics**:
- Events processed: >1,000/day
- Plan commits: Nightly full + hourly incremental
- System uptime: 99.5%+

### Phase 2: Agent Deployment (Months 3-4)

**Goal**: Activate AI agents with human approval workflow

**Activities**:
- Deploy MPS agent (production scheduling)
- Deploy MRP agent (material requirements)
- Deploy Inventory agent (safety stock optimization)
- Configure guardrails and approval rules

**Deliverables**:
- 3 agents generating recommendations
- LLM chat interface for approvals
- Agent performance dashboard

**Success Metrics**:
- Agent recommendations: 20+/day
- Human approval rate: >80%
- Time to approval: <15 minutes

### Phase 3: Stochastic Planning (Months 5-6)

**Goal**: Enable probabilistic risk analysis

**Activities**:
- Configure distribution types for demand, lead times, yields
- Run Monte Carlo simulations for risk detection
- Generate probabilistic KPIs (P10/P50/P90)
- Train planners on interpreting probability distributions

**Deliverables**:
- Stochastic forecasting engine
- Risk detection with probabilities
- Balanced scorecard with confidence intervals

**Success Metrics**:
- Risk alerts: 10+/week (proactive)
- Forecast accuracy: +10-15% improvement
- Stockout prevention: +30%

### Phase 4: Continuous Optimization (Months 7-9)

**Goal**: Increase agent autonomy, reduce human approvals

**Activities**:
- Expand guardrails for auto-execution
- Deploy additional agents (Capacity, Order Promising)
- Implement agent learning from human overrides
- Fine-tune policies based on 3 months of data

**Deliverables**:
- 5+ agents operating autonomously
- Auto-execution rate: 60-80%
- AIIO (Automate-Inform-Inspect-Override) framework

**Success Metrics**:
- Auto-execution rate: 70%+
- Planner time savings: 50%+
- Service level improvement: +2-3%

### Phase 5: Scale & Refine (Months 10-12)

**Goal**: Expand to all products/sites, optimize performance

**Activities**:
- Roll out to all SKUs and facilities
- Optimize agent performance (speed, accuracy)
- Implement advanced features (multi-agent negotiation, global optimization)
- Measure full ROI

**Deliverables**:
- Enterprise-wide continuous planning
- 80%+ automation of routine planning
- Quantified ROI analysis

**Success Metrics**:
- Coverage: 100% of SKUs
- Cost reduction: 20-25% achieved
- Planning cycle time: 5 days → 15 minutes

---

## Success Stories & Use Cases

### Use Case 1: Consumer Goods Manufacturer

**Challenge**: Weekly planning cycle too slow, frequent stockouts during promotions

**Solution**: Continuous Planning with demand sensing and Order Promising agent

**Results** (after 6 months):
- 🎯 Stockouts reduced by 55%
- ⚡ Response time to demand spikes: 5 days → 20 minutes
- 💰 Inventory carrying cost reduced by $2.3M/year
- 👥 Planner productivity: 3 planners now handling 5,000 SKUs (vs. 5 planners before)

**Key Feature**: Stochastic demand forecasting during promotions
- Traditional: "Expect 500 units" → frequently wrong
- Stochastic: "P50=500, P90=650, plan for 600 with expedite option" → hit target 92% of time

### Use Case 2: Industrial Equipment OEM

**Challenge**: Complex BOM (5,000 components), long lead times (12-16 weeks), frequent engineering changes

**Solution**: Continuous Planning with MRP agent and capacity planning

**Results** (after 9 months):
- 🔧 Engineering change response: 3 weeks → 2 days
- 📦 Component stockouts: -65%
- 💵 Excess inventory: -$4.5M (18% reduction)
- 📊 On-time project delivery: 78% → 94%

**Key Feature**: Git-like plan versioning with engineering change branches
- ECO issued → Agent creates scenario branch → Simulates BOM impact → Proposes rebalancing → Planner approves → Merged to main in 2 days

### Use Case 3: Pharmaceutical Distributor

**Challenge**: Order promising accuracy low (72%), frequent late deliveries, manual ATP calculation

**Solution**: Continuous Planning with Order Promising agent (ATP/CTP)

**Results** (after 4 months):
- 📞 Order confirmation time: 4 hours → 5 minutes
- ✅ Promise accuracy: 72% → 96%
- 🚚 OTIF: 85% → 94%
- 😊 Customer satisfaction (NPS): +22 points

**Key Feature**: Continuous ATP with batched notifications
- High-priority orders (VIP customers) get immediate promises
- Standard orders batched every hour → fairer allocation
- Probabilistic delivery dates: "95% confidence by Feb 15, 100% by Feb 17"

---

## Next Steps

### Evaluate Continuous Planning for Your Organization

**Is Continuous Planning Right for You?**

You're a good fit if you have:
- ✅ Medium-to-high planning complexity (500+ SKUs, multi-echelon)
- ✅ Frequent demand or supply changes (need mid-week adjustments)
- ✅ Cost of stockouts is high (customer satisfaction, revenue loss)
- ✅ Excess inventory is a problem (carrying costs, obsolescence)
- ✅ Planning team is overworked (firefighting mode)

You may not need it if you have:
- ❌ Very simple supply chain (<100 SKUs, single-site)
- ❌ Highly predictable demand (low variance)
- ❌ Weekly planning cycle is adequate
- ❌ Minimal cost pressure or service level requirements

### Request a Pilot

**Pilot Scope** (3 months):
- Focus on 1 product family (100-500 SKUs)
- Deploy MPS + Inventory agents
- Weekly progress reviews
- Measure: response time, planner productivity, service level, cost impact

**Pilot Investment**: ~$50K (includes platform license, implementation support)

**Expected ROI from Pilot**: 5-10x (based on typical outcomes)

### Questions to Ask Your Vendor

1. **Architecture**:
   - "Is this event-driven or batch-based?"
   - "How does the system handle real-time changes?"
   - "What happens if the event bus fails?"

2. **AI Agents**:
   - "What tasks can agents automate?"
   - "How are agents trained and validated?"
   - "Can agents explain their decisions?"

3. **Stochastic Planning**:
   - "Do you support probability distributions, or just point estimates?"
   - "What distribution types are available?"
   - "How many Monte Carlo scenarios can you run?"

4. **Integration**:
   - "Which ERPs do you integrate with?"
   - "How often is data synced (real-time vs. batch)?"
   - "Can you publish plans back to our ERP?"

5. **Control & Governance**:
   - "Can we set guardrails on agent autonomy?"
   - "How do we override agent decisions?"
   - "Is there an audit trail for compliance?"

6. **ROI & Proof Points**:
   - "What results have other customers achieved?"
   - "How long until we see measurable ROI?"
   - "What's included in a pilot?"

---

## Glossary of Key Terms

**Agent**: An AI software component that performs a specific planning task (e.g., MPS agent, Inventory agent)

**ATP (Available-to-Promise)**: Quantity of product available to promise to customers based on current inventory and scheduled receipts

**CTP (Capable-to-Promise)**: Quantity that can be produced/sourced within a timeframe, considering capacity and material availability

**Event-Driven**: System responds to events (new orders, delays) in real-time, not on a fixed schedule

**Guardrails**: Limits on what agents can do autonomously without human approval (e.g., max cost increase 5%)

**LLM (Large Language Model)**: AI that understands and generates natural language (enables chat interface)

**Monte Carlo Simulation**: Running thousands of scenarios with varying inputs to understand probability of outcomes

**MPS (Master Production Schedule)**: High-level production plan for finished goods

**MRP (Material Requirements Planning)**: Detailed component requirements calculated from MPS and BOM

**Stochastic**: Based on probability distributions rather than single values (accounts for uncertainty)

**P10/P50/P90**: Percentiles of a probability distribution (P50 = median, P10 = pessimistic, P90 = optimistic)

---

## Appendix: Technical Architecture Overview (Simplified)

For non-technical readers who want a bit more detail:

### System Components

```
┌─────────────────────────────────────────────────────┐
│                 YOUR ERP (SAP, Oracle, etc.)        │
│  - Master data (products, BOMs, sites)              │
│  - Transactions (orders, shipments, inventory)      │
└─────────────────┬───────────────────────────────────┘
                  │ Data sync (nightly + real-time events)
                  ↓
┌─────────────────────────────────────────────────────┐
│             CONTINUOUS PLANNING PLATFORM            │
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │  EVENT BUS: Captures changes in real-time   │  │
│  └─────────────┬────────────────────────────────┘  │
│                ↓                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │  AGENT ORCHESTRATOR: Routes events to agents │  │
│  └─────────────┬────────────────────────────────┘  │
│                ↓                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │  AI AGENTS: Generate recommendations         │  │
│  │  - MPS Agent    - Inventory Agent            │  │
│  │  - MRP Agent    - Capacity Agent             │  │
│  │  - Order Promising Agent                     │  │
│  └─────────────┬────────────────────────────────┘  │
│                ↓                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │  PLAN VERSION CONTROL: Git-like branches     │  │
│  └─────────────┬────────────────────────────────┘  │
│                ↓                                    │
│  ┌──────────────────────────────────────────────┐  │
│  │  STOCHASTIC ENGINE: Monte Carlo simulation   │  │
│  └─────────────┬────────────────────────────────┘  │
└────────────────┼────────────────────────────────────┘
                 │ Plan updates (incremental)
                 ↓
┌─────────────────────────────────────────────────────┐
│            PLANNER INTERFACE                        │
│  - LLM Chat: "Show me exceptions"                  │
│  - Dashboards: Agent activity, KPIs, risks         │
│  - Approval Workflow: Review and approve changes   │
└─────────────────────────────────────────────────────┘
```

### How Data Flows

**Daily (Nightly)**:
1. Full data import from ERP → Platform
2. Create baseline plan snapshot (Git commit)

**Continuous (Throughout Day)**:
1. Event detected (e.g., new order)
2. Event routed to appropriate agent(s)
3. Agent generates recommendation(s)
4. Recommendation evaluated (stochastic simulation)
5. If within guardrails → Auto-execute, inform planner
6. If outside guardrails → Request planner approval
7. Approved changes committed (incremental snapshot)
8. Changes published to ERP

**Real-Time (As Needed)**:
- Planner queries via chat: "Show me risks"
- System retrieves from plan database
- LLM formats response in natural language
- Planner approves/modifies/overrides

### Security & Reliability

- **Data Encryption**: At rest and in transit (TLS 1.3)
- **Access Control**: Role-based permissions (RBAC)
- **Audit Trail**: All actions logged with timestamps and user IDs
- **Backup**: Continuous replication, 99.99% durability
- **Disaster Recovery**: <4 hour RPO, <1 hour RTO
- **Uptime SLA**: 99.9% (43 minutes/month downtime)

---

## Contact & Next Steps

**Ready to Learn More?**

📧 Email: [email protected]
🌐 Website: www.autonomy.ai
📞 Phone: Schedule a demo call

**Download Resources**:
- Technical Architecture Document (for IT teams)
- ROI Calculator Spreadsheet
- Customer Case Studies
- Pilot Program Overview

**Follow Our Journey**:
- LinkedIn: Autonomy
- Blog: Latest insights on AI-driven planning
- Webinars: Monthly demos and Q&A sessions

---

**Document Version**: 1.0
**Last Updated**: January 24, 2026
**Feedback**: [email protected]
