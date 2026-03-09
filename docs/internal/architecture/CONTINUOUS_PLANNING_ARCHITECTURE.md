# Continuous Planning Architecture: Event-Driven AI Agents with Git-Like Versioning

**Document Version**: 2.0
**Date**: January 24, 2026
**Status**: Design Proposal (Updated with Native Capabilities & Stochastic Planning)
**Author**: AI Architecture Team

---

## Table of Contents

1. [Continuous Planning Paradigm](#1-continuous-planning-paradigm)
   - 1.1 [Traditional Cadence-Based Planning](#11-traditional-cadence-based-planning-current-state)
   - 1.2 [Continuous Event-Driven Planning](#12-continuous-event-driven-planning-proposed)
   - 1.3 [Event Taxonomy](#13-event-taxonomy)
   - 1.4 [Stochastic Planning: Planning with Uncertainty](#14-stochastic-planning-planning-with-uncertainty)
   - 1.5 [Conformal Prediction: Distribution-Free Uncertainty Quantification](#15-conformal-prediction-distribution-free-uncertainty-quantification)
   - 1.6 [Centralized vs. Decentralized Planning Modes](#16-centralized-vs-decentralized-planning-modes)
2. [Event-Driven Architecture](#2-event-driven-architecture)
3. [Git-Like Plan Versioning](#3-git-like-plan-versioning)
4. [Incremental CDC Snapshotting](#4-incremental-cdc-snapshotting)
5. [LLM-First UI Paradigm](#5-llm-first-ui-paradigm)
6. [Daily Data Import Flow](#6-daily-data-import-flow)
7. [Multi-Layer Agent Coordination](#7-multi-layer-agent-coordination)
   - 7.4 [Native Supply Chain Intelligence & Stochastic Planning](#74-native-supply-chain-intelligence--stochastic-planning)
   - 7.5 [Automate-Inform-Inspect-Override (AIIO) Framework](#75-automate-inform-inspect-override-aiio-framework)
8. [Order Promising and Tracking: Continuous ATP/CTP](#8-order-promising-and-tracking-continuous-atpctp)
9. [Database Schema Extensions](#9-database-schema-extensions)
10. [Implementation Roadmap](#10-implementation-roadmap)
11. [Performance Analysis](#11-performance-analysis)

---

## 1. Continuous Planning Paradigm

### 1.1 Traditional Cadence-Based Planning (Current State)

**Problems with Cadence-Based**:
```
Weekly MPS Cycle:
- Monday: Import SAP data (master + transactional)
- Tuesday: Run MPS generation (batch job)
- Wednesday: Material planners review exceptions
- Thursday: Approve and release MPS
- Friday: Publish to execution systems

Issues:
❌ 5-day latency from data to action
❌ Monday's demand spike not addressed until Thursday
❌ Manual batch review of 1000s of SKUs
❌ "Plan once, execute blindly" until next cycle
❌ Cannot react to intra-week disruptions
```

### 1.2 Continuous Event-Driven Planning (Proposed)

**Event-Driven Advantages**:
```
Continuous Planning Loop:
- Event detected: New customer order arrives (via SAP CDC)
- Agent triggered: MPS agent evaluates impact on capacity
- Agent replans: Adjusts affected weeks for impacted SKUs only
- Agent publishes: New plan version committed to branch
- Human notified: Exception alert sent to planner (if threshold exceeded)
- Plan executed: Incremental changes flow to ERP

Benefits:
✅ Minutes from event to replanning (vs. days)
✅ Only affected SKUs replanned (not entire catalog)
✅ Continuous optimization (not batch)
✅ Human-in-the-loop for exceptions only
✅ Real-time responsiveness to disruptions
```

### 1.3 Event Taxonomy

**Planning Events** (triggers for agent replanning):

| Event Type | Example | Triggered Agent | Replan Scope |
|------------|---------|-----------------|--------------|
| **Demand Events** | New customer order | MPS Agent | Affected finished goods |
| **Supply Events** | Supplier shipment delay | MRP Agent | Downstream components |
| **Capacity Events** | Machine breakdown | Capacity Agent | Alternative routings |
| **Inventory Events** | Cycle count variance | Inventory Agent | Safety stock recalc |
| **Policy Events** | Inventory target change | Policy Agent | Dependent plans |
| **Forecast Events** | Demand plan update | Demand Agent | Forecast-driven SKUs |
| **Exception Events** | Service level breach | Escalation Agent | Root cause analysis |

**Event Priority Levels**:
- **P0 (Critical)**: Customer order at risk, stockout imminent → Immediate agent response (<1 min)
- **P1 (High)**: Material shortage, capacity constraint → Agent response within 5 min
- **P2 (Medium)**: Inventory target deviation, forecast change → Agent response within 1 hour
- **P3 (Low)**: Planning parameter optimization, policy tuning → Agent response within 24 hours

### 1.4 Stochastic Planning: Planning with Uncertainty

**Why Stochastic Planning Matters**:

Traditional planning uses **point estimates** (single values):
- Demand forecast: 100 units
- Lead time: 7 days
- Production yield: 95%

This creates **false precision** - plans appear certain but reality is uncertain.

**Stochastic planning uses probability distributions**:
- Demand: Lognormal(μ=100, σ=20) → 80% of outcomes between 85-120 units
- Lead time: Gamma(shape=7, scale=1.2) → 70% between 6-9 days
- Production yield: Beta(α=95, β=5) → 90% between 93%-97%

**Benefits**:

| Traditional (Deterministic) | Stochastic (Probabilistic) |
|-----------------------------|----------------------------|
| "We need 100 units" | "We need P50=100 units, with 80% confidence between 85-115" |
| "Safety stock: 20 units" | "Safety stock: 20 units achieves 95% service level probability" |
| "This plan costs $50K" | "Expected cost: $50K, 90% confidence: $48K-$55K" |
| Plan looks certain, but fails 30% of the time | Plan explicitly quantifies uncertainty, achieves targets 95% of time |

**Implementation in Continuous Planning**:

```python
# Traditional: Single forecast value
demand_forecast = 100  # Point estimate

# Stochastic: Distribution of outcomes
demand_distribution = {
    'type': 'lognormal',
    'mean': 100,
    'std_dev': 20,
    'p10': 78,   # 10th percentile
    'p50': 100,  # Median
    'p90': 125   # 90th percentile
}

# Monte Carlo simulation: Run 1000 scenarios
scenarios = []
for i in range(1000):
    demand = sample_from_distribution(demand_distribution)
    lead_time = sample_from_distribution(lead_time_distribution)
    yield_rate = sample_from_distribution(yield_distribution)

    # Simulate plan outcome with these variables
    outcome = simulate_supply_chain(demand, lead_time, yield_rate)
    scenarios.append(outcome)

# Analyze results probabilistically
results = {
    'expected_cost': np.mean([s.cost for s in scenarios]),  # $50,250
    'cost_p10': np.percentile([s.cost for s in scenarios], 10),  # $47,800
    'cost_p90': np.percentile([s.cost for s in scenarios], 90),  # $54,200
    'service_level_probability': np.mean([s.service_level > 0.95 for s in scenarios]),  # 87%
    'stockout_probability': np.mean([s.has_stockout for s in scenarios])  # 13%
}
```

**20 Distribution Types Supported**:

- **Continuous**: Normal, Lognormal, Gamma, Beta, Weibull, Exponential, Triangular, Uniform
- **Discrete**: Poisson, Binomial, Negative Binomial, Discrete Uniform
- **Advanced**: Mixture distributions, Empirical (historical data), Truncated distributions
- **Multivariate**: Correlated distributions (e.g., demand across products)

**Where Stochastic Planning is Used**:

1. **Risk Detection** (Section 7.4): Monte Carlo simulation identifies stockout/excess risks proactively
2. **Recommendation Scoring** (Section 7.4): Agents evaluate actions using probabilistic outcomes
3. **Safety Stock Optimization**: Calculate required inventory for target service level with uncertainty
4. **Order Promising**: ATP/CTP with probabilistic delivery dates
5. **Scenario Planning**: "What-if" analysis with distributions, not point estimates
6. **Plan vs. Actual**: Compare actual outcomes to forecasted probability distributions

**Balanced Scorecard with Probability**:

Instead of single-point KPIs, agents optimize toward **probabilistic targets**:

```python
kpi_targets = {
    'service_level': {
        'target': 'P(OTIF > 95%) ≥ 90%',  # 90% chance of achieving >95% OTIF
        'current': 'P(OTIF > 95%) = 87%'   # Current probability
    },
    'total_cost': {
        'target': 'E[Cost] < $1M, P90 < $1.1M',  # Expected cost <$1M, worst-case <$1.1M
        'current': 'E[Cost] = $1.05M, P90 = $1.15M'
    },
    'inventory_days': {
        'target': 'E[DOS] = 30 days ± 5',  # Expected 30 days, low variance
        'current': 'E[DOS] = 35 days ± 8'
    }
}
```

### 1.5 Conformal Prediction: Distribution-Free Uncertainty Quantification

**Why Conformal Prediction?**

Stochastic planning (Section 1.4) relies on parametric distributions (normal, lognormal, etc.), which require:
1. **Distribution assumptions** (e.g., "demand follows a normal distribution")
2. **Parameter estimation** (e.g., mean and standard deviation)
3. **Model validation** (check if assumptions hold)

**Problem**: When assumptions are wrong, confidence intervals fail. Actual coverage can be 70% when you claimed 90%.

**Conformal prediction** provides **distribution-free, formally guaranteed** prediction intervals that work **regardless of the underlying distribution**.

**Mathematical Guarantee**:

Given a miscoverage rate α (e.g., 0.10 for 90% confidence), conformal prediction guarantees:

```
P(y_true ∈ prediction_interval) ≥ 1 - α
```

This holds **for any data distribution**, not just normal/lognormal.

**How It Works**:

1. **Calibration Phase**: Collect historical forecast errors (actual - predicted)
2. **Quantile Calculation**: Compute (1-α)-quantile of absolute errors
3. **Prediction Interval**: [point_forecast - quantile, point_forecast + quantile]

**Example Implementation**:

```python
import numpy as np
from typing import List, Tuple

class ConformalPredictor:
    """
    Distribution-free conformal prediction with guaranteed coverage probability.

    Based on:
    - Vovk et al. (2005): "Algorithmic Learning in a Random World"
    - Shafer & Vovk (2008): "A Tutorial on Conformal Prediction"
    - Angelopoulos & Bates (2021): "A Gentle Introduction to Conformal Prediction"
    """

    def __init__(self, alpha: float = 0.1):
        """
        Args:
            alpha: Miscoverage rate (0.1 = 90% guaranteed coverage)
        """
        self.alpha = alpha
        self.calibration_scores = []  # Absolute errors from calibration set
        self.quantile = None

    def calibrate(self, y_true: np.ndarray, y_pred: np.ndarray):
        """
        Calibrate using historical data (Plan vs. Actual).

        Args:
            y_true: Actual outcomes (e.g., realized demand)
            y_pred: Predicted values (e.g., forecasted demand)
        """
        # Compute absolute errors (nonconformity scores)
        self.calibration_scores = np.abs(y_true - y_pred)

        # Calculate (1-α) quantile of errors
        # Use ceiling to guarantee coverage (conservative)
        n = len(self.calibration_scores)
        q_level = np.ceil((n + 1) * (1 - self.alpha)) / n
        self.quantile = np.quantile(self.calibration_scores, q_level)

        coverage = np.mean(np.abs(y_true - y_pred) <= self.quantile)
        print(f"Calibrated: α={self.alpha}, quantile={self.quantile:.2f}, "
              f"empirical coverage={coverage:.1%} (target: {1-self.alpha:.1%})")

    def predict(self, point_forecast: float) -> Tuple[float, float]:
        """
        Generate conformal prediction interval.

        Args:
            point_forecast: Point forecast (e.g., from ML model or statistical forecast)

        Returns:
            (lower_bound, upper_bound) with guaranteed (1-α) coverage
        """
        if self.quantile is None:
            raise ValueError("Must call calibrate() first")

        lower = point_forecast - self.quantile
        upper = point_forecast + self.quantile

        return (lower, upper)

    def predict_with_metadata(self, point_forecast: float) -> dict:
        """
        Generate prediction interval with full metadata.
        """
        lower, upper = self.predict(point_forecast)

        return {
            'point_forecast': point_forecast,
            'lower_bound': lower,
            'upper_bound': upper,
            'interval_width': upper - lower,
            'coverage_guarantee': 1 - self.alpha,
            'miscoverage_rate': self.alpha,
            'quantile': self.quantile,
            'method': 'conformal_prediction'
        }


# Example: Demand forecasting with conformal prediction
class ConformalDemandForecaster:
    """
    Demand forecaster with conformal prediction intervals.
    """

    def __init__(self, base_forecaster, alpha: float = 0.1):
        """
        Args:
            base_forecaster: Any forecasting model (ARIMA, Prophet, ML, etc.)
            alpha: Miscoverage rate (0.1 = 90% guaranteed coverage)
        """
        self.base_forecaster = base_forecaster
        self.conformal = ConformalPredictor(alpha=alpha)
        self.is_calibrated = False

    def fit_and_calibrate(self, train_data: np.ndarray, calibration_data: Tuple[np.ndarray, np.ndarray]):
        """
        1. Train base forecaster on training data
        2. Calibrate conformal predictor on separate calibration set (Plan vs. Actual)

        Args:
            train_data: Historical demand for training forecaster
            calibration_data: (features, actuals) for conformal calibration
        """
        # Train base forecaster
        self.base_forecaster.fit(train_data)

        # Generate predictions on calibration set
        X_cal, y_cal = calibration_data
        y_pred_cal = self.base_forecaster.predict(X_cal)

        # Calibrate conformal predictor
        self.conformal.calibrate(y_cal, y_pred_cal)
        self.is_calibrated = True

    def forecast_with_guarantee(self, horizon: int = 13) -> List[dict]:
        """
        Generate demand forecast with guaranteed prediction intervals.

        Returns:
            List of forecasts with conformal intervals for each period
        """
        if not self.is_calibrated:
            raise ValueError("Must call fit_and_calibrate() first")

        forecasts = []
        for t in range(1, horizon + 1):
            # Get point forecast from base model
            point_forecast = self.base_forecaster.predict(t)

            # Generate conformal interval
            interval = self.conformal.predict_with_metadata(point_forecast)
            interval['period'] = t
            forecasts.append(interval)

        return forecasts


# Usage example
# 1. Calibrate using last 52 weeks of Plan vs. Actual data
historical_forecasts = np.array([100, 95, 110, 105, ...])  # Past forecasts
historical_actuals = np.array([98, 102, 115, 100, ...])    # Actual demand

conformal = ConformalPredictor(alpha=0.05)  # 95% guaranteed coverage
conformal.calibrate(historical_actuals, historical_forecasts)

# 2. Generate prediction for next period
next_period_forecast = 120  # From ML model or statistical forecast
lower, upper = conformal.predict(next_period_forecast)

print(f"Forecast: {next_period_forecast}")
print(f"95% Guaranteed Interval: [{lower:.1f}, {upper:.1f}]")
# Output: "Forecast: 120"
#         "95% Guaranteed Interval: [105.3, 134.7]"
```

**Supply-Side Applications**:

Conformal prediction applies to **all operational variables** with uncertainty:

| Variable | Traditional Approach | Conformal Approach |
|----------|---------------------|-------------------|
| **Demand** | Point forecast or normal distribution | Guaranteed prediction interval (90%, 95%, 99%) |
| **Supplier Lead Time** | Fixed value or empirical distribution | Formal guarantee: "Lead time ∈ [4, 10] days (95% coverage)" |
| **Manufacturing Yield** | Fixed percentage or beta distribution | Guaranteed yield range: "Yield ∈ [93%, 98%] (90% coverage)" |
| **Machine Uptime** | MTBF estimate | Guaranteed availability: "Uptime ∈ [85%, 95%] (95% coverage)" |
| **Transportation Time** | Fixed transit time | Guaranteed delivery window: "Arrival ∈ [2, 5] days (99% coverage)" |

**Conformal Decision Theory (CDT)**:

Use conformal intervals to **calibrate decisions** with formal risk guarantees:

```python
class ConformalDecisionMaker:
    """
    Make supply chain decisions with formal risk bounds using conformal prediction.
    """

    def calculate_safety_stock_with_guarantee(
        self,
        demand_conformal: ConformalPredictor,
        lead_time_conformal: ConformalPredictor,
        target_service_level: float = 0.95
    ) -> dict:
        """
        Calculate safety stock with formal service level guarantee.

        Traditional approach:
        - SS = z * σ_demand * sqrt(lead_time)
        - Assumes normal demand, fixed lead time
        - No guarantee on actual service level

        Conformal approach:
        - SS = max(demand_upper) * max(lead_time_upper) - expected_demand
        - No distribution assumptions
        - Formal guarantee on service level
        """
        # Get demand prediction interval
        expected_demand = 100  # Point forecast
        demand_lower, demand_upper = demand_conformal.predict(expected_demand)

        # Get lead time prediction interval
        expected_lead_time = 7  # Point forecast (days)
        lt_lower, lt_upper = lead_time_conformal.predict(expected_lead_time)

        # Worst-case scenario for safety stock (high demand, long lead time)
        worst_case_demand_during_lt = demand_upper * (lt_upper / expected_lead_time)

        # Safety stock = worst-case - expected
        safety_stock = worst_case_demand_during_lt - (expected_demand * (expected_lead_time / expected_lead_time))

        # Coverage probability = joint coverage (assuming independence)
        coverage_prob = (1 - demand_conformal.alpha) * (1 - lead_time_conformal.alpha)

        return {
            'safety_stock': safety_stock,
            'expected_demand': expected_demand,
            'demand_interval': (demand_lower, demand_upper),
            'lead_time_interval': (lt_lower, lt_upper),
            'service_level_guarantee': coverage_prob,
            'method': 'conformal_decision_theory'
        }

    def order_promising_with_guarantee(
        self,
        order_qty: int,
        due_date: int,  # Days from now
        inventory_on_hand: int,
        production_rate_conformal: ConformalPredictor,
        yield_conformal: ConformalPredictor
    ) -> dict:
        """
        Promise order delivery with formal confidence level.

        Returns:
            - can_promise: True/False
            - confidence_level: Formal guarantee (e.g., 0.95)
            - alternative_dates: If can't meet due_date, when can we deliver?
        """
        # Calculate production capacity with conformal intervals
        expected_production_rate = 50  # units/day
        prod_lower, prod_upper = production_rate_conformal.predict(expected_production_rate)

        expected_yield = 0.95
        yield_lower, yield_upper = yield_conformal.predict(expected_yield)

        # Conservative estimate: lower bound of production and yield
        guaranteed_production = prod_lower * yield_lower * due_date + inventory_on_hand

        # Can we promise with formal guarantee?
        can_promise = guaranteed_production >= order_qty

        # Joint confidence level
        confidence = (1 - production_rate_conformal.alpha) * (1 - yield_conformal.alpha)

        if not can_promise:
            # Calculate alternative date where we can guarantee delivery
            shortfall = order_qty - inventory_on_hand
            days_needed = np.ceil(shortfall / (prod_lower * yield_lower))
            alternative_date = days_needed
        else:
            alternative_date = due_date

        return {
            'can_promise': can_promise,
            'confidence_level': confidence,
            'requested_due_date': due_date,
            'guaranteed_due_date': alternative_date if not can_promise else due_date,
            'guaranteed_production': guaranteed_production,
            'required_qty': order_qty,
            'method': 'conformal_atp'
        }
```

**Integration with Agents**:

Agents use conformal prediction for:
1. **Risk Detection**: Formal guarantees on stockout probability
2. **Decision Making**: Conformal decision theory for safety stock, order promising
3. **Plan Evaluation**: Compare plans using guaranteed coverage, not assumed distributions
4. **What-If Analysis**: Scenario bounds with formal confidence levels

**Database Schema for Conformal Prediction**:

```sql
-- Store conformal calibration data
CREATE TABLE conformal_calibration (
    calibration_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    variable_name VARCHAR(100) NOT NULL,  -- 'demand', 'lead_time', 'yield', etc.
    product_id VARCHAR(100),
    site_id VARCHAR(100),
    alpha NUMERIC NOT NULL,  -- Miscoverage rate (0.05, 0.10, etc.)
    quantile NUMERIC NOT NULL,  -- Calibrated quantile value
    calibration_data JSONB NOT NULL,  -- Historical errors
    calibration_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    n_samples INTEGER NOT NULL,  -- Size of calibration set
    empirical_coverage NUMERIC,  -- Actual coverage achieved
    INDEX idx_variable (variable_name, product_id, site_id)
);

-- Store conformal prediction intervals
CREATE TABLE conformal_predictions (
    prediction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    calibration_id UUID REFERENCES conformal_calibration(calibration_id),
    forecast_date DATE NOT NULL,
    point_forecast NUMERIC NOT NULL,
    lower_bound NUMERIC NOT NULL,
    upper_bound NUMERIC NOT NULL,
    interval_width NUMERIC GENERATED ALWAYS AS (upper_bound - lower_bound) STORED,
    coverage_guarantee NUMERIC NOT NULL,  -- 1 - alpha
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    INDEX idx_forecast_date (forecast_date)
);
```

**Benefits Over Traditional Stochastic Planning**:

| Aspect | Stochastic Planning | Conformal Prediction |
|--------|---------------------|----------------------|
| **Distribution Assumptions** | Requires (normal, lognormal, etc.) | None (distribution-free) |
| **Coverage Guarantee** | Approximate (if assumptions hold) | **Formal mathematical guarantee** |
| **Robustness** | Fails when distribution changes | Adapts automatically to any distribution |
| **Complexity** | Must validate distribution fit | Simple quantile calculation |
| **Use Cases** | Internal planning, well-behaved data | **Customer commitments, SLAs, contracts** |

---

### 1.6 Centralized vs. Decentralized Planning Modes

**Two Planning Paradigms**:

Traditional supply chain planning systems (SAP IBP, Kinaxis, o9) use **centralized planning**:
- Single planning system with global visibility
- Optimizes entire network simultaneously
- Requires full data sharing across all sites

Our system supports **both centralized and decentralized** modes:

| Planning Mode | Visibility | Optimization Scope | Communication Pattern |
|---------------|------------|-------------------|----------------------|
| **Centralized** | Global (all sites, all data) | Network-wide (minimize total cost) | Hub-and-spoke (HQ → sites) |
| **Decentralized** | Local (own site + inbound orders) | Site-level (local objectives) | Peer-to-peer (site → site) |
| **Hybrid** | Selective (strategic centralized, operational decentralized) | Multi-level | Mixed |

**Centralized Planning Architecture**:

```
┌─────────────────────────────────────────────────────────┐
│            CENTRAL PLANNING SYSTEM (HQ)                 │
│  - Full visibility: demand, inventory, capacity         │
│  - Global optimization: minimize network cost           │
│  - Generates plans for all sites                        │
└────────────┬────────────────────────────────────────────┘
             │
             ├──► Site A: Receives production plan
             ├──► Site B: Receives replenishment plan
             ├──► Site C: Receives sourcing plan
             └──► Site D: Receives allocation plan
```

**Decentralized Planning Architecture** (Beer Game Model):

```
Market Demand
     ↓ (orders)
Site A (Retailer) → Plans based on customer orders + local inventory
     ↓ (orders upstream)
Site B (Wholesaler) → Plans based on Site A orders + local inventory
     ↓ (orders upstream)
Site C (Distributor) → Plans based on Site B orders + local inventory
     ↓ (orders upstream)
Site D (Factory) → Plans based on Site C orders + production capacity
```

**Key Difference**: In decentralized mode, **sites only see local information**:
- Site B doesn't know Site A's demand or inventory
- Site C doesn't know Site B's orders or Site A's actual demand
- Each site treats upstream/downstream sites as "black boxes"

**Trade-offs**:

| Factor | Centralized | Decentralized |
|--------|-------------|---------------|
| **Response Time** | Slow (must coordinate) | **Fast (local autonomy)** |
| **Network Optimization** | **Optimal (global view)** | Suboptimal (local decisions) |
| **Bullwhip Effect** | Low (central coordinator dampens) | **High (2-10x amplification)** |
| **Scalability** | Limited (central bottleneck) | **High (distributed)** |
| **Data Sharing** | Required (full transparency) | **Minimal (orders only)** |
| **Org Structure Fit** | Centralized organizations | **Autonomous divisions, franchises** |

**Bullwhip Effect in Decentralized Mode**:

The **bullwhip effect** is demand amplification through the supply chain:
- Customer demand variance: σ² = 10
- Retailer order variance: σ² = 20 (2x)
- Wholesaler order variance: σ² = 50 (5x)
- Distributor order variance: σ² = 100 (10x)

**Root causes**:
1. **Local optimization**: Each site over-orders to buffer uncertainty
2. **Information asymmetry**: Upstream sites don't see actual demand, only inflated orders
3. **Lead time padding**: Sites add safety buffer to orders
4. **Batch ordering**: Sites aggregate small orders into large batches

**Mitigating Bullwhip with Conformal Prediction**:

Use conformal prediction to **provide formal guarantees to downstream sites**, reducing need for over-ordering:

```python
class ConformalBullwhipMitigation:
    """
    Reduce bullwhip effect using conformal prediction for demand sharing.
    """

    def __init__(self, alpha: float = 0.10):
        self.conformal_demand = ConformalPredictor(alpha=alpha)

    def share_demand_signal_with_guarantee(
        self,
        downstream_site_id: str,
        upstream_site_id: str,
        forecast_horizon: int = 13
    ) -> dict:
        """
        Downstream site shares demand forecast with upstream, including
        conformal prediction interval for transparency.

        This reduces upstream over-ordering because upstream site knows
        the demand range with formal guarantee.
        """
        # Get downstream demand forecast
        point_forecast = self.forecast_demand(downstream_site_id, forecast_horizon)

        # Add conformal interval
        lower, upper = self.conformal_demand.predict(point_forecast)

        # Share with upstream
        demand_signal = {
            'from_site': downstream_site_id,
            'to_site': upstream_site_id,
            'forecast_horizon': forecast_horizon,
            'point_forecast': point_forecast,
            'guaranteed_interval': (lower, upper),
            'coverage_probability': 1 - self.conformal_demand.alpha,
            'message': f"We expect {point_forecast} units, with 90% guarantee it will be between {lower} and {upper}"
        }

        return demand_signal

    def calculate_order_with_formal_guarantee(
        self,
        demand_signal: dict,
        local_inventory: int,
        lead_time_conformal: ConformalPredictor
    ) -> dict:
        """
        Upstream site calculates order using conformal interval from downstream,
        instead of inflating based on worst-case assumptions.
        """
        # Use upper bound of demand forecast (conservative)
        demand_upper = demand_signal['guaranteed_interval'][1]

        # Use upper bound of lead time
        expected_lt = 7
        lt_lower, lt_upper = lead_time_conformal.predict(expected_lt)

        # Calculate order quantity with formal risk bound
        required_inventory = demand_upper * (lt_upper / 7)  # Demand during max lead time
        order_qty = max(0, required_inventory - local_inventory)

        # Joint coverage probability
        coverage = demand_signal['coverage_probability'] * (1 - lead_time_conformal.alpha)

        return {
            'order_qty': order_qty,
            'coverage_guarantee': coverage,
            'bullwhip_ratio': order_qty / demand_signal['point_forecast'],  # Should be <2 with conformal
            'method': 'conformal_order_planning'
        }
```

**Result**: Bullwhip ratio reduced from 5-10x to 1.5-2.5x by using conformal intervals for transparent demand sharing.

**OODA Loop for Decentralized Agents**:

Each site runs its own **OODA Loop** (Observe-Orient-Decide-Act):

```
OBSERVE:
- Monitor local inventory levels
- Track incoming orders from downstream
- Observe shipments from upstream

ORIENT:
- Forecast local demand (with conformal prediction)
- Assess inventory position (on-hand + pipeline - backlog)
- Evaluate lead time uncertainty (conformal interval)

DECIDE:
- Calculate order quantity using conformal decision theory
- Determine production schedule (if manufacturer)
- Allocate inventory to downstream orders

ACT:
- Place order upstream
- Fulfill downstream orders
- Adjust safety stock targets
```

**Implementation**:

```python
class DecentralizedNodeAgent:
    """
    Autonomous planning agent for a single supply chain site.
    Operates in decentralized mode with local information only.
    """

    def __init__(self, node_id: str, node_type: str):
        self.node_id = node_id
        self.node_type = node_type  # 'retailer', 'wholesaler', 'distributor', 'factory'

        # Conformal predictors for uncertainty quantification
        self.conformal_demand = ConformalPredictor(alpha=0.10)  # 90% guarantee
        self.conformal_lead_time = ConformalPredictor(alpha=0.10)
        self.conformal_yield = ConformalPredictor(alpha=0.05) if node_type == 'factory' else None

        # Local state (only what this node can observe)
        self.inventory_on_hand = 0
        self.pipeline_shipments = []  # Orders placed, not yet received
        self.backlog = []  # Unfilled downstream orders
        self.incoming_orders = []  # Orders from downstream

    async def ooda_loop(self):
        """
        Continuous OODA loop for autonomous planning.
        """
        while True:
            # OBSERVE
            observations = await self.observe()

            # ORIENT
            situation = await self.orient(observations)

            # DECIDE
            decision = await self.decide(situation)

            # ACT
            await self.act(decision)

            await asyncio.sleep(60)  # Run every minute

    async def observe(self) -> dict:
        """
        OBSERVE: Collect local data (no access to upstream/downstream internal state).
        """
        return {
            'inventory_on_hand': self.inventory_on_hand,
            'pipeline_shipments': self.pipeline_shipments,
            'backlog': len(self.backlog),
            'incoming_orders_today': len(self.incoming_orders),
            'timestamp': datetime.utcnow()
        }

    async def orient(self, observations: dict) -> dict:
        """
        ORIENT: Assess situation using conformal prediction for demand and lead time.
        """
        # Forecast demand with conformal interval
        demand_forecast = self.forecast_local_demand()
        demand_lower, demand_upper = self.conformal_demand.predict(demand_forecast)

        # Estimate lead time with conformal interval
        expected_lead_time = self.get_expected_lead_time()
        lt_lower, lt_upper = self.conformal_lead_time.predict(expected_lead_time)

        # Calculate inventory position
        inventory_position = (
            observations['inventory_on_hand'] +
            sum([s['qty'] for s in self.pipeline_shipments]) -
            observations['backlog']
        )

        return {
            'demand_forecast': demand_forecast,
            'demand_interval': (demand_lower, demand_upper),
            'lead_time_interval': (lt_lower, lt_upper),
            'inventory_position': inventory_position,
            'coverage_guarantee': (1 - self.conformal_demand.alpha) * (1 - self.conformal_lead_time.alpha)
        }

    async def decide(self, situation: dict) -> dict:
        """
        DECIDE: Calculate order quantity using conformal decision theory.
        """
        # Conservative approach: use upper bound of demand and lead time
        demand_upper = situation['demand_interval'][1]
        lt_upper = situation['lead_time_interval'][1]

        # Required inventory = demand during worst-case lead time
        required_inventory = demand_upper * lt_upper

        # Order up to required level
        order_qty = max(0, required_inventory - situation['inventory_position'])

        return {
            'action': 'place_order',
            'order_qty': order_qty,
            'reasoning': f"Demand forecast: {situation['demand_forecast']}, "
                        f"Guaranteed interval: {situation['demand_interval']}, "
                        f"Lead time interval: {situation['lead_time_interval']}",
            'confidence_level': situation['coverage_guarantee']
        }

    async def act(self, decision: dict):
        """
        ACT: Execute decision (place order, fulfill downstream).
        """
        if decision['action'] == 'place_order':
            await self.place_order_upstream(decision['order_qty'])
            print(f"[{self.node_id}] Placed order: {decision['order_qty']} units "
                  f"(confidence: {decision['confidence_level']:.1%})")
```

**Multi-Agent Negotiation in Decentralized Mode**:

Sites can temporarily collaborate for **what-if scenarios** without revealing full internal state:

```python
class DecentralizedWhatIfOrchestrator:
    """
    Enable what-if collaboration between autonomous nodes without central coordinator.
    """

    async def propose_whatif_scenario(
        self,
        initiator_node_id: str,
        scenario_description: str,
        affected_nodes: List[str]
    ) -> dict:
        """
        Initiator node proposes a what-if scenario (e.g., "What if I increase my order by 20%?").
        Affected upstream nodes respond with impact assessment.
        """
        # Initiator creates scenario proposal
        proposal = {
            'scenario_id': str(uuid.uuid4()),
            'initiator': initiator_node_id,
            'description': scenario_description,
            'proposed_changes': {
                initiator_node_id: {'order_increase': 0.20}
            },
            'affected_nodes': affected_nodes
        }

        # Broadcast to affected nodes
        responses = {}
        for node_id in affected_nodes:
            node_agent = self.get_node_agent(node_id)
            response = await node_agent.evaluate_whatif_impact(proposal)
            responses[node_id] = response

        # Aggregate responses
        return {
            'scenario_id': proposal['scenario_id'],
            'feasible': all([r['can_accommodate'] for r in responses.values()]),
            'responses': responses,
            'recommendation': self.generate_recommendation(responses)
        }

    async def evaluate_whatif_impact(self, proposal: dict) -> dict:
        """
        Node evaluates what-if proposal using conformal prediction.
        """
        # Calculate impact on local inventory and capacity
        order_increase = proposal['proposed_changes'].get(self.node_id, {}).get('order_increase', 0)

        # Current planned order
        baseline_order = self.calculate_baseline_order()

        # What-if order
        whatif_order = baseline_order * (1 + order_increase)

        # Check if we can accommodate using conformal capacity prediction
        capacity_forecast = self.get_capacity_forecast()
        capacity_lower, capacity_upper = self.conformal_capacity.predict(capacity_forecast)

        can_accommodate = whatif_order <= capacity_lower  # Conservative

        return {
            'node_id': self.node_id,
            'can_accommodate': can_accommodate,
            'baseline_order': baseline_order,
            'whatif_order': whatif_order,
            'capacity_interval': (capacity_lower, capacity_upper),
            'utilization_impact': whatif_order / capacity_upper,
            'confidence': 1 - self.conformal_capacity.alpha
        }
```

---

## 2. Event-Driven Architecture

### 2.1 Event Sourcing Pattern

**Architecture Components**:

```
┌─────────────────────────────────────────────────────────────────┐
│                         EVENT BUS                               │
│  (Apache Kafka / AWS EventBridge / RabbitMQ)                   │
└────────────┬────────────────────────────────────────────────────┘
             │
             ├───► SAP_DATA_IMPORT events
             ├───► DEMAND_CHANGE events
             ├───► SUPPLY_DISRUPTION events
             ├───► CAPACITY_ALERT events
             ├───► POLICY_UPDATE events
             └───► EXCEPTION_RAISED events

             ↓

┌─────────────────────────────────────────────────────────────────┐
│                     AGENT ORCHESTRATOR                          │
│  - Event filtering and routing                                 │
│  - Agent scheduling and prioritization                         │
│  - Conflict detection (multiple agents on same SKU)            │
└────────────┬────────────────────────────────────────────────────┘
             │
             ├───► MPS Agent (Policy Gradient RL)
             ├───► MRP Agent (BOM Explosion + Netting)
             ├───► Inventory Agent (Safety Stock Optimization)
             ├───► Capacity Agent (Constraint Scheduling)
             ├───► Policy Agent (Parameter Tuning)
             └───► LLM Supervisor Agent (Exception Handling)

             ↓

┌─────────────────────────────────────────────────────────────────┐
│                     PLAN VERSIONING SYSTEM                      │
│  - Git-like branches (main, scenarios, hotfixes)               │
│  - Commit plans with timestamps                                │
│  - Merge conflict resolution                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Event Processing Flow

**Event Lifecycle**:

1. **Event Generation** (Source Systems)
   ```python
   # Example: SAP sends new customer order via OData CDC
   event = {
       "event_id": "order-123456",
       "event_type": "DEMAND_CHANGE",
       "timestamp": "2026-01-22T10:30:00Z",
       "source": "SAP_ECC",
       "payload": {
           "order_id": "SO-789",
           "product_id": "CASE",
           "quantity": 1000,
           "requested_date": "2026-02-05",
           "site_id": "DC-001"
       },
       "priority": "P1"  # High priority
   }
   ```

2. **Event Ingestion** (Event Bus)
   ```python
   # Publish to Kafka topic
   producer.send('planning.demand.orders', event)
   ```

3. **Event Routing** (Agent Orchestrator)
   ```python
   # Orchestrator filters events and routes to agents
   @event_handler('DEMAND_CHANGE')
   async def handle_demand_change(event):
       # Check if MPS needs replanning
       affected_skus = get_affected_skus(event)

       # Create agent task
       task = AgentTask(
           agent_type="MPS",
           event_id=event['event_id'],
           products=affected_skus,
           priority=event['priority'],
           context={
               "order_id": event['payload']['order_id'],
               "quantity": event['payload']['quantity'],
               "due_date": event['payload']['requested_date']
           }
       )

       # Dispatch to MPS agent
       await agent_queue.enqueue(task)
   ```

4. **Agent Execution** (MPS Agent)
   ```python
   # MPS agent processes task
   async def mps_agent_execute(task):
       # Load current plan (from Git-like branch)
       current_plan = load_plan_branch('main')

       # Create scenario branch for replanning
       scenario_branch = create_branch('main', f'mps-order-{task.event_id}')

       # Run MPS replanning (only affected SKUs)
       new_plan = run_mps_replan(
           products=task.products,
           horizon=13,  # 13 weeks
           constraints={
               "capacity": load_capacity_constraints(),
               "inventory": load_inventory_targets(),
               "sourcing": load_sourcing_rules()
           }
       )

       # Commit plan to scenario branch
       commit_plan(scenario_branch, new_plan, message=f"MPS replan for order {task.context['order_id']}")

       # Evaluate plan impact
       impact = evaluate_plan_impact(current_plan, new_plan)

       # Auto-merge if low impact, otherwise escalate to human
       if impact['severity'] < THRESHOLD_AUTO_MERGE:
           merge_plan(scenario_branch, 'main')
           publish_plan_to_erp(new_plan)
       else:
           notify_planner(impact, scenario_branch)
   ```

5. **Plan Versioning** (Git-Like System)
   ```python
   # Plan committed to version control
   commit = {
       "commit_id": "abc123",
       "branch": "main",
       "timestamp": "2026-01-22T10:35:00Z",
       "author": "mps-agent",
       "message": "MPS replan for order SO-789",
       "changes": {
           "affected_products": ["CASE", "SIXPACK"],
           "weeks_changed": [5, 6, 7],
           "plan_delta": {
               "CASE": {
                   "week_5": {"before": 100, "after": 120},
                   "week_6": {"before": 100, "after": 110}
               }
           }
       }
   }
   ```

### 2.3 Agent Orchestrator Design

**Orchestrator Responsibilities**:

1. **Event Filtering**: Deduplicate, filter noise, aggregate micro-events
2. **Agent Scheduling**: Priority queue, resource allocation, load balancing
3. **Conflict Detection**: Prevent multiple agents from modifying same SKU simultaneously
4. **Dependency Management**: Ensure Policy Agents run before Execution Agents
5. **Escalation Logic**: Route exceptions to LLM Supervisor or human planners

**Orchestrator Pseudocode**:

```python
class AgentOrchestrator:
    def __init__(self):
        self.event_queue = PriorityQueue()  # P0 > P1 > P2 > P3
        self.agent_pool = {
            'mps': MPSAgentPool(max_workers=4),
            'mrp': MRPAgentPool(max_workers=8),
            'inventory': InventoryAgentPool(max_workers=2),
            'capacity': CapacityAgentPool(max_workers=2),
            'policy': PolicyAgentPool(max_workers=2),
            'llm_supervisor': LLMSupervisorAgent()
        }
        self.locks = {}  # SKU-level locks to prevent conflicts

    async def process_event(self, event):
        # 1. Filter and validate
        if not self.is_valid_event(event):
            return

        # 2. Determine affected scope
        affected_scope = self.get_affected_scope(event)

        # 3. Check for conflicts (other agents working on same SKUs)
        if self.has_conflict(affected_scope):
            # Queue event for retry
            await self.event_queue.enqueue(event, retry_after=60)
            return

        # 4. Acquire locks on affected SKUs
        async with self.acquire_locks(affected_scope):
            # 5. Route to appropriate agent
            agent = self.select_agent(event)

            # 6. Execute agent task
            result = await agent.execute(event, affected_scope)

            # 7. Evaluate result and decide next action
            if result.requires_human_review:
                await self.escalate_to_human(result)
            elif result.requires_downstream_agents:
                # Trigger dependent agents (e.g., MPS changed → trigger MRP)
                await self.trigger_dependent_agents(result)
            else:
                # Auto-commit and publish
                await self.commit_and_publish(result)

    def select_agent(self, event):
        """Route event to appropriate agent based on type"""
        routing_map = {
            'DEMAND_CHANGE': 'mps',
            'SUPPLY_DISRUPTION': 'mrp',
            'CAPACITY_ALERT': 'capacity',
            'POLICY_UPDATE': 'policy',
            'INVENTORY_VARIANCE': 'inventory',
            'EXCEPTION_RAISED': 'llm_supervisor'
        }
        agent_type = routing_map.get(event['event_type'])
        return self.agent_pool[agent_type]
```

---

## 3. Git-Like Plan Versioning

### 3.1 Kinaxis-Inspired Branching Model

**Kinaxis Concepts Mapped to Git**:

| Kinaxis Concept | Git Equivalent | Our Implementation |
|-----------------|----------------|---------------------|
| **Baseline** | `main` branch | Daily SAP import commits to `main` |
| **Scenario** | Feature branch | Agent creates `scenario/mps-order-123` branch |
| **Version History** | Commit log | 4 weeks of plan history retained |
| **Compare Plans** | `git diff` | Plan delta visualization |
| **Rollback** | `git revert` | Revert to previous plan commit |
| **Merge** | `git merge` | Agent auto-merges or escalates to human |

**Branch Strategy**:

```
main (production plan)
├── daily/2026-01-21  (yesterday's baseline)
├── daily/2026-01-22  (today's baseline, current HEAD)
│   ├── scenario/mps-order-789  (MPS agent scenario)
│   ├── scenario/supplier-delay-456  (MRP agent scenario)
│   └── hotfix/stockout-case  (Emergency fix)
└── daily/2026-01-23  (tomorrow's plan, after tonight's import)
```

**Branch Lifecycle**:

1. **Daily Baseline**: Every night at 23:00, create new daily branch from main
2. **Agent Scenarios**: Agents create short-lived feature branches for replanning
3. **Auto-Merge**: Low-impact scenarios merge to main automatically
4. **Human Review**: High-impact scenarios require planner approval
5. **Hotfixes**: Emergency changes bypass normal flow, merge directly to main
6. **Cleanup**: Delete merged branches after 7 days, retain commit history

### 3.2 Plan Version Schema

**Database Tables**:

```sql
-- Plan version control (Git-like commits)
CREATE TABLE plan_commits (
    commit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_name VARCHAR(255) NOT NULL,
    parent_commit_id UUID REFERENCES plan_commits(commit_id),  -- For merge tracking
    commit_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    author VARCHAR(255) NOT NULL,  -- 'mps-agent', 'planner-john', 'sap-import'
    commit_message TEXT,
    plan_snapshot JSONB NOT NULL,  -- Full or incremental snapshot
    is_incremental BOOLEAN DEFAULT FALSE,  -- TRUE if CDC, FALSE if full
    change_summary JSONB,  -- Stats: SKUs changed, weeks affected, cost impact
    INDEX idx_branch_timestamp (branch_name, commit_timestamp DESC)
);

-- Plan branches (Git-like refs)
CREATE TABLE plan_branches (
    branch_name VARCHAR(255) PRIMARY KEY,
    head_commit_id UUID NOT NULL REFERENCES plan_commits(commit_id),
    base_branch VARCHAR(255),  -- Parent branch (e.g., 'main')
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,  -- 'active', 'merged', 'abandoned'
    merged_at TIMESTAMPTZ,
    merged_by VARCHAR(255),
    INDEX idx_status (status)
);

-- Plan differences (Git-like diffs)
CREATE TABLE plan_diffs (
    diff_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_commit_id UUID NOT NULL REFERENCES plan_commits(commit_id),
    to_commit_id UUID NOT NULL REFERENCES plan_commits(commit_id),
    product_id VARCHAR(100) NOT NULL,
    site_id VARCHAR(100),
    period_start_date DATE NOT NULL,
    period_end_date DATE NOT NULL,
    field_name VARCHAR(100) NOT NULL,  -- 'planned_production_qty', 'safety_stock', etc.
    old_value NUMERIC,
    new_value NUMERIC,
    delta NUMERIC GENERATED ALWAYS AS (new_value - old_value) STORED,
    delta_percent NUMERIC GENERATED ALWAYS AS ((new_value - old_value) / NULLIF(old_value, 0) * 100) STORED,
    INDEX idx_commits (from_commit_id, to_commit_id),
    INDEX idx_product_period (product_id, period_start_date)
);

-- Plan KPIs (for variance analysis)
CREATE TABLE plan_kpis (
    kpi_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    commit_id UUID NOT NULL REFERENCES plan_commits(commit_id),
    kpi_name VARCHAR(100) NOT NULL,  -- 'total_cost', 'service_level', 'inventory_turns'
    kpi_value NUMERIC NOT NULL,
    kpi_unit VARCHAR(50),  -- '$', '%', 'days'
    calculation_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    INDEX idx_commit_kpi (commit_id, kpi_name)
);
```

### 3.3 Snapshot Strategy: Full vs. Incremental

**Problem**: Storing full MPS plan (10,000 SKUs × 52 weeks = 520K records) every hour is expensive.

**Solution**: Hybrid full + incremental CDC snapshots

**Decision Tree**:

```
Event Type → Snapshot Strategy
├── Daily SAP Import (23:00) → Full Snapshot (baseline)
├── Agent Replan (<100 SKUs) → Incremental CDC
├── Policy Change (affects all SKUs) → Full Snapshot
└── Hourly Auto-Save → Incremental CDC (only changes since last commit)
```

**Full Snapshot** (Daily Baseline):
```python
# Nightly full snapshot
commit_full_snapshot(
    branch='main',
    author='sap-import',
    message='Daily baseline from SAP CDC',
    plan_data={
        'mps_items': query_all_mps_plan_items(),  # All 520K records
        'inventory_levels': query_all_inv_levels(),
        'sourcing_rules': query_all_sourcing_rules(),
        'capacity_plans': query_all_capacity_plans()
    },
    is_incremental=False  # Full snapshot
)
```

**Incremental CDC** (Agent Replans):
```python
# Agent commits only changes
commit_incremental_snapshot(
    branch='scenario/mps-order-789',
    author='mps-agent',
    message='MPS replan for order SO-789',
    changes={
        'mps_items': [
            {'product_id': 'CASE', 'week': 5, 'planned_qty': 120, 'prev_qty': 100},
            {'product_id': 'CASE', 'week': 6, 'planned_qty': 110, 'prev_qty': 100}
        ]
    },
    is_incremental=True,  # CDC only
    parent_commit_id='abc123'  # Reference to baseline
)
```

**Storage Optimization**:
- **Full snapshot**: 520K records × 500 bytes = 260 MB (once per day)
- **Incremental snapshot**: ~50 records × 500 bytes = 25 KB (100x per day)
- **Total daily storage**: 260 MB + (25 KB × 100) = 262.5 MB (vs. 26 GB if full every hour)

---

## 4. Incremental CDC Snapshotting

### 4.1 Feasibility Analysis

**Question**: Is it feasible to perform incremental snapshots during the day to reduce end-of-day effort?

**Answer**: ✅ **Yes, highly feasible and recommended**

**Rationale**:

1. **Database Change Tracking**: PostgreSQL supports row-level triggers for CDC
2. **Event Sourcing**: Kafka/EventBridge can capture all planning events
3. **Git Model**: Incremental commits are the foundation of Git (proven at scale)
4. **Performance**: Incremental snapshots are 100-1000x smaller than full snapshots

**Industry Precedent**:
- **Kinaxis RapidResponse**: Uses in-memory columnar database with continuous delta tracking
- **SAP IBP**: Event-driven planning with incremental snapshots
- **o9 Solutions**: Real-time planning graph with CDC

### 4.2 Incremental Snapshotting Strategy

**Trigger-Based CDC** (Database Level):

```sql
-- Trigger function to capture MPS changes
CREATE OR REPLACE FUNCTION capture_mps_change()
RETURNS TRIGGER AS $$
BEGIN
    -- Insert change into CDC table
    INSERT INTO mps_change_data_capture (
        product_id,
        site_id,
        period_start_date,
        field_name,
        old_value,
        new_value,
        changed_at,
        changed_by
    ) VALUES (
        NEW.product_id,
        NEW.site_id,
        NEW.period_start_date,
        TG_ARGV[0],  -- Field name (e.g., 'planned_production_qty')
        OLD.planned_production_qty,
        NEW.planned_production_qty,
        NOW(),
        current_setting('app.current_user', TRUE)
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach trigger to MPS table
CREATE TRIGGER mps_change_trigger
AFTER UPDATE OF planned_production_qty ON mps_plan_items
FOR EACH ROW
WHEN (OLD.planned_production_qty IS DISTINCT FROM NEW.planned_production_qty)
EXECUTE FUNCTION capture_mps_change();
```

**Event-Driven CDC** (Application Level):

```python
# Agent publishes change events after replanning
class MPSAgent:
    async def commit_plan_changes(self, changes):
        # 1. Compute delta from current plan
        delta = self.compute_delta(self.current_plan, changes)

        # 2. Publish CDC events to event bus
        for change in delta:
            event = {
                'event_type': 'MPS_PLAN_CHANGE',
                'timestamp': datetime.utcnow(),
                'product_id': change['product_id'],
                'site_id': change['site_id'],
                'week': change['week'],
                'field': 'planned_production_qty',
                'old_value': change['old_value'],
                'new_value': change['new_value'],
                'delta': change['new_value'] - change['old_value'],
                'reason': 'order-789-replan'
            }
            await event_bus.publish('planning.mps.changes', event)

        # 3. Commit incremental snapshot
        commit_id = await self.version_control.commit_incremental(
            branch=self.current_branch,
            author='mps-agent',
            message=f'MPS replan: {len(delta)} changes',
            changes=delta
        )

        return commit_id
```

### 4.3 Incremental Snapshot Frequency

**Recommended Schedule**:

| Time | Snapshot Type | Trigger | Estimated Size | Cumulative Daily |
|------|---------------|---------|----------------|------------------|
| **00:00** | Full | SAP nightly import | 260 MB | 260 MB |
| **01:00-07:00** | Incremental | Low activity (few events) | 5 KB/hour | 260.03 MB |
| **08:00-17:00** | Incremental | Peak hours (agent replans) | 50 KB/hour | 260.48 MB |
| **18:00-23:00** | Incremental | Moderate activity | 20 KB/hour | 260.60 MB |

**Total Daily Storage**: ~261 MB (vs. 26 GB if full snapshots every hour)

**Retention Policy**:
- **Full snapshots**: Keep for 28 days (7 GB total)
- **Incremental snapshots**: Keep for 7 days (1.8 GB total)
- **Total storage**: 8.8 GB for 28 days of planning history

---

## 5. LLM-First UI Paradigm

### 5.1 Conversational Planning Interface

**Vision**: Planners interact with the system through **natural language**, with point-and-click UI as a secondary deep-dive option.

**User Experience Flow**:

```
Planner: "Show me MPS exceptions for CASE product this week"

LLM UI: "I found 3 MPS exceptions for CASE this week:

1. Week 5: Planned 120 units, but capacity constraint limits to 100
   - Impact: 20-unit shortfall
   - Affected orders: SO-789 (due 2026-02-05)
   - Recommendation: Expedite Week 4 production or source externally

2. Week 6: Inventory projected to drop below safety stock (target: 50, actual: 35)
   - Impact: Service level risk
   - Root cause: Higher-than-forecast demand last week
   - Recommendation: Increase Week 5 production by 15 units

3. Week 7: Component shortage for SIXPACK (BOTTLE short by 200)
   - Impact: Cannot build planned 100 CASE (requires 400 SIXPACK = 2400 BOTTLE)
   - Root cause: Supplier delay on PO-456
   - Recommendation: Expedite PO-456 or delay CASE production

[View Details] [Approve Agent Recommendation] [Custom Adjustments]"

Planner clicks [View Details] on Exception #1

LLM UI: "Opening detailed view for Week 5 capacity constraint...

[Interactive Gantt Chart Loads]
- Shows machine schedule for Week 5
- Highlights overload on Machine-A (120% utilization)
- Shows alternative: Machine-B has 30% available capacity

Would you like to:
1. Move 20 units from Machine-A to Machine-B? (Recommended)
2. Add overtime shift on Machine-A? (Cost: $500)
3. Outsource 20 units to Supplier-X? (Lead time: 3 days, cost: $1200)

Type your choice or ask me anything about this exception."

Planner: "What's the cost difference between option 1 and 2?"

LLM UI: "Cost comparison:

Option 1 (Move to Machine-B):
- Additional setup cost: $200 (one-time)
- No ongoing cost increase
- Total: $200

Option 2 (Overtime on Machine-A):
- Overtime premium: 1.5x labor rate
- Estimated cost: $500 for 20 units
- Total: $500

Option 1 saves $300 and utilizes existing capacity. Shall I approve this change?"

Planner: "Yes, but also notify me if Machine-B utilization exceeds 85% in future weeks"

LLM UI: "✅ Applied:
1. Moved 20 units CASE from Machine-A to Machine-B in Week 5
2. Created alert rule: Notify if Machine-B utilization > 85%

Commit ID: abc123
Branch: main
Changes published to SAP at 10:45 AM

Would you like to review the updated MPS plan or continue to Exception #2?"
```

### 5.2 LLM UI Architecture

**Components**:

```
┌─────────────────────────────────────────────────────────────┐
│                  FRONTEND (React)                          │
│  - Chat interface (primary)                                │
│  - Point-and-click dashboards (secondary)                  │
│  - Real-time agent activity feed                           │
└────────────┬────────────────────────────────────────────────┘
             │
             ↓
┌─────────────────────────────────────────────────────────────┐
│              LLM ORCHESTRATION LAYER                       │
│  - GPT-4 Turbo / Claude 3 Opus                            │
│  - Tool calling for data retrieval                         │
│  - Context window management (128K tokens)                 │
│  - Multi-turn conversation history                         │
└────────────┬────────────────────────────────────────────────┘
             │
             ├──► Planning API (FastAPI)
             ├──► Version Control API (Git-like ops)
             ├──► Agent Inspection API (agent decisions)
             └──► ERP Integration API (SAP publish)
```

**LLM Tool Definitions**:

```python
# Tools available to LLM for planning tasks
PLANNING_TOOLS = [
    {
        "name": "get_mps_exceptions",
        "description": "Retrieve MPS exceptions for a product, site, or time period",
        "parameters": {
            "product_id": "Optional product filter",
            "site_id": "Optional site filter",
            "week_start": "Optional start week",
            "week_end": "Optional end week",
            "severity": "Optional severity filter (critical, high, medium, low)"
        }
    },
    {
        "name": "get_plan_details",
        "description": "Retrieve detailed MPS plan for specific product and week",
        "parameters": {
            "product_id": "Product ID",
            "site_id": "Site ID",
            "week": "Week number"
        }
    },
    {
        "name": "compare_plan_versions",
        "description": "Compare two plan versions (e.g., today vs. yesterday)",
        "parameters": {
            "from_commit_id": "Baseline commit",
            "to_commit_id": "Comparison commit",
            "product_ids": "Optional list of products to compare"
        }
    },
    {
        "name": "approve_agent_recommendation",
        "description": "Approve an agent's recommended plan change",
        "parameters": {
            "scenario_branch": "Agent scenario branch name",
            "merge_to": "Target branch (usually 'main')"
        }
    },
    {
        "name": "simulate_plan_change",
        "description": "Simulate impact of manual plan adjustment",
        "parameters": {
            "product_id": "Product to adjust",
            "site_id": "Site",
            "week": "Week",
            "field": "Field to change (e.g., 'planned_production_qty')",
            "new_value": "New value"
        }
    },
    {
        "name": "get_agent_decision_explanation",
        "description": "Get explanation for why agent made a specific decision",
        "parameters": {
            "commit_id": "Commit ID of agent decision",
            "agent_type": "Agent that made decision (mps, mrp, etc.)"
        }
    }
]
```

### 5.3 Point-and-Click Deep Dive

**When Planners Need Traditional UI**:

1. **Complex Gantt Charts**: Capacity scheduling, critical path analysis
2. **Bulk Edits**: Change 50 products at once via spreadsheet-like grid
3. **Visual Analytics**: Sankey diagrams, waterfall charts, heatmaps
4. **Drill-Down Hierarchies**: Product family → SKU → Component levels

**Hybrid UI Pattern**:

```
┌──────────────────────────────────────────────────────────┐
│  [Chat: "Show capacity for Machine-A in Week 5"]        │
│                                                          │
│  LLM: "Machine-A is at 120% utilization in Week 5."    │
│       [View Gantt Chart] ← Click to open traditional UI │
└──────────────────────────────────────────────────────────┘
                    ↓ (Opens modal)
┌──────────────────────────────────────────────────────────┐
│  Machine-A Capacity Schedule - Week 5                   │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Mon  Tue  Wed  Thu  Fri  Sat  Sun                │ │
│  │  ██████████████████████████████████ (Overload)    │ │
│  │  Product: CASE (80 units)                         │ │
│  │  Product: SIXPACK (40 units)                      │ │
│  └────────────────────────────────────────────────────┘ │
│  [Back to Chat] [Apply Recommendations]                │
└──────────────────────────────────────────────────────────┘
```

---

## 6. Daily Data Import Flow

### 6.1 SAP Data Import Architecture

**Daily Import Schedule**:

```
23:00 - Pre-Import Snapshot
├── Commit current main branch as daily/2026-01-22
├── Create read-only tag for auditing
└── Prepare for new day's baseline

23:05 - SAP CDC Extraction
├── Extract master data changes (products, BOMs, sites)
├── Extract transactional data (orders, shipments, inventory)
├── Validate data quality
└── Stage in import_staging tables

23:15 - Plan vs. Actual Comparison
├── Load yesterday's plan (from daily/2026-01-21)
├── Load today's actuals (from SAP)
├── Compute variance for each KPI
└── Generate variance report

23:30 - Import to Main Branch
├── Apply master data changes
├── Apply transactional data
├── Commit as new baseline (daily/2026-01-23)
└── Trigger post-import agents

23:45 - Post-Import Agent Triggers
├── Policy agents recalculate inventory targets
├── MPS agent evaluates new demand
├── Capacity agent updates resource availability
└── LLM supervisor generates import summary for planners
```

### 6.2 Pre-Import Snapshot Process

**Purpose**: Preserve current state before importing new data from SAP

**Implementation**:

```python
async def pre_import_snapshot():
    """
    Create immutable snapshot of current plan before SAP import.
    This becomes the 'yesterday' baseline for plan vs. actual comparison.
    """
    # 1. Create daily branch from main
    today = datetime.now().date()
    branch_name = f'daily/{today}'

    # Commit full snapshot to daily branch
    commit_id = await version_control.commit_full_snapshot(
        branch='main',
        author='system',
        message=f'Pre-import snapshot for {today}',
        snapshot_data={
            'mps_items': query_all_mps_plan_items(),
            'inventory_levels': query_all_inv_levels(),
            'mrp_requirements': query_all_mrp_requirements(),
            'capacity_plans': query_all_capacity_plans(),
            'kpis': compute_all_kpis()
        }
    )

    # 2. Create immutable tag
    await version_control.create_tag(
        tag_name=f'import/{today}',
        commit_id=commit_id,
        immutable=True  # Cannot be deleted or modified
    )

    # 3. Log snapshot metadata
    await audit_log.record({
        'event': 'PRE_IMPORT_SNAPSHOT',
        'timestamp': datetime.utcnow(),
        'commit_id': commit_id,
        'branch': branch_name,
        'tag': f'import/{today}',
        'stats': {
            'mps_items_count': len(snapshot_data['mps_items']),
            'total_planned_production': sum([item.qty for item in snapshot_data['mps_items']]),
            'snapshot_size_mb': estimate_snapshot_size(snapshot_data)
        }
    })

    logger.info(f'Pre-import snapshot created: {commit_id}')
    return commit_id
```

**Storage Efficiency**:
- **Daily full snapshot**: 260 MB per day
- **Retention**: 28 days (7.3 GB total)
- **Compression**: gzip reduces to ~50 MB per day (1.4 GB for 28 days)

### 6.3 Incremental Snapshotting During the Day

**Strategy**: Capture changes hourly or on-demand to reduce end-of-day load

**Incremental Snapshot Triggers**:

1. **Time-Based** (Hourly Auto-Save)
   ```python
   @scheduled_task(cron='0 * * * *')  # Every hour
   async def hourly_incremental_snapshot():
       # Get changes since last snapshot
       last_snapshot = await get_last_snapshot_timestamp()
       changes = await get_planning_changes_since(last_snapshot)

       if len(changes) > 0:
           commit_id = await version_control.commit_incremental(
               branch='main',
               author='system',
               message=f'Hourly snapshot: {len(changes)} changes',
               changes=changes,
               parent_commit_id=last_snapshot.commit_id
           )
           logger.info(f'Hourly snapshot: {commit_id}, {len(changes)} changes')
   ```

2. **Event-Based** (Agent Commits)
   ```python
   # Agent commits immediately after replanning
   async def agent_commit_changes(agent_name, changes):
       commit_id = await version_control.commit_incremental(
           branch='main',
           author=agent_name,
           message=f'{agent_name} replan: {len(changes)} SKUs affected',
           changes=changes
       )

       # Trigger downstream agents if needed
       if agent_name == 'policy-agent':
           await trigger_dependent_agents(['mps-agent', 'mrp-agent'])
   ```

3. **Manual** (Planner Saves)
   ```python
   @api.post('/planning/save')
   async def manual_save(user_id: int, changes: List[PlanChange]):
       commit_id = await version_control.commit_incremental(
           branch='main',
           author=f'planner-{user_id}',
           message=f'Manual save by {get_user_name(user_id)}',
           changes=changes
       )
       return {'commit_id': commit_id, 'timestamp': datetime.utcnow()}
   ```

**Incremental Snapshot Benefits**:

✅ **Reduced EOD Load**: End-of-day snapshot only captures last hour of changes (not full day)
✅ **Better Audit Trail**: Hourly checkpoints show planning evolution throughout day
✅ **Faster Recovery**: Can restore to any hourly checkpoint if issue detected
✅ **Real-Time CDC**: Plan vs. actual can be updated continuously (not just nightly)

### 6.4 Plan vs. Actual Comparison

**Comparison Workflow**:

```python
async def compute_plan_vs_actual(import_date):
    """
    Compare yesterday's plan with today's actual results.
    Generate variance report for each KPI.
    """
    # 1. Load yesterday's plan (frozen snapshot)
    yesterday = import_date - timedelta(days=1)
    plan_commit = await version_control.get_commit_by_tag(f'import/{yesterday}')
    planned_data = await version_control.load_snapshot(plan_commit.commit_id)

    # 2. Load today's actuals (from SAP import)
    actual_data = await sap_integration.get_actuals(yesterday)

    # 3. Compute variance for key metrics
    variance = {
        'production': {
            'planned': sum([item.qty for item in planned_data['mps_items']]),
            'actual': sum([item.qty for item in actual_data['production_orders']]),
            'variance': None  # Calculated below
        },
        'inventory': {
            'planned': sum([inv.on_hand_qty for inv in planned_data['inventory_levels']]),
            'actual': sum([inv.on_hand_qty for inv in actual_data['inventory_levels']]),
            'variance': None
        },
        'service_level': {
            'planned': planned_data['kpis']['service_level'],
            'actual': compute_actual_service_level(actual_data),
            'variance': None
        },
        'cost': {
            'planned': planned_data['kpis']['total_cost'],
            'actual': sum([order.actual_cost for order in actual_data['production_orders']]),
            'variance': None
        }
    }

    # Calculate variance
    for metric, values in variance.items():
        values['variance'] = values['actual'] - values['planned']
        values['variance_percent'] = (values['variance'] / values['planned'] * 100) if values['planned'] > 0 else 0

    # 4. Store variance report
    await variance_reports.create({
        'report_date': yesterday,
        'plan_commit_id': plan_commit.commit_id,
        'actual_data_source': 'SAP_ECC',
        'variance_summary': variance,
        'generated_at': datetime.utcnow()
    })

    # 5. Generate alerts for significant variances
    for metric, values in variance.items():
        if abs(values['variance_percent']) > VARIANCE_THRESHOLD[metric]:
            await alerts.create({
                'severity': 'HIGH',
                'message': f'{metric} variance exceeds threshold: {values["variance_percent"]:.1f}%',
                'metric': metric,
                'planned': values['planned'],
                'actual': values['actual'],
                'variance': values['variance']
            })

    # 6. Trigger LLM summary for planners
    summary = await llm_supervisor.generate_variance_summary(variance)
    await notifications.send_to_planners(summary)

    return variance
```

**Variance Report Example**:

```
Daily Plan vs. Actual Report - 2026-01-22

Production Volume:
  Planned:  10,000 units
  Actual:    9,750 units
  Variance:   -250 units (-2.5%)
  Status: ⚠️ Below plan

Service Level:
  Planned:  95.0%
  Actual:   93.2%
  Variance:  -1.8%
  Status: ⚠️ Below target

Inventory Value:
  Planned:  $2.5M
  Actual:   $2.6M
  Variance:  +$100K (+4%)
  Status: ⚠️ Above plan (excess stock)

Total Cost:
  Planned:  $500K
  Actual:   $520K
  Variance:  +$20K (+4%)
  Status: ❌ Exceeded budget

Root Cause Analysis (by LLM Supervisor):

1. Production shortfall (-250 units):
   - Machine-A breakdown on 2026-01-22 (8 hours downtime)
   - Recommendation: Add overtime this weekend to catch up

2. Service level miss (-1.8%):
   - Late deliveries on 3 customer orders (SO-789, SO-790, SO-791)
   - Root cause: Production shortfall + unexpected demand spike for CASE
   - Recommendation: Expedite Week 5 production, prioritize these orders

3. Excess inventory (+$100K):
   - Overproduction of SIXPACK last week (anticipating demand that didn't materialize)
   - Recommendation: Reduce SIXPACK production next week, use excess for future weeks

4. Cost overrun (+$20K):
   - Expedite fees for supplier delay ($12K)
   - Overtime premium for Machine-B ($8K)
   - Recommendation: Review supplier performance, consider alternative sources

[Approve Recommendations] [View Detailed Breakdown] [Override]
```

---

## 7. Multi-Layer Agent Coordination

### 7.1 Agent Hierarchy

**Policy Agents** (Set the rules):
- **Inventory Policy Agent**: Calculate safety stock, reorder points, target DOC
- **Sourcing Policy Agent**: Optimize make-vs-buy, vendor selection, sourcing priorities
- **Capacity Policy Agent**: Determine shift patterns, overtime rules, bottleneck management
- **Demand Policy Agent**: Update forecast models, seasonality factors, demand sensing

**Execution Agents** (Implement the plan):
- **MPS Agent**: Generate master production schedule respecting policies
- **MRP Agent**: Explode BOM, calculate component requirements, generate purchase requisitions
- **Capacity Agent**: Schedule resources, load balance, resolve constraint violations
- **Order Promising Agent**: ATP/CTP calculation, order confirmation

**Supervisor Agents** (Coordinate and escalate):
- **LLM Supervisor**: Exception handling, root cause analysis, human escalation
- **Global Planner Agent**: Network-wide optimization, trade-off analysis

### 7.2 Agent Trigger Cascade

**Trigger Hierarchy**:

```
Policy Change Event (e.g., "Increase CASE safety stock from 50 to 75")
    ↓
Policy Agent (Inventory) recalculates targets for all CASE-related products
    ↓
Execution Agent (MPS) replans affected weeks to meet new targets
    ↓
Execution Agent (MRP) adjusts component requirements based on new MPS
    ↓
Execution Agent (Capacity) verifies resource availability for new MRP plan
    ↓
Supervisor Agent (LLM) reviews cascade impact and alerts planners if significant
```

**Implementation**:

```python
class AgentCoordinator:
    def __init__(self):
        self.policy_agents = ['inventory', 'sourcing', 'capacity', 'demand']
        self.execution_agents = ['mps', 'mrp', 'capacity', 'order_promising']
        self.supervisor_agents = ['llm', 'global_planner']

    async def handle_policy_change_event(self, event):
        """
        Handle policy change event with proper agent sequencing.
        Policy agents always run before execution agents.
        """
        # 1. Route to appropriate policy agent
        policy_agent = self.get_policy_agent(event.policy_type)
        policy_result = await policy_agent.recalculate_policies(event)

        # 2. Identify downstream execution agents
        affected_execution_agents = self.get_dependent_agents(policy_agent)

        # 3. Sequence execution agents (order matters!)
        agent_sequence = self.build_execution_sequence(affected_execution_agents)

        # 4. Execute agents in sequence
        results = []
        for agent_name in agent_sequence:
            agent = self.execution_agents[agent_name]
            result = await agent.replan(
                trigger_event=policy_result,
                context={'policy_change': event}
            )
            results.append(result)

            # Check if agent wants to abort cascade
            if result.abort_cascade:
                logger.warning(f'Agent {agent_name} aborted cascade: {result.reason}')
                break

        # 5. Supervisor review
        supervisor_result = await self.llm_supervisor.review_cascade(
            policy_change=event,
            agent_results=results
        )

        # 6. Escalate to human if high impact
        if supervisor_result.requires_human_review:
            await self.escalate_to_planner(supervisor_result)
        else:
            # Auto-commit all changes
            for result in results:
                await self.version_control.merge_to_main(result.scenario_branch)

        return supervisor_result

    def build_execution_sequence(self, agents):
        """
        Build correct execution sequence based on dependencies.
        MPS must run before MRP.
        MRP must run before Capacity.
        """
        dependency_graph = {
            'mps': [],  # No dependencies
            'mrp': ['mps'],  # Depends on MPS
            'capacity': ['mps', 'mrp'],  # Depends on MPS and MRP
            'order_promising': ['mps', 'mrp', 'capacity']  # Depends on all
        }

        # Topological sort
        return topological_sort(agents, dependency_graph)
```

### 7.3 Agent Conflict Resolution

**Conflict Scenario**:

```
Two agents attempt to modify the same SKU simultaneously:

Agent 1 (MPS): Wants to increase CASE production in Week 5 from 100 to 120
Agent 2 (Capacity): Wants to reduce CASE production in Week 5 from 100 to 90 (due to machine constraint)

Result: Conflict! Cannot have both 120 and 90.
```

**Resolution Strategy**:

```python
class ConflictResolver:
    def __init__(self):
        self.agent_priorities = {
            'capacity': 1,  # Highest priority (constraints are hard)
            'mps': 2,
            'mrp': 3,
            'inventory': 4,
            'demand': 5
        }

    async def resolve_conflict(self, agent1_result, agent2_result):
        """
        Resolve conflict between two agents using priority and LLM negotiation.
        """
        # 1. Check if same SKU/week affected
        conflicts = self.detect_conflicts(agent1_result, agent2_result)

        if len(conflicts) == 0:
            # No conflict, both can proceed
            return {'resolution': 'NO_CONFLICT', 'actions': ['merge_both']}

        # 2. Apply priority rules
        agent1_priority = self.agent_priorities[agent1_result.agent_name]
        agent2_priority = self.agent_priorities[agent2_result.agent_name]

        if agent1_priority < agent2_priority:
            # Agent 1 wins
            return {'resolution': 'PRIORITY', 'winner': agent1_result.agent_name, 'action': 'merge_agent1_only'}
        elif agent2_priority < agent1_priority:
            # Agent 2 wins
            return {'resolution': 'PRIORITY', 'winner': agent2_result.agent_name, 'action': 'merge_agent2_only'}
        else:
            # Equal priority, escalate to LLM supervisor
            return await self.llm_negotiate_conflict(agent1_result, agent2_result, conflicts)

    async def llm_negotiate_conflict(self, agent1_result, agent2_result, conflicts):
        """
        Use LLM supervisor to negotiate conflict resolution.
        """
        prompt = f"""
        Two planning agents have conflicting proposals:

        Agent 1 (MPS): Proposes increasing CASE production in Week 5 to 120 units
        Reasoning: New customer order SO-789 requires additional capacity

        Agent 2 (Capacity): Proposes reducing CASE production in Week 5 to 90 units
        Reasoning: Machine-A is at 120% utilization, overload constraint

        Context:
        - Current plan: 100 units
        - Machine-A capacity: 100 units/week (hard constraint)
        - Machine-B capacity: 50 units/week (can handle CASE with setup change)
        - Customer order SO-789: Due 2026-02-05 (Week 5)
        - Safety stock target: 50 units

        Options:
        1. Accept MPS proposal (120 units): Violates capacity constraint unless mitigated
        2. Accept Capacity proposal (90 units): Misses customer order
        3. Compromise: Move 20 units from Machine-A to Machine-B (allows 110 units)
        4. Compromise: Split production across Week 4 and Week 5 (partial advance)

        Recommend the optimal resolution and explain your reasoning.
        """

        llm_response = await self.llm.complete(prompt)

        # Parse LLM recommendation
        resolution = self.parse_llm_resolution(llm_response)

        # Log conflict resolution for audit
        await self.audit_log.record({
            'event': 'AGENT_CONFLICT_RESOLVED',
            'agent1': agent1_result.agent_name,
            'agent2': agent2_result.agent_name,
            'conflicts': conflicts,
            'resolution': resolution,
            'llm_reasoning': llm_response
        })

        return resolution
```

### 7.4 Native Supply Chain Intelligence & Stochastic Planning

**Platform Capabilities**:

The Autonomy platform includes **native supply chain intelligence** that generates insights and drives event-triggered replanning. These capabilities are built-in, not external integrations.

#### Intelligent Event Detection & Generation

**Native Insight Engines** generate planning events proactively:

| Insight Type | Detection Method | Planning Event Type | Triggered Agent |
|--------------|------------------|---------------------|-----------------|
| **Stock-out risk** | Probabilistic inventory projection (Monte Carlo) | INVENTORY_RISK_STOCKOUT | Inventory Policy Agent → MPS Agent |
| **Excess inventory** | DOC variance analysis + aging | INVENTORY_RISK_EXCESS | Inventory Policy Agent → Sourcing Agent |
| **Vendor delay prediction** | ML lead-time forecasting (GNN-based) | SUPPLY_DISRUPTION_DELAY | Sourcing Policy Agent → MRP Agent |
| **Order at-risk** | ATP/CTP tracking vs. promises | DELIVERY_RISK | Order Promising Agent → Capacity Agent |
| **Capacity constraint** | Resource utilization forecasting | CAPACITY_CONSTRAINT | Capacity Agent → MPS Agent |
| **Forecast deviation** | Demand sensing with variance detection | DEMAND_SIGNAL | Demand Policy Agent → MPS Agent |

**Implementation**:

```python
class NativeInsightEngine:
    """
    Native supply chain intelligence engine that generates planning insights.
    Uses stochastic simulation and ML models to predict risks proactively.
    """

    def __init__(self, event_bus, stochastic_sampler):
        self.event_bus = event_bus
        self.stochastic_sampler = stochastic_sampler
        self.insight_watchers = []  # Configurable watchlists

    async def detect_inventory_risk(self, product_id, site_id, horizon_weeks=13):
        """
        Detect stock-out or excess inventory risk using stochastic projection.

        Uses Monte Carlo simulation with:
        - Demand distribution (forecast + variability)
        - Lead time distribution (vendor reliability)
        - Yield distribution (production quality)
        """

        # 1. Run stochastic inventory projection
        scenarios = await self.stochastic_sampler.simulate_inventory_trajectory(
            product_id=product_id,
            site_id=site_id,
            horizon_weeks=horizon_weeks,
            num_scenarios=1000  # Monte Carlo iterations
        )

        # 2. Calculate risk probabilities
        risk_analysis = {
            'stockout_probability': np.mean([s.has_stockout for s in scenarios]),
            'stockout_week': self.find_first_stockout_week(scenarios),
            'excess_probability': np.mean([s.has_excess for s in scenarios]),
            'expected_dos': np.mean([s.days_of_supply for s in scenarios]),
            'p10_inventory': np.percentile([s.ending_inventory for s in scenarios], 10),
            'p50_inventory': np.percentile([s.ending_inventory for s in scenarios], 50),
            'p90_inventory': np.percentile([s.ending_inventory for s in scenarios], 90)
        }

        # 3. Determine severity and generate event if threshold exceeded
        if risk_analysis['stockout_probability'] > 0.20:  # >20% chance of stockout
            severity = 'CRITICAL' if risk_analysis['stockout_probability'] > 0.50 else 'HIGH'

            planning_event = PlanningEvent(
                event_type='INVENTORY_RISK_STOCKOUT',
                source_system='NATIVE_INSIGHT_ENGINE',
                priority='P0' if severity == 'CRITICAL' else 'P1',
                payload={
                    'product_id': product_id,
                    'site_id': site_id,
                    'risk_type': 'STOCKOUT',
                    'probability': risk_analysis['stockout_probability'],
                    'projected_stockout_week': risk_analysis['stockout_week'],
                    'current_dos': await self.get_current_dos(product_id, site_id),
                    'target_dos': await self.get_target_dos(product_id, site_id),
                    'stochastic_analysis': risk_analysis
                },
                event_timestamp=datetime.utcnow()
            )

            # Publish to event bus for agent processing
            await self.event_bus.publish(planning_event)

            return planning_event

        elif risk_analysis['excess_probability'] > 0.30:  # >30% chance of excess
            severity = 'MEDIUM'

            planning_event = PlanningEvent(
                event_type='INVENTORY_RISK_EXCESS',
                source_system='NATIVE_INSIGHT_ENGINE',
                priority='P2',
                payload={
                    'product_id': product_id,
                    'site_id': site_id,
                    'risk_type': 'EXCESS',
                    'probability': risk_analysis['excess_probability'],
                    'expected_dos': risk_analysis['expected_dos'],
                    'target_dos': await self.get_target_dos(product_id, site_id),
                    'holding_cost_impact': await self.estimate_excess_cost(risk_analysis),
                    'stochastic_analysis': risk_analysis
                },
                event_timestamp=datetime.utcnow()
            )

            await self.event_bus.publish(planning_event)

            return planning_event

        return None  # No risk detected

    async def detect_vendor_delay(self, vendor_id, product_id):
        """
        Predict vendor lead-time delays using ML-based forecasting (GNN).
        """

        # 1. Get historical lead-time performance
        historical_performance = await self.db.query(VendorLeadTime).filter(
            VendorLeadTime.vendor_id == vendor_id,
            VendorLeadTime.product_id == product_id
        ).order_by(VendorLeadTime.order_date.desc()).limit(100).all()

        # 2. Train/load GNN model for lead-time prediction
        predicted_lead_time = await self.gnn_agent.predict_lead_time(
            vendor_id=vendor_id,
            product_id=product_id,
            context=historical_performance
        )

        # 3. Compare to standard lead time
        standard_lead_time = await self.db.get_standard_lead_time(vendor_id, product_id)
        delay_days = predicted_lead_time - standard_lead_time

        # 4. Generate event if significant delay predicted
        if delay_days > 3:  # >3 day delay
            severity = 'CRITICAL' if delay_days > 7 else 'HIGH'

            planning_event = PlanningEvent(
                event_type='SUPPLY_DISRUPTION_DELAY',
                source_system='NATIVE_INSIGHT_ENGINE',
                priority='P0' if severity == 'CRITICAL' else 'P1',
                payload={
                    'vendor_id': vendor_id,
                    'product_id': product_id,
                    'predicted_lead_time_days': predicted_lead_time,
                    'standard_lead_time_days': standard_lead_time,
                    'delay_days': delay_days,
                    'affected_orders': await self.get_affected_orders(vendor_id, product_id),
                    'ml_confidence': 0.85  # GNN model confidence
                },
                event_timestamp=datetime.utcnow()
            )

            await self.event_bus.publish(planning_event)

            return planning_event

        return None

    @scheduled_task(cron='*/15 * * * *')  # Run every 15 minutes
    async def scan_for_risks(self):
        """
        Proactively scan for risks across all products/sites.
        """

        # Get all active products/sites
        active_inventory = await self.db.query(InventoryLevel).filter(
            InventoryLevel.on_hand_qty > 0
        ).all()

        # Parallel risk detection
        tasks = []
        for inv in active_inventory:
            tasks.append(self.detect_inventory_risk(inv.product_id, inv.site_id))

        insights = await asyncio.gather(*tasks)

        # Filter out None values
        valid_insights = [i for i in insights if i is not None]

        logger.info(f'Risk scan complete: {len(valid_insights)} insights generated')

        return valid_insights
```

#### Stochastic Recommendation Scoring

**Native recommendation engine** evaluates options using probabilistic outcomes:

**Implementation**:

```python
class StochasticRecommendationAgent:
    """
    Agents generate recommendations using probabilistic impact analysis.
    Each recommendation includes confidence intervals and risk distributions.
    """

    def __init__(self, agent_type, kpi_weights, stochastic_sampler):
        self.agent_type = agent_type
        self.kpi_weights = kpi_weights  # Shared performance goals
        self.stochastic_sampler = stochastic_sampler
        self.learning_history = []

    async def generate_recommendations(self, insight_event):
        """
        Generate ranked recommendations with probabilistic impact assessment.

        Returns list of actions scored by:
        - Risk resolution probability (not just point estimate)
        - Expected cost impact with P10/P50/P90 distribution
        - Service level likelihood distribution
        - Sustainability impact (CO2 emissions)
        """

        # 1. Generate candidate actions
        candidates = await self.generate_candidate_actions(insight_event)

        # 2. Simulate each action's impact stochastically
        scored_actions = []
        for action in candidates:
            # Run Monte Carlo simulation for this action
            impact = await self.simulate_action_stochastic(action, insight_event)

            # Calculate probabilistic score
            score = self.calculate_recommendation_score_stochastic(impact)

            scored_actions.append({
                'action': action,
                'score': score,
                'impact': impact,
                'scenario_branch': f'scenario/{self.agent_type}-{action.id}',
                'confidence': impact['confidence']
            })

        # 3. Rank by expected value of score (considering uncertainty)
        scored_actions.sort(key=lambda x: x['score']['expected_value'], reverse=True)

        return scored_actions

    def calculate_recommendation_score_stochastic(self, impact):
        """
        Score recommendation using probabilistic metrics from stochastic simulation.

        Scoring factors:
        - Risk resolution probability (P(stockout eliminated))
        - Expected cost impact (E[cost_delta])
        - Service level probability (P(OTIF > 95%))
        - Sustainability (E[CO2_reduction])
        - Confidence (based on variance of outcomes)
        """

        score_distribution = []

        for scenario in impact['scenarios']:  # 1000 Monte Carlo scenarios
            scenario_score = 0.0

            # Risk resolution (0-40 points)
            if scenario['stockout_resolved']:
                scenario_score += 40
            else:
                scenario_score += scenario['risk_reduction_pct'] * 0.4

            # Distance/logistics (0-20 points, inverse scoring)
            if scenario.get('transfer_distance_km', 0) > 0:
                distance_penalty = min(20, scenario['transfer_distance_km'] / 100)
                scenario_score += (20 - distance_penalty)
            else:
                scenario_score += 20

            # Sustainability (0-15 points)
            co2_reduction = scenario.get('co2_reduction_kg', 0)
            scenario_score += min(15, co2_reduction / 10)

            # Service level (0-15 points)
            if scenario['service_level'] > 0.95:
                scenario_score += 15
            else:
                scenario_score += scenario['service_level'] * 15

            # Inventory cost (0-10 points, negative delta is good)
            cost_delta = scenario['inventory_cost_delta']
            if cost_delta < 0:
                scenario_score += min(10, abs(cost_delta) / 1000)

            score_distribution.append(scenario_score)

        # Return expected value and distribution
        return {
            'expected_value': np.mean(score_distribution),
            'p10': np.percentile(score_distribution, 10),
            'p50': np.percentile(score_distribution, 50),
            'p90': np.percentile(score_distribution, 90),
            'std_dev': np.std(score_distribution),
            'confidence': self.calculate_confidence(score_distribution)
        }

    async def simulate_action_stochastic(self, action, event):
        """
        Simulate action impact using Monte Carlo simulation with stochastic variables.

        Returns probabilistic impact analysis:
        - scenarios: List of 1000 scenario outcomes
        - expected_values: E[cost], E[service_level], E[CO2]
        - distributions: P10/P50/P90 for key metrics
        - confidence: How consistent are the outcomes?
        """

        # Create scenario branch for simulation
        scenario_branch = await self.version_control.create_branch(
            branch_name=f'simulation/{action.id}',
            from_commit='main'
        )

        # Apply action in scenario
        await self.apply_action_to_scenario(action, scenario_branch)

        # Run stochastic simulation (1000 scenarios)
        stochastic_results = await self.stochastic_sampler.simulate_plan_outcomes(
            branch=scenario_branch,
            num_scenarios=1000,
            horizon_weeks=13,
            variables={
                'demand': 'lognormal',  # Demand distribution
                'lead_time': 'gamma',   # Lead time variability
                'yield': 'beta',        # Production yield
                'capacity': 'normal'    # Capacity fluctuation
            }
        )

        # Calculate impact vs. baseline (also stochastic)
        baseline_results = await self.stochastic_sampler.simulate_plan_outcomes(
            branch='main',
            num_scenarios=1000,
            horizon_weeks=13,
            variables={
                'demand': 'lognormal',
                'lead_time': 'gamma',
                'yield': 'beta',
                'capacity': 'normal'
            }
        )

        # Compare distributions
        impact = self.compare_stochastic_plans(baseline_results, stochastic_results)

        # Cleanup simulation branch
        await self.version_control.delete_branch(scenario_branch)

        return impact

    def compare_stochastic_plans(self, baseline, scenario):
        """
        Compare two stochastic plan results.

        Returns:
        - scenarios: List of paired comparisons (baseline[i] vs scenario[i])
        - expected_values: Mean of deltas
        - distributions: Percentiles of deltas
        - confidence: How likely is scenario better than baseline?
        """

        scenarios_comparison = []

        for i in range(len(baseline['scenarios'])):
            base_scenario = baseline['scenarios'][i]
            alt_scenario = scenario['scenarios'][i]

            comparison = {
                'stockout_resolved': (base_scenario['has_stockout'] and not alt_scenario['has_stockout']),
                'risk_reduction_pct': (base_scenario['stockout_probability'] - alt_scenario['stockout_probability']) * 100,
                'service_level': alt_scenario['service_level'],
                'service_level_delta': alt_scenario['service_level'] - base_scenario['service_level'],
                'total_cost_delta': alt_scenario['total_cost'] - base_scenario['total_cost'],
                'inventory_cost_delta': alt_scenario['inventory_cost'] - base_scenario['inventory_cost'],
                'co2_reduction_kg': base_scenario['co2_emissions_kg'] - alt_scenario['co2_emissions_kg'],
                'transfer_distance_km': alt_scenario.get('transfer_distance_km', 0)
            }

            scenarios_comparison.append(comparison)

        # Calculate aggregate statistics
        return {
            'scenarios': scenarios_comparison,
            'expected_values': {
                'cost_delta': np.mean([s['total_cost_delta'] for s in scenarios_comparison]),
                'service_level': np.mean([s['service_level'] for s in scenarios_comparison]),
                'co2_reduction': np.mean([s['co2_reduction_kg'] for s in scenarios_comparison])
            },
            'distributions': {
                'cost_delta_p10': np.percentile([s['total_cost_delta'] for s in scenarios_comparison], 10),
                'cost_delta_p50': np.percentile([s['total_cost_delta'] for s in scenarios_comparison], 50),
                'cost_delta_p90': np.percentile([s['total_cost_delta'] for s in scenarios_comparison], 90),
                'service_level_p10': np.percentile([s['service_level'] for s in scenarios_comparison], 10),
                'service_level_p50': np.percentile([s['service_level'] for s in scenarios_comparison], 50),
                'service_level_p90': np.percentile([s['service_level'] for s in scenarios_comparison], 90)
            },
            'confidence': {
                'probability_better_cost': np.mean([s['total_cost_delta'] < 0 for s in scenarios_comparison]),
                'probability_better_service': np.mean([s['service_level_delta'] > 0 for s in scenarios_comparison])
            }
        }
```

#### Conformal Prediction Integration with Agent Intelligence

**Conformal Prediction for Formal Guarantees**:

While stochastic planning (Monte Carlo simulation) provides **empirical probabilities** based on sampled scenarios, **conformal prediction** provides **formal mathematical guarantees** that hold regardless of distribution assumptions.

**Integration Strategy**:

| Use Case | Stochastic Planning (Monte Carlo) | Conformal Prediction |
|----------|-----------------------------------|----------------------|
| **Internal Risk Detection** | Empirical probabilities from 1000 scenarios | **Not needed** (empirical is sufficient) |
| **Agent Recommendations** | Score actions using expected values | **Not needed** (comparative analysis) |
| **Customer Order Promising** | Estimate delivery probability | **Use conformal** (formal guarantee required) |
| **Safety Stock Calculation** | Simulate stockout probability | **Use conformal** (service level guarantee) |
| **Supplier SLA Commitments** | Predict lead time variance | **Use conformal** (formal coverage guarantee) |

**Hybrid Approach** (Best Practice):

```python
class HybridStochasticConformalAgent:
    """
    Agent that combines stochastic simulation (for exploration) with
    conformal prediction (for formal guarantees).
    """

    def __init__(self):
        self.monte_carlo = StochasticSampler()
        self.conformal_demand = ConformalPredictor(alpha=0.10)  # 90% guarantee
        self.conformal_lead_time = ConformalPredictor(alpha=0.05)  # 95% guarantee

    async def calculate_safety_stock_hybrid(
        self,
        product_id: str,
        site_id: str,
        target_service_level: float = 0.95
    ) -> dict:
        """
        Hybrid approach:
        1. Monte Carlo simulation explores full distribution (internal use)
        2. Conformal prediction provides formal guarantee (external commitment)
        """

        # 1. Monte Carlo: Explore demand and lead time distributions
        mc_scenarios = await self.monte_carlo.simulate_inventory_trajectory(
            product_id=product_id,
            site_id=site_id,
            horizon_weeks=13,
            num_scenarios=1000
        )

        mc_safety_stock = self.calculate_safety_stock_from_mc(mc_scenarios, target_service_level)

        # 2. Conformal: Calculate with formal coverage guarantee
        demand_forecast = self.get_demand_forecast(product_id, site_id)
        demand_lower, demand_upper = self.conformal_demand.predict(demand_forecast)

        lead_time_forecast = self.get_lead_time_forecast(product_id, site_id)
        lt_lower, lt_upper = self.conformal_lead_time.predict(lead_time_forecast)

        # Conformal safety stock: worst-case with formal guarantee
        conformal_safety_stock = (demand_upper * lt_upper) - (demand_forecast * lead_time_forecast)

        # Joint coverage probability
        coverage_guarantee = (1 - self.conformal_demand.alpha) * (1 - self.conformal_lead_time.alpha)

        return {
            'recommended_safety_stock': conformal_safety_stock,  # Use conformal (conservative)
            'monte_carlo_safety_stock': mc_safety_stock,  # For comparison
            'method': 'hybrid_conformal_mc',
            'coverage_guarantee': coverage_guarantee,  # Formal guarantee
            'monte_carlo_service_level': self.calculate_mc_service_level(mc_scenarios),  # Empirical
            'recommendation': 'Use conformal for customer-facing commitments',
            'confidence_interval': {
                'demand': (demand_lower, demand_upper),
                'lead_time': (lt_lower, lt_upper)
            }
        }

    async def promise_order_with_guarantee(
        self,
        order_qty: int,
        requested_due_date: int,
        product_id: str,
        site_id: str
    ) -> dict:
        """
        Order promising with formal conformal guarantee (customer-facing).
        Monte Carlo used for internal risk assessment only.
        """

        # 1. Monte Carlo: Internal risk assessment
        mc_scenarios = await self.monte_carlo.simulate_atp_scenarios(
            product_id=product_id,
            site_id=site_id,
            order_qty=order_qty,
            due_date=requested_due_date,
            num_scenarios=1000
        )

        mc_promise_probability = np.mean([s.can_fulfill for s in mc_scenarios])

        # 2. Conformal: Formal guarantee for customer
        conformal_promise = await self.conformal_atp_calculator.promise_with_guarantee(
            order_qty=order_qty,
            requested_due_date=requested_due_date,
            product_id=product_id,
            site_id=site_id,
            target_confidence=0.95  # 95% formal guarantee
        )

        # 3. Decide based on customer type
        if self.is_vip_customer(order):
            # VIP: Use conformal guarantee (conservative, but formal)
            return {
                'can_promise': conformal_promise['can_promise'],
                'promised_due_date': conformal_promise['guaranteed_due_date'],
                'confidence_level': conformal_promise['confidence_level'],
                'method': 'conformal_guarantee',
                'message': f"We guarantee delivery by {conformal_promise['guaranteed_due_date']} "
                          f"with {conformal_promise['confidence_level']:.1%} formal confidence"
            }
        else:
            # Standard: Use Monte Carlo (less conservative, empirical)
            return {
                'can_promise': mc_promise_probability > 0.80,
                'promised_due_date': requested_due_date if mc_promise_probability > 0.80 else requested_due_date + 3,
                'confidence_level': mc_promise_probability,
                'method': 'monte_carlo_empirical',
                'message': f"We expect to deliver by {requested_due_date} "
                          f"with {mc_promise_probability:.1%} probability (empirical estimate)"
            }
```

**When to Use Conformal vs. Stochastic**:

**Conformal Prediction (Formal Guarantees)**:
- ✅ Customer order promising (ATP/CTP)
- ✅ Supplier SLA commitments
- ✅ Service level targets in contracts
- ✅ Safety stock calculations for critical SKUs
- ✅ Any external commitment requiring legal backing

**Monte Carlo Stochastic (Empirical Probabilities)**:
- ✅ Internal risk detection and alerts
- ✅ Agent decision scoring and ranking
- ✅ What-if scenario analysis
- ✅ Plan vs. actual variance explanation
- ✅ Balanced scorecard KPI tracking

**Conformal Prediction for Supply-Side Variables**:

Extend conformal prediction to all operational variables:

```python
class ConformalSupplyChainAgent:
    """
    Comprehensive conformal prediction for all supply chain uncertainties.
    """

    def __init__(self):
        # Demand-side conformal predictors
        self.conformal_demand = ConformalPredictor(alpha=0.10)  # 90% coverage
        self.conformal_forecast_error = ConformalPredictor(alpha=0.05)  # 95% coverage

        # Supply-side conformal predictors
        self.conformal_lead_time = ConformalPredictor(alpha=0.10)  # 90% coverage
        self.conformal_yield = ConformalPredictor(alpha=0.05)  # 95% coverage
        self.conformal_capacity = ConformalPredictor(alpha=0.10)  # 90% coverage
        self.conformal_transit_time = ConformalPredictor(alpha=0.05)  # 95% coverage

    async def calibrate_all_predictors(self, historical_data: dict):
        """
        Calibrate all conformal predictors using Plan vs. Actual data.
        """
        # Demand-side calibration
        await self.conformal_demand.calibrate(
            historical_data['actual_demand'],
            historical_data['forecast_demand']
        )

        await self.conformal_forecast_error.calibrate(
            historical_data['actual_demand'],
            historical_data['statistical_forecast']
        )

        # Supply-side calibration
        await self.conformal_lead_time.calibrate(
            historical_data['actual_lead_times'],
            historical_data['planned_lead_times']
        )

        await self.conformal_yield.calibrate(
            historical_data['actual_yields'],
            historical_data['planned_yields']
        )

        await self.conformal_capacity.calibrate(
            historical_data['actual_capacity'],
            historical_data['planned_capacity']
        )

        await self.conformal_transit_time.calibrate(
            historical_data['actual_transit_times'],
            historical_data['planned_transit_times']
        )

        print("All conformal predictors calibrated successfully")
        print(f"Demand coverage guarantee: {1 - self.conformal_demand.alpha:.1%}")
        print(f"Lead time coverage guarantee: {1 - self.conformal_lead_time.alpha:.1%}")
        print(f"Yield coverage guarantee: {1 - self.conformal_yield.alpha:.1%}")

    async def plan_with_formal_guarantees(self, product_id: str, site_id: str) -> dict:
        """
        Generate MPS plan with formal conformal guarantees on all variables.
        """
        # Demand with conformal interval
        demand_forecast = self.get_demand_forecast(product_id, site_id)
        demand_lower, demand_upper = self.conformal_demand.predict(demand_forecast)

        # Lead time with conformal interval
        lt_forecast = self.get_lead_time_forecast(product_id, site_id)
        lt_lower, lt_upper = self.conformal_lead_time.predict(lt_forecast)

        # Yield with conformal interval
        yield_forecast = self.get_yield_forecast(product_id, site_id)
        yield_lower, yield_upper = self.conformal_yield.predict(yield_forecast)

        # Capacity with conformal interval
        capacity_forecast = self.get_capacity_forecast(site_id)
        capacity_lower, capacity_upper = self.conformal_capacity.predict(capacity_forecast)

        # Calculate production plan with formal guarantees
        # Conservative: use upper demand, lower yield, lower capacity
        required_production = (demand_upper / yield_lower)

        can_produce = required_production <= capacity_lower

        # Joint coverage probability (assuming independence)
        joint_coverage = (
            (1 - self.conformal_demand.alpha) *
            (1 - self.conformal_lead_time.alpha) *
            (1 - self.conformal_yield.alpha) *
            (1 - self.conformal_capacity.alpha)
        )

        return {
            'product_id': product_id,
            'site_id': site_id,
            'demand_interval': (demand_lower, demand_upper),
            'lead_time_interval': (lt_lower, lt_upper),
            'yield_interval': (yield_lower, yield_upper),
            'capacity_interval': (capacity_lower, capacity_upper),
            'required_production': required_production,
            'can_produce_with_guarantee': can_produce,
            'joint_coverage_guarantee': joint_coverage,
            'method': 'conformal_mps_planning',
            'recommendation': 'Formal guarantee on feasibility' if can_produce else 'Capacity constraint detected'
        }
```

**Conformal Prediction in Agent Event Handling**:

```python
class ConformalRiskDetectionAgent(NativeInsightEngine):
    """
    Enhanced risk detection using conformal prediction for formal guarantees.
    """

    async def detect_stockout_risk_with_guarantee(
        self,
        product_id: str,
        site_id: str,
        target_service_level: float = 0.95
    ) -> Optional[PlanningEvent]:
        """
        Detect stockout risk with formal conformal guarantee.

        Traditional: Monte Carlo estimates probability
        Conformal: Provides formal coverage guarantee
        """

        # 1. Monte Carlo for empirical probability (internal assessment)
        mc_scenarios = await self.stochastic_sampler.simulate_inventory_trajectory(
            product_id=product_id,
            site_id=site_id,
            horizon_weeks=13,
            num_scenarios=1000
        )

        mc_stockout_prob = np.mean([s.has_stockout for s in mc_scenarios])

        # 2. Conformal prediction for formal guarantee (external commitment)
        conformal_analysis = await self.conformal_agent.plan_with_formal_guarantees(
            product_id=product_id,
            site_id=site_id
        )

        # 3. Determine if formal guarantee can be met
        can_guarantee_service_level = conformal_analysis['joint_coverage_guarantee'] >= target_service_level

        # 4. Generate event if formal guarantee cannot be met
        if not can_guarantee_service_level or mc_stockout_prob > 0.20:
            severity = 'CRITICAL' if mc_stockout_prob > 0.50 else 'HIGH'

            planning_event = PlanningEvent(
                event_type='INVENTORY_RISK_STOCKOUT_CONFORMAL',
                source_system='CONFORMAL_RISK_ENGINE',
                priority='P0' if severity == 'CRITICAL' else 'P1',
                payload={
                    'product_id': product_id,
                    'site_id': site_id,
                    'risk_type': 'STOCKOUT_FORMAL_GUARANTEE_VIOLATION',
                    'monte_carlo_stockout_probability': mc_stockout_prob,
                    'conformal_coverage_guarantee': conformal_analysis['joint_coverage_guarantee'],
                    'target_service_level': target_service_level,
                    'can_guarantee_formal': can_guarantee_service_level,
                    'demand_interval': conformal_analysis['demand_interval'],
                    'lead_time_interval': conformal_analysis['lead_time_interval'],
                    'yield_interval': conformal_analysis['yield_interval'],
                    'recommendation': 'Increase safety stock to meet formal guarantee' if not can_guarantee_service_level else 'Monitor closely',
                    'method': 'hybrid_monte_carlo_conformal'
                },
                event_timestamp=datetime.utcnow()
            )

            await self.event_bus.publish(planning_event)

            return planning_event

        return None  # Formal guarantee can be met
```

**Benefits of Hybrid Approach**:

| Metric | Monte Carlo Only | Conformal Only | **Hybrid (Best)** |
|--------|------------------|----------------|-------------------|
| **Internal Risk Detection** | ✅ Good | ❌ Overly conservative | ✅ Use MC (empirical) |
| **Customer Commitments** | ❌ No formal guarantee | ✅ Formal guarantee | ✅ Use conformal (formal) |
| **Exploration of Uncertainty** | ✅ Full distribution | ❌ Only intervals | ✅ Use MC for exploration |
| **Computational Cost** | ❌ High (1000+ scenarios) | ✅ Low (quantile calc) | ✅ Use conformal for commitments |
| **Adaptability** | ✅ Adapts to any distribution | ✅ Distribution-free | ✅ Both adapt |

#### Multi-Agent Collaboration

**Native Agent-to-Agent (A2A) Communication Protocol**:

Agents collaborate to reach consensus on plans that optimize shared KPIs using stochastic outcomes:

**A2A Communication Protocol**:

```python
class AgentToAgentProtocol:
    """
    Agent-to-agent communication for shared goal optimization.

    Agents collaborate to reach consensus on plans that optimize
    shared KPIs (cost, service level, inventory turns, CO2 emissions).
    """

    def __init__(self, shared_kpis):
        self.shared_kpis = shared_kpis
        self.communication_log = []

    async def coordinate_agents(self, triggered_agents, event):
        """
        Facilitate multi-agent collaboration to reach shared goal.

        Example: MPS agent wants to increase production, but Capacity agent
        flags constraint. Agents negotiate compromise.
        """

        # 1. Each agent generates initial proposal
        proposals = {}
        for agent in triggered_agents:
            proposal = await agent.generate_proposal(event)
            proposals[agent.agent_type] = proposal

        # 2. Detect conflicts
        conflicts = self.detect_inter_agent_conflicts(proposals)

        if len(conflicts) == 0:
            # No conflicts, proceed with all proposals
            return {'status': 'CONSENSUS', 'proposals': proposals}

        # 3. Multi-agent negotiation (up to 3 rounds)
        for round_num in range(3):
            negotiation_context = {
                'round': round_num,
                'conflicts': conflicts,
                'shared_kpis': self.shared_kpis,
                'proposals': proposals
            }

            # Each agent revises proposal considering others
            revised_proposals = {}
            for agent in triggered_agents:
                revised = await agent.revise_proposal(negotiation_context)
                revised_proposals[agent.agent_type] = revised

                # Log communication
                self.communication_log.append({
                    'timestamp': datetime.utcnow(),
                    'round': round_num,
                    'agent': agent.agent_type,
                    'message': revised['negotiation_message'],
                    'proposal_change': self.diff_proposals(
                        proposals[agent.agent_type],
                        revised
                    )
                })

            proposals = revised_proposals

            # Re-check conflicts
            conflicts = self.detect_inter_agent_conflicts(proposals)

            if len(conflicts) == 0:
                return {'status': 'CONSENSUS_REACHED', 'round': round_num, 'proposals': proposals}

        # 4. Failed to reach consensus → escalate to LLM Supervisor
        return await self.llm_supervisor_mediation(proposals, conflicts, event)

    async def llm_supervisor_mediation(self, proposals, conflicts, event):
        """
        LLM Supervisor mediates unresolved agent conflicts.

        Provides:
        - Conflict analysis
        - Recommended compromise
        - Trade-off explanation
        """

        prompt = f"""
        Multiple planning agents have conflicting proposals for event {event.event_type}:

        {self.format_proposals_for_llm(proposals)}

        Conflicts:
        {self.format_conflicts_for_llm(conflicts)}

        Shared KPIs:
        - Service Level Target: {self.shared_kpis['service_level_target']}%
        - Inventory Turns Target: {self.shared_kpis['inventory_turns_target']}
        - Total Cost Budget: ${self.shared_kpis['cost_budget']}
        - CO2 Emissions Limit: {self.shared_kpis['co2_limit_kg']} kg

        Analyze the trade-offs and recommend:
        1. Which proposal best balances the shared KPIs
        2. Suggested compromise (if applicable)
        3. Explanation of trade-offs
        4. Whether human review is required
        """

        llm_response = await self.llm.complete(prompt)

        resolution = self.parse_llm_mediation(llm_response)

        # Log mediation
        self.communication_log.append({
            'timestamp': datetime.utcnow(),
            'event': 'LLM_SUPERVISOR_MEDIATION',
            'resolution': resolution,
            'requires_human': resolution['requires_human_review']
        })

        return resolution

    def detect_inter_agent_conflicts(self, proposals):
        """
        Detect conflicts between agent proposals.

        Conflict types:
        - Resource contention (same machine, same week)
        - SKU overlap (both agents modifying same product/week)
        - Policy contradiction (agent A increases, agent B decreases)
        - Capacity violation (combined proposals exceed capacity)
        """
        conflicts = []

        agent_pairs = combinations(proposals.keys(), 2)

        for agent1, agent2 in agent_pairs:
            prop1 = proposals[agent1]
            prop2 = proposals[agent2]

            # Check SKU/week overlap
            sku_conflicts = self.find_sku_conflicts(prop1, prop2)
            if sku_conflicts:
                conflicts.append({
                    'type': 'SKU_OVERLAP',
                    'agents': [agent1, agent2],
                    'details': sku_conflicts
                })

            # Check capacity conflicts
            capacity_conflicts = self.find_capacity_conflicts(prop1, prop2)
            if capacity_conflicts:
                conflicts.append({
                    'type': 'CAPACITY_CONFLICT',
                    'agents': [agent1, agent2],
                    'details': capacity_conflicts
                })

        return conflicts
```

**Shared KPI Dashboard** (Agent Performance Goals):

```python
class SharedKPIDashboard:
    """
    Track shared performance goals that all agents optimize toward.

    Agents collaborate to achieve balanced outcomes across:
    - Financial: Total cost, EBITDA
    - Customer: Service level, OTIF
    - Operational: Inventory turns, lead time
    - Strategic: Sustainability (CO2), supplier diversity
    """

    def __init__(self):
        self.kpi_targets = {
            'service_level': {'target': 95.0, 'weight': 0.30},
            'total_cost': {'target': 1_000_000, 'weight': 0.25},
            'inventory_turns': {'target': 12, 'weight': 0.20},
            'otif': {'target': 90.0, 'weight': 0.15},
            'co2_emissions_kg': {'target': 50_000, 'weight': 0.10}
        }

    def calculate_shared_score(self, plan):
        """
        Calculate weighted score across all shared KPIs.

        Returns 0-100 score representing how well plan achieves
        balanced performance across all dimensions.
        """
        score = 0.0

        for kpi_name, config in self.kpi_targets.items():
            actual = plan.get_kpi_value(kpi_name)
            target = config['target']
            weight = config['weight']

            # Normalize to 0-100 (100 = met or exceeded target)
            if kpi_name in ['service_level', 'inventory_turns', 'otif']:
                # Higher is better
                kpi_score = min(100, (actual / target) * 100)
            else:
                # Lower is better (cost, CO2)
                kpi_score = min(100, (target / actual) * 100)

            score += kpi_score * weight

        return score
```

### 7.5 Automate-Inform-Inspect-Override (AIIO) Framework

**AIIO Principle**: Agents automate planning and inform humans, humans inspect results and override when necessary.

#### AIIO Responsibility Matrix

| Stage | Responsibility | Performer | Tool/Interface |
|-------|---------------|-----------|----------------|
| **Automate** | Generate plan recommendations | Agents | Event-driven agents, A2A collaboration |
| **Inform** | Notify humans of decisions | Agents | LLM chat, email alerts, dashboard |
| **Inspect** | Review agent decisions | Humans | LLM-first UI, point-and-click deep dive |
| **Override** | Change plan + provide context | Humans | UI with reason capture, file upload |

#### Automate: Agent Autonomous Actions

**What Agents Automate**:

1. **Routine Planning Tasks**:
   - MPS generation from demand forecasts
   - MRP explosion from BOM and MPS
   - Safety stock calculation from policy parameters
   - Order promising (ATP/CTP) within guardrails

2. **Exception Detection**:
   - Stockout risks, excess inventory
   - Capacity constraint violations
   - Supplier lead-time deviations
   - Service level breaches

3. **Recommendation Generation**:
   - Rebalancing options (transfer, expedite, substitute)
   - Policy adjustments (safety stock, reorder points)
   - Sourcing alternatives (backup vendors)

4. **Impact Simulation**:
   - "What-if" analysis in scenario branches
   - KPI impact estimation (cost, service level, CO2)
   - Risk vs. reward trade-off scoring

**Guardrails** (Limits on Agent Autonomy):

```python
class AgentGuardrails:
    """
    Define boundaries within which agents can act autonomously.
    Actions outside guardrails require human approval.
    """

    def __init__(self):
        self.guardrails = {
            # Financial guardrails
            'max_plan_cost_increase_pct': 5.0,  # Cannot increase plan cost >5% without approval
            'max_order_value_usd': 50_000,  # Cannot create PO >$50K without approval

            # Operational guardrails
            'max_safety_stock_increase_pct': 20.0,  # Cannot increase SS >20% without approval
            'max_production_qty_change_pct': 15.0,  # Cannot change MPS qty >15% without approval
            'max_lead_time_override_days': 7,  # Cannot change lead time >7 days without approval

            # Customer guardrails
            'min_service_level_pct': 92.0,  # Cannot accept plan with SL <92%
            'max_order_delay_days': 3,  # Cannot delay customer order >3 days without approval

            # Strategic guardrails
            'max_co2_increase_pct': 10.0,  # Cannot increase CO2 emissions >10%
            'min_supplier_diversity': 2  # Must maintain at least 2 suppliers per component
        }

    def check_agent_action(self, action, baseline_plan):
        """
        Verify agent action is within guardrails.

        Returns:
        - within_guardrails: True/False
        - violated_guardrails: List of guardrail violations
        - requires_human_approval: True if action needs human review
        """
        violations = []

        # Check cost impact
        cost_delta_pct = ((action.total_cost - baseline_plan.total_cost) /
                          baseline_plan.total_cost) * 100
        if cost_delta_pct > self.guardrails['max_plan_cost_increase_pct']:
            violations.append({
                'guardrail': 'max_plan_cost_increase_pct',
                'threshold': self.guardrails['max_plan_cost_increase_pct'],
                'actual': cost_delta_pct,
                'severity': 'HIGH'
            })

        # Check service level
        if action.service_level < self.guardrails['min_service_level_pct']:
            violations.append({
                'guardrail': 'min_service_level_pct',
                'threshold': self.guardrails['min_service_level_pct'],
                'actual': action.service_level,
                'severity': 'CRITICAL'
            })

        # Check order value (if creating PO)
        if action.action_type == 'CREATE_PURCHASE_ORDER':
            if action.order_value > self.guardrails['max_order_value_usd']:
                violations.append({
                    'guardrail': 'max_order_value_usd',
                    'threshold': self.guardrails['max_order_value_usd'],
                    'actual': action.order_value,
                    'severity': 'MEDIUM'
                })

        within_guardrails = len(violations) == 0
        requires_approval = any(v['severity'] in ['HIGH', 'CRITICAL'] for v in violations)

        return {
            'within_guardrails': within_guardrails,
            'violations': violations,
            'requires_human_approval': requires_approval
        }
```

**Auto-Execute vs. Human Approval Decision Tree**:

```
Agent generates recommendation
    ↓
Check guardrails
    ↓
Within guardrails? ────→ YES ────→ Check LLM Supervisor confidence
    ↓                                     ↓
   NO                             Confidence >90%? ──→ YES ──→ AUTO-EXECUTE + INFORM
    ↓                                     ↓                         (commit to main)
    ↓                                    NO
    ↓                                     ↓
    └─────────→ REQUIRES HUMAN APPROVAL ←┘
                         ↓
                 INFORM + AWAIT INSPECT
```

#### Inform: Agent Communication to Humans

**Notification Channels**:

1. **LLM Chat Interface** (Primary):
   ```
   Agent: "I've detected a stockout risk for CASE at DC-Boston in Week 8.
          Current inventory: 25 units, Forecasted demand: 150 units.

          I recommend transferring 100 units from DC-New York (200 km, 2-day transit).

          Impact:
          - Risk resolved: 100%
          - Service level: 95% → 98% (+3%)
          - Cost: +$2,450 (transfer + expedite)
          - CO2: +15 kg

          This action is within guardrails and has been auto-executed.
          Scenario branch 'scenario/inventory-dc-boston-rebalance' merged to main.

          [View Details] [Undo Action]"
   ```

2. **Email Alerts** (Critical/High Priority):
   - Subject: "🚨 Critical: Capacity constraint violation detected - Week 5"
   - Body: Summary + link to LLM chat session + link to deep-dive UI

3. **Dashboard Notifications** (All Priorities):
   - Badge count: "3 agent actions today"
   - Activity feed: Chronological list of agent decisions
   - Filterable by agent type, priority, outcome

**Notification Content Structure**:

```python
class AgentNotification:
    """
    Standardized notification format for agent communications.
    """

    def __init__(self, agent_decision):
        self.notification_id = str(uuid.uuid4())
        self.agent_type = agent_decision.agent_type
        self.timestamp = datetime.utcnow()
        self.priority = agent_decision.priority
        self.action_taken = agent_decision.action_type
        self.requires_review = agent_decision.requires_human_approval

        # Human-readable summary (LLM-generated)
        self.summary = agent_decision.llm_summary

        # Structured data for programmatic access
        self.details = {
            'trigger_event': agent_decision.trigger_event,
            'recommendation': agent_decision.recommendation,
            'impact': agent_decision.impact_analysis,
            'guardrail_status': agent_decision.guardrail_check,
            'scenario_branch': agent_decision.scenario_branch,
            'commit_id': agent_decision.commit_id,
            'auto_executed': agent_decision.auto_executed
        }

        # Actions planner can take
        self.available_actions = []
        if agent_decision.auto_executed:
            self.available_actions = ['view_details', 'undo', 'provide_feedback']
        else:
            self.available_actions = ['approve', 'reject', 'modify', 'request_alternatives']

    def format_for_chat(self):
        """Format notification for LLM chat interface."""
        return f"""
**{self.agent_type.upper()} Agent Action** - {self.priority}

{self.summary}

**Impact Analysis:**
- Service Level: {self.details['impact']['service_level_before']}% → {self.details['impact']['service_level_after']}%
- Total Cost: ${self.details['impact']['cost_before']:,.0f} → ${self.details['impact']['cost_after']:,.0f} ({self.details['impact']['cost_delta_pct']:+.1f}%)
- CO2 Emissions: {self.details['impact']['co2_delta_kg']:+,.0f} kg

**Status:** {'✅ Auto-executed' if self.auto_executed else '⏳ Awaiting your review'}

[View Details](#) [Scenario Diff](#) {'[Undo](#)' if self.auto_executed else '[Approve](#) [Reject](#)'}
"""

    def format_for_email(self):
        """Format notification for email alert."""
        priority_emoji = {'P0': '🚨', 'P1': '⚠️', 'P2': '⚡', 'P3': 'ℹ️'}

        return {
            'subject': f"{priority_emoji[self.priority]} {self.agent_type} Agent: {self.action_taken}",
            'body': self.format_for_chat(),
            'links': {
                'chat_session': f'/planning/chat?notification_id={self.notification_id}',
                'deep_dive': f'/planning/scenario/{self.details["scenario_branch"]}',
                'action': f'/planning/actions/{self.notification_id}'
            }
        }
```

**Inform Frequency** (Configurable per Planner):

```python
class PlannerNotificationPreferences:
    """
    Per-planner notification preferences.
    """

    def __init__(self, planner_id):
        self.planner_id = planner_id

        # Notification channels by priority
        self.channel_preferences = {
            'P0': ['chat', 'email', 'sms'],  # Critical: All channels
            'P1': ['chat', 'email'],  # High: Chat + email
            'P2': ['chat'],  # Medium: Chat only
            'P3': ['chat']  # Low: Chat only (no interrupt)
        }

        # Batching preferences (reduce notification fatigue)
        self.batching = {
            'P3': {'enabled': True, 'interval_minutes': 60},  # Batch P3 notifications hourly
            'P2': {'enabled': True, 'interval_minutes': 15}  # Batch P2 notifications every 15 min
        }

        # Quiet hours (no notifications)
        self.quiet_hours = {
            'enabled': True,
            'start_time': '22:00',
            'end_time': '07:00',
            'timezone': 'America/New_York',
            'exceptions': ['P0']  # P0 still notifies during quiet hours
        }
```

#### Inspect: Human Review of Agent Decisions

**Inspection Modes**:

1. **LLM Chat Query** (Natural Language):
   ```
   Planner: "Show me all agent actions from today"

   LLM: "I found 12 agent actions today:
         - 5 by MPS Agent (all auto-executed, average cost impact: +$1,200)
         - 3 by MRP Agent (2 auto-executed, 1 awaiting your review)
         - 2 by Inventory Agent (both auto-executed, inventory reduction: -15%)
         - 2 by Capacity Agent (both auto-executed, utilization improved: +8%)

         [View All] [Filter by Impact] [Show Pending Only]"

   Planner: "Show me the MRP action that needs my review"

   LLM: "The MRP Agent recommends creating a Purchase Order for 500 units of
         BOTTLE from Vendor-B (backup supplier).

         Reason: Primary vendor (Vendor-A) delayed shipment by 10 days.

         This action requires your review because:
         - Order value ($62,000) exceeds auto-execute threshold ($50,000)

         Would you like to approve, modify, or request alternatives?"
   ```

2. **Point-and-Click Dashboard**:
   - **Agent Activity Feed**: Chronological list with filters
   - **Scenario Comparison**: Side-by-side diff of baseline vs. agent proposal
   - **KPI Impact Chart**: Before/after visualization of key metrics
   - **Gantt Chart**: Visual schedule changes

3. **Deep Dive Inspection** (Detailed Analysis):
   ```
   Agent Decision Details

   ┌─────────────────────────────────────────────────────────┐
   │ MPS Agent Decision: Increase CASE production Week 8     │
   │ Timestamp: 2026-01-23 14:32:15 UTC                      │
   │ Status: Auto-executed ✅                                 │
   ├─────────────────────────────────────────────────────────┤
   │ Trigger Event:                                          │
   │ - Type: DEMAND_CHANGE                                   │
   │ - Source: New customer order SO-12345                   │
   │ - Priority: P1 (High)                                   │
   ├─────────────────────────────────────────────────────────┤
   │ Recommendation:                                         │
   │ - Increase CASE production from 100 → 120 units        │
   │ - Week: 8 (2026-02-17)                                  │
   │ - Site: Factory-Main                                    │
   ├─────────────────────────────────────────────────────────┤
   │ Impact Analysis:                                        │
   │ Service Level: 94.2% → 96.8% (+2.6%)                   │
   │ Total Cost: $45,230 → $47,680 (+$2,450, +5.4%)         │
   │ Inventory Turns: 11.2 → 11.5 (+0.3)                    │
   │ CO2 Emissions: +18 kg                                   │
   │ Machine-A Utilization: 85% → 92% (+7%)                 │
   ├─────────────────────────────────────────────────────────┤
   │ Guardrail Check: ✅ All guardrails passed               │
   │ - Cost increase: 5.4% (threshold: 10%)                 │
   │ - Production change: 20% (threshold: 25%)              │
   │ - Service level: 96.8% (min: 92%)                      │
   ├─────────────────────────────────────────────────────────┤
   │ Agent Confidence: 94% (High)                            │
   │ LLM Supervisor Review: Approved                         │
   ├─────────────────────────────────────────────────────────┤
   │ Scenario Branch: scenario/mps-so-12345-replan          │
   │ Commit ID: a3f9c2e7-8b4d-4f2e-9a1c-6d8e3f7b2a9c        │
   │ Merged to: main                                         │
   │ Merge Timestamp: 2026-01-23 14:33:42 UTC               │
   └─────────────────────────────────────────────────────────┘

   [View Scenario Diff] [View Plan vs. Actual] [Provide Feedback] [Undo Action]
   ```

**Inspection Workflow**:

```
Planner receives notification
    ↓
Planner asks LLM: "What did agents do today?"
    ↓
LLM summarizes: "12 actions, 1 needs your review"
    ↓
Planner: "Show me details on the one that needs review"
    ↓
LLM provides: Summary + [View Deep Dive] button
    ↓
Planner clicks: Opens point-and-click UI with full details
    ↓
Planner reviews: Scenario diff, KPI impact, agent reasoning
    ↓
Planner decides: Approve, Modify, Reject, or Request Alternatives
```

#### Override: Human Changes with Context Capture

**When Humans Override**:

1. **Reject Agent Recommendation**: "I don't agree with this action"
2. **Modify Agent Proposal**: "I agree with the direction, but want to change the quantity"
3. **Manual Plan Change**: "I'm making a manual adjustment outside of agent recommendations"

**Context Capture Requirement**:

When a human overrides an agent decision, they MUST provide context so the system can learn:

```python
class HumanOverride:
    """
    Capture human override with mandatory context for learning.
    """

    def __init__(self, planner_id, agent_decision_id, override_type):
        self.override_id = str(uuid.uuid4())
        self.planner_id = planner_id
        self.agent_decision_id = agent_decision_id
        self.override_type = override_type  # 'REJECT', 'MODIFY', 'MANUAL_CHANGE'
        self.timestamp = datetime.utcnow()

        # MANDATORY: Reason for override
        self.reason_category = None  # See categories below
        self.reason_details = None  # Free-text explanation

        # OPTIONAL: Supporting files
        self.uploaded_files = []  # PDFs, spreadsheets, emails, etc.

        # Override action
        self.override_action = None  # What planner did instead

        # Learning capture
        self.captured_context = {}

    def capture_reason(self, category, details, files=None):
        """
        Capture reason for override.

        Reason Categories (Standardized):
        - DOMAIN_KNOWLEDGE: "Agent lacks domain expertise in this area"
        - EXTERNAL_CONSTRAINT: "External factor agent doesn't know about"
        - STRATEGIC_DECISION: "Strategic business decision"
        - DATA_QUALITY: "Agent's input data is incorrect"
        - POLICY_EXCEPTION: "Special exception to policy"
        - CUSTOMER_PRIORITY: "Customer relationship priority"
        - SUPPLY_CHAIN_INSIGHT: "Agent missed supply chain nuance"
        - COST_SENSITIVITY: "More cost-conscious decision needed"
        - RISK_AVERSION: "Agent's risk tolerance too high"
        - OTHER: "Other reason (explain in details)"
        """

        # Validate category
        valid_categories = [
            'DOMAIN_KNOWLEDGE', 'EXTERNAL_CONSTRAINT', 'STRATEGIC_DECISION',
            'DATA_QUALITY', 'POLICY_EXCEPTION', 'CUSTOMER_PRIORITY',
            'SUPPLY_CHAIN_INSIGHT', 'COST_SENSITIVITY', 'RISK_AVERSION', 'OTHER'
        ]

        if category not in valid_categories:
            raise ValueError(f'Invalid reason category: {category}')

        if not details or len(details) < 10:
            raise ValueError('Reason details must be at least 10 characters')

        self.reason_category = category
        self.reason_details = details

        # Upload supporting files
        if files:
            for file in files:
                self.uploaded_files.append({
                    'filename': file.filename,
                    'content_type': file.content_type,
                    'size_bytes': file.size,
                    'storage_path': self.store_file(file),
                    'uploaded_at': datetime.utcnow()
                })

        # Extract learning context
        self.captured_context = self.extract_learning_context()

    def extract_learning_context(self):
        """
        Extract structured learning context from override.

        This context will be used to:
        1. Fine-tune agent models (if ML-based)
        2. Update agent prompts (if LLM-based)
        3. Adjust guardrails
        4. Improve recommendation scoring
        """

        agent_decision = self.get_agent_decision(self.agent_decision_id)

        context = {
            # Agent's original recommendation
            'agent_recommendation': {
                'action': agent_decision.action,
                'reasoning': agent_decision.reasoning,
                'confidence': agent_decision.confidence,
                'impact': agent_decision.impact_analysis
            },

            # Human's override
            'human_override': {
                'action': self.override_action,
                'reason_category': self.reason_category,
                'reason_details': self.reason_details,
                'outcome_preference': self.extract_outcome_preference()
            },

            # Comparison (what changed)
            'difference': {
                'action_diff': self.diff_actions(agent_decision.action, self.override_action),
                'kpi_preference_diff': self.diff_kpi_preferences(agent_decision, self.override_action)
            },

            # Learning signals
            'learning_signals': {
                'should_adjust_guardrail': self.reason_category in ['POLICY_EXCEPTION', 'RISK_AVERSION'],
                'should_update_kpi_weights': self.reason_category in ['COST_SENSITIVITY', 'CUSTOMER_PRIORITY'],
                'should_add_constraint': self.reason_category in ['EXTERNAL_CONSTRAINT', 'STRATEGIC_DECISION'],
                'should_flag_data_quality': self.reason_category == 'DATA_QUALITY'
            }
        }

        return context

    def extract_outcome_preference(self):
        """
        Infer planner's outcome preferences from override.

        Example: If planner reduced production quantity, infer they
        prefer lower inventory cost over higher service level in this case.
        """

        agent_impact = self.get_agent_decision(self.agent_decision_id).impact_analysis
        override_impact = self.simulate_override_impact(self.override_action)

        preferences = {}

        # Service level preference
        if override_impact['service_level'] < agent_impact['service_level']:
            preferences['service_level'] = 'LOWER_PRIORITY'  # Planner accepted lower SL
        elif override_impact['service_level'] > agent_impact['service_level']:
            preferences['service_level'] = 'HIGHER_PRIORITY'  # Planner wanted higher SL

        # Cost preference
        if override_impact['total_cost'] < agent_impact['total_cost']:
            preferences['cost'] = 'MORE_SENSITIVE'  # Planner chose cheaper option
        elif override_impact['total_cost'] > agent_impact['total_cost']:
            preferences['cost'] = 'LESS_SENSITIVE'  # Planner accepted higher cost

        # CO2 preference
        if override_impact['co2_kg'] < agent_impact['co2_kg']:
            preferences['sustainability'] = 'HIGHER_PRIORITY'
        elif override_impact['co2_kg'] > agent_impact['co2_kg']:
            preferences['sustainability'] = 'LOWER_PRIORITY'

        return preferences
```

**Override UI Flow**:

```
Agent recommendation pending approval
    ↓
Planner clicks: [Reject] or [Modify]
    ↓
Modal appears: "Why are you overriding this recommendation?"
    ↓
┌───────────────────────────────────────────────────────────┐
│ Override Reason (Required)                                │
│                                                           │
│ Category: [Dropdown]                                      │
│ ☐ Domain Knowledge                                        │
│ ☐ External Constraint ✓ (selected)                       │
│ ☐ Strategic Decision                                      │
│ ☐ Data Quality Issue                                      │
│ ☐ Policy Exception                                        │
│ ☐ Customer Priority                                       │
│ ☐ Supply Chain Insight                                    │
│ ☐ Cost Sensitivity                                        │
│ ☐ Risk Aversion                                           │
│ ☐ Other                                                   │
│                                                           │
│ Details (Required, min 10 characters):                    │
│ ┌─────────────────────────────────────────────────────┐  │
│ │ Vendor-B is currently undergoing a facility audit  │  │
│ │ and cannot accept orders for the next 2 weeks.     │  │
│ │ This information is not in the ERP system yet.     │  │
│ └─────────────────────────────────────────────────────┘  │
│                                                           │
│ Supporting Files (Optional):                              │
│ [Upload File] [+ Add Another]                            │
│ 📎 vendor_b_facility_audit_notice.pdf (125 KB)          │
│                                                           │
│ Your Alternative Action:                                  │
│ [Modify Agent Proposal ▼]                                │
│ - Use Vendor-C instead (next best alternative)           │
│ - Quantity: 500 units                                     │
│ - Lead Time: 14 days (vs. 10 days for Vendor-B)         │
│                                                           │
│ Estimated Impact of Your Change:                          │
│ - Service Level: 96.8% → 95.5% (-1.3%)                   │
│ - Total Cost: $47,680 → $49,200 (+$1,520)               │
│ - Delivery: 2 days later than agent's plan              │
│                                                           │
│         [Cancel]  [Submit Override]                       │
└───────────────────────────────────────────────────────────┘
```

**Learning Pipeline from Overrides**:

```python
class AgentLearningPipeline:
    """
    Process human overrides to improve agent performance over time.

    Implements "Reinforcement Learning from Human Feedback" (RLHF)
    for agent improvement.
    """

    def __init__(self):
        self.override_log = []
        self.learning_queue = []

    async def process_override(self, override: HumanOverride):
        """
        Process human override and update agent behavior.
        """

        # 1. Log override for analysis
        self.override_log.append(override)

        # 2. Extract learning signals
        context = override.captured_context
        learning_signals = context['learning_signals']

        # 3. Apply learning based on reason category
        if learning_signals['should_adjust_guardrail']:
            await self.adjust_guardrail(override)

        if learning_signals['should_update_kpi_weights']:
            await self.update_kpi_weights(override)

        if learning_signals['should_add_constraint']:
            await self.add_constraint(override)

        if learning_signals['should_flag_data_quality']:
            await self.flag_data_quality_issue(override)

        # 4. Update agent prompts (for LLM-based agents)
        if override.agent_type == 'llm':
            await self.update_llm_agent_prompt(override)

        # 5. Queue for model retraining (for ML-based agents)
        if override.agent_type in ['mps', 'mrp', 'capacity']:
            self.learning_queue.append({
                'agent_type': override.agent_type,
                'training_example': self.create_training_example(override),
                'timestamp': datetime.utcnow()
            })

        # 6. Trigger batch retraining if queue reaches threshold
        if len(self.learning_queue) >= 100:
            await self.trigger_batch_retraining()

    async def adjust_guardrail(self, override):
        """
        Adjust guardrails based on human override pattern.

        Example: If planner consistently accepts 7% cost increases,
        but guardrail is 5%, consider raising guardrail to 7%.
        """

        # Find similar overrides
        similar_overrides = self.find_similar_overrides(override, lookback_days=30)

        if len(similar_overrides) >= 5:  # Need pattern, not one-off
            # Analyze human's actual tolerance
            actual_tolerances = [o.captured_context['difference']['action_diff']
                                  for o in similar_overrides]

            avg_tolerance = np.mean([t['cost_delta_pct'] for t in actual_tolerances])

            current_guardrail = self.get_guardrail('max_plan_cost_increase_pct')

            if avg_tolerance > current_guardrail * 1.2:  # 20% higher than guardrail
                # Suggest guardrail increase
                suggested_guardrail = avg_tolerance

                await self.escalate_guardrail_change_request(
                    current=current_guardrail,
                    suggested=suggested_guardrail,
                    evidence=similar_overrides,
                    planner_id=override.planner_id
                )

    async def update_kpi_weights(self, override):
        """
        Update shared KPI weights based on planner's preferences.

        Example: If planner consistently chooses lower cost over service level,
        increase weight of cost in agent scoring.
        """

        preferences = override.captured_context['human_override']['outcome_preference']

        # Adjust KPI weights incrementally
        if preferences.get('cost') == 'MORE_SENSITIVE':
            # Increase cost weight by 5%
            current_weight = self.shared_kpis.kpi_targets['total_cost']['weight']
            new_weight = min(1.0, current_weight * 1.05)

            # Reduce other weights proportionally
            await self.rebalance_kpi_weights('total_cost', new_weight)

        if preferences.get('service_level') == 'HIGHER_PRIORITY':
            # Increase service level weight by 5%
            current_weight = self.shared_kpis.kpi_targets['service_level']['weight']
            new_weight = min(1.0, current_weight * 1.05)

            await self.rebalance_kpi_weights('service_level', new_weight)

    async def create_training_example(self, override):
        """
        Create supervised learning example from override.

        Format: (state, agent_action, human_action, human_reasoning)

        This will be used to fine-tune ML models to better match human preferences.
        """

        agent_decision = self.get_agent_decision(override.agent_decision_id)

        training_example = {
            # Input state (what agent saw)
            'state': {
                'demand_forecast': agent_decision.input_state['demand_forecast'],
                'inventory_level': agent_decision.input_state['inventory_level'],
                'capacity_utilization': agent_decision.input_state['capacity_utilization'],
                'service_level': agent_decision.input_state['service_level'],
                'total_cost': agent_decision.input_state['total_cost']
            },

            # Agent's action (what agent recommended)
            'agent_action': agent_decision.action,

            # Human's action (ground truth)
            'human_action': override.override_action,

            # Human's reasoning (for explainability)
            'human_reasoning': {
                'category': override.reason_category,
                'details': override.reason_details,
                'preferences': override.captured_context['human_override']['outcome_preference']
            },

            # Reward signal (how much better was human's action)
            'reward': self.calculate_reward_difference(agent_decision, override)
        }

        return training_example

    def calculate_reward_difference(self, agent_decision, override):
        """
        Calculate reward difference between agent action and human action.

        This is the learning signal:
        - Positive: Human action was better (agent should learn)
        - Negative: Agent action was better (human made suboptimal choice)
        - Zero: No difference
        """

        agent_impact = agent_decision.impact_analysis
        human_impact = self.simulate_override_impact(override.override_action)

        # Calculate multi-objective reward
        agent_score = self.shared_kpis.calculate_shared_score(agent_impact)
        human_score = self.shared_kpis.calculate_shared_score(human_impact)

        reward_diff = human_score - agent_score

        return reward_diff
```

### 7.6 Continuous Learning Loop

**AIIO Learning Cycle**:

```
┌─────────────────────────────────────────────────────────────────┐
│                     CONTINUOUS LEARNING LOOP                    │
└─────────────────────────────────────────────────────────────────┘

1. AUTOMATE
   Agents generate recommendations based on current models
        ↓
2. INFORM
   Notify humans of actions (auto-executed or pending approval)
        ↓
3. INSPECT
   Humans review agent decisions via LLM chat or point-and-click UI
        ↓
4. OVERRIDE
   Humans provide feedback:
   - Approve (implicit positive signal)
   - Override with context (explicit learning signal)
        ↓
5. LEARN
   System captures context:
   - Reason category
   - Free-text explanation
   - Supporting files (PDFs, emails, etc.)
   - Outcome preference (cost vs. service level trade-off)
        ↓
6. UPDATE
   Apply learning:
   - Adjust guardrails (if needed)
   - Update KPI weights (reflect human priorities)
   - Add constraints (external factors)
   - Fine-tune ML models (for ML agents)
   - Update LLM prompts (for LLM agents)
        ↓
7. IMPROVE
   Next iteration: Agents use updated models/prompts/guardrails
        ↓
   (Cycle repeats - agents get better over time)
```

**Learning Metrics Dashboard**:

```python
class AgentLearningMetrics:
    """
    Track agent learning and improvement over time.
    """

    def __init__(self):
        self.metrics = {
            # Approval rates (trend upward as agents learn)
            'auto_execute_rate': [],  # % of actions auto-executed without human review
            'human_approval_rate': [],  # % of pending actions approved by humans
            'override_rate': [],  # % of actions overridden (trend downward)

            # KPI performance (trend toward optimal)
            'service_level_achieved': [],
            'total_cost_vs_budget': [],
            'inventory_turns': [],

            # Learning signal quality
            'overrides_with_rich_context': [],  # % of overrides with file uploads
            'override_reason_diversity': [],  # Variety of override reasons

            # Agent confidence calibration
            'confidence_vs_approval': []  # How well agent confidence predicts human approval
        }

    def calculate_learning_progress(self, lookback_weeks=12):
        """
        Calculate agent learning progress over time.

        Returns:
        - improvement_score: 0-100 (higher = more improvement)
        - auto_execute_trend: 'IMPROVING', 'STABLE', 'DECLINING'
        - override_trend: 'IMPROVING', 'STABLE', 'DECLINING'
        """

        # Get data for lookback period
        recent_data = self.get_metrics_for_period(lookback_weeks)

        # Calculate trends
        auto_execute_trend = self.calculate_trend(recent_data['auto_execute_rate'])
        override_trend = self.calculate_trend(recent_data['override_rate'], inverse=True)

        # Overall improvement score
        improvement_score = (
            auto_execute_trend['score'] * 0.4 +
            override_trend['score'] * 0.4 +
            self.calculate_kpi_improvement_score(recent_data) * 0.2
        )

        return {
            'improvement_score': improvement_score,
            'auto_execute_trend': auto_execute_trend['direction'],
            'override_trend': override_trend['direction'],
            'confidence': 'HIGH' if len(recent_data) >= 100 else 'LOW'
        }
```

**Example Learning Evolution** (Over 12 Weeks):

```
Week 1: Auto-execute rate: 45%, Override rate: 35%
   → Agents conservative, humans override frequently

Week 4: Auto-execute rate: 52%, Override rate: 28%
   → Agents learning from overrides, improving

Week 8: Auto-execute rate: 61%, Override rate: 22%
   → Agents adapting to planner preferences

Week 12: Auto-execute rate: 72%, Override rate: 15%
   → Agents well-calibrated, humans trust more

Target: Auto-execute rate: 85%, Override rate: <10%
```


---

## 8. Order Promising and Tracking: Continuous ATP/CTP

### 8.1 Overview

**Purpose**: Extend continuous planning principles to order promising, enabling real-time Available-to-Promise (ATP) and Capable-to-Promise (CTP) calculations with intelligent batching and priority-based allocation.

**Key Innovation**: Orders are promised continuously as they arrive, but customer notifications are batched to allow higher-priority orders to pre-empt lower-priority promises without breaking customer commitments.

### 8.2 Order Promising Paradigms

**Two Complementary Approaches**:

| Approach | Promising Timing | Notification Timing | Use Case |
|----------|------------------|---------------------|----------|
| **Batch Promising** | Batch orders, promise together | Immediate after batch | High-volume B2C, fairness priority |
| **Continuous Promising with Batched Notification** | Promise as orders arrive | Batched notifications | B2B, priority-based allocation |

### 8.3 Batch Promising (Traditional with Continuous Improvements)

**Problem with Pure Batching**:
```
Scenario: Batch every 15 minutes
10:00 AM: Low-priority order A arrives (100 units)
10:05 AM: High-priority order B arrives (100 units)
10:15 AM: Batch runs, only 150 units ATP available

Result without priority:
❌ Order A gets 100 units (first-come-first-served)
❌ Order B gets 50 units (VIP customer short-shipped)
```

**Solution: Priority-Aware Batching**

```python
class BatchOrderPromisingAgent:
    """
    Batch order promising agent with priority-based allocation.
    """
    def __init__(self):
        self.batching_frequency_minutes = 15  # Configurable parameter
        self.batch_queue = PriorityQueue()  # Orders sorted by priority
        self.notification_frequency_minutes = 15  # Same as batching

    async def enqueue_order(self, order):
        """
        Add order to batch queue with priority.
        """
        priority_score = self.calculate_priority_score(order)

        await self.batch_queue.enqueue({
            'order': order,
            'priority': priority_score,
            'enqueued_at': datetime.utcnow(),
            'customer_tier': order.customer.tier,  # 'VIP', 'GOLD', 'STANDARD'
            'order_value': order.total_value,
            'requested_date': order.requested_delivery_date
        })

    def calculate_priority_score(self, order):
        """
        Calculate order priority score (0-100, higher = more important).

        Factors:
        - Customer tier: VIP (40), GOLD (20), STANDARD (0)
        - Order value: $10K+ (20), $5K-10K (10), <$5K (0)
        - Urgency: <7 days (20), 7-14 days (10), >14 days (0)
        - Strategic: Key account (20), Normal (0)
        """
        score = 0

        # Customer tier
        tier_scores = {'VIP': 40, 'GOLD': 20, 'STANDARD': 0}
        score += tier_scores.get(order.customer.tier, 0)

        # Order value
        if order.total_value >= 10000:
            score += 20
        elif order.total_value >= 5000:
            score += 10

        # Urgency
        days_until_due = (order.requested_delivery_date - datetime.utcnow().date()).days
        if days_until_due < 7:
            score += 20
        elif days_until_due < 14:
            score += 10

        # Strategic account
        if order.customer.is_strategic_account:
            score += 20

        return score

    @scheduled_task(cron=f'*/{batching_frequency_minutes} * * * *')
    async def process_batch(self):
        """
        Process batch of orders with priority-based ATP allocation.
        """
        # 1. Collect all orders in current batch window
        batch_orders = await self.batch_queue.dequeue_batch(
            max_age_minutes=self.batching_frequency_minutes
        )

        if len(batch_orders) == 0:
            return  # No orders to process

        # 2. Sort by priority (highest first)
        batch_orders.sort(key=lambda x: x['priority'], reverse=True)

        # 3. Load current ATP for all requested products/sites
        atp_snapshot = await self.load_atp_snapshot(batch_orders)

        # 4. Allocate ATP in priority order
        promises = []
        for order_item in batch_orders:
            order = order_item['order']

            promise = await self.promise_order(order, atp_snapshot)
            promises.append(promise)

            # Consume ATP for next order in batch
            if promise['promised']:
                atp_snapshot = self.consume_atp(atp_snapshot, promise)

        # 5. Commit all promises atomically (Git-like)
        commit_id = await self.version_control.commit_incremental(
            branch='main',
            author='order-promising-agent',
            message=f'Batch promising: {len(promises)} orders',
            changes={
                'promises': promises,
                'atp_consumed': self.calculate_atp_consumed(promises)
            }
        )

        # 6. Notify customers immediately (batch notification)
        await self.notify_customers_batch(promises)

        # 7. Log metrics
        await self.log_batch_metrics(batch_orders, promises)

        logger.info(f'Batch promising complete: {len(promises)} orders, commit {commit_id}')

    async def promise_order(self, order, atp_snapshot):
        """
        Promise a single order against ATP snapshot.
        """
        promise = {
            'order_id': order.id,
            'customer_id': order.customer_id,
            'requested_date': order.requested_delivery_date,
            'promised': False,
            'promised_date': None,
            'promised_qty': {},
            'partial': False,
            'reason': None
        }

        # Check ATP for each line item
        all_lines_promised = True
        for line in order.line_items:
            product_id = line.product_id
            site_id = line.preferred_site_id
            requested_qty = line.quantity

            # Get ATP from snapshot
            atp_qty = atp_snapshot.get((product_id, site_id, order.requested_delivery_date), 0)

            if atp_qty >= requested_qty:
                # Full promise
                promise['promised_qty'][line.id] = requested_qty
            elif atp_qty > 0:
                # Partial promise
                promise['promised_qty'][line.id] = atp_qty
                promise['partial'] = True
                all_lines_promised = False
            else:
                # No ATP
                promise['promised_qty'][line.id] = 0
                all_lines_promised = False

        if all_lines_promised:
            promise['promised'] = True
            promise['promised_date'] = order.requested_delivery_date
        elif promise['partial']:
            promise['promised'] = True  # Partial promise
            promise['promised_date'] = order.requested_delivery_date
            promise['reason'] = 'Partial availability'
        else:
            promise['promised'] = False
            promise['reason'] = 'No ATP available on requested date'

            # Offer alternative date (CTP)
            alternative_date = await self.calculate_ctp(order, atp_snapshot)
            if alternative_date:
                promise['alternative_date'] = alternative_date
                promise['reason'] += f', available on {alternative_date}'

        return promise
```

**Batch Promising Configuration**:

```python
BATCH_PROMISING_CONFIG = {
    'batching_frequency_minutes': 15,  # Promise every 15 minutes
    'notification_frequency_minutes': 15,  # Notify immediately after batch
    'max_batch_size': 1000,  # Process up to 1000 orders per batch
    'priority_override_enabled': True,  # Higher priority can override lower
    'partial_promise_allowed': True,  # Allow partial fulfillment
    'ctp_calculation_enabled': True,  # Calculate alternative dates
}
```

### 8.4 Continuous Promising with Batched Notification (Recommended)

**Advantage**: Preserve ATP in real-time for high-priority orders without breaking prior commitments to customers.

**How It Works**:

```
10:00 AM: Order A arrives (priority 20, 100 units)
    → Promise immediately: ATP consumed, promise stored (not yet notified)

10:05 AM: Order B arrives (priority 80, 100 units)
    → Check ATP: 50 units available
    → Option 1: Promise 50 units to Order B (partial)
    → Option 2: Revoke Order A's promise (not yet notified), give 100 to Order B
    → Decision: Choose Option 2 (priority override enabled)
    → Store promise for Order B, revoke Order A's promise

10:15 AM: Notification batch runs
    → Notify Order A: "50 units available on requested date, 50 units on alternative date"
    → Notify Order B: "100 units confirmed on requested date"
```

**Implementation**:

```python
class ContinuousOrderPromisingAgent:
    """
    Continuous order promising agent with batched notifications.
    Promises are made immediately but notifications are batched.
    """
    def __init__(self):
        self.promising_mode = 'CONTINUOUS'  # Promise on arrival
        self.notification_frequency_minutes = 60  # Notify every hour
        self.priority_override_window_minutes = 30  # Can revoke promises within 30 min
        self.pending_notifications = []  # Promises awaiting notification

    async def handle_new_order_event(self, order_event):
        """
        Handle new customer order event - promise immediately.
        """
        order = order_event.payload['order']

        # 1. Calculate order priority
        priority = self.calculate_priority_score(order)

        # 2. Load current ATP (real-time)
        atp_snapshot = await self.load_real_time_atp(order)

        # 3. Attempt to promise order
        promise = await self.promise_order_realtime(order, atp_snapshot, priority)

        # 4. Check if higher priority than any pending (not yet notified) promises
        if not promise['promised'] and self.priority_override_enabled:
            revoked_promises = await self.revoke_lower_priority_promises(
                order, priority, self.priority_override_window_minutes
            )

            if len(revoked_promises) > 0:
                # Retry promise with reclaimed ATP
                atp_snapshot = await self.load_real_time_atp(order)
                promise = await self.promise_order_realtime(order, atp_snapshot, priority)

                # Log revocations
                for revoked in revoked_promises:
                    await self.log_promise_revocation(revoked, order.id, priority)

        # 5. Store promise (commit to version control)
        promise_commit_id = await self.version_control.commit_incremental(
            branch='main',
            author='order-promising-agent',
            message=f'Continuous promise: Order {order.id}',
            changes={'promise': promise}
        )

        # 6. Add to pending notification queue (batched)
        await self.pending_notifications.append({
            'order_id': order.id,
            'customer_id': order.customer_id,
            'promise': promise,
            'promised_at': datetime.utcnow(),
            'notification_due': datetime.utcnow() + timedelta(minutes=self.notification_frequency_minutes),
            'commit_id': promise_commit_id
        })

        # 7. Trigger immediate notification if VIP customer (bypass batch)
        if order.customer.tier == 'VIP':
            await self.notify_customer_immediately(order.customer_id, promise)

        logger.info(f'Order {order.id} promised (priority {priority}), notification pending')

    async def revoke_lower_priority_promises(self, new_order, new_priority, window_minutes):
        """
        Revoke lower-priority promises that have not yet been notified.
        """
        revoked = []

        # Find promises within revocation window and lower priority
        cutoff_time = datetime.utcnow() - timedelta(minutes=window_minutes)

        pending_revocable = [
            p for p in self.pending_notifications
            if p['promised_at'] >= cutoff_time and
               self.calculate_priority_score_from_order(p['order_id']) < new_priority
        ]

        # Calculate how much ATP we need
        required_atp = sum([line.quantity for line in new_order.line_items])

        # Revoke promises until we have enough ATP
        for pending in sorted(pending_revocable, key=lambda x: x['priority']):
            if required_atp <= 0:
                break

            # Revoke promise
            revoked_atp = sum(pending['promise']['promised_qty'].values())

            await self.version_control.revert_commit(pending['commit_id'])
            self.pending_notifications.remove(pending)

            revoked.append({
                'order_id': pending['order_id'],
                'customer_id': pending['customer_id'],
                'atp_reclaimed': revoked_atp,
                'reason': 'Higher priority order received'
            })

            required_atp -= revoked_atp

        return revoked

    @scheduled_task(cron=f'*/{notification_frequency_minutes} * * * *')
    async def send_batched_notifications(self):
        """
        Send batched notifications to customers for all pending promises.
        """
        # 1. Get all notifications due
        now = datetime.utcnow()
        due_notifications = [
            n for n in self.pending_notifications
            if n['notification_due'] <= now
        ]

        if len(due_notifications) == 0:
            return  # No notifications due

        # 2. Group by customer (consolidate multiple orders)
        customer_notifications = {}
        for notif in due_notifications:
            customer_id = notif['customer_id']
            if customer_id not in customer_notifications:
                customer_notifications[customer_id] = []
            customer_notifications[customer_id].append(notif)

        # 3. Send consolidated notification to each customer
        for customer_id, notifications in customer_notifications.items():
            await self.send_customer_notification(customer_id, notifications)

        # 4. Remove from pending queue
        for notif in due_notifications:
            self.pending_notifications.remove(notif)

        # 5. Log metrics
        await self.log_notification_batch_metrics(due_notifications)

        logger.info(f'Sent {len(due_notifications)} notifications to {len(customer_notifications)} customers')

    async def send_customer_notification(self, customer_id, notifications):
        """
        Send consolidated notification to customer for all their promises.
        """
        customer = await self.db.get_customer(customer_id)

        # Build notification message
        message = {
            'customer_id': customer_id,
            'notification_type': 'ORDER_PROMISE',
            'timestamp': datetime.utcnow(),
            'orders': []
        }

        for notif in notifications:
            order_data = {
                'order_id': notif['order_id'],
                'promised': notif['promise']['promised'],
                'promised_date': notif['promise']['promised_date'],
                'partial': notif['promise']['partial'],
                'line_items': []
            }

            for line_id, qty in notif['promise']['promised_qty'].items():
                line = await self.db.get_order_line_item(line_id)
                order_data['line_items'].append({
                    'product_id': line.product_id,
                    'product_name': line.product.description,
                    'requested_qty': line.quantity,
                    'promised_qty': qty,
                    'unit': line.unit_of_measure
                })

            if 'alternative_date' in notif['promise']:
                order_data['alternative_date'] = notif['promise']['alternative_date']

            message['orders'].append(order_data)

        # Send via preferred channel (email, EDI, API webhook)
        if customer.preferred_notification_channel == 'EMAIL':
            await self.send_email_notification(customer.email, message)
        elif customer.preferred_notification_channel == 'EDI':
            await self.send_edi_notification(customer.edi_endpoint, message)
        elif customer.preferred_notification_channel == 'API':
            await self.send_webhook_notification(customer.webhook_url, message)

        # Also send to portal (always available)
        await self.send_portal_notification(customer_id, message)
```

**Continuous Promising Configuration**:

```python
CONTINUOUS_PROMISING_CONFIG = {
    'promising_mode': 'CONTINUOUS',  # Promise on arrival
    'notification_frequency_minutes': 60,  # Notify every hour
    'priority_override_enabled': True,  # Can revoke lower-priority promises
    'priority_override_window_minutes': 30,  # Only revoke within 30 min
    'vip_immediate_notification': True,  # VIP customers notified immediately
    'partial_promise_allowed': True,
    'ctp_calculation_enabled': True,
    'notification_consolidation': True,  # Consolidate multiple orders per customer
}
```

### 8.5 Configurable Parameters

**System-Wide Configuration**:

```python
class OrderPromisingConfig(Base):
    """
    Configurable parameters for order promising system.
    """
    __tablename__ = "order_promising_config"

    id = Column(Integer, primary_key=True)
    company_id = Column(String(100), ForeignKey("company.id"))

    # Promising Strategy
    promising_mode = Column(String(50), default='CONTINUOUS')  # 'BATCH' or 'CONTINUOUS'
    batching_frequency_minutes = Column(Integer, default=15)  # For BATCH mode
    notification_frequency_minutes = Column(Integer, default=60)  # For CONTINUOUS mode

    # Priority Override
    priority_override_enabled = Column(Boolean, default=True)
    priority_override_window_minutes = Column(Integer, default=30)

    # ATP/CTP Calculation
    atp_fence_days = Column(Integer, default=7)  # Frozen period, no ATP consumption
    ctp_horizon_weeks = Column(Integer, default=13)  # How far to search for alternative dates
    ctp_capacity_check_enabled = Column(Boolean, default=True)

    # Partial Fulfillment
    partial_promise_allowed = Column(Boolean, default=True)
    minimum_partial_percentage = Column(Float, default=0.5)  # Min 50% to promise

    # Customer Preferences
    vip_immediate_notification = Column(Boolean, default=True)
    notification_consolidation = Column(Boolean, default=True)

    # Performance
    max_orders_per_batch = Column(Integer, default=1000)
    max_concurrent_promises = Column(Integer, default=100)

    # Audit
    log_all_revocations = Column(Boolean, default=True)
    log_all_alternatives = Column(Boolean, default=False)  # CTP alternatives

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### 8.6 Priority-Based Allocation Logic

**Priority Calculation Framework**:

```python
class OrderPriorityCalculator:
    """
    Calculate order priority score for ATP allocation.
    """
    def __init__(self, config):
        self.config = config
        self.weights = {
            'customer_tier': 0.40,  # 40% weight
            'order_value': 0.20,    # 20% weight
            'urgency': 0.20,        # 20% weight
            'strategic': 0.20       # 20% weight
        }

    def calculate_priority(self, order):
        """
        Calculate priority score (0-100).
        """
        scores = {
            'customer_tier': self.score_customer_tier(order.customer),
            'order_value': self.score_order_value(order.total_value),
            'urgency': self.score_urgency(order.requested_delivery_date),
            'strategic': self.score_strategic(order.customer)
        }

        # Weighted sum
        priority = sum([
            scores[factor] * self.weights[factor] * 100
            for factor in scores
        ])

        return min(priority, 100)  # Cap at 100

    def score_customer_tier(self, customer):
        """
        Score based on customer tier (0.0 to 1.0).
        """
        tier_scores = {
            'VIP': 1.0,
            'GOLD': 0.7,
            'SILVER': 0.4,
            'STANDARD': 0.0
        }
        return tier_scores.get(customer.tier, 0.0)

    def score_order_value(self, total_value):
        """
        Score based on order value (0.0 to 1.0).
        """
        if total_value >= 50000:
            return 1.0
        elif total_value >= 10000:
            return 0.7
        elif total_value >= 5000:
            return 0.4
        else:
            return 0.0

    def score_urgency(self, requested_date):
        """
        Score based on urgency (0.0 to 1.0).
        """
        days_until_due = (requested_date - datetime.utcnow().date()).days

        if days_until_due < 3:
            return 1.0  # Critical urgency
        elif days_until_due < 7:
            return 0.7  # High urgency
        elif days_until_due < 14:
            return 0.4  # Medium urgency
        else:
            return 0.0  # Low urgency

    def score_strategic(self, customer):
        """
        Score based on strategic importance (0.0 to 1.0).
        """
        score = 0.0

        if customer.is_strategic_account:
            score += 0.5

        if customer.has_contractual_sla:
            score += 0.3

        if customer.annual_revenue >= 1000000:
            score += 0.2

        return min(score, 1.0)
```

### 8.7 ATP/CTP Calculation with MPS/MRP Integration

**Real-Time ATP Calculation**:

```python
class ATPCalculator:
    """
    Calculate Available-to-Promise in real-time from MPS plan.
    """
    async def calculate_atp(self, product_id, site_id, date_from, date_to):
        """
        Calculate ATP for product/site across date range.

        ATP = On-Hand + Planned Receipts - Committed Orders - Safety Stock
        """
        # 1. Get on-hand inventory
        on_hand = await self.db.get_inventory_level(product_id, site_id)

        # 2. Get planned receipts from MPS (production) and MRP (purchases/transfers)
        planned_receipts = await self.get_planned_receipts(
            product_id, site_id, date_from, date_to
        )

        # 3. Get committed orders (already promised)
        committed = await self.get_committed_orders(
            product_id, site_id, date_from, date_to
        )

        # 4. Get safety stock target
        safety_stock = await self.get_safety_stock(product_id, site_id)

        # 5. Calculate ATP by date bucket
        atp_by_date = {}
        cumulative_atp = on_hand - safety_stock

        current_date = date_from
        while current_date <= date_to:
            # Add planned receipts for this date
            receipts = planned_receipts.get(current_date, 0)
            cumulative_atp += receipts

            # Subtract committed orders for this date
            commits = committed.get(current_date, 0)
            cumulative_atp -= commits

            # ATP cannot be negative (capped at 0)
            atp_by_date[current_date] = max(cumulative_atp, 0)

            current_date += timedelta(days=1)

        return atp_by_date

    async def get_planned_receipts(self, product_id, site_id, date_from, date_to):
        """
        Get planned receipts from MPS (production) and MRP (purchases/transfers).
        """
        receipts = {}

        # Production orders from MPS
        mps_items = await self.db.query(MPSPlanItem).filter(
            MPSPlanItem.product_id == product_id,
            MPSPlanItem.site_id == site_id,
            MPSPlanItem.period_start_date >= date_from,
            MPSPlanItem.period_start_date <= date_to
        ).all()

        for mps in mps_items:
            receipts[mps.period_start_date] = receipts.get(mps.period_start_date, 0) + mps.planned_production_qty

        # Purchase orders from MRP
        purchase_orders = await self.db.query(PurchaseOrderLineItem).filter(
            PurchaseOrderLineItem.product_id == product_id,
            PurchaseOrderLineItem.delivery_site_id == site_id,
            PurchaseOrderLineItem.expected_delivery_date >= date_from,
            PurchaseOrderLineItem.expected_delivery_date <= date_to,
            PurchaseOrderLineItem.status.in_(['CONFIRMED', 'IN_TRANSIT'])
        ).all()

        for po in purchase_orders:
            receipts[po.expected_delivery_date] = receipts.get(po.expected_delivery_date, 0) + po.quantity

        # Transfer orders from MRP
        transfer_orders = await self.db.query(TransferOrderLineItem).filter(
            TransferOrderLineItem.product_id == product_id,
            TransferOrderLineItem.destination_site_id == site_id,
            TransferOrderLineItem.expected_delivery_date >= date_from,
            TransferOrderLineItem.expected_delivery_date <= date_to,
            TransferOrderLineItem.status.in_(['CONFIRMED', 'IN_TRANSIT'])
        ).all()

        for to in transfer_orders:
            receipts[to.expected_delivery_date] = receipts.get(to.expected_delivery_date, 0) + to.quantity

        return receipts
```

**Capable-to-Promise (CTP) with Capacity Check**:

```python
class CTPCalculator:
    """
    Calculate Capable-to-Promise with capacity constraints.
    """
    async def calculate_ctp(self, order, atp_snapshot):
        """
        Calculate alternative delivery date if ATP insufficient.

        CTP considers:
        1. Future ATP (beyond requested date)
        2. Capacity availability for additional production
        3. Supplier lead times for additional purchases
        """
        alternatives = []

        for line in order.line_items:
            product_id = line.product_id
            site_id = line.preferred_site_id
            requested_qty = line.quantity
            requested_date = order.requested_delivery_date

            # 1. Check future ATP buckets
            atp_buckets = await self.atp_calculator.calculate_atp(
                product_id, site_id,
                requested_date + timedelta(days=1),
                requested_date + timedelta(days=90)  # 90-day horizon
            )

            # Find first date with sufficient ATP
            for date, atp_qty in sorted(atp_buckets.items()):
                if atp_qty >= requested_qty:
                    alternatives.append({
                        'line_id': line.id,
                        'alternative_date': date,
                        'source': 'ATP',
                        'quantity': requested_qty,
                        'confidence': 1.0  # High confidence (already in plan)
                    })
                    break

            # 2. If no ATP, check if we can produce more
            if len([a for a in alternatives if a['line_id'] == line.id]) == 0:
                production_alternative = await self.check_production_capacity(
                    product_id, site_id, requested_qty, requested_date
                )

                if production_alternative:
                    alternatives.append({
                        'line_id': line.id,
                        'alternative_date': production_alternative['date'],
                        'source': 'PRODUCTION',
                        'quantity': requested_qty,
                        'confidence': production_alternative['confidence']  # Based on capacity availability
                    })

            # 3. If no production capacity, check if we can purchase
            if len([a for a in alternatives if a['line_id'] == line.id]) == 0:
                purchase_alternative = await self.check_purchase_option(
                    product_id, site_id, requested_qty, requested_date
                )

                if purchase_alternative:
                    alternatives.append({
                        'line_id': line.id,
                        'alternative_date': purchase_alternative['date'],
                        'source': 'PURCHASE',
                        'quantity': requested_qty,
                        'confidence': purchase_alternative['confidence']  # Based on supplier reliability
                    })

        # Consolidate alternatives (latest date across all lines)
        if len(alternatives) == len(order.line_items):
            consolidated_date = max([a['alternative_date'] for a in alternatives])
            return {
                'alternative_date': consolidated_date,
                'line_alternatives': alternatives,
                'feasible': True
            }
        else:
            return {
                'feasible': False,
                'reason': 'No viable alternative found within horizon'
            }

    async def check_production_capacity(self, product_id, site_id, qty, requested_date):
        """
        Check if additional production capacity available.
        """
        # 1. Get production process for product
        production_process = await self.db.get_production_process(product_id, site_id)

        if not production_process:
            return None  # Cannot produce at this site

        # 2. Get capacity plan for next 90 days
        capacity_plan = await self.db.query(CapacityPlan).filter(
            CapacityPlan.resource_id.in_(production_process.required_resources),
            CapacityPlan.site_id == site_id,
            CapacityPlan.period_start_date >= requested_date,
            CapacityPlan.period_start_date <= requested_date + timedelta(days=90)
        ).all()

        # 3. Find first date with available capacity
        for cap_period in sorted(capacity_plan, key=lambda x: x.period_start_date):
            available_capacity = cap_period.available_capacity - cap_period.committed_capacity

            # Convert capacity to product units
            required_capacity = qty * production_process.capacity_per_unit

            if available_capacity >= required_capacity:
                # Check lead time
                earliest_date = requested_date + timedelta(days=production_process.lead_time_days)
                production_date = max(cap_period.period_start_date, earliest_date)

                return {
                    'date': production_date,
                    'confidence': 0.8,  # High confidence if capacity available
                    'resource': cap_period.resource_id
                }

        return None  # No capacity available
```

### 8.8 Order Tracking and Status Updates

**Real-Time Order Tracking**:

```python
class OrderTrackingAgent:
    """
    Track order status and send proactive updates to customers.
    """
    async def track_order_status(self, order_id):
        """
        Calculate real-time order status based on supply plan.
        """
        order = await self.db.get_order(order_id)

        # Get all promises for this order
        promises = await self.db.get_order_promises(order_id)

        # Track each line item
        line_statuses = []
        for line in order.line_items:
            status = await self.calculate_line_status(line, promises)
            line_statuses.append(status)

        # Overall order status
        if all([s['status'] == 'ON_TRACK' for s in line_statuses]):
            overall_status = 'ON_TRACK'
        elif any([s['status'] == 'AT_RISK' for s in line_statuses]):
            overall_status = 'AT_RISK'
        elif any([s['status'] == 'DELAYED' for s in line_statuses]):
            overall_status = 'DELAYED'
        else:
            overall_status = 'PENDING'

        return {
            'order_id': order_id,
            'overall_status': overall_status,
            'promised_date': promises[0].promised_date if promises else None,
            'estimated_ship_date': self.calculate_estimated_ship_date(line_statuses),
            'line_items': line_statuses
        }

    async def calculate_line_status(self, line, promises):
        """
        Calculate status for a single line item.
        """
        # Find promise for this line
        promise_qty = 0
        promised_date = None
        for promise in promises:
            if line.id in promise.promised_qty:
                promise_qty = promise.promised_qty[line.id]
                promised_date = promise.promised_date
                break

        # Check if MPS/MRP plan still supports promise
        if promised_date:
            # Get planned receipts for this line
            planned_receipts = await self.get_planned_receipts_for_line(
                line.product_id, line.preferred_site_id, promised_date
            )

            if planned_receipts >= promise_qty:
                status = 'ON_TRACK'
                risk_level = 'LOW'
            elif planned_receipts >= promise_qty * 0.8:
                status = 'AT_RISK'
                risk_level = 'MEDIUM'
            else:
                status = 'DELAYED'
                risk_level = 'HIGH'
        else:
            status = 'PENDING'
            risk_level = 'UNKNOWN'

        return {
            'line_id': line.id,
            'product_id': line.product_id,
            'promised_qty': promise_qty,
            'promised_date': promised_date,
            'status': status,
            'risk_level': risk_level
        }

    @scheduled_task(cron='0 */4 * * *')  # Every 4 hours
    async def send_proactive_order_updates(self):
        """
        Proactively notify customers of order status changes.
        """
        # Get all active orders
        active_orders = await self.db.query(Order).filter(
            Order.status.in_(['CONFIRMED', 'IN_PROGRESS'])
        ).all()

        for order in active_orders:
            # Track status
            current_status = await self.track_order_status(order.id)

            # Get previous status
            previous_status = await self.db.get_last_order_status(order.id)

            # Detect changes
            if previous_status and current_status['overall_status'] != previous_status['overall_status']:
                # Status changed - notify customer
                await self.notify_customer_status_change(
                    order.customer_id,
                    order.id,
                    previous_status,
                    current_status
                )

            # Store current status
            await self.db.store_order_status(order.id, current_status)
```

### 8.9 Database Schema for Order Promising

```sql
-- Order promises (Git-like versioning)
CREATE TABLE order_promises (
    promise_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id VARCHAR(100) NOT NULL REFERENCES orders(id),
    commit_id UUID REFERENCES plan_commits(commit_id),  -- Link to plan version
    promised_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    promised_by VARCHAR(255) NOT NULL,  -- 'order-promising-agent', 'planner-john'
    notified_at TIMESTAMPTZ,  -- When customer was notified
    revoked_at TIMESTAMPTZ,  -- If promise was revoked before notification
    revoked_reason TEXT,
    promised_date DATE NOT NULL,
    promised_qty JSONB NOT NULL,  -- {line_id: qty}
    partial BOOLEAN DEFAULT FALSE,
    priority_score NUMERIC(5,2),  -- Order priority (0-100)
    alternative_date DATE,  -- CTP alternative if partial/no promise
    INDEX idx_order_id (order_id),
    INDEX idx_promised_date (promised_date),
    INDEX idx_notified (notified_at) WHERE notified_at IS NULL  -- Pending notifications
);

-- Order promise history (audit trail)
CREATE TABLE order_promise_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    promise_id UUID NOT NULL REFERENCES order_promises(promise_id),
    action VARCHAR(50) NOT NULL,  -- 'CREATED', 'REVOKED', 'NOTIFIED', 'MODIFIED'
    action_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action_by VARCHAR(255) NOT NULL,
    previous_state JSONB,
    new_state JSONB,
    reason TEXT,
    INDEX idx_promise_id_timestamp (promise_id, action_timestamp DESC)
);

-- Order tracking status
CREATE TABLE order_tracking_status (
    status_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id VARCHAR(100) NOT NULL REFERENCES orders(id),
    status_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    overall_status VARCHAR(50) NOT NULL,  -- 'ON_TRACK', 'AT_RISK', 'DELAYED', 'PENDING'
    line_statuses JSONB NOT NULL,  -- Array of line item statuses
    estimated_ship_date DATE,
    INDEX idx_order_id_timestamp (order_id, status_timestamp DESC)
);

-- Order promising configuration (per company)
CREATE TABLE order_promising_config (
    id SERIAL PRIMARY KEY,
    company_id VARCHAR(100) NOT NULL REFERENCES company(id),
    promising_mode VARCHAR(50) NOT NULL DEFAULT 'CONTINUOUS',  -- 'BATCH' or 'CONTINUOUS'
    batching_frequency_minutes INTEGER DEFAULT 15,
    notification_frequency_minutes INTEGER DEFAULT 60,
    priority_override_enabled BOOLEAN DEFAULT TRUE,
    priority_override_window_minutes INTEGER DEFAULT 30,
    atp_fence_days INTEGER DEFAULT 7,
    ctp_horizon_weeks INTEGER DEFAULT 13,
    ctp_capacity_check_enabled BOOLEAN DEFAULT TRUE,
    partial_promise_allowed BOOLEAN DEFAULT TRUE,
    minimum_partial_percentage NUMERIC(5,2) DEFAULT 0.5,
    vip_immediate_notification BOOLEAN DEFAULT TRUE,
    notification_consolidation BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(company_id)
);
```

### 8.10 Metrics and KPIs

**Order Promising Performance Metrics**:

```python
ORDER_PROMISING_METRICS = {
    'promise_rate': {
        'description': '% of orders fully promised on requested date',
        'target': 0.95,  # 95%
        'calculation': 'full_promises / total_orders'
    },
    'partial_promise_rate': {
        'description': '% of orders partially promised',
        'target': 0.03,  # <3%
        'calculation': 'partial_promises / total_orders'
    },
    'revocation_rate': {
        'description': '% of promises revoked before notification',
        'target': 0.01,  # <1%
        'calculation': 'revoked_promises / total_promises'
    },
    'promise_to_notification_time': {
        'description': 'Average time from promise to customer notification',
        'target': 30,  # 30 minutes
        'unit': 'minutes'
    },
    'ctp_success_rate': {
        'description': '% of orders where CTP found viable alternative',
        'target': 0.90,  # 90%
        'calculation': 'successful_ctp / total_ctp_attempts'
    },
    'promise_accuracy': {
        'description': '% of promises fulfilled on promised date',
        'target': 0.98,  # 98%
        'calculation': 'fulfilled_on_time / total_promises_notified'
    }
}
```

---

## 8. Database Schema Extensions

### 8.1 New Tables for Event-Driven Planning

```sql
-- Event log (all planning events)
CREATE TABLE planning_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(100) NOT NULL,  -- 'DEMAND_CHANGE', 'SUPPLY_DISRUPTION', etc.
    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_system VARCHAR(100),  -- 'SAP_ECC', 'manual', 'agent', 'sensor'
    payload JSONB NOT NULL,
    priority VARCHAR(20) NOT NULL,  -- 'P0', 'P1', 'P2', 'P3'
    processed_at TIMESTAMPTZ,
    processing_status VARCHAR(50),  -- 'pending', 'processing', 'completed', 'failed'
    assigned_agent VARCHAR(100),
    INDEX idx_event_type_timestamp (event_type, event_timestamp DESC),
    INDEX idx_processing_status (processing_status) WHERE processing_status IN ('pending', 'processing')
);

-- Agent task queue
CREATE TABLE agent_tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type VARCHAR(100) NOT NULL,  -- 'mps', 'mrp', 'capacity', 'policy', 'llm_supervisor'
    event_id UUID REFERENCES planning_events(event_id),
    priority VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    status VARCHAR(50) NOT NULL,  -- 'queued', 'assigned', 'running', 'completed', 'failed'
    task_context JSONB,  -- Agent-specific context
    result JSONB,  -- Agent output
    error_message TEXT,
    INDEX idx_agent_status (agent_type, status) WHERE status IN ('queued', 'assigned', 'running'),
    INDEX idx_priority_created (priority, created_at) WHERE status = 'queued'
);

-- Agent decisions (explainability)
CREATE TABLE agent_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type VARCHAR(100) NOT NULL,
    task_id UUID REFERENCES agent_tasks(task_id),
    commit_id UUID REFERENCES plan_commits(commit_id),
    decision_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    input_state JSONB NOT NULL,  -- Pre-decision state
    output_state JSONB NOT NULL,  -- Post-decision state
    reasoning JSONB,  -- Agent's reasoning (if available)
    confidence_score NUMERIC(5,4),  -- 0.0 to 1.0
    alternatives_considered JSONB,  -- Alternative options evaluated
    kpi_impact JSONB,  -- Estimated KPI impact
    INDEX idx_agent_timestamp (agent_type, decision_timestamp DESC)
);

-- Agent conflicts
CREATE TABLE agent_conflicts (
    conflict_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conflict_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    agent1_task_id UUID REFERENCES agent_tasks(task_id),
    agent2_task_id UUID REFERENCES agent_tasks(task_id),
    conflict_type VARCHAR(100) NOT NULL,  -- 'SKU_OVERLAP', 'RESOURCE_CONTENTION', 'POLICY_CONTRADICTION'
    conflict_details JSONB NOT NULL,
    resolution_method VARCHAR(100),  -- 'PRIORITY', 'LLM_NEGOTIATION', 'HUMAN_ESCALATION'
    resolution_result JSONB,
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(255),  -- Agent or human who resolved
    INDEX idx_unresolved (conflict_timestamp) WHERE resolved_at IS NULL
);

-- Plan variance reports
CREATE TABLE plan_variance_reports (
    report_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_date DATE NOT NULL,
    plan_commit_id UUID NOT NULL REFERENCES plan_commits(commit_id),
    actual_data_source VARCHAR(100) NOT NULL,  -- 'SAP_ECC', 'manual_entry'
    variance_summary JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_by INTEGER REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    INDEX idx_report_date (report_date DESC)
);

-- Agent performance metrics (for monitoring)
CREATE TABLE agent_performance_metrics (
    metric_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type VARCHAR(100) NOT NULL,
    metric_date DATE NOT NULL,
    tasks_completed INTEGER NOT NULL DEFAULT 0,
    tasks_failed INTEGER NOT NULL DEFAULT 0,
    avg_execution_time_sec NUMERIC(10,2),
    avg_confidence_score NUMERIC(5,4),
    auto_merge_rate NUMERIC(5,4),  -- % of scenarios merged without human review
    exception_rate NUMERIC(5,4),  -- % of scenarios escalated to human
    kpi_improvement JSONB,  -- Average KPI improvement vs. baseline
    INDEX idx_agent_date (agent_type, metric_date DESC)
);
```

---

## 9. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-4)

**Goal**: Establish event bus and Git-like versioning

**Deliverables**:
1. Set up Apache Kafka or AWS EventBridge for event bus
2. Implement `plan_commits`, `plan_branches`, `plan_diffs` tables
3. Build version control service with commit/branch/merge APIs
4. Create daily full snapshot + incremental CDC mechanism
5. Implement basic event generation from SAP import

**Success Criteria**:
- ✅ Can commit full snapshot nightly
- ✅ Can commit incremental snapshot hourly
- ✅ Can create/merge branches
- ✅ Can compute plan diffs between commits

### Phase 2: Agent Orchestration (Weeks 5-8)

**Goal**: Build event-driven agent framework

**Deliverables**:
1. Implement `planning_events`, `agent_tasks`, `agent_decisions` tables
2. Build Agent Orchestrator with priority queue
3. Convert MPS agent to event-driven model
4. Implement agent conflict detection and resolution
5. Add agent performance metrics dashboard

**Success Criteria**:
- ✅ MPS agent can be triggered by demand change events
- ✅ Agent can commit incremental plan changes
- ✅ Conflicts detected and escalated properly
- ✅ Agent execution metrics tracked

### Phase 3: Policy Agents (Weeks 9-12)

**Goal**: Implement policy-setting agents

**Deliverables**:
1. Build Inventory Policy Agent (safety stock optimization)
2. Build Sourcing Policy Agent (make-vs-buy, vendor selection)
3. Build Capacity Policy Agent (shift patterns, overtime rules)
4. Implement policy change event cascade to execution agents
5. Add policy effectiveness metrics

**Success Criteria**:
- ✅ Policy agents can recalculate targets based on events
- ✅ Policy changes trigger downstream MPS/MRP replanning
- ✅ Policy effectiveness tracked (before/after KPIs)

### Phase 4: Plan vs. Actual (Weeks 13-16)

**Goal**: Automated plan vs. actual comparison

**Deliverables**:
1. Build SAP CDC extraction service
2. Implement plan vs. actual variance calculation
3. Create variance report generator
4. Add LLM-generated root cause analysis
5. Build variance dashboard for planners

**Success Criteria**:
- ✅ Nightly plan vs. actual comparison runs automatically
- ✅ Variance reports generated with KPI deltas
- ✅ LLM provides root cause explanations
- ✅ Planners receive daily variance summaries

### Phase 5: LLM-First UI (Weeks 17-20)

**Goal**: Conversational planning interface

**Deliverables**:
1. Build chat interface (React + GPT-4/Claude)
2. Implement LLM tool calling for planning queries
3. Add agent decision explanation endpoint
4. Create point-and-click deep-dive modals
5. Implement plan approval workflow

**Success Criteria**:
- ✅ Planners can query exceptions via natural language
- ✅ LLM can retrieve and summarize planning data
- ✅ Agent decisions explainable through chat
- ✅ Human approval workflow integrated with Git branches

### Phase 6: Multi-Layer Coordination (Weeks 21-24)

**Goal**: Full agent hierarchy with cascading triggers

**Deliverables**:
1. Implement agent dependency graph
2. Build topological execution sequencing
3. Add LLM Supervisor for exception handling
4. Implement Global Planner for network optimization
5. Add agent performance benchmarking

**Success Criteria**:
- ✅ Policy agents trigger execution agents correctly
- ✅ Agent conflicts resolved automatically (>80% auto-merge)
- ✅ LLM Supervisor handles exceptions effectively
- ✅ End-to-end event → agent → plan → publish flow works

---

## 10. Performance Analysis

### 10.1 Scalability Estimates

**System Capacity**:

| Metric | Target | Notes |
|--------|--------|-------|
| **Events/day** | 100,000 | Peak: 10 events/sec |
| **Agent tasks/day** | 50,000 | 50% of events trigger agents |
| **Incremental commits/day** | 200 | Hourly + agent commits |
| **Full commits/day** | 1 | Nightly baseline |
| **Plan diff queries/day** | 1,000 | Planner inspections |
| **LLM queries/day** | 2,000 | Exception handling + chat |

**Storage Requirements** (1 year):

| Data Type | Daily | Monthly | Yearly |
|-----------|-------|---------|--------|
| **Full snapshots** | 50 MB (compressed) | 1.5 GB | 18 GB |
| **Incremental snapshots** | 10 MB | 300 MB | 3.6 GB |
| **Events log** | 100 MB | 3 GB | 36 GB |
| **Agent decisions** | 50 MB | 1.5 GB | 18 GB |
| **Plan diffs** | 20 MB | 600 MB | 7.2 GB |
| **Total** | ~230 MB/day | ~6.9 GB/month | **~83 GB/year** |

**Database Performance**:

```sql
-- Expected query patterns and indexes

-- 1. Get latest plan (100-1000 QPS)
SELECT * FROM plan_commits WHERE branch_name = 'main' ORDER BY commit_timestamp DESC LIMIT 1;
-- Index: idx_branch_timestamp

-- 2. Get pending agent tasks (10-100 QPS)
SELECT * FROM agent_tasks WHERE status = 'queued' ORDER BY priority, created_at LIMIT 100;
-- Index: idx_priority_created (partial index)

-- 3. Get plan diff (10-50 QPS)
SELECT * FROM plan_diffs WHERE from_commit_id = ? AND to_commit_id = ?;
-- Index: idx_commits

-- 4. Get unresolved conflicts (1-10 QPS)
SELECT * FROM agent_conflicts WHERE resolved_at IS NULL ORDER BY conflict_timestamp;
-- Index: idx_unresolved (partial index)
```

### 10.2 Latency Targets

**End-to-End Latency** (Event → Agent → Plan → Publish):

| Priority | Target | Actual (Estimated) |
|----------|--------|---------------------|
| **P0 (Critical)** | < 1 minute | ~30 seconds |
| **P1 (High)** | < 5 minutes | ~2 minutes |
| **P2 (Medium)** | < 1 hour | ~15 minutes |
| **P3 (Low)** | < 24 hours | ~2 hours |

**Component Latency Breakdown** (P1 event):

```
Event Generation (SAP → Kafka):        5 seconds
Event Routing (Orchestrator):          1 second
Agent Execution (MPS replan):          60 seconds
Plan Commit (Git-like):                2 seconds
Plan Diff Calculation:                 5 seconds
Conflict Detection:                    3 seconds
LLM Supervisor Review (if needed):     15 seconds
Merge to Main:                         2 seconds
Publish to SAP:                        10 seconds
────────────────────────────────────────────────
Total:                                 ~2 minutes
```

### 10.3 Cost Analysis

**Infrastructure Costs** (AWS):

| Component | Service | Monthly Cost |
|-----------|---------|--------------|
| **Event Bus** | AWS EventBridge (100K events/day) | $10 |
| **Database** | RDS PostgreSQL (db.r5.xlarge) | $350 |
| **Agent Compute** | ECS Fargate (4 vCPU, 8GB RAM, 24/7) | $120 |
| **LLM API** | OpenAI GPT-4 Turbo (2K requests/day, 10K tokens avg) | $150 |
| **Storage** | S3 (100 GB plan snapshots) | $2 |
| **Total** | | **~$632/month** |

**Cost per Agent Decision**:

- Agent compute: $120 / 50,000 decisions = **$0.0024 per decision**
- LLM API: $150 / 2,000 reviews = **$0.075 per LLM review**
- Database: $350 / 50,000 decisions = **$0.007 per decision**
- **Total**: **$0.0094 per agent decision** (or **$0.082 with LLM review**)

---

## Summary and Next Steps

### Key Innovations

1. **Event-Driven**: Agents react to changes in minutes, not days
2. **Git-Like Versioning**: Full plan history with branch/merge workflow
3. **Incremental CDC**: Efficient snapshotting reduces storage 100x
4. **LLM-First UI**: Conversational interface with deep-dive point-and-click
5. **Multi-Layer Agents**: Policy agents set rules, execution agents implement
6. **Plan vs. Actual**: Automated daily variance analysis with root cause
7. **Conformal Prediction**: Distribution-free prediction intervals with formal statistical guarantees
8. **Centralized & Decentralized Planning**: Support for both global optimization and autonomous site planning
9. **Hybrid Stochastic-Conformal**: Monte Carlo for internal analysis, conformal for customer commitments
10. **OODA Loop for Decentralized Agents**: Autonomous Observe-Orient-Decide-Act cycles for independent sites

### Decision Points

**For Discussion**:

1. **Event Bus**: Kafka (self-hosted) vs. AWS EventBridge (managed)?
2. **LLM Provider**: OpenAI GPT-4 Turbo vs. Claude 3 Opus vs. Self-hosted Llama 3?
3. **Incremental Snapshot Frequency**: Hourly vs. on-demand vs. continuous?
4. **Auto-Merge Threshold**: What % KPI impact requires human review?
5. **Agent Priority**: Confirm capacity agent has highest priority over MPS?
6. **Conformal Prediction Scope**: Which variables get conformal prediction (demand, lead time, yield, capacity)?
7. **Conformal Miscoverage Rate (α)**: Default to 0.10 (90% coverage) or 0.05 (95% coverage)?
8. **Planning Mode Default**: Centralized (traditional), decentralized (Beer Game), or hybrid?
9. **Bullwhip Mitigation**: Enable conformal demand sharing between sites in decentralized mode?
10. **Calibration Frequency**: How often to recalibrate conformal predictors (daily, weekly, monthly)?

### Recommended Next Actions

1. **Proof of Concept** (2 weeks):
   - Implement basic event bus (Kafka)
   - Create plan_commits table and Git-like commit API
   - Convert one agent (MPS) to event-driven model
   - Demo: Event → Agent → Commit → Merge flow
   - **NEW**: Implement ConformalPredictor class for demand forecasting
   - **NEW**: Test hybrid Monte Carlo + conformal approach on safety stock calculation

2. **Architecture Review** (1 week):
   - Present this document to stakeholders
   - Validate agent hierarchy and priority rules
   - Confirm LLM-first UI approach
   - Approve implementation roadmap
   - **NEW**: Decide on centralized vs. decentralized vs. hybrid planning mode
   - **NEW**: Approve conformal prediction scope (which variables get formal guarantees)

3. **Team Formation** (ongoing):
   - Backend: Event bus, agent orchestrator, version control
   - Frontend: LLM chat interface, point-and-click dashboards
   - ML/AI: Agent training, LLM integration, explainability
   - Data: SAP CDC, plan vs. actual, variance analysis
   - **NEW**: Statistical modeling: Conformal prediction calibration and validation

4. **Conformal Prediction Pilot** (3 weeks - NEW):
   - Collect 52 weeks of Plan vs. Actual data for calibration
   - Calibrate conformal predictors for demand, lead time, and yield
   - Validate empirical coverage matches theoretical guarantee (90%, 95%, 99%)
   - Implement hybrid stochastic-conformal agent for one product family
   - Measure impact on safety stock levels and service level guarantees

5. **Decentralized Planning Experiment** (4 weeks - NEW):
   - Configure Beer Game as decentralized planning testbed
   - Implement OODA loop for autonomous site agents
   - Test bullwhip effect mitigation using conformal demand sharing
   - Compare centralized vs. decentralized vs. hybrid performance
   - Measure bullwhip ratio reduction (target: 5-10x → 1.5-2.5x)

---

**Document Status**: Ready for Review
**Next Review**: Architecture review meeting
**Questions**: Contact AI Architecture Team
