# Decision-First Demo — Video Script

**"Every Supply Chain Decision, Visible and Measured"**

*Target: 4-5 minute polished video for azirella.com, LinkedIn, YouTube*
*Audience: VP Supply Chain, S&OP Directors, mid-market manufacturers ($100M-$2B)*

---

## Philosophy

This demo inverts the typical SaaS walkthrough. Instead of "here's our architecture, here are our features," we start with **a decision the system just made** and answer three questions:

1. **What did the AI decide?** (the decision card)
2. **Why?** (reasoning, evidence, confidence)
3. **What happened?** (outcome, learning, improvement)

The UI is shown as a safety net — "you can also click around if you want" — but the story is about decisions flowing, not screens being navigated.

---

## Recording Setup

- **Resolution**: 1920x1080 minimum (4K preferred for YouTube)
- **Browser**: Chrome, full screen, no bookmarks bar
- **Font scaling**: 110% browser zoom for readability
- **Login**: `admin@distdemo.com` / `Autonomy@2026`
- **Prerequisite**: Run `make warm-start-food-dist-quick` or all three seed scripts
- **Mouse**: Slow, deliberate movements. Highlight with cursor, don't click frantically.
- **Voiceover**: Record separately (cleaner audio). Script below is written for natural speech cadence.

---

## SCENE 1: The Decision Stream (0:00 - 0:45)

**Screen**: Decision Stream (`/decision-stream`) — this is the default landing page

**[Camera slowly scrolls the Decision Stream showing decision cards flowing in real-time]**

> **VOICEOVER:**
>
> "This is the Decision Stream. Every supply chain decision — whether made by an AI agent or a human planner — shows up here in real time."
>
> "Right now you're looking at FOODDIST_DC, a food distribution center managing 25 products across 10 suppliers and 10 customers."
>
> *(pause 1 second)*
>
> "Let's look at a decision that just happened."

**[Mouse hovers over the top decision card — a PO Creation decision for Chicken Breast IQF]**

> "The AI agent created a purchase order for 1,200 cases of chicken breast from Tyson. Decided — not suggested. Decided. Because it had 91% confidence, above the 60% threshold for autonomous execution."
>
> *(pause 1 second)*
>
> "But here's what matters: you can see exactly WHY."

**ACTION**: Click "Ask Why" on the decision card.

---

## SCENE 2: Ask Why — The Reasoning (0:45 - 1:30)

**Screen**: Decision card with Ask Why panel expanded inline

**[The reasoning panel expands showing the pre-computed explanation]**

> **VOICEOVER:**
>
> "The agent explains its reasoning in plain language. 'Current inventory covers 4.2 days. Reorder point is 7 days. March Madness demand surge expected — QUICKSERV pre-orders up 35%. Tyson lead time is 3 days, so ordering now avoids a stockout Thursday.'"
>
> *(pause 1 second)*
>
> "This isn't an LLM making something up after the fact. This reasoning was computed at decision time from the actual signals the agent processed — demand forecasts, inventory levels, supplier lead times, the urgency signals from other agents in the hive."

**[Scroll down to show the confidence score, risk assessment, and hive context]**

> "Confidence: 91%. Conformal risk bound: 0.08 — meaning there's an 8% chance this decision leads to a loss exceeding the threshold. That's within tolerance."
>
> *(pause 1 second)*
>
> "Now — what if a planner disagrees?"

---

## SCENE 3: The Override Story (1:30 - 2:15)

**Screen**: Scroll down to find a decision with status "Overridden" (e.g., Metro Grocery cream cheese ATP)

**[Mouse highlights an overridden decision card — red/amber status badge]**

> **VOICEOVER:**
>
> "Here's one the planner overrode. The agent recommended allocating 720 cases of cream cheese to Metro Grocery. The planner changed it to 900."
>
> "Why? 'Metro Grocery contractual minimum is 900 cases. Adjusted to meet contract obligation.'"

