# AWS SC Phase 5: Stochastic Modeling Framework

**Phase Started**: 2026-01-13
**Status**: 📋 **PLANNING**
**Prerequisites**: Phase 1-4 Complete ✅

---

## Executive Summary

Phase 5 transforms the Beer Game from a **deterministic simulation** to a **stochastic modeling framework**, enabling realistic modeling of supply chain uncertainty. This phase implements probabilistic distributions for 15 operational variables (lead times, capacities, yields) while maintaining deterministic control variables (inventory policies, pricing).

**Design Document**: [AWS_SC_STOCHASTIC_MODELING_DESIGN.md](AWS_SC_STOCHASTIC_MODELING_DESIGN.md)

---

## Phase 5 Goals

### Primary Objectives

1. **Support 20+ Distribution Types**: From simple (uniform, normal) to advanced (mixture, empirical)
2. **Backward Compatibility**: Deterministic values remain default (existing configs unchanged)
3. **Flexible Sampling**: Independent, correlated, and time-series sampling strategies
4. **Hierarchical Consistency**: Distributions respect existing override logic
5. **Production Ready**: Full testing, documentation, and validation

### Key Benefits

✅ **Realistic Simulations**: Model real-world uncertainty and variability
✅ **Risk Analysis**: Understand supply chain performance under uncertainty
✅ **Scenario Planning**: Test resilience to disruptions and variability
✅ **ML Training Data**: Generate diverse, realistic training datasets
✅ **Academic Research**: Support stochastic supply chain research

---

## Implementation Roadmap

### Sprint 1: Core Distribution Engine (Backend)
**Duration**: 2-3 days
**Lines of Code**: ~800-1,000

**Deliverables**:
- Distribution base class and 20 distribution types
- Sampling engine with strategies (independent, correlated, time-series)
- JSON schema validation and parsing
- Unit tests for all distribution types

**Files to Create**:
- `backend/app/services/stochastic/distribution_engine.py` (~500 lines)
- `backend/app/services/stochastic/distributions.py` (~300 lines)
- `backend/app/services/stochastic/sampling_strategies.py` (~200 lines)
- `backend/scripts/test_distribution_engine.py` (~400 lines)

---

### Sprint 2: Database Schema & Integration
**Duration**: 2-3 days
**Lines of Code**: ~600-800

**Deliverables**:
- Extend 15 database models with distribution fields
- Migration scripts for stochastic field additions
- Backward compatibility layer (deterministic as default)
- Integration with execution cache

**Models to Extend**:
1. **TransportationLane**: `material_flow_lead_time_dist`, `info_flow_lead_time_dist`, `lane_capacity_dist`
2. **ProductionProcess**: `mfg_lead_time_dist`, `cycle_time_dist`, `yield_dist`, `setup_time_dist`, `changeover_time_dist`
3. **ProductionCapacity**: `capacity_dist`
4. **ProductBom**: `scrap_rate_dist`
5. **SourcingRules**: `sourcing_lead_time_dist`
6. **VendorLeadTime**: `lead_time_dist`
7. **Forecast**: `demand_dist`, `forecast_error_dist`

**Files to Create/Modify**:
- `backend/migrations/versions/20260113_stochastic_distributions.py` (~200 lines)
- `backend/app/models/aws_sc_planning.py` (+150 lines)
- `backend/app/models/aws_sc_entities.py` (+150 lines)
- `backend/app/services/aws_sc_planning/execution_cache.py` (+100 lines)

---

### Sprint 3: Execution Adapter Integration
**Duration**: 2-3 days
**Lines of Code**: ~500-700

**Deliverables**:
- Integrate distribution sampling into BeerGameExecutionAdapter
- Replace deterministic values with distribution sampling
- Implement sampling strategies (per-round, per-order, time-series)
- Performance optimization for sampling overhead

**Key Changes**:
- Sample lead times from distributions during order/shipment creation
- Sample capacities during capacity checks
- Sample yields during production
- Cache sampled values when appropriate

