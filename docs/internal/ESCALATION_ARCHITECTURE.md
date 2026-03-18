# Escalation Architecture: Vertical Decision Routing

## 1. Overview

The Autonomy platform's 3-tier AI architecture (Execution TRMs, Operational tGNN, Strategic GraphSAGE/S&OP) operates at fundamentally different time scales. The **Escalation Arbiter** adds intelligent vertical routing between tiers, detecting when execution-level anomalies indicate that higher-tier policy parameters need revision.

**The core insight**: When TRMs consistently correct in the same direction (always ordering more, always buffering up), the execution decisions aren't wrong — the policy parameters feeding them are. This requires replanning at a higher tier, not retraining the execution model.

### Current Architecture Gap

The existing CDC→Relearning loop is **horizontal** (execution→execution):

```
TRM decisions → [powell_*_decisions] → OutcomeCollector → CDT calibration → TRM retrain
```

What's missing is **vertical escalation**:

```
Execution anomaly → Diagnosis → Operational replan OR Strategic policy review
```

---

## 2. Dual-Process Cognition (Kahneman → Platform)

Daniel Kahneman's "Thinking, Fast and Slow" (2011) describes two cognitive systems that map directly onto the platform's decision architecture.

### 2.1 System 1 and System 2 Mapping

| Kahneman Concept | Platform Mapping | Characteristics |
|-----------------|------------------|----------------|
| **System 1** (fast, intuitive) | 11 TRM Agents (<10ms) | Pattern-matched, trained, automatic, high throughput |
| **System 2** (slow, deliberate) | tGNN (daily) + GraphSAGE (weekly) | Analytical, network-aware, resource-intensive |
| **The Lazy Controller** | Conformal Prediction Router | System 2 only activates when System 1 signals uncertainty |
| **Cognitive Strain** | Escalation Arbiter triggers | Persistent anomalies force slow thinking |
| **WYSIATI** (What You See Is All There Is) | TRM local-only state | Each TRM sees only its site — can't diagnose network-wide issues |
| **Substitution** | TRM pattern matching | Complex optimal decision substituted with simpler learned heuristic |
| **Anchoring** | TRM training distribution | Decisions anchor on historical patterns; shifts cause systematic bias |

### 2.2 Key Insights from Kahneman Applied

**Substitution**: TRMs substitute a complex question ("What is the globally optimal ATP allocation given all network constraints?") with a simpler one ("What pattern-matched decision fits this local state?"). This works ~95% of the time. It fails on novel situations or when the underlying distribution has shifted — these are the escalation triggers.

**Regression to the Mean**: Persistent directional drift (always ordering more than baseline, always increasing buffers) signals that the policy parameters (θ) are miscalibrated. The execution model is correctly compensating for bad policy, but the right fix is to update the policy, not retrain the compensator.

**Anchoring**: TRM decisions anchor on their training data distributions. When the real world shifts (new supplier, demand regime change, capacity disruption), anchoring bias causes systematic error. The Escalation Arbiter detects this via drift metrics — consistent adjustment in one direction means the anchor (training distribution) is stale.

**The Lazy Controller**: System 2 (tGNN/GraphSAGE) is computationally expensive. It should NOT activate for every decision — only when System 1 (TRMs) exhibits clear signs of failure. The current conformal prediction router handles per-decision uncertainty (→ Claude Skills). The Escalation Arbiter handles persistent pattern-level failure (→ higher-tier replanning).

### 2.3 SOFAI Architecture Reference

The System Of Functioning with Autonomous Intelligence (SOFAI) architecture (Bergamaschi Ganapini et al., arxiv:2110.01834) formalizes dual-process cognition for AI systems:

- **Meta-Cognitive Module**: Routes between System 1 (fast heuristic solvers) and System 2 (slow deliberative solvers) based on problem characteristics and confidence assessment.
- **Platform mapping**: The Escalation Arbiter IS the Meta-Cognitive Module, routing between TRM (System 1) and tGNN/GraphSAGE (System 2) based on persistence signals and cross-site patterns.

---

## 3. Nested OODA Loops (Boyd → Platform)

John Boyd's OODA Loop (Observe-Orient-Decide-Act) describes decision cycles at different tempos. The platform implements three nested OODA loops.