**[Click Ask Why to show the agent's original reasoning alongside the override]**

> "The agent didn't know about the contract. It allocated based on priority logic and available inventory. The planner caught it."
>
> *(pause 1 second)*
>
> "Here's where it gets interesting. The system tracked the outcome. The 900-case fill met the contract and avoided a $15,000 penalty. The planner's override was scored as *effective*."
>
> "That override now has a higher training weight. Next time the agent sees a Metro Grocery order, it checks for contractual minimums. The override rate for this decision type drops. The agent gets better because a human disagreed."

---

## SCENE 4: The Compounding Loop — 30 Seconds (2:15 - 2:45)

**Screen**: Stay on Decision Stream, but overlay or transition to Agent Performance (`/agent-performance`)

> **VOICEOVER:**
>
> "This is the compounding loop."
>
> "More decisions flow through the system. Humans override the ones the AI gets wrong. The system measures whether overrides actually improved outcomes — using Bayesian statistics, not gut feel."
>
> "Good overrides get 2x training weight. Bad overrides get down-weighted. Over time, the AI handles more, the override rate drops, and the judgment that made your best planners valuable is captured permanently in the model."

**[Show the Agent Performance page briefly — category scores, override rates, automation percentages]**

> "ATP allocation: 92% autonomous, 8% override rate. Demand forecasting: 92% autonomous. Supply planning: 77% — that's where human expertise still adds the most value. And you can see it converging."

---

## SCENE 5: The Safety Net — Traditional UI (2:45 - 3:30)

**Screen**: Quick montage of point-and-click pages (5-7 seconds each)

> **VOICEOVER:**
>
> "Everything you just saw also has a traditional point-and-click interface. You're not locked into a stream view."

**[Navigate quickly through each, spending 5-7 seconds per screen:]**

1. **Demand Planning** (`/planning/demand`) — "Demand forecasts with P10/P50/P90 intervals"
2. **Inventory Optimization** (`/planning/inventory-optimization`) — "Safety stock policies across 8 policy types"
3. **Supply Planning** (`/planning/supply-plan`) — "Generated purchase, transfer, and manufacturing orders"
4. **ATP Worklist** (`/planning/execution/atp-worklist`) — "Priority-based allocation with fill percentage bars"
5. **Network Topology** (`/admin/tenant/supply-chain-configs` > Network tab) — "Your supply chain as a graph — suppliers, sites, customers"

> "These are the same screens you'd find in Kinaxis or SAP IBP. We have 96 of them. Full AWS Supply Chain data model compliance — all 35 entities."
>
> *(pause 1 second)*
>
> "But the point isn't the screens. The point is that the AI is making decisions continuously, and every one of them is visible, explainable, and improvable."

---

## SCENE 6: The Punchline (3:30 - 4:00)

**Screen**: Return to Decision Stream (`/decision-stream`)

> **VOICEOVER:**
>
> "Traditional planning software gives you screens to fill in. Autonomy gives you decisions that are already made — with the reasoning, the confidence, and the audit trail."
>
> "Planners don't plan. They supervise. And every time they correct the AI, the AI gets permanently better."
>
> *(pause 2 seconds)*
>
> "Autonomy. AI-native supply chain planning."

**[Hold on Decision Stream for 3 seconds, then fade to logo/URL]**

---

## END CARD (4:00 - 4:10)

**Screen**: Logo + URL + CTA

```
AUTONOMY
AI-Native Supply Chain Planning

azirella.com
```

> *(no voiceover — music only)*

---

## Shot List for Screen Recording

Record these as separate clips and edit together:

| Shot # | Duration | Screen | Action | Notes |
|--------|----------|--------|--------|-------|
| 1 | 15s | Decision Stream | Slow scroll down through cards | Establish the stream |
| 2 | 10s | Decision Stream | Hover over PO Creation card | Highlight the decided status |
| 3 | 15s | Decision Stream | Click Ask Why, panel expands | Show reasoning inline |
| 4 | 10s | Decision Stream | Scroll to show confidence/risk | Numbers visible |
| 5 | 10s | Decision Stream | Find overridden card | Red/amber status badge |
| 6 | 15s | Decision Stream | Click Ask Why on override | Show original reasoning + override reason |
| 7 | 10s | Agent Performance | Quick pan of category table | Scores, override rates, automation % |
| 8 | 7s | Demand Planning | Static shot | P10/P50/P90 chart |
| 9 | 7s | Inventory Optimization | Static shot | Policy table |
| 10 | 7s | Supply Planning | Static shot | PO/TO/MO list |
| 11 | 7s | ATP Worklist | Static shot | Priority-colored rows |
| 12 | 7s | Network Topology | Static shot | Sankey diagram |
| 13 | 10s | Decision Stream | Return, hold | Final shot |
| 14 | 10s | End card | Logo + URL | Fade in |

**Total raw recording: ~2.5 minutes of screen time + voiceover layered on top**

---

## Voiceover Production Notes

**Tone**: Confident, measured, not salesy. Think "senior consultant presenting to a VP" — not "SaaS marketing video." No hype words (revolutionary, game-changing, cutting-edge). Let the product speak.

**Pacing**: ~140 words per minute. The script above is ~620 words for a 4-minute video, which allows for natural pauses and breathing room.

**Music**: Low, ambient background. Think Epidemic Sound "corporate ambient" — not upbeat ukulele. The content is serious (supply chain decisions worth $millions) and the tone should match.

**Recording options**:
- **Best**: Professional voice talent via Fiverr/Voices.com (~$50-100 for 4 minutes)
- **Good**: ElevenLabs text-to-speech with a professional voice clone
- **Acceptable**: Record yourself in a quiet room with a decent mic (Blue Yeti, etc.)

---

## Comparison: Old Script vs Decision-First

| Aspect | Old Script (Planning Cascade) | New Script (Decision-First) |
|--------|------------------------------|---------------------------|
| **Opens with** | Architecture diagram | A decision that just happened |
| **Structure** | Layer by layer (S&OP → MPS → Supply → Allocation → Feedback) | Decision → Why → Override → Learning → Safety net |
| **UI role** | Primary — click through each screen | Safety net — "you can also do this" |
| **Key message** | "We have a 5-layer planning cascade" | "Every decision is visible, explainable, improvable" |
| **Audience reaction** | "That's a lot of features" | "I want that for my supply chain" |
| **Duration** | 15-20 minutes | 4-5 minutes |
| **Emotional hook** | Technical competence | The override story (planner catches what AI missed) |

---

## Extended Version (8-10 minutes)

For a longer version (conference presentation, deep-dive webinar), add these after Scene 5:

### SCENE 5B: The Six Storylines (60 seconds)

Show the S&OP Worklist (`/sop-worklist`) with 6 items:

> "In a typical week, the system processes dozens of interconnected events. A March Madness demand surge hits at the same time a winter storm delays dairy shipments from Buffalo. A quality hold on yogurt compounds the dairy shortage. An ice cream seasonal ramp starts a week early."
>
> "Each of these generates decisions across multiple agents — forecast adjustment, buffer increase, emergency PO, cross-DC rebalancing, quality disposition. The agents coordinate autonomously. The S&OP Director sees 6 strategic items to review, not 200 individual SKU decisions."

### SCENE 5C: The Executive Briefing (45 seconds)

Show Strategy Briefing (`/strategy-briefing`):

> "Every Monday, the VP gets a synthesized briefing covering all active storylines, ranked recommendations with confidence scores, and the ability to ask follow-up questions in natural language."

### SCENE 5D: Scenario Comparison (45 seconds)

Show Scenario Comparison (`/sc-analytics`):

> "When the Rich Products weather delay hits, the agent evaluates three contingency options — wait it out, split-source with Land O'Lakes, or full switch. It scores each against the balanced scorecard. The planner sees ranked alternatives with full analysis. They just make the call."

---

## Files Reference

| File | Purpose |
|------|---------|
| `docs/demos/Decision_First_Demo_Script.md` | This script |
| `docs/FOOD_DIST_DEMO_GUIDE.md` | Comprehensive demo guide (all dashboards) |
| `docs/demos/Planning_Cascade_Demo.md` | Architecture-first demo (old approach) |
| `docs/demos/Powell_Framework_Demo.md` | Role-based dashboard demo |
| `docs/demos/Planning_Cascade_Narration_Script.md` | Terminal demo voiceover |