**Files to Modify**:
- `backend/app/services/aws_sc_planning/beer_game_execution_adapter.py` (+300 lines)
- `backend/app/services/mixed_game_service.py` (+50 lines)

**Integration Points**:
- `_create_transfer_order()`: Sample material/info lead times
- `create_work_orders_with_capacity()`: Sample capacity values
- `_process_bom_transformation()`: Sample yields and scrap rates
- Round initialization: Sample per-round stochastic values

---

### Sprint 4: Admin UI & Configuration
**Duration**: 2-3 days
**Lines of Code**: ~800-1,000

**Deliverables**:
- Distribution builder UI component
- Visual distribution preview (histogram/PDF)
- Pre-configured distribution templates
- Game config UI for stochastic settings

**Components to Create**:
- `DistributionBuilder.jsx`: Visual distribution editor (~300 lines)
- `DistributionPreview.jsx`: Chart showing distribution shape (~150 lines)
- `StochasticConfigPanel.jsx`: Game-level stochastic settings (~200 lines)
- `DistributionTemplates.jsx`: Pre-built distribution library (~150 lines)

**Features**:
- **Distribution Builder**:
  - Dropdown to select distribution type
  - Dynamic form for distribution parameters
  - Real-time validation and preview
  - Save/load distribution configs

- **Distribution Preview**:
  - Histogram visualization (1000 samples)
  - PDF/CDF overlay
  - Summary statistics (mean, stddev, percentiles)

- **Templates**:
  - "Low Variability" (CV=10%)
  - "Medium Variability" (CV=25%)
  - "High Variability" (CV=50%)
  - "Disruption Risk" (mixture distribution)

**Files to Create**:
- `frontend/src/components/stochastic/DistributionBuilder.jsx` (~300 lines)
- `frontend/src/components/stochastic/DistributionPreview.jsx` (~150 lines)
- `frontend/src/components/stochastic/StochasticConfigPanel.jsx` (~200 lines)
- `frontend/src/components/stochastic/DistributionTemplates.jsx` (~150 lines)

---

### Sprint 5: Analytics & Visualization
**Duration**: 2-3 days
**Lines of Code**: ~600-800

**Deliverables**:
- Stochastic analytics service (variance, confidence intervals)
- Stochastic analytics dashboard tab
- Monte Carlo simulation runner
- Scenario comparison tools

**Analytics to Add**:
- **Variability Metrics**:
  - Standard deviation of lead times, capacities, yields
  - Coefficient of variation (CV)
  - Range (min/max observed)

- **Distribution Fit Analysis**:
  - Observed vs. configured distribution comparison
  - Goodness-of-fit tests (Kolmogorov-Smirnov)
  - Q-Q plots

- **Monte Carlo Analysis**:
  - Run N simulations with stochastic sampling
  - Confidence intervals for costs, service levels
  - Risk metrics (VaR, CVaR)

**Files to Create**:
- `backend/app/services/stochastic_analytics_service.py` (~300 lines)
- `backend/app/api/endpoints/stochastic_analytics.py` (~150 lines)
- `frontend/src/components/analytics/StochasticAnalytics.jsx` (~300 lines)
- `backend/scripts/monte_carlo_runner.py` (~200 lines)

---

## Technical Architecture

### Backend Stack

