# Azirella — Demo Prompt Card

**Autonomy Platform** | SAP IDES 1710 Demo | MZ Bikes

---

## Drop-in Order

### 1a. Complete (Straight-Through)

> Bigmart just called — they need 500 C900 bikes delivered to Detroit in 2 weeks. This is a new fleet deal we can't lose. Increase production and prioritize ATP allocation for this order across all MZ City bike components at Plant 1710 for the next 4 weeks.

### 1b. Incomplete (Triggers Clarification)

> Bigmart needs 500 bikes in 2 weeks — rush order.

*System asks: Which product? Which plant? Why prioritize?*

---

## Demand Disruption

### 2a. Demand Spike (Straight-Through)

> Market intelligence from our cycling industry analyst: summer season demand for Mountain series bikes will be 25% above forecast for the next 8 weeks across all East Coast customers. Adjust forecasts and increase buffer levels accordingly.

### 2b. Customer Cancellation (Triggers Clarification)

> CostClub is canceling their R200 order.

*System asks: How many units? One-time or permanent? Why?*

### 2c. New Product Introduction (Straight-Through)

> The board approved the E-Bike launch. Introduce MZ-FG-E100 at Plant 1710, target 100 units per week, launch in 6 weeks. We need to ramp up component sourcing immediately — this is our entry into the electric segment and the CEO is watching.

---

## Supply Disruption

### 3a. Supplier Delay (Straight-Through)

> EV Parts Inc. just notified us that all open POs are delayed by 14 days due to a fire at their Texas facility. We need to activate backup suppliers and expedite any critical component orders for the next 3 weeks. Our Q2 delivery commitments to Skymart and Bigmart are at risk.

### 3b. Quality Hold (Triggers Clarification)

> Quality issue on Frame 900 — put it on hold.

*System asks: How many units? Which location? What defect? Expected duration?*

### 3c. Supplier Bankruptcy (Straight-Through)

> WaveCrest Labs has declared bankruptcy effective immediately. All supply from WaveCrest is permanently lost. Activate all alternative sources, expedite transfers from Plant 1720 inventory, and raise safety stock levels on affected components by 30% for the next quarter. This is a critical supply chain risk event.

---

## Capacity & Production

### 4a. Capacity Loss (Straight-Through)

> Plant 1710 Assembly Line A is down for emergency repairs — we've lost 40% of production capacity. Estimated 3-week recovery. Prioritize high-margin C900 and M500 models, defer low-priority R-series production, and evaluate subcontracting options for Frame assemblies. Customer impact must be minimized — our OTIF target is 95%.

### 4b. Yield Problem (Triggers Clarification)

> Scrap rate is up on the C900 line.

*System asks: By how much? Which plant? What's causing it? How long?*

---

## Strategic / Executive

### 5a. Cost Reduction (Straight-Through)

> The CFO wants a 12% reduction in total inventory holding cost across all sites over the next 6 months. We're overinvested in slow-moving R-series stock while C-series is turning too fast. Rebalance network inventory and tighten buffer levels on R-series while maintaining 95% service on C-series. This is a board-level commitment.

### 5b. Service Level Target (Triggers Clarification)

> We need better fill rates.

*System asks: What target %? Which products? Which region? By when? Why now?*

---

## Quick Questions (Query Routing)

| Prompt | Navigates To |
|--------|-------------|
| Show me all pending ATP decisions | ATP Worklist |
| What's our inventory position on C900 bikes? | Inventory Visibility |
| Any overdue POs from EV Parts? | PO Worklist |
| How's demand trending for Mountain bikes this quarter? | Demand Plan View |
| Show me the supply chain network | SC Config Sankey |
| What did the AI decide about the Bigmart order? | Decision Stream |

---

## Recommended 30-Minute Demo Sequence

| # | Prompt | Type | Time |
|---|--------|------|------|
| 1 | **1a** — Drop-in order (Bigmart 500 C900) | Straight-through | 5 min |
| 2 | "Show me the supply chain network" | Question | 2 min |
| 3 | **3a** — EV Parts supplier delay | Straight-through | 5 min |
| 4 | **4b** — C900 scrap rate up | Clarification | 4 min |
| 5 | "What's our inventory on C900?" | Question | 1 min |
| 6 | **2a** — Mountain bikes demand spike | Straight-through | 4 min |
| 7 | **5a** — CFO cost reduction mandate | Straight-through | 5 min |
| 8 | **1b** — Bigmart 500 bikes (incomplete) | Clarification | 4 min |
