# Demand Planning & Forecasting — Platform Implementation

## Overview

The Autonomy platform implements a complete demand planning pipeline following AWS Supply Chain standards. This document covers the platform's actual architecture, not textbook theory (see `docs/knowledge/Demand_Planning_Forecasting_Guide.md` for academic foundations).

**Six integrated subsystems:**

1. **Baseline Forecast Generation** — LightGBM + Holt-Winters pipeline with clustering, drift detection, and probabilistic output (P10/P50/P90)
2. **Forecast Editing & Collaboration** — Versioned forecast adjustments, CPFR-style consensus, and approval workflows
3. **Promotional Planning** — Full lifecycle from draft through completion, integrated with forecasts via `supplementary_time_series`
4. **NPI (New Product Introduction)** — Demand ramp curves, supplier qualification gates, and forecast seeding for products with no history
5. **EOL (End of Life) & Phase-Out** — Demand phase-out curves, last-buy/last-manufacture dates, clearance markdown scheduling
6. **Forecast Exception Detection** — Automated anomaly detection with severity classification and exception worklists

**Data flow:**

```
Historical Orders (OutboundOrderLine)
    ↓
Forecast Pipeline (LightGBM / Holt-Winters)
    ↓ P10, P50, P90
Forecast Table
    ↓ ← Adjustments (manual, promotion, NPI, EOL, email signal)
    ↓ ← Demand Collaboration (CPFR consensus)
DemandProcessor (AWS SC Step 1)
    ↓ net demand + censored flags
InventoryTargetCalculator (Step 2)
    ↓
NetRequirementsCalculator (Step 3)
    ↓
SupplyPlan → MPS → MRP → Execution
```

---

## 1. Baseline Forecast Generation Pipeline

### Architecture

**Service**: `backend/app/services/forecast_pipeline_service.py` (995 lines)
**LightGBM**: `backend/app/services/demand_forecasting/lgbm_pipeline.py`
**API**: `backend/app/api/endpoints/forecast_pipeline.py` (671 lines)

The pipeline runs as a background task triggered via API or provisioning step 4 (`lgbm_forecast`).

### 4-Stage Pipeline

```
Stage 1: Data Loading & Quality Filtering
    → Load history from OutboundOrderLine
    → Filter by CV² threshold (default 0.49) and ADI threshold (default 1.32)
    → Intermittent demand detection (Croston's criteria)

Stage 2: Time Series Characteristics
    → Feature extraction (tsfresh or classifier-based)
    → PCA dimensionality reduction (95% variance threshold)

Stage 3: Feature Selection & Clustering
    → KMeans clustering (min_clusters=2, max_clusters=8)
    → Feature importance via LassoCV, RandomForest, or MutualInformation
    → Series grouped by demand pattern similarity

Stage 4: Forecasting
    → Primary: LightGBM quantile regression (if ≥26 observations)
    → Fallback: Holt-Winters triple exponential smoothing
    → Output: P10, P50 (median), P90 per product × site × period
    → Conformal prediction intervals available via conformal_orchestrator
```

### LightGBM Integration

**File**: `backend/app/services/demand_forecasting/lgbm_pipeline.py`

```python
LGBMForecastPipeline.run_stage4_lgbm(
    run_id, config_id, history, cluster_results, censored_flags,
    n_periods=13,        # 13-week default horizon
    time_bucket="W",     # Weekly
    retrain=False,       # Use cached model if available
)
```

- **Feature engineering**: Lag features, rolling statistics, calendar variables, event tags
- **Quantile models**: Three LightGBM models trained per cluster (P10, P50, P90)
- **Censored demand**: Stockout periods flagged by `DemandProcessor` are excluded from training (Lokad methodology)
- **Checkpoints**: Saved to `backend/checkpoints/lgbm/`
- **Minimum data**: 26 observations per series; below this threshold, falls back to Holt-Winters

### Drift Detection

The pipeline monitors forecast quality drift between runs:

| Condition | Threshold | Action |
|-----------|-----------|--------|
| Absolute WAPE exceeds threshold | `wape_drift_threshold` (default 0.25) | Flag drift |
| Relative WAPE change vs baseline | `wape_relative_threshold` | Flag drift |
| Demand pattern change (cluster shift) | `pattern_change_threshold` | Flag drift |
| `auto_refit_on_drift` enabled | Any drift condition | Trigger LightGBM retraining |