**Distribution Engine**:
```python
class Distribution(ABC):
    """Base class for all distributions"""
    @abstractmethod
    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        pass

    @abstractmethod
    def pdf(self, x: np.ndarray) -> np.ndarray:
        pass

    @abstractmethod
    def to_dict(self) -> Dict:
        pass

    @classmethod
    @abstractmethod
    def from_dict(cls, config: Dict) -> 'Distribution':
        pass

class NormalDistribution(Distribution):
    def __init__(self, mean: float, stddev: float, min: Optional[float] = None, max: Optional[float] = None):
        self.mean = mean
        self.stddev = stddev
        self.min = min
        self.max = max

    def sample(self, size: int = 1, seed: Optional[int] = None) -> np.ndarray:
        rng = np.random.default_rng(seed)
        samples = rng.normal(self.mean, self.stddev, size)
        if self.min is not None:
            samples = np.maximum(samples, self.min)
        if self.max is not None:
            samples = np.minimum(samples, self.max)
        return samples

    def to_dict(self) -> Dict:
        return {
            'type': 'normal',
            'mean': self.mean,
            'stddev': self.stddev,
            'min': self.min,
            'max': self.max
        }

    @classmethod
    def from_dict(cls, config: Dict) -> 'NormalDistribution':
        return cls(
            mean=config['mean'],
            stddev=config['stddev'],
            min=config.get('min'),
            max=config.get('max')
        )
```

**Distribution Factory**:
```python
class DistributionFactory:
    _registry = {
        'deterministic': DeterministicDistribution,
        'uniform': UniformDistribution,
        'normal': NormalDistribution,
        'lognormal': LognormalDistribution,
        'triangular': TriangularDistribution,
        'gamma': GammaDistribution,
        'beta': BetaDistribution,
        'poisson': PoissonDistribution,
        'empirical': EmpiricalDistribution,
        'mixture': MixtureDistribution,
        # ... 20 total
    }

    @classmethod
    def create(cls, config: Dict) -> Distribution:
        dist_type = config.get('type', 'deterministic')
        if dist_type not in cls._registry:
            raise ValueError(f"Unknown distribution type: {dist_type}")
        return cls._registry[dist_type].from_dict(config)
```

**Sampling Strategies**:
```python
class SamplingStrategy(ABC):
    @abstractmethod
    def sample(self, distributions: Dict[str, Distribution], seed: Optional[int] = None) -> Dict[str, float]:
        pass

class IndependentSampling(SamplingStrategy):
    """Sample each distribution independently"""
    def sample(self, distributions: Dict[str, Distribution], seed: Optional[int] = None) -> Dict[str, float]:
        return {key: dist.sample(1, seed)[0] for key, dist in distributions.items()}

class CorrelatedSampling(SamplingStrategy):
    """Sample with correlation matrix"""
    def __init__(self, correlation_matrix: np.ndarray):
        self.correlation_matrix = correlation_matrix

    def sample(self, distributions: Dict[str, Distribution], seed: Optional[int] = None) -> Dict[str, float]:
        # Use Cholesky decomposition for correlated sampling
        pass

class TimeSeriesSampling(SamplingStrategy):
    """Sample with autocorrelation (AR/ARIMA)"""
    def __init__(self, ar_coeff: float = 0.5):
        self.ar_coeff = ar_coeff
        self.prev_values = {}

    def sample(self, distributions: Dict[str, Distribution], seed: Optional[int] = None) -> Dict[str, float]:
        # AR(1) process: X_t = ar_coeff * X_{t-1} + epsilon_t
        pass
```

### Database Schema

**JSON Field Format** (PostgreSQL JSONB):
```json
{
  "material_flow_lead_time_dist": {
    "type": "normal",
    "mean": 7.0,
    "stddev": 1.5,
    "min": 3.0,
    "max": 12.0,
    "seed": 42
  },
  "lane_capacity_dist": {
    "type": "truncated_normal",
    "mean": 100.0,
    "stddev": 15.0,
    "min": 50.0,
    "max": 150.0
  },
  "yield_dist": {
    "type": "beta",
    "alpha": 90.0,
    "beta": 10.0,
    "min": 0.85,
    "max": 1.0
  }
}
```

**Backward Compatibility**:
- If `*_dist` field is NULL → Use deterministic value from existing field
- If `*_dist` is `{"type": "deterministic", "value": X}` → Equivalent to NULL
- All existing configs continue to work without modification

### Frontend Components

