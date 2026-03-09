# Demand Planning & Forecasting

## Comprehensive Reference Guide for Supply Chain Demand Management

---

## 1. Definitions

### Demand Planning
Demand planning is the cross-functional process of developing a consensus demand forecast that drives all downstream supply chain planning. It combines statistical forecasting, market intelligence, sales input, and promotional planning to produce a single demand signal.

### Demand Sensing
Short-term demand signal processing that uses recent data (POS, orders, shipments) to adjust the statistical forecast for the immediate horizon (1-4 weeks). Reduces forecast error by 30-40% in the short term.

### Demand Shaping
Active management of demand through pricing, promotions, product availability, and marketing to influence customer buying patterns and align demand with supply capabilities.

---

## 2. Forecasting Methods

### 2.1 Statistical (Time Series) Methods

#### Moving Average
```
Simple Moving Average: F(t+1) = (1/N) × Σ D(t-i) for i=0 to N-1

Weighted Moving Average: F(t+1) = Σ wᵢ × D(t-i), where Σwᵢ = 1
```
- **Use**: Stable demand with no trend or seasonality
- **Parameters**: N (number of periods), weights
- **Pros**: Simple, easy to understand
- **Cons**: Lags trend, equal weight to old data (SMA)

#### Exponential Smoothing

**Simple Exponential Smoothing (SES)**:
```
F(t+1) = α × D(t) + (1-α) × F(t)
```
- α = smoothing constant (0 < α < 1)
- Higher α = more weight on recent data

**Holt's Linear Trend (Double Exponential Smoothing)**:
```
Level:  L(t) = α × D(t) + (1-α) × (L(t-1) + T(t-1))
Trend:  T(t) = β × (L(t) - L(t-1)) + (1-β) × T(t-1)
Forecast: F(t+h) = L(t) + h × T(t)
```

**Holt-Winters (Triple Exponential Smoothing)**:

Additive seasonality:
```
Level:    L(t) = α × (D(t) - S(t-m)) + (1-α) × (L(t-1) + T(t-1))
Trend:    T(t) = β × (L(t) - L(t-1)) + (1-β) × T(t-1)
Season:   S(t) = γ × (D(t) - L(t)) + (1-γ) × S(t-m)
Forecast: F(t+h) = L(t) + h × T(t) + S(t+h-m)
```

Multiplicative seasonality:
```
Level:    L(t) = α × (D(t) / S(t-m)) + (1-α) × (L(t-1) + T(t-1))
Trend:    T(t) = β × (L(t) - L(t-1)) + (1-β) × T(t-1)
Season:   S(t) = γ × (D(t) / L(t)) + (1-γ) × S(t-m)
Forecast: F(t+h) = (L(t) + h × T(t)) × S(t+h-m)
```
- m = seasonal period (e.g., 12 for monthly, 52 for weekly)

#### ARIMA (Box-Jenkins)
```
ARIMA(p, d, q):
  p = autoregressive order (AR)
  d = differencing order (Integration)
  q = moving average order (MA)

SARIMA(p,d,q)(P,D,Q)m adds seasonal components
```

**Model Selection**: Use AIC/BIC criteria, ACF/PACF plots for parameter identification.

#### Croston's Method (Intermittent Demand)
```
When D(t) > 0:
    Z(t) = α × D(t) + (1-α) × Z(t-1)      # demand size
    P(t) = α × q(t) + (1-α) × P(t-1)       # inter-arrival interval
    F = Z(t) / P(t)

When D(t) = 0:
    Z(t) = Z(t-1)
    P(t) = P(t-1)
```
- **Use**: Spare parts, slow-moving items with many zero-demand periods
- **Variants**: SBA (Syntetos-Boylan Approximation) corrects Croston's upward bias

### 2.2 Causal / Regression Methods

```
D(t) = β₀ + β₁×Price + β₂×Promotion + β₃×Season + β₄×Economic_Index + ε
```

| Predictor | Type | Example |
|-----------|------|---------|
| Price | Continuous | Price elasticity |
| Promotion | Binary/Categorical | Promotion lift |
| Distribution | Continuous | # of stores carrying |
| Competitor | Binary | Competitor actions |
| Weather | Continuous | Temperature, precipitation |
| Economic | Continuous | GDP, consumer confidence |
| Events | Binary | Holidays, sports events |