**Database**: `ForecastPipelineRun` tracks `drift_detected`, `drift_reason`, `drift_wape_current`, `drift_wape_baseline` per run.

### Censored Demand Detection (Lokad)

**File**: `backend/app/services/aws_sc_planning/demand_processor.py`

When `InvLevel.on_hand_qty ≤ 0` during a period, observed demand is treated as **censored** — actual demand was higher than what was fulfilled. These periods are:

1. Flagged in `DemandProcessor.process_demand()` return value
2. Excluded from distribution fitting in `distribution_fitter.py`
3. Excluded from LightGBM training data
4. Surfaced in forecast exception reports

### Publishing Workflow

```python
ForecastPipelineService.publish_run(run_id, user_id, notes)
```

1. Loads predictions from `ForecastPipelinePrediction` table
2. Upserts into `Forecast` table (P10, P50, P90, forecast_quantity = P50)
3. Creates `ForecastPipelinePublishLog` audit record
4. Marks run as `is_published = True`

**Version tracking**: Each publish creates a point-in-time snapshot. Previous forecasts are soft-replaced (not deleted).

### Configuration Parameters

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `time_bucket` | `W` | D (daily), W (weekly), M (monthly) |
| `forecast_horizon` | 13 | Periods to forecast ahead |
| `min_clusters` / `max_clusters` | 2 / 8 | KMeans cluster range |
| `min_observations` | 12 | Minimum history per series |
| `cv_sq_threshold` | 0.49 | CV² quality filter |
| `adi_threshold` | 1.32 | Average demand interval filter |
| `cluster_selection_method` | KMeans | KMeans, HDBSCAN, Agglomerative, etc. |
| `characteristics_creation_method` | tsfresh | tsfresh, classifier, or both |
| `feature_importance_method` | LassoCV | LassoCV, RandomForest, MutualInformation |

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/forecast-pipeline/configs` | GET/POST | List or create pipeline configurations |
| `/forecast-pipeline/configs/{id}` | PUT | Update pipeline configuration |
| `/forecast-pipeline/runs` | GET/POST | List runs or trigger new run |
| `/forecast-pipeline/runs/{id}` | GET | Get run status and metadata |
| `/forecast-pipeline/runs/{id}/execute` | POST | Manually execute a run |
| `/forecast-pipeline/runs/{id}/publish` | POST | Publish forecasts to Forecast table |
| `/forecast-pipeline/runs/{id}/publish-log` | GET | Get publish audit trail |
| `/forecast-pipeline/runs/{id}/drift-status` | GET | Get drift detection results |
| `/forecast-pipeline/runs/{id}/train-lgbm` | POST | Trigger LightGBM training |

### Provisioning Integration

**Step 4 (`lgbm_forecast`)** in the 13-step provisioning pipeline:
- Loads or creates a `ForecastPipelineConfig` for the config
- Runs the full 4-stage pipeline
- Publishes P10/P50/P90 forecasts to the `Forecast` table
- Serves as the baseline for all downstream planning steps

---

## 2. Forecast Editing & Collaboration

### Forecast Adjustments

**API**: `backend/app/api/endpoints/forecast_adjustments.py`

Three adjustment modes:

| Mode | Behavior |
|------|----------|
| `absolute` | Set forecast to exact value |
| `delta` | Add or subtract from current value |
| `percentage` | Apply % change (e.g., +10%) |

**Editable table** (`GET /forecast-adjustments/table`): Returns a pivoted product × site × period grid with P10/P50/P90 values, `user_override_quantity`, and `adjustment_type` for inline editing.

**Adjustment types** (from `Forecast.adjustment_type`):
- `PROMOTION` — Uplift from promotional activity
- `NEW_PRODUCT` — NPI demand ramp
- `PHASE_OUT` — EOL demand reduction
- `EXECUTIVE` — Management override
- `SEASON` — Seasonal adjustment
- `null` — Manual analyst edit (no category)

### Forecast Versioning

```python
POST /forecast-adjustments/versions    # Create snapshot
POST /forecast-adjustments/versions/{id}/restore  # Rollback
```

- **Version types**: `snapshot` (manual), `baseline` (pipeline output), `consensus` (post-CPFR), `published` (approved)
- Each version captures full forecast state for rollback
- `is_current` / `is_locked` flags control editability

### Demand Collaboration (CPFR)

**API**: `backend/app/api/endpoints/demand_collaboration.py`

Implements CPFR (Collaborative Planning, Forecasting, and Replenishment) with trading partners:

**Collaboration types:**
- `forecast_share` — Partner shares their demand forecast
- `consensus` — Agreed forecast between buyer and seller
- `alert` — Demand-related notification
- `exception` — Forecast divergence requiring resolution

**Workflow**: `draft → submitted → approved/rejected`

**Exception detection**: `GET /demand-collaboration/exceptions/detect` identifies collaborations where partner forecast deviates from baseline by more than a configurable threshold.

**Key fields** (AWS SC compliant):
- `tpartner_id` — Trading partner (buyer/seller)
- `product_id`, `site_id` — Scope
- `baseline_forecast_quantity` — Our forecast
- `forecast_quantity` — Partner's forecast
- `variance_from_baseline` — % difference

---

## 3. Promotional Planning

**Models**: `backend/app/models/promotional_planning.py`
**Service**: `backend/app/services/promotional_planning_service.py`
**API**: `backend/app/api/endpoints/promotional_planning.py`

### Promotion Types

| Type | Description | Typical Uplift |
|------|-------------|----------------|
| `price_discount` | Temporary price reduction | 15-40% |
| `bogo` | Buy one get one (free or discounted) | 30-60% |
| `bundle` | Product bundling | 10-25% |
| `display` | In-store display/endcap placement | 5-15% |
| `seasonal` | Seasonal/holiday promotion | 20-50% |
| `clearance` | Markdown/liquidation | Variable |
| `loyalty` | Loyalty program reward | 5-10% |
| `new_product_launch` | NPI launch promotion | Variable |

### Workflow

```
draft → planned → approved → active → completed
                                    → cancelled (from any state)