**Distribution Builder UI**:
```jsx
const DistributionBuilder = ({ value, onChange, variable }) => {
  const [distType, setDistType] = useState(value?.type || 'deterministic');
  const [params, setParams] = useState(value || {});
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    // Generate preview samples
    fetchDistributionPreview(params).then(setPreview);
  }, [params]);

  const handleTypeChange = (newType) => {
    setDistType(newType);
    setParams(getDefaultParams(newType));
  };

  const handleParamChange = (param, value) => {
    const newParams = { ...params, [param]: value };
    setParams(newParams);
    onChange(newParams);
  };

  return (
    <Box>
      <FormControl fullWidth>
        <InputLabel>Distribution Type</InputLabel>
        <Select value={distType} onChange={(e) => handleTypeChange(e.target.value)}>
          <MenuItem value="deterministic">Deterministic (Fixed Value)</MenuItem>
          <MenuItem value="uniform">Uniform</MenuItem>
          <MenuItem value="normal">Normal (Gaussian)</MenuItem>
          <MenuItem value="lognormal">Lognormal</MenuItem>
          <MenuItem value="triangular">Triangular</MenuItem>
          <MenuItem value="gamma">Gamma</MenuItem>
          <MenuItem value="beta">Beta</MenuItem>
          <MenuItem value="poisson">Poisson</MenuItem>
          {/* ... 20 total */}
        </Select>
      </FormControl>

      {/* Dynamic parameter inputs based on distType */}
      <DynamicParams distType={distType} params={params} onChange={handleParamChange} />

      {/* Distribution preview */}
      {preview && <DistributionPreview data={preview} />}
    </Box>
  );
};
```

---

## Distribution Type Catalog

### 1. Basic Distributions

**Deterministic** (Backward Compatible Default):
```json
{
  "type": "deterministic",
  "value": 7.0
}
```

**Uniform** (All values equally likely):
```json
{
  "type": "uniform",
  "min": 5.0,
  "max": 10.0
}
```

**Discrete Uniform** (Integer uniform):
```json
{
  "type": "discrete_uniform",
  "min": 3,
  "max": 12
}
```

### 2. Symmetric Distributions

**Normal (Gaussian)**:
```json
{
  "type": "normal",
  "mean": 7.0,
  "stddev": 1.5,
  "min": 3.0,
  "max": 12.0
}
```

**Truncated Normal**:
```json
{
  "type": "truncated_normal",
  "mean": 7.0,
  "stddev": 2.0,
  "min": 4.0,
  "max": 10.0
}
```

**Triangular** (Three-point estimate):
```json
{
  "type": "triangular",
  "min": 5.0,
  "mode": 7.0,
  "max": 12.0
}
```

### 3. Right-Skewed Distributions

**Lognormal** (Right-skewed, non-negative):
```json
{
  "type": "lognormal",
  "mean_log": 2.0,
  "stddev_log": 0.3,
  "min": 0.0,
  "max": 50.0
}
```

**Gamma** (Flexible right-skewed):
```json
{
  "type": "gamma",
  "shape": 2.0,
  "scale": 3.5,
  "min": 0.0
}
```

**Weibull** (Time-to-failure):
```json
{
  "type": "weibull",
  "shape": 2.0,
  "scale": 8.0
}
```

**Exponential** (Memoryless):
```json
{
  "type": "exponential",
  "rate": 0.15
}
```

### 4. Bounded Distributions

**Beta** (Bounded [0,1] for percentages):
```json
{
  "type": "beta",
  "alpha": 90.0,
  "beta": 10.0,
  "min": 0.85,
  "max": 1.0
}
```

### 5. Discrete Count Distributions

**Poisson** (Discrete counts):
```json
{
  "type": "poisson",
  "lambda": 5.0
}
```

**Binomial** (Successes in n trials):
```json
{
  "type": "binomial",
  "n": 100,
  "p": 0.95
}
```

**Negative Binomial** (Overdispersed Poisson):
```json
{
  "type": "negative_binomial",
  "r": 5,
  "p": 0.7
}
```

### 6. Data-Driven Distributions