### 2.3 Machine Learning Methods

| Method | Strengths | Weaknesses |
|--------|-----------|------------|
| **Random Forest** | Handles non-linearity, feature importance | Poor extrapolation |
| **Gradient Boosting (XGBoost/LightGBM)** | High accuracy, handles mixed features | Risk of overfitting |
| **LSTM/GRU** | Captures long sequences, temporal patterns | Requires large data, slow training |
| **Transformer** | Attention over full history, parallelizable | Data-hungry, complex |
| **N-BEATS** | Interpretable, state-of-art accuracy | Univariate only |
| **DeepAR** | Probabilistic, cross-series learning | Amazon-specific architecture |
| **Temporal Fusion Transformer (TFT)** | Multi-horizon, interpretable attention | Complex architecture |

### 2.4 Judgmental Methods

| Method | When to Use |
|--------|------------|
| **Sales force composite** | Bottom-up from sales team estimates |
| **Delphi method** | Expert consensus through iterative rounds |
| **Market research** | New product introductions, no history |
| **Executive opinion** | Strategic direction, market disruption |
| **Customer surveys** | B2B with large customers, contractual |

---

## 3. Probabilistic Forecasting

### 3.1 Why Probabilistic?

Traditional point forecasts give a single number (e.g., "demand = 1000 units"). Probabilistic forecasts provide a **full probability distribution**:

- P10 = 800 units (10% chance demand is below 800)
- P50 = 1000 units (median expectation)
- P90 = 1300 units (90% chance demand is below 1300)

**Benefits**:
- Enables risk-aware planning (safety stock tied to service level)
- Supports scenario planning with quantified uncertainty
- Enables economic optimization (balance service vs. cost vs. cash)
- Exposes forecast quality beyond point accuracy

### 3.2 Generating Probabilistic Forecasts

**Parametric Approach**: Assume distribution family + estimate parameters
```
Demand ~ Normal(μ=1000, σ=150)
  → P10 = 1000 - 1.28 × 150 = 808
  → P50 = 1000
  → P90 = 1000 + 1.28 × 150 = 1192
```

**Non-Parametric (Empirical) Approach**: Use historical residuals
```
1. Fit point forecast model
2. Compute residuals: e(t) = D(t) - F(t)
3. Estimate percentiles from residual distribution
4. P10(t+h) = F(t+h) + Quantile(residuals, 0.10)
5. P90(t+h) = F(t+h) + Quantile(residuals, 0.90)
```

**Quantile Regression**: Directly estimate conditional quantiles
```
Minimize: Σ ρ_τ(D(t) - F_τ(X(t)))
where ρ_τ(u) = u(τ - I(u<0))  # pinball loss
```

**Conformal Prediction**: Distribution-free prediction intervals
```
1. Split data: training + calibration
2. Fit model on training, compute conformity scores on calibration
3. Prediction interval at level (1-α): F(t+h) ± Quantile(scores, 1-α)
4. Guaranteed coverage regardless of distribution
```

### 3.3 Evaluating Probabilistic Forecasts

| Metric | Formula | Measures |
|--------|---------|----------|
| **Pinball Loss** | ρ_τ(y - q_τ) | Quantile accuracy |
| **CRPS** | ∫(F(x) - I(x≥y))² dx | Full distribution accuracy |
| **Winkler Score** | Width + penalty for misses | Prediction interval quality |
| **Calibration** | % of actuals within predicted intervals | Statistical reliability |
| **Sharpness** | Width of prediction intervals | Precision (narrower = better) |

---

## 4. Forecast Accuracy Metrics

### Point Forecast Metrics

| Metric | Formula | Properties |
|--------|---------|------------|
| **MAE** | (1/n) Σ\|Aᵢ - Fᵢ\| | Absolute error, same units as data |
| **MSE** | (1/n) Σ(Aᵢ - Fᵢ)² | Penalizes large errors |
| **RMSE** | √MSE | Same units as data, penalizes large errors |
| **MAPE** | (1/n) Σ\|Aᵢ - Fᵢ\|/Aᵢ × 100 | Percentage, undefined when Aᵢ=0 |
| **WMAPE** | Σ\|Aᵢ - Fᵢ\| / ΣAᵢ × 100 | Volume-weighted MAPE |
| **sMAPE** | (1/n) Σ 2\|Aᵢ-Fᵢ\|/(Aᵢ+Fᵢ) × 100 | Symmetric, bounded |
| **MASE** | MAE / MAE_naive | Scale-free, compares to naive baseline |
| **Tracking Signal** | ΣDFE / MAD | Detects systematic bias |

