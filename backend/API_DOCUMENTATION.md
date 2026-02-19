# Beer Game API v1.1

## Authentication
- JWT with HTTP-only cookies
- Required header: `X-CSRF-Token` for non-GET requests
- Login: `POST /auth/login`
- Get current user: `GET /auth/me`

## Scenario Endpoints

### Create Scenario
```http
POST /scenarios/
```
**Request:**
```json
{
  "name": "Supply Chain Challenge",
  "max_periods": 20,
  "participant_count": 4,
  "demand_pattern": {
    "type": "step",
    "params": {
      "initial_demand": 4,
      "step_period": 5,
      "step_size": 2
    }
  }
}
```

### Join Scenario
```http
POST /scenarios/{scenario_id}/join
```
**Request:**
```json
{"role": "retailer"}
```

### Submit Order
```http
POST /scenarios/{scenario_id}/orders
```
**Request:**
```json
{
  "period": 1,
  "quantity": 8,
  "type": "regular"
}
```

### Get Scenario State
```http
GET /scenarios/{scenario_id}/state
```
**Response:**
```json
{
  "scenario_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "in_progress",
  "current_period": 5,
  "participants": [
    {
      "id": 42,
      "role": "retailer",
      "inventory": 15,
      "backlog": 0,
      "last_order": 8
    }
  ]
}
```

## WebSocket
```
ws://localhost:8000/ws/scenario/{scenario_id}
```

## Error Responses
- `400 Bad Request`: Invalid parameters
- `401 Unauthorized`: Invalid/missing token
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `429 Too Many Requests`: Rate limit exceeded

### Get Scenario Details
```
GET /scenarios/{scenario_id}
```

**Response (200 OK):**
```json
{
  "id": 1,
  "name": "My Beer Game",
  "status": "in_progress",
  "current_period": 3,
  "max_periods": 20,
  "created_at": "2023-04-01T10:00:00Z",
  "updated_at": "2023-04-01T10:05:30Z"
}
```

### Start a Scenario
```
POST /scenarios/{scenario_id}/start
```

**Response (200 OK):**
```json
{
  "id": 1,
  "name": "My Beer Game",
  "status": "in_progress",
  "current_period": 1,
  "max_periods": 20,
  "created_at": "2023-04-01T10:00:00Z",
  "updated_at": "2023-04-01T10:06:15Z"
}
```

### Get Scenario State
```
GET /scenarios/{scenario_id}/state
```

**Response (200 OK):**
```json
{
  "id": 1,
  "name": "My Beer Game",
  "status": "in_progress",
  "current_period": 3,
  "max_periods": 20,
  "demand_pattern": {
    "type": "classic",
    "params": {
      "initial_demand": 4,
      "change_week": 6,
      "final_demand": 8
    },
    "current_demand": 8,
    "next_demand": 8
  },
  "participants": [
    {
      "id": 1,
      "name": "Retailer 1",
      "role": "retailer",
      "is_ai": false,
      "current_stock": 10,
      "incoming_shipments": [{"quantity": 4, "arrival_period": 5}],
      "backorders": 0,
      "total_cost": 15.50
    }
  ]
}
```

## Participant Endpoints

### Add Participant to Scenario
```
POST /scenarios/{scenario_id}/participants
```

**Request Body:**
```json
{
  "name": "Retailer 1",
  "role": "retailer",
  "is_ai": false
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "scenario_id": 1,
  "name": "Retailer 1",
  "role": "retailer",
  "is_ai": false,
  "user_id": 123
}
```

### List Participants in Scenario
```
GET /scenarios/{scenario_id}/participants
```

**Response (200 OK):**
```json
[
  {
    "id": 1,
    "scenario_id": 1,
    "name": "Retailer 1",
    "role": "retailer",
    "is_ai": false,
    "user_id": 123
  },
  {
    "id": 2,
    "scenario_id": 1,
    "name": "Wholesaler 1",
    "role": "wholesaler",
    "is_ai": true,
    "user_id": null
  }
]
```

## Order Endpoints

### Submit Order
```
POST /scenarios/{scenario_id}/participants/{participant_id}/orders
```

**Request Body:**
```json
{
  "quantity": 5
}
```