**Empirical Discrete** (User-defined):
```json
{
  "type": "empirical_discrete",
  "values": [5, 7, 10, 14],
  "probabilities": [0.2, 0.5, 0.25, 0.05]
}
```

**Empirical Continuous** (From samples):
```json
{
  "type": "empirical_continuous",
  "samples": [6.2, 7.1, 6.8, 7.5, 8.2, ...]
}
```

**Piecewise Linear CDF**:
```json
{
  "type": "piecewise_linear_cdf",
  "breakpoints": [0, 5, 10, 15, 20],
  "cdf_values": [0.0, 0.2, 0.7, 0.95, 1.0]
}
```

### 7. Advanced Distributions

**Mixture** (Combination of distributions):
```json
{
  "type": "mixture",
  "components": [
    {
      "weight": 0.9,
      "distribution": {
        "type": "normal",
        "mean": 7.0,
        "stddev": 1.0
      }
    },
    {
      "weight": 0.1,
      "distribution": {
        "type": "uniform",
        "min": 15.0,
        "max": 25.0
      }
    }
  ]
}
```
**Use Case**: Normal operations (90%) + disruptions (10%)

**Categorical** (Named categories):
```json
{
  "type": "categorical",
  "categories": ["low", "medium", "high"],
  "probabilities": [0.2, 0.6, 0.2],
  "mappings": {"low": 5.0, "medium": 10.0, "high": 20.0}
}
```

---

## Variable Classification

### ✅ Stochastic Operational Variables (15)

Variables that describe **how the supply chain operates**:

| Variable | Current Field | New Distribution Field | Recommended Distributions |
|----------|---------------|------------------------|---------------------------|
| **Material Flow Lead Time** | `material_flow_lead_time` | `material_flow_lead_time_dist` | Normal, Lognormal, Gamma |
| **Information Flow Lead Time** | `information_flow_lead_time` | `info_flow_lead_time_dist` | Discrete Uniform, Poisson |
| **Lane Capacity** | `capacity` | `lane_capacity_dist` | Truncated Normal, Gamma |
| **Manufacturing Lead Time** | `manufacturing_lead_time` | `mfg_lead_time_dist` | Lognormal, Gamma |
| **Production Cycle Time** | `cycle_time` | `cycle_time_dist` | Normal, Weibull |
| **Manufacturing Yield** | `yield_pct` | `yield_dist` | Beta, Truncated Normal |
| **Production Capacity** | `max_capacity_per_period` | `capacity_dist` | Truncated Normal, Gamma |
| **Setup Time** | `setup_time` | `setup_time_dist` | Lognormal, Triangular |
| **Changeover Time** | `changeover_time` | `changeover_time_dist` | Triangular, Gamma |
| **Component Scrap Rate** | `scrap_pct` | `scrap_rate_dist` | Beta, Binomial |
| **Sourcing Lead Time** | `lead_time_days` | `sourcing_lead_time_dist` | Lognormal, Gamma |
| **Vendor Lead Time** | `lead_time_days` | `vendor_lead_time_dist` | Truncated Normal, Mixture |
| **Market Demand** | `quantity` | `demand_dist` | Poisson, Negative Binomial |
| **Order Aging/Spoilage** | - | `aging_dist` | Exponential, Weibull |
| **Demand Forecast Error** | - | `forecast_error_dist` | Normal, Laplace |

### ❌ Deterministic Control Variables (Remain Fixed)

Variables that **govern/control** supply chain behavior:

- **Inventory Policies**: target_qty, min_qty, max_qty, reorder_point, order_qty, service_level
- **Financial Parameters**: holding_cost, backlog_cost, selling_price, unit_cost
- **Policy Constraints**: min_order_qty, max_order_qty, qty_multiple
- **Planning Parameters**: frozen_horizon_days, planning_time_fence

---

## Use Cases

### 1. Risk Analysis
**Scenario**: Assess supply chain performance under lead time uncertainty

