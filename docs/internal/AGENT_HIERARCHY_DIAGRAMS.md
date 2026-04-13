# Agent Hierarchy Diagrams — Standardized Reference

> **Platform reference:** [Autonomy-Core/docs/AGENT_ARCHITECTURE.md](../../../Autonomy-Core/docs/AGENT_ARCHITECTURE.md) — product-agnostic treatment. This doc covers the TMS-specific instantiation and TMS-specific agent content.


This file contains the canonical Mermaid diagrams for the Autonomy agent architecture.
Use the **External** versions in customer-facing documents. Use the **Internal** versions
in engineering and architecture documents.

---

## 1. Five-Layer Agent Hierarchy

### External Version (approach-only, no technology names)

```mermaid
graph TD
    SOP["<b>Strategic Consensus</b><br/><i>Weekly · Policy Parameters</i>"]
    AAP["<b>Cross-Authority Protocol</b><br/><i>Ad Hoc · Trade-off Authorization</i>"]
    NET["<b>Network Coordination</b><br/><i>Daily · Inter-Site Directives</i>"]
    SITE["<b>Site Cross-Agent Coordination</b><br/><i>Hourly · Predictive Urgency Modulation</i>"]

    subgraph EXEC["<b>11 Execution Agents</b> · &lt;10ms per Decision"]
        direction LR
        DEMAND["Demand Sensing<br/><small>Order Promising · Exception Tracking</small>"]
        SUPPLY["Supply Securing<br/><small>Purchasing · Transfers · Subcontracting</small>"]
        HEALTH["Health Monitoring<br/><small>Inventory Buffers · Forecast Adjustment</small>"]
        INTEG["Integrity Protection<br/><small>Quality · Maintenance</small>"]
        BUILD["Production & Logistics<br/><small>Manufacturing Orders · Transfer Orders</small>"]
    end

    SOP -->|"policy parameters"| NET
    AAP <-->|"authorization"| NET
    NET -->|"site directives"| SITE
    SITE -->|"urgency adjustments"| EXEC
    EXEC -->|"signals & outcomes"| SITE
    SITE -->|"escalation"| NET
```

### Internal Version (full technical detail)

```mermaid
graph TD
    SOP["<b>Layer 4: S&OP GraphSAGE</b><br/>Policy parameters θ<br/><i>Weekly · CFA · ~500K params</i>"]
    AAP["<b>AAP Protocol</b><br/>AuthorizationRequest/Response<br/><i>Ad Hoc</i>"]
    NET["<b>Layer 3: Network tGNN</b><br/>tGNNSiteDirective<br/><i>Daily · CFA/VFA · ~473K params</i>"]
    SITE["<b>Layer 2: Site tGNN</b><br/>GATv2+GRU · 22 causal edges<br/><i>Hourly · VFA · ~25K params</i>"]

    subgraph HIVE["<b>Layer 1: TRM Hive</b> · HiveSignalBus + UrgencyVector · &lt;10ms · ~7M params/TRM"]
        subgraph SC["Scout (Demand)"]
            ATP["ATP Executor"]
            OT["Order Tracking"]
        end
        subgraph FO["Forager (Supply)"]
            PO["PO Creation"]
            REB["Rebalancing"]
            SUB["Subcontracting"]
        end
        subgraph NU["Nurse (Health)"]
            BUF["Inventory Buffer"]
            FA["Forecast Adj"]
        end
        subgraph GU["Guard (Integrity)"]
            QD["Quality"]
            MS["Maintenance"]
        end
        subgraph BU["Builder (Execution)"]
            MO["MO Execution"]
            TO["TO Execution"]
        end
    end

    SOP -->|"θ params"| NET
    AAP <-->|"AuthorizationRequest"| NET
    NET -->|"tGNNSiteDirective"| SITE
    SITE -->|"urgency Δ"| HIVE
    HIVE -->|"HiveSignalBus signals"| SITE
    SITE -->|"escalation"| NET
```

---

## 2. Warm Start Pipeline

### External Version