### 3.1 Three-Tier OODA Structure

```
┌──────────────────────────────────────────────────────────┐
│  Strategic OODA (GraphSAGE S&OP) — Weekly/Monthly        │
│                                                          │
│  Observe: Network topology changes, market signals,      │
│           risk score trends, macro indicators             │
│  Orient:  Bottleneck analysis, concentration risk,       │
│           network resilience assessment                   │
│  Decide:  Policy parameters θ (safety stock multipliers, │
│           allocation priorities, sourcing mix,            │
│           service level targets)                          │
│  Act:     Update S&OP embeddings → feed to tGNN          │
│                                                          │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Operational OODA (tGNN) — Daily                  │    │
│  │                                                   │    │
│  │  Observe: Transactional data + S&OP embeddings,   │    │
│  │           inventory positions, order pipeline      │    │
│  │  Orient:  Cross-site demand propagation,          │    │
│  │           capacity-demand imbalances               │    │
│  │  Decide:  Priority allocations per product-site,  │    │
│  │           tGNNSiteDirective per site               │    │
│  │  Act:     Push directives to each site's TRM hive │    │
│  │                                                   │    │
│  │  ┌──────────────────────────────────────────┐     │    │
│  │  │  Execution OODA (TRMs) — <10ms            │     │    │
│  │  │                                           │     │    │
│  │  │  Observe: Local state (inventory, backlog,│     │    │
│  │  │           pipeline, demand, urgency)       │     │    │
│  │  │  Orient:  Urgency vectors, hive signals,  │     │    │
│  │  │           tGNN directive context           │     │    │
│  │  │  Decide:  Order qty, ATP allocation,      │     │    │
│  │  │           rebalancing, scheduling          │     │    │
│  │  │  Act:     Execute decision immediately     │     │    │
│  │  └──────────────────────────────────────────┘     │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

### 3.2 Boyd's Key Concepts Applied

**Schwerpunkt (Focal Point)**: The orientation phase is the center of gravity of the OODA loop. For TRMs, orientation = trained weights + CDT calibration + tGNN directive. When orientation is wrong (stale training, miscalibrated CDT, outdated directive), decisions systematically fail — the loop produces increasing error even though each individual step executes correctly.

**Implicit Guidance & Control**: Well-trained TRMs operate like experienced soldiers executing mission command — they don't need explicit orders for routine situations. The tGNNSiteDirective provides "commander's intent" (priority allocations, emphasis areas), not micromanagement of individual decisions. This is why TRMs can operate at <10ms without waiting for daily tGNN output.

**Tempo**: The side that cycles through OODA faster gains advantage. TRMs at <10ms give unmatched execution tempo. But *strategic tempo* — how quickly the system detects and corrects policy errors — depends on escalation speed. Without vertical escalation, a bad strategic decision (wrong safety stock multiplier) persists for weeks until the next scheduled S&OP review, while TRMs waste cycles compensating.

**Mission Command**: Push authority to the lowest capable level. TRMs own execution decisions. tGNN owns daily allocations. GraphSAGE owns policy parameters. The Escalation Arbiter respects this hierarchy — it never overrides a TRM decision. Instead, it requests replanning at the appropriate higher tier.

**Getting Inside the Opponent's OODA Loop**: In competitive supply chain contexts, the organization that detects market shifts and adjusts policy faster wins. Vertical escalation shortens the strategic OODA cycle from "scheduled weekly review" to "anomaly-triggered replan within hours."

---

## 4. Powell 2026 Framework Integration

Warren B. Powell's two 2026 books provide the formal decision-theoretic foundation for the escalation architecture.

### 4.1 Three Stages of Decision Automation (Bridging Vol I, Ch 1)

Powell defines three stages: **Framing → Modeling → Implementation**.

The Escalation Arbiter's primary function is **framing** — correctly classifying the problem before selecting the modeling approach:

| Stage | Arbiter Function |
|-------|-----------------|
| **Framing** | Is this execution noise, operational misallocation, or strategic policy error? |
| **Modeling** | Route to the correct policy class: VFA (TRM retrain), CFA/VFA (tGNN refresh), CFA (S&OP review) |
| **Implementation** | Trigger the concrete action: retrain, refresh, or authorize policy change |

**Three Framing Questions** (Bridging Vol I):
1. **What are the performance metrics?** → The Arbiter monitors balanced scorecard metrics across all tiers. Execution metrics (fill rate, on-time) vs. operational metrics (allocation efficiency) vs. strategic metrics (total cost, resilience).
2. **What are the types of decisions?** → Execution (continuous: order quantities), operational (vectors: priority allocations), strategic (continuous: policy parameters θ).
3. **What are the sources of uncertainty?** → The Arbiter must distinguish execution uncertainty (demand noise, lead time variance) from structural uncertainty (demand regime shift, supplier failure, capacity change).

### 4.2 Powell's 7 Levels of AI — Platform Mapping

| Level | Powell Definition | Platform Component |
|-------|------------------|-------------------|
| 1 | Rule-based logic | Deterministic engine (base stock, BOM explosion, netting) |
| 2 | Statistics/ML | Conformal prediction, CDT calibration, demand forecasting |
| 3 | Pattern recognition | TRM agents (7M-param recursive networks, <10ms) |
| 4 | Large language models | Claude Skills (exception handling, ~5% of decisions) |
| 5 | Deterministic optimization | MPS/MRP solvers, inventory policy optimization |
| 6 | Sequential decision problems | Full Powell SDAM framework (VFA/CFA/DLA across tiers) |
| 7 | Creativity/reasoning/judgment | Escalation Arbiter diagnosis, S&OP consensus negotiation |

The Escalation Arbiter operates at **Level 7** — it requires judgment to correctly diagnose *why* execution is failing and *which* tier should act. This is not pattern recognition (Level 3) because the mapping from symptoms to root causes is many-to-many and context-dependent.

### 4.3 Three Classes of Computer Intelligence

Powell distinguishes:
1. **Human-specified behaviors**: Deterministic engine rules, threshold-based CDC triggers
2. **Machine learning**: TRM training, GNN training, conformal prediction calibration
3. **Optimization**: CFA policy parameter search, VFA value function estimation

The Escalation Arbiter bridges all three: it uses human-specified thresholds for initial detection, machine-learned patterns for diagnosis, and routes to optimization (CFA/VFA) at higher tiers.

### 4.4 State Variable Decomposition (SDAM 2nd Ed, Ch 1)

Powell decomposes the state Sₜ = (Rₜ, Iₜ, Bₜ):

| Component | Powell Definition | Platform Mapping | Escalation Relevance |
|-----------|------------------|-----------------|---------------------|
| **Rₜ (Physical)** | Tangible state | Inventory levels, backlog, pipeline, capacity | Directly observed; anomalies here are symptoms |
| **Iₜ (Information)** | Data/knowledge | Demand forecasts, lead time estimates, supplier status | Changes here may require operational replan |
| **Bₜ (Belief)** | Uncertainty quantification | CDT calibration state, conformal intervals, TRM confidence | Drift in Bₜ is the primary escalation signal |

**Key insight**: The Escalation Arbiter monitors **Bₜ drift** — when the belief state (conformal intervals, CDT calibration) persistently diverges from reality, the current tier's model is inadequate. Rₜ anomalies might be noise; Bₜ drift indicates structural change.

### 4.5 Interaction Matrices (Bridging Vol I, Ch 2)

Powell's interaction matrices map relationships between decisions and metrics:

**Decisions × Metrics Matrix** (which tier's decisions affect which metrics):

| Decision Tier | Service Level | Total Cost | Inventory Turns | Resilience |
|--------------|--------------|-----------|----------------|-----------|
| Execution (TRM) | Direct | Direct | Direct | Indirect |
| Operational (tGNN) | Direct | Direct | Direct | Direct |
| Strategic (GraphSAGE) | Indirect | Direct | Indirect | Direct |

**Uncertainty × Metrics Matrix** (which uncertainties affect which metrics):

| Uncertainty Source | Service Level | Total Cost | Inventory Turns |
|-------------------|--------------|-----------|----------------|
| Demand noise | Medium | Low | Low |
| Demand regime shift | High | High | High |
| Lead time variance | Medium | Medium | Low |
| Supplier disruption | High | High | Medium |
| Capacity change | High | Medium | Medium |

The Arbiter uses these matrices for routing: if the metric degradation is in "service level" and the co-occurring uncertainty is "demand regime shift" (not just noise), escalate to strategic level because the uncertainty source requires strategic-level decisions.

### 4.6 Styles of Uncertainty (SDAM 2nd Ed)

Powell identifies 8 styles of uncertainty relevant to escalation routing:

| Style | Description | Tier Response |
|-------|------------|---------------|
| Fine-grained variability | Normal operational noise | Execution (TRM handles) |
| Shifts | Gradual distributional change | Operational (tGNN refresh) |
| Bursts | Sudden spikes then reversion | Execution → Operational if persistent |
| Spikes | One-off extreme events | Execution (TRM + Skills) |
| Spatial events | Location-specific disruption | Operational (tGNN rebalance) |
| Systemic events | Network-wide disruption | Strategic (S&OP review) |
| Rare events | Low-probability high-impact | Strategic (policy review) |
| Contingencies | Known unknowns requiring plans | Strategic (scenario planning) |

The Escalation Arbiter classifies the observed uncertainty style to determine routing.

---

## 5. Escalation Arbiter Architecture

### 5.1 Position in the Decision Pipeline

```
Execution Tier (TRMs, <10ms, System 1, inner OODA loop)
    │
    ├── Per-decision: Conformal prediction → Claude Skills (horizontal, existing)
    │
    └── Pattern-level: Decision adjustments recorded
                            │
                            ▼
                   Escalation Arbiter (every 2h, System 2 activation check)
                            │
                            ├── No action: Patterns within tolerance
                            ├── Horizontal: CDC retrain / CDT recalibrate (existing loop)
                            ├── Vertical-Operational: Off-cadence tGNN refresh
                            └── Vertical-Strategic: S&OP policy review request
