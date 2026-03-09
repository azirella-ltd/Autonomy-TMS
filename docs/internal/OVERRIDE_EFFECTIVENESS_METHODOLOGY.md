# Override Effectiveness: Methodology for Causal Attribution

## 1. The Problem

When a human planner overrides an agent's decision, the platform must answer:

> **Was the override beneficial, neutral, or detrimental to outcomes?**

This is fundamentally a **causal inference** question. We observe one reality (the world where the human's decision was executed) and must estimate a counterfactual (what would have happened if the agent's recommendation had been followed). We can never observe both simultaneously — the *fundamental problem of causal inference* (Holland, 1986).

The answer matters for two reasons:

1. **Training weights**: Overrides become expert demonstrations in the TRM replay buffer. If we weight bad overrides at 2x, we train the agent to replicate human mistakes. If we correctly weight them, the agent learns *only* from genuinely better human judgment.

2. **Executive dashboard**: The Override Effectiveness Rate tells the SC VP whether human oversight is adding value or creating friction — and whether the organization can safely increase agent autonomy.

### 1.1 Why Hard Thresholds Are Insufficient

The current implementation classifies overrides by computing `delta = human_reward - agent_counterfactual_reward` and applying hard thresholds:

```
delta >= +0.05  → BENEFICIAL
delta <= -0.05  → DETRIMENTAL
otherwise       → NEUTRAL
```

This has three problems:

1. **False certainty**: A delta of +0.06 gets the same classification as +0.50, despite radically different confidence levels.
2. **Ignores observability**: An ATP override with 4-hour feedback and direct demand observation produces a high-confidence delta. A safety stock override with 14-day feedback and heavy confounding produces a nearly meaningless delta. Both get the same classification treatment.
3. **No learning**: The thresholds are static. The system doesn't get better at evaluating overrides as it accumulates more data.

---

## 2. The Observability Spectrum

Not all TRM decision types are created equal when it comes to counterfactual estimation. The key variables are:

