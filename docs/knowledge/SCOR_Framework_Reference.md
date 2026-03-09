# SCOR Digital Standard (DS) Framework Reference

## Comprehensive Guide to the Supply Chain Operations Reference Model

---

## 1. Overview

### What is SCOR?

The **Supply Chain Operations Reference (SCOR)** model is the world's most widely accepted framework for supply chain management. Originally developed by the Supply Chain Council (now ASCM — Association for Supply Chain Management), SCOR provides a standardized language, process taxonomy, metrics hierarchy, and best practices for describing, measuring, and improving supply chain performance.

### SCOR Digital Standard (DS)

The latest evolution (2022+) transforms SCOR from a linear model to an **infinity loop** reflecting the circular, interconnected nature of modern supply chains. The SCOR DS integrates digital capabilities, sustainability, and workforce considerations alongside traditional process and performance management.

---

## 2. SCOR Process Framework

### 2.1 Six Core Processes (SCOR DS)

```
        ┌──────────────────────────────────────┐
        │               PLAN                    │
        │  (Orchestrates all other processes)    │
        └──────────────────────────────────────┘
              ↓           ↓           ↓
    ┌─────────────┐ ┌───────────┐ ┌──────────────┐
    │   SOURCE    │→│ TRANSFORM │→│    FULFILL    │
    │ (Procure)   │ │ (Make)    │ │ (Deliver)     │
    └─────────────┘ └───────────┘ └──────────────┘
              ↓           ↓           ↓
        ┌──────────────────────────────────────┐
        │              ORDER                    │
        │  (Customer-facing order management)   │
        └──────────────────────────────────────┘
              ↓
        ┌──────────────────────────────────────┐
        │              RETURN                   │
        │  (Reverse logistics and disposal)     │
        └──────────────────────────────────────┘
              ↓
        ┌──────────────────────────────────────┐
        │              ENABLE                   │
        │  (Cross-cutting support processes)    │
        └──────────────────────────────────────┘
```

### 2.2 Process Descriptions

| Process | Code | Description | Key Activities |
|---------|------|-------------|----------------|
| **Plan** | P | Balance demand and supply resources across the supply chain | Demand planning, supply planning, S&OP/IBP, inventory planning |
| **Order** | O | Manage customer orders from creation through fulfillment | Order entry, ATP/CTP check, order promising, order tracking |
| **Source** | S | Procure goods and services to meet planned or actual demand | Supplier selection, procurement, receiving, quality inspection |
| **Transform** | T | Convert materials into finished products | Production scheduling, manufacturing, testing, packaging |
| **Fulfill** | F | Deliver finished goods to meet planned or actual demand | Warehousing, pick/pack/ship, transportation, last-mile delivery |
| **Return** | R | Process returns of defective, excess, or end-of-life products | Return authorization, disposition, refurbishment, recycling |
| **Enable** | E | Support processes that govern the supply chain | Master data, compliance, risk, technology, workforce |

### 2.3 SCOR DS vs Classic SCOR

| Aspect | Classic SCOR (v12.0) | SCOR Digital Standard |
|--------|---------------------|----------------------|
| **Model shape** | Linear (Plan-Source-Make-Deliver-Return) | Infinity loop (circular) |
| **Processes** | 5 (Plan, Source, Make, Deliver, Return) | 7 (adds Order, Transform, Fulfill, Enable) |
| **Make → Transform** | Manufacturing focus | Broader transformation (services, digital) |
| **Deliver → Fulfill** | Physical delivery | Omnichannel fulfillment |
| **Order** | Part of Plan/Deliver | Standalone customer-facing process |
| **Enable** | Implied | Explicit cross-cutting process |
| **Digital** | Limited | Digital capabilities integrated throughout |
| **Sustainability** | Add-on | Built into framework |
| **Workforce** | Not included | People pillar added |

---

## 3. SCOR Process Levels

### Level 1: Strategic (Process Types)