```

### 5.2 Persistence Detection

The Arbiter's primary input is **persistence signals** — statistical summaries of recent TRM decision adjustments:

```
PersistenceSignal:
    site_key: str               # Which site
    trm_type: str               # Which of the 11 TRM types
    direction: float            # Mean adjustment direction [-1, +1]
    magnitude: float            # Mean |adjustment| as fraction of baseline
    consistency: float          # Fraction of adjustments in dominant direction [0, 1]
    duration_hours: float       # How long the pattern has persisted
    decision_count: int         # Number of decisions in the window
    trigger_reasons: List[str]  # Co-occurring CDC trigger reasons
```

**How persistence is computed**:
1. Query `powell_*_decisions` tables for the last `PERSISTENCE_WINDOW_HOURS` (default: 48h)
2. For each (site_key, trm_type), compute the adjustment = `trm_quantity - engine_baseline_quantity`
3. Normalize by baseline: `adjustment_fraction = adjustment / max(baseline, 1)`
4. Compute running statistics: `direction = mean(sign(adj))`, `magnitude = mean(|adj_fraction|)`, `consistency = max(fraction_positive, fraction_negative)`

### 5.3 Cross-Site Pattern Detection

When multiple sites show the same persistence pattern, the problem is almost certainly at the operational or strategic level:

```
CrossSitePattern:
    affected_sites: List[str]
    fraction_of_sites: float      # Fraction of total sites affected
    dominant_direction: float     # Network-wide adjustment direction
    dominant_trm_types: List[str] # Which TRM types show the pattern