**Response (201 Created):**
```json
{
  "id": 1,
  "scenario_id": 1,
  "participant_id": 1,
  "period_number": 3,
  "quantity": 5,
  "created_at": "2023-04-01T10:15:30Z"
}
```

## Period Endpoints

### Get Current Period
```
GET /scenarios/{scenario_id}/periods/current
```

**Response (200 OK):**
```json
{
  "id": 3,
  "scenario_id": 1,
  "period_number": 3,
  "customer_demand": 8,
  "created_at": "2023-04-01T10:10:00Z",
  "participant_periods": [
    {
      "id": 5,
      "participant_id": 1,
      "period_id": 3,
      "order_placed": 5,
      "order_received": 4,
      "inventory_before": 6,
      "inventory_after": 2,
      "backorders_before": 0,
      "backorders_after": 0,
      "holding_cost": 1.0,
      "backorder_cost": 0.0,
      "total_cost": 1.0
    }
  ]
}
```

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Invalid request data"
}
```

### 401 Unauthorized
```json
{
  "detail": "Not authenticated"
}
```

### 403 Forbidden
```json
{
  "detail": "Not enough permissions"
}
```

### 404 Not Found
```json
{
  "detail": "Scenario not found"
}
```

## Demand Pattern Types

The scenario supports different demand patterns that can be specified when creating a scenario:

### Classic Pattern
- **Type:** `classic`
- **Parameters:**
  - `initial_demand`: Customer demand before the change (default: 4)
  - `change_week`: Week number at which demand shifts to the new level (default: 6)
  - `final_demand`: Customer demand after the change (default: 8)

Example:
```json
{
  "type": "classic",
  "params": {
    "initial_demand": 4,
    "change_week": 6,
    "final_demand": 8
  }
}
```

### Random Pattern
- **Type:** `random`
- **Parameters:**
  - `min_demand`: Minimum possible demand (default: 2)
  - `max_demand`: Maximum possible demand (default: 12)

### Seasonal Pattern
- **Type:** `seasonal`
- **Parameters:**
  - `base_demand`: Base demand level (default: 8)
  - `amplitude`: Amplitude of seasonal variation (default: 4)
  - `period`: Number of rounds in a full cycle (default: 12)

---

## ATP/CTP Probabilistic Endpoints (Phase 5)

These endpoints provide probabilistic Available-to-Promise (ATP) and Capable-to-Promise (CTP) calculations using Monte Carlo simulation with stochastic lead times.

### Get Probabilistic ATP
```http
GET /mixed-scenarios/{scenario_id}/atp-probabilistic/{participant_id}
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `scenario_id` | int | Yes | Scenario ID |
| `participant_id` | int | Yes | Participant ID |
| `n_simulations` | int | No | Number of Monte Carlo runs (default: 100, max: 1000) |
| `include_safety_stock` | bool | No | Whether to reserve safety stock (default: true) |

**Response (200 OK):**
```json
{
  "on_hand": 500,
  "safety_stock": 50,
  "scheduled_receipts_p50": 200,
  "allocated_orders": 300,
  "atp_p50": 350,
  "scheduled_receipts_p10": 150,
  "atp_p10": 300,
  "scheduled_receipts_p90": 250,
  "atp_p90": 400,
  "lead_time_mean": 2.3,
  "lead_time_stddev": 0.8,
  "simulation_runs": 100,
  "timestamp": "2026-01-30T12:00:00",
  "alerts": [
    {
      "level": "warning",
      "message": "Low inventory warning",
      "threshold": 100,
      "actual": 50,
      "recommendation": "Consider expediting orders"
    }
  ]
}
```