Defines scope and content of the supply chain. 7 process types.

### Level 2: Configuration (Process Categories)

Configures the supply chain strategy. 30+ process categories.

| Process | Categories |
|---------|-----------|
| **Plan** | P1: Plan Supply Chain, P2: Plan Source, P3: Plan Transform, P4: Plan Fulfill, P5: Plan Return |
| **Source** | S1: Source Stocked Product, S2: Source Make-to-Order, S3: Source Engineer-to-Order |
| **Transform** | T1: Transform Make-to-Stock, T2: Transform Make-to-Order, T3: Transform Engineer-to-Order |
| **Fulfill** | F1: Fulfill Stocked Product, F2: Fulfill Make-to-Order, F3: Fulfill Engineer-to-Order |
| **Return** | R1: Return Defective, R2: Return Excess, R3: Return MRO |
| **Order** | O1: Manage Orders, O2: Manage Quotations, O3: Manage Returns |
| **Enable** | E1: Manage Rules, E2: Manage Performance, E3: Manage Data, E4: Manage Risk, E5: Manage Compliance, E6: Manage Workforce, E7: Manage Technology |

### Level 3: Decomposition (Process Elements)

Detailed process steps. Each Level 2 category decomposes into process elements.

**Example: S1 — Source Stocked Product**:
- S1.1: Schedule Product Deliveries
- S1.2: Receive Product
- S1.3: Verify Product
- S1.4: Transfer Product
- S1.5: Authorize Supplier Payment

**Example: T1 — Transform Make-to-Stock**:
- T1.1: Schedule Production Activities
- T1.2: Issue Sourced/In-Process Product
- T1.3: Produce and Test
- T1.4: Package
- T1.5: Stage Finished Product
- T1.6: Release Finished Product to Fulfill

### Level 4: Implementation

Industry and company-specific implementation. Not defined by SCOR — this is where organizations add their unique processes.

---

## 4. SCOR Performance Attributes and Metrics

### 4.1 Five Performance Attributes

| Attribute | Definition | Customer/Internal | Direction |
|-----------|-----------|-------------------|-----------|
| **Reliability** | Ability to perform tasks as expected | Customer-facing | Higher is better |
| **Responsiveness** | Speed at which tasks are performed | Customer-facing | Lower is better |
| **Agility** | Ability to respond to external changes | Customer-facing | Higher/Lower |
| **Cost** | Cost of operating supply chain processes | Internal-facing | Lower is better |
| **Asset Management** | Effectiveness of asset utilization | Internal-facing | Higher is better |

### 4.2 Level 1 Strategic Metrics

| Attribute | Metric | Definition | Benchmark Range |
|-----------|--------|-----------|----------------|
| **Reliability** | Perfect Order Fulfillment (POF) | % of orders delivered on-time, in-full, damage-free, with correct documentation | 80-95% |
| **Responsiveness** | Order Fulfillment Cycle Time (OFCT) | Average time from order receipt to customer delivery | 1-30 days |
| **Agility** | Upside Supply Chain Flexibility | Time to achieve 20% increase in unplanned demand | 30-120 days |
| | Upside Supply Chain Adaptability | Maximum sustainable increase in quantity (30 days) | 10-40% |
| | Downside Supply Chain Adaptability | Maximum sustainable reduction without penalties (30 days) | 20-50% |
| | Overall Value at Risk (VAR) | Sum of probabilities × impact of supply chain risks | Varies |
| **Cost** | Total Cost to Serve (TCTS) | Sum of all supply chain costs as % of revenue | 4-12% |
| **Asset Management** | Cash-to-Cash Cycle Time (C2C) | Days Inventory + Days Receivable − Days Payable | 20-80 days |
| | Return on Supply Chain Fixed Assets | (Revenue − COGS − SC Costs) / SC Fixed Assets | 15-40% |
| | Return on Working Capital | (Revenue − COGS − SC Costs) / Working Capital | 10-30% |