### Forecast Bias

```
Bias = Σ(Forecast - Actual) / Σ(Actual) × 100

Positive bias → systematic over-forecasting
Negative bias → systematic under-forecasting
Target: |Bias| < 5%
```

### Forecast Value Added (FVA)

FVA measures whether each step in the forecasting process improves accuracy:

```
FVA_step = Accuracy_after_step - Accuracy_before_step

Steps:
1. Statistical baseline          → WMAPE = 28%
2. + Demand sensing              → WMAPE = 22% → FVA = +6%
3. + Sales input                 → WMAPE = 20% → FVA = +2%
4. + Marketing/promotion overlay → WMAPE = 19% → FVA = +1%
5. + Executive override          → WMAPE = 21% → FVA = -2% (NEGATIVE!)
```

**Decision**: If a step has negative FVA consistently, remove it from the process.

---

## 5. Demand Planning Process

### 5.1 Monthly Demand Review Cycle

```
Week 1: Statistical Forecast Generation
    → Run forecasting models, generate baseline
    → Apply demand sensing adjustments (short horizon)
    → Identify exceptions and outliers

Week 2: Demand Analyst Review
    → Review exceptions, correct data issues
    → Apply known events (promotions, launches, phase-outs)
    → Prepare for consensus meeting

Week 3: Consensus Demand Review
    → Cross-functional meeting (Sales, Marketing, Supply Chain, Finance)
    → Review assumptions, update demand drivers
    → Agree on consensus forecast (unconstrained)
    → Document assumptions and risks (upside/downside)

Week 4: Demand Input to S&OP
    → Finalize demand plan for S&OP process
    → Provide demand scenarios (base, upside, downside)
    → Hand off to Supply Review
```

### 5.2 Demand Segmentation

Segment products for differentiated forecasting approaches:

| Segment | Volume | Variability | Method |
|---------|--------|-------------|--------|
| **A-X** | High | Low (stable) | Statistical + minor adjustment |
| **A-Y** | High | Medium | Statistical + causal + sales input |
| **A-Z** | High | High (erratic) | Collaborative + demand sensing |
| **B-X** | Medium | Low | Statistical (auto-pilot) |
| **B-Y** | Medium | Medium | Statistical + exception management |
| **B-Z** | Medium | High | Statistical + judgment |
| **C-X** | Low | Low | Statistical (auto-pilot) |
| **C-Y** | Low | Medium | Aggregate forecasting |
| **C-Z** | Low | High | Croston's or aggregate |

**ABC**: Revenue or volume classification (Pareto)
**XYZ**: Coefficient of variation classification

### 5.3 New Product Forecasting

For products with no history:

| Method | Data Required | Accuracy |
|--------|---------------|----------|
| **Analogy** | Similar product history | Moderate |
| **Structured analogy** | Panel of experts + similar products | Better |
| **Diffusion models** | Market size, adoption rate (Bass model) | Good for technology |
| **Market research** | Survey data, test markets | Good for consumer |
| **Launch curves** | Ramp-up profile from similar launches | Good for planning |

**Bass Diffusion Model**:
```
F(t) = M × (p + q × F(t-1)/M) × (1 - F(t-1)/M)

Where:
  M = market potential (total adopters)
  p = coefficient of innovation (external influence)
  q = coefficient of imitation (internal influence)
```

---

## 6. Demand Sensing

### 6.1 Signals for Short-Term Adjustment

| Signal | Latency | Horizon | Impact |
|--------|---------|---------|--------|
| **POS data** | 1-2 days | 1-2 weeks | Direct consumer demand |
| **Customer orders** | Real-time | 1-4 weeks | B2B demand |
| **Web traffic/searches** | Real-time | 1-2 weeks | Leading indicator |
| **Social media** | Real-time | 1-2 weeks | Sentiment/virality |
| **Weather** | 1-7 days | 1-2 weeks | Seasonal products |
| **Promotions (actual)** | 1-3 days | 1-2 weeks | Promotion lift actuals |
| **Competitor actions** | 1-7 days | 2-4 weeks | Market share shifts |
| **Economic indicators** | Monthly | 4-12 weeks | Macro trends |