```

### Demand Impact Tracking

| Field | Purpose |
|-------|---------|
| `expected_uplift_pct` | Planned demand increase (pre-event) |
| `expected_cannibalization_pct` | Expected impact on adjacent products |
| `actual_uplift_pct` | Measured demand increase (post-event) |
| `actual_cannibalization_pct` | Measured impact on adjacent products |
| `budget` / `actual_spend` | Financial tracking |

### AWS SC Integration

On activation:
1. Creates `supplementary_time_series` record (series_type=`PROMOTION`)
2. Creates `Forecast` adjustments (adjustment_type=`PROMOTION`)
3. Links via `supp_time_series_ids` and `forecast_adjustment_ids` for traceability

**Scope** (all AWS SC references):
- `product_ids` — Which products are promoted
- `site_ids` — Which sites participate
- `channel_ids` — Which channels (retail, e-commerce, wholesale)
- `customer_tpartner_ids` — Which customer trading partners

---

## 4. New Product Introduction (NPI)

**Models**: `backend/app/models/product_lifecycle.py`
**API**: `backend/app/api/endpoints/product_lifecycle.py`

### NPI Project Lifecycle

```
planning → qualification → pilot → ramp_up → launched
                                            → cancelled
```

### Demand Ramp

The `demand_ramp_curve` field stores week-by-week demand ramp as a percentage list:

```json
[10, 25, 50, 75, 100]
```

This means: Week 1 = 10% of steady-state demand, Week 2 = 25%, ..., Week 5+ = 100%.

**Integration**: On `ramp_up` status transition:
- Creates `Forecast` adjustments (adjustment_type=`NEW_PRODUCT`)
- Seeds `InvPolicy` for initial safety stock
- Updates `product_bom.lifecycle_phase` from `PILOT` → `PRODUCTION`

### Supplier Qualification

```json
{
  "vendor_123": "qualified",
  "vendor_456": "pending",
  "vendor_789": "not_started"
}
```

Maps to `VendorProduct` and `SourcingRules` for sourcing readiness.

### Quality Gates

```json
[
  {"gate": "Design Review", "status": "passed", "date": "2026-01-15"},
  {"gate": "Prototype Testing", "status": "passed", "date": "2026-02-01"},
  {"gate": "Pilot Production", "status": "in_progress", "date": null},
  {"gate": "Full Release", "status": "pending", "date": null}
]
```

### Financial Tracking

| Field | Purpose |
|-------|---------|
| `investment` | Total NPI investment |
| `expected_revenue_yr1` | Year 1 revenue forecast |
| `initial_forecast_qty` | Steady-state demand quantity |
| `risk_assessment` | Free-text risk analysis |

---

## 5. End of Life (EOL) & Phase-Out

### EOL Plan

**Status**: `planning → approved → in_progress → completed → cancelled`

**Key dates**:

| Date | Meaning |
|------|---------|
| `last_buy_date` | Final date to place purchase orders for raw materials |
| `last_manufacture_date` | Final production run date |
| `last_ship_date` | Final date to fulfill customer orders |
| `expected_eol_date` | Target end-of-life date |

### Demand Phase-Out Curve

```json
[90, 75, 50, 25, 10, 0]
```

Week-by-week demand reduction: Week 1 = 90% of current, ..., Week 6 = 0%.

**Integration**: On `in_progress` transition:
- Creates `Forecast` adjustments (adjustment_type=`PHASE_OUT`)
- Generates clearance `Promotion` if markdown plan exists
- Updates `product_bom.lifecycle_phase` → `PHASE_OUT`

### Markdown (Clearance) Plan

```json
{
  "markdown_schedule": [
    {"week": 1, "discount_pct": 10},
    {"week": 3, "discount_pct": 25},
    {"week": 5, "discount_pct": 50}
  ],
  "original_price": 29.99,
  "floor_price": 9.99,
  "target_sell_through_pct": 95,
  "disposition_if_unsold": "donate"
}
```

**Disposition options**: `scrap`, `donate`, `return_to_vendor`, `hold`

### Successor Product Tracking

`ProductLifecycle.successor_product_id` links the EOL product to its replacement, enabling demand transfer from declining product to successor NPI.

### Lifecycle Stage Mapping to AWS SC

| Lifecycle Stage | `product.is_active` | `product_bom.lifecycle_phase` |
|----------------|---------------------|-------------------------------|
| concept | true | DESIGN |
| development | true | DESIGN |
| launch | true | PILOT |
| growth | true | PRODUCTION |
| maturity | true | PRODUCTION |
| decline | true | PHASE_OUT |
| eol | true | PHASE_OUT |
| discontinued | false | OBSOLETE |

---

## 6. Forecast Exception Detection

**Service**: `backend/app/services/forecast_exception_detector.py`

### Detection Rules

| Rule | Logic | Severity |
|------|-------|----------|
| `VARIANCE_THRESHOLD` | `abs(actual - forecast) / forecast > threshold%` | By magnitude |
| `TREND_DETECTION` | N consecutive periods with same-direction variance | HIGH if ≥3 periods |
| `OUTLIER_DETECTION` | Actual > N standard deviations from forecast | CRITICAL if >3σ |
| `BIAS_DETECTION` | Consistent over/under forecasting across periods | MEDIUM/HIGH |

### Severity Classification

| Severity | Variance Range |
|----------|---------------|
| CRITICAL | ≥ 100% |
| HIGH | ≥ 50% |
| MEDIUM | ≥ 25% |
| LOW | < 25% |

### Exception Lifecycle

```
NEW → RESOLVED (by adjustment or next forecast run)
    → DISMISSED (by analyst, with reason)