### Get Probabilistic CTP
```http
GET /mixed-scenarios/{scenario_id}/ctp-probabilistic/{participant_id}
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `scenario_id` | int | Yes | Scenario ID |
| `participant_id` | int | Yes | Participant ID (must be manufacturer node) |
| `product_id` | string | Yes | **AWS SC Product ID** (e.g., "FG-001") |
| `n_simulations` | int | No | Number of Monte Carlo runs (default: 100) |

> **Note:** The `product_id` parameter uses string format for AWS Supply Chain Data Model compliance.

**Response (200 OK):**
```json
{
  "production_capacity": 1000,
  "current_commitments": 600,
  "yield_rate_mean": 0.95,
  "yield_rate_stddev": 0.02,
  "ctp_p10": 340,
  "ctp_p50": 380,
  "ctp_p90": 410,
  "available_capacity_p10": 360,
  "available_capacity_p50": 400,
  "available_capacity_p90": 430,
  "constrained_by": null,
  "component_constraints": [
    {
      "item_id": "COMP-001",
      "item_name": "Aluminum Can",
      "required_per_unit": 1,
      "available_atp": 10000,
      "max_producible": 10000,
      "shortfall": 0
    }
  ],
  "production_lead_time_mean": 5.0,
  "production_lead_time_stddev": 1.0,
  "simulation_runs": 100,
  "timestamp": "2026-01-30T12:00:00"
}
```

### Get Pipeline Visualization
```http
GET /mixed-scenarios/{scenario_id}/pipeline-visualization/{participant_id}
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `scenario_id` | int | Yes | Scenario ID |
| `participant_id` | int | Yes | Participant ID |
| `n_simulations` | int | No | Number of simulations (default: 100) |

**Response (200 OK):**
```json
{
  "participant_id": 3,
  "participant_name": "Distributor",
  "current_period": 5,
  "pipeline_total": 150,
  "shipments": [
    {
      "slot": 0,
      "quantity": 50,
      "scheduled_arrival_period": 6,
      "arrival_p10_period": 6,
      "arrival_p50_period": 6,
      "arrival_p90_period": 7,
      "arrival_probability_next_period": 0.85,
      "source_node": "Factory",
      "source_node_id": 1
    }
  ],
  "arrival_distribution": {
    "period_6": {"quantity_p10": 0, "quantity_p50": 50, "quantity_p90": 50}
  },
  "lead_time_stats": {
    "mean": 2.1,
    "stddev": 0.5,
    "p10": 2,
    "p50": 2,
    "p90": 3
  },
  "timestamp": "2026-01-30T12:00:00"
}
```

### Get ATP/CTP History
```http
GET /mixed-scenarios/{scenario_id}/atp-history/{participant_id}
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `scenario_id` | int | Yes | Scenario ID |
| `participant_id` | int | Yes | Participant ID |
| `limit` | int | No | Maximum records to return (default: 20) |

**Response (200 OK):**
```json
{
  "participant_id": 3,
  "participant_name": "Distributor",
  "node_id": 8,
  "node_name": "Distributor",
  "current_period": 10,
  "history": [
    {
      "period": "5",
      "date": "2026-01-25",
      "atp_p10": 300,
      "atp_p50": 350,
      "atp_p90": 400,
      "on_hand": 500,
      "scheduled_receipts": 200,
      "allocated_orders": 300,
      "lead_time_mean": 2.3,
      "lead_time_stddev": 0.8,
      "timestamp": "2026-01-25T12:00:00"
    }
  ],
  "ctp_history": [
    {
      "period": "5",
      "date": "2026-01-25",
      "ctp_p10": 340,
      "ctp_p50": 380,
      "ctp_p90": 410,
      "production_capacity": 1000,
      "commitments": 600,
      "available_capacity": 400,
      "component_constrained": false,
      "timestamp": "2026-01-25T12:00:00"
    }
  ]
}
```

### ATP/CTP Formulas

**ATP (Available to Promise):**
```
ATP = On-Hand Inventory + Scheduled Receipts - Allocated Orders - Safety Stock
```

**CTP (Capable to Promise):**
```
CTP = (Production Capacity - Commitments) × Yield Rate × Component Availability
```

### Probabilistic Interpretation

- **P10 (Pessimistic)**: 10% probability the value will be at or below this
- **P50 (Median)**: 50% probability - the most likely outcome
- **P90 (Optimistic)**: 90% probability the value will be at or below this

The Monte Carlo simulation samples from stochastic lead time distributions to generate the probability distribution of ATP/CTP values.

---

## Conformal Prediction Endpoints

Conformal Prediction provides prediction intervals with *statistical coverage guarantees*. Unlike Monte Carlo which estimates probability distributions, conformal prediction guarantees that the interval will contain the true value at least X% of the time (where X is the specified coverage level).

### Get Conformal ATP
```http
GET /mixed-scenarios/{scenario_id}/atp-conformal/{participant_id}
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `scenario_id` | int | Yes | Scenario ID |
| `participant_id` | int | Yes | Participant ID |
| `coverage` | float | No | Target coverage probability (default: 0.90) |
| `method` | string | No | Conformal method: split, quantile, adaptive (default: adaptive) |