```mermaid
graph LR
    P1["<b>1. Individual<br/>Agent Learning</b><br/><i>1-2 days</i>"]
    P2["<b>2. Coordinated<br/>Simulation</b><br/><i>2-3 days</i>"]
    P3["<b>3. Cross-Agent<br/>Model Training</b><br/><i>~1 day</i>"]
    P4["<b>4. Stress<br/>Testing</b><br/><i>3-5 days</i>"]
    P5["<b>5. Copilot<br/>Calibration</b><br/><i>2-4 weeks</i>"]
    P6["<b>6. Autonomous<br/>Operation</b><br/><i>Continuous</i>"]

    P1 -->|"competent agents"| P2
    P2 -->|"coordination traces"| P3
    P3 -->|"trained model"| P4
    P4 -->|"robust agents"| P5
    P5 -->|"calibrated"| P6
    P6 -->|"continuous learning"| P6

    SIM(["Simulation<br/>(Digital Twin)"])
    SIM -.->|"curriculum"| P1
    SIM -.->|"episodes"| P2
    SIM -.->|"disruptions"| P4
    SIM -.->|"counterfactual eval"| P6
```

### Internal Version

```mermaid
graph LR
    P1["<b>Phase 1: TRM BC</b><br/>SyntheticTRMDataGenerator<br/><i>1-2 days</i>"]
    P2["<b>Phase 2: CoordinatedSim</b><br/>MultiHeadTrace generation<br/><i>2-3 days · 28.6M records</i>"]
    P3["<b>Phase 3: Site tGNN</b><br/>BC + PPO from traces<br/><i>~1 day · ~25K params</i>"]
    P4["<b>Phase 4: Stochastic</b><br/>Monte Carlo + CQL/PPO<br/><i>3-5 days · 17.6M records</i>"]
    P5["<b>Phase 5: Copilot</b><br/>Shadow mode + overrides<br/><i>2-4 weeks</i>"]
    P6["<b>Phase 6: CDC Loop</b><br/>Outcome→CDT→Retrain<br/><i>Continuous</i>"]

    P1 -->|"11 TRM checkpoints"| P2
    P2 -->|"MultiHeadTrace"| P3
    P3 -->|"site_tgnn_latest.pt"| P4
    P4 -->|"stress-tested checkpoints"| P5
    P5 -->|"calibrated"| P6
    P6 -->|":25/:32/:35/:45"| P6

    SIM(["CoordinatedSimRunner<br/>(SimPy/BeerGame)"])
    SIM -.->|"hive_curriculum.py"| P1
    SIM -.->|"run_episode()"| P2
    SIM -.->|"Monte Carlo inject"| P4
    SIM -.->|"counterfactual"| P6
```

---

## 3. Decision Flow (Single Decision)

### External Version

```mermaid
graph TD
    EVENT["Event Occurs<br/><small>Supplier delay, demand spike,<br/>quality hold, capacity loss</small>"]
    ENGINE["Deterministic Engine<br/><small>Constraint-validated baseline<br/>100% auditable</small>"]
    AGENT["Execution Agent<br/><small>Learned adjustment to baseline<br/>&lt;10ms, bounded ±20%</small>"]
    CONF{"Confidence<br/>Check"}
    AUTO["Auto-Execute<br/><small>Within guardrails</small>"]
    ESCALATE["Escalate to<br/>Human Planner<br/><small>Ranked options with<br/>trade-off analysis</small>"]
    LEARN["Record Decision<br/>& Outcome<br/><small>Continuous learning</small>"]

    EVENT --> ENGINE
    ENGINE --> AGENT
    AGENT --> CONF
    CONF -->|"High confidence"| AUTO
    CONF -->|"Low confidence"| ESCALATE
    AUTO --> LEARN
    ESCALATE -->|"Accept or Override"| LEARN
    LEARN -->|"Improves future decisions"| AGENT
```

---

## Document Classification

| Document | Audience | Label | Diagrams |
|----------|----------|-------|----------|
| `EXECUTIVE_SUMMARY.md` | Internal | `INTERNAL` | Internal hierarchy + warm start |
| `docs/external/EXECUTIVE_SUMMARY.md` | Customers, investors | `EXTERNAL` | External hierarchy + warm start |
| `TECHNICAL_OVERVIEW.md` | Internal (engineering) | `INTERNAL` | Internal hierarchy + warm start |
| `docs/external/TECHNICAL_OVERVIEW.md` | Solution architects, CTOs | `EXTERNAL` | External hierarchy + decision flow |
| `TRM_AGENTS_EXPLAINED.md` | Internal (engineering) | `INTERNAL` | Internal hierarchy |
| `POWELL_APPROACH.md` | Internal (engineering) | `INTERNAL` | Internal hierarchy + warm start |
| `TRM_HIVE_ARCHITECTURE.md` | Internal (engineering) | `INTERNAL` | Internal hierarchy + warm start |
| `CLAUDE.md` | Internal (dev reference) | `INTERNAL` | N/A (too large) |