**Configuration**:
```json
{
  "material_flow_lead_time_dist": {
    "type": "mixture",
    "components": [
      {
        "weight": 0.95,
        "distribution": {"type": "normal", "mean": 7.0, "stddev": 1.0}
      },
      {
        "weight": 0.05,
        "distribution": {"type": "uniform", "min": 20.0, "max": 30.0}
      }
    ]
  }
}
```

**Analysis**:
- Run 1000 Monte Carlo simulations
- Calculate 95% confidence intervals for costs
- Identify scenarios leading to stockouts
- Measure resilience to disruptions

### 2. Capacity Planning
**Scenario**: Understand capacity utilization variability

**Configuration**:
```json
{
  "capacity_dist": {
    "type": "truncated_normal",
    "mean": 100.0,
    "stddev": 15.0,
    "min": 60.0,
    "max": 120.0
  },
  "yield_dist": {
    "type": "beta",
    "alpha": 90.0,
    "beta": 10.0,
    "min": 0.85,
    "max": 1.0
  }
}
```

**Analysis**:
- Track actual capacity usage distribution
- Calculate probability of exceeding capacity
- Optimize capacity buffer levels
- Evaluate impact of yield variability

### 3. Vendor Reliability
**Scenario**: Model supplier performance variability

**Configuration**:
```json
{
  "vendor_lead_time_dist": {
    "type": "mixture",
    "components": [
      {
        "weight": 0.85,
        "distribution": {"type": "triangular", "min": 5.0, "mode": 7.0, "max": 10.0}
      },
      {
        "weight": 0.15,
        "distribution": {"type": "uniform", "min": 15.0, "max": 25.0}
      }
    ]
  }
}
```

**Analysis**:
- Evaluate vendor on-time performance
- Compare vendor reliability
- Optimize safety stock levels
- Assess dual-sourcing benefits

### 4. Demand Forecasting
**Scenario**: Model forecast uncertainty

**Configuration**:
```json
{
  "demand_dist": {
    "type": "negative_binomial",
    "r": 10,
    "p": 0.7
  },
  "forecast_error_dist": {
    "type": "normal",
    "mean": 0.0,
    "stddev": 0.15,
    "min": -0.5,
    "max": 0.5
  }
}
```

**Analysis**:
- Quantify forecast error impact
- Optimize forecast-driven inventory policies
- Calculate safety stock requirements
- Evaluate forecast accuracy metrics

---

## Testing Strategy

### Unit Tests (Per Distribution)
- Sample generation (validate shape, bounds)
- PDF/CDF calculation accuracy
- JSON serialization/deserialization
- Edge cases (extreme parameters, invalid inputs)

### Integration Tests
- Distribution factory creation
- Database field storage/retrieval
- Execution adapter sampling
- Cache integration

### System Tests
- Full game with stochastic distributions
- Monte Carlo simulation (100 runs)
- Validate statistical properties (mean, variance)
- Performance benchmarks (sampling overhead)

### Validation Tests
- Known distribution properties (e.g., Normal mean/stddev)
- Goodness-of-fit tests (K-S test)
- Reproducibility with seeds
- Numerical stability

---

## Performance Considerations

### Sampling Overhead
- **Target**: <5% overhead per round
- **Optimization**: Cache sampled values when appropriate
- **Batch Sampling**: Sample multiple values at once

### Memory Usage
- **Concern**: Distribution objects stored in cache
- **Mitigation**: Lazy loading, share distributions across similar entities

### Database Storage
- **JSONB Fields**: Efficient storage and indexing
- **Migration**: No data duplication, backward compatible

---

## Documentation

### User Documentation
1. **Distribution Guide**: Explanation of each distribution type with use cases
2. **Configuration Tutorial**: Step-by-step guide to configure stochastic variables
3. **Best Practices**: Recommendations for distribution selection
4. **Templates Library**: Pre-configured distributions for common scenarios

### Developer Documentation
1. **Architecture Overview**: System design and integration points
2. **API Reference**: Distribution classes and methods
3. **Extension Guide**: How to add new distribution types
4. **Testing Guide**: Unit and integration testing patterns