### 4.3 Perfect Order Fulfillment Decomposition

```
Perfect Order = On-Time × In-Full × Damage-Free × Documentation Accurate

POF = % On-Time Delivery
    × % Complete Orders (fill rate)
    × % Damage-Free
    × % Correct Documentation

Example:
  On-Time: 95% × In-Full: 97% × Damage-Free: 99% × Documentation: 98%
  POF = 0.95 × 0.97 × 0.99 × 0.98 = 89.3%
```

### 4.4 Level 2 Metrics (Diagnostic)

| Process | Reliability Metric | Responsiveness Metric | Cost Metric |
|---------|-------------------|----------------------|-------------|
| **Plan** | Forecast accuracy | Planning cycle time | Planning cost |
| **Source** | Supplier on-time delivery | Source lead time | Material cost |
| **Transform** | Production yield | Manufacturing cycle time | Production cost |
| **Fulfill** | Delivery performance | Delivery lead time | Fulfillment cost |
| **Return** | Return processing rate | Return cycle time | Return cost |

---

## 5. SCOR Best Practices

### 5.1 Best Practices by Process

| Process | Best Practice | Description |
|---------|--------------|-------------|
| **Plan** | Demand sensing | Use POS/real-time data to adjust short-term forecasts |
| **Plan** | S&OP/IBP | Monthly cross-functional planning with financial integration |
| **Plan** | Probabilistic planning | Use probability distributions instead of point estimates |
| **Source** | Strategic sourcing | Total cost of ownership, multi-criteria supplier evaluation |
| **Source** | Supplier collaboration | VMI, consignment, CPFR |
| **Transform** | Lean manufacturing | Pull systems, waste reduction, continuous flow |
| **Transform** | Postponement | Delay product differentiation to reduce forecast risk |
| **Fulfill** | Cross-docking | Bypass warehousing for high-velocity products |
| **Fulfill** | Dynamic routing | Real-time transportation optimization |
| **Return** | Circular economy | Design for reuse, remanufacture, recycle |

### 5.2 Digital Best Practices (SCOR DS)

| Capability | Description | SCOR Process |
|-----------|-------------|-------------|
| **Digital twin** | Virtual model of supply chain for simulation | Plan, Enable |
| **AI/ML forecasting** | Machine learning for demand prediction | Plan |
| **IoT tracking** | Real-time shipment and inventory visibility | Source, Fulfill |
| **Blockchain** | Immutable record for provenance, compliance | Source, Enable |
| **RPA** | Automated transaction processing | Source, Order |
| **Advanced analytics** | Prescriptive optimization for planning | Plan, Transform |
| **Control tower** | End-to-end visibility and exception management | All processes |

---

## 6. SCOR Configuration Approach

### 6.1 Supply Chain Thread Diagram

A SCOR thread diagram maps the specific Level 2 processes used in a supply chain:

```
Supplier 1    [S1]→[T1]→[F1]    Distribution Center
              Source   Transform   Fulfill
                         ↓
Customer A    [O1]←─────[F1]     Store
              Order      Fulfill

Thread: P1→S1→T1→F1→O1 (Make-to-Stock through distribution)
```

### 6.2 Geographic Mapping

```
Country A (Manufacturing):
  Plant 1: T1 (MTS), T2 (MTO)
  Supplier Hub: S1, S2

Country B (Distribution):
  Regional DC: F1 (stock fulfillment)
  Customer Service: O1 (order management)

Country C (Market):
  Local DC: F1 (local fulfillment)
  Returns Center: R1 (defective returns)
```

---

## 7. SCOR Implementation Methodology

### Phase 1: Scope and Organize
- Define project scope (which supply chains, products, geographies)
- Identify stakeholders and form team
- Establish current-state baseline metrics

### Phase 2: Configure Supply Chain
- Map Level 2 processes (as-is configuration)
- Identify performance gaps vs benchmarks
- Prioritize improvement opportunities