```

### 5.4 Escalation Routing Logic

| Signal Pattern | Diagnosis | Routing | Action |
|---------------|-----------|---------|--------|
| Single TRM, short duration (<24h), low consistency (<0.6) | Execution noise | None | Normal CDC cycle handles it |
| Single TRM, long duration (>48h), high consistency (>0.7) | Local policy drift | Vertical-Operational | tGNN refresh emphasizing this site-product |
| Multiple TRMs (3+), same site, high consistency | Site-level policy error | Vertical-Operational | tGNN refresh + full allocation rebalance |
| 2-3 sites, same direction, same TRM type | Regional shift | Vertical-Operational | tGNN refresh with cross-site coordination |
| >30% of sites, same direction | Network-wide shift | Vertical-Strategic | S&OP GraphSAGE re-inference + policy review |
| Cross-site + demand signal divergence | Market regime change | Vertical-Strategic | Full S&OP consensus board trigger |

### 5.5 Escalation Thresholds

All thresholds are configurable per tenant:

```
PERSISTENCE_WINDOW_HOURS = 48           # Look-back window for pattern detection
CONSISTENCY_THRESHOLD = 0.70            # 70% same-direction → significant
MAGNITUDE_THRESHOLD_OPERATIONAL = 0.20  # 20% avg adjustment → operational escalation
MAGNITUDE_THRESHOLD_STRATEGIC = 0.35    # 35% avg adjustment → strategic escalation
CROSS_SITE_FRACTION = 0.30             # 30% of sites showing pattern → strategic
MIN_DECISIONS_FOR_SIGNAL = 20           # Minimum decisions before pattern is meaningful
COOLDOWN_OPERATIONAL_HOURS = 12         # Min time between operational escalations
COOLDOWN_STRATEGIC_HOURS = 72           # Min time between strategic escalations
```

### 5.6 Escalation Actions

**Horizontal (existing CDC loop)**:
- TRM retrain via `CDCRetrainingService`
- CDT recalibration via `CDTCalibrationService`
- No change to current behavior

**Vertical-Operational**:
- Request off-cadence tGNN re-inference via `InterHiveSignalService`
- Include persistence evidence in the refresh context
- tGNN incorporates anomaly data into its next allocation computation

**Vertical-Strategic**:
- Create `AuthorizationRequest` targeting S&OP consensus board via AAP
- Include persistence evidence, affected sites/products, and recommended policy adjustments
- In copilot mode: format for human review via `EscalationFormatter`
- In autonomous mode: S&OP agents evaluate and may auto-adjust policy parameters

### 5.7 Audit Trail

All escalation events are logged to `powell_escalation_log` with:
- Site(s) affected, TRM types involved
- Persistence evidence (direction, magnitude, consistency, duration)
- Cross-site pattern data
- Escalation level (horizontal/operational/strategic)
- Recommended action and diagnosis
- Resolution status and outcome

### 5.8 Scheduling

```
Existing relearning schedule:
  :30 — OutcomeCollector (SiteAgentDecision)
  :32 — OutcomeCollector (TRM decisions)
  :33 — OutcomeCollector (Skills decisions)
  :35 — CDT calibration
  :45 — CDC retraining evaluation (every 6h)