### 6.2 Demand Sensing Process

```
1. Ingest real-time signals (POS, orders, weather, events)
2. Compute short-term forecast adjustment:
   Adjusted_F(t+1) = w₁ × Statistical_F(t+1) + w₂ × Signal_F(t+1)
3. Apply machine learning model trained on signal → actual relationships
4. Output: Revised short-horizon forecast (1-14 days)
5. Feed revised forecast to ATP/AATP and replenishment
```

---

## 7. Collaborative Planning (CPFR)

### Collaborative Planning, Forecasting, and Replenishment

```
Step 1: Strategy & Planning
    → Agree on business goals, scope, roles
    → Define exception criteria and escalation

Step 2: Demand & Supply Management
    → Share forecasts between trading partners
    → Identify exceptions (forecast > threshold divergence)
    → Resolve exceptions collaboratively

Step 3: Execution
    → Convert collaborative forecast to orders
    → Monitor performance
    → Continuous improvement

Step 4: Analysis
    → Review KPIs (forecast accuracy, fill rate, inventory turns)
    → Root cause analysis of exceptions
    → Update collaboration agreement
```

### CPFR Exception Types

| Exception | Trigger | Resolution |
|-----------|---------|------------|
| **Forecast divergence** | Buyer and seller forecasts differ > 20% | Joint review and reconciliation |
| **Order mismatch** | Orders deviate from forecast > threshold | Demand clarification |
| **Supply shortage** | Supplier capacity < committed forecast | Allocation discussion |
| **Promotion deviation** | Actual lift ≠ planned lift | Adjust replenishment |
| **New product deviation** | Launch actuals ≠ planned ramp | Revise launch curve |

---

## 8. Demand Planning in Major Platforms

### SAP IBP Demand Planning
- Statistical forecasting with 30+ models
- Machine learning integration (SAP HANA PAL)
- Consensus-based planning with workflow
- Demand sensing add-on
- What-if simulation for demand scenarios

### Kinaxis RapidResponse Demand Planning
- Concurrent planning (demand + supply simultaneously)
- Machine learning demand sensing
- Promotion management and cannibalization
- Multi-level forecasting (bottom-up/top-down)
- Real-time collaboration workbench

### o9 Solutions Demand Planning
- AI/ML-powered "digital brain"
- Enterprise knowledge graph for causal relationships
- Automated model selection and tuning
- Scenario planning with probabilistic outcomes
- External data integration (weather, economic, social)

---

## 9. Forecast Aggregation and Disaggregation

### Top-Down
```
National Forecast → Region → DC → Store
  F_store = F_national × (Historical_share_store / Σ Historical_shares)
```

### Bottom-Up
```
Store forecasts → DC → Region → National
  F_national = Σ F_store for all stores
```

### Middle-Out (Preferred)
```
Forecast at product family × region level
  ↑ Aggregate UP for S&OP
  ↓ Disaggregate DOWN for replenishment
```

**Why Middle-Out**: Balances statistical accuracy (aggregation reduces noise) with planning granularity (disaggregation enables execution).

---

## 10. Demand Planning Anti-Patterns

1. **Forecasting what you shipped, not what customers wanted**: Use unconstrained demand, not shipment history
2. **Over-fitting to noise**: Weekly SKU-level forecasts with 2 years of history and 50 features
3. **Ignoring intermittent demand**: Applying normal-distribution methods to spare parts
4. **Sandbagging**: Sales systematically under-forecasting to beat targets
5. **Hockey stick**: Optimistic monthly forecast overrides that never materialize
6. **Last-mile override**: Executive override that adds bias without FVA
7. **One model fits all**: Using same method for stable vs. erratic vs. new products
8. **Confusing accuracy with precision**: 50.3 ± 0.1 vs. 50 ± 15 — precision without accuracy
9. **Ignoring the cost of forecast error**: A 10% over-forecast and 10% under-forecast have very different cost impacts
10. **Not measuring FVA**: Every process step should prove it adds value

---

*Sources: ASCM CPIM Part 2 (MPR Module), Lokad Quantitative Supply Chain, Hyndman & Athanasopoulos "Forecasting: Principles and Practice" (3rd ed), VICS CPFR Model, Gartner Demand Planning Research*