```

### ForecastException Fields

| Field | Type | Purpose |
|-------|------|---------|
| `exception_number` | str | Human-readable ID (auto-generated) |
| `product_id` / `site_id` | FK | Scope |
| `forecast_quantity` | float | What was forecast |
| `actual_quantity` | float | What actually happened |
| `variance_quantity` | float | Absolute difference |
| `variance_percent` | float | Percentage difference |
| `direction` | str | `OVER` or `UNDER` |
| `exception_type` | str | Detection rule that triggered |
| `severity` / `priority` | str | Classification |
| `detection_method` | str | `AUTOMATED` |
| `status` | str | `NEW`, `RESOLVED`, `DISMISSED` |

---

## 7. Signal-Driven Forecast Adjustments (TRM)

### ForecastAdjustmentTRM

**Engine**: `backend/app/services/powell/engines/forecast_adjustment_engine.py`
**TRM**: `backend/app/services/powell/forecast_adjustment_trm.py`

The Forecast Adjustment TRM is one of 11 narrow execution TRM agents. It processes demand signals from email ingestion, voice, and market intelligence:

```
Email Signal (demand_increase/decrease)
    ↓ EmailSignalService
    ↓ classified by LLM (Haiku)
    ↓ routed to forecast_adjustment TRM
    ↓
