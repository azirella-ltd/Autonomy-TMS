# Planning Cascade Demo - Narration Script

**Total Duration: ~5 minutes (with 3-second delays)**

Use this script while screen recording the demo:
```bash
cd backend && python scripts/demo_planning_cascade.py --no-pause --delay 3
```

---

## INTRO (0:00 - 0:15)

**[Title Screen Appears]**

> "Welcome to the Autonomy Planning Cascade demo. Today I'll show you how Autonomy helps distributors like Dot Foods manage their supply chain planning with AI agents and human oversight."

---

## OVERVIEW: Cascade Flow (0:15 - 0:45)

**[Planning Cascade Tree Appears]**

> "The Planning Cascade has five layers. Starting at the top with S&OP Policy Envelope, which sets the strategic guardrails."

> "Then Supply Baseline Pack generates candidate supply plans."

> "The Supply Agent selects the optimal plan and creates a Supply Commit."

> "The Allocation Agent distributes supply across customer segments."

> "And finally, execution outcomes feed back to re-tune the upstream parameters."

> "Notice this works in TWO modes: INPUT mode where customers provide their own parameters, and FULL mode where Autonomy optimizes everything."

---

## STEP 1: S&OP Policy Envelope (0:45 - 1:15)

**[Service Level Targets Table Appears]**

> "Step 1 is the S&OP Policy Envelope. These are the strategic guardrails."

> "We define service level targets by customer segment. Strategic customers get 99% OTIF floor. Standard gets 95%. Transactional gets 90%."

**[Inventory Policies Table Appears]**

> "We also set inventory policies by category. Frozen Proteins get 2 weeks of safety stock. Refrigerated Dairy gets 1.5 weeks because of shorter shelf life."

**[Financial Guardrails Panel Appears]**

> "And financial guardrails: a $2.5 million inventory cap and 3x GMROI target."

---

## STEP 2: Current Inventory State (1:15 - 1:45)

**[Inventory Table Appears]**

> "Step 2 shows our current inventory state - 25 SKUs across frozen proteins, dairy, dry goods, and beverages."

> "Each SKU shows on-hand quantity, in-transit shipments, average daily demand, and days of supply."

> "For example, Chicken Breast IQF has 398 units on hand with 18.6 days of supply."

**[Demand by Segment Appears]**

> "Demand breaks down by segment: Strategic customers need about 1,000 units per week, Standard needs 1,670, and Transactional needs 668."

---

## STEP 3: Supply Baseline Pack Candidates (1:45 - 2:15)

**[Candidate Plans Table Appears]**

> "Step 3 is where Autonomy generates five candidate supply plans - this is FULL mode."

> "Each method offers a different cost-versus-service tradeoff."

> "Min Cost EOQ is cheapest at $105K but only achieves 92% OTIF."

> "Service Maximized hits 98% OTIF but costs $142K."

> "Parametric CFA - using Powell's Cost Function Approximation - gives us the sweet spot: 96% OTIF at $115K."

**[Mode Comparison Panel Appears]**

> "In INPUT mode, customers would upload their existing MRP output instead. Same workflow, different data source."

---

## STEP 4: Supply Agent (2:15 - 3:30)

**[Agent Reasoning Panel Appears - CYAN BORDER]**

> "Step 4 is the Supply Agent - and this is where Autonomy is DIFFERENT."

> "Look at this Agent Reasoning panel. The AI doesn't just give you an answer - it EXPLAINS why."

> "It selected Parametric CFA because it optimizes cost, meets service constraints, and maintains lead time feasibility."

> "The confidence score is 87% - that tells you how reliable this recommendation is."

**[Supply Commit Summary Appears]**

> "The agent generated 47 purchase orders totaling $115,000, projecting 96% OTIF."

**[Integrity Checks Appear]**

> "Before submitting, the agent runs integrity checks. These are BLOCKING - they must pass. No negative inventory, lead times are feasible, MOQs are met."

**[Risk Flags Appear - YELLOW]**

> "Risk flags are ADVISORY - they don't block, but they flag issues for human review. FP003 Pork Chops is projected at 89% OTIF, below the 90% floor. That needs attention."

**[Human Adjustment Panel Appears - YELLOW BORDER]**

> "Now the KEY differentiator: Human-in-the-Loop Override."

> "The human reviewer can accept the agent's decision as-is, or override to make any changes."

> "Look at this adjustment table. The user increased FP003 from 500 to 600 units - a 20% increase - because of the low ROP risk."

> "They decreased DP002 from 300 to 250 to stay within the DOS ceiling."

> "Every adjustment is tracked with a rationale. This creates an audit trail AND training data for the agent to learn from."

---

## STEP 5: Allocation Agent (3:30 - 4:00)

**[Allocation Table Appears]**

> "Step 5 is the Allocation Agent, distributing supply across customer segments."

> "Strategic customers get priority - 99.6% fill rate, above the 99% floor."

> "Standard gets 98%, well above their 95% floor."

> "Transactional gets exactly 90% - right at the floor."

**[Allocation Status Appears]**

> "This is intentional. We're NOT over-serving lower-tier customers at the expense of higher-tier ones. The system enforces segment prioritization."

---

## STEP 6: Feed-Back Signals (4:00 - 4:30)

**[Feed-Back Table Appears]**

> "Step 6 closes the loop with feed-back signals from execution."

> "Actual Strategic OTIF was 98.5% versus the 99% target - that signals to the Supply Agent to order more next time."

> "Expedite frequency was 3.2 per week versus a target of 2.0 - that signals to S&OP to increase safety stock for frozen."

**[Re-tuning Panel Appears]**

> "This continuous improvement loop is how the system gets better over time. Execution outcomes automatically re-tune upstream parameters."

---

## CLOSING (4:30 - 5:00)

**[Demo Complete Panel Appears]**

> "That's the Planning Cascade. To summarize:"

> "One - Transparency. AI agents explain their reasoning."

> "Two - Governance. Humans can accept or override with full audit trail."

> "Three - Traceability. Every decision is hash-linked."

> "Four - Continuous improvement. Feed-back signals re-tune the system."

> "Thanks for watching. Visit the API docs or cascade dashboard to explore further."

---

## Recording Tips

1. **Terminal Size**: Use a large terminal (at least 120 columns wide)
2. **Font Size**: Increase font size for readability (14-16pt recommended)
3. **Dark Theme**: Terminal dark themes work best for recording
4. **Audio**: Record voice separately if possible for cleaner editing
5. **Practice**: Run through once without recording to get timing right

## Command Reference

```bash
# Standard demo (with pauses)
python scripts/demo_planning_cascade.py

# Video recording mode (3-second delays)
python scripts/demo_planning_cascade.py --no-pause

# Custom delay (5 seconds)
python scripts/demo_planning_cascade.py --no-pause --delay 5

# Faster pace (2 seconds)
python scripts/demo_planning_cascade.py --no-pause --delay 2
```

## Demo Login

**Recommended:** Use the unified demo user for all demos:
- Email: demo@distdemo.com
- Password: Autonomy@2025

This user has access to ALL Powell Framework dashboards - no logout needed!

To seed demo data:
```bash
docker compose exec backend python scripts/seed_dot_foods_demo.py
```

## Related Demos

- **[Powell Framework Demo](Powell_Framework_Demo.md)**: Role-based dashboards (Executive, S&OP Worklist)
- **[Planning Cascade Demo](Planning_Cascade_Demo.md)**: Full planning cascade walkthrough