| Factor | Makes Counterfactual Easier | Makes Counterfactual Harder |
|--------|----------------------------|---------------------------|
| **Feedback horizon** | Short (hours) | Long (weeks) |
| **Confounding** | Low (outcome depends mainly on this decision) | High (outcome depends on many simultaneous decisions) |
| **State observability** | Full (actual demand/supply observed) | Partial (can't observe what *would* have been demanded) |
| **Decision reversibility** | Irreversible (committed action) | Partially reversible (other interventions can compensate) |

### 2.1 TRM Types by Observability Tier

**Tier 1 — Direct Analytical Counterfactual** (high confidence)

| TRM Type | Horizon | Why Counterfactual is Feasible |
|----------|---------|-------------------------------|
| ATP Executor | 4 hours | Agent promised X units, human overrode to Y units. Actual demand was D. We can directly compute fill rates for both. Delivery timing is independent of the ATP quantity decision. |
| Forecast Adjustment | 30 days | Agent adjusted forecast to F_a, human overrode to F_h. Actual demand D is eventually observed. Error = \|F - D\|. Both errors are directly computable. |
| Quality Disposition | 2 days | Agent recommended "accept", human overrode to "rework". Outcome (customer complaint, rework success) is directly observable and attributable. |

For these types, the counterfactual reward can be computed analytically by substituting the agent's action into the observed environment. The causal link between action and outcome is strong and direct.

**Tier 2 — Statistical Counterfactual** (moderate confidence)

| TRM Type | Horizon | Confounders | Approach |
|----------|---------|-------------|----------|
| MO Execution | 3 days | Production line state, other orders in queue | Matched-pair comparison with similar MOs |
| TO Execution | 5 days | Transit variability, consolidation effects | Matched-pair with similar routes |
| Order Tracking | 3 days | Supplier behavior, other order changes | Propensity-score matching |
| PO Creation | 7 days | Supplier lead time variability, demand changes during lead time | Bayesian + matched-pair when data permits |

For these types, we can't analytically compute the counterfactual because the outcome depends on factors beyond the overridden decision. But we *can* find similar historical situations where the agent's recommendation was followed and compare outcomes statistically.

**Tier 3 — Bayesian Prior Only** (low initial confidence, improves over time)

| TRM Type | Horizon | Why Counterfactual is Hard |
|----------|---------|--------------------------|
| Safety Stock | 14 days | A safety stock change affects service level over weeks. During those weeks, demand, supply, and dozens of other decisions also affect service level. Attributing the outcome to *this specific SS change* requires disentangling all those effects. |
| Inventory Buffer | 14 days | Same as safety stock — the outcome is a function of the entire inventory system state, not just this one buffer adjustment. |
| Maintenance | 7 days | Equipment failure is stochastic. The human deferred maintenance, no breakdown occurred — was that luck or judgment? Sample sizes per equipment type are small. |
| Subcontracting | 14 days | External vendor performance introduces uncontrollable variance. The human chose a different vendor — was their quality better because of the vendor choice, or because of the batch? |

For these types, the honest answer is: **we don't know yet**. The Bayesian framework correctly represents this uncertainty.

---

## 3. The Bayesian Framework

### 3.1 Core Idea

Instead of a hard BENEFICIAL/NEUTRAL/DETRIMENTAL label, maintain a **Beta distribution posterior** for each override context:

```
p(effective | data) ~ Beta(α, β)
```

Where:
- α = count of "success" signals (override demonstrably better)
- β = count of "failure" signals (override demonstrably worse)
- E[p] = α / (α + β) — the expected effectiveness rate
- Var[p] = αβ / ((α+β)²(α+β+1)) — uncertainty decreases as data accumulates

### 3.2 Prior Selection

**Uninformative prior: Beta(1, 1)**

This is the uniform distribution on [0, 1], encoding "we have no idea whether this human's overrides are good or bad." The expected effectiveness starts at 50%.

This is the right default because:
- It makes no assumption about human quality
- It produces conservative training weights (≈1.0, the same as non-expert data)
- It converges to the truth as evidence accumulates

**Alternative: Weakly informative prior: Beta(2, 1)**

If we believe humans override *for a reason* and that reason is usually sound (the "expert prior"), we can start at 67% expected effectiveness. This gives a slight initial boost to override training weight while still allowing negative evidence to dominate.

**Recommendation**: Use Beta(1, 1) for new users/new TRM types. Allow promotion to Beta(2, 1) after a user demonstrates consistent beneficial overrides across Tier 1 decision types.

### 3.3 Posterior Updates

When an outcome is observed for an overridden decision:

```python
# Tier 1: Strong signal — full update
if tier == 1:
    if delta > 0:
        α += 1.0           # Full success count
    elif delta < 0:
        β += 1.0           # Full failure count
    # else: no update (truly neutral)

# Tier 2: Moderate signal — fractional update
elif tier == 2:
    confidence = min(1.0, matched_pair_count / 20)  # More matches = more confidence
    if delta > 0:
        α += confidence
    elif delta < 0:
        β += confidence

# Tier 3: Weak signal — minimal update
elif tier == 3:
    # Only update when we have high confidence (many confounders controlled for)
    if causal_estimate_confidence > 0.7:
        signal_strength = 0.3  # Still discounted
        if delta > 0:
            α += signal_strength
        elif delta < 0:
            β += signal_strength
```

### 3.4 From Posterior to Training Weight

The Beta posterior maps to training weights through:

```python
def posterior_to_weight(alpha, beta):
    """Convert Beta posterior to TRM training sample weight."""
    expected = alpha / (alpha + beta)
    n = alpha + beta - 2  # Effective observation count (subtract prior)

    # Scale: 0.3 (detrimental) to 2.0 (proven beneficial)
    # At 50% (uninformative), weight = 0.85 (slight discount for uncertainty)
    weight = 0.3 + 1.7 * expected

    # Uncertainty discount: reduce weight when we're unsure
    # With <5 observations, cap the maximum weight
    certainty = min(1.0, n / 10)
    max_weight = 0.85 + 1.15 * certainty  # 0.85 → 2.0 as certainty grows
    weight = min(weight, max_weight)

    return weight
```

This produces:

| Observations | E[p] | Training Weight | Interpretation |
|-------------|-------|----------------|----------------|
| 0 (prior only) | 0.50 | 0.85 | Slight discount for unknown quality |
| 3 beneficial, 0 harmful | 0.80 | 1.12 | Growing confidence, but capped |
| 10 beneficial, 2 harmful | 0.83 | 1.71 | Strong evidence, approaching full expert weight |
| 20 beneficial, 3 harmful | 0.87 | 1.78 | Near-full expert weight |
| 0 beneficial, 5 harmful | 0.14 | 0.54 | Significant discount |
| 1 beneficial, 10 harmful | 0.15 | 0.37 | Near-minimum weight |

### 3.5 Granularity: What Gets Its Own Posterior?

The posterior should be maintained at the intersection of:

1. **User** (or user group): Different humans have different override quality
2. **TRM type**: A human may be excellent at forecast adjustments but poor at safety stock decisions
3. **Site** (optional): Context-specific expertise

This gives us a posterior table:

```
(user_id, trm_type) → Beta(α, β)
```

With optional site-level refinement:
```
(user_id, trm_type, site_key) → Beta(α, β)
```

When insufficient data exists at the site level, fall back to the (user, trm_type) aggregate. When insufficient data exists at the user level, fall back to the global (trm_type) aggregate.

---

## 4. Causal Inference: Can It Be Learned?

**Yes.** The user's question — "can causality be learned over time" — has a clear affirmative answer. Here's how:

### 4.1 The Accumulating Natural Experiment

Every time the system operates, it generates two types of observations:

1. **Treatment group**: Decisions where a human overrode the agent
2. **Control group**: Decisions where the agent's recommendation was followed

Both groups operate in the same environment (same demand patterns, same supply constraints, same time period). Over time, this creates a growing observational dataset suitable for causal inference.

The key insight: **the system doesn't need randomized controlled trials**. It needs enough observational data with sufficient state variation to statistically control for confounders.

### 4.2 Techniques That Improve With Data

**Level 1: Propensity Score Matching (available early)**

Match each overridden decision to the most similar non-overridden decision based on state at decision time:

```
For overridden decision d with state S_d:
    Find d' where:
        - d'.trm_type == d.trm_type
        - d'.site_key == d.site_key (or similar site)
        - d' was NOT overridden
        - ||S_d - S_d'|| is minimized (state similarity)

    Causal estimate = outcome(d) - outcome(d')
```

Requirements: ~50 matched pairs per TRM type to begin producing reliable estimates. The system should track match quality and only use high-quality matches.

**Level 2: Doubly Robust Estimation (moderate data)**

Combines propensity scoring with outcome regression for more robust estimates. Less sensitive to model misspecification than either approach alone.

```
CATE(s) = E[Y(1) - Y(0) | S=s]
        ≈ μ₁(s) - μ₀(s) + (T/π(s)) * (Y - μ₁(s)) - ((1-T)/(1-π(s))) * (Y - μ₀(s))

Where:
  T = 1 if overridden, 0 if not
  π(s) = P(override | state=s)  — propensity score
  μ₁(s), μ₀(s) = outcome regression models
```

Requirements: ~200+ observations per TRM type.

**Level 3: Causal Forests (rich data)**

Heterogeneous treatment effect estimation using random forests adapted for causal inference (Athey & Imbens, 2018). This is the most powerful approach because it identifies *when* overrides help vs. hurt:

```
"Human overrides of Safety Stock are beneficial when:
  - Demand CV > 0.3 (high volatility — human pattern recognition adds value)
  - Lead time recently increased (human notices before formal data update)

Human overrides of Safety Stock are detrimental when:
  - System is stable (low CV, steady demand — human adds noise)
  - Multiple overrides in short succession (overcorrection pattern)"
```

Requirements: ~1000+ observations per TRM type. But the payoff is enormous — the system learns *the conditions under which human judgment adds value*.

### 4.3 The Causality Learning Pipeline

```
Phase 0 (Day 1):
    Bayesian prior only — Beta(1,1) for all (user, trm_type)
    Training weight ≈ 0.85 for all overrides
    Dashboard shows: "Insufficient data for effectiveness measurement"

Phase 1 (Weeks 1-4, ~50 override observations per type):
    Tier 1 types: Analytical counterfactual computes deltas
    Tier 2-3 types: Bayesian posterior begins updating
    Training weights diverge by type for Tier 1
    Dashboard shows: Tier 1 effectiveness rates with confidence intervals

Phase 2 (Months 1-3, ~200 override observations per type):
    Propensity score matching produces first Tier 2 estimates
    Bayesian posteriors for Tier 3 are meaningfully non-uniform
    Per-user posteriors begin diverging (some humans better than others)
    Dashboard shows: Tier 1-2 effectiveness rates, Tier 3 "learning..."

Phase 3 (Months 3-6, ~500+ observations per type):
    Doubly robust estimation refines Tier 2 estimates
    First causal forest models trained for high-volume Tier 2 types
    System begins identifying WHEN overrides help vs. hurt
    Dashboard shows: "Override value conditions" report

Phase 4 (Months 6+, ~1000+ observations per type):
    Full causal forest models for all types with sufficient data
    Heterogeneous treatment effects: per-state override value estimates
    Agent can predict BEFORE a human overrides whether the override will be beneficial
    Dashboard shows: "Predicted override value" alongside worklist items
```

### 4.4 The Confounding Problem in Detail

Consider a concrete example of why Tier 3 is hard:

**Scenario**: Safety Stock Override

```
State at decision time:
  - Product: Widget-A at Site DC-East
  - Current SS: 100 units
  - Agent recommends: Maintain at 100 (no change)
  - Human overrides: Increase to 150

Observed outcome (2 weeks later):
  - No stockout occurred
  - Service level: 100%
  - Average on-hand inventory: 142 units

Question: Was the override beneficial?
```

The naive answer is "no stockout, so the override was good." But:

- Would 100 units have also prevented stockout? If max daily demand was 60 and lead time was 1 day, then 100 was plenty.
- Did other decisions change during those 2 weeks? Maybe a PO was expedited that would have prevented stockout anyway.
- Did the human have private information (e.g., a customer called about a big upcoming order that wasn't in the forecast yet)?

**How the system resolves this over time**:

1. **Analytical partial counterfactual**: Given actual demand realization D over the period and observed lead times, compute minimum SS that would have prevented stockout. If min_required_SS = 80, then both 100 and 150 were sufficient — the override was NEUTRAL (excess inventory cost with no service benefit).

2. **Matched-pair**: Find 10 other cases where Widget-A at DC-East (or similar product-site) had SS=100 and similar demand patterns. What was their stockout rate? If 0/10 had stockouts, the override was probably unnecessary.

3. **Private information capture**: The override reason text may contain "customer ABC placing large order next week." This is a **signal** that the forecast adjustment TRM should have processed. If so, the override is BENEFICIAL but for the wrong reason — it compensates for a signal ingestion gap, not a safety stock calculation error.

---

## 5. Implementation Plan

### 5.1 Schema Changes

**New model: `OverrideEffectivenessPosterior`**

```python
class OverrideEffectivenessPosterior(Base):
    """Bayesian posterior for override effectiveness by (user, trm_type)."""
    __tablename__ = "override_effectiveness_posteriors"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    trm_type = Column(String(50), nullable=False)
    site_key = Column(String(100), nullable=True)  # Optional site-level refinement

    # Beta distribution parameters
    alpha = Column(Float, default=1.0)  # Success count + prior
    beta = Column(Float, default=1.0)   # Failure count + prior

    # Derived (updated on each observation)
    expected_effectiveness = Column(Float, default=0.5)  # α/(α+β)
    observation_count = Column(Integer, default=0)  # Total observations
    training_weight = Column(Float, default=0.85)  # Derived from posterior

    # Metadata
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "trm_type", "site_key",
                         name="uq_posterior_user_trm_site"),
        Index("idx_posterior_user_trm", "user_id", "trm_type"),
    )
```

**New model: `CausalMatchPair`**

```python
class CausalMatchPair(Base):
    """Matched pairs for propensity-score-based causal inference."""
    __tablename__ = "override_causal_match_pairs"

    id = Column(Integer, primary_key=True)
    overridden_decision_id = Column(Integer, ForeignKey("powell_site_agent_decisions.id"))
    control_decision_id = Column(Integer, ForeignKey("powell_site_agent_decisions.id"))

    trm_type = Column(String(50), nullable=False)
    state_distance = Column(Float)  # ||S_override - S_control||
    propensity_score = Column(Float)  # P(override | state)

    # Outcomes
    override_reward = Column(Float)
    control_reward = Column(Float)
    treatment_effect = Column(Float)  # override_reward - control_reward

    match_quality = Column(String(20))  # HIGH, MEDIUM, LOW
    created_at = Column(DateTime, server_default=func.now())
```

### 5.2 Service: `OverrideEffectivenessService`

Core service that replaces the hard-threshold classification with Bayesian updating:

```python
class OverrideEffectivenessService:
    """
    Bayesian override effectiveness with tiered causal inference.

    Maintains Beta distribution posteriors per (user, trm_type) and
    updates them with evidence-weighted signals based on the observability
    tier of each decision type.
    """

    TIER_MAP = {
        # Tier 1: Direct analytical counterfactual
        "atp_executor": 1,
        "atp_exception": 1,
        "forecast_adjustment": 1,
        "quality": 1,

        # Tier 2: Statistical counterfactual (matched pairs)
        "mo": 2,
        "to": 2,
        "order_tracking": 2,
        "po": 2,
        "po_timing": 2,

        # Tier 3: Bayesian prior only (high confounding)
        "inventory_buffer": 3,
        "inventory_adjustment": 3,
        "safety_stock": 3,
        "rebalancing": 3,
        "maintenance": 3,
        "subcontracting": 3,
    }

    def update_posterior(self, user_id, trm_type, delta, site_key=None):
        """Update the Beta posterior based on observed override outcome."""
        tier = self.TIER_MAP.get(trm_type, 3)
        posterior = self._get_or_create_posterior(user_id, trm_type, site_key)

        signal_strength = self._compute_signal_strength(tier, delta)

        if delta > 0:
            posterior.alpha += signal_strength
        elif delta < 0:
            posterior.beta += signal_strength

        posterior.observation_count += 1
        posterior.expected_effectiveness = posterior.alpha / (posterior.alpha + posterior.beta)
        posterior.training_weight = self._posterior_to_weight(
            posterior.alpha, posterior.beta
        )

    def get_training_weight(self, user_id, trm_type, site_key=None):
        """Get current training weight for an override from this user on this TRM type."""
        posterior = self._get_posterior(user_id, trm_type, site_key)
        if posterior is None:
            return 0.85  # Default for unknown
        return posterior.training_weight

    def _compute_signal_strength(self, tier, delta):
        """How much to update the posterior based on tier and delta magnitude."""
        if tier == 1:
            return 1.0  # Full update
        elif tier == 2:
            return 0.5  # Partial update (will increase with matched pairs)
        else:
            return 0.15  # Minimal update (high confounding)

    def _posterior_to_weight(self, alpha, beta):
        """Convert Beta posterior to training sample weight."""
        expected = alpha / (alpha + beta)
        n = alpha + beta - 2  # Subtract prior pseudo-counts

        weight = 0.3 + 1.7 * expected  # Scale to [0.3, 2.0]

        certainty = min(1.0, max(0, n) / 10)
        max_weight = 0.85 + 1.15 * certainty
        weight = min(weight, max_weight)

        return round(weight, 3)
```

### 5.3 Service: `CausalMatchingService`

Builds matched pairs for Tier 2 estimation:

```python
class CausalMatchingService:
    """
    Propensity-score matching for Tier 2 causal inference.

    Runs periodically (daily) to match overridden decisions with
    similar non-overridden decisions and compute treatment effects.
    """

    def find_matches(self, trm_type, lookback_days=90, max_matches=5):
        """Find control matches for each unmatched overridden decision."""
        # 1. Load overridden decisions without matches
        # 2. Load non-overridden decisions in same period
        # 3. Compute state distance (L2 norm of normalized state vectors)
        # 4. For each overridden decision, find top-k nearest controls
        # 5. Compute treatment effect = override_reward - mean(control_rewards)
        # 6. Store match pairs

    def compute_propensity_scores(self, trm_type):
        """Train logistic regression: P(override | state) for better matching."""
        # Uses all decisions (overridden and not) as training data
        # Features: normalized state vector components
        # Target: was_overridden (0/1)
        # Used to weight matched pairs by inverse propensity
```

### 5.4 Modifications to Existing Code

**`outcome_collector.py`**: Replace hard classification with Bayesian update

```python
# Current (hard threshold):
if delta >= 0.05: classification = "BENEFICIAL"

# New (Bayesian):
effectiveness_service.update_posterior(
    user_id=decision.override_user_id,
    trm_type=decision.decision_type,
    delta=delta,
    site_key=decision.site_key,
)
# Still store the point classification for display/filtering,
# but training weight comes from the posterior
```

**`trm_site_trainer.py`**: Replace `_compute_sample_weights` static method

```python
# Current (hard mapping):
if eff == "BENEFICIAL": weights[i] = 2.0

# New (Bayesian posterior):
weights[i] = effectiveness_service.get_training_weight(
    user_id=override_user_ids[i],
    trm_type=self.trm_type,
)
```

### 5.5 Dashboard Additions

**Override Effectiveness tab enhancements:**

1. **Confidence indicators**: Show not just "62% effectiveness rate" but "62% (±15%, based on 23 observations)" using the Beta distribution's credible interval.

2. **Tier badges**: Mark each TRM type with its observability tier so executives understand why some metrics are more reliable than others.

3. **Causality learning progress**: For each TRM type, show how many matched pairs exist and what confidence level has been reached:
   ```
   ATP Executor:      ████████████████████ 95% confidence (Tier 1, analytical)
   MO Execution:      ████████████░░░░░░░░ 62% confidence (Tier 2, 47 matched pairs)
   Safety Stock:      ███░░░░░░░░░░░░░░░░░ 18% confidence (Tier 3, Bayesian only)
   ```

4. **Per-user effectiveness**: Show which planners produce the best overrides, by TRM type. This naturally supports training/coaching conversations.

5. **Override value conditions** (Phase 3+): When causal forests are available, show the conditions under which overrides add value:
   ```
   "Safety Stock overrides are beneficial when demand CV > 0.3 and
    trending up. They are detrimental when the system is stable."
   ```

### 5.6 Implementation Phases

**Phase A (Immediate — completes current implementation)**
- Add `OverrideEffectivenessPosterior` model
- Create `OverrideEffectivenessService` with Beta updating
- Wire into `OutcomeCollectorService` (replace hard thresholds as primary, keep hard labels as secondary/display)
- Wire into `TRMSiteTrainer._compute_sample_weights` (fetch from posterior)
- Update dashboard to show confidence intervals

**Phase B (Week 2-3 — matched pair infrastructure)**
- Add `CausalMatchPair` model
- Create `CausalMatchingService`
- Add daily scheduled job for match finding
- Upgrade Tier 2 signal strength to use matched-pair count
- Dashboard: show matched pair counts and treatment effects

**Phase C (Month 2-3 — causal forests, requires ~500+ observations)**
- Implement causal forest training (scikit-learn `CausalForestDML` or custom)
- Generate heterogeneous treatment effect estimates
- Upgrade Tier 2 and 3 signal strengths using forest confidence
- Dashboard: "Override Value Conditions" report
- Agent pre-decision: predict whether incoming override will be beneficial

---

## 6. The Causality Learning Loop

To directly address the question: **can causality be learned over time?**

Yes. The system implements a progressive causal learning loop:

```
                 ┌─────────────────────────────────────────┐
                 │                                         │
    Decision     │   Bayesian         Matched-Pair         │   Causal Forest
    Observed ───►│   Posterior  ───►  Comparison   ───►    │   (HTE Model)
                 │   Update           (when pairs          │
                 │   (always)          available)           │
                 │                                         │
                 └──────────────────┬──────────────────────┘
                                    │
                                    ▼
                        Training Weight for
                        Replay Buffer Sample
                                    │
                                    ▼
                          TRM Agent Learns
                          (weighted by causal
                           evidence, not faith)
```

The critical property: **the system is honest about what it doesn't know**. Early on, with few observations, training weights stay near 1.0 (we don't amplify uncertain data). As evidence accumulates and causal estimates sharpen, weights diverge — good overrides get amplified, bad ones get suppressed.

This is fundamentally different from the original approach of blindly setting `is_expert=True, weight=2.0` on all overrides. That approach assumes the answer. The Bayesian approach *discovers* the answer.

### 6.1 The Self-Correcting Property

The system has a self-correcting property that prevents degenerate outcomes:

1. If overrides are genuinely beneficial → posterior increases → weight increases → agent learns from them → agent improves → fewer overrides needed (humans override less because agent is better)

2. If overrides are detrimental → posterior decreases → weight decreases → agent ignores them → agent maintains quality → human sees agent outperforming → overrides decrease

3. If overrides are mixed → per-type posteriors diverge → agent learns from beneficial types only → targeted improvement

In all three cases, the system converges toward correct behavior. The Bayesian framework prevents catastrophic training corruption from bad overrides while still extracting value from good ones.

---

## 7. Summary of Recommendations

1. **Replace hard thresholds with Bayesian Beta posteriors** as the primary mechanism for override effectiveness scoring. Keep hard labels (BENEFICIAL/NEUTRAL/DETRIMENTAL) as secondary display labels derived from the posterior.

2. **Use tiered signal strengths**: Tier 1 (analytical counterfactual) gets full Bayesian updates; Tier 2 (statistical) gets partial updates scaled by matched-pair availability; Tier 3 (high confounding) gets minimal updates that grow as causal models improve.

3. **Start with uninformative priors Beta(1,1)**: Training weights begin at ~0.85 for all overrides. This is conservative but safe — it prevents bad overrides from being amplified at 2x before we have evidence.

4. **Build matched-pair infrastructure early**: Even before full causal forests, propensity-score matching provides meaningful estimates for Tier 2 types.

5. **Plan for causal forests at ~500+ observations**: These provide the highest-value insight — *when* overrides help, not just *whether* they help.

6. **Make uncertainty visible in the dashboard**: Show confidence intervals, not point estimates. Show the tier of each TRM type. Show the learning progress. Executives should understand that "62% effectiveness ± 15%" means something very different from "62% effectiveness ± 2%".

---

## 8. Systemic Impact: Local vs. Site-Level Override Effectiveness

### 8.1 The Problem of Local Optimality

Decision-level counterfactual comparison (Sections 2-4) answers: **"Did this override produce a better outcome for this specific decision?"** But this misses a critical dimension: **"Did this override improve or degrade the site's overall performance?"**

**Example**: A planner reallocates inventory from a standard order to a priority customer order. The decision-level delta is strongly positive (priority order ships on time). But the standard order now misses its SLA, and two more orders behind it are also delayed. The site's overall OTIF drops by 3%. The override was **locally beneficial but systemically harmful**.

This is the classic **local vs. global optimization** problem. Supply chain decisions are coupled — changing one allocation affects all other allocations sharing the same resource pool.

### 8.2 Three-Scope Measurement

Override effectiveness should be measured at three scopes:

| Scope | Question | Method | Current? |
|-------|----------|--------|----------|
| **Decision-local** | Did *this* decision achieve a better outcome? | Counterfactual comparison (Section 3) | Yes |
| **Site-window** | Did the *site's aggregate BSC* improve in the feedback window? | Pre/post window comparison | **Yes (new)** |
| **Network-ripple** | Did *downstream sites* experience degradation? | Cross-site causal tracing | Future (requires tGNN directives) |

### 8.3 Site-Window BSC Comparison

After an override at time `t` for site `site_key`, the system computes:

```
Pre-override window:  [t - feedback_horizon, t)
Post-override window: [t, t + feedback_horizon]

BSC_pre  = aggregate_bsc(all decisions at site_key in pre-window)
BSC_post = aggregate_bsc(all decisions at site_key in post-window)

site_bsc_delta = (BSC_post.composite - BSC_pre.composite) / max(|BSC_pre.composite|, 0.01)
```

The BSC proxy aggregates four metrics from all decisions at the same site:

| Metric | Weight | Interpretation |
|--------|--------|---------------|
| Mean reward signal | 40% | Overall decision quality at site |
| Positive reward rate | 30% | % of decisions with positive outcomes (service success) |
| Reward stability (1/(1+variance)) | 20% | Operational consistency (low variance = stable operations) |
| Negative reward rate (subtracted) | 10% | Service failures — captures the downstream damage from resource reallocation |

The `site_bsc_delta` is normalized to [-1, +1]:
- **> 0**: Site performance improved after the override (systemically beneficial)
- **≈ 0**: No detectable systemic effect (locally contained override)
- **< 0**: Site performance degraded (override helped one thing, hurt others)

### 8.4 Composite Override Score

The composite score combines local and systemic measurements:

```python
composite = 0.4 * local_delta + 0.6 * site_bsc_delta
```

The site-level BSC receives **higher weight** (60%) because it captures the aggregate reality. A planner who consistently makes locally-correct overrides that degrade the overall site will see their composite score — and therefore their Bayesian posterior — reflect the systemic damage.

**Fallback**: When insufficient site data exists for BSC comparison (< 3 decisions in either window), the composite falls back to the decision-local delta alone.

### 8.5 Impact on Training Weights

The composite score is what feeds into the Bayesian posterior update (Section 3.3), **not** the local delta alone. This means:

```
Planner makes 10 overrides:
  - 8 are locally beneficial (positive local_delta)
  - But 6 of those cause site-level degradation (negative site_bsc_delta)
  - Composite scores: 3 positive, 5 negative, 2 neutral
  - Posterior: E[p] drifts toward ~0.40, training_weight ≈ 0.68

vs. blind 2x weighting: all 10 would have been weighted at 2.0
vs. local-only Bayesian: E[p] would be ~0.80, training_weight ≈ 1.66
```

The composite approach correctly captures that this planner's overrides are net-negative for the site, even though they look individually impressive.

### 8.6 Limitations and Future Work

**Current limitations**:
- Site-window BSC is correlational, not causal. Other events in the window (new orders, demand spikes, upstream disruptions) also affect BSC. The comparison attributes all change to the override.
- Only considers the override decision's own site. Cross-site ripple effects (e.g., a rebalance override that depletes origin site) are not yet captured.
- Requires sufficient decision density at the site for meaningful comparison.

**Future: Network Ripple Graph** (requires tGNN integration):
- Tag downstream decisions that share a resource pool with the override
- Compute per-decision ripple deltas using the tGNN's attention weights to identify causal paths
- Weight ripple effects by causal proximity (direct impact > indirect impact)

**Future: Bayesian Structural Time Series**:
- Use CausalImpact-style analysis (Brodersen et al., 2015) to estimate the override's causal effect on site KPIs
- Accounts for trends, seasonality, and other contemporaneous events
- Requires 20+ pre-override time points for reliable estimation

---

## 9. Mathematical Appendix: Bayesian Beta Posterior

### 9.1 Why Beta-Binomial?

The Beta distribution is the conjugate prior for the Bernoulli/Binomial likelihood. Since we're modeling a binary outcome (override beneficial or not), the Beta-Binomial model is the natural Bayesian choice:

```
Prior:      p ~ Beta(α₀, β₀)
Likelihood: X_i ~ Bernoulli(p)        [each override outcome is a "success" or "failure"]
Posterior:  p | data ~ Beta(α₀ + Σxᵢ, β₀ + n - Σxᵢ)
```

**Conjugacy** means the posterior has the same functional form as the prior, which:
- Makes updates O(1) — just increment α or β
- Avoids MCMC or numerical integration
- Provides closed-form credible intervals via the Beta quantile function
- Is computationally trivial (runs in microseconds, no GPU needed)

### 9.2 Prior Selection Rationale

**Beta(1, 1)** — the uniform distribution on [0, 1]:

```
E[p] = 1/(1+1) = 0.50
Var[p] = 1·1 / (2²·3) = 1/12 ≈ 0.083
```

This encodes maximal ignorance: "we assign equal probability to every possible effectiveness rate." The training weight at this prior is 0.85, which is a slight discount from the non-expert weight of 1.0 — reflecting the principle that unvalidated human overrides should receive *less* than default credence, not more.

**Why not Beta(2, 1) (optimistic)?** An optimistic prior assumes humans override for good reasons. While plausible, this assumption can be wrong — confirmation bias, status quo bias, and anchoring affect planner decision-making. Starting neutral lets the data speak.

**Why not Beta(5, 5) (peaked at 0.5)?** A peaked prior resists early evidence. With Beta(5, 5), it takes 4+ observations to move the posterior meaningfully. Beta(1, 1) is more responsive to initial data, which is desirable when we want the system to learn quickly.

### 9.3 Signal Strength and Fractional Updates

Not all observations carry the same evidentiary weight. The signal strength scales the update:

```
Standard update:      α += 1.0  (if beneficial)
Tier 2 update:        α += s₂   where s₂ ∈ [0.3, 0.9], scaled by matched-pair count
Tier 3 update:        α += 0.15 (minimal — high confounding)
```

Fractional updates preserve the Beta conjugacy structure. A fractional update of `s` is mathematically equivalent to observing `s` fraction of a Bernoulli trial. The posterior remains a valid Beta distribution.

**Signal strength for Tier 2** scales with matched-pair availability:

```python
s₂ = min(0.9, 0.3 + (matched_pairs / 50) * 0.6)
```

At 0 matched pairs: s₂ = 0.3 (weak signal, like slightly better than Tier 3)
At 20 matched pairs: s₂ = 0.54 (moderate signal)
At 50+ matched pairs: s₂ = 0.9 (approaching Tier 1 confidence)

### 9.4 Posterior-to-Weight Mapping

The training weight must satisfy:
1. **Monotonically increasing in E[p]** — better overrides → higher weight
2. **Bounded** — range [0.3, 2.0] prevents extreme amplification/suppression
3. **Uncertainty-discounted** — few observations → weight capped near 0.85

```python
weight = 0.3 + 1.7 * E[p]                    # Linear mapping [0,1] → [0.3, 2.0]
certainty = min(1.0, max(0, n) / 10)          # n = effective observations
max_weight = 0.85 + 1.15 * certainty          # Cap: 0.85 → 2.0 as n grows
weight = min(weight, max_weight)               # Apply cap
```

This produces the following training weight surface:

```
E[p] ↓ / Observations →   0     3     5     10    20+
0.20 (detrimental)       0.64  0.64  0.64  0.64  0.64
0.50 (uninformative)     0.85  0.85  1.15  1.15  1.15
0.70 (moderate)          0.85  1.05  1.27  1.49  1.49
0.85 (proven effective)  0.85  1.10  1.44  1.75  1.75
0.95 (excellent)         0.85  1.10  1.44  2.00  2.00
```

**Key properties**:
- At n=0, all weights are 0.85 regardless of E[p] — we don't trust uninformed priors
- The diagonal converges: as data accumulates, the weight approaches the "true" mapping
- Detrimental overrides are suppressed to 0.64 even with few observations (the Bayesian framework is asymmetrically cautious about bad evidence)

### 9.5 Credible Intervals

The 90% credible interval uses the Beta quantile function:

```python
from scipy.stats import beta
CI_90 = [beta.ppf(0.05, α, β), beta.ppf(0.95, α, β)]
```

Example credible intervals:

```
Beta(1, 1):     CI₉₀ = [0.05, 0.95]  → "We know almost nothing"
Beta(5, 2):     CI₉₀ = [0.39, 0.93]  → "Probably effective, but uncertain"
Beta(15, 5):    CI₉₀ = [0.54, 0.88]  → "Likely effective, narrowing"
Beta(50, 10):   CI₉₀ = [0.73, 0.89]  → "Confidently effective"
Beta(3, 12):    CI₉₀ = [0.08, 0.37]  → "Confidently ineffective"
```

When scipy is unavailable, a normal approximation is used:

```python
mean = α / (α + β)
std = sqrt(α * β / ((α + β)² * (α + β + 1)))
CI_90 ≈ [mean - 1.645 * std, mean + 1.645 * std]
```

---

## 10. Causal Inference: Technical Deep-Dive

### 10.1 The Fundamental Problem

Following Holland (1986), for each override decision `i`, we want:

```
τᵢ = Yᵢ(1) - Yᵢ(0)
```

Where `Yᵢ(1)` is the outcome under override (observed) and `Yᵢ(0)` is the outcome without override (counterfactual, never observed). We can only ever observe one of these.

**Tier 1 (Analytical Counterfactual)**: For ATP and Forecast Adjustment, the counterfactual is mechanistically computable. The agent recommended `X`, the human chose `Y`, and the environment realization `E` is observed. We can compute `reward(X, E)` and `reward(Y, E)` directly.

**Tier 2 (Statistical Counterfactual)**: For MO, TO, PO, etc., the outcome depends on confounders `C` (production line state, transit conditions, supplier behavior). We estimate the counterfactual by finding a control decision with similar `(state, confounders)` that was not overridden.

**Tier 3 (Weak Signal)**: For Safety Stock, Inventory, Maintenance, the confounders are numerous and long-acting. Direct causal attribution requires either strong modeling assumptions or very large sample sizes.

### 10.2 Propensity Score Matching (Tier 2)

**Goal**: Estimate the Average Treatment Effect on the Treated (ATT):

```
ATT = E[Y(1) - Y(0) | T=1]
    ≈ (1/n) Σᵢ [Yᵢ - Ŷ_match(i)]    for overridden decisions i
```

**Steps**:
1. **Propensity model**: Train logistic regression `P(override | state) = σ(w·s + b)` using all decisions (overridden and not)
2. **Matching**: For each overridden decision, find the k nearest non-overridden decisions by state distance, weighted by propensity score
3. **Treatment effect**: `τ̂ᵢ = reward_override - mean(reward_controls)`
4. **Quality filter**: Only keep matches with `state_distance < threshold` and `propensity_score ∈ [0.1, 0.9]` (avoid extreme propensities)

**Match quality classification**:
- **HIGH**: state_distance < 0.1, |propensity_score_diff| < 0.1
- **MEDIUM**: state_distance < 0.3, |propensity_score_diff| < 0.2
- **LOW**: state_distance < 0.5 (used with caution)

**Data requirements**: ~50 matched pairs per TRM type for initial estimates, ~200+ for reliable ATT.

### 10.3 Doubly Robust Estimation (Phase 3)

Combines propensity scoring with outcome regression for robustness against model misspecification:

```
τ̂_DR = (1/n) Σ [ T/π(s) · (Y - μ₁(s)) - (1-T)/(1-π(s)) · (Y - μ₀(s)) + μ₁(s) - μ₀(s) ]
```

This is consistent if **either** the propensity model π(s) **or** the outcome model μ(s) is correctly specified. The dual protection makes it the preferred estimator when both models are available.

### 10.4 Causal Forests (Phase 4, Athey & Imbens 2018)

Generalized Random Forests adapted for causal inference enable **heterogeneous treatment effect** estimation:

```
τ̂(s) = E[Y(1) - Y(0) | S=s]
```

This answers not just "are overrides beneficial?" but "**when** are overrides beneficial?"

**Example output for Safety Stock TRM**:

```
Override value conditions (learned from 1,200+ observations):
  - BENEFICIAL when: demand_cv > 0.35 AND lead_time_trend = increasing
    (Human notices supply risk before formal data update. Average benefit: +0.12)
  - DETRIMENTAL when: demand_cv < 0.15 AND system_stable = True
    (Human adds noise to already-optimal decision. Average harm: -0.08)
  - NEUTRAL when: supplier_count > 3
    (Multiple sources buffer against either decision. No significant difference.)
```

**Requirements**: ~1,000+ observations per TRM type with sufficient state variation.

### 10.5 Causal Learning Timeline

```
Data Volume        Method Available              Dashboard Shows
──────────        ────────────────              ───────────────
Day 1             Bayesian prior Beta(1,1)       "Awaiting data"
~20 overrides     Tier 1 analytical CFs          Effectiveness ± wide CI
~50 overrides     Propensity matching begins      Tier 2 estimates appear
~200 overrides    Doubly robust estimation        CI narrows significantly
~500 overrides    Causal forest training          "Override value conditions"
~1000+ overrides  Full heterogeneous effects      Predictive override scoring
```

---

## References

- Holland, P.W. (1986). "Statistics and Causal Inference." *JASA*, 81(396), 945-960.
- Athey, S. & Imbens, G.W. (2018). "Estimation and Inference of Heterogeneous Treatment Effects using Random Forests." *JASA*, 113.
- Rubin, D.B. (2005). "Causal Inference Using Potential Outcomes." *JASA*, 100(469), 322-331.
- Powell, W.B. (2022). *Sequential Decision Analytics and Modeling*. — Sections on VFA and belief state management directly apply to the posterior maintenance.
- Brodersen, K.H. et al. (2015). "Inferring causal impact using Bayesian structural time series models." *Annals of Applied Statistics*, 9(1), 247-274. — Foundation for future site-level causal impact analysis.
- Rosenbaum, P.R. & Rubin, D.B. (1983). "The central role of the propensity score in observational studies for causal effects." *Biometrika*, 70(1), 41-55. — Theoretical basis for Tier 2 propensity-score matching.