ForecastAdjustmentEngine (deterministic baseline)
    ↓ direction + magnitude from signal analysis
    ↓
ForecastAdjustmentTRM (neural adjustment)
    ↓ <10ms inference
    ↓ CDT risk_bound = P(loss > threshold)
    ↓
powell_forecast_adjustment_decisions
    ↓ (if confidence > threshold)
    ↓
Forecast table (P50 adjusted)
```

**Signal → TRM routing** (from email signal pipeline):

| Signal Type | Primary TRM | Secondary TRM |
|-------------|-------------|---------------|
| `demand_increase` | forecast_adjustment | inventory_buffer |
| `demand_decrease` | forecast_adjustment | inventory_buffer |

---

## 8. Forecast Data Model (AWS SC Compliant)

### Forecast Table

```python
class Forecast(Base):
    __tablename__ = "forecast"

    id: int                          # Primary key
    config_id: int                   # FK to supply_chain_configs
    product_id: str                  # FK to product
    site_id: int                     # FK to site
    forecast_date: date              # Period date

    # Probabilistic output
    forecast_quantity: float         # P50 (baseline point forecast)
    forecast_p10: float              # 10th percentile
    forecast_p50: float              # 50th percentile (median)
    forecast_p90: float              # 90th percentile

    # User override (takes precedence over statistical forecast)
    user_override_quantity: float    # Manual override value (nullable)

    # Adjustment tracking
    adjustment_type: str             # PROMOTION | NEW_PRODUCT | PHASE_OUT | null
    adjustment_value: float          # Adjustment magnitude

    # Quality metrics (populated by warm start / pipeline)
    forecast_error: float            # Actual - Forecast (nullable)
    forecast_bias: float             # Cumulative bias (nullable)

    # Audit
    created_by_id: int
    updated_by_id: int
    created_at: datetime
    updated_at: datetime
```

### ConsensusDemand Table

```python
class ConsensusDemand(Base):
    __tablename__ = "consensus_demand"

    # Forecast components
    statistical_forecast: float      # From pipeline
    sales_forecast: float            # Sales team input
    marketing_forecast: float        # Marketing team input
    management_override: float       # Executive override

    # Consensus result
    consensus_quantity: float        # Agreed-upon value
    consensus_p10: float
    consensus_p50: float
    consensus_p90: float

    # Adjustment tracking
    adjustment_reason: str
    adjustment_type: str             # PROMOTION | SEASON | NEW_PRODUCT | PHASE_OUT | EXECUTIVE

    # S&OP integration
    sop_cycle_id: int
    approval_date: date
    version: int
```

### SupplementaryTimeSeries

Used for promotional uplift, NPI ramp, and EOL phase-out overlays:

```python
class SupplementaryTimeSeries(Base):
    __tablename__ = "supplementary_time_series"

    series_type: str    # PROMOTION | SAFETY_STOCK | DEMAND_SENSING | CANNIBALIZATION
    product_id: str
    site_id: int
    start_date: date
    end_date: date
    quantity: float     # Uplift or reduction quantity
    metadata: JSON      # Source promotion/NPI/EOL IDs
```

---

## 9. Integration Map

### How Subsystems Connect

```
                    ┌─────────────────────────┐
                    │  Email Signal Pipeline   │
                    │  (demand_increase/       │
                    │   demand_decrease)       │
                    └────────┬────────────────┘
                             ↓
┌──────────────┐   ┌─────────────────────────┐   ┌──────────────┐
│  Promotional │   │   Forecast Adjustment   │   │   NPI / EOL  │
│  Planning    │──→│   TRM                   │←──│   Projects   │
│  Service     │   │   (signal-driven)       │   │              │
└──────┬───────┘   └────────┬────────────────┘   └──────┬───────┘
       │                    ↓                           │
       │           ┌─────────────────────────┐          │
       └──────────→│   Forecast Table        │←─────────┘
                   │   (P10 / P50 / P90)     │
                   └────────┬────────────────┘
                            ↓
                   ┌─────────────────────────┐
                   │  Demand Collaboration   │
                   │  (CPFR consensus)       │
                   └────────┬────────────────┘
                            ↓
                   ┌─────────────────────────┐
                   │  Exception Detection    │
                   │  (anomaly monitoring)   │
                   └────────┬────────────────┘
                            ↓
                   ┌─────────────────────────┐
                   │  DemandProcessor        │
                   │  (Step 1: net demand)   │
                   │  + censored detection   │
                   └────────┬────────────────┘
                            ↓
                   Supply Planning (Steps 2-3)
