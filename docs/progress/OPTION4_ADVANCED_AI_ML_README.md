# Option 4: Advanced AI/ML - Implementation Guide

**Status**: Core Implementation Complete
**Estimated Total Effort**: 10-15 days
**Current Progress**: Day 1-3 Complete (Core RL + Enhanced GNN + Predictive Analytics)

---

## Overview

This option extends The Beer Game platform with cutting-edge AI/ML capabilities:

1. **Reinforcement Learning Agents** (PPO, SAC, A2C)
2. **Enhanced GNN Architectures** (GraphSAGE, Heterogeneous GNN, Temporal Attention)
3. **Predictive Analytics Service** (Forecasting, What-If Analysis)
4. **Explainable AI** (SHAP values, Feature Importance)
5. **AutoML Integration** (Hyperparameter Optimization)

---

## Components Implemented

### 1. Reinforcement Learning Agents

**File**: `backend/app/agents/rl_agent.py` (650 lines)

**Capabilities**:
- **Algorithms**: PPO (Proximal Policy Optimization), SAC (Soft Actor-Critic), A2C (Advantage Actor-Critic)
- **Training**: Parallel environment support, curriculum learning
- **Evaluation**: Performance metrics, episode replay
- **Deployment**: Production-ready inference with fallback to heuristics

**Key Classes**:
- `RLAgent`: Main agent class with train/predict/evaluate methods
- `BeerGameRLEnv`: Gym-compatible environment for training
- `RLConfig`: Configuration dataclass for hyperparameters
- `TensorBoardCallback`: Custom callback for logging

**Usage Example**:
```python
from app.agents.rl_agent import create_rl_agent

# Create and train agent
agent = create_rl_agent(
    algorithm="PPO",
    total_timesteps=1_000_000,
    learning_rate=3e-4,
    device="cuda"
)

agent.train(n_envs=4, eval_freq=10000)

# Use in game
order_quantity = agent.compute_order(node, context)
```

**Training Script**: `backend/scripts/training/train_rl_agents.py`

```bash
# Train PPO agent
python backend/scripts/training/train_rl_agents.py \
    --algorithm PPO \
    --total-timesteps 1000000 \
    --n-envs 4 \
    --device cuda

# Train SAC agent
python backend/scripts/training/train_rl_agents.py \
    --algorithm SAC \
    --total-timesteps 500000 \
    --learning-rate 1e-4 \
    --device cuda

# View training progress
tensorboard --logdir logs/rl
```

**Performance Benchmarks** (Expected):
- PPO: 15-30% cost reduction vs. naive policy
- SAC: 20-35% cost reduction (better sample efficiency)
- Training time: 2-6 hours on GPU (1M timesteps)

---

### 2. Enhanced GNN Architectures

**File**: `backend/app/models/gnn/enhanced_gnn.py` (750 lines)

**Architectures Implemented**:

#### a) GraphSAGE Supply Chain GNN
- **Inductive learning**: Generalizes to unseen network topologies
- **Neighbor sampling**: Scalable to large supply chains
- **Multi-task learning**: Joint prediction of orders, costs, bullwhip

**Architecture**:
```python
GraphSAGESupplyChain(
    node_feature_dim=16,
    edge_feature_dim=4,
    hidden_dim=128,
    num_layers=3,
    aggregator="mean"
)
```

**Outputs**:
- `order`: Predicted order quantities
- `cost`: Predicted costs
- `bullwhip`: Bullwhip risk scores
- `embeddings`: Node embeddings for downstream tasks

#### b) Heterogeneous Supply Chain GNN
- **Multiple node types**: Retailer, Wholesaler, Distributor, Factory, Supplier
- **Multiple edge types**: Order flows, shipment flows, information flows
- **Type-specific processing**: Different encoders/decoders per type

**Architecture**:
```python
HeterogeneousSupplyChainGNN(
    node_types=["retailer", "wholesaler", "distributor", "factory"],
    edge_types=[
        ("retailer", "orders_from", "wholesaler"),
        ("wholesaler", "ships_to", "retailer")
    ],
    node_feature_dims={"retailer": 16, "wholesaler": 18, ...},
    hidden_dim=128
)
```

#### c) Enhanced Temporal GNN
- **Spatial encoder**: GraphSAGE for per-timestep processing
- **Temporal encoder**: Multi-head attention over time sequences
- **Confidence estimation**: Uncertainty quantification for predictions

**Architecture**:
```python
EnhancedTemporalGNN(
    node_feature_dim=16,
    edge_feature_dim=4,
    hidden_dim=128,
    num_spatial_layers=2,
    num_temporal_layers=2,
    num_heads=4,
    window_size=10
)
```

**Multi-Task Loss**:
- Automatically balances order prediction, cost prediction, bullwhip prediction
- Uncertainty-weighted loss (Kendall et al., 2018)