### Academic Documentation
1. **Mathematical Foundations**: Distribution formulas and properties
2. **Sampling Algorithms**: Implementation details
3. **Validation Methods**: Statistical tests and verification
4. **Research Applications**: Example research use cases

---

## Migration & Rollout

### Phase 5.0: Foundation (Sprint 1-2)
- Core distribution engine
- Database schema extensions
- Backward compatibility ensured

### Phase 5.1: Integration (Sprint 3)
- Execution adapter integration
- Basic stochastic gameplay
- Performance optimization

### Phase 5.2: UI & Analytics (Sprint 4-5)
- Admin UI for distribution configuration
- Stochastic analytics dashboard
- Monte Carlo simulation tools

### Phase 5.3: Production (Testing & Docs)
- Comprehensive testing
- Documentation completion
- Template library
- Production deployment

---

## Success Criteria

### Functional Requirements ✅
- [ ] All 20 distribution types implemented and tested
- [ ] 15 operational variables support distributions
- [ ] Backward compatibility maintained (100% of existing configs work)
- [ ] Distribution builder UI functional
- [ ] Stochastic analytics dashboard operational

### Performance Requirements ✅
- [ ] Sampling overhead <5% per round
- [ ] Distribution preview renders <500ms
- [ ] Monte Carlo simulation (100 runs) completes <30 seconds
- [ ] Database queries maintain sub-second response time

### Quality Requirements ✅
- [ ] Unit test coverage >90%
- [ ] Integration tests pass 100%
- [ ] Statistical validation tests pass (K-S, chi-square)
- [ ] Documentation complete (user + developer)
- [ ] Code review approved

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Sampling Overhead** | Medium | High | Profile and optimize hot paths, batch sampling |
| **Complexity Creep** | High | Medium | Strict scope control, defer advanced features |
| **Backward Compatibility Break** | Low | High | Comprehensive regression testing, deterministic as default |
| **User Confusion** | Medium | Medium | Simple UI, templates, documentation, examples |
| **Statistical Accuracy** | Low | High | Validation tests, use numpy/scipy, expert review |

---

## Dependencies

### External Libraries
- **NumPy**: Distribution sampling and numerical operations
- **SciPy**: Advanced distributions (beta, gamma, etc.)
- **Matplotlib/Plotly**: Distribution preview visualization

### Internal Dependencies
- Phase 1-4 complete ✅
- Execution cache (Phase 3 Sprint 1) ✅
- Database models (Phase 2) ✅
- Admin UI framework (existing) ✅

---

## Estimated Timeline

| Sprint | Duration | Lines of Code | Effort |
|--------|----------|---------------|--------|
| **Sprint 1**: Distribution Engine | 2-3 days | 800-1,000 | High |
| **Sprint 2**: Database Schema | 2-3 days | 600-800 | Medium |
| **Sprint 3**: Adapter Integration | 2-3 days | 500-700 | High |
| **Sprint 4**: Admin UI | 2-3 days | 800-1,000 | Medium |
| **Sprint 5**: Analytics | 2-3 days | 600-800 | Medium |
| **Testing & Docs** | 1-2 days | 400-600 | Medium |
| **Total** | **12-17 days** | **3,700-4,900** | - |

---

## Conclusion

Phase 5 represents a major capability upgrade, transforming The Beer Game from a deterministic simulation to a comprehensive stochastic modeling platform. This enables realistic supply chain research, risk analysis, and advanced ML training data generation while maintaining full backward compatibility.

**Next Steps**:
1. Review and approve this plan
2. Begin Sprint 1: Core Distribution Engine
3. Iterative development with testing at each sprint
4. Production deployment with documentation

---

**Phase 5 Plan Completed By**: Claude Sonnet 4.5
**Plan Creation Date**: 2026-01-13
**Ready for Implementation**: Yes ✅

🚀 **Phase 5 planning complete! Ready to transform The Beer Game into a stochastic modeling platform.**