New:
  :40 — Escalation Arbiter evaluation (every 2h)
```

The 2-hour cadence balances responsiveness with avoiding false positives. The 48-hour look-back window means the Arbiter sees ~24 evaluations' worth of data.

### 5.9 Urgency + Likelihood: Decision Stream Prioritization

The Escalation Arbiter handles *vertical* routing (which tier replans). The Decision Stream handles *human* routing (which decisions need a planner's attention). These are complementary mechanisms — the Arbiter detects *systemic* failure patterns, while the Decision Stream surfaces *individual* decisions that need human judgment.

Every TRM decision carries two scores:

- **Urgency** (0.0–1.0): Time-sensitivity derived from the agent's UrgencyVector, HiveSignalBus state, and exception severity. A rush order with depleted inventory scores high. A routine restock with weeks of supply scores low.
- **Likelihood** (0.0–1.0): Agent confidence that the recommended action resolves the issue. Derived from TRM output confidence, conformal prediction interval width, and CDT risk bounds.

**The four quadrants**:

| | Low Likelihood | High Likelihood |
|---|---|---|
| **High Urgency** | **Human needed** — top of Decision Stream. Clock is ticking and the agent's best guess isn't good enough. This is where human expertise creates the most value. | **Autonomous** — agent acts within guardrails, logged for awareness. |
| **Low Urgency** | **Abandoned** — not worth anyone's time. Recorded for audit/training but excluded from the active stream. | **Autonomous** — agent acts within guardrails, logged for awareness. |

**Abandonment uses a sliding scale**: `urgency + likelihood` must exceed a configurable threshold (default: 0.5). The lower the urgency, the higher the likelihood must be to survive. High-urgency decisions are never abandoned — the Kahneman insight applies: when time pressure is high and the agent is uncertain, that is precisely when System 2 (human judgment) must engage.

**Relationship to confidence routing**: Confidence routing (Section 5.1) determines which *model* makes the decision (TRM vs. exception handler). Urgency+likelihood prioritization determines which decisions *humans see*. A decision can be handled by the TRM (high confidence in the confidence router) but still surface in the Decision Stream because the underlying situation is urgent and the outcome likelihood is uncertain.

**Relationship to vertical escalation**: The Arbiter detects *patterns* across many decisions. Urgency+likelihood operates on *individual* decisions. A single high-urgency/low-likelihood decision triggers human review. A persistent pattern of such decisions triggers vertical escalation. Both mechanisms can fire independently — a planner might override a single high-urgency decision (urgency+likelihood) while the Arbiter simultaneously detects that the pattern across 50 similar decisions indicates a policy error (vertical escalation).

---

## 6. Implementation Files

| File | Purpose |
|------|---------|
| `backend/app/services/powell/escalation_arbiter.py` | Escalation Arbiter service |
| `backend/app/models/escalation_log.py` | PowellEscalationLog SQLAlchemy model |
| `backend/migrations/versions/20260228_escalation_arbiter.py` | Database migration |
| `backend/app/services/powell/cdc_monitor.py` | Extended ReplanAction enum |
| `backend/app/services/powell/site_agent.py` | Decision recording for arbiter |
| `backend/app/services/powell/relearning_jobs.py` | Scheduled arbiter evaluation |

---

## 7. Relationship to Existing Architecture

### 7.1 Conformal Prediction Router (Horizontal)

The existing conformal prediction router handles **per-decision** uncertainty:
- TRM confidence < threshold → Claude Skills
- This is System 1 → System 1' (a different fast reasoner)
- Operates at decision time (<10ms + Skills latency)

The Escalation Arbiter handles **pattern-level** failure:
- Persistent directional drift → Higher-tier replanning
- This is System 1 pattern → System 2 activation
- Operates asynchronously (every 2h)

### 7.2 CDC Monitor (Horizontal)

The existing CDC monitor detects threshold violations and triggers TRM retraining:
- Single-event triggers (inventory too low, service level dropped)
- Routes to `ReplanAction` (FULL_CFA, TGNN_REFRESH, ALLOCATION_ONLY, PARAM_ADJUSTMENT)

The Escalation Arbiter extends this with persistence analysis:
- Multi-event patterns across time and space
- New `ReplanAction` values: VERTICAL_OPERATIONAL, VERTICAL_STRATEGIC
- Operates on a different cadence (2h vs event-driven)

### 7.3 Agentic Authorization Protocol (Cross-Authority)

Strategic escalation uses the existing AAP infrastructure:
- `AuthorizationRequest` with persistence evidence
- S&OP consensus board evaluates policy change proposals
- Human escalation via `EscalationFormatter` in copilot mode

### 7.4 Multi-Site Coordination Stack

The existing 4-layer stack gains a vertical dimension:

| Layer | Existing Function | Escalation Addition |
|-------|------------------|-------------------|
| 1. Intra-Hive | UrgencyVector + HiveSignalBus | Persistence signals collected here |
| 2. tGNN Inter-Hive | Daily allocations + directives | Off-cadence refresh triggered by Arbiter |
| 3. AAP Cross-Authority | Authorization negotiation | Strategic escalation routed through AAP |
| 4. S&OP Consensus | Weekly policy parameters | Anomaly-triggered policy review |

---

## 8. References

- Kahneman, D. (2011). *Thinking, Fast and Slow*. Farrar, Straus and Giroux.
- Boyd, J. R. (1987). *A Discourse on Winning and Losing*. OODA Loop concept.
- Bergamaschi Ganapini, M., et al. (2021). *Thinking Fast and Slow in AI*. arxiv:2110.01834.
- Powell, W. B. (2026). *Bridging Reinforcement Learning and Stochastic Optimization, Vol I: Framing*. Kindle.
- Powell, W. B. (2026). *Sequential Decision Analytics and Modeling, 2nd Edition*. Kindle.
- Samsung SAIL Montreal (2025). TRM architecture. arxiv:2510.04871.