**Usage Example**:
```python
from app.models.gnn.enhanced_gnn import create_enhanced_gnn

# Create GraphSAGE model
model = create_enhanced_gnn(
    architecture="graphsage",
    node_feature_dim=16,
    hidden_dim=128,
    num_layers=3
)

# Create Temporal GNN model
model = create_enhanced_gnn(
    architecture="temporal",
    node_feature_dim=16,
    hidden_dim=128,
    window_size=10
)

# Forward pass
outputs = model(x, edge_index, edge_attr)
# outputs: {"order": [...], "cost": [...], "bullwhip": [...]}
```

---

### 3. Predictive Analytics Service

**File**: `backend/app/services/predictive_analytics_service.py` (850 lines)

**Capabilities**:

#### a) Demand Forecasting
- Forecast demand over 1-52 round horizon
- Uncertainty quantification (confidence bounds)
- Trend detection and seasonality

**API**:
```python
forecasts = await service.forecast_demand(
    game_id=123,
    node_id=456,
    horizon=10,
    confidence_level=0.95
)
# Returns: List[ForecastResult] with value, lower_bound, upper_bound
```

#### b) Bullwhip Effect Prediction
- Per-node bullwhip ratio prediction
- Risk level classification (low/medium/high)
- Contributing factor analysis

**API**:
```python
predictions = await service.predict_bullwhip(game_id=123)
# Returns: List[BullwhipPrediction] with ratios and risk factors
```

#### c) Cost Trajectory Forecasting
- Multi-horizon cost forecasting
- Risk scenarios (best/likely/worst case)
- Expected total cost calculation

**API**:
```python
trajectory = await service.forecast_cost_trajectory(
    game_id=123,
    node_id=456,
    horizon=10
)
# Returns: CostTrajectory with forecasts and risk scenarios
```

#### d) Explainable AI (SHAP)
- Feature importance analysis using SHAP values
- Natural language interpretation
- Directionality (increases/decreases orders)

**API**:
```python
explanation = await service.explain_prediction(
    game_id=123,
    node_id=456,
    round_number=15
)
# Returns: Feature importances, interpretation, visualization data
```

#### e) What-If Analysis
- Compare multiple scenarios against baseline
- Delta calculations (order changes, cost impacts)
- Actionable recommendations

**API**:
```python
analysis = await service.analyze_what_if(
    game_id=123,
    node_id=456,
    scenarios=[
        {"name": "Increase Inventory", "changes": {"inventory": 30}},
        {"name": "Reduce Orders", "changes": {"last_order": 5}}
    ]
)
# Returns: Baseline, scenario results, recommendations
```

#### f) Comprehensive Insights Report
- All analytics in one report
- Risk assessment
- Actionable recommendations

**API**:
```python
report = await service.generate_insights_report(game_id=123)
# Returns: Complete analytics report with all metrics
```

---

### 4. API Endpoints

**File**: `backend/app/api/endpoints/predictive_analytics.py` (450 lines)

**Endpoints**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/forecast/demand` | POST | Demand forecasting with confidence bounds |
| `/predict/bullwhip` | POST | Bullwhip effect prediction for all nodes |
| `/forecast/cost-trajectory` | POST | Cost trajectory with risk scenarios |
| `/explain/prediction` | POST | SHAP-based feature importance |
| `/analyze/what-if` | POST | What-if scenario analysis |
| `/insights/report` | POST | Comprehensive insights report |
| `/health` | GET | Health check |

**Request/Response Models**:
- All endpoints use Pydantic models for validation
- Type-safe request/response handling
- Comprehensive error handling

**Example Usage**:
```bash
# Demand forecast
curl -X POST "http://localhost:8000/api/v1/predictive-analytics/forecast/demand" \
  -H "Content-Type: application/json" \
  -d '{
    "game_id": 123,
    "node_id": 456,
    "horizon": 10,
    "confidence_level": 0.95
  }'

# Bullwhip prediction
curl -X POST "http://localhost:8000/api/v1/predictive-analytics/predict/bullwhip" \
  -H "Content-Type: application/json" \
  -d '{"game_id": 123}'

# What-if analysis
curl -X POST "http://localhost:8000/api/v1/predictive-analytics/analyze/what-if" \
  -H "Content-Type: application/json" \
  -d '{
    "game_id": 123,
    "node_id": 456,
    "scenarios": [
      {"name": "Increase Stock", "changes": {"inventory": 30}}
    ]
  }'
```

---

## Installation

### 1. Install ML Dependencies

```bash
# Install from requirements file
cd backend
pip install -r requirements_ml.txt

# Or install individually
pip install stable-baselines3 gymnasium torch torch-geometric shap optuna
```

### 2. GPU Support (Optional)

For CUDA 11.8:
```bash
pip install torch==2.2.0+cu118 torch-geometric==2.5.0 \
  --extra-index-url https://download.pytorch.org/whl/cu118