### Phase 3: Align Processes
- Design Level 3 processes (to-be)
- Define information and material flows
- Identify enabling technology requirements

### Phase 4: Implement
- Deploy process changes
- Configure systems and technology
- Train workforce
- Measure and adjust

### Phase 5: Sustain
- Monitor metrics continuously
- Conduct periodic SCOR assessments
- Benchmark against industry peers
- Continuous improvement program

---

## 8. SCOR and Industry Standards Mapping

| SCOR Process | AWS SC Equivalent | SAP Module | Oracle Module |
|-------------|-------------------|-----------|---------------|
| **Plan** | Demand Planning, Supply Planning | PP, APO-DP, IBP | Demantra, ASCP |
| **Source** | Procurement | MM | Purchasing |
| **Transform** | Manufacturing | PP, QM | Manufacturing |
| **Fulfill** | Fulfillment | SD, LE-WM | Shipping |
| **Order** | Order Management | SD | Order Management |
| **Return** | Returns | SD (returns) | RMA |
| **Enable** | Master Data, Compliance | MDG, GRC | MDM |

---

## 9. SCOR Benchmarking

### 9.1 SCORmark Assessment

ASCM provides benchmarking database comparing organizations:

| Performance Level | Percentile | Description |
|------------------|-----------|-------------|
| **Parity** | Median (50th) | Industry average performance |
| **Advantage** | 70th percentile | Competitive advantage |
| **Superior** | 90th percentile | Best-in-class performance |

### 9.2 Industry Benchmarks (Illustrative)

| Metric | Consumer Products | High Tech | Industrial |
|--------|------------------|-----------|-----------|
| Perfect Order | 85-92% | 80-90% | 75-88% |
| OFCT | 3-7 days | 5-14 days | 7-30 days |
| Total SC Cost (% Rev) | 6-10% | 5-8% | 8-15% |
| Cash-to-Cash | 30-60 days | 40-80 days | 50-90 days |
| Inventory Turns | 8-15 | 6-12 | 4-8 |

---

## 10. SCOR Applied to Autonomy Platform

### Mapping Platform Capabilities to SCOR

| SCOR Process | Autonomy Capability | Status |
|-------------|---------------------|--------|
| **P1: Plan Supply Chain** | S&OP/IBP, Demand-Supply Balancing | In progress |
| **P2: Plan Source** | Sourcing Rules, Multi-sourcing | Implemented |
| **P3: Plan Transform** | MPS, BOM Explosion, MRP | Implemented |
| **P4: Plan Fulfill** | DRP, Inventory Deployment | Partial |
| **P5: Plan Return** | Not yet implemented | Gap |
| **S1: Source Stocked** | PO Creation TRM, Vendor Management | Implemented |
| **T1: Transform MTS** | MO Execution TRM, Production Process | Implemented |
| **F1: Fulfill Stocked** | TO Execution TRM, Allocation Service | Implemented |
| **O1: Manage Orders** | ATP Executor TRM, Order Tracking TRM | Implemented |
| **R1: Return Defective** | Quality Disposition TRM | Partial |
| **E1-E7: Enable** | Master Data, RBAC, Agent Config | Partial |

### SCOR Metrics in Platform

| SCOR Metric | Platform Equivalent | Where Tracked |
|-------------|-------------------|---------------|
| Perfect Order | OTIF (On-Time In-Full) | Balanced Scorecard |
| Forecast Accuracy | WMAPE, Bias | Demand Planning KPIs |
| Total Cost to Serve | E[Total Cost] | Stochastic Scorecard |
| Cash-to-Cash | DOS + DPO - DRO | Financial Metrics |
| Supply Chain Flexibility | Lead time distributions | Stochastic Planning |

---

*Sources: ASCM SCOR Digital Standard (v13.0), ASCM SCORmark Benchmarking, Supply Chain Council SCOR Reference Model v12.0, Gartner Supply Chain Maturity Model*