**Response (200 OK):**
```json
{
  "atp_point": 350,
  "atp_lower": 280,
  "atp_upper": 420,
  "coverage": 0.90,
  "method": "adaptive",
  "calibration_size": 45,
  "interval_width": 140,
  "is_calibrated": true,
  "adaptive_alpha": 0.105,
  "coverage_stats": {
    "empirical_coverage": 0.91,
    "target_coverage": 0.90,
    "coverage_gap": 0.01,
    "n_observations": 45
  },
  "monte_carlo_comparison": {
    "mc_p10": 300,
    "mc_p50": 350,
    "mc_p90": 400
  },
  "timestamp": "2026-01-30T12:00:00"
}
```

### Calibrate Conformal ATP
```http
POST /mixed-scenarios/{scenario_id}/atp-conformal/{participant_id}/calibrate
```

**Request:**
```json
{
  "predictions": [350, 340, 360, 355, ...],
  "actuals": [345, 355, 350, 360, ...]
}
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `coverage` | float | No | Target coverage (default: 0.90) |
| `method` | string | No | Conformal method (default: adaptive) |

**Response (200 OK):**
```json
{
  "calibration_size": 50,
  "empirical_coverage": 0.88,
  "target_coverage": 0.90,
  "quantile_value": 15.3,
  "method": "adaptive",
  "message": "Calibration successful"
}
```

### Get Conformal Demand Forecast
```http
GET /mixed-scenarios/{scenario_id}/demand-conformal/{participant_id}
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `scenario_id` | int | Yes | Scenario ID |
| `participant_id` | int | Yes | Participant ID |
| `horizon` | int | No | Forecast horizon in periods (default: 1) |
| `coverage` | float | No | Target coverage (default: 0.90) |

**Response (200 OK):**
```json
{
  "demand_point": 100,
  "demand_lower": 85,
  "demand_upper": 120,
  "coverage": 0.90,
  "horizon": 1,
  "calibration_size": 30,
  "interval_width": 35,
  "is_calibrated": true,
  "historical_demand": [95, 102, 98, 105, 100, 97],
  "forecast_accuracy": {
    "mape": 8.5,
    "rmse": 12.3,
    "bias": 2.1
  },
  "timestamp": "2026-01-30T12:00:00"
}
```

### Get Conformal Lead Time
```http
GET /mixed-scenarios/{scenario_id}/lead-time-conformal/{participant_id}
```

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `scenario_id` | int | Yes | Scenario ID |
| `participant_id` | int | Yes | Participant ID |
| `coverage` | float | No | Target coverage (default: 0.90) |

**Response (200 OK):**
```json
{
  "expected_lead_time": 2.0,
  "lead_time_lower": 1.5,
  "lead_time_upper": 3.2,
  "coverage": 0.90,
  "calibration_size": 25,
  "interval_width": 1.7,
  "is_calibrated": true,
  "historical_lead_times": [2.0, 2.1, 1.9, 2.3, 1.8, 2.2],
  "arrival_window": {
    "earliest_period": 3,
    "expected_period": 4,
    "latest_period": 5
  },
  "timestamp": "2026-01-30T12:00:00"
}
```

### Conformal Prediction Methods

| Method | Description | Best For |
|--------|-------------|----------|
| **split** | Uses absolute residuals \|y - ŷ\| as nonconformity scores | Simple, fast, general purpose |
| **quantile** | Conformalized Quantile Regression (CQR) | Heteroscedastic data (varying uncertainty) |
| **adaptive** | Adaptive Conformal Inference (ACI) | Non-stationary data, distribution shift |

### Coverage Guarantee

Unlike Monte Carlo's probabilistic estimates, conformal prediction provides *statistical guarantees*:

> If the predictor is calibrated with coverage α (e.g., 0.90), the prediction interval [lower, upper] will contain the true value at least α% of the time, regardless of the underlying data distribution.

This is achieved through calibration on historical prediction-actual pairs, computing nonconformity scores, and adjusting interval width based on the empirical quantile of these scores.