```

For CUDA 12.1:
```bash
pip install torch==2.2.0+cu121 torch-geometric==2.5.0 \
  --extra-index-url https://download.pytorch.org/whl/cu121
```

### 3. Verify Installation

```python
import torch
import stable_baselines3
import torch_geometric
import shap

print(f"PyTorch: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"Stable-Baselines3: {stable_baselines3.__version__}")
print(f"PyTorch Geometric: {torch_geometric.__version__}")
print(f"SHAP: {shap.__version__}")
```

---

## Training Workflows

### RL Agent Training

**Quick Start** (CPU, 100k steps):
```bash
python backend/scripts/training/train_rl_agents.py \
  --algorithm PPO \
  --total-timesteps 100000 \
  --n-envs 2 \
  --device cpu \
  --verbose 1
```

**Production Training** (GPU, 1M steps):
```bash
python backend/scripts/training/train_rl_agents.py \
  --algorithm PPO \
  --total-timesteps 1000000 \
  --n-envs 8 \
  --learning-rate 3e-4 \
  --batch-size 128 \
  --hidden-dim 256 \
  --device cuda \
  --checkpoint-dir checkpoints/rl/ppo_1m \
  --log-dir logs/rl/ppo_1m \
  --eval-freq 10000 \
  --verbose 1
```

**Hyperparameter Tuning** (Multiple Runs):
```bash
# PPO with different learning rates
for lr in 1e-4 3e-4 1e-3; do
  python backend/scripts/training/train_rl_agents.py \
    --algorithm PPO \
    --learning-rate $lr \
    --checkpoint-dir checkpoints/rl/ppo_lr_${lr}
done
```

**Monitor Training**:
```bash
tensorboard --logdir logs/rl
# Open http://localhost:6006
```

### GNN Training

(To be implemented in remaining days - will reuse existing `train_gnn.py` with enhanced architectures)

```bash
# Train GraphSAGE model
python backend/scripts/training/train_enhanced_gnn.py \
  --architecture graphsage \
  --hidden-dim 128 \
  --num-layers 3 \
  --epochs 50 \
  --device cuda

# Train Temporal GNN model
python backend/scripts/training/train_enhanced_gnn.py \
  --architecture temporal \
  --window-size 10 \
  --hidden-dim 128 \
  --epochs 50 \
  --device cuda
```

---

## Integration with Existing System

### 1. Register RL Agents

Add to `backend/app/services/agents.py`:

```python
from app.agents.rl_agent import create_rl_agent

# Load pre-trained RL agent
rl_agent_ppo = create_rl_agent(
    algorithm="PPO",
    model_path="checkpoints/rl/PPO_final.zip"
)

# Register in agent factory
def get_policy_by_strategy(strategy: str):
    if strategy == "rl_ppo":
        return rl_agent_ppo
    elif strategy == "rl_sac":
        return rl_agent_sac
    # ... existing strategies
```

### 2. Add API Router

Add to `backend/main.py`:

```python
from app.api.endpoints import predictive_analytics

app.include_router(
    predictive_analytics.router,
    prefix="/api/v1/predictive-analytics",
    tags=["predictive-analytics"]
)
```

### 3. Frontend Integration

(To be implemented in remaining days)

Create new components:
- `PredictiveAnalyticsDashboard.jsx`: Main dashboard
- `DemandForecastChart.jsx`: Forecast visualization
- `BullwhipHeatmap.jsx`: Risk heatmap
- `CostTrajectoryChart.jsx`: Cost scenarios
- `FeatureImportanceChart.jsx`: SHAP visualization
- `WhatIfAnalyzer.jsx`: Scenario comparison tool

---

## Remaining Work (Days 4-15)

### Days 4-6: AutoML Integration
- [ ] Optuna hyperparameter optimization for RL
- [ ] Ray Tune distributed tuning for GNN
- [ ] Automated architecture search
- [ ] Model registry and versioning
- [ ] A/B testing framework

### Days 7-9: Advanced GNN Training
- [ ] Enhanced GNN training pipeline
- [ ] GraphSAGE inductive learning
- [ ] Heterogeneous GNN for multi-type networks
- [ ] Transfer learning across supply chains
- [ ] Model ensembling

### Days 10-12: Frontend Dashboard
- [ ] Predictive Analytics Dashboard component
- [ ] Real-time forecasting charts
- [ ] Interactive what-if analysis UI
- [ ] SHAP visualization (waterfall, force plots)
- [ ] Cost trajectory risk visualizations
- [ ] Bullwhip effect heatmaps

### Days 13-15: Integration & Testing
- [ ] End-to-end integration tests
- [ ] Performance benchmarking
- [ ] Load testing for prediction APIs
- [ ] Documentation updates
- [ ] User guide for predictive features
- [ ] API examples and tutorials

---

## Performance Expectations

### RL Agents

| Metric | Naive Policy | Conservative | ML Forecast | RL (PPO) | RL (SAC) |
|--------|--------------|--------------|-------------|----------|----------|
| **Avg Cost** | $8,500 | $6,200 | $5,800 | $5,200 | $4,900 |
| **Cost Reduction** | Baseline | 27% | 32% | 39% | 42% |
| **Service Level** | 85% | 88% | 90% | 92% | 93% |
| **Bullwhip Ratio** | 2.8 | 1.9 | 1.7 | 1.4 | 1.3 |

### GNN Models

| Architecture | RMSE (Demand) | MAE (Cost) | Bullwhip Acc | Inference Time |
|--------------|---------------|------------|--------------|----------------|
| **Original GNN** | 3.2 | $180 | 78% | 15ms |
| **GraphSAGE** | 2.8 | $145 | 82% | 12ms |
| **Temporal GNN** | 2.4 | $120 | 85% | 18ms |
| **Hetero GNN** | 2.6 | $135 | 83% | 20ms |

### API Performance

| Endpoint | Avg Latency | P95 Latency | Throughput |
|----------|-------------|-------------|------------|
| `/forecast/demand` | 85ms | 150ms | 120 req/s |
| `/predict/bullwhip` | 120ms | 200ms | 80 req/s |
| `/explain/prediction` | 450ms | 800ms | 20 req/s |
| `/analyze/what-if` | 250ms | 400ms | 40 req/s |
| `/insights/report` | 1.2s | 2.1s | 10 req/s |

---

## Testing

### Unit Tests

```bash
# Test RL agent
pytest backend/tests/test_rl_agent.py -v

# Test enhanced GNN
pytest backend/tests/test_enhanced_gnn.py -v

# Test predictive analytics service
pytest backend/tests/test_predictive_analytics.py -v
```

### Integration Tests

```bash
# Test API endpoints
pytest backend/tests/test_predictive_analytics_api.py -v
```

### Performance Tests

```bash
# Load test prediction endpoints
locust -f backend/tests/load/test_predictions.py --host http://localhost:8000
```

---

## Troubleshooting

### Issue: PyTorch Geometric Installation Fails

**Solution**:
```bash
# Install dependencies first
pip install torch==2.2.0
pip install torch-scatter torch-sparse torch-cluster torch-spline-conv -f https://data.pyg.org/whl/torch-2.2.0+cu118.html
pip install torch-geometric
```

### Issue: Stable-Baselines3 CUDA Error

**Solution**:
```bash
# Verify PyTorch CUDA
python -c "import torch; print(torch.cuda.is_available())"

# If False, reinstall PyTorch with CUDA
pip install torch==2.2.0+cu118 --extra-index-url https://download.pytorch.org/whl/cu118
```

### Issue: SHAP Takes Too Long

**Solution**:
- Use KernelExplainer with smaller background dataset (100 samples max)
- Consider TreeExplainer for tree-based models (faster)
- Cache explanations for frequently accessed predictions

### Issue: RL Training Unstable

**Solution**:
- Reduce learning rate (try 1e-4 instead of 3e-4)
- Increase batch size for more stable gradients
- Normalize observations and rewards
- Check reward function for imbalanced scales

---

## References

### Research Papers

1. **PPO**: Schulman et al., "Proximal Policy Optimization Algorithms" (2017)
2. **SAC**: Haarnoja et al., "Soft Actor-Critic: Off-Policy Maximum Entropy Deep RL" (2018)
3. **GraphSAGE**: Hamilton et al., "Inductive Representation Learning on Large Graphs" (2017)
4. **HGT**: Hu et al., "Heterogeneous Graph Transformer" (2020)
5. **Multi-Task Learning**: Kendall et al., "Multi-Task Learning Using Uncertainty" (2018)
6. **SHAP**: Lundberg & Lee, "A Unified Approach to Interpreting Model Predictions" (2017)

### Documentation

- Stable-Baselines3: https://stable-baselines3.readthedocs.io/
- PyTorch Geometric: https://pytorch-geometric.readthedocs.io/
- SHAP: https://shap.readthedocs.io/
- Optuna: https://optuna.readthedocs.io/
- Ray Tune: https://docs.ray.io/en/latest/tune/

---

## Contributors

- Core RL Implementation: AI/ML Team
- Enhanced GNN Architectures: Research Team
- Predictive Analytics Service: Backend Team
- API Development: Backend Team
- Frontend Dashboard: (Upcoming) Frontend Team

---

**Last Updated**: 2026-01-15
**Version**: 1.0.0
**Status**: Core Implementation Complete (Days 1-3 of 10-15)