```

### Precedence Rules

When multiple adjustment sources exist for the same product × site × period:

1. **User override** (`user_override_quantity`) — always wins if set
2. **Consensus quantity** (`consensus_demand.consensus_quantity`) — CPFR-agreed
3. **Adjustment overlay** (`adjustment_type` + `adjustment_value`) — promo/NPI/EOL
4. **Statistical forecast** (`forecast_p50`) — pipeline output

### Warm Start Integration

Provisioning Step 1 (`warm_start`):
1. Loads existing `Forecast` P10/P50/P90 values
2. Samples 52 weeks of synthetic demand via `triangular(P10, P50, P90) × (1 + noise)`
3. Writes to `OutboundOrderLine` as historical actuals
4. Computes `Forecast.forecast_error` and `forecast_bias`
5. Seeds `PerformanceMetric` history for KPI dashboards

Provisioning Step 4 (`lgbm_forecast`):
1. Runs the 4-stage forecast pipeline against warm-started history
2. Publishes P10/P50/P90 to `Forecast` table
3. This becomes the baseline for supply planning (Steps 9+)

---

## 10. Frontend Pages

| Page | Path | Purpose |
|------|------|---------|
| Demand Plan View | `/planning/demand-plan` | View current demand plan with P10/P50/P90 |
| Demand Plan Edit | `/planning/demand-plan/edit` | Inline forecast editing with version control |
| Forecast Pipeline | `/admin/forecast-pipeline` | Configure and run forecast pipeline |
| Promotional Planning | `/planning/promotions` | Manage promotions lifecycle |
| Product Lifecycle | `/planning/product-lifecycle` | NPI projects, EOL plans, markdown |
| Forecast Exceptions | `/planning/forecast-exceptions` | Exception worklist and resolution |
| Consensus Planning | `/planning/consensus` | CPFR collaboration and approval |

---

## 11. Key Implementation Files

| File | Lines | Purpose |
|------|-------|---------|
| `services/forecast_pipeline_service.py` | 995 | 4-stage pipeline orchestrator |
| `services/demand_forecasting/lgbm_pipeline.py` | — | LightGBM quantile regression |
| `services/demand_forecasting/lgbm_forecaster.py` | — | Feature engineering for LightGBM |
| `services/demand_forecasting/feature_engineer.py` | — | Time series feature extraction |
| `services/demand_forecasting/event_tagger.py` | — | Event impact tagging |
| `services/aws_sc_planning/demand_processor.py` | — | Step 1: demand aggregation + censored detection |
| `services/forecast_exception_detector.py` | — | Anomaly detection (4 rules) |
| `services/promotional_planning_service.py` | 319 | Promotion CRUD + workflow |
| `services/powell/forecast_adjustment_trm.py` | — | TRM for signal-driven adjustments |
| `services/powell/engines/forecast_adjustment_engine.py` | — | Deterministic forecast adjustment engine |
| `api/endpoints/forecast_pipeline.py` | 671 | Pipeline configuration and execution API |
| `api/endpoints/forecast_adjustments.py` | — | Forecast editing and versioning API |
| `api/endpoints/demand_collaboration.py` | — | CPFR consensus API |
| `api/endpoints/promotional_planning.py` | 291 | Promotion management API |
| `api/endpoints/product_lifecycle.py` | 581 | NPI/EOL/lifecycle API |
| `models/sc_entities.py` | — | Forecast, ConsensusDemand, SupplementaryTimeSeries |
| `models/promotional_planning.py` | 150+ | Promotion, PromotionHistory |
| `models/product_lifecycle.py` | 150+ | NPIProject, EOLPlan, MarkdownPlan, ProductLifecycle |

---

*Last updated: 2026-03-14*
*Academic reference: `docs/knowledge/Demand_Planning_Forecasting_Guide.md`*
